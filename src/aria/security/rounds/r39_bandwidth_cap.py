"""R39 — Per-tenant bandwidth cap.

Threat: a paying tenant (or their compromised key) consumes the entire
egress link by streaming gigabytes through ``screen_bulk``.  Even if
the per-minute rate-limit holds, a single bulk request of 50 MB ×
1 RPS sustained = 4 TB/day.

Defence: per-tenant rolling-window byte counter, both inbound and
outbound.  At 1 GiB/min default cap, a 5-second window decision
returns 429 with Retry-After computed from the next-budget time.
"""

from __future__ import annotations

import collections
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Deque, Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Bucket:
    events: Deque[Tuple[float, int]] = field(default_factory=collections.deque)


_BUCKETS: Dict[str, _Bucket] = collections.defaultdict(_Bucket)
_LOCK = threading.Lock()


def _budget_per_min() -> int:
    return int(os.environ.get("ARIA_BANDWIDTH_CAP_PER_MIN_BYTES", str(1 << 30)))     # 1 GiB


def consume_bytes(identity: str, n_bytes: int) -> Tuple[bool, int]:
    """Returns ``(allowed, retry_after_seconds_if_blocked)``."""
    if n_bytes <= 0 or not identity:
        return True, 0
    now = time.monotonic()
    cap = _budget_per_min()
    with _LOCK:
        b = _BUCKETS[identity]
        while b.events and now - b.events[0][0] > 60.0:
            b.events.popleft()
        used = sum(c for _, c in b.events)
        if used + n_bytes > cap:
            # Compute next free moment
            if b.events:
                retry = max(1, int(60.0 - (now - b.events[0][0]) + 1.0))
            else:
                retry = 1
            return False, retry
        b.events.append((now, n_bytes))
        return True, 0


def reset(identity: str) -> None:
    with _LOCK:
        _BUCKETS.pop(identity, None)


register(DefencePlugin(
    round_id="R39",
    name="bandwidth_cap",
    description="Per-tenant 1 GiB/min byte budget with retry-after computation.",
))
