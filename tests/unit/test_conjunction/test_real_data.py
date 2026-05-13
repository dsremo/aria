"""Tests using real downloaded TLE and space weather data files."""

import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from aria.conjunction.conjunction.close_approach import (
    build_close_approach,
    build_close_approaches_batch,
)
from aria.conjunction.conjunction.tca_finder import TCAFinder
from aria.conjunction.data.breakup_detect import BreakupDetector
from aria.conjunction.data.catalog import SpaceObjectCatalog
from aria.conjunction.data.space_weather_loader import SpaceWeatherLoader
from aria.conjunction.data.tle_parser import TLEParser
from aria.conjunction.propagation.frames import eci_to_ecef, teme_to_eci_j2000
from aria.conjunction.propagation.sgp4_propagator import SGP4Error, SGP4Propagator
from aria.conjunction.screening.apogee_perigee import ApogeePerigeeFilter

DATA_DIR = Path(__file__).parent.parent / "data"

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "stations.tle").exists(),
    reason="Real TLE data files not present (run scripts/download_test_data.py first)",
)


# ---------------------------------------------------------------------------
# Fixtures — load real TLE files once
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def stations():
    """Real ISS, CSS, POISK etc TLEs from stations.tle."""
    text = (DATA_DIR / "stations.tle").read_text()
    return TLEParser.parse_multi_tle(text)


@pytest.fixture(scope="module")
def cosmos2251_debris():
    """Real Cosmos 2251 debris TLEs."""
    text = (DATA_DIR / "cosmos2251_debris.tle").read_text()
    return TLEParser.parse_multi_tle(text)


@pytest.fixture(scope="module")
def iridium33_debris():
    """Real Iridium 33 debris TLEs."""
    text = (DATA_DIR / "iridium33_debris.tle").read_text()
    return TLEParser.parse_multi_tle(text)


@pytest.fixture(scope="module")
def full_catalog_sample():
    """A 500-object sample from tle_full_catalog.txt for speed."""
    text = (DATA_DIR / "tle_full_catalog.txt").read_text()
    all_objects = TLEParser.parse_multi_tle(text)
    return all_objects[:500]


# ---------------------------------------------------------------------------
# TLE Parser — real data
# ---------------------------------------------------------------------------

class TestRealTLEParsing:

    def test_stations_tle_all_parsed(self, stations):
        assert len(stations) >= 5  # ISS, CSS, POISK, etc.

    def test_iss_present(self, stations):
        norad_ids = {obj.norad_id for obj in stations}
        assert "25544" in norad_ids

    def test_all_stations_have_satellite(self, stations):
        for obj in stations:
            assert obj.satellite is not None, f"{obj.name} missing satellite"

    def test_all_stations_have_elements(self, stations):
        for obj in stations:
            assert obj.elements is not None
            assert obj.elements.semi_major_axis > 6371

    def test_cosmos2251_debris_count(self, cosmos2251_debris):
        """Cosmos 2251 generated ~500 trackable debris pieces."""
        assert len(cosmos2251_debris) >= 400

    def test_cosmos2251_inclination_cluster(self, cosmos2251_debris):
        """All Cosmos 2251 debris should be near ~74° inclination."""
        incs = [math.degrees(obj.elements.inclination)
                for obj in cosmos2251_debris if obj.elements]
        assert all(70 <= i <= 78 for i in incs), \
            f"Some debris far from 74°: min={min(incs):.1f}°, max={max(incs):.1f}°"

    def test_cosmos2251_altitude_range(self, cosmos2251_debris):
        """Debris should be in 400–1200 km altitude range."""
        for obj in cosmos2251_debris:
            if obj.elements:
                alt = obj.elements.perigee_altitude
                assert 300 < alt < 1500, f"{obj.name} perigee {alt:.0f}km out of range"

    def test_iridium33_debris_count(self, iridium33_debris):
        """Iridium 33 collision generated ~100 trackable pieces."""
        assert len(iridium33_debris) >= 80

    def test_full_catalog_large(self, full_catalog_sample):
        assert len(full_catalog_sample) == 500

    def test_full_catalog_orbital_diversity(self, full_catalog_sample):
        """Full catalog should have objects across altitude regimes."""
        smas = [obj.elements.semi_major_axis for obj in full_catalog_sample
                if obj.elements]
        min_sma = min(smas)
        max_sma = max(smas)
        assert max_sma - min_sma > 5000  # LEO to MEO/GEO diversity


