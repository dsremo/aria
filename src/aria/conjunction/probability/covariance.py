"""
Covariance matrix operations for conjunction assessment.

Handles:
  - Combining primary and secondary covariances
  - Rotating covariance between coordinate frames (RTN ↔ ECI)
  - Projecting 3D position covariance onto the 2D encounter plane (B-plane)
  - Generating default covariances in the CORRECT frame
  - Covariance realism scaling

CRITICAL: Covariance matrices must be in the SAME coordinate frame before
combining. Default covariances are generated in RTN (natural for orbiting
objects) and MUST be rotated to ECI before combining with other covariances
or projecting to the encounter plane.

Frame rotation: C_eci = R^T · C_rtn · R
  where R is the 3x3 RTN rotation matrix (rows = R_hat, T_hat, N_hat)

The covariance realism problem:
  TLE-derived covariances are often unrealistic because:
  1. They don't account for unmodeled forces (atmospheric density spikes)
  2. Linearized dynamics artificially preserve Gaussian shape
  3. Cartesian representation "leaks" probability along the orbit path
  Operators often apply empirical scaling factors (1.5x-3x).
"""

from __future__ import annotations

import numpy as np

from aria.conjunction.propagation.frames import eci_to_rtn, project_to_encounter_plane


def combine_covariances(
    cov_primary: np.ndarray,
    cov_secondary: np.ndarray,
) -> np.ndarray:
    """Combine two position covariance matrices.

    BOTH covariances must be in the SAME coordinate frame (typically ECI).
    For independently tracked objects, C_combined = C_1 + C_2.

    Args:
        cov_primary: 3x3 position covariance of primary (km², in ECI)
        cov_secondary: 3x3 position covariance of secondary (km², in ECI)

    Returns:
        3x3 combined position covariance (km², in ECI)
    """
    return np.asarray(cov_primary, dtype=np.float64) + np.asarray(cov_secondary, dtype=np.float64)


def rotate_covariance_rtn_to_eci(
    cov_rtn: np.ndarray,
    position_eci: np.ndarray,
    velocity_eci: np.ndarray,
) -> np.ndarray:
    """Rotate a covariance matrix from RTN frame to ECI frame.

    C_eci = R^T · C_rtn · R

    where R is the RTN rotation matrix (rows are R_hat, T_hat, N_hat).
    R rotates ECI→RTN, so R^T rotates RTN→ECI.

    Args:
        cov_rtn: 3x3 covariance in RTN frame (km²)
        position_eci: Object position in ECI (km)
        velocity_eci: Object velocity in ECI (km/s)

    Returns:
        3x3 covariance in ECI frame (km²)
    """
    R_mat = eci_to_rtn(position_eci, velocity_eci)  # 3x3, rows = [R, T, N]
    C_rtn = np.asarray(cov_rtn, dtype=np.float64)
    # R^T · C · R = ECI covariance
    return R_mat.T @ C_rtn @ R_mat


def rotate_covariance_eci_to_rtn(
    cov_eci: np.ndarray,
    position_eci: np.ndarray,
    velocity_eci: np.ndarray,
) -> np.ndarray:
    """Rotate a covariance matrix from ECI frame to RTN frame.

    C_rtn = R · C_eci · R^T

    Args:
        cov_eci: 3x3 covariance in ECI frame (km²)
        position_eci: Object position in ECI (km)
        velocity_eci: Object velocity in ECI (km/s)

    Returns:
        3x3 covariance in RTN frame (km²)
    """
    R_mat = eci_to_rtn(position_eci, velocity_eci)
    C_eci = np.asarray(cov_eci, dtype=np.float64)
    return R_mat @ C_eci @ R_mat.T


def project_covariance_to_encounter_plane(
    miss_vector_eci: np.ndarray,
    relative_velocity_eci: np.ndarray,
    combined_covariance_3d: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Project miss vector and covariance onto encounter plane.

    The combined_covariance_3d MUST be in ECI frame.

    Args:
        miss_vector_eci: Relative position at TCA (3,) in km (ECI)
        relative_velocity_eci: Relative velocity at TCA (3,) in km/s (ECI)
        combined_covariance_3d: 3x3 combined position covariance (km², ECI)

    Returns:
        (miss_2d, covariance_2d): projected values in encounter plane
    """
    return project_to_encounter_plane(
        miss_vector_eci,
        relative_velocity_eci,
        combined_covariance_3d,
    )


def generate_default_covariance_rtn(
    position_sigma_km: float = 1.0,    # ESTIMATE — 1 km 1σ typical TLE position uncertainty (Kelso 2009)
    in_track_scaling: float = 5.0,     # ESTIMATE — 5× in-track vs radial (Alfano 2005 JGCD 28 427 §2)
) -> np.ndarray:
    """Generate a default diagonal covariance matrix in RTN frame.

    In-track (T) uncertainty is typically 3-10x larger than radial (R) or
    cross-track (N) due to drag and mean-motion uncertainty.

    NOTE: This is in RTN frame. You MUST call rotate_covariance_rtn_to_eci()
    before combining with other covariances or projecting to encounter plane.

    Args:
        position_sigma_km: 1σ position uncertainty in R and N (km)
        in_track_scaling: Factor by which in-track σ exceeds radial σ

    Returns:
        3x3 diagonal covariance in RTN frame (km²)
    """
    sigma_r = position_sigma_km
    sigma_t = position_sigma_km * in_track_scaling
    sigma_n = position_sigma_km

    return np.diag([sigma_r**2, sigma_t**2, sigma_n**2])


def generate_default_covariance(
    position_sigma_km: float = 1.0,
    velocity_sigma_km_s: float = 0.001,
    in_track_scaling: float = 5.0,
) -> np.ndarray:
    """Generate a default diagonal covariance matrix in ECI-like frame.

    WARNING: This is an APPROXIMATION. For accurate results, generate in RTN
    and rotate to ECI using the object's state vector. This function generates
    a covariance that's reasonable for isotropic ECI analysis when the object's
    state is not available (e.g., default fallback).

    The diagonal ECI covariance underestimates the in-track error because
    the in-track direction is not aligned with any ECI axis. Use
    generate_default_covariance_rtn() + rotate_covariance_rtn_to_eci() for
    accurate results.

    Args:
        position_sigma_km: 1σ position uncertainty (km)
        velocity_sigma_km_s: 1σ velocity uncertainty (km/s) — unused for position-only
        in_track_scaling: Rough scaling for one axis to approximate in-track

    Returns:
        3x3 diagonal position covariance (km²)
    """
    # Use geometric mean of radial and in-track for an "average" ECI uncertainty
    position_sigma_km * (1 + in_track_scaling) / 2.0
    sigma_r = position_sigma_km
    sigma_t = position_sigma_km * in_track_scaling

    return np.diag([sigma_r**2, sigma_t**2, sigma_r**2])


def scale_covariance(
    covariance: np.ndarray,
    scale_factor: float,
) -> np.ndarray:
    """Apply a realism scaling factor to a covariance matrix.

    Scales σ by scale_factor → σ² scales by scale_factor².
    Operators commonly use 1.5x-3x for TLE-derived covariances.

    Args:
        covariance: Original covariance matrix
        scale_factor: Multiplicative factor applied to σ (σ² scales by factor²)

    Returns:
        Scaled covariance matrix
    """
    return np.asarray(covariance, dtype=np.float64) * (scale_factor**2)
