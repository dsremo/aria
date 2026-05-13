"""Integration test: V3-V2 masked-pretrain warmstart wired into
`detector._get_lstm_model()` via `register_pretrain_path`.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")  # noqa: E402
import numpy as np

from aria.dsremo.detection import detector as det_mod
from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
from aria.dsremo.detection.masked_pretrain import (
    MaskedPretrainConfig,
    pretrain_gru_on_corpus,
    save_pretrain_result,
)


@pytest.fixture(autouse=True)
def _reset():
    det_mod.register_pretrain_path(None)
    det_mod._lstm_models.clear()
    yield
    det_mod.register_pretrain_path(None)
    det_mod._lstm_models.clear()


def _corpus(k_sats: int = 8, samples: int = 900):
    # Need ≥200 disjoint seq_length=30 windows across the corpus.
    # 8 sats × 900 samples ÷ 30 = 240 windows → safely above MIN_CORPUS_WINDOWS=200.
    rng = np.random.default_rng(0)
    out = {}
    for i in range(k_sats):
        t = np.arange(samples)
        out[f"SAT-{i}"] = (0.4 * np.sin(2 * np.pi * t / 40.0)
                           + rng.normal(0.0, 0.05, samples)).astype(np.float32)
    return out


class TestWarmstartIntegration:

    def test_no_pretrain_falls_back_to_cold_start(self):
        det_mod.register_pretrain_path(None)
        m = det_mod._build_lstm_with_optional_warmstart()
        assert isinstance(m, AutoencoderDetector)
        assert not m.is_fitted  # cold start

    def test_register_none_clears(self, tmp_path):
        det_mod.register_pretrain_path(tmp_path / "pre.pt")
        assert det_mod._pretrain_path is not None
        det_mod.register_pretrain_path(None)
        assert det_mod._pretrain_path is None

    def test_pretrain_loads_on_construction(self, tmp_path):
        cfg = MaskedPretrainConfig(
            seq_length=det_mod._lstm_seq_length,
            hidden=det_mod._lstm_hidden_size,
            bottleneck=det_mod._lstm_bottleneck_size,
            epochs=2,
        )
        result = pretrain_gru_on_corpus(_corpus(), config=cfg, rng_seed=0)
        path = tmp_path / "pre.pt"
        save_pretrain_result(result, path)

        det_mod.register_pretrain_path(path)
        m = det_mod._build_lstm_with_optional_warmstart()
        assert m.is_fitted, "pretrain path set → model should be warmstarted"

    def test_shape_mismatch_silently_cold_starts(self, tmp_path):
        # Pretrain with different arch than the detector defaults.
        cfg = MaskedPretrainConfig(
            seq_length=det_mod._lstm_seq_length,
            hidden=det_mod._lstm_hidden_size + 99,   # deliberate mismatch
            bottleneck=det_mod._lstm_bottleneck_size,
            epochs=2,
        )
        result = pretrain_gru_on_corpus(_corpus(), config=cfg, rng_seed=0)
        path = tmp_path / "pre.pt"
        save_pretrain_result(result, path)

        det_mod.register_pretrain_path(path)
        m = det_mod._build_lstm_with_optional_warmstart()
        # Silent cold-start on mismatch per the V3-V2 contract.
        assert not m.is_fitted

    def test_missing_file_silently_cold_starts(self, tmp_path):
        det_mod.register_pretrain_path(tmp_path / "does_not_exist.pt")
        m = det_mod._build_lstm_with_optional_warmstart()
        assert not m.is_fitted

    def test_get_lstm_model_uses_warmstart_factory(self, tmp_path):
        """Verify the hot path `_get_lstm_model` delegates through."""
        cfg = MaskedPretrainConfig(
            seq_length=det_mod._lstm_seq_length,
            hidden=det_mod._lstm_hidden_size,
            bottleneck=det_mod._lstm_bottleneck_size,
            epochs=2,
        )
        result = pretrain_gru_on_corpus(_corpus(), config=cfg, rng_seed=0)
        path = tmp_path / "pre.pt"
        save_pretrain_result(result, path)
        det_mod.register_pretrain_path(path)

        m = det_mod._get_lstm_model("SAT-HOT", "bat_v")
        assert m.is_fitted, "_get_lstm_model must use warmstart factory"
