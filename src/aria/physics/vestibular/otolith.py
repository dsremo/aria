"""Otolith organs — first-order overdamped response (§4.4 of C2 scope).

The utricle and saccule sense the specific gravito-inertial force
per unit mass (Grant & Best 1987 *Neuroscience* 23(2) 379-389):

    f_GIA = g_real − a_rot                               [m/s²]

where g_real is the local gravitational acceleration (negligible
inside an interstellar ship far from any star) and a_rot is the
rotating-frame acceleration sum from C1 (centrifugal + Coriolis +
Euler).

Otolith macular displacement δ obeys an overdamped first-order
system whose dynamics are dominated by the viscous coupling between
the otoconial mass and the gel layer:

    T_oto · δ̇ + δ = k_oto · f_GIA                        [m]

with T_oto ≈ 0.08 s (Grant & Best 1987 §3.2 figure 4) and k_oto a
unit-calibrated displacement gain. The 80 ms time constant means
the otoliths track quasi-static changes in effective gravity
(habitat spin-up, sustained centrifugal load) faithfully but
slightly attenuate frequencies above ~2 Hz.

For our purposes the steady-state response (the displacement
proportional to the input GIA vector) is the primary observable,
and the time-domain step response provides the transient.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class OtolithConstants:
    """Otolith first-order constants per Grant & Best 1987.

    Attributes:
        T_oto_s: time constant (s). Grant & Best 1987 §3.2 fig 4.
        k_oto_m_per_m_s2: displacement gain (m / (m/s²)). Calibrated
            so a unit GIA produces a unit response in the model
            output. The absolute scale is rarely used; only ratios
            and time evolution matter for the sensory-conflict path.
    """

    T_oto_s: float = 0.08  # Grant & Best 1987 §3.2
    k_oto_m_per_m_s2: float = 1.0  # unit-calibrated


OTOLITH_DEFAULT_CONSTANTS: OtolithConstants = OtolithConstants()


def otolith_response_steady_state(
    f_gia_m_s2: np.ndarray,
    constants: OtolithConstants = OTOLITH_DEFAULT_CONSTANTS,
) -> np.ndarray:
    """Steady-state otolith displacement vector under a constant GIA
    input.

    δ_∞ = k_oto · f_GIA                                  [m]

    Args:
        f_gia_m_s2: (3,) gravito-inertial force per unit mass (m/s²).
        constants: otolith time and gain constants.

    Returns:
        (3,) steady-state displacement vector (m).
    """
    f = np.asarray(f_gia_m_s2, dtype=float).reshape(3)
    return constants.k_oto_m_per_m_s2 * f


def otolith_step_response(
    time_s: float,
    step_f_gia_m_s2: np.ndarray,
    constants: OtolithConstants = OTOLITH_DEFAULT_CONSTANTS,
) -> np.ndarray:
    """Time-domain response to a step in the GIA vector at t = 0.

    For the first-order ODE `T δ̇ + δ = k f`, the closed-form step
    response is

        δ(t) = k f · (1 − exp(−t / T))                   [m]

    rising from 0 toward the steady state on a T_oto timescale.

    Args:
        time_s: elapsed time since the step (s). Negative t returns 0.
        step_f_gia_m_s2: (3,) constant GIA after the step (m/s²).
        constants: otolith parameters.

    Returns:
        (3,) displacement vector at time t.
    """
    f = np.asarray(step_f_gia_m_s2, dtype=float).reshape(3)
    if time_s <= 0.0:
        return np.zeros(3)
    return (
        constants.k_oto_m_per_m_s2
        * f
        * (1.0 - math.exp(-time_s / constants.T_oto_s))
    )
