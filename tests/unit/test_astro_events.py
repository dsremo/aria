"""Validation for astronomical event detector.

Reference values from JPL HORIZONS / NASA almanac for known oppositions
and elongations across 2024-2026.
"""

from __future__ import annotations

import math

import pytest

from aria.simulation.solar_system import jd_from_calendar
from aria.simulation.astro_events import (
    AstroEvent,
    find_oppositions,
    find_greatest_elongations,
    find_perihelia,
    find_lunar_extrema,
    find_lunar_eclipses,
    find_solar_eclipses,
    find_planet_pair_conjunctions,
    find_all_events,
)


def _date_jd(y, m, d):
    return jd_from_calendar(y, m, d)


def test_outer_planet_oppositions_in_year():
    """Each outer planet has roughly one opposition per ~12-13 months."""
    events = find_oppositions(_date_jd(2026, 1, 1), _date_jd(2027, 1, 1))
    bodies = {e.body for e in events}
    # Saturn, Uranus, Neptune all have a 2026 opposition; Mars/Jupiter possibly.
    assert "saturn" in bodies
    assert "uranus" in bodies
    assert "neptune" in bodies


def test_opposition_elongation_above_150():
    events = find_oppositions(_date_jd(2026, 1, 1), _date_jd(2027, 1, 1))
    for e in events:
        assert e.value > 150.0, f"{e.body} opposition too low elongation: {e.value}"


def test_mercury_elongations_4_per_year():
    """Mercury hits ~6 maximum elongations per year (3 east + 3 west)."""
    events = find_greatest_elongations(_date_jd(2026, 1, 1), _date_jd(2027, 1, 1))
    mercury = [e for e in events if e.body == "mercury"]
    assert len(mercury) >= 4
    for e in mercury:
        # Mercury max elongation is always 18° to 28°.
        assert 15 < e.value < 30, f"Mercury elongation out of range: {e.value}"


def test_venus_max_elongation_around_45():
    events = find_greatest_elongations(_date_jd(2024, 1, 1), _date_jd(2027, 1, 1))
    venus = [e for e in events if e.body == "venus"]
    assert len(venus) >= 2
    for e in venus:
        assert 40 < e.value < 50, f"Venus elongation out of range: {e.value}"


def test_mercury_perihelion_period():
    """Mercury reaches perihelion ~every 88 days."""
    events = find_perihelia(_date_jd(2026, 1, 1), _date_jd(2027, 1, 1),
                            bodies=("mercury",))
    assert len(events) >= 3   # ≈4 per year
    for e in events:
        # Mercury perihelion distance ~0.307 AU
        assert 0.30 < e.value < 0.32


def test_lunar_perigee_period_about_27d():
    """Moon perigee occurs every ~27.5 days (anomalistic month)."""
    events = find_lunar_extrema(_date_jd(2026, 4, 1), _date_jd(2026, 9, 1))
    perigees = [e for e in events if e.kind == "perigee"]
    assert len(perigees) >= 4
    # Distances bracket the well-known 356-407 Mm range.
    for e in perigees:
        assert 350_000 < e.value < 370_000


def test_planet_pair_conjunction_below_threshold():
    events = find_planet_pair_conjunctions(_date_jd(2026, 1, 1), _date_jd(2026, 12, 31),
                                           threshold_deg=5.0)
    for e in events:
        assert e.value < 5.0


def test_find_all_events_chronological():
    events = find_all_events(_date_jd(2026, 4, 1), _date_jd(2026, 12, 1))
    times = [e.jd for e in events]
    assert times == sorted(times)
    assert len(events) > 5


# ════════════════════════════════════════════════════════════════════
#  Eclipse tests — match against NASA Five Millennium Catalog of
#  Eclipses for 2026-2027.
# ════════════════════════════════════════════════════════════════════

def _civil_from_jd(jd):
    z = int(jd + 0.5)
    a = z + 1 + (z - 1867216) // 36524 - ((z - 1867216) // 36524) // 4 if z >= 2299161 else z
    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)
    day = int(b - d - int(30.6001 * e) + (jd + 0.5 - z))
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    return year, month, day


def test_solar_eclipses_2026_2027():
    """NASA catalog: 2026-Feb-17, 2026-Aug-12, 2027-Feb-06, 2027-Aug-02."""
    events = find_solar_eclipses(_date_jd(2026, 1, 1), _date_jd(2028, 1, 1))
    dates = {_civil_from_jd(e.jd)[:3] for e in events}
    expected = {
        (2026, 2, 17), (2026, 8, 12),
        (2027, 2, 6),  (2027, 8, 2),
    }
    # Allow ±1 day tolerance for date wrapping near 0 UT.
    for y, mo, d in expected:
        assert any(abs(ey - y) == 0 and em == mo and abs(ed - d) <= 1
                   for ey, em, ed in dates), \
            f"missed solar eclipse {y}-{mo}-{d} (found {sorted(dates)})"


def test_lunar_eclipses_2026_2027():
    """NASA catalog: 2026-Mar-03, 2026-Aug-28, 2027-Feb-20, 2027-Aug-17."""
    events = find_lunar_eclipses(_date_jd(2026, 1, 1), _date_jd(2028, 1, 1))
    dates = {_civil_from_jd(e.jd)[:3] for e in events}
    expected = {
        (2026, 3, 3),  (2026, 8, 28),
        (2027, 2, 20), (2027, 8, 17),
    }
    for y, mo, d in expected:
        assert any(abs(ey - y) == 0 and em == mo and abs(ed - d) <= 1
                   for ey, em, ed in dates), \
            f"missed lunar eclipse {y}-{mo}-{d} (found {sorted(dates)})"


def test_eclipse_classification_has_recognized_label():
    events = (find_solar_eclipses(_date_jd(2026, 1, 1), _date_jd(2027, 1, 1))
              + find_lunar_eclipses(_date_jd(2026, 1, 1), _date_jd(2027, 1, 1)))
    for e in events:
        # Every classification must include one of these tokens
        assert any(t in e.description for t in ("total", "annular", "partial", "penumbral"))
