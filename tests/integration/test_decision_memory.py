"""Integration tests for the Agent Decision Memory system.

Tests cover:
  - DecisionRecord creation and retrieval
  - Outcome updates and pattern rebuilding
  - Pattern aggregation correctness
  - Aging / exponential decay weighting
  - DecisionRecommender ranking and confidence
  - Statistics computation (by type, subsystem, severity)
  - Pruning old records
  - Edge cases: no data, single record, all failures
  - Async wrappers
  - Multi-subsystem interaction
"""

from __future__ import annotations

import asyncio
import math
import time

import pytest

from aria.cognitive.decision_memory import (
    DecisionMemory,
    DecisionPattern,
    DecisionRecord,
    DecisionRecommender,
    DecisionType,
    Outcome,
    Recommendation,
)
from aria.db.persistence import PersistenceManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pm() -> PersistenceManager:
    """In-memory PersistenceManager for test isolation."""
    p = PersistenceManager(":memory:")
    p.init_db()
    return p


@pytest.fixture
def dm(pm: PersistenceManager) -> DecisionMemory:
    """DecisionMemory wired to the in-memory DB."""
    d = DecisionMemory(pm)
    d.init_schema()
    return d


@pytest.fixture
def recommender(dm: DecisionMemory) -> DecisionRecommender:
    return DecisionRecommender(dm)


def _seed_battery_low_decisions(dm: DecisionMemory, count: int = 5) -> list[str]:
    """Helper: seed several battery_low decisions with known outcomes."""
    ids: list[str] = []
    for i in range(count):
        rid = dm.record_decision(
            subsystem="power",
            decision_type=DecisionType.LOAD_SHED.value,
            trigger="battery_low",
            action="shed_science_loads",
            mission_time_s=float(i * 3600),
            severity="WARNING",
            context={"soc": 18.0 - i, "in_eclipse": i % 2 == 0},
            confidence=0.9,
        )
        ids.append(rid)
    return ids


# ---------------------------------------------------------------------------
# Basic recording and retrieval
# ---------------------------------------------------------------------------

class TestRecordDecision:
    def test_record_returns_id(self, dm: DecisionMemory) -> None:
        rid = dm.record_decision(
            subsystem="power", decision_type="load_shed",
            trigger="battery_low", action="shed_science_loads",
            mission_time_s=1000.0,
        )
        assert isinstance(rid, str)
        assert len(rid) == 32  # uuid4 hex

    def test_record_retrievable(self, dm: DecisionMemory) -> None:
        rid = dm.record_decision(
            subsystem="thermal", decision_type="anomaly_response",
            trigger="radiator_overheat", action="increase_coolant_flow",
            mission_time_s=5000.0, severity="CRITICAL",
            context={"temp_c": 85.0}, confidence=0.95, notes="first occurrence",
        )
        rec = dm.get_record(rid)
        assert rec is not None
        assert rec.subsystem == "thermal"
        assert rec.trigger == "radiator_overheat"
        assert rec.action == "increase_coolant_flow"
        assert rec.severity == "CRITICAL"
        assert rec.confidence == 0.95
        assert rec.context == {"temp_c": 85.0}
        assert rec.outcome == Outcome.PENDING.value
        assert rec.notes == "first occurrence"

    def test_record_default_outcome_is_pending(self, dm: DecisionMemory) -> None:
        rid = dm.record_decision(
            subsystem="power", decision_type="load_shed",
            trigger="battery_low", action="shed_science_loads",
            mission_time_s=1000.0,
        )
        rec = dm.get_record(rid)
        assert rec is not None
        assert rec.outcome == "pending"

    def test_record_count(self, dm: DecisionMemory) -> None:
        assert dm.get_record_count() == 0
        _seed_battery_low_decisions(dm, 3)
        assert dm.get_record_count() == 3

    def test_nonexistent_record_returns_none(self, dm: DecisionMemory) -> None:
        assert dm.get_record("nonexistent_id") is None


# ---------------------------------------------------------------------------
# Outcome updates
# ---------------------------------------------------------------------------

