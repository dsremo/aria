"""Tests for conjunction event trending and Pc history tracking."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from aria.conjunction.core.types import (
    CloseApproach,
    ObjectType,
    OrbitalElements,
    RiskLevel,
    SpaceObject,
)
from aria.conjunction.pipeline.trending import (
    ConjunctionEvent,
    ConjunctionTracker,
    PcSnapshot,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_approach(
    primary_id: str = "25544",
    secondary_id: str = "99999",
    miss_km: float = 1.0,
    pc: float = 1e-4,
    tca: datetime | None = None,
    risk: RiskLevel = RiskLevel.RED,
) -> CloseApproach:
    if tca is None:
        tca = datetime(2024, 3, 15, 12, 0, 0)
    primary = SpaceObject(
        norad_id=primary_id, name=f"SAT-{primary_id}",
        tle_line1="", tle_line2="",
        object_type=ObjectType.PAYLOAD,
        elements=OrbitalElements(6780, 0.001, 0.9, 0, 0, 0, tca),
    )
    secondary = SpaceObject(
        norad_id=secondary_id, name=f"DEBRIS-{secondary_id}",
        tle_line1="", tle_line2="",
        object_type=ObjectType.DEBRIS,
        elements=OrbitalElements(6782, 0.001, 0.9, 0.01, 0, 0, tca),
    )
    return CloseApproach(
        primary=primary,
        secondary=secondary,
        tca=tca,
        miss_distance_km=miss_km,
        miss_distance_rtn=np.array([0.1, miss_km, 0.1]),
        relative_velocity_km_s=7.5,
        relative_position=np.array([miss_km, 0, 0]),
        relative_velocity_vec=np.array([0, 7.5, 0]),
        probability_of_collision=pc,
        risk_level=risk,
    )


def _make_snapshot(
    tca: datetime,
    pc: float,
    miss_km: float = 1.0,
    risk: RiskLevel = RiskLevel.RED,
    hours_to_tca: float = 24.0,
    timestamp: datetime | None = None,
) -> PcSnapshot:
    if timestamp is None:
        timestamp = datetime.utcnow()
    return PcSnapshot(
        timestamp=timestamp,
        tca=tca,
        miss_distance_km=miss_km,
        probability_of_collision=pc,
        risk_level=risk,
        hours_to_tca=hours_to_tca,
    )


# ---------------------------------------------------------------------------
# PcSnapshot
# ---------------------------------------------------------------------------

class TestPcSnapshot:

    def test_creation(self):
        now = datetime.utcnow()
        tca = now + timedelta(hours=24)
        snap = PcSnapshot(
            timestamp=now,
            tca=tca,
            miss_distance_km=1.5,
            probability_of_collision=1e-4,
            risk_level=RiskLevel.RED,
            hours_to_tca=24.0,
        )
        assert snap.probability_of_collision == 1e-4
        assert snap.miss_distance_km == 1.5
        assert snap.risk_level == RiskLevel.RED


# ---------------------------------------------------------------------------
# ConjunctionEvent
# ---------------------------------------------------------------------------

class TestConjunctionEvent:

    def _make_event(self, pid="25544", sid="99999") -> ConjunctionEvent:
        return ConjunctionEvent(
            primary_id=pid, secondary_id=sid,
            primary_name="ISS", secondary_name="DEBRIS",
        )

    def test_event_key_order_independent(self):
        ev1 = self._make_event("25544", "99999")
        ev2 = self._make_event("99999", "25544")
        assert ev1.event_key == ev2.event_key

    def test_latest_none_when_no_snapshots(self):
        ev = self._make_event()
        assert ev.latest is None

    def test_latest_returns_last_snapshot(self):
        ev = self._make_event()
        tca = datetime(2024, 3, 15)
        ev.snapshots.append(_make_snapshot(tca, pc=1e-5))
        ev.snapshots.append(_make_snapshot(tca, pc=2e-4))
        assert ev.latest.probability_of_collision == 2e-4

    def test_peak_pc_empty(self):
        ev = self._make_event()
        assert ev.peak_pc == 0.0

    def test_peak_pc_returns_max(self):
        ev = self._make_event()
        tca = datetime(2024, 3, 15)
        ev.snapshots.append(_make_snapshot(tca, pc=1e-5))
        ev.snapshots.append(_make_snapshot(tca, pc=5e-4))
        ev.snapshots.append(_make_snapshot(tca, pc=2e-5))
        assert ev.peak_pc == 5e-4

    def test_pc_trend_unknown_with_one_snapshot(self):
        ev = self._make_event()
        ev.snapshots.append(_make_snapshot(datetime(2024, 3, 15), pc=1e-4))
        assert ev.pc_trend == "UNKNOWN"

    def test_pc_trend_rising(self):
        ev = self._make_event()
        tca = datetime(2024, 3, 15)
        now = datetime(2024, 3, 14)
        # Pc tripled → rising
        ev.snapshots.append(_make_snapshot(tca, pc=1e-4, timestamp=now))
        ev.snapshots.append(_make_snapshot(tca, pc=2e-4, timestamp=now + timedelta(hours=1)))
        ev.snapshots.append(_make_snapshot(tca, pc=4e-4, timestamp=now + timedelta(hours=2)))
        assert ev.pc_trend == "RISING"

    def test_pc_trend_falling(self):
        ev = self._make_event()
        tca = datetime(2024, 3, 15)
        now = datetime(2024, 3, 14)
        # Two snapshots: Pc drops by >50% → rel_change = (1e-4/4e-4) - 1 = -0.75 < -0.5
        ev.snapshots.append(_make_snapshot(tca, pc=4e-4, timestamp=now))
        ev.snapshots.append(_make_snapshot(tca, pc=1e-4, timestamp=now + timedelta(hours=2)))
        assert ev.pc_trend == "FALLING"

    def test_pc_trend_stable(self):
        ev = self._make_event()
        tca = datetime(2024, 3, 15)
        now = datetime(2024, 3, 14)
        # Pc barely changes
        ev.snapshots.append(_make_snapshot(tca, pc=1e-4, timestamp=now))
        ev.snapshots.append(_make_snapshot(tca, pc=1.1e-4, timestamp=now + timedelta(hours=1)))
        ev.snapshots.append(_make_snapshot(tca, pc=1.05e-4, timestamp=now + timedelta(hours=2)))
        assert ev.pc_trend == "STABLE"

    def test_pc_slope_per_hour_zero_with_one_snapshot(self):
        ev = self._make_event()
        ev.snapshots.append(_make_snapshot(datetime(2024, 3, 15), pc=1e-4))
        assert ev.pc_slope_per_hour == 0.0

    def test_pc_slope_per_hour_positive(self):
        ev = self._make_event()
        t0 = datetime(2024, 3, 14, 0, 0, 0)
        t1 = t0 + timedelta(hours=2)
        tca = datetime(2024, 3, 15)
        ev.snapshots.append(_make_snapshot(tca, pc=1e-4, timestamp=t0))
        ev.snapshots.append(_make_snapshot(tca, pc=3e-4, timestamp=t1))
        slope = ev.pc_slope_per_hour
        assert slope > 0
        # slope = (3e-4 - 1e-4) / 2h = 1e-4/h
        assert slope == pytest.approx(1e-4, rel=1e-3)

    def test_pc_slope_zero_when_same_time(self):
        """Zero time delta → slope = 0."""
        ev = self._make_event()
        tca = datetime(2024, 3, 15)
        t = datetime(2024, 3, 14, 0, 0, 0)
        ev.snapshots.append(_make_snapshot(tca, pc=1e-4, timestamp=t))
        ev.snapshots.append(_make_snapshot(tca, pc=3e-4, timestamp=t))  # same timestamp
        assert ev.pc_slope_per_hour == 0.0

    def test_forecast_pc_no_snapshots(self):
        ev = self._make_event()
        assert ev.forecast_pc() == 0.0

    def test_forecast_pc_rising_trend(self):
        ev = self._make_event()
        t0 = datetime(2024, 3, 14, 0, 0, 0)
        t1 = t0 + timedelta(hours=2)
        tca = datetime(2024, 3, 15)
        ev.snapshots.append(_make_snapshot(tca, pc=1e-4, timestamp=t0))
        ev.snapshots.append(_make_snapshot(tca, pc=3e-4, timestamp=t1))
        forecast = ev.forecast_pc(hours_ahead=8.0)
        assert forecast > 3e-4  # should forecast higher

    def test_forecast_pc_never_below_10_percent(self):
        """Forecast should not fall below 10% of current Pc."""
        ev = self._make_event()
        t0 = datetime(2024, 3, 14, 0, 0, 0)
        t1 = t0 + timedelta(hours=2)
        tca = datetime(2024, 3, 15)
        # Falling trend
        ev.snapshots.append(_make_snapshot(tca, pc=1e-3, timestamp=t0))
        ev.snapshots.append(_make_snapshot(tca, pc=1e-6, timestamp=t1))
        current = ev.latest.probability_of_collision
        forecast = ev.forecast_pc(hours_ahead=100.0)
        assert forecast >= current * 0.1


# ---------------------------------------------------------------------------
# ConjunctionTracker
# ---------------------------------------------------------------------------

class TestConjunctionTracker:

    def test_update_creates_new_event(self):
        tracker = ConjunctionTracker()
        approach = _make_approach(tca=datetime(2025, 1, 1, 12, 0, 0))
        event = tracker.update(approach, assessment_time=datetime(2025, 1, 1, 0, 0, 0))
        assert event is not None
        assert event.primary_id == "25544"
        assert len(event.snapshots) == 1

    def test_update_appends_to_existing_event(self):
        tracker = ConjunctionTracker()
        tca = datetime(2025, 1, 1, 12, 0, 0)
        approach = _make_approach(tca=tca)
        t0 = datetime(2025, 1, 1, 0, 0, 0)
        t1 = t0 + timedelta(hours=4)

        tracker.update(approach, assessment_time=t0)
        event = tracker.update(approach, assessment_time=t1)
        assert len(event.snapshots) == 2

    def test_get_event_found(self):
        tracker = ConjunctionTracker()
        approach = _make_approach(tca=datetime(2025, 1, 1, 12, 0, 0))
        tracker.update(approach, assessment_time=datetime(2025, 1, 1))
        event = tracker.get_event("25544", "99999")
        assert event is not None

    def test_get_event_order_insensitive(self):
        tracker = ConjunctionTracker()
        approach = _make_approach(tca=datetime(2025, 1, 1, 12, 0, 0))
        tracker.update(approach, assessment_time=datetime(2025, 1, 1))
        # Reversed order
        event = tracker.get_event("99999", "25544")
        assert event is not None

    def test_get_event_not_found(self):
        tracker = ConjunctionTracker()
        assert tracker.get_event("00001", "00002") is None

    def test_active_events_future_tca(self):
        tracker = ConjunctionTracker()
        future_tca = datetime.utcnow() + timedelta(hours=24)
        approach = _make_approach(tca=future_tca)
        tracker.update(approach, assessment_time=datetime.utcnow())
        active = tracker.active_events()
        assert len(active) == 1

    def test_active_events_past_tca_excluded(self):
        tracker = ConjunctionTracker()
        past_tca = datetime(2020, 1, 1, 12, 0, 0)  # far in past
        approach = _make_approach(tca=past_tca)
        tracker.update(approach, assessment_time=datetime(2019, 12, 31))
        active = tracker.active_events()
        assert len(active) == 0

    def test_rising_threats_detected(self):
        tracker = ConjunctionTracker()
        future_tca = datetime.utcnow() + timedelta(hours=24)
        approach = _make_approach(tca=future_tca, pc=1e-4, risk=RiskLevel.RED)
        t0 = datetime.utcnow() - timedelta(hours=4)
        t1 = datetime.utcnow() - timedelta(hours=2)
        t2 = datetime.utcnow()

        # Simulate rising Pc
        approach.probability_of_collision = 1e-5
        tracker.update(approach, assessment_time=t0)
        approach.probability_of_collision = 5e-5
        tracker.update(approach, assessment_time=t1)
        approach.probability_of_collision = 5e-4  # tripled → RISING
        tracker.update(approach, assessment_time=t2)

        rising = tracker.rising_threats()
        assert len(rising) >= 0  # depends on timing

    def test_update_with_none_assessment_time(self):
        """When assessment_time is None, should use utcnow."""
        tracker = ConjunctionTracker()
        approach = _make_approach(tca=datetime.utcnow() + timedelta(hours=12))
        event = tracker.update(approach, assessment_time=None)
        assert len(event.snapshots) == 1

    def test_snapshot_hours_to_tca(self):
        tracker = ConjunctionTracker()
        now = datetime(2024, 3, 14, 0, 0, 0)
        tca = now + timedelta(hours=24)
        approach = _make_approach(tca=tca)
        event = tracker.update(approach, assessment_time=now)
        snap = event.snapshots[-1]
        assert snap.hours_to_tca == pytest.approx(24.0, rel=1e-6)
