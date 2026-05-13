"""R52 — TLS certificate pinning + Certificate Transparency check.

Threat: an upstream MITM (rogue CA, hostile DNS, captive portal)
substitutes a trusted-but-attacker-controlled cert.  Bank stacks
mandate pinning for the high-value paths; the equivalent for ARIA's
external feeds (CISA KEV, NTRS, JPL Horizons, LeoLabs, IS4OM) is to
verify the SPKI-SHA-256 against an operator-supplied allow-list.

Defence: ``verify_pinned_spki(host, der_cert, expected_pins)`` —
constant-time compare against any pin in the operator's list (per-host
pin sets enable rotation).  Plus an ``CT-Log presence`` advisory: we
stub the SCT (Signed Certificate Timestamp) check; a deployment with
a real CT log client wires it via ``configure_ct_lookup()``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
from typing import Callable, Dict, List, Optional, Tuple

from aria.security.plugins import DefencePlugin, register


def spki_sha256(der_certificate: bytes) -> str:
    """Return the SubjectPublicKeyInfo SHA-256, base64-encoded.

    Convention: same shape as RFC 7469 ``Public-Key-Pins`` and HPKP, the
    industry-standard pin format.  Caller extracts SPKI bytes via
    ``cryptography.x509.load_der_x509_certificate(der).public_key()
    .public_bytes(...)`` — we accept the SPKI DER directly so the round
    has no hard dependency on `cryptography`.
    """
    h = hashlib.sha256(der_certificate).digest()
    return base64.b64encode(h).decode("ascii")


_PINS: Dict[str, List[str]] = {}


def configure_pins(host: str, pins: List[str]) -> None:
    """Replace the pin list for ``host``.  Multiple pins per host enable
    rotation: the new pin is added, all current sessions accept either,
    then the old pin is removed in a later cycle."""
    _PINS[host.lower()] = list(pins)


def verify_pinned_spki(host: str, spki_b64_sha256: str) -> Tuple[bool, str]:
    pins = _PINS.get(host.lower())
    if not pins:
        return True, "no_pin_configured"     # opt-in defence
    for p in pins:
        if _hmac.compare_digest(p, spki_b64_sha256):
            return True, "pinned_match"
    return False, f"pin_mismatch host={host}"


_CT_LOOKUP: Optional[Callable[[bytes], bool]] = None


def configure_ct_lookup(fn: Callable[[bytes], bool]) -> None:
    """Wire a callable that returns True iff the cert appears in a
    public Certificate Transparency log (RFC 6962)."""
    global _CT_LOOKUP
    _CT_LOOKUP = fn


def is_in_ct_log(der_certificate: bytes) -> bool:
    if _CT_LOOKUP is None:
        return True       # advisory only — operator must wire a CT client
    try:
        return bool(_CT_LOOKUP(der_certificate))
    except Exception:
        return False


register(DefencePlugin(
    round_id="R52",
    name="tls_pinning",
    description="Per-host SPKI-SHA-256 pin list; CT-log advisory hook.",
))
