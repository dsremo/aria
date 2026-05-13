"""Spacecraft fire safety — first-principles combustion kinetics.

Provides Arrhenius global reaction rates, laminar flame speed (Metghalchi &
Keck 1982), adiabatic flame temperature, LOI criterion (NASA-STD-6001B),
microgravity flame-speed correction (Ronney 1985), and flashover HRR
threshold (Quintiere 1995).

Public API:
    METHANE, ETHANOL, N_HEPTANE, HYDROGEN — FuelKinetics presets
    FuelKinetics
    molar_concentration_mol_m3
    global_reaction_rate_mol_m3_s
    heat_release_rate_W_m3
    adiabatic_flame_temperature_K
    laminar_flame_speed_m_s
    is_above_loi
    stoichiometric_o2_mass_fraction
    microgravity_flame_speed_m_s
    flashover_hrr_threshold_W
    is_flashover_risk
"""

from .combustion_kinetics import (
    ETHANOL,
    HYDROGEN,
    METHANE,
    MICROGRAVITY_FLAME_SPEED_FACTOR,
    N_HEPTANE,
    P_REF_PA,
    RADIATIVE_EXTINCTION_FLAME_SPEED_M_S,
    T_REF_K,
    FuelKinetics,
    adiabatic_flame_temperature_K,
    flashover_hrr_threshold_W,
    global_reaction_rate_mol_m3_s,
    heat_release_rate_W_m3,
    is_above_loi,
    is_flashover_risk,
    laminar_flame_speed_m_s,
    microgravity_flame_speed_m_s,
    molar_concentration_mol_m3,
    stoichiometric_o2_mass_fraction,
)

__all__ = [
    "ETHANOL",
    "HYDROGEN",
    "METHANE",
    "MICROGRAVITY_FLAME_SPEED_FACTOR",
    "N_HEPTANE",
    "P_REF_PA",
    "RADIATIVE_EXTINCTION_FLAME_SPEED_M_S",
    "T_REF_K",
    "FuelKinetics",
    "adiabatic_flame_temperature_K",
    "flashover_hrr_threshold_W",
    "global_reaction_rate_mol_m3_s",
    "heat_release_rate_W_m3",
    "is_above_loi",
    "is_flashover_risk",
    "laminar_flame_speed_m_s",
    "microgravity_flame_speed_m_s",
    "molar_concentration_mol_m3",
    "stoichiometric_o2_mass_fraction",
]
