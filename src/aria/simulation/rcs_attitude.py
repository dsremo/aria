"""6-DOF attitude control with RCS thrusters.

Quaternion + angular-rate state, Euler's equations of motion, RCS
thruster torque allocation. Addresses the audit gap "Euler's equations
exist but not connected to RCS thruster model."

State:
  q = (qw, qx, qy, qz)   unit quaternion, body→inertial
  ω = (ωx, ωy, ωz)       body-frame rates (rad/s)

Dynamics (Euler's equations):
  I ω̇ + ω × (I ω) = τ_rcs

Reference:
    Schaub, H. & Junkins, J. L. (2014) "Analytical Mechanics of
        Space Systems," 3rd ed. AIAA. §3.4, §8.3.
    Wie, B. (2008) "Space Vehicle Dynamics and Control," 2nd ed. AIAA.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np


@dataclass
class Thruster:
    """One RCS thruster on the spacecraft body."""
    name: str
    position_m: np.ndarray      # location on body (3,)
    direction: np.ndarray       # thrust unit vector in body frame (3,)
    force_n: float              # max thrust magnitude


@dataclass
class RigidBody:
    """Spacecraft inertia + RCS suite."""
    name: str
    mass_kg: float
    inertia_tensor: np.ndarray  # (3,3) about CoM, body frame
    thrusters: List[Thruster] = field(default_factory=list)


def quat_normalize(q: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(q)
    return q / n if n > 0 else np.array([1.0, 0, 0, 0])


def quat_derivative(q: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """q̇ = 0.5 · Ω(ω) · q"""
    wx, wy, wz = omega
    W = 0.5 * np.array([
        [0, -wx, -wy, -wz],
        [wx, 0, wz, -wy],
        [wy, -wz, 0, wx],
        [wz, wy, -wx, 0],
    ])
    return W @ q


def rotate_vector_by_quat(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    qw, qx, qy, qz = q
    R = np.array([
        [1 - 2 * (qy**2 + qz**2), 2*(qx*qy - qz*qw),    2*(qx*qz + qy*qw)],
        [2*(qx*qy + qz*qw),       1 - 2*(qx**2 + qz**2), 2*(qy*qz - qx*qw)],
        [2*(qx*qz - qy*qw),       2*(qy*qz + qx*qw),    1 - 2*(qx**2 + qy**2)],
    ])
    return R @ v


def rcs_torque(body: RigidBody, thruster_commands: List[float]) -> np.ndarray:
    """Sum of torques from each thruster given its throttle command [0,1]."""
    tau = np.zeros(3)
    for thr, cmd in zip(body.thrusters, thruster_commands):
        F = cmd * thr.force_n * thr.direction
        r = thr.position_m
        tau += np.cross(r, F)
    return tau


def simulate_attitude(body: RigidBody,
                      q0: np.ndarray,
                      omega0: np.ndarray,
                      thruster_schedule: List[List[float]],
                      dt_s: float = 0.1) -> Tuple[np.ndarray, np.ndarray, List[dict]]:
    """Integrate attitude dynamics under a time-varying RCS schedule."""
    q = quat_normalize(q0.astype(float))
    omega = np.asarray(omega0, dtype=float).copy()
    I = body.inertia_tensor
    I_inv = np.linalg.inv(I)
    history = []
    for k, cmds in enumerate(thruster_schedule):
        tau = rcs_torque(body, cmds)
        # Euler's equations: I·ω̇ = τ − ω × (I·ω)
        omega_dot = I_inv @ (tau - np.cross(omega, I @ omega))
        omega += omega_dot * dt_s
        q = quat_normalize(q + quat_derivative(q, omega) * dt_s)
        history.append({
            "t": k * dt_s, "q": q.copy(), "omega": omega.copy(),
            "tau": tau.copy(),
        })
    return q, omega, history


def apollo_csm_rcs() -> RigidBody:
    """Approximate Apollo CSM: 16 thrusters in 4 quads."""
    I = np.diag([24_000, 28_000, 28_000])   # kg·m² (Apollo CSM)
    r = 1.5
    F = 445.0   # N (Apollo R-4D)
    thrusters: List[Thruster] = []
    # Four quads on the SM at four azimuths
    for k, az in enumerate([0, 90, 180, 270]):
        az_rad = math.radians(az)
        x = r * math.cos(az_rad)
        y = r * math.sin(az_rad)
        pos = np.array([x, y, 0.0])
        # 4 thrusters per quad: +pitch, -pitch, +yaw, -yaw
        thrusters.append(Thruster(f"Q{k}+pitch", pos, np.array([0, 0, +1]), F))
        thrusters.append(Thruster(f"Q{k}-pitch", pos, np.array([0, 0, -1]), F))
        thrusters.append(Thruster(f"Q{k}+yaw",   pos, np.array([math.sin(az_rad), -math.cos(az_rad), 0]), F))
        thrusters.append(Thruster(f"Q{k}-yaw",   pos, np.array([-math.sin(az_rad), math.cos(az_rad), 0]), F))
    return RigidBody("Apollo CSM", 30_000, I, thrusters)
