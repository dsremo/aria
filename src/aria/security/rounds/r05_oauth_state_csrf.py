"""R5 — OAuth state-CSRF + redirect-URI validation.

Threat: an attacker initiates an OAuth flow at the victim's IdP using a
controlled callback (``redirect_uri``).  When the victim authorises,
the code lands on the attacker's callback and is replayable.  CWE-352
+ CWE-601 — exploited at scale against Salesforce CRM connectors
(2023) and various SaaS OAuth chains (2024).

Defence: HMAC-bound ``state`` parameter + redirect-URI exact-match
allow-list.  ``mint_state(nonce)`` returns ``f"{nonce}.{hmac}"`` where
``hmac`` is keyed on a per-deployment secret.  ``verify_state`` is
constant-time.  The redirect URI must be in a configured allow-list
of fully-qualified URLs — no prefix or wildcard match.
"""

from __future__ import annotations

import hmac as _hmac
import os
import secrets
from typing import Iterable, Tuple

from aria.security.plugins import DefencePlugin, register


def _key() -> bytes:
    """Per-deployment HMAC key.

    Audit HIGH-12 — refuses to fall back to the process-local random key
    when ``ARIA_ENV=prod``.  Multi-worker deployments (gunicorn N>1, k8s
    replicas) used to mint state in worker A and reject it in worker B
    because each worker rolled its own per-process key; production
    therefore demands an explicit shared key.
    """
    k = os.environ.get("ARIA_OAUTH_STATE_KEY", "").encode()
    if not k:
        if os.environ.get("ARIA_ENV", "").lower() == "prod":
            raise RuntimeError(
                "R5.oauth_state: ARIA_OAUTH_STATE_KEY unset in production; "
                "set it to `secrets.token_hex(32)` shared across all workers"
            )
        # Process-local fallback — dev / unit tests only.
        global _PROCESS_KEY
        try:
            return _PROCESS_KEY
        except NameError:
            _PROCESS_KEY = secrets.token_bytes(32)
            return _PROCESS_KEY
    return k


def mint_state(nonce: str | None = None) -> str:
    """Return an opaque state string that survives a round-trip and
    can be verified back with :func:`verify_state`."""
    n = nonce or secrets.token_hex(16)
    sig = _hmac.new(_key(), n.encode(), digestmod="sha256").hexdigest()[:16]
    return f"{n}.{sig}"


def verify_state(state: str) -> bool:
    if not state or "." not in state:
        return False
    n, sig = state.rsplit(".", 1)
    expected = _hmac.new(_key(), n.encode(), digestmod="sha256").hexdigest()[:16]
    return _hmac.compare_digest(sig, expected)


def verify_redirect_uri(presented: str, allow_list: Iterable[str]) -> Tuple[bool, str]:
    """Exact-match URI allow-list.  Returns ``(ok, reason)``."""
    if not presented:
        return False, "empty redirect_uri"
    norm = {a.strip().rstrip("/") for a in allow_list}
    if presented.rstrip("/") not in norm:
        return False, f"redirect_uri {presented!r} not in allow-list"
    return True, ""


register(DefencePlugin(
    round_id="R5",
    name="oauth_state_csrf",
    description="HMAC-bound OAuth state + exact-match redirect-URI allow-list.",
))
