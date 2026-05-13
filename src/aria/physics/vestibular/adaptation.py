"""Vestibular adaptation envelope (§4.6 of C2 scope).

Crew members exposed continuously to a rotating environment
gradually adapt: motion sickness symptoms wane over hours to days,
and the comfort thresholds for cross-coupled angular acceleration
relax accordingly. The empirical fit (Graybiel 1975 *Aerospace
Medicine* 46(9) 1155-1161; Young 2019 *Aviat Space Environ Med*
90(6) 574-584) is a simple exponential approach to full adaptation:

    P_adapted(E) = 1 − exp(−E / E_½)                     [dimensionless]

with `E` the cumulative exposure time spent above the spin
threshold (s) and `E_½ ≈ 72 h ≈ 2.59×10⁵ s` for a 4 rpm habitat
(Young 2019 Fig 3 fit; the published range is 48-120 h depending
on subject population, with 72 h as the midpoint).

Interpretation: after one E_½ of cumulative exposure (~3 days),
~63% of crew members have adapted. After two E_½ (~6 days), ~86%.
After three (~9 days), ~95%. The remaining ~5% are persistent
non-adapters who would need to be assigned to non-rotating duties
or to the ship hub.
"""

from __future__ import annotations

import math


# Young 2019 Fig 3 midpoint of the 48-120 h range.
YOUNG_2019_E_HALF_S: float = 72.0 * 3600.0  # 2.592e5 s


def adaptation_probability(
    cumulative_exposure_s: float,
    e_half_s: float = YOUNG_2019_E_HALF_S,
) -> float:
    """Probability that a representative crew member has adapted
    after `E` seconds of cumulative spin-environment exposure.

    P(E) = 1 − exp(−E / E_½)                              [dimensionless]

    Args:
        cumulative_exposure_s: total time spent in the rotating
            environment above the spin-rate threshold (s). Negative
            values are clamped to 0.
        e_half_s: half-dose constant (s). Default = Young 2019 fit
            for 4 rpm.

    Returns:
        Adaptation probability in [0, 1].
    """
    if e_half_s <= 0.0:
        raise ValueError("e_half_s must be positive")
    if cumulative_exposure_s <= 0.0:
        return 0.0
    return 1.0 - math.exp(-cumulative_exposure_s / e_half_s)
