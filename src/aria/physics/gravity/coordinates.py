"""Coordinate transformations for N-body systems.

Provides conversions between four coordinate systems used in
celestial mechanics:

1. **Inertial (barycentric)**: Standard — all positions/velocities
   relative to the system barycenter.
2. **Heliocentric**: Positions relative to the central body (star/Sun).
   Used by WHFast and most propagators.
3. **Jacobi**: Hierarchical — each body referenced to the center of mass
   of all interior bodies. Required by proper symplectic integrators.
4. **Democratic heliocentric**: Positions heliocentric, velocities
   barycentric. Used by the MERCURY integrator (Chambers 1999).

Algorithm approaches studied from Rebound transformations.c (GPL,
clean-room reimplemented from Duncan, Levison & Lee 1998 AJ 116 2067
and Wisdom & Holman 1991 AJ 102 1528).

References:
    Duncan, M.J., Levison, H.F. & Lee, M.H. (1998).
    "A Multiple Time Step Symplectic Algorithm for Integrating Close
    Encounters." AJ, 116(4), 2067-2077.

    Wisdom, J. & Holman, M. (1991). "Symplectic maps for the N-body
    problem." AJ, 102, 1528-1538.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np


def inertial_to_heliocentric(
    positions: np.ndarray,
    velocities: np.ndarray,
    masses: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert from barycentric to heliocentric coordinates.

    Args:
        positions: (N, 3) barycentric positions
        velocities: (N, 3) barycentric velocities
        masses: (N,) particle masses (index 0 = central body)

    Returns:
        (positions_helio, velocities_helio) — both (N, 3)
        Central body (index 0) will be at origin.
    """
    pos_helio = positions - positions[0]
    vel_helio = velocities - velocities[0]
    return pos_helio, vel_helio


def heliocentric_to_inertial(
    positions: np.ndarray,
    velocities: np.ndarray,
    masses: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert from heliocentric to barycentric coordinates.

    Computes the barycenter from heliocentric positions and masses,
    then shifts all particles so the barycenter is at origin.
    """
    N = len(masses)
    M_total = np.sum(masses)

    # Barycenter in heliocentric coords
    com_pos = np.zeros(3)
    com_vel = np.zeros(3)
    for i in range(N):
        com_pos += masses[i] * positions[i]
        com_vel += masses[i] * velocities[i]
    com_pos /= M_total
    com_vel /= M_total

    pos_bary = positions - com_pos
    vel_bary = velocities - com_vel
    return pos_bary, vel_bary


def inertial_to_jacobi(
    positions: np.ndarray,
    velocities: np.ndarray,
    masses: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert from barycentric to Jacobi coordinates.

    Jacobi coordinates reference each body to the center of mass of
    all interior bodies. This is the natural coordinate system for
    the Wisdom-Holman symplectic integrator.

    Body 0: position of the central body (unchanged)
    Body i (i>0): position relative to COM of bodies 0..i-1

    Reference: Wisdom & Holman 1991, Eq. (1)-(3).
    """
    N = len(masses)
    pos_jac = np.zeros_like(positions)
    vel_jac = np.zeros_like(velocities)

    # Body 0: same as barycentric (or set to COM = 0)
    pos_jac[0] = positions[0].copy()
    vel_jac[0] = velocities[0].copy()

    # Running center of mass of bodies 0..i-1
    com_pos = masses[0] * positions[0]
    com_vel = masses[0] * velocities[0]
    m_interior = masses[0]

    for i in range(1, N):
        # Jacobi position: relative to COM of interior bodies
        pos_jac[i] = positions[i] - com_pos / m_interior
        vel_jac[i] = velocities[i] - com_vel / m_interior

        # Update running COM
        com_pos += masses[i] * positions[i]
        com_vel += masses[i] * velocities[i]
        m_interior += masses[i]

    return pos_jac, vel_jac


def jacobi_to_inertial(
    positions: np.ndarray,
    velocities: np.ndarray,
    masses: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert from Jacobi to barycentric coordinates.

    Inverse of inertial_to_jacobi.
    """
    N = len(masses)
    pos_bary = np.zeros_like(positions)
    vel_bary = np.zeros_like(velocities)

    pos_bary[0] = positions[0].copy()
    vel_bary[0] = velocities[0].copy()

    com_pos = masses[0] * pos_bary[0]
    com_vel = masses[0] * vel_bary[0]
    m_interior = masses[0]

    for i in range(1, N):
        # Invert: pos_bary[i] = pos_jac[i] + COM(0..i-1)
        pos_bary[i] = positions[i] + com_pos / m_interior
        vel_bary[i] = velocities[i] + com_vel / m_interior

        com_pos += masses[i] * pos_bary[i]
        com_vel += masses[i] * vel_bary[i]
        m_interior += masses[i]

    return pos_bary, vel_bary


def inertial_to_democratic_heliocentric(
    positions: np.ndarray,
    velocities: np.ndarray,
    masses: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert to democratic heliocentric coordinates.

    Positions: heliocentric (relative to central body)
    Velocities: barycentric (relative to system COM)

    This mixed coordinate system is used by the MERCURY integrator
    (Chambers 1999) and simplifies the Hamiltonian splitting.

    Reference: Duncan, Levison & Lee 1998 AJ 116 2067.
    """
    N = len(masses)
    M_total = np.sum(masses)

    # Positions: heliocentric
    pos_dh = positions - positions[0]

    # Velocities: barycentric (shift to COM frame)
    com_vel = np.zeros(3)
    for i in range(N):
        com_vel += masses[i] * velocities[i]
    com_vel /= M_total

    vel_dh = velocities - com_vel

    return pos_dh, vel_dh


def democratic_heliocentric_to_inertial(
    positions: np.ndarray,
    velocities: np.ndarray,
    masses: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert from democratic heliocentric to barycentric.

    Inverse of inertial_to_democratic_heliocentric.
    """
    N = len(masses)
    M_total = np.sum(masses)

    # Recover heliocentric position of central body from constraint:
    # sum(m_i * r_i_helio) / M_total = -m_0 * r_0_helio / M_total = 0 in bary
    # But we stored positions[0] = 0 (heliocentric), so:
    # r_0_bary = -sum(m_i * positions[i]) / m_0 for i>0
    r0_bary = np.zeros(3)
    for i in range(1, N):
        r0_bary -= masses[i] * positions[i]
    r0_bary /= masses[0]

    pos_bary = np.zeros_like(positions)
    pos_bary[0] = r0_bary
    for i in range(1, N):
        pos_bary[i] = positions[i] + r0_bary

    # Velocities are already barycentric
    vel_bary = velocities.copy()

    return pos_bary, vel_bary


def compute_com(
    positions: np.ndarray, velocities: np.ndarray, masses: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute center of mass position and velocity."""
    M = np.sum(masses)
    com_pos = np.sum(masses[:, None] * positions, axis=0) / M
    com_vel = np.sum(masses[:, None] * velocities, axis=0) / M
    return com_pos, com_vel


def move_to_com(
    positions: np.ndarray, velocities: np.ndarray, masses: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """Shift all particles so the center of mass is at the origin."""
    com_pos, com_vel = compute_com(positions, velocities, masses)
    return positions - com_pos, velocities - com_vel
