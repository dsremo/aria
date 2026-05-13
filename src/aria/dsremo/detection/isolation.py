"""Isolation Forest detector — multivariate anomaly detection.

This is the most powerful detector in Phase 1. It operates on the full
feature vector across multiple parameters simultaneously, catching anomalies
that only show up in parameter *relationships*.

Example: battery_voltage and solar_current normally correlate. If voltage
drops but current stays high, a univariate detector sees nothing wrong.
Isolation Forest catches the broken correlation.

The model is periodically re-fit on recent normal data (unsupervised).
No labeled anomaly data needed.
"""

from __future__ import annotations

import numpy as np
import structlog
from sklearn.ensemble import IsolationForest

from aria.dsremo.core.models import DetectorResult, Severity

logger = structlog.get_logger()


class IsolationForestDetector:
    """Multivariate anomaly detection using Isolation Forest."""

    def __init__(
        self,
        contamination: float = 0.01,         # ESTIMATE — 1% anomaly rate (Liu 2008 ICDM §4: typical contamination)
        n_estimators: int = 100,             # Liu 2008 ICDM §4: 100 trees; plateau at ~100 for convergence
        min_training_samples: int = 200,     # ESTIMATE — 200 samples minimum for stable Isolation Forest fit
    ):
        self.contamination = contamination
        self._default_contamination = contamination
        self.n_estimators = n_estimators
        self.min_training_samples = min_training_samples

        self._model: IsolationForest | None = None
        self._is_fitted = False
        self._feature_names: list[str] = []
        self._fit_count = 0
        # P3-J: Per-satellite contamination overrides
        self._sat_contamination: dict[str, float] = {}

    @property
    def is_ready(self) -> bool:
        return self._is_fitted

    def set_contamination(self, satellite_id: str, contamination: float) -> None:
        """Set per-satellite contamination rate (P3-J: channel-adaptive)."""
        self._sat_contamination[satellite_id] = max(0.0001, min(contamination, 0.5))

    def estimate_contamination(self, training_data: np.ndarray) -> float:
        """Estimate contamination from training data using IQR outlier fraction.

        P3-J fix: Instead of a fixed global contamination, estimate the actual
        anomaly fraction from the training data using the interquartile range
        method: points beyond Q1 - 3×IQR or Q3 + 3×IQR are considered outliers.
        """
        if len(training_data) < 50:
            return self._default_contamination
        # Use per-feature IQR and count points that are outliers in ANY dimension
        n_samples = len(training_data)
        outlier_mask = np.zeros(n_samples, dtype=bool)
        for col in range(training_data.shape[1]):
            vals = training_data[:, col]
            q1, q3 = float(np.percentile(vals, 25)), float(np.percentile(vals, 75))
            iqr = q3 - q1
            if iqr < 1e-12:
                continue
            lo, hi = q1 - 3.0 * iqr, q3 + 3.0 * iqr
            outlier_mask |= (vals < lo) | (vals > hi)
        fraction = float(np.sum(outlier_mask)) / n_samples
        # Clamp to [0.001, 0.1] — never below 0.1% (too sensitive) or above 10%
        return max(0.001, min(fraction, 0.10))

    def fit(self, training_data: np.ndarray, feature_names: list[str], satellite_id: str = "") -> None:
        """Fit the model on recent normal telemetry data.

        training_data: shape (n_samples, n_features)
        feature_names: list of parameter names matching the columns
        """
        if len(training_data) < self.min_training_samples:
            logger.warning(
                "isolation_forest_skip_fit",
                reason="insufficient_data",
                samples=len(training_data),
                required=self.min_training_samples,
            )
            return

        # P3-J: Use per-satellite contamination if set, else estimate from data.
        effective_contamination = self._sat_contamination.get(
            satellite_id,
            self.estimate_contamination(training_data),
        )
        self._model = IsolationForest(
            contamination=effective_contamination,
            n_estimators=self.n_estimators,
            random_state=42,
            n_jobs=1,  # single-threaded to avoid fork issues in async
        )
        self._model.fit(training_data)
        self._is_fitted = True
        self._feature_names = feature_names
        self._fit_count += 1

        logger.info(
            "isolation_forest_fitted",
            samples=len(training_data),
            features=len(feature_names),
            fit_count=self._fit_count,
        )

    def detect(self, feature_vector: np.ndarray) -> DetectorResult:
        """Score a single multivariate observation.

        feature_vector: shape (n_features,) — one value per parameter
        """
        if not self._is_fitted or self._model is None:
            return DetectorResult(
                detector_name="isolation_forest",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={"reason": "model_not_fitted"},
            )

        sample = feature_vector.reshape(1, -1)

        # Isolation Forest anomaly score: negative = more anomalous
        raw_score = self._model.decision_function(sample)[0]
        prediction = self._model.predict(sample)[0]  # 1 = normal, -1 = anomaly

        # Normalize to [0, 1] where 1 = highly anomalous
        # decision_function returns ~[-0.5, 0.5], with negative = anomaly
        normalized_score = float(np.clip(-raw_score + 0.5, 0, 1))

        is_anomaly = prediction == -1

        # Identify which features contributed most to the anomaly
        contributions = self._compute_feature_contributions(feature_vector)

        severity = Severity.NOMINAL
        if is_anomaly:
            if normalized_score > 0.85:
                severity = Severity.CRITICAL
            elif normalized_score > 0.65:
                severity = Severity.WARNING
            else:
                severity = Severity.WATCH

        return DetectorResult(
            detector_name="isolation_forest",
            is_anomaly=is_anomaly,
            score=normalized_score,
            severity=severity,
            details={
                "raw_score": float(raw_score),
                "feature_contributions": contributions,
                "fit_count": self._fit_count,
            },
        )

    def _compute_feature_contributions(self, feature_vector: np.ndarray) -> dict[str, float]:
        """Estimate which features contributed most to the anomaly score.

        Uses a simple perturbation-based approach: mask each feature to its
        mean value and measure score change. Not as rigorous as SHAP but
        fast enough for real-time use.
        """
        if not self._is_fitted or self._model is None:
            return {}

        base_score = self._model.decision_function(feature_vector.reshape(1, -1))[0]
        contributions = {}

        for i, name in enumerate(self._feature_names):
            perturbed = feature_vector.copy()
            perturbed[i] = 0.0  # set to zero (approximate mean for standardized data)
            perturbed_score = self._model.decision_function(perturbed.reshape(1, -1))[0]
            # Positive delta = this feature made it more anomalous
            contributions[name] = float(base_score - perturbed_score)

        return contributions

    def needs_refit(self, samples_since_fit: int, refit_interval: int = 1000) -> bool:
        """Check if the model should be retrained on newer data."""
        if not self._is_fitted:
            return True
        return samples_since_fit >= refit_interval
