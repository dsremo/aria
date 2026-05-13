"""Tests for V3-H1: hierarchical-Bayes per-class LLR weights."""

from __future__ import annotations

import numpy as np
import pytest

from aria.dsremo.detection.hierarchical_llr import (
    HierarchicalLLRWeights,
)


DETECTORS = ["cusum", "ewma", "gru", "bocpd", "variance"]


class TestConstruction:

    def test_empty_detectors_rejected(self):
        with pytest.raises(ValueError):
            HierarchicalLLRWeights([])

    def test_duplicate_detectors_rejected(self):
        with pytest.raises(ValueError):
            HierarchicalLLRWeights(["cusum", "ewma", "cusum"])

    def test_bad_prior_strength(self):
        with pytest.raises(ValueError):
            HierarchicalLLRWeights(DETECTORS, prior_strength=0)

    def test_bad_min_class_samples(self):
        with pytest.raises(ValueError):
            HierarchicalLLRWeights(DETECTORS, min_class_samples=0)

    def test_default_global_is_uniform(self):
        hlr = HierarchicalLLRWeights(DETECTORS)
        gw = hlr.global_weights
        assert set(gw.keys()) == set(DETECTORS)
        assert all(gw[d] == pytest.approx(1 / len(DETECTORS)) for d in DETECTORS)


class TestSetGlobalWeights:

    def test_happy_normalise(self):
        hlr = HierarchicalLLRWeights(DETECTORS)
        hlr.set_global_weights({"cusum": 2.0, "ewma": 1.0, "gru": 1.0})
        gw = hlr.global_weights
        assert sum(gw.values()) == pytest.approx(1.0)
        assert gw["cusum"] > gw["ewma"]

    def test_unknown_detector_rejected(self):
        hlr = HierarchicalLLRWeights(DETECTORS)
        with pytest.raises(ValueError):
            hlr.set_global_weights({"unknown_det": 1.0})

    def test_negative_weight_rejected(self):
        hlr = HierarchicalLLRWeights(DETECTORS)
        with pytest.raises(ValueError):
            hlr.set_global_weights({"cusum": -1.0})

    def test_all_zero_rejected(self):
        hlr = HierarchicalLLRWeights(DETECTORS)
        with pytest.raises(ValueError):
            hlr.set_global_weights({d: 0.0 for d in DETECTORS})


class TestFitClass:

    def _make_data(
        self,
        n: int,
        seed: int,
        informative_dim: int,
    ):
        """Labels correlated with one detector dimension; others noise."""
        rng = np.random.default_rng(seed)
        n_pos = n // 2
        scores = rng.random((n, len(DETECTORS)))
        labels = np.zeros(n, dtype=np.int8)
        labels[:n_pos] = 1
        # Boost the informative dimension for positives
        scores[labels == 1, informative_dim] += 1.0
        return scores, labels

    def test_fit_class_shifts_weight_toward_informative(self):
        hlr = HierarchicalLLRWeights(DETECTORS, prior_strength=30)
        scores, labels = self._make_data(n=200, seed=0, informative_dim=2)
        stats = hlr.fit_class("LEO_cubesat", scores, labels)
        w = stats.weights
        # GRU (informative) should end up with the largest weight.
        assert max(w, key=w.get) == "gru"
        # Sum to 1 (normalised).
        assert sum(w.values()) == pytest.approx(1.0, abs=1e-9)

    def test_shrinkage_larger_n_less_global(self):
        hlr = HierarchicalLLRWeights(DETECTORS, prior_strength=30)
        small, small_labels = self._make_data(n=10, seed=0, informative_dim=2)
        large, large_labels = self._make_data(n=1000, seed=0, informative_dim=2)

        small_stats = hlr.fit_class("SMALL", small, small_labels)
        large_stats = hlr.fit_class("LARGE", large, large_labels)
        # Larger class → higher alpha (closer to MLE).
        assert large_stats.shrinkage_alpha > small_stats.shrinkage_alpha

    def test_class_below_min_falls_back_to_global(self):
        hlr = HierarchicalLLRWeights(DETECTORS, prior_strength=30, min_class_samples=20)
        scores, labels = self._make_data(n=5, seed=0, informative_dim=2)
        stats = hlr.fit_class("TINY", scores, labels)
        assert stats.shrinkage_alpha == 0.0
        assert stats.weights == hlr.global_weights

    def test_no_signal_falls_back_to_global(self):
        hlr = HierarchicalLLRWeights(DETECTORS, prior_strength=30, min_class_samples=5)
        rng = np.random.default_rng(0)
        scores = rng.random((100, len(DETECTORS)))
        labels = np.zeros(100, dtype=np.int8)  # all-zero labels → no signal
        stats = hlr.fit_class("EMPTY", scores, labels)
        assert stats.weights == hlr.global_weights

    def test_reject_bad_score_shape(self):
        hlr = HierarchicalLLRWeights(DETECTORS)
        with pytest.raises(ValueError):
            hlr.fit_class("X", np.zeros((10, 3)), np.zeros(10))  # wrong D


class TestGetWeights:

    def test_known_class_returns_shrunk(self):
        hlr = HierarchicalLLRWeights(DETECTORS, prior_strength=30, min_class_samples=5)
        rng = np.random.default_rng(0)
        scores = rng.random((200, len(DETECTORS)))
        # Give dim 0 strong correlation with labels
        labels = (scores[:, 0] > 0.5).astype(np.int8)
        hlr.fit_class("LEO_medium", scores, labels)
        w = hlr.get_weights("LEO_medium")
        assert sum(w.values()) == pytest.approx(1.0)
        assert w["cusum"] > 1 / len(DETECTORS)  # informative dim (cusum=idx0) inflated

    def test_unknown_class_returns_global(self):
        hlr = HierarchicalLLRWeights(DETECTORS)
        hlr.set_global_weights({"cusum": 3.0, "ewma": 1.0})
        w = hlr.get_weights("DEEP_SPACE_PROBE")
        gw = hlr.global_weights
        assert w == gw

    def test_class_stats_accessor(self):
        hlr = HierarchicalLLRWeights(DETECTORS, prior_strength=30, min_class_samples=5)
        rng = np.random.default_rng(0)
        scores = rng.random((50, len(DETECTORS)))
        labels = (scores[:, 2] > 0.5).astype(np.int8)
        hlr.fit_class("LEO", scores, labels)
        stats = hlr.class_stats("LEO")
        assert stats is not None
        assert "LEO" in hlr.known_classes()

    def test_reset_class(self):
        hlr = HierarchicalLLRWeights(DETECTORS, prior_strength=30, min_class_samples=5)
        rng = np.random.default_rng(0)
        scores = rng.random((50, len(DETECTORS)))
        labels = (scores[:, 2] > 0.5).astype(np.int8)
        hlr.fit_class("LEO", scores, labels)
        hlr.reset_class("LEO")
        assert hlr.class_stats("LEO") is None
        assert hlr.get_weights("LEO") == hlr.global_weights
