"""4-CMG pyramid cluster (§4.3 of C4 scope).

A standard Control Moment Gyro pyramid (Wie 1998 §7.4) has four
single-gimbal CMGs mounted on the four faces of a symmetric pyramid
with skew angle β. The canonical value β = arctan(√2) ≈ 54.7356°
makes the maximum-momentum envelope spherical — the ISS CMG cluster
uses this geometry (Bedrossian et al. 2009 *J Guidance* 32(2) 553).

Per CMG `i`, define the gimbal axis ĝ_i (fixed in the bus frame) and
the rotor spin axis ŝ_i(δ_i), which lies in the plane perpendicular
to ĝ_i and rotates with gimbal angle δ_i. The rotor angular momentum
vector is

    h_i(δ_i) = h_0 · ŝ_i(δ_i)                                  [N·m·s]

so the total cluster momentum is Σ h_i(δ_i) and the Jacobian that
maps gimbal rates to cluster-torque rate is

    J_i = ∂h_i/∂δ_i = h_0 · ∂ŝ_i/∂δ_i = h_0 · (ĝ_i × ŝ_i)     [N·m]

The 3×4 Jacobian matrix H(δ) has these as its columns. The commanded
torque on the bus is τ = −H(δ) · δ̇.

Pyramid parameters (Wie 1998 §7.4, Fig 7.16):

    gimbal axes:        ĝ_1 = (-sβ,  0, cβ)
                        ĝ_2 = ( 0, -sβ, cβ)
                        ĝ_3 = ( sβ,  0, cβ)
                        ĝ_4 = ( 0,  sβ, cβ)
    rotor axes (δ=0):   ŝ_1 = ( 0,  1,  0)
                        ŝ_2 = ( 1,  0,  0)
                        ŝ_3 = ( 0, -1,  0)
                        ŝ_4 = (-1,  0,  0)

with s = sin, c = cos. Rotor axis as a function of gimbal angle is

    ŝ_i(δ_i) = cos δ_i · ŝ_i(0) + sin δ_i · (ĝ_i × ŝ_i(0))
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# ISS CMG pyramid skew angle (Wie 1998 §7.4.2; Bedrossian 2009).
ISS_CMG_PYRAMID_SKEW_DEG: float = 54.7356

# ISS CMG rotor angular momentum (Bedrossian 2009 Table 2).
ISS_CMG_ROTOR_MOMENTUM_N_M_S: float = 4760.0


def _pyramid_gimbal_and_zero_rotor_axes(
    skew_rad: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (ĝ, ŝ_0) arrays of shape (4, 3)."""
    s, c = math.sin(skew_rad), math.cos(skew_rad)
    g = np.array(
        [
            [-s, 0.0, c],
            [0.0, -s, c],
            [s, 0.0, c],
            [0.0, s, c],
        ]
    )
    s0 = np.array(
        [
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0],
            [-1.0, 0.0, 0.0],
        ]
    )
    return g, s0


def cmg_pyramid_total_momentum(
    gimbal_angles_rad: np.ndarray,
    rotor_momentum_n_m_s: float = ISS_CMG_ROTOR_MOMENTUM_N_M_S,
    skew_deg: float = ISS_CMG_PYRAMID_SKEW_DEG,
) -> np.ndarray:
    """Total CMG cluster momentum h_stack = Σ h_i(δ_i)         [N·m·s].

    Args:
        gimbal_angles_rad: (4,) array of δ_i.
        rotor_momentum_n_m_s: scalar |h_i| per CMG (assumed equal).
        skew_deg: pyramid skew angle in degrees.

    Returns:
        3-vector of cluster angular momentum in the bus frame.
    """
    delta = np.asarray(gimbal_angles_rad, dtype=float)
    if delta.shape != (4,):
        raise ValueError("gimbal_angles_rad must be (4,)")
    if rotor_momentum_n_m_s <= 0.0:
        raise ValueError("rotor_momentum_n_m_s must be positive")
    skew = math.radians(skew_deg)
    g, s0 = _pyramid_gimbal_and_zero_rotor_axes(skew)
    total = np.zeros(3)
    for i in range(4):
        s_hat = (
            math.cos(delta[i]) * s0[i]
            + math.sin(delta[i]) * np.cross(g[i], s0[i])
        )
        total += rotor_momentum_n_m_s * s_hat
    return total


def cmg_pyramid_jacobian(
    gimbal_angles_rad: np.ndarray,
    rotor_momentum_n_m_s: float = ISS_CMG_ROTOR_MOMENTUM_N_M_S,
    skew_deg: float = ISS_CMG_PYRAMID_SKEW_DEG,
) -> np.ndarray:
    """3×4 Jacobian H(δ) with columns J_i = h_0 · (ĝ_i × ŝ_i(δ_i)).

    Wie 1998 §7.4.2 eq. 7.59. The CMG steering law uses this matrix.
    """
    delta = np.asarray(gimbal_angles_rad, dtype=float)
    if delta.shape != (4,):
        raise ValueError("gimbal_angles_rad must be (4,)")
    if rotor_momentum_n_m_s <= 0.0:
        raise ValueError("rotor_momentum_n_m_s must be positive")
    skew = math.radians(skew_deg)
    g, s0 = _pyramid_gimbal_and_zero_rotor_axes(skew)
    h = np.zeros((3, 4))
    for i in range(4):
        s_hat = (
            math.cos(delta[i]) * s0[i]
            + math.sin(delta[i]) * np.cross(g[i], s0[i])
        )
        h[:, i] = rotor_momentum_n_m_s * np.cross(g[i], s_hat)
    return h


@dataclass(frozen=True)
class PyramidCMGCluster:
    """Immutable descriptor of a 4-CMG pyramid cluster.

    Attributes:
        rotor_momentum_n_m_s: |h_i| per CMG.
        skew_deg: pyramid skew angle (β).
        gimbal_rate_limit_rad_s: hardware δ̇ saturation (defaults
            from Wie 1998 §7.4.1 ISS value 0.0524 rad/s = 3°/s).
    """

    rotor_momentum_n_m_s: float = ISS_CMG_ROTOR_MOMENTUM_N_M_S
    skew_deg: float = ISS_CMG_PYRAMID_SKEW_DEG
    gimbal_rate_limit_rad_s: float = 0.0524  # Wie 1998 §7.4.1 ISS
