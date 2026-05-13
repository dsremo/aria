"""Tests for the change-point detector."""

import numpy as np
import pytest

from aria.dsremo.core.models import Severity
from aria.dsremo.detection.changepoint import ChangePointDetector


class TestChangePointDetector:
    @pytest.fixture
    def detector(self):
        return ChangePointDetector(penalty=3.0, min_segment_size=20)

    def test_stable_signal_no_changepoints(self, detector):
        signal = np.ones(200) * 7.4 + np.random.default_rng(42).normal(0, 0.02, 200)
        result = detector.detect(signal, "battery_voltage")
        assert not result.is_anomaly or result.score < 0.3

    def test_detects_mean_shift(self, detector):
        rng = np.random.default_rng(42)
        signal = np.concatenate([
            7.4 + rng.normal(0, 0.05, 100),  # normal
            5.8 + rng.normal(0, 0.05, 100),  # shifted down (battery failure)
        ])
        result = detector.detect(signal, "battery_voltage")
        assert result.is_anomaly
        assert result.score > 0.3
        assert len(result.details.get("change_points", [])) > 0

    def test_detects_variance_change(self, detector):
        rng = np.random.default_rng(42)
        signal = np.concatenate([
            7.4 + rng.normal(0, 0.02, 100),  # low noise
            7.4 + rng.normal(0, 0.5, 100),   # high noise (sensor degradation)
        ])
        result = detector.detect(signal, "battery_voltage")
        # Should detect the variance change
        cps = result.details.get("change_points", [])
        assert len(cps) > 0

    def test_insufficient_data(self, detector):
        signal = np.array([7.4, 7.3, 7.5])  # too short
        result = detector.detect(signal, "v")
        assert not result.is_anomaly
        assert result.details.get("reason") == "insufficient_data"

    def test_multiple_change_points(self, detector):
        rng = np.random.default_rng(42)
        signal = np.concatenate([
            7.4 + rng.normal(0, 0.03, 80),
            6.0 + rng.normal(0, 0.03, 80),
            8.0 + rng.normal(0, 0.03, 80),
        ])
        result = detector.detect(signal, "v")
        cps = result.details.get("change_points", [])
        assert len(cps) >= 1  # at least one detected
