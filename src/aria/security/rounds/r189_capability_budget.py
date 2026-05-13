"""R189 — Per-capability rate budget.

Threat: even a benign agent can flood downstream services through
rapid tool calls — file_write, db_query, llm_call — and bring down a
shared SaaS quota or rack up huge bills.  Worse, an attacker hijacks
the agent and burns the budget intentionally.

Defence: a token-bucket limiter keyed on (session, capability).
Operators set per-capability budgets; the limiter refuses calls past
the bucket.  Pairs with R28 token-budget exhaustion + R140 oracle.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Bucket:
    tokens: float
    refill_per_second: float
    capacity: float
    last_ts: float


_DEFAULTS: Dict[str, Tuple[float, float]] = {
    "llm_call":    (60.0, 1.0),
    "tool_call":   (300.0, 5.0),
    "db_query":    (200.0, 3.0),
    "file_write":  (100.0, 0.5),
    "outbound_http": (60.0, 1.0),
}

_BUCKETS: Dict[str, _Bucket] = {}
_LOCK = threading.Lock()


def configure(capability: str, capacity: float, refill_per_second: float) -> None:
    _DEFAULTS[capability] = (capacity, refill_per_second)


def consume(session_id: str, capability: str, cost: float = 1.0) -> Tuple[bool, str]:
    key = f"{session_id}|{capability}"
    cap, refill = _DEFAULTS.get(capability, (60.0, 1.0))
    now = time.monotonic()
    with _LOCK:
        b = _BUCKETS.get(key)
        if b is None:
            b = _Bucket(tokens=cap, refill_per_second=refill, capacity=cap, last_ts=now)
            _BUCKETS[key] = b
        elapsed = now - b.last_ts
        b.tokens = min(b.capacity, b.tokens + elapsed * b.refill_per_second)
        b.last_ts = now
        if b.tokens < cost:
            return False, f"budget_exceeded cap={capability} need={cost} have={b.tokens:.2f}"
        b.tokens -= cost
    return True, "ok"


def reset(session_id: str, capability: str = "") -> None:
    with _LOCK:
        if capability:
            _BUCKETS.pop(f"{session_id}|{capability}", None)
        else:
            for k in list(_BUCKETS):
                if k.startswith(f"{session_id}|"):
                    _BUCKETS.pop(k, None)


register(DefencePlugin(
    round_id="R189",
    name="capability_budget",
    description="Per-capability token-bucket rate limit per agent session.",
))
