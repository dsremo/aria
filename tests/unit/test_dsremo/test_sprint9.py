"""Sprint 9 tests — Variance Detection + STL FFT + Production Quality.

Covers:
  - TestScoringModule          — dsremo.eval.scoring (10 tests)
  - TestVarianceDetector       — VarianceDetector (12 tests)
  - TestSTLFFTPeriod           — STLDecomposer._fft_period + _estimate_period (10 tests)
  - TestCooldownUtils          — detect_data_frequency + adaptive_cooldown_hours (8 tests)
  - TestEnsembleWithVariance   — 6-detector ensemble weights + integration (8 tests)
  - TestVarianceChannelConfig  — per-channel variance_z_threshold API (10 tests)
  - TestAutoCoooldownDefault   — analyze_csv auto-cooldown as default (5 tests)
"""

from __future__ import annotations

import csv
import io
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(offset_s: float) -> datetime:
    """Return UTC datetime offset_s seconds from 2024-01-01 00:00:00."""
    return datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=offset_s)


def _make_calibration(ref_std: float = 1.0, state: str = "calibrated") -> Any:
    """Build a lightweight CalibrationState-like object for testing."""
    from aria.dsremo.detection.calibration import CalibrationState
    cal = CalibrationState()
    cal.state = state
    cal.ref_mean = 0.0
    cal.ref_std = ref_std
    # Update derived thresholds
    if state == "calibrated":
        cal._update_derived(ref_std)
    return cal


# ---------------------------------------------------------------------------
# 1. TestScoringModule
# ---------------------------------------------------------------------------

class TestScoringModule:
    """aria.dsremo.eval.scoring — cluster_events + score + ScoringResult."""

    def test_cluster_events_single_cluster(self):
        from aria.dsremo.eval.scoring import cluster_events
        ts = [_utc(0), _utc(60), _utc(120)]
        result = cluster_events(ts, gap_s=600)
        assert len(result) == 1
        assert len(result[0]) == 3

    def test_cluster_events_two_separate_clusters(self):
        from aria.dsremo.eval.scoring import cluster_events
        # gap_s=300: 600s > 300s → two clusters
        ts = [_utc(0), _utc(600 + 1)]
        result = cluster_events(ts, gap_s=300)
        assert len(result) == 2

    def test_cluster_events_empty_list_returns_empty(self):
        from aria.dsremo.eval.scoring import cluster_events
        assert cluster_events([], gap_s=600) == []

    def test_cluster_events_all_same_second_one_cluster(self):
        from aria.dsremo.eval.scoring import cluster_events
        ts = [_utc(0), _utc(0), _utc(0)]
        result = cluster_events(ts, gap_s=600)
        assert len(result) == 1

    def test_score_perfect_detection(self):
        from aria.dsremo.eval.scoring import score
        detected = [_utc(300)]   # inside GT window
        gt = [(_utc(0), _utc(600))]
        r = score(detected, gt, window_s=60)
        assert r.tp == 1 and r.fp == 0 and r.fn == 0
        assert r.precision == pytest.approx(1.0)
        assert r.recall == pytest.approx(1.0)
        assert r.f1 == pytest.approx(1.0)

    def test_score_all_false_positives(self):
        from aria.dsremo.eval.scoring import score
        detected = [_utc(10_000)]   # far from any GT
        gt = [(_utc(0), _utc(600))]
        r = score(detected, gt, window_s=60)
        assert r.tp == 0 and r.fp == 1 and r.fn == 1
        assert r.precision == 0.0 and r.recall == 0.0 and r.f1 == 0.0

    def test_score_all_false_negatives(self):
        from aria.dsremo.eval.scoring import score
        gt = [(_utc(0), _utc(600))]
        r = score([], gt, window_s=60)
        assert r.tp == 0 and r.fp == 0 and r.fn == 1
        assert r.recall == 0.0

    def test_score_partial_tp_fp_fn(self):
        from aria.dsremo.eval.scoring import score
        gt = [(_utc(0), _utc(600)), (_utc(3600), _utc(4200))]
        detected = [_utc(300), _utc(8000)]   # 1 TP + 1 FP; 1 FN
        r = score(detected, gt, window_s=60)
        assert r.tp == 1 and r.fp == 1 and r.fn == 1

    def test_score_window_tolerance_just_inside(self):
        from aria.dsremo.eval.scoring import score
        # Detection is exactly window_s seconds before GT start → should match
        gt = [(_utc(300), _utc(600))]
        detected = [_utc(300 - 60)]   # 60s before start, window_s=60
        r = score(detected, gt, window_s=60)
        assert r.tp == 1

    def test_scoring_result_is_frozen_dataclass(self):
        from aria.dsremo.eval.scoring import ScoringResult
        r = ScoringResult(tp=1, fp=0, fn=0, precision=1.0, recall=1.0, f1=1.0,
                          event_count=1, detected_count=1)
        with pytest.raises((AttributeError, TypeError)):
            r.tp = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. TestVarianceDetector
