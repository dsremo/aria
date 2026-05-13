"""Tests for EventLogger audit trail."""

from __future__ import annotations

import asyncio

import pytest

from aria.bus.message_bus import Message, MessageBus
from aria.metrics.event_log import EventLogger


@pytest.fixture
async def bus():
    b = MessageBus(max_history=100)
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
async def event_log(bus: MessageBus) -> EventLogger:
    el = EventLogger(bus)
    await el.start()
    return el


async def test_logs_anomaly_events(event_log: EventLogger, bus: MessageBus):
    """Anomaly events are captured in the audit log."""
    await bus.publish(Message(
        topic="aria.anomaly.power",
        payload={"severity": "WARNING", "message": "Battery low"},
        source_agent="power",
    ))
    await asyncio.sleep(0.1)

    assert event_log.event_count >= 1
    events = event_log.query(category="ANOMALY")
    assert len(events) >= 1
    assert events[0].severity == "WARNING"


async def test_logs_captain_alerts(event_log: EventLogger, bus: MessageBus):
    """Captain alerts are logged."""
    await bus.publish(Message(
        topic="aria.captain.alert",
        payload={"severity": "CRITICAL", "message": "CO2 high", "source": "coordinator"},
    ))
    await asyncio.sleep(0.1)

    events = event_log.query(category="ALERT")
    assert len(events) >= 1
    assert events[0].severity == "CRITICAL"


async def test_logs_fdir_response(event_log: EventLogger, bus: MessageBus):
    """FDIR responses are logged."""
    await bus.publish(Message(
        topic="aria.fdir.response",
        payload={"fault_type": "BATTERY_THERMAL_RUNAWAY", "severity": "CRITICAL", "actions": ["disconnect"]},
    ))
    await asyncio.sleep(0.1)

    events = event_log.query(category="FDIR")
    assert len(events) >= 1
    assert "BATTERY_THERMAL_RUNAWAY" in events[0].summary


async def test_logs_emergency_events(event_log: EventLogger, bus: MessageBus):
    """Emergency events are logged as ALERT/EMERGENCY."""
    await bus.publish(Message(
        topic="aria.emergency.fire.response",
        payload={"zone": "lab", "actions": ["suppress"]},
        source_agent="eclss",
    ))
    await asyncio.sleep(0.1)

    events = event_log.query(severity="EMERGENCY")
    assert len(events) >= 1


async def test_manual_log(event_log: EventLogger):
    """Manual log entries work."""
    event_log.log(
        category="SECURITY",
        severity="WARNING",
        source="api_server",
        summary="Unauthorized access attempt",
        payload={"ip": "192.168.1.100"},
    )
    events = event_log.query(category="SECURITY")
    assert len(events) == 1
    assert events[0].source == "api_server"


async def test_query_filters(event_log: EventLogger, bus: MessageBus):
    """Query filters work correctly."""
    await bus.publish(Message(topic="aria.anomaly.power", payload={"severity": "WARNING", "message": "a"}, source_agent="power"))
    await bus.publish(Message(topic="aria.anomaly.eclss", payload={"severity": "CRITICAL", "message": "b"}, source_agent="eclss"))
    await asyncio.sleep(0.1)

    all_events = event_log.query()
    assert len(all_events) >= 2

    warnings = event_log.query(severity="WARNING")
    critical = event_log.query(severity="CRITICAL")
    assert len(warnings) >= 1
    assert len(critical) >= 1


async def test_summary_statistics(event_log: EventLogger, bus: MessageBus):
    """Summary returns correct counts."""
    for i in range(5):
        await bus.publish(Message(topic="aria.anomaly.test", payload={"severity": "WATCH", "message": f"test-{i}"}, source_agent="test"))
    await asyncio.sleep(0.1)

    summary = event_log.summary()
    assert summary["total_events"] >= 5
    assert summary["by_category"].get("ANOMALY", 0) >= 5


async def test_ring_buffer_limit():
    """EventLogger respects max_events limit."""
    bus = MessageBus(max_history=10)
    await bus.start()
    el = EventLogger(bus, max_events=5)

    for i in range(10):
        el.log("TEST", "INFO", "test", f"event-{i}")

    assert el.event_count == 5
    events = el.query()
    assert events[0].summary == "event-5"  # Oldest kept
    assert events[-1].summary == "event-9"  # Most recent

    await bus.stop()


async def test_query_by_source(event_log: EventLogger, bus: MessageBus):
    """Filter events by source agent."""
    event_log.log("ANOMALY", "WARNING", "power", "Power alert")
    event_log.log("ANOMALY", "WARNING", "thermal", "Thermal alert")
    event_log.log("ANOMALY", "CRITICAL", "power", "Power critical")

    power_events = event_log.query(source="power")
    assert len(power_events) == 2
    assert all(e.source == "power" for e in power_events)


async def test_query_limit(event_log: EventLogger, bus: MessageBus):
    """Query respects limit parameter."""
    for i in range(20):
        event_log.log("TEST", "INFO", "test", f"event-{i}")

    limited = event_log.query(limit=5)
    assert len(limited) == 5


async def test_counts_by_category(event_log: EventLogger, bus: MessageBus):
    """Category counts are tracked correctly."""
    event_log.log("ANOMALY", "WARNING", "a", "x")
    event_log.log("ANOMALY", "WARNING", "b", "y")
    event_log.log("FDIR", "CRITICAL", "c", "z")

    counts = event_log.counts_by_category
    assert counts.get("ANOMALY", 0) >= 2
    assert counts.get("FDIR", 0) >= 1


async def test_correlation_event_logged(event_log: EventLogger, bus: MessageBus):
    """Correlation events get special formatting."""
    await bus.publish(Message(
        topic="aria.anomaly.correlation",
        payload={
            "root_cause": "BATTERY_THERMAL_RUNAWAY",
            "confidence": 0.92,
            "severity": "CRITICAL",
        },
    ))
    await asyncio.sleep(0.1)

    events = event_log.query(category="ANOMALY")
    assert any("root cause" in e.summary.lower() for e in events)


async def test_maneuver_event_logged(event_log: EventLogger, bus: MessageBus):
    """Maneuver start/complete events are logged."""
    await bus.publish(Message(
        topic="aria.propulsion.maneuver.started",
        payload={"maneuver_id": "CAM-001"},
    ))
    await asyncio.sleep(0.1)

    events = event_log.query(category="DECISION")
    assert any("started" in e.summary.lower() for e in events)


async def test_safe_mode_change_logged(event_log: EventLogger, bus: MessageBus):
    """Safe mode changes are logged as STATE events."""
    await bus.publish(Message(
        topic="aria.safety.mode_change",
        payload={"from_level": "NOMINAL", "to_level": "REDUCED"},
    ))
    await asyncio.sleep(0.1)

    events = event_log.query(category="STATE")
    assert any("safe mode" in e.summary.lower() for e in events)
