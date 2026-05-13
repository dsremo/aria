"""R62 — WebAuthn / FIDO2 challenge-response flow.

Threat: phishable second factor (SMS, TOTP) — every Snowflake-class
2024 incident had MFA via SMS or no MFA.  WebAuthn / FIDO2 with a
hardware authenticator is **not phishable** because the client device
binds the assertion to the origin name; the malicious site sees a
different challenge and the authenticator refuses.

Defence: a minimal challenge issuer + assertion verifier.  ARIA mints
a 32-byte random ``challenge`` keyed to the user's session, pins the
expected ``rpId``, and verifies the resulting assertion's ``client
DataJSON`` + ``authenticatorData`` against the user's pinned public
key.  Real cryptographic verify is delegated to ``cryptography``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from aria.security.plugins import DefencePlugin, register


_CHALLENGES: Dict[str, Tuple[bytes, float]] = {}
_TTL_SECONDS = 120.0


def mint_challenge(session_id: str) -> str:
    """Issue a 32-byte challenge for ``session_id``.  Base64URL-encoded."""
    nonce = secrets.token_bytes(32)
    _CHALLENGES[session_id] = (nonce, time.monotonic())
    return base64.urlsafe_b64encode(nonce).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode("ascii"))


@dataclass
class AssertionResult:
    ok: bool
    reason: str = ""


def verify_assertion(
    *,
    session_id: str,
    expected_rp_id: str,
    expected_origin: str,
    client_data_json_b64: str,
    authenticator_data_b64: str,
    signature_b64: str,
    user_public_key_pem: str,
) -> AssertionResult:
    """Verify a WebAuthn assertion.  Returns ``AssertionResult.ok = True``
    iff every field matches AND the signature verifies under the pinned
    public key."""
    pair = _CHALLENGES.pop(session_id, None)
    if pair is None:
        return AssertionResult(False, "no_challenge")
    nonce, ts = pair
    if time.monotonic() - ts > _TTL_SECONDS:
        return AssertionResult(False, "challenge_expired")

    try:
        client_data = json.loads(_b64url_decode(client_data_json_b64))
    except Exception:
        return AssertionResult(False, "bad_client_data")
    if client_data.get("type") != "webauthn.get":
        return AssertionResult(False, "wrong_type")
    if client_data.get("origin") != expected_origin:
        return AssertionResult(False, "origin_mismatch")
    challenge_b64 = base64.urlsafe_b64encode(nonce).rstrip(b"=").decode("ascii")
    if client_data.get("challenge") != challenge_b64:
        return AssertionResult(False, "challenge_mismatch")

    try:
        auth_data = _b64url_decode(authenticator_data_b64)
    except Exception:
        return AssertionResult(False, "bad_auth_data")
    rp_id_hash = hashlib.sha256(expected_rp_id.encode()).digest()
    if auth_data[:32] != rp_id_hash:
        return AssertionResult(False, "rp_id_mismatch")
    flags = auth_data[32]
    if not (flags & 0x01):
        return AssertionResult(False, "user_not_present")

    # Signed bytes = authenticatorData + SHA-256(clientDataJSON)
    signed = auth_data + hashlib.sha256(_b64url_decode(client_data_json_b64)).digest()
    sig = _b64url_decode(signature_b64)
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, padding
        pk = serialization.load_pem_public_key(user_public_key_pem.encode())
        if isinstance(pk, ec.EllipticCurvePublicKey):
            pk.verify(sig, signed, ec.ECDSA(hashes.SHA256()))
        else:
            pk.verify(sig, signed, padding.PKCS1v15(), hashes.SHA256())
        return AssertionResult(True)
    except Exception as exc:
        return AssertionResult(False, f"sig_verify_failed:{exc}")


register(DefencePlugin(
    round_id="R62",
    name="webauthn",
    description="Challenge issuer + assertion verifier for FIDO2 / WebAuthn admin.",
))
