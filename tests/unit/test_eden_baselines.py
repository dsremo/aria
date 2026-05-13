"""Tests for EDEN ISS Antarctic greenhouse baseline module."""

from __future__ import annotations

import math
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from aria.simulation.eden_iss_baselines import (
    EDEN_ISS_BASELINES,
    SensorBaseline,
    apply_mission_drift,
    get_eden_iss_par_w_per_m2,
    get_realistic_value,
    load_baselines,
    parse_eden_iss_data,
    _compute_mean,
    _compute_std,
    _percentile,
)


# ────────────────────────────────────────────────────────────
#  1. HARDCODED BASELINES SANITY
# ────────────────────────────────────────────────────────────

class TestHardcodedBaselines:
    """Verify the hardcoded EDEN ISS baselines match known data ranges."""

    def test_baselines_has_required_keys(self):
        required = {"co2_ppm", "temperature_c", "humidity_pct", "par_umol"}
        assert required.issubset(EDEN_ISS_BASELINES.keys())

    def test_co2_range_realistic(self):
        bl = EDEN_ISS_BASELINES["co2_ppm"]
        # EDEN ISS greenhouse CO2 runs 400-2030 ppm (enriched)
        assert 800 < bl.mean < 1400, f"CO2 mean {bl.mean} outside expected range"
        assert bl.p5 >= 0
        assert bl.p95 <= 2500
        assert bl.std > 100  # High variance expected in greenhouse CO2

    def test_temperature_range_realistic(self):
        bl = EDEN_ISS_BASELINES["temperature_c"]
        # EDEN ISS greenhouse ~19-25C
        assert 18 < bl.mean < 26, f"Temp mean {bl.mean} outside expected range"
        assert bl.p5 > 15
        assert bl.p95 < 30

    def test_humidity_range_realistic(self):
        bl = EDEN_ISS_BASELINES["humidity_pct"]
        # EDEN ISS greenhouse 50-80% RH
        assert 50 < bl.mean < 80, f"RH mean {bl.mean} outside expected range"
        assert bl.p5 > 30
        assert bl.p95 < 100

    def test_par_range_realistic(self):
        bl = EDEN_ISS_BASELINES["par_umol"]
        # PAR includes dark periods (0) and active lighting (up to ~440 umol)
        assert bl.mean > 10  # Includes off-periods
        assert bl.p95 > 200  # Active lighting should be high
        assert bl.max <= 600  # Physical upper bound for LED arrays

    def test_all_baselines_have_positive_samples(self):
        for key, bl in EDEN_ISS_BASELINES.items():
            assert bl.n_samples > 0, f"{key} has 0 samples"

    def test_all_baselines_p5_le_mean_le_p95(self):
        for key, bl in EDEN_ISS_BASELINES.items():
            assert bl.p5 <= bl.mean <= bl.p95, (
                f"{key}: p5={bl.p5}, mean={bl.mean}, p95={bl.p95}"
            )


# ────────────────────────────────────────────────────────────
#  2. REALISTIC VALUE SAMPLING
# ────────────────────────────────────────────────────────────

class TestGetRealisticValue:
    """Test the stochastic sampling function."""

    def test_value_within_p5_p95(self):
        rng = random.Random(42)
        bl = EDEN_ISS_BASELINES["co2_ppm"]
        for _ in range(200):
            v = get_realistic_value("co2_ppm", rng)
            assert bl.p5 <= v <= bl.p95, f"CO2 value {v} outside [p5, p95]"

    def test_deterministic_with_seed(self):
        v1 = get_realistic_value("temperature_c", random.Random(123))
        v2 = get_realistic_value("temperature_c", random.Random(123))
        assert v1 == v2

    def test_different_seeds_differ(self):
        v1 = get_realistic_value("temperature_c", random.Random(1))
        v2 = get_realistic_value("temperature_c", random.Random(9999))
        # Not strictly guaranteed but extremely unlikely to be equal
        assert v1 != v2

    def test_non_negative_for_physical_quantities(self):
        rng = random.Random(42)
        for _ in range(100):
            assert get_realistic_value("co2_ppm", rng) >= 0
            assert get_realistic_value("par_umol", rng) >= 0
            assert get_realistic_value("humidity_pct", rng) >= 0

    def test_unknown_sensor_raises_keyerror(self):
        with pytest.raises(KeyError):
            get_realistic_value("nonexistent_sensor")

    def test_custom_baselines(self):
        custom = {
            "test_sensor": SensorBaseline(
                mean=50.0, std=5.0, min=20.0, max=80.0,
                p5=40.0, p95=60.0, n_samples=100, source="test",
            )
        }
        rng = random.Random(42)
        v = get_realistic_value("test_sensor", rng, baselines=custom)
        assert 40.0 <= v <= 60.0

    def test_default_rng_works(self):
        # Should not raise
        v = get_realistic_value("co2_ppm")
        assert isinstance(v, float)


# ────────────────────────────────────────────────────────────
#  3. PAR TO WATT CONVERSION
# ────────────────────────────────────────────────────────────

