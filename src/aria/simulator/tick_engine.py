"""Central subsystem tick engine.

Every registered subsystem has a ``tick(dt_s: float)`` method. The engine
advances them in a deterministic order per simulation second, publishes
events to the bus, and exposes a single ``advance(dt_s)`` entry point so
the HTTP layer and the React UI only need to know one call.

Ordering matters: reactor first (produces power), power distribution
second, then thermal / propulsion / ECLSS / habitat / avionics. A
subsystem can depend on the *previous* tick's output of earlier-ordered
subsystems — this is standard engineering-sim explicit integration,
OK when dt_s is sub-second.

Typical usage:

    engine = get_tick_engine()
    engine.advance(dt_s=1.0)    # 1 simulated second
    engine.advance(dt_s=60.0)   # 1 minute (internally substepped)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller
from aria.simulator.startup_sequence import get_startup_controller


class TickableProtocol(Protocol):
    """Minimal interface a subsystem must satisfy to join the tick engine."""

    name: str

    def tick(self, dt_s: float) -> None:
        ...


@dataclass
class _Tickable:
    """Internal wrapper carrying tick order + the callback."""

    order: int
    name: str
    fn: Callable[[float], None]


@dataclass
class TickEngine:
    """Drives every subsystem + mission/startup controllers in lockstep."""

    # Sorted list of registered tickables (lowest order first)
    tickables: List[_Tickable] = field(default_factory=list)
    # Substep length — larger dt_s than this gets chopped into MAX_SUBSTEP chunks
    MAX_SUBSTEP_S: float = 60.0
    # Rolling stats
    total_sim_time_s: float = 0.0
    tick_count: int = 0
    last_wall_ms: float = 0.0

    # ── registration ─────────────────────────────────────────

    def register(self, name: str, fn: Callable[[float], None], *, order: int = 50) -> None:
        """Register a subsystem tick. `order` sorts low→high; defaults to 50.

        Suggested order bands:
            10-19  power source  (reactor)
            20-29  distribution  (power bus)
            30-39  propulsion + thermal
            40-49  consumption   (eclss, habitat, avionics, comms)
            50-59  sensors + safety
            60+    bookkeeping (logging, archival)
        """
        existing = [t for t in self.tickables if t.name == name]
        for t in existing:
            self.tickables.remove(t)
        self.tickables.append(_Tickable(order=order, name=name, fn=fn))
        self.tickables.sort(key=lambda t: (t.order, t.name))

    def unregister(self, name: str) -> bool:
        before = len(self.tickables)
        self.tickables = [t for t in self.tickables if t.name != name]
        return len(self.tickables) < before

    def registered_names(self) -> List[str]:
        return [t.name for t in self.tickables]

    # ── tick ─────────────────────────────────────────────────

    def advance(self, dt_s: float) -> None:
        """Advance the simulator by dt_s seconds, substepping as needed."""
        if dt_s <= 0:
            return
        from aria.simulator import telemetry_otel as otel
        bus = get_event_bus()
        phase = get_phase_controller()
        t0 = time.perf_counter()
        remaining = dt_s
        with otel.span("tick_engine.advance",
                       **{"aria.dt_s": float(dt_s),
                          "aria.sim_yr_start": float(phase.elapsed_yr)}):
            while remaining > 0:
                step = min(remaining, self.MAX_SUBSTEP_S)
                step_yr = step / (365.25 * 24 * 3600)
                with otel.span("tick_engine.substep",
                               **{"aria.step_s": float(step)}):
                    # 0) Advance the central mission clock BEFORE any
                    # subsystem runs.  Every consumer (trajectory_state,
                    # phase controller, advisor, status strip) reads the
                    # clock in `t.fn(step)` below, so they all see exactly
                    # the same T+ value within a substep.  Without this,
                    # callers that drive `engine.advance()` directly (any
                    # integration test, or any future scheduler) leave
                    # MissionClock frozen at 0 — which broke the
                    # ARRIVAL→ORBIT auto-transition (1-day stabilisation
                    # window keyed off elapsed_yr never elapsed).  See
                    # `tests/integration/test_mission_end_to_end.py
                    # ::test_moon_mission_reaches_orbit`.
                    if step_yr > 0:
                        try:
                            from aria.core.mission_clock import get_mission_clock
                            get_mission_clock().advance(step_yr)
                        except Exception:
                            pass
                    # 1) Advance startup sequence
                    get_startup_controller().tick(step)
                    # 2) Advance every registered subsystem in order
                    for t in self.tickables:
                        with otel.span(f"subsystem.{t.name}",
                                       **{"aria.subsystem": t.name,
                                          "aria.order": t.order}) as sub_span:
                            try:
                                t.fn(step)
                            except Exception as e:
                                # Record on the subsystem span *and*
                                # publish the legacy bus event so old
                                # consumers keep working.
                                sub_span.record_exception(e)
                                try:
                                    from opentelemetry.trace import Status, StatusCode
                                    sub_span.set_status(Status(StatusCode.ERROR, str(e)[:200]))
                                except Exception:
                                    pass
                                bus.publish(
                                    "tick.subsystem_error",
                                    severity="warning",
                                    source="tick_engine",
                                    payload={"subsystem": t.name, "error": str(e)},
                                    sim_time_yr=phase.elapsed_yr,
                                )
                    # 3) Advance mission phase clock (dt_s → years)
                    phase.tick(step / (365.25 * 24 * 3600))
                    remaining -= step
        self.total_sim_time_s += dt_s
        self.tick_count += 1
        self.last_wall_ms = (time.perf_counter() - t0) * 1000.0
        bus.publish(
            "tick.advanced",
            severity="debug",
            source="tick_engine",
            payload={"dt_s": dt_s, "wall_ms": round(self.last_wall_ms, 2),
                     "registered": len(self.tickables)},
            sim_time_yr=phase.elapsed_yr,
        )

    # ── serialisation for HTTP ───────────────────────────────

    def to_dict(self) -> dict:
        return {
            "registered":       [t.name for t in self.tickables],
            "registered_order": [(t.order, t.name) for t in self.tickables],
            "total_sim_time_s": round(self.total_sim_time_s, 2),
            "tick_count":       self.tick_count,
            "last_wall_ms":     round(self.last_wall_ms, 3),
        }


_DEFAULT_ENGINE: Optional[TickEngine] = None
_DEFAULT_ENGINE_LOCK = threading.Lock()


def get_tick_engine() -> TickEngine:
    # R65 (2026-04-24): locked double-check — two threads hitting this
    # in parallel (HTTP handler + auto-tick daemon) could each build a
    # fresh TickEngine, then subsystem registrations would be split
    # across two engines and half the simulation would never advance.
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is not None:
        return _DEFAULT_ENGINE
    with _DEFAULT_ENGINE_LOCK:
        if _DEFAULT_ENGINE is None:
            _DEFAULT_ENGINE = TickEngine()
        return _DEFAULT_ENGINE


def reset_tick_engine() -> None:
    global _DEFAULT_ENGINE
    with _DEFAULT_ENGINE_LOCK:
        _DEFAULT_ENGINE = TickEngine()
