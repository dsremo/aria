"""V3-H3: Isotonic-regression ensemble-score calibration via PAVA.

Heckerman panel §H-3 in the V3 audit: the existing Platt scaling maps
ensemble scores to probabilities via `P = σ(A·score + B)`.  The sigmoid
shape is wrong for ensemble outputs that are already a weighted sum of
[0, 1] detector scores — the calibration curve is typically concave or
piecewise linear.  Platt under-estimates anomaly probability in the
most decision-relevant 0.3–0.5 range.

Fix (Zadrozny & Elkan 2002 KDD §3): isotonic regression makes no
parametric assumption and fits any monotone non-decreasing curve via
Pool Adjacent Violators (PAVA).  We bootstrap the calibrator from
synthetic injections (V3-S1 `inject_labeled_anomalies`) on nominal
historical residuals; it is refit monthly as real operator feedback
accumulates.

This module is pure NumPy — no sklearn dependency.

Reference
  * Zadrozny & Elkan 2002 ACM KDD §3 — isotonic vs Platt comparison.
  * Guo et al. 2017 ICML — Expected Calibration Error (ECE) metric.
  * Barlow, Bartholomew, Bremner, Brunk 1972 "Statistical Inference
    under Order Restrictions" §1.2 — original PAVA.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


DEFAULT_ECE_BINS = 10   # Guo 2017 ECE §4.1 — 10-bin reliability plot is the community standard
DEFAULT_ECE_TARGET = 0.05  # Zadrozny & Elkan 2002 §4 accept region — ECE < 0.05 is "well-calibrated"
_MIN_CALIBRATION_SAMPLES = 30  # ESTIMATE — ≥30 (score, label) pairs for a reliable PAVA fit at 10 bins


@dataclass(frozen=True)
class IsotonicCalibrator:
    """PAVA-fitted isotonic calibrator.

    `x_boundaries` and `y_values` describe a step function (monotone
    non-decreasing in y): for each queried score, find the right-most
    boundary ≤ score and return the associated y.  Equivalent to
    linear interpolation with NEAREST behaviour on ties.
    """

    x_boundaries: np.ndarray   # shape (M,) sorted
    y_values:     np.ndarray   # shape (M,)
    n_fit:        int
    ece:          float
    bins:         int

    def predict(self, scores: np.ndarray) -> np.ndarray:
        """Return calibrated probabilities for the given raw ensemble scores."""
        s = np.asarray(scores, dtype=np.float64)
        # np.interp: linear interpolation between (x_boundaries, y_values).
        # For scores outside the fitted range, clamps to edge values — the
        # desirable behaviour for calibration (never extrapolate).
        return np.clip(
            np.interp(s, self.x_boundaries, self.y_values),
            0.0, 1.0,
        )


def pav_fit(scores: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pool Adjacent Violators monotone-non-decreasing regression.

    scores : shape (N,)
    labels : shape (N,) {0, 1}

    Returns (x_boundaries, y_values).  The returned step function
    maps score → calibrated probability; ties in scores are collapsed
    to a single bin using their mean label.

    Reference: Barlow et al. 1972 §1.2 (PAVA).
    """
    if scores.ndim != 1 or labels.ndim != 1:
        raise ValueError(
            f"scores and labels must be 1-D, got {scores.shape=} {labels.shape=}"
        )
    if scores.shape != labels.shape:
        raise ValueError("scores and labels shape mismatch")
    if scores.size == 0:
        raise ValueError("empty scores/labels")

    order = np.argsort(scores, kind="mergesort")
    xs = scores[order].astype(np.float64)
    ys = labels[order].astype(np.float64)

    # Collapse ties in x: replace each tied run with the mean y.
    #
    # np.unique preserves order because xs is already sorted.
    unique_x, first_idx = np.unique(xs, return_index=True)
    grouped_y = np.zeros_like(unique_x)
    counts = np.zeros_like(unique_x, dtype=np.int64)
    for i in range(len(unique_x)):
        start = first_idx[i]
        end = first_idx[i + 1] if i + 1 < len(first_idx) else len(xs)
        grouped_y[i] = ys[start: end].mean()
        counts[i] = end - start

    # PAVA: left-to-right sweep, merging adjacent violators by weighted mean.
    y_out     = grouped_y.tolist()
    w_out     = counts.tolist()
    stack_x   = unique_x.tolist()
    i = 1
    while i < len(y_out):
        if y_out[i] < y_out[i - 1]:
            # Merge i with i-1
            new_w = w_out[i - 1] + w_out[i]
            new_y = (y_out[i - 1] * w_out[i - 1] + y_out[i] * w_out[i]) / new_w
            y_out[i - 1] = new_y
            w_out[i - 1] = new_w
            # Keep the LEFT x-boundary; drop stack_x[i]
            del y_out[i]
            del w_out[i]
            del stack_x[i]
            # Step back to recheck the new left neighbour
            if i > 1:
                i -= 1
        else:
            i += 1

    return np.asarray(stack_x, dtype=np.float64), np.asarray(y_out, dtype=np.float64)


