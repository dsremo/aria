"""Weak / strong equivalence-principle bounds (§4.1, §4.2 of M2).

Eötvös parameter definition (Will 2014 *Living Rev Relativ* 17 4
§2.1):

    η(A, B) = 2 (a_A − a_B) / (a_A + a_B)                     [–]

and the MICROSCOPE 2017 experimental bound
|η| ≤ 1.5×10⁻¹⁵ (Touboul et al. 2017 *PRL* 119 231101) that M2
uses as the prior on any composition-dependent acceleration
difference.
"""

from __future__ import annotations

from .bounds_db import MICROSCOPE_ETA_BOUND


def eotvos_parameter(
    acceleration_a_m_s2: float,
    acceleration_b_m_s2: float,
) -> float:
    """Canonical Eötvös parameter for two test masses in the same
    gravitational field.

    η = 2 (a_A − a_B) / (a_A + a_B)                          [–]

    Returns 0 when both accelerations are zero (defined limit).
    """
    denom = acceleration_a_m_s2 + acceleration_b_m_s2
    if denom == 0.0:
        return 0.0
    return 2.0 * (acceleration_a_m_s2 - acceleration_b_m_s2) / denom


def microscope_differential_acceleration_bound(
    local_gravity_m_s2: float,
    eta_bound: float = MICROSCOPE_ETA_BOUND,
) -> float:
    """Worst-case |Δa_AB| between two ship subcomponents consistent
    with MICROSCOPE.

    |Δa_AB| ≤ η_bound · |g_local|                            [m/s²]

    For deep-space cruise with `g_local ≈ 10⁻¹⁰ m/s²` the bound is
    `~10⁻²⁵ m/s²` — utterly negligible. At a Jupiter gravity assist
    (`g_local ≈ 0.1 m/s²`) it is `~10⁻¹⁶ m/s²`.
    """
    if eta_bound < 0.0:
        raise ValueError("eta_bound must be non-negative")
    return eta_bound * abs(local_gravity_m_s2)
