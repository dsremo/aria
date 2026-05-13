"""Tests for security module."""

from __future__ import annotations

import pytest

from aria.genastra.core.exceptions import ApiKeyInvalidError, InsufficientScopeError, PlanLimitExceededError
from aria.genastra.core.models import TenantPlan
from aria.genastra.core.security import (
    AuthContext,
    extract_bearer_token,
    generate_api_key,
    hash_api_key,
    validate_api_key_format,
)


class TestApiKeyGeneration:
    def test_generates_key_with_prefix(self) -> None:
        key, key_hash = generate_api_key()
        assert key.startswith("ga_live_")
        assert len(key_hash) == 32  # SHA-256 = 32 bytes

    def test_key_hash_is_deterministic(self) -> None:
        key, _ = generate_api_key()
        h1 = hash_api_key(key)
        h2 = hash_api_key(key)
        assert h1 == h2

    def test_different_keys_different_hashes(self) -> None:
        _, h1 = generate_api_key()
        _, h2 = generate_api_key()
        assert h1 != h2

    def test_format_validation(self) -> None:
        key, _ = generate_api_key()
        assert validate_api_key_format(key)
        assert not validate_api_key_format("invalid_key")
        assert not validate_api_key_format("ga_live_")  # too short


class TestBearerTokenExtraction:
    def test_valid_bearer(self) -> None:
        key, _ = generate_api_key()
        token = extract_bearer_token(f"Bearer {key}")
        assert token == key

    def test_missing_header(self) -> None:
        with pytest.raises(ApiKeyInvalidError, match="Missing"):
            extract_bearer_token(None)

    def test_invalid_scheme(self) -> None:
        with pytest.raises(ApiKeyInvalidError, match="Bearer"):
            extract_bearer_token("Basic sometoken")

    def test_invalid_format(self) -> None:
        with pytest.raises(ApiKeyInvalidError, match="format"):
            extract_bearer_token("Bearer invalid_token_no_prefix")


class TestAuthContext:
    def _make_ctx(self, scopes: tuple[str, ...] = ("protein:read",), plan: str = "free") -> AuthContext:
        import uuid
        return AuthContext(
            tenant_id=uuid.uuid4(),
            api_key_id=uuid.uuid4(),
            scopes=scopes,
            plan=TenantPlan(plan),
        )

    def test_require_scope_passes(self) -> None:
        ctx = self._make_ctx(scopes=("protein:read", "protein:write"))
        ctx.require_scope("protein:read")  # Should not raise

    def test_require_scope_fails(self) -> None:
        ctx = self._make_ctx(scopes=("protein:read",))
        with pytest.raises(InsufficientScopeError):
            ctx.require_scope("expression:write")

    def test_plan_limit_under(self) -> None:
        ctx = self._make_ctx(plan="free")
        ctx.check_plan_limit("structures", 50)  # Under 100 limit

    def test_plan_limit_exceeded(self) -> None:
        ctx = self._make_ctx(plan="free")
        with pytest.raises(PlanLimitExceededError):
            ctx.check_plan_limit("structures", 100)  # At limit
