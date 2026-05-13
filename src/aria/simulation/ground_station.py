"""Ground station modeling — visibility, elevation, range, Doppler.

Models ground station locations on an oblate Earth ellipsoid and
computes satellite visibility windows with azimuth-elevation-range
(AER) tracking.

Algorithm approaches studied from:
- poliastro spheroid_location.py + core/events.py elevation_function (MIT)
- Nyx od/ground_station/mod.rs (AGPL, clean-room reimplemented)
- Open Space Toolkit Access/Generator (Apache 2.0)

References:
    Vallado, D.A. (2013). "Fundamentals of Astrodynamics" §4.4.
    Montenbruck & Gill (2000). "Satellite Orbits" §5.3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

import numpy as np


# WGS-84 ellipsoid constants
_R_EARTH_M = 6378137.0          # equatorial radius [m] (WGS-84)
_F_EARTH = 1.0 / 298.257223563  # flattening (WGS-84)
_E2_EARTH = 2.0 * _F_EARTH - _F_EARTH ** 2  # eccentricity squared
_OMEGA_EARTH = 7.2921150e-5  # Earth rotation rate [rad/s] (IERS 2010)


@dataclass
class GroundStation:
    """A ground station on an oblate Earth ellipsoid.

    Supports geodetic ↔ ECEF conversion, satellite visibility checks,
    and azimuth-elevation-range computation.
    """
    name: str
    latitude_deg: float     # geodetic latitude [deg]
    longitude_deg: float    # geodetic longitude [deg]
    altitude_m: float = 0.0 # height above ellipsoid [m]
    min_elevation_deg: float = 5.0  # minimum tracking elevation [deg]

    def ecef_position(self) -> np.ndarray:
        """Convert geodetic coordinates to ECEF (Earth-Centered Earth-Fixed).

        Uses the WGS-84 ellipsoid model.
        Reference: Vallado (2013) Eq. (4-3).
        """
        lat = math.radians(self.latitude_deg)
        lon = math.radians(self.longitude_deg)

        sin_lat = math.sin(lat)
        cos_lat = math.cos(lat)

        # Radius of curvature in the prime vertical
        N = _R_EARTH_M / math.sqrt(1.0 - _E2_EARTH * sin_lat ** 2)

        x = (N + self.altitude_m) * cos_lat * math.cos(lon)
        y = (N + self.altitude_m) * cos_lat * math.sin(lon)
        z = (N * (1.0 - _E2_EARTH) + self.altitude_m) * sin_lat

        return np.array([x, y, z])

    def aer(
        self, sat_ecef: np.ndarray, t_since_epoch_s: float = 0.0
    ) -> tuple[float, float, float]:
        """Compute azimuth, elevation, range from station to satellite.

        Args:
            sat_ecef: (3,) satellite position in ECEF [m]
            t_since_epoch_s: time since reference epoch [s], used to
                rotate station position with Earth. Set to 0 for
                non-rotating ECEF (satellite already in ECEF).

        Returns:
            (azimuth_deg, elevation_deg, range_m)

        Reference: Montenbruck & Gill (2000) Eq. (5.58-5.60).
        """
        sta_ecef = self.ecef_position()

        # Apply Earth rotation if computing in ECI frame
        if abs(t_since_epoch_s) > 0.01:
            angle = _OMEGA_EARTH * t_since_epoch_s
            ca, sa = math.cos(angle), math.sin(angle)
            x, y = sta_ecef[0], sta_ecef[1]
            sta_ecef = np.array([x * ca - y * sa, x * sa + y * ca, sta_ecef[2]])

        delta = sat_ecef - sta_ecef  # range vector

        lat = math.radians(self.latitude_deg)
        lon = math.radians(self.longitude_deg)
        sin_lat, cos_lat = math.sin(lat), math.cos(lat)
        sin_lon, cos_lon = math.sin(lon), math.cos(lon)

        # Rotation from ECEF to topocentric (South-East-Zenith → East-North-Up)
        # SEZ frame:
        s = sin_lat * cos_lon * delta[0] + sin_lat * sin_lon * delta[1] - cos_lat * delta[2]
        e = -sin_lon * delta[0] + cos_lon * delta[1]
        z = cos_lat * cos_lon * delta[0] + cos_lat * sin_lon * delta[1] + sin_lat * delta[2]

        range_m = math.sqrt(s ** 2 + e ** 2 + z ** 2)

        # Elevation
        if range_m < 1e-10:
            return 0.0, 90.0, 0.0
        elevation_rad = math.asin(np.clip(z / range_m, -1.0, 1.0))

        # Azimuth (from North, clockwise)
        azimuth_rad = math.atan2(e, -s)  # SEZ convention
        if azimuth_rad < 0:
            azimuth_rad += 2.0 * math.pi

        return math.degrees(azimuth_rad), math.degrees(elevation_rad), range_m

    def is_visible(self, sat_ecef: np.ndarray) -> bool:
        """Check if a satellite is above the minimum elevation."""
        _, elev, _ = self.aer(sat_ecef)
        return elev >= self.min_elevation_deg

    def slant_range(self, sat_ecef: np.ndarray) -> float:
        """Distance from station to satellite [m]."""
        return float(np.linalg.norm(sat_ecef - self.ecef_position()))


@dataclass
class PassWindow:
    """A satellite pass over a ground station."""
    start_time: float       # acquisition of signal (AOS)
    end_time: float         # loss of signal (LOS)
    max_elevation_deg: float
    duration_s: float


def compute_pass_windows(
    station: GroundStation,
    sat_ecef_fn,
    t_start: float,
    t_end: float,
    dt: float = 10.0,
) -> List[PassWindow]:
    """Compute all pass windows of a satellite over a ground station.

    Args:
        station: Ground station
        sat_ecef_fn: callable(t) → (3,) satellite ECEF position [m]
        t_start: start time [s]
        t_end: end time [s]
        dt: sampling interval [s]

    Returns:
        List of PassWindow objects
    """
    passes: List[PassWindow] = []
    in_pass = False
    aos_time = 0.0
    max_elev = 0.0

    t = t_start
    while t <= t_end:
        sat_pos = sat_ecef_fn(t)
        _, elev, _ = station.aer(sat_pos)

        if elev >= station.min_elevation_deg:
            if not in_pass:
                aos_time = t
                max_elev = elev
                in_pass = True
            else:
                max_elev = max(max_elev, elev)
        else:
            if in_pass:
                passes.append(PassWindow(
                    start_time=aos_time,
                    end_time=t,
                    max_elevation_deg=max_elev,
                    duration_s=t - aos_time,
                ))
                in_pass = False

        t += dt

    # Close any open pass
    if in_pass:
        passes.append(PassWindow(
            start_time=aos_time,
            end_time=t_end,
            max_elevation_deg=max_elev,
            duration_s=t_end - aos_time,
        ))

    return passes


# ── Built-in ground stations ─────────────────────────────────────

DSN_GOLDSTONE = GroundStation("DSN Goldstone", 35.4267, -116.89, 1031, min_elevation_deg=6)
DSN_CANBERRA = GroundStation("DSN Canberra", -35.4014, 148.9817, 680, min_elevation_deg=6)
DSN_MADRID = GroundStation("DSN Madrid", 40.4314, -4.2481, 834, min_elevation_deg=6)
ISRO_ISTRAC = GroundStation("ISTRAC Bangalore", 13.0340, 77.5116, 920, min_elevation_deg=5)
ESA_ESTRACK_MALARGUE = GroundStation("ESTRACK Malargue", -35.7758, -69.3975, 1550, min_elevation_deg=5)
