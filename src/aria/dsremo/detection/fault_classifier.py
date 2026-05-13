"""V3-H4: Naive Bayes fault type classifier from detector firing patterns.

When detectors fire, operators want: P(fault_type = BATTERY_DEGRADATION |
CUSUM fired on battery_voltage, CorrelationGraph fired on solar/voltage).

Currently, the explanation module generates text but computes no posterior
probability distribution over fault types.

This module provides a lightweight Naive Bayes classifier from
(detectors_triggered, subsystem, severity) → P(fault_type).

Uses Laplace smoothing for unseen combinations.  Trained incrementally
from confirmed incidents.

Reference: Heckerman, D., Geiger, D. & Chickering, D.M. (1995).
           "Learning Bayesian networks." Machine Learning 20(3):197–243.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

import structlog

logger = structlog.get_logger()

# All known fault types.
FAULT_TYPES = (
    "drift", "spike", "dropout", "degradation",
    "oscillation", "correlation_break", "sensor_fault",
    "mode_transition", "unknown",
)


class FaultClassifier:
    """Naive Bayes classifier for fault type given detector evidence.

    Features:
        - Binary vector of 12+ detector firings
        - Subsystem ID
        - Severity level

    Train from confirmed incidents:
        clf.train(
            detectors_triggered=("cusum", "ewma"),
            subsystem="eps",
            severity="warning",
            fault_type="drift",
        )

    Predict:
        posterior = clf.predict(
            detectors_triggered=("cusum", "ewma"),
            subsystem="eps",
            severity="warning",
        )
        # posterior = {"drift": 0.72, "degradation": 0.15, ...}
    """

    def __init__(self, laplace_alpha: float = 1.0) -> None:
        self._alpha = laplace_alpha
        # Counts for Naive Bayes.
        self._class_counts: Counter[str] = Counter()
        self._feature_counts: dict[str, Counter[str]] = defaultdict(Counter)
        # feature key format: "det:cusum", "sub:eps", "sev:warning"
        self._total_samples = 0

    def train(
        self,
        detectors_triggered: tuple[str, ...],
        subsystem: str,
        severity: str,
        fault_type: str,
    ) -> None:
        """Add one confirmed incident to the training set."""
        self._class_counts[fault_type] += 1
        self._total_samples += 1

        # Detector features (binary: present or absent).
        for det in detectors_triggered:
            self._feature_counts[fault_type][f"det:{det}"] += 1

        # Subsystem and severity as categorical features.
        self._feature_counts[fault_type][f"sub:{subsystem}"] += 1
        self._feature_counts[fault_type][f"sev:{severity}"] += 1

    def predict(
        self,
        detectors_triggered: tuple[str, ...],
        subsystem: str,
        severity: str,
        top_k: int = 3,
    ) -> list[tuple[str, float]]:
        """Return top-k fault types with posterior probabilities.

        Returns list of (fault_type, probability) sorted by probability desc.
        Returns empty list if no training data.
        """
        if self._total_samples == 0:
            return []

        features = [f"det:{d}" for d in detectors_triggered]
        features.append(f"sub:{subsystem}")
        features.append(f"sev:{severity}")

        n_classes = len(self._class_counts)
        log_posteriors: dict[str, float] = {}

        for ft in self._class_counts:
            # Log prior: P(class) with Laplace smoothing.
            log_prior = math.log(
                (self._class_counts[ft] + self._alpha)
                / (self._total_samples + self._alpha * n_classes)
            )

            # Log likelihood: Π P(feature | class).
            log_likelihood = 0.0
            class_total = self._class_counts[ft]
            ft_counts = self._feature_counts[ft]

            for f in features:
                count = ft_counts.get(f, 0)
                # Laplace smoothed: P(f|class) = (count + α) / (class_total + 2α)
                # Binary feature: 2 possible values (present/absent).
                prob = (count + self._alpha) / (class_total + 2.0 * self._alpha)
                log_likelihood += math.log(max(prob, 1e-12))

            log_posteriors[ft] = log_prior + log_likelihood

        # Normalize via log-sum-exp.
        max_log = max(log_posteriors.values())
        denom = math.log(sum(math.exp(lp - max_log) for lp in log_posteriors.values())) + max_log

        posteriors = {
            ft: math.exp(lp - denom)
            for ft, lp in log_posteriors.items()
        }

        # Sort by probability descending, take top-k.
        ranked = sorted(posteriors.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

    @property
    def sample_count(self) -> int:
        return self._total_samples
