"""R82 — DNS-over-HTTPS / DNS-over-TLS enforcement.

Threat: plain UDP-53 DNS lets an on-path attacker forge responses
(Kaminsky 2008 still relevant; recent: 2023 DNS poisoning of certain
ISP resolvers).  Banking + nation-state guidance: use DoH (RFC 8484)
or DoT (RFC 7858) for any name lookup that drives security decisions
(cert validation, allow-list checks).

Defence: a small ``resolve_doh(host, server)`` that wraps ``safe_open_url``
to query a Cloudflare / Quad9 DoH endpoint with an
``application/dns-message`` body.  ARIA's outbound calls then resolve
through this path when ``ARIA_USE_DOH=1``.  Builds the wire format by
hand so we don't pull in dnspython; correct minimal A-record query.
"""

from __future__ import annotations

import os
import secrets
import struct
from typing import List, Optional, Tuple

from aria.security.plugins import DefencePlugin, register


_DEFAULT_DOH = os.environ.get("ARIA_DOH_RESOLVER", "https://1.1.1.1/dns-query")


def _encode_query(name: str, qtype: int = 1) -> bytes:
    """RFC 1035 wire format: header + question for ``qtype`` (1 = A)."""
    qid = secrets.randbits(16)
    flags = 0x0100               # standard query, RD=1
    header = struct.pack(">HHHHHH", qid, flags, 1, 0, 0, 0)
    parts = name.encode("ascii").split(b".")
    qbytes = b"".join(bytes([len(p)]) + p for p in parts) + b"\x00"
    qbytes += struct.pack(">HH", qtype, 1)
    return header + qbytes


def _parse_a_records(payload: bytes) -> List[str]:
    """Best-effort parse — returns dotted-quad strings for A records."""
    if len(payload) < 12:
        return []
    qdcount, ancount = struct.unpack(">HH", payload[4:8])
    pos = 12
    # Skip questions
    for _ in range(qdcount):
        # Read labels until null
        while pos < len(payload):
            ln = payload[pos]
            pos += 1
            if ln == 0:
                break
            if ln & 0xC0:
                pos += 1
                break
            pos += ln
        pos += 4    # qtype + qclass
    out: List[str] = []
    for _ in range(ancount):
        if pos + 12 > len(payload):
            break
        # Skip name (compressed pointer is common)
        if payload[pos] & 0xC0:
            pos += 2
        else:
            while pos < len(payload):
                ln = payload[pos]
                pos += 1
                if ln == 0:
                    break
                pos += ln
        if pos + 10 > len(payload):
            break
        atype, _aclass, _ttl, rdlen = struct.unpack(">HHIH", payload[pos:pos + 10])
        pos += 10
        if atype == 1 and rdlen == 4 and pos + 4 <= len(payload):
            ip_bytes = payload[pos:pos + 4]
            out.append(".".join(str(b) for b in ip_bytes))
        pos += rdlen
    return out


def resolve_doh(name: str, *, doh_url: Optional[str] = None) -> List[str]:
    from aria.security.guard import GuardError, safe_open_url
    url = doh_url or _DEFAULT_DOH
    qbytes = _encode_query(name)
    import base64
    qb64 = base64.urlsafe_b64encode(qbytes).rstrip(b"=").decode("ascii")
    try:
        body = safe_open_url(
            f"{url}?dns={qb64}",
            timeout=5.0,
            max_bytes=4096,
            allowed_schemes=("https",),
            allowed_content_types=("application/dns-message",),
            enforce_host_allowlist=False,
            headers={
                "Accept": "application/dns-message",
                "User-Agent": "aria-core r82",
            },
        )
        return _parse_a_records(body)
    except GuardError:
        return []
    except Exception:
        return []


register(DefencePlugin(
    round_id="R82",
    name="doh_dot",
    description="DoH client (RFC-8484 wire format) for hardened DNS.",
))
