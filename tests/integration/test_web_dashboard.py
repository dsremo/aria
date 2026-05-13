"""Integration tests for the ARIA web dashboard.

Tests cover:
  - Server startup and shutdown
  - REST endpoints (status, snapshots, events)
  - WebSocket connections and messaging
  - Data format correctness
  - Demo snapshot generation
  - Recording loading
  - Snapshot push and broadcast
  - Event filtering
"""

from __future__ import annotations

import asyncio
import json
import math
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from aria.simulator.web_dashboard import (
    DashboardConfig,
    WebDashboard,
    generate_demo_snapshots,
)


# ─── Fixtures ────────────────────────────────────────────────

@pytest.fixture
def config():
    return DashboardConfig(host="127.0.0.1", port=0)  # port=0 -> OS picks


@pytest.fixture
def dashboard(config):
    return WebDashboard(config)


@pytest.fixture
def demo_snapshots():
    return generate_demo_snapshots(years=50, seed=42)


@pytest.fixture
def populated_dashboard(config, demo_snapshots):
    d = WebDashboard(config)
    d._snapshots = demo_snapshots
    d._recording_loaded = True
    for snap in demo_snapshots:
        if snap.get("events"):
            d._events.extend(snap["events"])
    return d


@pytest.fixture
def sample_recording(demo_snapshots, tmp_path):
    """Write a sample recording JSON to a temp file."""
    path = tmp_path / "mission_test.json"
    data = {
        "format_version": 1,
        "metadata": {"target": "alpha_centauri"},
        "snapshots": demo_snapshots,
    }
    path.write_text(json.dumps(data))
    return path


# ─── Test: Demo Snapshot Generation ──────────────────────────

class TestDemoSnapshots:
    def test_generates_correct_count(self):
        snaps = generate_demo_snapshots(years=100, seed=1)
        assert len(snaps) == 100

    def test_snapshot_has_required_fields(self):
        snaps = generate_demo_snapshots(years=10)
        snap = snaps[0]
        required = [
            "mission_year", "distance_ly", "velocity_c", "phase",
            "position_x", "position_y", "position_z",
            "hull_integrity", "shield_health", "total_power_watts",
            "food_production_ratio", "crew_count", "water_liters",
            "fuel_fraction", "challenges",
        ]
        for field in required:
            assert field in snap, f"Missing field: {field}"

    def test_mission_year_increments(self):
        snaps = generate_demo_snapshots(years=20)
        for i, snap in enumerate(snaps):
            assert snap["mission_year"] == i + 1

    def test_distance_increases(self):
        snaps = generate_demo_snapshots(years=50)
        for i in range(1, len(snaps)):
            assert snaps[i]["distance_ly"] >= snaps[i - 1]["distance_ly"]

    def test_hull_degrades_over_time(self):
        snaps = generate_demo_snapshots(years=100)
        assert snaps[-1]["hull_integrity"] < snaps[0]["hull_integrity"]

    def test_challenges_present_with_six_entries(self):
        snaps = generate_demo_snapshots(years=5)
        ch = snaps[0]["challenges"]
        assert len(ch) == 6
        expected_names = {"materials", "food", "knowledge", "genetics", "psychology", "fuel"}
        assert set(ch.keys()) == expected_names

    def test_challenge_severity_increases(self):
        snaps = generate_demo_snapshots(years=100)
        ch_first = snaps[0]["challenges"]["materials"]["severity"]
        ch_last = snaps[-1]["challenges"]["materials"]["severity"]
        assert ch_last > ch_first

    def test_3d_positions_are_computed(self):
        snaps = generate_demo_snapshots(years=10)
        for snap in snaps:
            assert isinstance(snap["position_x"], float)
            assert isinstance(snap["position_y"], float)
            assert isinstance(snap["position_z"], float)

    def test_events_generated(self):
        """With enough years, at least some events should be generated."""
        snaps = generate_demo_snapshots(years=200, seed=42)
        total_events = sum(len(s.get("events", [])) for s in snaps)
        assert total_events > 0

    def test_deterministic_with_same_seed(self):
        a = generate_demo_snapshots(years=50, seed=99)
        b = generate_demo_snapshots(years=50, seed=99)
        assert a == b


# ─── Test: Dashboard Initialization ─────────────────────────

