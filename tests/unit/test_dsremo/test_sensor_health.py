"""Tests for V3-M1 SensorHealthMonitor.

Validates:
 1. SensorCalibration.corrected_value applies offset before gain (NASA/TM-2010-216260 §4.3)
 2. corrected_value returns raw on pathological gain ≤ -50 %
 3. Empty monitor returns raw value + unchanged quality
 4. record_calibration populates tier from gain/offset thresholds
 5. get_or_create is idempotent (same instance)
 6. 1 % gain error → DEGRADED tier
 7. 5 % gain error → UNTRUSTWORTHY tier
 8. 0.5 % gain error → NOMINAL tier
 9. Offset tier uses range_full_scale when provided
10. Offset tier uses absolute fallback when range_full_scale = 0
11. Stale calibration (age > 90 days) promotes to STALE tier
12. quality_factor decays past stale threshold
13. apply_correction returns (corrected, quality*q_factor, tier)
14. apply_correction compounds input quality and sensor quality multiplicatively
15. apply_correction skips unknown channels (passthrough)
16. channels_in_tier filters by requested tier
17. iter_calibrations yields every registered sensor
18. refresh_tier reclassifies after artificial time advance
19. History accumulates across multiple calibrations
20. Combined gain + offset + stale → stale dominates (STALE tier)
21. UNTRUSTWORTHY dominates over DEGRADED when both would apply
22. Quality factor for NOMINAL sensor = 1.0 regardless of age when never calibrated
"""

from __future__ import annotations

import pytest

from aria.dsremo.detection.sensor_health import (
    CALIBRATION_STALE_S,
    QUALITY_DEGRADED,
    QUALITY_NOMINAL,
    QUALITY_UNTRUSTWORTHY,
    SensorCalibration,
    SensorHealthMonitor,
    SensorHealthTier,
    apply_sensor_corrections,
    get_monitor,
    reset_monitor,
)


class TestSensorCalibration:

    def test_corrected_value_applies_offset_then_gain(self):
        cal = SensorCalibration(
            satellite_id="SAT-1",
            parameter="battery_voltage",
            gain_error_estimate=0.02,    # +2 %
            offset_error_estimate=0.10,  # +0.10 V bias
        )
        # raw=29.14 → (29.14 - 0.10) / 1.02 = 28.47…
        corrected = cal.corrected_value(29.14)
        assert abs(corrected - (29.04 / 1.02)) < 1e-9

    def test_pathological_gain_returns_raw(self):
        cal = SensorCalibration(
            satellite_id="SAT-1", parameter="x", gain_error_estimate=-0.99
        )
        assert cal.corrected_value(5.0) == 5.0

    def test_quality_factor_nominal_never_calibrated(self):
        cal = SensorCalibration(satellite_id="SAT", parameter="p")
        # Never calibrated (epoch=0) → base quality only, no decay branch.
        assert cal.quality_factor(now_epoch=1e9) == QUALITY_NOMINAL


class TestRecordAndTier:

    def test_record_calibration_sets_nominal_tier_for_small_error(self):
        mon = SensorHealthMonitor()
        cal = mon.record_calibration("SAT", "p", gain_error=0.005, offset_error=0.0, epoch=1.0)
        assert cal.tier == SensorHealthTier.NOMINAL

    def test_one_percent_gain_error_is_degraded(self):
        mon = SensorHealthMonitor()
        cal = mon.record_calibration("SAT", "p", gain_error=0.012, offset_error=0.0, epoch=1.0)
        assert cal.tier == SensorHealthTier.DEGRADED

    def test_five_percent_gain_error_is_untrustworthy(self):
        mon = SensorHealthMonitor()
        cal = mon.record_calibration("SAT", "p", gain_error=0.06, offset_error=0.0, epoch=1.0)
        assert cal.tier == SensorHealthTier.UNTRUSTWORTHY

    def test_get_or_create_is_idempotent(self):
        mon = SensorHealthMonitor()
        a = mon.get_or_create("SAT", "p")
        b = mon.get_or_create("SAT", "p")
        assert a is b

    def test_offset_tier_uses_range_full_scale(self):
        """Range = 100 → 1 % threshold = 1.0 in absolute units.  Offset 1.5 → DEGRADED."""
        mon = SensorHealthMonitor()
        cal = mon.record_calibration(
            "SAT", "p", gain_error=0.0, offset_error=1.5,
            range_full_scale=100.0, epoch=1.0,
        )
        assert cal.tier == SensorHealthTier.DEGRADED

    def test_offset_tier_falls_back_when_range_unset(self):
        """Offset 2e-3 with range=0 hits the absolute fallback (1e-3 → DEGRADED)."""
        mon = SensorHealthMonitor()
        cal = mon.record_calibration("SAT", "p", gain_error=0.0, offset_error=2e-3, epoch=1.0)
        assert cal.tier == SensorHealthTier.DEGRADED

    def test_untrustworthy_dominates_over_degraded(self):
        """Both gain_error and offset_error exceed degraded, one exceeds untrustworthy."""
        mon = SensorHealthMonitor()
        cal = mon.record_calibration("SAT", "p", gain_error=0.06, offset_error=1.5,
                                     range_full_scale=100.0, epoch=1.0)
        assert cal.tier == SensorHealthTier.UNTRUSTWORTHY

    def test_history_accumulates(self):
        mon = SensorHealthMonitor()
        mon.record_calibration("SAT", "p", gain_error=0.001, offset_error=0.0, epoch=1.0)
        mon.record_calibration("SAT", "p", gain_error=0.002, offset_error=0.0, epoch=2.0)
        mon.record_calibration("SAT", "p", gain_error=0.003, offset_error=0.0, epoch=3.0)
        cal = mon.get("SAT", "p")
        assert cal is not None
        assert len(cal.history) == 3
        assert [h[1] for h in cal.history] == [0.001, 0.002, 0.003]


