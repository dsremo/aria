"""3-1-3 Euler angle conversions (§4.6 of C3 scope).

The 3-1-3 convention (z-x-z) is the classical choice in textbooks
(Goldstein 2002 Figure 4.7, ISBN 978-0201657029). Three successive
rotations:

  1. rotate by φ about the z-axis of the original frame,
  2. rotate by θ about the x-axis of the new frame (the "line of
     nodes"),
  3. rotate by ψ about the z-axis of the final frame.

The composed rotation matrix is (Goldstein 2002 eq. 4.46):

    R = R_z(ψ) R_x(θ) R_z(φ)

This module provides the forward `(φ, θ, ψ) → R` and the inverse
`R → (φ, θ, ψ)`. The inverse is singular at `sin θ = 0`, which is why
quaternions are preferred numerically; C3 uses Euler angles only for
diagnostic output and switches to quaternions inside `|sin θ| < 10⁻³`.
"""

from __future__ import annotations

import math

import numpy as np


def rotation_matrix_313(phi: float, theta: float, psi: float) -> np.ndarray:
    """3-1-3 Euler-angle rotation matrix `R = R_z(ψ) R_x(θ) R_z(φ)`.

    All angles in radians. Returns a (3, 3) proper rotation matrix
    (determinant +1, orthogonal).
    """
    c1, s1 = math.cos(phi), math.sin(phi)
    c2, s2 = math.cos(theta), math.sin(theta)
    c3, s3 = math.cos(psi), math.sin(psi)

    Rz_phi = np.array(
        [[c1, -s1, 0.0], [s1, c1, 0.0], [0.0, 0.0, 1.0]], dtype=float
    )
    Rx_theta = np.array(
        [[1.0, 0.0, 0.0], [0.0, c2, -s2], [0.0, s2, c2]], dtype=float
    )
    Rz_psi = np.array(
        [[c3, -s3, 0.0], [s3, c3, 0.0], [0.0, 0.0, 1.0]], dtype=float
    )
    return Rz_psi @ Rx_theta @ Rz_phi


def euler_angles_313_from_rotation_matrix(
    R: np.ndarray,
) -> tuple[float, float, float]:
    """Inverse of `rotation_matrix_313`.

    Returns:
        ``(phi, theta, psi)`` in radians.

    Raises:
        ValueError: if R is within 1e-6 of a singular configuration
            (`|sin θ| < 1e-3`). Caller is expected to fall back to
            quaternions in that regime.
    """
    R = np.asarray(R, dtype=float).reshape(3, 3)
    # R_{33} = cos θ in the 3-1-3 convention.
    cos_theta = R[2, 2]
    cos_theta = min(max(cos_theta, -1.0), 1.0)
    theta = math.acos(cos_theta)
    sin_theta = math.sin(theta)
    if abs(sin_theta) < 1.0e-3:
        raise ValueError(
            "3-1-3 Euler inverse is singular for sin(theta) → 0; "
            "use quaternions in this regime"
        )
    # Expanding R = R_z(psi) · R_x(theta) · R_z(phi) entry-by-entry
    # with c(x) ≡ cos x, s(x) ≡ sin x gives:
    #   R[0, 2] = sin(psi) sin(theta)
    #   R[1, 2] = -cos(psi) sin(theta)
    #   R[2, 0] = sin(phi) sin(theta)
    #   R[2, 1] = cos(phi) sin(theta)
    #   R[2, 2] = cos(theta)
    # so atan2 of the right quadrant gives each angle unambiguously:
    psi = math.atan2(R[0, 2], -R[1, 2])
    phi = math.atan2(R[2, 0], R[2, 1])
    return phi, theta, psi
