"""R3 — JWT ``alg=none`` and algorithm-confusion attacks.

Threat: forged tokens whose header claims ``"alg": "none"`` or
``"alg": "HS256"`` against a server that expects RS256 (key-confusion
class).  Both are decade-old defects — still found in the wild every
year.  Recent: PyJWT < 2.10.0 had an algorithm-confusion regression
(CVE-2024-53861, fixed Dec 2024).

Defence: pre-flight reject any inbound bearer that looks like a JWT
with ``alg=none`` or unbounded-algorithm header.  We never trust the
header alg at all — the operator's expected algorithm is configured
out-of-band; we use the header only to *reject* the obviously wrong.
"""

from __future__ import annotations

import base64
import json
from typing import Iterable, Tuple

from aria.security.plugins import DefencePlugin, register


_ALLOWED_ALGS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "EdDSA", "HS256"})
_BANNED_ALGS = frozenset({"none", "None", "NONE", "nOnE", ""})


def _b64url_decode(seg: str) -> bytes:
    seg += "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg.encode("ascii"))


def jwt_header(token: str) -> dict:
    try:
        if token.count(".") != 2:
            return {}
        head_b64 = token.split(".", 1)[0]
        return json.loads(_b64url_decode(head_b64).decode("utf-8"))
    except Exception:
        return {}


def is_dangerous_jwt(token: str) -> Tuple[bool, str]:
    """Return ``(banned, reason)``.  Reason empty if the token isn't a JWT."""
    head = jwt_header(token)
    if not head:
        return False, ""
    alg = head.get("alg", "")
    if alg in _BANNED_ALGS:
        return True, f"jwt_alg={alg!r}"
    if alg not in _ALLOWED_ALGS:
        return True, f"jwt_alg={alg!r} not in allow-list"
    typ = head.get("typ", "JWT")
    if typ not in ("JWT", "JWT+ARIA"):
        return True, f"jwt_typ={typ!r}"
    return False, ""


def _on_request(request, _body: bytes) -> None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return
    tok = auth[len("Bearer "):].strip()
    bad, reason = is_dangerous_jwt(tok)
    if bad:
        raise RuntimeError(f"R3.jwt_alg_none: {reason}")


register(DefencePlugin(
    round_id="R3",
    name="jwt_alg_confusion",
    description="Reject JWT bearers with alg=none or non-allowlisted alg.",
    on_request=_on_request,
))
