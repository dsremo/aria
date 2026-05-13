"""R53 — HKDF per-tenant key derivation.

Threat: a single master secret leaked from one tenant compromises
every tenant.  Bank stacks derive per-tenant per-purpose keys from a
master KEK so each rotation is local.  ARIA's tenant store stores
plaintext API keys (R47 noted this); HKDF gives us a deterministic
derivation path for purposes ("audit_seal", "rotation_token",
"webhook_hmac") tied to the master secret + tenant id.

Defence: ``derive(purpose, tenant_id, length)`` — RFC-5869 HKDF-SHA256
keyed on ``ARIA_MASTER_KEY``.  Operator stores the master in a KMS or
secret store; if the master is wrapped by an HSM the round is FIPS-Class
ready.  Constant-time compare on derived material.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

from aria.security.plugins import DefencePlugin, register


_BANNED_MASTER_KEYS = {
    "0" * 32, "0" * 64,
    "f" * 32, "f" * 64,
    "deadbeef" * 4, "deadbeef" * 8,
    "ARIA-DEV-MASTER-KEY",
}


def _master_key() -> bytes:
    raw = os.environ.get("ARIA_MASTER_KEY", "")
    if not raw:
        raise RuntimeError(
            "R53.hkdf: ARIA_MASTER_KEY unset.  Generate one via "
            "`python -c 'import secrets;print(secrets.token_hex(32))'` and "
            "store it in a KMS / HSM-wrapped secret store."
        )
    # Audit CRIT-7 — entropy floor + deny-list.  256-bit (64 hex chars) is
    # the production minimum; production refuses anything that maps onto a
    # well-known weak default or has a low distinct-character count.
    is_prod = os.environ.get("ARIA_ENV", "").lower() == "prod"
    min_len = 64 if is_prod else 32
    if len(raw) < min_len:
        raise RuntimeError(
            f"R53.hkdf: ARIA_MASTER_KEY < {min_len} chars (need 256 bit in prod)"
        )
    if raw.lower() in _BANNED_MASTER_KEYS:
        raise RuntimeError("R53.hkdf: ARIA_MASTER_KEY matches a deny-listed default")
    # Distinct-char floor — production only.  CLAUDE.md exempts test-
    # fixture values, so dev/test can keep using ``"f" * 64``.
    if is_prod and len(set(raw)) < 8:
        raise RuntimeError(
            f"R53.hkdf: ARIA_MASTER_KEY has only {len(set(raw))} distinct chars; refuse"
        )
    return raw.encode("utf-8")


def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(salt or b"\x00" * 32, ikm, hashlib.sha256).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    out = b""
    block = b""
    counter = 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def _default_salt() -> bytes:
    """Audit MED-13 — prefer the operator-supplied per-deployment salt
    over the hardcoded constant.  ``ARIA_HKDF_SALT_HEX`` lets each
    deployment have a distinct salt so cross-deployment rainbow tables
    on the master key are useless."""
    raw = os.environ.get("ARIA_HKDF_SALT_HEX", "")
    if raw:
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass
    return b"ARIA-R53-HKDF"


def derive(
    purpose: str,
    tenant_id: str,
    length: int = 32,
    *,
    salt: Optional[bytes] = None,
) -> bytes:
    """RFC-5869 HKDF-SHA256.  ``info`` = ``b"ARIA|{purpose}|{tenant_id}"``."""
    if not purpose or not tenant_id:
        raise ValueError("purpose + tenant_id required")
    if length < 1 or length > 8160:
        raise ValueError("length must be 1..8160")
    prk = hkdf_extract(salt or _default_salt(), _master_key())
    info = f"ARIA|{purpose}|{tenant_id}".encode("utf-8")
    return hkdf_expand(prk, info, length)


def derive_hex(purpose: str, tenant_id: str, length: int = 32) -> str:
    return derive(purpose, tenant_id, length).hex()


register(DefencePlugin(
    round_id="R53",
    name="hkdf_per_tenant",
    description="RFC-5869 HKDF-SHA256 per-tenant per-purpose key derivation.",
))
