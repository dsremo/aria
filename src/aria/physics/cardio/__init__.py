"""Cardiovascular deconditioning (Pod K2 — P1-10).

First-order compartment models for plasma-volume loss, cephalic
fluid shift, cardiac mass atrophy, SANS onset, and orthostatic-
intolerance probability under partial-g exposure.

References (full bibliography in the K2 scope note):
  - Convertino 1996 *J Appl Physiol* 81 7 — biphasic PV kinetics.
  - Hargens & Vico 2016 *Eur J Appl Physiol* 116 29.
  - Pavy-Le Traon et al. 2007 *Eur J Appl Physiol* 101 143.
  - Perhonen et al. 2001 *J Appl Physiol* 91 645.
  - Buckey et al. 1996 *J Appl Physiol* 81 7 — orthostatic logistic.
  - Mader et al. 2011 *Ophthalmology* 118 2058; Lee 2018 *npj
    Microgravity* 4 10 — SANS progression.
  - Lee et al. 2015 *Aviat Space Environ Med* 86 A1 — ARED effect.
"""

from __future__ import annotations

from .compartments import (
    CARDIAC_MASS_ALPHA,
    CARDIAC_MASS_TAU_DAYS,
    CONVERTINO_A_FAST,
    CONVERTINO_A_SLOW,
    CONVERTINO_TAU_FAST_H,
    CONVERTINO_TAU_SLOW_D,
    FLUID_SHIFT_DELTA_V_MAX_L,
    FLUID_SHIFT_TAU_HOURS,
    cardiac_mass_retention,
    cephalic_fluid_volume,
    plasma_volume_fraction,
)
from .sans_model import (
    SANS_K_PER_DAY,
    SANS_ONSET_DAYS,
    sans_probability,
)
from .orthostatic import (
    BUCKEY_BETA_DURATION,
    BUCKEY_BETA_PV,
    BUCKEY_INTERCEPT,
    orthostatic_intolerance_probability,
)
from .countermeasures import (
    ARED_EFFECTIVENESS_FRACTION,
    apply_countermeasure_reduction,
)

__all__ = [
    "ARED_EFFECTIVENESS_FRACTION",
    "BUCKEY_BETA_DURATION",
    "BUCKEY_BETA_PV",
    "BUCKEY_INTERCEPT",
    "CARDIAC_MASS_ALPHA",
    "CARDIAC_MASS_TAU_DAYS",
    "CONVERTINO_A_FAST",
    "CONVERTINO_A_SLOW",
    "CONVERTINO_TAU_FAST_H",
    "CONVERTINO_TAU_SLOW_D",
    "FLUID_SHIFT_DELTA_V_MAX_L",
    "FLUID_SHIFT_TAU_HOURS",
    "SANS_K_PER_DAY",
    "SANS_ONSET_DAYS",
    "apply_countermeasure_reduction",
    "cardiac_mass_retention",
    "cephalic_fluid_volume",
    "orthostatic_intolerance_probability",
    "plasma_volume_fraction",
    "sans_probability",
]
