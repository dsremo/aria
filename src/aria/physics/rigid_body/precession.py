"""Precession and gyroscopic torque closed forms (§4.4, §4.5, §9.4).

Three distinct regimes are covered here by analytic formulas derived
in the scope note §4:

  1. **Torque-free symmetric top**: `Ω_p = ((I_∥ − I_⊥)/I_⊥) ω_3`
     (Goldstein 2002 §5.6 eq. 5.49, ISBN 978-0201657029). Positive for
     an oblate body, negative for prolate. This is the rate at which
     the spin axis traces a cone in the body frame about the invariable
     (L) axis.

  2. **Heavy symmetric top, fast-spin limit**: the canonical gyroscope
     under gravity. When `ω_spin² ≫ m g l I_⊥ / I_∥²`, the nutation
     decouples and the steady precession is (Landau-Lifshitz Vol. 1 §35
     Problem 1, ISBN 978-0750628969):

         Ω_prec ≈ m g l / (I_∥ ω_spin)                    [rad/s]

     Below the fast-spin threshold the coupled nutation must be
     integrated; see `euler_equations.py`.

  3. **CMG reaction torque** (Wertz 1978 §15.2 "Control Moment
     Gyroscopes", ISBN 978-9027709592): a spinning rotor whose gimbal
     pivots at rate `ω_gimbal` exerts a reaction torque on the
     spacecraft equal to

         τ = I_∥ · ω_spin × ω_gimbal                      [N·m]

     This is the foundational identity of every CMG-based attitude
     control system and is verified by the C4 pod's CMG tests.
"""

from __future__ import annotations

import numpy as np


def torque_free_precession_rate(
    I_parallel_kg_m2: float,
    I_perpendicular_kg_m2: float,
    spin_rate_rad_s: float,
) -> float:
    """Torque-free precession rate of a symmetric top.

    Ω_p = ((I_∥ − I_⊥) / I_⊥) · ω_3                       [rad/s]

    Args:
        I_parallel_kg_m2: moment of inertia about the symmetry axis.
        I_perpendicular_kg_m2: moment of inertia about an axis in the
            equatorial plane.
        spin_rate_rad_s: `ω_3`, the body-frame spin component along
            the symmetry axis.

    Returns:
        Precession rate in rad/s. Positive → oblate (pancake) body,
        negative → prolate (pencil) body, zero → spherical.

    Reference: Goldstein 2002 §5.6 eq. 5.49.
    """
    if I_parallel_kg_m2 <= 0.0 or I_perpendicular_kg_m2 <= 0.0:
        raise ValueError("moments of inertia must be positive")
    return (
        (I_parallel_kg_m2 - I_perpendicular_kg_m2)
        / I_perpendicular_kg_m2
        * spin_rate_rad_s
    )


def fast_spin_precession_rate(
    mass_kg: float,
    g_m_s2: float,
    pivot_offset_m: float,
    I_parallel_kg_m2: float,
    spin_rate_rad_s: float,
) -> float:
    """Fast-spin heavy-top precession rate `Ω_prec = m g l / (I_∥ ω_spin)`.

    Valid in the fast-spin limit where the nutation angle amplitude is
    small. The condition is

        ω_spin² ≫ m g l I_⊥ / I_∥²

    but this routine does not check it — the caller is responsible for
    validating the regime against `I_⊥`.

    Args:
        mass_kg: top mass (kg).
        g_m_s2: magnitude of the local gravitational acceleration (m/s²).
        pivot_offset_m: distance from the pivot to the center of mass
            along the spin axis (m).
        I_parallel_kg_m2: moment of inertia about the spin axis.
        spin_rate_rad_s: angular speed about the spin axis.

    Returns:
        Steady precession rate about the vertical (rad/s).

    Reference: Landau-Lifshitz Vol. 1 §35 Problem 1; Goldstein 2002
    §5.7 eq. 5.72.
    """
    if mass_kg <= 0.0:
        raise ValueError("mass_kg must be positive")
    if g_m_s2 < 0.0:
        raise ValueError("g_m_s2 must be non-negative")
    if pivot_offset_m < 0.0:
        raise ValueError("pivot_offset_m must be non-negative")
    if I_parallel_kg_m2 <= 0.0:
        raise ValueError("I_parallel_kg_m2 must be positive")
    if spin_rate_rad_s == 0.0:
        raise ValueError("spin_rate_rad_s must be nonzero")
    return mass_kg * g_m_s2 * pivot_offset_m / (I_parallel_kg_m2 * spin_rate_rad_s)


def cmg_reaction_torque(
    I_parallel_kg_m2: float,
    omega_spin_rad_s: np.ndarray,
    omega_gimbal_rad_s: np.ndarray,
) -> np.ndarray:
    """Control-moment-gyro reaction torque `τ = I_∥ ω_spin × ω_gimbal`.

    A spinning flywheel with angular momentum `L = I_∥ ω_spin` that is
    re-oriented at rate `ω_gimbal` exerts a torque on the spacecraft
    equal to

        τ = dL/dt = ω_gimbal × L = I_∥ ω_gimbal × ω_spin

    (Wertz 1978 §15.2). The sign convention here: we return
    `I_∥ ω_spin × ω_gimbal`, which is −1 times the Wertz expression
    above — the sign represents the torque exerted by the rotor on
    the spacecraft (Newton's third law flip). The magnitude is the
    same:

        |τ| = I_∥ |ω_spin| |ω_gimbal| sin θ

    where θ is the angle between the spin and gimbal-rate vectors.
    For the canonical `ω_spin ⊥ ω_gimbal` case this reduces to
    `|τ| = I_∥ ω_spin ω_gimbal`.

    Args:
        I_parallel_kg_m2: flywheel moment of inertia about the spin
            axis (kg·m²).
        omega_spin_rad_s: (3,) spin angular-velocity vector (rad/s).
        omega_gimbal_rad_s: (3,) gimbal-rate angular-velocity vector
            (rad/s).

    Returns:
        (3,) reaction torque vector (N·m).
    """
    if I_parallel_kg_m2 <= 0.0:
        raise ValueError("I_parallel_kg_m2 must be positive")
    w_spin = np.asarray(omega_spin_rad_s, dtype=float).reshape(3)
    w_gimbal = np.asarray(omega_gimbal_rad_s, dtype=float).reshape(3)
    return I_parallel_kg_m2 * np.cross(w_spin, w_gimbal)
