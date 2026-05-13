"""Sprint 13: TCN Detector + 8-Detector Ensemble Tests.

Target: 755 existing + 30 new = 785 passing tests.

Classes
-------
TestTCNDetector              (15 tests) — TCNDetector unit tests
TestEnsembleWith8Detectors   ( 8 tests) — ensemble weight/integration
TestTCNIntegration           ( 7 tests) — detector.py plumbing
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sine_wave(n: int = 200, period: float = 20.0, noise: float = 0.05) -> list[float]:
    """Return n samples of a sine wave with optional small Gaussian noise."""
    rng = __import__("random")
    rng.seed(42)
    return [math.sin(2 * math.pi * i / period) + rng.gauss(0, noise) for i in range(n)]


def _constant_spike(n: int = 32, level: float = 100.0) -> list[float]:
    """Return n constant-value residuals far from training distribution."""
    return [level] * n


# ═══════════════════════════════════════════════════════════════════════════════
# Class 1: TCNDetector unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestTCNDetector:
    """Unit tests for TCNDetector (Sprint 13)."""

    # ── Construction ─────────────────────────────────────────────────────────

    def test_construction_defaults(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector()
        assert det.seq_length == 32
        assert det.n_channels == 16
        assert det.n_blocks == 4
        assert det.kernel_size == 3
        assert det.epochs == 40
        assert det.min_train_samples == 64
        assert det.retrain_interval == 500
        assert det.threshold_sigma == 3.0

    def test_construction_custom_params(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=16, n_channels=8, n_blocks=2, epochs=10, min_train_samples=32)
        assert det.seq_length == 16
        assert det.n_channels == 8
        assert det.n_blocks == 2
        assert det.epochs == 10
        assert det.min_train_samples == 32

    # ── add_sample / sample_count ─────────────────────────────────────────────

    def test_add_sample_increments_count(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=8, min_train_samples=16)
        assert det.sample_count == 0
        det.add_sample(1.0)
        det.add_sample(2.0)
        assert det.sample_count == 2

    # ── Fit behaviour ─────────────────────────────────────────────────────────

    def test_fit_with_sufficient_data_sets_is_fitted(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=8, min_train_samples=16, epochs=3)
        normal = _sine_wave(100, period=8, noise=0.02)
        for v in normal:
            det.add_sample(v)
        det.fit()
        assert det.is_fitted is True

    def test_fit_with_insufficient_data_stays_unfitted(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=8, min_train_samples=64, epochs=3)
        for v in _sine_wave(30, period=8, noise=0.02):
            det.add_sample(v)
        det.fit()
        assert det.is_fitted is False

    def test_fit_sets_threshold_positive(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=8, min_train_samples=16, epochs=5)
        for v in _sine_wave(80, period=8, noise=0.02):
            det.add_sample(v)
        det.fit()
        assert det._threshold > 0.0

    def test_fit_resets_samples_since_fit(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=8, min_train_samples=16, epochs=3)
        for v in _sine_wave(80, period=8, noise=0.02):
            det.add_sample(v)
        det.fit()
        assert det._samples_since_fit == 0

    # ── needs_refit ──────────────────────────────────────────────────────────

    def test_needs_refit_false_before_interval(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=8, min_train_samples=16, retrain_interval=50, epochs=3)
        for v in _sine_wave(80, period=8, noise=0.02):
            det.add_sample(v)
        det.fit()
        for _ in range(49):
            det.add_sample(0.1)
        assert det.needs_refit() is False

    def test_needs_refit_true_after_interval(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=8, min_train_samples=16, retrain_interval=10, epochs=3)
        for v in _sine_wave(80, period=8, noise=0.02):
            det.add_sample(v)
        det.fit()
        for _ in range(10):
            det.add_sample(0.1)
        assert det.needs_refit() is True

    # ── detect: no-fit / insufficient data ───────────────────────────────────

    def test_detect_without_fit_returns_nominal(self) -> None:
        from aria.dsremo.core.models import Severity
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=8, min_train_samples=16)
        result = det.detect([0.1] * 20)
        assert result.is_anomaly is False
        assert result.severity == Severity.NOMINAL
        assert result.details.get("reason") == "model_not_fitted"

    def test_detect_insufficient_residuals_returns_nominal(self) -> None:
        from aria.dsremo.core.models import Severity
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=16, min_train_samples=32, epochs=3)
        for v in _sine_wave(80, period=8, noise=0.02):
            det.add_sample(v)
        det.fit()
        result = det.detect([0.1] * 5)   # fewer than seq_length=16
        assert result.is_anomaly is False
        assert result.severity == Severity.NOMINAL
        assert result.details.get("reason") == "insufficient_data"

    # ── detect: in-distribution vs anomaly ───────────────────────────────────

    def test_detect_normal_sequence_low_score(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=16, min_train_samples=32, epochs=10)
        normal = _sine_wave(200, period=16, noise=0.02)
        for v in normal:
            det.add_sample(v)
        det.fit()
        result = det.detect(normal[-32:])
        assert result.score < 0.5
        assert result.is_anomaly is False

    def test_detect_anomalous_sequence_fires(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=16, min_train_samples=32, epochs=10)
        normal = _sine_wave(200, period=16, noise=0.02)
        for v in normal:
            det.add_sample(v)
        det.fit()
        result = det.detect(_constant_spike(32, level=50.0))
        assert result.is_anomaly is True

    # ── Score clamping ────────────────────────────────────────────────────────

    def test_score_clamped_to_unit_interval(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=16, min_train_samples=32, epochs=5)
        normal = _sine_wave(200, period=16, noise=0.02)
        for v in normal:
            det.add_sample(v)
        det.fit()
        for residuals in [normal[-32:], _constant_spike(32, 1000.0)]:
            r = det.detect(residuals)
            assert 0.0 <= r.score <= 1.0

    # ── Model size ────────────────────────────────────────────────────────────

    def test_model_parameter_count_under_10k(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=16, min_train_samples=32, n_channels=16, n_blocks=4, epochs=3)
        for v in _sine_wave(80, period=8, noise=0.02):
            det.add_sample(v)
        det.fit()
        assert det._model is not None
        total = sum(p.numel() for p in det._model.parameters())
        assert total < 10_000, f"Model too large: {total} params"

    # ── details dict keys ─────────────────────────────────────────────────────

    def test_detect_anomaly_details_keys(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=16, min_train_samples=32, epochs=5)
        normal = _sine_wave(200, period=16, noise=0.02)
        for v in normal:
            det.add_sample(v)
        det.fit()
        result = det.detect(_constant_spike(32, level=50.0))
        assert "mse" in result.details
        assert "threshold" in result.details
        assert "train_mse_mean" in result.details
        assert "train_mse_std" in result.details
        assert "z_score" in result.details


# ═══════════════════════════════════════════════════════════════════════════════
# Class 2: 8-Detector Ensemble Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnsembleWith8Detectors:
    """Ensemble-level tests after adding TCN as 8th detector."""

    def test_weights_sum_to_one(self) -> None:
        from aria.dsremo.detection.detector import WEIGHTS
        total = sum(WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"WEIGHTS sum = {total}"

    def test_tcn_key_present_in_weights(self) -> None:
        from aria.dsremo.detection.detector import WEIGHTS
        assert "tcn" in WEIGHTS

    def test_lstm_key_still_present(self) -> None:
        from aria.dsremo.detection.detector import WEIGHTS
        assert "lstm" in WEIGHTS

    def test_eight_detector_names_in_weights(self) -> None:
        from aria.dsremo.detection.detector import WEIGHTS
        # Sprint 13 added tcn — subsequent sprints may add more detectors, so
        # check all Sprint-13 keys are present (subset), not exact equality.
        expected = {"cusum", "ewma", "statistical", "changepoint",
                    "isolation_forest", "variance", "lstm", "tcn"}
        assert expected.issubset(set(WEIGHTS.keys()))

    def test_build_explanation_handles_tcn(self) -> None:
        from aria.dsremo.core.models import DetectorResult, Severity
        from aria.dsremo.detection.detector import _build_explanation

        tcn_result = DetectorResult(
            detector_name="tcn",
            is_anomaly=True,
            score=0.8,
            severity=Severity.WARNING,
            details={"mse": 0.42, "threshold": 0.15, "z_score": 2.5,
                     "train_mse_mean": 0.05, "train_mse_std": 0.03},
        )
        nominal = DetectorResult(
            detector_name="cusum",
            is_anomaly=False,
            score=0.0,
            severity=Severity.NOMINAL,
            details={},
        )
        alarm_row = {"value": 12.34, "unit": "Pa", "timestamp": "2024-01-01T00:00:00Z"}
        # Minimal feature result stub with required attributes
        class _FakeFeatures:
            raw_value = 12.34
            rolling_std = 0.5
        explanation = _build_explanation("pressure", _FakeFeatures(), [nominal, tcn_result], alarm_row, "stl")
        assert "TCN" in explanation

    def test_tcn_weight_less_than_cusum(self) -> None:
        from aria.dsremo.detection.detector import WEIGHTS
        assert WEIGHTS["tcn"] < WEIGHTS["cusum"]

    def test_cusum_still_positive_weight(self) -> None:
        # Sprint 13 assumption (cusum == max) was invalidated by the LLR
        # benchmark re-weighting landed in the bocpd sprint, which pushed
        # `variance` and `trend_velocity` above `cusum`.  The load-bearing
        # invariant here is actually "cusum is a non-trivial ensemble
        # member" — assert that instead.
        from aria.dsremo.detection.detector import WEIGHTS
        assert WEIGHTS["cusum"] > 0.1

    def test_init_detectors_reads_tcn_seq_length(self) -> None:
        from aria.dsremo.detection import detector as det_mod
        fake_settings = {
            "detection": {"tcn_seq_length": 48, "tcn_epochs": 20},
            "features":  {},
        }
        det_mod.init_detectors(type("S", (), {"get": lambda self, k, d=None: fake_settings.get(k, d)})())
        assert det_mod._tcn_seq_length == 48
        assert det_mod._tcn_epochs == 20


# ═══════════════════════════════════════════════════════════════════════════════
# Class 3: TCN Integration Tests (detector.py plumbing)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTCNIntegration:
    """Test that TCN is wired correctly into the ensemble orchestrator."""

    def test_get_tcn_model_returns_tcn_detector(self) -> None:
        from aria.dsremo.detection.detector import _get_tcn_model
        from aria.dsremo.detection.tcn_detector import TCNDetector
        model = _get_tcn_model("sat-A", "pressure")
        assert isinstance(model, TCNDetector)

    def test_same_key_returns_same_instance(self) -> None:
        from aria.dsremo.detection.detector import _get_tcn_model
        m1 = _get_tcn_model("sat-B", "temperature")
        m2 = _get_tcn_model("sat-B", "temperature")
        assert m1 is m2

    def test_different_key_returns_different_instance(self) -> None:
        from aria.dsremo.detection.detector import _get_tcn_model
        m1 = _get_tcn_model("sat-C", "param1")
        m2 = _get_tcn_model("sat-C", "param2")
        assert m1 is not m2

    def test_after_enough_samples_becomes_fitted(self) -> None:
        from aria.dsremo.detection.detector import _get_tcn_model
        import random; random.seed(7)
        det = _get_tcn_model("sat-D", "voltage_test_fit")
        det.__class__.__init__(det, seq_length=8, min_train_samples=16, epochs=3)
        det._buffer.clear()
        det._is_fitted = False
        for v in _sine_wave(80, period=8, noise=0.02):
            det.add_sample(v)
        det.fit()
        assert det.is_fitted is True

    def test_detect_on_trained_model_returns_tcn_result(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=8, min_train_samples=16, epochs=3)
        normal = _sine_wave(80, period=8, noise=0.02)
        for v in normal:
            det.add_sample(v)
        det.fit()
        result = det.detect(normal[-16:])
        assert result.detector_name == "tcn"

    def test_retrain_triggered_after_interval(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=8, min_train_samples=16, retrain_interval=10, epochs=3)
        for v in _sine_wave(80, period=8, noise=0.02):
            det.add_sample(v)
        det.fit()
        for _ in range(10):
            det.add_sample(0.0)
        assert det.needs_refit() is True

    def test_torch_not_available_path_returns_nominal(self) -> None:
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=8, min_train_samples=16, epochs=3)
        # Manually mark as fitted so detect() tries to run inference
        det._is_fitted = True
        det._model = None   # simulate no model

        # Patch torch import to raise ImportError
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "torch":
                raise ImportError("torch not available")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = det.detect([0.5] * 16)

        assert result.is_anomaly is False
        assert result.details.get("reason") == "torch_not_available"