class TestStaleCalibration:

    def test_stale_tier_after_90_days(self):
        mon = SensorHealthMonitor()
        mon.record_calibration("SAT", "p", gain_error=0.001, offset_error=0.0, epoch=1000.0)
        # Advance beyond stale threshold.
        tier = mon.refresh_tier("SAT", "p", now_epoch=1000.0 + CALIBRATION_STALE_S + 1.0)
        assert tier == SensorHealthTier.STALE

    def test_stale_overrides_clean_channel(self):
        """STALE replaces NOMINAL even when errors are zero."""
        mon = SensorHealthMonitor()
        mon.record_calibration("SAT", "p", gain_error=0.0, offset_error=0.0, epoch=1.0)
        tier = mon.refresh_tier("SAT", "p", now_epoch=1.0 + CALIBRATION_STALE_S + 10.0)
        assert tier == SensorHealthTier.STALE

    def test_quality_decays_past_stale_threshold(self):
        cal = SensorCalibration(
            satellite_id="SAT", parameter="p",
            gain_error_estimate=0.0, offset_error_estimate=0.0,
            last_calibration_epoch=1.0, tier=SensorHealthTier.STALE,
        )
        q_fresh = cal.quality_factor(now_epoch=1.0 + CALIBRATION_STALE_S)
        q_very_old = cal.quality_factor(now_epoch=1.0 + CALIBRATION_STALE_S * 4.0)
        assert q_very_old < q_fresh


class TestApplyCorrection:

    def test_unknown_channel_passes_through(self):
        mon = SensorHealthMonitor()
        v, q, tier = mon.apply_correction("SAT", "unknown", raw_value=5.0, quality=0.9)
        assert v == 5.0
        assert q == 0.9
        assert tier == SensorHealthTier.NOMINAL

    def test_correction_applied_for_registered_channel(self):
        mon = SensorHealthMonitor()
        mon.record_calibration(
            "SAT", "V_bus",
            gain_error=0.02, offset_error=0.10,
            range_full_scale=50.0,  # 0.10/50 = 0.2% < 1% → offset not degraded
            epoch=1.0,
        )
        v, q, tier = mon.apply_correction("SAT", "V_bus", raw_value=29.14,
                                          quality=1.0, now_epoch=2.0)
        assert abs(v - (29.04 / 1.02)) < 1e-9
        # 2 % gain > 1 % → DEGRADED → quality multiplied by 0.8
        assert tier == SensorHealthTier.DEGRADED
        assert abs(q - QUALITY_DEGRADED) < 1e-9

    def test_quality_compounds_multiplicatively(self):
        mon = SensorHealthMonitor()
        mon.record_calibration("SAT", "p", gain_error=0.02, offset_error=0.0, epoch=1.0)
        _, q, _ = mon.apply_correction("SAT", "p", raw_value=1.0, quality=0.5, now_epoch=2.0)
        # 0.5 × 0.8 = 0.4
        assert abs(q - 0.5 * QUALITY_DEGRADED) < 1e-9

    def test_untrustworthy_uses_half_quality(self):
        mon = SensorHealthMonitor()
        mon.record_calibration("SAT", "p", gain_error=0.08, offset_error=0.0, epoch=1.0)
        _, q, _ = mon.apply_correction("SAT", "p", raw_value=1.0, quality=1.0, now_epoch=2.0)
        assert abs(q - QUALITY_UNTRUSTWORTHY) < 1e-9


