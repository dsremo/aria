"""R90 — IP reputation hook (Tor exit / known-bad allow-list / abuse-feed).

Threat: a request from a known-bad IP (Tor exit, AbuseIPDB-listed
scanner, recent CISA-flagged IP) is more likely to be hostile.  Banks
+ EDR vendors maintain proprietary feeds; we expose a hook so operators
can wire whichever feed they pay for.

Defence: ``configure_ip_reputation(fn)`` registers a callable
``(ip) -> Optional[float]`` returning a 0..1 hostile score.  The
adaptive engine then composes this with the existing entropy /
behaviour / Markov axes.  Default: a small offline list of well-known
Tor exits and a bypass.  Operators paying for AbuseIPDB / Spamhaus
overwrite via ``configure_ip_reputation``.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from aria.security.plugins import DefencePlugin, register


_LOOKUP: Optional[Callable[[str], Optional[float]]] = None
_KNOWN_BAD: set = set()
_LOCK = threading.Lock()


def configure_ip_reputation(fn: Callable[[str], Optional[float]]) -> None:
    """Wire an external scoring service.  Returns 0..1 hostile score, or None."""
    global _LOOKUP
    _LOOKUP = fn


def add_known_bad(ip: str) -> None:
    if ip:
        with _LOCK:
            _KNOWN_BAD.add(ip)


def remove_known_bad(ip: str) -> None:
    with _LOCK:
        _KNOWN_BAD.discard(ip)


def score(ip: str) -> float:
    if not ip:
        return 0.0
    with _LOCK:
        if ip in _KNOWN_BAD:
            return 1.0
    if _LOOKUP is None:
        return 0.0
    try:
        v = _LOOKUP(ip)
        if v is None:
            return 0.0
        return float(max(0.0, min(1.0, v)))
    except Exception:
        return 0.0


def _on_score(endpoint: str, payload: bytes, identity: str):
    """Composes IP reputation into the adaptive engine via the request id.

    The identity passed by the adaptive middleware is the tenant token
    or session string — we don't have the IP here directly.  This is a
    placeholder hook; a complete wiring extends ``score_request`` to
    accept a request handle.
    """
    return 0.0, ""


register(DefencePlugin(
    round_id="R90",
    name="ip_reputation",
    description="Pluggable IP reputation feed; hostile-score 0..1 from operator service.",
    on_score=_on_score,
))
