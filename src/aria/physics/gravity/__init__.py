"""Pod A1 — Ephemeris, two-body, and N-body gravity.

Implements audit items §1.1.1 (Newtonian `GM/r²`), §1.1.4 (patched-conic
trajectory), §1.1.5 (full N-body), §1.1.6 (stellar perturbations during
cruise), §1.1.7 (target-star gravity at approach), §1.1.8 (planetary
capture Δv), §1.1.9 (Hohmann transfer), §1.1.22 (SSB offset), §1.1.26
(gravitational slingshot).

See `docs/pods/A1_ephemeris.md` for the scope note (derivations,
citations, and verification test cases).

The SPICE/DE440 ephemeris wrapper is in `ephemeris.py`; it is an
optional dependency (spiceypy + DE440.bsp kernel) and degrades
gracefully when the toolkit is not installed.

Public API:
    constants.*                — GM_*, R_*, J2_*, AU, c, …
    kepler_period              — Kepler's third law
    vis_viva_speed             — orbital speed at (r, a)
    hohmann_transfer_delta_v   — (Δv_1, Δv_2, Δv_total, t_transfer)
    planetary_capture_delta_v  — vis-viva capture at a body
    slingshot_vector_delta_v   — full 3-D slingshot with heliocentric Δv
    propagate_proper_motion    — target-star position at epoch
    acceleration_nbody         — Σ GM_i (r_s − R_i) / |...|³
    rk4_step                   — classical RK4 single step
    rk78_adaptive_step         — Dormand-Prince 8(7) adaptive step
    TwoBodyOrbit               — analytic Kepler container
    NBodySystem                — integrator orchestration object
"""

from .constants import (
    AU_M,
    GM_EARTH_M3_S2,
    GM_JUPITER_M3_S2,
    GM_MARS_M3_S2,
    GM_MOON_M3_S2,
    GM_SATURN_M3_S2,
    GM_SUN_M3_S2,
    GRAVITATIONAL_CONSTANT,
    J2_EARTH,
    J2_JUPITER,
    LIGHT_YEAR_M,
    R_EARTH_M,
    R_JUPITER_M,
    R_SUN_M,
    SPEED_OF_LIGHT_M_S,
)
from .two_body import (
    TwoBodyOrbit,
    hohmann_transfer_delta_v,
    kepler_period,
    planetary_capture_delta_v,
    vis_viva_speed,
)
from .slingshot import slingshot_vector_delta_v
from .proper_motion import (
    StarCatalogEntry,
    propagate_proper_motion,
)
from .nbody import (
    NBodySystem,
    acceleration_nbody,
    rk4_step,
    rk78_adaptive_step,
)
from .ephemeris import (
    BodyState,
    AnalyticEphemeris,
    HorizonsRestEphemeris,
    SpiceEphemeris,
    KernelManager,
    get_body_state,
)
from .space_environment import (
    ChargingRisk,
    assess_charging_risk,
    dose_rate_msv_day,
    gyroradius_m,
    igrf_dipole,
    lorentz_acceleration,
    lorentz_force,
    magnetic_l_shell,
    magnetic_torque,
    plasma_density_m3,
    plasma_temperature_k,
    south_atlantic_anomaly_boost,
    van_allen_traversal_dose_msv,
    van_allen_electron_flux,
    van_allen_proton_flux,
)

__all__ = [
    "AU_M",
    "GM_EARTH_M3_S2",
    "GM_JUPITER_M3_S2",
    "GM_MARS_M3_S2",
    "GM_MOON_M3_S2",
    "GM_SATURN_M3_S2",
    "GM_SUN_M3_S2",
    "GRAVITATIONAL_CONSTANT",
    "J2_EARTH",
    "J2_JUPITER",
    "LIGHT_YEAR_M",
    "R_EARTH_M",
    "R_JUPITER_M",
    "R_SUN_M",
    "SPEED_OF_LIGHT_M_S",
    "TwoBodyOrbit",
    "hohmann_transfer_delta_v",
    "kepler_period",
    "planetary_capture_delta_v",
    "vis_viva_speed",
    "slingshot_vector_delta_v",
    "StarCatalogEntry",
    "propagate_proper_motion",
    "NBodySystem",
    "acceleration_nbody",
    "rk4_step",
    "rk78_adaptive_step",
    "BodyState",
    "AnalyticEphemeris",
    "HorizonsRestEphemeris",
    "SpiceEphemeris",
    "KernelManager",
    "get_body_state",
    # Space environment + Lorentz/magnetic
    "ChargingRisk",
    "assess_charging_risk",
    "dose_rate_msv_day",
    "gyroradius_m",
    "igrf_dipole",
    "lorentz_acceleration",
    "lorentz_force",
    "magnetic_l_shell",
    "magnetic_torque",
    "plasma_density_m3",
    "plasma_temperature_k",
    "south_atlantic_anomaly_boost",
    "van_allen_belt_traversal_dose_msv",
    "van_allen_electron_flux",
    "van_allen_proton_flux",
]
