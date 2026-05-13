"""V3-H1: Hierarchical-Bayes per-satellite-class LLR ensemble weights.

Heckerman panel §H-1 in the V3 audit: the global LLR ensemble weights
(CUSUM 0.19, EWMA 0.16, GRU 0.12, ...) were learned from aggregate data
across *all* satellite classes, but detector informativeness varies
significantly by class:

  * GEO comms: BOCPD for solar-panel aging, CUSUM for transponder gain
  * LEO CubeSat: variance detector dominates under thermal cycling
  * MEO navigation: trend-velocity for atomic-clock drift

Using class-agnostic weights mis-allocates evidence for any class that
differs from the training mix.

Fix (Gelman 2013 §5.3): learn per-class weights with a weakly-
informative shared prior.  Classes with few labelled events lean
towards the global weights; classes with more data pull away from the
prior toward their own MLE.  No class re-learns from scratch.

This module is pure NumPy (no scipy dependence), bounded at ≲ 12 classes
× ≲ 16 detectors — the classical normal-normal partial-pooling
shrinkage estimator, a closed-form variant of hierarchical Bayes that
avoids MCMC and keeps the CPU-only promise.

Reference
  * Gelman, Carlin, Stern, Dunson, Vehtari, Rubin (2013) Bayesian Data
    Analysis, 3rd ed. §5.3 — hierarchical models for grouped data.
  * Jacobs, Jordan, Nowlan, Hinton 1991 Neural Computation 3(1):79-87
    — Adaptive Mixtures of Local Experts (mixture-of-experts foundation).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


DEFAULT_PRIOR_STRENGTH = 30   # ESTIMATE — 30 prior "pseudo-observations" anchors classes with ≲30 real samples to the global mean; Gelman 2013 §5.3 recommends n_prior of same order as class n
DEFAULT_MIN_CLASS_SAMPLES = 5 # ESTIMATE — below 5 labels the class-local MLE is pure noise; prefer global
DEFAULT_GLOBAL_WEIGHT = 1.0   # Prior weight is uniform across detectors by default (neutral); can be passed explicitly


@dataclass(frozen=True)
class ClassWeightStats:
    """Diagnostics for one class's weights after partial pooling."""

    class_name:      str
    n_samples:       int
    shrinkage_alpha: float
    weights:         dict[str, float] = field(default_factory=dict)
    mle_weights:     dict[str, float] = field(default_factory=dict)
    global_weights:  dict[str, float] = field(default_factory=dict)


def _detector_label_correlations(
    scores: np.ndarray,
    labels: np.ndarray,
) -> np.ndarray:
    """Return the per-detector Pearson correlation with {0, 1} labels.

    scores : shape (N, D) detector outputs in [0, 1]
    labels : shape (N,)   {0, 1}
    Zero-variance detectors get 0.  Negatives are clipped to 0
    (a detector anti-correlated with labels has no informational
    weight in a positive ensemble).
    """
    if scores.ndim != 2 or labels.ndim != 1:
        raise ValueError(
            f"scores must be (N,D) and labels (N,), got {scores.shape=} {labels.shape=}"
        )
    if scores.shape[0] != labels.shape[0]:
        raise ValueError("scores and labels have different N")
    if labels.size == 0:
        return np.zeros(scores.shape[1], dtype=np.float64)

    ly = labels.astype(np.float64)
    yd = ly - ly.mean()
    ys = ly.std()
    if ys == 0.0:
        return np.zeros(scores.shape[1], dtype=np.float64)

    D = scores.shape[1]
    out = np.zeros(D, dtype=np.float64)
    for d in range(D):
        x = scores[:, d].astype(np.float64)
        xs = x.std()
        if xs == 0.0:
            out[d] = 0.0
            continue
        out[d] = max(0.0, float(((x - x.mean()) * yd).mean() / (xs * ys)))
    return out


