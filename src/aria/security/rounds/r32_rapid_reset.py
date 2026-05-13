"""R32 — HTTP/2 RAPID-RESET (CVE-2023-44487).

Threat: an HTTP/2 client opens a stream, sends RST_STREAM, opens
another, sends RST_STREAM — at hundreds of thousands per second per
TCP connection.  Each reset costs the server a stream-create + cleanup
which is expensive even though the client pays nothing.  Cloudflare,
Google, AWS all reported attacks of 100M+ rps in late 2023.

Defence: aiohttp speaks HTTP/1.1 by default — RAPID-RESET is HTTP/2-
specific.  When operators front aria-core with an HTTP/2 reverse proxy
(nginx / Caddy) the proxy must enforce the per-connection
``http2_max_concurrent_streams`` + ``http2_max_resets_per_minute``
caps.  This round ships a configuration generator + a runtime
detector for connections terminating an unusual number of streams.
"""

from __future__ import annotations

import collections
import threading
import time
from dataclasses import dataclass, field
from typing import Deque, Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _ConnState:
    resets: Deque[float] = field(default_factory=collections.deque)


_CONNS: Dict[str, _ConnState] = collections.defaultdict(_ConnState)
_LOCK = threading.Lock()


def record_reset(connection_id: str) -> Tuple[float, int]:
    """Record an HTTP/2 stream reset.  Returns ``(score, resets_in_window)``."""
    now = time.monotonic()
    with _LOCK:
        c = _CONNS[connection_id]
        while c.resets and now - c.resets[0] > 60.0:
            c.resets.popleft()
        c.resets.append(now)
        n = len(c.resets)
    if n >= 200:
        return 1.0, n
    if n >= 50:
        return 0.6, n
    return 0.0, n


_NGINX_RECOMMENDED = """\
# R32 — HTTP/2 RAPID-RESET (CVE-2023-44487) hardening for nginx
http2_max_concurrent_streams 32;
http2_max_field_size 4k;
http2_max_header_size 16k;
http2_recv_buffer_size 256k;

# Per-connection abuse cap
limit_req_zone $binary_remote_addr zone=h2:10m rate=200r/s;
limit_req zone=h2 burst=400 nodelay;
"""


def nginx_recommended_config() -> str:
    return _NGINX_RECOMMENDED


register(DefencePlugin(
    round_id="R32",
    name="http2_rapid_reset",
    description="Per-connection RST_STREAM rate detector + reverse-proxy config.",
))
