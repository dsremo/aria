"""R89 — WebSocket authentication on upgrade.

Threat: ARIA's read-only event-stream WebSocket (`/api/v1/ws/events`,
`/ws/live`) accepts the upgrade without an auth check (R50 Block C
documented this as residual risk).  An anonymous viewer may fingerprint
the system through the bus content even if mutating commands need auth.
Banking standard: every long-lived stream is authenticated.

Defence: ``require_token_on_upgrade(request)`` — reads a token from
either ``Authorization: Bearer`` or ``X-ARIA-Token`` header (the same
shapes as the HTTP path), validates it via the operator-supplied
verifier, returns the principal or refuses the upgrade.  Plugs into
the dashboard / dsremo bus.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from aria.security.plugins import DefencePlugin, register


_VERIFIER: Optional[Callable[[str], Optional[str]]] = None


def configure_token_verifier(fn: Callable[[str], Optional[str]]) -> None:
    """Wire a callable that takes a raw token and returns a principal-id
    string when valid (or None to deny)."""
    global _VERIFIER
    _VERIFIER = fn


def require_token_on_upgrade(request) -> Tuple[bool, str]:
    """Return ``(allowed, principal_or_reason)``."""
    auth = (request.headers.get("Authorization", "")
            .removeprefix("Bearer ").strip())
    tok = (
        auth
        or request.headers.get("X-ARIA-Token", "")
    )
    if not tok:
        return False, "missing_token"
    if _VERIFIER is None:
        return False, "verifier_not_configured"
    try:
        principal = _VERIFIER(tok)
    except Exception as exc:
        return False, f"verifier_error:{exc}"
    if not principal:
        return False, "invalid_token"
    return True, principal


register(DefencePlugin(
    round_id="R89",
    name="websocket_auth",
    description="Enforce auth on WS upgrade; closes a residual R50 gap.",
))
