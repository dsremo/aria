"""Low-thrust guidance laws for electric propulsion transfers.

Implements optimal low-thrust transfer guidance between circular orbits
using the Edelbaum (1961) / Kechichian (1997) theory. This is the
analytical backbone for ion/Hall-effect thruster mission design.

Also provides a bielliptic three-impulse transfer for when it's
more efficient than Hohmann (r_f/r_i > 11.94).

Algorithms studied from poliastro core/thrust/change_a_inc.py (MIT)
and core/maneuver.py (MIT). Reimplemented for ARIA.

References:
    Edelbaum, T.N. (1961). "Propulsion Requirements for Controllable
    Satellites." ARS Journal, 31(8), 1079-1089.

    Kechichian, J.A. (1997). "Reformulation of Edelbaum's Low-Thrust
    Transfer Problem Using Optimal Control Theory." JGCD, 20(5), 988-994.

    Vallado, D.A. (2013). "Fundamentals of Astrodynamics" 4th ed. §6.3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Tuple

import numpy as np


# ══════════════════════════════════════════════════════════════════
#  Edelbaum low-thrust guidance (a + inclination change)
# ══════════════════════════════════════════════════════════════════

@dataclass
class LowThrustResult:
    """Result of a low-thrust transfer computation."""
    delta_v_ms: float           # Total Δv required [m/s]
    transfer_time_s: float      # Transfer time [seconds]
    initial_yaw_rad: float      # Initial thrust yaw angle β₀ [rad]
    v_circular_initial: float   # Initial circular velocity [m/s]
    v_circular_final: float     # Final circular velocity [m/s]


def edelbaum_transfer(
    mu: float,
    a_initial: float,
    a_final: float,
    inc_initial: float,
    inc_final: float,
    thrust_accel: float,
) -> LowThrustResult:
    """Compute optimal low-thrust transfer between circular inclined orbits.

    Uses the Edelbaum/Kechichian theory for simultaneous semi-major axis
    and inclination change with continuous constant-magnitude thrust.

    Args:
        mu: gravitational parameter [m³/s²]
        a_initial: initial semi-major axis [m]
        a_final: final semi-major axis [m]
        inc_initial: initial inclination [rad]
        inc_final: final inclination [rad]
        thrust_accel: constant thrust acceleration [m/s²]

    Returns:
        LowThrustResult with Δv, transfer time, and yaw schedule.
    """
    v0 = math.sqrt(mu / a_initial)  # initial circular velocity
    vf = math.sqrt(mu / a_final)    # final circular velocity

    delta_i = abs(inc_final - inc_initial)

    # Initial yaw angle (Kechichian 1997 Eq. 15)
    if delta_i < 1e-12:
        beta0 = 0.0
    else:
        beta0 = math.atan2(
            math.sin(math.pi / 2.0 * delta_i),
            v0 / vf - math.cos(math.pi / 2.0 * delta_i),
        )

    # Total Δv (Edelbaum 1961 Eq. 7, Kechichian reformulation)
    if delta_i < 1e-12:
        dv = abs(vf - v0)
    else:
        dv = v0 * math.cos(beta0) - v0 * math.sin(beta0) / math.tan(
            math.pi / 2.0 * delta_i + beta0
        )

    # Transfer time
    t_transfer = abs(dv) / thrust_accel if thrust_accel > 0 else float('inf')

    return LowThrustResult(
        delta_v_ms=abs(dv),
        transfer_time_s=t_transfer,
        initial_yaw_rad=beta0,
        v_circular_initial=v0,
        v_circular_final=vf,
    )


def edelbaum_yaw_angle(
    t: float,
    v0: float,
    thrust_accel: float,
    beta0: float,
) -> float:
    """Compute the optimal yaw angle at time t during an Edelbaum transfer.

    The yaw angle β(t) is the angle between the thrust vector and the
    local velocity direction. Positive β thrusts out-of-plane for
    inclination change.

    Args:
        t: time since transfer start [s]
        v0: initial circular velocity [m/s]
        thrust_accel: constant thrust acceleration [m/s²]
        beta0: initial yaw angle [rad]

    Returns:
        β(t) in radians.
    """
    return math.atan2(
        v0 * math.sin(beta0),
        v0 * math.cos(beta0) - thrust_accel * t,
    )


def edelbaum_accel_vector(
    t: float,
    r: np.ndarray,
    v: np.ndarray,
    v0: float,
    thrust_accel: float,
    beta0: float,
    delta_inc_sign: float = 1.0,
) -> np.ndarray:
    """Compute the acceleration vector for Edelbaum guidance at time t.

    Returns the thrust acceleration in the RTN frame, decomposed into
    tangential (along-velocity) and normal (out-of-plane) components.

    Args:
        t: time since transfer start [s]
        r: position vector [m]
        v: velocity vector [m]
        v0: initial circular velocity [m/s]
        thrust_accel: magnitude of acceleration [m/s²]
        beta0: initial yaw angle [rad]
        delta_inc_sign: +1 for increasing inclination, -1 for decreasing

    Returns:
        (3,) acceleration vector [m/s²]
    """
    beta_t = edelbaum_yaw_angle(t, v0, thrust_accel, beta0)

    # Tangential direction (along velocity)
    v_norm = np.linalg.norm(v)
    if v_norm < 1e-15:
        return np.zeros(3)
    t_hat = v / v_norm

    # Normal direction (orbit normal / out-of-plane)
    h = np.cross(r, v)
    h_norm = np.linalg.norm(h)
    if h_norm < 1e-15:
        return thrust_accel * math.cos(beta_t) * t_hat
    w_hat = h / h_norm

    # Sign of beta depends on direction of inclination change
    beta_signed = beta_t * delta_inc_sign

    return thrust_accel * (math.cos(beta_signed) * t_hat + math.sin(beta_signed) * w_hat)


# ══════════════════════════════════════════════════════════════════
#  Bielliptic transfer (three-impulse)
# ══════════════════════════════════════════════════════════════════

@dataclass
class BiellipticResult:
    """Result of a bielliptic transfer computation."""
    dv1_ms: float    # First burn (raise to intermediate)
    dv2_ms: float    # Second burn (at intermediate apoapsis)
    dv3_ms: float    # Third burn (circularize at final)
    total_dv_ms: float
    tof_s: float     # Total time of flight
    r_intermediate: float  # Intermediate orbit apoapsis [m]


def bielliptic_transfer(
    mu: float,
    r_initial: float,
    r_final: float,
    r_intermediate: float,
) -> BiellipticResult:
    """Three-impulse bielliptic transfer between circular orbits.

    More efficient than Hohmann when r_final/r_initial > 11.94
    (the critical ratio from Vallado 2013 §6.3.2).

    Args:
        mu: gravitational parameter [m³/s²]
        r_initial: initial circular orbit radius [m]
        r_final: final circular orbit radius [m]
        r_intermediate: intermediate apoapsis radius [m] (must be > max(r_i, r_f))

    Returns:
        BiellipticResult with per-burn Δv and total time.

    Reference: Vallado (2013) §6.3.2, Battin (1999) §6.2.
    """
    if r_intermediate <= max(r_initial, r_final):
        raise ValueError("r_intermediate must exceed both r_initial and r_final")

    # Transfer orbit 1: r_initial → r_intermediate
    a1 = (r_initial + r_intermediate) / 2.0
    v_initial = math.sqrt(mu / r_initial)
    v_t1_periapsis = math.sqrt(2.0 * mu * r_intermediate / (r_initial * (r_initial + r_intermediate)))
    dv1 = v_t1_periapsis - v_initial

    # At r_intermediate (apoapsis of transfer 1)
    v_t1_apoapsis = math.sqrt(2.0 * mu * r_initial / (r_intermediate * (r_initial + r_intermediate)))

    # Transfer orbit 2: r_intermediate → r_final
    a2 = (r_intermediate + r_final) / 2.0
    v_t2_apoapsis = math.sqrt(2.0 * mu * r_final / (r_intermediate * (r_intermediate + r_final)))
    dv2 = v_t2_apoapsis - v_t1_apoapsis

    # Circularize at r_final
    v_final = math.sqrt(mu / r_final)
    v_t2_periapsis = math.sqrt(2.0 * mu * r_intermediate / (r_final * (r_intermediate + r_final)))
    dv3 = v_final - v_t2_periapsis

    # Time of flight: half-periods of each transfer ellipse
    tof = math.pi * (math.sqrt(a1 ** 3 / mu) + math.sqrt(a2 ** 3 / mu))

    return BiellipticResult(
        dv1_ms=abs(dv1),
        dv2_ms=abs(dv2),
        dv3_ms=abs(dv3),
        total_dv_ms=abs(dv1) + abs(dv2) + abs(dv3),
        tof_s=tof,
        r_intermediate=r_intermediate,
    )
