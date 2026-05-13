"""Pod A2 — Tidal tensor, gravitational time dilation, frame dragging,
gravitational waves, galactic tidal field.

Implements audit items §1.1.12–§1.1.14 (tidal forces), §1.1.16–§1.1.17
(gravitational time dilation + redshift), §1.1.19–§1.1.21 (frame
dragging, gravitomagnetism, gravitational waves), §1.1.23 (galactic
tidal field).

See `docs/pods/A2_tidal_tensor.md` for the scope note (derivations,
citations, test cases).

Public API:
    tidal_tensor_single_perturber      — E^i_j = (GM/r³)(δ − 3n̂n̂)
    tidal_tensor_total                 — Σ over N perturbers
    tidal_tensor_trace                 — diagnostic: should be ~0 in vacuum
    tidal_acceleration_on_point        — F^i = −E^i_j L^j  for a hull point
    radial_tidal_acceleration          — 2GML/r³ closed-form
    schwarzschild_pn_correction        — r_s/r fractional PN factor
    gravitational_potential            — Φ(r) = −Σ GM/|r−R|
    gravitational_time_dilation_rate   — dτ/dt = 1 + Φ/c²
    gravitational_redshift             — Δν/ν = (Φ_emit − Φ_recv)/c²
    pound_rebka_shift                  — gh/c² for a uniform vertical field
    lense_thirring_precession          — Ω_LT = (G/c²r³)(3(Ĵ·r̂)r̂ − Ĵ)
    lense_thirring_polar_rate          — |Ω_LT| = 2GJ/(c²r³)
    peters_mathews_gw_power            — (32/5)(G⁴/c⁵) m₁²m₂²(m₁+m₂)/r⁵
    oort_galactic_tidal_tensor         — galactic Oort-A/B tensor
"""

from .tidal_tensor import (
    radial_tidal_acceleration,
    tidal_acceleration_on_point,
    tidal_tensor_single_perturber,
    tidal_tensor_total,
    tidal_tensor_trace,
)
from .tidal_tensor_pn import schwarzschild_pn_correction
from .grav_time_dilation import (
    gravitational_potential,
    gravitational_time_dilation_rate,
)
from .grav_redshift import gravitational_redshift, pound_rebka_shift
from .lense_thirring import (
    J_EARTH_KG_M2_S,
    J_JUPITER_KG_M2_S,
    J_SUN_KG_M2_S,
    lense_thirring_polar_rate,
    lense_thirring_precession,
    lense_thirring_schiff_polar_orbit,
)
from .gw_energy_loss import peters_mathews_gw_power
from .galactic_tidal import (
    OORT_A_KM_S_KPC,
    OORT_B_KM_S_KPC,
    RHO_LOCAL_KG_M3,
    oort_galactic_tidal_tensor,
)
from .hull_tidal_loading import (
    differential_tidal_acceleration_m_s2,
    hull_tidal_acceleration_profile,
    hull_tidal_bending_moment_Nm,
    hull_tidal_tension_N,
    is_tidal_stress_critical,
    max_tidal_differential_m_s2,
    solar_perihelion_tidal_scenario,
    tidal_stress_at_cross_section_Pa,
)

__all__ = [
    # Tidal tensor
    "tidal_tensor_single_perturber",
    "tidal_tensor_total",
    "tidal_tensor_trace",
    "tidal_acceleration_on_point",
    "radial_tidal_acceleration",
    "schwarzschild_pn_correction",
    # Clocks / redshift
    "gravitational_potential",
    "gravitational_time_dilation_rate",
    "gravitational_redshift",
    "pound_rebka_shift",
    # Frame dragging
    "J_EARTH_KG_M2_S",
    "J_JUPITER_KG_M2_S",
    "J_SUN_KG_M2_S",
    "lense_thirring_precession",
    "lense_thirring_polar_rate",
    "lense_thirring_schiff_polar_orbit",
    # GW
    "peters_mathews_gw_power",
    # Galactic
    "OORT_A_KM_S_KPC",
    "OORT_B_KM_S_KPC",
    "RHO_LOCAL_KG_M3",
    "oort_galactic_tidal_tensor",
    # Extended-body hull tidal loading
    "differential_tidal_acceleration_m_s2",
    "hull_tidal_acceleration_profile",
    "hull_tidal_bending_moment_Nm",
    "hull_tidal_tension_N",
    "is_tidal_stress_critical",
    "max_tidal_differential_m_s2",
    "solar_perihelion_tidal_scenario",
    "tidal_stress_at_cross_section_Pa",
]
