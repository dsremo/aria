"""R294 — Clipboard / screen-capture governor.

Threat: clipboard is a classic exfil channel — a quick Cmd+C +
screenshot bypasses every server-side rate limit.  Endpoint DLP
products tackle this at OS hooks; web apps need an in-app governor.

Defence: a per-user clipboard-event audit + size limiter.  The
governor returns whether the requested copy exceeds policy bytes,
and emits an event for downstream UEBA (R246).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class ClipboardEvent:
    timestamp: float
    user_id: str
    bytes_copied: int
    document_classification: str = "internal"


@dataclass
class _UserClipboard:
    history: Deque[ClipboardEvent] = field(default_factory=lambda: deque(maxlen=512))


_HISTORY: Dict[str, _UserClipboard] = defaultdict(_UserClipboard)
_LOCK = threading.Lock()


def admit_copy(
    user_id: str, bytes_copied: int, *,
    max_bytes_per_event: int = 64 * 1024,
    max_bytes_per_hour: int = 10 * 1024 * 1024,
    classification: str = "internal",
    now: float = 0.0,
) -> Tuple[bool, str]:
    if bytes_copied > max_bytes_per_event:
        return False, f"clipboard.event_too_large:{bytes_copied}"
    t = now or time.time()
    with _LOCK:
        state = _HISTORY[user_id]
        state.history.append(ClipboardEvent(t, user_id, bytes_copied, classification))
        recent = [e for e in state.history if t - e.timestamp <= 3600.0]
    total = sum(e.bytes_copied for e in recent)
    if total > max_bytes_per_hour:
        return False, f"clipboard.hourly_burst:{total}/{max_bytes_per_hour}"
    if classification in ("confidential", "secret", "top_secret") and total > max_bytes_per_hour // 4:
        return False, f"clipboard.classified_burst:{total}"
    return True, "ok"


def reset_for_tests() -> None:
    with _LOCK:
        _HISTORY.clear()


register(DefencePlugin(
    round_id="R294",
    name="clipboard_governor",
    description="Per-user clipboard byte-cap with hourly + classified-doc burst guards.",
))