class TestUpdateOutcome:
    def test_update_success(self, dm: DecisionMemory) -> None:
        rid = dm.record_decision(
            subsystem="power", decision_type="load_shed",
            trigger="battery_low", action="shed_science_loads",
            mission_time_s=1000.0,
        )
        updated = dm.update_outcome(rid, Outcome.SUCCESS, resolution_time_s=120.0)
        assert updated is True

        rec = dm.get_record(rid)
        assert rec is not None
        assert rec.outcome == "success"
        assert rec.resolution_time_s == 120.0

    def test_update_failure(self, dm: DecisionMemory) -> None:
        rid = dm.record_decision(
            subsystem="eclss", decision_type="anomaly_response",
            trigger="co2_high", action="increase_scrubber_rate",
            mission_time_s=2000.0,
        )
        dm.update_outcome(rid, Outcome.FAILURE, notes="scrubber was offline")
        rec = dm.get_record(rid)
        assert rec is not None
        assert rec.outcome == "failure"
        assert rec.notes == "scrubber was offline"

    def test_update_nonexistent_returns_false(self, dm: DecisionMemory) -> None:
        assert dm.update_outcome("bogus_id", Outcome.SUCCESS) is False

    def test_update_rebuilds_pattern(self, dm: DecisionMemory) -> None:
        rid = dm.record_decision(
            subsystem="power", decision_type="load_shed",
            trigger="battery_low", action="shed_science_loads",
            mission_time_s=1000.0,
        )
        dm.update_outcome(rid, Outcome.SUCCESS, resolution_time_s=60.0)

        pattern = dm.get_pattern("power", "battery_low", "shed_science_loads", "load_shed")
        assert pattern is not None
        assert pattern.success_count == 1
        assert pattern.total_count == 1


# ---------------------------------------------------------------------------
# Querying records
# ---------------------------------------------------------------------------

class TestQueryRecords:
    def test_query_by_subsystem(self, dm: DecisionMemory) -> None:
        dm.record_decision(subsystem="power", decision_type="load_shed",
                           trigger="battery_low", action="shed", mission_time_s=100)
        dm.record_decision(subsystem="thermal", decision_type="anomaly_response",
                           trigger="overheat", action="cool", mission_time_s=200)

        power_recs = dm.query_records(subsystem="power")
        assert len(power_recs) == 1
        assert power_recs[0].subsystem == "power"

    def test_query_by_trigger(self, dm: DecisionMemory) -> None:
        _seed_battery_low_decisions(dm, 4)
        dm.record_decision(subsystem="power", decision_type="anomaly_response",
                           trigger="bus_undervoltage", action="check_regulators",
                           mission_time_s=50000)

        recs = dm.query_records(trigger="battery_low")
        assert len(recs) == 4

    def test_query_ordered_by_mission_time_desc(self, dm: DecisionMemory) -> None:
        dm.record_decision(subsystem="power", decision_type="load_shed",
                           trigger="t", action="a", mission_time_s=100)
        dm.record_decision(subsystem="power", decision_type="load_shed",
                           trigger="t", action="a", mission_time_s=300)
        dm.record_decision(subsystem="power", decision_type="load_shed",
                           trigger="t", action="a", mission_time_s=200)

        recs = dm.query_records(subsystem="power")
        times = [r.mission_time_s for r in recs]
        assert times == [300.0, 200.0, 100.0]

    def test_query_with_limit(self, dm: DecisionMemory) -> None:
        _seed_battery_low_decisions(dm, 10)
        recs = dm.query_records(trigger="battery_low", limit=3)
        assert len(recs) == 3

    def test_find_similar(self, dm: DecisionMemory) -> None:
        _seed_battery_low_decisions(dm, 5)
        similar = dm.find_similar("power", "battery_low", limit=3)
        assert len(similar) == 3
        assert all(r.trigger == "battery_low" for r in similar)


# ---------------------------------------------------------------------------
# Pattern aggregation
# ---------------------------------------------------------------------------

