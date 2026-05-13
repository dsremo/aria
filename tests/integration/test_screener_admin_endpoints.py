"""Tests for the admin / rotate / usage / bulk-stream endpoints."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from aria.products.conjunction_screener.service import create_app
from aria.products.conjunction_screener.tenants import TenantStore


# Audit CRIT-3 — the wire admin token is HMAC-SHA-256 of the configured
# secret keyed by the service id, so a token minted for the screener is
# NOT valid against the cubesat advisor (or vice versa).
ADMIN_SECRET = "A" * 64
SCREENER_SERVICE_ID = b"aria-screener:v1"
ADMIN_WIRE_TOKEN = hmac.new(
    ADMIN_SECRET.encode("utf-8"), SCREENER_SERVICE_ID, hashlib.sha256,
).hexdigest()


async def _client(app):
    from aiohttp.test_utils import TestServer, TestClient
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    return client


@pytest.fixture
def store(tmp_path: Path) -> TenantStore:
    return TenantStore(tmp_path / "tenants.sqlite3")


class TestAdminEndpoints:
    @pytest.mark.asyncio
    async def test_admin_create_returns_key(self, store: TenantStore):
        app = create_app(tenant_store=store, admin_token_hex=ADMIN_SECRET)
        client = await _client(app)
        try:
            resp = await client.post(
                "/v1/admin/tenants",
                json={"tenant_id": "acme", "rate_limit_per_min": 50},
                headers={"X-ARIA-Admin-Token": ADMIN_WIRE_TOKEN},
            )
            assert resp.status == 200
            body = await resp.json()
            assert body["tenant_id"] == "acme"
            assert len(body["api_key_hex"]) == 64
            assert body["rate_limit_per_min"] == 50
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_admin_unauthed_fails(self, store: TenantStore):
        app = create_app(tenant_store=store, admin_token_hex=ADMIN_SECRET)
        client = await _client(app)
        try:
            resp = await client.post(
                "/v1/admin/tenants",
                json={"tenant_id": "acme"},
                headers={"X-ARIA-Admin-Token": "wrong"},
            )
            assert resp.status == 401
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_admin_suspend_blocks_screen(self, store: TenantStore):
        t = store.create_tenant("acme")
        app = create_app(tenant_store=store, admin_token_hex=ADMIN_SECRET)
        client = await _client(app)
        try:
            r = await client.post(
                "/v1/admin/tenants/suspend",
                json={"tenant_id": "acme", "suspended": True},
                headers={"X-ARIA-Admin-Token": ADMIN_WIRE_TOKEN},
            )
            assert r.status == 200
            r2 = await client.post(
                "/v1/screen", json={},
                headers={"X-ARIA-Token": t.api_key_hex},
            )
            assert r2.status == 401
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_admin_list_tenants(self, store: TenantStore):
        store.create_tenant("acme")
        store.create_tenant("orbit-co")
        app = create_app(tenant_store=store, admin_token_hex=ADMIN_SECRET)
        client = await _client(app)
        try:
            r = await client.get(
                "/v1/admin/tenants",
                headers={"X-ARIA-Admin-Token": ADMIN_WIRE_TOKEN},
            )
            assert r.status == 200
            body = await r.json()
            ids = sorted(t["tenant_id"] for t in body["tenants"])
            assert ids == ["acme", "orbit-co"]
        finally:
            await client.close()


class TestKeyRotationHTTP:
    @pytest.mark.asyncio
    async def test_rotate_returns_new_key(self, store: TenantStore):
        t = store.create_tenant("acme")
        app = create_app(tenant_store=store)
        client = await _client(app)
        try:
            r = await client.post(
                "/v1/rotate_key",
                headers={"X-ARIA-Token": t.api_key_hex},
            )
            assert r.status == 200
            body = await r.json()
            assert body["tenant_id"] == "acme"
            assert body["new_api_key_hex"] != t.api_key_hex
            assert len(body["new_api_key_hex"]) == 64
            assert body["previous_expires_at"] > 0
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_old_key_works_in_grace_window(self, store: TenantStore):
        t = store.create_tenant("acme")
        store.rotate_key("acme")
        app = create_app(tenant_store=store)
        client = await _client(app)
        try:
            r = await client.get(
                "/v1/usage",
                headers={"X-ARIA-Token": t.api_key_hex},
            )
            # Old key authorises within grace window.  Even though the
            # request itself is empty, auth works.
            assert r.status == 200
        finally:
            await client.close()


class TestUsageEndpoint:
    @pytest.mark.asyncio
    async def test_usage_summary_empty_for_new_tenant(self, store: TenantStore):
        t = store.create_tenant("acme")
        app = create_app(tenant_store=store)
        client = await _client(app)
        try:
            r = await client.get(
                "/v1/usage",
                headers={"X-ARIA-Token": t.api_key_hex},
            )
            assert r.status == 200
            body = await r.json()
            assert body["tenant_id"] == "acme"
            assert body["request_count"] == 0
        finally:
            await client.close()


class TestBulkStream:
    @pytest.mark.asyncio
    async def test_bulk_stream_emits_one_line_per_secondary(
        self, store: TenantStore,
    ):
        from aria.validation import iridium_cosmos_replay as ic
        t = store.create_tenant("acme")
        app = create_app(tenant_store=store)
        client = await _client(app)
        try:
            inputs = ic.load_inputs()
            primary = {
                "norad_id": inputs.primary_norad_id,
                "name": inputs.primary_name,
                "line1": inputs.primary_line1,
                "line2": inputs.primary_line2,
                "radius_m": inputs.primary_radius_m,
            }
            secondary = {
                "norad_id": inputs.secondary_norad_id,
                "name": inputs.secondary_name,
                "line1": inputs.secondary_line1,
                "line2": inputs.secondary_line2,
                "radius_m": inputs.secondary_radius_m,
            }
            body = {
                "primary": primary,
                "secondaries": [secondary, secondary],
                "approx_tca_utc": "2009-02-10T16:56:00Z",
            }
            r = await client.post(
                "/v1/screen_bulk", json=body,
                headers={"X-ARIA-Token": t.api_key_hex},
            )
            assert r.status == 200
            text = (await r.read()).decode("utf-8")
            lines = [ln for ln in text.splitlines() if ln.strip()]
            assert len(lines) == 2
            for ln in lines:
                rec = json.loads(ln)
                assert rec["primary_norad_id"] == inputs.primary_norad_id
                assert rec["risk_level"] in ("RED", "YELLOW", "GREEN")
        finally:
            await client.close()
