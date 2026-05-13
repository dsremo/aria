"""Long-term trend forecasting for operator planning.

Provides days-to-limit extrapolation from STL trend:
    "At current degradation rate, battery_voltage will cross the
     warning threshold in 45 days."

Unlike the TTL prediction in detector.py (which only fires when the limit
is within 60 minutes), this module provides weeks/months forecasts for
capacity planning and maintenance scheduling.
"""

from __future__ import annotations

import numpy as np
import structlog

logger = structlog.get_logger()


def forecast_days_to_limit(
    trend: np.ndarray,
    timestamps: np.ndarray,
    current_value: float,
    limit_high: float | None = None,
    limit_low: float | None = None,
    min_points: int = 50,   # ESTIMATE — 50 points minimum for reliable OLS slope (Cohen 1988 §7: n ≥ 50)
) -> dict:
    """Estimate days until a limit is reached based on linear trend extrapolation.

    Uses ordinary least squares on the STL trend component for a more
    robust estimate than the short-window velocity used in TTL prediction.

    Args:
        trend:         STL trend component (oldest → newest).
        timestamps:    Unix epoch timestamps, same length as trend.
        current_value: Current raw telemetry value.
        limit_high:    Upper redline (or None).
        limit_low:     Lower redline (or None).
        min_points:    Minimum trend points needed for reliable estimate.

    Returns:
        {
            "slope_per_day": float,      # units per day
            "days_to_high": float|None,  # days until high limit (None if not approaching)
            "days_to_low": float|None,   # days until low limit (None if not approaching)
            "r_squared": float,          # goodness of fit (0-1)
            "reliable": bool,            # True if R² > 0.5 and enough data
        }
    """
    if len(trend) < min_points or len(timestamps) < min_points:
        return {
            "slope_per_day": 0.0,
            "days_to_high": None,
            "days_to_low": None,
            "r_squared": 0.0,
            "reliable": False,
        }

    # Fit linear regression on trend vs time
    t = timestamps - timestamps[0]  # relative seconds
    t_days = t / 86400.0

    # OLS: y = a + b*x
    n = len(t_days)
    x_mean = float(np.mean(t_days))
    y_mean = float(np.mean(trend))

    ss_xy = float(np.sum((t_days - x_mean) * (trend - y_mean)))
    ss_xx = float(np.sum((t_days - x_mean) ** 2))

    if ss_xx < 1e-12:
        return {
            "slope_per_day": 0.0,
            "days_to_high": None,
            "days_to_low": None,
            "r_squared": 0.0,
            "reliable": False,
        }

    slope = ss_xy / ss_xx  # units per day
    intercept = y_mean - slope * x_mean

    # R²
    y_pred = intercept + slope * t_days
    ss_res = float(np.sum((trend - y_pred) ** 2))
    ss_tot = float(np.sum((trend - y_mean) ** 2))
    r_sq = 1.0 - ss_res / max(ss_tot, 1e-12)

    reliable = r_sq > 0.5 and n >= min_points

    # Extrapolate from current value
    days_to_high = None
    days_to_low = None

    if limit_high is not None and slope > 1e-12:
        remaining = limit_high - current_value
        if remaining > 0:
            days_to_high = round(remaining / slope, 1)

    if limit_low is not None and slope < -1e-12:
        remaining = current_value - limit_low
        if remaining > 0:
            days_to_low = round(remaining / abs(slope), 1)

    return {
        "slope_per_day": round(slope, 6),
        "days_to_high": days_to_high,
        "days_to_low": days_to_low,
        "r_squared": round(r_sq, 4),
        "reliable": reliable,
    }
