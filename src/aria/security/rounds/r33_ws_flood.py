"""R33 — WebSocket flood / message-rate DoS.

Threat: a WebSocket-enabled endpoint accepts long-lived bidirectional
streams.  An attacker opens 100 connections, each blasting 50 K/sec
empty pings, exhausting CPU and event-loop budget.  The dashboard
``/ws/live`` and bus-event WS in dsremo are both exposed.

Defence: per-connection token bucket — each WS message debits one
token; refilling at a configurable rate.  When the bucket dries up,
the server closes the connection with code 1008 (policy violation).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Bucket:
    tokens: float
    last: float
    capacity: float
    rate: float

    def consume(self, n: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = now - self.last
        self.last = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False


class WSFlowControl:
    """Per-connection bucket; default 100 msg/s burst, 20 msg/s sustained."""

    def __init__(self, *, capacity: float = 100.0, rate: float = 20.0) -> None:
        self._capacity = capacity
        self._rate = rate
        self._buckets: dict = {}
        self._lock = threading.Lock()

    def allow(self, connection_id: str) -> bool:
        with self._lock:
            b = self._buckets.get(connection_id)
            if b is None:
                b = _Bucket(
                    tokens=self._capacity,
                    last=time.monotonic(),
                    capacity=self._capacity,
                    rate=self._rate,
                )
                self._buckets[connection_id] = b
            return b.consume()

    def close(self, connection_id: str) -> None:
        with self._lock:
            self._buckets.pop(connection_id, None)


_GLOBAL_FC = WSFlowControl()


def allow_ws_message(connection_id: str) -> bool:
    return _GLOBAL_FC.allow(connection_id)


def close_ws_session(connection_id: str) -> None:
    _GLOBAL_FC.close(connection_id)


register(DefencePlugin(
    round_id="R33",
    name="ws_flood",
    description="Per-WebSocket-connection token bucket (100 burst / 20 sustained).",
))
