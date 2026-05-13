"""Sprint 7 tests — Admin Panel: Full UI Coverage for All APIs.

All tests are pure unit/integration tests — no real DB required.
Covers:
  - TestAdminPasswordReset    — POST /users/{id}/reset-password (6 tests)
  - TestMemoryStoreAdminStubs — user/tenant/key stubs in memory_store.py (12 tests)
  - TestAdminUserAPI          — full /users + /keys round-trip via demo_client (10 tests)
  - TestAdminTenantsAPI       — /tenants round-trip (dsremo-scope demo) (6 tests)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run a coroutine synchronously in a new event loop."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# 1. TestAdminPasswordReset
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def demo_client():
    """Demo-mode TestClient — role='admin', no real DB."""
    from aria.dsremo.api.app import create_app
    app = create_app(demo=True)
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def demo_client_with_user(demo_client):
    """Create a test user in memory store and return (client, user_id)."""
    from aria.dsremo.db import memory_store as ms

    user = _run(ms.create_user(
        email="target@test.local",
        password_hash="$bcrypt$initial",
        role="viewer",
    ))
    return demo_client, user["id"]


class TestAdminPasswordReset:
    """POST /api/v1/users/{id}/reset-password."""

    def test_admin_can_reset_password_200(self, demo_client_with_user):
        client, user_id = demo_client_with_user
        resp = client.post(
            f"/api/v1/users/{user_id}/reset-password",
            json={"new_password": "NewSecure123"},
        )
        assert resp.status_code == 200

    def test_reset_returns_message(self, demo_client_with_user):
        client, user_id = demo_client_with_user
        resp = client.post(
            f"/api/v1/users/{user_id}/reset-password",
            json={"new_password": "AnotherPass1"},
        )
        data = resp.json()
        assert "message" in data
        assert "sign in" in data["message"].lower()

    def test_unknown_user_returns_404(self, demo_client):
        resp = demo_client.post(
            "/api/v1/users/00000000-0000-0000-0000-000000000000/reset-password",
            json={"new_password": "ValidPass99"},
        )
        assert resp.status_code == 404

    def test_password_too_short_returns_422(self, demo_client_with_user):
        client, user_id = demo_client_with_user
        resp = client.post(
            f"/api/v1/users/{user_id}/reset-password",
            json={"new_password": "short"},
        )
        assert resp.status_code == 422

    def test_password_too_long_returns_422(self, demo_client_with_user):
        client, user_id = demo_client_with_user
        resp = client.post(
            f"/api/v1/users/{user_id}/reset-password",
            json={"new_password": "x" * 129},
        )
        assert resp.status_code == 422

    def test_password_hash_is_updated_in_store(self, demo_client_with_user):
        """After reset, the stored hash must differ from the initial stub hash."""
        from aria.dsremo.db import memory_store as ms
        client, user_id = demo_client_with_user
        client.post(
            f"/api/v1/users/{user_id}/reset-password",
            json={"new_password": "FreshNew456"},
        )
        user = _run(ms.get_user_by_id(user_id))
        # The new hash is a real bcrypt hash — definitely not the initial stub
        assert user is not None
        assert user["password_hash"] != "$bcrypt$initial"


# ---------------------------------------------------------------------------
# 2. TestMemoryStoreAdminStubs
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=False)
def fresh_store():
    """Temporarily swap _users and _tenants to isolated dicts for stub tests."""
    from aria.dsremo.db import memory_store as ms
    import uuid

    original_users   = ms._users.copy()
    original_tenants = ms._tenants.copy()
    original_keys    = list(ms._admin_api_keys)

    # Clear for isolation
    ms._users.clear()
    ms._tenants.clear()
    ms._admin_api_keys.clear()

    yield ms

    # Restore
    ms._users.clear()
    ms._users.update(original_users)
    ms._tenants.clear()
    ms._tenants.update(original_tenants)
    ms._admin_api_keys.clear()
    ms._admin_api_keys.extend(original_keys)


class TestMemoryStoreAdminStubs:
    """Direct async stub tests — no HTTP layer."""

    # --- User stubs ---

    def test_create_user_stores_record(self, fresh_store):
        ms = fresh_store
        user = _run(ms.create_user("alice@x.com", "hash123", "viewer"))
        assert user["email"] == "alice@x.com"
        assert user["role"] == "viewer"
        assert user["active"] is True

    def test_list_users_returns_created_records(self, fresh_store):
        ms = fresh_store
        _run(ms.create_user("bob@x.com", "h1", "operator"))
        _run(ms.create_user("carol@x.com", "h2", "admin"))
        users = _run(ms.list_users())
        emails = {u["email"] for u in users}
        assert "bob@x.com" in emails
        assert "carol@x.com" in emails

    def test_get_user_by_id_returns_correct_record(self, fresh_store):
        ms = fresh_store
        created = _run(ms.create_user("dave@x.com", "h", "viewer"))
        fetched = _run(ms.get_user_by_id(created["id"]))
        assert fetched is not None
        assert fetched["email"] == "dave@x.com"

    def test_get_user_by_id_unknown_returns_none(self, fresh_store):
        ms = fresh_store
        result = _run(ms.get_user_by_id("nonexistent-id"))
        assert result is None

    def test_update_user_role_returns_true(self, fresh_store):
        ms = fresh_store
        user = _run(ms.create_user("eve@x.com", "h", "viewer"))
        ok = _run(ms.update_user_role(user["id"], "operator"))
        assert ok is True
        updated = _run(ms.get_user_by_id(user["id"]))
        assert updated["role"] == "operator"

    def test_deactivate_user_sets_active_false(self, fresh_store):
        ms = fresh_store
        user = _run(ms.create_user("frank@x.com", "h", "viewer"))
        ok = _run(ms.deactivate_user_by_id(user["id"]))
        assert ok is True
        record = _run(ms.get_user_by_id(user["id"]))
        assert record["active"] is False

    def test_reactivate_user_sets_active_true(self, fresh_store):
        ms = fresh_store
        user = _run(ms.create_user("grace@x.com", "h", "viewer"))
        _run(ms.deactivate_user_by_id(user["id"]))
        ok = _run(ms.reactivate_user(user["id"]))
        assert ok is True
        record = _run(ms.get_user_by_id(user["id"]))
        assert record["active"] is True

    # --- Tenant stubs ---

    def test_create_tenant_stores_record(self, fresh_store):
        ms = fresh_store
        tenant = _run(ms.create_tenant("acme", "Acme Corp", "pro"))
        assert tenant["id"] == "acme"
        assert tenant["name"] == "Acme Corp"
        assert tenant["plan"] == "pro"

    def test_list_tenants_returns_records(self, fresh_store):
        ms = fresh_store
        _run(ms.create_tenant("t1", "T1 Ltd"))
        _run(ms.create_tenant("t2", "T2 Ltd"))
        tenants = _run(ms.list_tenants())
        ids = {t["id"] for t in tenants}
        assert "t1" in ids
        assert "t2" in ids

    def test_update_tenant_changes_name(self, fresh_store):
        ms = fresh_store
        _run(ms.create_tenant("xyz", "XYZ Inc"))
        ok = _run(ms.update_tenant("xyz", name="XYZ Renamed"))
        assert ok is True
        t = _run(ms.get_tenant_by_id("xyz"))
        assert t["name"] == "XYZ Renamed"

    def test_update_tenant_unknown_returns_false(self, fresh_store):
        ms = fresh_store
        ok = _run(ms.update_tenant("no-such-tenant", name="Nope"))
        assert ok is False

    def test_revoke_api_key_by_prefix(self, fresh_store):
        ms = fresh_store
        # Manually inject a key record
        ms._admin_api_keys.append({
            "label": "test-key",
            "hash_prefix": "abc123",
            "tenant_id": "default",
            "active": True,
        })
        ok = _run(ms.revoke_api_key_by_prefix("abc"))
        assert ok is True
        keys = _run(ms.list_api_keys_for_tenant())
        assert len(keys) == 0  # filtered out because active=False


# ---------------------------------------------------------------------------
# 3. TestAdminUserAPI — /users + /keys via demo_client
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def admin_client():
    """Separate demo client for user API tests (module-scoped, clean per-module state)."""
    from aria.dsremo.api.app import create_app
    app = create_app(demo=True)
    with TestClient(app) as client:
        yield client


class TestAdminUserAPI:
    """HTTP-level tests for /users and /keys routes in demo mode."""

    def test_list_users_returns_200(self, admin_client):
        resp = admin_client.get("/api/v1/users")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_users_includes_demo_admin(self, admin_client):
        resp = admin_client.get("/api/v1/users")
        emails = [u["email"] for u in resp.json()]
        assert "admin@demo.local" in emails

    def test_create_user_returns_201(self, admin_client):
        resp = admin_client.post(
            "/api/v1/users",
            json={"email": "newuser@x.com", "password": "Pass12345", "role": "viewer"},
        )
        assert resp.status_code == 201

    def test_create_user_returns_correct_email(self, admin_client):
        resp = admin_client.post(
            "/api/v1/users",
            json={"email": "unique789@x.com", "password": "Pass12345", "role": "operator"},
        )
        assert resp.json()["email"] == "unique789@x.com"

    def test_patch_user_role_returns_200(self, admin_client):
        # Create a user first
        create_resp = admin_client.post(
            "/api/v1/users",
            json={"email": "role_test@x.com", "password": "Pass99999", "role": "viewer"},
        )
        user_id = create_resp.json()["id"]
        resp = admin_client.patch(
            f"/api/v1/users/{user_id}/role",
            json={"role": "operator"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "operator"

    def test_deactivate_user_returns_200(self, admin_client):
        create_resp = admin_client.post(
            "/api/v1/users",
            json={"email": "deact@x.com", "password": "Pass11111", "role": "viewer"},
        )
        user_id = create_resp.json()["id"]
        resp = admin_client.post(f"/api/v1/users/{user_id}/deactivate")
        assert resp.status_code == 200

    def test_reactivate_user_returns_200(self, admin_client):
        create_resp = admin_client.post(
            "/api/v1/users",
            json={"email": "react@x.com", "password": "Pass22222", "role": "viewer"},
        )
        user_id = create_resp.json()["id"]
        admin_client.post(f"/api/v1/users/{user_id}/deactivate")
        resp = admin_client.post(f"/api/v1/users/{user_id}/reactivate")
        assert resp.status_code == 200

    def test_reset_password_returns_200(self, admin_client):
        create_resp = admin_client.post(
            "/api/v1/users",
            json={"email": "pwreset@x.com", "password": "OldPass123", "role": "viewer"},
        )
        user_id = create_resp.json()["id"]
        resp = admin_client.post(
            f"/api/v1/users/{user_id}/reset-password",
            json={"new_password": "NewPass999"},
        )
        assert resp.status_code == 200

    def test_generate_api_key_returns_201(self, admin_client):
        resp = admin_client.post("/api/v1/keys", json={"label": "ci-pipeline"})
        assert resp.status_code == 201
        data = resp.json()
        assert "key" in data
        assert len(data["key"]) > 20  # plaintext key is present and non-trivial

    def test_list_api_keys_returns_200(self, admin_client):
        resp = admin_client.get("/api/v1/keys")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# 4. TestAdminTenantsAPI — /tenants routes (dsremo scope in demo)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dsremo_demo_client():
    """Demo-mode TestClient with dsremo_admin role.

    The default demo dependency returns role='admin', which is NOT in
    require_dsremo_admin's allowed set.  We use FastAPI's
    dependency_overrides to inject a dsremo_admin user so all
    require_dsremo_admin checks pass.
    """
    from aria.dsremo.api.app import create_app
    from aria.dsremo.api.dependencies import get_current_user

    dsremo_user = {
        "user_id": "dsremo-demo",
        "tenant_id": "default",
        "role": "dsremo_admin",
        "scope": "dsremo",
    }

    app = create_app(demo=True)
    app.dependency_overrides[get_current_user] = lambda: dsremo_user

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


class TestAdminTenantsAPI:
    """HTTP-level tests for /tenants routes (dsremo admin only)."""

    def test_list_tenants_returns_200(self, dsremo_demo_client):
        resp = dsremo_demo_client.get("/api/v1/tenants")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_tenants_includes_default(self, dsremo_demo_client):
        resp = dsremo_demo_client.get("/api/v1/tenants")
        ids = [t["id"] for t in resp.json()]
        assert "default" in ids

    def test_create_tenant_returns_201(self, dsremo_demo_client):
        resp = dsremo_demo_client.post(
            "/api/v1/tenants",
            json={"id": "sprint7-test", "name": "Sprint7 Test Tenant", "plan": "pro"},
        )
        assert resp.status_code == 201

    def test_create_tenant_stores_correct_fields(self, dsremo_demo_client):
        resp = dsremo_demo_client.post(
            "/api/v1/tenants",
            json={"id": "sprint7-fields", "name": "Fields Tenant", "plan": "free"},
        )
        data = resp.json()
        assert data["id"] == "sprint7-fields"
        assert data["name"] == "Fields Tenant"

    def test_create_duplicate_tenant_returns_409(self, dsremo_demo_client):
        dsremo_demo_client.post(
            "/api/v1/tenants",
            json={"id": "dup-tenant", "name": "Dup", "plan": "free"},
        )
        resp = dsremo_demo_client.post(
            "/api/v1/tenants",
            json={"id": "dup-tenant", "name": "Dup Again", "plan": "free"},
        )
        assert resp.status_code == 409

    def test_patch_tenant_updates_name(self, dsremo_demo_client):
        dsremo_demo_client.post(
            "/api/v1/tenants",
            json={"id": "patch-me", "name": "Old Name", "plan": "free"},
        )
        resp = dsremo_demo_client.patch(
            "/api/v1/tenants/patch-me",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"
