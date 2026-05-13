"""R150 — Request-ID uniqueness audit (forensics tie).

Threat: an attacker tries to slip a request through with a crafted
``X-Request-Id`` that collides with another tenant's recent ID — log
correlation across the audit chain then merges two flows into one.
Banks + air-gapped deployers want every request-ID to be unique
across the entire fleet's audit horizon (24 h).

Defence: ``record_request_id(rid, tenant)`` records every minted +
inbound ID with the tenant context.  On collision, raise + alert.
Pairs with R-foundation `make_request_id_middleware` (which validates
the shape) — this one validates *uniqueness*.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Tuple

from aria.security.plugins import DefencePlugin, register


_SEEN: Dict[str, Tuple[float, str]] = {}
_QUEUE: Deque[Tuple[float, str]] = deque(maxlen=131072)         # 128 K IDs
_LOCK = threading.Lock()
_TTL = 86_400.0


def record_request_id(request_id: str, tenant: str) -> Tuple[bool, str]:
    """Returns ``(unique, reason)``.  unique=False = collision."""
    if not request_id:
        return False, "empty"
    now = time.monotonic()
    with _LOCK:
        # Evict expired IDs from the front of the queue
        while _QUEUE and now - _QUEUE[0][0] > _TTL:
            _, old = _QUEUE.popleft()
            _SEEN.pop(old, None)
        prev = _SEEN.get(request_id)
        if prev is not None:
            prev_ts, prev_tenant = prev
            return False, f"collision_with_tenant={prev_tenant} age={now - prev_ts:.0f}s"
        _SEEN[request_id] = (now, tenant)
        _QUEUE.append((now, request_id))
    return True, "unique"


def known_count() -> int:
    with _LOCK:
        return len(_SEEN)


register(DefencePlugin(
    round_id="R150",
    name="request_id_unique",
    description="Per-fleet request-ID collision detector with 24 h horizon.",
))
