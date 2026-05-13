"""Tests for the Isolation Forest multivariate detector."""

import numpy as np
import pytest

from aria.dsremo.core.models import Severity
from aria.dsremo.detection.isolation import IsolationForestDetector


class TestIsolationForestDetector:
    @pytest.fixture
    def detector(self):
        return IsolationForestDetector(contamination=0.05, min_training_samples=50)

    @pytest.fixture
    def trained_detector(self, detector):
        """Detector fitted on normal multivariate data."""
        rng = np.random.default_rng(42)
        # 3 correlated features: voltage, current, temperature
        n = 200
        voltage = 7.4 + rng.normal(0, 0.1, n)
        current = 1.2 + 0.3 * (voltage - 7.4) + rng.normal(0, 0.05, n)
        temp = 22.0 + 2.0 * (voltage - 7.4) + rng.normal(0, 0.5, n)
        data = np.column_stack([voltage, current, temp])
        detector.fit(data, ["voltage", "current", "temp"])
        return detector

    def test_not_ready_before_fit(self, detector):
        assert not detector.is_ready
        result = detector.detect(np.array([7.4, 1.2, 22.0]))
        assert not result.is_anomaly
        assert result.details.get("reason") == "model_not_fitted"

    def test_ready_after_fit(self, trained_detector):
        assert trained_detector.is_ready

    def test_normal_point_not_anomalous(self, trained_detector):
        result = trained_detector.detect(np.array([7.4, 1.2, 22.0]))
        assert not result.is_anomaly
        assert result.score < 0.5

    def test_extreme_point_is_anomalous(self, trained_detector):
        # Completely out of distribution
        result = trained_detector.detect(np.array([20.0, 10.0, 80.0]))
        assert result.is_anomaly
        assert result.score > 0.5

    def test_subtle_correlation_break(self, trained_detector):
        # Voltage normal, but current inconsistent (correlation broken)
        result = trained_detector.detect(np.array([7.4, 5.0, 22.0]))
        # This may or may not trigger — depends on contamination threshold
        # But score should be elevated
        assert result.score > 0.2

    def test_feature_contributions(self, trained_detector):
        result = trained_detector.detect(np.array([20.0, 10.0, 80.0]))
        contribs = result.details.get("feature_contributions", {})
        assert len(contribs) == 3
        assert "voltage" in contribs

    def test_skip_fit_insufficient_data(self, detector):
        small_data = np.random.default_rng(42).normal(0, 1, (10, 3))
        detector.fit(small_data, ["a", "b", "c"])
        assert not detector.is_ready  # too few samples

    def test_needs_refit(self, trained_detector):
        assert not trained_detector.needs_refit(500)
        assert trained_detector.needs_refit(1001)
