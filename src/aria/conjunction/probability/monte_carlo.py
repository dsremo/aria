"""
Monte Carlo collision probability estimation.

Used when the 2D short-encounter assumption breaks down:
  - Low relative velocity (< 100 m/s) — GEO, proximity operations
  - Non-Gaussian uncertainty distributions
  - Complex hard-body geometries

Approach:
  1. Sample N points from the combined position uncertainty distribution
  2. For each sample, check if the relative distance < combined radius
  3. Pc = count_within_radius / N

Statistical precision:
  For Pc ~ 1e-4: N = 1e6 gives ~10% relative error (100 hits expected)
  For Pc ~ 1e-6: N = 1e8 needed (100 hits) — computationally expensive
  For Pc ~ 1e-8: Impractical — use analytical methods instead

Vectorized with NumPy for maximum throughput.
"""

from __future__ import annotations

import math

import numpy as np


def monte_carlo_pc(
    miss_vector_2d: np.ndarray,
    covariance_2d: np.ndarray,
    combined_radius_km: float,
    n_samples: int = 1_000_000,
    seed: int | None = None,
) -> float:
    """Compute Pc via Monte Carlo sampling in the encounter plane.

    Args:
        miss_vector_2d: 2D miss vector (km)
        covariance_2d: 2x2 combined covariance (km²)
        combined_radius_km: R₁ + R₂ (km)
        n_samples: Number of Monte Carlo samples
        seed: Random seed for reproducibility

    Returns:
        Estimated Pc with statistical uncertainty
    """
    rng = np.random.default_rng(seed)

    m = np.asarray(miss_vector_2d, dtype=np.float64)
    C = np.asarray(covariance_2d, dtype=np.float64)
    R = combined_radius_km

    # Cholesky decomposition for efficient sampling: C = L L^T
    try:
        L = np.linalg.cholesky(C)
    except np.linalg.LinAlgError:
        # Non-positive-definite covariance — add small regularization
        C_reg = C + np.eye(2) * 1e-10
        L = np.linalg.cholesky(C_reg)

    # Generate samples: x ~ N(m, C) → x = m + L @ z where z ~ N(0, I)
    z = rng.standard_normal((2, n_samples))
    samples = m[:, np.newaxis] + L @ z  # (2, n_samples)

    # Count samples within the hard-body disk centered at origin
    distances_sq = samples[0] ** 2 + samples[1] ** 2
    hits = np.sum(distances_sq <= R**2)

    pc = hits / n_samples
    return float(pc)


def monte_carlo_pc_3d(
    miss_vector_3d: np.ndarray,
    covariance_3d: np.ndarray,
    combined_radius_km: float,
    relative_velocity: np.ndarray,
    encounter_duration_s: float = 60.0,  # ESTIMATE — 60 s encounter window at 10 km/s (Alfano 2005 JGCD 28 427 §3)
    n_samples: int = 1_000_000,          # ESTIMATE — 1M samples for Pc ~1e-4 (Casali 2018; ~100 expected hits)
    seed: int | None = None,
    velocity_covariance_3d: np.ndarray | None = None,
) -> float:
    """3D Monte Carlo Pc for low-velocity / long-duration encounters.

    Samples from the full 6D state (position + velocity) when velocity
    covariance is available, or from 3D position-only otherwise.

    For each sample:
      1. Draw (Δr, Δv) from the 6D uncertainty
      2. Compute the relative trajectory r(t) = Δr + Δv × t
      3. Find the time of minimum distance (clamped to encounter window)
      4. Check if minimum distance < combined radius

    When velocity covariance is provided, the position uncertainty GROWS
    as we move away from TCA: σ_pos(t) = σ_pos(0) + σ_vel × t. This
    correctly captures the risk for long encounters that the 2D method misses.

    Args:
        miss_vector_3d: 3D relative position at TCA (km)
        covariance_3d: 3x3 combined position covariance (km²)
        combined_radius_km: R₁ + R₂ (km)
        relative_velocity: 3D relative velocity at TCA (km/s)
        encounter_duration_s: Duration to check around TCA (seconds)
        n_samples: Number of Monte Carlo samples
        seed: Random seed
        velocity_covariance_3d: 3x3 combined velocity covariance (km²/s²).
            If None, velocity is treated as deterministic.

    Returns:
        Estimated 3D Pc
    """
    rng = np.random.default_rng(seed)

    m = np.asarray(miss_vector_3d, dtype=np.float64)
    C_pos = np.asarray(covariance_3d, dtype=np.float64)
    v_rel = np.asarray(relative_velocity, dtype=np.float64)
    R = combined_radius_km

    # Sample position uncertainty
    try:
        L_pos = np.linalg.cholesky(C_pos)
    except np.linalg.LinAlgError:
        L_pos = np.linalg.cholesky(C_pos + np.eye(3) * 1e-10)

    z_pos = rng.standard_normal((3, n_samples))
    positions = m[:, np.newaxis] + L_pos @ z_pos  # (3, n_samples)

    # Sample velocity uncertainty if available
    if velocity_covariance_3d is not None:
        C_vel = np.asarray(velocity_covariance_3d, dtype=np.float64)
        try:
            L_vel = np.linalg.cholesky(C_vel)
        except np.linalg.LinAlgError:
            L_vel = np.linalg.cholesky(C_vel + np.eye(3) * 1e-12)

        z_vel = rng.standard_normal((3, n_samples))
        velocities = v_rel[:, np.newaxis] + L_vel @ z_vel  # (3, n_samples)
    else:
        velocities = np.broadcast_to(v_rel[:, np.newaxis], (3, n_samples)).copy()

    # For each sample, find minimum distance along the trajectory
    # r(t) = positions + velocities * t
    # |r(t)|² = |pos|² + 2(pos·vel)t + |vel|²t²
    # d/dt|r|² = 2(pos·vel) + 2|vel|²t = 0  →  t_min = -(pos·vel)/|vel|²

    v_mag_sq = np.sum(velocities**2, axis=0)  # (n_samples,)

    # Handle near-stationary cases
    stationary = v_mag_sq < 1e-20
    if np.all(stationary):
        distances_sq = np.sum(positions**2, axis=0)
        hits = np.sum(distances_sq <= R**2)
        return float(hits / n_samples)

    # Time of minimum distance per sample
    pos_dot_vel = np.sum(positions * velocities, axis=0)  # (n_samples,)

    # Safe division — stationary samples get t_min=0
    t_min = np.zeros(n_samples)
    moving = ~stationary
    t_min[moving] = -pos_dot_vel[moving] / v_mag_sq[moving]

    # Clamp to encounter window
    half_dur = encounter_duration_s / 2.0
    t_min = np.clip(t_min, -half_dur, half_dur)

    # Minimum distance for each sample
    closest = positions + velocities * t_min[np.newaxis, :]
    distances_sq = np.sum(closest**2, axis=0)
    hits = np.sum(distances_sq <= R**2)

    return float(hits / n_samples)