class TestPatterns:
    def test_pattern_created_on_outcome_update(self, dm: DecisionMemory) -> None:
        ids = _seed_battery_low_decisions(dm, 3)
        dm.update_outcome(ids[0], Outcome.SUCCESS, resolution_time_s=60.0)
        dm.update_outcome(ids[1], Outcome.SUCCESS, resolution_time_s=120.0)
        dm.update_outcome(ids[2], Outcome.FAILURE, resolution_time_s=300.0)

        pattern = dm.get_pattern("power", "battery_low", "shed_science_loads", "load_shed")
        assert pattern is not None
        assert pattern.total_count == 3
        assert pattern.success_count == 2
        assert pattern.failure_count == 1
        assert pattern.avg_resolution_time_s == pytest.approx(160.0, rel=0.01)

    def test_pattern_success_rate(self, dm: DecisionMemory) -> None:
        ids = _seed_battery_low_decisions(dm, 4)
        dm.update_outcome(ids[0], Outcome.SUCCESS)
        dm.update_outcome(ids[1], Outcome.SUCCESS)
        dm.update_outcome(ids[2], Outcome.PARTIAL)
        dm.update_outcome(ids[3], Outcome.FAILURE)

        pattern = dm.get_pattern("power", "battery_low", "shed_science_loads", "load_shed")
        assert pattern is not None
        # success_rate: 2 / (2 + 1 + 1) = 0.5
        assert pattern.success_rate == pytest.approx(0.5)
        # effectiveness: (2 + 0.5*1) / 4 = 0.625
        assert pattern.effectiveness_score == pytest.approx(0.625)

    def test_pattern_effectiveness_all_success(self, dm: DecisionMemory) -> None:
        ids = _seed_battery_low_decisions(dm, 3)
        for rid in ids:
            dm.update_outcome(rid, Outcome.SUCCESS, resolution_time_s=30.0)

        pattern = dm.get_pattern("power", "battery_low", "shed_science_loads", "load_shed")
        assert pattern is not None
        assert pattern.effectiveness_score == pytest.approx(1.0)

    def test_get_patterns_for_trigger(self, dm: DecisionMemory) -> None:
        # Two different actions for the same trigger
        r1 = dm.record_decision(subsystem="power", decision_type="load_shed",
                                trigger="battery_low", action="shed_science",
                                mission_time_s=100)
        r2 = dm.record_decision(subsystem="power", decision_type="load_shed",
                                trigger="battery_low", action="shed_crew_quarters",
                                mission_time_s=200)
        dm.update_outcome(r1, Outcome.SUCCESS)
        dm.update_outcome(r2, Outcome.FAILURE)

        patterns = dm.get_patterns_for_trigger("power", "battery_low")
        assert len(patterns) == 2
        actions = {p.action for p in patterns}
        assert actions == {"shed_science", "shed_crew_quarters"}

    def test_get_all_patterns(self, dm: DecisionMemory) -> None:
        r1 = dm.record_decision(subsystem="power", decision_type="load_shed",
                                trigger="battery_low", action="shed",
                                mission_time_s=100)
        r2 = dm.record_decision(subsystem="thermal", decision_type="anomaly_response",
                                trigger="overheat", action="cool",
                                mission_time_s=200)
        dm.update_outcome(r1, Outcome.SUCCESS)
        dm.update_outcome(r2, Outcome.SUCCESS)

        all_patterns = dm.get_all_patterns()
        assert len(all_patterns) == 2

        power_only = dm.get_all_patterns(subsystem="power")
        assert len(power_only) == 1

    def test_rebuild_all_patterns(self, dm: DecisionMemory) -> None:
        ids = _seed_battery_low_decisions(dm, 3)
        for rid in ids:
            dm.update_outcome(rid, Outcome.SUCCESS, resolution_time_s=50.0)

        count = dm.rebuild_all_patterns(current_mission_time_s=20000.0)
        assert count >= 1

        pattern = dm.get_pattern("power", "battery_low", "shed_science_loads", "load_shed")
        assert pattern is not None
        assert pattern.weighted_success_rate > 0

    def test_pattern_count(self, dm: DecisionMemory) -> None:
        assert dm.get_pattern_count() == 0
        r1 = dm.record_decision(subsystem="power", decision_type="load_shed",
                                trigger="battery_low", action="shed",
                                mission_time_s=100)
        dm.update_outcome(r1, Outcome.SUCCESS)
        assert dm.get_pattern_count() == 1


