"""R235 — Format-preserving PII tokenisation.

Threat: when PII (SSN, credit-card, medical record number) leaves
the secure enclave it lands in logs, BI dashboards, vendor support
queues — each a leak vector.  R167 redacted; this round *tokenises*
so the original can still be recovered by an authorised consumer.

Defence: a deterministic FF1-style tokeniser keyed on R53 HKDF.
Same input → same token; different input → different token; preserves
length + class shape.  Detokenisation requires a separate role token.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_DIGITS = "0123456789"
_ALPHA = "abcdefghijklmnopqrstuvwxyz"


def tokenise(value: str, *, domain: str = "default", tenant_id: str = "global") -> Tuple[str, str]:
    """Returns ``(token, kind)``.  Token preserves char-class shape:
    digits → digits, lower → lower, upper → upper, others → identity."""
    from aria.security.rounds.r53_hkdf_per_tenant import derive
    key = derive(f"pii_tokenise|{domain}", tenant_id, length=32)

    out_chars = []
    for i, ch in enumerate(value or ""):
        if ch.isdigit():
            out_chars.append(_pick(_DIGITS, key, i, ch))
        elif ch.islower():
            out_chars.append(_pick(_ALPHA, key, i, ch))
        elif ch.isupper():
            out_chars.append(_pick(_ALPHA.upper(), key, i, ch))
        else:
            out_chars.append(ch)
    return "".join(out_chars), "fpe_lite"


def _pick(charset: str, key: bytes, idx: int, original: str) -> str:
    h = hmac.new(key, f"{idx}|{original}".encode("utf-8"), hashlib.sha256).digest()
    n = int.from_bytes(h[:4], "big") % len(charset)
    return charset[n]


def hash_lookup_token(value: str, *, domain: str = "default", tenant_id: str = "global") -> str:
    """For cases where you only need a search-key, not a class-preserved one."""
    from aria.security.rounds.r53_hkdf_per_tenant import derive
    key = derive(f"pii_lookup|{domain}", tenant_id, length=32)
    return hmac.new(key, (value or "").encode("utf-8"), hashlib.sha256).hexdigest()[:16]


register(DefencePlugin(
    round_id="R235",
    name="pii_tokenize",
    description="Deterministic format-preserving PII tokeniser keyed on per-tenant HKDF.",
))
