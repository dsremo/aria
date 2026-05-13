"""Tests for maneuver detection and breakup detection."""

import math
from datetime import datetime, timedelta

import pytest

from aria.conjunction.core.types import ObjectType, OrbitalElements, SpaceObject
from aria.conjunction.data.breakup_detect import BreakupDetector
from aria.conjunction.data.maneuver_detect import DELTA_N_THRESHOLD, ManeuverFlag, detect_maneuver

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_obj(norad_id: str, sma: float, ecc: float, inc_deg: float,
              raan_deg: float = 0.0, epoch: datetime | None = None,
              obj_type: ObjectType = ObjectType.PAYLOAD) -> SpaceObject:
    if epoch is None:
        epoch = datetime(2024, 2, 14, 0, 0, 0)
    elements = OrbitalElements(
        semi_major_axis=sma,
        eccentricity=ecc,
        inclination=math.radians(inc_deg),
        raan=math.radians(raan_deg),
        arg_perigee=0.0,
        true_anomaly=0.0,
        epoch=epoch,
    )
    return SpaceObject(
        norad_id=norad_id,
        name=f"SAT-{norad_id}",
        tle_line1="",
        tle_line2="",
        object_type=obj_type,
        elements=elements,
    )


# ---------------------------------------------------------------------------
# detect_maneuver
# ---------------------------------------------------------------------------

class TestDetectManeuver:

    def test_no_maneuver_stable_orbit(self):
        """Polar orbit (inc=90°): zero RAAN drift, same SMA/ecc → no maneuver."""
        # inc=90° → cos(inc)=0 → RAAN drift rate = 0 → residual RAAN change = 0
        t0 = datetime(2024, 2, 14, 0, 0, 0)
        t1 = t0 + timedelta(hours=8)
        tle_old = _make_obj("1", sma=7000.0, ecc=0.001, inc_deg=90.0, epoch=t0)
        tle_new = _make_obj("1", sma=7000.0, ecc=0.001, inc_deg=90.0, epoch=t1)
        result = detect_maneuver(tle_old, tle_new)
        assert result is None

    def test_different_norad_id_returns_none(self):
        """Different NORAD IDs → no maneuver (wrong comparison)."""
        tle_old = _make_obj("1", sma=7000.0, ecc=0.001, inc_deg=51.6)
        tle_new = _make_obj("2", sma=7010.0, ecc=0.001, inc_deg=51.6)
        result = detect_maneuver(tle_old, tle_new)
        assert result is None

    def test_missing_elements_returns_none(self):
        """Missing orbital elements → return None."""
        tle_old = SpaceObject(norad_id="1", name="X", tle_line1="", tle_line2="",
                               elements=None)
        tle_new = _make_obj("1", sma=7000.0, ecc=0.001, inc_deg=51.6)
        assert detect_maneuver(tle_old, tle_new) is None
        assert detect_maneuver(tle_new, tle_old) is None

    def test_negative_dt_returns_none(self):
        """If new TLE is older than old TLE → return None."""
        t0 = datetime(2024, 2, 15, 0, 0, 0)
        t1 = datetime(2024, 2, 14, 0, 0, 0)  # earlier
        tle_old = _make_obj("1", sma=7000.0, ecc=0.001, inc_deg=51.6, epoch=t0)
        tle_new = _make_obj("1", sma=7010.0, ecc=0.001, inc_deg=51.6, epoch=t1)
        result = detect_maneuver(tle_old, tle_new)
        assert result is None

    def test_altitude_change_maneuver_detected(self):
        """Large mean motion change → maneuver detected."""
        t0 = datetime(2024, 2, 14, 0, 0, 0)
        t1 = t0 + timedelta(hours=6)
        # sma changes significantly → mean motion changes
        # n = sqrt(mu/a^3), for a=7000 km: n ≈ 1.0781e-3 rad/s = 14.91 rev/day
        # for a=7050 km: n ≈ 14.80 rev/day → Δn = 0.11 > threshold 0.005
        tle_old = _make_obj("1", sma=7000.0, ecc=0.001, inc_deg=51.6, epoch=t0)
        tle_new = _make_obj("1", sma=7080.0, ecc=0.001, inc_deg=51.6, epoch=t1)
        result = detect_maneuver(tle_old, tle_new)
        assert result is not None
        assert result.norad_id == "1"
        assert result.delta_mean_motion > DELTA_N_THRESHOLD

    def test_eccentricity_change_detected(self):
        """Large eccentricity change → maneuver detected."""
        t0 = datetime(2024, 2, 14, 0, 0, 0)
        t1 = t0 + timedelta(hours=8)
        tle_old = _make_obj("1", sma=7000.0, ecc=0.001, inc_deg=51.6, epoch=t0)
        tle_new = _make_obj("1", sma=7000.0, ecc=0.010, inc_deg=51.6, epoch=t1)
        result = detect_maneuver(tle_old, tle_new)
        assert result is not None
        assert result.delta_eccentricity > 0.0005

    def test_maneuver_flag_fields(self):
        """ManeuverFlag should have all expected fields."""
        t0 = datetime(2024, 2, 14, 0, 0, 0)
        t1 = t0 + timedelta(hours=6)
        tle_old = _make_obj("1", sma=7000.0, ecc=0.001, inc_deg=51.6, epoch=t0)
        tle_new = _make_obj("1", sma=7100.0, ecc=0.001, inc_deg=51.6, epoch=t1)
        result = detect_maneuver(tle_old, tle_new)
        assert result is not None
        assert isinstance(result, ManeuverFlag)
        assert result.norad_id == "1"
        assert result.confidence in ("HIGH", "MEDIUM", "LOW")
        assert result.reason != ""
        assert result.detected_at == t1

    def test_explicit_dt_hours(self):
        """Providing dt_hours explicitly should work."""
        tle_old = _make_obj("1", sma=7000.0, ecc=0.001, inc_deg=51.6)
        tle_new = _make_obj("1", sma=7100.0, ecc=0.001, inc_deg=51.6)
        result = detect_maneuver(tle_old, tle_new, dt_hours=6.0)
        assert result is not None

    def test_high_confidence_multiple_triggers(self):
        """Multiple threshold violations → HIGH confidence."""
        t0 = datetime(2024, 2, 14, 0, 0, 0)
        t1 = t0 + timedelta(hours=6)
        tle_old = _make_obj("1", sma=7000.0, ecc=0.001, inc_deg=51.6, epoch=t0)
        tle_new = _make_obj("1", sma=7100.0, ecc=0.010, inc_deg=51.6, epoch=t1)
        result = detect_maneuver(tle_old, tle_new)
        assert result is not None
        assert result.confidence == "HIGH"


