"""Earth-satellite Kepler propagator from TLE elements.

For Earth-orbiting satellites, this module:
1. Takes a parsed TLE (aria.simulation.tle_parser.TLE)
2. Propagates the orbit from the TLE epoch to a requested Julian Date
3. Outputs ECI position/velocity, ECEF position, and (with an observer)
   topocentric (alt, az, range)

The propagator is a **2-body Kepler with J2 secular drift** — much
simpler than full SGP4 (Hoots & Roehrich 1980) but accurate to a few km
for ISS / LEO objects within ~1 day of the TLE epoch. For longer-range
prediction or formation-flying use, swap in a full SGP4 / SDP4 backend.

References:
    Vallado (2013) Fundamentals of Astrodynamics §9.7 (J2 secular).
    Hoots, F. R. & Roehrich, R. L. (1980) Spacetrack Report #3.
    Curtis (2014) Orbital Mechanics for Engineering Students §4.6.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from aria.simulation.tle_parser import TLE


# Earth physical constants (WGS-84 / GRS80)
_MU_EARTH = 3.986004418e14   # m³/s²    (EGM-96 / WGS-84)
_R_EARTH_M = 6378137.0       # m        (WGS-84 equatorial)
_J2 = 1.08262668e-3          # Earth zonal coefficient
_OMEGA_EARTH = 7.2921150e-5  # rad/s    (IERS 2010)


# ════════════════════════════════════════════════════════════════════
#  Time conversions
# ════════════════════════════════════════════════════════════════════

def datetime_to_jd(dt: datetime) -> float:
    """Convert a datetime in UTC to Julian Date."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    secs = (dt - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds()
    return secs / 86400.0 + 2440587.5


# ════════════════════════════════════════════════════════════════════
#  Kepler solver (re-implementation for this module to avoid a circular
#  dep with solar_system.py)
# ════════════════════════════════════════════════════════════════════

def _solve_kepler(M: float, e: float, tol: float = 1e-12) -> float:
    """Newton-Raphson Kepler solver. M in radians."""
    M = M % (2 * math.pi)
    E = M + e * math.sin(M)
    for _ in range(40):
        f = E - e * math.sin(E) - M
        fp = 1 - e * math.cos(E)
        dE = -f / fp
        E += dE
        if abs(dE) < tol:
            break
    return E


# ════════════════════════════════════════════════════════════════════
#  ECI position / velocity from TLE at a given JD
# ════════════════════════════════════════════════════════════════════

@dataclass
class SatelliteState:
    """Instantaneous orbital state of a satellite."""
    jd: float
    r_eci_m: Tuple[float, float, float]    # ECI position [m]
    v_eci_mps: Tuple[float, float, float]  # ECI velocity [m/s]
    altitude_km: float                      # geocentric altitude
    speed_kmps: float                       # |v|
    period_min: float                       # orbital period


