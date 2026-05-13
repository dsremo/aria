"""R282 — Business-logic race-condition detector.

Threat: a balance-check + transfer that isn't atomic lets two
concurrent requests both pass the check before either deducts.  Race-
condition exploits in Starbucks gift cards (2014), HackerOne bug
bounties for fintech apps, double-spend on swap UIs.

Defence: a per-key idempotency-and-lock helper.  ``acquire_business_op``
returns False if the key is in flight or already-completed; every
state transition records the operation in a small ledger.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _OpRecord:
    state: str        # "in_flight" | "completed" | "failed"
    started_at: float
    completed_at: float = 0.0


_LEDGER: "OrderedDict[str, _OpRecord]" = OrderedDict()
_LOCK = threading.Lock()
_TTL_SECONDS = 600.0
_MAX_ENTRIES = 4096


def acquire_business_op(idempotency_key: str) -> Tuple[bool, str]:
    if not idempotency_key:
        return False, "empty_key"
    t = time.time()
    with _LOCK:
        # Trim stale + size cap
        while _LEDGER and t - next(iter(_LEDGER.values())).started_at > _TTL_SECONDS:
            _LEDGER.popitem(last=False)
        while len(_LEDGER) > _MAX_ENTRIES:
            _LEDGER.popitem(last=False)

        rec = _LEDGER.get(idempotency_key)
        if rec is not None:
            if rec.state == "in_flight":
                return False, f"race.in_flight age={t - rec.started_at:.2f}s"
            if rec.state == "completed":
                return False, "race.already_completed"
        _LEDGER[idempotency_key] = _OpRecord(state="in_flight", started_at=t)
    return True, "ok"


def complete_business_op(idempotency_key: str, *, success: bool = True) -> None:
    with _LOCK:
        rec = _LEDGER.get(idempotency_key)
        if rec is None:
            return
        rec.state = "completed" if success else "failed"
        rec.completed_at = time.time()


def reset_for_tests() -> None:
    with _LOCK:
        _LEDGER.clear()


register(DefencePlugin(
    round_id="R282",
    name="business_logic_race",
    description="Per-key idempotency-and-lock guard against business-logic races.",
))
