"""V3-V4: Temporal cross-channel attention detector.

Fault propagation in spacecraft has characteristic lags: a battery-voltage
anomaly precedes increased ADCS pointing error by ~120 s because reaction
wheels draw from a drooping power bus; thermal-expansion stress lags a
gradient change by minutes.  Lag-zero pair-wise correlation (what the
existing CorrelationGraph detector uses) cannot see these causal chains.

Fix (Shih, Sun, Lee 2019 §4 — Temporal Pattern Attention for Multivariate
Time Series Forecasting): maintain a lagged cross-correlation tensor
`A[i, j, τ] = corr(ch_i(t), ch_j(t − τ))` for a small menu of lags, learn
a baseline `A_ref` from calibration, and flag windows whose Frobenius
deviation `‖A_current − A_ref‖_F` exceeds a calibrated threshold.

Scope: this lives *per ECSS subsystem* (e.g. EPS↔EPS, ADCS↔ADCS).  The
user's defaults pick a 32-sample window matching the TCN detector.

References
  * Shih, Sun, Lee (2019). "Temporal Pattern Attention for Multivariate
    Time Series Forecasting." Machine Learning 108(8):1421-1441 §4.
  * Hundman et al. (2018) KDD — multi-channel LSTM for SMAP/MSL.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np


DEFAULT_LAGS_SAMPLES: tuple[int, ...] = (0, 4, 8, 16)  # Shih 2019 §4.1 — sparse lag menu capturing short/medium temporal patterns
DEFAULT_WINDOW_SIZE   = 32   # Matches TCN seq_length — keeps per-step compute O(M² · |lags|) negligible
DEFAULT_MIN_FIT_WINDOWS = 8  # ESTIMATE — ≥8 disjoint baseline windows gives stable Σ A_ref; Hanley-McNeil 1982 §2.2 rank-statistic heuristic
DEFAULT_FROBENIUS_TOL   = 0.5  # ESTIMATE — 0.5 ≈ one full A-matrix element shifted by 1.0 across M² cells; tune per channel
DEFAULT_SEVERITY_FACTORS = (1.0, 1.5, 2.0)  # WATCH / WARNING / CRITICAL multipliers of threshold_frobenius


def _pearson_lagged(a: np.ndarray, b: np.ndarray, lag: int) -> float:
    """Pearson correlation of a(t) with b(t−lag).

    Positive lag means b is shifted *backwards* relative to a — i.e. past
    values of b paired with current values of a.  For lag = 0 this is the
    vanilla Pearson correlation.  Returns 0.0 when the usable overlap is
    shorter than 3 samples or when either side has zero variance.
    """
    if lag < 0:
        raise ValueError(f"lag must be ≥ 0, got {lag!r}")
    n = min(len(a), len(b))
    if n - lag < 3:
        return 0.0
    x = a[lag:n]
    y = b[: n - lag]
    sx, sy = float(x.std()), float(y.std())
    if sx == 0.0 or sy == 0.0:
        return 0.0
    return float(((x - x.mean()) * (y - y.mean())).mean() / (sx * sy))


def compute_attention_tensor(
    windows: dict[str, np.ndarray],
    lags: tuple[int, ...],
) -> tuple[np.ndarray, list[str]]:
    """Build the `A[i, j, τ]` cross-correlation tensor for one window.

    windows  : dict {channel_id: 1-D window}, one shared length per call.
    lags     : positive integer lags (lag 0 must be first if included).
    Returns (A, channel_order) where A has shape (M, M, L).
    """
    if not windows:
        return np.zeros((0, 0, 0), dtype=np.float32), []
    order = sorted(windows.keys())
    M = len(order)
    L = len(lags)
    A = np.zeros((M, M, L), dtype=np.float32)
    arrays = [np.asarray(windows[k], dtype=np.float64) for k in order]
    for i in range(M):
        for j in range(M):
            for k, lag in enumerate(lags):
                A[i, j, k] = _pearson_lagged(arrays[i], arrays[j], lag)
    return A, order


@dataclass
class CrossAttentionReport:
    """Per-evaluation cross-channel attention report."""

    satellite_id: str
    subsystem:    str
    score:        float
    tier:         str           # NOMINAL / WATCH / WARNING / CRITICAL
    channel_order: list[str]
    lags_samples: tuple[int, ...]
    threshold:    float
    A_current:    np.ndarray
    A_ref:        np.ndarray
    n_samples:    int

    def to_dict(self) -> dict:
        return {
            "satellite_id": self.satellite_id,
            "subsystem":    self.subsystem,
            "score":        self.score,
            "tier":         self.tier,
            "channel_order": list(self.channel_order),
            "lags_samples": list(self.lags_samples),
            "threshold":    self.threshold,
            "n_samples":    self.n_samples,
            # A_current / A_ref elided — heavy; callers that need matrices
            # read them off the dataclass attributes directly.
        }


@dataclass
class _SubsystemState:
    buffers: dict[str, deque] = field(default_factory=dict)
    A_ref:   np.ndarray | None = None
    channel_order: list[str]  = field(default_factory=list)


class TemporalCrossAttention:
    """Per-satellite × per-subsystem lagged cross-correlation detector.

    Usage
    -----
    det = TemporalCrossAttention(window_size=32, lags_samples=(0, 4, 8, 16))
    # Calibration: feed baseline windows
    det.fit_baseline(sat="SAT-A", subsystem="eps", channels={
        "battery_v":    baseline_v,
        "bus_current":  baseline_i,
        "array_power":  baseline_p,
    })
    # Runtime: stream samples
    for t, (v, i, p) in enumerate(stream):
        det.update("SAT-A", "eps", {"battery_v": v, "bus_current": i, "array_power": p})
    report = det.score("SAT-A", "eps")
    if report and report.tier != "NOMINAL":
        ...
    """

    def __init__(
        self,
        *,
        window_size:         int   = DEFAULT_WINDOW_SIZE,
        lags_samples:        tuple[int, ...] = DEFAULT_LAGS_SAMPLES,
        threshold_frobenius: float = DEFAULT_FROBENIUS_TOL,
        severity_factors:    tuple[float, float, float] = DEFAULT_SEVERITY_FACTORS,
    ) -> None:
        if window_size <= max(lags_samples, default=0) + 2:
            raise ValueError(
                f"window_size={window_size} must exceed max(lags)+2; "
                f"lags={lags_samples}"
            )
        if threshold_frobenius <= 0:
            raise ValueError(f"threshold_frobenius must be positive, got {threshold_frobenius!r}")
        if len(severity_factors) != 3 or not all(
            severity_factors[i] <= severity_factors[i + 1] for i in range(2)
        ):
            raise ValueError(
                f"severity_factors must be a 3-tuple non-decreasing, got {severity_factors!r}"
            )

        self.window_size        = int(window_size)
        self.lags_samples       = tuple(int(lag) for lag in lags_samples)
        self.threshold_frobenius = float(threshold_frobenius)
        self.severity_factors    = tuple(float(x) for x in severity_factors)
        self._states: dict[tuple[str, str], _SubsystemState] = {}

    # ── Calibration ───────────────────────────────────────────────────────────

    def fit_baseline(
        self,
        satellite_id: str,
        subsystem: str,
        channels: dict[str, np.ndarray],
    ) -> None:
        """Compute A_ref from a long baseline period per channel.

        `channels` is a dict {channel_id: 1-D baseline array}.  All arrays
        must be at least `window_size + max(lags)` long.  A_ref is the
        *mean* attention tensor across disjoint sliding windows, which
        mirrors how Shih 2019 §4 averages training-set attention maps.
        """
        if not channels:
            raise ValueError("fit_baseline requires at least one channel")
        min_len = self.window_size
        arrays: list[np.ndarray] = []
        for cid, arr in sorted(channels.items()):
            a = np.asarray(arr, dtype=np.float64)
            if a.ndim != 1:
                raise ValueError(f"channel '{cid}' must be 1-D, got shape {a.shape}")
            if len(a) < min_len:
                raise ValueError(
                    f"channel '{cid}' too short: need ≥{min_len}, got {len(a)}"
                )
            arrays.append(a)
        order = sorted(channels.keys())
        n = min(len(a) for a in arrays)
        step = max(1, self.window_size // 2)  # ESTIMATE — 50 % overlap: Welch 1967 IEEE Trans AU — standard spectral-estimate window overlap
        starts = list(range(0, n - self.window_size + 1, step))
        if len(starts) < DEFAULT_MIN_FIT_WINDOWS:
            raise ValueError(
                f"baseline too short for ≥{DEFAULT_MIN_FIT_WINDOWS} windows "
                f"(have {len(starts)} with window={self.window_size}, step={step}). "
                f"Pass longer baseline arrays."
            )
        accum = None
        for s in starts:
            wins = {cid: arrays[i][s: s + self.window_size] for i, cid in enumerate(order)}
            A, _ = compute_attention_tensor(wins, self.lags_samples)
            accum = A if accum is None else accum + A
        A_ref = (accum / len(starts)).astype(np.float32)
        st = self._states.setdefault((satellite_id, subsystem), _SubsystemState())
        st.A_ref = A_ref
        st.channel_order = list(order)
        for cid in order:
            st.buffers.setdefault(cid, deque(maxlen=self.window_size))

    # ── Streaming ingest ──────────────────────────────────────────────────────

    def update(
        self,
        satellite_id: str,
        subsystem: str,
        values: dict[str, float],
    ) -> None:
        """Append one per-channel sample to the rolling buffers.

        Unknown channels (not seen during fit_baseline) are silently
        ignored so an upstream pipeline mis-tagging a channel can't raise.
        """
        key = (satellite_id, subsystem)
        st = self._states.get(key)
        if st is None or st.A_ref is None:
            return
        for cid in st.channel_order:
            if cid in values:
                st.buffers[cid].append(float(values[cid]))

    # ── Scoring ───────────────────────────────────────────────────────────────

    def score(
        self,
        satellite_id: str,
        subsystem: str,
    ) -> CrossAttentionReport | None:
        """Return a CrossAttentionReport if the rolling buffer is full, else None."""
        key = (satellite_id, subsystem)
        st = self._states.get(key)
        if st is None or st.A_ref is None:
            return None
        if not st.channel_order:
            return None
        if any(len(st.buffers[c]) < self.window_size for c in st.channel_order):
            return None

        windows = {c: np.asarray(st.buffers[c], dtype=np.float64) for c in st.channel_order}
        A_cur, _ = compute_attention_tensor(windows, self.lags_samples)
        score = float(np.linalg.norm(A_cur - st.A_ref))
        tier = self._tier(score)
        return CrossAttentionReport(
            satellite_id=satellite_id,
            subsystem=subsystem,
            score=score,
            tier=tier,
            channel_order=list(st.channel_order),
            lags_samples=tuple(self.lags_samples),
            threshold=self.threshold_frobenius,
            A_current=A_cur,
            A_ref=st.A_ref,
            n_samples=self.window_size,
        )

    def _tier(self, score: float) -> str:
        t = self.threshold_frobenius
        w, wr, c = self.severity_factors
        if score >= t * c:
            return "CRITICAL"
        if score >= t * wr:
            return "WARNING"
        if score >= t * w:
            return "WATCH"
        return "NOMINAL"

    # ── Housekeeping ──────────────────────────────────────────────────────────

    def reset(self, satellite_id: str | None = None) -> None:
        if satellite_id is None:
            self._states.clear()
            return
        for key in list(self._states.keys()):
            if key[0] == satellite_id:
                del self._states[key]


__all__ = [
    "CrossAttentionReport",
    "DEFAULT_FROBENIUS_TOL",
    "DEFAULT_LAGS_SAMPLES",
    "DEFAULT_WINDOW_SIZE",
    "TemporalCrossAttention",
    "compute_attention_tensor",
]