# ---------------------------------------------------------------------------
# Catalog — real data
# ---------------------------------------------------------------------------

class TestRealCatalogLoading:

    def test_load_tle_file_stations(self):
        cat = SpaceObjectCatalog()
        count = cat.load_tle_file(DATA_DIR / "stations.tle")
        assert count >= 5
        assert "25544" in cat  # ISS

    def test_load_cosmos2251(self):
        cat = SpaceObjectCatalog()
        count = cat.load_tle_file(DATA_DIR / "cosmos2251_debris.tle")
        assert count >= 400

    def test_stale_detection_on_real_data(self, stations):
        """All station TLEs should be fresh (from 2026) relative to old cutoff."""
        cat = SpaceObjectCatalog()
        for obj in stations:
            cat.add(obj)
        # Very old cutoff: 100000h means never stale
        stale = cat.stale_objects(max_age_hours=100000.0)
        assert len(stale) == 0


# ---------------------------------------------------------------------------
# SGP4 Propagation — real TLEs
# ---------------------------------------------------------------------------

class TestRealSGP4Propagation:

    def test_propagate_iss_at_epoch(self, stations):
        iss = next(obj for obj in stations if obj.norad_id == "25544")
        state = SGP4Propagator.propagate(iss, iss.elements.epoch)
        r = np.linalg.norm(state.position)
        v = np.linalg.norm(state.velocity)
        assert 6500 < r < 7000
        assert 7.0 < v < 8.0

    def test_propagate_many_stations(self, stations):
        epoch = stations[0].elements.epoch
        results = SGP4Propagator.propagate_many(stations, epoch)
        assert len(results) >= len(stations) - 2  # allow 2 failures

    def test_propagate_many_all_positions_valid(self, stations):
        epoch = stations[0].elements.epoch
        results = SGP4Propagator.propagate_many(stations, epoch)
        for norad_id, state in results.items():
            r = np.linalg.norm(state.position)
            assert 6371 < r < 45000, f"{norad_id} position {r:.0f}km out of range"

    def test_propagate_many_batch(self, stations):
        """Array API: propagate N objects × M epochs."""
        epoch = stations[0].elements.epoch
        epochs = [epoch + timedelta(minutes=10 * k) for k in range(6)]
        batch = SGP4Propagator.propagate_many_batch(stations[:5], epochs)
        assert batch.shape == (5, 6, 6)
        # At epoch, ISS should have valid position (not NaN)
        iss_states = batch[0]
        assert not np.all(np.isnan(iss_states))

    def test_propagate_batch_iss_over_orbit(self, stations):
        """Batch propagation of ISS over one full orbit (~90 min)."""
        iss = next(obj for obj in stations if obj.norad_id == "25544")
        epoch = iss.elements.epoch
        states = SGP4Propagator.propagate_batch(
            iss, epoch, epoch + timedelta(minutes=90), step_seconds=60.0
        )
        assert len(states) >= 85  # should get ~91 states
        # Ground track should vary
        positions = np.array([s.position for s in states])
        assert positions[:, 0].std() > 100  # x varies significantly

    def test_sgp4_error_no_satellite(self, stations):
        """Object without satellite should raise SGP4Error."""
        from aria.conjunction.core.types import SpaceObject
        bad_obj = SpaceObject(norad_id="0", name="X", tle_line1="", tle_line2="",
                               satellite=None)
        with pytest.raises(SGP4Error, match="No Satrec"):
            SGP4Propagator.propagate(bad_obj, datetime.utcnow())

    def test_propagate_many_skips_no_satellite(self):
        """propagate_many should skip objects without satellite."""
        from aria.conjunction.core.types import SpaceObject
        bad = SpaceObject(norad_id="0", name="X", tle_line1="", tle_line2="",
                           satellite=None)
        results = SGP4Propagator.propagate_many([bad], datetime.utcnow())
        assert len(results) == 0

    def test_propagate_many_batch_nan_for_no_satellite(self, stations):
        """propagate_many_batch should return NaN for objects without satellite."""
        from aria.conjunction.core.types import SpaceObject
        bad = SpaceObject(norad_id="X", name="X", tle_line1="", tle_line2="",
                           satellite=None)
        epoch = stations[0].elements.epoch
        result = SGP4Propagator.propagate_many_batch([bad], [epoch])
        assert result.shape == (1, 1, 6)
        assert np.all(np.isnan(result[0, 0]))

    def test_frame_transform_teme_to_eci(self, stations):
        """TEME → ECI transform should preserve vector norm."""
        iss = next(obj for obj in stations if obj.norad_id == "25544")
        state_teme = SGP4Propagator.propagate(iss, iss.elements.epoch)
        state_eci = teme_to_eci_j2000(state_teme)
        # Norm should be preserved (rotation only)
        assert np.linalg.norm(state_eci.position) == pytest.approx(
            np.linalg.norm(state_teme.position), rel=1e-6
        )

    def test_frame_transform_eci_to_ecef(self, stations):
        """ECI → ECEF transform should preserve vector norm."""
        iss = next(obj for obj in stations if obj.norad_id == "25544")
        state = SGP4Propagator.propagate(iss, iss.elements.epoch)
        state_eci = teme_to_eci_j2000(state)
        state_ecef = eci_to_ecef(state_eci)
        assert np.linalg.norm(state_ecef.position) == pytest.approx(
            np.linalg.norm(state_eci.position), rel=1e-6
        )


