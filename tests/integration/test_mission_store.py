"""Integration tests for the mission persistence store.

Tests cover save/load round-trips, list/query operations, delete,
score/grade persistence, challenge states, severity distributions,
file-backed persistence across close/reopen, edge cases, and ordering.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pytest

from aria.persistence.mission_store import MissionStore, MissionRecord, MissionSummary


# ────────────────────────────────────────────────────────────────
#  Fixtures
# ────────────────────────────────────────────────────────────────

@dataclass
class FakeResults:
    """Mimics MissionResults from mission_runner for testing."""

    mission_name: str = "TestMission"
    mission_type: str = "LEO"
    duration_sim_s: float = 5520.0
    duration_wall_s: float = 0.42
    total_frames: int = 552
    total_events: int = 100
    total_alerts: int = 5
    altitude_range_km: tuple[float, float] = (398.0, 402.0)
    velocity_range_m_s: tuple[float, float] = (7650.0, 7670.0)
    latitude_range_deg: tuple[float, float] = (-51.6, 51.6)
    eclipse_count: int = 3
    agent_messages_processed: int = 1500
    anomalies_detected: int = 7
    severity_distribution: dict[str, int] = field(default_factory=lambda: {
        "NOMINAL": 80, "WARNING": 15, "CRITICAL": 5
    })
    challenge_states: dict[str, str] = field(default_factory=dict)
    terminal_challenges: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


@pytest.fixture
def store(tmp_path):
    """Create a file-backed mission store for each test."""
    db_path = str(tmp_path / "test_missions.db")
    s = MissionStore(db_path=db_path)
    yield s
    s.close()


@pytest.fixture
def results():
    return FakeResults()


@pytest.fixture
def interstellar_results():
    return FakeResults(
        mission_name="Interstellar-200yr",
        mission_type="INTERSTELLAR",
        duration_sim_s=200.0,
        duration_wall_s=3.5,
        total_frames=200,
        total_events=5000,
        total_alerts=150,
        altitude_range_km=(0, 0),
        velocity_range_m_s=(0, 0),
        latitude_range_deg=(0, 0),
        eclipse_count=0,
        anomalies_detected=42,
        severity_distribution={
            "NOMINAL": 3000, "WARNING": 1500, "CRITICAL": 400, "EMERGENCY": 100
        },
        challenge_states={
            "food_shortage": "active",
            "radiation_damage": "terminal",
            "hull_breach": "resolved",
        },
        terminal_challenges=1,
    )


# ────────────────────────────────────────────────────────────────
#  Save / Load round-trip
# ────────────────────────────────────────────────────────────────

class TestSaveLoad:

    def test_save_returns_12_char_id(self, store, results):
        mission_id = store.save(results)
        assert isinstance(mission_id, str)
        assert len(mission_id) == 12

    def test_load_by_id(self, store, results):
        mid = store.save(results)
        record = store.load(mid)
        assert record is not None
        assert record.id == mid
        assert record.name == "TestMission"
        assert record.mission_type == "LEO"

    def test_load_preserves_numeric_fields(self, store, results):
        mid = store.save(results, score=85.0, grade="A")
        record = store.load(mid)
        assert record.duration_sim_s == 5520.0
        assert record.duration_wall_s == pytest.approx(0.42)
        assert record.total_frames == 552
        assert record.total_events == 100
        assert record.total_alerts == 5
        assert record.eclipse_count == 3
        assert record.agent_messages_processed == 1500
        assert record.anomalies_detected == 7

    def test_load_preserves_tuple_ranges(self, store, results):
        mid = store.save(results)
        record = store.load(mid)
        assert record.altitude_range_km == (398.0, 402.0)
        assert record.velocity_range_m_s == (7650.0, 7670.0)
        assert record.latitude_range_deg == (-51.6, 51.6)

    def test_load_nonexistent_returns_none(self, store):
        assert store.load("nonexistent_id") is None

    def test_save_with_score_and_grade(self, store, results):
        mid = store.save(results, score=72.5, grade="B")
        record = store.load(mid)
        assert record.score == pytest.approx(72.5)
        assert record.grade == "B"

    def test_save_without_score_stores_none(self, store, results):
        mid = store.save(results)
        record = store.load(mid)
        assert record.score is None
        assert record.grade is None

    def test_save_extra_metadata(self, store, results):
        extra = {"seed": 42, "config": "breakthrough", "notes": "test run"}
        mid = store.save(results, extra=extra)
        record = store.load(mid)
        assert record.extra == extra

    def test_save_failed_mission(self, store):
        failed = FakeResults(errors=["Basilisk not available", "Timeout"])
        mid = store.save(failed)
        record = store.load(mid)
        assert record.status == "failed"
        assert len(record.errors) == 2
        assert "Basilisk not available" in record.errors


# ────────────────────────────────────────────────────────────────
#  List
# ────────────────────────────────────────────────────────────────

class TestList:

    def test_list_empty_database(self, store):
        assert store.list_missions() == []

    def test_list_returns_summaries(self, store, results):
        store.save(results)
        missions = store.list_missions()
        assert len(missions) == 1
        s = missions[0]
        assert isinstance(s, MissionSummary)
        assert s.name == "TestMission"
        assert s.mission_type == "LEO"
        assert s.status == "success"

    def test_list_ordered_newest_first(self, store):
        store.save(FakeResults(mission_name="First"))
        store.save(FakeResults(mission_name="Second"))
        store.save(FakeResults(mission_name="Third"))
        missions = store.list_missions()
        assert len(missions) == 3
        assert missions[0].name == "Third"
        assert missions[2].name == "First"

    def test_list_respects_limit(self, store):
        for i in range(10):
            store.save(FakeResults(mission_name=f"M-{i}"))
        assert len(store.list_missions(limit=3)) == 3
        assert len(store.list_missions(limit=100)) == 10

    def test_list_includes_score(self, store, results):
        store.save(results, score=91.0, grade="A+")
        s = store.list_missions()[0]
        assert s.score == 91.0
        assert s.grade == "A+"


# ────────────────────────────────────────────────────────────────
#  Query
# ────────────────────────────────────────────────────────────────

class TestQuery:

    def test_latest_on_empty_db(self, store):
        assert store.latest() is None

    def test_latest_returns_most_recent(self, store):
        store.save(FakeResults(mission_name="Old"))
        store.save(FakeResults(mission_name="New"))
        latest = store.latest()
        assert latest is not None
        assert latest.name == "New"

    def test_by_type_filters_correctly(self, store, results, interstellar_results):
        store.save(results)
        store.save(interstellar_results)
        store.save(FakeResults(mission_name="GEO-Test", mission_type="GEO"))

        assert len(store.by_type("LEO")) == 1
        assert len(store.by_type("INTERSTELLAR")) == 1
        assert len(store.by_type("GEO")) == 1
        assert len(store.by_type("MARS")) == 0

    def test_by_date_range_inclusive(self, store, results):
        store.save(results)
        # Range that covers today
        found = store.by_date_range("2020-01-01", "2030-12-31")
        assert len(found) == 1
        # Range in the distant past
        assert len(store.by_date_range("2000-01-01", "2000-12-31")) == 0

    def test_count(self, store, results):
        assert store.count() == 0
        store.save(results)
        assert store.count() == 1
        store.save(results)
        assert store.count() == 2


# ────────────────────────────────────────────────────────────────
#  Delete
# ────────────────────────────────────────────────────────────────

class TestDelete:

    def test_delete_existing(self, store, results):
        mid = store.save(results)
        assert store.delete(mid) is True
        assert store.load(mid) is None

    def test_delete_nonexistent_returns_false(self, store):
        assert store.delete("no_such_id") is False

    def test_delete_all(self, store):
        for i in range(5):
            store.save(FakeResults(mission_name=f"M-{i}"))
        assert store.count() == 5
        deleted = store.delete_all()
        assert deleted == 5
        assert store.count() == 0

    def test_delete_does_not_affect_others(self, store):
        id1 = store.save(FakeResults(mission_name="Keep"))
        id2 = store.save(FakeResults(mission_name="Remove"))
        store.delete(id2)
        assert store.load(id1) is not None
        assert store.load(id2) is None
        assert store.count() == 1


# ────────────────────────────────────────────────────────────────
#  Interstellar-specific data
# ────────────────────────────────────────────────────────────────

class TestInterstellarData:

    def test_challenge_states_round_trip(self, store, interstellar_results):
        mid = store.save(interstellar_results)
        record = store.load(mid)
        assert record.challenge_states == {
            "food_shortage": "active",
            "radiation_damage": "terminal",
            "hull_breach": "resolved",
        }
        assert record.terminal_challenges == 1

    def test_severity_distribution_round_trip(self, store, interstellar_results):
        mid = store.save(interstellar_results)
        record = store.load(mid)
        assert record.severity_distribution["EMERGENCY"] == 100
        assert record.severity_distribution["CRITICAL"] == 400
        assert sum(record.severity_distribution.values()) == 5000


# ────────────────────────────────────────────────────────────────
#  File-backed persistence
# ────────────────────────────────────────────────────────────────

class TestFilePersistence:

    def test_db_file_created(self, tmp_path):
        db_path = str(tmp_path / "check.db")
        s = MissionStore(db_path=db_path)
        assert os.path.exists(db_path)
        s.close()

    def test_survives_close_reopen(self, tmp_path):
        db_path = str(tmp_path / "persist.db")
        s1 = MissionStore(db_path=db_path)
        mid = s1.save(FakeResults(mission_name="Persist"))
        s1.close()

        s2 = MissionStore(db_path=db_path)
        record = s2.load(mid)
        assert record is not None
        assert record.name == "Persist"
        s2.close()


# ────────────────────────────────────────────────────────────────
#  Edge cases
# ────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_unique_ids_across_many_saves(self, store):
        ids = set()
        for i in range(20):
            mid = store.save(FakeResults(mission_name=f"M-{i}"))
            ids.add(mid)
        assert len(ids) == 20

    def test_empty_severity_distribution(self, store):
        r = FakeResults(severity_distribution={})
        mid = store.save(r)
        assert store.load(mid).severity_distribution == {}

    def test_zero_range_tuples(self, store):
        r = FakeResults(
            altitude_range_km=(0, 0),
            velocity_range_m_s=(0, 0),
            latitude_range_deg=(0, 0),
        )
        mid = store.save(r)
        record = store.load(mid)
        assert record.altitude_range_km == (0, 0)

    def test_large_event_count(self, store):
        r = FakeResults(total_events=1_000_000, total_alerts=50_000)
        mid = store.save(r)
        record = store.load(mid)
        assert record.total_events == 1_000_000

    def test_many_errors(self, store):
        errors = [f"Error {i}" for i in range(100)]
        r = FakeResults(errors=errors)
        mid = store.save(r)
        record = store.load(mid)
        assert len(record.errors) == 100
        assert record.status == "failed"

    def test_timestamp_is_iso_utc(self, store, results):
        mid = store.save(results)
        record = store.load(mid)
        # Should parse as valid ISO datetime
        dt = datetime.fromisoformat(record.timestamp)
        assert dt.year >= 2024
