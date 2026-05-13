"""R40 — HTTP keep-alive socket-hold abuse.

Threat: an attacker opens a connection, sends one valid request, then
holds the keep-alive socket open while the operating system thinks the
worker is busy.  Differs from slowloris: the request itself completes,
it's the IDLE between requests that's hostile.

Defence: per-connection idle-timeout that fires regardless of HTTP
request state.  Default: 30 s of idle → close.  ``track_activity()``
called on every request renews the timer.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Conn:
    last_activity: float
    requests: int = 0


_CONNS: Dict[str, _Conn] = {}
_LOCK = threading.Lock()


def track_activity(connection_id: str) -> None:
    now = time.monotonic()
    with _LOCK:
        c = _CONNS.get(connection_id)
        if c is None:
            _CONNS[connection_id] = _Conn(last_activity=now, requests=1)
        else:
            c.last_activity = now
            c.requests += 1


def is_idle(connection_id: str, *, idle_seconds: float = 30.0) -> bool:
    with _LOCK:
        c = _CONNS.get(connection_id)
    if c is None:
        return False
    return (time.monotonic() - c.last_activity) > idle_seconds


def close(connection_id: str) -> None:
    with _LOCK:
        _CONNS.pop(connection_id, None)


register(DefencePlugin(
    round_id="R40",
    name="keepalive_abuse",
    description="Per-connection idle timer; close after 30 s of no requests.",
))
