"""Observer-location aware sky — what's above the horizon right now.

Converts geocentric apparent (RA, Dec) to topocentric (altitude, azimuth)
for an observer at a given latitude, longitude and Julian Date. Filters
the catalogs (stars, planets, Messier, asteroids, comets, moons) by
horizon visibility and returns ready-to-render sky positions.

Coordinate convention:
- Latitude  φ (degrees, N positive, S negative)
- Longitude λ (degrees, E positive, W negative — IAU convention)
- Altitude  alt (degrees above horizon, 0..90)
- Azimuth   az  (degrees from North through East, 0..360)

References:
    Meeus, J. (1998) Astronomical Algorithms, Ch. 12 (sidereal time),
                                                Ch. 13 (transformations).
    USNO Naval Observatory Vector Astrometry Subroutines (NOVAS).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from aria.simulation.solar_system import (
    SkyBody, all_visible_bodies, geocentric_position,
)


# Standard altitudes (degrees) at which "rise" / "set" are reported.
# Negative altitudes account for the body's apparent radius and atmospheric
# refraction near the horizon (Meeus §15).
ALT_SUN_RISE_SET = -0.8333    # 34' refraction + 16' Sun semi-diameter
ALT_MOON_RISE_SET = +0.125    # 34' refraction − 16' Moon SD + 0.5° parallax
ALT_CIVIL_TWILIGHT = -6.0     # Sun centre 6° below horizon
ALT_NAUT_TWILIGHT = -12.0
ALT_ASTRO_TWILIGHT = -18.0    # full dark sky (no atmospheric scattering)


@dataclass
class HorizonPosition:
    """A body's position in the observer's sky."""
    name: str
    kind: str                 # 'sun' / 'moon' / 'planet' / 'star' / 'satellite' / 'asteroid' / 'comet' / 'messier'
    alt_deg: float            # 0..90 above horizon
    az_deg: float             # 0..360 from north through east
    ra_deg: float
    dec_deg: float
    magnitude: float
    distance_au: Optional[float] = None
    color: Tuple[float, float, float] = (1.0, 1.0, 1.0)


# ════════════════════════════════════════════════════════════════════
#  Sidereal time
# ════════════════════════════════════════════════════════════════════

def greenwich_sidereal_time_deg(jd_ut: float) -> float:
    """Greenwich Mean Sidereal Time at Julian Date (UT), in degrees [0, 360).

    Meeus eq. 12.4.
    """
    T = (jd_ut - 2451545.0) / 36525.0
    gmst = (280.46061837
            + 360.98564736629 * (jd_ut - 2451545.0)
            + 0.000387933 * T * T
            - T * T * T / 38710000.0)
    return gmst % 360.0


def local_sidereal_time_deg(jd_ut: float, longitude_deg: float) -> float:
    """Local Mean Sidereal Time. Longitude convention: East positive."""
    return (greenwich_sidereal_time_deg(jd_ut) + longitude_deg) % 360.0


# ════════════════════════════════════════════════════════════════════
#  Equatorial → horizontal
# ════════════════════════════════════════════════════════════════════

def equatorial_to_horizontal(ra_deg: float, dec_deg: float,
                             lst_deg: float, lat_deg: float
                             ) -> Tuple[float, float]:
    """Convert (RA, Dec) → (alt, az) for the given local sidereal time + lat.

    Returns:
        (alt_deg, az_deg). az_deg measured from north (0°) clockwise
        through east (90°) — standard astronomical convention.
    """
    h_deg = (lst_deg - ra_deg) % 360.0    # local hour angle, deg
    h = math.radians(h_deg)
    dec = math.radians(dec_deg)
    lat = math.radians(lat_deg)

    sin_alt = math.sin(dec) * math.sin(lat) + math.cos(dec) * math.cos(lat) * math.cos(h)
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt = math.asin(sin_alt)

    # Azimuth measured from north through east. Meeus eq. 13.6.
    cos_alt = math.cos(alt)
    if cos_alt < 1e-9:
        return math.degrees(alt), 0.0
    sin_az = -math.sin(h) * math.cos(dec) / cos_alt
    cos_az = (math.sin(dec) - math.sin(lat) * sin_alt) / (math.cos(lat) * cos_alt)
    cos_az = max(-1.0, min(1.0, cos_az))
    az = math.atan2(sin_az, cos_az)
    return math.degrees(alt), math.degrees(az) % 360.0


def is_above_horizon(ra_deg: float, dec_deg: float,
                     jd_ut: float, lat_deg: float, lon_deg: float,
                     min_alt_deg: float = -1.0) -> bool:
    """Quick visibility check — true if alt > min_alt at the given UT."""
    lst = local_sidereal_time_deg(jd_ut, lon_deg)
    alt, _ = equatorial_to_horizontal(ra_deg, dec_deg, lst, lat_deg)
    return alt > min_alt_deg


# ════════════════════════════════════════════════════════════════════
#  Atmospheric refraction (Bennett 1982)
# ════════════════════════════════════════════════════════════════════

def refraction_correction_deg(alt_deg: float) -> float:
    """Bennett 1982 refraction correction (arcmin → deg) for true altitude.

    Adds to true altitude to get apparent (observed) altitude.
    Most useful near horizon (~34' shift) and zero above 60°.
    """
    if alt_deg < -1.0:
        return 0.0
    h_rad = math.radians(alt_deg + 7.31 / (alt_deg + 4.4))
    return (1.0 / math.tan(h_rad)) / 60.0   # arcmin → deg


# ════════════════════════════════════════════════════════════════════
#  Catalog filtering — what's visible right now
# ════════════════════════════════════════════════════════════════════

def visible_planets(jd_ut: float, lat_deg: float, lon_deg: float,
                    min_alt_deg: float = 0.0) -> List[HorizonPosition]:
    """Sun, Moon, planets, Pluto currently above the horizon."""
    lst = local_sidereal_time_deg(jd_ut, lon_deg)
    out: List[HorizonPosition] = []
    for body in all_visible_bodies(jd_ut):
        alt, az = equatorial_to_horizontal(body.ra_deg, body.dec_deg, lst, lat_deg)
        if alt < min_alt_deg:
            continue
        kind = (
            "sun" if body.name == "sun" else
            "moon" if body.name == "moon" else
            "planet"
        )
        out.append(HorizonPosition(
            name=body.name, kind=kind,
            alt_deg=alt, az_deg=az,
            ra_deg=body.ra_deg, dec_deg=body.dec_deg,
            magnitude=body.magnitude,
            distance_au=body.distance_au, color=body.color,
        ))
    return out


def visible_bright_stars(jd_ut: float, lat_deg: float, lon_deg: float,
                         mag_limit: float = 4.0,
                         min_alt_deg: float = 0.0) -> List[HorizonPosition]:
    """Naked-eye bright stars currently above the horizon."""
    from aria.simulation.star_field import load_hyg, bv_to_rgb
    lst = local_sidereal_time_deg(jd_ut, lon_deg)
    out: List[HorizonPosition] = []
    for s in load_hyg():
        if s.vmag > mag_limit:
            continue
        alt, az = equatorial_to_horizontal(s.ra_deg, s.dec_deg, lst, lat_deg)
        if alt < min_alt_deg:
            continue
        rgb = bv_to_rgb(s.bv_color)
        out.append(HorizonPosition(
            name=s.name or f"HIP{s.hip_id}",
            kind="star",
            alt_deg=alt, az_deg=az,
            ra_deg=s.ra_deg, dec_deg=s.dec_deg,
            magnitude=s.vmag, color=rgb,
        ))
    return out


def visible_messier(jd_ut: float, lat_deg: float, lon_deg: float,
                    mag_limit: float = 8.0,
                    min_alt_deg: float = 0.0) -> List[HorizonPosition]:
    """Messier deep-sky objects above the horizon."""
    from aria.simulation.messier import visible_messier as _visible
    lst = local_sidereal_time_deg(jd_ut, lon_deg)
    out: List[HorizonPosition] = []
    for m in _visible(mag_limit):
        alt, az = equatorial_to_horizontal(m.ra_deg, m.dec_deg, lst, lat_deg)
        if alt < min_alt_deg:
            continue
        out.append(HorizonPosition(
            name=f"M{m.m} {m.name or m.ngc}",
            kind="messier",
            alt_deg=alt, az_deg=az,
            ra_deg=m.ra_deg, dec_deg=m.dec_deg,
            magnitude=m.vmag, color=(0.7, 0.5, 0.85),
        ))
    return out


def sky_snapshot(jd_ut: float, lat_deg: float, lon_deg: float,
                 mag_limit_stars: float = 4.5,
                 mag_limit_dso: float = 8.0,
                 min_alt_deg: float = 0.0) -> Dict[str, List[HorizonPosition]]:
    """One-call snapshot of everything above the horizon for an observer."""
    return {
        "planets": visible_planets(jd_ut, lat_deg, lon_deg, min_alt_deg),
        "stars":   visible_bright_stars(jd_ut, lat_deg, lon_deg, mag_limit_stars, min_alt_deg),
        "messier": visible_messier(jd_ut, lat_deg, lon_deg, mag_limit_dso, min_alt_deg),
    }


# ════════════════════════════════════════════════════════════════════
#  Major city presets for the UI
# ════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════
#  Rise / set / twilight — bisection on altitude(t)
# ════════════════════════════════════════════════════════════════════

@dataclass
class DayConditions:
    """Sun/Moon timing for an observer's day-of-interest."""
    sunrise_jd: Optional[float]
    sunset_jd:  Optional[float]
    solar_noon_jd: Optional[float]
    civil_twilight_dawn_jd: Optional[float]
    civil_twilight_dusk_jd: Optional[float]
    astro_twilight_dawn_jd: Optional[float]
    astro_twilight_dusk_jd: Optional[float]
    moonrise_jd: Optional[float]
    moonset_jd:  Optional[float]
    moon_phase_fraction: float        # 0..1 illuminated fraction
    moon_phase_label: str             # 'New' / 'Waxing crescent' / ...
    moon_age_days: float              # 0..29.5 days from new


def _altitude_of(body: str, jd: float, lat: float, lon: float) -> float:
    """Apparent altitude (deg) of body at given UT for an observer."""
    pos = geocentric_position(body, jd)
    lst = local_sidereal_time_deg(jd, lon)
    alt, _ = equatorial_to_horizontal(pos.ra_deg, pos.dec_deg, lst, lat)
    return alt


def _find_altitude_crossing(body: str, jd_lo: float, jd_hi: float,
                            target_alt: float, lat: float, lon: float,
                            ascending: bool, tol_d: float = 1.0/1440) -> Optional[float]:
    """Bisection search for time when alt(body) = target_alt within [jd_lo, jd_hi].

    `ascending=True` looks for a transition from below→above; otherwise above→below.
    Returns None if no crossing exists in the interval.
    """
    f_lo = _altitude_of(body, jd_lo, lat, lon) - target_alt
    f_hi = _altitude_of(body, jd_hi, lat, lon) - target_alt
    # Sign agnostic — we just need a sign change.
    if f_lo * f_hi > 0:
        return None
    while jd_hi - jd_lo > tol_d:
        mid = 0.5 * (jd_lo + jd_hi)
        f_mid = _altitude_of(body, mid, lat, lon) - target_alt
        if f_lo * f_mid <= 0:
            jd_hi, f_hi = mid, f_mid
        else:
            jd_lo, f_lo = mid, f_mid
    return 0.5 * (jd_lo + jd_hi)


def _scan_altitude_crossing(body: str, jd_start: float, jd_end: float,
                            target_alt: float, lat: float, lon: float,
                            ascending: bool, n_samples: int = 96) -> Optional[float]:
    """Coarse-then-fine search for the first ascending/descending crossing
    of target_alt in [jd_start, jd_end]. Returns crossing JD or None.
    """
    times = [jd_start + (jd_end - jd_start) * k / n_samples for k in range(n_samples + 1)]
    last_alt = _altitude_of(body, times[0], lat, lon)
    for i in range(1, len(times)):
        cur_alt = _altitude_of(body, times[i], lat, lon)
        going_up = cur_alt > last_alt
        crosses = (last_alt - target_alt) * (cur_alt - target_alt) < 0
        if crosses and going_up == ascending:
            jd = _find_altitude_crossing(body, times[i - 1], times[i],
                                         target_alt, lat, lon, ascending)
            if jd is not None:
                return jd
        last_alt = cur_alt
    return None


def _solar_noon(jd_start: float, jd_end: float,
                lat: float, lon: float) -> Optional[float]:
    """Time of Sun's upper transit (highest altitude) within the window."""
    # Sample 24 points and refine the maximum.
    n = 48
    best_jd = None
    best_alt = -91.0
    for k in range(n + 1):
        jd = jd_start + (jd_end - jd_start) * k / n
        alt = _altitude_of("sun", jd, lat, lon)
        if alt > best_alt:
            best_alt = alt
            best_jd = jd
    if best_jd is None:
        return None
    # Golden-section refine
    GR = (math.sqrt(5) - 1) / 2.0
    half = (jd_end - jd_start) / n
    a, b = best_jd - half, best_jd + half
    c = b - GR * (b - a)
    d = a + GR * (b - a)
    fc, fd = -_altitude_of("sun", c, lat, lon), -_altitude_of("sun", d, lat, lon)
    while abs(b - a) > 1.0 / 1440:
        if fc < fd:
            b = d
        else:
            a = c
        c = b - GR * (b - a)
        d = a + GR * (b - a)
        fc, fd = -_altitude_of("sun", c, lat, lon), -_altitude_of("sun", d, lat, lon)
    return 0.5 * (a + b)


def _moon_phase(jd: float) -> Tuple[float, str, float]:
    """Returns (illuminated_fraction, label, age_days)."""
    sun = geocentric_position("sun", jd)
    moon = geocentric_position("moon", jd)
    # Phase angle: angle Sun-Moon-observer ≈ elongation supplement.
    elongation_rad = math.radians(_ang_sep_basic(
        sun.ra_deg, sun.dec_deg, moon.ra_deg, moon.dec_deg))
    illum = 0.5 * (1 - math.cos(elongation_rad))    # cosine illumination law

    # Phase age via mean longitude difference.
    # Ecliptic longitude of Sun and Moon (approximate).
    lambda_sun = math.atan2(
        math.sin(math.radians(sun.ra_deg)) * math.cos(math.radians(EPSILON_J2000_DEG)),
        math.cos(math.radians(sun.ra_deg))) * 180 / math.pi
    lambda_moon = math.atan2(
        math.sin(math.radians(moon.ra_deg)) * math.cos(math.radians(EPSILON_J2000_DEG)),
        math.cos(math.radians(moon.ra_deg))) * 180 / math.pi
    elong_lon = (lambda_moon - lambda_sun) % 360.0
    age = elong_lon / 360.0 * 29.530589   # synodic month length

    if elong_lon < 1 or elong_lon > 359:
        label = "New"
    elif elong_lon < 90:
        label = "Waxing crescent"
    elif abs(elong_lon - 90) < 1:
        label = "First quarter"
    elif elong_lon < 180:
        label = "Waxing gibbous"
    elif abs(elong_lon - 180) < 1:
        label = "Full"
    elif elong_lon < 270:
        label = "Waning gibbous"
    elif abs(elong_lon - 270) < 1:
        label = "Last quarter"
    else:
        label = "Waning crescent"
    return illum, label, age


def _ang_sep_basic(ra1, dec1, ra2, dec2):
    """Local copy of angular separation to avoid circular import."""
    a1, a2 = math.radians(ra1), math.radians(ra2)
    d1, d2 = math.radians(dec1), math.radians(dec2)
    cos_sep = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(a1 - a2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_sep))))


