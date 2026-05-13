"""End-to-end mission tests — catch bugs unit tests miss.

The bug pattern: each subsystem's unit tests exercise it for a handful
of ticks. Bugs that only appear when multiple subsystems run together
across a multi-day mission (ARRIVAL fuel waste, roller burn-out after
a single maglev trip, mission objectives capping at 92.86 %) routinely
slip through.

Each test here runs an actual mission (Moon or Jupiter) with the full
tick graph registered, and asserts the class of physics invariant that
would have caught the shipped bug.
"""

from __future__ import annotations

import importlib

import pytest

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import Phase, get_phase_controller
from aria.simulator.tick_engine import get_tick_engine, reset_tick_engine
from aria.simulator.trajectory_state import (
    get_trajectory_state, reset_trajectory_state,
)


_SUBSYSTEMS = [
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


@pytest.fixture
def mission_world():
    """Reset + register every subsystem; return the tick engine."""
    reset_tick_engine()
    reset_trajectory_state()
    from aria.simulator.fuel_tracker import reset_fuel_inventory
    from aria.simulator.propulsion_thermal import reset_propulsion_thermal
    reset_fuel_inventory()
    reset_propulsion_thermal()
    for mod_name in ("crew_health", "hull_damage", "agriculture_yield",
                     "bearing_dynamics", "power_tracker"):
        mod = importlib.import_module(f"aria.simulator.{mod_name}")
        resetter = getattr(mod, f"reset_{mod_name}", None)
        if resetter is None:
            # Fall back to best-guess reset names the modules actually export.
            for candidate in (f"reset_{mod_name.replace('_state', '')}",
                              f"reset_{mod_name.split('_')[0]}"):
                resetter = getattr(mod, candidate, None)
                if resetter is not None:
                    break
        if resetter is not None:
            resetter()

    bus = get_event_bus()
    bus.clear_history()
    bus._history = type(bus._history)(maxlen=50_000)

    phase = get_phase_controller()
    phase.current = Phase.PRELAUNCH
    phase.elapsed_yr = 0.0
    phase.history.clear()

    engine = get_tick_engine()
    for name, modpath in _SUBSYSTEMS:
        if name not in engine.registered_names():
            importlib.import_module(modpath).register_with_tick_engine()

    yield engine
    reset_tick_engine()


def _drive_mission(engine, target, total_days, boost_days, substep_s):
    """Send the ship to `target` via a simple BOOST→CRUISE→DECEL plan."""
    traj = get_trajectory_state()
    traj.set_target(target)
    phase = get_phase_controller()
    engine.MAX_SUBSTEP_S = substep_s

    phase.transition(Phase.BOOST)
    engine.advance(boost_days * 86400.0)
    # Short solar-system missions typically auto-arrive during BOOST —
    # don't force phase transitions if the auto-arrival already ran us
    # all the way to ORBIT.
    if phase.current == Phase.BOOST:
        phase.transition(Phase.CRUISE)
    remaining = (total_days - boost_days) * 86400.0
    if remaining > 0:
        engine.advance(remaining)


# ────────────────────────────────────────────────────────────────────

def test_moon_mission_reaches_orbit(mission_world):
    """30-day Moon mission should auto-arrive and auto-transition to ORBIT,
    not park indefinitely in ARRIVAL. Catches the bug where the
    `phase_orbit` objective never completes (mission caps at 92.86 %)."""
    _drive_mission(mission_world, "Moon", total_days=30,
                   boost_days=10, substep_s=3600.0)

    phase = get_phase_controller()
    traj = get_trajectory_state()

    assert phase.current == Phase.ORBIT, (
        f"expected ORBIT after Moon mission, got {phase.current.value}. "
        f"Missing auto ARRIVAL→ORBIT transition?"
    )
    assert traj.fraction_complete >= 0.999
    assert traj.velocity_m_s < 1.0, "ship should be parked at Moon"


def test_arrival_phase_does_not_burn_main_drive(mission_world):
    """The ARRIVAL phase must not command main-drive thrust. With
    main_thrust_frac=0.10 (the old value) a short solar-system mission
    wastes ~9 % of the propellant budget on useless station-keeping
    burns that trajectory_state's arrival-clamp immediately zeroes."""
    _drive_mission(mission_world, "Moon", total_days=30,
                   boost_days=10, substep_s=3600.0)
    traj = get_trajectory_state()

    # Moon needs Δv ≈ 2 km/s; with 186 km/s budget that's < 2 % fuel.
    # If ARRIVAL is burning uselessly, usage creeps much higher.
    burned_frac = 1.0 - traj.propellant_fraction_remaining
    assert burned_frac < 0.10, (
        f"Moon mission burned {burned_frac:.1%} of fuel — far above "
        f"the ~2 % needed. ARRIVAL phase drawing main drive?"
    )


def test_bearing_survives_single_maglev_trip(mission_world):
    """A single maglev trip during a Moon mission must NOT burn the
    roller bearings to EOL. Before the distributed-60-station fix,
    per-bearing load was 75× its rated capacity and rollers hit 100 %
    life-consumed within one tick of roller-mode operation."""
    _drive_mission(mission_world, "Moon", total_days=30,
                   boost_days=10, substep_s=3600.0)

    from aria.simulator.bearing_dynamics import get_bearing_state
    bs = get_bearing_state()
    assert bs.roller_life_consumed_frac < 0.20, (
        f"rollers at {bs.roller_life_consumed_frac*100:.1f}% life consumed "
        f"after a 30-day mission — bearings are not distributed."
    )


def test_maglev_winding_temperature_equilibrates(mission_world):
    """Winding temp must settle to an equilibrium, not rise linearly.
    Old model: 320 + 5·(hours/8760) → 820 K at 100 yr → safety trip.
    Fixed model: first-order lag toward ~325 K."""
    _drive_mission(mission_world, "Proxima Centauri", total_days=5 * 365,
                   boost_days=30, substep_s=86400.0 * 10)

    from aria.simulator.bearing_dynamics import get_bearing_state
    bs = get_bearing_state()
    # 5 years in, temp must be near equilibrium, not hundreds of K above.
    assert 300.0 < bs.magnet_winding_temp_k < 360.0, (
        f"winding temp {bs.magnet_winding_temp_k:.0f} K after 5 yr — "
        f"unbounded linear growth?"
    )


def test_mission_objectives_reach_100pct_on_arrival(mission_world):
    """Full mission must complete all 14 objectives, including phase_orbit."""
    _drive_mission(mission_world, "Moon", total_days=30,
                   boost_days=10, substep_s=3600.0)
    from aria.simulator.mission_objectives import get_mission_objectives
    mo = get_mission_objectives()
    pct = mo.to_dict().get("progress_pct", 0)
    assert pct >= 99.9, (
        f"mission progress stuck at {pct:.1f}% — phase_orbit "
        f"or another late objective never fires."
    )
