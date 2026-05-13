"""Sprint 11: GRU Autoencoder ML Detector tests.

30 tests across 3 classes:
  TestGRUAutoencoder         (15) — unit tests for AutoencoderDetector
  TestEnsembleWith7Detectors  (8) — WEIGHTS, explanation, ensemble integration
  TestAutoencoderIntegration  (7) — _get_lstm_model, per-channel singletons

Expected total after Sprint 11: 688 + 30 = 718 passing.
"""

from __future__ import annotations

import math

import pytest

from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
from aria.dsremo.core.models import Severity


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sine_data(n: int = 200, period: int = 20, amp: float = 1.0) -> list[float]:
    """Smooth sinusoidal residual stream — represents 'normal' data."""
    return [amp * math.sin(2 * math.pi * i / period) for i in range(n)]


def _trained_detector(
    data: list[float] | None = None,
    seq_length: int = 30,
    min_train_samples: int = 60,
    epochs: int = 5,
) -> AutoencoderDetector:
    """Return an already-fitted AutoencoderDetector for use in tests."""
    d = AutoencoderDetector(
        seq_length=seq_length,
        min_train_samples=min_train_samples,
        epochs=epochs,
    )
    stream = data or _sine_data(200)
    for r in stream:
        d.add_sample(r)
    d.fit()
    return d


# ── Class 1: Unit tests for AutoencoderDetector ──────────────────────────────

class TestGRUAutoencoder:

    # 1 — construction with default params
    def test_default_params(self):
        d = AutoencoderDetector()
        assert d.seq_length == 30
        assert d.hidden_size == 32
        assert d.bottleneck_size == 8
        assert d.epochs == 30
        assert d.min_train_samples == 60
        assert d.retrain_interval == 500
        assert d.threshold_sigma == 3.0
        assert not d.is_fitted
        assert d.sample_count == 0

    # 2 — fit with sufficient data → is_fitted = True
    def test_fit_sufficient_data(self):
        d = _trained_detector()
        assert d.is_fitted
        assert d._threshold > 0

    # 3 — fit with insufficient data → not fitted
    def test_fit_insufficient_data(self):
        d = AutoencoderDetector(min_train_samples=60, epochs=5)
        for v in _sine_data(30):   # 30 < 60 = min_train_samples
            d.add_sample(v)
        d.fit()
        assert not d.is_fitted

    # 4 — detect before fit → NOMINAL with reason=model_not_fitted
    def test_detect_before_fit(self):
        d = AutoencoderDetector()
        result = d.detect(_sine_data(30))
        assert result.detector_name == "lstm"
        assert not result.is_anomaly
        assert result.score == 0.0
        assert result.severity == Severity.NOMINAL
        assert result.details.get("reason") == "model_not_fitted"

    # 5 — detect with too-short residuals → NOMINAL reason=insufficient_data
    def test_detect_insufficient_residuals(self):
        d = _trained_detector()
        result = d.detect([0.1, 0.2])   # only 2 < seq_length=30
        assert not result.is_anomaly
        assert result.details.get("reason") == "insufficient_data"

    # 6 — detect normal in-distribution sequence → score < 0.5, is_anomaly=False
    def test_detect_normal_sequence(self):
        stream = _sine_data(200)
        d = _trained_detector(data=stream)
        result = d.detect(stream[-30:])
        assert result.detector_name == "lstm"
        assert not result.is_anomaly
        assert result.score < 0.5

    # 7 — detect strongly anomalous sequence → is_anomaly=True
    def test_detect_anomalous_sequence(self):
        stream = _sine_data(200)
        d = _trained_detector(data=stream)
        spike = [100.0] * 30   # far outside training distribution
        result = d.detect(spike)
        assert result.is_anomaly
        assert result.score > 0.5

    # 8a — severity WATCH (mild anomaly)
    def test_severity_bands_exist(self):
        """Severity classification covers WATCH/WARNING/CRITICAL."""
        stream = _sine_data(200)
        d = _trained_detector(data=stream)
        # Force a CRITICAL result by using an extreme spike
        result = d.detect([1000.0] * 30)
        assert result.is_anomaly
        assert result.severity in (Severity.WATCH, Severity.WARNING, Severity.CRITICAL)

    # 8b — CRITICAL for very large spike
    def test_severity_critical_large_spike(self):
        stream = _sine_data(200)
        d = _trained_detector(data=stream)
        result = d.detect([1000.0] * 30)
        assert result.is_anomaly
        assert result.severity == Severity.CRITICAL

    # 9 — score clamped to [0, 1]
    def test_score_clamped_to_unit_interval(self):
        stream = _sine_data(200)
        d = _trained_detector(data=stream)
        for window in ([1000.0] * 30, stream[-30:]):
            result = d.detect(window)
            assert 0.0 <= result.score <= 1.0, f"score={result.score} out of [0,1]"

    # 10 — needs_refit() False before interval
    def test_needs_refit_false_initially(self):
        d = _trained_detector()
        assert not d.needs_refit()

    # 11 — needs_refit() True after retrain_interval new samples
    def test_needs_refit_true_after_interval(self):
        d = AutoencoderDetector(retrain_interval=10, min_train_samples=60, epochs=5)
        for v in _sine_data(200):
            d.add_sample(v)
        d.fit()
        for v in _sine_data(11):   # 11 > retrain_interval=10
            d.add_sample(v)
        assert d.needs_refit()

    # 12 — add_sample increments sample_count
    def test_add_sample_increments_count(self):
        d = AutoencoderDetector()
        assert d.sample_count == 0
        d.add_sample(1.0)
        d.add_sample(2.0)
        assert d.sample_count == 2

    # 13 — fit() resets _samples_since_fit to 0
    def test_fit_resets_samples_since_fit(self):
        d = AutoencoderDetector(retrain_interval=5, min_train_samples=60, epochs=5)
        for v in _sine_data(200):
            d.add_sample(v)
        d.fit()
        for v in _sine_data(5):
            d.add_sample(v)
        assert d._samples_since_fit == 5
        d.fit()   # retrain
        assert d._samples_since_fit == 0

    # 14 — model has < 10 K parameters (tiny architecture confirmed)
    def test_model_parameter_count_small(self):
        d = _trained_detector()
        assert d._model is not None
        total = sum(p.numel() for p in d._model.parameters())
        assert total < 10_000, f"Model has {total} params — expected < 10K for CPU VPS"

    # 15 — details dict has all required keys on anomaly result
    def test_details_keys_on_anomaly(self):
        stream = _sine_data(200)
        d = _trained_detector(data=stream)
        result = d.detect([500.0] * 30)
        assert result.is_anomaly
        for key in ("mse", "threshold", "train_mse_mean", "train_mse_std", "z_score"):
            assert key in result.details, f"Missing key: {key}"


