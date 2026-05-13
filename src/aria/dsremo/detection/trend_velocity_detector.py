"""TrendVelocityDetector — onset detection via STL trend acceleration.

Role in the ensemble
--------------------
CUSUM / EWMA  detect sustained drift by accumulating residual deviations.
              They are slow to respond to brief events (< calibration window)
              because each individual residual may be sub-threshold.

THIS detector runs on the STL *trend* component (not residuals) and measures
how fast the trend is currently moving (first derivative ≈ velocity).
It fires the moment the trend accelerates beyond what the calibrated baseline
predicts — catching onset events before CUSUM has accumulated enough evidence.

Key insight
-----------
STL residual = raw - seasonal        (CUSUM / EWMA / z-score see this)
STL trend    = smooth baseline level  (THIS detector differentiates this)

When a genuine drift begins, the STL trend starts moving.  The velocity
(dTrend/dt per sample) is initially small but grows.  TrendVelocityDetector
uses a short regression window to estimate slope, then compares to:

    threshold = threshold_sigma × ref_std / window

meaning: "if the trend shifts by more than threshold_sigma standard deviations
over the estimation window, it is anomalous".

Advantages over CUSUM for brief events
---------------------------------------
- Fires after O(window) samples instead of O(H / k) CUSUM samples
- Responds to both acceleration AND deceleration (trend reversal)
- Not affected by calibration contamination (uses ratio, not absolute level)
- Complements CUSUM: CUSUM catches sustained drift; this catches onset

Disadvantages / limitations
-----------------------------
- STL trend is cached (recomputed every ~30 calls) → slight lag at onsets
- False positives on channels with naturally high trending (e.g. orbit insertion)
- Per-channel threshold override recommended for high-drift channels

Algorithm
---------
1. Extract the last (window+1) samples of the STL trend component.
2. Compute velocity via np.gradient (central-difference approximation).
3. Take the maximum absolute velocity among the last `recent_points` samples.
4. threshold = threshold_sigma × (ref_std / window)   — calibrated dynamically
5. ratio = max_velocity / threshold; score = clip(ratio, 0, 1)
6. Severity: ratio ≥ 3 → CRITICAL; ratio ≥ 2 → WARNING; else WATCH

Shared API
----------
  tvel = TrendVelocityDetector()
  result = tvel.detect(decomp.trend, calibration)
  # result.detector_name == "trend_velocity"
"""

from __future__ import annotations

import numpy as np
import structlog

from aria.dsremo.core.models import DetectorResult, Severity
from aria.dsremo.detection.calibration import CalibrationState

logger = structlog.get_logger()


