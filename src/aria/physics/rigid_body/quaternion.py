"""Unit-quaternion attitude kinematics (§4.7 of C3 scope).

A unit quaternion `q = (q_0, q_1, q_2, q_3)` with `|q| = 1` encodes a
rotation without gimbal lock. Its kinematic equation under a body-
frame angular velocity `ω` is (Kuipers 1999 *Quaternions and Rotation
Sequences* §6.7 eq. 6.36, ISBN 978-0691102986):

    q̇ = (1/2) Ω(ω) q                                    [1/s]

with the 4×4 skew-like matrix

    Ω(ω) = ⎡  0    −ω_1  −ω_2  −ω_3 ⎤
           ⎢ ω_1    0    ω_3  −ω_2 ⎥
           ⎢ ω_2  −ω_3    0    ω_1 ⎥
           ⎣ ω_3   ω_2  −ω_1    0  ⎦

or equivalently `q̇ = (1/2) q ⊗ (0, ω)` (Hamilton convention with
scalar-first storage).

Every function in this module uses scalar-first storage `(q_0, q_1,
q_2, q_3)` where `q_0 = cos(θ/2)` and `(q_1, q_2, q_3) = sin(θ/2) n̂`
for a rotation by angle θ about unit axis n̂.
"""

from __future__ import annotations

import math

import numpy as np


def quaternion_multiply(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    """Hamilton product `q1 ⊗ q2` (scalar-first).

    The rotation composition rule: if `R(q1)` and `R(q2)` are the
    rotation matrices of q1 and q2, then
        R(q1 ⊗ q2) = R(q1) R(q2)
    i.e. q2 is applied first, then q1 (right-to-left reading).
    """
    q1 = np.asarray(q1, dtype=float).reshape(4)
    q2 = np.asarray(q2, dtype=float).reshape(4)
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return np.array(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ],
        dtype=float,
    )


def quaternion_conjugate(q: np.ndarray) -> np.ndarray:
    """Conjugate `q* = (q_0, −q_1, −q_2, −q_3)`."""
    q = np.asarray(q, dtype=float).reshape(4)
    return np.array([q[0], -q[1], -q[2], -q[3]], dtype=float)


def quaternion_normalize(q: np.ndarray, tol: float = 1.0e-12) -> np.ndarray:
    """Project `q` onto the unit 3-sphere.

    Raises ``ValueError`` if the norm is below ``tol`` (zero quaternion).
    """
    q = np.asarray(q, dtype=float).reshape(4)
    n = float(np.linalg.norm(q))
    if n < tol:
        raise ValueError("quaternion has zero norm")
    return q / n


def quaternion_kinematic_matrix(omega_rad_s: np.ndarray) -> np.ndarray:
    """4×4 kinematic matrix `Ω(ω)` such that `q̇ = (1/2) Ω q`.

    Kuipers 1999 §6.7 eq. 6.36.
    """
    w = np.asarray(omega_rad_s, dtype=float).reshape(3)
    return np.array(
        [
            [0.0, -w[0], -w[1], -w[2]],
            [w[0], 0.0, w[2], -w[1]],
            [w[1], -w[2], 0.0, w[0]],
            [w[2], w[1], -w[0], 0.0],
        ],
        dtype=float,
    )


def quaternion_to_rotation_matrix(q: np.ndarray) -> np.ndarray:
    """Convert a unit quaternion to a 3×3 rotation matrix.

    Uses the standard Hamilton-convention formula (Kuipers 1999 §7.9):

        R(q) = ⎡1-2(y²+z²)   2(xy-wz)    2(xz+wy)⎤
               ⎢ 2(xy+wz)   1-2(x²+z²)   2(yz-wx)⎥
               ⎣ 2(xz-wy)    2(yz+wx)   1-2(x²+y²)⎦

    The input quaternion is assumed unit; caller should normalize if
    in doubt.
    """
    q = np.asarray(q, dtype=float).reshape(4)
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


def quaternion_from_axis_angle(
    axis: np.ndarray, angle_rad: float
) -> np.ndarray:
    """Construct a unit quaternion for a rotation by ``angle_rad``
    about ``axis``.

    q = (cos(θ/2), sin(θ/2) n̂)
    """
    axis = np.asarray(axis, dtype=float).reshape(3)
    n = float(np.linalg.norm(axis))
    if n == 0.0:
        raise ValueError("axis must be nonzero")
    n_hat = axis / n
    half = 0.5 * angle_rad
    s = math.sin(half)
    return np.array(
        [math.cos(half), s * n_hat[0], s * n_hat[1], s * n_hat[2]], dtype=float
    )


def integrate_quaternion_rk4(
    q0: np.ndarray,
    t0: float,
    t_end: float,
    dt: float,
    omega_fn,  # Callable[[float], np.ndarray]
) -> tuple[np.ndarray, float]:
    """Integrate `q̇ = (1/2) Ω(ω(t)) q` with classical RK4.

    The quaternion is re-normalized after every step to suppress drift
    off the unit sphere.

    Args:
        q0: (4,) initial attitude quaternion (scalar-first).
        t0, t_end: integration bounds (s).
        dt: step size (s).
        omega_fn: callable ``t → ω(t)`` returning (3,) rad/s.

    Returns:
        ``(q_final, t_final)``.
    """
    if dt <= 0.0:
        raise ValueError("dt must be positive")
    if t_end <= t0:
        raise ValueError("t_end must be strictly greater than t0")

    q = quaternion_normalize(np.asarray(q0, dtype=float).reshape(4))
    t = float(t0)
    while t < t_end:
        h = min(dt, t_end - t)
        k1 = 0.5 * quaternion_kinematic_matrix(omega_fn(t)) @ q
        k2 = 0.5 * quaternion_kinematic_matrix(omega_fn(t + 0.5 * h)) @ (q + 0.5 * h * k1)
        k3 = 0.5 * quaternion_kinematic_matrix(omega_fn(t + 0.5 * h)) @ (q + 0.5 * h * k2)
        k4 = 0.5 * quaternion_kinematic_matrix(omega_fn(t + h)) @ (q + h * k3)
        q = q + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
        q = quaternion_normalize(q)
        t += h
    return q, t
