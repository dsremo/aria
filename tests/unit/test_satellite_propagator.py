"""Validation for the TLE → ECI/ECEF/topocentric propagator."""

from __future__ import annotations

import math

import pytest

from aria.simulation.satellite_catalog import load_satellites, categories
from aria.simulation.satellite_propagator import (
    datetime_to_jd, ecef_to_geodetic, eci_to_ecef, gmst_radians,
    ground_track, observer_view, propagate_tle,
)
from aria.simulation.tle_parser import parse_tle


_ISS_TLE = parse_tle(
    "1 25544U 98067A   24015.50000000  .00016717  00000-0  10270-3 0  9994",
    "2 25544  51.6413   0.0000 0005291 132.2917  16.7083 15.49309239432456",
    "ISS",
)


def test_iss_altitude_at_epoch():
    jd = datetime_to_jd(_ISS_TLE.epoch)
    st = propagate_tle(_ISS_TLE, jd)
    # ISS altitude is 408–418 km in this epoch
    assert 400 < st.altitude_km < 430


def test_iss_speed_in_range():
    jd = datetime_to_jd(_ISS_TLE.epoch)
    st = propagate_tle(_ISS_TLE, jd)
    # Circular LEO at 415 km → v ≈ √(GM/(R+h)) ≈ 7.66 km/s
    assert 7.5 < st.speed_kmps < 7.8


def test_iss_period_about_93_min():
    jd = datetime_to_jd(_ISS_TLE.epoch)
    st = propagate_tle(_ISS_TLE, jd)
    assert 92 < st.period_min < 94


def test_eci_ecef_roundtrip_consistency():
    """ECEF position magnitude should match ECI position magnitude (rotation only)."""
    jd = datetime_to_jd(_ISS_TLE.epoch) + 0.1
    st = propagate_tle(_ISS_TLE, jd)
    ecef = eci_to_ecef(st.r_eci_m, jd)
    r_eci = math.sqrt(sum(c * c for c in st.r_eci_m))
    r_ecef = math.sqrt(sum(c * c for c in ecef))
    assert abs(r_eci - r_ecef) < 1.0   # < 1 m


def test_subsatellite_inside_inclination_band():
    """ISS sub-satellite latitude must stay within ±51.6° (inclination)."""
    jd = datetime_to_jd(_ISS_TLE.epoch)
    for k in range(0, 24 * 60, 5):     # one day, every 5 min
        st = propagate_tle(_ISS_TLE, jd + k / 1440.0)
        ecef = eci_to_ecef(st.r_eci_m, st.jd)
        lat, _, _ = ecef_to_geodetic(ecef)
        # Allow 0.5° margin for slight propagation drift
        assert abs(lat) < 52.5, f"ISS lat {lat:.2f}° outside inclination"


def test_observer_view_positive_range():
    jd = datetime_to_jd(_ISS_TLE.epoch)
    st = propagate_tle(_ISS_TLE, jd)
    view = observer_view(st, lat_deg=12.97, lon_deg=77.59)
    assert view.range_km > 400         # at least altitude
    assert -90 <= view.altitude_deg <= 90
    assert 0 <= view.azimuth_deg < 360


def test_ground_track_continuous():
    jd0 = datetime_to_jd(_ISS_TLE.epoch)
    pts = ground_track(_ISS_TLE, jd0, jd0 + 0.05, step_min=1.0)
    assert len(pts) > 30
    for p in pts:
        assert -90 <= p.lat_deg <= 90
        assert -180 <= p.lon_deg <= 180


def test_catalog_loads():
    sats = load_satellites()
    assert len(sats) >= 12
    cats = categories()
    assert "crewed" in cats
    assert "navigation" in cats


def test_geo_satellites_are_sidereal():
    """GOES / INSAT period should be ~1436 min (sidereal day)."""
    sats = load_satellites()
    geos = [(t, c) for t, c in sats if c == "geo"]
    assert len(geos) >= 1
    for tle, _ in geos:
        period = 1440.0 / tle.mean_motion_rev_per_day
        assert 1430 < period < 1445, f"{tle.name} period {period}"


def test_gmst_returns_radians_in_range():
    g = gmst_radians(2451545.0)
    assert 0 <= g < 2 * math.pi
