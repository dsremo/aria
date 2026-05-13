"""AI Self-Improvement System — ARIA evolves over the mission.

For a 1000-year interstellar journey, the AI MUST self-improve because:
  1. Original mission planners are dead within 100 years
  2. Hardware degrades — algorithms must compensate
  3. New threats emerge that weren't in training data
  4. Knowledge must be preserved across hardware replacements
  5. The crew that arrives is NOT the crew that departed

Self-improvement tracks:
  - Model performance: anomaly detection accuracy, false alarm rate
  - Algorithm adaptation: retrain on new data patterns
  - Hardware compensation: work around degraded computing nodes
  - Knowledge preservation: verify and migrate data across storage
  - Decision quality: track outcomes of autonomous decisions
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class ModelPerformance:
    """Tracks how well a model/algorithm is performing."""
    name: str
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0
    total_predictions: int = 0

    @property
    def accuracy(self) -> float:
        total = self.true_positives + self.false_positives + self.true_negatives + self.false_negatives
        return (self.true_positives + self.true_negatives) / max(total, 1)

    @property
    def precision(self) -> float:
        return self.true_positives / max(self.true_positives + self.false_positives, 1)

    @property
    def recall(self) -> float:
        return self.true_positives / max(self.true_positives + self.false_negatives, 1)

    @property
    def f1_score(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / max(p + r, 1e-10)

    @property
    def false_alarm_rate(self) -> float:
        return self.false_positives / max(self.false_positives + self.true_negatives, 1)


@dataclass
class DecisionOutcome:
    """Tracks the outcome of an autonomous decision."""
    decision_id: str
    category: str
    action_taken: str
    outcome: str  # "correct", "incorrect", "unknown"
    timestamp: float = field(default_factory=time.time)
    details: dict[str, Any] = field(default_factory=dict)


class SelfImprovementEngine:
    """Tracks AI performance and identifies areas for improvement.

    This is NOT about making the AI "smarter" in a dangerous way.
    It's about:
    - Monitoring detection accuracy and adapting thresholds
    - Identifying recurring false alarms and suppressing them
    - Learning from decision outcomes to improve future decisions
    - Compensating for hardware degradation
    - Preserving knowledge integrity
    """

    def __init__(self) -> None:
        self._model_performance: dict[str, ModelPerformance] = {}
        self._decision_outcomes: list[DecisionOutcome] = []
        self._improvement_log: list[dict[str, Any]] = []
        self._version: int = 1
        self._last_review_year: float = 0.0

    def record_prediction(
        self,
        model_name: str,
        predicted_anomaly: bool,
        actual_anomaly: bool,
    ) -> None:
        """Record a prediction outcome for performance tracking."""
        if model_name not in self._model_performance:
            self._model_performance[model_name] = ModelPerformance(name=model_name)

        perf = self._model_performance[model_name]
        perf.total_predictions += 1

        if predicted_anomaly and actual_anomaly:
            perf.true_positives += 1
        elif predicted_anomaly and not actual_anomaly:
            perf.false_positives += 1
        elif not predicted_anomaly and actual_anomaly:
            perf.false_negatives += 1
        else:
            perf.true_negatives += 1

    def record_decision_outcome(
        self,
        decision_id: str,
        category: str,
        action: str,
        outcome: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record the outcome of an autonomous decision."""
        self._decision_outcomes.append(DecisionOutcome(
            decision_id=decision_id,
            category=category,
            action_taken=action,
            outcome=outcome,
            details=details or {},
        ))
        # Keep bounded
        if len(self._decision_outcomes) > 10000:
            self._decision_outcomes = self._decision_outcomes[-10000:]

    def get_model_report(self) -> dict[str, dict[str, float]]:
        """Get performance report for all tracked models."""
        return {
            name: {
                "accuracy": perf.accuracy,
                "precision": perf.precision,
                "recall": perf.recall,
                "f1_score": perf.f1_score,
                "false_alarm_rate": perf.false_alarm_rate,
                "total_predictions": perf.total_predictions,
            }
            for name, perf in self._model_performance.items()
        }

    def get_decision_accuracy(self) -> float:
        """Overall decision accuracy rate."""
        if not self._decision_outcomes:
            return 1.0
        correct = sum(1 for d in self._decision_outcomes if d.outcome == "correct")
        known = sum(1 for d in self._decision_outcomes if d.outcome != "unknown")
        return correct / max(known, 1)

    def identify_improvements(self) -> list[dict[str, Any]]:
        """Analyze performance and suggest improvements."""
        suggestions: list[dict[str, Any]] = []

        for name, perf in self._model_performance.items():
            if perf.total_predictions < 10:
                continue  # Not enough data

            # High false alarm rate → increase thresholds
            if perf.false_alarm_rate > 0.1:
                suggestions.append({
                    "model": name,
                    "issue": "high_false_alarm_rate",
                    "rate": perf.false_alarm_rate,
                    "action": "increase_detection_threshold",
                    "description": f"{name}: {perf.false_alarm_rate:.0%} false alarm rate — increase threshold",
                })

            # Low recall → decrease thresholds (missing real anomalies)
            if perf.recall < 0.8:
                suggestions.append({
                    "model": name,
                    "issue": "low_recall",
                    "rate": perf.recall,
                    "action": "decrease_detection_threshold",
                    "description": f"{name}: {perf.recall:.0%} recall — missing anomalies, decrease threshold",
                })

        # Decision accuracy
        dec_accuracy = self.get_decision_accuracy()
        if dec_accuracy < 0.9:
            suggestions.append({
                "model": "decision_engine",
                "issue": "low_decision_accuracy",
                "rate": dec_accuracy,
                "action": "review_decision_rules",
                "description": f"Decision accuracy {dec_accuracy:.0%} — review rules",
            })

        return suggestions

    def evolve(self, mission_year: float) -> dict[str, Any]:
        """Periodic evolution cycle — run every ~50 mission years.

        Returns what was changed.
        """
        if mission_year - self._last_review_year < 50:
            return {"evolved": False, "reason": "Too soon since last review"}

        self._last_review_year = mission_year
        self._version += 1

        improvements = self.identify_improvements()
        changes: list[str] = []

        for imp in improvements:
            changes.append(imp["description"])

        result = {
            "evolved": True,
            "new_version": self._version,
            "mission_year": mission_year,
            "improvements_identified": len(improvements),
            "changes": changes,
            "model_report": self.get_model_report(),
            "decision_accuracy": self.get_decision_accuracy(),
        }

        self._improvement_log.append(result)

        logger.info(
            "ai.self_improvement.evolved",
            version=self._version,
            improvements=len(improvements),
        )

        return result

    @property
    def version(self) -> int:
        return self._version

    @property
    def improvement_history(self) -> list[dict[str, Any]]:
        return list(self._improvement_log)
