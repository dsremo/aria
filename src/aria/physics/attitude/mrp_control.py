"""MRP feedback attitude controller.

Implements the Modified Rodrigues Parameter (MRP) feedback control law
for spacecraft attitude stabilization and tracking. MRP is a 3-parameter
attitude representation that avoids gimbal lock (unlike Euler angles)
and is more compact than quaternions.

The control law computes the required torque to drive the spacecraft
from its current attitude to a reference attitude, with optional
integral feedback for steady-state error rejection.

Control law (Schaub & Junkins 2018, Eq. 8.151):
    Lr = -K*sigma_BR - P*delta_omega - P*Ki*z + [omega x] (I*omega + h_rw)
         - I*(domega_r/dt - omega x omega_r) - L_ext

where:
    sigma_BR = MRP attitude error (body relative to reference)
    delta_omega = omega_BN - omega_RN (rate tracking error)
    z = integral of sigma_BR (with anti-windup)
    I = spacecraft inertia tensor
    h_rw = reaction wheel angular momentum

Algorithm studied from Basilisk mrpFeedback.c (ISC license).

References:
    Schaub, H. & Junkins, J.L. (2018). "Analytical Mechanics of Space
    Systems" 4th ed. AIAA. Chapter 8.

    Shuster, M.D. (1993). "A Survey of Attitude Representations."
    J. Astronautical Sciences, 41(4), 439-517.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class AttitudeState:
    """Spacecraft attitude state in MRP representation."""
    sigma: np.ndarray = field(default_factory=lambda: np.zeros(3))   # MRP attitude
    omega: np.ndarray = field(default_factory=lambda: np.zeros(3))   # angular velocity [rad/s]
    inertia: np.ndarray = field(default_factory=lambda: np.eye(3) * 100.0)  # [kg*m²]


@dataclass
class AttitudeReference:
    """Desired attitude reference."""
    sigma_ref: np.ndarray = field(default_factory=lambda: np.zeros(3))  # reference MRP
    omega_ref: np.ndarray = field(default_factory=lambda: np.zeros(3))  # ref angular velocity
    domega_ref: np.ndarray = field(default_factory=lambda: np.zeros(3))  # ref angular accel


@dataclass
class ControlTorque:
    """Output of the attitude controller."""
    torque: np.ndarray = field(default_factory=lambda: np.zeros(3))  # [N*m]
    integral_torque: np.ndarray = field(default_factory=lambda: np.zeros(3))


class MRPFeedbackController:
    """MRP feedback attitude control with integral action.

    Usage:
        ctrl = MRPFeedbackController(K=0.1, P=10.0)
        state = AttitudeState(sigma=..., omega=..., inertia=...)
        ref = AttitudeReference(sigma_ref=..., omega_ref=...)
        torque = ctrl.compute(state, ref, dt=0.1)
    """

    def __init__(
        self,
        K: float = 0.1,          # proportional gain [rad/s]
        P: float = 10.0,         # rate gain [N*m*s]
        Ki: float = 0.0,         # integral gain [N*m] (0 = disabled)
        integral_limit: float = 1.0,  # anti-windup limit [N*m]
    ) -> None:
        self.K = K
        self.P = P
        self.Ki = Ki
        self.integral_limit = integral_limit

        # Internal integral state
        self._int_sigma = np.zeros(3)
        self._z = np.zeros(3)

    def reset(self) -> None:
        """Reset integral state."""
        self._int_sigma = np.zeros(3)
        self._z = np.zeros(3)

    def compute(
        self,
        state: AttitudeState,
        ref: AttitudeReference,
        dt: float,
        rw_momentum: Optional[np.ndarray] = None,
        external_torque: Optional[np.ndarray] = None,
    ) -> ControlTorque:
        """Compute control torque using MRP feedback law.

        Args:
            state: Current spacecraft attitude state
            ref: Desired reference attitude
            dt: Control timestep [s]
            rw_momentum: (3,) reaction wheel angular momentum [N*m*s]
            external_torque: (3,) known external torques [N*m]

        Returns:
            ControlTorque with body-frame torque command
        """
        I = state.inertia
        sigma_BR = mrp_error(state.sigma, ref.sigma_ref)
        omega_BR = state.omega - ref.omega_ref
        omega_BN = state.omega

        # Integral feedback with anti-windup
        self._z[:] = 0.0
        int_torque = np.zeros(3)
        if self.Ki > 0 and dt > 0:
            self._int_sigma += self.K * dt * sigma_BR

            # Anti-windup: clamp integral magnitude
            for i in range(3):
                if abs(self._int_sigma[i]) > self.integral_limit:
                    self._int_sigma[i] = math.copysign(self.integral_limit, self._int_sigma[i])

            self._z = self._int_sigma + I @ omega_BR
            int_torque = self.P * self.Ki * self._z

        # Main control law: Lr = K*sigma + P*omega_err + P*Ki*z
        Lr = self.K * sigma_BR + self.P * omega_BR + int_torque

        # Gyroscopic term: omega x (I*omega + h_rw)
        h_total = I @ omega_BN
        if rw_momentum is not None:
            h_total = h_total + rw_momentum

        omega_cross = omega_BN
        if self.Ki > 0:
            omega_cross = ref.omega_ref + self.Ki * self._z

        Lr -= np.cross(omega_cross, h_total)

        # Feedforward: I*(domega_r/dt - omega x omega_r)
        ff = np.cross(omega_BN, ref.omega_ref) - ref.domega_ref
        Lr += I @ ff

        # Known external torques
        if external_torque is not None:
            Lr += external_torque

        # Negate for positive control convention
        Lr = -Lr

        return ControlTorque(torque=Lr, integral_torque=-int_torque)


# ══════════════════════════════════════════════════════════════════
#  MRP utilities
# ══════════════════════════════════════════════════════════════════

def mrp_error(sigma_current: np.ndarray, sigma_desired: np.ndarray) -> np.ndarray:
    """Compute MRP attitude error: sigma_BR = sigma_BN ⊖ sigma_RN.

    The MRP subtraction (relative rotation) is:
        sigma_BR = ((1 - |sigma_R|²)*sigma_B - (1 - |sigma_B|²)*sigma_R
                    + 2*cross(sigma_B, sigma_R))
                   / (1 + |sigma_B|²*|sigma_R|² + 2*dot(sigma_B, sigma_R))

    Reference: Schaub & Junkins (2018) Eq. (3.168).
    """
    s1 = np.asarray(sigma_current, dtype=float)
    s2 = np.asarray(sigma_desired, dtype=float)

    s1_sq = np.dot(s1, s1)
    s2_sq = np.dot(s2, s2)
    s1_dot_s2 = np.dot(s1, s2)

    denom = 1.0 + s1_sq * s2_sq + 2.0 * s1_dot_s2
    if abs(denom) < 1e-15:
        return np.zeros(3)

    num = ((1.0 - s2_sq) * s1 - (1.0 - s1_sq) * s2 + 2.0 * np.cross(s1, s2))

    sigma_err = num / denom

    # Switch to shadow set if |sigma| > 1 (MRP singularity avoidance)
    if np.dot(sigma_err, sigma_err) > 1.0:
        sigma_err = -sigma_err / np.dot(sigma_err, sigma_err)

    return sigma_err


def mrp_to_dcm(sigma: np.ndarray) -> np.ndarray:
    """Convert MRP to Direction Cosine Matrix (rotation matrix).

    Reference: Schaub & Junkins (2018) Eq. (3.153).
    """
    s = np.asarray(sigma, dtype=float)
    s_sq = np.dot(s, s)

    s_tilde = np.array([
        [0, -s[2], s[1]],
        [s[2], 0, -s[0]],
        [-s[1], s[0], 0],
    ])

    C = np.eye(3) + (8.0 * s_tilde @ s_tilde - 4.0 * (1.0 - s_sq) * s_tilde) / (1.0 + s_sq) ** 2

    return C


def mrp_kinematics(sigma: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """Compute MRP kinematic differential equation: dsigma/dt = B(sigma) * omega / 4.

    Reference: Schaub & Junkins (2018) Eq. (3.156).
    """
    s = np.asarray(sigma, dtype=float)
    s_sq = np.dot(s, s)

    s_tilde = np.array([
        [0, -s[2], s[1]],
        [s[2], 0, -s[0]],
        [-s[1], s[0], 0],
    ])

    B = ((1.0 - s_sq) * np.eye(3) + 2.0 * s_tilde + 2.0 * np.outer(s, s))
    return 0.25 * B @ omega


def propagate_attitude(
    sigma: np.ndarray,
    omega: np.ndarray,
    inertia: np.ndarray,
    torque: np.ndarray,
    dt: float,
    damping_matrix: Optional[np.ndarray] = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Propagate attitude state forward by dt using RK4.

    Integrates both Euler's equation (omega dynamics) and MRP kinematics.
    Structural damping is modelled as a viscous term −C·ω added to Euler's
    equation (Rayleigh damping; Meirovitch 1967, Sec. 6.4).

    Args:
        sigma: (3,) current MRP
        omega: (3,) current angular velocity [rad/s]
        inertia: (3,3) inertia tensor [kg*m²]
        torque: (3,) applied torque [N*m]
        dt: timestep [s]
        damping_matrix: (3,3) structural damping matrix C [N*m*s/rad].
            None → no structural damping (pure rigid body).

    Returns:
        (sigma_new, omega_new)

    Reference: Meirovitch, L. (1967). "Analytical Methods in Vibrations."
        Macmillan, §6.4 (viscous damping in rigid-body equations).
    """
    I = inertia
    I_inv = np.linalg.inv(I)
    C = damping_matrix  # may be None

    def derivs(s, w):
        ds = mrp_kinematics(s, w)
        gyro = np.cross(w, I @ w)
        damp = C @ w if C is not None else np.zeros(3)
        dw = I_inv @ (torque - gyro - damp)
        return ds, dw

    # RK4
    ds1, dw1 = derivs(sigma, omega)
    ds2, dw2 = derivs(sigma + 0.5 * dt * ds1, omega + 0.5 * dt * dw1)
    ds3, dw3 = derivs(sigma + 0.5 * dt * ds2, omega + 0.5 * dt * dw2)
    ds4, dw4 = derivs(sigma + dt * ds3, omega + dt * dw3)

    sigma_new = sigma + dt / 6.0 * (ds1 + 2 * ds2 + 2 * ds3 + ds4)
    omega_new = omega + dt / 6.0 * (dw1 + 2 * dw2 + 2 * dw3 + dw4)

    # Shadow set switching
    if np.dot(sigma_new, sigma_new) > 1.0:
        sigma_new = -sigma_new / np.dot(sigma_new, sigma_new)

    return sigma_new, omega_new


