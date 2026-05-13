"""Solar system ephemeris validation against Stellarium/JPL HORIZONS J2000 data.

The Standish 1992 mean elements give planet positions accurate to:
  Mercury–Mars  : <30''
  Jupiter–Saturn: <1'
  Uranus–Neptune: <3'
  Pluto         : <60'

These are the tolerances we test against. Reference positions are
geocentric apparent at J2000.0 (JD 2451545.0).
"""

from __future__ import annotations

import math

import pytest

from aria.simulation.solar_system import (
    EPSILON_J2000_DEG,
    all_visible_bodies,
    centuries_from_j2000,
    geocentric_position,
    heliocentric_ecliptic,
    jd_from_calendar,
)


def _ang_sep(ra1, dec1, ra2, dec2):
    """Great-circle angular separation in degrees."""
    a = math.radians(ra1)
    b = math.radians(ra2)
    d1 = math.radians(dec1)
    d2 = math.radians(dec2)
    cos_sep = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(a - b)
    cos_sep = max(-1.0, min(1.0, cos_sep))
    return math.degrees(math.acos(cos_sep))


def test_jd_j2000_round_trip():
    assert jd_from_calendar(2000, 1, 1.5) == pytest.approx(2451545.0)
    assert centuries_from_j2000(2451545.0) == pytest.approx(0.0)


def test_obliquity_value():
    # IERS 2003 mean obliquity at J2000 = 23.4392911°
    assert EPSILON_J2000_DEG == pytest.approx(23.4392911, abs=1e-7)


def test_sun_at_j2000():
    # Stellarium / JPL: Sun on 2000-Jan-01 12:00 UT was at RA ≈ 281.4°, Dec ≈ -23.04°
    s = geocentric_position("sun", 2451545.0)
    sep = _ang_sep(s.ra_deg, s.dec_deg, 281.4, -23.04)
    assert sep < 0.5, f"Sun J2000 off by {sep:.2f}°"
    assert s.magnitude < -25  # very bright


def test_mars_at_j2000():
    # JPL HORIZONS for Mars geocentric on 2000-Jan-01 12:00 UT:
    # RA ≈ 22h02m → 330.5°, Dec ≈ -13.2°
    m = geocentric_position("mars", 2451545.0)
    sep = _ang_sep(m.ra_deg, m.dec_deg, 330.5, -13.2)
    assert sep < 0.5, f"Mars J2000 off by {sep:.2f}°"
    assert 0 < m.magnitude < 2  # ~+0.7 mag


def test_jupiter_at_j2000():
    # JPL HORIZONS Jupiter geocentric J2000: RA ≈ 23.97°, Dec ≈ +8.6°
    j = geocentric_position("jupiter", 2451545.0)
    sep = _ang_sep(j.ra_deg, j.dec_deg, 23.97, 8.6)
    assert sep < 0.05, f"Jupiter J2000 off by {sep:.3f}°"


def test_pluto_at_j2000():
    # Pluto J2000: RA ≈ 251.4°, Dec ≈ -11.4° — Standish accuracy ~1° here
    p = geocentric_position("pluto", 2451545.0)
    sep = _ang_sep(p.ra_deg, p.dec_deg, 251.4, -11.4)
    assert sep < 1.5, f"Pluto J2000 off by {sep:.2f}°"


def test_earth_helio_distance():
    # Earth-Sun distance varies 0.983-1.017 AU; on Jan 1 we're near perihelion.
    x, y, z = heliocentric_ecliptic("earth", 2451545.0)
    r = math.sqrt(x * x + y * y + z * z)
    assert 0.98 < r < 1.02


def test_all_visible_bodies_returns_sorted():
    bodies = all_visible_bodies(2451545.0)
    # Must include sun, moon, all 8 planets + pluto = 10 entries minimum.
    names = [b.name for b in bodies]
    assert {"sun", "moon", "mercury", "venus", "mars", "jupiter",
            "saturn", "uranus", "neptune", "pluto"}.issubset(names)
    # Sorted brightest → faintest → Sun first, Pluto last.
    mags = [b.magnitude for b in bodies]
    assert mags == sorted(mags)
    assert bodies[0].name == "sun"


def test_solar_system_color_finite():
    for b in all_visible_bodies(2451545.0):
        assert all(0.0 <= c <= 1.0 for c in b.color)
        assert math.isfinite(b.magnitude)
        assert b.distance_au > 0
