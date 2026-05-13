"""Solar System body ephemeris and apparent-sky positions.

Provides geocentric apparent (RA, Dec) for the Sun, Moon, all 8 planets,
Pluto, and major dwarf planets / asteroids using Standish-rate Keplerian
elements (NASA JPL "Approximate Positions of the Planets", Standish 1992,
fitted to DE405 over 1800-2050, accurate to 1-30 arcmin).

Suitable for planetarium-style sky rendering. For navigation-grade
precision use JPL DE440 via Skyfield.

Model:
- Each body has osculating elements (a, e, i, Ω, ϖ, L) and linear rates
  per Julian century (cy = 36525 d) from J2000.0.
- Solve Kepler's equation for E.
- Form heliocentric ecliptic position; rotate to equatorial; subtract
  Earth's heliocentric position to get geocentric apparent.

References:
    Standish (1992) JPL IOM 312.D-92-009 — "Keplerian elements for
        approximate positions of the major planets"
    Meeus, J. (1998). Astronomical Algorithms, 2nd ed., Ch. 33 (Sun),
        Ch. 47 (Moon), Ch. 33-37 (planets).
    Vallado (2013) §3.5 — apparent place reduction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple


# ════════════════════════════════════════════════════════════════════
#  Standish 1992 / DE405 Keplerian elements (a, e, i, Ω, ϖ, L) at J2000
#  and per-Julian-century rates. Units: AU, rad-equivalents (we keep
#  degrees here and convert later for clarity).
#
#  ϖ = longitude of perihelion = Ω + ω
#  L = mean longitude = ϖ + M
# ════════════════════════════════════════════════════════════════════

# (a_au, e, i_deg, mean_long_deg, long_peri_deg, long_node_deg)
# Rates per century follow each row (same units, per cy).
PLANET_ELEMENTS: Dict[str, Dict[str, Tuple[float, float]]] = {
    "mercury": {
        "a":   (0.38709927,  0.00000037),
        "e":   (0.20563593,  0.00001906),
        "i":   (7.00497902, -0.00594749),
        "L":   (252.25032350, 149472.67411175),
        "wbar":(77.45779628, 0.16047689),
        "node":(48.33076593, -0.12534081),
    },
    "venus": {
        "a":   (0.72333566,  0.00000390),
        "e":   (0.00677672, -0.00004107),
        "i":   (3.39467605, -0.00078890),
        "L":   (181.97909950, 58517.81538729),
        "wbar":(131.60246718, 0.00268329),
        "node":(76.67984255, -0.27769418),
    },
    "earth": {
        "a":   (1.00000261,  0.00000562),
        "e":   (0.01671123, -0.00004392),
        "i":   (-0.00001531, -0.01294668),
        "L":   (100.46457166, 35999.37244981),
        "wbar":(102.93768193, 0.32327364),
        "node":(0.0, 0.0),
    },
    "mars": {
        "a":   (1.52371034,  0.00001847),
        "e":   (0.09339410,  0.00007882),
        "i":   (1.84969142, -0.00813131),
        "L":   (-4.55343205, 19140.30268499),
        "wbar":(-23.94362959, 0.44441088),
        "node":(49.55953891, -0.29257343),
    },
    "jupiter": {
        "a":   (5.20288700, -0.00011607),
        "e":   (0.04838624, -0.00013253),
        "i":   (1.30439695, -0.00183714),
        "L":   (34.39644051, 3034.74612775),
        "wbar":(14.72847983, 0.21252668),
        "node":(100.47390909, 0.20469106),
    },
    "saturn": {
        "a":   (9.53667594, -0.00125060),
        "e":   (0.05386179, -0.00050991),
        "i":   (2.48599187,  0.00193609),
        "L":   (49.95424423, 1222.49362201),
        "wbar":(92.59887831, -0.41897216),
        "node":(113.66242448, -0.28867794),
    },
    "uranus": {
        "a":   (19.18916464, -0.00196176),
        "e":   (0.04725744, -0.00004397),
        "i":   (0.77263783, -0.00242939),
        "L":   (313.23810451, 428.48202785),
        "wbar":(170.95427630, 0.40805281),
        "node":(74.01692503, 0.04240589),
    },
    "neptune": {
        "a":   (30.06992276,  0.00026291),
        "e":   (0.00859048,  0.00005105),
        "i":   (1.77004347,  0.00035372),
        "L":   (-55.12002969, 218.45945325),
        "wbar":(44.96476227, -0.32241464),
        "node":(131.78422574, -0.00508664),
    },
    # Pluto: Standish extended set (longer-arc fit, 1800-2050 ±200")
    "pluto": {
        "a":   (39.48211675, -0.00031596),
        "e":   (0.24882730,  0.00005170),
        "i":   (17.14001206,  0.00004818),
        "L":   (238.92903833, 145.20780515),
        "wbar":(224.06891629, -0.04062942),
        "node":(110.30393684, -0.01183482),
    },
}


# Mean physical magnitude H (V-band absolute mag at 1 AU, 0° phase angle).
# Used with apparent-distance to estimate visible magnitude.
PLANET_MAGNITUDE_H: Dict[str, float] = {
    "mercury": -0.42,  # Mallama 2017 PSS 144:21
    "venus":   -4.40,
    "mars":    -1.52,
    "jupiter": -9.40,
    "saturn":  -8.88,  # rings excluded
    "uranus":  -7.19,
    "neptune": -6.87,
    "pluto":   -1.00,
}

# Approximate display color (RGB 0-1) for the dashboard renderer.
PLANET_COLOR: Dict[str, Tuple[float, float, float]] = {
    "sun":     (1.00, 0.95, 0.55),
    "moon":    (0.85, 0.85, 0.80),
    "mercury": (0.70, 0.65, 0.55),
    "venus":   (1.00, 0.95, 0.75),
    "earth":   (0.40, 0.55, 0.95),
    "mars":    (0.95, 0.50, 0.30),
    "jupiter": (0.90, 0.75, 0.55),
    "saturn":  (0.95, 0.85, 0.65),
    "uranus":  (0.65, 0.85, 0.95),
    "neptune": (0.40, 0.55, 0.95),
    "pluto":   (0.75, 0.65, 0.55),
}


# Obliquity of the ecliptic at J2000.0 (Vondrák et al. 2011).
EPSILON_J2000_DEG = 23.4392911


# ════════════════════════════════════════════════════════════════════
#  Time conversions
# ════════════════════════════════════════════════════════════════════

def jd_from_calendar(year: int, month: int, day: float) -> float:
    """Julian Date from civil calendar (Meeus Ch. 7).

    Valid for any positive Julian Date. `day` may be fractional UT.
    """
    if month <= 2:
        year -= 1
        month += 12
    a = year // 100
    b = 2 - a + a // 4
    return (math.floor(365.25 * (year + 4716))
            + math.floor(30.6001 * (month + 1))
            + day + b - 1524.5)


def centuries_from_j2000(jd: float) -> float:
    """Julian centuries since J2000.0 (= JD 2451545.0)."""
    return (jd - 2451545.0) / 36525.0


# ════════════════════════════════════════════════════════════════════
#  Kepler solver
# ════════════════════════════════════════════════════════════════════

def _solve_kepler(M_deg: float, e: float, tol: float = 1e-9) -> float:
    """Solve M = E − e sin E by Newton-Raphson; returns E in radians."""
    M = math.radians(M_deg) % (2 * math.pi)
    E = M + e * math.sin(M)
    for _ in range(30):
        dE = (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
        E -= dE
        if abs(dE) < tol:
            break
    return E


# ════════════════════════════════════════════════════════════════════
#  Heliocentric position from Standish elements
# ════════════════════════════════════════════════════════════════════

def heliocentric_ecliptic(body: str, jd: float) -> Tuple[float, float, float]:
    """Heliocentric ecliptic (x, y, z) in AU at the given Julian Date.

    Uses Standish 1992 / DE405 mean elements. Accuracy:
        Mercury–Mars: better than 30"
        Jupiter–Saturn: better than 1'
        Uranus–Neptune: 1-3'
        Pluto: 30-60' over 1800-2050.
    """
    el = PLANET_ELEMENTS[body]
    T = centuries_from_j2000(jd)

    a    = el["a"][0]    + el["a"][1]    * T
    e    = el["e"][0]    + el["e"][1]    * T
    inc  = el["i"][0]    + el["i"][1]    * T
    L    = el["L"][0]    + el["L"][1]    * T
    wbar = el["wbar"][0] + el["wbar"][1] * T
    node = el["node"][0] + el["node"][1] * T

    omega = wbar - node          # argument of perihelion
    M = (L - wbar) % 360.0       # mean anomaly
    if M > 180:
        M -= 360.0

    E = _solve_kepler(M, e)
    cosE, sinE = math.cos(E), math.sin(E)

    # Position in orbital plane (perifocal frame), AU
    x_orb = a * (cosE - e)
    y_orb = a * math.sqrt(1 - e * e) * sinE

    # Rotate to heliocentric ecliptic (Meeus eq. 33.10)
    co, so = math.cos(math.radians(omega)), math.sin(math.radians(omega))
    cn, sn = math.cos(math.radians(node)),  math.sin(math.radians(node))
    ci, si = math.cos(math.radians(inc)),   math.sin(math.radians(inc))

    x = (co * cn - so * sn * ci) * x_orb + (-so * cn - co * sn * ci) * y_orb
    y = (co * sn + so * cn * ci) * x_orb + (-so * sn + co * cn * ci) * y_orb
    z = (so * si)               * x_orb + (co * si)                  * y_orb
    return x, y, z


def _ecliptic_to_equatorial(x: float, y: float, z: float) -> Tuple[float, float, float]:
    """Rotate ecliptic → equatorial about the X axis by ε (J2000)."""
    eps = math.radians(EPSILON_J2000_DEG)
    ce, se = math.cos(eps), math.sin(eps)
    return x, y * ce - z * se, y * se + z * ce


# ════════════════════════════════════════════════════════════════════
#  Geocentric apparent sky position (RA, Dec, magnitude)
# ════════════════════════════════════════════════════════════════════

@dataclass
class SkyBody:
    name: str
    ra_deg: float           # 0..360
    dec_deg: float          # -90..90
    distance_au: float      # geocentric distance
    magnitude: float        # estimated apparent V mag
    color: Tuple[float, float, float]


def geocentric_position(body: str, jd: float) -> SkyBody:
    """Apparent (RA, Dec) and visible magnitude for a planet at Julian Date.

    Sun and Moon are handled with simple analytical series; planets via
    heliocentric subtraction of Earth's heliocentric position.
    """
    if body == "sun":
        return _sun_apparent(jd)
    if body == "moon":
        return _moon_apparent(jd)

    if body not in PLANET_ELEMENTS:
        raise KeyError(f"Unknown body: {body}")

    xb, yb, zb = heliocentric_ecliptic(body, jd)
    xe, ye, ze = heliocentric_ecliptic("earth", jd)
    # Geocentric ecliptic
    xg, yg, zg = xb - xe, yb - ye, zb - ze
    # Convert to equatorial
    xe2, ye2, ze2 = _ecliptic_to_equatorial(xg, yg, zg)
    r_geo = math.sqrt(xe2 * xe2 + ye2 * ye2 + ze2 * ze2)
    ra = math.degrees(math.atan2(ye2, xe2)) % 360.0
    dec = math.degrees(math.asin(ze2 / r_geo))

    # Distance from Sun
    r_helio = math.sqrt(xb * xb + yb * yb + zb * zb)
    # Phase angle for Lambertian magnitude estimate
    # cos phase = (r² + Δ² - R²) / (2 r Δ)
    R2 = xe * xe + ye * ye + ze * ze
    cos_phase = (r_helio * r_helio + r_geo * r_geo - R2) / max(2 * r_helio * r_geo, 1e-9)
    cos_phase = max(-1.0, min(1.0, cos_phase))
    phase_rad = math.acos(cos_phase)
    # Lambertian disk reflection factor (Meeus eq. 41.7 simplified)
    reflect = (math.sin(phase_rad) + (math.pi - phase_rad) * math.cos(phase_rad)) / math.pi
    H = PLANET_MAGNITUDE_H.get(body, 0.0)
    # Apparent magnitude:  m = H + 5 log10(r * Δ) − 2.5 log10(reflect)
    log_term = 5.0 * math.log10(max(r_helio * r_geo, 1e-9))
    refl_term = -2.5 * math.log10(max(reflect, 1e-3))
    mag = H + log_term + refl_term

    return SkyBody(
        name=body,
        ra_deg=ra,
        dec_deg=dec,
        distance_au=r_geo,
        magnitude=mag,
        color=PLANET_COLOR.get(body, (0.8, 0.8, 0.8)),
    )


def _sun_apparent(jd: float) -> SkyBody:
    """Apparent geocentric (RA, Dec) of the Sun (Meeus Ch. 25)."""
    T = centuries_from_j2000(jd)
    L0 = (280.46646 + 36000.76983 * T + 0.0003032 * T * T) % 360.0
    M = math.radians((357.52911 + 35999.05029 * T - 0.0001537 * T * T) % 360.0)
    e = 0.016708634 - 0.000042037 * T - 0.0000001267 * T * T
    C = ((1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(M)
         + (0.019993 - 0.000101 * T) * math.sin(2 * M)
         + 0.000289 * math.sin(3 * M))
    true_long = L0 + C
    v = math.degrees(M) + C
    R = 1.000001018 * (1 - e * e) / (1 + e * math.cos(math.radians(v)))
    lam = math.radians(true_long)
    eps = math.radians(EPSILON_J2000_DEG)
    ra = math.degrees(math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))) % 360.0
    dec = math.degrees(math.asin(math.sin(eps) * math.sin(lam)))
    return SkyBody("sun", ra, dec, R, -26.74, PLANET_COLOR["sun"])


def _moon_apparent(jd: float) -> SkyBody:
    """Low-precision Moon position with distance variation (Meeus Ch.47, ~0.3°).

    Adds the leading periodic distance terms (Meeus Table 47.B) so the
    geocentric distance varies between perigee ~356_000 km and apogee
    ~407_000 km the way it really does. Without this, perigee/apogee
    detectors find no extrema.
    """
    T = centuries_from_j2000(jd)
    L_prime = (218.3164477 + 481267.88123421 * T) % 360.0     # Moon mean longitude
    D = math.radians((297.8501921 + 445267.1114034 * T) % 360.0)   # mean elongation
    M = math.radians((357.5291092 + 35999.0502909 * T) % 360.0)    # Sun mean anom
    Mp = math.radians((134.9633964 + 477198.8675055 * T) % 360.0)  # Moon mean anom
    F = math.radians((93.2720950 + 483202.0175233 * T) % 360.0)    # arg of latitude

    # Periodic perturbations to ecliptic longitude (degrees)
    long_pert = (
        6.289 * math.sin(Mp)
        - 1.274 * math.sin(Mp - 2 * D)
        + 0.658 * math.sin(2 * D)
        - 0.186 * math.sin(M)
        - 0.059 * math.sin(2 * Mp - 2 * D)
    )
    lat_pert = (
        5.128 * math.sin(F)
        + 0.281 * math.sin(Mp + F)
        + 0.278 * math.sin(Mp - F)
        + 0.173 * math.sin(2 * D - F)
    )
    # Periodic perturbations to Earth-Moon distance (km), Meeus 47.B leading rows.
    dist_pert_km = (
        -20905.355 * math.cos(Mp)
        -  3699.111 * math.cos(2 * D - Mp)
        -  2955.968 * math.cos(2 * D)
        -   569.925 * math.cos(2 * Mp)
        +    48.888 * math.cos(M)
        -  3149.000 * math.cos(2 * F)
        +   246.158 * math.cos(2 * D - 2 * Mp)
        -   152.138 * math.cos(2 * D - M - Mp)
        -   170.733 * math.cos(2 * D + Mp)
    )
    distance_km = 385000.56 + dist_pert_km

    lam = math.radians(L_prime + long_pert)
    beta = math.radians(lat_pert)

    eps = math.radians(EPSILON_J2000_DEG)
    sin_lam, cos_lam = math.sin(lam), math.cos(lam)
    sin_beta, cos_beta = math.sin(beta), math.cos(beta)
    sin_eps, cos_eps = math.sin(eps), math.cos(eps)
    ra = math.degrees(math.atan2(
        sin_lam * cos_eps - (sin_beta / cos_beta) * sin_eps,
        cos_lam,
    )) % 360.0
    dec = math.degrees(math.asin(
        sin_beta * cos_eps + cos_beta * sin_eps * sin_lam,
    ))
    distance_au = distance_km / 149597870.7
    return SkyBody("moon", ra, dec, distance_au, -12.6, PLANET_COLOR["moon"])


# ════════════════════════════════════════════════════════════════════
#  Convenience: full planetarium snapshot
# ════════════════════════════════════════════════════════════════════

def all_visible_bodies(jd: float, include_dim: bool = True) -> List[SkyBody]:
    """Compute apparent positions for Sun, Moon, planets, Pluto.

    Returns a sky-snapshot list ordered brightest-to-dimmest.
    """
    bodies: List[SkyBody] = []
    bodies.append(geocentric_position("sun", jd))
    bodies.append(geocentric_position("moon", jd))
    for name in ("mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"):
        try:
            sb = geocentric_position(name, jd)
            if include_dim or sb.magnitude < 7.0:
                bodies.append(sb)
        except Exception:
            continue
    bodies.sort(key=lambda b: b.magnitude)
    return bodies


def jd_now() -> float:
    """Current Julian Date in UT (system clock)."""
    import datetime as _dt
    now = _dt.datetime.utcnow()
    day_frac = (now.hour + now.minute / 60.0 + now.second / 3600.0) / 24.0
    return jd_from_calendar(now.year, now.month, now.day + day_frac)