# ---------------------------------------------------------------------------
# BreakupDetector
# ---------------------------------------------------------------------------

class TestBreakupDetector:

    def test_first_check_triggers_alert_if_large_bin(self):
        """First check: all objects are 'new' → alert if count >= threshold."""
        detector = BreakupDetector(min_new_objects=5)
        catalog = [_make_obj(str(i), sma=7000.0, ecc=0.001, inc_deg=51.6)
                   for i in range(20)]
        alerts = detector.check(catalog)
        # All 20 objects are new on first call → alert
        assert len(alerts) >= 1
        assert alerts[0].new_object_count == 20

    def test_sudden_growth_detected(self):
        """Adding many objects to same bin after history is established → alert."""
        detector = BreakupDetector(
            altitude_bin_km=50.0,
            inclination_bin_deg=2.0,
            min_new_objects=5,
        )

        # First check: 3 existing objects → alert since 3 < 5 threshold? No, 3 < 5 → no alert
        initial = [_make_obj(str(i), sma=7000.0, ecc=0.001, inc_deg=51.6)
                   for i in range(3)]
        detector.check(initial)  # 3 objects, below threshold of 5

        # Second check: 10 new objects added → should trigger
        current = initial + [
            _make_obj(str(i + 100), sma=7000.0, ecc=0.001, inc_deg=51.6)
            for i in range(10)
        ]
        alerts = detector.check(current)
        assert len(alerts) == 1
        assert alerts[0].new_object_count == 10

    def test_growth_below_threshold_no_alert(self):
        """Adding fewer objects than threshold → no alert."""
        detector = BreakupDetector(min_new_objects=10)

        # First check with 2 objects (below threshold of 10)
        initial = [_make_obj(str(i), sma=7000.0, ecc=0.001, inc_deg=51.6)
                   for i in range(2)]
        detector.check(initial)

        # Add only 5 new objects but threshold is 10
        current = initial + [
            _make_obj(str(i + 10), sma=7000.0, ecc=0.001, inc_deg=51.6)
            for i in range(5)
        ]
        alerts = detector.check(current)
        assert len(alerts) == 0

    def test_bin_key_none_for_no_elements(self):
        """Objects without elements should return None bin key → skipped."""
        detector = BreakupDetector(min_new_objects=1)
        obj_no_el = SpaceObject(norad_id="0", name="X", tle_line1="", tle_line2="",
                                elements=None)
        alerts = detector.check([obj_no_el])
        assert len(alerts) == 0

    def test_different_bins_separate_alerts(self):
        """Objects in different orbital regimes trigger separate breakup checks."""
        detector = BreakupDetector(min_new_objects=3)

        # First check with 2 objects each bin (below threshold of 3)
        initial_leo = [_make_obj(str(i), sma=7000.0, ecc=0.001, inc_deg=51.6)
                       for i in range(2)]
        initial_meo = [_make_obj(str(i + 50), sma=12000.0, ecc=0.001, inc_deg=55.0)
                       for i in range(2)]
        detector.check(initial_leo + initial_meo)

        # Add 5 new objects in each bin
        leo = initial_leo + [_make_obj(str(i + 100), sma=7000.0, ecc=0.001, inc_deg=51.6)
                              for i in range(5)]
        meo = initial_meo + [_make_obj(str(i + 200), sma=12000.0, ecc=0.001, inc_deg=55.0)
                              for i in range(5)]
        alerts = detector.check(leo + meo)
        assert len(alerts) == 2

    def test_parent_candidate_identified(self):
        """A pre-existing PAYLOAD in the same bin should be identified as parent."""
        detector = BreakupDetector(min_new_objects=3)

        # Parent payload pre-exists (first check, 1 object, below threshold)
        parent = _make_obj("parent", sma=7000.0, ecc=0.001, inc_deg=51.6,
                           obj_type=ObjectType.PAYLOAD)
        detector.check([parent])

        # New debris fragments appear
        debris = [_make_obj(str(i), sma=7000.0, ecc=0.001, inc_deg=51.6,
                            obj_type=ObjectType.DEBRIS)
                  for i in range(5)]
        alerts = detector.check([parent] + debris)
        assert len(alerts) == 1
        assert alerts[0].parent_candidate is not None
        assert alerts[0].parent_candidate.norad_id == "parent"

    def test_alert_altitude_band_correct(self):
        """Alert altitude band should reflect the actual altitude."""
        # First check with 2 objects below threshold
        detector = BreakupDetector(altitude_bin_km=50.0, min_new_objects=3)
        initial = [_make_obj(str(i), sma=7000.0, ecc=0.001, inc_deg=51.6) for i in range(2)]
        detector.check(initial)

        # Add 5 more → triggers alert
        current = initial + [_make_obj(str(i + 10), sma=7000.0, ecc=0.001, inc_deg=51.6)
                              for i in range(5)]
        alerts = detector.check(current)
        assert len(alerts) == 1
        alt_lo, alt_hi = alerts[0].altitude_band
        assert alt_lo < 700  # should be around 600 km
        assert alt_hi - alt_lo == pytest.approx(50.0)

    def test_same_catalog_second_check_no_alerts(self):
        """Running the same catalog twice → no new alerts on second run."""
        detector = BreakupDetector(min_new_objects=3)
        catalog = [_make_obj(str(i), sma=7000.0, ecc=0.001, inc_deg=51.6) for i in range(10)]

        detector.check(catalog)   # first check
        alerts = detector.check(catalog)  # second: same objects → 0 new
        assert len(alerts) == 0
