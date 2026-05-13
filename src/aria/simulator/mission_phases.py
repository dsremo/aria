"""Generation-ship mission phase state machine.

Formalises the life of the ship as a sequence of phases, each with
different subsystem constraints. Currently the simulator had a
`GenerationShipConfig.enable_*` toggle soup but no explicit phase
semantics — crew metabolism, thermal load, power draw all change
qualitatively between "parked in cislunar space" and "mid-cruise at
0.02 c" and "braking approach to α Cen A".

Phase order (default generation-ship profile):
    PRELAUNCH → BOOST → CRUISE → DECELERATION → ARRIVAL → ORBIT

Each phase:
  * has entry + exit preconditions (sanity-checked)
  * sets typical subsystem-load ranges (0..1 scale)
  * has a nominal duration

References
----------
Phase breakdown follows Forward 1984 "Roundtrip Interstellar Travel Using
Laser-Pushed Lightsails" §3 (phases: boost, coast, rendezvous); adapted
for a continuous-burn fusion ship per Frisbee 2003 JPL/D-26963.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Phase(str, Enum):
    """Mission phases in order."""

    PRELAUNCH      = "prelaunch"
    BOOST          = "boost"
    CRUISE         = "cruise"
    DECELERATION   = "deceleration"
    ARRIVAL        = "arrival"
    ORBIT          = "orbit"
    EMERGENCY      = "emergency"   # exceptional sideband


@dataclass(frozen=True)
class PhaseSpec:
    """Nominal envelope for a mission phase.

    Load fractions are 0..1, interpreted as "use this fraction of
    maximum rated capacity during this phase." They're not limits —
    they're nominal setpoints. The physics sim enforces real limits
    from thermal / power budgets.
    """

    phase: Phase
    nominal_duration_yr: float   # years, for planning purposes
    power_load_frac: float       # 0..1 of reactor full output
    thermal_load_frac: float     # 0..1 of radiator capacity
    rcs_load_frac: float         # 0..1 of RCS propellant rate
    main_thrust_frac: float      # 0..1 of main-drive thrust
    crew_metabolic_frac: float   # usually 1.0 (crew always alive)
    description: str = ""


# Nominal phase specifications. Values are engineering rule-of-thumbs per
# Frisbee 2003 (§4, continuous-drive generation ship). Keep as data so the
# physics sim can override when needed.
PHASE_SPECS: Dict[Phase, PhaseSpec] = {
    Phase.PRELAUNCH: PhaseSpec(
        phase=Phase.PRELAUNCH,
        nominal_duration_yr=0.5,        # 6 months final commissioning, Frisbee 2003 §3.4
        power_load_frac=0.10,           # APU + avionics + checkout, no propulsion
        thermal_load_frac=0.15,
        rcs_load_frac=0.0,
        main_thrust_frac=0.0,
        crew_metabolic_frac=0.1,        # skeleton crew during commissioning
        description="Commissioning in cislunar assembly orbit; reactor in standby",
    ),
    Phase.BOOST: PhaseSpec(
        phase=Phase.BOOST,
        nominal_duration_yr=5.0,        # continuous fusion burn to 0.02 c, Frisbee 2003 Table 5
        power_load_frac=0.95,           # near-full reactor output → nozzle
        thermal_load_frac=0.90,         # peak thermal load
        rcs_load_frac=0.15,             # attitude hold during thrust
        main_thrust_frac=1.00,
        crew_metabolic_frac=1.0,
        description="Continuous fusion boost until cruise velocity reached",
    ),
    Phase.CRUISE: PhaseSpec(
        phase=Phase.CRUISE,
        nominal_duration_yr=215.0,       # α Cen A @ 0.02 c = 220 yr total, minus boost/decel
        power_load_frac=0.25,           # only life support + avionics
        thermal_load_frac=0.30,
        rcs_load_frac=0.02,             # minimal station-keeping
        main_thrust_frac=0.0,
        crew_metabolic_frac=1.0,
        description="Inertial cruise — main drive off, crew ecosystem primary load",
    ),
    Phase.DECELERATION: PhaseSpec(
        phase=Phase.DECELERATION,
        nominal_duration_yr=5.0,        # symmetric with BOOST
        power_load_frac=0.95,
        thermal_load_frac=0.90,
        rcs_load_frac=0.15,
        main_thrust_frac=1.00,
        crew_metabolic_frac=1.0,
        description="Retrograde fusion burn — mirror of BOOST",
    ),
    Phase.ARRIVAL: PhaseSpec(
        phase=Phase.ARRIVAL,
        nominal_duration_yr=0.5,
        power_load_frac=0.35,
        thermal_load_frac=0.40,
        rcs_load_frac=0.30,             # orbital insertion manoeuvres — RCS only
        main_thrust_frac=0.0,           # main drive idle: trajectory clamps v→0 at arrival,
                                        # any non-zero main-thrust fraction here just drains
                                        # propellant while the clamp zeroes the resulting Δv.
        crew_metabolic_frac=1.0,
        description="Orbital insertion via RCS trim — main drive idle",
    ),
    Phase.ORBIT: PhaseSpec(
        phase=Phase.ORBIT,
        nominal_duration_yr=100.0,       # indefinite operational phase
        power_load_frac=0.25,
        thermal_load_frac=0.30,
        rcs_load_frac=0.05,
        main_thrust_frac=0.0,
        crew_metabolic_frac=1.0,
        description="Stable orbit at destination, colonisation ops",
    ),
    Phase.EMERGENCY: PhaseSpec(
        phase=Phase.EMERGENCY,
        nominal_duration_yr=0.1,        # days to hours
        power_load_frac=0.15,           # load-shedding to life support
        thermal_load_frac=0.20,
        rcs_load_frac=0.0,
        main_thrust_frac=0.0,
        crew_metabolic_frac=1.0,
        description="Emergency — non-critical systems shed; life support + comms only",
    ),
}


# Legal phase transitions. Any transition not in this set is rejected
# unless forced (e.g. EMERGENCY can be entered from anywhere, and ORBIT
# can be indefinite). Keep explicit so ordering bugs surface immediately.
_LEGAL_TRANSITIONS: Dict[Phase, List[Phase]] = {
    Phase.PRELAUNCH:    [Phase.BOOST, Phase.EMERGENCY],
    Phase.BOOST:        [Phase.CRUISE, Phase.EMERGENCY],
    Phase.CRUISE:       [Phase.DECELERATION, Phase.EMERGENCY],
    Phase.DECELERATION: [Phase.ARRIVAL, Phase.EMERGENCY],
    Phase.ARRIVAL:      [Phase.ORBIT, Phase.EMERGENCY],
    Phase.ORBIT:        [Phase.EMERGENCY],
    Phase.EMERGENCY:    list(Phase),     # can recover to any phase on operator override
}


@dataclass
class MissionPhaseController:
    """Runtime state for the mission phase.

    Holds the current phase + the mission-elapsed time + a transition
    history for debugging. Non-persistent by design — `/api/mission/phase`
    provides the current state at any instant.
    """

    current: Phase = Phase.PRELAUNCH
    history: List[tuple[float, Phase, Phase]] = field(default_factory=list)
    """List of (elapsed_yr, from_phase, to_phase) transition events."""

    # R7 (2026-04-24, sync refactor): `elapsed_yr` is no longer a
    # locally-stored field — it's a property that reads from the
    # process-wide MissionClock so the phase controller and every
    # other consumer (telemetry, status strip, advisor snapshot)
    # see the same T+ value.  Was 5 independent clocks; now 1.
    @property
    def elapsed_yr(self) -> float:
        from aria.core.mission_clock import get_mission_clock
        return get_mission_clock().elapsed_yr

    @elapsed_yr.setter
    def elapsed_yr(self, value: float) -> None:
        # Setter exists only for legacy paths (snapshot restore,
        # operator reset).  Normal mission-time advance must go
        # through `MissionClock.advance()` via the auto-tick loop.
        from aria.core.mission_clock import get_mission_clock
        get_mission_clock().reset(to_yr=float(value))

    def transition(self, new_phase: Phase, *, force: bool = False,
                   _auto: bool = False) -> None:
        """Move to `new_phase`. Raises if the transition is illegal
        unless `force=True` (reserved for operator override / EMERGENCY).

        R65-R4 (2026-04-24): bus-event emission moved here so every
        transition (auto via `tick()` *and* explicit via demo / operator
        override / /api/mission/transition) publishes `phase.transition`.
        Previously only the auto-tick path emitted, so the demo script's
        BOOST→ARRIVAL→ORBIT cascade was silent.  The `_auto` kwarg
        flags automatic transitions in the bus payload so a narrator
        can distinguish them from explicit operator commands.
        """
        if new_phase == self.current:
            # R8-fix (2026-04-24): operator click PRELAUNCH while
            # already in PRELAUNCH should still zero the clock — it's
            # the "reset mission" button even if the phase field
            # already matches.  Other phases are idempotent no-ops.
            if force and new_phase == Phase.PRELAUNCH and self.elapsed_yr > 0:
                from aria.core.mission_clock import get_mission_clock
                get_mission_clock().reset(to_yr=0.0)
                self.history = []
            return
        if not force and new_phase not in _LEGAL_TRANSITIONS.get(self.current, []):
            raise ValueError(
                f"Illegal phase transition {self.current.value} → {new_phase.value}"
            )
        old = self.current
        # BUG-027 (2026-04-24, walkthrough): operator click "prelaunch"
        # from a later phase used to leave `elapsed_yr` at its current
        # value — `PHASE PRELAUNCH · T+ 1.00 yr` is not a physical state.
        # Any backward jump to PRELAUNCH zeros the clock AND the
        # transition history (this is a reset, not a time-travel).  Also
        # zero on a forced jump INTO PRELAUNCH from anywhere — auto
        # never does this (nominal_next always walks forward), so this
        # only fires on explicit operator/API reset.
        if new_phase == Phase.PRELAUNCH and old != Phase.PRELAUNCH:
            self.elapsed_yr = 0.0
            self.history = []
            self.current = new_phase
            self._emit_transition_event(
                old=old.value, new=new_phase.value, auto=_auto, forced=force)
            return
        self.history.append((self.elapsed_yr, old, new_phase))
        self.current = new_phase
        self._emit_transition_event(old=old.value, new=new_phase.value, auto=_auto, forced=force)

    def _emit_transition_event(self, *, old: str, new: str, auto: bool, forced: bool) -> None:
        """Publish `phase.transition` on the bus.  Import locally and
        swallow failures so a missing bus never breaks physics."""
        try:
            from aria.simulator.event_bus import get_event_bus
            get_event_bus().publish(
                "phase.transition",
                severity="info",
                source="mission_phases",
                payload={
                    "old":    old,
                    "new":    new,
                    "at_yr":  round(self.elapsed_yr, 4),
                    "auto":   auto,
                    "forced": forced,
                },
            )
        except Exception:
            pass

    def tick(self, delta_yr: float) -> float:
        """Check for phase auto-transition. Does NOT advance time.

        R7 (2026-04-24, sync refactor): mission time is no longer
        advanced here — `MissionClock.advance()` is the single
        source-of-truth writer.  The caller (auto-tick loop) advances
        the clock once per iteration, then calls this method to check
        whether the new elapsed crosses the current phase's nominal
        duration and triggers an auto-transition.  The `delta_yr`
        argument is kept for backward compatibility with callers that
        still pass it; it is informational only and not added to any
        running counter.

        Returns `delta_yr` unchanged (used to be the elapsed delta —
        kept the contract so existing callers don't break).  BUG-014
        history: until R65 this method was a single
        `self.elapsed_yr += delta_yr`; under R7 we removed even that
        line and route every increment through MissionClock.
        """
        # Time is already advanced by MissionClock; nothing to do here
        # except check for auto-transition.

        # How long has the current phase been active?  We compare against
        # the nominal_duration_yr on its PhaseSpec.  elapsed_in_phase is
        # computed as elapsed - last-transition-time; falls back to
        # elapsed itself on the first phase.
        last_txn_yr = self.history[-1][0] if self.history else 0.0
        elapsed_in_phase = self.elapsed_yr - last_txn_yr

        # ORBIT is the terminal nominal phase (destination operations);
        # don't auto-exit it.  EMERGENCY is operator-only.
        spec = PHASE_SPECS[self.current]
        if self.current in (Phase.ORBIT, Phase.EMERGENCY):
            return delta_yr

        # BUG-039 (2026-04-24, walkthrough): the default nominal
        # durations are sized for a 220-yr interstellar generation
        # ship (PRELAUNCH=0.5 yr, BOOST=5 yr, CRUISE=215 yr).  For
        # cislunar or cisplanetary missions (Moon, Mars) the trajectory
        # auto-arrival fires within microseconds of sim-time, long
        # before the default durations elapse — so live Mission Control
        # skipped straight from PRELAUNCH to ARRIVAL without ever
        # entering BOOST/CRUISE/DECELERATION.  Scale the duration to
        # the actual mission: short for Moon, default for interstellar.
        effective_duration = spec.nominal_duration_yr
        try:
            from aria.simulator.trajectory_state import get_trajectory_state
            dist_ly = float(get_trajectory_state().distance_total_ly)
            if dist_ly > 0.0 and dist_ly < 0.001:
                # Sub-light-year target — compress all phases into
                # the target's ship-arrival timescale (roughly 8 days
                # for Moon, a few months for Mars).  Scale so the
                # whole 225.5-yr interstellar profile collapses into
                # the mission's actual duration.  For Moon at
                # 4e-8 ly, scale ≈ 4e-8 / 4.37 ≈ 1e-8 → PRELAUNCH
                # becomes 0.5 × 1e-8 ≈ 0.16 s; that's too aggressive.
                # Use √(dist/proxima) so operators see each phase for
                # a human-readable duration (Moon: scale ≈ 1e-4 →
                # PRELAUNCH = 26 min, BOOST = 4.4 hr — realistic for
                # an Apollo-class cislunar rehearsal).
                import math
                scale = max(1e-5, math.sqrt(dist_ly / 4.37))
                effective_duration = spec.nominal_duration_yr * scale
        except Exception:
            pass

        if elapsed_in_phase < effective_duration:
            return delta_yr

        nxt = self.nominal_next()
        if nxt is None:
            return delta_yr
        # Legal by construction (nominal_next walks the same sequence as
        # _LEGAL_TRANSITIONS); let .transition() emit the bus event so
        # auto AND explicit transitions share one publish path.
        self.transition(nxt, force=False, _auto=True)
        return delta_yr

    def spec(self) -> PhaseSpec:
        return PHASE_SPECS[self.current]

    def nominal_next(self) -> Optional[Phase]:
        """Return the 'default' next phase in the nominal timeline."""
        order = [Phase.PRELAUNCH, Phase.BOOST, Phase.CRUISE,
                 Phase.DECELERATION, Phase.ARRIVAL, Phase.ORBIT]
        try:
            idx = order.index(self.current)
        except ValueError:
            return None
        if idx + 1 >= len(order):
            return None
        return order[idx + 1]

    def to_dict(self) -> dict:
        spec = self.spec()
        return {
            "current_phase": self.current.value,
            "elapsed_yr": round(self.elapsed_yr, 2),
            "spec": {
                "nominal_duration_yr": spec.nominal_duration_yr,
                "power_load_frac": spec.power_load_frac,
                "thermal_load_frac": spec.thermal_load_frac,
                "rcs_load_frac": spec.rcs_load_frac,
                "main_thrust_frac": spec.main_thrust_frac,
                "crew_metabolic_frac": spec.crew_metabolic_frac,
                "description": spec.description,
            },
            "nominal_next": self.nominal_next().value if self.nominal_next() else None,
            "history": [
                {"at_yr": round(t, 2), "from": f.value, "to": to_p.value}
                for t, f, to_p in self.history
            ],
        }


# Singleton for the web API
import threading as _threading
_DEFAULT_CONTROLLER: Optional[MissionPhaseController] = None
_DEFAULT_CONTROLLER_LOCK = _threading.Lock()


def get_phase_controller() -> MissionPhaseController:
    # R65 (2026-04-24): locked double-check singleton.  Without the lock,
    # the auto-tick daemon and the aiohttp handler for `/api/mission/phase`
    # could each build a separate MissionPhaseController on startup; one
    # would advance phase, the other would answer the UI — `history` and
    # `elapsed_yr` would then diverge across two truth sources.
    global _DEFAULT_CONTROLLER
    if _DEFAULT_CONTROLLER is not None:
        return _DEFAULT_CONTROLLER
    with _DEFAULT_CONTROLLER_LOCK:
        if _DEFAULT_CONTROLLER is None:
            _DEFAULT_CONTROLLER = MissionPhaseController()
        return _DEFAULT_CONTROLLER
