"""Closed-form rotating-frame kinematics (§4.1–§4.7 of C1 scope).

All derivations live in `docs/pods/C1_rotating_hab.md` §4. Summary:

Starting from Newton's second law in an inertial frame and applying
the rotating-frame chain rule for time derivatives (Goldstein 2002
§4.9, eq. 4.86; Landau-Lifshitz Vol. 1 §39, eq. 39.1), the equation
of motion in a frame rotating at angular velocity `Ω(t)` is

    a_rot = (F_real / m)
            − 2 Ω × v_rot            <- Coriolis
            − Ω × (Ω × r)             <- centrifugal
            − (dΩ/dt) × r             <- Euler

(Goldstein eq. 4.91). This module provides scalar and vector closed-
forms for each term under the simplifying assumptions of (i) a fixed
spin axis and (ii) a rigid ring, valid for the ARIA habitat design.

Key scalar forms at a point of radial distance `r` from the axis,
with spin rate `ω = |Ω|` and angular acceleration `α = dω/dt`:

    a_cf  = ω² r                                          [m/s²] (radial, outward)
    a_cor = 2 ω v_w                                       [m/s²] (walking tangentially)
    a_E   = α r                                           [m/s²] (tangential, opposing α)
    Δg    = ω² h_body                                     [m/s²] (head-to-foot)

Typical ARIA numbers (4 rpm = 0.4189 rad/s, R = 56 m):
    ω² R = 9.82 m/s²   (≈ 1 g artificial gravity at the deck)
    2 ω v_w = 1.17 m/s² at v_w = 1.4 m/s (Bohannon 1997 nominal walk)
    ω² · 1.85 m = 0.325 m/s² (3.3 % head-to-foot differential)

The fluid paraboloid free-surface form `z(r) = z₀ + ω² r² / (2 g_local)`
is also provided for Pod H2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


# ─────────────────────────────────────────────────────────────────────
#  Ring configuration holder (a convenience container, no solver state)
# ─────────────────────────────────────────────────────────────────────


@dataclass
class RotatingRingConfig:
    """Static design parameters for a rigid habitat ring.

    Attributes:
        ring_radius_m: Radius from the spin axis to the crew deck (m).
        spin_rate_rad_s: Design angular speed `ω` about the axis (rad/s).
        body_height_m: Crew body height used for differential-g
            computations (m). Defaults to the NASA-STD-3001 Vol. 2
            Rev. C 2024 95th-percentile male stature 1.85 m.

    Static citations:
        - NASA-STD-3001 Vol. 2 Rev. C 2024 Table 4.3.1 (anthropometry)
        - Bohannon 1997 Age & Ageing 26(1) 15–19 (walking speed)
        - ISO 80000-3:2019 (standard gravity g_0 = 9.80665 m/s²)
    """

    ring_radius_m: float
    spin_rate_rad_s: float
    body_height_m: float = 1.85  # NASA-STD-3001 Vol.2 Rev.C 2024 Table 4.3.1

    @property
    def design_g_art_m_s2(self) -> float:
        """Artificial gravity at the deck: `ω² R`."""
        return centrifugal_acceleration_scalar(
            self.spin_rate_rad_s, self.ring_radius_m
        )

    @property
    def design_g_art_in_g0(self) -> float:
        """Artificial gravity in units of standard gravity (9.80665)."""
        return self.design_g_art_m_s2 / 9.80665  # ISO 80000-3:2019 g_0

    @property
    def delta_g_head_foot_m_s2(self) -> float:
        """Head-to-foot differential-g using the configured body height."""
        return differential_g_head_to_foot(
            self.spin_rate_rad_s, self.body_height_m
        )


# ─────────────────────────────────────────────────────────────────────
#  Centrifugal
# ─────────────────────────────────────────────────────────────────────


def centrifugal_acceleration_scalar(
    spin_rate_rad_s: float, radial_distance_m: float
) -> float:
    """Scalar centrifugal acceleration `a = ω² r` [m/s²], directed
    radially outward in the rotating frame.

    Args:
        spin_rate_rad_s: `ω = |Ω|` (rad/s). Must be non-negative.
        radial_distance_m: perpendicular distance from the spin axis
            (m). Must be non-negative.

    Returns:
        Magnitude of the centrifugal acceleration in m/s² (positive).
    """
    if spin_rate_rad_s < 0.0:
        raise ValueError("spin_rate_rad_s must be non-negative")
    if radial_distance_m < 0.0:
        raise ValueError("radial_distance_m must be non-negative")
    return spin_rate_rad_s * spin_rate_rad_s * radial_distance_m


def centrifugal_acceleration_vector(
    omega_rad_s: np.ndarray, position_m: np.ndarray
) -> np.ndarray:
    """Vector centrifugal acceleration `a_cf = −Ω × (Ω × r)` [m/s²].

    Works for an arbitrary spin-axis orientation. For `Ω = ω ẑ` and
    `r = (r, 0, 0)`, this reduces to `(ω² r, 0, 0)` i.e. the scalar
    form above.

    Args:
        omega_rad_s: (3,) spin angular-velocity vector (rad/s).
        position_m: (3,) position vector of the query point (m), in
            the same frame as ``omega_rad_s`` with the origin on the
            spin axis.

    Returns:
        (3,) acceleration vector in m/s².
    """
    Omega = np.asarray(omega_rad_s, dtype=float).reshape(3)
    r = np.asarray(position_m, dtype=float).reshape(3)
    return -np.cross(Omega, np.cross(Omega, r))


# ─────────────────────────────────────────────────────────────────────
#  Coriolis
# ─────────────────────────────────────────────────────────────────────


def coriolis_acceleration_scalar(
    spin_rate_rad_s: float, tangential_velocity_m_s: float
) -> float:
    """Magnitude of the Coriolis acceleration on a crew member walking
    tangentially at speed `v_w` in the rotating frame:

        |a_cor| = 2 ω v_w                                 [m/s²]

    For a walker moving in the direction of the spin (prograde) the
    resulting acceleration is radially inward (toward the spin axis);
    retrograde walking gives outward. The sign is caller's problem;
    this function returns the positive magnitude.

    Args:
        spin_rate_rad_s: |Ω| in rad/s.
        tangential_velocity_m_s: |v_w| in m/s. Sign is ignored.

    Returns:
        |a_cor| in m/s².
    """
    if spin_rate_rad_s < 0.0:
        raise ValueError("spin_rate_rad_s must be non-negative")
    return 2.0 * spin_rate_rad_s * abs(tangential_velocity_m_s)


def coriolis_acceleration_vector(
    omega_rad_s: np.ndarray, velocity_rot_m_s: np.ndarray
) -> np.ndarray:
    """Vector Coriolis acceleration `a_cor = −2 Ω × v_rot` [m/s²].

    Args:
        omega_rad_s: (3,) spin angular velocity (rad/s).
        velocity_rot_m_s: (3,) velocity of the point **in the rotating
            frame** (m/s).

    Returns:
        (3,) Coriolis acceleration vector (m/s²).
    """
    Omega = np.asarray(omega_rad_s, dtype=float).reshape(3)
    v = np.asarray(velocity_rot_m_s, dtype=float).reshape(3)
    return -2.0 * np.cross(Omega, v)


# ─────────────────────────────────────────────────────────────────────
#  Euler force (transient, during spin rate change)
# ─────────────────────────────────────────────────────────────────────


def euler_acceleration_scalar(
    angular_acceleration_rad_s2: float, radial_distance_m: float
) -> float:
    """Magnitude of the Euler acceleration `|a_E| = α r` [m/s²].

    For a fixed spin axis and a radially-located point, the Euler
    pseudo-force is tangential and opposing the direction of spin-up.

    Args:
        angular_acceleration_rad_s2: `α = dω/dt` (rad/s²). Sign ignored.
        radial_distance_m: distance from axis (m). Must be non-negative.

    Returns:
        |a_E| magnitude in m/s².
    """
    if radial_distance_m < 0.0:
        raise ValueError("radial_distance_m must be non-negative")
    return abs(angular_acceleration_rad_s2) * radial_distance_m


def euler_acceleration_vector(
    omega_dot_rad_s2: np.ndarray, position_m: np.ndarray
) -> np.ndarray:
    """Vector Euler acceleration `a_E = −(dΩ/dt) × r` [m/s²].

    Args:
        omega_dot_rad_s2: (3,) angular-acceleration vector (rad/s²).
        position_m: (3,) position vector of the query point (m).

    Returns:
        (3,) Euler pseudo-acceleration in m/s².
    """
    alpha_vec = np.asarray(omega_dot_rad_s2, dtype=float).reshape(3)
    r = np.asarray(position_m, dtype=float).reshape(3)
    return -np.cross(alpha_vec, r)


# ─────────────────────────────────────────────────────────────────────
#  Differential-g gradient across body height
# ─────────────────────────────────────────────────────────────────────


def differential_g_head_to_foot(
    spin_rate_rad_s: float, body_height_m: float
) -> float:
    """Head-to-foot centrifugal-gravity difference `Δg = ω² h` [m/s²].

    Derivation: at the foot level the centrifugal acceleration is
    `g_foot = ω² r_foot`; at the head level (radially inboard by
    `h_body`) it is `g_head = ω² (r_foot − h_body)`. The difference
    is therefore `Δg = g_foot − g_head = ω² h_body`, independent of
    `r_foot` — a linear gradient `dg/dr = ω²` (the "2" in some
    audit statements comes from a different ratio-form convention;
    the dimensional slope is `ω²`).

    Args:
        spin_rate_rad_s: |Ω| in rad/s. Must be non-negative.
        body_height_m: crew body height in meters (positive).

    Returns:
        Foot-acceleration-minus-head-acceleration in m/s² (positive).
    """
    if spin_rate_rad_s < 0.0:
        raise ValueError("spin_rate_rad_s must be non-negative")
    if body_height_m < 0.0:
        raise ValueError("body_height_m must be non-negative")
    return spin_rate_rad_s * spin_rate_rad_s * body_height_m


# ─────────────────────────────────────────────────────────────────────
#  Coriolis deflection of a dropped object
# ─────────────────────────────────────────────────────────────────────


def coriolis_dropped_object_deflection(
    spin_rate_rad_s: float,
    g_art_m_s2: float,
    drop_height_m: float,
) -> tuple[float, float]:
    """Tangential deflection of an object dropped from rest at height
    `h` above the deck of a rotating ring.

    The object starts at rest in the rotating frame, falls under the
    centrifugal "gravity" `g_art = ω² r` (evaluated at the release
    radius, treated as constant over the short fall), and is deflected
    tangentially by the Coriolis term. Integrating
    `a_cor = −2 ω v_fall` with `v_fall = g_art · t` yields

        Δx_tangential = (1/3) · ω · g_art · t_fall³      [m]

    with fall time `t_fall = √(2 h / g_art)` (straightforward
    kinematics, same as a uniform-gravity fall). Reference:
    Hall 2016 J. Spacecraft & Rockets 53(4) 612–619 (DOI 10.2514/1.A33430)
    §3, "Artificial Gravity Visualization".

    Args:
        spin_rate_rad_s: |Ω| of the ring (rad/s).
        g_art_m_s2: centrifugal gravity at the release radius (m/s²).
        drop_height_m: height above the deck at release (m).

    Returns:
        ``(fall_time_s, tangential_deflection_m)`` — the fall time in
        seconds and the tangential deflection in meters (positive
        magnitude; direction depends on spin sense).
    """
    if spin_rate_rad_s < 0.0:
        raise ValueError("spin_rate_rad_s must be non-negative")
    if g_art_m_s2 <= 0.0:
        raise ValueError("g_art_m_s2 must be positive")
    if drop_height_m < 0.0:
        raise ValueError("drop_height_m must be non-negative")
    t_fall = math.sqrt(2.0 * drop_height_m / g_art_m_s2)
    delta_x = (1.0 / 3.0) * spin_rate_rad_s * g_art_m_s2 * (t_fall**3)
    return t_fall, delta_x


# ─────────────────────────────────────────────────────────────────────
#  Fluid paraboloid free surface (informational — consumed by H2)
# ─────────────────────────────────────────────────────────────────────


def fluid_paraboloid_height(
    spin_rate_rad_s: float,
    radial_distance_m: float,
    reference_height_m: float = 0.0,
    local_gravity_m_s2: float = 9.80665,
) -> float:
    """Free-surface height of a liquid at rest in the rotating frame.

    Equilibrium requires the surface to be an equipotential of the
    combined gravitational + centrifugal potential. For the ring
    interior where the "gravity" is the centrifugal field itself
    along the radial direction, the surface takes the parabolic form

        z(r) = z_0 + ω² r² / (2 g_local)                  [m]

    (Landau-Lifshitz Vol. 6 *Fluid Mechanics* §15, ISBN 978-0750627672).

    Args:
        spin_rate_rad_s: ω = |Ω| (rad/s).
        radial_distance_m: r (m).
        reference_height_m: z_0 offset at r = 0 (m).
        local_gravity_m_s2: g_local to use for non-dimensionalization
            (m/s²); defaults to standard gravity g_0 = 9.80665
            (ISO 80000-3:2019).

    Returns:
        z(r) in meters.
    """
    if local_gravity_m_s2 <= 0.0:
        raise ValueError("local_gravity_m_s2 must be positive")
    return (
        reference_height_m
        + spin_rate_rad_s
        * spin_rate_rad_s
        * radial_distance_m
        * radial_distance_m
        / (2.0 * local_gravity_m_s2)
    )
