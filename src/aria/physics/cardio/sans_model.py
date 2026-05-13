"""Spaceflight-Associated Neuro-ocular Syndrome (§4.5 of K2 scope).

Exponential onset model fit to the Mader 2011 *Ophthalmology* 118
2058 cohort of 27 astronauts and the Lee 2018 *npj Microgravity* 4
10 ISS review:

    P_SANS(t) = 1 − exp[ −k · (1 − g/g₀) · max(0, t − t₀) ]  [–]

with `k ≈ 0.003 /d` (ESTIMATE fit) and `t₀ ≈ 30 d` onset delay.
"""

from __future__ import annotations

import math

from .compartments import G_ZERO_M_S2

# ESTIMATE fit to Mader 2011 Ophthalmology 118 2058 cohort.
SANS_K_PER_DAY: float = 0.003
SANS_ONSET_DAYS: float = 30.0


def sans_probability(
    time_days: float,
    local_g_m_s2: float,
    k_per_day: float = SANS_K_PER_DAY,
    onset_days: float = SANS_ONSET_DAYS,
) -> float:
    """Cumulative probability of SANS optic-disc edema.

    P(t) = 1 − exp[−k (1 − g/g₀) · max(0, t − t₀)]           [–]

    Returns 0 for t ≤ t₀ or g ≥ g₀ (no hypogravity exposure).
    """
    if time_days < 0.0:
        raise ValueError("time_days must be non-negative")
    if local_g_m_s2 < 0.0:
        raise ValueError("local_g_m_s2 must be non-negative")
    if k_per_day <= 0.0:
        raise ValueError("k_per_day must be positive")
    if onset_days < 0.0:
        raise ValueError("onset_days must be non-negative")
    if time_days <= onset_days:
        return 0.0
    deficit = max(0.0, 1.0 - local_g_m_s2 / G_ZERO_M_S2)
    if deficit == 0.0:
        return 0.0
    return 1.0 - math.exp(-k_per_day * deficit * (time_days - onset_days))