class TestParConversion:
    """Test PAR-to-LED-power conversion."""

    def test_par_w_per_m2_reasonable(self):
        w = get_eden_iss_par_w_per_m2()
        # EDEN ISS p95 PAR ~423 umol -> ~92 W/m2
        assert 50 < w < 150, f"LED W/m2 = {w} seems unreasonable"

    def test_par_conversion_math(self):
        # 423 umol / 4.6 umol_per_W = ~91.96
        w = get_eden_iss_par_w_per_m2()
        expected = 423.0 / 4.6
        assert abs(w - expected) < 1.0

    def test_par_fallback_without_data(self):
        w = get_eden_iss_par_w_per_m2(baselines={})
        assert w == 50.0  # documented fallback


# ────────────────────────────────────────────────────────────
#  4. DATA PARSING (integration-ish, uses actual CSV files)
# ────────────────────────────────────────────────────────────

class TestParsing:
    """Test CSV parsing — only runs if data directory exists."""

    @pytest.fixture
    def data_dir(self):
        aria_root = Path(__file__).resolve().parents[2]
        d = aria_root / "data" / "raw" / "eden_iss" / "edeniss2020"
        if not d.exists():
            pytest.skip("EDEN ISS data directory not present")
        return d

    def test_parse_returns_baselines(self, data_dir):
        baselines = parse_eden_iss_data(data_dir, subsystem_filter="AMS-FEG")
        assert len(baselines) > 0
        assert "co2_ppm" in baselines

    def test_parsed_co2_matches_hardcoded(self, data_dir):
        parsed = parse_eden_iss_data(data_dir, subsystem_filter="AMS-FEG")
        if "co2_ppm" not in parsed:
            pytest.skip("CO2 data not parsed")
        hardcoded = EDEN_ISS_BASELINES["co2_ppm"]
        # Allow 10% tolerance: hardcoded is from co2-1 only, parsed aggregates
        # co2-1 + co2-gl which have slightly different distributions
        assert abs(parsed["co2_ppm"].mean - hardcoded.mean) / hardcoded.mean < 0.10

    def test_load_baselines_uses_data_when_available(self, data_dir):
        baselines = load_baselines(data_dir)
        assert len(baselines) >= 4  # co2, temp, rh, par at minimum


# ────────────────────────────────────────────────────────────
#  5. LOAD BASELINES FALLBACK
# ────────────────────────────────────────────────────────────

class TestLoadBaselines:
    """Test the load_baselines fallback logic."""

    def test_fallback_when_dir_missing(self):
        baselines = load_baselines(data_dir="/nonexistent/path")
        # Should fall back to hardcoded
        assert "co2_ppm" in baselines
        assert baselines["co2_ppm"].mean == EDEN_ISS_BASELINES["co2_ppm"].mean

    def test_fallback_when_parse_raises(self):
        with patch(
            "aria.simulation.eden_iss_baselines.parse_eden_iss_data",
            side_effect=RuntimeError("boom"),
        ):
            baselines = load_baselines()
            assert "co2_ppm" in baselines


# ────────────────────────────────────────────────────────────
#  6. HELPER FUNCTIONS
# ────────────────────────────────────────────────────────────

class TestHelpers:
    def test_compute_mean(self):
        assert _compute_mean([1.0, 2.0, 3.0]) == 2.0
        assert _compute_mean([]) == 0.0

    def test_compute_std(self):
        vals = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        mean = _compute_mean(vals)
        std = _compute_std(vals, mean)
        assert 1.5 < std < 2.5  # known std ~2.0

    def test_percentile(self):
        vals = list(range(100))
        assert _percentile(vals, 50) == 50
        assert _percentile(vals, 5) == 5
        assert _percentile(vals, 95) == 95
        assert _percentile([], 50) == 0.0


# ────────────────────────────────────────────────────────────
#  7. INTEGRATION WITH HABITAT SYSTEMS
# ────────────────────────────────────────────────────────────

class TestHabitatIntegration:
    """Verify that habitat_systems uses EDEN ISS baselines."""

    def test_agricultural_zone_co2_is_eden_iss(self):
        from aria.simulation.habitat_systems import EnvironmentalControlState
        state = EnvironmentalControlState()
        # Should be ~1063 ppm, not the old 1200 ppm
        assert 900 < state.agricultural_zone.co2_ppm < 1200

    def test_agricultural_zone_temp_is_eden_iss(self):
        from aria.simulation.habitat_systems import EnvironmentalControlState
        state = EnvironmentalControlState()
        # Should be ~21.89C, not the old 25C
        assert 20 < state.agricultural_zone.target_temp_c < 24

    def test_agricultural_zone_humidity_is_eden_iss(self):
        from aria.simulation.habitat_systems import EnvironmentalControlState
        state = EnvironmentalControlState()
        # Should be ~63.32%, not the old 70%
        assert 58 < state.agricultural_zone.target_humidity_rh < 68


# ────────────────────────────────────────────────────────────
#  8. INTEGRATION WITH CROP OPTIMIZER
# ────────────────────────────────────────────────────────────

