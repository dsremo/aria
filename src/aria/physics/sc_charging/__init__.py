"""Spacecraft charging (Pod D2 — P1-4 / P1-8).

Surface (frame) charging, Debye sheath, deep-dielectric bulk charging,
and electrostatic-discharge (ESD) triggering for a spacecraft in plasma +
energetic-electron environment.

References: Lai 2012 *Fundamentals of Spacecraft Charging* (ISBN
978-0691129471); NASA-HDBK-4002A (2011); Chen 2016 *Introduction to
Plasma Physics* 3rd ed (ISBN 978-3319223087); Mullen et al. 1986
*J Spacecr Rockets* 23 593 (SCATHA); Frederickson et al. 1992
*IEEE Trans Nucl Sci* 39 1773.
"""

from __future__ import annotations

from .surface_current_balance import (
    ambient_electron_current_density,
    ambient_ion_current_density,
    equilibrium_surface_potential,
    photoemission_current_density,
    worst_case_eclipse_potential,
)
from .debye_sheath import child_langmuir_sheath_thickness, debye_length
from .deep_dielectric import (
    csda_range_kg_m2,
    csda_range_m,
    peak_internal_field_parallel_plate,
)
from .esd_trigger import (
    arc_energy_parallel_plate,
    esd_probability_per_hour,
    esd_triggered,
)
from .materials_db import DIELECTRIC_TABLE, Dielectric, get_dielectric

__all__ = [
    "DIELECTRIC_TABLE",
    "Dielectric",
    "ambient_electron_current_density",
    "ambient_ion_current_density",
    "arc_energy_parallel_plate",
    "child_langmuir_sheath_thickness",
    "csda_range_kg_m2",
    "csda_range_m",
    "debye_length",
    "equilibrium_surface_potential",
    "esd_probability_per_hour",
    "esd_triggered",
    "get_dielectric",
    "peak_internal_field_parallel_plate",
    "photoemission_current_density",
    "worst_case_eclipse_potential",
]
