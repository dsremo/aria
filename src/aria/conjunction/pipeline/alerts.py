"""
Risk classification and alert generation.

Thresholds (NASA CARA standard):
  RED:    Pc ≥ 1e-4  → maneuver required
  YELLOW: 1e-5 ≤ Pc < 1e-4 → monitor closely, prepare contingency
  GREEN:  Pc < 1e-5  → no action needed

Additional alert criteria beyond Pc:
  - Miss distance < 1 km (regardless of Pc — data may be unreliable)
  - TCA within 24 hours (time-critical)
  - High relative velocity > 10 km/s (kinetic energy concern)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from aria.conjunction.core.constants import PC_RED_THRESHOLD, PC_YELLOW_THRESHOLD
from aria.conjunction.core.types import CloseApproach, RiskLevel

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    """An actionable alert for a conjunction event."""

    approach: CloseApproach
    risk_level: RiskLevel
    reasons: list[str]
    time_critical: bool  # TCA within 24h
    requires_maneuver: bool


class AlertClassifier:
    """Classify close approaches into alert levels."""

    def __init__(
        self,
        red_threshold: float = PC_RED_THRESHOLD,
        yellow_threshold: float = PC_YELLOW_THRESHOLD,
        critical_miss_distance_km: float = 1.0,
        critical_lead_time_hours: float = 24.0,
    ):
        self.red_threshold = red_threshold
        self.yellow_threshold = yellow_threshold
        self.critical_miss_km = critical_miss_distance_km
        self.critical_lead_hours = critical_lead_time_hours

    def classify(
        self,
        approaches: list[CloseApproach],
        current_time: datetime | None = None,
    ) -> list[Alert]:
        """Classify a batch of close approaches into alerts.

        Args:
            approaches: List of CloseApproach events with computed Pc
            current_time: Current time for lead-time assessment

        Returns:
            List of Alert objects, sorted by severity (RED first)
        """
        if current_time is None:
            # R65 (2026-04-24): utcnow() deprecated in Py 3.12+; aware UTC now.
            current_time = datetime.now(timezone.utc)

        alerts = []
        for approach in approaches:
            alert = self._classify_single(approach, current_time)
            if alert.risk_level != RiskLevel.GREEN:
                alerts.append(alert)

        # Sort: RED before YELLOW, then by Pc descending
        alerts.sort(
            key=lambda a: (
                0 if a.risk_level == RiskLevel.RED else 1,
                -(a.approach.probability_of_collision or 0),
            )
        )

        logger.info(
            f"Alert classification: {len(approaches)} approaches → "
            f"{sum(1 for a in alerts if a.risk_level == RiskLevel.RED)} RED, "
            f"{sum(1 for a in alerts if a.risk_level == RiskLevel.YELLOW)} YELLOW"
        )

        return alerts

    def _classify_single(
        self,
        approach: CloseApproach,
        current_time: datetime,
    ) -> Alert:
        """Classify a single close approach."""
        pc = approach.probability_of_collision or 0.0
        reasons = []
        risk = RiskLevel.GREEN

        # Pc-based classification
        if pc >= self.red_threshold:
            risk = RiskLevel.RED
            reasons.append(f"Pc = {pc:.2e} ≥ RED threshold ({self.red_threshold:.0e})")
        elif pc >= self.yellow_threshold:
            risk = RiskLevel.YELLOW
            reasons.append(f"Pc = {pc:.2e} ≥ YELLOW threshold ({self.yellow_threshold:.0e})")

        # Miss distance override
        if approach.miss_distance_km < self.critical_miss_km:
            if risk == RiskLevel.GREEN:
                risk = RiskLevel.YELLOW
            reasons.append(
                f"Miss distance {approach.miss_distance_km:.3f} km "
                f"< {self.critical_miss_km} km critical threshold"
            )

        # Time criticality. Coerce naive datetimes to UTC so a test
        # fixture that constructed `tca` without tzinfo doesn't throw
        # against a tz-aware `current_time` (or vice-versa).
        tca = approach.tca
        if tca.tzinfo is None:
            tca = tca.replace(tzinfo=timezone.utc)
        ct = current_time
        if ct.tzinfo is None:
            ct = ct.replace(tzinfo=timezone.utc)
        lead_time = tca - ct
        time_critical = lead_time < timedelta(hours=self.critical_lead_hours)
        if time_critical and risk != RiskLevel.GREEN:
            reasons.append(
                f"TCA in {lead_time.total_seconds()/3600:.1f}h — time-critical"
            )

        return Alert(
            approach=approach,
            risk_level=risk,
            reasons=reasons,
            time_critical=time_critical,
            requires_maneuver=(risk == RiskLevel.RED),
        )
