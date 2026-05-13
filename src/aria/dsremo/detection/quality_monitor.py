"""V3-Be2: Quality meta-monitor — monitors the quality field itself for anomalies.

The telemetry quality field (0.0–1.0) is normally used as a weight, but the
quality value itself can indicate sensor failures:
    - Stuck quality register: quality=1.0 for >500 consecutive readings
    - Sustained degradation: mean(quality) < 0.3 over last 100 readings
    - Sensor dropout: quality=0.0 for >10 consecutive readings

Reference: CCSDS 660.0-B-2 §7.3.2: quality indicator semantic definitions.
"""

from __future__ import annotations

import structlog

from aria.dsremo.core.models import DetectorResult, Severity

logger = structlog.get_logger()


class QualityMetaMonitor:
    """Monitors telemetry quality field for systematic sensor errors.

    Treats the quality metadata as its own signal channel and detects
    anomalous patterns that indicate sensor malfunction.
    """

    def __init__(
        self,
        stuck_threshold: int = 500,
        dropout_threshold: int = 10,
        degradation_window: int = 100,
        degradation_mean_threshold: float = 0.3,
    ) -> None:
        self._stuck_threshold = stuck_threshold
        self._dropout_threshold = dropout_threshold
        self._degradation_window = degradation_window
        self._degradation_mean_threshold = degradation_mean_threshold
        self._consecutive_perfect: dict[str, int] = {}
        self._consecutive_zero: dict[str, int] = {}
        self._quality_buffer: dict[str, list[float]] = {}

    def update(self, key: str, quality: float) -> DetectorResult | None:
        """Process one quality reading.  Returns anomaly if pattern detected.

        Args:
            key:     Channel key, e.g. "SAT-1:battery_voltage".
            quality: Quality field from TelemetryPoint (0.0–1.0).

        Returns:
            DetectorResult if an anomalous quality pattern is detected,
            None otherwise.
        """
        # Track consecutive extremes.
        if quality >= 0.999:
            self._consecutive_perfect[key] = self._consecutive_perfect.get(key, 0) + 1
            self._consecutive_zero[key] = 0
        elif quality <= 0.001:
            self._consecutive_zero[key] = self._consecutive_zero.get(key, 0) + 1
            self._consecutive_perfect[key] = 0
        else:
            self._consecutive_perfect[key] = 0
            self._consecutive_zero[key] = 0

        # Rolling quality buffer.
        buf = self._quality_buffer.setdefault(key, [])
        buf.append(quality)
        if len(buf) > self._degradation_window:
            buf.pop(0)

        # ── Check 1: Sensor dropout (CRITICAL) ───────────────────────
        n_zero = self._consecutive_zero.get(key, 0)
        if n_zero >= self._dropout_threshold:
            return DetectorResult(
                detector_name="quality_meta",
                is_anomaly=True,
                score=1.0,
                severity=Severity.CRITICAL,
                details={
                    "reason": "sensor_dropout",
                    "consecutive_zero": n_zero,
                },
            )

        # ── Check 2: Stuck quality register (WATCH) ──────────────────
        n_perfect = self._consecutive_perfect.get(key, 0)
        if n_perfect >= self._stuck_threshold:
            return DetectorResult(
                detector_name="quality_meta",
                is_anomaly=True,
                score=0.5,
                severity=Severity.WATCH,
                details={
                    "reason": "stuck_quality_register",
                    "consecutive_perfect": n_perfect,
                },
            )

        # ── Check 3: Sustained quality degradation (WARNING) ─────────
        if len(buf) >= self._degradation_window:
            mean_q = sum(buf) / len(buf)
            if mean_q < self._degradation_mean_threshold:
                score = min(
                    1.0,
                    (self._degradation_mean_threshold - mean_q)
                    / self._degradation_mean_threshold,
                )
                return DetectorResult(
                    detector_name="quality_meta",
                    is_anomaly=True,
                    score=score,
                    severity=Severity.WARNING,
                    details={
                        "reason": "sustained_quality_degradation",
                        "mean_quality": round(mean_q, 3),
                    },
                )

        return None

    def reset(self, key: str | None = None) -> None:
        """Clear state for one channel or all channels."""
        if key:
            self._consecutive_perfect.pop(key, None)
            self._consecutive_zero.pop(key, None)
            self._quality_buffer.pop(key, None)
        else:
            self._consecutive_perfect.clear()
            self._consecutive_zero.clear()
            self._quality_buffer.clear()