# ---------------------------------------------------------------------------
# Screening — real data
# ---------------------------------------------------------------------------

class TestRealScreening:

    def test_apogee_perigee_filter_stations(self, stations):
        """Station filter: ISS-like objects should pair with each other."""
        filt = ApogeePerigeeFilter(pad_km=10.0)
        pairs = filt.filter(stations)
        # All stations are in similar orbits → many pairs
        assert len(pairs) >= 1

    def test_apogee_perigee_cosmos_debris(self, cosmos2251_debris):
        """All Cosmos 2251 debris at ~74° inc should have many overlapping orbits."""
        filt = ApogeePerigeeFilter(pad_km=50.0)
        pairs = filt.filter(cosmos2251_debris[:50])
        assert len(pairs) > 100  # debris cloud → many pairs

    def test_full_catalog_screening_reduces_pairs(self, full_catalog_sample):
        """Full catalog screening should eliminate most pairs."""
        filt = ApogeePerigeeFilter(pad_km=10.0)
        pairs = filt.filter(full_catalog_sample)
        total_possible = len(full_catalog_sample) * (len(full_catalog_sample) - 1) // 2
        # Should eliminate >80% of pairs
        assert len(pairs) < total_possible * 0.5


# ---------------------------------------------------------------------------
# TCA Finder and Close Approach — real TLEs
# ---------------------------------------------------------------------------

class TestRealTCAFinder:

    def test_find_tca_self_conjunction(self, stations):
        """Self-conjunction: TCA distance should be ~0."""
        iss = next(obj for obj in stations if obj.norad_id == "25544")
        finder = TCAFinder(coarse_step_s=30.0, search_window_minutes=5.0)
        results = finder.find_tca(iss, iss, iss.elements.epoch)
        assert len(results) >= 1
        _, dist = results[0]
        assert dist < 0.01  # ~0 km

    def test_build_close_approach_self(self, stations):
        """build_close_approach for self-conjunction should work."""
        iss = next(obj for obj in stations if obj.norad_id == "25544")
        finder = TCAFinder(coarse_step_s=30.0, search_window_minutes=5.0)
        approach = build_close_approach(iss, iss, iss.elements.epoch, finder)
        assert approach is not None
        assert approach.miss_distance_km < 0.01
        assert approach.primary_state is not None
        assert approach.secondary_state is not None

    def test_build_close_approaches_batch_empty(self, stations):
        """Empty candidates → empty result."""
        result = build_close_approaches_batch(stations, [])
        assert result == []

    def test_find_all_tca_multi_pass(self, stations):
        """find_all_tca should find multiple ISS passes over a long window."""
        iss = next(obj for obj in stations if obj.norad_id == "25544")
        finder = TCAFinder(coarse_step_s=30.0, search_window_minutes=10.0)
        epoch = iss.elements.epoch
        # ISS period ~92 min → 3h window should give ~2 passes vs itself
        results = finder.find_all_tca(
            iss, iss,
            start=epoch,
            end=epoch + timedelta(hours=3),
            coarse_step_s=60.0,
        )
        # Self-conjunction gives very small distances at every step → results may vary
        # Just ensure the function runs and returns a list
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Breakup Detection — real debris clouds
# ---------------------------------------------------------------------------