def propagate_tle(tle: TLE, jd_ut: float) -> SatelliteState:
    """Propagate a TLE from its epoch to the requested Julian Date.

    Uses 2-body Kepler with J2 secular node + arg-of-perigee + mean-anomaly
    drift (the dominant LEO long-period effect). Drag (B*) and higher-order
    perturbations are ignored — accuracy degrades to >1 km after a few
    days; refresh the TLE for any longer prediction window.
    """
    epoch_jd = datetime_to_jd(tle.epoch)
    dt_min = (jd_ut - epoch_jd) * 1440.0          # minutes since epoch
    dt_s = dt_min * 60.0

    # Mean motion in rad/s
    n0 = tle.mean_motion_rev_per_day * 2 * math.pi / 86400.0
    a = (_MU_EARTH / n0 ** 2) ** (1.0 / 3.0)
    e = tle.eccentricity
    inc = math.radians(tle.inclination_deg)
    raan0 = math.radians(tle.raan_deg)
    argp0 = math.radians(tle.arg_perigee_deg)
    M0 = math.radians(tle.mean_anomaly_deg)

    # J2 secular drifts (rad/s). Vallado eq. 9-37, 9-38, 9-39.
    p = a * (1 - e * e)
    factor = -1.5 * n0 * _J2 * (_R_EARTH_M / p) ** 2
    raan_dot = factor * math.cos(inc)
    argp_dot = -factor * (2.5 * math.sin(inc) ** 2 - 2.0)
    M_dot   = -factor * math.sqrt(1 - e * e) * (1.5 * math.sin(inc) ** 2 - 1.0)

    raan = raan0 + raan_dot * dt_s
    argp = argp0 + argp_dot * dt_s
    M    = M0    + (n0 + M_dot) * dt_s

    # Solve Kepler for true anomaly
    E = _solve_kepler(M, e)
    cosE, sinE = math.cos(E), math.sin(E)
    nu = math.atan2(math.sqrt(1 - e * e) * sinE, cosE - e)

    # Position in perifocal frame (PQW)
    r_pf = a * (1 - e * cosE)
    x_pf = r_pf * math.cos(nu)
    y_pf = r_pf * math.sin(nu)

    # Velocity in perifocal frame
    h = math.sqrt(_MU_EARTH * a * (1 - e * e))
    vx_pf = -(_MU_EARTH / h) * math.sin(nu)
    vy_pf =  (_MU_EARTH / h) * (e + math.cos(nu))

    # Rotate PQW → ECI via three-axis rotation Rz(Ω)·Rx(i)·Rz(ω)
    cR, sR = math.cos(raan), math.sin(raan)
    ci, si = math.cos(inc), math.sin(inc)
    cw, sw = math.cos(argp), math.sin(argp)

    P11 = cR * cw - sR * sw * ci
    P12 = -cR * sw - sR * cw * ci
    P21 = sR * cw + cR * sw * ci
    P22 = -sR * sw + cR * cw * ci
    P31 = sw * si
    P32 = cw * si

    rx = P11 * x_pf + P12 * y_pf
    ry = P21 * x_pf + P22 * y_pf
    rz = P31 * x_pf + P32 * y_pf

    vx = P11 * vx_pf + P12 * vy_pf
    vy = P21 * vx_pf + P22 * vy_pf
    vz = P31 * vx_pf + P32 * vy_pf

    r_mag = math.sqrt(rx * rx + ry * ry + rz * rz)
    v_mag = math.sqrt(vx * vx + vy * vy + vz * vz)
    alt_km = (r_mag - _R_EARTH_M) / 1000.0
    period_min = 2 * math.pi / n0 / 60.0

    return SatelliteState(
        jd=jd_ut,
        r_eci_m=(rx, ry, rz),
        v_eci_mps=(vx, vy, vz),
        altitude_km=alt_km,
        speed_kmps=v_mag / 1000.0,
        period_min=period_min,
    )


# ════════════════════════════════════════════════════════════════════
#  ECI ↔ ECEF (mean sidereal rotation)
# ════════════════════════════════════════════════════════════════════

def gmst_radians(jd_ut: float) -> float:
    """Greenwich Mean Sidereal Time at the given UT. Meeus eq. 12.4."""
    T = (jd_ut - 2451545.0) / 36525.0
    gmst_deg = (280.46061837
                + 360.98564736629 * (jd_ut - 2451545.0)
                + 0.000387933 * T * T
                - T * T * T / 38710000.0)
    return math.radians(gmst_deg % 360.0)


def eci_to_ecef(r_eci: Tuple[float, float, float],
                jd_ut: float) -> Tuple[float, float, float]:
    """Rotate ECI → ECEF by GMST around the +Z axis."""
    theta = gmst_radians(jd_ut)
    ct, st = math.cos(theta), math.sin(theta)
    x, y, z = r_eci
    return x * ct + y * st, -x * st + y * ct, z