# Need the same obliquity constant the solar_system module uses.
from aria.simulation.solar_system import EPSILON_J2000_DEG  # noqa: E402


def day_conditions(jd_ut: float, lat_deg: float, lon_deg: float,
                   window_h: float = 30.0) -> DayConditions:
    """Compute sunrise/sunset/twilight/moonrise + moon phase around jd_ut.

    Searches a ±window_h hour window so we always catch the next/prev
    crossings even for high-latitude sites where the Sun may not rise
    or set on a given day. Polar non-events return None for those fields.
    """
    half = window_h / 24.0 / 2.0
    jd0 = jd_ut - half
    jd1 = jd_ut + half

    sunrise = _scan_altitude_crossing("sun", jd0, jd1, ALT_SUN_RISE_SET,
                                      lat_deg, lon_deg, ascending=True)
    sunset = _scan_altitude_crossing("sun", jd0, jd1, ALT_SUN_RISE_SET,
                                     lat_deg, lon_deg, ascending=False)
    civil_dawn = _scan_altitude_crossing("sun", jd0, jd1, ALT_CIVIL_TWILIGHT,
                                         lat_deg, lon_deg, ascending=True)
    civil_dusk = _scan_altitude_crossing("sun", jd0, jd1, ALT_CIVIL_TWILIGHT,
                                         lat_deg, lon_deg, ascending=False)
    astro_dawn = _scan_altitude_crossing("sun", jd0, jd1, ALT_ASTRO_TWILIGHT,
                                         lat_deg, lon_deg, ascending=True)
    astro_dusk = _scan_altitude_crossing("sun", jd0, jd1, ALT_ASTRO_TWILIGHT,
                                         lat_deg, lon_deg, ascending=False)
    noon = _solar_noon(jd0, jd1, lat_deg, lon_deg)
    moonrise = _scan_altitude_crossing("moon", jd0, jd1, ALT_MOON_RISE_SET,
                                       lat_deg, lon_deg, ascending=True)
    moonset = _scan_altitude_crossing("moon", jd0, jd1, ALT_MOON_RISE_SET,
                                      lat_deg, lon_deg, ascending=False)
    illum, label, age = _moon_phase(jd_ut)

    return DayConditions(
        sunrise_jd=sunrise, sunset_jd=sunset, solar_noon_jd=noon,
        civil_twilight_dawn_jd=civil_dawn, civil_twilight_dusk_jd=civil_dusk,
        astro_twilight_dawn_jd=astro_dawn, astro_twilight_dusk_jd=astro_dusk,
        moonrise_jd=moonrise, moonset_jd=moonset,
        moon_phase_fraction=illum, moon_phase_label=label,
        moon_age_days=age,
    )


CITIES: Dict[str, Tuple[float, float]] = {
    # name -> (lat_deg, lon_deg E)
    "Bengaluru":     ( 12.9716,  77.5946),
    "New Delhi":     ( 28.6139,  77.2090),
    "Mumbai":        ( 19.0760,  72.8777),
    "London":        ( 51.5074,  -0.1278),
    "New York":      ( 40.7128, -74.0060),
    "San Francisco": ( 37.7749, -122.4194),
    "Tokyo":         ( 35.6762, 139.6503),
    "Sydney":        (-33.8688, 151.2093),
    "Cape Town":     (-33.9249,  18.4241),
    "Reykjavík":     ( 64.1466, -21.9426),
    "Quito":         ( -0.1807, -78.4678),
    "South Pole":    (-90.0000,   0.0000),
    "North Pole":    ( 90.0000,   0.0000),
    "Equator/0°":    (  0.0000,   0.0000),
}
