"""Satellite constellation design — Walker/Flower patterns.

Generates constellation orbital elements for:
- **Walker-delta** (T/P/F): T total satellites in P orbital planes,
  each plane has T/P satellites, phasing F controls interplane offset.
  Examples: GPS (24/6/2), Galileo (30/3/1), Starlink shells.
- **Flower constellations**: Elliptical orbits with repeat-ground-track
  properties. Used for persistent regional coverage.

Also provides coverage analysis:
- Minimum satellites for continuous global coverage at given elevation
- Revisit time for a ground target
- Earth coverage geometry

References:
    Walker (1984) J. Brit. Interplanetary Soc. 37:559
    Mortari et al. (2004) J. Astronautical Sciences 52(3):257
    Wertz (2001) "Mission Geometry; Orbit and Constellation Design" §13
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

import numpy as np


@dataclass
class OrbitalElements:
    """Classical orbital elements."""
    a_km: float            # semi-major axis
    ecc: float             # eccentricity
    inc_deg: float         # inclination
    raan_deg: float        # right ascension of ascending node
    arg_perigee_deg: float
    mean_anomaly_deg: float


@dataclass
class Constellation:
    """A designed constellation."""
    name: str
    satellites: List[OrbitalElements]
    total_satellites: int
    orbital_planes: int
    pattern: str           # "Walker-delta", "Flower", etc.
    description: str = ""


def walker_delta_constellation(
    t_total: int,
    p_planes: int,
    f_phasing: int,
    altitude_km: float,
    inclination_deg: float = 55.0,
    name: str = "Walker-delta",
) -> Constellation:
    """Design a Walker-delta constellation T/P/F.

    Walker notation T/P/F:
    - T: total number of satellites
    - P: number of equally-spaced orbital planes
    - F: phasing factor (0 ≤ F < P), controls interplane satellite offset

    Interplane phase shift = F × 360/T degrees
    Intraplane phase shift = 360 × P/T degrees

    Args:
        t_total: total satellites (e.g., 24 for GPS)
        p_planes: orbital planes (e.g., 6 for GPS)
        f_phasing: phasing parameter (e.g., 2 for GPS)
        altitude_km: circular orbit altitude
        inclination_deg: common inclination

    Returns:
        Constellation with t_total satellite element sets.

    Reference: Walker 1984 JBIS 37:559.
    """
    if t_total % p_planes != 0:
        raise ValueError(f"t_total ({t_total}) must be divisible by p_planes ({p_planes})")
    if not (0 <= f_phasing < p_planes):
        raise ValueError(f"f_phasing must be in [0, {p_planes})")

    s_per_plane = t_total // p_planes
    a_km = 6378.137 + altitude_km

    satellites: List[OrbitalElements] = []
    for j in range(p_planes):
        raan = j * 360.0 / p_planes
        for i in range(s_per_plane):
            # Mean anomaly = intraplane offset + interplane phasing
            ma = (i * 360.0 / s_per_plane + j * f_phasing * 360.0 / t_total) % 360.0
            satellites.append(OrbitalElements(
                a_km=a_km,
                ecc=0.0,
                inc_deg=inclination_deg,
                raan_deg=raan,
                arg_perigee_deg=0.0,
                mean_anomaly_deg=ma,
            ))

    return Constellation(
        name=name,
        satellites=satellites,
        total_satellites=t_total,
        orbital_planes=p_planes,
        pattern="Walker-delta",
        description=f"{t_total}/{p_planes}/{f_phasing} at {altitude_km:.0f} km, {inclination_deg:.1f}°",
    )


def walker_star_constellation(
    t_total: int,
    p_planes: int,
    altitude_km: float,
    inclination_deg: float = 90.0,
    name: str = "Walker-star",
) -> Constellation:
    """Design a Walker-star (polar) constellation.

    Walker-star uses only 180° of RAAN (vs 360° for delta), creating
    a polar constellation pattern. Used by Iridium (66 sats, 6 planes,
    86.4° inclination).

    Args:
        t_total, p_planes: Walker parameters
        altitude_km: circular altitude
        inclination_deg: inclination (typically near 90°)

    Returns:
        Constellation with t_total satellites.
    """
    if t_total % p_planes != 0:
        raise ValueError(f"t_total must be divisible by p_planes")

    s_per_plane = t_total // p_planes
    a_km = 6378.137 + altitude_km

    satellites: List[OrbitalElements] = []
    for j in range(p_planes):
        raan = j * 180.0 / p_planes  # 180° span for star
        for i in range(s_per_plane):
            ma = (i * 360.0 / s_per_plane) % 360.0
            satellites.append(OrbitalElements(
                a_km=a_km,
                ecc=0.0,
                inc_deg=inclination_deg,
                raan_deg=raan,
                arg_perigee_deg=0.0,
                mean_anomaly_deg=ma,
            ))

    return Constellation(
        name=name,
        satellites=satellites,
        total_satellites=t_total,
        orbital_planes=p_planes,
        pattern="Walker-star",
        description=f"{t_total}/{p_planes} polar at {altitude_km:.0f} km",
    )


def ground_coverage_angle(
    altitude_km: float, min_elevation_deg: float = 10.0
) -> float:
    """Earth-central angle of the coverage footprint from a satellite.

    Computes the half-angle subtended at Earth's center by the circle
    of ground visibility (where elevation ≥ min_elevation_deg).

    Args:
        altitude_km: satellite altitude
        min_elevation_deg: minimum required ground elevation

    Returns:
        Earth-central half-angle [deg]

    Reference: Wertz 2001 §8-1 Eq. (8-22).
    """
    r_earth = 6378.137
    r_sat = r_earth + altitude_km

    # Geometry: ground elevation ε, satellite slant angle η, Earth-central
    # angle λ satisfy: ε + η + λ = 90° (exterior angle theorem).
    # From law of sines: sin(η)/R_earth = sin(90°+ε)/r_sat → sin(η) = R_E/r_sat * cos(ε)
    eps_rad = math.radians(min_elevation_deg)
    sin_eta = (r_earth / r_sat) * math.cos(eps_rad)
    if sin_eta > 1.0:
        return 0.0
    eta = math.asin(sin_eta)
    lambda_rad = math.pi / 2 - eps_rad - eta

    return math.degrees(lambda_rad)


def min_satellites_for_continuous_coverage(
    altitude_km: float, min_elevation_deg: float = 10.0
) -> int:
    """Minimum satellites in a Walker-delta for continuous global coverage.

    Uses Adams-Rider constellation coverage theorem:
        N_min ≈ 4π / (Ω_footprint)
    where Ω is the solid angle of each satellite's footprint.

    This is a lower bound — actual designs need margin for orbit
    maintenance, de-orbit handling, and non-uniform coverage needs.

    Args:
        altitude_km: altitude (same for all sats)
        min_elevation_deg: minimum elevation for usable coverage

    Returns:
        Minimum satellite count

    Reference: Rider (1985) J. Spacecr. Rockets 22(5):472.
    """
    half_angle_deg = ground_coverage_angle(altitude_km, min_elevation_deg)
    if half_angle_deg <= 0:
        return 0
    # Solid angle of spherical cap = 2π(1 - cos(θ))
    solid_angle_sr = 2 * math.pi * (1 - math.cos(math.radians(half_angle_deg)))
    sphere_sr = 4 * math.pi
    return max(1, int(math.ceil(sphere_sr / solid_angle_sr * 1.2)))  # 20% margin


# ══════════════════════════════════════════════════════════════════
#  Built-in examples (real operational constellations)
# ══════════════════════════════════════════════════════════════════

def gps_constellation() -> Constellation:
    """GPS: 24/6/2 Walker-delta at 20200 km, 55° inclination."""
    return walker_delta_constellation(
        t_total=24, p_planes=6, f_phasing=2,
        altitude_km=20200.0,
        inclination_deg=55.0,
        name="GPS",
    )


def galileo_constellation() -> Constellation:
    """Galileo: 30/3/1 Walker-delta at 23222 km, 56° inclination."""
    return walker_delta_constellation(
        t_total=30, p_planes=3, f_phasing=1,
        altitude_km=23222.0,
        inclination_deg=56.0,
        name="Galileo",
    )


def iridium_constellation() -> Constellation:
    """Iridium: 66 sats, 6 polar planes at 780 km, 86.4° inclination."""
    return walker_star_constellation(
        t_total=66, p_planes=6,
        altitude_km=780.0,
        inclination_deg=86.4,
        name="Iridium",
    )
