"""DiscordDetector — Matrix Profile discord detection via z-normalized distances.

Role in the ensemble
--------------------
CUSUM / EWMA / Z-score detect statistical deviations (mean shifts, spikes).
TrendVelocity    detects onset acceleration.
THIS detector finds *shape discords* — subsequences that are dissimilar to
ANY other pattern seen in the channel's recent history.

Key insight
-----------
A "discord" in the Matrix Profile sense is a subsequence whose nearest neighbor
(most similar subsequence) is far away in z-normalized Euclidean distance.
A normal signal has most windows matching some other window closely.
An anomalous pattern that has never appeared before will have a high discord score.

Examples of anomalies this catches that statistics miss:
- A channel that drifts in a NEW shape (different curvature from all past drifts)
- A transient oscillation at a frequency not seen during calibration
- An unusual flat period in an otherwise oscillating channel
- A spike followed by an unusual recovery trajectory

Algorithm
---------
1. Use the last ``window`` residuals as the search space.
2. Query = last ``m`` residuals (most recent subsequence).
3. Compute z-normalized Euclidean distance from query to every position in the
   window (excluding a trivial-match exclusion zone of m//4 around the query).
4. discord_score = min distance to nearest neighbor.
   Low = normal (close match exists), High = discord (unusual pattern).
5. Reference distribution: mean/std of discord scores over recent history
   (calibrated from the same residual window).
6. Alarm: score > mean + threshold_sigma × std.

Implementation
--------------
Uses an FFT-based cross-correlation approach (O(n log n) per call, no numba).
No external dependencies beyond numpy.  Fast: ~0.35ms for n=300, m=20.

Shared API (stateless — mirrors VarianceDetector)
-------------------------------------------------
  det = DiscordDetector()
  result = det.detect(decomp.residuals, calibration)
  # result.detector_name == "matrix_profile"
"""

from __future__ import annotations

import numpy as np
import structlog

from aria.dsremo.core.models import DetectorResult, Severity
from aria.dsremo.detection.calibration import CalibrationState

logger = structlog.get_logger()


