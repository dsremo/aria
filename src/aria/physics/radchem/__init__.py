"""Radiation chemistry (Pod J2 — P1-9).

Water radiolysis primary G-values with LET dependence (Spinks & Woods
1990, Pastina & LaVerne 2001, Elliot & Bartels 2009), H₂ source term
and steady-state H₂/H₂O₂ balances in shield water, and polymer damage
via Charlesby-Pinner sol-fraction and Clough 1988 Weibull mechanical
degradation.

References (full bibliography in the J2 scope note):
  - Spinks & Woods 1990 *An Introduction to Radiation Chemistry* 3rd
    ed Wiley.
  - Elliot & Bartels 2009 AECL-153-127160-450-001.
  - Pastina & LaVerne 2001 *J Phys Chem A* 105 9316.
  - Charlesby & Pinner 1959 *Proc Roy Soc A* 249 367.
  - Dole 1972 *Radiation Chemistry of Macromolecules* vol 1 Academic.
  - Clough 1988 *IEEE Trans Nucl Sci* NS-35 1302.
  - Clough & Gillen 1989 *Radiation-Induced Oxidation Reactions*
    Elsevier.
"""

from __future__ import annotations

from .g_values import (
    G_VALUE_LOW_LET_WATER,
    g_value_hydrogen_let,
    molar_production_rate,
    species_molar_production_rate,
)
from .polymer_damage import (
    POLYMER_J2_TABLE,
    PolymerJ2,
    charlesby_pinner_sol_fraction,
    clough_weibull_elongation_retention,
    clough_weibull_tensile_retention,
    get_polymer_j2,
)
from .water_steady_state import (
    hydrogen_steady_state_concentration,
    hydrogen_outgas_rate_mol_s,
)

__all__ = [
    "G_VALUE_LOW_LET_WATER",
    "POLYMER_J2_TABLE",
    "PolymerJ2",
    "charlesby_pinner_sol_fraction",
    "clough_weibull_elongation_retention",
    "clough_weibull_tensile_retention",
    "g_value_hydrogen_let",
    "get_polymer_j2",
    "hydrogen_outgas_rate_mol_s",
    "hydrogen_steady_state_concentration",
    "molar_production_rate",
    "species_molar_production_rate",
]
