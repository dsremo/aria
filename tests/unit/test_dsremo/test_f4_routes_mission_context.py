"""V3-F4 API tests: mission_config + orbital_events + satellite context."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from aria.dsremo.detection.orbital_events import get_orbital_timeline


SAT = "SAT-F4-01"


@pytest.fixture(scope="module")
def demo_client():
    from aria.dsremo.api.app import create_app
    app = create_app(demo=True)
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def _clear_timeline():
    """Reset the singleton OrbitalEventTimeline between tests."""
    get_orbital_timeline().clear()
    yield
    get_orbital_timeline().clear()


# ---------------------------------------------------------------------------
# GET /satellites/{sat}/context
# ---------------------------------------------------------------------------

class TestContextEndpoint:

    def test_empty_context_before_config(self, demo_client):
        r = demo_client.get(f"/api/v1/satellites/{SAT}/context")
        assert r.status_code == 200
        body = r.json()
        assert body["satellite_id"] == SAT
        assert body["launch_epoch"] is None
        assert body["design_life_s"] is None
        assert body["design_life_pct_consumed"] is None
        assert body["next_eclipse"] is None
        assert body["next_contact"] is None
        assert body["next_maneuver"] is None
        assert body["upcoming_events"] == []

    def test_context_after_putting_config(self, demo_client):
        launch = time.time() - 30 * 86_400
        r = demo_client.put(
            f"/api/v1/satellites/{SAT}/mission_config",
            json={"launch_epoch": launch, "design_life_days": 1825},
        )
        assert r.status_code == 200
        r = demo_client.get(f"/api/v1/satellites/{SAT}/context")
        assert r.status_code == 200
        body = r.json()
        assert body["launch_epoch"] == pytest.approx(launch, rel=1e-6)
        assert body["design_life_s"] == pytest.approx(1825 * 86_400.0, rel=1e-6)
        assert body["mission_elapsed_s"] == pytest.approx(30 * 86_400.0, abs=60.0)
        assert 1.0 < body["design_life_pct_consumed"] < 3.0

    def test_context_surfaces_next_eclipse(self, demo_client):
        future = time.time() + 500
        demo_client.post(
            f"/api/v1/satellites/{SAT}/orbital_events",
            json={"event_type": "eclipse_entry", "start_epoch": future, "duration_s": 30},
        )
        r = demo_client.get(f"/api/v1/satellites/{SAT}/context")
        body = r.json()
        assert body["next_eclipse"] is not None
        assert body["next_eclipse"]["event_type"] == "eclipse_entry"
        assert body["next_eclipse"]["start_epoch"] == pytest.approx(future, abs=1.0)

    def test_context_rejects_zero_horizon(self, demo_client):
        r = demo_client.get(f"/api/v1/satellites/{SAT}/context?horizon_s=0")
        assert r.status_code == 422  # Query validation

    def test_context_rejects_excessive_horizon(self, demo_client):
        r = demo_client.get(f"/api/v1/satellites/{SAT}/context?horizon_s={40 * 86_400}")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# PUT /satellites/{sat}/mission_config
# ---------------------------------------------------------------------------

class TestPutMissionConfig:

    def test_put_returns_stored_row(self, demo_client):
        r = demo_client.put(
            f"/api/v1/satellites/{SAT}/mission_config",
            json={"launch_epoch": 1_700_000_000.0, "design_life_days": 365},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["satellite_id"] == SAT
        assert body["launch_epoch"] == pytest.approx(1_700_000_000.0)
        assert body["design_life_days"] == 365

    def test_put_upsert_overwrites(self, demo_client):
        demo_client.put(
            f"/api/v1/satellites/{SAT}/mission_config",
            json={"launch_epoch": 1.0, "design_life_days": 100},
        )
        r2 = demo_client.put(
            f"/api/v1/satellites/{SAT}/mission_config",
            json={"launch_epoch": 2.0, "design_life_days": 200},
        )
        assert r2.json()["launch_epoch"] == pytest.approx(2.0)
        assert r2.json()["design_life_days"] == 200

    def test_put_rejects_zero_design_life(self, demo_client):
        r = demo_client.put(
            f"/api/v1/satellites/{SAT}/mission_config",
            json={"launch_epoch": 1.0, "design_life_days": 0},
        )
        assert r.status_code == 422

    def test_put_rejects_negative_design_life(self, demo_client):
        r = demo_client.put(
            f"/api/v1/satellites/{SAT}/mission_config",
            json={"launch_epoch": 1.0, "design_life_days": -5},
        )
        assert r.status_code == 422

    def test_put_caps_design_life_at_30y(self, demo_client):
        r = demo_client.put(
            f"/api/v1/satellites/{SAT}/mission_config",
            json={"launch_epoch": 1.0, "design_life_days": 365 * 30 + 1},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST / DELETE / GET /satellites/{sat}/orbital_events
# ---------------------------------------------------------------------------

class TestOrbitalEventsEndpoints:

    def test_post_registers_event(self, demo_client):
        future = time.time() + 120
        r = demo_client.post(
            f"/api/v1/satellites/{SAT}/orbital_events",
            json={
                "event_type": "maneuver",
                "start_epoch": future,
                "duration_s": 60,
                "description": "orbit-raise Δv=2.1 m/s",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["event_type"] == "maneuver"
        assert body["starts_in_s"] > 0
        assert body["description"] == "orbit-raise Δv=2.1 m/s"

    def test_get_orbital_events_returns_registered(self, demo_client):
        now = time.time()
        for offset in (100, 200, 300):
            demo_client.post(
                f"/api/v1/satellites/{SAT}/orbital_events",
                json={"event_type": "gs_handover", "start_epoch": now + offset, "duration_s": 60},
            )
        r = demo_client.get(f"/api/v1/satellites/{SAT}/orbital_events")
        assert r.status_code == 200
        events = r.json()
        assert len(events) == 3
        starts = [e["start_epoch"] for e in events]
        assert starts == sorted(starts)

    def test_get_orbital_events_filter_by_window(self, demo_client):
        now = time.time()
        demo_client.post(
            f"/api/v1/satellites/{SAT}/orbital_events",
            json={"event_type": "eclipse_entry", "start_epoch": now + 100, "duration_s": 30},
        )
        demo_client.post(
            f"/api/v1/satellites/{SAT}/orbital_events",
            json={"event_type": "eclipse_entry", "start_epoch": now + 10_000, "duration_s": 30},
        )
        r = demo_client.get(
            f"/api/v1/satellites/{SAT}/orbital_events",
            params={"from_epoch": now, "to_epoch": now + 500},
        )
        assert r.status_code == 200
        events = r.json()
        assert len(events) == 1

    def test_get_orbital_events_reversed_window_is_400(self, demo_client):
        now = time.time()
        r = demo_client.get(
            f"/api/v1/satellites/{SAT}/orbital_events",
            params={"from_epoch": now + 1000, "to_epoch": now},
        )
        assert r.status_code == 400

    def test_delete_clears_all_events(self, demo_client):
        now = time.time()
        demo_client.post(
            f"/api/v1/satellites/{SAT}/orbital_events",
            json={"event_type": "maneuver", "start_epoch": now + 100, "duration_s": 30},
        )
        r = demo_client.delete(f"/api/v1/satellites/{SAT}/orbital_events")
        assert r.status_code == 204
        r2 = demo_client.get(f"/api/v1/satellites/{SAT}/orbital_events")
        assert r2.json() == []

    def test_post_rejects_zero_duration(self, demo_client):
        r = demo_client.post(
            f"/api/v1/satellites/{SAT}/orbital_events",
            json={"event_type": "maneuver", "start_epoch": time.time() + 100, "duration_s": 0},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# /ops static file mount smoke tests
# ---------------------------------------------------------------------------

class TestOpsStaticMount:

    def test_ops_index_served(self, demo_client):
        r = demo_client.get("/ops/")
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/html" in ct.lower()
        body = r.text
        assert "DSREMO" in body.upper() or "MISSION TIMELINE" in body.upper()

    def test_ops_index_not_leaking_env(self, demo_client):
        """Sanity: no secrets or absolute filesystem paths leaked into HTML."""
        body = demo_client.get("/ops/").text
        assert "DSREMO_JWT_SECRET" not in body
        assert "/home/" not in body
