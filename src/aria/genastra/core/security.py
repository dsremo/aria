"""Authentication, API key management, and rate limiting."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aria.genastra.core.constants import PLAN_LIMITS
from aria.genastra.core.exceptions import (
    ApiKeyInvalidError,
    InsufficientScopeError,
    PlanLimitExceededError,
)

if TYPE_CHECKING:
    from uuid import UUID

    from aria.genastra.core.models import TenantPlan

API_KEY_PREFIX = "ga_live_"
API_KEY_BYTES = 32  # 256-bit key


def generate_api_key() -> tuple[str, bytes]:
    """Generate a new API key and its SHA-256 hash.

    Returns:
        (full_key, key_hash) — full key is shown once to user, hash is stored.
    """
    random_part = secrets.token_urlsafe(API_KEY_BYTES)
    full_key = f"{API_KEY_PREFIX}{random_part}"
    key_hash = hashlib.sha256(full_key.encode()).digest()
    return full_key, key_hash


def hash_api_key(key: str) -> bytes:
    """Hash an API key for lookup."""
    return hashlib.sha256(key.encode()).digest()


def validate_api_key_format(key: str) -> bool:
    """Check that an API key has the expected prefix and length."""
    return key.startswith(API_KEY_PREFIX) and len(key) > len(API_KEY_PREFIX) + 10


@dataclass(frozen=True)
class AuthContext:
    """Authenticated request context."""

    tenant_id: UUID
    api_key_id: UUID
    scopes: tuple[str, ...]
    plan: TenantPlan

    def require_scope(self, scope: str) -> None:
        """Raise if the API key lacks the required scope."""
        if scope not in self.scopes:
            raise InsufficientScopeError(
                f"This operation requires scope '{scope}'. "
                f"Your key has: {', '.join(self.scopes)}"
            )

    def check_plan_limit(self, resource: str, current_usage: int) -> None:
        """Raise if the tenant has exceeded their plan limit for this resource."""
        limits = PLAN_LIMITS.get(self.plan, PLAN_LIMITS["free"])
        limit = limits.get(f"{resource}_per_month", 0)
        if current_usage >= limit:
            raise PlanLimitExceededError(resource, limit, current_usage)


def extract_bearer_token(authorization: str | None) -> str:
    """Extract the token from an Authorization: Bearer header."""
    if not authorization:
        raise ApiKeyInvalidError("Missing Authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise ApiKeyInvalidError("Authorization header must be 'Bearer <token>'")
    token = parts[1].strip()
    if not validate_api_key_format(token):
        raise ApiKeyInvalidError("Invalid API key format")
    return token
