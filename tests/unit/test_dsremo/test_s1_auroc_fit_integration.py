"""V3-S1 integration: fit(use_auroc_objective=True) end-to-end.

Requires torch; skipped otherwise.  Uses the AutoencoderDetector (GRU)
subclass; TCN behaviour is identical through AbstractMLDetector.fit().
"""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")  # noqa: E402

from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector


def _clean_stream(n: int, seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    # Smooth sine + small Gaussian noise — easy for a tiny GRU to fit.
    t = np.arange(n)
    sig = 0.5 * np.sin(2 * np.pi * t / 50.0) + rng.normal(0.0, 0.05, n)
    return sig.astype(np.float32).tolist()


class TestAurocFit:

    def test_fit_with_auroc_objective_produces_fitted_model(self):
        det = AutoencoderDetector(
            seq_length=16, hidden_size=8, bottleneck_size=4,
            min_train_samples=80, epochs=12,
        )
        det._buffer = _clean_stream(400, seed=0)
        det.fit(use_auroc_objective=True, auroc_seed=0, auroc_patience=3)
        assert det.is_fitted, "AUROC-path fit must set is_fitted"
        # Plain 1-channel path preserved.
        assert det._input_channels == 1
        assert np.isfinite(det._threshold)

    def test_auroc_path_backward_compat_default_false(self):
        det = AutoencoderDetector(
            seq_length=16, hidden_size=8, bottleneck_size=4,
            min_train_samples=80, epochs=5,
        )
        det._buffer = _clean_stream(200, seed=0)
        det.fit()  # default path
        assert det.is_fitted

    def test_auroc_path_handles_too_small_buffer(self):
        det = AutoencoderDetector(
            seq_length=16, hidden_size=8, bottleneck_size=4,
            min_train_samples=80, epochs=4,
        )
        det._buffer = _clean_stream(90, seed=0)
        # Val slice would be too small for AUROC; fit must still succeed
        # by silently falling back to the MSE loop.
        det.fit(use_auroc_objective=True, auroc_seed=0)
        assert det.is_fitted

    def test_auroc_detect_still_works(self):
        det = AutoencoderDetector(
            seq_length=16, hidden_size=8, bottleneck_size=4,
            min_train_samples=80, epochs=10,
        )
        det._buffer = _clean_stream(400, seed=1)
        det.fit(use_auroc_objective=True, auroc_seed=1, auroc_patience=3)
        # Clean window → low score.
        clean = _clean_stream(16, seed=99)
        res = det.detect(clean)
        assert res.score >= 0.0 and res.score <= 1.0
        # Pathological window → typically higher score.
        spike_window = clean[:-1] + [10.0]
        res_spike = det.detect(spike_window)
        assert res_spike.score >= res.score
