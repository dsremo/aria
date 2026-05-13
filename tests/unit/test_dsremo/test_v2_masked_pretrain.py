"""Tests for V3-V2: masked-residual pretraining + warm-start."""

from __future__ import annotations

import numpy as np
import pytest

from aria.dsremo.detection.masked_pretrain import (
    DEFAULT_MASK_RATIO,
    MaskedPretrainConfig,
    build_masked_windows,
)


def _synthetic_sat(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return (0.4 * np.sin(2 * np.pi * t / 40.0)
            + rng.normal(0.0, 0.05, n)).astype(np.float32)


class TestBuildMaskedWindows:

    def test_shape_matches_corpus(self):
        corpus = {"A": _synthetic_sat(90, 0), "B": _synthetic_sat(90, 1)}
        X_mask, X_tgt, mask, mean, std = build_masked_windows(
            corpus, seq_length=30, rng=np.random.default_rng(0),
        )
        # Each sat contributes 3 disjoint 30-sample windows → 6 total
        assert X_mask.shape == (6, 30)
        assert X_tgt.shape == (6, 30)
        assert mask.shape == (6, 30)
        assert np.isfinite(mean)
        assert std > 0.0

    def test_mask_zeros_positions_in_X_masked(self):
        corpus = {"A": _synthetic_sat(120, 0)}
        X_mask, X_tgt, mask, mean, std = build_masked_windows(
            corpus, seq_length=30, rng=np.random.default_rng(0),
        )
        for k in range(X_mask.shape[0]):
            masked_positions = mask[k].astype(bool)
            # Zero-masked → X_masked[row, masked] == 0
            assert np.all(X_mask[k, masked_positions] == 0.0)

    def test_at_least_one_masked_position_per_window(self):
        corpus = {"A": _synthetic_sat(900, 0)}
        X_mask, X_tgt, mask, _, _ = build_masked_windows(
            corpus,
            seq_length=30,
            mask_ratio=0.02,  # low ratio → some rows could round to zero masks
            rng=np.random.default_rng(0),
        )
        assert (mask.sum(axis=1) >= 1.0).all()

    def test_skips_too_short_satellites(self):
        corpus = {"short": np.zeros(10, dtype=np.float32),
                  "long":  _synthetic_sat(90, 0)}
        X_mask, _, _, _, _ = build_masked_windows(
            corpus, seq_length=30, rng=np.random.default_rng(0),
        )
        # Only "long" contributes: 90 // 30 = 3 windows
        assert X_mask.shape == (3, 30)

    def test_rejects_empty_corpus(self):
        with pytest.raises(ValueError):
            build_masked_windows({}, seq_length=30)

    def test_rejects_all_too_short(self):
        corpus = {"a": np.zeros(5), "b": np.zeros(5)}
        with pytest.raises(ValueError):
            build_masked_windows(corpus, seq_length=30)

    def test_rejects_bad_mask_ratio(self):
        corpus = {"a": _synthetic_sat(90, 0)}
        with pytest.raises(ValueError):
            build_masked_windows(corpus, seq_length=30, mask_ratio=0.0)
        with pytest.raises(ValueError):
            build_masked_windows(corpus, seq_length=30, mask_ratio=1.0)

    def test_rejects_non_positive_seq_length(self):
        corpus = {"a": _synthetic_sat(90, 0)}
        with pytest.raises(ValueError):
            build_masked_windows(corpus, seq_length=0)

    def test_normalisation_stats_match_numpy(self):
        corpus = {"A": _synthetic_sat(90, 0), "B": _synthetic_sat(90, 1)}
        _, _, _, mean, std = build_masked_windows(
            corpus, seq_length=30, rng=np.random.default_rng(0),
        )
        pooled = np.concatenate([corpus["A"], corpus["B"]]).astype(np.float64)
        assert mean == pytest.approx(float(pooled.mean()), rel=1e-5)
        assert std == pytest.approx(float(pooled.std()), rel=1e-5)

    def test_default_mask_ratio_canonical(self):
        assert DEFAULT_MASK_RATIO == pytest.approx(0.15)


class TestPretrainAndWarmstart:
    """Integration tests — skipped if torch is missing."""

    @pytest.fixture
    def torch_available(self):
        pytest.importorskip("torch")

    def _corpus(self, k_sats: int = 6, samples: int = 300):
        return {
            f"SAT-{i}": _synthetic_sat(samples, seed=i)
            for i in range(k_sats)
        }

    def test_pretrain_produces_result(self, torch_available, tmp_path):
        from aria.dsremo.detection.masked_pretrain import (
            pretrain_gru_on_corpus,
            save_pretrain_result,
            load_pretrain_result,
        )
        cfg = MaskedPretrainConfig(
            seq_length=15, hidden=8, bottleneck=4, epochs=3,
        )
        result = pretrain_gru_on_corpus(
            self._corpus(k_sats=8, samples=450),
            config=cfg,
            rng_seed=0,
        )
        assert result.n_windows >= 200
        assert result.n_satellites == 8
        assert np.isfinite(result.final_loss)
        path = tmp_path / "pre.pt"
        save_pretrain_result(result, path)
        assert path.exists()
        rehydrated = load_pretrain_result(path)
        assert rehydrated.config.seq_length == 15
        assert rehydrated.train_mean == pytest.approx(result.train_mean)

    def test_warmstart_loads_matching_checkpoint(self, torch_available, tmp_path):
        pytest.importorskip("torch")
        from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
        from aria.dsremo.detection.masked_pretrain import (
            pretrain_gru_on_corpus,
            save_pretrain_result,
        )
        cfg = MaskedPretrainConfig(
            seq_length=15, hidden=8, bottleneck=4, epochs=3,
        )
        result = pretrain_gru_on_corpus(
            self._corpus(k_sats=8, samples=450), config=cfg, rng_seed=0,
        )
        path = tmp_path / "pre.pt"
        save_pretrain_result(result, path)

        det = AutoencoderDetector(
            seq_length=15, hidden_size=8, bottleneck_size=4, min_train_samples=30, epochs=1,
        )
        assert det.warmstart_from(path) is True
        assert det.is_fitted
        # detect() should return a valid score post-warmstart
        res = det.detect(list(_synthetic_sat(15, seed=99)))
        assert 0.0 <= res.score <= 1.0

    def test_warmstart_rejects_shape_mismatch(self, torch_available, tmp_path):
        from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
        from aria.dsremo.detection.masked_pretrain import (
            pretrain_gru_on_corpus,
            save_pretrain_result,
        )
        cfg = MaskedPretrainConfig(seq_length=15, hidden=8, bottleneck=4, epochs=2)
        result = pretrain_gru_on_corpus(
            self._corpus(k_sats=8, samples=450), config=cfg, rng_seed=0,
        )
        path = tmp_path / "pre.pt"
        save_pretrain_result(result, path)

        # Different hidden size → must refuse to load.
        det = AutoencoderDetector(
            seq_length=15, hidden_size=16, bottleneck_size=4, min_train_samples=30, epochs=1,
        )
        assert det.warmstart_from(path) is False
        assert det.is_fitted is False

    def test_warmstart_missing_file_returns_false(self, torch_available, tmp_path):
        from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
        det = AutoencoderDetector()
        assert det.warmstart_from(tmp_path / "nope.pt") is False
        assert det.is_fitted is False