def tune_gains(
    inertia: np.ndarray,
    settling_time_s: float = 60.0,
    damping_ratio: float = 0.7,
) -> tuple[float, float, float]:
    """Compute MRP feedback gains from spacecraft inertia and desired response.

    Uses second-order linear approximation: the MRP feedback law near
    the origin behaves like a damped harmonic oscillator with
    natural frequency wn and damping ratio zeta.

    Args:
        inertia: (3,3) or (3,) inertia tensor/principal moments [kg*m²]
        settling_time_s: desired 2% settling time [s]
        damping_ratio: desired damping ratio (0.7 = critically damped response)

    Returns:
        (K, P, Ki) — proportional, rate, and integral gains

    Reference: Schaub & Junkins (2018) §8.6.2 gain selection guidelines.
    """
    if inertia.ndim == 2:
        J = np.max(np.diag(inertia))  # use largest principal moment
    else:
        J = np.max(inertia)

    # Natural frequency from settling time: wn ≈ 4 / (zeta * t_s)
    wn = 4.0 / (damping_ratio * settling_time_s)

    # From linearized MRP dynamics near origin:
    # K = wn² * J  (proportional, units: N·m)
    # P = 2 * zeta * wn * J  (rate, units: N·m·s)
    K = wn ** 2 * J
    P = 2.0 * damping_ratio * wn * J

    # Integral gain: typically small, ~0.01 * K
    Ki = 0.01 * K / P if P > 0 else 0.0

    return K, P, Ki
