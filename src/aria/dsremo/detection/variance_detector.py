"""VarianceDetector — detects anomalous variance inflation in STL residuals.

Role in the ensemble (post-STL architecture):
    CUSUM / EWMA   handle drift and level shifts (mean changes).
    StatisticalDetector handles single-point spikes (z-score on residuals).
    THIS detector handles VARIANCE SPIKES — when residual scatter doubles or
    triples while the mean stays near zero.

Motivation (CATS dataset, ESA Solenix, Zenodo 8338435):
    Channel ced1 has a continuous sinusoidal oscillation.  Normal segments:
    σ_residual ≈ 137 ADU.  Anomaly segments: σ_residual ≈ 311 ADU (2.27×).
    The mean difference is only 0.2σ — invisible to z-score, CUSUM, EWMA.
    A variance ratio of 2.27× is highly significant and reliably detectable.

Algorithm:
    1. Take the last `window` residuals (default 30).
    2. Compute their std (rolling_std).
    3. Compare to calibration.ref_std (the baseline σ established during warmup).
    4. ratio = rolling_std / max(ref_std, 1e-6)
    5. If ratio > variance_z_threshold → anomaly.

Why stateless:
    ref_std comes from CalibrationState (already stateful, persisted to DB).
    This detector just reads it — no additional state needed, same pattern
    as StatisticalDetector.
"""

from __future__ import annotations

import numpy as np

from aria.dsremo.core.models import DetectorResult, Severity
from aria.dsremo.detection.calibration import CalibrationState


class VarianceDetector:
    """Variance-ratio spike detector.  Stateless — context from calibration."""

    def __init__(
        self,
        variance_z_threshold: float = 2.5,  # ESTIMATE — 2.5× ratio catches CATS-type doubling (ESA Solenix Zenodo 8338435)
        window: int = 30,                   # ESTIMATE — 30-sample rolling window (≈30 s at 1 Hz)
    ) -> None:
        """
        Args:
            variance_z_threshold: Alarm when rolling_std / ref_std exceeds this.
                                  Default 2.5 catches CATS-type doubling (ratio 2.27×)
                                  while leaving margin above normal noise.
            window:               Number of recent residuals to compute rolling_std.
                                  Default 30 (≈30 s at 1Hz, ≈30 min at 1-min data).
        """
        self.variance_z_threshold = variance_z_threshold
        self.window = window

    def detect(
        self,
        residuals: np.ndarray,
        calibration: CalibrationState,
        variance_z_threshold: float | None = None,
    ) -> DetectorResult:
        """Evaluate residual variance ratio for one channel.

        Args:
            residuals:            Full STL residual window (oldest → newest).
                                  Uses only the last `window` entries.
            calibration:          CalibrationState for this channel.  Must be
                                  calibrated (is_calibrated=True) to have a
                                  meaningful ref_std.
            variance_z_threshold: Per-channel override (from channel_config).
                                  Falls back to self.variance_z_threshold if None.

        Returns:
            DetectorResult from the "variance" detector.
        """
        threshold = variance_z_threshold if variance_z_threshold is not None \
            else self.variance_z_threshold

        # Guard: calibration must be complete for a baseline ref_std.
        if not calibration.is_calibrated:
            return DetectorResult(
                detector_name="variance",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={"reason": "warming_up"},
            )

        ref_std = calibration.ref_std
        # Guard: near-zero ref_std means the channel is nearly constant —
        # handled by StatisticalDetector's constant-signal guard.
        if ref_std < 1e-9:
            return DetectorResult(
                detector_name="variance",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={"reason": "constant_channel", "ref_std": float(ref_std)},
            )

        # Use only the last `window` residuals.
        recent = residuals[-self.window:] if len(residuals) >= self.window \
            else residuals

        min_samples = max(2, self.window // 2)
        if len(recent) < min_samples:
            return DetectorResult(
                detector_name="variance",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={"reason": "insufficient_data", "n": len(recent)},
            )

        # ddof=1 for unbiased estimate (same as calibration.py)
        rolling_std = float(np.std(recent, ddof=1))
        ratio = rolling_std / max(ref_std, 1e-6)

        if ratio < threshold:
            # Sub-threshold: score maps ratio → [0, 0.3]
            score = min(0.3, ratio / threshold * 0.3)
            return DetectorResult(
                detector_name="variance",
                is_anomaly=False,
                score=float(score),
                severity=Severity.NOMINAL,
                details={
                    "ratio":       round(ratio, 4),
                    "threshold":   threshold,
                    "rolling_std": round(rolling_std, 6),
                    "ref_std":     round(ref_std, 6),
                },
            )

        score    = min(1.0, (ratio - threshold) / threshold + 0.5)
        severity = self._classify_severity(ratio, threshold)

        return DetectorResult(
            detector_name="variance",
            is_anomaly=True,
            score=float(score),
            severity=severity,
            details={
                "ratio":       round(ratio, 4),
                "threshold":   threshold,
                "rolling_std": round(rolling_std, 6),
                "ref_std":     round(ref_std, 6),
            },
        )

    def _classify_severity(self, ratio: float, threshold: float) -> Severity:
        """Map ratio to severity using threshold multiples.

        Multiples chosen so that CATS-type 2.27× (at threshold=2.5) → WATCH.
        A channel with 5× normal variance → WARNING.
        A channel with 7.5× normal variance → CRITICAL.
        """
        if ratio >= threshold * 3.0:
            return Severity.CRITICAL
        if ratio >= threshold * 2.0:
            return Severity.WARNING
        return Severity.WATCH
