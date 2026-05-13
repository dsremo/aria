"""Tests for the feature engineering engine."""

import numpy as np
import pytest

from aria.dsremo.features.engine import FeatureEngine, FeatureVector


class TestFeatureEngine:
    def test_first_value_returns_defaults(self, feature_engine):
        fv = feature_engine.compute("battery_voltage", 7.4, 1000.0)
        assert fv.parameter == "battery_voltage"
        assert fv.raw_value == 7.4
        assert fv.z_score == 0.0
        assert fv.rate_of_change == 0.0

    def test_z_score_for_normal_values(self, feature_engine):
        # Feed 100 normal values
        for i in range(100):
            fv = feature_engine.compute("v", 7.4 + np.random.normal(0, 0.05), float(i))

        # Z-score should be small for value near mean
        fv = feature_engine.compute("v", 7.4, 100.0)
        assert abs(fv.z_score) < 2.0

    def test_z_score_spikes_for_anomalous_value(self, feature_engine):
        # Feed 100 normal values
        for i in range(100):
            feature_engine.compute("v", 7.4, float(i))

        # Inject extreme value
        fv = feature_engine.compute("v", 20.0, 100.0)
        assert abs(fv.z_score) > 3.0

    def test_rate_of_change(self, feature_engine):
        feature_engine.compute("v", 7.0, 0.0)
        fv = feature_engine.compute("v", 8.0, 1.0)
        assert fv.rate_of_change == pytest.approx(1.0, abs=0.1)

    def test_rolling_stats(self, feature_engine):
        values = [7.0, 7.2, 7.4, 7.1, 7.3]
        for i, v in enumerate(values):
            fv = feature_engine.compute("v", v, float(i))

        assert fv.rolling_mean == pytest.approx(np.mean(values), abs=0.01)
        assert fv.rolling_std == pytest.approx(np.std(values, ddof=1), abs=0.01)
        assert fv.rolling_min == 7.0
        assert fv.rolling_max == 7.4

    def test_cross_features_correlated(self, feature_engine):
        # Two perfectly correlated parameters
        for i in range(50):
            feature_engine.compute("solar", float(i) * 0.1, float(i))
            feature_engine.compute("battery", float(i) * 0.05 + 7.0, float(i))

        cross = feature_engine.compute_cross_features("solar", "battery")
        assert cross["correlation"] > 0.9

    def test_cross_features_insufficient_data(self, feature_engine):
        feature_engine.compute("a", 1.0, 0.0)
        cross = feature_engine.compute_cross_features("a", "b")
        assert cross["correlation"] == 0.0

    def test_multivariate_snapshot(self, feature_engine):
        for i in range(10):
            feature_engine.compute("a", float(i), float(i))
            feature_engine.compute("b", float(i) * 2, float(i))

        snap = feature_engine.get_multivariate_snapshot(["a", "b"])
        assert snap is not None
        assert len(snap) == 2

    def test_multivariate_snapshot_incomplete(self, feature_engine):
        feature_engine.compute("a", 1.0, 0.0)
        snap = feature_engine.get_multivariate_snapshot(["a", "b"])
        assert snap is None

    def test_reset(self, feature_engine):
        feature_engine.compute("v", 7.4, 0.0)
        feature_engine.reset("v")
        fv = feature_engine.compute("v", 7.4, 1.0)
        assert fv.z_score == 0.0  # back to no history
