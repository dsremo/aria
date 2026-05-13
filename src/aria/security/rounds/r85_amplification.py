"""R85 — Reflection / amplification DDoS (NTP / DNS / memcached / SSDP).

Threat: an attacker spoofs the victim's IP and sends a tiny query to
an open NTP / DNS / memcached server; the server replies with a much
larger response to the victim.  Memcached UDP-amplification reached
51 200× peak (2018).  Recent: 2024 saw renewed CLDAP / mDNS
amplification campaigns.

Defence: ARIA does not run NTP / DNS / memcached on the public side,
so we are not a reflector by default.  This round ships a *boot check*
that confirms no UDP listener exists on the high-amp ports
(``UDP/53``, ``UDP/123``, ``UDP/389``, ``UDP/11211``, ``UDP/1900``,
``UDP/5353``), and the operator's deploy doc.
"""

from __future__ import annotations

import socket
from typing import Dict, List

from aria.security.plugins import DefencePlugin, register


_AMPLIFIER_PORTS = (53, 123, 389, 11211, 1900, 5353, 19, 17)


def open_amplifier_ports() -> Dict[int, str]:
    """Return ``{port: bind_address}`` for any UDP socket ARIA's process
    holds on a known amplifier port.  Empty dict = clean.
    """
    out: Dict[int, str] = {}
    for port in _AMPLIFIER_PORTS:
        # We can't enumerate other processes' sockets without /proc
        # walking; we check our own by attempting a non-binding probe.
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                # Already bound by someone — flag it
                out[port] = "already_in_use"
            else:
                sock.close()
        except Exception:
            continue
    return out


_NGINX_RECOMMENDED = """\
# R85 — egress / ingress firewall hint
# UDP amplification ports must NOT be reachable from the public internet:
#   block UDP/53 (DNS recursion), UDP/123 (NTP), UDP/389 (CLDAP),
#         UDP/11211 (memcached), UDP/1900 (SSDP), UDP/5353 (mDNS)
# from any non-trusted source.
"""


register(DefencePlugin(
    round_id="R85",
    name="amplification",
    description="Boot check that ARIA's process is not an amplifier reflector.",
))
