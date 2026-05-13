"""R64 — One-time backup codes for MFA recovery.

Threat: an admin loses their phone or hardware key and is locked out;
the operator panics and disables MFA in prod.  Snowflake's response to
their 2024 incident was "force MFA"; without recovery codes that
becomes operationally fragile.

Defence: a generator + verifier for one-time recovery codes hashed at
rest (Argon2id via R60).  Codes consume on use (single-shot).  Default
configuration: 8 codes per user, 12 chars each from
``[a-hjkmnp-z2-9]`` (exclude visually-confusable chars).
"""

from __future__ import annotations

import secrets
import threading
from typing import Dict, List, Set

from aria.security.plugins import DefencePlugin, register


_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def generate_codes(n: int = 8, length: int = 12) -> List[str]:
    if n < 1 or n > 32:
        raise ValueError("n must be 1..32")
    if length < 8 or length > 40:
        raise ValueError("length must be 8..40")
    return ["".join(secrets.choice(_ALPHABET) for _ in range(length)) for _ in range(n)]


_USED: Dict[str, Set[str]] = {}
_HASHES: Dict[str, Dict[str, str]] = {}        # principal_id -> {hash: code_id}
_LOCK = threading.Lock()


def store_codes_for(principal_id: str, codes: List[str]) -> None:
    """Hash each code and store against ``principal_id``.  Plain codes
    are returned to the caller once for one-time display."""
    from aria.security.rounds.r60_kdf_password import hash_password
    with _LOCK:
        _HASHES[principal_id] = {}
        _USED.setdefault(principal_id, set())
        for i, code in enumerate(codes):
            try:
                # Pad to >= 12 chars; argon2 minimum
                h = hash_password(code + "_aria_backup")
                _HASHES[principal_id][h] = f"code_{i+1}"
            except Exception:
                continue


def consume(principal_id: str, presented_code: str) -> bool:
    """Return True iff the code matches an unused stored hash; on success
    the code is marked consumed and cannot be used again."""
    from aria.security.rounds.r60_kdf_password import verify_password
    with _LOCK:
        store = _HASHES.get(principal_id, {})
        used = _USED.setdefault(principal_id, set())
        for h, cid in list(store.items()):
            if cid in used:
                continue
            if verify_password(presented_code + "_aria_backup", h):
                used.add(cid)
                return True
    return False


def remaining(principal_id: str) -> int:
    with _LOCK:
        store = _HASHES.get(principal_id, {})
        used = _USED.get(principal_id, set())
        return max(0, len(store) - len(used))


register(DefencePlugin(
    round_id="R64",
    name="backup_codes",
    description="Argon2-hashed one-time recovery codes (8 × 12 chars by default).",
))
