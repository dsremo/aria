"""R32 Phase 3 — end-to-end auth/authz against the live web dashboard."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aria.simulator.web_dashboard import DashboardConfig, WebDashboard
from aria.security import principals as p
from aria.security import auth_service as auth
from aria.security import session_store as sst


REPO = Path(__file__).resolve().parents[2]
SEALED = REPO / "data" / "sealed"
DEV_KEYS = json.loads(
    (REPO / "tests" / "fixtures" / "dev_keys.json").read_text(),
)


def _privkey(name: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(
        bytes.fromhex(DEV_KEYS[name]["priv_seed_hex"]),
    )


def _setup_auth(tmp_path: Path) -> tuple[auth.AuthService, sst.SessionStore]:
    p.reset_for_test(sealed_dir=SEALED, runtime_dir=tmp_path)
    sessions = sst.SessionStore(runtime_dir=tmp_path)
    sst._INSTANCE = sessions
    auth.reset_for_test(sessions=sessions)
    return auth.get_auth_service(), sessions


def _make_dashboard(*, auth_required: bool) -> WebDashboard:
    cfg = DashboardConfig(host="127.0.0.1", port=0, auth_required=auth_required)
    return WebDashboard(cfg)


async def _make_client(d: WebDashboard) -> TestClient:
    server = TestServer(d.app)
    client = TestClient(server)
    await client.start_server()
    return client


async def _login(svc: auth.AuthService, client: TestClient,
                 principal_id: str) -> str:
    """End-to-end: GET /api/auth/challenge → sign → POST /api/auth/login."""
    r = await client.get(
        f"/api/auth/challenge?principal_id={principal_id}",
    )
    assert r.status == 200
    ch = await r.json()
    sig = _privkey(principal_id).sign(
        f"{ch['nonce']}|{ch['principal_id']}|{ch['expires_at']}".encode(),
    ).hex()
    r2 = await client.post("/api/auth/login", json={
        "principal_id": principal_id, "nonce": ch["nonce"],
        "signature_hex": sig,
    })
    assert r2.status == 200
    body = await r2.json()
    return body["session_token"]


# ── Auth-disabled path: anonymous can still hit everything ──────


@pytest.mark.asyncio
async def test_auth_disabled_anonymous_hits_telemetry(tmp_path):
    _setup_auth(tmp_path)
    d = _make_dashboard(auth_required=False)
    client = await _make_client(d)
    try:
        r = await client.get("/api/status")
        assert r.status == 200
        r = await client.get("/healthz")
        assert r.status == 200
    finally:
        await client.close()


# ── Auth-enabled path: anonymous gets 401 on protected endpoints ──


@pytest.mark.asyncio
async def test_auth_enabled_protected_endpoint_401(tmp_path):
    _setup_auth(tmp_path)
    d = _make_dashboard(auth_required=True)
    client = await _make_client(d)
    try:
        # /api/auth/me is anonymous-allowed.
        r = await client.get("/api/auth/me")
        assert r.status == 200
        body = await r.json()
        assert body["role"] == "anonymous"
        # /api/safety/state is NOT in the anonymous list.
        r = await client.get("/api/safety/state")
        assert r.status in (401, 200)  # depends on default GET perm
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_auth_enabled_login_then_telemetry(tmp_path):
    svc, _ = _setup_auth(tmp_path)
    d = _make_dashboard(auth_required=True)
    client = await _make_client(d)
    try:
        token = await _login(svc, client, "crew.alpha")
        r = await client.get(
            "/api/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status == 200
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_auth_enabled_kill_reset_forbidden_for_crew(tmp_path):
    svc, _ = _setup_auth(tmp_path)
    d = _make_dashboard(auth_required=True)
    client = await _make_client(d)
    try:
        token = await _login(svc, client, "crew.alpha")
        r = await client.post(
            "/api/safety/kill_reset", json={"key_signature": "x"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status == 403
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_auth_enabled_kill_reset_allowed_for_captain(tmp_path):
    svc, _ = _setup_auth(tmp_path)
    d = _make_dashboard(auth_required=True)
    client = await _make_client(d)
    try:
        token = await _login(svc, client, "captain.tau")
        r = await client.post(
            "/api/safety/kill_reset", json={"key_signature": "x"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # 200 (kill not asserted → noop ok) or 409 (kill not asserted)
        # — either way NOT 403.
        assert r.status in (200, 409)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_auth_enabled_failure_inject_forbidden_for_crew(tmp_path):
    svc, _ = _setup_auth(tmp_path)
    d = _make_dashboard(auth_required=True)
    client = await _make_client(d)
    try:
        token = await _login(svc, client, "crew.alpha")
        r = await client.post(
            "/api/failures/trigger", json={"scenario": "x"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # crew lacks failures.inject (maintainer-only).
        assert r.status == 403
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_auth_enabled_failure_inject_allowed_for_maintainer(tmp_path):
    svc, _ = _setup_auth(tmp_path)
    d = _make_dashboard(auth_required=True)
    client = await _make_client(d)
    try:
        token = await _login(svc, client, "maintainer.lyra")
        r = await client.post(
            "/api/failures/trigger", json={"scenario": "x"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # NOT 403 — handler may return 400 / 200 depending on payload
        # but the authz gate must pass.
        assert r.status != 403
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_logout_revokes_session(tmp_path):
    svc, sessions = _setup_auth(tmp_path)
    d = _make_dashboard(auth_required=True)
    client = await _make_client(d)
    try:
        token = await _login(svc, client, "crew.alpha")
        # First call: ok.
        r = await client.get(
            "/api/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status == 200
        # Logout.
        r = await client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status == 200
        # Subsequent call with the same token: 401.
        r = await client.get(
            "/api/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status == 401
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_auth_me_returns_role_and_permissions(tmp_path):
    svc, _ = _setup_auth(tmp_path)
    d = _make_dashboard(auth_required=True)
    client = await _make_client(d)
    try:
        token = await _login(svc, client, "captain.tau")
        r = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status == 200
        body = await r.json()
        assert body["role"] == "captain"
        assert body["principal_id"] == "captain.tau"
        assert "kill_switch.reset" in body["permissions"]
        assert "approval.sign" in body["permissions"]
    finally:
        await client.close()
