"""V3-A5: Retrospective changepoint localization after BOCPD trigger.

BOCPD online detection has inherent localization delay (~1/hazard samples).
After BOCPD triggers, this module runs PELT (batch algorithm) on a recent
window to precisely localize the changepoint time.

Reports both detection_time and changepoint_time in the anomaly record.

Reference: Killick, R., Fearnhead, P. & Eckley, I.A. (2012). "Optimal
           detection of changepoints with a linear computational cost."
           JASA 107(500):1590–1598.
"""

from __future__ import annotations

import numpy as np
import structlog

logger = structlog.get_logger()


def localize_changepoint(
    residuals: np.ndarray,
    detection_index: int,
    hazard: float = 0.002,
    min_segment: int = 5,
) -> dict:
    """Run PELT-like binary segmentation to localize a changepoint.

    After BOCPD fires at detection_index, looks backward over
    2 × expected_run_length samples to find the exact changepoint.

    Args:
        residuals:       Full residual array for the channel.
        detection_index: Index at which BOCPD triggered.
        hazard:          BOCPD hazard rate (for window sizing).
        min_segment:     Minimum segment length for PELT.

    Returns:
        {"changepoint_index": int, "detection_index": int,
         "localization_lag": int, "confidence": float}
    """
    # Look-back window: 2 × expected run length.
    lookback = int(min(2.0 / max(hazard, 1e-6), len(residuals)))
    start = max(0, detection_index - lookback)
    window = residuals[start: detection_index + 1]

    if len(window) < 2 * min_segment:
        return {
            "changepoint_index": detection_index,
            "detection_index": detection_index,
            "localization_lag": 0,
            "confidence": 0.0,
        }

    # Binary segmentation: find the split point that maximizes
    # the reduction in total variance.
    best_split = len(window) // 2
    best_gain = 0.0
    total_var = float(np.var(window))

    if total_var < 1e-12:
        return {
            "changepoint_index": detection_index,
            "detection_index": detection_index,
            "localization_lag": 0,
            "confidence": 0.0,
        }

    for k in range(min_segment, len(window) - min_segment):
        left = window[:k]
        right = window[k:]
        var_left = float(np.var(left))
        var_right = float(np.var(right))
        weighted_var = (len(left) * var_left + len(right) * var_right) / len(window)
        gain = total_var - weighted_var

        if gain > best_gain:
            best_gain = gain
            best_split = k

    changepoint_abs = start + best_split
    lag = detection_index - changepoint_abs
    # Confidence: proportion of variance explained by the split.
    confidence = min(1.0, best_gain / max(total_var, 1e-12))

    return {
        "changepoint_index": changepoint_abs,
        "detection_index": detection_index,
        "localization_lag": lag,
        "confidence": round(confidence, 4),
    }
