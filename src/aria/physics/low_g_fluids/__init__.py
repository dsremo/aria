"""Low-gravity and capillary-dominated fluids (Pod H2 — P1-6).

Dimensionless-regime detection, Young-Laplace capillary statics,
Abramson sloshing modes in upright cylinders and centrifuged ring
tanks, Marangoni thermocapillary primitives, and non-Newtonian
constitutive laws (Carreau, power-law, Bingham) needed by downstream
rheology consumers.

References (full bibliography in the H2 scope note):
  - Myshkis et al. 1987 *Low-Gravity Fluid Mechanics* (Springer, ISBN
    978-3642708329).
  - Landau & Lifshitz 1987 *Fluid Mechanics* 2nd ed §61.
  - Abramson (ed.) 1966 NASA SP-106 "The Dynamic Behavior of Liquids in
    Moving Containers".
  - Ibrahim 2005 *Liquid Sloshing Dynamics* (ISBN 978-0521838856).
  - Pearson 1958 *J Fluid Mech* 4 489.
  - Bird, Stewart & Lightfoot 2007 *Transport Phenomena* 2nd ed.
  - Yeleswarapu 1998 PhD thesis Univ Pittsburgh.
"""

from __future__ import annotations

from .dimensionless import (
    bond_number,
    capillary_number,
    marangoni_number,
    ohnesorge_number,
    weber_number,
)
from .fluids_db import FluidH2, FLUID_H2_TABLE, get_fluid_h2
from .nonnewtonian import (
    BLOOD_CARREAU_YELESWARAPU,
    CarreauModel,
    bingham_apparent_viscosity,
    carreau_apparent_viscosity,
    power_law_apparent_viscosity,
)
from .slosh_modal import (
    ABRAMSON_XI_11,
    centrifuged_ring_tank_frequency,
    cylindrical_tank_slosh_frequency,
    spring_mass_slosh_mass_ratio,
)
from .young_laplace import (
    BOND_CAPILLARY_THRESHOLD,
    capillary_length,
    capillary_pressure_spherical_cap,
    is_capillary_regime,
    jurin_capillary_rise,
    young_laplace_pressure_jump,
)

__all__ = [
    "ABRAMSON_XI_11",
    "BLOOD_CARREAU_YELESWARAPU",
    "BOND_CAPILLARY_THRESHOLD",
    "CarreauModel",
    "FLUID_H2_TABLE",
    "FluidH2",
    "bingham_apparent_viscosity",
    "bond_number",
    "capillary_length",
    "capillary_number",
    "capillary_pressure_spherical_cap",
    "carreau_apparent_viscosity",
    "centrifuged_ring_tank_frequency",
    "cylindrical_tank_slosh_frequency",
    "get_fluid_h2",
    "is_capillary_regime",
    "jurin_capillary_rise",
    "marangoni_number",
    "ohnesorge_number",
    "power_law_apparent_viscosity",
    "spring_mass_slosh_mass_ratio",
    "weber_number",
    "young_laplace_pressure_jump",
]
