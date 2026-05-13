"""R66 — Strong session binding (cookie + IP + UA + ASN).

Threat: a session token leaked over a tab, log line, or screen share
is replayed from a different network.  Bare token = portable attack
surface.  Banking + Microsoft Entra ID both bind sessions to additional
device signals — replay from a fresh subnet triggers re-auth.

Defence: at session mint time, capture (IP, UA, optional ASN) and
attach to the session.  On every subsequent request, compute a soft
match score; below threshold → require step-up (R65).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Binding:
    ip: str
    ua_prefix: str             # first 64 chars
    asn: Optional[int] = None


_BINDINGS: Dict[str, _Binding] = {}
_LOCK = threading.Lock()


def attach(token: str, *, ip: str, user_agent: str, asn: Optional[int] = None) -> None:
    if not token or len(token) < 8:
        return
    with _LOCK:
        _BINDINGS[token] = _Binding(
            ip=ip or "",
            ua_prefix=(user_agent or "")[:64],
            asn=asn,
        )


def match_score(token: str, *, ip: str, user_agent: str, asn: Optional[int] = None) -> Tuple[float, str]:
    """Return ``(score, reason)`` in [0, 1].

      1.00 = full match
      0.75 = same /24 subnet, same UA prefix
      0.50 = different IP, same ASN, same UA
      0.25 = different IP, different ASN, same UA
      0.00 = no binding / different UA
    """
    with _LOCK:
        b = _BINDINGS.get(token)
    if not b:
        return 0.0, "no_binding"
    if (user_agent or "")[:64] != b.ua_prefix:
        return 0.0, "ua_mismatch"
    if ip == b.ip:
        return 1.0, "exact"
    # /24 same?
    try:
        if ip.split(".")[:3] == b.ip.split(".")[:3]:
            return 0.75, "subnet_match"
    except Exception:
        pass
    if asn is not None and b.asn is not None:
        if asn == b.asn:
            return 0.5, "asn_match"
        return 0.25, "asn_different"
    return 0.25, "ip_changed"


def detach(token: str) -> None:
    with _LOCK:
        _BINDINGS.pop(token, None)


register(DefencePlugin(
    round_id="R66",
    name="session_binding",
    description="Bind tokens to (IP/UA/ASN); soft-match for replay detection.",
))
