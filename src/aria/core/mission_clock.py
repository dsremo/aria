"""Single mission-time authority.

Built 2026-04-24 in response to the walkthrough finding that ARIA had
**five** independently-maintained clocks (engine.mission_time_years,
phase_controller.elapsed_yr, trajectory_state.elapsed_yr,
auto_tick.cumulative_sim_s, MissionTime.sim_yr) which drifted from
each other in routine use — the status strip and Telemetry tile
displayed values that disagreed by 2× during the same poll cycle.

This module is the ONLY place mission time is incremented.  Every
other subsystem must READ from `get_mission_clock().elapsed_yr` and
must NEVER maintain a parallel counter.  The auto-tick loop calls
`advance(dt_yr)` exactly once per iteration; subsystems' `tick(dt_s)`
methods receive the delta but must not store their own running total.

Atomicity:
- Reads are lock-free (Python GIL guarantees a 64-bit float read is
  atomic).  We tolerate one cycle of staleness in exchange for not
  forcing every reader through a contended lock.
- Writes hold the module lock so concurrent `advance()` from a future
  multi-threaded driver will not lose updates.

Thread safety: the lock is module-level RLock; reads do not take it.

References
----------
NASA SCAN/MOC Mission Operations Handbook (1999) §4.2 — Mission
Elapsed Time (MET) is the single ground-station-truth clock.
ESA ECSS-E-ST-70C §5.4.2 — Onboard time correlation requires a
single monotonically-increasing reference.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional

# Seconds per Julian year (365.25 d) — matches every existing
# year-conversion constant in the codebase.
_YEAR_S: float = 365.25 * 24.0 * 3600.0


@dataclass
class MissionClock:
    """Process-wide mission elapsed-time authority.

    `elapsed_yr` is the canonical T+ value displayed on the status
    strip, used by phase auto-transition, written into bus events,
    referenced by the LLM advisor snapshot, and persisted in
    snapshots / recordings.  No subsystem may maintain its own
    parallel `elapsed_yr` field — read this one instead.
    """

    elapsed_yr: float = 0.0
    # Wall-clock time of the most recent advance(), useful for
    # telemetry latency calculations but never for sim-state.
    _last_advanced_at_wall: Optional[float] = None
    # Generation counter — incremented on every `advance()` and on
    # every `reset()`.  Subscribers can use this to detect "the clock
    # was reset" without polling for an elapsed_yr decrease.
    generation: int = 0
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def advance(self, dt_yr: float) -> float:
        """Advance the mission clock by `dt_yr`.  Returns new elapsed.

        Negative or zero dt is a no-op.  Negative dt would imply
        time travel — disallowed at the API surface; use `reset()`
        for explicit operator rewinds (PRELAUNCH transition).
        """
        if dt_yr <= 0.0:
            return self.elapsed_yr
        with self._lock:
            self.elapsed_yr += dt_yr
            self.generation += 1
            import time as _time
            self._last_advanced_at_wall = _time.time()
            return self.elapsed_yr

    def advance_seconds(self, dt_s: float) -> float:
        """Convenience for callers integrating in SI seconds."""
        return self.advance(dt_s / _YEAR_S)

    def reset(self, to_yr: float = 0.0) -> None:
        """Operator-driven reset (e.g., transition back to PRELAUNCH).

        Bumps `generation` so any cached state keyed on the previous
        clock value can be invalidated.  Bus event `mission.clock.reset`
        is published so subscribers learn of the rewind.
        """
        with self._lock:
            self.elapsed_yr = float(to_yr)
            self.generation += 1
        # Publish OUTSIDE the lock to avoid holding it across a
        # subscriber chain that might re-enter clock methods.
        try:
            from aria.simulator.event_bus import get_event_bus
            get_event_bus().publish(
                "mission.clock.reset",
                severity="info",
                source="mission_clock",
                payload={"to_yr": float(to_yr), "generation": self.generation},
            )
        # Wiring audit Pass 7 (F6.13) — narrow the broad except.
        # Simulator EventBus may not be present in production-only
        # deploys; that's the legitimate "bus optional" case.
        except (ImportError, AttributeError):
            pass

    def to_dict(self) -> dict:
        """JSON-serialisable snapshot.  Reads are atomic; no lock."""
        return {
            "elapsed_yr": round(self.elapsed_yr, 6),
            "generation": self.generation,
            "last_advanced_at_wall": self._last_advanced_at_wall,
        }


_DEFAULT_CLOCK: Optional[MissionClock] = None
_DEFAULT_CLOCK_LOCK = threading.Lock()


def get_mission_clock() -> MissionClock:
    """Process-wide singleton; thread-safe lazy init."""
    global _DEFAULT_CLOCK
    if _DEFAULT_CLOCK is not None:
        return _DEFAULT_CLOCK
    with _DEFAULT_CLOCK_LOCK:
        if _DEFAULT_CLOCK is None:
            _DEFAULT_CLOCK = MissionClock()
        return _DEFAULT_CLOCK


def reset_mission_clock() -> None:
    """Test-only — replace the singleton with a fresh instance.

    Production code must call `get_mission_clock().reset()` instead;
    that path bumps the generation counter and publishes the bus
    event so all downstream caches invalidate atomically.
    """
    global _DEFAULT_CLOCK
    with _DEFAULT_CLOCK_LOCK:
        _DEFAULT_CLOCK = MissionClock()
