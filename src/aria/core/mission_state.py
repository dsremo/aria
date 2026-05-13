"""Single mission-state authority for cross-cutting live values.

Counterpart to `aria.core.mission_clock`.  Holds the cross-subsystem
state that ARIA's audit found fragmented across multiple singletons
(``crew_size`` was independently maintained in `crew_health`,
`crew_schedule`, `agriculture_yield`, and `engine.SimulatorState`,
all defaulting to 1000 with no propagation between them; same story
for hull integrity).

This module:

  * ``crew_alive`` — current population.  Single integer, mutated
    only via `set_crew_alive(n)`.  Every consumer reads it through
    `get_mission_state().crew_alive`; subsystems that still expose a
    `crew_size` attribute do so as a `@property` that delegates here.
  * ``hull_integrity_pct`` — live worst-region health, computed from
    `hull_damage.HullDamageState` on each access.  Expensive to keep
    in sync with a callback, cheap to compute on demand.

Atomicity & threading:
  * Reads are lock-free (Python GIL guarantees a small int/float read).
  * Writes hold the module RLock so concurrent `set_*` calls don't
    interleave.
  * Generation counter bumps on every mutation; subscribers using
    `bus.subscribe("mission.state.changed")` can react.

Why not put these on `MissionClock`?  Because the clock has only ONE
operation (advance) and is on the hot path.  Keeping it minimal makes
its semantics easy to reason about.  Cross-subsystem state lives here.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional


_DEFAULT_CREW_SIZE: int = 1000   # legacy default — matches the value
                                  # that was hardcoded in 4 modules.


@dataclass
class MissionState:
    """Process-wide cross-subsystem state.

    `crew_alive` and the hull-integrity aggregator are intentionally
    the only fields.  Resist the temptation to dump everything here —
    individual subsystem state stays in its own singleton (fuel,
    eclss, propulsion, etc.); only values that were leaking across
    multiple sources of truth belong on this object.
    """

    crew_alive: int = _DEFAULT_CREW_SIZE
    generation: int = 0
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # ── Crew ─────────────────────────────────────────────────────

    def set_crew_alive(self, n: int) -> None:
        """Update the population. Bumps generation + publishes event."""
        n = max(0, int(n))
        with self._lock:
            if n == self.crew_alive:
                return
            old = self.crew_alive
            self.crew_alive = n
            self.generation += 1
        try:
            from aria.simulator.event_bus import get_event_bus
            get_event_bus().publish(
                "mission.state.crew_changed",
                severity="info" if n >= old else "warning",
                source="mission_state",
                payload={"old": old, "new": n, "delta": n - old,
                         "generation": self.generation},
            )
        # Wiring audit Pass 7 (F6.13) — narrow the broad except.
        # `aria.simulator.event_bus` may not be importable in
        # production deploys without the simulator package; that is
        # the only legitimate "bus optional" case. Other exceptions
        # (publish-side bugs, attribute renames) should surface.
        except (ImportError, AttributeError):
            pass

    # ── Hull (live aggregate) ────────────────────────────────────

    @property
    def hull_integrity_pct(self) -> float:
        """Worst-region hull health, computed live from hull_damage.

        Returns 100.0 if hull_damage isn't available (test fixtures,
        early init).  Aggregates by `min` because a hull-breach in
        one region kills the ship — averages would hide it.
        """
        try:
            from aria.simulator.hull_damage import get_hull_damage
            hd = get_hull_damage()
            regions = getattr(hd, "regions", None) or {}
            if not regions:
                return 100.0
            return float(min(r.health_pct for r in regions.values()))
        # Wiring audit Pass 7 (F6.13) — narrow the broad except.
        # ImportError covers the simulator-not-installed path; the
        # generator inside `min()` can raise `ValueError` on empty
        # iterable but we already guard that above. Other exceptions
        # (e.g. AttributeError from a renamed `health_pct`) should
        # surface rather than silently return 100% (false healthy).
        except ImportError:
            return 100.0

    @property
    def hull_breached(self) -> bool:
        """True when worst-region health hit 0 — survival-check truth."""
        return self.hull_integrity_pct <= 0.0

    # ── Snapshots / IO ───────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "crew_alive":         self.crew_alive,
            "hull_integrity_pct": round(self.hull_integrity_pct, 3),
            "hull_breached":      self.hull_breached,
            "generation":         self.generation,
        }


_DEFAULT_STATE: Optional[MissionState] = None
_DEFAULT_STATE_LOCK = threading.Lock()


def get_mission_state() -> MissionState:
    """Process-wide singleton; thread-safe lazy init."""
    global _DEFAULT_STATE
    if _DEFAULT_STATE is not None:
        return _DEFAULT_STATE
    with _DEFAULT_STATE_LOCK:
        if _DEFAULT_STATE is None:
            _DEFAULT_STATE = MissionState()
        return _DEFAULT_STATE


def reset_mission_state() -> None:
    """Test-only — replace the singleton with a fresh instance."""
    global _DEFAULT_STATE
    with _DEFAULT_STATE_LOCK:
        _DEFAULT_STATE = MissionState()