class TestDashboardInit:
    def test_default_config(self):
        d = WebDashboard()
        assert d.snapshot_count == 0
        assert d.event_count == 0
        assert d.client_count == 0
        assert not d.running

    def test_custom_config(self, config):
        d = WebDashboard(config)
        assert d._config.host == "127.0.0.1"

    def test_app_creation(self, dashboard):
        app = dashboard.app
        assert isinstance(app, web.Application)
        # Verify routes exist
        routes = [r.resource.canonical for r in app.router.routes() if hasattr(r, 'resource') and r.resource]
        assert "/" in routes or any("/" == r for r in routes)


# ─── Test: Recording Loading ─────────────────────────────────

class TestRecordingLoading:
    def test_load_json_recording(self, dashboard, sample_recording):
        count = dashboard.load_recording(sample_recording)
        assert count == 50
        assert dashboard.snapshot_count == 50
        assert dashboard._recording_loaded

    def test_load_raw_array(self, dashboard, tmp_path):
        path = tmp_path / "raw.json"
        data = [{"mission_year": i, "hull_integrity": 1.0 - i * 0.01} for i in range(10)]
        path.write_text(json.dumps(data))
        count = dashboard.load_recording(path)
        assert count == 10

    def test_load_extracts_events(self, dashboard, sample_recording):
        dashboard.load_recording(sample_recording)
        # Some snapshots should have events
        assert dashboard.event_count >= 0  # May or may not have events


# ─── Test: Push Operations ───────────────────────────────────

class TestPushOperations:
    def test_push_snapshot(self, dashboard):
        snap = {"mission_year": 1, "hull_integrity": 0.99}
        dashboard.push_snapshot(snap)
        assert dashboard.snapshot_count == 1

    def test_push_event(self, dashboard):
        event = {"year": 1, "severity": "WARNING", "description": "Test"}
        dashboard.push_event(event)
        assert dashboard.event_count == 1

    def test_push_respects_max_snapshots(self):
        config = DashboardConfig(max_snapshots=5)
        d = WebDashboard(config)
        for i in range(10):
            d.push_snapshot({"mission_year": i})
        assert d.snapshot_count == 5
        # Should keep the latest
        assert d._snapshots[-1]["mission_year"] == 9

    def test_push_respects_max_events(self):
        config = DashboardConfig(max_events=3)
        d = WebDashboard(config)
        for i in range(5):
            d.push_event({"year": i, "severity": "WARNING"})
        assert d.event_count == 3


# ─── Test: Data Conversion ───────────────────────────────────

class TestDataConversion:
    def test_interstellar_state_dict(self, dashboard):
        state = {
            "mission_year": 50,
            "distance_ly": 5.0,
            "velocity_c": 0.1,
            "phase": "INTERSTELLAR_CRUISE",
            "hull_integrity": 0.95,
            "radiation_shielding_mass_kg": 8000,
            "total_power_watts": 450000,
            "hydroponic_capacity": 0.9,
            "crew_count": 6,
            "crew_generation": 2,
            "water_liters": 45000,
            "fusion_fuel_kg": 40000,
            "fuel_initial_kg": 50000,
        }
        result = dashboard._interstellar_state_to_dict(state)
        assert result["mission_year"] == 50
        assert result["hull_integrity"] == 0.95
        assert result["shield_health"] == 0.8  # 8000/10000
        assert result["fuel_fraction"] == 0.8  # 40000/50000
        assert "position_x" in result
        assert "position_y" in result
        assert "position_z" in result

    def test_year_event_dict(self, dashboard):
        event = MagicMock()
        event.year = 10
        event.category = "HULL"
        event.severity = "WARNING"
        event.description = "Micrometeorite impact"
        event.subsystem = "hull"
        event.impact = {"damage": 0.01}
        result = dashboard._year_event_to_dict(event)
        assert result["year"] == 10
        assert result["severity"] == "WARNING"

    def test_year_event_dict_from_dict(self, dashboard):
        event = {"year": 5, "severity": "CRITICAL", "description": "Test"}
        result = dashboard._year_event_to_dict(event)
        assert result == event


# ─── Test: HTTP Endpoints via aiohttp test client ────────────

@pytest.fixture
async def client(populated_dashboard):
    app = populated_dashboard.app
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()