# ---------------------------------------------------------------------------
# Aging / exponential decay
# ---------------------------------------------------------------------------

class TestAging:
    def test_recent_decisions_weighted_higher(self, dm: DecisionMemory) -> None:
        """A recent success should outweigh an old failure."""
        # Old failure at t=0
        r1 = dm.record_decision(subsystem="power", decision_type="load_shed",
                                trigger="battery_low", action="shed",
                                mission_time_s=0.0)
        dm.update_outcome(r1, Outcome.FAILURE)

        # Recent success at t=60 days
        sixty_days_s = 60 * 24 * 3600.0
        r2 = dm.record_decision(subsystem="power", decision_type="load_shed",
                                trigger="battery_low", action="shed",
                                mission_time_s=sixty_days_s)
        dm.update_outcome(r2, Outcome.SUCCESS)

        # Rebuild with current time at 61 days
        current = 61 * 24 * 3600.0
        dm.rebuild_all_patterns(current_mission_time_s=current)

        pattern = dm.get_pattern("power", "battery_low", "shed", "load_shed")
        assert pattern is not None
        # The weighted rate should be closer to 1.0 than 0.5 because
        # the success is recent and the failure is old
        assert pattern.weighted_success_rate > 0.5

    def test_aging_with_same_age_equals_raw_rate(self, dm: DecisionMemory) -> None:
        """If all decisions are at the same time, weighted = raw."""
        for i in range(4):
            r = dm.record_decision(subsystem="power", decision_type="load_shed",
                                   trigger="x", action="y",
                                   mission_time_s=1000.0)
            if i < 2:
                dm.update_outcome(r, Outcome.SUCCESS)
            else:
                dm.update_outcome(r, Outcome.FAILURE)

        dm.rebuild_all_patterns(current_mission_time_s=1000.0)
        pattern = dm.get_pattern("power", "x", "y", "load_shed")
        assert pattern is not None
        assert pattern.weighted_success_rate == pytest.approx(0.5, abs=0.01)


# ---------------------------------------------------------------------------
# Recommender
# ---------------------------------------------------------------------------