def expected_calibration_error(
    calibrator: IsotonicCalibrator,
    scores: np.ndarray,
    labels: np.ndarray,
    n_bins: int = DEFAULT_ECE_BINS,
) -> float:
    """Guo et al. 2017 ICML §4.1 ECE over equal-width bins of [0, 1]."""
    s = np.asarray(scores, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    p = calibrator.predict(s)
    n = p.size
    if n == 0:
        return 0.0
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for b in range(n_bins):
        lo, hi = edges[b], edges[b + 1]
        mask = (p >= lo) & (p < hi if b + 1 < n_bins else p <= hi)
        if not mask.any():
            continue
        bin_acc = y[mask].mean()
        bin_conf = p[mask].mean()
        ece += (mask.sum() / n) * abs(bin_acc - bin_conf)
    return float(ece)


def fit_isotonic_calibrator(
    scores: np.ndarray,
    labels: np.ndarray,
    *,
    ece_bins: int = DEFAULT_ECE_BINS,
) -> IsotonicCalibrator:
    """Fit an isotonic calibrator on (score, label) pairs + report ECE."""
    scores = np.asarray(scores, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int8)
    if scores.size < _MIN_CALIBRATION_SAMPLES:
        raise ValueError(
            f"need ≥{_MIN_CALIBRATION_SAMPLES} samples for PAVA fit, "
            f"got {scores.size}"
        )
    x_b, y_v = pav_fit(scores, labels)
    # PAVA produces monotone-non-decreasing ys by construction.
    calib = IsotonicCalibrator(
        x_boundaries=x_b,
        y_values=y_v,
        n_fit=int(scores.size),
        ece=0.0,
        bins=int(ece_bins),
    )
    # Compute ECE on the fit set for a diagnostic; caller should refit on
    # held-out data for an honest out-of-sample ECE.
    ece = expected_calibration_error(calib, scores, labels, n_bins=ece_bins)
    # Dataclass is frozen — recreate with the ECE stamped in.
    return IsotonicCalibrator(
        x_boundaries=calib.x_boundaries,
        y_values=calib.y_values,
        n_fit=calib.n_fit,
        ece=ece,
        bins=calib.bins,
    )


def bootstrap_from_injection(
    clean_scores: np.ndarray,
    seed: int | None = None,
    injection_rate: float = 0.15,
) -> IsotonicCalibrator:
    """Bootstrap a calibrator from nominal scores via synthetic injection.

    Helpful when no labelled operator feedback exists yet: treat the
    clean-stream scores as class-0 samples, perturb `injection_rate` of
    them by +0.3 (pushing them into the "anomalous" region), label the
    perturbed entries 1.  PAVA then learns the raw → calibrated mapping.

    Returns an IsotonicCalibrator ready for `predict()`.
    """
    rng = np.random.default_rng(seed) if seed is not None else np.random.default_rng()
    s = np.asarray(clean_scores, dtype=np.float64).ravel()
    if s.size < _MIN_CALIBRATION_SAMPLES:
        raise ValueError(
            f"need ≥{_MIN_CALIBRATION_SAMPLES} clean scores, got {s.size}"
        )
    if not 0.0 < injection_rate < 1.0:
        raise ValueError(f"injection_rate must be in (0, 1), got {injection_rate!r}")
    labels = np.zeros(s.size, dtype=np.int8)
    n_pos = max(1, int(s.size * injection_rate))
    pos_idx = rng.choice(s.size, size=n_pos, replace=False)
    s = s.copy()
    s[pos_idx] = np.clip(s[pos_idx] + 0.3, 0.0, 1.0)  # ESTIMATE — +0.3 score bump matches median (WARN − NOMINAL) ensemble delta
    labels[pos_idx] = 1
    return fit_isotonic_calibrator(s, labels)


__all__ = [
    "DEFAULT_ECE_BINS",
    "DEFAULT_ECE_TARGET",
    "IsotonicCalibrator",
    "bootstrap_from_injection",
    "expected_calibration_error",
    "fit_isotonic_calibrator",
    "pav_fit",
]
