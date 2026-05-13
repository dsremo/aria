"""Tests for the statistical anomaly detector."""

import numpy as np
import pytest

from aria.dsremo.core.models import Severity
from aria.dsremo.detection.statistical import StatisticalDetector
from aria.dsremo.features.engine import FeatureEngine


class TestStatisticalDetector:
    @pytest.fixture
    def detector(self):
        return StatisticalDetector(z_threshold=3.0, severe_z_threshold=5.0)

    def test_nominal_value_not_anomalous(self, detector):
        engine = FeatureEngine(window_size=100)
        rng = np.random.default_rng(42)

        # Feed normal values
        for i in range(100):
            engine.compute("v", 7.4 + rng.normal(0, 0.05), float(i))

        fv = engine.compute("v", 7.42, 100.0)
        result = detector.detect(fv, np.array([7.4] * 100))
        assert not result.is_anomaly
        assert result.severity == Severity.NOMINAL

    def test_extreme_value_is_anomalous(self, detector):
        engine = FeatureEngine(window_size=100)

        for i in range(100):
            engine.compute("v", 7.4, float(i))

        fv = engine.compute("v", 12.0, 100.0)
        result = detector.detect(fv, np.array([7.4] * 100))
        assert result.is_anomaly
        assert result.severity in (Severity.WARNING, Severity.CRITICAL)
        assert result.score > 0.5

    def test_insufficient_data_returns_nominal(self, detector):
        engine = FeatureEngine(window_size=100)
        fv = engine.compute("v", 7.4, 0.0)
        result = detector.detect(fv, np.array([7.4] * 5))  # only 5 points
        assert not result.is_anomaly
        # May return "constant_residual" (constant guard) or "insufficient_data"
        # depending on which guard fires first — both correctly yield NOMINAL.
        assert result.details.get("reason") in ("insufficient_data", "constant_residual")

    def test_gradual_drift_caught(self, detector):
        engine = FeatureEngine(window_size=200)

        # Normal baseline
        for i in range(150):
            engine.compute("v", 7.4, float(i))

        # Gradual drift
        for i in range(50):
            engine.compute("v", 7.4 + i * 0.1, float(150 + i))

        fv = engine.compute("v", 12.4, 200.0)
        result = detector.detect(fv, np.array([7.4] * 200))
        assert result.is_anomaly

    def test_severity_classification(self, detector):
        engine = FeatureEngine(window_size=100)

        for i in range(100):
            engine.compute("v", 7.4, float(i))

        # Z ~ 3.5 → WATCH
        fv_watch = engine.compute("v", 7.4 + 3.5 * 0.02, 100.0)
        # For controlled test, create features manually
        from aria.dsremo.features.engine import FeatureVector
        fv = FeatureVector(
            parameter="v", timestamp_epoch=100.0, raw_value=10.0,
            rolling_mean=7.4, rolling_std=0.5, z_score=3.5,
            rate_of_change=0.0, rolling_min=7.0, rolling_max=8.0,
            range_position=0.8, deviation_from_trend=2.6,
        )
        result = detector.detect(fv, np.array([7.4] * 100))
        assert result.severity == Severity.WATCH

        # Z ~ 6 → CRITICAL
        fv_crit = FeatureVector(
            parameter="v", timestamp_epoch=100.0, raw_value=10.0,
            rolling_mean=7.4, rolling_std=0.5, z_score=6.0,
            rate_of_change=0.0, rolling_min=7.0, rolling_max=8.0,
            range_position=0.8, deviation_from_trend=2.6,
        )
        result = detector.detect(fv_crit, np.array([7.4] * 100))
        assert result.severity == Severity.CRITICAL