class TestFilters:

    def test_channels_in_tier_filters_correctly(self):
        mon = SensorHealthMonitor()
        mon.record_calibration("SAT", "healthy",   gain_error=0.001, offset_error=0.0, epoch=1.0)
        mon.record_calibration("SAT", "degraded",  gain_error=0.02,  offset_error=0.0, epoch=1.0)
        mon.record_calibration("SAT", "untrusted", gain_error=0.10,  offset_error=0.0, epoch=1.0)

        nominal  = mon.channels_in_tier(SensorHealthTier.NOMINAL)
        degraded = mon.channels_in_tier(SensorHealthTier.DEGRADED)
        untrust  = mon.channels_in_tier(SensorHealthTier.UNTRUSTWORTHY)

        assert ("SAT", "healthy")   in nominal
        assert ("SAT", "degraded")  in degraded
        assert ("SAT", "untrusted") in untrust
        assert len(nominal) == 1 and len(degraded) == 1 and len(untrust) == 1

    def test_iter_calibrations_returns_all(self):
        mon = SensorHealthMonitor()
        mon.record_calibration("SAT1", "a", gain_error=0.0, offset_error=0.0, epoch=1.0)
        mon.record_calibration("SAT2", "b", gain_error=0.0, offset_error=0.0, epoch=1.0)
        cals = list(mon.iter_calibrations())
        assert len(cals) == 2

    def test_refresh_tier_for_missing_channel_returns_nominal(self):
        mon = SensorHealthMonitor()
        # No record — refresh should be a safe no-op.
        assert mon.refresh_tier("missing", "missing") == SensorHealthTier.NOMINAL


class TestApplySensorCorrections:
    """Batch-level helper that operates on TelemetryPoint lists (ingest path)."""

    def _make_point(self, satellite_id="SAT", parameter="v_bus", value=10.0, quality=1.0):
        from datetime import datetime, timezone
        from aria.dsremo.core.models import TelemetryPoint
        return TelemetryPoint(
            satellite_id=satellite_id,
            timestamp=datetime.now(timezone.utc),
            subsystem="eps",
            parameter=parameter,
            value=value,
            unit="V",
            quality=quality,
        )

    def test_unknown_channel_passes_through_unchanged(self):
        mon = SensorHealthMonitor()
        p = self._make_point()
        out = apply_sensor_corrections([p], monitor=mon)
        # Same object (not a copy) when no correction needed.
        assert len(out) == 1
        assert out[0] is p

    def test_calibrated_channel_value_and_quality_updated(self):
        mon = SensorHealthMonitor()
        mon.record_calibration(
            "SAT", "v_bus",
            gain_error=0.02, offset_error=0.0,
            range_full_scale=50.0, epoch=1.0,
        )
        p = self._make_point(value=10.0)
        out = apply_sensor_corrections([p], monitor=mon, now_epoch=2.0)
        assert len(out) == 1
        assert abs(out[0].value - (10.0 / 1.02)) < 1e-9
        # 2% gain → DEGRADED → quality factor 0.8
        assert abs(out[0].quality - QUALITY_DEGRADED) < 1e-9

    def test_preserves_length_and_order(self):
        mon = SensorHealthMonitor()
        mon.record_calibration("SAT", "a", gain_error=0.02, offset_error=0.0,
                               range_full_scale=50.0, epoch=1.0)
        pts = [
            self._make_point(parameter="a", value=1.0),  # calibrated
            self._make_point(parameter="b", value=2.0),  # uncalibrated
            self._make_point(parameter="a", value=3.0),  # calibrated
        ]
        out = apply_sensor_corrections(pts, monitor=mon, now_epoch=2.0)
        assert len(out) == 3
        # Uncalibrated point passes through unchanged.
        assert out[1].value == 2.0
        assert out[1].quality == 1.0

    def test_get_monitor_singleton(self):
        reset_monitor()
        try:
            a = get_monitor()
            b = get_monitor()
            assert a is b
        finally:
            reset_monitor()
