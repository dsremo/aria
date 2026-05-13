"""Corrosion and oxidation kinetics for spacecraft structural materials.

Parabolic, linear, and logarithmic high-temperature oxidation (Wagner 1933,
Pilling & Bedworth 1923, Cabrera-Mott 1949), pitting corrosion depth
(Godard 1967), atomic-oxygen ATOX erosion at LEO (Brinza 2001), and
stress corrosion cracking threshold check (ASTM E1820).

Public API:
    TI_6AL_4V_OXIDATION, EUROFER97_OXIDATION, MO_RE_OXIDATION, AL_6061_OXIDATION
    OxidationMaterial
    parabolic_rate_constant_m2_s
    linear_rate_constant_m_s
    oxide_thickness_parabolic_m
    oxide_thickness_linear_m
    oxide_thickness_logarithmic_m
    pilling_bedworth_ratio
    mass_gain_kg_m2_parabolic
    pitting_depth_m
    atox_erosion_depth_m
    is_scc_risk
"""

from .oxidation_kinetics import (
    AL_6061_OXIDATION,
    AL_PITTING_A,
    AL_PITTING_N,
    ATOX_EROSION_YIELD_AL_OXIDE,
    ATOX_EROSION_YIELD_KAPTON,
    ATOX_O_FLUX_LEO_PER_M2_S,
    EUROFER97_OXIDATION,
    MO_RE_OXIDATION,
    OxidationMaterial,
    TI_6AL_4V_OXIDATION,
    atox_erosion_depth_m,
    is_scc_risk,
    linear_rate_constant_m_s,
    mass_gain_kg_m2_parabolic,
    oxide_thickness_linear_m,
    oxide_thickness_logarithmic_m,
    oxide_thickness_parabolic_m,
    parabolic_rate_constant_m2_s,
    pilling_bedworth_ratio,
    pitting_depth_m,
)

__all__ = [
    "AL_6061_OXIDATION",
    "AL_PITTING_A",
    "AL_PITTING_N",
    "ATOX_EROSION_YIELD_AL_OXIDE",
    "ATOX_EROSION_YIELD_KAPTON",
    "ATOX_O_FLUX_LEO_PER_M2_S",
    "EUROFER97_OXIDATION",
    "MO_RE_OXIDATION",
    "OxidationMaterial",
    "TI_6AL_4V_OXIDATION",
    "atox_erosion_depth_m",
    "is_scc_risk",
    "linear_rate_constant_m_s",
    "mass_gain_kg_m2_parabolic",
    "oxide_thickness_linear_m",
    "oxide_thickness_logarithmic_m",
    "oxide_thickness_parabolic_m",
    "parabolic_rate_constant_m2_s",
    "pilling_bedworth_ratio",
    "pitting_depth_m",
]
