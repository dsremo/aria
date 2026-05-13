"""Clohessy-Wiltshire rendezvous + docking relative dynamics.

Fills the "rendezvous is a Δv checkbox, not physics" gap. The CW
equations (Clohessy & Wiltshire 1960) give the linearized equations of
motion for a chaser spacecraft relative to a target in a circular
orbit.  They let ARIA actually integrate an approach trajectory, size
the ΔV budget for a realistic V-bar or R-bar rendezvous, and compute
closure-rate constraints for soft docking.

State (LVLH frame, target-centered):
  x = radial outward from target
  y = along-track (direction of motion)
  z = out-of-plane

Equations:
  ẍ − 2 n ẏ − 3 n² x = a_x
  ÿ + 2 n ẋ          = a_y
  z̈ + n² z          = a_z

with n = √(μ / r_target³) the target's mean motion. Analytical two-impulse
transfers (Glandorf) can be composed with numerical integration for a
multi-burn V-bar approach.

Reference:
    Clohessy, W. H. & Wiltshire, R. S. (1960) "Terminal Guidance System for
        Satellite Rendezvous," J. Aerosp. Sci. 27(9):653.
    Vallado (2013) §6.6 "Relative Motion."
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


MU_EARTH = 3.986004418e14


def mean_motion_n(orbit_altitude_km: float, mu: float = MU_EARTH,
                  r_body_m: float = 6378137.0) -> float:
    """Target mean motion n (rad/s)."""
    r = r_body_m + orbit_altitude_km * 1000
    return math.sqrt(mu / (r ** 3))


@dataclass
class CWState:
    t_s: float
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float


@dataclass
class CWResult:
    trajectory: List[CWState] = field(default_factory=list)
    total_dv_mps: float = 0.0
    closest_approach_m: float = 0.0
    docking_success: bool = False
    notes: List[str] = field(default_factory=list)


def cw_state_transition(n: float, t: float) -> Tuple[np.ndarray, np.ndarray]:
    """Clohessy-Wiltshire state-transition matrices Φ_rr, Φ_rv for time t.

    δr(t) = Φ_rr(t) δr(0) + Φ_rv(t) δv(0)
    """
    s, c = math.sin(n * t), math.cos(n * t)
    # In-plane (x, y) 2x2 blocks
    phi_rr = np.array([
        [4 - 3 * c,       0, 0],
        [6 * (s - n * t), 1, 0],
        [0,               0, c],
    ], dtype=float)
    phi_rv = np.array([
        [s / n,                   2 * (1 - c) / n, 0],
        [-2 * (1 - c) / n,        (4 * s - 3 * n * t) / n, 0],
        [0,                       0, s / n],
    ], dtype=float)
    return phi_rr, phi_rv


def two_impulse_transfer(n: float, r0: np.ndarray, rf: np.ndarray,
                          tf: float, v0: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray, float]:
    """Compute the two impulsive burns that move chaser from r0 to rf in time tf.

    Returns (Δv1, Δv2, total_dv) — the first kick at t=0 and the braking
    kick at t=tf.
    """
    v0 = v0 if v0 is not None else np.zeros(3)
    phi_rr, phi_rv = cw_state_transition(n, tf)
    # rf = Φ_rr r0 + Φ_rv (v0 + Δv1)   ⇒   Δv1 = Φ_rv⁻¹ (rf − Φ_rr r0) − v0
    rhs = rf - phi_rr @ r0
    dv1 = np.linalg.solve(phi_rv, rhs) - v0
    # Velocity at arrival = d/dt[Φ_rr r0 + Φ_rv (v0 + dv1)]
    # Differentiate state-transition: Φ_vr and Φ_vv
    s, c = math.sin(n * tf), math.cos(n * tf)
    phi_vr = np.array([
        [3 * n * s,      0, 0],
        [6 * n * (c - 1), 0, 0],
        [0,               0, -n * s],
    ], dtype=float)
    phi_vv = np.array([
        [c,        2 * s,            0],
        [-2 * s,   4 * c - 3,         0],
        [0,        0,                c],
    ], dtype=float)
    v_arrival = phi_vr @ r0 + phi_vv @ (v0 + dv1)
    dv2 = -v_arrival  # zero relative velocity at dock
    return dv1, dv2, float(np.linalg.norm(dv1) + np.linalg.norm(dv2))


def integrate_cw(n: float, r0: np.ndarray, v0: np.ndarray,
                  tf: float, dt_s: float = 5.0) -> List[CWState]:
    """Propagate CW trajectory analytically (no thrust)."""
    traj: List[CWState] = []
    t = 0.0
    while t <= tf + 1e-6:
        phi_rr, phi_rv = cw_state_transition(n, t)
        r = phi_rr @ r0 + phi_rv @ v0
        # Velocities via finite difference of phi over a small dt
        s, c = math.sin(n * t), math.cos(n * t)
        phi_vr = np.array([
            [3 * n * s,      0, 0],
            [6 * n * (c - 1), 0, 0],
            [0,               0, -n * s],
        ], dtype=float)
        phi_vv = np.array([
            [c,        2 * s,            0],
            [-2 * s,   4 * c - 3,         0],
            [0,        0,                c],
        ], dtype=float)
        v = phi_vr @ r0 + phi_vv @ v0
        traj.append(CWState(t_s=t, x=r[0], y=r[1], z=r[2],
                            vx=v[0], vy=v[1], vz=v[2]))
        t += dt_s
    return traj


def simulate_v_bar_approach(orbit_altitude_km: float = 400.0,
                             start_range_m: float = 1000.0,
                             approach_time_s: float = 1800.0,
                             docking_speed_limit_mps: float = 0.1) -> CWResult:
    """Two-impulse V-bar rendezvous: chaser starts behind target on the
    velocity vector, fires to arrive at port with zero relative velocity.

    V-bar means "along the velocity vector" — the Apollo / ISS standard
    approach axis. Start 1 km behind, dock after 30 min.
    """
    n = mean_motion_n(orbit_altitude_km)
    r0 = np.array([0.0, -start_range_m, 0.0])   # 1 km behind
    rf = np.array([0.0, 0.0, 0.0])               # docking port
    dv1, dv2, total_dv = two_impulse_transfer(n, r0, rf, approach_time_s)
    # Integrate with initial burn applied
    traj = integrate_cw(n, r0, dv1, approach_time_s, dt_s=approach_time_s / 200)
    closest = min(math.sqrt(s.x * s.x + s.y * s.y + s.z * s.z) for s in traj)
    # Closing speed at rendezvous
    final = traj[-1]
    closing_speed = math.sqrt(final.vx ** 2 + final.vy ** 2 + final.vz ** 2)
    # Docking succeeds if final range < 5 m and closing speed < limit
    success = closest < 5.0 and closing_speed < docking_speed_limit_mps
    notes = [
        f"Δv1={np.linalg.norm(dv1):.3f} m/s  Δv2={np.linalg.norm(dv2):.3f} m/s",
        f"total Δv={total_dv:.3f} m/s over {approach_time_s/60:.1f} min",
        f"closest approach {closest:.2f} m  final closing speed {closing_speed*1000:.1f} mm/s",
    ]
    return CWResult(trajectory=traj, total_dv_mps=total_dv,
                     closest_approach_m=closest, docking_success=success,
                     notes=notes)
