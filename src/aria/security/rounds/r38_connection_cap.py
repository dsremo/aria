"""R38 — Per-IP TCP connection cap.

Threat: an attacker opens 10 000 idle TCP connections from one IP,
holding socket FDs and starving legitimate clients.  This is the
non-HTTP tier of the slowloris family.  Defence ideally lives in the
reverse proxy (nginx ``limit_conn`` / Caddy ``rate_limit``) but
deployers without one need a Python-side fallback.

Defence: a counter per IP, incremented on connection accept,
decremented on close.  When the cap is exceeded the connection is
closed before it sees any application bytes.  Plus a generated
nginx config snippet for operators using a real reverse proxy.
"""

from __future__ import annotations

import threading
from typing import Dict

from aria.security.plugins import DefencePlugin, register


class _ConnCounter:
    def __init__(self, *, cap_per_ip: int = 64) -> None:
        self._cap = cap_per_ip
        self._counts: Dict[str, int] = {}
        self._lock = threading.Lock()

    def acquire(self, ip: str) -> bool:
        with self._lock:
            n = self._counts.get(ip, 0)
            if n >= self._cap:
                return False
            self._counts[ip] = n + 1
            return True

    def release(self, ip: str) -> None:
        with self._lock:
            n = self._counts.get(ip, 0)
            if n <= 1:
                self._counts.pop(ip, None)
            else:
                self._counts[ip] = n - 1

    def count(self, ip: str) -> int:
        with self._lock:
            return self._counts.get(ip, 0)


_GLOBAL = _ConnCounter()


def acquire(ip: str) -> bool:
    return _GLOBAL.acquire(ip)


def release(ip: str) -> None:
    _GLOBAL.release(ip)


_NGINX = """\
# R38 — per-IP connection cap for nginx in front of aria-core
limit_conn_zone $binary_remote_addr zone=aria_per_ip:10m;
server {
    listen 443 ssl http2;
    limit_conn aria_per_ip 64;
    ...
}
"""


def nginx_recommended_config() -> str:
    return _NGINX


register(DefencePlugin(
    round_id="R38",
    name="connection_cap",
    description="Python-side per-IP connection counter (64 default) + nginx config.",
))
