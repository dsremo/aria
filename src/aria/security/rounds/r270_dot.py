"""R270 — DNS-over-TLS (DoT) preference.

Threat: classical port-53 DNS leaks every host the client looks up
to any on-path observer (employer, ISP, hostile network).  R82 added
DoH; DoT (RFC 7858) is the equivalent for use in containerised /
embedded contexts where HTTPS overhead is unwanted.

Defence: a thin TLS-1.3-pinned DoT client + audit helper that confirms
an outbound resolver list contains only DoT-capable servers.
"""

from __future__ import annotations

import socket
import ssl
import struct
from typing import Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


_KNOWN_DOT_RESOLVERS = {
    "1.1.1.1": "cloudflare-dns.com",
    "8.8.8.8": "dns.google",
    "9.9.9.9": "dns.quad9.net",
}


def make_dot_query(name: str, qtype: int = 1) -> bytes:
    """Build a single A-record DNS query (id=0)."""
    flags = 0x0100         # standard query, recursion desired
    header = struct.pack(">HHHHHH", 0, flags, 1, 0, 0, 0)
    qname = b""
    for label in name.split("."):
        if not label:
            continue
        qname += bytes([len(label)]) + label.encode("idna")
    qname += b"\x00"
    qtype_bytes = struct.pack(">HH", qtype, 1)
    return header + qname + qtype_bytes


def query_dot(server: str, name: str, *, port: int = 853, timeout: float = 5.0) -> Tuple[bool, bytes]:
    sni = _KNOWN_DOT_RESOLVERS.get(server, server)
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    sock = socket.create_connection((server, port), timeout=timeout)
    try:
        with ctx.wrap_socket(sock, server_hostname=sni) as tls:
            payload = make_dot_query(name)
            tls.sendall(struct.pack(">H", len(payload)) + payload)
            length = struct.unpack(">H", tls.recv(2))[0]
            response = tls.recv(length)
            return True, response
    except Exception as exc:
        return False, str(exc).encode()


def audit_resolver_list(resolvers: Iterable[str]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    for r in resolvers:
        if r not in _KNOWN_DOT_RESOLVERS:
            issues.append(f"dot.unknown_resolver:{r}")
    return not issues, issues


register(DefencePlugin(
    round_id="R270",
    name="dot",
    description="DNS-over-TLS client + resolver-list audit (RFC 7858).",
))