class TestRecommender:
    def test_recommend_returns_sorted_by_confidence(
        self, dm: DecisionMemory, recommender: DecisionRecommender,
    ) -> None:
        # Good action
        for _ in range(5):
            r = dm.record_decision(subsystem="power", decision_type="load_shed",
                                   trigger="battery_low", action="shed_science",
                                   mission_time_s=1000.0)
            dm.update_outcome(r, Outcome.SUCCESS, resolution_time_s=60.0)

        # Bad action
        for _ in range(5):
            r = dm.record_decision(subsystem="power", decision_type="load_shed",
                                   trigger="battery_low", action="do_nothing",
                                   mission_time_s=1000.0)
            dm.update_outcome(r, Outcome.FAILURE)

        recs = recommender.recommend("power", "battery_low")
        assert len(recs) == 2
        assert recs[0].action == "shed_science"
        assert recs[0].confidence > recs[1].confidence

    def test_recommend_empty_when_no_data(
        self, dm: DecisionMemory, recommender: DecisionRecommender,
    ) -> None:
        recs = recommender.recommend("power", "battery_low")
        assert recs == []

    def test_get_best_action(
        self, dm: DecisionMemory, recommender: DecisionRecommender,
    ) -> None:
        for _ in range(3):
            r = dm.record_decision(subsystem="power", decision_type="load_shed",
                                   trigger="battery_low", action="shed_science",
                                   mission_time_s=1000.0)
            dm.update_outcome(r, Outcome.SUCCESS, resolution_time_s=45.0)

        best = recommender.get_best_action("power", "battery_low")
        assert best is not None
        assert best.action == "shed_science"
        assert best.success_rate == pytest.approx(1.0)

    def test_get_best_action_none_when_empty(
        self, dm: DecisionMemory, recommender: DecisionRecommender,
    ) -> None:
        assert recommender.get_best_action("power", "battery_low") is None

    def test_recommendation_has_reasoning(
        self, dm: DecisionMemory, recommender: DecisionRecommender,
    ) -> None:
        r = dm.record_decision(subsystem="power", decision_type="load_shed",
                               trigger="battery_low", action="shed_science",
                               mission_time_s=1000.0)
        dm.update_outcome(r, Outcome.SUCCESS, resolution_time_s=30.0)

        recs = recommender.recommend("power", "battery_low")
        assert len(recs) == 1
        assert "shed_science" in recs[0].reasoning
        assert "battery_low" in recs[0].reasoning

    def test_actions_to_avoid(
        self, dm: DecisionMemory, recommender: DecisionRecommender,
    ) -> None:
        for _ in range(5):
            r = dm.record_decision(subsystem="power", decision_type="load_shed",
                                   trigger="battery_low", action="ignore_alarm",
                                   mission_time_s=1000.0)
            dm.update_outcome(r, Outcome.FAILURE)

        avoid = recommender.get_actions_to_avoid("power", "battery_low")
        assert len(avoid) == 1
        assert avoid[0].action == "ignore_alarm"
        assert avoid[0].success_rate == 0.0

    def test_recommend_with_mission_time_aging(
        self, dm: DecisionMemory, recommender: DecisionRecommender,
    ) -> None:
        # Old failures
        for i in range(3):
            r = dm.record_decision(subsystem="power", decision_type="load_shed",
                                   trigger="battery_low", action="shed_science",
                                   mission_time_s=float(i * 100))
            dm.update_outcome(r, Outcome.FAILURE)

        # Recent successes
        recent_t = 90 * 24 * 3600.0
        for i in range(3):
            r = dm.record_decision(subsystem="power", decision_type="load_shed",
                                   trigger="battery_low", action="shed_science",
                                   mission_time_s=recent_t + i * 100)
            dm.update_outcome(r, Outcome.SUCCESS, resolution_time_s=30.0)

        recs = recommender.recommend(
            "power", "battery_low",
            current_mission_time_s=recent_t + 1000,
        )
        assert len(recs) >= 1
        # After aging, the recent successes should dominate
        assert recs[0].action == "shed_science"


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class TestStatistics:
    def test_statistics_by_type(self, dm: DecisionMemory) -> None:
        r1 = dm.record_decision(subsystem="power", decision_type="load_shed",
                                trigger="battery_low", action="shed",
                                mission_time_s=100, severity="WARNING")
        r2 = dm.record_decision(subsystem="power", decision_type="anomaly_response",
                                trigger="bus_uv", action="check",
                                mission_time_s=200, severity="CRITICAL")
        dm.update_outcome(r1, Outcome.SUCCESS, resolution_time_s=60.0)
        dm.update_outcome(r2, Outcome.FAILURE, resolution_time_s=300.0)

        stats = dm.get_statistics()
        assert stats["total_resolved"] == 2
        assert "load_shed" in stats["by_decision_type"]
        assert stats["by_decision_type"]["load_shed"]["success_rate"] == pytest.approx(1.0)
        assert stats["by_decision_type"]["anomaly_response"]["success_rate"] == pytest.approx(0.0)

    def test_statistics_by_subsystem(self, dm: DecisionMemory) -> None:
        r1 = dm.record_decision(subsystem="power", decision_type="load_shed",
                                trigger="x", action="y", mission_time_s=100)
        r2 = dm.record_decision(subsystem="thermal", decision_type="anomaly_response",
                                trigger="z", action="w", mission_time_s=200)
        dm.update_outcome(r1, Outcome.SUCCESS)
        dm.update_outcome(r2, Outcome.SUCCESS)

        stats = dm.get_statistics()
        assert "power" in stats["by_subsystem"]
        assert "thermal" in stats["by_subsystem"]

    def test_statistics_by_severity(self, dm: DecisionMemory) -> None:
        r1 = dm.record_decision(subsystem="power", decision_type="load_shed",
                                trigger="x", action="y", mission_time_s=100,
                                severity="WARNING")
        r2 = dm.record_decision(subsystem="power", decision_type="load_shed",
                                trigger="x", action="y", mission_time_s=200,
                                severity="CRITICAL")
        dm.update_outcome(r1, Outcome.SUCCESS)
        dm.update_outcome(r2, Outcome.FAILURE)

        stats = dm.get_statistics()
        assert stats["by_severity"]["WARNING"]["success_rate"] == pytest.approx(1.0)
        assert stats["by_severity"]["CRITICAL"]["success_rate"] == pytest.approx(0.0)

    def test_statistics_filtered_by_subsystem(self, dm: DecisionMemory) -> None:
        r1 = dm.record_decision(subsystem="power", decision_type="load_shed",
                                trigger="x", action="y", mission_time_s=100)
        r2 = dm.record_decision(subsystem="thermal", decision_type="anomaly_response",
                                trigger="z", action="w", mission_time_s=200)
        dm.update_outcome(r1, Outcome.SUCCESS)
        dm.update_outcome(r2, Outcome.FAILURE)

        stats = dm.get_statistics(subsystem="power")
        assert stats["total_resolved"] == 1
        assert "thermal" not in stats["by_subsystem"]

    def test_statistics_exclude_pending(self, dm: DecisionMemory) -> None:
        dm.record_decision(subsystem="power", decision_type="load_shed",
                           trigger="x", action="y", mission_time_s=100)
        # No outcome update — stays pending

        stats = dm.get_statistics()
        assert stats["total_resolved"] == 0


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------