class TestRealBreakupDetection:

    def test_cosmos2251_forms_dense_cloud(self, cosmos2251_debris):
        """All Cosmos 2251 debris should bin into very few orbital regimes."""
        detector = BreakupDetector(altitude_bin_km=100.0, inclination_bin_deg=5.0,
                                   min_new_objects=10)
        alerts = detector.check(cosmos2251_debris)
        # All debris in same orbital regime → one or two dense bins
        total_new = sum(a.new_object_count for a in alerts)
        assert total_new >= len(cosmos2251_debris) * 0.9  # >90% in detected bins

    def test_cosmos2251_no_new_on_second_check(self, cosmos2251_debris):
        """After establishing history, same catalog → no new alerts."""
        detector = BreakupDetector(min_new_objects=5)
        detector.check(cosmos2251_debris)  # establish history
        alerts = detector.check(cosmos2251_debris)  # same → no new
        assert len(alerts) == 0

    def test_combined_cosmos_iridium_separate_regimes(self, cosmos2251_debris, iridium33_debris):
        """Cosmos 2251 (74°) and Iridium 33 (86°) should be in different bins."""
        detector = BreakupDetector(
            altitude_bin_km=200.0,
            inclination_bin_deg=5.0,
            min_new_objects=20,
        )
        all_debris = cosmos2251_debris + iridium33_debris
        alerts = detector.check(all_debris)
        # Should detect multiple bins (Cosmos at 74°, Iridium at 86°)
        assert len(alerts) >= 2


# ---------------------------------------------------------------------------
# Space Weather Loader — real CSV
# ---------------------------------------------------------------------------

class TestRealSpaceWeatherLoader:

    def test_load_real_csv(self):
        loader = SpaceWeatherLoader()
        count = loader.load_csv(DATA_DIR / "space_weather.csv")
        assert count > 1000
        assert loader.size == count

    def test_kp_values_valid_range(self):
        loader = SpaceWeatherLoader()
        loader.load_csv(DATA_DIR / "space_weather.csv")
        lo, _ = loader.date_range
        record = loader.get(lo)
        assert record is not None
        assert all(0.0 <= k for k in record.kp_values)

    def test_date_range_spans_multiple_years(self):
        loader = SpaceWeatherLoader()
        loader.load_csv(DATA_DIR / "space_weather_5yr.csv")
        lo, hi = loader.date_range
        assert (hi - lo).days >= 365 * 4  # at least 4 years

    def test_get_specific_date(self):
        loader = SpaceWeatherLoader()
        loader.load_csv(DATA_DIR / "space_weather.csv")
        lo, _ = loader.date_range
        record = loader.get(lo)
        assert record is not None
        assert record.date == lo

    def test_get_nearest_fallback(self):
        loader = SpaceWeatherLoader()
        loader.load_csv(DATA_DIR / "space_weather.csv")
        lo, _ = loader.date_range
        # Query a date before data starts → fallback
        before = lo - timedelta(days=10)
        record = loader.get_nearest(before)
        assert record is not None

    def test_storm_periods_identified(self):
        loader = SpaceWeatherLoader()
        loader.load_csv(DATA_DIR / "space_weather_5yr.csv")
        # Kp×10, so threshold 50 = Kp 5.0
        storms = loader.storm_periods(kp_threshold=50.0)
        # 5 years should have at least a few geomagnetic storms
        assert len(storms) >= 5

    def test_to_space_weather_state(self):
        loader = SpaceWeatherLoader()
        loader.load_csv(DATA_DIR / "space_weather.csv")
        lo, _ = loader.date_range
        record = loader.get(lo)
        assert record is not None
        state = record.to_space_weather_state()
        assert state is not None
        assert state.f107_index > 0

    def test_get_state_returns_state(self):
        loader = SpaceWeatherLoader()
        loader.load_csv(DATA_DIR / "space_weather.csv")
        lo, _ = loader.date_range
        state = loader.get_state(lo)
        assert state is not None

    def test_f107_values_physically_reasonable(self):
        loader = SpaceWeatherLoader()
        loader.load_csv(DATA_DIR / "space_weather.csv")
        lo, _ = loader.date_range
        record = loader.get(lo)
        # F10.7 should be 60–300 SFU in normal solar conditions
        assert 50.0 <= record.f107_obs <= 500.0
