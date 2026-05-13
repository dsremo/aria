"""Mission objectives tracker — what needs to be done, what's done.

Defines a checklist of mission milestones (cold-start complete, BOOST
phase entered, 25 % distance, half-distance, deceleration begun, arrival,
etc.). Each tick, evaluates each objective's "is met now?" predicate and
sets `completed_at_yr` if so.

Useful for:
  * Showing operator a clear "we are 47 % through the mission" view
  * Triggering follow-on events (e.g. on `arrival`, schedule orbit-insertion)
  * After-action review

Each objective's predicate references other singletons; they are
evaluated lazily so adding a new subsystem doesn't force this module to
import everything at module load.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class Objective:
    """A single mission objective."""

    objective_id: str
    label: str
    description: str
    category: str          # 'startup' / 'phase' / 'distance' / 'subsystem' / 'arrival'
    predicate: Callable[[], bool]    # returns True iff objective met *now*
    completed_at_yr: Optional[float] = None
    notes: str = ""

    @property
    def is_complete(self) -> bool:
        return self.completed_at_yr is not None


def _objective_definitions() -> List[Objective]:
    """All objectives. Predicates are lazy — they import inside the body."""
    objs: List[Objective] = []

    # ── Startup objectives ──────────────────────────────────────
    def _startup_complete() -> bool:
        from aria.simulator.startup_sequence import StepStatus, get_startup_controller
        c = get_startup_controller()
        return c.complete and not c.aborted

    def _reactor_online() -> bool:
        from aria.simulator.startup_sequence import StepStatus, get_startup_controller
        s = get_startup_controller().get_step("reactor_power_ramp")
        return s is not None and s.status == StepStatus.SUCCESS

    def _ring_spinning() -> bool:
        from aria.simulator.bearing_dynamics import BearingMode, get_bearing_state
        return get_bearing_state().mode in (BearingMode.MAGNETIC, BearingMode.ROLLER)

    objs.append(Objective("startup_apu", "APU online",
                          "Auxiliary power unit ignited", "startup", _apu_online))
    objs.append(Objective("startup_reactor", "Reactor at full power",
                          "Reactor ramped to 100 MWt", "startup", _reactor_online))
    objs.append(Objective("startup_ring", "Habitat ring spinning",
                          "Magnetic bearing engaged", "startup", _ring_spinning))
    objs.append(Objective("startup_complete", "Cold-start sequence complete",
                          "All 19 startup steps succeeded", "startup", _startup_complete))

    # ── Phase objectives ───────────────────────────────────────
    def _entered_boost() -> bool:
        from aria.simulator.mission_phases import Phase, get_phase_controller
        return get_phase_controller().current.value not in ("prelaunch",) or _entered_higher_phase()

    def _entered_higher_phase() -> bool:
        from aria.simulator.mission_phases import Phase, get_phase_controller
        c = get_phase_controller().current.value
        return c in ("cruise", "deceleration", "arrival", "orbit")

    def _entered_cruise() -> bool:
        from aria.simulator.mission_phases import Phase, get_phase_controller
        return get_phase_controller().current.value in ("cruise", "deceleration", "arrival", "orbit")

    def _entered_decel() -> bool:
        from aria.simulator.mission_phases import get_phase_controller
        return get_phase_controller().current.value in ("deceleration", "arrival", "orbit")

    def _entered_orbit() -> bool:
        from aria.simulator.mission_phases import get_phase_controller
        return get_phase_controller().current.value == "orbit"

    objs.append(Objective("phase_boost", "Begin boost",
                          "Mission transitioned to BOOST phase", "phase", _entered_boost))
    objs.append(Objective("phase_cruise", "Reach cruise",
                          "Mission transitioned to CRUISE phase", "phase", _entered_cruise))
    objs.append(Objective("phase_decel", "Begin deceleration",
                          "Mission transitioned to DECELERATION phase", "phase", _entered_decel))
    objs.append(Objective("phase_orbit", "Achieve orbit",
                          "Ship in stable orbit at destination", "phase", _entered_orbit))

    # ── Distance objectives ────────────────────────────────────
    def _frac_at_least(threshold: float) -> Callable[[], bool]:
        def _check() -> bool:
            from aria.simulator.trajectory_state import get_trajectory_state
            return get_trajectory_state().fraction_complete >= threshold
        return _check

    objs.append(Objective("distance_25", "25 % distance reached",
                          "Ship at 25 % of total cruise distance", "distance",
                          _frac_at_least(0.25)))
    objs.append(Objective("distance_50", "Half-way",
                          "Ship at 50 % distance", "distance",
                          _frac_at_least(0.50)))
    objs.append(Objective("distance_75", "75 % distance reached",
                          "Ship at 75 % of cruise distance", "distance",
                          _frac_at_least(0.75)))
    objs.append(Objective("distance_arrival", "Arrival at target",
                          "Ship reached cruise destination", "arrival",
                          _frac_at_least(1.0)))

    # ── Subsystem objectives ───────────────────────────────────
    def _crew_alive() -> bool:
        from aria.simulator.crew_health import get_crew_health
        return get_crew_health().bone_density_pct > 50

    def _no_unresolved_hull_critical() -> bool:
        from aria.simulator.hull_damage import get_hull_damage
        worst = get_hull_damage().worst_fatigue_region()
        return worst.fatigue_index < 0.95

    objs.append(Objective("crew_alive", "Crew survival",
                          "Aggregate crew health remains viable",
                          "subsystem", _crew_alive))
    objs.append(Objective("hull_intact", "Hull intact",
                          "No region above 95 % fatigue",
                          "subsystem", _no_unresolved_hull_critical))

    return objs


def _apu_online() -> bool:
    from aria.simulator.startup_sequence import StepStatus, get_startup_controller
    s = get_startup_controller().get_step("apu_ignition")
    return s is not None and s.status == StepStatus.SUCCESS


@dataclass
class MissionObjectivesState:
    objectives: List[Objective] = field(default_factory=_objective_definitions)

    # ── tick ────────────────────────────────────────────────────

    def tick(self, dt_s: float) -> None:
        from aria.simulator.event_bus import get_event_bus
        from aria.simulator.mission_phases import get_phase_controller
        bus = get_event_bus()
        phase = get_phase_controller()
        for obj in self.objectives:
            if obj.is_complete:
                continue
            try:
                if obj.predicate():
                    obj.completed_at_yr = phase.elapsed_yr
                    bus.publish(f"objective.complete.{obj.objective_id}",
                                severity="info", source="mission_objectives",
                                payload={"id": obj.objective_id, "label": obj.label,
                                         "category": obj.category},
                                sim_time_yr=phase.elapsed_yr)
            except Exception as e:
                obj.notes = f"predicate error: {e}"

    # ── derived ────────────────────────────────────────────────

    def progress_pct(self) -> float:
        if not self.objectives:
            return 0.0
        return 100.0 * sum(1 for o in self.objectives if o.is_complete) / len(self.objectives)

    def to_dict(self) -> dict:
        from aria.simulator.mission_phases import get_phase_controller
        return {
            "current_yr": round(get_phase_controller().elapsed_yr, 3),
            "progress_pct": round(self.progress_pct(), 2),
            "completed": sum(1 for o in self.objectives if o.is_complete),
            "total":     len(self.objectives),
            "objectives": [
                {
                    "id":               o.objective_id,
                    "label":            o.label,
                    "description":      o.description,
                    "category":         o.category,
                    "complete":         o.is_complete,
                    # `if o.completed_at_yr` was truthy-checking a float — which
                    # drops legitimate yr = 0.0 completions (startup_apu fires
                    # instantly, so completed_at_yr = 0.0 was serialised as
                    # None while `complete` still read True — 5 UI rows showed
                    # the contradiction). Explicit None-check preserves 0.0.
                    "completed_at_yr":  round(o.completed_at_yr, 3) if o.completed_at_yr is not None else None,
                    "notes":            o.notes,
                }
                for o in self.objectives
            ],
        }


_DEFAULT: Optional[MissionObjectivesState] = None


def get_mission_objectives() -> MissionObjectivesState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = MissionObjectivesState()
    return _DEFAULT


def reset_mission_objectives() -> None:
    global _DEFAULT
    _DEFAULT = MissionObjectivesState()


def register_with_tick_engine() -> None:
    from aria.simulator.tick_engine import get_tick_engine
    get_tick_engine().register("mission_objectives", get_mission_objectives().tick, order=70)
