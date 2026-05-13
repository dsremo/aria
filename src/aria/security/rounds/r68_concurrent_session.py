"""R68 — Concurrent-session limit.

Threat: stolen credentials let an attacker stand up a parallel session
in another country while the legit user keeps working.  Banking
standard: cap concurrent sessions per principal; alert on overlap;
optionally evict the older session on a new login.

Defence: a per-principal session counter with a configurable cap (3 by
default).  Login over the cap returns 429 ``too_many_sessions`` unless
``force=True`` is supplied (which evicts the oldest).
"""

from __future__ import annotations

import collections
import os
import threading
from dataclasses import dataclass
from typing import Deque, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Session:
    token: str
    started_at: float


_SESSIONS: Dict[str, Deque[_Session]] = collections.defaultdict(collections.deque)
_LOCK = threading.Lock()


def _cap() -> int:
    return int(os.environ.get("ARIA_MAX_CONCURRENT_SESSIONS", "3"))


def open_session(principal: str, token: str, *, force: bool = False) -> Tuple[bool, str]:
    import time
    now = time.monotonic()
    with _LOCK:
        d = _SESSIONS[principal]
        if len(d) >= _cap() and not force:
            return False, "too_many_sessions"
        if force and len(d) >= _cap():
            d.popleft()
        d.append(_Session(token=token, started_at=now))
    return True, "ok"


def close_session(principal: str, token: str) -> None:
    with _LOCK:
        d = _SESSIONS.get(principal)
        if not d:
            return
        for i, s in enumerate(list(d)):
            if s.token == token:
                del d[i]
                return


def list_sessions(principal: str) -> List[Tuple[str, float]]:
    with _LOCK:
        d = _SESSIONS.get(principal, collections.deque())
        return [(s.token, s.started_at) for s in d]


def reset(principal: str) -> None:
    with _LOCK:
        _SESSIONS.pop(principal, None)


register(DefencePlugin(
    round_id="R68",
    name="concurrent_session",
    description="Per-principal session cap (3 default); force-evict oldest.",
))