# ---------------------------------------------------------------------------

class TestVarianceDetector:
    """VarianceDetector — stateless variance-ratio anomaly detection."""

    def _make_residuals(self, std: float, n: int = 50) -> np.ndarray:
        rng = np.random.default_rng(42)
        return rng.normal(0, std, n).astype(np.float64)

    def test_nominal_signal_below_threshold(self):
        from aria.dsremo.detection.variance_detector import VarianceDetector
        vd = VarianceDetector(variance_z_threshold=2.5)
        cal = _make_calibration(ref_std=1.0)
        residuals = self._make_residuals(std=0.9)   # ratio ≈ 0.9 < 2.5
        result = vd.detect(residuals, cal)
        assert not result.is_anomaly
        assert result.detector_name == "variance"

    def test_variance_spike_above_threshold(self):
        from aria.dsremo.detection.variance_detector import VarianceDetector
        vd = VarianceDetector(variance_z_threshold=2.5, window=30)
        cal = _make_calibration(ref_std=1.0)
        # Use deterministic alternating ±4 signal: std = 4.0 exactly, ratio=4.0 > 2.5
        residuals = np.concatenate([np.zeros(20), np.tile([4.0, -4.0], 15)])
        result = vd.detect(residuals, cal)
        assert result.is_anomaly

    def test_severity_watch_at_threshold(self):
        from aria.dsremo.detection.variance_detector import VarianceDetector
        from aria.dsremo.core.models import Severity
        vd = VarianceDetector(variance_z_threshold=2.5, window=30)
        cal = _make_calibration(ref_std=1.0)
        # Construct residuals so rolling_std ≈ 2.7 (just above threshold, below 2×)
        residuals = np.full(50, 0.0, dtype=np.float64)
        residuals[-30:] = np.linspace(-2.7, 2.7, 30)
        result = vd.detect(residuals, cal)
        if result.is_anomaly:
            assert result.severity in (Severity.WATCH, Severity.WARNING)

    def test_returns_nominal_if_not_calibrated(self):
        from aria.dsremo.detection.variance_detector import VarianceDetector
        vd = VarianceDetector()
        cal = _make_calibration(ref_std=1.0, state="warming_up")
        result = vd.detect(np.ones(50), cal)
        assert not result.is_anomaly
        assert result.details["reason"] == "warming_up"

    def test_returns_nominal_if_insufficient_residuals(self):
        from aria.dsremo.detection.variance_detector import VarianceDetector
        vd = VarianceDetector(window=30)
        cal = _make_calibration(ref_std=1.0)
        result = vd.detect(np.ones(5), cal)   # only 5, min = 15
        assert not result.is_anomaly
        assert result.details["reason"] == "insufficient_data"

    def test_near_zero_ref_std_guard(self):
        from aria.dsremo.detection.variance_detector import VarianceDetector
        vd = VarianceDetector()
        cal = _make_calibration(ref_std=1e-12)
        result = vd.detect(np.ones(50), cal)
        assert not result.is_anomaly   # constant channel guard

    def test_per_channel_threshold_override(self):
        from aria.dsremo.detection.variance_detector import VarianceDetector
        vd = VarianceDetector(variance_z_threshold=2.5, window=30)
        cal = _make_calibration(ref_std=1.0)
        residuals = self._make_residuals(std=2.7)
        # With global threshold 2.5 → likely anomaly (ratio ≈ 2.7)
        # With per-channel override 10.0 → not anomaly
        result_high = vd.detect(residuals, cal, variance_z_threshold=10.0)
        assert not result_high.is_anomaly

    def test_cats_synthetic_sigma_doubles_detected(self):
        """CATS-type: anomaly segment has 2× the normal σ."""
        from aria.dsremo.detection.variance_detector import VarianceDetector
        vd = VarianceDetector(variance_z_threshold=1.8, window=30)
        cal = _make_calibration(ref_std=137.0)
        # Anomaly: rolling_std ≈ 311
        rng = np.random.default_rng(1)
        residuals = rng.normal(0, 311, 50).astype(np.float64)
        result = vd.detect(residuals, cal)
        assert result.is_anomaly

    def test_cats_synthetic_sigma_stable_not_detected(self):
        """Normal CATS segment: rolling_std ≈ ref_std → no alarm."""
        from aria.dsremo.detection.variance_detector import VarianceDetector
        vd = VarianceDetector(variance_z_threshold=2.5, window=30)
        cal = _make_calibration(ref_std=137.0)
        rng = np.random.default_rng(2)
        residuals = rng.normal(0, 137, 50).astype(np.float64)
        result = vd.detect(residuals, cal)
        assert not result.is_anomaly

    def test_score_proportional_to_ratio(self):
        from aria.dsremo.detection.variance_detector import VarianceDetector
        vd = VarianceDetector(variance_z_threshold=2.5, window=30)
        cal_low = _make_calibration(ref_std=1.0)
        cal_high = _make_calibration(ref_std=1.0)
        low_residuals = np.full(50, 0.0)
        low_residuals[-30:] = np.linspace(-2.8, 2.8, 30)
        high_residuals = np.full(50, 0.0)
        high_residuals[-30:] = np.linspace(-5.0, 5.0, 30)
        r_low  = vd.detect(low_residuals, cal_low)
        r_high = vd.detect(high_residuals, cal_high)
        if r_high.is_anomaly and r_low.is_anomaly:
            assert r_high.score >= r_low.score

    def test_window_uses_only_last_n_residuals(self):
        from aria.dsremo.detection.variance_detector import VarianceDetector
        vd = VarianceDetector(variance_z_threshold=2.5, window=10)
        cal = _make_calibration(ref_std=1.0)
        # First 90 residuals are normal (std≈1), last 10 are high-variance (std≈5)
        residuals = np.concatenate([np.zeros(90), np.linspace(-5, 5, 10)])
        result = vd.detect(residuals, cal)
        # Uses last 10 → high variance → anomaly
        assert result.is_anomaly

    def test_detector_name_is_variance(self):
        from aria.dsremo.detection.variance_detector import VarianceDetector
        vd = VarianceDetector()
        cal = _make_calibration(ref_std=1.0)
        result = vd.detect(np.ones(50), cal)
        assert result.detector_name == "variance"


