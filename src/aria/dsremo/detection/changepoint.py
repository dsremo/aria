"""Change-point detector — structural breaks in STL residuals via PELT.

Uses the PELT (Pruned Exact Linear Time) algorithm via the `ruptures` library.
Detects moments where the statistical properties of the RESIDUAL signal change:
  - Mean shift in residuals  (sensor failure, mode change that STL didn't absorb)
  - Variance shift           (vibration onset, noise increase)
  - Trend break in residuals (degradation onset — acceleration of drift)

Running on STL residuals instead of raw telemetry means eclipse transitions
(which live in the seasonal component) no longer generate changepoints.

The key advantage: catches the *moment* a fault begins, not just that
values are currently abnormal. "Something changed at T=14:32:07" is
more useful than "values are high."
"""

from __future__ import annotations

import numpy as np
import ruptures
import structlog

from aria.dsremo.core.models import DetectorResult, Severity

logger = structlog.get_logger()


class ChangePointDetector:
    """Detects abrupt behavioral changes in telemetry parameters."""

    def __init__(
        self,
        penalty: float = 3.0,         # ESTIMATE — BIC penalty; Killick 2012 JASA 107 1590: pen ≈ 2log(n)
        min_segment_size: int = 30,   # ESTIMATE — 30-sample min segment (≈30 s at 1 Hz)
        model: str = "rbf",           # "rbf" for mean+variance, "l2" for mean only
        lookback: int = 300,          # ESTIMATE — 5-min lookback at 1 Hz (Killick 2012 PELT window)
    ):
        self.penalty = penalty
        self.min_segment_size = min_segment_size
        self.model = model
        self.lookback = lookback

    def detect(self, values: np.ndarray, parameter: str = "") -> DetectorResult:
        """Analyze a window of STL residuals for structural change points.

        Args:
            values:    1D array of STL residuals, oldest → newest.
                       Caller passes residuals (NOT raw telemetry values).
            parameter: Channel name for log context only.
        """
        if len(values) < self.min_segment_size * 2:
            return DetectorResult(
                detector_name="changepoint",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={"reason": "insufficient_data", "length": len(values)},
            )

        window = values[-self.lookback:] if len(values) > self.lookback else values

        try:
            algo = ruptures.Pelt(model=self.model, min_size=self.min_segment_size)
            algo.fit(window.reshape(-1, 1))
            change_points = algo.predict(pen=self.penalty)
        except Exception as e:
            logger.warning("changepoint_detection_error", error=str(e), parameter=parameter)
            return DetectorResult(
                detector_name="changepoint",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={"error": str(e)},
            )

        # Remove the trailing point (ruptures always includes len(signal))
        real_cps = [cp for cp in change_points if cp < len(window)]

        if not real_cps:
            return DetectorResult(
                detector_name="changepoint",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={"change_points": [], "segment_count": 1},
            )

        # Score based on recency and magnitude of change points
        score, severity, details = self._score_change_points(window, real_cps)

        return DetectorResult(
            detector_name="changepoint",
            is_anomaly=score > 0.3,
            score=score,
            severity=severity,
            details=details,
        )

    def _score_change_points(
        self, window: np.ndarray, change_points: list[int]
    ) -> tuple[float, Severity, dict]:
        """Score change points by recency and magnitude."""
        n = len(window)
        total_score = 0.0
        cp_details = []

        for cp in change_points:
            # Recency weight: change points near the end of the window matter more
            recency = cp / n  # 0 = old, 1 = recent

            # Magnitude: how different are the segments before and after
            before = window[max(0, cp - self.min_segment_size):cp]
            after = window[cp:min(n, cp + self.min_segment_size)]

            if len(before) < 5 or len(after) < 5:
                continue

            mean_shift = abs(np.mean(after) - np.mean(before))
            std_before = np.std(before) if np.std(before) > 0 else 1e-10
            normalized_shift = mean_shift / std_before

            # Variance change
            var_ratio = np.var(after) / max(np.var(before), 1e-10)

            # Combined score for this change point
            cp_score = min(1.0, (normalized_shift * 0.3 + recency * 0.4 + min(var_ratio, 3) / 3 * 0.3))
            total_score = max(total_score, cp_score)

            cp_details.append({
                "index": int(cp),
                "recency": round(recency, 3),
                "mean_shift": round(float(mean_shift), 4),
                "normalized_shift": round(float(normalized_shift), 4),
                "variance_ratio": round(float(var_ratio), 4),
                "score": round(float(cp_score), 4),
            })

        # Severity
        if total_score >= 0.8:
            severity = Severity.CRITICAL
        elif total_score >= 0.5:
            severity = Severity.WARNING
        elif total_score >= 0.3:
            severity = Severity.WATCH
        else:
            severity = Severity.NOMINAL

        return float(total_score), severity, {
            "change_points": cp_details,
            "segment_count": len(change_points) + 1,
        }
