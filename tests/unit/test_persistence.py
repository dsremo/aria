"""Tests for ARIA SQLite persistence layer."""

from __future__ import annotations

import asyncio
import json

import pytest

from aria.db.persistence import PersistenceManager


@pytest.fixture()
def pm() -> PersistenceManager:
    """Return an initialised in-memory PersistenceManager."""
    mgr = PersistenceManager(":memory:")
    mgr.init_db()
    return mgr


# ------------------------------------------------------------------
# 1. Schema creation
# ------------------------------------------------------------------

class TestInitDb:
    def test_tables_created(self, pm: PersistenceManager) -> None:
        """init_db should create all four tables."""
        conn = pm._get_conn()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = sorted(r["name"] for r in rows)
        assert "decisions" in names
        assert "episodes" in names
        assert "events" in names
        assert "state_snapshots" in names

    def test_indexes_created(self, pm: PersistenceManager) -> None:
        """init_db should create indexes on key columns."""
        conn = pm._get_conn()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        ).fetchall()
        idx_names = {r["name"] for r in rows}
        assert "idx_events_timestamp" in idx_names
        assert "idx_events_category" in idx_names
        assert "idx_events_severity" in idx_names
        assert "idx_episodes_event_type" in idx_names

    def test_init_db_idempotent(self, pm: PersistenceManager) -> None:
        """Calling init_db twice should not raise."""
        pm.init_db()  # second call
        assert pm.get_event_count() == 0


# ------------------------------------------------------------------
# 2. save_event / query_events
# ------------------------------------------------------------------

class TestEvents:
    def test_save_and_query_event(self, pm: PersistenceManager) -> None:
        eid = pm.save_event(
            timestamp="2026-04-06T00:00:00Z",
            category="thermal",
            severity="warning",
            source="sensor-A",
            summary="Temperature spike",
            payload={"temp_c": 85.2},
        )
        assert isinstance(eid, str) and len(eid) == 32
        events = pm.query_events()
        assert len(events) == 1
        evt = events[0]
        assert evt["category"] == "thermal"
        assert evt["severity"] == "warning"
        assert json.loads(evt["payload_json"])["temp_c"] == 85.2

    def test_query_events_filter_category(self, pm: PersistenceManager) -> None:
        pm.save_event("t1", "power", "info", "src", "ok")
        pm.save_event("t2", "thermal", "warning", "src", "hot")
        pm.save_event("t3", "power", "critical", "src", "fail")
        assert len(pm.query_events(category="power")) == 2
        assert len(pm.query_events(category="thermal")) == 1

    def test_query_events_filter_severity(self, pm: PersistenceManager) -> None:
        pm.save_event("t1", "power", "info", "src", "ok")
        pm.save_event("t2", "power", "critical", "src", "fail")
        results = pm.query_events(severity="critical")
        assert len(results) == 1
        assert results[0]["severity"] == "critical"

    def test_query_events_limit(self, pm: PersistenceManager) -> None:
        for i in range(10):
            pm.save_event(f"t{i:02d}", "cat", "info", "src", f"event-{i}")
        assert len(pm.query_events(limit=3)) == 3

    def test_get_event_count(self, pm: PersistenceManager) -> None:
        assert pm.get_event_count() == 0
        pm.save_event("t1", "c", "s", "src", "x")
        pm.save_event("t2", "c", "s", "src", "y")
        assert pm.get_event_count() == 2


# ------------------------------------------------------------------
# 3. save_episode / query_episodes
# ------------------------------------------------------------------

class TestEpisodes:
    def test_save_and_query_episode(self, pm: PersistenceManager) -> None:
        eid = pm.save_episode("anomaly", "critical", "Anomaly detected", {"metric": "cpu"})
        assert isinstance(eid, str)
        eps = pm.query_episodes()
        assert len(eps) == 1
        assert eps[0]["event_type"] == "anomaly"
        assert json.loads(eps[0]["details_json"])["metric"] == "cpu"

    def test_query_episodes_filter(self, pm: PersistenceManager) -> None:
        pm.save_episode("anomaly", "warning", "a1")
        pm.save_episode("recovery", "info", "r1")
        assert len(pm.query_episodes(event_type="anomaly")) == 1
        assert len(pm.query_episodes(event_type="recovery")) == 1


# ------------------------------------------------------------------
# 4. Decisions and state snapshots
# ------------------------------------------------------------------

class TestDecisionsAndSnapshots:
    def test_save_decision(self, pm: PersistenceManager) -> None:
        did = pm.save_decision("t1", "orbital", "high", "maneuver", "executed burn")
        assert isinstance(did, str) and len(did) == 32
        row = pm._get_conn().execute("SELECT * FROM decisions WHERE id = ?", (did,)).fetchone()
        assert row["outcome"] == "maneuver"

    def test_save_state_snapshot(self, pm: PersistenceManager) -> None:
        sid = pm.save_state_snapshot({"mode": "nominal", "battery": 92})
        row = pm._get_conn().execute("SELECT * FROM state_snapshots WHERE id = ?", (sid,)).fetchone()
        state = json.loads(row["state_json"])
        assert state["mode"] == "nominal"
        assert state["battery"] == 92


# ------------------------------------------------------------------
# 5. Async wrappers
# ------------------------------------------------------------------

class TestAsync:
    def test_async_round_trip(self, pm: PersistenceManager) -> None:
        async def _run() -> None:
            await pm.async_save_event("t1", "comms", "info", "radio", "beacon ok", {"rssi": -42})
            events = await pm.async_query_events(category="comms")
            assert len(events) == 1
            count = await pm.async_get_event_count()
            assert count == 1

        asyncio.run(_run())

    def test_async_episode_round_trip(self, pm: PersistenceManager) -> None:
        async def _run() -> None:
            await pm.async_save_episode("failover", "warning", "switched to backup")
            eps = await pm.async_query_episodes(event_type="failover")
            assert len(eps) == 1

        asyncio.run(_run())
