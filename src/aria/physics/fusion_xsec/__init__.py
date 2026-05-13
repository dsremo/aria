"""Fusion cross sections and tritium breeding (Pod E1 — P1-11).

Bosch-Hale 1992 Maxwellian-averaged D-T fusion reactivity, volumetric
fusion power, single-level Breit-Wigner capture cross section with an
optional zero-T Lorentzian kernel (Doppler broadening deferred to the
ENDF pipeline), and ⁶Li / ⁷Li tritium-breeding closed-form checks.

References (full list in the E1 scope note):
  - Bosch & Hale 1992 *Nucl Fusion* 32 611 — reactivity fit.
  - Brown et al. 2018 *Nucl Data Sheets* 148 1 — ENDF/B-VIII.0.
  - Cullen & Weisbin 1976 *Nucl Sci Eng* 60 199 — Doppler ψ-χ.
  - Abdou et al. 2015 *Fusion Eng Des* 100 2 — TBR ≥ 1.10 requirement.
  - Federici et al. 2019 *Fusion Eng Des* 141 30 — HCPB blanket
    reference TBR.
"""

from __future__ import annotations

from .bosch_hale import (
    BOSCH_HALE_DT_COEFFS,
    Q_DT_MEV,
    Q_NEUTRON_DT_MEV,
    bosch_hale_dt_reactivity_m3_s,
    fusion_power_density_w_m3,
    fusion_power_volumetric,
)
from .breit_wigner import (
    breit_wigner_capture_cross_section_barn,
)
from .endf_anchors import (
    LI6_NALPHA_THERMAL_BARN,
    LI6_NATURAL_ABUNDANCE,
    LI7_NALPHA_THRESHOLD_MEV,
    REQUIRED_TBR_ABDOU_2015,
    meets_tbr_requirement,
)

__all__ = [
    "BOSCH_HALE_DT_COEFFS",
    "LI6_NALPHA_THERMAL_BARN",
    "LI6_NATURAL_ABUNDANCE",
    "LI7_NALPHA_THRESHOLD_MEV",
    "Q_DT_MEV",
    "Q_NEUTRON_DT_MEV",
    "REQUIRED_TBR_ABDOU_2015",
    "bosch_hale_dt_reactivity_m3_s",
    "breit_wigner_capture_cross_section_barn",
    "fusion_power_density_w_m3",
    "fusion_power_volumetric",
    "meets_tbr_requirement",
]
