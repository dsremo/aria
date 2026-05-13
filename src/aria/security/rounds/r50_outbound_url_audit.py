"""R50 — Outbound-URL plugin-fired allow-list audit.

Threat: a future contributor wires a new third-party API call
(``http_get('https://newvendor.example.com/...')``) and forgets to
extend the SSRF allow-list or the trust-feed.  Catching this in
review is brittle; a runtime audit guarantees we know about it.

Defence: a plugin ``on_outbound_url`` hook that fires every time
``aria.security.guard.safe_open_url`` is called.  The hook simply
records the host and emits a CRITICAL audit event the *first* time
each new host is seen.  Operators consume this via the audit-log feed
and add the host to the official allow-list (or remove the call).
"""

from __future__ import annotations

import logging
import threading
import urllib.parse
from typing import List, Set

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r50")
_SEEN: Set[str] = set()
_LOCK = threading.Lock()


def _on_outbound(url: str) -> List[str]:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return []
    if not host:
        return []
    with _LOCK:
        first = host not in _SEEN
        _SEEN.add(host)
    if first:
        logger.warning("r50.first_outbound_to host=%s url=%s", host, url[:200])
    return []  # never blocks; just records


def seen_hosts() -> List[str]:
    with _LOCK:
        return sorted(_SEEN)


register(DefencePlugin(
    round_id="R50",
    name="outbound_url_audit",
    description="Record + alert on first outbound call to any new host.",
    on_outbound_url=_on_outbound,
))
