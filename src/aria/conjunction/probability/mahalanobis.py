"""
Mahalanobis distance pre-filter for collision probability.

The Mahalanobis distance measures the miss distance normalized by the
combined covariance (uncertainty):

  D_M = sqrt(m^T C^-1 m)

where m is the 2D miss vector in the encounter plane and C is the 2x2
combined projected covariance.

Physical interpretation:
  D_M = 1 → miss distance equals 1σ of the uncertainty
  D_M = 3 → 3σ miss → Pc is extremely small
  D_M > 5 → Pc < ~1e-7 → negligible, skip expensive integration

This pre-filter saves ~70% of Pc computation by avoiding the numerical
integration for clearly safe events.

WARNING (Dilution Effect):
  Pc is NOT monotonically decreasing with D_M. If the covariance is very
  large (poor data quality), D_M can be small even when the true risk is low.
  This is the "dilution curve" problem. The Mahalanobis filter is a necessary
  but not sufficient condition — always compute P_max as a sanity check.
"""

from __future__ import annotations

import numpy as np

from aria.conjunction.core.constants import MAHALANOBIS_SKIP_THRESHOLD


def mahalanobis_distance(
    miss_vector_2d: np.ndarray,
    covariance_2d: np.ndarray,
) -> float:
    """Compute Mahalanobis distance in the encounter plane.

    Args:
        miss_vector_2d: 2D projected miss vector (km)
        covariance_2d: 2x2 combined covariance in encounter plane (km²)

    Returns:
        Mahalanobis distance (dimensionless)
    """
    m = np.asarray(miss_vector_2d, dtype=np.float64)
    C = np.asarray(covariance_2d, dtype=np.float64)

    # Handle degenerate covariance
    det = np.linalg.det(C)
    if det < 1e-30:
        # Singular covariance — can't compute meaningful D_M
        return 0.0

    C_inv = np.linalg.inv(C)
    d_sq = float(m @ C_inv @ m)

    return float(np.sqrt(max(0.0, d_sq)))


def should_skip_pc(
    miss_vector_2d: np.ndarray,
    covariance_2d: np.ndarray,
    threshold: float = MAHALANOBIS_SKIP_THRESHOLD,
) -> tuple[bool, float]:
    """Determine if Pc computation can be skipped based on Mahalanobis distance.

    Args:
        miss_vector_2d: 2D miss vector (km)
        covariance_2d: 2x2 covariance (km²)
        threshold: Skip if D_M exceeds this (default: 5.0)

    Returns:
        (should_skip, mahalanobis_distance)
    """
    d_m = mahalanobis_distance(miss_vector_2d, covariance_2d)
    return d_m > threshold, d_m


def maximum_pc(
    combined_radius_km: float,
    covariance_2d: np.ndarray,
) -> float:
    """Compute maximum possible Pc (P_max) for a given covariance.

    P_max occurs when the miss distance is zero.

    For equal variances (σ₁ = σ₂ = σ):
      P_max = 1 - exp(-R²/(2σ²))

    For unequal variances (σ₁ ≠ σ₂):
      P_max = R² / (2(σ₂² - σ₁²)) × [exp(-R²/(2σ₂²)) - exp(-R²/(2σ₁²))]

    The leading-order approximation P_max ≈ R²/(2πσ₁σ₂) is only valid when R << σ.
    For ISS-class objects (R=54m) with tight covariance (σ~100m), this is 15% off.

    Args:
        combined_radius_km: Sum of object radii (km)
        covariance_2d: 2x2 covariance (km²)

    Returns:
        Maximum possible Pc
    """
    import math

    eigenvalues = np.linalg.eigvalsh(covariance_2d)
    if np.any(eigenvalues <= 0):
        return 1.0  # degenerate — be conservative

    sigma_sq_1 = float(min(eigenvalues))
    sigma_sq_2 = float(max(eigenvalues))
    R = combined_radius_km
    R_sq = R**2

    # Check variance ratio
    if abs(sigma_sq_2 - sigma_sq_1) / max(sigma_sq_2, 1e-30) < 0.01:
        # Equal variance case: P_max = 1 - exp(-R²/(2σ²))
        sigma_sq = (sigma_sq_1 + sigma_sq_2) / 2.0
        arg = R_sq / (2.0 * sigma_sq)
        return 1.0 - math.exp(-arg) if arg < 700 else 1.0
    else:
        # Unequal variance case (Alfano exact P_max):
        # P_max = R² / (2(σ₂² - σ₁²)) × [exp(-R²/(2σ₂²)) - exp(-R²/(2σ₁²))]
        diff = sigma_sq_2 - sigma_sq_1
        arg1 = R_sq / (2.0 * sigma_sq_1)
        arg2 = R_sq / (2.0 * sigma_sq_2)
        exp1 = math.exp(-arg1) if arg1 < 700 else 0.0
        exp2 = math.exp(-arg2) if arg2 < 700 else 0.0
        p_max = R_sq / (2.0 * diff) * (exp2 - exp1)
        return max(0.0, min(1.0, p_max))
