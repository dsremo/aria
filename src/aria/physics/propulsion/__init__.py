"""Spacecraft propulsion physics — pressurization systems.

Blowdown and regulated propellant tank pressurization (Huzel & Huang 1992),
pressurant absorption by Henry's law (Wiktorowicz 1972), and
pressurant mass budget (Larson & Wertz 1999 §18).

Public API:
    HELIUM, NITROGEN, GN2
    PressurantGas
    blowdown_pressure_Pa
    blowdown_pressure_ratio
    blowdown_pressure_ratio_isothermal
    blowdown_pressure_ratio_adiabatic
    dissolved_pressurant_mol_m3
    absorbed_pressurant_volume_m3
    absorption_volume_fraction
    pressurant_mass_kg_regulated
    pressurant_bottle_volume_m3
    blowdown_final_pressure_with_absorption
    blowdown_pressure_history
"""

from .pressurization import (
    GN2,
    HELIUM,
    NITROGEN,
    PressurantGas,
    R_UNIVERSAL,
    absorbed_pressurant_volume_m3,
    absorption_volume_fraction,
    blowdown_final_pressure_with_absorption,
    blowdown_pressure_Pa,
    blowdown_pressure_history,
    blowdown_pressure_ratio,
    blowdown_pressure_ratio_adiabatic,
    blowdown_pressure_ratio_isothermal,
    dissolved_pressurant_mol_m3,
    pressurant_bottle_volume_m3,
    pressurant_mass_kg_regulated,
)

__all__ = [
    "GN2",
    "HELIUM",
    "NITROGEN",
    "PressurantGas",
    "R_UNIVERSAL",
    "absorbed_pressurant_volume_m3",
    "absorption_volume_fraction",
    "blowdown_final_pressure_with_absorption",
    "blowdown_pressure_Pa",
    "blowdown_pressure_history",
    "blowdown_pressure_ratio",
    "blowdown_pressure_ratio_adiabatic",
    "blowdown_pressure_ratio_isothermal",
    "dissolved_pressurant_mol_m3",
    "pressurant_bottle_volume_m3",
    "pressurant_mass_kg_regulated",
]
