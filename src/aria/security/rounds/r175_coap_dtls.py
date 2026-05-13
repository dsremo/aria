"""R175 — CoAP DTLS PSK validation.

Threat: CoAP over UDP without DTLS is plaintext; many constrained-
device deployments use a hard-coded PSK shared across the fleet, so
one compromised device leaks the key for the entire deployment.

Defence: validate a CoAP DTLS connection profile — refuse no-sec /
RawPublicKey-only / shared PSK across many devices.  Recommend
per-device PSK with HKDF (R53) derivation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_coap_profile(profile: Dict[str, Any]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    sec = (profile.get("security") or "").lower()
    if sec in ("nosec", "no-sec", "none", ""):
        issues.append("coap.no_security")

    if sec == "psk":
        psk_id = profile.get("psk_identity") or ""
        psk = profile.get("psk_secret") or b""
        if not psk_id:
            issues.append("coap.psk_no_identity")
        if isinstance(psk, (bytes, bytearray)) and len(psk) < 16:
            issues.append("coap.psk_too_short")
        if profile.get("shared_across_fleet"):
            issues.append("coap.psk_shared_fleet")

    if sec == "rpk" and not profile.get("device_certificate"):
        issues.append("coap.rpk_no_cert")

    cipher = (profile.get("dtls_cipher") or "").upper()
    if cipher and "AES" not in cipher and "CHACHA" not in cipher:
        issues.append(f"coap.weak_dtls_cipher:{cipher}")

    return not issues, issues


def derive_per_device_psk(device_id: str) -> bytes:
    """Per-device PSK via HKDF (R53)."""
    from aria.security.rounds.r53_hkdf_per_tenant import derive
    return derive("coap_dtls_psk", device_id, length=32)


register(DefencePlugin(
    round_id="R175",
    name="coap_dtls",
    description="CoAP DTLS PSK audit; per-device key derivation via HKDF.",
))
