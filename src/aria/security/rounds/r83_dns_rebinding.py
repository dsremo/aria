"""R83 — DNS rebinding (advanced, beyond R15).

Threat: an attacker controls ``rebind.example.com``.  First lookup
returns ``8.8.8.8`` (passes SSRF check); ARIA caches.  Seconds later
the same hostname returns ``169.254.169.254`` for the connect step.
The basic SSRF guard in :mod:`aria.security.guard` resolves once + checks
private IPs but does NOT pin the resolved IP to the connect socket.

Defence: ``resolve_and_pin(host)`` returns ``(public_ip, host)`` —
caller opens the socket directly to ``public_ip`` with the original
``Host`` header set, eliminating the second lookup.  Plus a small
``RebindDetector`` that observes the gap between resolution and connect
and flags any change.
"""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _PinEntry:
    ip: str
    pinned_at: float


_PINS: dict = {}
_LOCK = threading.Lock()


def resolve_and_pin(host: str) -> Optional[str]:
    """Resolve once, return the IP, cache for connect-step reuse.

    The cache lives 5 s — long enough for one connect, short enough
    that legitimate DNS-changes don't break.
    """
    if not host:
        return None
    now = time.monotonic()
    with _LOCK:
        e = _PINS.get(host)
        if e and (now - e.pinned_at) < 5.0:
            return e.ip
    try:
        ip = socket.gethostbyname(host)
    except OSError:
        return None
    with _LOCK:
        _PINS[host] = _PinEntry(ip=ip, pinned_at=now)
    return ip


class RebindDetector:
    """Compare consecutive resolutions of the same host."""

    def __init__(self) -> None:
        self._seen: dict = {}
        self._lock = threading.Lock()

    def observe(self, host: str, ip: str) -> Tuple[bool, str]:
        with self._lock:
            prev = self._seen.get(host)
            self._seen[host] = ip
        if prev and prev != ip:
            return True, f"rebound host={host} {prev} -> {ip}"
        return False, ""


_DETECTOR = RebindDetector()


def detect_rebind(host: str, ip: str) -> Tuple[bool, str]:
    return _DETECTOR.observe(host, ip)


register(DefencePlugin(
    round_id="R83",
    name="dns_rebinding",
    description="Resolve-and-pin + cross-call rebind detection beyond R15.",
))
