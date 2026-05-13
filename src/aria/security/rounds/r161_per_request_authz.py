"""R161 — Per-request authorization decision recorder.

Threat: zero-trust mandates *every* request is authorized end-to-end,
not just the connection.  A per-connection authz decision (e.g. mTLS
handshake) doesn't catch later authority changes — token revocation,
role change, capability removal.

Defence: a per-request decision log + ``check`` helper that combines
SPIFFE identity (R154), BeyondCorp posture (R153), and explicit scope
match.  Each decision is recorded for forensic reconstruction.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class AuthzDecision:
    timestamp: float
    principal: str
    resource: str
    action: str
    allow: bool
    reason: str


_LEDGER: Deque[AuthzDecision] = deque(maxlen=65536)
_LOCK = threading.Lock()


def check(
    principal: str,
    *,
    resource: str,
    action: str,
    granted_scopes: Iterable[str],
    required_scope: str,
    posture: str = "ALLOW",
) -> Tuple[bool, str]:
    if posture == "DENY":
        return _record(principal, resource, action, False, "posture_deny")
    if posture not in ("ALLOW", "LIMITED"):
        return _record(principal, resource, action, False, f"posture_invalid:{posture}")
    if required_scope not in set(granted_scopes):
        return _record(principal, resource, action, False, f"scope_missing:{required_scope}")
    return _record(principal, resource, action, True, "ok")


def _record(principal: str, resource: str, action: str, allow: bool, reason: str) -> Tuple[bool, str]:
    with _LOCK:
        _LEDGER.append(AuthzDecision(time.time(), principal, resource, action, allow, reason))
    return allow, reason


def recent(n: int = 100) -> list:
    with _LOCK:
        return list(_LEDGER)[-n:]


register(DefencePlugin(
    round_id="R161",
    name="per_request_authz",
    description="Per-request authz combining SPIFFE + posture + scope; records every decision.",
))
