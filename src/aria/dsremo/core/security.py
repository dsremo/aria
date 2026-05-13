"""Security primitives — authentication, integrity verification, sanitization.

Zero-trust approach: every input is suspect, every frame can be verified.
No security-through-obscurity. All operations are constant-time where possible.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
import structlog

logger = structlog.get_logger()

# Precompiled regex for input sanitization — catches common injection patterns
_DANGEROUS_PATTERNS = re.compile(
    r"[<>\"';\\]|"            # XSS / SQL injection chars
    r"(\b(DROP|DELETE|INSERT|UPDATE|ALTER|EXEC|UNION)\b)",  # SQL keywords
    re.IGNORECASE,
)


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key and its hash.

    Returns (plaintext_key, hashed_key).
    The plaintext is shown once to the user. We store only the hash.
    """
    plaintext = f"stl_{secrets.token_urlsafe(32)}"
    hashed = _hash_api_key(plaintext)
    return plaintext, hashed


def _hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256 with a static prefix salt.

    Constant-time comparison should be used when verifying.
    """
    return hashlib.sha256(f"dsremo::{key}".encode()).hexdigest()


def verify_api_key(provided_key: str, stored_hash: str) -> bool:
    """Verify an API key against its stored hash. Constant-time comparison."""
    provided_hash = _hash_api_key(provided_key)
    return hmac.compare_digest(provided_hash, stored_hash)


def sign_telemetry(payload: dict | list, secret: str) -> str:
    """HMAC-SHA256 sign a telemetry payload for tamper detection.

    The signature covers the canonical JSON serialization (sorted keys,
    no whitespace) to ensure deterministic signing regardless of field order.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        secret.encode(),
        canonical.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(payload: dict | list, signature: str, secret: str) -> bool:
    """Verify a telemetry HMAC signature. Constant-time comparison."""
    expected = sign_telemetry(payload, secret)
    return hmac.compare_digest(expected, signature)


def sanitize_string(value: str, max_length: int = 256) -> str:
    """Sanitize a string input — strip dangerous chars, enforce length.

    This is a defense-in-depth measure. Primary protection is parameterized
    queries and Pydantic validation, but we sanitize at ingestion too.
    """
    truncated = value[:max_length]
    cleaned = _DANGEROUS_PATTERNS.sub("", truncated)
    return cleaned.strip()


def sanitize_identifier(value: str) -> str:
    """Sanitize identifiers (satellite_id, parameter names, etc.).

    Only allows alphanumeric, hyphens, underscores, and dots.
    """
    return re.sub(r"[^a-zA-Z0-9_\-.]", "", value)[:128]


class RateLimiter:
    """Sliding window rate limiter — per API key, in-memory.

    Uses a simple token bucket approach. No external dependencies.
    For production at scale, move to Redis-backed limiting.
    """

    def __init__(self, max_requests: int = 300, window_seconds: int = 60):
        self._max = max_requests
        self._window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Check if a request from this key is within rate limits."""
        now = time.monotonic()
        cutoff = now - self._window

        # Prune expired entries
        entries = self._requests[key]
        self._requests[key] = [t for t in entries if t > cutoff]

        if len(self._requests[key]) >= self._max:
            logger.warning("rate_limit_exceeded", api_key_prefix=key[:8])
            return False

        self._requests[key].append(now)
        return True

    def reset(self, key: str) -> None:
        """Reset rate limit for a specific key."""
        self._requests.pop(key, None)


def validate_payload_size(data: bytes, max_bytes: int = 1_048_576) -> bool:
    """Reject payloads exceeding size limit (default 1MB)."""
    return len(data) <= max_bytes


# ---------------------------------------------------------------------------
# Password hashing (bcrypt)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt (rounds=12, constant work factor)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plaintext: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash. Constant-time comparison."""
    return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))


# ---------------------------------------------------------------------------
# JWT access tokens (HS256)
# ---------------------------------------------------------------------------


def create_access_token(
    user_id: str,
    tenant_id: str,
    role: str,
    secret: str,
    ttl_seconds: int = 900,
    email: str = "",
) -> str:
    """Create a signed HS256 JWT access token.

    Claims:
        sub   — user UUID
        tid   — tenant ID (used by get_current_user to set RLS context)
        role  — RBAC role string
        email — user email (for /auth/me without a DB lookup)
        iat   — issued at
        exp   — expiry (default 15 min)
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "tid": tenant_id,
        "role": role,
        "email": email,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str, secret: str) -> dict:
    """Decode and validate a JWT access token.

    Raises jwt.InvalidTokenError (or subclass) on expiry, bad signature, etc.
    """
    return jwt.decode(token, secret, algorithms=["HS256"])


def create_dsremo_token(
    user_id: str,
    role: str,
    secret: str,
    ttl_seconds: int = 900,
    email: str = "",
) -> str:
    """Create a signed HS256 JWT for a Dsremo internal user.

    Differs from create_access_token:
      - No 'tid' claim (dsremo users are cross-tenant).
      - 'scope' = 'dsremo' so get_current_user can detect this type and
        read X-Tenant-ID header instead of a fixed tenant from the token.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "email": email,
        "scope": "dsremo",
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(payload, secret, algorithm="HS256")