def ecef_to_geodetic(r_ecef: Tuple[float, float, float]
                     ) -> Tuple[float, float, float]:
    """ECEF (m) → (lat_deg, lon_deg, alt_m) on WGS-84.

    Bowring 1985 iteration; converges in ~3 iterations for any altitude
    up to GEO.
    """
    x, y, z = r_ecef
    a = _R_EARTH_M
    f = 1.0 / 298.257223563
    e2 = 2 * f - f * f
    p = math.sqrt(x * x + y * y)
    lon = math.atan2(y, x)
    if p < 1e-6:
        lat = math.pi / 2 if z > 0 else -math.pi / 2
        return math.degrees(lat), math.degrees(lon), abs(z) - a * math.sqrt(1 - e2)
    lat = math.atan2(z, p * (1 - e2))
    alt = 0.0
    for _ in range(5):
        sin_lat = math.sin(lat)
        N = a / math.sqrt(1 - e2 * sin_lat * sin_lat)
        alt = p / math.cos(lat) - N
        new_lat = math.atan2(z, p * (1 - e2 * N / (N + alt)))
        if abs(new_lat - lat) < 1e-12:
            lat = new_lat
            break
        lat = new_lat
    return math.degrees(lat), math.degrees(lon), alt


# ════════════════════════════════════════════════════════════════════
#  Topocentric (alt, az, range) for an observer
# ════════════════════════════════════════════════════════════════════

@dataclass
class TopocentricView:
    azimuth_deg: float            # 0..360 from north through east
    altitude_deg: float           # -90..90
    range_km: float


def observer_view(state: SatelliteState, lat_deg: float, lon_deg: float,
                  obs_alt_m: float = 0.0) -> TopocentricView:
    """Convert satellite ECI state → (alt, az, range) for a ground observer."""
    # Observer ECEF
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    a = _R_EARTH_M
    f = 1.0 / 298.257223563
    e2 = 2 * f - f * f
    N = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    obs_x = (N + obs_alt_m) * math.cos(lat) * math.cos(lon)
    obs_y = (N + obs_alt_m) * math.cos(lat) * math.sin(lon)
    obs_z = (N * (1 - e2) + obs_alt_m) * math.sin(lat)

    # Satellite ECEF
    sat_x, sat_y, sat_z = eci_to_ecef(state.r_eci_m, state.jd)

    # Range vector (ECEF)
    rx = sat_x - obs_x
    ry = sat_y - obs_y
    rz = sat_z - obs_z

    # Rotate ECEF → topocentric SEZ (south, east, zenith)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    rs =  sin_lat * cos_lon * rx + sin_lat * sin_lon * ry - cos_lat * rz
    re = -sin_lon * rx + cos_lon * ry
    rz_ = cos_lat * cos_lon * rx + cos_lat * sin_lon * ry + sin_lat * rz

    rng = math.sqrt(rs * rs + re * re + rz_ * rz_)
    alt = math.degrees(math.asin(rz_ / max(rng, 1e-9)))
    # Azimuth measured from N (0°) through E (90°) — standard convention.
    az = math.degrees(math.atan2(re, -rs)) % 360.0
    return TopocentricView(azimuth_deg=az, altitude_deg=alt, range_km=rng / 1000.0)


# ════════════════════════════════════════════════════════════════════
#  Convenience: full ground-track over a time window
# ════════════════════════════════════════════════════════════════════

@dataclass
class GroundTrackPoint:
    jd: float
    lat_deg: float
    lon_deg: float
    alt_km: float


def ground_track(tle: TLE, jd_start: float, jd_end: float,
                 step_min: float = 1.0) -> List[GroundTrackPoint]:
    """Sub-satellite trace over a UT window. Step in minutes."""
    pts: List[GroundTrackPoint] = []
    jd = jd_start
    while jd <= jd_end + 1e-9:
        st = propagate_tle(tle, jd)
        ecef = eci_to_ecef(st.r_eci_m, jd)
        lat, lon, alt = ecef_to_geodetic(ecef)
        pts.append(GroundTrackPoint(jd=jd, lat_deg=lat, lon_deg=lon,
                                    alt_km=alt / 1000.0))
        jd += step_min / 1440.0
    return pts