class TestPruning:
    def test_prune_removes_oldest(self, dm: DecisionMemory) -> None:
        for i in range(10):
            dm.record_decision(subsystem="power", decision_type="load_shed",
                               trigger="x", action="y", mission_time_s=float(i * 100))

        assert dm.get_record_count() == 10
        deleted = dm.prune_old_records(keep_count=5)
        assert deleted == 5
        assert dm.get_record_count() == 5

        # Verify oldest are gone — remaining should be mission_time >= 500
        recs = dm.query_records(limit=100)
        times = sorted(r.mission_time_s for r in recs)
        assert times[0] >= 500.0

    def test_prune_noop_when_under_limit(self, dm: DecisionMemory) -> None:
        _seed_battery_low_decisions(dm, 3)
        deleted = dm.prune_old_records(keep_count=10)
        assert deleted == 0
        assert dm.get_record_count() == 3


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------

class TestAsync:
    def test_async_init_schema(self, pm: PersistenceManager) -> None:
        dm = DecisionMemory(pm)
        asyncio.get_event_loop().run_until_complete(dm.async_init_schema())
        # Should be able to record after async init
        rid = dm.record_decision(subsystem="power", decision_type="load_shed",
                                 trigger="x", action="y", mission_time_s=100)
        assert rid

    def test_async_record_decision(self, dm: DecisionMemory) -> None:
        loop = asyncio.get_event_loop()
        rid = loop.run_until_complete(dm.async_record_decision(
            subsystem="power", decision_type="load_shed",
            trigger="battery_low", action="shed_science",
            mission_time_s=1000.0,
        ))
        assert isinstance(rid, str)
        assert dm.get_record(rid) is not None

    def test_async_update_outcome(self, dm: DecisionMemory) -> None:
        rid = dm.record_decision(subsystem="power", decision_type="load_shed",
                                 trigger="x", action="y", mission_time_s=100)
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            dm.async_update_outcome(rid, Outcome.SUCCESS, resolution_time_s=30.0),
        )
        assert result is True
        assert dm.get_record(rid).outcome == "success"

    def test_async_query_records(self, dm: DecisionMemory) -> None:
        _seed_battery_low_decisions(dm, 3)
        loop = asyncio.get_event_loop()
        recs = loop.run_until_complete(dm.async_query_records(subsystem="power"))
        assert len(recs) == 3

    def test_async_get_statistics(self, dm: DecisionMemory) -> None:
        r = dm.record_decision(subsystem="power", decision_type="load_shed",
                               trigger="x", action="y", mission_time_s=100)
        dm.update_outcome(r, Outcome.SUCCESS)
        loop = asyncio.get_event_loop()
        stats = loop.run_until_complete(dm.async_get_statistics())
        assert stats["total_resolved"] == 1

    def test_async_recommend(self, dm: DecisionMemory) -> None:
        r = dm.record_decision(subsystem="power", decision_type="load_shed",
                               trigger="battery_low", action="shed",
                               mission_time_s=100)
        dm.update_outcome(r, Outcome.SUCCESS, resolution_time_s=30.0)

        recommender = DecisionRecommender(dm)
        loop = asyncio.get_event_loop()
        recs = loop.run_until_complete(
            recommender.async_recommend(subsystem="power", trigger="battery_low"),
        )
        assert len(recs) == 1


