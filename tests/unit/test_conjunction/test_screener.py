"""Tests for SmartSieveScreener, ExclusionList, and TimeFilter."""

import math
from datetime import datetime, timedelta
from unittest.mock import patch

from aria.conjunction.core.types import ObjectType, OrbitalElements, SpaceObject
from aria.conjunction.data.tle_parser import TLEParser
from aria.conjunction.screening.screener import ExclusionList, SmartSieveScreener
from aria.conjunction.screening.time_filter import TimeFilter

# ISS TLE (2008 epoch, known valid)
ISS_LINE1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
ISS_LINE2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"

# STARLINK TLE (similar epoch)
SL_LINE1 = "1 44713C 19074A   08265.50000000  .00000000  00000-0  00000-0 0  9997"
SL_LINE2 = "2 44713  53.0000 100.0000 0001000  0.0000 360.0000 15.05000000     04"


def _make_obj_with_elements(norad_id: str, sma: float, ecc: float,
                             inc_deg: float, raan_deg: float = 0.0,
                             name: str | None = None) -> SpaceObject:
    elements = OrbitalElements(
        semi_major_axis=sma,
        eccentricity=ecc,
        inclination=math.radians(inc_deg),
        raan=math.radians(raan_deg),
        arg_perigee=0.0,
        true_anomaly=0.0,
        epoch=datetime(2024, 2, 14),
    )
    return SpaceObject(
        norad_id=norad_id,
        name=name or f"OBJ-{norad_id}",
        tle_line1="",
        tle_line2="",
        object_type=ObjectType.DEBRIS,
        elements=elements,
    )


# ---------------------------------------------------------------------------
# ExclusionList
# ---------------------------------------------------------------------------

class TestExclusionList:

    def test_add_pair_and_is_excluded(self):
        exc = ExclusionList()
        exc.add_pair("25544", "99999")

        obj_a = _make_obj_with_elements("25544", 7000, 0.001, 51.6, name="ISS")
        obj_b = _make_obj_with_elements("99999", 7002, 0.001, 51.6, name="DEBRIS")

        assert exc.is_excluded(obj_a, obj_b) is True
        assert exc.is_excluded(obj_b, obj_a) is True  # order insensitive

    def test_unregistered_pair_not_excluded(self):
        exc = ExclusionList()
        exc.add_pair("1", "2")

        obj_a = _make_obj_with_elements("3", 7000, 0.001, 51.6)
        obj_b = _make_obj_with_elements("4", 7002, 0.001, 51.6)

        assert exc.is_excluded(obj_a, obj_b) is False

    def test_add_pattern_starlink(self):
        exc = ExclusionList()
        exc.add_pattern("STARLINK*", "STARLINK*")

        sl1 = _make_obj_with_elements("1", 7000, 0.001, 53.0, name="STARLINK-100")
        sl2 = _make_obj_with_elements("2", 7001, 0.001, 53.0, name="STARLINK-200")
        other = _make_obj_with_elements("3", 7000, 0.001, 51.6, name="ISS")

        assert exc.is_excluded(sl1, sl2) is True
        assert exc.is_excluded(sl2, sl1) is True
        assert exc.is_excluded(sl1, other) is False
        assert exc.is_excluded(other, sl1) is False

    def test_pattern_case_insensitive(self):
        exc = ExclusionList()
        exc.add_pattern("starlink*", "starlink*")

        sl1 = _make_obj_with_elements("1", 7000, 0.001, 53.0, name="STARLINK-1")
        sl2 = _make_obj_with_elements("2", 7001, 0.001, 53.0, name="starlink-2")

        assert exc.is_excluded(sl1, sl2) is True

    def test_empty_exclusion_list(self):
        exc = ExclusionList()
        obj_a = _make_obj_with_elements("1", 7000, 0.001, 51.6)
        obj_b = _make_obj_with_elements("2", 7002, 0.001, 51.6)
        assert exc.is_excluded(obj_a, obj_b) is False

    def test_mixed_patterns_and_pairs(self):
        exc = ExclusionList()
        exc.add_pair("100", "200")
        exc.add_pattern("GPS*", "GPS*")

        gps1 = _make_obj_with_elements("300", 26560, 0.01, 55.0, name="GPS-BLK-IIF-1")
        gps2 = _make_obj_with_elements("400", 26560, 0.01, 55.0, name="GPS-BLK-IIF-2")
        pair_a = _make_obj_with_elements("100", 7000, 0.001, 51.6)
        pair_b = _make_obj_with_elements("200", 7001, 0.001, 51.6)

        assert exc.is_excluded(gps1, gps2) is True
        assert exc.is_excluded(pair_a, pair_b) is True
        assert exc.is_excluded(gps1, pair_a) is False


# ---------------------------------------------------------------------------
# SmartSieveScreener with mocked Stage 2 and 3
# ---------------------------------------------------------------------------

