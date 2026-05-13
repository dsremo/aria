"""R287 — Server-Sent Events (SSE) validation.

Threat: SSE streams hold long-lived HTTP/1.1 connections that bypass
many gateway-level rate limits.  A misconfigured CORS + SSE endpoint
can leak per-user notifications cross-origin, and an unbounded event
stream can be tunnel for exfil.

Defence: per-connection rate-cap on event emission, per-event size
cap, refusal of CORS wildcards on SSE responses.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _StreamState:
    events_per_second: Deque[float] = field(default_factory=lambda: deque(maxlen=1024))


_STREAMS: Dict[str, _StreamState] = defaultdict(_StreamState)
_LOCK = threading.Lock()


def admit_sse_event(
    stream_id: str, event_bytes: int, *,
    max_event_bytes: int = 16_384,
    max_events_per_second: int = 50,
    now: float = 0.0,
) -> Tuple[bool, str]:
    if event_bytes > max_event_bytes:
        return False, f"sse.event_too_large:{event_bytes}>{max_event_bytes}"
    t = now or time.time()
    with _LOCK:
        state = _STREAMS[stream_id]
        state.events_per_second.append(t)
        recent = sum(1 for ts in state.events_per_second if t - ts <= 1.0)
    if recent > max_events_per_second:
        return False, f"sse.rate_exceeded:{recent}/{max_events_per_second}"
    return True, "ok"


def audit_sse_response_headers(headers: Dict[str, str]) -> Tuple[bool, list]:
    issues = []
    norm = {k.lower(): v for k, v in (headers or {}).items()}
    if norm.get("content-type", "").lower() != "text/event-stream":
        issues.append(f"sse.wrong_content_type:{norm.get('content-type', '')}")
    if norm.get("access-control-allow-origin") == "*":
        issues.append("sse.cors_wildcard")
    if "cache-control" in norm and "no-cache" not in norm["cache-control"].lower():
        issues.append("sse.cache_control_not_no_cache")
    return not issues, issues


def reset_for_tests() -> None:
    with _LOCK:
        _STREAMS.clear()


register(DefencePlugin(
    round_id="R287",
    name="sse_audit",
    description="SSE per-event size + rate cap + CORS wildcard refusal.",
))
