"""R160 — Zero-trust outbound-only tunnel posture.

Threat: a publicly exposed admin port (SSH, RDP, K8s API, database)
is the largest open-internet attack surface most orgs maintain.
Cloudflare Tunnel / Tailscale invert the model: agent dials out, no
inbound port required.

Defence: an audit helper that lists the host's listening sockets and
refuses to start if any port outside an opt-in allow-list is bound to
0.0.0.0 / :: when ARIA_ENV=prod.
"""

from __future__ import annotations

import os
import socket
from typing import Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


def list_listening_ports() -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    try:
        with open("/proc/net/tcp") as fh:
            lines = fh.readlines()[1:]
    except OSError:
        return out
    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        local = parts[1]
        state = parts[3]
        if state != "0A":             # 0A = LISTEN
            continue
        ip_hex, port_hex = local.split(":")
        port = int(port_hex, 16)
        # /proc/net/tcp ip is little-endian
        ip_bytes = bytes.fromhex(ip_hex)[::-1]
        ip_str = socket.inet_ntoa(ip_bytes) if len(ip_bytes) == 4 else ip_hex
        out.append((ip_str, port))
    return out


def boot_check_outbound_only(allowed_ports: Iterable[int]) -> Tuple[bool, List[str]]:
    if os.environ.get("ARIA_ENV") != "prod":
        return True, ["non_prod"]
    allow = set(int(p) for p in allowed_ports)
    issues: List[str] = []
    for ip, port in list_listening_ports():
        if ip in ("0.0.0.0", "::") and port not in allow:
            issues.append(f"public_listener {ip}:{port}")
    return not issues, issues


register(DefencePlugin(
    round_id="R160",
    name="zero_trust_tunnel",
    description="Refuse non-allowlisted public listeners in prod (zero-trust outbound posture).",
))
