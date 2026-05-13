"""R33 Phase 4 — admin endpoints e2e against the live web dashboard."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aria.simulator.web_dashboard import DashboardConfig, WebDashboard
from aria.security import principals as p
from aria.security import auth_service as auth
from aria.security import session_store as sst
from aria.security import admin
from aria.safety.approval_queue import (
    get_approval_queue,
    reset_for_test as reset_aq,
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
    reset_aq()
    admin.reset_for_test()
    # _create_app calls register_admin_executors itself.
    return auth.get_auth_service()


async def _login(svc: auth.AuthService, client: TestClient,
                 principal_id: str) -> str:
    r = await client.get(
        f"/api/auth/challenge?principal_id={principal_id}",
    )
    body = await r.json()
    sig = _privkey(principal_id).sign(
        f"{body['nonce']}|{body['principal_id']}|{body['expires_at']}".encode(),
    ).hex()
    r2 = await client.post("/api/auth/login", json={
        "principal_id": principal_id, "nonce": body["nonce"],
        "signature_hex": sig,
    })
    return (await r2.json())["session_token"]


async def _make_client(auth_required: bool = True) -> TestClient:
    cfg = DashboardConfig(host="127.0.0.1", port=0,
                          auth_required=auth_required)
    d = WebDashboard(cfg)
    server = TestServer(d.app)
    client = TestClient(server)
    await client.start_server()
    return client


# ── List + me ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_principals_list_visible_to_authenticated(tmp_path):
    svc = _setup(tmp_path)
    client = await _make_client()
    try:
        token = await _login(svc, client, "crew.alpha")
        r = await client.get("/api/admin/principals",
                             headers={"Authorization": f"Bearer {token}"})
        assert r.status == 200
        body = await r.json()
        assert any(x["principal_id"] == "captain.tau"
                   for x in body["principals"])
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_admin_permissions_actor_holds_filter(tmp_path):
    svc = _setup(tmp_path)
    client = await _make_client()
    try:
        token = await _login(svc, client, "crew.alpha")
        r = await client.get("/api/admin/permissions",
                             headers={"Authorization": f"Bearer {token}"})
        body = await r.json()
        # Crew holds approval.sign but not principal.create.
        assert "approval.sign" in body["actor_holds"]
        assert "principal.create" not in body["actor_holds"]
        assert body["actor_role"] == "crew"
    finally:
        await client.close()


# ── Forbidden paths ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_forbidden_for_crew(tmp_path):
    svc = _setup(tmp_path)
    client = await _make_client()
    try:
        token = await _login(svc, client, "crew.alpha")
        r = await client.post(
            "/api/admin/principals",
            json={"principal_id": "x", "role": "crew",
                  "pubkey_hex": "00" * 32},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status == 403
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_create_allowed_for_captain(tmp_path):
    svc = _setup(tmp_path)
    client = await _make_client()
    try:
        token = await _login(svc, client, "captain.tau")
        new_pub = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
        r = await client.post(
            "/api/admin/principals",
            json={"principal_id": "crew.test_admin", "role": "crew",
                  "pubkey_hex": new_pub},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status == 200
        body = await r.json()
        assert body["ok"] is True
        assert body["proposal_id"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_anonymous_blocked_at_admin(tmp_path):
    _setup(tmp_path)
    client = await _make_client()
    try:
        r = await client.get("/api/admin/principals")
        assert r.status == 401
    finally:
        await client.close()


# ── Custom role flow ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_custom_role_full_flow(tmp_path):
    svc = _setup(tmp_path)
    client = await _make_client()
    try:
        token = await _login(svc, client, "captain.tau")
        # 1. Captain proposes a custom role.
        r = await client.post(
            "/api/admin/roles/custom",
            json={"name": "ops_specialist", "inherits": ["operator"],
                  "permissions": ["telemetry.read", "telemetry.read_sensitive"],
                  "description": "ops with sensitive view"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status == 200
        proposal_id = (await r.json())["proposal_id"]

        # 2. Captain signs first; bring queue cooling-off to 0 for test.
        q = get_approval_queue()
        q._proposals[proposal_id].cooling_off_s = 0.0
        r2 = await client.post(
            "/api/safety/approve",
            json={"proposal_id": proposal_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status == 200

        # 3. Maintainer signs.
        m_token = await _login(svc, client, "maintainer.lyra")
        r3 = await client.post(
            "/api/safety/approve",
            json={"proposal_id": proposal_id},
            headers={"Authorization": f"Bearer {m_token}"},
        )
        assert r3.status == 200

        # 4. Confirm role visible.
        r4 = await client.get(
            "/api/admin/roles",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = await r4.json()
        names = [x["name"] for x in body["roles"]]
        assert "ops_specialist" in names
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_custom_role_unknown_perm_400(tmp_path):
    svc = _setup(tmp_path)
    client = await _make_client()
    try:
        token = await _login(svc, client, "captain.tau")
        r = await client.post(
            "/api/admin/roles/custom",
            json={"name": "bad_role", "inherits": ["operator"],
                  "permissions": ["telemetry.read", "fictional.permission"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        # propose_create_custom_role raises AdminError → handler returns 400.
        assert r.status == 400
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_custom_role_sealed_name_400(tmp_path):
    svc = _setup(tmp_path)
    client = await _make_client()
    try:
        token = await _login(svc, client, "captain.tau")
        r = await client.post(
            "/api/admin/roles/custom",
            json={"name": "captain", "inherits": ["operator"],
                  "permissions": []},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status == 400
    finally:
        await client.close()
