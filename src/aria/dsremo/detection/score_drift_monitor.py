"""V3-Be4: Anomaly score distribution drift monitoring (PSI).

If the 90th percentile of anomaly_confidence drifts from 0.35 to 0.65
over 30 days without a corresponding increase in confirmed anomalies,
this is false positive inflation — detectors are becoming trigger-happy.

This module tracks score distribution percentiles daily and computes
Population Stability Index (PSI) to detect distribution shift.

PSI thresholds (industry standard):
    PSI < 0.10 → stable
    0.10 ≤ PSI < 0.25 → marginal shift, investigate
    PSI ≥ 0.25 → significant shift, detector audit required

Reference: Siddiqi, N. (2006). Credit Risk Scorecards. Wiley. §4.4.
"""

from __future__ import annotations

from collections import deque

import numpy as np
import structlog

logger = structlog.get_logger()


class ScoreDriftMonitor:
    """Tracks anomaly score distribution for drift detection via PSI.

    Maintains daily score snapshots per satellite and computes PSI between
    the current window and a trailing baseline.
    """

    def __init__(
        self,
        baseline_days: int = 28,      # ESTIMATE — 28-day baseline window (4 weeks); Siddiqi 2006 §4.4 recommends ≥1 month
        current_window_days: int = 7, # ESTIMATE — 7-day current window; Siddiqi 2006 §4.4: 1-week monitoring cycle
        psi_warning: float = 0.10,    # Siddiqi 2006 Credit Risk Scorecards §4.4: PSI 0.10-0.25 → marginal shift
        psi_critical: float = 0.25,   # Siddiqi 2006 §4.4: PSI ≥ 0.25 → significant shift (model audit required)
        n_bins: int = 10,             # ESTIMATE — 10 bins for PSI; Siddiqi 2006 §4.4: 10-20 bins standard
    ) -> None:
        self._baseline_days = baseline_days
        self._current_days = current_window_days
        self._psi_warning = psi_warning
        self._psi_critical = psi_critical
        self._n_bins = n_bins
        # satellite_id → deque of daily score lists
        self._daily_scores: dict[str, deque[list[float]]] = {}
        # Current day's accumulator
        self._today_scores: dict[str, list[float]] = {}

    def add_score(self, satellite_id: str, confidence: float) -> None:
        """Record one anomaly confidence score for today."""
        buf = self._today_scores.setdefault(satellite_id, [])
        buf.append(max(0.0, min(1.0, confidence)))

    def end_day(self, satellite_id: str) -> dict | None:
        """Finalize today's scores and compute PSI against baseline.

        Call once per day (e.g., at midnight UTC) per satellite.

        Returns:
            {"psi": float, "status": str, "percentiles": dict} or None
            if insufficient history.
        """
        today = self._today_scores.pop(satellite_id, [])
        if not today:
            return None

        history = self._daily_scores.setdefault(
            satellite_id,
            deque(maxlen=self._baseline_days + self._current_days),
        )
        history.append(today)

        if len(history) < self._baseline_days + 1:
            return None  # not enough history

        # Split into baseline (older) and current (recent) windows.
        all_days = list(history)
        baseline_scores = []
        for day in all_days[: self._baseline_days]:
            baseline_scores.extend(day)
        current_scores = []
        for day in all_days[-self._current_days:]:
            current_scores.extend(day)

        if len(baseline_scores) < 20 or len(current_scores) < 10:
            return None

        psi = self._compute_psi(
            np.array(baseline_scores), np.array(current_scores),
        )

        if psi >= self._psi_critical:
            status = "critical_shift"
            logger.warning(
                "score_distribution_shift",
                satellite=satellite_id,
                psi=round(psi, 4),
                status=status,
            )
        elif psi >= self._psi_warning:
            status = "marginal_shift"
        else:
            status = "stable"

        # Compute percentiles for the report.
        curr = np.array(current_scores)
        percentiles = {
            f"p{p}": round(float(np.percentile(curr, p)), 4)
            for p in (25, 50, 75, 90, 99)
        }

        return {
            "psi": round(psi, 4),
            "status": status,
            "percentiles": percentiles,
            "baseline_n": len(baseline_scores),
            "current_n": len(current_scores),
        }

    def _compute_psi(
        self,
        baseline: np.ndarray,
        current: np.ndarray,
    ) -> float:
        """Population Stability Index between two score distributions.

        PSI = Σ (p_current - p_baseline) × ln(p_current / p_baseline)
        over histogram bins.
        """
        bins = np.linspace(0.0, 1.0, self._n_bins + 1)
        eps = 1e-4  # avoid log(0)

        base_hist, _ = np.histogram(baseline, bins=bins)
        curr_hist, _ = np.histogram(current, bins=bins)

        # Normalize to proportions.
        base_p = (base_hist + eps) / (base_hist.sum() + eps * self._n_bins)
        curr_p = (curr_hist + eps) / (curr_hist.sum() + eps * self._n_bins)

        psi = float(np.sum((curr_p - base_p) * np.log(curr_p / base_p)))
        return max(0.0, psi)

    def reset(self, satellite_id: str | None = None) -> None:
        if satellite_id:
            self._daily_scores.pop(satellite_id, None)
            self._today_scores.pop(satellite_id, None)
        else:
            self._daily_scores.clear()
            self._today_scores.clear()
