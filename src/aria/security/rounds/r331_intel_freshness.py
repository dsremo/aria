"""R331 — Threat-feed signature freshness.

Threat: stale threat-feed signatures (KEV catalog, AV definitions,
YARA rule sets, OpenSSL CRLs) silently degrade detection over weeks.
A 14-day-old feed misses every CVE published after it.

Defence: per-feed last-refresh ledger.  ``audit_feed_freshness``
flags feeds older than the operator-set window; the ledger ties to
R93 (KEV) + R324 (TAXII) refresh paths.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class FeedDescriptor:
    feed_id: str
    last_refresh_at: float = 0.0
    expected_period_seconds: float = 24 * 3600
    last_record_count: int = 0


_FEEDS: Dict[str, FeedDescriptor] = {}
_LOCK = threading.Lock()


def register_feed(feed_id: str, *, period_seconds: float = 24 * 3600) -> None:
    with _LOCK:
        if feed_id not in _FEEDS:
            _FEEDS[feed_id] = FeedDescriptor(feed_id=feed_id, expected_period_seconds=period_seconds)


def record_refresh(feed_id: str, *, record_count: int = 0, now: float = 0.0) -> None:
    t = now or time.time()
    with _LOCK:
        f = _FEEDS.setdefault(feed_id, FeedDescriptor(feed_id=feed_id))
        f.last_refresh_at = t
        f.last_record_count = record_count


def audit_feed_freshness(*, now: float = 0.0) -> Tuple[bool, List[str]]:
    t = now or time.time()
    issues: List[str] = []
    with _LOCK:
        feeds = list(_FEEDS.values())
    for f in feeds:
        if f.last_refresh_at == 0.0:
            issues.append(f"feed.never_refreshed:{f.feed_id}")
            continue
        age = t - f.last_refresh_at
        if age > 2 * f.expected_period_seconds:
            issues.append(f"feed.stale:{f.feed_id} age_h={int(age / 3600)}")
        if f.last_record_count == 0:
            issues.append(f"feed.empty:{f.feed_id}")
    return not issues, issues


def reset_for_tests() -> None:
    with _LOCK:
        _FEEDS.clear()


register(DefencePlugin(
    round_id="R331",
    name="intel_freshness",
    description="Per-feed freshness ledger; flag stale or empty refreshes.",
))