def _discord_score_last(T: np.ndarray, m: int) -> float:
    """Return the z-normalized Euclidean distance from the last m-length
    subsequence to its nearest neighbor in T (excluding trivial matches).

    This implements the Matrix Profile "discord" metric using FFT-based
    cross-correlation — no numba/STUMPY required.

    High return value = discord (unusual shape).
    Low return value  = normal (close match found in history).
    Returns 0.0 when there is insufficient data or a constant signal.
    """
    T = np.asarray(T, dtype=np.float64)
    n = len(T)
    L = n - m + 1  # number of subsequences
    if L < 2:
        return 0.0

    # ── Query: last m samples ─────────────────────────────────────────────
    Q = T[n - m:]
    mu_Q  = float(Q.mean())
    sig_Q = float(Q.std())
    if sig_Q < 1e-9:
        return 0.0  # constant query — cannot compute distance

    # ── Sliding-window mean and std for all L subsequences ────────────────
    pad  = np.concatenate(([0.0], T))
    c    = np.cumsum(pad)
    c2   = np.cumsum(pad ** 2)
    mu   = (c[m:] - c[:L]) / m          # shape (L,)
    m2   = (c2[m:] - c2[:L]) / m       # shape (L,)
    sig  = np.sqrt(np.maximum(0.0, m2 - mu ** 2))
    sig  = np.where(sig < 1e-9, 1.0, sig)  # treat constant subs as sig=1

    # ── FFT cross-correlation: raw_QT[i] = Σ_j Q[j] * T[i+j] ────────────
    sz     = 1 << int(np.ceil(np.log2(2 * n)))   # next power-of-2 padding
    raw_QT = np.fft.irfft(
        np.fft.rfft(T, n=sz) * np.fft.rfft(Q[::-1], n=sz),
        n=sz,
    )[m - 1: m - 1 + L]                           # shape (L,)

    # ── Z-normalized distance ─────────────────────────────────────────────
    # dist²[i] = 2m * (1 - (raw_QT[i] - m*mu_Q*mu[i]) / (m * sig_Q * sig[i]))
    denom = sig_Q * sig * m
    denom = np.where(denom < 1e-9, 1e-9, denom)
    inner = np.clip((raw_QT - m * mu_Q * mu) / denom, -1.0, 1.0)
    dist  = np.sqrt(np.maximum(0.0, 2.0 * m * (1.0 - inner)))   # shape (L,)

    # ── Exclusion zone: avoid trivial self-match ──────────────────────────
    ez     = max(1, m // 4)  # Yeh 2016 KDD §3.1: exclusion zone = m//4 (standard Matrix Profile convention)
    ez_lo  = max(0, L - 1 - ez)
    dist[ez_lo:] = np.inf

    valid = dist[dist < np.inf]
    return float(np.min(valid)) if len(valid) > 0 else 0.0


# P3-K: Check for stumpy availability at import time.
_STUMPY_AVAILABLE = False
try:
    import stumpy  # noqa: F401
    _STUMPY_AVAILABLE = True
except ImportError:
    pass


class DiscordDetector:
    """Matrix Profile discord detector.

    P3-K fix: When stumpy is available, uses stumpy.stump() for the initial
    matrix profile computation (O(n²) but MASS-optimized), providing
    numerically exact results.  Falls back to the FFT cross-correlation
    method (O(n log n)) when stumpy is not installed.

    Detects when the most recent m-sample window of STL residuals is unusual
    compared to all other m-sample windows in the recent history.

    Stateless: reference distribution derived from the residual window itself
    (mean/std of discord scores across the window — self-calibrating).
    """

    def __init__(
        self,
        m:                  int   = 20,    # ESTIMATE — 20-sample subsequence (Yeh 2016 KDD: m ~20-50 for physiological signals)
        window:             int   = 300,   # ESTIMATE — 300-sample look-back (~5 min at 1 Hz); Yeh 2016 §3: window ≥ 4m recommended
        threshold_sigma:    float = 3.0,   # ESTIMATE — 3σ discord threshold; Shewhart 1931 / common matrix-profile practice (Yeh 2016)
        min_window_factor:  int   = 4,     # Yeh 2016 KDD §3.1: exclusion zone = m//4; need at least 4m samples for meaningful MP
        use_stumpy:         bool  = True,  # P3-K: use stumpy when available
    ) -> None:
        """
        Args:
            m:                  Subsequence length.  Shorter = more sensitive to
                                brief transients; longer = catches extended patterns.
            window:             Number of recent residuals used as the search space.
                                Must be >= 4×m (enforced internally).
            threshold_sigma:    Alarm when discord_score > mean + k × std of
                                the profile values in the current window.
            min_window_factor:  Minimum ratio window/m.  Enforced at detect time.
        """
        self.m                 = m
        self.window            = max(window, min_window_factor * m + 1)
        self.threshold_sigma   = threshold_sigma
        self.min_window_factor = min_window_factor
        self.use_stumpy        = use_stumpy and _STUMPY_AVAILABLE

    # ── Detection ──────────────────────────────────────────────────────────

    def detect(
        self,
        residuals:          np.ndarray,
        calibration:        CalibrationState,
        discord_threshold:  float | None = None,   # per-channel override
    ) -> DetectorResult:
        """Score the latest residual pattern for discord anomaly.

        Args:
            residuals:         STL residual window (full, oldest → newest).
                               Uses only the last ``window`` entries.
            calibration:       CalibrationState for this channel.  Must be
                               calibrated (is_calibrated=True).
            discord_threshold: Per-channel override for threshold_sigma.

        Returns:
            DetectorResult with detector_name="matrix_profile".  Score ∈ [0, 1].
        """
        if not calibration.is_calibrated:
            return DetectorResult(
                detector_name="matrix_profile",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={"reason": "warming_up"},
            )

        thr_sigma = discord_threshold if discord_threshold is not None \
            else self.threshold_sigma

        # ── Extract working window ────────────────────────────────────────
        min_needed = self.min_window_factor * self.m + 1
        if len(residuals) < min_needed:
            return DetectorResult(
                detector_name="matrix_profile",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={
                    "reason":  "insufficient_data",
                    "n":       len(residuals),
                    "needed":  min_needed,
                },
            )

        w = residuals[-self.window:] if len(residuals) >= self.window else residuals

        if float(np.std(w)) < 1e-9:
            return DetectorResult(
                detector_name="matrix_profile",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={"reason": "constant_channel"},
            )

        # ── Discord score for the last subsequence ────────────────────────
        # P3-K: Use stumpy.stump when available for numerically exact results.
        if self.use_stumpy:
            try:
                mp = stumpy.stump(w, self.m)  # type: ignore[name-not-defined]
                discord_score = float(mp[-1, 0])  # nearest-neighbor distance for last subsequence
            except Exception:
                discord_score = _discord_score_last(w, self.m)
        else:
            discord_score = _discord_score_last(w, self.m)

        # ── Reference distribution: all discord scores in the window ──────
        # Compute scores for every position (sampled at step=m//2 for speed)
        step = max(1, self.m // 2)
        L    = len(w) - self.m + 1
        sample_positions = range(0, L - 1, step)   # exclude the last position
        ref_scores = []
        for i in sample_positions:
            # Roll the window so position i is the "last" query
            sub = w[: i + self.m]
            if len(sub) >= self.min_window_factor * self.m + 1:
                ref_scores.append(_discord_score_last(sub, self.m))

        if not ref_scores:
            # Fallback: use a single-point reference from calibration.ref_std
            ref_mean = max(float(calibration.ref_std), 1e-6)
            ref_std  = ref_mean * 0.5
        else:
            arr      = np.array(ref_scores, dtype=np.float64)
            ref_mean = float(np.mean(arr))
            ref_std  = max(float(np.std(arr)), 1e-6)

        threshold  = ref_mean + thr_sigma * ref_std
        z          = (discord_score - ref_mean) / ref_std
        ratio      = max(0.0, z / thr_sigma)
        score      = float(min(1.0, ratio))
        is_anomaly = discord_score > threshold

        severity = Severity.NOMINAL
        if is_anomaly:
            if z >= 3 * thr_sigma:
                severity = Severity.CRITICAL
            elif z >= 2 * thr_sigma:
                severity = Severity.WARNING
            else:
                severity = Severity.WATCH

        return DetectorResult(
            detector_name="matrix_profile",
            is_anomaly=is_anomaly,
            score=score,
            severity=severity,
            details={
                "discord_score": round(discord_score, 6),
                "threshold":     round(threshold, 6),
                "ref_mean":      round(ref_mean, 6),
                "ref_std":       round(ref_std, 6),
                "z_score":       round(z, 4),
            },
        )
