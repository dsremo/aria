"""R316 — Cascading-timeout enforcement.

Threat: a request with a 30-second client timeout calls a service
with no inner timeout that calls a database with no inner timeout —
each layer gets stuck waiting and the whole stack times out together.
Tail-latency amplification.

Defence: a per-request deadline propagated through call chain.
``deadline_for_subcall`` returns the remaining budget minus a safety
margin so the subcall always finishes before the parent.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class Deadline:
    deadline_monotonic: float


_LOCAL = threading.local()


def set_deadline(seconds_from_now: float) -> Deadline:
    d = Deadline(deadline_monotonic=time.monotonic() + max(0.001, seconds_from_now))
    _LOCAL.deadline = d
    return d


def get_deadline() -> Optional[Deadline]:
    return getattr(_LOCAL, "deadline", None)


def clear_deadline() -> None:
    if hasattr(_LOCAL, "deadline"):
        delattr(_LOCAL, "deadline")


def deadline_for_subcall(*, safety_margin_ms: float = 50.0) -> Tuple[bool, float]:
    """Returns (has_budget, seconds_for_subcall)."""
    d = get_deadline()
    if d is None:
        return True, 30.0
    remaining = d.deadline_monotonic - time.monotonic()
    if remaining <= safety_margin_ms / 1000.0:
        return False, 0.0
    return True, remaining - safety_margin_ms / 1000.0


def is_expired() -> bool:
    d = get_deadline()
    return d is not None and time.monotonic() >= d.deadline_monotonic


register(DefencePlugin(
    round_id="R316",
    name="timeout_cascade",
    description="Per-request deadline propagation with safety margin for sub-calls.",
))
