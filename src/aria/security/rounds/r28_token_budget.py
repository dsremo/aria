"""R28 — Token-budget exhaustion / context-window stuffing.

Threat: an attacker submits a single 200-KB user message — at 4 chars
per token that's 50 K tokens, exhausting the model context, the
operator's monthly token budget, and the response time SLO.  Cheap
DOS that also pushes the original system prompt out of context, often
weakening alignment.

Defence: per-tenant + per-session sliding token-count budget.  We
estimate tokens with the rough rule ``len(utf8) / 4`` (the ratio is
within 20 % for English / code; a cheap-and-cheerful estimator).
Operators wire a real tokeniser via ``configure_token_estimator()``
when accuracy matters more than throughput.  Hits over budget refuse
with HTTP 429 + Retry-After.
"""

from __future__ import annotations

import collections
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, Optional, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Bucket:
    events: Deque[Tuple[float, int]] = field(default_factory=collections.deque)


_BUCKETS: Dict[str, _Bucket] = collections.defaultdict(_Bucket)
_LOCK = threading.Lock()
_ESTIMATOR: Optional[Callable[[str], int]] = None


def configure_token_estimator(fn: Callable[[str], int]) -> None:
    global _ESTIMATOR
    _ESTIMATOR = fn


def estimate_tokens(text: str) -> int:
    if _ESTIMATOR is not None:
        try:
            return int(_ESTIMATOR(text))
        except Exception:
            pass
    if not text:
        return 0
    # Cheap heuristic: 1 token ≈ 4 chars of UTF-8.
    return max(1, len(text.encode("utf-8")) // 4)


def _budget_per_minute() -> int:
    return int(os.environ.get("ARIA_TOKEN_BUDGET_PER_MIN", "60000"))


def consume(identity: str, text: str) -> Tuple[bool, int, int]:
    """Return ``(allowed, used, budget)``.  Sliding 60-second window."""
    cost = estimate_tokens(text)
    now = time.monotonic()
    budget = _budget_per_minute()
    with _LOCK:
        b = _BUCKETS[identity]
        # Evict events older than 60 s
        while b.events and now - b.events[0][0] > 60.0:
            b.events.popleft()
        used = sum(c for _, c in b.events)
        if used + cost > budget:
            return False, used + cost, budget
        b.events.append((now, cost))
        return True, used + cost, budget


def reset(identity: str) -> None:
    with _LOCK:
        _BUCKETS.pop(identity, None)


register(DefencePlugin(
    round_id="R28",
    name="token_budget",
    description="Per-identity token-count sliding window; default 60K tokens/min.",
))
