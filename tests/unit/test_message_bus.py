"""Tests for the ARIA message bus."""

import asyncio

import pytest

from aria.bus.message_bus import Message, MessageBus
from aria.core.types import EventPriority


@pytest.fixture
async def bus():
    b = MessageBus(max_history=100)
    await b.start()
    yield b
    await b.stop()


async def test_publish_and_subscribe(bus: MessageBus):
    """Messages published to a topic are delivered to subscribers."""
    received: list[Message] = []

    async def handler(msg: Message):
        received.append(msg)

    bus.subscribe("test.topic", handler)
    await bus.publish(Message(topic="test.topic", payload={"value": 42}))
    await asyncio.sleep(0.1)

    assert len(received) == 1
    assert received[0].payload["value"] == 42


async def test_wildcard_subscription(bus: MessageBus):
    """Wildcard subscriptions match topic prefixes."""
    received: list[Message] = []

    async def handler(msg: Message):
        received.append(msg)

    bus.subscribe("aria.telemetry.*", handler)

    await bus.publish(Message(topic="aria.telemetry.anomaly.detected", payload={}))
    await bus.publish(Message(topic="aria.telemetry.ingest", payload={}))
    await bus.publish(Message(topic="aria.navigation.update", payload={}))  # Should NOT match
    await asyncio.sleep(0.1)

    assert len(received) == 2


async def test_priority_ordering(bus: MessageBus):
    """Higher priority messages are delivered before lower priority."""
    received: list[EventPriority] = []

    async def handler(msg: Message):
        received.append(msg.priority)

    bus.subscribe("*", handler)

    # Stop the bus dispatch loop so we can queue messages
    bus._running = False
    await asyncio.sleep(0.05)

    # Queue messages in reverse priority order
    for priority in [EventPriority.P4_BULK, EventPriority.P1_CRITICAL, EventPriority.P0_EMERGENCY]:
        await bus._queue.put((priority.value, 0, Message(topic="test", payload={}, priority=priority)))

    # Restart dispatch
    bus._running = True
    bus._dispatch_task = asyncio.create_task(bus._dispatch_loop())
    await asyncio.sleep(0.1)

    # P0 should arrive first, then P1, then P4
    assert received[0] == EventPriority.P0_EMERGENCY
    assert received[1] == EventPriority.P1_CRITICAL
    assert received[2] == EventPriority.P4_BULK


async def test_message_history(bus: MessageBus):
    """Published messages are stored in history."""
    for i in range(5):
        await bus.publish(Message(topic=f"test.{i}", payload={"i": i}))
    await asyncio.sleep(0.1)

    history = bus.get_history(limit=10)
    assert len(history) == 5


async def test_no_subscriber_increments_dropped(bus: MessageBus):
    """Messages with no subscribers are counted as dropped."""
    await bus.publish(Message(topic="unsubscribed.topic", payload={}))
    await asyncio.sleep(0.1)

    assert bus.stats["total_dropped"] >= 1


async def test_unsubscribe(bus: MessageBus):
    """Unsubscribed callbacks stop receiving messages."""
    received: list[Message] = []

    async def handler(msg: Message):
        received.append(msg)

    bus.subscribe("test.topic", handler)
    await bus.publish(Message(topic="test.topic", payload={}))
    await asyncio.sleep(0.1)
    assert len(received) == 1

    bus.unsubscribe("test.topic", handler)
    await bus.publish(Message(topic="test.topic", payload={}))
    await asyncio.sleep(0.1)
    assert len(received) == 1  # No new message


async def test_stats_tracking(bus: MessageBus):
    """Bus stats are correctly tracked."""
    for i in range(10):
        await bus.publish(Message(topic=f"test.stats.{i}", payload={"i": i}))
    await asyncio.sleep(0.1)
    stats = bus.stats
    assert stats["total_published"] >= 10


async def test_history_topic_filter(bus: MessageBus):
    """History filtering by topic works."""
    await bus.publish(Message(topic="test.a", payload={}))
    await bus.publish(Message(topic="test.b", payload={}))
    await bus.publish(Message(topic="test.a", payload={}))
    await asyncio.sleep(0.1)

    a_msgs = bus.get_history(topic_filter="test.a")
    assert len(a_msgs) == 2