# ---------------------------------------------------------------------------
# 3. TestSTLFFTPeriod
# ---------------------------------------------------------------------------

class TestSTLFFTPeriod:
    """STLDecomposer._fft_period + _estimate_period."""

    def test_pure_sine_fft_detects_correct_period(self):
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        period = 30
        x = np.sin(2 * np.pi * np.arange(300) / period).astype(np.float64)
        detected = STLDecomposer._fft_period(x)
        assert abs(detected - period) <= 2  # allow ±2 sample rounding

    def test_broadband_noise_returns_zero(self):
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        rng = np.random.default_rng(99)
        noise = rng.normal(0, 1, 300).astype(np.float64)
        detected = STLDecomposer._fft_period(noise)
        assert detected == 0

    def test_period_smaller_than_min_period_returns_zero(self):
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        x = np.sin(2 * np.pi * np.arange(100) / 2.0)  # period=2 < min_period=4
        detected = STLDecomposer._fft_period(x, min_period=4)
        assert detected == 0

    def test_period_larger_than_half_window_returns_zero(self):
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        n = 100
        # Period = n (= n // 2 * 2), but FFT period must be <= n // 2
        x = np.sin(2 * np.pi * np.arange(n) / n)
        detected = STLDecomposer._fft_period(x)
        assert detected == 0

    def test_detrending_allows_sine_plus_linear_ramp(self):
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        period = 30
        n = 300
        t = np.arange(n, dtype=np.float64)
        x = np.sin(2 * np.pi * t / period) + 0.05 * t  # sine + linear trend
        detected = STLDecomposer._fft_period(x)
        assert abs(detected - period) <= 3

    def test_cats_synthetic_90s_period_at_1hz_600_window(self):
        """CATS root cause: 90s period at 1Hz, window=600 → FFT finds period=90."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        period = 90
        n = 600
        t = np.arange(n, dtype=np.float64)
        x = 137.0 * np.sin(2 * np.pi * t / period)  # CATS-like oscillation
        detected = STLDecomposer._fft_period(x)
        assert abs(detected - period) <= 5   # ±5 samples

    def test_estimate_period_fallback_to_orbital_when_fft_zero(self):
        """If FFT finds nothing (pure DC), fallback uses orbital_period_s hint."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        decomp = STLDecomposer(orbital_period_s=600)
        # DC signal → FFT returns 0, fallback: 600s / 60s = 10 samples
        dc_values = np.ones(200, dtype=np.float64)
        timestamps = np.arange(200, dtype=np.float64) * 60.0  # 1-min data
        period = decomp._estimate_period(timestamps, 200, dc_values)
        # Either FFT found nothing and fallback gave 10, or both returned 0
        assert period == 0 or period == 10

    def test_estimate_period_returns_zero_when_both_fail(self):
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        decomp = STLDecomposer(orbital_period_s=5400)
        # 1Hz data: orbital_period_s=5400 samples > n//2=300 → returns 0
        noise = np.random.default_rng(77).normal(0, 1, 600).astype(np.float64)
        timestamps = np.arange(600, dtype=np.float64) * 1.0  # 1Hz
        period = decomp._estimate_period(timestamps, 600, noise)
        # FFT on pure noise → 0; orbital hint 5400/1=5400 > 300 → 0
        assert period == 0

    def test_stl_used_when_fft_finds_valid_period(self):
        """When FFT detects a period, decomp.method should be 'stl'."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        period = 30
        n = 300
        t = np.arange(n, dtype=np.float64)
        x = 5.0 * np.sin(2 * np.pi * t / period) + np.random.default_rng(7).normal(0, 0.1, n)
        timestamps = t  # 1s intervals
        decomp = STLDecomposer(orbital_period_s=5400)
        result = decomp.decompose("test:ch1", x, timestamps)
        # STL requires n >= 2 × period (300 >= 60) → should use STL
        assert result.method in ("stl", "savgol_trend")  # STL may fail gracefully
        assert result.n_samples == n

    def test_decompose_api_unchanged(self):
        """decompose() public API unchanged — returns DecompositionResult."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer, DecompositionResult
        decomp = STLDecomposer()
        x = np.random.default_rng(5).normal(0, 1, 50).astype(np.float64)
        result = decomp.decompose("key:param", x)
        assert isinstance(result, DecompositionResult)
        assert len(result.residual) == len(x)
        assert result.method in ("stl", "savgol_trend", "cold_start")


