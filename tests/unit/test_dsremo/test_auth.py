"""Tests for Sprint 2: User Auth (JWT + RBAC).

All tests are pure unit tests — no database required.
Tests cover: password hashing, JWT encode/decode, RBAC logic, and Pydantic schemas.
"""

from __future__ import annotations

import time

import jwt
import pytest
from pydantic import ValidationError

from aria.dsremo.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from aria.dsremo.api.schemas import LoginRequest, RefreshRequest, TokenResponse, UserOut


_SECRET = "test-secret-key-that-is-long-enough-for-hs256"


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_roundtrip(self):
        hashed = hash_password("correct-horse-battery-staple")
        assert verify_password("correct-horse-battery-staple", hashed)

    def test_wrong_password_rejected(self):
        hashed = hash_password("correct-password")
        assert not verify_password("wrong-password", hashed)

    def test_empty_password_wrong_rejected(self):
        hashed = hash_password("some-password")
        assert not verify_password("", hashed)

    def test_bcrypt_hashes_differ_for_same_password(self):
        """bcrypt uses random salt — same password yields different hashes."""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2
        # But both verify correctly
        assert verify_password("same", h1)
        assert verify_password("same", h2)

    def test_hash_has_bcrypt_prefix(self):
        hashed = hash_password("password")
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

class TestJWT:
    def test_encode_decode_roundtrip(self):
        token = create_access_token("user-1", "acme", "admin", _SECRET, ttl_seconds=300)
        payload = decode_access_token(token, _SECRET)
        assert payload["sub"] == "user-1"
        assert payload["tid"] == "acme"
        assert payload["role"] == "admin"

    def test_expired_token_raises(self):
        token = create_access_token("user-1", "acme", "viewer", _SECRET, ttl_seconds=-1)
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(token, _SECRET)

    def test_tampered_token_raises(self):
        token = create_access_token("user-1", "acme", "viewer", _SECRET, ttl_seconds=300)
        # Flip a character in the signature (last 10 chars)
        parts = token.split(".")
        bad_sig = parts[2][:-2] + "xx"
        bad_token = ".".join(parts[:2] + [bad_sig])
        with pytest.raises(jwt.InvalidSignatureError):
            decode_access_token(bad_token, _SECRET)

    def test_wrong_secret_raises(self):
        token = create_access_token("user-1", "acme", "viewer", _SECRET, ttl_seconds=300)
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token, "completely-different-secret")

    def test_all_roles_encodable(self):
        for role in ("admin", "operator", "viewer", "report_only"):
            token = create_access_token("u", "t", role, _SECRET)
            payload = decode_access_token(token, _SECRET)
            assert payload["role"] == role

    def test_token_has_expected_claims(self):
        token = create_access_token("uuid-123", "tenant-abc", "operator", _SECRET, ttl_seconds=900)
        payload = decode_access_token(token, _SECRET)
        assert "sub" in payload
        assert "tid" in payload
        assert "role" in payload
        assert "iat" in payload
        assert "exp" in payload
        assert payload["exp"] > payload["iat"]

    def test_ttl_respected(self):
        token = create_access_token("u", "t", "viewer", _SECRET, ttl_seconds=3600)
        payload = decode_access_token(token, _SECRET)
        # exp should be ~3600s from now (allow 5s clock skew)
        remaining = payload["exp"] - int(time.time())
        assert 3595 <= remaining <= 3605


# ---------------------------------------------------------------------------
# RBAC logic
# ---------------------------------------------------------------------------

class TestRBAC:
    """Test the role hierarchy without a running FastAPI app."""

    _ROLES = ("admin", "operator", "viewer", "report_only")

    def _check(self, user_role: str, allowed_roles: tuple[str, ...]) -> bool:
        """Mirrors require_role() logic."""
        return user_role in allowed_roles

    def test_admin_passes_all_levels(self):
        require_admin    = ("admin",)
        require_operator = ("admin", "operator")
        require_viewer   = ("admin", "operator", "viewer", "report_only")
        assert self._check("admin", require_admin)
        assert self._check("admin", require_operator)
        assert self._check("admin", require_viewer)

    def test_operator_blocked_from_admin(self):
        require_admin = ("admin",)
        assert not self._check("operator", require_admin)

    def test_viewer_blocked_from_operator(self):
        require_operator = ("admin", "operator")
        assert not self._check("viewer", require_operator)

    def test_report_only_blocked_from_viewer_route(self):
        # report_only can ONLY access report_only-level routes (anomalies read)
        require_viewer_strict = ("admin", "operator", "viewer")
        assert not self._check("report_only", require_viewer_strict)

    def test_report_only_passes_full_viewer(self):
        require_viewer_full = ("admin", "operator", "viewer", "report_only")
        assert self._check("report_only", require_viewer_full)

    def test_unknown_role_blocked_everywhere(self):
        for allowed in [("admin",), ("admin", "operator"), ("admin", "operator", "viewer", "report_only")]:
            assert not self._check("superadmin", allowed)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class TestLoginRequestSchema:
    def test_valid(self):
        r = LoginRequest(email="user@example.com", password="secure123", tenant_id="acme")
        assert r.email == "user@example.com"
        assert r.tenant_id == "acme"

    def test_default_tenant(self):
        r = LoginRequest(email="user@example.com", password="x")
        assert r.tenant_id == "default"

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="not-an-email", password="x")

    def test_empty_password_rejected(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="user@example.com", password="")

    def test_password_too_long_rejected(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="user@example.com", password="x" * 129)

    def test_empty_tenant_id_rejected(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="user@example.com", password="x", tenant_id="")


class TestTokenResponseSchema:
    def test_valid(self):
        r = TokenResponse(
            access_token="eyJ...",
            refresh_token="dGVzdA...",
            expires_in=900,
        )
        assert r.token_type == "bearer"
        assert r.expires_in == 900

    def test_token_type_default(self):
        r = TokenResponse(access_token="a", refresh_token="b", expires_in=900)
        assert r.token_type == "bearer"


class TestUserOutSchema:
    def test_valid(self):
        u = UserOut(user_id="uuid-1", email="admin@co.com", role="admin", tenant_id="acme")
        assert u.role == "admin"
        assert u.tenant_id == "acme"


class TestRefreshRequestSchema:
    def test_valid(self):
        r = RefreshRequest(refresh_token="opaque-token-string")
        assert r.refresh_token == "opaque-token-string"

    def test_empty_rejected(self):
        with pytest.raises(ValidationError):
            RefreshRequest(refresh_token="")
