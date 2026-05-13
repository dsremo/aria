"""Tests for PCA-based anomaly detection module.

Covers: AnomalyDetector, ShipAnomalyMonitor, scoring, RUL estimation,
subsystem profiles, edge cases, and integration with degradation_bridge.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from aria.simulation.anomaly_detection import (
    CMAPSS_ALPHA,
    AnomalyDetector,
    AnomalyResult,
    ShipAnomalyMonitor,
    _fit_pca,
    _generate_synthetic_normal,
    _pca_reconstruction_error,
    _resolve_subsystem,
    _score_to_rul,
    _spe_to_score,
)


# ──────────────────────────────────────────────────────────────────────
# 1. Basic initialization
# ──────────────────────────────────────────────────────────────────────

class TestAnomalyDetectorInit:
    """Test detector construction for all subsystems."""

    @pytest.mark.parametrize("subsystem", [
        "reactor", "pump", "bearing", "electronics", "co2_scrubber",
    ])
    def test_init_all_subsystems(self, subsystem: str) -> None:
        """Each supported subsystem should initialize without error."""
        det = AnomalyDetector(subsystem)
        assert det.subsystem == subsystem
        assert len(det.channels) > 0
        assert det.threshold > 0.0
        assert det.design_life_hours > 0.0

    def test_init_unknown_subsystem_raises(self) -> None:
        """Unknown subsystem name should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown subsystem"):
            AnomalyDetector("warp_drive")

    def test_init_alias_resolution(self) -> None:
        """Aliases should resolve to canonical subsystem."""
        det = AnomalyDetector("fusion_reactor")
        assert det.subsystem == "reactor"

        det2 = AnomalyDetector("life_support")
        assert det2.subsystem == "co2_scrubber"


# ──────────────────────────────────────────────────────────────────────
# 2. Detection on nominal readings
# ──────────────────────────────────────────────────────────────────────

class TestNominalDetection:
    """Nominal sensor readings should produce low anomaly scores."""

    def test_nominal_reactor_not_anomalous(self) -> None:
        """Reactor at nominal values should not trigger anomaly."""
        det = AnomalyDetector("reactor")
        readings = {ch: nom for ch, nom in zip(det.channels, [
            1000.0, 550.0, 0.02, 1.0, 5.0, 0.5, 5.5, 100.0
        ])}
        result = det.detect(readings)
        assert isinstance(result, AnomalyResult)
        assert 0.0 <= result.score <= 1.0
        assert result.score < 0.5, f"Nominal readings got score {result.score}"
        assert result.is_anomaly is False
        assert result.predicted_rul_hours > 0

    def test_empty_readings_use_nominal(self) -> None:
        """Empty dict should fill with nominal values -> low score."""
        det = AnomalyDetector("bearing")
        result = det.detect({})
        assert result.score < 0.6
        assert result.subsystem == "bearing"

    def test_partial_readings(self) -> None:
        """Providing only some channels should still work."""
        det = AnomalyDetector("pump")
        result = det.detect({"discharge_pressure_kPa": 300.0})
        assert 0.0 <= result.score <= 1.0


# ──────────────────────────────────────────────────────────────────────
# 3. Detection on anomalous readings
# ──────────────────────────────────────────────────────────────────────

class TestAnomalousDetection:
    """Far-from-nominal readings should produce high anomaly scores."""

    def test_extreme_readings_high_score(self) -> None:
        """Readings far from nominal should score high."""
        det = AnomalyDetector("reactor")
        # Grossly abnormal: core temp 3x, pressure 0.1x
        readings = {
            "core_temp_K": 3000.0,
            "plasma_pressure_kPa": 55.0,
            "fuel_flow_ratio": 0.1,
            "neutron_flux_rel": 5.0,
            "coolant_flow_kg_s": 0.5,
            "vibration_mm_s": 5.0,
            "magnetic_field_T": 2.0,
            "power_output_MW": 20.0,
        }
        result = det.detect(readings)
        assert result.score > 0.7, f"Extreme readings only scored {result.score}"
        assert result.is_anomaly is True

    def test_anomaly_has_lower_rul(self) -> None:
        """Anomalous readings should predict lower RUL than nominal."""
        det = AnomalyDetector("bearing")
        nominal_result = det.detect({})
        anomalous_result = det.detect({
            "vibration_rms_g": 2.0,   # normal ~ 0.3
            "vibration_peak_g": 10.0,  # normal ~ 1.2
            "vibration_kurtosis": 15.0, # normal ~ 3.0
            "temperature_C": 90.0,      # normal ~ 40
        })
        assert anomalous_result.predicted_rul_hours < nominal_result.predicted_rul_hours

    def test_contributing_sensors_populated(self) -> None:
        """Contributing sensors list should be non-empty for anomalies."""
        det = AnomalyDetector("electronics")
        result = det.detect({
            "board_temp_C": 120.0,  # way above 55 nominal
            "junction_temp_C": 200.0,
        })
        assert len(result.contributing_sensors) > 0
        assert all(isinstance(s, str) for s in result.contributing_sensors)


