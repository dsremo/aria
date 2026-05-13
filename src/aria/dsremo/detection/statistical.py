"""Statistical detector — rolling Z-score on STL residuals.

Role in the ensemble (post-STL architecture):
    CUSUM / EWMA handle drift and level shifts.
    This detector handles SPIKES — sudden single-point outliers that CUSUM
    misses because it requires sustained accumulation.

Input: STL residual array (oldest → newest), NOT raw telemetry values.
    Residuals are centred near 0 (mean subtracted by calibration baseline).
    Z-score of a residual = "how many σ away from zero is this deviation?"

The detector also flags rapid rate-of-change anomalies (dv/dt) using the
same residual window.  A spike looks like a large residual; a ramp looks
like a large rate-of-change.

Constant-value guard: if residuals have std < 1e-4, the channel is
perfectly stable and the score is forced to NOMINAL.
"""

from __future__ import annotations

import numpy as np

from aria.dsremo.core.models import DetectorResult, Severity
from aria.dsremo.features.engine import FeatureVector


class StatisticalDetector:
    """Z-score spike detector.  Stateless — all context comes from the window."""

    def __init__(
        self,
        z_threshold: float = 3.5,           # ESTIMATE — 3.5σ spike threshold (Shewhart 1931; ESA telemetry practice)
        severe_z_threshold: float = 5.0,    # ESTIMATE — 5σ critical (NASA NPR 7120.5E anomaly response threshold)
        min_window: int = 30,               # ESTIMATE — 30-sample minimum for stable rolling statistics
    ):
        self.z_threshold = z_threshold
        self.severe_z_threshold = severe_z_threshold
        self.min_window = min_window

    @staticmethod
    def _mad_z(current: float, window: np.ndarray) -> float:
        """Modified z-score using MAD (Median Absolute Deviation).

        Grafana/Prometheus production insight (2024): standard std squares
        differences, so one spike blows up the band and blinds the detector
        for hours.  MAD = median(|x − median(x)|) is spike-immune by design.
        Factor 0.6745 normalises MAD to match σ for Gaussian data (NIST).
        Returns 0.0 when MAD ≈ 0 (constant signal — caller falls back to std).
        """
        med = float(np.median(window))
        mad = float(np.median(np.abs(window - med)))
        if mad < 1e-6:
            return 0.0
        return float(0.6745 * abs(current - med) / mad)

    def detect(
        self,
        features: FeatureVector,
        window_values: np.ndarray | None = None,
    ) -> DetectorResult:
        """Evaluate a single parameter's feature vector for spikes.

        Uses MAD-based modified z-score (spike-robust) when enough window data
        is available, falling back to rolling-std z-score otherwise.  The MAD
        approach prevents single outlier spikes from collapsing the detection
        band — a known failure mode in production monitoring systems.

        Args:
            features:     FeatureVector computed on the STL residual window.
                          features.raw_value  = current residual
                          features.z_score    = residual / rolling_std(residuals)
            window_values: Raw residual array (optional).  Used for minimum-
                          window enforcement and rate-of-change check.

        Returns:
            DetectorResult from the "statistical" detector.
        """
        # Prefer MAD-based z when we have enough data (spike-robust).
        z_std = abs(features.z_score)
        if window_values is not None and len(window_values) >= self.min_window:
            z_mad = self._mad_z(float(features.raw_value), window_values)
            z = z_mad if z_mad > 0.0 else z_std
        else:
            z = z_std

        # Constant-signal guard: perfectly flat residuals mean the STL
        # decomposition captured everything — this channel is nominal.
        if features.rolling_std < 1e-4:
            return DetectorResult(
                detector_name="statistical",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={
                    "reason": "constant_residual",
                    "rolling_std": float(features.rolling_std),
                },
            )

        # Insufficient history for a meaningful z-score.
        # When window_values is None we rely on the feature engine's rolling_std
        # (already validated above), so skip the window-size check entirely.
        n = len(window_values) if window_values is not None else self.min_window
        if n < self.min_window:
            return DetectorResult(
                detector_name="statistical",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={"reason": "insufficient_data", "window_size": n},
            )

        # Score: maps z → [0, 1]
        #   z <  z_threshold : sub-threshold, low score (0 → 0.3)
        #   z >= z_threshold : anomalous, score starts at 0.5 and grows
        if z < self.z_threshold:
            score = z / self.z_threshold * 0.3
            return DetectorResult(
                detector_name="statistical",
                is_anomaly=False,
                score=float(score),
                severity=Severity.NOMINAL,
                details={
                    "z_score":   float(features.z_score),
                    "threshold": self.z_threshold,
                },
            )

        score    = min(1.0, (z - self.z_threshold) / self.z_threshold + 0.5)
        severity = self._classify_severity(z)

        # Rate-of-change anomaly: residual is jumping too fast.
        roc_flag = (
            abs(features.rate_of_change) > abs(features.rolling_std) * 3
            if features.rolling_std > 0
            else False
        )

        return DetectorResult(
            detector_name="statistical",
            is_anomaly=True,
            score=float(score),
            severity=severity,
            details={
                "z_score":              float(features.z_score),
                "threshold":            self.z_threshold,
                "rate_of_change_anomaly": roc_flag,
                "rolling_mean":         float(features.rolling_mean),
                "rolling_std":          float(features.rolling_std),
                "deviation":            float(features.deviation_from_trend),
            },
        )

    def _classify_severity(self, z: float) -> Severity:
        if z >= self.severe_z_threshold:
            return Severity.CRITICAL
        if z >= self.z_threshold * 1.5:
            return Severity.WARNING
        return Severity.WATCH

    def detect_batch(
        self,
        feature_vectors: list[FeatureVector],
        window_arrays: dict[str, np.ndarray],
    ) -> list[DetectorResult]:
        return [
            self.detect(fv, window_arrays.get(fv.parameter))
            for fv in feature_vectors
        ]
