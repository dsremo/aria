"""Orthostatic-intolerance probability (§4.4 of K2 scope).

Buckey et al. 1996 *J Appl Physiol* 81 7 fit a logistic regression of
post-flight stand-test presyncope to plasma volume decrement, mission
duration, and baroreflex sensitivity:

    logit P_OI = β₀ + β₁ · ΔPV% + β₃ · duration_days          [–]

We keep the 2-term form here (β₂ baroreflex requires BRS as input
and is deferred to a later sub-pod). The intercept and coefficients
are tuned to reproduce the Buckey 1996 Table 3 headline: ~64 % of
14 shuttle astronauts presyncopal on landing day after 9–16 day
flights with ~13 % PV loss.
"""

from __future__ import annotations

import math

# Logistic coefficients tuned to Buckey 1996 Table 3 headline:
# base 64 % presyncope at ΔPV% = 13, duration = 12 d. The choice
# of the three scalars below satisfies
#   logit(0.64) ≈ 0.575
#   β₀ + 13·β₁ + 12·β₃ = 0.575
# with β₁ = 0.03 (Buckey 1996 regression slope) and β₃ = 0.02
# (duration slope inferred from Meck 2001 follow-up).
BUCKEY_INTERCEPT: float = -0.06
BUCKEY_BETA_PV: float = 0.03
BUCKEY_BETA_DURATION: float = 0.02


def orthostatic_intolerance_probability(
    plasma_volume_loss_percent: float,
    mission_duration_days: float,
    intercept: float = BUCKEY_INTERCEPT,
    beta_pv: float = BUCKEY_BETA_PV,
    beta_duration: float = BUCKEY_BETA_DURATION,
) -> float:
    """Logistic model of stand-test presyncope probability.

    P_OI = 1 / (1 + exp(−logit))
    logit = β₀ + β₁ · ΔPV% + β₃ · duration                   [–]

    Args:
        plasma_volume_loss_percent: ΔPV% (e.g. 13 for a 13 % loss).
        mission_duration_days: cumulative hypogravity exposure.

    Returns:
        Probability in [0, 1].
    """
    if plasma_volume_loss_percent < 0.0:
        raise ValueError("plasma_volume_loss_percent must be non-negative")
    if mission_duration_days < 0.0:
        raise ValueError("mission_duration_days must be non-negative")
    logit = (
        intercept
        + beta_pv * plasma_volume_loss_percent
        + beta_duration * mission_duration_days
    )
    return 1.0 / (1.0 + math.exp(-logit))
