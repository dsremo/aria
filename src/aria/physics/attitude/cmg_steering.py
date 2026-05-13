"""CMG steering law and singularity metric (§4.3 of C4 scope).

Moore-Penrose pseudoinverse steering (Wie 1998 §7.4.3):

    δ̇ = −H⁺(δ) · τ_cmd                                       [rad/s]

is optimal in the least-squares sense but blows up near internal
singularities where rank(H) < 3. The Margulies-Aubrun 1978
*J Astronaut Sci* 26(2) 159 singularity metric uses

    m_MA(δ) = √( det(H Hᵀ) )                                  [N³·m³·s³]

which vanishes at any singular configuration and equals the volume
of the 3-D momentum-envelope parallelepiped elsewhere. Oh & Vadali
1991 *J Guidance* 14(1) 69 showed that a damped pseudoinverse
(Singular Value Decomposition with small-singular-value clipping) is
the simplest steering law that degrades gracefully near the
singularity.
"""

from __future__ import annotations

import numpy as np


def singularity_margin(jacobian_3x4: np.ndarray) -> float:
    """Margulies-Aubrun 1978 singularity metric √(det(H Hᵀ)).

    Returns 0 at any singular configuration; equal to h₀³ for the
    most-generic non-singular pyramid pose (Wie 1998 §7.4.3).
    """
    h = np.asarray(jacobian_3x4, dtype=float)
    if h.shape != (3, 4):
        raise ValueError("jacobian_3x4 must be 3x4")
    determinant = float(np.linalg.det(h @ h.T))
    if determinant < 0.0:
        return 0.0  # numerical underflow; treat as singular
    return float(np.sqrt(determinant))


def cmg_pseudoinverse_steering(
    jacobian_3x4: np.ndarray,
    commanded_torque_n_m: np.ndarray,
    min_singular_value: float = 1.0e-3,
) -> np.ndarray:
    """Damped Moore-Penrose steering law for CMG gimbal rates.

    δ̇ = −H⁺_damped · τ_cmd                                   [rad/s]

    where H⁺_damped clips all singular values below
    `min_singular_value` to zero before the Moore-Penrose inversion,
    giving graceful degradation near internal singularities
    (Oh & Vadali 1991 *J Guidance* 14(1) 69; Wie 1998 §7.4.3).

    Args:
        jacobian_3x4: H(δ) from ``cmg_pyramid_jacobian``.
        commanded_torque_n_m: τ_cmd in the bus frame (3,).
        min_singular_value: SVD clipping threshold in the units of
            σ_i. Singular values below this are replaced by zero.

    Returns:
        Gimbal-rate command δ̇ ∈ ℝ⁴ (rad/s).
    """
    h = np.asarray(jacobian_3x4, dtype=float)
    tau = np.asarray(commanded_torque_n_m, dtype=float)
    if h.shape != (3, 4):
        raise ValueError("jacobian_3x4 must be 3x4")
    if tau.shape != (3,):
        raise ValueError("commanded_torque_n_m must be (3,)")
    u, s, vt = np.linalg.svd(h, full_matrices=False)
    mask = s > min_singular_value
    s_damped = np.zeros_like(s)
    s_damped[mask] = 1.0 / s[mask]
    h_pinv = (vt.T * s_damped) @ u.T  # (4, 3)
    return -h_pinv @ tau
