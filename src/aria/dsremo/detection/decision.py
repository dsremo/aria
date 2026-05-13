"""Decision-theoretic framework for autonomous anomaly response.

Provides cost-sensitive thresholding and confidence calibration so that
autonomous systems (or operators) can make optimal safing decisions:

    optimal_threshold = C(false_alarm) / (C(false_alarm) + C(missed_detection))

Instead of the arbitrary fixed thresholds (0.50/0.65/0.85), this module
allows per-mission cost configuration.

Also provides Platt scaling for confidence calibration — mapping raw
ensemble scores to true probabilities via logistic regression on
historical labeled data.

References:
    - Neyman-Pearson framework for detection theory
    - Platt (1999): Probabilistic Outputs for SVMs
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass(frozen=True)
class CostConfig:
    """Mission-specific cost configuration for decision-making.

    All costs are relative (unitless ratios).  Only the ratio
    C(false_alarm) / C(missed_detection) matters for threshold computation.
    """

    # Cost of a false alarm: unnecessary safing, lost science time.
    # For a science mission: high (e.g., $50K/day lost).
    # For a demo mission: low.
    c_false_alarm: float = 1.0

    # Cost of a missed detection: hardware damage, mission loss.
    # For crewed missions: extremely high.
    # For CubeSats: moderate.
    c_missed_detection: float = 10.0

    # Cost of entering safe mode when there IS a fault (correct action).
    c_safe_given_fault: float = 0.1

    # Cost of doing nothing when there IS a fault.
    c_nothing_given_fault: float = 100.0

    @property
    def optimal_threshold(self) -> float:
        """Bayes-optimal detection threshold.

        P(fault) threshold above which safing is optimal:
            t* = C(FA) / (C(FA) + C(MD))

        For c_false_alarm=1, c_missed_detection=10:
            t* = 1/11 ≈ 0.091 (very aggressive — alert on low confidence)

        For c_false_alarm=10, c_missed_detection=1:
            t* = 10/11 ≈ 0.909 (very conservative — only alert on high confidence)
        """
        denom = self.c_false_alarm + self.c_missed_detection
        if denom <= 0:
            return 0.5
        return self.c_false_alarm / denom

    @property
    def optimal_safing_threshold(self) -> float:
        """Threshold for autonomous safing decisions (more conservative).

        Uses the full 4-cost model:
            t* = (C(safe|no_fault) - C(nothing|no_fault)) /
                 ((C(safe|no_fault) - C(nothing|no_fault)) +
                  (C(nothing|fault) - C(safe|fault)))
        """
        # C(nothing|no_fault) = 0 (correct non-action)
        num = self.c_false_alarm
        denom = self.c_false_alarm + (self.c_nothing_given_fault - self.c_safe_given_fault)
        if denom <= 0:
            return 0.5
        return num / denom


class PlattCalibrator:
    """Platt scaling for confidence calibration.

    Maps raw ensemble scores to calibrated probabilities via logistic regression:
        P(anomaly | score) = 1 / (1 + exp(A × score + B))

    Parameters A and B are fit from historical labeled data (score, label) pairs
    using maximum likelihood on the logistic model.
    """

    def __init__(self) -> None:
        self.A: float = -1.0  # default: identity-like mapping
        self.B: float = 0.0
        self._fitted: bool = False

    def fit(self, scores: list[float], labels: list[bool]) -> None:
        """Fit Platt scaling from labeled data.

        Args:
            scores: Raw ensemble confidence scores.
            labels: True if real anomaly, False if false positive.
        """
        if len(scores) < 10:
            logger.warning("platt_calibration_insufficient_data", n=len(scores))
            return

        # Simple logistic regression via Newton's method (Platt 1999).
        # Target: P(y=1|s) = 1 / (1 + exp(A×s + B))
        # Note: A is typically negative (higher score → higher probability).
        import numpy as np  # noqa: PLC0415

        s = np.array(scores, dtype=np.float64)
        y = np.array(labels, dtype=np.float64)

        # Target probabilities (Platt's label smoothing)
        n_pos = np.sum(y)
        n_neg = len(y) - n_pos
        t_pos = (n_pos + 1.0) / (n_pos + 2.0)
        t_neg = 1.0 / (n_neg + 2.0)
        t = np.where(y > 0.5, t_pos, t_neg)

        # Newton's method for logistic regression
        A, B = 0.0, math.log((n_neg + 1.0) / (n_pos + 1.0))
        for _ in range(100):
            p = 1.0 / (1.0 + np.exp(A * s + B))
            d = p * (1.0 - p)
            d = np.maximum(d, 1e-12)

            # Gradient
            g_A = np.sum(s * (p - t))
            g_B = np.sum(p - t)

            # Hessian
            h_AA = np.sum(s * s * d)
            h_AB = np.sum(s * d)
            h_BB = np.sum(d)

            det = h_AA * h_BB - h_AB * h_AB
            if abs(det) < 1e-12:
                break

            A -= (h_BB * g_A - h_AB * g_B) / det
            B -= (h_AA * g_B - h_AB * g_A) / det

        self.A = A
        self.B = B
        self._fitted = True
        logger.info("platt_calibration_fitted", A=round(A, 4), B=round(B, 4), n=len(scores))

    def calibrate(self, score: float) -> float:
        """Map a raw score to a calibrated probability."""
        if not self._fitted:
            return score  # pass through if not fitted
        exp_val = self.A * score + self.B
        if exp_val > 50:
            return 0.0
        if exp_val < -50:
            return 1.0
        return 1.0 / (1.0 + math.exp(exp_val))

    @property
    def is_fitted(self) -> bool:
        return self._fitted


# Default mission cost profiles
COST_PROFILES: dict[str, CostConfig] = {
    "crewed": CostConfig(c_false_alarm=0.5, c_missed_detection=1000.0,
                         c_safe_given_fault=0.1, c_nothing_given_fault=10000.0),
    "science": CostConfig(c_false_alarm=10.0, c_missed_detection=100.0,
                          c_safe_given_fault=1.0, c_nothing_given_fault=500.0),
    "cubesat": CostConfig(c_false_alarm=1.0, c_missed_detection=5.0,
                          c_safe_given_fault=0.5, c_nothing_given_fault=20.0),
    "demo": CostConfig(c_false_alarm=1.0, c_missed_detection=2.0,
                       c_safe_given_fault=0.5, c_nothing_given_fault=5.0),
}


# Singleton calibrator
_calibrator = PlattCalibrator()


def get_calibrator() -> PlattCalibrator:
    return _calibrator