# ---------------------------------------------------------------------------
# Multi-subsystem / cross-agent
# ---------------------------------------------------------------------------

class TestMultiSubsystem:
    def test_patterns_isolated_by_subsystem(self, dm: DecisionMemory) -> None:
        """Patterns for power.battery_low should not mix with thermal.battery_low."""
        r1 = dm.record_decision(subsystem="power", decision_type="load_shed",
                                trigger="battery_low", action="shed",
                                mission_time_s=100)
        r2 = dm.record_decision(subsystem="thermal", decision_type="anomaly_response",
                                trigger="battery_low", action="cool",
                                mission_time_s=200)
        dm.update_outcome(r1, Outcome.SUCCESS)
        dm.update_outcome(r2, Outcome.FAILURE)

        power_patterns = dm.get_patterns_for_trigger("power", "battery_low")
        assert len(power_patterns) == 1
        assert power_patterns[0].action == "shed"

        thermal_patterns = dm.get_patterns_for_trigger("thermal", "battery_low")
        assert len(thermal_patterns) == 1
        assert thermal_patterns[0].action == "cool"

    def test_statistics_global_includes_all(self, dm: DecisionMemory) -> None:
        for sub in ["power", "thermal", "eclss"]:
            r = dm.record_decision(subsystem=sub, decision_type="anomaly_response",
                                   trigger="alert", action="respond",
                                   mission_time_s=100)
            dm.update_outcome(r, Outcome.SUCCESS)

        stats = dm.get_statistics()
        assert stats["total_resolved"] == 3
        assert len(stats["by_subsystem"]) == 3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_pattern_with_only_pending_outcomes(self, dm: DecisionMemory) -> None:
        """Pending-only records should not create a pattern with success stats."""
        _seed_battery_low_decisions(dm, 3)
        # Don't update any outcomes — they stay pending

        dm.rebuild_all_patterns()
        pattern = dm.get_pattern("power", "battery_low", "shed_science_loads", "load_shed")
        assert pattern is not None
        assert pattern.success_count == 0
        assert pattern.failure_count == 0

    def test_pattern_with_all_neutral(self, dm: DecisionMemory) -> None:
        ids = _seed_battery_low_decisions(dm, 3)
        for rid in ids:
            dm.update_outcome(rid, Outcome.NEUTRAL)

        pattern = dm.get_pattern("power", "battery_low", "shed_science_loads", "load_shed")
        assert pattern is not None
        assert pattern.success_rate == 0.0
        assert pattern.neutral_count == 3

    def test_decision_record_is_frozen(self) -> None:
        """DecisionRecord should be immutable once created."""
        rec = DecisionRecord(
            record_id="abc", timestamp="2026-01-01T00:00:00Z",
            mission_time_s=0.0, subsystem="power",
            decision_type="load_shed", trigger="battery_low",
            action="shed", context={},
        )
        with pytest.raises(AttributeError):
            rec.outcome = "success"  # type: ignore[misc]

    def test_empty_context(self, dm: DecisionMemory) -> None:
        rid = dm.record_decision(subsystem="power", decision_type="load_shed",
                                 trigger="x", action="y", mission_time_s=100)
        rec = dm.get_record(rid)
        assert rec is not None
        assert rec.context == {}

    def test_large_context(self, dm: DecisionMemory) -> None:
        big_ctx = {f"key_{i}": f"value_{i}" for i in range(100)}
        rid = dm.record_decision(subsystem="power", decision_type="load_shed",
                                 trigger="x", action="y", mission_time_s=100,
                                 context=big_ctx)
        rec = dm.get_record(rid)
        assert rec is not None
        assert len(rec.context) == 100