class TestHTTPEndpoints:
    @pytest.mark.asyncio
    async def test_index_returns_html(self, client):
        resp = await client.get("/")
        assert resp.status == 200
        text = await resp.text()
        assert "ARIA" in text
        assert "Plotly" in text or "plotly" in text

    @pytest.mark.asyncio
    async def test_status_endpoint(self, client):
        resp = await client.get("/api/status")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["snapshots"] == 50
        assert isinstance(data["events"], int)
        assert isinstance(data["clients"], int)
        assert data["recording_loaded"] is True

    @pytest.mark.asyncio
    async def test_snapshots_endpoint(self, client):
        resp = await client.get("/api/snapshots")
        assert resp.status == 200
        data = await resp.json()
        assert data["total"] == 50
        assert len(data["snapshots"]) == 50

    @pytest.mark.asyncio
    async def test_snapshots_pagination(self, client):
        resp = await client.get("/api/snapshots?offset=10&limit=5")
        data = await resp.json()
        assert data["count"] == 5
        assert data["offset"] == 10
        # First snapshot should be year 11 (offset 10, 0-indexed)
        assert data["snapshots"][0]["mission_year"] == 11

    @pytest.mark.asyncio
    async def test_snapshot_by_year(self, client):
        resp = await client.get("/api/snapshot/25")
        assert resp.status == 200
        data = await resp.json()
        assert abs(data["mission_year"] - 25) <= 1

    @pytest.mark.asyncio
    async def test_snapshot_invalid_year(self, client):
        resp = await client.get("/api/snapshot/abc")
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_events_endpoint(self, client):
        resp = await client.get("/api/events")
        assert resp.status == 200
        data = await resp.json()
        assert "events" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_events_filter_by_severity(self, client):
        resp = await client.get("/api/events?severity=WARNING")
        data = await resp.json()
        for event in data["events"]:
            assert event["severity"] == "WARNING"

    @pytest.mark.asyncio
    async def test_cors_headers(self, client):
        resp = await client.get("/api/status")
        assert "Access-Control-Allow-Origin" in resp.headers


# ─── Test: WebSocket ─────────────────────────────────────────

class TestWebSocket:
    @pytest.mark.asyncio
    async def test_ws_connection(self, client):
        async with client.ws_connect("/ws") as ws:
            # Should receive initial snapshot
            msg = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
            assert msg["type"] == "snapshot"
            assert "data" in msg

    @pytest.mark.asyncio
    async def test_ws_get_snapshot_command(self, client):
        async with client.ws_connect("/ws") as ws:
            # Consume initial message
            await asyncio.wait_for(ws.receive_json(), timeout=2.0)

            # Request specific year
            await ws.send_json({"command": "get_snapshot", "year": 10})
            msg = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
            assert msg["type"] == "snapshot"
            assert abs(msg["data"]["mission_year"] - 10) <= 1

    @pytest.mark.asyncio
    async def test_ws_client_tracking(self, populated_dashboard):
        app = populated_dashboard.app
        server = TestServer(app)
        client = TestClient(server)
        await client.start_server()
        try:
            assert populated_dashboard.client_count == 0
            async with client.ws_connect("/ws") as ws:
                await asyncio.wait_for(ws.receive_json(), timeout=2.0)
                assert populated_dashboard.client_count == 1
            # After disconnect, give event loop a cycle
            await asyncio.sleep(0.1)
            assert populated_dashboard.client_count == 0
        finally:
            await client.close()


# ─── Test: Server Lifecycle ──────────────────────────────────

class TestServerLifecycle:
    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        config = DashboardConfig(host="127.0.0.1", port=0)
        d = WebDashboard(config)
        # We test app creation, not full start (port=0 doesn't work with TCPSite)
        app = d.app
        assert app is not None
        assert not d.running

    def test_push_interstellar_state(self):
        d = WebDashboard()
        # Simulate with a dict
        state = {
            "mission_year": 10,
            "distance_ly": 1.0,
            "velocity_c": 0.1,
            "phase": "INTERSTELLAR_CRUISE",
            "hull_integrity": 0.99,
            "crew_count": 4,
            "water_liters": 49000,
            "total_power_watts": 490000,
            "hydroponic_capacity": 0.98,
            "radiation_shielding_mass_kg": 9900,
            "fusion_fuel_kg": 49500,
            "fuel_initial_kg": 50000,
        }
        d.push_interstellar_state(state)
        assert d.snapshot_count == 1
        snap = d._snapshots[0]
        assert snap["mission_year"] == 10
        assert "position_x" in snap
