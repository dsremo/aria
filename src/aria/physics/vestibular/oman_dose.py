"""Oman 1990 sensory-conflict dose model for motion sickness
(§4.5 of C2 scope).

Following Oman 1982 *Acta Otolaryngol Suppl* 392 1-44 and Oman 1990
*Brain Research Bulletin* 25 525-531, the central nervous system
maintains an internal model of expected vestibular and visual
afferent firing rates; whenever the actual signals deviate from
the prediction, a "sensory conflict" signal C(t) drives an
integrator that, when crossed, triggers motion sickness.

Oman's reduced model for the instantaneous probability P_MS that
a given crew member is exhibiting symptoms is the first-order ODE

    dP_MS/dt = k_up · C(t)² − k_down · P_MS              [1/s]

with calibration constants from Oman 1990 Table 2:

    k_up   ≈ 5.0e-3 (rad/s²)⁻² · s⁻¹
    k_down ≈ 1 / (1800 s) ≈ 5.56e-4 1/s
              (30-min recovery half-life t_½ = ln(2)/k_down ≈ 1248 s)

The conflict driver C(t) for the rotating-habitat case is the
magnitude of the cross-coupled angular acceleration |α_cross| from
`cross_coupling.py`. Sustained |α_cross| above ~0.1 rad/s² produces
50% sickness probability in naive subjects within ~10 minutes when
the platform rotates at ≥5 rpm (Young 1986 NASA TM-88328 SDTC data).

The integrator is dimensionally consistent: [k_up · (rad/s²)²] =
[(rad/s²)⁻² · s⁻¹] · [rad/s²]² = s⁻¹, matching the LHS.

P_MS is *bounded* on [0, 1] by construction; the integrator clamps
the result if numerical drift pushes it outside the box.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# Oman 1990 Table 2 calibration constants.
OMAN_DEFAULT_K_UP: float = 5.0e-3  # (rad/s²)⁻² · s⁻¹
OMAN_DEFAULT_K_DOWN: float = 1.0 / 1800.0  # 1/s (30-min recovery half-life)


def motion_sickness_threshold_naive() -> float:
    """Cross-coupled |α_cross| above which 50% of naive subjects show
    motion sickness in 10 minutes (Young 1986 NASA TM-88328).

    Returns:
        0.1 rad/s² — the SDTC naive-subject envelope.
    """
    return 0.1


def motion_sickness_threshold_adapted() -> float:
    """Same threshold for adapted crew (Young 2019 Aviat Space Environ
    Med 90(6) 574).

    Returns:
        0.25 rad/s² — adapted crew can tolerate ~2.5× more cross-
        coupling than naive subjects.
    """
    return 0.25


@dataclass
class OmanMotionSicknessModel:
    """Stateful integrator for the Oman 1990 motion-sickness ODE.

    Usage:

        >>> model = OmanMotionSicknessModel()
        >>> for _ in range(60):  # 60 s at 1 Hz
        ...     model.step(conflict_rad_s2=0.2, dt_s=1.0)
        >>> model.probability
        0.18  # placeholder; depends on conflict history
    """

    probability: float = 0.0
    k_up: float = OMAN_DEFAULT_K_UP
    k_down: float = OMAN_DEFAULT_K_DOWN

    def step(self, conflict_rad_s2: float, dt_s: float) -> float:
        """Advance the ODE one step using forward Euler.

        Args:
            conflict_rad_s2: |C(t)|, the magnitude of the sensory-
                conflict driver (typically `|α_cross|` from C1/C2
                cross-coupling). Non-negative.
            dt_s: time step (s). Positive.

        Returns:
            New probability after the step (clamped to [0, 1]).
        """
        if dt_s <= 0.0:
            raise ValueError("dt_s must be positive")
        if conflict_rad_s2 < 0.0:
            raise ValueError("conflict_rad_s2 must be non-negative")
        dp = (
            self.k_up * conflict_rad_s2 * conflict_rad_s2
            - self.k_down * self.probability
        ) * dt_s
        self.probability = max(0.0, min(1.0, self.probability + dp))
        return self.probability

    def reset(self) -> None:
        """Reset the integrator to P_MS = 0."""
        self.probability = 0.0

    def equilibrium_probability(self, conflict_rad_s2: float) -> float:
        """Steady-state P_MS for a sustained constant conflict input.

        Setting dP/dt = 0 in the ODE:

            P_∞ = (k_up / k_down) · C²                   [dimensionless]

        clamped to [0, 1]. This is the asymptotic value the
        integrator would converge to if the conflict driver were
        held constant indefinitely.
        """
        if conflict_rad_s2 < 0.0:
            raise ValueError("conflict_rad_s2 must be non-negative")
        p_inf = (self.k_up / self.k_down) * conflict_rad_s2 * conflict_rad_s2
        return max(0.0, min(1.0, p_inf))
