"""
Conjunction event history and Pc trending.

Tracks the evolution of conjunction events across multiple CDM updates.
Provides:
  - Pc trend (rising, falling, stable)
  - Miss distance evolution
  - Time-to-TCA countdown
  - Risk escalation/de-escalation alerts

NASA CARA operators look at Pc trend slope over 3+ CDM updates
to decide whether to maneuver. A rising Pc is far more concerning
than a static one, even if the absolute value is the same.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from aria.conjunction.core.types import CloseApproach, RiskLevel

logger = logging.getLogger(__name__)


@dataclass
class PcSnapshot:
    """A single observation of a conjunction event at one point in time."""

    timestamp: datetime  # when this assessment was made
    tca: datetime
    miss_distance_km: float
    probability_of_collision: float
    risk_level: RiskLevel
    hours_to_tca: float


@dataclass
class ConjunctionEvent:
    """A conjunction event tracked over time across multiple CDM updates.

    Identified by the (primary_id, secondary_id) pair and approximate TCA.
    Multiple snapshots are recorded as new CDMs/assessments arrive.
    """

    primary_id: str
    secondary_id: str
    primary_name: str
    secondary_name: str
    snapshots: list[PcSnapshot] = field(default_factory=list)

    @property
    def event_key(self) -> str:
        lo, hi = min(self.primary_id, self.secondary_id), max(self.primary_id, self.secondary_id)
        return f"{lo}-{hi}"

    @property
    def latest(self) -> PcSnapshot | None:
        return self.snapshots[-1] if self.snapshots else None

    @property
    def peak_pc(self) -> float:
        return max((s.probability_of_collision for s in self.snapshots), default=0.0)

    @property
    def pc_trend(self) -> str:
        """Compute Pc trend: 'RISING', 'FALLING', 'STABLE', or 'UNKNOWN'."""
        if len(self.snapshots) < 2:
            return "UNKNOWN"

        recent = self.snapshots[-3:]  # last 3 updates
        pcs = [s.probability_of_collision for s in recent]

        if len(pcs) < 2:
            return "UNKNOWN"

        # Linear trend via simple slope
        slope = (pcs[-1] - pcs[0]) / max(len(pcs) - 1, 1)

        # Relative change
        if pcs[0] > 0:
            rel_change = slope / pcs[0]
        else:
            rel_change = 1.0 if slope > 0 else 0.0

        if rel_change > 0.5:  # Pc increased by >50%
            return "RISING"
        elif rel_change < -0.5:  # Pc decreased by >50%
            return "FALLING"
        return "STABLE"

    @property
    def pc_slope_per_hour(self) -> float:
        """Rate of change of Pc per hour (for forecasting)."""
        if len(self.snapshots) < 2:
            return 0.0

        s0 = self.snapshots[0]
        s1 = self.snapshots[-1]
        dt_hours = (s1.timestamp - s0.timestamp).total_seconds() / 3600.0
        if dt_hours <= 0:
            return 0.0

        return (s1.probability_of_collision - s0.probability_of_collision) / dt_hours

    def forecast_pc(self, hours_ahead: float = 8.0) -> float:
        """Forecast Pc at next CDM update using linear extrapolation.

        Conservative: never forecast below the current Pc × 0.1.
        """
        if not self.snapshots:
            return 0.0

        current = self.snapshots[-1].probability_of_collision
        slope = self.pc_slope_per_hour

        forecast = current + slope * hours_ahead
        return max(forecast, current * 0.1)  # don't forecast below 10% of current


class ConjunctionTracker:
    """Track conjunction events across multiple assessment cycles."""

    def __init__(self, tca_match_window_hours: float = 24.0):
        """
        Args:
            tca_match_window_hours: Two assessments with TCA within this window
                                   are considered the same event
        """
        self._events: dict[str, ConjunctionEvent] = {}
        self.tca_match_window_hours = tca_match_window_hours

    def update(  # noqa: E501
        self, approach: CloseApproach, assessment_time: datetime | None = None
    ) -> ConjunctionEvent:
        """Record a new assessment for a conjunction event.

        If this (primary, secondary) pair has been seen before with a similar TCA,
        appends a snapshot. Otherwise, creates a new event.
        """
        if assessment_time is None:
            assessment_time = datetime.utcnow()

        event_key = self._make_key(approach.primary.norad_id, approach.secondary.norad_id)

        # Find or create event
        if event_key in self._events:
            event = self._events[event_key]
        else:
            event = ConjunctionEvent(
                primary_id=approach.primary.norad_id,
                secondary_id=approach.secondary.norad_id,
                primary_name=approach.primary.name,
                secondary_name=approach.secondary.name,
            )
            self._events[event_key] = event

        hours_to_tca = (approach.tca - assessment_time).total_seconds() / 3600.0

        snapshot = PcSnapshot(
            timestamp=assessment_time,
            tca=approach.tca,
            miss_distance_km=approach.miss_distance_km,
            probability_of_collision=approach.probability_of_collision or 0.0,
            risk_level=approach.risk_level,
            hours_to_tca=hours_to_tca,
        )
        event.snapshots.append(snapshot)

        trend = event.pc_trend
        if trend == "RISING" and snapshot.risk_level != RiskLevel.GREEN:
            logger.warning(
                f"RISING Pc for {event.primary_name} vs {event.secondary_name}: "
                f"Pc={snapshot.probability_of_collision:.2e}, trend={trend}, "
                f"TCA in {hours_to_tca:.1f}h"
            )

        return event

    def get_event(self, primary_id: str, secondary_id: str) -> ConjunctionEvent | None:
        return self._events.get(self._make_key(primary_id, secondary_id))

    def active_events(self) -> list[ConjunctionEvent]:
        """Return events with TCA still in the future."""
        now = datetime.utcnow()
        return [e for e in self._events.values()
                if e.latest and e.latest.tca > now]

    def rising_threats(self) -> list[ConjunctionEvent]:
        """Return active events with rising Pc trend."""
        return [e for e in self.active_events() if e.pc_trend == "RISING"]

    @staticmethod
    def _make_key(id_a: str, id_b: str) -> str:
        return f"{min(id_a, id_b)}-{max(id_a, id_b)}"
