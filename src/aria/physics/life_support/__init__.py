"""ECLSS physics models for habitat atmosphere and life-support systems.

Provides first-principles mass-balance models for:
  - O₂/CO₂ cabin atmosphere (partial pressures, ppm)
  - CDRA two-bed molecular sieve degradation (sorption capacity decay)
  - Sabatier reactor CO₂ methanation with catalyst aging
  - OGA (O₂ generation assembly) electrolysis cell degradation
  - Trace contaminant kinetics (CO, CH₄, acetaldehyde)
"""

from .humidity import (
    RH_COMFORT_MAX,
    RH_COMFORT_MIN,
    RH_MOLD_THRESHOLD,
    comfort_assessment,
    condensation_rate_kg_m2_s,
    dew_point_K,
    is_condensation_risk,
    relative_humidity,
    saturation_vapour_pressure_kPa,
    specific_humidity_kg_per_kg,
    vapour_pressure_from_rh_kPa,
)
from .atmosphere_dynamics import (
    CREW_CO2_KG_DAY,
    CREW_O2_KG_DAY,
    CDRA_NOMINAL_EFFICIENCY,
    SABATIER_NOMINAL_EFFICIENCY,
    OGA_NOMINAL_RATE_KG_DAY_PER_CREW,
    AtmosphereState,
    EclssConfig,
    cdra_scrubbing_efficiency,
    oga_o2_rate_kg_day,
    sabatier_co2_removal_fraction,
    step_atmosphere,
    cabin_co2_ppm,
    co2_incapacitation_risk,
    o2_hypoxia_risk,
)

__all__ = [
    # Humidity
    "RH_COMFORT_MAX",
    "RH_COMFORT_MIN",
    "RH_MOLD_THRESHOLD",
    "comfort_assessment",
    "condensation_rate_kg_m2_s",
    "dew_point_K",
    "is_condensation_risk",
    "relative_humidity",
    "saturation_vapour_pressure_kPa",
    "specific_humidity_kg_per_kg",
    "vapour_pressure_from_rh_kPa",
    # Atmosphere
    "CREW_CO2_KG_DAY",
    "CREW_O2_KG_DAY",
    "CDRA_NOMINAL_EFFICIENCY",
    "SABATIER_NOMINAL_EFFICIENCY",
    "OGA_NOMINAL_RATE_KG_DAY_PER_CREW",
    "AtmosphereState",
    "EclssConfig",
    "cdra_scrubbing_efficiency",
    "oga_o2_rate_kg_day",
    "sabatier_co2_removal_fraction",
    "step_atmosphere",
    "cabin_co2_ppm",
    "co2_incapacitation_risk",
    "o2_hypoxia_risk",
]