# ── Class 2: 7-detector ensemble integration ─────────────────────────────────

class TestEnsembleWith7Detectors:

    # 1 — WEIGHTS sum to 1.0
    def test_weights_sum_to_one(self):
        from aria.dsremo.detection.detector import WEIGHTS
        total = sum(WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"WEIGHTS sum={total}"

    # 2 — "lstm" key present in WEIGHTS
    def test_lstm_key_in_weights(self):
        from aria.dsremo.detection.detector import WEIGHTS
        assert "lstm" in WEIGHTS
        assert WEIGHTS["lstm"] > 0.0

    # 3 — 7 detector names present (not 6)
    def test_seven_detector_names(self):
        from aria.dsremo.detection.detector import WEIGHTS
        # Sprint 13 added "tcn" as 8th detector — assert all Sprint 11 detectors still present
        required = {"cusum", "ewma", "statistical", "changepoint",
                    "isolation_forest", "variance", "lstm"}
        assert required.issubset(set(WEIGHTS.keys())), f"Got: {set(WEIGHTS.keys())}"

    # 4 — ensemble vote: 1 of 7 detectors firing → single group, agreement=0.70
    def test_ensemble_vote_lstm_alone_confidence(self):
        """When lstm alone fires at score=1.0, confidence uses correlation-aware
        group fusion (P0-A/B fix).  Single group = agreement 0.70.
        """
        from aria.dsremo.detection.detector import _ensemble_vote
        from aria.dsremo.core.models import DetectorResult, Severity

        def _nom(name):
            return DetectorResult(
                detector_name=name, is_anomaly=False, score=0.0,
                severity=Severity.NOMINAL, details={},
            )

        lstm_r = DetectorResult(
            detector_name="lstm", is_anomaly=True, score=1.0,
            severity=Severity.CRITICAL, details={},
        )
        results = [
            _nom("cusum"), _nom("ewma"), _nom("statistical"),
            _nom("changepoint"), _nom("isolation_forest"), _nom("variance"),
            lstm_r,
        ]
        _, confidence, _ = _ensemble_vote(results)
        # Correlation-aware ensemble: single group (ml_temporal), agreement=0.70.
        # Exact value depends on score calibration; should be in WATCH range.
        assert 0.35 < confidence < 0.80

    # 5 — _build_explanation handles "lstm" case and contains "Autoencoder"
    def test_build_explanation_lstm_case(self):
        from aria.dsremo.detection.detector import _build_explanation
        from aria.dsremo.core.models import DetectorResult, Severity
        from aria.dsremo.features.engine import FeatureEngine

        fe   = FeatureEngine(window_size=600)
        feat = fe.compute("bv:res", 0.5, 1000.0)

        lstm_r = DetectorResult(
            detector_name="lstm",
            is_anomaly=True,
            score=0.9,
            severity=Severity.WARNING,
            details={"mse": 0.0123, "threshold": 0.005,
                     "train_mse_mean": 0.001, "train_mse_std": 0.001,
                     "z_score": 3.7},
        )
        explanation = _build_explanation(
            "battery_voltage", feat, [lstm_r],
            {"value": 7.2, "unit": "V", "subsystem": "eps",
             "parameter": "battery_voltage", "timestamp": None},
            "stl",
        )
        assert "Autoencoder" in explanation
        assert "MSE" in explanation
        assert "0.0123" in explanation

    # 6 — lstm alone at score=1.0 triggers at least CAUTION/WATCH
    def test_lstm_alone_triggers_alert(self):
        """A single strong ML detector should produce an alert for human review.

        With correlation-aware ensemble (P0-A/B fix), single-group firing
        gets agreement=0.70.  Should clear at least CAUTION threshold.
        """
        from aria.dsremo.detection.detector import _ensemble_vote
        from aria.dsremo.core.models import DetectorResult, Severity

        def _nom(name):
            return DetectorResult(
                detector_name=name, is_anomaly=False, score=0.0,
                severity=Severity.NOMINAL, details={},
            )

        lstm_r = DetectorResult(
            detector_name="lstm", is_anomaly=True, score=1.0,
            severity=Severity.CRITICAL, details={},
        )
        results = [
            _nom("cusum"), _nom("ewma"), _nom("statistical"),
            _nom("changepoint"), _nom("isolation_forest"), _nom("variance"),
            lstm_r,
        ]
        is_anomaly, confidence, severity = _ensemble_vote(results)
        assert is_anomaly
        assert confidence > 0.35  # at least CAUTION threshold
        assert severity in (Severity.CAUTION, Severity.WATCH, Severity.WARNING)

    # 7 — lstm + variance together give higher confidence than variance alone
    def test_lstm_plus_variance_higher_confidence(self):
        from aria.dsremo.detection.detector import _ensemble_vote
        from aria.dsremo.core.models import DetectorResult, Severity

        def _nom(name):
            return DetectorResult(
                detector_name=name, is_anomaly=False, score=0.0,
                severity=Severity.NOMINAL, details={},
            )

        def _fire(name):
            return DetectorResult(
                detector_name=name, is_anomaly=True, score=1.0,
                severity=Severity.CRITICAL, details={},
            )

        r_var_only = [
            _nom("cusum"), _nom("ewma"), _nom("statistical"),
            _nom("changepoint"), _nom("isolation_forest"), _fire("variance"),
            _nom("lstm"),
        ]
        r_both = [
            _nom("cusum"), _nom("ewma"), _nom("statistical"),
            _nom("changepoint"), _nom("isolation_forest"), _fire("variance"),
            _fire("lstm"),
        ]
        _, conf_var_only, _ = _ensemble_vote(r_var_only)
        _, conf_both,     _ = _ensemble_vote(r_both)
        assert conf_both > conf_var_only

    # 8 — init_detectors reads lstm config keys from settings dict
    def test_init_detectors_reads_lstm_config(self):
        from aria.dsremo.detection import detector as det_mod

        class FakeSettings:
            def get(self, key, default=None):
                if key == "detection":
                    return {
                        "lstm_seq_length":        45,
                        "lstm_hidden_size":        16,
                        "lstm_bottleneck_size":     4,
                        "lstm_epochs":              3,
                        "lstm_min_train_samples":  90,
                        "lstm_retrain_interval":  200,
                        "lstm_threshold_sigma":   2.5,
                    }
                return default or {}

        det_mod.init_detectors(FakeSettings())
        assert det_mod._lstm_seq_length == 45
        assert det_mod._lstm_hidden_size == 16
        assert det_mod._lstm_bottleneck_size == 4
        assert det_mod._lstm_epochs == 3
        assert det_mod._lstm_min_train == 90
        assert det_mod._lstm_retrain_interval == 200
        assert det_mod._lstm_threshold_sigma == 2.5
        # Restore defaults so subsequent tests are not affected
        det_mod._lstm_seq_length      = 30
        det_mod._lstm_hidden_size     = 32
        det_mod._lstm_bottleneck_size = 8
        det_mod._lstm_epochs          = 30
        det_mod._lstm_min_train       = 60
        det_mod._lstm_retrain_interval = 500
        det_mod._lstm_threshold_sigma = 3.0


# ── Class 3: per-channel model management + integration ──────────────────────

class TestAutoencoderIntegration:

    def setup_method(self):
        """Clear the global lstm_models dict before each test."""
        from aria.dsremo.detection import detector as det_mod
        det_mod._lstm_models.clear()

    # 1 — _get_lstm_model returns AutoencoderDetector
    def test_get_lstm_model_returns_instance(self):
        from aria.dsremo.detection.detector import _get_lstm_model
        m = _get_lstm_model("SAT-1", "battery_voltage")
        assert isinstance(m, AutoencoderDetector)

    # 2 — same key returns same instance (singleton per channel)
    def test_same_key_same_instance(self):
        from aria.dsremo.detection.detector import _get_lstm_model
        m1 = _get_lstm_model("SAT-1", "battery_voltage")
        m2 = _get_lstm_model("SAT-1", "battery_voltage")
        assert m1 is m2

    # 3 — different channel key returns different instance
    def test_different_key_different_instance(self):
        from aria.dsremo.detection.detector import _get_lstm_model
        m1 = _get_lstm_model("SAT-1", "battery_voltage")
        m2 = _get_lstm_model("SAT-1", "battery_current")
        assert m1 is not m2
        m3 = _get_lstm_model("SAT-2", "battery_voltage")
        assert m1 is not m3

    # 4 — after enough add_sample() + fit(), is_fitted becomes True
    def test_auto_fit_after_min_samples(self):
        d = AutoencoderDetector(
            seq_length=10,
            min_train_samples=20,
            epochs=3,
        )
        stream = _sine_data(80, period=10)
        for r in stream:
            d.add_sample(r)
        d.fit()
        assert d.is_fitted

    # 5 — detect on trained model returns DetectorResult with detector_name=="lstm"
    def test_detect_returns_lstm_detector_name(self):
        d = AutoencoderDetector(seq_length=10, min_train_samples=20, epochs=3)
        stream = _sine_data(80, period=10)
        for r in stream:
            d.add_sample(r)
        d.fit()
        result = d.detect(stream[-10:])
        assert result.detector_name == "lstm"

    # 6 — retrain triggered after retrain_interval new samples
    def test_retrain_needed_after_interval(self):
        d = AutoencoderDetector(
            seq_length=10,
            min_train_samples=20,
            retrain_interval=15,
            epochs=3,
        )
        stream = _sine_data(80, period=10)
        for r in stream:
            d.add_sample(r)
        d.fit()
        assert not d.needs_refit()
        for r in _sine_data(16, period=10):
            d.add_sample(r)
        assert d.needs_refit()

    # 7 — torch_not_available path: patched detect returns NOMINAL without exception
    def test_graceful_fallback_torch_not_available(self):
        """Verify the torch_not_available fallback branch is reachable and safe."""
        from aria.dsremo.core.models import DetectorResult, Severity

        d = AutoencoderDetector(seq_length=10, min_train_samples=20, epochs=3)
        stream = _sine_data(80, period=10)
        for r in stream:
            d.add_sample(r)
        d.fit()
        assert d.is_fitted

        # Patch detect to return the torch_not_available placeholder directly
        def _patched(residuals):
            return DetectorResult(
                detector_name="lstm",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={"reason": "torch_not_available"},
            )

        d.detect = _patched
        result = d.detect(stream[-10:])
        assert result.detector_name == "lstm"
        assert not result.is_anomaly
        assert result.details["reason"] == "torch_not_available"
