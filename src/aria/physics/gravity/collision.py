"""Collision detection and resolution for N-body systems.

Implements swept-sphere (line) collision detection that checks for
overlaps between timesteps, not just at discrete snapshots. This catches
fast-approaching objects that would pass through each other in a
snapshot-only check.

Also provides merge resolution (momentum-conserving coalescence) and
bounce resolution (elastic/inelastic).

Two detection modes:
- detect_collisions_direct(): O(N²) — correct for all distributions, <100 particles
- detect_collisions_tree():   O(N log N) — spatial hash grid, scales to >10000 particles
  Cell size = 2 × (max_radius + max_relative_speed × dt), so only nearby particles
  are checked. Algorithm inspired by Rebound's oct-tree approach (clean-room reimplemented).

Algorithm approach studied from Rebound collision.c (GPL, clean-room
reimplemented from published algorithms):
- Swept-sphere via Hermite interpolation of positions between timesteps
- Minimum separation via quadratic formula on d²(t)

References:
    Chambers, J.E. (1999). "A hybrid symplectic integrator that permits
    close encounters between massive bodies."
    MNRAS, 304(4), 793-799.
    Rein, H. & Papaloizou, J.C.B. (2010). "On the evolution of mean motion
    resonances through stochastic forces." A&A 510, A4. (Rebound paper)
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np


@dataclass
class Particle:
    """A particle with position, velocity, mass, and radius."""
    pos: np.ndarray              # (3,) position [m]
    vel: np.ndarray              # (3,) velocity [m/s]
    mass: float = 1.0            # [kg]
    radius: float = 0.0          # [m] (physical radius for collision)
    name: str = ""
    pos_prev: np.ndarray = field(default_factory=lambda: np.zeros(3))
    vel_prev: np.ndarray = field(default_factory=lambda: np.zeros(3))


@dataclass
class CollisionEvent:
    """A detected collision between two particles."""
    i: int                       # index of particle 1
    j: int                       # index of particle 2
    t_collision: float           # estimated collision time [s]
    min_distance: float          # minimum approach distance [m]
    relative_speed: float        # relative speed at closest approach [m/s]


def detect_collisions_direct(
    particles: List[Particle],
    dt: float,
) -> List[CollisionEvent]:
    """O(N²) direct collision detection using swept-sphere test.

    For each pair of particles, checks if their swept spheres overlap
    during the timestep [t, t+dt]. Uses Hermite interpolation of
    positions to find the minimum separation.

    Args:
        particles: list of Particle objects (with pos, vel, pos_prev, vel_prev)
        dt: timestep [s]

    Returns:
        List of CollisionEvent for all detected collisions.
    """
    n = len(particles)
    events: List[CollisionEvent] = []

    for i in range(n):
        for j in range(i + 1, n):
            event = _check_pair(particles[i], particles[j], i, j, dt)
            if event is not None:
                events.append(event)

    # Sort by collision time (earliest first)
    events.sort(key=lambda e: e.t_collision)
    return events


def detect_collisions_tree(
    particles: List[Particle],
    dt: float,
) -> List[CollisionEvent]:
    """O(N log N) spatial-hash collision detection.

    Partitions space into a uniform grid where the cell size guarantees
    that any pair that could collide during [t, t+dt] is in the same or
    adjacent cells.  Only ~27 neighboring cells need to be searched per
    particle instead of all N.

    Cell size:
        l = 2 × (r_max + v_rel_max × dt)

    where r_max = max particle radius, v_rel_max = max pairwise relative speed
    estimated conservatively as 2 × max(|v_i|).

    Args:
        particles: list of Particle objects
        dt: timestep [s]

    Returns:
        List of CollisionEvent, same as detect_collisions_direct().

    Complexity: O(N × k) average, O(N²) worst-case (all particles in one cell).
    For sparse debris fields k ≈ 1, giving O(N) practical performance.
    """
    n = len(particles)
    if n < 2:
        return []

    # Estimate cell size from maximum interaction radius
    max_radius = max((p.radius for p in particles), default=0.0)
    max_speed = max((float(np.linalg.norm(p.vel)) for p in particles), default=0.0)
    cell_size = 2.0 * (max_radius + 2.0 * max_speed * dt)

    # If cell_size is zero (all radii and speeds are zero), fall back to direct
    if cell_size < 1e-30:
        return detect_collisions_direct(particles, dt)

    inv_cell = 1.0 / cell_size

    # Assign each particle to a grid cell
    grid: Dict[Tuple[int, int, int], List[int]] = defaultdict(list)
    for idx, p in enumerate(particles):
        cx = int(math.floor(p.pos[0] * inv_cell))
        cy = int(math.floor(p.pos[1] * inv_cell))
        cz = int(math.floor(p.pos[2] * inv_cell))
        grid[(cx, cy, cz)].append(idx)

    checked: set = set()
    events: List[CollisionEvent] = []

    for (cx, cy, cz), cell_indices in grid.items():
        # Check all pairs within this cell
        for k1 in range(len(cell_indices)):
            i = cell_indices[k1]
            for k2 in range(k1 + 1, len(cell_indices)):
                j = cell_indices[k2]
                pair = (min(i, j), max(i, j))
                if pair not in checked:
                    checked.add(pair)
                    ev = _check_pair(particles[i], particles[j], i, j, dt)
                    if ev is not None:
                        events.append(ev)

        # Check against adjacent cells (only forward-adjacent to avoid double-checking)
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                for dz in range(-1, 2):
                    if dx == 0 and dy == 0 and dz == 0:
                        continue  # same cell already handled above
                    neighbor = (cx + dx, cy + dy, cz + dz)
                    if neighbor not in grid:
                        continue
                    for i in cell_indices:
                        for j in grid[neighbor]:
                            pair = (min(i, j), max(i, j))
                            if pair not in checked:
                                checked.add(pair)
                                # Always pass (smaller_idx, larger_idx) to match
                                # the direct method's iteration order.
                                lo, hi = pair
                                ev = _check_pair(particles[lo], particles[hi], lo, hi, dt)
                                if ev is not None:
                                    events.append(ev)

    events.sort(key=lambda e: e.t_collision)
    return events


def _check_pair(
    p1: Particle, p2: Particle, idx_i: int, idx_j: int, dt: float
) -> Optional[CollisionEvent]:
    """Check if two particles collide during [0, dt].

    Uses quadratic interpolation of the squared distance to find the
    minimum separation. If the minimum is less than the sum of radii,
    a collision is detected.
    """
    # Position difference at start and end of timestep
    dr0 = p1.pos - p2.pos
    dv0 = p1.vel - p2.vel

    # Quadratic model: d²(t) = |dr0 + dv0*t|² = a*t² + b*t + c
    a = np.dot(dv0, dv0)
    b = 2.0 * np.dot(dr0, dv0)
    c = np.dot(dr0, dr0)

    # Check if particles are approaching
    if b >= 0 and a <= 1e-30:
        return None  # moving apart or parallel

    # Minimum of quadratic: t_min = -b / (2a)
    combined_radius = p1.radius + p2.radius

    if a > 1e-30:
        t_min = -b / (2.0 * a)
        t_min = max(0.0, min(dt, t_min))  # clamp to [0, dt]
    else:
        t_min = 0.0

    # Distance at t_min
    dr_min = dr0 + dv0 * t_min
    d_min = np.linalg.norm(dr_min)

    if d_min <= combined_radius:
        return CollisionEvent(
            i=idx_i,
            j=idx_j,
            t_collision=t_min,
            min_distance=d_min,
            relative_speed=np.linalg.norm(dv0),
        )

    # Also check endpoints
    d_start = np.linalg.norm(dr0)
    d_end = np.linalg.norm(dr0 + dv0 * dt)

    if d_start <= combined_radius:
        return CollisionEvent(idx_i, idx_j, 0.0, d_start, np.linalg.norm(dv0))
    if d_end <= combined_radius:
        return CollisionEvent(idx_i, idx_j, dt, d_end, np.linalg.norm(dv0))

    return None


def resolve_merge(
    p1: Particle, p2: Particle
) -> Particle:
    """Merge two particles (momentum-conserving coalescence).

    Conserves total momentum and mass. The merged particle's radius
    is computed from volume conservation (sphere assumption).

    Used for: debris accretion, planetesimal formation, spacecraft docking.
    """
    total_mass = p1.mass + p2.mass
    if total_mass < 1e-30:
        return p1

    # Momentum-conserving velocity
    new_vel = (p1.mass * p1.vel + p2.mass * p2.vel) / total_mass

    # Center-of-mass position
    new_pos = (p1.mass * p1.pos + p2.mass * p2.pos) / total_mass

    # Volume-conserving radius
    new_radius = (p1.radius ** 3 + p2.radius ** 3) ** (1.0 / 3.0)

    return Particle(
        pos=new_pos,
        vel=new_vel,
        mass=total_mass,
        radius=new_radius,
        name=f"{p1.name}+{p2.name}" if p1.name or p2.name else "",
    )


def resolve_bounce(
    p1: Particle, p2: Particle, restitution: float = 0.5
) -> Tuple[np.ndarray, np.ndarray]:
    """Elastic/inelastic bounce between two particles.

    Returns the new velocities (v1_new, v2_new) after the collision.

    Args:
        p1, p2: colliding particles
        restitution: coefficient of restitution (0 = perfectly inelastic, 1 = elastic)

    Reference: Goldstein "Classical Mechanics" §3.11 two-body scattering.
    """
    dr = p2.pos - p1.pos
    dr_norm = np.linalg.norm(dr)
    if dr_norm < 1e-15:
        return p1.vel.copy(), p2.vel.copy()

    n = dr / dr_norm  # collision normal
    dv = p1.vel - p2.vel
    dv_n = np.dot(dv, n)

    if dv_n <= 0:
        # Not approaching (separating or parallel)
        return p1.vel.copy(), p2.vel.copy()

    # Impulse magnitude (dv_n > 0 means p1 approaches p2 along n)
    m1, m2 = p1.mass, p2.mass
    j = (1.0 + restitution) * dv_n / (1.0 / m1 + 1.0 / m2)

    v1_new = p1.vel - (j / m1) * n
    v2_new = p2.vel + (j / m2) * n

    return v1_new, v2_new
