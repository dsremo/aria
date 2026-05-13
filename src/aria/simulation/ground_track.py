"""Ground track computation for Earth-orbiting satellites.

Converts ECI satellite positions to sub-satellite latitude/longitude over
a rotating Earth. Produces the classic "ground track" visualization showing
which parts of Earth's surface are overflown.

Used for:
- Sun-synchronous orbit verification (should cover same time-of-day each pass)
- Revisit time analysis for constellation design
- Coverage maps for imaging/comms missions
- ISS pass prediction for public viewing

References:
    Vallado (2013) §3.3 — coordinate frames
    Hofmann-Wellenhof (2007) "GNSS — GPS/GLONASS/Galileo" §5
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np


_OMEGA_EARTH = 7.2921150e-5  # rad/s, IERS 2010
_R_EARTH = 6378137.0         # WGS-84 equatorial radius


@dataclass
class GroundTrackPoint:
    """A single point on the ground track."""
    time_s: float
    latitude_deg: float
    longitude_deg: float
    altitude_km: float
    speed_kmps: float          # ground track speed (not orbital)


def eci_to_ecef(r_eci: np.ndarray, t_since_epoch_s: float) -> np.ndarray:
    """Rotate ECI → ECEF by the Earth rotation angle.

    Approximates the Earth rotation as a simple z-axis rotation at
    the mean sidereal rate. Ignores precession/nutation — fine for
    ground track visualization but not precise enough for geodetic work.
    """
    theta = _OMEGA_EARTH * t_since_epoch_s
    ct, st = math.cos(theta), math.sin(theta)
    x, y, z = r_eci
    return np.array([x * ct + y * st, -x * st + y * ct, z])


def ecef_to_geodetic(r_ecef: np.ndarray) -> Tuple[float, float, float]:
    """Convert ECEF → geodetic (latitude, longitude, altitude) on WGS-84.

    Uses the iterative method (Heikkinen 1982 / Bowring 1985).
    Accurate to machine precision for altitudes up to GEO.

    Args:
        r_ecef: (3,) position in ECEF [m]

    Returns:
        (latitude_deg, longitude_deg, altitude_m)
    """
    x, y, z = r_ecef
    # WGS-84 parameters
    a = _R_EARTH
    f = 1.0 / 298.257223563
    e2 = 2 * f - f * f

    # Longitude is straightforward
    lon = math.atan2(y, x)

    # Latitude via iteration (typically converges in 2-3 iterations)
    p = math.sqrt(x * x + y * y)
    if p < 1e-10:
        # Polar point
        lat = math.pi / 2 if z > 0 else -math.pi / 2
        alt = abs(z) - a * math.sqrt(1 - e2)
        return math.degrees(lat), math.degrees(lon), alt

    lat = math.atan2(z, p * (1 - e2))
    for _ in range(5):
        sin_lat = math.sin(lat)
        N = a / math.sqrt(1 - e2 * sin_lat * sin_lat)
        alt = p / math.cos(lat) - N
        new_lat = math.atan2(z, p * (1 - e2 * N / (N + alt)))
        if abs(new_lat - lat) < 1e-12:
            lat = new_lat
            break
        lat = new_lat

    sin_lat = math.sin(lat)
    N = a / math.sqrt(1 - e2 * sin_lat * sin_lat)
    alt = p / math.cos(lat) - N

    return math.degrees(lat), math.degrees(lon), alt


def compute_ground_track(
    eci_positions: np.ndarray,
    times_s: np.ndarray,
) -> List[GroundTrackPoint]:
    """Compute ground track from a series of ECI positions.

    Args:
        eci_positions: (n, 3) ECI positions at each time
        times_s: (n,) times in seconds

    Returns:
        List of GroundTrackPoint.
    """
    points: List[GroundTrackPoint] = []
    prev_lat = None
    prev_lon = None
    prev_t = None

    for i, (r_eci, t) in enumerate(zip(eci_positions, times_s)):
        r_ecef = eci_to_ecef(np.asarray(r_eci), t)
        lat_deg, lon_deg, alt_m = ecef_to_geodetic(r_ecef)

        # Ground track speed (great-circle over Earth surface)
        speed = 0.0
        if prev_lat is not None:
            dlat = math.radians(lat_deg - prev_lat)
            dlon = math.radians(lon_deg - prev_lon)
            # Wrap longitude delta
            if abs(dlon) > math.pi:
                dlon = dlon - 2 * math.pi * (1 if dlon > 0 else -1)
            a_hav = (math.sin(dlat / 2) ** 2
                     + math.cos(math.radians(lat_deg))
                     * math.cos(math.radians(prev_lat))
                     * math.sin(dlon / 2) ** 2)
            angular = 2 * math.atan2(math.sqrt(a_hav), math.sqrt(1 - a_hav))
            dist_m = _R_EARTH * angular
            dt = max(t - prev_t, 1e-6)
            speed = dist_m / dt / 1000.0  # km/s

        points.append(GroundTrackPoint(
            time_s=float(t),
            latitude_deg=lat_deg,
            longitude_deg=lon_deg,
            altitude_km=alt_m / 1000.0,
            speed_kmps=speed,
        ))

        prev_lat = lat_deg
        prev_lon = lon_deg
        prev_t = t

    return points


def coverage_fraction(track: List[GroundTrackPoint], grid_deg: float = 5.0) -> float:
    """Estimate what fraction of Earth's surface the track covers.

    Bins the track into a lat/lon grid and counts occupied cells.
    Useful for constellation design — higher = better coverage.

    Returns:
        Fraction of grid cells visited (0 = nothing, 1 = global)
    """
    n_lat = int(180 / grid_deg)
    n_lon = int(360 / grid_deg)
    grid = np.zeros((n_lat, n_lon), dtype=bool)
    for p in track:
        i_lat = int((p.latitude_deg + 90) / grid_deg)
        i_lon = int((p.longitude_deg + 180) / grid_deg)
        i_lat = max(0, min(n_lat - 1, i_lat))
        i_lon = max(0, min(n_lon - 1, i_lon))
        grid[i_lat, i_lon] = True

    # Weight by cos(latitude) for equal-area grid cells
    lat_centers_deg = np.linspace(-90 + grid_deg / 2, 90 - grid_deg / 2, n_lat)
    weights = np.cos(np.radians(lat_centers_deg))
    covered_area = np.sum(grid * weights[:, None])
    total_area = np.sum(weights) * n_lon
    return float(covered_area / total_area) if total_area > 0 else 0.0


def is_sun_synchronous(
    inclination_deg: float,
    altitude_km: float,
    tolerance_deg: float = 2.0,
) -> bool:
    """Check if an orbit is approximately sun-synchronous.

    A sun-sync orbit has its nodal regression rate match the Earth's
    orbital rate around the Sun (~360°/365.25 days ≈ 0.9856°/day).

    J2-induced node regression: Ω̇ = -1.5 n J2 (R_E/p)² cos(i)

    where n is mean motion, p is semi-latus rectum.

    Args:
        inclination_deg: orbit inclination [deg]
        altitude_km: circular altitude [km]
        tolerance_deg: how close to 0.9856°/day

    Returns:
        True if within tolerance of sun-sync rate.

    Reference: Vallado 2013 §9.7.1.
    """
    mu = 3.986e14
    J2 = 1.08263e-3
    R = 6378137.0

    a = R + altitude_km * 1000.0
    n = math.sqrt(mu / a ** 3)  # rad/s
    cos_i = math.cos(math.radians(inclination_deg))

    # Node regression rate in rad/s
    omega_dot = -1.5 * n * J2 * (R / a) ** 2 * cos_i

    # Convert to deg/day
    omega_dot_deg_per_day = math.degrees(omega_dot) * 86400.0

    # Target: 0.9856 deg/day
    target = 360.0 / 365.25
    return abs(omega_dot_deg_per_day - target) < tolerance_deg
