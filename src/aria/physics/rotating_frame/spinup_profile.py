"""Cosine-smoothed spin-up profile (§4.5 of C1 scope).

A linear spin-up ramp `ω(t) = (ω_design / T_ramp) · t` has a step in
angular acceleration `α` at both ends, producing impulsive Euler
jerks that are painful for crew inner ears. The standard choice is
the raised-cosine profile (Clark 1999 NASA/CR-1999-209574 §4.2):

    ω(t) = (ω_design / 2) · [1 − cos(π t / T_ramp)]    [rad/s]
    α(t) = (ω_design / 2) · (π / T_ramp) · sin(π t / T_ramp)

which starts and ends with `α = 0`, peaks at `t = T_ramp / 2`, and
reaches the target `ω_design` smoothly at `t = T_ramp`. The peak
angular acceleration is

    α_peak = (π / 2) · ω_design / T_ramp               [rad/s²]

Design constraint (Young 2019 Aviat Space Environ Med 90(6) 574–584
"Adaptation thresholds"): naive crew head-angular-acceleration limit
is 0.04 rad/s², adapted crew limit 0.10 rad/s². The minimum ramp
time is therefore

    T_ramp ≥ (π / 2) · ω_design / α_max               [s]

This module provides both the profile and the minimum-ramp closed form.
"""

from __future__ import annotations

import math


def cosine_spinup_profile(
    time_s: float,
    omega_target_rad_s: float,
    ramp_duration_s: float,
) -> tuple[float, float]:
    """Evaluate the cosine-smoothed spin-up profile at time ``t``.

    Args:
        time_s: elapsed time since ramp start (s). Values outside
            ``[0, ramp_duration_s]`` are clamped: before the ramp
            `(ω, α) = (0, 0)`; after it `(ω_target, 0)`.
        omega_target_rad_s: design angular speed at the end of the
            ramp (rad/s).
        ramp_duration_s: total ramp time `T_ramp` (s). Must be
            strictly positive.

    Returns:
        ``(omega_t, alpha_t)`` — (rad/s, rad/s²) tuple.
    """
    if ramp_duration_s <= 0.0:
        raise ValueError("ramp_duration_s must be positive")
    if omega_target_rad_s < 0.0:
        raise ValueError("omega_target_rad_s must be non-negative")
    if time_s <= 0.0:
        return 0.0, 0.0
    if time_s >= ramp_duration_s:
        return omega_target_rad_s, 0.0
    phase = math.pi * time_s / ramp_duration_s
    omega = 0.5 * omega_target_rad_s * (1.0 - math.cos(phase))
    alpha = 0.5 * omega_target_rad_s * (math.pi / ramp_duration_s) * math.sin(phase)
    return omega, alpha


def cosine_spinup_peak_alpha(
    omega_target_rad_s: float, ramp_duration_s: float
) -> float:
    """Peak angular acceleration during a cosine-smoothed spin-up.

    α_peak = (π / 2) · ω_target / T_ramp                [rad/s²]

    This is also the value at `t = T_ramp / 2` of
    ``cosine_spinup_profile``.
    """
    if ramp_duration_s <= 0.0:
        raise ValueError("ramp_duration_s must be positive")
    if omega_target_rad_s < 0.0:
        raise ValueError("omega_target_rad_s must be non-negative")
    return 0.5 * math.pi * omega_target_rad_s / ramp_duration_s


def cosine_spinup_min_ramp_time(
    omega_target_rad_s: float, alpha_max_rad_s2: float
) -> float:
    """Minimum ramp duration `T_ramp ≥ (π/2) · ω_target / α_max`.

    Args:
        omega_target_rad_s: design angular speed (rad/s).
        alpha_max_rad_s2: maximum allowable angular acceleration
            (rad/s²). For naive crew use 0.04 (Young 2019); for
            adapted crew use 0.10 (Clark 1999 Table 3).

    Returns:
        Minimum ramp duration in seconds.
    """
    if omega_target_rad_s <= 0.0:
        raise ValueError("omega_target_rad_s must be positive")
    if alpha_max_rad_s2 <= 0.0:
        raise ValueError("alpha_max_rad_s2 must be positive")
    return 0.5 * math.pi * omega_target_rad_s / alpha_max_rad_s2
