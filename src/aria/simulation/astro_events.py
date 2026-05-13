"""Astronomical event detector — find observable phenomena over a date range.

Given a start/end Julian Date, scans coarse-then-fine for these events:

- **Opposition**: elongation Sun↔planet ≈ 180° (best viewing for outer planets)
- **Greatest elongation**: max angular separation Sun↔Mercury or Sun↔Venus
- **Inferior / superior conjunction**: inner planet directly between or behind Sun
- **Conjunction (planet pairs)**: local minimum of angular separation
- **Perihelion**: local minimum of heliocentric distance for any body
- **Comet perihelion**: same, restricted to the comet catalog
- **Lunar perigee / apogee**: extrema of Moon-Earth distance
- **Eclipse window** (rough): Sun-Moon-Earth alignment near node

Algorithm: each detector samples its target metric on a coarse grid
(typically 1 day for planets, 1 hour for the Moon), finds local
extrema, then golden-section refines the time of each extremum to ~1
minute. No Sun aberration / planetary rotation accounted for.

References:
    Meeus, J. (1998) Astronomical Algorithms, 2nd ed., Ch. 36 (planet
        positions), Ch. 47 (Moon), Ch. 38 (oppositions).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from aria.simulation.solar_system import (
    geocentric_position, heliocentric_ecliptic, _ecliptic_to_equatorial,
    PLANET_ELEMENTS,
)
from aria.simulation.small_bodies import COMETS, geocentric_smallbody, _helio_smallbody


# Solar / lunar physical radii (km) — used for eclipse-type discrimination.
# Sun: IAU 2015 nominal solar radius
# Moon: USGS mean equatorial radius
_R_SUN_KM = 695_700.0          # IAU 2015 Resolution B3
_R_MOON_KM = 1_737.4           # NASA NSSDCA Moon fact sheet
_R_EARTH_KM = 6_378.137        # WGS-84 equatorial
_AU_KM = 149_597_870.7


@dataclass
class AstroEvent:
    """A single sky event with its time and human-readable description."""
    jd: float
    kind: str         # 'opposition', 'conjunction', 'perihelion', 'gr_elongation', 'perigee', 'apogee'
    body: str
    body2: Optional[str] = None      # for conjunctions / oppositions
    value: float = 0.0               # event-specific (degrees, AU, etc.)
    description: str = ""


# ════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════

def _angular_sep_deg(ra1, dec1, ra2, dec2) -> float:
    """Great-circle separation between two equatorial coordinates."""
    a1, a2 = math.radians(ra1), math.radians(ra2)
    d1, d2 = math.radians(dec1), math.radians(dec2)
    cos_sep = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(a1 - a2)
    cos_sep = max(-1.0, min(1.0, cos_sep))
    return math.degrees(math.acos(cos_sep))


def _refine_extremum(metric: Callable[[float], float], jd_lo: float, jd_hi: float,
                     find_min: bool = True, tol_d: float = 1.0 / 1440) -> float:
    """Golden-section search for the extremum of metric(jd) inside [jd_lo, jd_hi].

    tol_d defaults to ~1 minute. Returns the JD of the extremum.
    """
    GR = (math.sqrt(5) - 1) / 2.0
    a, b = jd_lo, jd_hi
    c = b - GR * (b - a)
    d = a + GR * (b - a)
    fc, fd = metric(c), metric(d)
    sign = 1 if find_min else -1
    while abs(b - a) > tol_d:
        if sign * fc < sign * fd:
            b = d
        else:
            a = c
        c = b - GR * (b - a)
        d = a + GR * (b - a)
        fc, fd = metric(c), metric(d)
    return 0.5 * (a + b)


def _scan_extrema(metric: Callable[[float], float], start_jd: float, end_jd: float,
                  step_d: float, find_min: bool = True) -> List[float]:
    """Coarse scan for sign changes in the derivative of metric(jd).

    Returns refined JDs of all interior local extrema. Endpoints excluded
    so we don't false-trigger on monotone trends.
    """
    out: List[float] = []
    n = max(3, int(math.ceil((end_jd - start_jd) / step_d)) + 1)
    times = [start_jd + (end_jd - start_jd) * k / (n - 1) for k in range(n)]
    vals = [metric(t) for t in times]
    for i in range(1, n - 1):
        is_min = vals[i] < vals[i - 1] and vals[i] < vals[i + 1]
        is_max = vals[i] > vals[i - 1] and vals[i] > vals[i + 1]
        target_hit = is_min if find_min else is_max
        if target_hit:
            jd_ref = _refine_extremum(metric, times[i - 1], times[i + 1],
                                      find_min=find_min)
            out.append(jd_ref)
    return out


# ════════════════════════════════════════════════════════════════════
#  Detectors
# ════════════════════════════════════════════════════════════════════

OUTER_PLANETS = ("mars", "jupiter", "saturn", "uranus", "neptune")
INNER_PLANETS = ("mercury", "venus")


def find_oppositions(start_jd: float, end_jd: float,
                     step_d: float = 5.0) -> List[AstroEvent]:
    """An outer planet is at opposition when Sun-Earth-planet ≈ 180°.

    Equivalent: the heliocentric ecliptic longitude difference Earth↔planet
    crosses zero. Coarse scan on (Δλ mod 360 - 180), refine to elongation peak.
    """
    out: List[AstroEvent] = []
    for body in OUTER_PLANETS:
        def elongation(jd: float, b=body) -> float:
            sun = geocentric_position("sun", jd)
            pl = geocentric_position(b, jd)
            return _angular_sep_deg(sun.ra_deg, sun.dec_deg,
                                    pl.ra_deg, pl.dec_deg)
        # Find local maxima of geocentric elongation (peaks at 180°).
        for jd in _scan_extrema(elongation, start_jd, end_jd, step_d, find_min=False):
            elo = elongation(jd)
            if elo > 150.0:
                out.append(AstroEvent(
                    jd=jd, kind="opposition", body=body, body2="sun",
                    value=elo,
                    description=f"{body.capitalize()} opposition (elongation {elo:.1f}°)",
                ))
    return out


def find_greatest_elongations(start_jd: float, end_jd: float,
                              step_d: float = 2.0) -> List[AstroEvent]:
    """Mercury / Venus reach greatest east/west elongation.

    Local maxima of geocentric Sun↔planet angular separation.
    """
    out: List[AstroEvent] = []
    for body in INNER_PLANETS:
        def elongation(jd: float, b=body) -> float:
            sun = geocentric_position("sun", jd)
            pl = geocentric_position(b, jd)
            return _angular_sep_deg(sun.ra_deg, sun.dec_deg,
                                    pl.ra_deg, pl.dec_deg)
        for jd in _scan_extrema(elongation, start_jd, end_jd, step_d, find_min=False):
            elo = elongation(jd)
            # Determine east/west by ecliptic longitude difference.
            sun = geocentric_position("sun", jd)
            pl = geocentric_position(body, jd)
            d_ra = (pl.ra_deg - sun.ra_deg) % 360
            side = "east (evening sky)" if 0 < d_ra < 180 else "west (morning sky)"
            out.append(AstroEvent(
                jd=jd, kind="gr_elongation", body=body, body2="sun",
                value=elo,
                description=f"{body.capitalize()} greatest {side}, elongation {elo:.1f}°",
            ))
    return out


def find_inferior_conjunctions(start_jd: float, end_jd: float,
                               step_d: float = 2.0) -> List[AstroEvent]:
    """Mercury/Venus pass between Earth and Sun (elongation → 0°)."""
    out: List[AstroEvent] = []
    for body in INNER_PLANETS:
        def elongation(jd: float, b=body) -> float:
            sun = geocentric_position("sun", jd)
            pl = geocentric_position(b, jd)
            return _angular_sep_deg(sun.ra_deg, sun.dec_deg,
                                    pl.ra_deg, pl.dec_deg)
        for jd in _scan_extrema(elongation, start_jd, end_jd, step_d, find_min=True):
            elo = elongation(jd)
            if elo < 10.0:
                pl = geocentric_position(body, jd)
                # Inferior vs superior: compare distance to 1 AU
                kind_label = "inferior" if pl.distance_au < 1.0 else "superior"
                out.append(AstroEvent(
                    jd=jd, kind=f"{kind_label}_conjunction", body=body, body2="sun",
                    value=elo,
                    description=f"{body.capitalize()} {kind_label} conjunction "
                                f"(separation {elo:.2f}°)",
                ))
    return out


def find_planet_pair_conjunctions(start_jd: float, end_jd: float,
                                  step_d: float = 1.0,
                                  threshold_deg: float = 5.0) -> List[AstroEvent]:
    """Close approaches between any two visible planets (≤ threshold)."""
    out: List[AstroEvent] = []
    bodies = ("mercury", "venus", "mars", "jupiter", "saturn")
    for i, a in enumerate(bodies):
        for b in bodies[i + 1:]:
            def sep(jd: float, A=a, B=b) -> float:
                pa = geocentric_position(A, jd)
                pb = geocentric_position(B, jd)
                return _angular_sep_deg(pa.ra_deg, pa.dec_deg,
                                        pb.ra_deg, pb.dec_deg)
            for jd in _scan_extrema(sep, start_jd, end_jd, step_d, find_min=True):
                d = sep(jd)
                if d <= threshold_deg:
                    out.append(AstroEvent(
                        jd=jd, kind="planet_conjunction", body=a, body2=b, value=d,
                        description=f"{a.capitalize()}–{b.capitalize()} conjunction "
                                    f"({d:.2f}°)",
                    ))
    return out


def find_perihelia(start_jd: float, end_jd: float,
                   bodies: Optional[Tuple[str, ...]] = None,
                   step_d: float = 1.0) -> List[AstroEvent]:
    """Heliocentric distance minima for selected planets."""
    if bodies is None:
        bodies = tuple(PLANET_ELEMENTS.keys())
    out: List[AstroEvent] = []
    for body in bodies:
        def r_helio(jd: float, b=body) -> float:
            x, y, z = heliocentric_ecliptic(b, jd)
            return math.sqrt(x * x + y * y + z * z)
        for jd in _scan_extrema(r_helio, start_jd, end_jd, step_d, find_min=True):
            d_au = r_helio(jd)
            out.append(AstroEvent(
                jd=jd, kind="perihelion", body=body, value=d_au,
                description=f"{body.capitalize()} perihelion at {d_au:.4f} AU",
            ))
    return out


def find_comet_perihelia(start_jd: float, end_jd: float,
                         step_d: float = 1.0) -> List[AstroEvent]:
    """Comets reaching perihelion in the date range — great viewing windows."""
    out: List[AstroEvent] = []
    for c in COMETS:
        def r(jd: float, comet=c) -> float:
            pos = _helio_smallbody(comet, jd)
            if pos is None:
                return 1e9
            return math.sqrt(pos[0] ** 2 + pos[1] ** 2 + pos[2] ** 2)
        for jd in _scan_extrema(r, start_jd, end_jd, step_d, find_min=True):
            d = r(jd)
            if d > 50:        # too distant to be observable / element drift
                continue
            sb = geocentric_smallbody(c, jd)
            mag = sb.magnitude if sb else 0.0
            out.append(AstroEvent(
                jd=jd, kind="comet_perihelion", body=c.name, value=d,
                description=f"{c.name} perihelion ({d:.3f} AU, V≈{mag:.1f})",
            ))
    return out


def find_lunar_extrema(start_jd: float, end_jd: float,
                       step_d: float = 0.25) -> List[AstroEvent]:
    """Moon perigee (closest) and apogee (farthest) from Earth."""
    def moon_dist(jd: float) -> float:
        return geocentric_position("moon", jd).distance_au
    out: List[AstroEvent] = []
    for jd in _scan_extrema(moon_dist, start_jd, end_jd, step_d, find_min=True):
        out.append(AstroEvent(jd=jd, kind="perigee", body="moon",
                              value=moon_dist(jd) * 149597870.7,
                              description=f"Lunar perigee ({moon_dist(jd) * 149597870.7:.0f} km)"))
    for jd in _scan_extrema(moon_dist, start_jd, end_jd, step_d, find_min=False):
        out.append(AstroEvent(jd=jd, kind="apogee", body="moon",
                              value=moon_dist(jd) * 149597870.7,
                              description=f"Lunar apogee ({moon_dist(jd) * 149597870.7:.0f} km)"))
    return out


# ════════════════════════════════════════════════════════════════════
#  Eclipse detection (lunar + solar)
# ════════════════════════════════════════════════════════════════════

def _sun_moon_geometry(jd: float):
    """Return (sun, moon, sep_deg) where sep_deg is geocentric Sun↔Moon."""
    sun = geocentric_position("sun", jd)
    moon = geocentric_position("moon", jd)
    sep = _angular_sep_deg(sun.ra_deg, sun.dec_deg, moon.ra_deg, moon.dec_deg)
    return sun, moon, sep


def _apparent_semidiameter_deg(radius_km: float, distance_au: float) -> float:
    """Apparent semi-diameter (half angular size) of a body at given distance."""
    if distance_au <= 0:
        return 0.0
    distance_km = distance_au * _AU_KM
    return math.degrees(math.asin(min(1.0, radius_km / distance_km)))


def find_solar_eclipses(start_jd: float, end_jd: float,
                        step_d: float = 0.5) -> List[AstroEvent]:
    """Find solar eclipse maxima (Moon passes near or in front of Sun).

    Geocentric heuristic: when Sun↔Moon angular separation is within
    Sun_SD + Moon_SD AND ecliptic latitude alignment is small enough that
    *some* observer on Earth sees an eclipse, an event is reported.

    Returns events with kind="solar_eclipse" and a value field giving the
    minimum separation in arc-min. Type (total/annular/partial) is
    described in `description` based on apparent diameter ratio.

    This is a geocentric eclipse predictor — local circumstances (which
    cities see totality) require the more involved Besselian elements
    treatment which is out of scope here.
    """
    out: List[AstroEvent] = []

    def _sep(jd: float) -> float:
        _, _, s = _sun_moon_geometry(jd)
        return s

    # Lunar synodic month ~29.5 d; sample finer than that to catch each pass.
    for jd in _scan_extrema(_sep, start_jd, end_jd, step_d, find_min=True):
        sun, moon, sep_deg = _sun_moon_geometry(jd)
        sun_sd = _apparent_semidiameter_deg(_R_SUN_KM, sun.distance_au)
        moon_sd = _apparent_semidiameter_deg(_R_MOON_KM, moon.distance_au)
        # Geocentric eclipse window: separation < sum of semidiameters
        # PLUS ~1° tolerance for Earth's parallax (Moon parallax ~57').
        gamma = sep_deg
        threshold = sun_sd + moon_sd + 1.0   # parallax + a small margin
        if gamma > threshold:
            continue

        # Eclipse type: compare apparent disk radii. If moon disk fully
        # covers sun: total. If sun's annulus shows around moon: annular.
        # Otherwise partial.
        if moon_sd >= sun_sd and gamma < (moon_sd - sun_sd):
            etype = "total"
        elif sun_sd > moon_sd and gamma < (sun_sd - moon_sd):
            etype = "annular"
        else:
            etype = "partial"

        out.append(AstroEvent(
            jd=jd, kind="solar_eclipse", body="sun", body2="moon",
            value=gamma * 60,  # arc-min
            description=(f"Solar eclipse ({etype}) — geocentric separation "
                         f"{gamma * 60:.1f}', Moon SD={moon_sd*60:.1f}', "
                         f"Sun SD={sun_sd*60:.1f}'"),
        ))
    return out


def find_lunar_eclipses(start_jd: float, end_jd: float,
                        step_d: float = 0.5) -> List[AstroEvent]:
    """Find lunar eclipse maxima (Moon passes through Earth's shadow).

    Geometric model: Earth's umbral shadow at the Moon's distance has
    angular radius ≈ 0.272° + (Moon parallax) − (Sun parallax) ≈ ~0.7°.
    Penumbra ≈ ~1.3°. We detect when geocentric Sun↔Moon separation
    is near 180° (Moon is opposite Sun) and the Moon's apparent path
    crosses these shadow circles.
    """
    out: List[AstroEvent] = []

    def _anti_sep(jd: float) -> float:
        # 180° − sep, so the function is minimized at opposition (the
        # fundamental requirement for lunar eclipse).
        _, _, sep = _sun_moon_geometry(jd)
        return abs(180.0 - sep)

    for jd in _scan_extrema(_anti_sep, start_jd, end_jd, step_d, find_min=True):
        sun, moon, sep = _sun_moon_geometry(jd)
        delta_180 = 180.0 - sep
        # Moon's distance → Earth shadow angular sizes (Meeus 54)
        # σ_umbra ≈ 0.7404° at the Moon's mean distance, scales with parallax.
        moon_parallax_deg = math.degrees(math.asin(_R_EARTH_KM / (moon.distance_au * _AU_KM)))
        sun_parallax_deg = math.degrees(math.asin(_R_EARTH_KM / (sun.distance_au * _AU_KM)))
        umbra_radius_deg = 1.02 * (moon_parallax_deg - sun_parallax_deg
                                   + math.degrees(math.asin(_R_SUN_KM / (sun.distance_au * _AU_KM))) - 0.0)
        # The above blends Bessel's classical formula. Use a simpler
        # well-cited version: σ_u = 1.02 (π_m + π_s − s_s)
        sun_sd_deg = math.degrees(math.asin(_R_SUN_KM / (sun.distance_au * _AU_KM)))
        umbra_radius_deg = 1.02 * (moon_parallax_deg + sun_parallax_deg - sun_sd_deg)
        penumbra_radius_deg = 1.02 * (moon_parallax_deg + sun_parallax_deg + sun_sd_deg)
        moon_sd_deg = _apparent_semidiameter_deg(_R_MOON_KM, moon.distance_au)

        # Eclipse occurs when the Moon enters Earth's shadow. The "gap"
        # here is geocentric Sun↔Moon angular separation minus 180°,
        # which approximates ecliptic latitude near opposition. Use the
        # penumbra radius as the inclusion threshold (a strict overlap
        # check would also need the Moon's actual ecliptic latitude
        # vs longitude split — a future improvement).
        gap = abs(delta_180)
        if gap > penumbra_radius_deg:
            continue

        if gap + moon_sd_deg < umbra_radius_deg:
            etype = "total"
        elif gap < umbra_radius_deg + moon_sd_deg:
            etype = "partial umbral"
        else:
            etype = "penumbral"

        out.append(AstroEvent(
            jd=jd, kind="lunar_eclipse", body="moon", body2="earth_shadow",
            value=gap * 60,    # arc-min
            description=(f"Lunar eclipse ({etype}) — opposition gap "
                         f"{gap * 60:.1f}', umbra={umbra_radius_deg*60:.1f}', "
                         f"penumbra={penumbra_radius_deg*60:.1f}'"),
        ))
    return out


# ════════════════════════════════════════════════════════════════════
#  Meteor shower peaks
# ════════════════════════════════════════════════════════════════════

def find_meteor_shower_peaks(start_jd: float, end_jd: float) -> List[AstroEvent]:
    """Annual meteor shower peaks falling inside the date window."""
    from aria.simulation.meteor_showers import SHOWERS
    from aria.simulation.solar_system import jd_from_calendar

    # Determine year range to scan.
    # Approximate JD↔year via 365.25-day year; refine below.
    # Use Meeus calendar inversion (cheap)
    def _year_of_jd(jd: float) -> int:
        z = int(jd + 0.5)
        if z >= 2299161:
            alpha = (z - 1867216.25) / 36524.25
            a = z + 1 + int(alpha) - int(alpha) // 4
        else:
            a = z
        b = a + 1524
        c = int((b - 122.1) / 365.25)
        d = int(365.25 * c)
        e = int((b - d) / 30.6001)
        m = e - 1 if e < 14 else e - 13
        return c - 4716 if m > 2 else c - 4715

    out: List[AstroEvent] = []
    for y in range(_year_of_jd(start_jd), _year_of_jd(end_jd) + 1):
        for s in SHOWERS:
            jd = jd_from_calendar(y, s.peak_month, s.peak_day + 0.5)
            if start_jd <= jd <= end_jd:
                out.append(AstroEvent(
                    jd=jd, kind="meteor_shower", body=s.code, body2=s.parent_body,
                    value=float(s.zhr),
                    description=(f"{s.name} peak — ZHR {s.zhr}, "
                                 f"radiant ({s.radiant_ra_deg:.1f}°, {s.radiant_dec_deg:+.1f}°), "
                                 f"v={s.velocity_kmps} km/s, parent {s.parent_body}"),
                ))
    return out


# ════════════════════════════════════════════════════════════════════
#  Convenience: one-call find-everything
# ════════════════════════════════════════════════════════════════════

def find_all_events(start_jd: float, end_jd: float) -> List[AstroEvent]:
    """Run every detector and return events sorted chronologically."""
    events: List[AstroEvent] = []
    events.extend(find_oppositions(start_jd, end_jd))
    events.extend(find_greatest_elongations(start_jd, end_jd))
    events.extend(find_inferior_conjunctions(start_jd, end_jd))
    events.extend(find_planet_pair_conjunctions(start_jd, end_jd))
    events.extend(find_perihelia(start_jd, end_jd))
    events.extend(find_comet_perihelia(start_jd, end_jd))
    events.extend(find_lunar_extrema(start_jd, end_jd))
    events.extend(find_solar_eclipses(start_jd, end_jd))
    events.extend(find_lunar_eclipses(start_jd, end_jd))
    events.extend(find_meteor_shower_peaks(start_jd, end_jd))
    events.sort(key=lambda e: e.jd)
    return events
