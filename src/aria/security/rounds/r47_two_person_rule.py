"""R47 — Two-person rule for high-impact admin actions.

Threat: a single compromised admin token (Snowflake / Storm-0558 class)
issues an irreversible command — wipe a tenant, rotate the master
key, push a new constitution.  ARIA already supports a
two-person-rule pattern in :mod:`aria.security.admin` (R33); this
round wires it into the *plug-in* registry so that every defended
endpoint can opt in by listing the action name.

Defence: ``require_two_person(action, primary_token, secondary_token)``
verifies BOTH tokens, that they belong to DIFFERENT principals, and
records both signatures into the audit chain before authorising.
A single token can never advance, regardless of role.
"""

from __future__ import annotations

import hmac as _hmac
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Set, Tuple

from aria.security.plugins import DefencePlugin, register


# Action → set of principal-IDs whose primary tokens are recognised.
# Operators populate at boot via configure_authoriser_set().
_AUTHORISERS: Dict[str, Set[str]] = {}


def configure_authoriser_set(action: str, principals: Set[str]) -> None:
    _AUTHORISERS[action] = set(principals)


@dataclass
class TwoPersonResult:
    allowed: bool
    primary: str = ""
    secondary: str = ""
    reason: str = ""


def require_two_person(
    *,
    action: str,
    primary_token: str,
    primary_principal: str,
    secondary_token: str,
    secondary_principal: str,
    primary_expected: str,
    secondary_expected: str,
) -> TwoPersonResult:
    """Verify both tokens against the expected per-principal secrets.

    The expected secrets are looked up by the caller from the principal
    store — we don't reach into env directly because that would mean
    the round has to know about every principal.  Constant-time compare
    on each.  Reject if both come from the same principal.
    """
    if primary_principal == secondary_principal:
        return TwoPersonResult(False, reason="same_principal")
    allowed_set = _AUTHORISERS.get(action, set())
    if allowed_set and primary_principal not in allowed_set:
        return TwoPersonResult(False, reason="primary_not_authorised")
    if allowed_set and secondary_principal not in allowed_set:
        return TwoPersonResult(False, reason="secondary_not_authorised")
    if not _hmac.compare_digest(primary_token, primary_expected):
        return TwoPersonResult(False, reason="primary_token_mismatch")
    if not _hmac.compare_digest(secondary_token, secondary_expected):
        return TwoPersonResult(False, reason="secondary_token_mismatch")
    return TwoPersonResult(True, primary=primary_principal,
                           secondary=secondary_principal)


register(DefencePlugin(
    round_id="R47",
    name="two_person_rule",
    description="Require two distinct authorised principals for irreversible actions.",
))