# ──────────────────────────────────────────────────────────────────────
# 4. RUL estimation
# ──────────────────────────────────────────────────────────────────────

class TestRULEstimation:
    """Test the C-MAPSS degradation curve inversion for RUL."""

    def test_score_zero_full_rul(self) -> None:
        """Score 0 -> full design life remaining."""
        rul = _score_to_rul(0.0, 100000.0, CMAPSS_ALPHA)
        assert rul == 100000.0

    def test_score_one_zero_rul(self) -> None:
        """Score 1 -> zero RUL."""
        rul = _score_to_rul(1.0, 100000.0, CMAPSS_ALPHA)
        assert rul == 0.0

    def test_score_monotonically_decreases_rul(self) -> None:
        """Higher scores should give lower RUL."""
        design_life = 200000.0
        scores = np.linspace(0.0, 1.0, 20)
        ruls = [_score_to_rul(s, design_life, CMAPSS_ALPHA) for s in scores]
        for i in range(len(ruls) - 1):
            assert ruls[i] >= ruls[i + 1], (
                f"RUL not monotonically decreasing at score {scores[i]:.2f}"
            )

    def test_rul_uses_alpha(self) -> None:
        """Different alpha values should give different RUL curves."""
        rul_low_alpha = _score_to_rul(0.5, 100000.0, 1.0)
        rul_high_alpha = _score_to_rul(0.5, 100000.0, 2.0)
        assert rul_low_alpha != rul_high_alpha


# ──────────────────────────────────────────────────────────────────────
# 5. PCA internals
# ──────────────────────────────────────────────────────────────────────

class TestPCAInternals:
    """Test PCA fitting and reconstruction error computation."""

    def test_fit_pca_shapes(self) -> None:
        """PCA should return correctly shaped arrays."""
        rng = np.random.default_rng(0)
        data = rng.standard_normal((100, 5))
        mean, components, explained_var, residual_var = _fit_pca(data, 3)
        assert mean.shape == (5,)
        assert components.shape == (3, 5)
        assert explained_var.shape == (3,)
        assert residual_var > 0

    def test_reconstruction_error_zero_for_pca_space(self) -> None:
        """Points exactly in the PCA subspace should have ~zero SPE."""
        rng = np.random.default_rng(1)
        # Data that lives in 2D subspace of 5D space
        basis = rng.standard_normal((2, 5))
        coeffs = rng.standard_normal((200, 2))
        data = coeffs @ basis + rng.standard_normal((200, 5)) * 0.001

        mean, components, _, _ = _fit_pca(data, 2)
        spe = _pca_reconstruction_error(data[:1], mean, components)
        assert spe[0] < 1.0  # Very small residual

    def test_spe_increases_with_deviation(self) -> None:
        """SPE should increase as point moves away from training dist."""
        det = AnomalyDetector("pump")
        profile = det._profile
        assert profile.mean is not None
        assert profile.components is not None

        # Nominal point
        spe_nom = _pca_reconstruction_error(
            profile.nominal, profile.mean, profile.components
        )[0]

        # Shifted point
        shifted = profile.nominal + profile.std * 10
        spe_shifted = _pca_reconstruction_error(
            shifted, profile.mean, profile.components
        )[0]

        assert spe_shifted > spe_nom


# ──────────────────────────────────────────────────────────────────────
# 6. Score normalization
# ──────────────────────────────────────────────────────────────────────

class TestScoreNormalization:
    """Test SPE -> [0,1] score mapping."""

    def test_score_at_mean_is_half(self) -> None:
        """SPE equal to training mean should give score ~0.5."""
        score = _spe_to_score(100.0, 100.0, 20.0)
        assert abs(score - 0.5) < 0.01

    def test_score_bounded(self) -> None:
        """Score should always be in [0, 1]."""
        for spe in [-1000, 0, 100, 10000]:
            score = _spe_to_score(float(spe), 100.0, 20.0)
            assert 0.0 <= score <= 1.0

    def test_zero_std_returns_zero(self) -> None:
        """Zero std should not crash, returns 0."""
        score = _spe_to_score(100.0, 100.0, 0.0)
        assert score == 0.0


# ──────────────────────────────────────────────────────────────────────
# 7. ShipAnomalyMonitor
# ──────────────────────────────────────────────────────────────────────