def importance_sampling_pc(
    miss_vector_2d: np.ndarray,
    covariance_2d: np.ndarray,
    combined_radius_km: float,
    n_samples: int = 100_000,
    seed: int | None = None,
) -> tuple[float, float]:
    """Compute Pc via Importance Sampling — efficient for rare events (Pc < 1e-5).

    Standard MC needs N = 100/Pc samples for 10% relative error.
    At Pc = 1e-6, that's 10⁸ samples — impractical.

    Importance Sampling uses a PROPOSAL distribution concentrated near the
    hard-body disk, then reweights by the likelihood ratio:
      Pc = (1/N) × Σ [I(|x_i| < R) × f_target(x_i) / f_proposal(x_i)]

    Proposal: Gaussian centered at ORIGIN (center of hard body) with the same
    covariance, truncated to 3R. This concentrates samples where collisions occur.

    Variance reduction: typically 100-1000x compared to standard MC.

    Args:
        miss_vector_2d: 2D miss vector (km)
        covariance_2d: 2x2 combined covariance (km²)
        combined_radius_km: R₁ + R₂ (km)
        n_samples: Number of IS samples (100K is usually enough)
        seed: Random seed

    Returns:
        (pc_estimate, relative_standard_error)
    """
    rng = np.random.default_rng(seed)

    m = np.asarray(miss_vector_2d, dtype=np.float64)
    C = np.asarray(covariance_2d, dtype=np.float64)
    R = combined_radius_km

    # Target distribution: N(m, C) — Gaussian centered at miss point
    # Proposal distribution: N(0, C) — Gaussian centered at origin (hard body center)
    # Likelihood ratio: f_target(x) / f_proposal(x) = exp(-½(x-m)^T C^-1 (x-m) + ½ x^T C^-1 x)
    #                 = exp(m^T C^-1 x - ½ m^T C^-1 m)

    try:
        L = np.linalg.cholesky(C)
    except np.linalg.LinAlgError:
        L = np.linalg.cholesky(C + np.eye(2) * 1e-10)

    C_inv = np.linalg.inv(C)
    C_inv_m = C_inv @ m
    half_m_C_inv_m = 0.5 * float(m @ C_inv_m)

    # Sample from proposal: N(0, C)
    z = rng.standard_normal((2, n_samples))
    samples = L @ z  # (2, n_samples) — centered at origin

    # Check which samples are inside the hard body
    distances_sq = samples[0]**2 + samples[1]**2
    inside = distances_sq <= R**2

    if not np.any(inside):
        return 0.0, float("inf")

    # Compute likelihood ratio for samples inside the disk
    # log(w_i) = m^T C^-1 x_i - ½ m^T C^-1 m
    log_weights = C_inv_m[0] * samples[0, inside] + C_inv_m[1] * samples[1, inside] - half_m_C_inv_m
    weights = np.exp(log_weights)

    # IS estimate: Pc = (1/N) × Σ w_i
    pc = float(np.sum(weights)) / n_samples

    # Relative standard error
    if np.sum(inside) > 1:
        var_weights = float(np.var(weights))
        se = math.sqrt(var_weights / np.sum(inside)) / max(float(np.mean(weights)), 1e-30)
    else:
        se = float("inf")

    return max(0.0, min(1.0, pc)), se


def monte_carlo_confidence_interval(
    pc: float,
    n_samples: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Compute confidence interval for MC-estimated Pc.

    Uses the normal approximation to the binomial (valid when n*p > 5).

    Args:
        pc: Estimated Pc
        n_samples: Number of MC samples used
        confidence: Confidence level (default 95%)

    Returns:
        (lower_bound, upper_bound) of the confidence interval
    """
    from scipy.stats import norm

    z = norm.ppf((1 + confidence) / 2)
    se = math.sqrt(pc * (1 - pc) / n_samples) if pc > 0 else 0
    return (max(0, pc - z * se), min(1, pc + z * se))
