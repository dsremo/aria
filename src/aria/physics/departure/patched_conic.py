"""Patched-conic primitives for the departure problem (§4.4 of A3 scope).

The patched-conic approximation (Vallado 4th ed §9.2, ISBN 978-1881883180)
treats each body's sphere of influence (SOI) as containing only that
body's gravity; transitions between SOIs are instantaneous. Under this
assumption a multi-body trajectory is a chain of Keplerian conics joined
at SOI boundaries.

This module provides the geometric primitives A3 needs to assemble a
departure plan — SOI radii, gravitational-slingshot turning angle and
Δv, and the hyperbolic-flyby turning-angle formula. The actual orbit
integration is delegated to Pod A1 (ephemeris and N-body).

Laplace SOI radius (Vallado §1.3.3):

    r_SOI = a_body · (m_body / M_sun)^(2/5)         [m]

Gravitational slingshot: a hyperbolic flyby of a body with v_∞ relative
to it rotates the incoming velocity vector by the turning angle 2δ:

    sin δ = 1 / (1 + r_p v_∞² / μ_body)              [dimensionless]

and the magnitude of the heliocentric Δv gained (or lost, depending
on geometry) is

    |Δv_slingshot| = 2 v_∞ sin δ                    [m/s]

Upper bound: Δv_max = 2 v_∞, achieved in the limit r_p → 0 (δ → π/2).

Reference: Vallado 4th ed §12.3 "Planetary flyby"; Battin §6 *An
Introduction to the Mathematics and Methods of Astrodynamics* (AIAA,
ISBN 978-1563473425).
"""

from __future__ import annotations

import math


def sphere_of_influence_radius(
    body_semi_major_axis_m: float,
    body_mass_kg: float,
    central_mass_kg: float,
) -> float:
    """Laplace sphere-of-influence radius of a body orbiting a primary.

    r_SOI = a · (m / M)^(2/5)                        [m]

    Args:
        body_semi_major_axis_m: orbital semi-major axis of the body
            around the central mass (m).
        body_mass_kg: mass of the body whose SOI we want (kg).
        central_mass_kg: mass of the primary (kg).

    Returns:
        r_SOI in meters.

    Example (Earth in solar orbit):
        r_SOI ≈ 1.496e11 · (5.972e24 / 1.989e30)^(2/5)
             ≈ 9.25e8 m  (≈ 925 000 km)
    """
    if body_semi_major_axis_m <= 0.0:
        raise ValueError("body_semi_major_axis_m must be positive")
    if body_mass_kg <= 0.0:
        raise ValueError("body_mass_kg must be positive")
    if central_mass_kg <= 0.0:
        raise ValueError("central_mass_kg must be positive")
    return body_semi_major_axis_m * (body_mass_kg / central_mass_kg) ** (2.0 / 5.0)


def flyby_turning_angle(
    v_infinity_m_s: float,
    periapsis_radius_m: float,
    body_gravitational_parameter_m3_s2: float,
) -> float:
    """Half-turning-angle δ of a hyperbolic flyby.

    sin δ = 1 / (1 + r_p v_∞² / μ)                  [dimensionless]

    Args:
        v_infinity_m_s: v_∞ relative to the flyby body (m/s).
        periapsis_radius_m: closest-approach distance (m).
        body_gravitational_parameter_m3_s2: μ of the flyby body (m³/s²).

    Returns:
        δ in radians (half the full turning angle; the velocity vector
        rotates by 2 δ).
    """
    if v_infinity_m_s < 0.0:
        raise ValueError("v_infinity_m_s must be non-negative")
    if periapsis_radius_m <= 0.0:
        raise ValueError("periapsis_radius_m must be positive")
    if body_gravitational_parameter_m3_s2 <= 0.0:
        raise ValueError("body_gravitational_parameter_m3_s2 must be positive")
    denom = 1.0 + periapsis_radius_m * v_infinity_m_s * v_infinity_m_s / (
        body_gravitational_parameter_m3_s2
    )
    return math.asin(1.0 / denom)


def slingshot_delta_v(
    v_infinity_m_s: float,
    periapsis_radius_m: float,
    body_gravitational_parameter_m3_s2: float,
) -> float:
    """Magnitude of the heliocentric Δv acquired from a gravitational
    slingshot.

    |Δv| = 2 v_∞ · sin δ                              [m/s]

    The sign and direction depend on the geometry of the encounter; the
    caller is responsible for orienting the Δv vector. This function
    returns the magnitude only.

    Upper bound: 2 v_∞ (in the r_p → 0 limit, δ → π/2). For realistic
    flybys (r_p > R_body + atmosphere) the achievable Δv is somewhat
    less.
    """
    delta = flyby_turning_angle(
        v_infinity_m_s, periapsis_radius_m, body_gravitational_parameter_m3_s2
    )
    return 2.0 * v_infinity_m_s * math.sin(delta)
