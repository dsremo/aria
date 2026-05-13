"""Pod A3 — Earth/Sol escape and Oberth departure physics.

Implements audit items §1.1.2 (LEO→0.1c escape), §1.1.3 (Oberth effect),
§1.1.4 (patched-conic departure), §1.1.26 (gravitational slingshot).

See `docs/pods/A3_oberth_departure.md` for the scope note. Derivations,
citations, and verification test cases live there.

Public API:
    tsiolkovsky_delta_v        — rocket equation
    stacked_delta_v            — multi-stage Tsiolkovsky sum
    escape_velocity            — √(2μ/r)
    v_infinity_from_v          — hyperbolic excess
    oberth_v_infinity_gain     — perihelion burn Δv∞ gain
    oberth_multiplier          — 1 + 2 v_p / Δv_burn
    sphere_of_influence_radius — r_SOI = a (m/M)^(2/5)
    slingshot_delta_v          — 2 v∞ sin δ
    laser_sail_acceleration    — 2P/(mc)
    DepartureDeltaVBudget      — §4.5 accounting dataclass
"""

from .tsiolkovsky import (
    STANDARD_GRAVITY_M_S2,
    stacked_delta_v,
    tsiolkovsky_delta_v,
)
from .escape import (
    GM_EARTH_M3_S2,
    GM_SUN_M3_S2,
    escape_velocity,
    v_infinity_from_v,
    vis_viva_speed,
)
from .oberth import (
    oberth_multiplier,
    oberth_v_infinity_after_burn,
    oberth_v_infinity_gain_squared,
)
from .patched_conic import (
    slingshot_delta_v,
    sphere_of_influence_radius,
)
from .laser_sail import (
    SPEED_OF_LIGHT_M_S,
    laser_sail_acceleration,
    laser_sail_cruise_time,
)
from .delta_v_budget import DepartureDeltaVBudget

__all__ = [
    "STANDARD_GRAVITY_M_S2",
    "GM_EARTH_M3_S2",
    "GM_SUN_M3_S2",
    "SPEED_OF_LIGHT_M_S",
    "tsiolkovsky_delta_v",
    "stacked_delta_v",
    "escape_velocity",
    "vis_viva_speed",
    "v_infinity_from_v",
    "oberth_multiplier",
    "oberth_v_infinity_gain_squared",
    "oberth_v_infinity_after_burn",
    "sphere_of_influence_radius",
    "slingshot_delta_v",
    "laser_sail_acceleration",
    "laser_sail_cruise_time",
    "DepartureDeltaVBudget",
]