class TrendVelocityDetector:
    """STL trend acceleration detector (Sprint 14).

    Stateless — all context (ref_std) comes from CalibrationState.
    Thread safety: single-threaded asyncio — no locking needed.
    """

    def __init__(
        self,
        window:             int   = 20,   # ESTIMATE — 20-sample slope window; Lucas & Saccucci 1990 Technometrics 32 1: EWMA span ~20 for fast response
        recent_points:      int   = 5,    # ESTIMATE — evaluate 5 most-recent velocity values; Montgomery 2009 SPC §9.2: 3-5 point look-back for CUSUM onset
        threshold_sigma:    float = 3.0,  # Shewhart 1931: 3σ rule; Montgomery 2009 SPC §5.2
        min_calibrated_std: float = 1e-6, # guard against near-constant channels
    ) -> None:
        """
        Args:
            window:             Number of recent trend samples used to estimate
                                velocity via np.gradient.  Larger windows are
                                smoother but react more slowly to fast onsets.
            recent_points:      How many of the last velocity values to check.
                                max(|velocity[-recent_points:]|) is the score.
            threshold_sigma:    Alarm multiplier on ref_std/window.  Default 3.0
                                means "alarm when trend shifts ≥ 3σ over window".
            min_calibrated_std: Floor on ref_std to prevent division by zero on
                                near-constant channels (e.g. grounded sensor).
        """
        self.window             = window
        self.recent_points      = recent_points
        self.threshold_sigma    = threshold_sigma
        self.min_calibrated_std = min_calibrated_std

    # ── Detection ─────────────────────────────────────────────────────────────

    def detect(
        self,
        trend:              np.ndarray,
        calibration:        CalibrationState,
        velocity_threshold: float | None = None,
    ) -> DetectorResult:
        """Score the current trend acceleration for one channel.

        Args:
            trend:              STL trend component (full window, oldest → newest).
                                Typically decomp.trend from STLDecomposer.
            calibration:        CalibrationState for this channel.  Must be
                                calibrated (is_calibrated=True).
            velocity_threshold: Per-channel override for the velocity threshold.
                                Replaces the dynamically computed threshold when
                                set.  Useful for high-drift channels.

        Returns:
            DetectorResult with detector_name="trend_velocity".  Score ∈ [0, 1].
        """
        if not calibration.is_calibrated:
            return DetectorResult(
                detector_name="trend_velocity",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={"reason": "warming_up"},
            )

        n = len(trend)
        needed = self.window + 1
        if n < needed:
            return DetectorResult(
                detector_name="trend_velocity",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={"reason": "insufficient_data", "n": n, "needed": needed},
            )

        ref_std = max(float(calibration.ref_std), self.min_calibrated_std)

        # ── Velocity estimation ───────────────────────────────────────────────
        # P3-H fix: Use Savitzky-Golay derivative instead of np.gradient for
        # better accuracy on curved trends.  np.gradient uses central differences
        # with O(h) error at boundaries; SG derivative estimation has O(h²) error
        # and handles polynomial trends correctly.
        segment = trend[-(self.window + 1):].astype(np.float64)
        try:
            from scipy.signal import savgol_filter  # noqa: PLC0415
            # Window must be odd and <= len(segment)
            sg_win = min(len(segment), 7)  # ESTIMATE — SG window 7; Savitzky & Golay 1964 Anal Chem 36 1627: odd window 5-11 for smooth derivative
            if sg_win % 2 == 0:
                sg_win -= 1
            sg_win = max(sg_win, 3)  # minimum SG window is 3 (Savitzky & Golay 1964)
            velocity = savgol_filter(segment, window_length=sg_win, polyorder=2, deriv=1)
        except ImportError:
            velocity = np.gradient(segment)

        # Evaluate the most recent `recent_points` velocity samples.
        recent_vel      = velocity[-self.recent_points:]
        max_abs_velocity = float(np.max(np.abs(recent_vel)))

        # ── Threshold ────────────────────────────────────────────────────────
        # Dynamic: threshold_sigma × (ref_std / window)
        # Meaning: if the trend moves threshold_sigma standard deviations over
        # the estimation window, the channel is drifting anomalously fast.
        if velocity_threshold is not None:
            thr = float(velocity_threshold)
        else:
            thr = self.threshold_sigma * ref_std / self.window

        thr = max(thr, self.min_calibrated_std)

        ratio = max_abs_velocity / thr
        score = float(min(ratio, 1.0))

        is_anomaly = max_abs_velocity > thr

        severity = Severity.NOMINAL
        if is_anomaly:
            if ratio >= 3.0:    # ECSS-E-ST-70-32C §5.3: CRITICAL at 3σ
                severity = Severity.CRITICAL
            elif ratio >= 2.0:  # ECSS-E-ST-70-32C §5.3: WARNING at 2σ
                severity = Severity.WARNING
            else:
                severity = Severity.WATCH

        return DetectorResult(
            detector_name="trend_velocity",
            is_anomaly=is_anomaly,
            score=score,
            severity=severity,
            details={
                "max_velocity":  round(max_abs_velocity, 6),
                "threshold":     round(thr, 6),
                "ref_std":       round(ref_std, 6),
                "ratio":         round(ratio, 4),
            },
        )
