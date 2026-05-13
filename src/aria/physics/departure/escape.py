"""Escape velocity, vis-viva, and hyperbolic excess (§4.2 of A3 scope).

From energy conservation in the Keplerian two-body problem,

    v² / 2 − μ / r = const = v_∞² / 2

(Bate-Mueller-White §1.5, ISBN 978-0486600611). This yields the standard
results for a body of reduced mass in the gravitational field of a central
mass with gravitational parameter `μ = G · M`:

    v_escape(r) = √(2 μ / r)                      [m/s]
    v_∞         = √(v² − 2 μ / r)                 [m/s]  (if v > v_escape)
    v(r; a)     = √(μ (2/r − 1/a))                vis-viva, semi-major axis a

Characteristic energy C3 = v_∞² (m²/s²) is the hyperbolic departure energy
and is the standard mission-design figure of merit.
"""

from __future__ import annotations

import math

# Earth gravitational parameter (WGS-84, NIMA TR 8350.2, 2000).
GM_EARTH_M3_S2: float = 3.986004418e14  # WGS-84 (NIMA TR 8350.2)

# Sun gravitational parameter (JPL DE440, Park 2021 AJ 161 105,
# DOI 10.3847/1538-3881/abd414).
GM_SUN_M3_S2: float = 1.32712440041939e20  # JPL DE440 (Park 2021)

# Jupiter gravitational parameter (Juno, Iess 2018 Nature 555 220,
# DOI 10.1038/nature25776).
GM_JUPITER_M3_S2: float = 1.26686534e17  # Juno (Iess 2018)

# Earth mean heliocentric orbital speed (IAU 2015 Resolution B3,
# derived from nominal AU and 1 sidereal year).
V_EARTH_HELIOCENTRIC_M_S: float = 2.978e4  # IAU 2015 (~29.78 km/s)

# Sphere of influence radii (Vallado 4th ed Table 1-3, ISBN 978-1881883180).
R_SOI_EARTH_M: float = 9.245e8  # Vallado Table 1-3
R_SOI_JUPITER_M: float = 4.82e10  # Vallado Table 1-3


def escape_velocity(gravitational_parameter_m3_s2: float, radius_m: float) -> float:
    """Escape speed from radius `r` in a central gravity field.

    v_escape = √(2 μ / r)                           [m/s]

    Args:
        gravitational_parameter_m3_s2: μ = G·M of the central body (m³/s²).
        radius_m: distance from the central body's center (m).

    Returns:
        Escape velocity in m/s.
    """
    if gravitational_parameter_m3_s2 <= 0.0:
        raise ValueError("gravitational_parameter_m3_s2 must be positive")
    if radius_m <= 0.0:
        raise ValueError("radius_m must be positive")
    return math.sqrt(2.0 * gravitational_parameter_m3_s2 / radius_m)


def circular_orbit_speed(
    gravitational_parameter_m3_s2: float, radius_m: float
) -> float:
    """Speed of a circular orbit at radius `r`: v_c = √(μ/r)."""
    if gravitational_parameter_m3_s2 <= 0.0:
        raise ValueError("gravitational_parameter_m3_s2 must be positive")
    if radius_m <= 0.0:
        raise ValueError("radius_m must be positive")
    return math.sqrt(gravitational_parameter_m3_s2 / radius_m)


def vis_viva_speed(
    gravitational_parameter_m3_s2: float,
    radius_m: float,
    semi_major_axis_m: float,
) -> float:
    """Vis-viva equation: orbital speed at radius `r` on an orbit with
    semi-major axis `a`.

    v = √(μ (2/r − 1/a))                            [m/s]

    For an ellipse, `a > 0` and `r` ranges over the orbit; for a parabola
    `a → ∞` and v = √(2μ/r) = v_escape; for a hyperbola `a < 0`.
    """
    if gravitational_parameter_m3_s2 <= 0.0:
        raise ValueError("gravitational_parameter_m3_s2 must be positive")
    if radius_m <= 0.0:
        raise ValueError("radius_m must be positive")
    inner = gravitational_parameter_m3_s2 * (2.0 / radius_m - 1.0 / semi_major_axis_m)
    if inner < 0.0:
        raise ValueError(
            "vis-viva expression is negative: r lies outside the orbit "
            "(r > 2a for an ellipse). Inputs: "
            f"mu={gravitational_parameter_m3_s2}, r={radius_m}, a={semi_major_axis_m}"
        )
    return math.sqrt(inner)


def v_infinity_from_v(
    speed_m_s: float, gravitational_parameter_m3_s2: float, radius_m: float
) -> float:
    """Hyperbolic excess speed `v_∞` given the instantaneous speed at
    radius `r`.

    v_∞ = √(v² − 2 μ / r)                           [m/s]

    Returns 0.0 if the ship is exactly at escape (numerical ≤ 0).
    Raises if the ship is bound (v < v_escape).
    """
    if speed_m_s < 0.0:
        raise ValueError("speed_m_s must be non-negative")
    if gravitational_parameter_m3_s2 <= 0.0:
        raise ValueError("gravitational_parameter_m3_s2 must be positive")
    if radius_m <= 0.0:
        raise ValueError("radius_m must be positive")
    v_esc_sq = 2.0 * gravitational_parameter_m3_s2 / radius_m
    v_inf_sq = speed_m_s * speed_m_s - v_esc_sq
    if v_inf_sq < 0.0:
        raise ValueError(
            f"Ship is bound: v={speed_m_s} m/s < v_escape="
            f"{math.sqrt(v_esc_sq)} m/s at r={radius_m} m"
        )
    return math.sqrt(v_inf_sq)


def characteristic_energy_c3(
    speed_m_s: float, gravitational_parameter_m3_s2: float, radius_m: float
) -> float:
    """C3 ≡ v_∞² — standard mission-design departure energy (m²/s²)."""
    v_inf = v_infinity_from_v(speed_m_s, gravitational_parameter_m3_s2, radius_m)
    return v_inf * v_inf
