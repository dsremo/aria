"""V3-M4: Alpha-lambda RUL confidence bounds for trend velocity predictions.

TrendVelocity computes TTL = (limit - value) / trend_rate as a point estimate.
Without uncertainty, operators cannot distinguish "12 ± 0.5 hours" (actionable)
from "12 ± 5 days" (useless).

This module propagates trend_rate uncertainty via the delta method:
    σ_TTL ≈ |TTL| × σ_v / |μ_v|

Reports 90% confidence interval: TTL ± 1.645 × σ_TTL.

Reference: NASA/TM-2012-217519 §3.2: α-λ performance metric.
           Saxena, A. et al. (2010). "Metrics for offline evaluation of
           prognostic performance." IJPHM 1(1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class RULEstimate:
    """Time-to-limit estimate with confidence bounds."""

    ttl_hours: float            # point estimate
    ttl_lower_hours: float      # 90% CI lower bound
    ttl_upper_hours: float      # 90% CI upper bound
    confidence_level: float     # 0.90
    trend_rate: float           # d(value)/dt in units per hour
    trend_rate_std: float       # std of trend rate estimate


def compute_rul_with_confidence(
    current_value: float,
    limit_value: float,
    trend_rates: list[float],
    confidence: float = 0.90,
) -> RULEstimate | None:
    """Compute TTL with delta-method confidence interval.

    Args:
        current_value: Current parameter value.
        limit_value:   Threshold that triggers alarm/safing.
        trend_rates:   Recent trend rate estimates (d(value)/dt per hour).
                       Typically from a rolling window of np.gradient(trend).
        confidence:    Confidence level (default 0.90 for 90% CI).

    Returns:
        RULEstimate with TTL point estimate and CI, or None if trend is
        near-zero or insufficient data.
    """
    if len(trend_rates) < 3:
        return None

    arr = np.array(trend_rates, dtype=np.float64)
    mu_v = float(np.mean(arr))
    sigma_v = float(np.std(arr, ddof=1))

    if abs(mu_v) < 1e-12:
        return None  # no measurable trend

    ttl = (limit_value - current_value) / mu_v  # hours

    # Delta method: σ_TTL ≈ |TTL| × σ_v / |μ_v|
    sigma_ttl = abs(ttl) * sigma_v / abs(mu_v) if abs(mu_v) > 1e-12 else float("inf")

    # z-score for confidence level (two-tailed).
    # For 90%: z=1.645, 95%: z=1.96, 99%: z=2.576
    from scipy.stats import norm  # noqa: PLC0415
    z = float(norm.ppf(0.5 + confidence / 2.0))

    lower = ttl - z * sigma_ttl
    upper = ttl + z * sigma_ttl

    return RULEstimate(
        ttl_hours=round(ttl, 2),
        ttl_lower_hours=round(lower, 2),
        ttl_upper_hours=round(upper, 2),
        confidence_level=confidence,
        trend_rate=round(mu_v, 6),
        trend_rate_std=round(sigma_v, 6),
    )
