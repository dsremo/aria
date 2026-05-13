"""R60 — Password / passphrase KDF (Argon2id with sane defaults).

Threat: any operator-side admin password stored as SHA-256 (or even
PBKDF2 with low iterations) is GPU-crackable in hours.  ARIA does not
ship password-based auth in the primary flow (it uses tokens) but the
admin onboarding ceremony, the operator break-glass path, and any
ops-tooling that asks for a passphrase deserve a real KDF.

Defence: ``hash_password(password)`` + ``verify_password(password,
hash_str)`` using Argon2id from ``argon2-cffi`` when available.  Falls
back to PBKDF2-HMAC-SHA-512 with 600 000 iterations (OWASP 2023+).
The fallback is *secure* — it just costs more CPU per check.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_PBKDF2_ITER = 600_000
_PBKDF2_SALT_LEN = 16
_PBKDF2_KEY_LEN = 64


def _has_argon2() -> bool:
    try:
        import argon2          # noqa: F401
        return True
    except Exception:
        return False


def hash_password(password: str) -> str:
    """Return an opaque, encoded hash string suitable for storage."""
    if not password or len(password) < 12:
        raise ValueError("R60.kdf: password must be ≥ 12 chars")
    if _has_argon2():
        from argon2 import PasswordHasher
        return PasswordHasher().hash(password)
    salt = secrets.token_bytes(_PBKDF2_SALT_LEN)
    key = hashlib.pbkdf2_hmac(
        "sha512", password.encode("utf-8"), salt, _PBKDF2_ITER, _PBKDF2_KEY_LEN,
    )
    return (
        f"$pbkdf2-sha512$i={_PBKDF2_ITER}$"
        f"{base64.b64encode(salt).decode().rstrip('=')}$"
        f"{base64.b64encode(key).decode().rstrip('=')}"
    )


def verify_password(password: str, hash_str: str) -> bool:
    if not password or not hash_str:
        return False
    if hash_str.startswith("$argon2"):
        try:
            from argon2 import PasswordHasher
            from argon2.exceptions import VerifyMismatchError
            try:
                return PasswordHasher().verify(hash_str, password)
            except VerifyMismatchError:
                return False
        except Exception:
            return False
    if hash_str.startswith("$pbkdf2-sha512$"):
        try:
            _, _, params, salt_b64, key_b64 = hash_str.split("$")
            iters = int(params.split("=", 1)[1])
            salt = base64.b64decode(salt_b64 + "==")
            expected = base64.b64decode(key_b64 + "==")
            actual = hashlib.pbkdf2_hmac(
                "sha512", password.encode("utf-8"), salt, iters, len(expected),
            )
            import hmac as _hmac
            return _hmac.compare_digest(actual, expected)
        except Exception:
            return False
    return False


register(DefencePlugin(
    round_id="R60",
    name="kdf_password",
    description="Argon2id-preferred password hashing with PBKDF2-SHA512 fallback.",
))
