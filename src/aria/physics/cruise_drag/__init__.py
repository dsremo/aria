"""Interstellar / intergalactic cruise drag and accretion.

Closes Phase 3 with the ISM ram-pressure drag, Bondi-Hoyle accretion
rate, and Chandrasekhar 1943 dynamical friction primitives that the
long-cruise navigation budget needs but that no single scope note
explicitly owned.

References:
  - Ferrière 2001 *Rev Mod Phys* 73 1031 — ISM phase densities.
  - Redfield & Linsky 2008 *ApJ* 673 283 — Local Interstellar Cloud
    parameters.
  - Bondi & Hoyle 1944 *MNRAS* 104 273; Bondi 1952 *MNRAS* 112 195
    — spherical accretion onto a moving body.
  - Chandrasekhar 1943 *ApJ* 97 255 — dynamical friction formula.
  - Binney & Tremaine 2008 *Galactic Dynamics* 2nd ed §8.1 — modern
    dynamical-friction treatment (ISBN 978-0691130279).
"""

from __future__ import annotations

from .bondi_accretion import (
    bondi_accretion_rate_kg_s,
    bondi_hoyle_rate_kg_s,
)
from .dynamical_friction import (
    chandrasekhar_dynamical_friction_acceleration,
    coulomb_log_default,
)
from .ism_phases import (
    COLD_NEUTRAL_MEDIUM,
    ISMPhase,
    LOCAL_INTERSTELLAR_CLOUD,
    LOCAL_BUBBLE,
    WARM_NEUTRAL_MEDIUM,
    get_ism_phase,
)
from .ram_pressure import (
    ram_pressure_drag_acceleration,
    ram_pressure_pa,
    stopping_length_m,
)

__all__ = [
    "COLD_NEUTRAL_MEDIUM",
    "ISMPhase",
    "LOCAL_BUBBLE",
    "LOCAL_INTERSTELLAR_CLOUD",
    "WARM_NEUTRAL_MEDIUM",
    "bondi_accretion_rate_kg_s",
    "bondi_hoyle_rate_kg_s",
    "chandrasekhar_dynamical_friction_acceleration",
    "coulomb_log_default",
    "get_ism_phase",
    "ram_pressure_drag_acceleration",
    "ram_pressure_pa",
    "stopping_length_m",
]