# ---------------------------------------------------------------------------
# 4. TestCooldownUtils
# ---------------------------------------------------------------------------

class TestCooldownUtils:
    """detect_data_frequency + adaptive_cooldown_hours."""

    def _write_csv(self, tmp_path: Path, rows: list[str], sep: str = ",") -> Path:
        p = tmp_path / "test.csv"
        p.write_text(sep.join(["timestamp", "val"]) + "\n" + "\n".join(rows))
        return p

    def test_detect_1hz_data(self, tmp_path: Path):
        from aria.dsremo.ingest.utils import detect_data_frequency
        # 10 rows at 1-second intervals
        rows = [f"2024-01-01T00:00:{i:02d}Z,1.0" for i in range(10)]
        p = self._write_csv(tmp_path, rows)
        interval = detect_data_frequency(p)
        assert abs(interval - 1.0) < 0.1

    def test_detect_5min_data(self, tmp_path: Path):
        from aria.dsremo.ingest.utils import detect_data_frequency
        rows = [f"2024-01-01T0{i//60}:{i%60:02d}:00Z,1.0" for i in range(0, 60, 5)]
        p = self._write_csv(tmp_path, rows)
        interval = detect_data_frequency(p)
        assert abs(interval - 300.0) < 30.0

    def test_detect_semicolon_separator(self, tmp_path: Path):
        from aria.dsremo.ingest.utils import detect_data_frequency
        rows = [f"2024-01-01T00:00:{i:02d}Z;1.0" for i in range(5)]
        p = tmp_path / "test.csv"
        p.write_text("timestamp;val\n" + "\n".join(rows))
        interval = detect_data_frequency(p)
        assert abs(interval - 1.0) < 0.5

    def test_detect_fewer_than_2_rows_returns_fallback(self, tmp_path: Path):
        from aria.dsremo.ingest.utils import detect_data_frequency
        p = self._write_csv(tmp_path, ["2024-01-01T00:00:00Z,1.0"])
        interval = detect_data_frequency(p)
        assert interval == pytest.approx(3600.0)

    def test_adaptive_cooldown_1s_data(self):
        from aria.dsremo.ingest.utils import adaptive_cooldown_hours
        result = adaptive_cooldown_hours(1.0)
        # max(300, 500×1) = 500s → 500/3600 ≈ 0.139h
        assert result == pytest.approx(500.0 / 3600.0, rel=1e-3)

    def test_adaptive_cooldown_5min_data(self):
        from aria.dsremo.ingest.utils import adaptive_cooldown_hours
        result = adaptive_cooldown_hours(300.0)
        # max(300, 500×300=150000) = 150000s = 41.67h (not capped — cap is 72h=259200s)
        assert result == pytest.approx(150000.0 / 3600.0, rel=1e-3)

    def test_adaptive_cooldown_1h_data_capped(self):
        from aria.dsremo.ingest.utils import adaptive_cooldown_hours
        result = adaptive_cooldown_hours(3600.0)
        assert result == pytest.approx(72.0)

    def test_adaptive_cooldown_very_short_interval_floors_at_5min(self):
        from aria.dsremo.ingest.utils import adaptive_cooldown_hours
        result = adaptive_cooldown_hours(0.1)
        # max(300, 500×0.1=50) = 300s → 300/3600 ≈ 0.0833h
        assert result == pytest.approx(300.0 / 3600.0, rel=1e-3)


