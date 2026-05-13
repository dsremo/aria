"""Validation for planetary moon ephemeris.

Reference values from JPL HORIZONS / Stellarium for July 2024.
"""

from __future__ import annotations

import math

import pytest

from aria.simulation.solar_system import jd_from_calendar
from aria.simulation.moons import (
    ALL_MOONS, JUPITER_MOONS, SATURN_MOONS,
    geocentric_moon, planetcentric_position, visible_moons,
)


def _ang_sep(a1, d1, a2, d2):
    a, b = math.radians(a1), math.radians(a2)
    p, q = math.radians(d1), math.radians(d2)
    cos_sep = math.sin(p) * math.sin(q) + math.cos(p) * math.cos(q) * math.cos(a - b)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_sep))))


def test_catalog_population():
    assert len(ALL_MOONS) >= 15
    assert len(JUPITER_MOONS) == 4   # Galilean satellites
    assert len(SATURN_MOONS) >= 5


def test_galilean_moons_cluster_around_jupiter():
    """Io/Europa/Ganymede/Callisto must be within ~0.5° of Jupiter."""
    from aria.simulation.solar_system import geocentric_position
    jd = jd_from_calendar(2024, 7, 1.0)
    jup = geocentric_position("jupiter", jd)
    for moon in JUPITER_MOONS:
        sb = geocentric_moon(moon, jd)
        sep = _ang_sep(sb.ra_deg, sb.dec_deg, jup.ra_deg, jup.dec_deg)
        assert sep < 0.5, f"{moon.name} too far from Jupiter: {sep:.3f}°"


def test_galilean_brightness_naked_eye():
    # All four Galilean moons V<7 from Earth — naked-eye if not lost in Jovian glare.
    jd = jd_from_calendar(2024, 7, 1.0)
    for moon in JUPITER_MOONS:
        sb = geocentric_moon(moon, jd)
        assert sb.magnitude < 7.0, f"{moon.name} too faint: {sb.magnitude:.2f}"


def test_titan_brightness():
    # Titan V≈8.4 — well-known reference.
    titan = next(m for m in SATURN_MOONS if m.name == "Titan")
    sb = geocentric_moon(titan, jd_from_calendar(2024, 7, 1.0))
    assert 7.5 < sb.magnitude < 9.5, f"Titan mag off: {sb.magnitude:.2f}"


def test_planetcentric_distance_in_range():
    """Each moon's distance from its parent should match its semi-major axis."""
    jd = 2451545.0
    for moon in ALL_MOONS:
        x, y, z = planetcentric_position(moon, jd)
        AU_KM = 149597870.7
        r_km = math.sqrt(x * x + y * y + z * z) * AU_KM
        # Within 2× the semi-major axis (ellipse extremes)
        assert 0.4 * moon.a_km < r_km < 2.0 * moon.a_km, \
            f"{moon.name}: r={r_km:.0f}km, expected ~{moon.a_km}km"


def test_visible_moons_sorted_and_finite():
    bodies = visible_moons(2451545.0, mag_limit=20)
    mags = [b.magnitude for b in bodies]
    assert mags == sorted(mags)
    for b in bodies:
        assert math.isfinite(b.magnitude)
        assert b.distance_au > 0
        assert 0 <= b.ra_deg < 360
        assert -90 <= b.dec_deg <= 90
