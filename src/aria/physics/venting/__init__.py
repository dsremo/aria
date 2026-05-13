"""R39 — venting physics: thrust/torque + breach + stuck-valve + sublimator.

Closes Tier-2 item 2.6 from `docs/PRODUCTION_READINESS_RESEARCH.md`.

The user's brief named "Cassini's water vent shifted Saturn approach by
mm/s for weeks" and "Soyuz 11 hull breach killed crew in 30 s" as the
two failure modes ARIA had not modelled.  This package models both.

Submodules:
    vent_dynamics  — choked-flow + isentropic thrust + torque coupling
    hull_breach    — accidental cabin decompression (Soyuz 11 class)
    stuck_valve    — failure mode: vent valve stuck open after command
    sublimator     — open-loop water-flash thermal flash (Apollo PLSS)

The four submodules share one physics core in ``vent_dynamics`` and
present narrow operational APIs above it.
"""

from aria.physics.venting.vent_dynamics import (
    GasState,
    VentGeometry,
    VentResult,
    choked_mass_flow,
    isentropic_exit_velocity,
    vent_thrust_and_torque,
)
from aria.physics.venting.hull_breach import (
    BreachConfig,
    BreachState,
    breach_step,
    simulate_breach,
)
from aria.physics.venting.stuck_valve import (
    StuckValveConfig,
    simulate_stuck_valve,
)
from aria.physics.venting.sublimator import (
    SublimatorConfig,
    SublimatorResult,
    simulate_sublimator,
)

__all__ = [
    # vent_dynamics
    "GasState", "VentGeometry", "VentResult",
    "choked_mass_flow", "isentropic_exit_velocity", "vent_thrust_and_torque",
    # hull_breach
    "BreachConfig", "BreachState", "breach_step", "simulate_breach",
    # stuck_valve
    "StuckValveConfig", "simulate_stuck_valve",
    # sublimator
    "SublimatorConfig", "SublimatorResult", "simulate_sublimator",
]