class TestCropOptimizerIntegration:
    """Verify crop optimizer uses EDEN ISS PAR validation."""

    def test_validate_light_report_structure(self):
        from aria.simulation.crop_optimizer import CropRotationOptimizer
        opt = CropRotationOptimizer(seed=42)
        report = opt.validate_light_against_eden_iss()
        assert "eden_iss_led_equivalent_w_m2" in report
        assert "crops" in report
        assert len(report["crops"]) > 0

    def test_all_crops_have_light_status(self):
        from aria.simulation.crop_optimizer import CropRotationOptimizer
        opt = CropRotationOptimizer(seed=42)
        report = opt.validate_light_against_eden_iss()
        for crop in report["crops"]:
            assert crop["status"] in ("within_range", "above_eden_iss", "below_eden_iss")
            assert crop["light_W_per_m2"] > 0

    def test_eden_iss_led_power_matches_module(self):
        from aria.simulation.crop_optimizer import _EDEN_ISS_LED_W_M2
        assert 50 < _EDEN_ISS_LED_W_M2 < 150


# ────────────────────────────────────────────────────────────
#  9. MISSION DRIFT MODEL
# ────────────────────────────────────────────────────────────

class TestApplyMissionDrift:
    """Verify the agricultural baseline drift model."""

    def test_year_zero_returns_same_values(self):
        drifted = apply_mission_drift(EDEN_ISS_BASELINES, 0.0)
        for key in EDEN_ISS_BASELINES:
            assert drifted[key].mean == pytest.approx(
                EDEN_ISS_BASELINES[key].mean, rel=1e-4
            ), f"{key} mean changed at year 0"

    def test_negative_year_treated_as_zero(self):
        drifted_neg = apply_mission_drift(EDEN_ISS_BASELINES, -10.0)
        drifted_zero = apply_mission_drift(EDEN_ISS_BASELINES, 0.0)
        for key in EDEN_ISS_BASELINES:
            assert drifted_neg[key].mean == pytest.approx(
                drifted_zero[key].mean, rel=1e-4
            )

    def test_co2_mean_drifts_toward_target_over_time(self):
        bl0 = apply_mission_drift(EDEN_ISS_BASELINES, 0.0)
        bl50 = apply_mission_drift(EDEN_ISS_BASELINES, 50.0)
        bl200 = apply_mission_drift(EDEN_ISS_BASELINES, 200.0)
        # CO2 target is 1100 ppm; starting mean is 1063.24
        # At year 50, should be between start and target
        assert bl0["co2_ppm"].mean < bl50["co2_ppm"].mean < 1100.0
        # At year 200, should be very close to target
        assert abs(bl200["co2_ppm"].mean - 1100.0) < 10.0

    def test_std_shrinks_over_time(self):
        bl0 = apply_mission_drift(EDEN_ISS_BASELINES, 0.0)
        bl100 = apply_mission_drift(EDEN_ISS_BASELINES, 100.0)
        for key in ("co2_ppm", "temperature_c", "humidity_pct", "vpd_mbar"):
            if key in EDEN_ISS_BASELINES:
                assert bl100[key].std <= bl0[key].std + 1e-9, (
                    f"{key} std did not decrease: {bl0[key].std} → {bl100[key].std}"
                )

    def test_std_always_positive(self):
        bl = apply_mission_drift(EDEN_ISS_BASELINES, 500.0)
        for key, sensor in bl.items():
            assert sensor.std > 0, f"{key} std is non-positive at year 500"

    def test_par_mean_increases_over_time(self):
        bl0 = apply_mission_drift(EDEN_ISS_BASELINES, 0.0)
        bl100 = apply_mission_drift(EDEN_ISS_BASELINES, 100.0)
        # PAR target (250) > starting mean (178.70)
        assert bl100["par_umol"].mean > bl0["par_umol"].mean

    def test_source_label_includes_year(self):
        bl = apply_mission_drift(EDEN_ISS_BASELINES, 42.0)
        assert "drift-adjusted yr=42" in bl["co2_ppm"].source

    def test_unknown_keys_pass_through_unchanged(self):
        custom = {
            "co2_ppm": EDEN_ISS_BASELINES["co2_ppm"],
            "exotic_gas": SensorBaseline(
                mean=5.0, std=1.0, min=0.0, max=10.0,
                p5=3.0, p95=7.0, n_samples=100, source="test",
            ),
        }
        drifted = apply_mission_drift(custom, 50.0)
        assert drifted["exotic_gas"] is custom["exotic_gas"]

    def test_p5_lte_mean_lte_p95_after_drift(self):
        for t in (0.0, 10.0, 50.0, 100.0, 200.0):
            drifted = apply_mission_drift(EDEN_ISS_BASELINES, t)
            for key, bl in drifted.items():
                assert bl.p5 <= bl.mean <= bl.p95, (
                    f"t={t} {key}: p5={bl.p5} mean={bl.mean} p95={bl.p95}"
                )
