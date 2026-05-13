"""V3-K4: Multiple testing correction for multi-channel anomaly detection.

When monitoring 100+ channels simultaneously, the probability that at least
one channel falsely triggers grows rapidly (FWER = 1 - (1-α)^m ≈ 1.0 for
m=100 at α=0.01).

Provides both:
    - Holm-Bonferroni FWER control: bounds P(any false alarm) < α
    - Benjamini-Hochberg FDR control: bounds expected FP proportion < q

For spacecraft safety, FWER is the correct criterion (ECSS-E-ST-70C).
FDR is offered as a less conservative option for constellation monitoring.

Reference: Holm, S. (1979). "A simple sequentially rejective multiple test
           procedure." Scandinavian Journal of Statistics 6(2):65–70.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


def holm_bonferroni(
    p_values: list[tuple[str, float]],
    alpha: float = 0.01,  # ESTIMATE — 1% FWER target; Holm 1979 Scand J Stat 6 65: α=0.01 standard for safety-critical monitoring
) -> list[tuple[str, float, bool]]:
    """Holm-Bonferroni step-down FWER correction.

    Args:
        p_values: List of (channel_key, p_value) tuples.
        alpha:    Family-wise error rate target (default 0.01 = 1%).

    Returns:
        List of (channel_key, p_value, is_significant) tuples,
        sorted by p-value ascending.  is_significant=True only for
        channels surviving FWER correction.

    FWER guarantee: P(any false rejection) ≤ α.
    """
    m = len(p_values)
    if m == 0:
        return []

    sorted_pv = sorted(p_values, key=lambda x: x[1])
    results: list[tuple[str, float, bool]] = []

    rejected_so_far = True  # stop rejecting after first non-rejection
    for i, (key, pv) in enumerate(sorted_pv):
        threshold = alpha / (m - i)
        if rejected_so_far and pv <= threshold:
            results.append((key, pv, True))
        else:
            rejected_so_far = False
            results.append((key, pv, False))

    return results


def benjamini_hochberg(
    p_values: list[tuple[str, float]],
    q: float = 0.05,  # Benjamini & Hochberg 1995 J R Stat Soc B 57 289: 5% FDR is the canonical default
) -> list[tuple[str, float, bool]]:
    """Benjamini-Hochberg FDR correction.

    Args:
        p_values: List of (channel_key, p_value) tuples.
        q:        False discovery rate target (default 5%).

    Returns:
        List of (channel_key, p_value, is_significant) tuples.
        is_significant=True for channels surviving FDR correction.

    FDR guarantee: E[FP / (FP + TP)] ≤ q.
    """
    m = len(p_values)
    if m == 0:
        return []

    sorted_pv = sorted(p_values, key=lambda x: x[1])

    # Find largest k such that p_(k) ≤ k/m × q.
    max_k = 0
    for k, (_, pv) in enumerate(sorted_pv, start=1):
        if pv <= k / m * q:
            max_k = k

    results: list[tuple[str, float, bool]] = []
    for i, (key, pv) in enumerate(sorted_pv):
        results.append((key, pv, i < max_k))

    return results


def confidence_to_p_value(confidence: float) -> float:
    """Convert ensemble confidence to approximate p-value.

    Under the null hypothesis (no anomaly), confidence scores are
    approximately uniformly distributed in [0, 0.5] (below watch threshold).
    A confidence of 0.7 maps to a p-value of ~0.3.

    Simple transformation: p = 1 - confidence.
    """
    return max(0.0, min(1.0, 1.0 - confidence))
