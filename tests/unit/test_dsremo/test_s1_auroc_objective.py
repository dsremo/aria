"""Tests for V3-S1: AUROC objective helpers (no torch required).

Covers:
  * inject_labeled_anomalies: shape, label count, rejects bad params
  * window_labels: prefix-sum semantics match the naive definition
  * auroc_from_scores: Hanley-McNeil identity, perfect / random / inverted
"""

from __future__ import annotations

import numpy as np
import pytest

from aria.dsremo.detection.auroc_objective import (
    auroc_from_scores,
    inject_labeled_anomalies,
    window_labels,
)


class TestInjectLabeled:

    def test_shape_and_dtype(self):
        rng = np.random.default_rng(0)
        clean = rng.standard_normal(200).astype(np.float32)
        out = inject_labeled_anomalies(clean, rng=rng)
        assert out.residuals.shape == (200,)
        assert out.sample_labels.shape == (200,)
        assert out.sample_labels.dtype == np.int8

    def test_injects_at_least_one_anomaly(self):
        rng = np.random.default_rng(0)
        clean = rng.standard_normal(500).astype(np.float32)
        out = inject_labeled_anomalies(clean, rng=rng)
        assert out.sample_labels.sum() >= 3

    def test_non_zero_rate_changes_values(self):
        rng = np.random.default_rng(0)
        clean = rng.standard_normal(300).astype(np.float32)
        out = inject_labeled_anomalies(clean, rng=rng)
        # At labelled indices the residual should differ from clean.
        mask = out.sample_labels == 1
        diff = np.abs(out.residuals[mask] - clean[mask])
        assert (diff > 0).all()

    def test_rejects_non_positive_rate(self):
        with pytest.raises(ValueError):
            inject_labeled_anomalies(np.zeros(30), injection_rate=0.0)
        with pytest.raises(ValueError):
            inject_labeled_anomalies(np.zeros(30), injection_rate=-0.1)

    def test_rejects_huge_rate(self):
        with pytest.raises(ValueError):
            inject_labeled_anomalies(np.zeros(30), injection_rate=0.8)

    def test_rejects_multi_dim(self):
        with pytest.raises(ValueError):
            inject_labeled_anomalies(np.zeros((30, 2)))

    def test_rejects_tiny_input(self):
        with pytest.raises(ValueError):
            inject_labeled_anomalies(np.zeros(5))

    def test_constant_input_still_injects(self):
        # sigma falls back to 1.0 when input is flat; function must not raise.
        out = inject_labeled_anomalies(np.zeros(100), rng=np.random.default_rng(0))
        assert out.sample_labels.sum() >= 3


class TestWindowLabels:

    def test_any_positive_in_window_is_one(self):
        sample = np.array([0, 0, 1, 0, 0, 0], dtype=np.int8)
        # seq_length=3 → 4 windows: [0,0,1]=1, [0,1,0]=1, [1,0,0]=1, [0,0,0]=0
        got = window_labels(sample, seq_length=3)
        assert got.tolist() == [1, 1, 1, 0]

    def test_all_zero_samples_yields_all_zero_windows(self):
        got = window_labels(np.zeros(10, dtype=np.int8), seq_length=3)
        assert got.tolist() == [0] * 8

    def test_all_one_samples_yields_all_one_windows(self):
        got = window_labels(np.ones(10, dtype=np.int8), seq_length=3)
        assert got.tolist() == [1] * 8

    def test_empty_windows_when_seq_longer_than_sample(self):
        got = window_labels(np.zeros(3, dtype=np.int8), seq_length=5)
        assert got.shape == (0,)

    def test_rejects_non_positive_seq_length(self):
        with pytest.raises(ValueError):
            window_labels(np.zeros(10, dtype=np.int8), seq_length=0)
        with pytest.raises(ValueError):
            window_labels(np.zeros(10, dtype=np.int8), seq_length=-3)

    def test_prefix_sum_matches_naive_definition(self):
        rng = np.random.default_rng(0)
        sample = (rng.random(200) < 0.1).astype(np.int8)
        seq = 8
        got = window_labels(sample, seq_length=seq)
        # Naive comparison
        naive = np.array([
            int(sample[i: i + seq].sum() > 0)
            for i in range(len(sample) - seq + 1)
        ], dtype=np.int8)
        assert (got == naive).all()


class TestAUROC:

    def test_perfect_separation_is_one(self):
        scores = np.array([0.1, 0.2, 0.9, 1.0])
        labels = np.array([0, 0, 1, 1])
        assert auroc_from_scores(scores, labels) == pytest.approx(1.0)

    def test_perfect_inversion_is_zero(self):
        scores = np.array([0.9, 1.0, 0.1, 0.2])
        labels = np.array([0, 0, 1, 1])
        assert auroc_from_scores(scores, labels) == pytest.approx(0.0)

    def test_all_tied_is_half(self):
        scores = np.ones(10)
        labels = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
        assert auroc_from_scores(scores, labels) == pytest.approx(0.5)

    def test_no_positives_returns_half(self):
        scores = np.array([0.1, 0.2, 0.3])
        labels = np.zeros(3)
        assert auroc_from_scores(scores, labels) == pytest.approx(0.5)

    def test_no_negatives_returns_half(self):
        scores = np.array([0.1, 0.2, 0.3])
        labels = np.ones(3)
        assert auroc_from_scores(scores, labels) == pytest.approx(0.5)

    def test_mixed_gives_known_value(self):
        # 2 pos, 3 neg: scores pos=[0.7, 0.3], neg=[0.1, 0.5, 0.9]
        # concordant pairs: (0.7,0.1)=1, (0.7,0.5)=1, (0.7,0.9)=0,
        #                   (0.3,0.1)=1, (0.3,0.5)=0, (0.3,0.9)=0 → 3/6 = 0.5
        scores = np.array([0.7, 0.3, 0.1, 0.5, 0.9])
        labels = np.array([1,   1,   0,   0,   0])
        assert auroc_from_scores(scores, labels) == pytest.approx(0.5, abs=1e-9)

    def test_tie_handling_uses_mean_rank(self):
        # Two pos @0.5, two neg @0.5, one pos @0.8 → AUROC should be > 0.5
        scores = np.array([0.5, 0.5, 0.5, 0.5, 0.8])
        labels = np.array([0, 0, 1, 1, 1])
        auroc = auroc_from_scores(scores, labels)
        assert 0.6 < auroc <= 1.0

    def test_rejects_shape_mismatch(self):
        with pytest.raises(ValueError):
            auroc_from_scores(np.array([1, 2, 3]), np.array([0, 1]))

    def test_rejects_multi_dim(self):
        with pytest.raises(ValueError):
            auroc_from_scores(np.zeros((3, 2)), np.zeros((3, 2)))


class TestIntegrationInjectScoreAUROC:

    def test_injection_separable_by_squared_residual(self):
        """The injected anomalies should be mechanically separable.

        Sanity: using |residual - mean| as the "anomaly score" against
        the known labels should give AUROC ≥ 0.95 on a clean baseline.
        """
        rng = np.random.default_rng(0)
        clean = rng.standard_normal(600).astype(np.float32)
        out = inject_labeled_anomalies(clean, rng=rng)
        score = np.abs(out.residuals - clean.mean())  # trivial detector
        auroc = auroc_from_scores(score, out.sample_labels.astype(float))
        assert auroc >= 0.95
