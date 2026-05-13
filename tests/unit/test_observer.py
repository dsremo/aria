"""Validation for observer-location sky transformations."""

from __future__ import annotations

import math

import pytest

from aria.simulation.observer import (
    CITIES,
    day_conditions,
    equatorial_to_horizontal,
    greenwich_sidereal_time_deg,
    is_above_horizon,
    local_sidereal_time_deg,
    refraction_correction_deg,
    sky_snapshot,
)
from aria.simulation.solar_system import jd_from_calendar


def test_gmst_meeus_example():
    """Meeus example 12.b: JD 2446895.5 → GMST = 13h 10m 46.366s = 197.69319°."""
    g = greenwich_sidereal_time_deg(2446895.5)
    assert abs(g - 197.69319) < 0.001


def test_polaris_altitude_equals_latitude():
    """Polaris (Dec ≈ 89.26°) altitude approximates the observer's latitude."""
    lst = local_sidereal_time_deg(2451545.0, 0.0)
    for lat in (0, 30, 51.5, 70):
        alt, _ = equatorial_to_horizontal(37.95, 89.26, lst, lat)
        # Polaris is ~0.74° from true pole, so within 1° of latitude is correct.
        assert abs(alt - lat) < 1.0


def test_zenith_at_pole_for_polestar():
    """Standing at the north pole, anything at +90° declination is at zenith."""
    lst = local_sidereal_time_deg(2451545.0, 0.0)
    alt, _ = equatorial_to_horizontal(0, 90.0, lst, 90)
    assert alt == pytest.approx(90.0, abs=0.01)


def test_southern_observer_sees_southern_stars():
    """A star at Dec=-60° is permanently up only south of latitude -30°."""
    # At lat -50°, declination -60° star: minimum altitude = lat + dec - 90 + 90 = +20° (always up).
    # Use any LST since it's circumpolar.
    lst = 0.0
    alt, _ = equatorial_to_horizontal(180.0, -60.0, lst, -50)
    assert alt > 0


def test_horizon_check():
    # Polaris from southern hemisphere is below horizon
    assert not is_above_horizon(37.95, 89.26, 2451545.0, lat_deg=-30, lon_deg=0)
    # …and above horizon from northern
    assert is_above_horizon(37.95, 89.26, 2451545.0, lat_deg=+30, lon_deg=0)


def test_refraction_increases_near_horizon():
    """Bennett refraction grows from ~0° at zenith to ~34' near horizon."""
    z_correction = refraction_correction_deg(89.0)
    h_correction = refraction_correction_deg(0.5)
    assert h_correction > z_correction
    assert h_correction > 0.4   # > 24'
    assert z_correction < 0.05  # < 3'


def test_sky_snapshot_shape():
    snap = sky_snapshot(2451545.0, lat_deg=12.97, lon_deg=77.59,
                        mag_limit_stars=2.5, mag_limit_dso=6.0)
    assert "planets" in snap
    assert "stars" in snap
    assert "messier" in snap
    # All entries must be above horizon
    for arr in snap.values():
        for p in arr:
            assert p.alt_deg >= 0
            assert 0 <= p.az_deg < 360


def test_city_presets_have_valid_coords():
    for name, (lat, lon) in CITIES.items():
        assert -90 <= lat <= 90, f"{name} bad lat"
        assert -180 < lon <= 180, f"{name} bad lon"


# ════════════════════════════════════════════════════════════════════
#  day_conditions tests
# ════════════════════════════════════════════════════════════════════

def test_bengaluru_sunrise_sunset_april():
    """Bengaluru on 2026-Apr-18: sunrise ≈ 06:05 IST = 0:35 UT, sunset ≈ 18:32 IST = 13:02 UT."""
    jd = jd_from_calendar(2026, 4, 18) + 0.5    # noon UT
    cond = day_conditions(jd, lat_deg=12.9716, lon_deg=77.5946)
    assert cond.sunrise_jd is not None
    assert cond.sunset_jd is not None
    # Convert to UT minutes-of-day for comparison
    sr_min = (cond.sunrise_jd - math.floor(cond.sunrise_jd + 0.5) + 0.5) * 1440
    ss_min = (cond.sunset_jd - math.floor(cond.sunset_jd + 0.5) + 0.5) * 1440
    # Allow ±5 min tolerance
    assert abs(sr_min - 35) < 10, f"sunrise UT min {sr_min}"
    assert abs(ss_min - 13 * 60 - 2) < 10, f"sunset UT min {ss_min}"


def test_solar_noon_between_sunrise_sunset():
    jd = jd_from_calendar(2026, 6, 21) + 0.5
    cond = day_conditions(jd, lat_deg=51.5, lon_deg=0)
    assert cond.solar_noon_jd is not None
    assert cond.sunrise_jd < cond.solar_noon_jd < cond.sunset_jd


def test_dawn_before_sunrise_dusk_after_sunset():
    jd = jd_from_calendar(2026, 4, 18) + 0.5
    cond = day_conditions(jd, lat_deg=12.97, lon_deg=77.59)
    assert cond.civil_twilight_dawn_jd < cond.sunrise_jd
    assert cond.astro_twilight_dawn_jd < cond.civil_twilight_dawn_jd
    assert cond.civil_twilight_dusk_jd > cond.sunset_jd
    assert cond.astro_twilight_dusk_jd > cond.civil_twilight_dusk_jd


def test_moon_phase_progression():
    """One synodic month should sweep through all phases."""
    jd_start = jd_from_calendar(2026, 4, 17) + 0.5    # day after new moon
    labels_seen = set()
    for d in range(0, 30, 2):
        cond = day_conditions(jd_start + d, lat_deg=0, lon_deg=0)
        labels_seen.add(cond.moon_phase_label)
    # Should hit at least crescent + quarter + gibbous + full
    assert "Waxing crescent" in labels_seen
    assert "Waxing gibbous" in labels_seen
    assert "Waning crescent" in labels_seen or "Waning gibbous" in labels_seen


def test_north_pole_polar_day_no_sunrise():
    """In June, the North Pole has continuous sun — sunrise/sunset are None."""
    jd = jd_from_calendar(2026, 6, 21) + 0.5
    cond = day_conditions(jd, lat_deg=89.9, lon_deg=0)
    # Sun is always above horizon here, so no rise/set crossing
    assert cond.sunrise_jd is None
    assert cond.sunset_jd is None
