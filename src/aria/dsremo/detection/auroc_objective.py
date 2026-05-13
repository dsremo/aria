"""V3-S1: AUROC objective for GRU / TCN autoencoder training.

The V3 audit (Singh panel §S-1) flagged that `AbstractMLDetector.fit()`
trains on reconstruction MSE and also early-stops on MSE — a *proxy*
for separation quality.  A model can reach excellent val-MSE on the
clean training distribution while still being useless at separating
real anomalies from noise.  Unknown how well the detector discriminates.

Fix (Singh 2020 §4): generate synthetic labeled val anomalies by
injecting controlled perturbations (spike / drift / step) into a clean
hold-out slice, score reconstruction MSE per window, and compute AUROC
against the {0,1} labels.  Use AUROC as the early-stopping objective.

This module stays pure-NumPy so it can be imported without torch.
`AbstractMLDetector.fit(..., use_auroc_objective=True)` plugs it into
the training loop.

References
  * Singh et al. 2020, "Anomaly Detection in the Time Domain", §4.
  * Hanley & McNeil 1982, Radiology 143 §2.2 — the AUROC-Wilcoxon
    identity used here (`auroc_from_scores`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# Per Singh 2020 §4.2: a 2% injection rate on a 200-sample val slice
# yields ~4 anomaly windows — enough for a stable AUROC estimate when
# combined with the class-1 expansion from window overlap.
DEFAULT_INJECTION_RATE = 0.02  # Singh 2020 §4.2 — rate that keeps class balance ≥ 1 %
DEFAULT_VAL_FRACTION   = 0.15  # Singh 2020 §4.1 — 10-20 % val split for small telemetry buffers
_SPIKE_SIGMA_MULT   = 5.0  # Singh 2020 §4.2 — 5σ spike guarantees visible class-1 anomaly
_DRIFT_SIGMA_MULT   = 3.0  # ESTIMATE — 3σ linear drift matches sensor-degradation scenario_injector intensity=0.4
_STEP_SIGMA_MULT    = 4.0  # ESTIMATE — 4σ step matches `spike` fault in scenario injector intensity=0.5
_DRIFT_LEN_FRACTION = 0.06  # ESTIMATE — drift occupies 6 % of val length; plenty to force reconstruction error
_STEP_LEN_FRACTION  = 0.04  # ESTIMATE — step occupies 4 % of val length


@dataclass(frozen=True)
class LabeledInjection:
    """Result of injecting synthetic anomalies into a clean residual slice."""

    residuals: np.ndarray          # shape (N,) post-injection values
    sample_labels: np.ndarray      # shape (N,) {0,1} — 1 where an anomaly was injected


def inject_labeled_anomalies(
    clean: np.ndarray,
    *,
    injection_rate: float = DEFAULT_INJECTION_RATE,
    rng: np.random.Generator | None = None,
) -> LabeledInjection:
    """Inject controlled anomalies (spike / drift / step) into a clean slice.

    The three fault shapes mirror `simulate/injector.py` scenarios without
    depending on the full simulator — sufficient for a self-supervised
    val-AUROC objective.  Returns (residuals, sample_labels) where
    sample_labels[i] == 1 means sample i is *inside* an injected anomaly.
    """
    if rng is None:
        rng = np.random.default_rng()
    if clean.ndim != 1:
        raise ValueError(f"clean must be 1-D, got shape {clean.shape}")
    if injection_rate <= 0.0 or injection_rate >= 0.5:
        raise ValueError(f"injection_rate must be in (0, 0.5), got {injection_rate!r}")

    n = len(clean)
    if n < 10:
        raise ValueError(f"clean slice too small for injection: {n}")

    out = clean.astype(np.float64, copy=True)
    labels = np.zeros(n, dtype=np.int8)

    sigma = float(out.std())
    if sigma == 0.0:
        sigma = 1.0  # degenerate but safe

    # Expected number of samples to perturb
    target = max(3, int(round(n * injection_rate)))

    # Bag of 3 shapes; choose uniformly at random until the target sample
    # count is met or exceeded.  Order-invariant.
    shapes = ["spike", "drift", "step"]
    attempts = 0
    while labels.sum() < target and attempts < 50:
        attempts += 1
        shape = rng.choice(shapes)
        if shape == "spike":
            # Single-sample perturbation of ±5σ.  Lands on an unlabeled slot.
            idx = int(rng.integers(0, n))
            if labels[idx]:
                continue
            sign = 1.0 if rng.random() < 0.5 else -1.0
            out[idx] += sign * _SPIKE_SIGMA_MULT * sigma
            labels[idx] = 1

        elif shape == "drift":
            # Linear drift of length ⌈drift_frac × n⌉, ramps up to ±3σ.
            length = max(3, int(round(_DRIFT_LEN_FRACTION * n)))
            start = int(rng.integers(0, max(1, n - length)))
            if np.any(labels[start: start + length]):
                continue
            ramp = np.linspace(0.0, _DRIFT_SIGMA_MULT * sigma, length)
            sign = 1.0 if rng.random() < 0.5 else -1.0
            out[start: start + length] += sign * ramp
            labels[start: start + length] = 1

        elif shape == "step":
            length = max(2, int(round(_STEP_LEN_FRACTION * n)))
            start = int(rng.integers(0, max(1, n - length)))
            if np.any(labels[start: start + length]):
                continue
            sign = 1.0 if rng.random() < 0.5 else -1.0
            out[start: start + length] += sign * _STEP_SIGMA_MULT * sigma
            labels[start: start + length] = 1

    return LabeledInjection(
        residuals=out.astype(np.float32),
        sample_labels=labels.astype(np.int8),
    )


def window_labels(sample_labels: np.ndarray, seq_length: int) -> np.ndarray:
    """Turn per-sample {0,1} labels into per-window labels.

    A window is labelled 1 iff ANY of its `seq_length` samples was an
    injected anomaly.  This matches how reconstruction MSE is scored
    per window in `AbstractMLDetector.fit` / `detect`.
    """
    if seq_length <= 0:
        raise ValueError(f"seq_length must be positive, got {seq_length!r}")
    n = len(sample_labels)
    n_windows = n - seq_length + 1
    if n_windows <= 0:
        return np.zeros((0,), dtype=np.int8)

    labels_i8 = sample_labels.astype(np.int8, copy=False)
    # Prefix-sum trick: any-1-in-window ⇔ (prefix[i+seq] - prefix[i]) > 0.
    prefix = np.concatenate(([0], np.cumsum(labels_i8)))
    windowed = (prefix[seq_length:] - prefix[:-seq_length]) > 0
    return windowed.astype(np.int8)


def auroc_from_scores(scores: np.ndarray, labels: np.ndarray) -> float:
    """Hanley-McNeil 1982 §2.2 Wilcoxon estimator of AUROC.

    scores  : shape (N,) predicted anomaly scores (higher = more anomalous)
    labels  : shape (N,) {0,1} ground-truth labels

    Returns a float in [0, 1].  Returns 0.5 when either class is empty
    (undefined, but 0.5 is the conservative "random" baseline that keeps
    the training-loop early-stopping code simple).
    """
    if scores.shape != labels.shape:
        raise ValueError(
            f"scores {scores.shape} and labels {labels.shape} must have the same shape"
        )
    if scores.ndim != 1:
        raise ValueError(f"scores and labels must be 1-D, got shape {scores.shape}")

    labels_bool = labels.astype(bool)
    n_pos = int(labels_bool.sum())
    n_neg = int(len(labels) - n_pos)
    if n_pos == 0 or n_neg == 0:
        return 0.5

    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty_like(order, dtype=np.float64)
    # Assign mean ranks to ties (Hanley-McNeil §2.2).
    sorted_scores = scores[order]
    i = 0
    while i < len(sorted_scores):
        j = i
        while j + 1 < len(sorted_scores) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        mean_rank = 0.5 * (i + j) + 1.0  # 1-indexed mean rank
        ranks[order[i: j + 1]] = mean_rank
        i = j + 1

    sum_ranks_pos = ranks[labels_bool].sum()
    auroc = (sum_ranks_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return float(auroc)


__all__ = [
    "DEFAULT_INJECTION_RATE",
    "DEFAULT_VAL_FRACTION",
    "LabeledInjection",
    "auroc_from_scores",
    "inject_labeled_anomalies",
    "window_labels",
]
