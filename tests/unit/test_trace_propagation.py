"""R35 — end-to-end trace_id propagation through the failsafe stack."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aria.simulator.web_dashboard import DashboardConfig, WebDashboard
from aria.security import audit
from aria.security import auth_service as auth
from aria.security import principals as p
from aria.security import session_store as sst
from aria.security import trace_context as tc
from aria.safety import incident_policy as ipol
from aria.safety import incident_registry as ireg
from aria.safety import approval_queue as aq
from aria.safety.incident_policy import (
    Controllability, IncidentClass,
)


REPO = Path(__file__).resolve().parents[2]
SEALED = REPO / "data" / "sealed"
DEV_KEYS = json.loads(
    (REPO / "tests" / "fixtures" / "dev_keys.json").read_text(),
)


def _privkey(name: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(
        bytes.fromhex(DEV_KEYS[name]["priv_seed_hex"]),
    )


def _setup(tmp_path: Path) -> auth.AuthService:
    p.reset_for_test(sealed_dir=SEALED, runtime_dir=tmp_path)
    sessions = sst.SessionStore(runtime_dir=tmp_path)
    sst._INSTANCE = sessions
    auth.reset_for_test(sessions=sessions)
    audit.reset_for_test()
    ipol.reset_for_test(sealed_dir=SEALED)
    ireg.reset_for_test(runtime_dir=tmp_path)
    aq.reset_for_test()
    return auth.get_auth_service()


# ── HTTP middleware ────────────────────────────────────────────


async def _make_client() -> TestClient:
    cfg = DashboardConfig(host="127.0.0.1", port=0, auth_required=False)
    d = WebDashboard(cfg)
    server = TestServer(d.app)
    client = TestClient(server)
    await client.start_server()
    return client


@pytest.mark.asyncio
async def test_request_gets_trace_id_response_header(tmp_path):
    _setup(tmp_path)
    client = await _make_client()
    try:
        r = await client.get("/api/status")
        assert "X-Trace-Id" in r.headers
        assert r.headers["X-Trace-Id"].startswith("trc_")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_incoming_trace_id_is_honoured(tmp_path):
    _setup(tmp_path)
    client = await _make_client()
    try:
        r = await client.get(
            "/api/status",
            headers={"X-Trace-Id": "trc_aaaaaaaaaaaaaaaa"},
        )
        assert r.headers["X-Trace-Id"] == "trc_aaaaaaaaaaaaaaaa"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_bogus_trace_id_replaced_with_fresh(tmp_path):
    _setup(tmp_path)
    client = await _make_client()
    try:
        r = await client.get(
            "/api/status",
            headers={"X-Trace-Id": "<script>alert(1)</script>"},
        )
        # The bogus value did NOT make it into the response.
        assert r.headers["X-Trace-Id"] != "<script>alert(1)</script>"
        assert r.headers["X-Trace-Id"].startswith("trc_")
    finally:
        await client.close()


# ── Audit chain inherits the trace_id ──────────────────────────


@pytest.mark.asyncio
async def test_audit_entries_in_request_share_trace_id(tmp_path):
    """An admin endpoint that writes an audit entry should tag it
    with the same trace_id the response carried."""
    svc = _setup(tmp_path)
    client = await _make_client()
    try:
        # Login (writes audit entries) under a known trace.
        r = await client.get(
            "/api/auth/challenge?principal_id=captain.tau",
            headers={"X-Trace-Id": "trc_aaaaaaaaaaaaaaaa"},
        )
        ch = await r.json()
        sig = _privkey("captain.tau").sign(
            f"{ch['nonce']}|{ch['principal_id']}|{ch['expires_at']}".encode(),
        ).hex()
        r2 = await client.post(
            "/api/auth/login",
            json={"principal_id": "captain.tau", "nonce": ch["nonce"],
                  "signature_hex": sig},
            headers={"X-Trace-Id": "trc_aaaaaaaaaaaaaaaa"},
        )
        assert r2.status == 200
        # The audit chain has at least one entry tagged with our trace.
        entries = audit.get_audit_log().get_entries(
            trace_id="trc_aaaaaaaaaaaaaaaa",
        )
        assert len(entries) >= 1
        assert all(e.trace_id == "trc_aaaaaaaaaaaaaaaa" for e in entries)
    finally:
        await client.close()


# ── Incident inherits trace_id from active context ────────────


def test_incident_open_captures_trace_id(tmp_path):
    _setup(tmp_path)
    with tc.trace_scope() as tid:
        inc = ireg.get_incident_registry().open(
            title="x", incident_class=IncidentClass.SUBSYSTEM,
            severity="warning", source="test",
        )
    assert inc.trace_id == tid
    # And the audit entry for the open() shares it.
    ents = audit.get_audit_log().get_entries(trace_id=tid)
    assert any(e.action == "incident.opened" for e in ents)


# ── ApprovalQueue propagates trace_id from propose() to executor ──


def test_approval_queue_restores_trace_for_executor(tmp_path):
    _setup(tmp_path)
    aq.reset_for_test()
    queue = aq.get_approval_queue()

    captured_trace_in_executor = []

    def executor(params):
        # The executor fires LATER on a different async task; the
        # trace_id from propose() should still be active.
        captured_trace_in_executor.append(
            tc.current_trace_id(mint_if_absent=False),
        )
        # Also: writing an audit entry from inside the executor picks
        # up the propose-time trace_id automatically.
        audit.log_event("system", "executor", "ran", "ok")

    queue.register_executor("test_action", executor)

    with tc.trace_scope() as tid:
        proposal_id = queue.propose(
            action="test_action", params={}, proposer="test",
            required_signers=2, cooling_off_s=0.0,
        )
    # Sign + fire OUTSIDE the trace_scope — proves the queue
    # restores the trace from its captured snapshot.
    queue.approve(proposal_id, "alice", recall_answer_ok=True)
    queue.approve(proposal_id, "bob", recall_answer_ok=True)
    queue.try_execute()
    assert captured_trace_in_executor == [tid]
    # Audit entry from the executor carries the captured trace.
    ents = audit.get_audit_log().get_entries(trace_id=tid)
    assert any(e.action == "ran" for e in ents)


# ── /api/audit/trace?trace_id=X ─────────────────────────────────


@pytest.mark.asyncio
async def test_audit_trace_by_trace_id(tmp_path):
    _setup(tmp_path)
    # Open an incident under a known trace.
    with tc.trace_scope() as tid:
        inc = ireg.get_incident_registry().open(
            title="x", incident_class=IncidentClass.SUBSYSTEM,
            severity="warning", source="test",
        )
    client = await _make_client()
    try:
        r = await client.get(f"/api/audit/trace?trace_id={tid}")
        body = await r.json()
        assert body["count"] >= 1
        assert all(e["trace_id"] == tid for e in body["entries"])
        # And the entries include the incident.opened log.
        actions = [e["action"] for e in body["entries"]]
        assert "incident.opened" in actions
    finally:
        await client.close()
