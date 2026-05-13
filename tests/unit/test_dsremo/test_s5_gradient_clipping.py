"""Tests for V3-S5: gradient clipping + training divergence detection.

Validates:
 1. Normal training completes without divergence (backward-compat smoke test)
 2. Training on contaminated data (NaN residual) detects divergence and leaves
    is_fitted == False — detect() then returns NOMINAL with reason model_not_fitted
 3. Gradient clipping is exercised without breaking training on clean data
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector


def _train_on(values: list[float], epochs: int = 2) -> AutoencoderDetector:
    det = AutoencoderDetector(
        seq_length=16, epochs=epochs, min_train_samples=40, retrain_interval=100,
    )
    for v in values:
        det.add_sample(v)
    det.fit()
    return det


class TestCleanTraining:

    def test_fit_completes_on_clean_data(self):
        # 80 samples of mild Gaussian noise.
        import numpy as np
        rng = np.random.default_rng(0)
        values = rng.normal(size=80).tolist()
        det = _train_on(values)
        assert det.is_fitted
        # Verify all parameters are finite (gradient clipping kept them tame).
        for p in det._model.parameters():
            assert torch.isfinite(p).all()


class TestDivergence:

    def test_nan_input_triggers_divergence_recovery(self):
        """A NaN in the training buffer induces NaN loss; the detector should
        flag divergence and leave is_fitted = False rather than silently
        producing a broken model."""
        values = [0.0] * 40 + [float("nan")] * 40
        det = _train_on(values, epochs=3)
        # Training should detect the NaN loss and bail out.
        assert not det.is_fitted

    def test_detect_on_diverged_model_returns_nominal(self):
        values = [0.0] * 40 + [float("inf")] * 40
        det = _train_on(values, epochs=3)
        assert not det.is_fitted
        result = det.detect([0.0] * 16)
        assert result.detector_name == "lstm"
        assert not result.is_anomaly
        assert result.details.get("reason") == "model_not_fitted"
