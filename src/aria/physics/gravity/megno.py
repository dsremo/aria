"""MEGNO chaos indicator — Mean Exponential Growth of Nearby Orbits.

Computes the MEGNO (Y) and Lyapunov exponent for an orbit to detect
chaotic vs regular motion. A regular orbit has <Y> → 2.0; a chaotic
orbit has <Y> → ∞ (growing linearly with time).

This is a unique differentiator for conjunction assessment: chaotic
orbits are unpredictable beyond a Lyapunov time, so collision
probability becomes meaningless. MEGNO identifies these cases.

The method integrates variational equations alongside the equations
of motion. A small perturbation vector (δ) evolves via the Jacobian
of the acceleration, and MEGNO is computed from the growth rate of |δ|.

References:
    Cincotta, P.M. & Simó, C. (2000). "Simple Tools to Study Global
    Dynamics in Non-Axisymmetric Galactic Potentials – I."
    Astronomy & Astrophysics Suppl., 147, 205-228.

    Cincotta, P.M., Giordano, C.M. & Simó, C. (2003). "Phase Space
    Structure of Multi-Dimensional Systems by Means of MEGNO."
    Physica D, 182, 151-178.

    Algorithm studied from Rebound tools.c (GPL, clean-room reimplemented
    from the published papers above).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Tuple

import numpy as np


@dataclass
class MegnoResult:
    """Result of a MEGNO chaos analysis."""
    megno_mean: float        # <Y> — time-averaged MEGNO (2.0 = regular, growing = chaotic)
    megno_instant: float     # Y(t) — instantaneous MEGNO
    lyapunov_exp: float      # largest Lyapunov exponent (positive = chaotic) [1/time_unit]
    is_chaotic: bool         # True if MEGNO indicates chaotic motion
    t_final: float
    n_steps: int


def compute_megno(
    accel_fn: Callable[[float, np.ndarray], np.ndarray],
    r0: np.ndarray,
    v0: np.ndarray,
    t0: float,
    t_end: float,
    mu: float,
    dt: float = 0.0,
    chaos_threshold: float = 2.5,
    min_periods: float = 0.0,
) -> MegnoResult:
    """Compute MEGNO and Lyapunov exponent for an orbit.

    Integrates the equations of motion AND the variational equations
    simultaneously using RK4. The variational equations track how a
    small perturbation grows over time.

    Convergence note: for regular (non-chaotic) orbits, <Y> converges to
    2.0 as t → ∞, but the convergence is slow (∝ 1/t). A circular orbit
    gives <Y> ≈ 2.07 at 100 orbital periods and ≈ 2.35 at 10 periods.
    Chaotic orbits diverge rapidly (>5 after a few periods), so the
    algorithm reliably distinguishes chaos even at short integration times;
    but for precision <Y> ≈ 2.0, use min_periods ≥ 50.

    Args:
        accel_fn: callable(t, r) → (3,) acceleration
        r0: (3,) initial position
        v0: (3,) initial velocity
        t0: start time
        t_end: end time (may be extended by min_periods)
        mu: gravitational parameter (for Jacobian computation)
        dt: timestep (0 = auto from orbital period estimate)
        chaos_threshold: MEGNO threshold for chaos classification.
            Default 2.5 works for integrations > 10 orbital periods.
            For short integrations (< 5 periods), use 4.0 to avoid false positives.
        min_periods: ensure integration covers at least this many orbital
            periods. If t_end − t0 is too short, t_end is extended.
            Use min_periods=50 for accurate <Y> ≈ 2.0 (±0.1).

    Returns:
        MegnoResult with MEGNO, Lyapunov exponent, and chaos flag.
    """
    r = np.asarray(r0, dtype=float).copy()
    v = np.asarray(v0, dtype=float).copy()
    t = float(t0)

    # Auto-select timestep and estimate orbital period
    r_mag = np.linalg.norm(r)
    a_mag = float(np.linalg.norm(accel_fn(t, r)))
    if a_mag > 0:
        period_est = 2.0 * np.pi * np.sqrt(r_mag / a_mag)
    else:
        period_est = 0.0

    if dt <= 0:
        if period_est > 0:
            dt = period_est / 100.0
        else:
            dt = (t_end - t0) / 1000.0

    # Enforce minimum integration length if requested
    if min_periods > 0 and period_est > 0:
        t_min_required = t0 + min_periods * period_est
        t_end = max(t_end, t_min_required)

    dt = min(dt, (t_end - t0) / 10.0)

    # Initial variational vector (random unit perturbation)
    rng = np.random.RandomState(42)
    delta_r = rng.randn(3)
    delta_v = rng.randn(3)
    delta_norm = np.sqrt(np.dot(delta_r, delta_r) + np.dot(delta_v, delta_v))
    delta_r /= delta_norm
    delta_v /= delta_norm

    # MEGNO accumulators
    Y_sum = 0.0   # sum for time-averaged MEGNO
    Y_inst = 0.0  # instantaneous MEGNO
    n_steps = 0

    while t < t_end:
        h = min(dt, t_end - t)
        if h < 1e-15:
            break

        # RK4 step for both state and variational equations
        r, v, delta_r, delta_v, dy = _rk4_megno_step(
            accel_fn, mu, t, r, v, delta_r, delta_v, h
        )
        t += h
        n_steps += 1

        # Accumulate MEGNO
        delta_mag = np.sqrt(np.dot(delta_r, delta_r) + np.dot(delta_v, delta_v))
        if delta_mag > 0 and t - t0 > 0:
            Y_inst = 2.0 * (t - t0) * dy / max(delta_mag, 1e-300)
            Y_sum += Y_inst * h

        # Renormalize variational vector to prevent overflow
        if delta_mag > 1e10:
            scale = 1.0 / delta_mag
            delta_r *= scale
            delta_v *= scale

    # Time-averaged MEGNO
    total_time = t - t0
    megno_mean = Y_sum / max(total_time, 1e-30) if total_time > 0 else 0.0

    # Lyapunov exponent: for regular orbits, <Y>/(2t) → 0; for chaotic, it's positive
    delta_mag = np.sqrt(np.dot(delta_r, delta_r) + np.dot(delta_v, delta_v))
    lyapunov = np.log(max(delta_mag, 1e-300)) / max(total_time, 1e-30)

    return MegnoResult(
        megno_mean=megno_mean,
        megno_instant=Y_inst,
        lyapunov_exp=lyapunov,
        is_chaotic=megno_mean > chaos_threshold,
        t_final=t,
        n_steps=n_steps,
    )


def _gravity_jacobian(r: np.ndarray, mu: float) -> np.ndarray:
    """Compute the 3x3 Jacobian (tidal tensor) of the gravitational acceleration.

    J_ij = ∂a_i/∂r_j = -μ/r³ (δ_ij - 3 r_i r_j / r²)

    This is the gradient of the gravitational field, needed for
    variational equation integration.
    """
    r_mag = np.linalg.norm(r)
    if r_mag < 1e-30:
        return np.zeros((3, 3))

    r3 = r_mag ** 3
    r5 = r_mag ** 5

    J = np.zeros((3, 3))
    for i in range(3):
        for j in range(3):
            J[i, j] = -mu * (-3.0 * r[i] * r[j] / r5)
            if i == j:
                J[i, j] += -mu / r3

    return J


def _rk4_megno_step(
    accel_fn, mu, t, r, v, dr, dv, h
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    """RK4 step for both orbit and variational equations.

    Returns (r_new, v_new, dr_new, dv_new, delta_growth_rate)
    """
    # State derivatives
    def derivs(t_loc, r_loc, v_loc, dr_loc, dv_loc):
        a = accel_fn(t_loc, r_loc)
        J = _gravity_jacobian(r_loc, mu)
        da = J @ dr_loc  # variational acceleration
        return v_loc, a, dv_loc, da

    # RK4 stages
    v1, a1, dv1, da1 = derivs(t, r, v, dr, dv)

    r2 = r + 0.5 * h * v1
    v2_arg = v + 0.5 * h * a1
    dr2 = dr + 0.5 * h * dv1
    dv2 = dv + 0.5 * h * da1
    v2, a2, ddv2, dda2 = derivs(t + 0.5 * h, r2, v2_arg, dr2, dv2)

    r3 = r + 0.5 * h * v2
    v3_arg = v + 0.5 * h * a2
    dr3 = dr + 0.5 * h * ddv2
    dv3 = dv + 0.5 * h * dda2
    v3, a3, ddv3, dda3 = derivs(t + 0.5 * h, r3, v3_arg, dr3, dv3)

    r4 = r + h * v3
    v4_arg = v + h * a3
    dr4 = dr + h * ddv3
    dv4 = dv + h * dda3
    v4, a4, ddv4, dda4 = derivs(t + h, r4, v4_arg, dr4, dv4)

    # Combine
    r_new = r + h / 6.0 * (v1 + 2.0 * v2 + 2.0 * v3 + v4)
    v_new = v + h / 6.0 * (a1 + 2.0 * a2 + 2.0 * a3 + a4)
    dr_new = dr + h / 6.0 * (dv1 + 2.0 * ddv2 + 2.0 * ddv3 + ddv4)
    dv_new = dv + h / 6.0 * (da1 + 2.0 * dda2 + 2.0 * dda3 + dda4)

    # Growth rate of variational vector
    delta_mag = np.sqrt(np.dot(dr_new, dr_new) + np.dot(dv_new, dv_new))
    delta_dot = (np.dot(dr_new, dv_new) + np.dot(dv_new, _gravity_jacobian(r_new, mu) @ dr_new))
    dy = delta_dot / max(delta_mag, 1e-300)

    return r_new, v_new, dr_new, dv_new, dy