class TestSmartSieveScreener:

    def test_empty_catalog_returns_empty(self):
        screener = SmartSieveScreener()
        result = screener.screen([])
        assert result == []

    def test_single_object_no_pairs(self):
        obj = _make_obj_with_elements("1", 7000.0, 0.001, 51.6)
        screener = SmartSieveScreener()
        result = screener.screen([obj])
        assert result == []

    def test_exclusion_list_applied_before_stage2(self):
        """Excluded pairs should not survive even if orbits would pass."""
        obj1 = _make_obj_with_elements("1", 7000, 0.0, 45.0, 0.0, name="STARLINK-1")
        obj2 = _make_obj_with_elements("2", 7000, 0.0, 45.0, 90.0, name="STARLINK-2")

        exc = ExclusionList()
        exc.add_pattern("STARLINK*", "STARLINK*")

        screener = SmartSieveScreener(
            altitude_pad_km=100.0,
            moid_threshold_km=1000.0,
            exclusion_list=exc,
        )

        # Mock Stage 2 + Stage 3 to pass everything through
        with patch.object(screener.stage2, 'filter', return_value=[(0, 1)]):
            with patch.object(screener.stage3, 'filter', return_value=[(0, 1, datetime.utcnow())]):
                # Stage 1 will pass them (same altitude), then exclusion removes them
                result = screener.screen([obj1, obj2])

        assert result == []

    def test_no_exclusions_passes_through(self):
        """Without exclusions, screener should pass what stages allow."""
        obj1 = _make_obj_with_elements("1", 7000, 0.0, 45.0, 0.0, name="SAT-1")
        obj2 = _make_obj_with_elements("2", 7000, 0.0, 45.0, 90.0, name="SAT-2")

        screener = SmartSieveScreener(
            altitude_pad_km=100.0,
            moid_threshold_km=1000.0,
        )
        tca = datetime(2024, 2, 14, 12, 0, 0)

        with patch.object(screener.stage2, 'filter', return_value=[(0, 1)]):
            with patch.object(screener.stage3, 'filter', return_value=[(0, 1, tca)]):
                result = screener.screen([obj1, obj2])

        assert len(result) == 1
        assert result[0][:2] == (0, 1)
        assert result[0][2] == tca

    def test_no_pairs_survive_stage1(self):
        """If LEO vs GEO — Stage 1 eliminates all pairs."""
        obj_leo = _make_obj_with_elements("1", 6800, 0.001, 51.6)
        obj_geo = _make_obj_with_elements("2", 42164, 0.001, 0.1)
        screener = SmartSieveScreener()
        result = screener.screen([obj_leo, obj_geo])
        assert result == []

    def test_no_pairs_survive_stage2(self):
        """Orbits at same altitude but impossible MOID → Stage 2 eliminates."""
        obj1 = _make_obj_with_elements("1", 7000, 0.0, 45.0, 0.0)
        obj2 = _make_obj_with_elements("2", 7000, 0.0, 45.0, 90.0)
        screener = SmartSieveScreener(moid_threshold_km=0.0)  # threshold = 0 → nothing passes

        with patch.object(screener.stage2, 'filter', return_value=[]):
            result = screener.screen([obj1, obj2])

        assert result == []

    def test_no_pairs_survive_stage3(self):
        """Stage 2 passes but Stage 3 eliminates all."""
        obj1 = _make_obj_with_elements("1", 7000, 0.0, 45.0, 0.0)
        obj2 = _make_obj_with_elements("2", 7000, 0.0, 45.0, 90.0)
        screener = SmartSieveScreener()

        with patch.object(screener.stage2, 'filter', return_value=[(0, 1)]):
            with patch.object(screener.stage3, 'filter', return_value=[]):
                result = screener.screen([obj1, obj2])

        assert result == []

    def test_screen_with_start_epoch(self):
        """Passing start_epoch should work without error."""
        obj1 = _make_obj_with_elements("1", 7000, 0.0, 45.0, 0.0)
        obj2 = _make_obj_with_elements("2", 42164, 0.001, 0.1)
        epoch = datetime(2024, 2, 14)
        screener = SmartSieveScreener()
        result = screener.screen([obj1, obj2], start_epoch=epoch)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# TimeFilter
# ---------------------------------------------------------------------------

class TestTimeFilter:

    def test_empty_pairs_returns_empty(self):
        filt = TimeFilter(window_hours=1.0, step_seconds=60.0)
        result = filt.filter([], [], datetime(2024, 2, 14))
        assert result == []

    def test_with_iss_self_pair(self):
        """Self-conjunction: ISS vs ISS should survive (distance = 0)."""
        iss = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2, name="ISS")
        iss2 = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2, name="ISS2")
        iss2.norad_id = "25545"

        filt = TimeFilter(window_hours=1.0, step_seconds=60.0, coarse_threshold_km=50.0)
        epoch = iss.elements.epoch

        result = filt.filter([iss, iss2], [(0, 1)], start_epoch=epoch)

        # Self-conjunction: distance = 0 always, should survive
        assert len(result) == 1
        assert result[0][:2] == (0, 1)

    def test_well_separated_pair_eliminated(self):
        """Two objects in very different orbits should be eliminated by time filter."""
        iss = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2, name="ISS")
        # Create a GEO-like object with no satellite (will be skipped)
        geo = _make_obj_with_elements("99999", 42164, 0.001, 0.1)

        filt = TimeFilter(window_hours=0.5, step_seconds=60.0, coarse_threshold_km=1.0)
        epoch = iss.elements.epoch

        # geo.satellite = None → will be skipped, pair eliminated
        result = filt.filter([iss, geo], [(0, 1)], start_epoch=epoch)
        assert len(result) == 0

    def test_default_epoch_uses_utcnow(self):
        """When start_epoch=None, filter should use utcnow without error."""
        iss = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2, name="ISS")
        filt = TimeFilter(window_hours=0.1, step_seconds=30.0)
        # Should not raise
        result = filt.filter([iss], [], start_epoch=None)
        assert result == []

    def test_approximate_tca_within_window(self):
        """Returned TCA should fall within the screening window."""
        iss = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2, name="ISS")
        iss2 = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2, name="ISS2")
        iss2.norad_id = "25545"

        window_hours = 1.0
        epoch = iss.elements.epoch
        filt = TimeFilter(window_hours=window_hours, step_seconds=60.0, coarse_threshold_km=100.0)
        result = filt.filter([iss, iss2], [(0, 1)], start_epoch=epoch)

        if result:
            tca = result[0][2]
            assert tca >= epoch
            assert tca <= epoch + timedelta(hours=window_hours)
