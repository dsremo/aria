"""Tests for the multi-tenant SQLite store + key-rotation grace window."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from aria.products.conjunction_screener.tenants import (
    Tenant, TenantStore, ROTATION_GRACE_SECONDS,
)


@pytest.fixture
def store(tmp_path: Path) -> TenantStore:
    return TenantStore(tmp_path / "tenants.sqlite3")


class TestCRUD:
    def test_create_then_get(self, store: TenantStore):
        # Audit HIGH-11 — create_tenant returns the plaintext key once
        # (so the operator can hand it to the customer); subsequent
        # reads from the store return the SHA-256 digest at rest.
        t = store.create_tenant("acme", rate_limit_per_min=120, rate_limit_per_day=20000)
        assert t.tenant_id == "acme"
        assert len(t.api_key_hex) == 64    # plaintext at-create
        assert t.previous_api_key_hex is None
        got = store.get("acme")
        assert got is not None
        # Round-2 audit NEW-HIGH-6 — at-rest format upgraded from
        # ``sha256:`` (unsalted) to ``hmac:`` (HMAC-SHA-256 with
        # per-deployment salt).  Legacy ``sha256:`` rows are still
        # readable for one rotation cycle of compatibility.
        assert got.api_key_hex.startswith("hmac:")
        # Round-trip the plaintext through find_by_key to confirm the
        # hash matches.
        assert store.find_by_key(t.api_key_hex).tenant_id == "acme"

    def test_list_all_sorted(self, store: TenantStore):
        store.create_tenant("zeta")
        store.create_tenant("alpha")
        ids = [x.tenant_id for x in store.list_all()]
        assert ids == ["alpha", "zeta"]

    def test_delete(self, store: TenantStore):
        store.create_tenant("acme")
        store.delete("acme")
        assert store.get("acme") is None

    def test_update_rate_limits(self, store: TenantStore):
        store.create_tenant("acme")
        store.update_rate_limits("acme", per_min=999)
        got = store.get("acme")
        assert got is not None and got.rate_limit_per_min == 999


class TestAuth:
    def test_active_key_matches(self, store: TenantStore):
        t = store.create_tenant("acme")
        assert store.find_by_key(t.api_key_hex).tenant_id == "acme"

    def test_unknown_key_is_none(self, store: TenantStore):
        store.create_tenant("acme")
        assert store.find_by_key("0" * 64) is None

    def test_suspended_tenant_blocked(self, store: TenantStore):
        t = store.create_tenant("acme")
        store.suspend("acme", suspended=True)
        assert store.find_by_key(t.api_key_hex) is None

    def test_resume_tenant_works(self, store: TenantStore):
        t = store.create_tenant("acme")
        store.suspend("acme", suspended=True)
        store.suspend("acme", suspended=False)
        assert store.find_by_key(t.api_key_hex).tenant_id == "acme"


class TestKeyRotation:
    def test_rotation_changes_active_key(self, store: TenantStore):
        # Audit HIGH-11 — both create and rotate return the plaintext.
        # The previous-key slot stores the SHA-256 digest of the OLD
        # plaintext (operator-side has no plaintext access to past keys).
        from aria.products.conjunction_screener.tenants import _hash_key
        t = store.create_tenant("acme")
        old_plaintext = t.api_key_hex
        new_t = store.rotate_key("acme")
        assert new_t.api_key_hex != old_plaintext
        # Round-2 audit NEW-HIGH-6 — previous-slot stores the salted
        # HMAC digest, not unsalted SHA-256.
        assert new_t.previous_api_key_hex == _hash_key(old_plaintext)
        assert new_t.previous_api_key_hex.startswith("hmac:")

    def test_old_key_works_during_grace_window(self, store: TenantStore):
        t = store.create_tenant("acme")
        old_key = t.api_key_hex
        store.rotate_key("acme")
        # Old key still resolves to the tenant.
        match = store.find_by_key(old_key)
        assert match is not None
        assert match.tenant_id == "acme"

    def test_old_key_rejected_after_grace_expires(self, store: TenantStore):
        t = store.create_tenant("acme")
        old_key = t.api_key_hex
        store.rotate_key("acme", grace_seconds=0)
        time.sleep(0.01)
        assert store.find_by_key(old_key) is None


class TestUsage:
    def test_record_and_summary(self, store: TenantStore):
        store.create_tenant("acme")
        for i in range(5):
            store.record_usage("acme", "screen", n_pairs=2, elapsed_ms=10.0 * (i + 1))
        summary = store.usage_summary("acme")
        assert summary["request_count"] == 5
        assert summary["pair_count"] == 10
        assert 9.0 <= summary["avg_elapsed_ms"] <= 31.0

    def test_summary_empty_returns_zero(self, store: TenantStore):
        store.create_tenant("acme")
        s = store.usage_summary("acme")
        assert s["request_count"] == 0
        assert s["pair_count"] == 0
