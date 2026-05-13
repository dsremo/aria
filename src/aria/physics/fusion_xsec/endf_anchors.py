"""ENDF/B-VIII.0 canonical anchor values and TBR gate (§5 of E1 scope).

Thermal-point cross sections and abundances that E1 needs before the
NJOY/ENDF pipeline delivers full group constants. Every value carries
a per-line citation. The required tritium breeding ratio gate from
Abdou et al. 2015 *Fusion Eng Des* 100 2 is the threshold the full
fuel-cycle model must clear to close the tritium inventory without
resupply.
"""

from __future__ import annotations

# ENDF/B-VIII.0 MT=105 at 0.0253 eV, Brown et al. 2018
# *Nucl Data Sheets* 148 1.
LI6_NALPHA_THERMAL_BARN: float = 940.0

# ⁷Li(n,n'α)T threshold — endothermic reaction, ENDF/B-VIII.0 MT=205.
LI7_NALPHA_THRESHOLD_MEV: float = 2.467

# IUPAC 2021 / Meija et al. 2016 *Pure Appl Chem* 88 293.
LI6_NATURAL_ABUNDANCE: float = 0.0759

# Abdou et al. 2015 *Fusion Eng Des* 100 2 — minimum TBR for
# self-sustaining D-T fuel cycle including losses.
REQUIRED_TBR_ABDOU_2015: float = 1.10


def meets_tbr_requirement(
    local_tbr: float, threshold: float = REQUIRED_TBR_ABDOU_2015
) -> bool:
    """Return True iff `local_tbr ≥ threshold`.

    A `tbr ≥ 1.10` blanket design closes the tritium cycle against
    radioactive decay, plasma burn-up, and processing losses (Abdou
    et al. 2015 eq. 12). Values below the threshold require either
    external tritium resupply or a redesigned multiplier.
    """
    if local_tbr < 0.0:
        raise ValueError("local_tbr must be non-negative")
    if threshold <= 0.0:
        raise ValueError("threshold must be positive")
    return local_tbr >= threshold