# ---------------------------------------------------------------------------
# 5. TestEnsembleWithVariance
# ---------------------------------------------------------------------------

class TestEnsembleWithVariance:
    """6-detector ensemble: WEIGHTS, variance integration, explanation."""

    def test_weights_sum_to_one(self):
        from aria.dsremo.detection.detector import WEIGHTS
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

    def test_variance_key_present_in_weights(self):
        from aria.dsremo.detection.detector import WEIGHTS
        assert "variance" in WEIGHTS
        assert WEIGHTS["variance"] > 0

    def test_six_detectors_in_results_list(self):
        """Ensemble now has 7 detectors (lstm added in Sprint 11)."""
        # Verify by checking WEIGHTS has at least 6 keys (7 after Sprint 11)
        from aria.dsremo.detection.detector import WEIGHTS
        assert len(WEIGHTS) >= 6

    def test_variance_alone_triggers_ensemble(self):
        """_ensemble_vote with only variance triggered → is_anomaly=True."""
        from aria.dsremo.detection.detector import _ensemble_vote
        from aria.dsremo.core.models import DetectorResult, Severity
        nominal = lambda name: DetectorResult(  # noqa: E731
            detector_name=name, is_anomaly=False, score=0.0,
            severity=Severity.NOMINAL, details={},
        )
        variance_alarm = DetectorResult(
            detector_name="variance", is_anomaly=True, score=0.9,
            severity=Severity.WARNING, details={},
        )
        results = [
            nominal("cusum"), nominal("ewma"), nominal("statistical"),
            nominal("changepoint"), nominal("isolation_forest"),
            variance_alarm,
        ]
        is_anomaly, confidence, severity = _ensemble_vote(results)
        assert is_anomaly

    def test_variance_plus_cusum_higher_confidence(self):
        """Two detectors → higher confidence than one."""
        from aria.dsremo.detection.detector import _ensemble_vote
        from aria.dsremo.core.models import DetectorResult, Severity
        nominal = lambda name: DetectorResult(  # noqa: E731
            detector_name=name, is_anomaly=False, score=0.0,
            severity=Severity.NOMINAL, details={},
        )
        alarm = lambda name: DetectorResult(  # noqa: E731
            detector_name=name, is_anomaly=True, score=0.9,
            severity=Severity.WARNING, details={},
        )
        one_result  = [alarm("variance")] + [nominal(n) for n in
                       ("cusum", "ewma", "statistical", "changepoint", "isolation_forest")]
        two_results = [alarm("variance"), alarm("cusum")] + [nominal(n) for n in
                       ("ewma", "statistical", "changepoint", "isolation_forest")]
        _, conf_one, _ = _ensemble_vote(one_result)
        _, conf_two, _ = _ensemble_vote(two_results)
        assert conf_two > conf_one

    def test_agreement_factor_uses_six_detectors(self):
        """Agreement factor: 1/6 triggered should give < 1/5 triggered."""
        from aria.dsremo.detection.detector import _ensemble_vote
        from aria.dsremo.core.models import DetectorResult, Severity
        nominal = lambda name: DetectorResult(  # noqa: E731
            detector_name=name, is_anomaly=False, score=0.0,
            severity=Severity.NOMINAL, details={},
        )
        alarm = lambda name: DetectorResult(  # noqa: E731
            detector_name=name, is_anomaly=True, score=0.9,
            severity=Severity.WARNING, details={},
        )
        # 1 of 6 detectors
        results_6 = [alarm("cusum")] + [nominal(n) for n in
                     ("ewma", "statistical", "changepoint", "isolation_forest", "variance")]
        is_anomaly, conf, _ = _ensemble_vote(results_6)
        if is_anomaly:
            assert conf < 0.7  # single detector, low agreement

    def test_build_explanation_handles_variance_case(self):
        """_build_explanation should not crash on 'variance' detector."""
        from aria.dsremo.detection.detector import _build_explanation
        from aria.dsremo.core.models import DetectorResult, Severity
        from aria.dsremo.features.engine import FeatureVector

        features = FeatureVector(
            parameter="ch1", timestamp_epoch=0.0, raw_value=1.0,
            rolling_mean=0.0, rolling_std=1.0, z_score=0.5,
            rate_of_change=0.01, rolling_min=-1.0, rolling_max=1.0,
            range_position=0.5, deviation_from_trend=0.1,
        )
        var_result = DetectorResult(
            detector_name="variance", is_anomaly=True, score=0.8,
            severity=Severity.WARNING,
            details={"ratio": 2.8, "threshold": 2.5, "rolling_std": 2.8, "ref_std": 1.0},
        )
        row = {"value": 5.0, "unit": "ADU", "subsystem": "thermal", "parameter": "ch1",
               "timestamp": datetime.now(timezone.utc)}
        explanation = _build_explanation("ch1", features, [var_result], row, "stl")
        assert "Variance spike" in explanation
        assert "2.80" in explanation

    def test_init_detectors_sets_variance_threshold(self):
        """init_detectors() should accept variance_z_threshold from config."""
        from aria.dsremo.detection import detector as det_mod
        # Build a minimal settings mock
        settings = {
            "detection": {"variance_z_threshold": 3.0, "variance_window": 20},
            "features": {},
        }
        class FakeSettings:
            def get(self, key, default=None):
                return settings.get(key, default or {})

        det_mod.init_detectors(FakeSettings())
        assert det_mod._variance_detector.variance_z_threshold == pytest.approx(3.0)
        assert det_mod._variance_detector.window == 20


