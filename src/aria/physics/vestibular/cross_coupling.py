"""Cross-coupled angular acceleration in a rotating habitat
(§4.3 of C2 scope).

When a crew member tilts their head while the habitat ring is
spinning, the cross product of the ring angular velocity and the
voluntary head angular velocity produces an apparent angular
acceleration about a third axis (orthogonal to both):

    α_cross = Ω_ring × ω_head_tilt                       [rad/s²]

This is the source of the **Coriolis illusion** (Guedry & Benson
1978 *Aviation Space Environ Med* 49(1) 29-35). The semicircular
canals along the third axis register a real angular acceleration
that has no corresponding visual or proprioceptive cue, producing
a vivid sensation of tumbling that is the dominant cause of
motion sickness in rotating spacecraft.

Magnitude for the canonical 4 rpm habitat (`|Ω_ring| = 0.4189
rad/s`) and a moderate-rate head tilt (`|ω_tilt| = 1 rad/s`)
about an orthogonal axis:

    |α_cross| = 0.4189 · 1 ≈ 0.42 rad/s²

The NASA Slow-Rotating Chair (SDTC = Space Disorientation Training
Chair) data (Young 1986 NASA TM-88328) show that sustained
|α_cross| above ~0.1 rad/s² produces overt motion sickness in
50% of naive subjects within 10 minutes when the platform rotates
at ≥5 rpm. Adapted crew can tolerate ~0.2-0.3 rad/s².
"""

from __future__ import annotations

import numpy as np


def cross_coupled_angular_acceleration(
    omega_ring_rad_s: np.ndarray,
    omega_head_tilt_rad_s: np.ndarray,
) -> np.ndarray:
    """Coriolis-illusion angular acceleration `Ω_ring × ω_head` [rad/s²].

    Args:
        omega_ring_rad_s: (3,) ring angular-velocity vector in the
            ship frame (rad/s).
        omega_head_tilt_rad_s: (3,) crew head angular-velocity vector
            in the deck frame, expressed in the same basis as the
            ring vector (rad/s).

    Returns:
        (3,) cross-coupled angular acceleration vector in rad/s².
        The magnitude is what the Oman 1990 dose model uses as input
        to the sensory-conflict integrator.
    """
    Omega = np.asarray(omega_ring_rad_s, dtype=float).reshape(3)
    omega_h = np.asarray(omega_head_tilt_rad_s, dtype=float).reshape(3)
    return np.cross(Omega, omega_h)
