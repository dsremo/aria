"""R286 — WebSocket subprotocol negotiation audit.

Threat: WebSocket subprotocol selection (RFC 6455 §1.9) is often
ignored — server accepts any client-offered subprotocol.  Mis-handled
selections lead to confused-client attacks where attacker JS speaks
a privileged subprotocol it shouldn't have.

Defence: validate the WebSocket handshake — the server's
``Sec-WebSocket-Protocol`` response must be in the operator-defined
allow-list, and client-offered subprotocols not in the list raise an
audit event.
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


def negotiate_subprotocol(
    client_offered: Iterable[str],
    *,
    server_allowed: Iterable[str],
) -> Tuple[bool, str, List[str]]:
    """Returns (ok, chosen, audit_notes)."""
    offered = [p.strip() for p in client_offered if p and p.strip()]
    allowed = list(server_allowed)
    notes: List[str] = []

    if not offered:
        return False, "", ["ws.no_subprotocol_offered"]
    if not allowed:
        return False, "", ["ws.no_subprotocol_allowed_on_server"]

    rejected = [p for p in offered if p not in allowed]
    if rejected:
        notes.append(f"ws.client_offered_unknown:{','.join(rejected)}")

    chosen = next((p for p in offered if p in allowed), "")
    if not chosen:
        return False, "", notes + ["ws.no_overlap"]
    return True, chosen, notes


register(DefencePlugin(
    round_id="R286",
    name="websocket_subprotocol",
    description="WebSocket subprotocol negotiation audit + strict allow-list.",
))
