"""Sloshing modal analysis (§4.6, §4.7 of H2 scope).

Abramson (ed.) 1966 *The Dynamic Behavior of Liquids in Moving
Containers* NASA SP-106 derives the small-amplitude lateral slosh
natural frequency of liquid in an upright cylindrical tank as

    ω_{mn}² = g (ξ_{mn} / R) tanh(ξ_{mn} h / R)               [rad²/s²]

where ξ_{mn} is the n-th root of J'_m(ξ) = 0. The first lateral
mode (m = 1, n = 1) uses ξ_{11} = 1.841 184 (Abramson 1966 Table 2.1),
giving the engineer's everyday sloshing formula. For a centrifuged
ring tank (rotating habitat) the *effective* gravity is replaced by
g_eff = Ω² r, where r is the radial position of the tank.

Rough spring-mass equivalents for the first slosh mode: Abramson
1966 eq. 2.34 gives the oscillating liquid-mass fraction

    m_1 / m_total ≈ (2 R / (ξ_{11}² h)) · tanh(ξ_{11} h / R)

which for h / R ≫ 1 converges to ≈ 0.455 / (h/R), and for shallow
tanks (h / R → 0) approaches 1.0.

References:
  - Abramson (ed.) 1966 NASA SP-106.
  - Ibrahim 2005 *Liquid Sloshing Dynamics* 2nd ed (ISBN
    978-0521838856) §4.6 (rotating frames).
  - Dodge 2000 NASA CR-2000-210135 (engineering handbook).
"""

from __future__ import annotations

import math

# First Bessel-derivative root J'_1(ξ) = 0. Abramson 1966 Table 2.1
# (ISBN unavailable; NASA SP-106).
ABRAMSON_XI_11: float = 1.8411838


def cylindrical_tank_slosh_frequency(
    gravity_m_s2: float,
    tank_radius_m: float,
    fill_depth_m: float,
    xi_mn: float = ABRAMSON_XI_11,
) -> float:
    """First lateral slosh natural frequency in an upright cylinder.

    f = (1/2π) · √( g · ξ/R · tanh(ξ h / R) )                 [Hz]

    Returns 0 when g ≤ 0 (no restoring force). Canonical check:
    R = 1 m, h = 1 m, g = 9.81 m/s² → f ≈ 0.664 Hz (Abramson 1966
    Fig 2.8 regression).
    """
    if tank_radius_m <= 0.0:
        raise ValueError("tank_radius_m must be positive")
    if fill_depth_m <= 0.0:
        raise ValueError("fill_depth_m must be positive")
    if xi_mn <= 0.0:
        raise ValueError("xi_mn must be positive")
    if gravity_m_s2 <= 0.0:
        return 0.0
    arg = xi_mn * fill_depth_m / tank_radius_m
    omega_sq = gravity_m_s2 * xi_mn / tank_radius_m * math.tanh(arg)
    return math.sqrt(omega_sq) / (2.0 * math.pi)


def centrifuged_ring_tank_frequency(
    rotation_rate_rad_s: float,
    radial_distance_m: float,
    tank_radius_m: float,
    fill_depth_m: float,
    xi_mn: float = ABRAMSON_XI_11,
) -> float:
    """Slosh frequency inside a small tank mounted on a spinning ring.

    The centrifugal body force at radius r from the spin axis is
    g_eff = Ω² r (Ibrahim 2005 §4.6); the sloshing frequency follows
    the standard Abramson formula with `g → g_eff`.

    Args:
        rotation_rate_rad_s: Ω (rad/s, non-negative).
        radial_distance_m: r from spin axis to the tank centre (m).
        tank_radius_m: R of the tank itself (m).
        fill_depth_m: h (m).
        xi_mn: Bessel-derivative root. Default first-lateral.

    Returns:
        Lateral slosh frequency (Hz).
    """
    if rotation_rate_rad_s < 0.0:
        raise ValueError("rotation_rate_rad_s must be non-negative")
    if radial_distance_m < 0.0:
        raise ValueError("radial_distance_m must be non-negative")
    g_eff = rotation_rate_rad_s * rotation_rate_rad_s * radial_distance_m
    return cylindrical_tank_slosh_frequency(
        gravity_m_s2=g_eff,
        tank_radius_m=tank_radius_m,
        fill_depth_m=fill_depth_m,
        xi_mn=xi_mn,
    )


def spring_mass_slosh_mass_ratio(
    fill_depth_m: float,
    tank_radius_m: float,
    xi_mn: float = ABRAMSON_XI_11,
) -> float:
    """Fraction of liquid mass participating in the first slosh mode.

    Abramson 1966 eq. 2.34:

        m₁ / m_tot = (2 R / (ξ² h)) · tanh(ξ h / R)

    Dimensionless, bounded in (0, 1]. Converges to 1 for shallow
    tanks (h/R → 0) and decays like 1/h for deep tanks.
    """
    if fill_depth_m <= 0.0:
        raise ValueError("fill_depth_m must be positive")
    if tank_radius_m <= 0.0:
        raise ValueError("tank_radius_m must be positive")
    arg = xi_mn * fill_depth_m / tank_radius_m
    return (2.0 * tank_radius_m / (xi_mn * xi_mn * fill_depth_m)) * math.tanh(arg)
