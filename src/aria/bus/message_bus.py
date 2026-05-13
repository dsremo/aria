"""Priority-queued pub/sub message bus.

ARIA agents communicate exclusively through this bus — no direct calls.

Performance targets from the plan:
  - P0 emergency: < 50us delivery
  - P1 critical:  < 1ms delivery
  - P2 warning:   < 5ms delivery
  - P3+ routine:  < 50ms delivery
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

import structlog

from aria.core.types import EventPriority

logger = structlog.get_logger()

# Type alias for subscriber callbacks
Subscriber = Callable[["Message"], Coroutine[Any, Any, None]]


@dataclass(frozen=True)
class Message:
    """Immutable message on the ARIA bus.

    Every inter-agent communication, sensor reading, anomaly alert,
    and command flows through this structure.
    """

    topic: str  # e.g. "aria.telemetry.anomaly.detected"
    payload: dict[str, Any]
    priority: EventPriority = EventPriority.P3_ROUTINE
    source_agent: str = ""
    target_agent: str = ""  # Empty = broadcast
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: str = ""  # Links related messages (e.g. request → response)

    def __lt__(self, other: Message) -> bool:
        """Priority ordering for the queue."""
        return self.priority.value < other.priority.value


class MessageBus:
    """Priority-queued pub/sub message bus for ARIA agents.

    Features:
      - Topic-based subscriptions with glob patterns (e.g. "aria.telemetry.*")
      - Priority queue ensures P0 emergency messages jump ahead
      - Message history for replay and debugging
      - Metrics: message counts, latency per priority level
    """

    def __init__(self, max_history: int = 10_000) -> None:
        self._subscribers: dict[str, list[Subscriber]] = {}
        self._queue: asyncio.PriorityQueue[tuple[int, float, Message]] = (
            asyncio.PriorityQueue()
        )
        self._history: list[Message] = []
        self._max_history = max_history
        self._running = False
        self._dispatch_task: asyncio.Task[None] | None = None
        self._stats = {
            "total_published": 0,
            "total_delivered": 0,
            "total_dropped": 0,
        }

    @property
    def stats(self) -> dict[str, Any]:
        # Wiring audit Pass 7 (F11.5) — added ``history_size`` so
        # diagnostics endpoints don't need to reach into the private
        # ``self._history`` list.
        return {
            **self._stats,
            "subscribers": len(self._subscribers),
            "queue_size": self._queue.qsize(),
            "history_size": len(self._history),
        }

    async def start(self) -> None:
        """Start the message dispatch loop."""
        if self._running:
            return
        self._running = True
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())
        logger.info("bus.started")

    async def stop(self) -> None:
        """Stop the message dispatch loop gracefully."""
        self._running = False
        if self._dispatch_task:
            # Push a sentinel to unblock the queue
            sentinel = Message(topic="__shutdown__", payload={}, priority=EventPriority.P0_EMERGENCY)
            await self.publish(sentinel)
            await self._dispatch_task
            self._dispatch_task = None
        logger.info("bus.stopped", stats=self._stats)

    def subscribe(self, topic_pattern: str, callback: Subscriber) -> None:
        """Subscribe to a topic pattern.

        Supports exact match and prefix glob:
          - "aria.telemetry.anomaly.detected" — exact
          - "aria.telemetry.*" — all telemetry topics
          - "*" — all messages (use sparingly)
        """
        if topic_pattern not in self._subscribers:
            self._subscribers[topic_pattern] = []
        self._subscribers[topic_pattern].append(callback)
        logger.debug("bus.subscribe", pattern=topic_pattern)

    def unsubscribe(self, topic_pattern: str, callback: Subscriber) -> None:
        """Remove a subscription."""
        if topic_pattern in self._subscribers:
            self._subscribers[topic_pattern] = [
                cb for cb in self._subscribers[topic_pattern] if cb is not callback
            ]

    async def publish(self, message: Message) -> None:
        """Publish a message to the bus.

        Messages are priority-queued — P0 emergency messages are dispatched
        before P3 routine even if published later.
        """
        self._stats["total_published"] += 1

        # Store in history (ring buffer)
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Enqueue with priority ordering
        await self._queue.put((message.priority.value, time.monotonic(), message))

    def get_history(
        self,
        topic_filter: str = "",
        limit: int = 100,
    ) -> list[Message]:
        """Retrieve recent messages, optionally filtered by topic."""
        messages = self._history
        if topic_filter:
            messages = [m for m in messages if self._topic_matches(topic_filter, m.topic)]
        return messages[-limit:]

    async def _dispatch_loop(self) -> None:
        """Main dispatch loop — pulls from priority queue and delivers."""
        while self._running:
            try:
                _priority, _ts, message = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            if message.topic == "__shutdown__":
                break

            await self._deliver(message)

    async def _deliver(self, message: Message) -> None:
        """Deliver message to all matching subscribers."""
        delivered = False
        for pattern, callbacks in self._subscribers.items():
            if self._topic_matches(pattern, message.topic):
                for callback in callbacks:
                    try:
                        await callback(message)
                        self._stats["total_delivered"] += 1
                        delivered = True
                    except Exception as exc:
                        logger.error(
                            "bus.delivery_error",
                            topic=message.topic,
                            pattern=pattern,
                            error=str(exc),
                        )

        if not delivered and message.topic != "__shutdown__":
            self._stats["total_dropped"] += 1

    @staticmethod
    def _topic_matches(pattern: str, topic: str) -> bool:
        """Match a topic against a subscription pattern."""
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return topic == prefix or topic.startswith(prefix + ".")
        return pattern == topic


# Convenience: module-level singleton for the main bus
_default_bus: MessageBus | None = None


def get_bus() -> MessageBus:
    """Get or create the default message bus singleton."""
    global _default_bus
    if _default_bus is None:
        _default_bus = MessageBus()
    return _default_bus
