"""Dual-spin bus + ring dynamics (§4.1, §4.2 of C4 scope).

Wertz 1978 *Spacecraft Attitude Determination and Control* §16 treats
a spacecraft with an internal momentum rotor as the archetype of
"dual-spin" stability. The total angular momentum in the bus frame is

    L_total = I_bus · Ω_bus + I_∥ ω_rel ê_spin + Σ h_CMG_i     [kg·m²/s]

and when the bus slews at Ω_bus the ring exerts a reaction (gyroscopic)
torque

    τ_gyro = Ω_bus × L_ring = I_∥ ω_rel (Ω_bus × ê_spin)       [N·m]

(Wie 1998 §7.3). For a symmetric bus with moments (I₁, I₁, I₃) spun
at ω_3 about the symmetry axis, the free-nutation angular frequency
(no rotor, no external torque) is

    ω_nut = |(I₃ − I₁)/I₁| · ω_3                              [rad/s]

(Goldstein et al. 2002 *Classical Mechanics* 3rd ed §5.7).
"""

from __future__ import annotations

import numpy as np


def dual_spin_total_angular_momentum(
    bus_inertia_tensor_kg_m2: np.ndarray,
    bus_angular_velocity_rad_s: np.ndarray,
    ring_inertia_parallel_kg_m2: float,
    ring_spin_rate_rad_s: float,
    ring_spin_axis_bus_frame: np.ndarray,
    cmg_momentum_bus_frame: np.ndarray | None = None,
) -> np.ndarray:
    """Return L_total in the bus frame (Wertz 1978 eq. 16.1).

    Args:
        bus_inertia_tensor_kg_m2: 3×3 inertia tensor of the bus (ring
            locked) in the bus frame.
        bus_angular_velocity_rad_s: Ω_bus in the bus frame (3,).
        ring_inertia_parallel_kg_m2: I_∥ (about the ring spin axis).
        ring_spin_rate_rad_s: ω_rel of the ring relative to the bus.
        ring_spin_axis_bus_frame: unit vector ê_spin in the bus frame.
        cmg_momentum_bus_frame: Σ h_CMG_i in the bus frame (3,) or
            None to omit.

    Returns:
        L_total (3,) in kg·m²/s.
    """
    i_bus = np.asarray(bus_inertia_tensor_kg_m2, dtype=float)
    omega = np.asarray(bus_angular_velocity_rad_s, dtype=float)
    e_spin = np.asarray(ring_spin_axis_bus_frame, dtype=float)
    if i_bus.shape != (3, 3):
        raise ValueError("bus_inertia_tensor_kg_m2 must be 3x3")
    if omega.shape != (3,):
        raise ValueError("bus_angular_velocity_rad_s must be (3,)")
    if e_spin.shape != (3,):
        raise ValueError("ring_spin_axis_bus_frame must be (3,)")
    norm = float(np.linalg.norm(e_spin))
    if norm == 0.0:
        raise ValueError("ring_spin_axis_bus_frame must be nonzero")
    e_hat = e_spin / norm
    l_total = i_bus @ omega + ring_inertia_parallel_kg_m2 * ring_spin_rate_rad_s * e_hat
    if cmg_momentum_bus_frame is not None:
        h_cmg = np.asarray(cmg_momentum_bus_frame, dtype=float)
        if h_cmg.shape != (3,):
            raise ValueError("cmg_momentum_bus_frame must be (3,)")
        l_total = l_total + h_cmg
    return l_total


def gyroscopic_reaction_torque(
    bus_angular_velocity_rad_s: np.ndarray,
    ring_angular_momentum_bus_frame: np.ndarray,
) -> np.ndarray:
    """τ_gyro = Ω_bus × L_ring                                 [N·m].

    Wie 1998 §7.3. Points perpendicular to both the slew axis and
    the ring spin axis.

    Canonical C4 check: I_∥ = 2.35e9 kg·m², ω_rel = 0.4189 rad/s
    (→ |L_ring| = 9.84e8), Ω_bus = 1e-3 rad/s perpendicular to ê_spin
    → |τ_gyro| ≈ 9.84e5 N·m.
    """
    omega = np.asarray(bus_angular_velocity_rad_s, dtype=float)
    l_ring = np.asarray(ring_angular_momentum_bus_frame, dtype=float)
    if omega.shape != (3,) or l_ring.shape != (3,):
        raise ValueError("inputs must be (3,)")
    return np.cross(omega, l_ring)


def wertz_nutation_frequency(
    transverse_moment_kg_m2: float,
    spin_moment_kg_m2: float,
    spin_rate_rad_s: float,
) -> float:
    """Free-torque nutation frequency of a symmetric rigid body.

    ω_nut = |(I_s − I_t)/I_t| · ω_spin                        [rad/s]

    (Goldstein 2002 §5.7; Wertz 1978 eq. 16.3.) For an oblate body
    (I_s > I_t) the motion is prograde; for a prolate body
    (I_s < I_t) retrograde. The returned value is the magnitude.
    """
    if transverse_moment_kg_m2 <= 0.0:
        raise ValueError("transverse_moment_kg_m2 must be positive")
    if spin_moment_kg_m2 <= 0.0:
        raise ValueError("spin_moment_kg_m2 must be positive")
    return (
        abs(spin_moment_kg_m2 - transverse_moment_kg_m2)
        / transverse_moment_kg_m2
        * abs(spin_rate_rad_s)
    )
