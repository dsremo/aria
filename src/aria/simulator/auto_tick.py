"""Background auto-tick thread — runs the simulation in real-ish time.

Lets the React UI press "Play" instead of clicking +1 hr repeatedly.
A daemon thread wakes every `wall_interval_s` and calls
`engine.advance(sim_dt_s)`. Sim/wall ratio is the user-chosen "speed":

    speed_factor = 1     → real-time (1 sim-second per wall-second)
    speed_factor = 60    → 1 sim-minute per wall-second
    speed_factor = 3600  → 1 sim-hour per wall-second
    speed_factor = 86400 → 1 sim-day per wall-second

Public API: start / stop / set_speed / status. All idempotent.

Concurrency: one daemon thread, locked status object, the engine itself
is single-threaded so there's no contention except via the lock.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AutoTickStatus:
    running: bool = False
    speed_factor: float = 60.0       # default 1 sim-min per wall-sec
    # BUG-025/026 (2026-04-24): shortened from 0.5 → 0.1 s.  Shorter
    # ticks mean Pause reacts faster (max one tick of leaked sim-time
    # post-click) and preset labels match observed rate more closely
    # at high speeds.  Overhead is ~10 Hz engine.advance calls which
    # is negligible for the current physics budget.
    wall_interval_s: float = 0.1
    started_at_wall: Optional[float] = None
    cumulative_sim_s: float = 0.0
    cumulative_wall_s: float = 0.0
    tick_count: int = 0
    last_error: Optional[str] = None


class AutoTickRunner:
    """Daemon thread driving the global tick engine."""

    def __init__(self) -> None:
        self.status = AutoTickStatus()
        self._lock = threading.RLock()
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── control ──────────────────────────────────────────────

    def start(self, speed_factor: float = 60.0, wall_interval_s: float = 0.5) -> None:
        with self._lock:
            if self.status.running:
                self.status.speed_factor = float(speed_factor)
                self.status.wall_interval_s = float(wall_interval_s)
                return
            self.status.running = True
            self.status.speed_factor = float(speed_factor)
            self.status.wall_interval_s = float(wall_interval_s)
            self.status.started_at_wall = time.time()
            self.status.last_error = None
            self._stop_evt.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True, name="aria-autotick")
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self.status.running = False
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def set_speed(self, speed_factor: float) -> None:
        with self._lock:
            self.status.speed_factor = float(speed_factor)

    # ── loop ────────────────────────────────────────────────

    def _loop(self) -> None:
        # Lazy-register every default subsystem so tick is fully wired
        from aria.simulator.tick_engine import get_tick_engine
        from aria.simulator.event_bus import get_event_bus
        engine = get_tick_engine()

        # Wire up every subsystem we know about (idempotent)
        wire_default_subsystems()
        bus = get_event_bus()
        bus.publish("auto_tick.started",
                    severity="info", source="auto_tick",
                    payload={"speed_factor": self.status.speed_factor})
        last_wall = time.time()
        while not self._stop_evt.is_set():
            t0 = time.time()
            wall_dt = t0 - last_wall
            last_wall = t0
            # R65 (2026-04-24) D-4: read the tunables under the lock so a
            # mid-flight set_speed() can't tear the float read on 32-bit
            # Python or interleave with our capture.  Capture once, use
            # consistently for the remainder of this iteration.
            with self._lock:
                speed_factor = self.status.speed_factor
                wall_interval = self.status.wall_interval_s
            # BUG-026 (2026-04-24, walkthrough): two feedback problems
            # were producing label-mismatched rates:
            #   1. wall_dt grew when engine.advance took longer than
            #      the target interval, which inflated sim_dt, which
            #      made the next engine.advance slower (positive
            #      feedback → 1 yr/s ran as 2.4 yr/s).
            #   2. The obvious fix `min(wall_dt, wall_interval)`
            #      under-shot: if engine.advance itself takes 1 s
            #      (regardless of interval), capping wall_dt to 0.1 s
            #      divides the realised rate by 10×.
            # Compromise: cap each tick at 1 yr of sim-time so a stuck
            # engine.advance can't sprint through centuries, but let
            # wall_dt × speed_factor otherwise pass through so the
            # realised rate still tracks real wall-clock elapsed.
            _MAX_SIM_DT_S = 365.25 * 24 * 3600    # one Julian year per tick
            sim_dt_s = min(wall_dt * speed_factor, _MAX_SIM_DT_S)
            # BUG-025 (2026-04-24, walkthrough): re-check the stop flag
            # right before the expensive `engine.advance` call.  If the
            # operator hit PAUSE during our sleep window, we skip this
            # tick entirely — previously one extra iteration always
            # fired post-pause, leaking sim-time into the "paused"
            # display.
            if self._stop_evt.is_set():
                break
            try:
                # R7+R36 (2026-04-25, sync refactor): tick_engine.advance()
                # now owns the SINGLE mission clock + phase-controller
                # advance internally (per-substep, atomic with the
                # subsystem fan-out).  Callers — this worker, integration
                # tests, future schedulers — get a consistent monotonic
                # T+ without having to remember to advance both clocks
                # before / after dispatching subsystems.  Previously, only
                # this worker did so → integration tests that drove
                # engine.advance() directly left MissionClock frozen at 0.
                engine.advance(sim_dt_s)
                with self._lock:
                    self.status.cumulative_sim_s += sim_dt_s
                    self.status.cumulative_wall_s += wall_dt
                    self.status.tick_count += 1
            except Exception as e:
                with self._lock:
                    self.status.last_error = f"{type(e).__name__}: {e}"
                bus.publish("auto_tick.error",
                            severity="critical", source="auto_tick",
                            payload={"error": str(e)})
                break
            # Sleep the remainder of the interval (also read under lock)
            with self._lock:
                wall_interval = self.status.wall_interval_s
            remaining = wall_interval - (time.time() - t0)
            if remaining > 0:
                self._stop_evt.wait(remaining)
        bus.publish("auto_tick.stopped",
                    severity="info", source="auto_tick",
                    payload={"cumulative_sim_s": self.status.cumulative_sim_s,
                             "cumulative_wall_s": self.status.cumulative_wall_s})

    # ── status ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "running": self.status.running,
                "speed_factor": self.status.speed_factor,
                "wall_interval_s": self.status.wall_interval_s,
                "started_at_wall": self.status.started_at_wall,
                "cumulative_sim_s": round(self.status.cumulative_sim_s, 2),
                "cumulative_sim_yr": round(self.status.cumulative_sim_s / (365.25 * 24 * 3600), 4),
                "cumulative_wall_s": round(self.status.cumulative_wall_s, 2),
                "tick_count": self.status.tick_count,
                "last_error": self.status.last_error,
            }


def wire_default_subsystems() -> None:
    """Idempotently register every known subsystem with the tick engine."""
    from aria.simulator.tick_engine import get_tick_engine
    engine = get_tick_engine()

    registrations = [
        ("computing_radiation", "aria.simulator.computing_radiation"),
        ("eclss_contaminants",  "aria.simulator.eclss_contaminants"),
        ("bearing_dynamics",    "aria.simulator.bearing_dynamics"),
        ("propulsion_thermal",  "aria.simulator.propulsion_thermal"),
        ("power_tracker",       "aria.simulator.power_tracker"),
        ("trajectory_state",    "aria.simulator.trajectory_state"),
        ("fuel_tracker",        "aria.simulator.fuel_tracker"),
        ("crew_health",         "aria.simulator.crew_health"),
        ("comms_budget",        "aria.simulator.comms_budget"),
        ("agriculture_yield",   "aria.simulator.agriculture_yield"),
        ("event_scheduler",     "aria.simulator.event_scheduler"),
        ("hull_damage",         "aria.simulator.hull_damage"),
        ("random_events",       "aria.simulator.random_events"),
        ("mission_objectives",  "aria.simulator.mission_objectives"),
        ("crew_schedule",       "aria.simulator.crew_schedule"),
        ("repair_queue",        "aria.simulator.repair_queue"),
    ]
    import importlib
    for name, modpath in registrations:
        if name in engine.registered_names():
            continue
        try:
            mod = importlib.import_module(modpath)
            mod.register_with_tick_engine()
        except Exception:
            pass


_DEFAULT_RUNNER: Optional[AutoTickRunner] = None
_DEFAULT_RUNNER_LOCK = threading.Lock()


def get_auto_tick() -> AutoTickRunner:
    # R65 (2026-04-24): locked double-check singleton.  Two simultaneous
    # `/api/auto_tick/start` requests could each build a new runner and
    # start a daemon thread, double-advancing the sim.
    global _DEFAULT_RUNNER
    if _DEFAULT_RUNNER is not None:
        return _DEFAULT_RUNNER
    with _DEFAULT_RUNNER_LOCK:
        if _DEFAULT_RUNNER is None:
            _DEFAULT_RUNNER = AutoTickRunner()
        return _DEFAULT_RUNNER