class HierarchicalLLRWeights:
    """Per-class ensemble weights with hierarchical-Bayes shrinkage.

    Public API
    ----------
    hlr = HierarchicalLLRWeights(detector_names=[...])
    hlr.set_global_weights({"cusum": 0.19, "ewma": 0.16, ...})
    hlr.fit_class("LEO_cubesat", scores_NxD, labels_N)
    hlr.fit_class("GEO_comms",  scores_NxD, labels_N)
    w = hlr.get_weights("LEO_cubesat")   # dict {detector: weight}, sums to 1
    w_new = hlr.get_weights("UNKNOWN_CLASS")  # falls back to global
    """

    def __init__(
        self,
        detector_names: list[str],
        *,
        prior_strength:     int   = DEFAULT_PRIOR_STRENGTH,
        min_class_samples:  int   = DEFAULT_MIN_CLASS_SAMPLES,
    ) -> None:
        if not detector_names:
            raise ValueError("detector_names cannot be empty")
        if len(set(detector_names)) != len(detector_names):
            raise ValueError(f"detector_names must be unique, got {detector_names!r}")
        if prior_strength <= 0:
            raise ValueError(f"prior_strength must be positive, got {prior_strength!r}")
        if min_class_samples <= 0:
            raise ValueError(f"min_class_samples must be positive, got {min_class_samples!r}")

        self.detector_names    = list(detector_names)
        self.prior_strength    = int(prior_strength)
        self.min_class_samples = int(min_class_samples)
        # Initialize with uniform global prior.
        self._global_weights: np.ndarray = np.ones(len(detector_names), dtype=np.float64)
        self._global_weights /= self._global_weights.sum()
        # Class-specific state, keyed by class name.
        self._class_stats: dict[str, ClassWeightStats] = {}

    # ── Prior (global) weights ────────────────────────────────────────────────

    def set_global_weights(self, weights: dict[str, float]) -> None:
        """Set the shared global weight prior.

        Keys not in `detector_names` are rejected; missing detectors
        default to 0 and the full vector is L1-renormalised.
        """
        unknown = set(weights) - set(self.detector_names)
        if unknown:
            raise ValueError(f"unknown detectors in weights: {sorted(unknown)!r}")
        v = np.array([weights.get(n, 0.0) for n in self.detector_names], dtype=np.float64)
        if np.any(v < 0.0):
            raise ValueError("global weights must be ≥ 0")
        total = float(v.sum())
        if total <= 0.0:
            raise ValueError("global weights sum to zero")
        self._global_weights = v / total

    @property
    def global_weights(self) -> dict[str, float]:
        return dict(zip(self.detector_names, self._global_weights.tolist()))

    # ── Per-class fit ─────────────────────────────────────────────────────────

    def fit_class(
        self,
        class_name: str,
        scores: np.ndarray,
        labels: np.ndarray,
    ) -> ClassWeightStats:
        """Learn shrunk weights for a satellite class.

        scores : shape (N, D)  detector outputs (same D ordering as detector_names)
        labels : shape (N,)    {0, 1} ground-truth labels
        """
        if scores.ndim != 2 or scores.shape[1] != len(self.detector_names):
            raise ValueError(
                f"scores must be (N, {len(self.detector_names)}), got {scores.shape}"
            )
        n = int(labels.shape[0])
        corrs = _detector_label_correlations(scores, labels)
        total = float(corrs.sum())
        if total > 0.0:
            mle = corrs / total
        else:
            # No usable signal — lean fully on global.
            mle = self._global_weights.copy()

        if n < self.min_class_samples:
            alpha = 0.0  # full global
            shrunk = self._global_weights.copy()
        else:
            alpha = float(n) / (n + self.prior_strength)
            shrunk = alpha * mle + (1.0 - alpha) * self._global_weights
            # Renormalise to guard against numerical drift
            s = float(shrunk.sum())
            if s > 0.0:
                shrunk = shrunk / s

        stats = ClassWeightStats(
            class_name=class_name,
            n_samples=n,
            shrinkage_alpha=alpha,
            weights=dict(zip(self.detector_names, shrunk.tolist())),
            mle_weights=dict(zip(self.detector_names, mle.tolist())),
            global_weights=self.global_weights,
        )
        self._class_stats[class_name] = stats
        return stats

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_weights(self, class_name: str) -> dict[str, float]:
        """Weights for a class, falling back to global if unknown."""
        stats = self._class_stats.get(class_name)
        if stats is None:
            return self.global_weights
        return dict(stats.weights)

    def class_stats(self, class_name: str) -> ClassWeightStats | None:
        return self._class_stats.get(class_name)

    def known_classes(self) -> list[str]:
        return sorted(self._class_stats.keys())

    def reset_class(self, class_name: str) -> None:
        self._class_stats.pop(class_name, None)


__all__ = [
    "DEFAULT_MIN_CLASS_SAMPLES",
    "DEFAULT_PRIOR_STRENGTH",
    "ClassWeightStats",
    "HierarchicalLLRWeights",
]
