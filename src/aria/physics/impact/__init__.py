"""Pod F4 — Hypervelocity impact and Whipple shield mechanics.

Implements audit items §5.18 (Hertzian contact), §5.19 (Whipple
shield / hypervelocity impact), §5.20 (Hugoniot shock propagation).

Covers four impact regimes with a closed-form dispatcher:
  1. Hertzian elastic contact        (v < ~50 m/s)
  2. Low-velocity impact             (50 m/s .. 3 km/s)
  3. Hypervelocity / Christiansen    (3 km/s .. 15 km/s)
  4. Ultra-relativistic dust         (> 0.01 c, ESTIMATE regime)

See `docs/pods/F4_whipple_hvimpact.md` for the scope note.

Public API:
    hertzian_contact_force        — F = (4/3) E* √R δ^(3/2)
    hertzian_max_pressure         — p_0 from F, E*, R
    reduced_elastic_modulus       — 1/E* = (1-ν₁²)/E₁ + (1-ν₂²)/E₂
    hugoniot_shock_velocity       — U_s = c_0 + s u_p (Marsh 1980)
    hugoniot_peak_pressure        — p_H = ρ_0 U_s u_p
    hugoniot_peak_density         — Rankine-Hugoniot mass jump
    crater_depth_christiansen     — NASA TM-105002 scaling
    whipple_critical_diameter_nno — NNO ballistic-limit equation
    whipple_is_perforated         — dispatcher for the BLE
    ejecta_mass_schonberg         — M_ej ≈ 10 m_p (v/3km/s)
    relativistic_impact_kinetic_energy
    relativistic_impact_momentum
    ImpactRegime                  — regime enum
    classify_impact_regime        — (v, d) → regime label
    HugoniotMaterial              — c_0, s, Γ_0, ρ_0 bundle
    MMOD_AL_2024_T3, MMOD_TI_6AL_4V
"""

from .hertzian import (
    hertzian_contact_force,
    hertzian_contact_radius,
    hertzian_max_pressure,
    reduced_elastic_modulus,
)
from .hugoniot import (
    HUGONIOT_AL_2024_T3,
    HUGONIOT_TI_6AL_4V,
    HugoniotMaterial,
    hugoniot_peak_density,
    hugoniot_peak_pressure,
    hugoniot_shock_velocity,
)
from .crater import crater_depth_christiansen
from .whipple import (
    ImpactRegime,
    classify_impact_regime,
    whipple_critical_diameter_nno,
    whipple_is_perforated,
)
from .ejecta import (
    ejecta_cone_half_angle_default,
    ejecta_mass_schonberg,
)
from .relativistic_dust import (
    ULTRA_RELATIVISTIC_THRESHOLD_FRACTION_C,
    is_ultra_relativistic_regime,
    relativistic_impact_kinetic_energy,
    relativistic_impact_momentum,
)
from .ism_ablation import (
    ABLATION_BE,
    ABLATION_C_C,
    ABLATION_TI_6AL_4V,
    AblationMaterial,
    ISM_DUST_GAS_RATIO,
    ISM_HE_H_RATIO,
    ISM_MEAN_GRAIN_MASS_KG,
    ISM_N_H_PER_M3,
    PLASMA_ABLATION_VELOCITY_M_S,
    dust_grain_ablation_rate_kg_m2_s,
    gas_sputtering_rate_kg_m2_s,
    ism_ablation_depth_m,
    ism_ablation_rate_kg_m2_s,
    ism_alpha_flux_per_m2_s,
    ism_dust_flux_kg_m2_s,
    ism_proton_flux_per_m2_s,
    is_plasma_ablation_regime,
    mission_ablation_budget,
    proton_kinetic_energy_J,
)

__all__ = [
    "hertzian_contact_force",
    "hertzian_contact_radius",
    "hertzian_max_pressure",
    "reduced_elastic_modulus",
    "HugoniotMaterial",
    "HUGONIOT_AL_2024_T3",
    "HUGONIOT_TI_6AL_4V",
    "hugoniot_shock_velocity",
    "hugoniot_peak_pressure",
    "hugoniot_peak_density",
    "crater_depth_christiansen",
    "ImpactRegime",
    "classify_impact_regime",
    "whipple_critical_diameter_nno",
    "whipple_is_perforated",
    "ejecta_mass_schonberg",
    "ejecta_cone_half_angle_default",
    "ULTRA_RELATIVISTIC_THRESHOLD_FRACTION_C",
    "is_ultra_relativistic_regime",
    "relativistic_impact_kinetic_energy",
    "relativistic_impact_momentum",
    # ISM ablation
    "ABLATION_BE",
    "ABLATION_C_C",
    "ABLATION_TI_6AL_4V",
    "AblationMaterial",
    "ISM_DUST_GAS_RATIO",
    "ISM_HE_H_RATIO",
    "ISM_MEAN_GRAIN_MASS_KG",
    "ISM_N_H_PER_M3",
    "PLASMA_ABLATION_VELOCITY_M_S",
    "dust_grain_ablation_rate_kg_m2_s",
    "gas_sputtering_rate_kg_m2_s",
    "ism_ablation_depth_m",
    "ism_ablation_rate_kg_m2_s",
    "ism_alpha_flux_per_m2_s",
    "ism_dust_flux_kg_m2_s",
    "ism_proton_flux_per_m2_s",
    "is_plasma_ablation_regime",
    "mission_ablation_budget",
    "proton_kinetic_energy_J",
]
