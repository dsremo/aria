"""R138 — LLM output watermarking.

Threat: an attacker exfiltrates ARIA's LLM output and republishes it
as their own; ARIA can't prove provenance later.  Bank + government
deployments increasingly require watermarked outputs (especially for
images / synthetic media; harder for text).

Defence: a small ``stamp(text, key)`` that appends an HMAC-SHA-256
of the text to a sidecar metadata field.  The watermark is OUT-OF-BAND
(not embedded in the text — that would change content); operators
distribute alongside.  ``verify_stamp(text, hmac_b64, key)`` confirms.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


def stamp(text: str, *, key: bytes) -> str:
    """Return a base64 HMAC-SHA-256 over ``text``."""
    if not isinstance(text, str):
        raise ValueError("text must be str")
    if not key or len(key) < 16:
        raise ValueError("key must be >= 16 bytes")
    digest = hmac.new(key, text.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_stamp(text: str, hmac_b64: str, *, key: bytes) -> Tuple[bool, str]:
    if not text or not hmac_b64:
        return False, "empty"
    try:
        expected = base64.b64decode(hmac_b64)
    except Exception:
        return False, "bad_b64"
    actual = hmac.new(key, text.encode("utf-8"), hashlib.sha256).digest()
    if hmac.compare_digest(expected, actual):
        return True, "verified"
    return False, "hmac_mismatch"


register(DefencePlugin(
    round_id="R138",
    name="output_watermark",
    description="HMAC-SHA-256 sidecar watermark for LLM outputs (out-of-band).",
))
