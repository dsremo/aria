"""R32 Phase 2 — aiohttp middleware + require_permission tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aria.security import principals as p
from aria.security import auth_service as auth
from aria.security import session_store as sst
from aria.security.middleware import (
    make_auth_middleware,
    require_permission,
)


REPO = Path(__file__).resolve().parents[2]
SEALED = REPO / "data" / "sealed"
DEV_KEYS = json.loads((REPO / "tests" / "fixtures" / "dev_keys.json").read_text())


def _privkey(name: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(
        bytes.fromhex(DEV_KEYS[name]["priv_seed_hex"]),
    )


def _setup(tmp_path: Path) -> tuple[auth.AuthService, sst.SessionStore]:
    p.reset_for_test(sealed_dir=SEALED, runtime_dir=tmp_path)
    sessions = sst.SessionStore(runtime_dir=tmp_path)
    sst._INSTANCE = sessions   # share singleton with middleware
    auth.reset_for_test(sessions=sessions)
    return auth.get_auth_service(), sessions


def _login_token(svc: auth.AuthService, principal_id: str) -> str:
    ch = svc.issue_challenge(principal_id)
    sig = _privkey(principal_id).sign(ch.signing_payload()).hex()
    s = svc.login(principal_id, ch.nonce, sig)
    return s.token


def _build_app() -> web.Application:
    app = web.Application(middlewares=[make_auth_middleware()])

    async def healthz(request):
        return web.json_response({"ok": True})

    @require_permission("telemetry.read")
    async def telemetry(request):
        return web.json_response({"data": [1, 2, 3]})

    @require_permission("approval.sign")
    async def sign(request):
        return web.json_response({"signed": True})

    @require_permission("kill_switch.reset")
    async def kill_reset(request):
        return web.json_response({"reset": True})

    app.router.add_get("/healthz", healthz)
    app.router.add_get("/api/telemetry", telemetry)
    app.router.add_post("/api/safety/approve", sign)
    app.router.add_post("/api/safety/kill_reset", kill_reset)
    return app


async def _make_client() -> TestClient:
    server = TestServer(_build_app())
    client = TestClient(server)
    await client.start_server()
    return client


@pytest.mark.asyncio
class TestMiddleware:
    async def test_healthz_anonymous_ok(self, tmp_path):
        _setup(tmp_path)
        client = await _make_client()
        try:
            r = await client.get("/healthz")
            assert r.status == 200
        finally:
            await client.close()

    async def test_protected_no_token_401(self, tmp_path):
        _setup(tmp_path)
        client = await _make_client()
        try:
            r = await client.get("/api/telemetry")
            assert r.status == 401
        finally:
            await client.close()

    async def test_protected_bad_token_401(self, tmp_path):
        _setup(tmp_path)
        client = await _make_client()
        try:
            r = await client.get(
                "/api/telemetry",
                headers={"Authorization": "Bearer " + "0" * 64},
            )
            assert r.status == 401
        finally:
            await client.close()

    async def test_telemetry_read_allowed_for_crew(self, tmp_path):
        svc, _ = _setup(tmp_path)
        client = await _make_client()
        try:
            token = _login_token(svc, "crew.alpha")
            r = await client.get(
                "/api/telemetry",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status == 200
        finally:
            await client.close()

    async def test_approval_sign_no_token_401(self, tmp_path):
        _setup(tmp_path)
        client = await _make_client()
        try:
            r = await client.post("/api/safety/approve", json={})
            assert r.status == 401
        finally:
            await client.close()

    async def test_approval_sign_allowed_for_crew(self, tmp_path):
        svc, _ = _setup(tmp_path)
        client = await _make_client()
        try:
            token = _login_token(svc, "crew.alpha")
            r = await client.post(
                "/api/safety/approve", json={},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status == 200
        finally:
            await client.close()

    async def test_kill_reset_forbidden_for_crew(self, tmp_path):
        svc, _ = _setup(tmp_path)
        client = await _make_client()
        try:
            token = _login_token(svc, "crew.alpha")
            r = await client.post(
                "/api/safety/kill_reset", json={},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status == 403
        finally:
            await client.close()

    async def test_kill_reset_allowed_for_captain(self, tmp_path):
        svc, _ = _setup(tmp_path)
        client = await _make_client()
        try:
            token = _login_token(svc, "captain.tau")
            r = await client.post(
                "/api/safety/kill_reset", json={},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status == 200
        finally:
            await client.close()

    async def test_revoked_session_401(self, tmp_path):
        svc, sessions = _setup(tmp_path)
        client = await _make_client()
        try:
            token = _login_token(svc, "crew.alpha")
            sessions.revoke(token)
            r = await client.get(
                "/api/telemetry",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status == 401
        finally:
            await client.close()
