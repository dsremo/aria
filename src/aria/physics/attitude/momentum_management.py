"""CMG momentum management and RCS desaturation (§4.4 of C4 scope).

When |h_stack| approaches h_max the cluster loses torque authority and
must be "unloaded" by an external torque. The standard trigger, used
on ISS, is 80 % of h_max (Wie 1998 §7.4.4). The RCS impulse required
to bring the stack to zero is simply the magnitude of h_stack divided
by the moment arm of the thruster pair; because the RCS geometry is
mission-specific, this module returns the raw impulse `|h_stack|`
in N·m·s and leaves moment-arm conversion to the propulsion pod.
"""

from __future__ import annotations

import numpy as np

# Wie 1998 §7.4.4 / ISS operational practice.
CMG_DESAT_TRIGGER_FRACTION: float = 0.80


def is_cmg_saturation_imminent(
    cluster_momentum_n_m_s: np.ndarray,
    h_max_n_m_s: float,
    trigger_fraction: float = CMG_DESAT_TRIGGER_FRACTION,
) -> bool:
    """Return True iff |h_stack| ≥ trigger_fraction · h_max."""
    if h_max_n_m_s <= 0.0:
        raise ValueError("h_max_n_m_s must be positive")
    if not (0.0 < trigger_fraction <= 1.0):
        raise ValueError("trigger_fraction must be in (0, 1]")
    magnitude = float(np.linalg.norm(np.asarray(cluster_momentum_n_m_s)))
    return magnitude >= trigger_fraction * h_max_n_m_s


def rcs_desat_impulse_required(
    cluster_momentum_n_m_s: np.ndarray,
    moment_arm_m: float = 1.0,
) -> float:
    """Total RCS impulse magnitude (N·s) to null the cluster momentum.

    |F Δt| = |h_stack| / r_arm                                [N·s]

    Args:
        cluster_momentum_n_m_s: h_stack (3,) in the bus frame.
        moment_arm_m: effective thruster moment arm (m, positive).
            Defaults to 1 m — callers with real ship geometry must
            pass the correct value.

    Returns:
        Required RCS impulse in N·s.
    """
    if moment_arm_m <= 0.0:
        raise ValueError("moment_arm_m must be positive")
    h_mag = float(np.linalg.norm(np.asarray(cluster_momentum_n_m_s)))
    return h_mag / moment_arm_m
