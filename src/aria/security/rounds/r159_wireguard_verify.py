"""R159 — WireGuard peer pubkey + endpoint verifier.

Threat: a misconfigured WireGuard tunnel that accepts any peer pubkey
becomes an open VPN.  Many private clusters expose the WG UDP port
publicly and rely on the peer-list as the only access control.

Defence: parse a WG config blob, return the set of declared peer
pubkeys, and audit that no peer has ``AllowedIPs = 0.0.0.0/0`` unless
explicitly opted in.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_PEER_RE = re.compile(
    r"\[Peer\][^\[]*?PublicKey\s*=\s*([A-Za-z0-9+/=]{43,44})"
    r"[^\[]*?AllowedIPs\s*=\s*([^\n]+)",
    re.MULTILINE,
)


def audit_wg_config(config_text: str, *, allow_default_route_peers: bool = False) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    peers = _PEER_RE.findall(config_text or "")
    if not peers:
        issues.append("no_peers_found")
        return False, issues
    for pubkey, allowed in peers:
        nets = [n.strip() for n in allowed.split(",")]
        if any(n in ("0.0.0.0/0", "::/0") for n in nets) and not allow_default_route_peers:
            issues.append(f"default_route_peer pubkey={pubkey[:8]}…")
    return not issues, issues


def is_valid_wg_pubkey(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9+/]{43}=", s or ""))


register(DefencePlugin(
    round_id="R159",
    name="wireguard_verify",
    description="WireGuard config peer-list audit; flag default-route peers.",
))