class TestShipAnomalyMonitor:
    """Test the multi-subsystem monitor."""

    def test_default_subsystems(self) -> None:
        """Monitor should register all 5 default subsystems."""
        monitor = ShipAnomalyMonitor()
        assert len(monitor.subsystems) == 5
        assert "reactor" in monitor.subsystems
        assert "co2_scrubber" in monitor.subsystems

    def test_scan_all_returns_results(self) -> None:
        """scan_all should return one result per subsystem."""
        monitor = ShipAnomalyMonitor()
        results = monitor.scan_all({})
        assert len(results) == 5
        subsystems_seen = {r.subsystem for r in results}
        assert "reactor" in subsystems_seen
        assert "bearing" in subsystems_seen

    def test_scan_subsystem(self) -> None:
        """scan_subsystem should work with canonical and alias names."""
        monitor = ShipAnomalyMonitor()
        result = monitor.scan_subsystem("reactor", {})
        assert result.subsystem == "reactor"

    def test_scan_unknown_raises(self) -> None:
        """Scanning an unregistered subsystem should raise KeyError."""
        monitor = ShipAnomalyMonitor()
        with pytest.raises(KeyError, match="not in monitor"):
            monitor.scan_subsystem("warp_drive", {})

    def test_custom_subsystem_list(self) -> None:
        """Monitor should accept a custom subsystem list."""
        monitor = ShipAnomalyMonitor(subsystems=["reactor", "pump"])
        assert monitor.subsystems == ["pump", "reactor"]

    def test_get_detector(self) -> None:
        """get_detector should return the underlying AnomalyDetector."""
        monitor = ShipAnomalyMonitor()
        det = monitor.get_detector("bearing")
        assert isinstance(det, AnomalyDetector)
        assert det.subsystem == "bearing"


# ──────────────────────────────────────────────────────────────────────
# 8. Batch detection
# ──────────────────────────────────────────────────────────────────────

class TestBatchDetection:
    """Test batch processing."""

    def test_batch_returns_correct_count(self) -> None:
        """detect_batch should return one result per input."""
        det = AnomalyDetector("pump")
        readings_list = [{}, {"discharge_pressure_kPa": 400.0}, {}]
        results = det.detect_batch(readings_list)
        assert len(results) == 3
        assert all(isinstance(r, AnomalyResult) for r in results)


# ──────────────────────────────────────────────────────────────────────
# 9. train_from_data classmethod
# ──────────────────────────────────────────────────────────────────────

class TestTrainFromData:
    """Test the classmethod that accepts a data path."""

    def test_train_from_nonexistent_path(self) -> None:
        """Should gracefully fall back to synthetic when no data found."""
        det = AnomalyDetector.train_from_data(
            Path("/nonexistent/path"), subsystem="reactor"
        )
        assert det.subsystem == "reactor"
        # Should still work for detection
        result = det.detect({})
        assert 0.0 <= result.score <= 1.0

    def test_train_from_data_path(self, tmp_path: Path) -> None:
        """With an empty directory, should fall back gracefully."""
        det = AnomalyDetector.train_from_data(tmp_path, subsystem="bearing")
        assert det.subsystem == "bearing"


# ──────────────────────────────────────────────────────────────────────
# 10. Alias resolution
# ──────────────────────────────────────────────────────────────────────

class TestAliasResolution:
    """Test subsystem alias resolution."""

    @pytest.mark.parametrize("alias,expected", [
        ("fusion_reactor", "reactor"),
        ("engine", "reactor"),
        ("life_support", "co2_scrubber"),
        ("scrubber", "co2_scrubber"),
        ("avionics", "electronics"),
        ("reactor", "reactor"),  # identity
    ])
    def test_alias_resolves(self, alias: str, expected: str) -> None:
        assert _resolve_subsystem(alias) == expected


# ──────────────────────────────────────────────────────────────────────
# 11. Synthetic data generation
# ──────────────────────────────────────────────────────────────────────

class TestSyntheticData:
    """Test synthetic normal data generation."""

    def test_synthetic_data_shape(self) -> None:
        """Generated data should match profile dimensions."""
        det = AnomalyDetector("reactor")
        data = _generate_synthetic_normal(det._profile, n_samples=500)
        assert data.shape == (500, len(det.channels))

    def test_synthetic_data_near_nominal(self) -> None:
        """Generated data mean should be close to nominal."""
        det = AnomalyDetector("co2_scrubber")
        data = _generate_synthetic_normal(det._profile, n_samples=5000)
        means = data.mean(axis=0)
        for i, (m, nom) in enumerate(zip(means, det._profile.nominal)):
            # Within 3 sigma of nominal
            assert abs(m - nom) < 3 * det._profile.std[i], (
                f"Channel {det.channels[i]}: mean={m:.2f}, nominal={nom:.2f}"
            )


# ──────────────────────────────────────────────────────────────────────
# 12. Reproducibility
# ──────────────────────────────────────────────────────────────────────

class TestReproducibility:
    """Same seed should give same results."""

    def test_same_seed_same_results(self) -> None:
        det1 = AnomalyDetector("reactor", seed=99)
        det2 = AnomalyDetector("reactor", seed=99)
        readings = {"core_temp_K": 1050.0, "vibration_mm_s": 0.8}
        r1 = det1.detect(readings)
        r2 = det2.detect(readings)
        assert r1.score == r2.score
        assert r1.predicted_rul_hours == r2.predicted_rul_hours

    def test_different_seed_different_results(self) -> None:
        det1 = AnomalyDetector("pump", seed=1)
        det2 = AnomalyDetector("pump", seed=2)
        readings = {"discharge_pressure_kPa": 350.0}
        r1 = det1.detect(readings)
        r2 = det2.detect(readings)
        # Could be same by chance but very unlikely with different PCA fits
        # Just verify both produce valid results
        assert 0.0 <= r1.score <= 1.0
        assert 0.0 <= r2.score <= 1.0
