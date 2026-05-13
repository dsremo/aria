"""R34 Phase 5 — incident + audit-trace endpoints e2e."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from aria.simulator.web_dashboard import DashboardConfig, WebDashboard
from aria.security import audit
from aria.safety import incident_policy as p
from aria.safety import incident_registry as reg
from aria.safety.incident_policy import (
    Controllability, IncidentClass,
)


REPO = Path(__file__).resolve().parents[2]
SEALED = REPO / "data" / "sealed"


def _setup(tmp_path: Path):
    p.reset_for_test(sealed_dir=SEALED)
    audit.reset_for_test()
    reg.reset_for_test(runtime_dir=tmp_path)


async def _make_client(auth_required: bool = False) -> TestClient:
    cfg = DashboardConfig(host="127.0.0.1", port=0,
                          auth_required=auth_required)
    d = WebDashboard(cfg)
    server = TestServer(d.app)
    client = TestClient(server)
    await client.start_server()
    return client


# ── List + GET ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_list_initially(tmp_path):
    _setup(tmp_path)
    client = await _make_client()
    try:
        r = await client.get("/api/incidents")
        body = await r.json()
        assert r.status == 200
        assert body["count"] == 0
        assert body["incidents"] == []
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_open_then_list_then_get(tmp_path):
    _setup(tmp_path)
    inc = reg.get_incident_registry().open(
        title="cabin pressure low",
        incident_class=IncidentClass.LIFE_CRITICAL,
        severity="critical",
        source="eclss",
        detail={"pressure_kpa": 60.0},
    )
    client = await _make_client()
    try:
        r = await client.get("/api/incidents")
        body = await r.json()
        assert body["count"] == 1
        assert body["incidents"][0]["incident_id"] == inc.incident_id
        # Single get.
        r2 = await client.get(f"/api/incidents/{inc.incident_id}")
        det = await r2.json()
        assert det["title"] == "cabin pressure low"
        assert det["response_mode"] == "AUTO_STABILIZE"
    finally:
        await client.close()


# ── Lifecycle via API ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_lifecycle_via_api(tmp_path):
    _setup(tmp_path)
    inc = reg.get_incident_registry().open(
        title="navigation drift",
        incident_class=IncidentClass.MISSION_CRITICAL,
        controllability=Controllability.NOVEL_UNKNOWN,
        severity="critical",
        source="navigation",
    )
    client = await _make_client()
    try:
        # Note.
        r = await client.post(
            f"/api/incidents/{inc.incident_id}/note",
            json={"text": "checking"},
        )
        assert r.status == 200
        # Fix attempt.
        r = await client.post(
            f"/api/incidents/{inc.incident_id}/fix",
            json={"summary": "reset estimator", "success": True},
        )
        assert r.status == 200
        # Root cause.
        r = await client.post(
            f"/api/incidents/{inc.incident_id}/root_cause",
            json={"text": "post-eclipse quaternion drift"},
        )
        assert r.status == 200
        # Resolve.
        r = await client.post(
            f"/api/incidents/{inc.incident_id}/resolve",
            json={"resolution": "stable for 1 hr"},
        )
        assert r.status == 200
        # GET shows it as RESOLVED.
        body = await (await client.get(
            f"/api/incidents/{inc.incident_id}")).json()
        assert body["status"] == "RESOLVED"
        assert body["root_cause"] == "post-eclipse quaternion drift"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_unknown_incident_404(tmp_path):
    _setup(tmp_path)
    client = await _make_client()
    try:
        r = await client.get("/api/incidents/inc_nonexistent")
        assert r.status == 404
        r2 = await client.post("/api/incidents/inc_nope/note",
                               json={"text": "x"})
        assert r2.status == 404
    finally:
        await client.close()


# ── Audit trace ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_trace_filters_by_incident_id(tmp_path):
    _setup(tmp_path)
    a = reg.get_incident_registry().open(
        title="A", incident_class=IncidentClass.SUBSYSTEM,
        source="x", severity="warning",
    )
    b = reg.get_incident_registry().open(
        title="B", incident_class=IncidentClass.SUBSYSTEM,
        source="x", severity="warning",
    )
    client = await _make_client()
    try:
        r = await client.get(
            f"/api/audit/trace?incident_id={a.incident_id}",
        )
        body = await r.json()
        # Each open() emits exactly 1 audit entry → 1 for A.
        assert body["count"] == 1
        assert all(e["incident_id"] == a.incident_id for e in body["entries"])
        assert body["entries"][0]["action"] == "incident.opened"
        assert body["head_hash"]   # non-empty hash chain head
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_audit_chain_status_endpoint(tmp_path):
    _setup(tmp_path)
    reg.get_incident_registry().open(
        title="x", incident_class=IncidentClass.SUBSYSTEM,
        source="x", severity="warning",
    )
    client = await _make_client()
    try:
        r = await client.get("/api/audit/chain_status")
        body = await r.json()
        assert body["entries"] >= 1
        assert body["chain_intact"] is True
        assert body["verify_ok"] is True
        assert body["head_hash"]
    finally:
        await client.close()
