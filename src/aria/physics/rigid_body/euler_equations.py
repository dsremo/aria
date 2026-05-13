"""Euler's equations of rigid-body motion (§4.2–§4.3 of C3 scope).

Starting from angular momentum in the body frame

    L_body = I ω_body                                     [kg·m²/s]

and the general relation between body-frame and inertial time
derivatives (Goldstein 2002 eq. 5.36, ISBN 978-0201657029)

    (dL/dt)_inertial = (dL/dt)_body + ω × L

the applied torque τ is simply the inertial derivative:

    τ = (dL/dt)_body + ω × L                              [N·m]

In the principal body frame where I = diag(I_1, I_2, I_3), this reduces
to the three scalar Euler equations (Goldstein 2002 eq. 5.39;
Landau-Lifshitz Vol. 1 §36 eq. 36.5, ISBN 978-0750628969):

    I_1 ω̇_1 − (I_2 − I_3) ω_2 ω_3 = τ_1
    I_2 ω̇_2 − (I_3 − I_1) ω_3 ω_1 = τ_2
    I_3 ω̇_3 − (I_1 − I_2) ω_1 ω_2 = τ_3

Equivalently, in full matrix form valid for any symmetric I (not
necessarily diagonal),

    I ω̇ = τ − ω × (I ω)

and this is what `euler_equations_rhs` computes.

Conservation quantities monitored by the integrator:

    L² = (Iω)·(Iω)                 (constant in torque-free case)
    T  = (1/2) ωᵀ I ω               (kinetic energy; dT/dt = ω·τ)

These are checked by the test suite to verify integrator correctness.
"""

from __future__ import annotations

from typing import Callable

import numpy as np


def euler_equations_rhs(
    inertia_kg_m2: np.ndarray,
    omega_rad_s: np.ndarray,
    torque_n_m: np.ndarray,
) -> np.ndarray:
    """Body-frame angular acceleration `dω/dt = I⁻¹ (τ − ω × (I ω))`.

    Works for any symmetric positive-definite inertia tensor, not only
    diagonal principal-frame tensors.

    Args:
        inertia_kg_m2: (3, 3) body-frame inertia tensor (kg·m²).
        omega_rad_s: (3,) body-frame angular velocity (rad/s).
        torque_n_m: (3,) body-frame applied torque (N·m).

    Returns:
        (3,) body-frame angular acceleration (rad/s²).
    """
    I = np.asarray(inertia_kg_m2, dtype=float).reshape(3, 3)
    omega = np.asarray(omega_rad_s, dtype=float).reshape(3)
    torque = np.asarray(torque_n_m, dtype=float).reshape(3)
    L = I @ omega
    rhs = torque - np.cross(omega, L)
    # Solve I · ω̇ = rhs. `np.linalg.solve` gives machine-precision
    # regardless of whether I is diagonal.
    return np.linalg.solve(I, rhs)


def kinetic_energy(
    inertia_kg_m2: np.ndarray, omega_rad_s: np.ndarray
) -> float:
    """Rotational kinetic energy `T = (1/2) ωᵀ I ω` [J]."""
    I = np.asarray(inertia_kg_m2, dtype=float).reshape(3, 3)
    omega = np.asarray(omega_rad_s, dtype=float).reshape(3)
    return 0.5 * float(omega @ I @ omega)


TorqueFn = Callable[[float, np.ndarray], np.ndarray]
"""A time- and state-dependent torque function `τ(t, ω) → (3,)` [N·m]."""


def integrate_rigid_body_rk4(
    inertia_kg_m2: np.ndarray,
    omega0_rad_s: np.ndarray,
    t0: float,
    t_end: float,
    dt: float,
    torque_fn: TorqueFn | None = None,
) -> tuple[np.ndarray, float]:
    """Integrate body-frame ω(t) with classical RK4 under an
    arbitrary time- and state-dependent torque.

    Args:
        inertia_kg_m2: (3, 3) body-frame inertia tensor (kg·m²). Held
            constant — see §10 of the scope for `dI/dt` handling.
        omega0_rad_s: (3,) initial body-frame angular velocity.
        t0, t_end: integration bounds (s).
        dt: fixed step size (s).
        torque_fn: optional `(t, ω) → τ` returning (3,) N·m. Default
            is the zero torque (torque-free precession).

    Returns:
        ``(omega_final, t_final)`` — (3,) and float.

    Conservation check: the caller is expected to verify |L|² and T
    drift (see the test suite). This routine does not enforce them.
    """
    if dt <= 0.0:
        raise ValueError("dt must be positive")
    if t_end <= t0:
        raise ValueError("t_end must be strictly greater than t0")

    I = np.asarray(inertia_kg_m2, dtype=float).reshape(3, 3)
    omega = np.asarray(omega0_rad_s, dtype=float).reshape(3).copy()

    if torque_fn is None:
        def _zero_tau(_t: float, _w: np.ndarray) -> np.ndarray:
            return np.zeros(3)
        torque_fn = _zero_tau

    t = float(t0)
    while t < t_end:
        h = min(dt, t_end - t)
        k1 = euler_equations_rhs(I, omega, torque_fn(t, omega))
        k2 = euler_equations_rhs(
            I, omega + 0.5 * h * k1, torque_fn(t + 0.5 * h, omega + 0.5 * h * k1)
        )
        k3 = euler_equations_rhs(
            I, omega + 0.5 * h * k2, torque_fn(t + 0.5 * h, omega + 0.5 * h * k2)
        )
        k4 = euler_equations_rhs(
            I, omega + h * k3, torque_fn(t + h, omega + h * k3)
        )
        omega = omega + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
        t += h
    return omega, t


def integrate_free_body_rk4(
    inertia_kg_m2: np.ndarray,
    omega0_rad_s: np.ndarray,
    t0: float,
    t_end: float,
    dt: float,
) -> tuple[np.ndarray, float]:
    """Convenience wrapper for torque-free integration."""
    return integrate_rigid_body_rk4(
        inertia_kg_m2, omega0_rad_s, t0, t_end, dt, torque_fn=None
    )