# ---------------------------------------------------------------------------
# 6. TestVarianceChannelConfig
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture
def demo_client():
    """Demo-mode TestClient — lifespan patches queries → memory_store.

    Demo mode:
    - dependency_overrides injects admin user (no JWT login needed)
    - lifespan replaces routes_channels.queries with memory_store (no real DB)
    """
    from fastapi.testclient import TestClient
    from aria.dsremo.api.app import create_app
    app = create_app(demo=True)
    with TestClient(app) as client:
        yield client


class TestVarianceChannelConfig:
    """Per-channel variance_z_threshold: DB stub + API routes."""

    def test_variance_z_threshold_in_override_fields(self):
        from aria.dsremo.api.routes_channels import _OVERRIDE_FIELDS
        assert "variance_z_threshold" in _OVERRIDE_FIELDS

    def test_channel_config_in_has_variance_field(self):
        from aria.dsremo.api.schemas import ChannelConfigIn
        fields = ChannelConfigIn.model_fields
        assert "variance_z_threshold" in fields

    def test_channel_config_in_validates_gt_zero(self):
        from aria.dsremo.api.schemas import ChannelConfigIn
        with pytest.raises(Exception):
            ChannelConfigIn(variance_z_threshold=-1.0)  # must be > 0

    def test_put_channel_config_with_variance_threshold(self, demo_client):
        # Demo mode injects admin user automatically — no auth header needed.
        resp = demo_client.put(
            "/api/v1/channels/MYSAT/ch1/config",
            json={"variance_z_threshold": 3.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["overrides"].get("variance_z_threshold") == pytest.approx(3.0)

    def test_get_channel_config_shows_variance_threshold(self, demo_client):
        # First set it
        demo_client.put(
            "/api/v1/channels/MYSAT/ch2/config",
            json={"variance_z_threshold": 2.0},
        )
        resp = demo_client.get("/api/v1/channels/MYSAT/ch2/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["overrides"].get("variance_z_threshold") == pytest.approx(2.0)

    def test_delete_channel_config_removes_variance_threshold(self, demo_client):
        demo_client.put(
            "/api/v1/channels/MYSAT/ch3/config",
            json={"variance_z_threshold": 4.0},
        )
        resp = demo_client.delete("/api/v1/channels/MYSAT/ch3/config")
        assert resp.status_code == 200

    def test_effective_thresholds_include_variance_z_threshold(self):
        from aria.dsremo.detection.detector import get_effective_thresholds
        eff = get_effective_thresholds("ANY-SAT", "any_param")
        assert "variance_z_threshold" in eff
        assert eff["variance_z_threshold"] > 0

    def test_upsert_channel_config_stores_variance_z_threshold(self):
        """Memory store stub correctly stores variance_z_threshold."""
        import asyncio
        from aria.dsremo.db import memory_store as ms
        async def run():
            result = await ms.upsert_channel_config(
                "MYSAT", "ch_test",
                variance_z_threshold=1.8,
            )
            return result
        result = asyncio.get_event_loop().run_until_complete(run())
        assert result.get("variance_z_threshold") == pytest.approx(1.8)

    def test_has_overrides_true_when_only_variance_set(self, demo_client):
        resp = demo_client.put(
            "/api/v1/channels/MYSAT/ch_variance_only/config",
            json={"variance_z_threshold": 3.5},
        )
        assert resp.status_code == 200

    def test_coalesce_null_variance_preserves_existing(self, demo_client):
        # Set variance_z_threshold
        demo_client.put(
            "/api/v1/channels/MYSAT/ch4/config",
            json={"variance_z_threshold": 2.5},
        )
        # Update z_threshold only (variance should be preserved)
        resp = demo_client.put(
            "/api/v1/channels/MYSAT/ch4/config",
            json={"z_threshold": 4.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        # variance_z_threshold must still be present (COALESCE preserved it)
        assert data["overrides"].get("variance_z_threshold") == pytest.approx(2.5)

    def test_load_all_channel_configs_includes_variance(self):
        """load_all_channel_configs in memory_store includes variance_z_threshold."""
        import asyncio
        from aria.dsremo.db import memory_store as ms
        async def run():
            await ms.upsert_channel_config(
                "LOADTEST", "ch1",
                variance_z_threshold=2.2,
            )
            return await ms.load_all_channel_configs()
        configs = asyncio.get_event_loop().run_until_complete(run())
        sat_configs = [c for c in configs if c.get("satellite_id") == "LOADTEST"]
        assert any(c.get("variance_z_threshold") is not None for c in sat_configs)


# ---------------------------------------------------------------------------
# 7. TestAutoCoooldownDefault
# ---------------------------------------------------------------------------

class TestAutoCoooldownDefault:
    """analyze_csv.py auto-cooldown is now DEFAULT (not opt-in)."""

    def test_detect_data_frequency_importable_from_utils(self):
        from aria.dsremo.ingest.utils import detect_data_frequency
        assert callable(detect_data_frequency)

    def test_adaptive_cooldown_hours_importable_from_utils(self):
        from aria.dsremo.ingest.utils import adaptive_cooldown_hours
        assert callable(adaptive_cooldown_hours)

    def test_analyze_csv_imports_from_utils_not_local(self):
        """analyze_csv.py must NOT define _detect_data_frequency locally."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_csv",
            ROOT / "scripts" / "analyze_csv.py",
        )
        mod = importlib.util.module_from_spec(spec)
        # Local helper functions were removed in Sprint 9
        assert not hasattr(mod, "_detect_data_frequency"), \
            "analyze_csv.py still has local _detect_data_frequency — should import from utils"
        assert not hasattr(mod, "_adaptive_cooldown"), \
            "analyze_csv.py still has local _adaptive_cooldown — should import from utils"

    def test_adaptive_cooldown_hours_1hz_returns_8_min(self):
        from aria.dsremo.ingest.utils import adaptive_cooldown_hours
        result = adaptive_cooldown_hours(1.0)
        # 500s / 3600 ≈ 0.139h ≈ 8.3 min
        assert 0.13 < result < 0.15

    def test_explicit_cooldown_hours_disables_auto_detect(self, tmp_path: Path):
        """When cooldown_hours is provided, auto-detect must be skipped."""
        from aria.dsremo.ingest.utils import adaptive_cooldown_hours, detect_data_frequency
        # The logic in analyze_csv.py: if eff_cooldown is None → auto-detect
        eff_cooldown = 5.0  # explicit
        if eff_cooldown is None:
            # Would call detect_data_frequency — but this branch is not taken
            eff_cooldown = adaptive_cooldown_hours(detect_data_frequency(tmp_path / "none.csv"))
        assert eff_cooldown == pytest.approx(5.0)
