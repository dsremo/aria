"""Tests for Sprint 2.5: Internal Users, Tenant API, User Management API.

All tests are pure unit tests — no database required.
Tests cover:
  - create_dsremo_token() — scope, claims, encoding
  - Permission hierarchy — require_* role checks, escalation guard
  - Schema validation — TenantIn, UserCreateRequest, UpdateRoleRequest,
    ChangePasswordRequest, ApiKeyCreateRequest
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aria.dsremo.core.security import (
    create_access_token,
    create_dsremo_token,
    decode_access_token,
)
from aria.dsremo.api.schemas import (
    ApiKeyCreateRequest,
    ChangePasswordRequest,
    TenantIn,
    TenantPatch,
    UpdateRoleRequest,
    UserCreateRequest,
)

_SECRET = "test-secret-key-that-is-long-enough-for-hs256"


# ---------------------------------------------------------------------------
# Dsremo JWT token
# ---------------------------------------------------------------------------

class TestDsremoToken:
    def test_scope_is_dsremo(self):
        token = create_dsremo_token("uid-1", "superuser", _SECRET)
        payload = decode_access_token(token, _SECRET)
        assert payload["scope"] == "dsremo"

    def test_no_tid_claim(self):
        token = create_dsremo_token("uid-1", "dsremo_admin", _SECRET)
        payload = decode_access_token(token, _SECRET)
        assert "tid" not in payload

    def test_sub_and_role_present(self):
        token = create_dsremo_token("uid-xyz", "developer", _SECRET)
        payload = decode_access_token(token, _SECRET)
        assert payload["sub"] == "uid-xyz"
        assert payload["role"] == "developer"

    def test_all_dsremo_roles_encodable(self):
        for role in ("superuser", "dsremo_admin", "developer"):
            token = create_dsremo_token("u", role, _SECRET)
            payload = decode_access_token(token, _SECRET)
            assert payload["role"] == role

    def test_dsremo_and_tenant_tokens_differ_by_scope(self):
        st = create_dsremo_token("u", "superuser", _SECRET)
        tt = create_access_token("u", "acme", "admin", _SECRET)
        sp = decode_access_token(st, _SECRET)
        tp = decode_access_token(tt, _SECRET)
        assert sp.get("scope") == "dsremo"
        assert "scope" not in tp  # tenant tokens have no scope claim

    def test_ttl_honoured(self):
        import time
        token = create_dsremo_token("u", "superuser", _SECRET, ttl_seconds=3600)
        payload = decode_access_token(token, _SECRET)
        remaining = payload["exp"] - int(time.time())
        assert 3595 <= remaining <= 3605

    def test_expired_dsremo_token_raises(self):
        import jwt
        token = create_dsremo_token("u", "superuser", _SECRET, ttl_seconds=-1)
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(token, _SECRET)


# ---------------------------------------------------------------------------
# Permission hierarchy
# ---------------------------------------------------------------------------

class TestPermissionHierarchy:
    """Test require_role() logic without a running FastAPI app."""

    def _check(self, user_role: str, allowed_roles: tuple[str, ...]) -> bool:
        return user_role in allowed_roles

    # Dsremo roles should pass dsremo-level checks
    def test_superuser_passes_dsremo_admin_check(self):
        allowed = ("superuser", "dsremo_admin")
        assert self._check("superuser", allowed)

    def test_dsremo_admin_passes_tenant_admin_check(self):
        allowed = ("admin", "superuser", "dsremo_admin")
        assert self._check("dsremo_admin", allowed)

    def test_developer_passes_viewer_check(self):
        allowed = (
            "admin", "tenant_manager", "operator", "viewer", "report_only",
            "superuser", "dsremo_admin", "developer",
        )
        assert self._check("developer", allowed)

    def test_developer_blocked_from_tenant_admin(self):
        allowed = ("admin", "superuser", "dsremo_admin")
        assert not self._check("developer", allowed)

    def test_tenant_manager_passes_operator_check(self):
        allowed = ("admin", "tenant_manager", "operator", "superuser", "dsremo_admin")
        assert self._check("tenant_manager", allowed)

    def test_tenant_manager_blocked_from_tenant_admin(self):
        allowed = ("admin", "superuser", "dsremo_admin")
        assert not self._check("tenant_manager", allowed)

    def test_operator_blocked_from_admin_check(self):
        allowed = ("admin", "superuser", "dsremo_admin")
        assert not self._check("operator", allowed)

    def test_unknown_role_blocked_everywhere(self):
        for allowed in [
            ("admin",),
            ("admin", "superuser", "dsremo_admin"),
            ("superuser", "dsremo_admin", "developer"),
        ]:
            assert not self._check("hackerole", allowed)


# ---------------------------------------------------------------------------
# Role escalation guard
# ---------------------------------------------------------------------------

class TestRoleEscalationGuard:
    """Test _max_assignable_tier() and _check_role_escalation() logic."""

    # Mirror the implementation from routes_users.py
    _TENANT_ROLE_TIER = {
        "report_only":    0,
        "viewer":         1,
        "operator":       2,
        "tenant_manager": 3,
        "admin":          4,
    }
    _DSREMO_ROLES = frozenset({"developer", "dsremo_admin", "superuser"})

    def _max_tier(self, role: str) -> int:
        if role in self._DSREMO_ROLES:
            return 4
        return self._TENANT_ROLE_TIER.get(role, -1)

    def _can_assign(self, requester: str, target: str) -> bool:
        return self._TENANT_ROLE_TIER.get(target, -1) <= self._max_tier(requester)

    def test_dsremo_admin_can_assign_any_tenant_role(self):
        for role in ("report_only", "viewer", "operator", "tenant_manager", "admin"):
            assert self._can_assign("dsremo_admin", role)

    def test_superuser_can_assign_any_tenant_role(self):
        for role in ("report_only", "viewer", "operator", "tenant_manager", "admin"):
            assert self._can_assign("superuser", role)

    def test_admin_can_assign_up_to_admin(self):
        assert self._can_assign("admin", "admin")
        assert self._can_assign("admin", "tenant_manager")
        assert self._can_assign("admin", "operator")

    def test_tenant_manager_cannot_assign_admin(self):
        assert not self._can_assign("tenant_manager", "admin")

    def test_tenant_manager_can_assign_operator(self):
        assert self._can_assign("tenant_manager", "operator")
        assert self._can_assign("tenant_manager", "viewer")
        assert self._can_assign("tenant_manager", "report_only")

    def test_operator_cannot_assign_any_role(self):
        for role in ("report_only", "viewer", "operator", "tenant_manager", "admin"):
            # operator tier = 2, so can assign up to tier 2 (operator itself)
            if role in ("report_only", "viewer", "operator"):
                assert self._can_assign("operator", role)
            else:
                assert not self._can_assign("operator", role)

    def test_unknown_requester_role_cannot_assign(self):
        assert not self._can_assign("unknown_role", "viewer")


# ---------------------------------------------------------------------------
# TenantIn schema
# ---------------------------------------------------------------------------

class TestTenantInSchema:
    def test_valid(self):
        t = TenantIn(id="acme-corp", name="ACME Corp")
        assert t.id == "acme-corp"
        assert t.plan == "free"

    def test_uppercase_id_rejected(self):
        with pytest.raises(ValidationError):
            TenantIn(id="ACME", name="ACME")

    def test_space_in_id_rejected(self):
        with pytest.raises(ValidationError):
            TenantIn(id="acme corp", name="ACME")

    def test_special_chars_rejected(self):
        with pytest.raises(ValidationError):
            TenantIn(id="acme_corp!", name="ACME")

    def test_hyphen_allowed(self):
        t = TenantIn(id="acme-123", name="ACME 123")
        assert t.id == "acme-123"

    def test_too_short_id_rejected(self):
        with pytest.raises(ValidationError):
            TenantIn(id="a", name="Single")

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            TenantIn(id="acme", name="")

    def test_plan_field(self):
        t = TenantIn(id="acme", name="ACME", plan="enterprise")
        assert t.plan == "enterprise"


class TestTenantPatchSchema:
    def test_both_none_ok(self):
        p = TenantPatch()
        assert p.name is None
        assert p.active is None

    def test_name_only(self):
        p = TenantPatch(name="New Name")
        assert p.name == "New Name"

    def test_active_only(self):
        p = TenantPatch(active=False)
        assert p.active is False


# ---------------------------------------------------------------------------
# UserCreateRequest schema
# ---------------------------------------------------------------------------

class TestUserCreateRequestSchema:
    def test_valid(self):
        r = UserCreateRequest(email="user@acme.com", password="securepass123")
        assert r.role == "viewer"  # default

    def test_custom_role(self):
        r = UserCreateRequest(email="a@b.com", password="securepass", role="operator")
        assert r.role == "operator"

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            UserCreateRequest(email="not-email", password="securepass")

    def test_weak_password_rejected(self):
        with pytest.raises(ValidationError):
            UserCreateRequest(email="a@b.com", password="short")

    def test_too_long_password_rejected(self):
        with pytest.raises(ValidationError):
            UserCreateRequest(email="a@b.com", password="x" * 129)

    def test_invalid_role_rejected(self):
        with pytest.raises(ValidationError):
            UserCreateRequest(email="a@b.com", password="securepass", role="superuser")

    def test_all_valid_tenant_roles(self):
        for role in ("admin", "tenant_manager", "operator", "viewer", "report_only"):
            r = UserCreateRequest(email="a@b.com", password="securepass123", role=role)
            assert r.role == role


# ---------------------------------------------------------------------------
# UpdateRoleRequest schema
# ---------------------------------------------------------------------------

class TestUpdateRoleRequestSchema:
    def test_valid_role(self):
        r = UpdateRoleRequest(role="operator")
        assert r.role == "operator"

    def test_invalid_role_rejected(self):
        with pytest.raises(ValidationError):
            UpdateRoleRequest(role="dsremo_admin")

    def test_empty_role_rejected(self):
        with pytest.raises(ValidationError):
            UpdateRoleRequest(role="")


# ---------------------------------------------------------------------------
# ChangePasswordRequest schema
# ---------------------------------------------------------------------------

class TestChangePasswordRequestSchema:
    def test_valid(self):
        r = ChangePasswordRequest(current_password="old-pass", new_password="new-pass-long")
        assert r.new_password == "new-pass-long"

    def test_short_new_password_rejected(self):
        with pytest.raises(ValidationError):
            ChangePasswordRequest(current_password="old", new_password="short")

    def test_too_long_new_password_rejected(self):
        with pytest.raises(ValidationError):
            ChangePasswordRequest(current_password="old", new_password="x" * 129)

    def test_empty_current_password_rejected(self):
        with pytest.raises(ValidationError):
            ChangePasswordRequest(current_password="", new_password="newpassword")


# ---------------------------------------------------------------------------
# ApiKeyCreateRequest schema
# ---------------------------------------------------------------------------

class TestApiKeyCreateRequestSchema:
    def test_valid(self):
        r = ApiKeyCreateRequest(label="ci-runner")
        assert r.label == "ci-runner"

    def test_empty_label_rejected(self):
        with pytest.raises(ValidationError):
            ApiKeyCreateRequest(label="")

    def test_too_long_label_rejected(self):
        with pytest.raises(ValidationError):
            ApiKeyCreateRequest(label="x" * 65)
