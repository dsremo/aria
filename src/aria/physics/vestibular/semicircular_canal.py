"""Semicircular canal — torsion-pendulum model (§4.1 of C2 scope).

Each of the three semicircular canals (anterior, posterior, horizontal)
acts as a fluid-filled torus whose endolymph rotates relative to the
canal wall under applied head angular acceleration. The cupula is an
elastic diaphragm whose deflection ξ obeys the classical Steinhausen
1933 torsion-pendulum equation as systematized by Van Egmond, Groen,
and Jongkees 1949 *J Physiology* 110(1) 1-17 (eq. 4):

    Θ ξ̈ + Π ξ̇ + Δ ξ = Θ α_h(t)                          [N·m]

where
    Θ  = effective endolymph moment of inertia        (kg·m²)
    Π  = viscous damping coefficient                   (N·m·s)
    Δ  = cupular elastic restoring stiffness          (N·m)
    α_h = head angular acceleration along canal axis  (rad/s²)

Defining the two canonical time constants
    T_1 = Π / Δ        (long, ~10 s — cupula restoration)
    T_2 = Θ / Π        (short, ~3 ms — endolymph inertia)
the equation reduces to

    ξ̈ + (1/T_2) ξ̇ + 1/(T_1 T_2) ξ = α_h(t)              [rad/s²]

In the physiologically relevant frequency band (0.1-5 Hz),
T_2 ≪ T_1, so the canal behaves as a band-pass *rate sensor*
with transfer function (Benson 2002 Ernsting's Aviation Medicine
Ch. 17 eq. 17.3, ISBN 978-0340764787):

    H(s) = Ξ(s) / Ω_h(s) = T_1 s / [(1 + T_1 s)(1 + T_2 s)]

The amplitude response is

    |H(jω)| = T_1 ω / sqrt[(1 + (T_1 ω)²)(1 + (T_2 ω)²)]

Canonical human values from Benson 2002 Table 17.2:
    T_1 ≈ 10 s
    T_2 ≈ 0.003 s

For a step in head angular velocity ω_0 (constant after t = 0),
the cupula displacement (in equivalent angular units, rad) is the
inverse Laplace of (ω_0/s) · H(s):

    ξ(t) = ω_0 · [exp(−t/T_1) − exp(−t/T_2)] / (1 − T_2/T_1)

For T_2 ≪ T_1 the second exponential decays in milliseconds and
the response simplifies to ξ(t) ≈ ω_0 · exp(−t/T_1), which is
why the canal "forgets" sustained rotation after a few T_1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SemicircularCanalConstants:
    """Canonical canal time constants per Benson 2002 Table 17.2.

    Attributes:
        T_1_s: long time constant (cupula restoration), ≈ 10 s.
        T_2_s: short time constant (endolymph inertia), ≈ 3 ms.
    """

    # Benson 2002 Ernsting's Aviation Medicine Ch.17 Table 17.2
    T_1_s: float = 10.0
    T_2_s: float = 3.0e-3


HUMAN_CANAL_CONSTANTS: SemicircularCanalConstants = SemicircularCanalConstants()


def canal_transfer_function_amplitude(
    angular_frequency_rad_s: float,
    constants: SemicircularCanalConstants = HUMAN_CANAL_CONSTANTS,
) -> float:
    """Amplitude `|H(jω)|` of the canal transfer function (rate sensor).

    |H(jω)| = T_1 ω / sqrt[(1 + (T_1 ω)²)(1 + (T_2 ω)²)]

    Args:
        angular_frequency_rad_s: ω in rad/s. Non-negative.
        constants: canal time constants (default: human).

    Returns:
        Dimensionless |H(jω)|. Maximum is achieved at the geometric
        mean of 1/T_1 and 1/T_2.
    """
    if angular_frequency_rad_s < 0.0:
        raise ValueError("angular_frequency_rad_s must be non-negative")
    if angular_frequency_rad_s == 0.0:
        return 0.0
    w = angular_frequency_rad_s
    t1 = constants.T_1_s
    t2 = constants.T_2_s
    num = t1 * w
    denom = math.sqrt((1.0 + (t1 * w) ** 2) * (1.0 + (t2 * w) ** 2))
    return num / denom


def cupula_step_response(
    time_s: float,
    omega_step_rad_s: float,
    constants: SemicircularCanalConstants = HUMAN_CANAL_CONSTANTS,
) -> float:
    """Cupula deflection (rad-equivalent) at time `t` after a step
    change in head angular velocity to `ω_step` at t = 0.

    Closed-form analytic solution of the torsion-pendulum equation
    with Heaviside input:

        ξ(t) = ω_step · [exp(−t/T_1) − exp(−t/T_2)] / (1 − T_2/T_1)

    For T_2 ≪ T_1 (the human case) and t ≫ T_2, this simplifies to
    ξ(t) ≈ ω_step · exp(−t/T_1) — the long exponential decay that
    causes pilots to "forget" sustained rotation.

    Args:
        time_s: time since step (s). Negative t returns 0 by causality.
        omega_step_rad_s: step amplitude in head angular velocity (rad/s).
        constants: canal time constants.

    Returns:
        Cupula deflection in the same angular units as ω_step.
        At t = 0 the response is 0; rises to peak ω_step on a
        T_2 timescale; decays back to 0 on a T_1 timescale.
    """
    if time_s < 0.0:
        return 0.0
    t1 = constants.T_1_s
    t2 = constants.T_2_s
    if t1 == t2:
        # Degenerate case: a critically damped pendulum.
        return omega_step_rad_s * (time_s / t1) * math.exp(-time_s / t1)
    return omega_step_rad_s * (
        math.exp(-time_s / t1) - math.exp(-time_s / t2)
    ) / (1.0 - t2 / t1)
