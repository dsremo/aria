"""V3-V3: STL decomposition uncertainty propagation.

STL produces point estimates for residuals.  But LOESS smoothing has
confidence bands: a residual of 0.8σ at the boundary of a ±0.2σ STL
confidence band is statistically indistinguishable from 0.6σ (nominal).

This module computes effective residual uncertainty by combining
measurement noise with STL estimation uncertainty, then scales CUSUM
increments by the effective uncertainty.

Reference: Cleveland, W.S. (1979). "Robust locally weighted regression
           and smoothing scatterplots." JASA 74(368):829–836.
"""

from __future__ import annotations

import numpy as np
import structlog

logger = structlog.get_logger()


def compute_stl_uncertainty(
    values: np.ndarray,
    residuals: np.ndarray,
    trend: np.ndarray,
    seasonal: np.ndarray,
    measurement_noise_std: float = 0.0,
) -> np.ndarray:
    """Estimate per-sample effective uncertainty after STL decomposition.

    Combines:
    1. STL estimation uncertainty (from local residual variance)
    2. Measurement noise (if known)

    Returns σ_effective array, same length as residuals.
    Used to scale CUSUM increments: residual_t / σ_effective(t).
    """
    n = len(residuals)
    if n < 10:
        return np.ones(n)

    # Estimate local STL uncertainty from rolling residual variance.
    # A wider local variance means STL is less certain about the
    # seasonal/trend decomposition at that point.
    window = max(5, n // 20)
    sigma_loess = np.ones(n)
    for i in range(n):
        start = max(0, i - window)
        end = min(n, i + window + 1)
        local_std = float(np.std(residuals[start:end]))
        sigma_loess[i] = max(local_std, 1e-9)

    # Combine with measurement noise.
    sigma_meas = measurement_noise_std if measurement_noise_std > 0 else 0.0
    sigma_effective = np.sqrt(sigma_loess ** 2 + sigma_meas ** 2)

    return sigma_effective


def scale_residual_by_uncertainty(
    residual: float,
    sigma_effective: float,
    sigma_ref: float,
) -> float:
    """Scale a single residual by effective uncertainty.

    Returns residual × (σ_ref / σ_effective) so that uncertain
    residuals are down-weighted relative to the reference standard.

    When σ_effective > σ_ref (high uncertainty), the scaled residual
    is smaller → less CUSUM accumulation → fewer false alarms.
    """
    if sigma_effective < 1e-9 or sigma_ref < 1e-9:
        return residual
    return residual * (sigma_ref / sigma_effective)
