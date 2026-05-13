"""R67 — Just-in-Time (JIT) privileged access.

Threat: a standing admin role lying around at all times = perpetual
attack surface.  Best-of-breed (Azure PIM, AWS IAM Identity Center)
mints role assumption ON DEMAND with a TTL and an audit trail; the
account is non-privileged at rest.

Defence: ``request_elevation(principal, role, ttl_seconds, justification)``
returns a short-lived elevation token; ``check_elevation(principal,
required_role)`` lets handlers gate.  Pairs with R47 two-person rule
for the highest-risk roles.  All requests + grants logged to the audit
chain.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r67")

_MAX_TTL = 3600.0


@dataclass
class _Elevation:
    role: str
    granted_at: float
    expires_at: float
    justification: str
    grant_id: str


_ELEV: Dict[str, _Elevation] = {}     # principal -> active elevation
_LOCK = threading.Lock()


def request_elevation(
    principal: str,
    role: str,
    *,
    ttl_seconds: float = 900.0,
    justification: str = "",
) -> Tuple[bool, str]:
    """Request a short-lived role assumption.  Returns ``(granted, grant_id)``.
    Any prior elevation for the same principal is revoked first."""
    if not principal or not role:
        return False, "missing_principal_or_role"
    if not justification:
        return False, "justification_required"
    if ttl_seconds <= 0 or ttl_seconds > _MAX_TTL:
        return False, "ttl_out_of_range"
    grant_id = "elev_" + secrets.token_hex(8)
    now = time.monotonic()
    with _LOCK:
        _ELEV[principal] = _Elevation(
            role=role, granted_at=now, expires_at=now + ttl_seconds,
            justification=justification[:200], grant_id=grant_id,
        )
    logger.info(
        "r67.elevation_granted principal=%s role=%s grant=%s ttl=%.0f reason=%s",
        principal, role, grant_id, ttl_seconds, justification[:80],
    )
    return True, grant_id


def revoke(principal: str) -> None:
    with _LOCK:
        e = _ELEV.pop(principal, None)
    if e:
        logger.info("r67.elevation_revoked principal=%s grant=%s", principal, e.grant_id)


def check_elevation(principal: str, required_role: str) -> bool:
    with _LOCK:
        e = _ELEV.get(principal)
    if e is None:
        return False
    if time.monotonic() > e.expires_at:
        revoke(principal)
        return False
    return e.role == required_role


def status(principal: str) -> Tuple[bool, float, str]:
    with _LOCK:
        e = _ELEV.get(principal)
    if e is None:
        return False, 0.0, ""
    remaining = max(0.0, e.expires_at - time.monotonic())
    return remaining > 0, remaining, e.role


register(DefencePlugin(
    round_id="R67",
    name="jit_access",
    description="Short-lived role elevation with TTL + justification audit.",
))
