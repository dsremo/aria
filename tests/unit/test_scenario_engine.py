"""Tests for the scenario scripting engine."""

from __future__ import annotations

import asyncio

import pytest

from aria.bus.message_bus import Message, MessageBus
from aria.core.scenario_engine import (
    APOLLO_13_SCENARIO,
    NORMAL_ORBIT_SCENARIO,
    SOLAR_STORM_SCENARIO,
    ScenarioEngine,
    ScenarioEvent,
    ScenarioScript,
)
from aria.core.types import EventPriority


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_quick_script(n_events: int = 3, spacing_s: float = 0.1) -> ScenarioScript:
    """Create a small fast script for testing."""
    events = [
        ScenarioEvent(
            time_offset_s=i * spacing_s,
            topic=f"test.event.{i}",
            payload={"index": i},
            description=f"Test event {i}",
        )
        for i in range(n_events)
    ]
    return ScenarioScript(name="quick_test", description="Fast test script", events=events)


class MessageCollector:
    """Subscribes to a bus topic and collects received messages."""

    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def __call__(self, message: Message) -> None:
        self.messages.append(message)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_events_fire_in_order() -> None:
    """All events should be published in time-offset order."""
    bus = MessageBus()
    await bus.start()

    collector = MessageCollector()
    bus.subscribe("test.event.*", collector)

    script = _make_quick_script(n_events=4, spacing_s=0.05)
    engine = ScenarioEngine(bus, script)
    await engine.run(time_scale=100.0)

    # Let the bus dispatch
    await asyncio.sleep(0.15)
    await bus.stop()

    assert len(engine.fired_events) == 4
    offsets = [e.time_offset_s for e in engine.fired_events]
    assert offsets == sorted(offsets), "Events should fire in chronological order"


@pytest.mark.asyncio
async def test_stop_mid_scenario() -> None:
    """Stopping the engine should halt event publishing."""
    bus = MessageBus()
    await bus.start()

    collector = MessageCollector()
    bus.subscribe("test.event.*", collector)

    # Use wider spacing so we can stop in between
    script = _make_quick_script(n_events=10, spacing_s=0.5)
    engine = ScenarioEngine(bus, script)

    async def stop_after_delay() -> None:
        await asyncio.sleep(0.15)
        engine.stop()

    await asyncio.gather(engine.run(time_scale=10.0), stop_after_delay())
    await asyncio.sleep(0.1)
    await bus.stop()

    # Should have fired some events but not all 10
    assert len(engine.fired_events) < 10, "Engine should have been stopped before all events fired"
    assert not engine.is_running


@pytest.mark.asyncio
async def test_progress_tracking() -> None:
    """Progress should go from 0.0 to 1.0 as events fire."""
    bus = MessageBus()
    await bus.start()

    script = _make_quick_script(n_events=4, spacing_s=0.02)
    engine = ScenarioEngine(bus, script)

    assert engine.progress == 0.0

    await engine.run(time_scale=100.0)
    await asyncio.sleep(0.1)
    await bus.stop()

    assert engine.progress == 1.0
    assert len(engine.fired_events) == 4


@pytest.mark.asyncio
async def test_message_payload_contains_scenario_metadata() -> None:
    """Published messages should include scenario metadata in payload."""
    bus = MessageBus()
    await bus.start()

    collector = MessageCollector()
    bus.subscribe("*", collector)

    script = ScenarioScript(
        name="meta_test",
        description="Test metadata injection",
        events=[
            ScenarioEvent(
                time_offset_s=0,
                topic="test.meta",
                payload={"key": "value"},
                description="Metadata event",
            )
        ],
    )
    engine = ScenarioEngine(bus, script)
    await engine.run(time_scale=100.0)
    await asyncio.sleep(0.15)
    await bus.stop()

    assert len(collector.messages) >= 1
    msg = collector.messages[0]
    assert msg.payload["_scenario"] == "meta_test"
    assert msg.payload["_description"] == "Metadata event"
    assert msg.payload["_time_offset_s"] == 0
    assert msg.payload["key"] == "value"
    assert msg.source_agent == "scenario_engine"


@pytest.mark.asyncio
async def test_invalid_time_scale_raises() -> None:
    """time_scale <= 0 should raise ValueError."""
    bus = MessageBus()
    script = _make_quick_script()
    engine = ScenarioEngine(bus, script)

    with pytest.raises(ValueError, match="time_scale must be positive"):
        await engine.run(time_scale=0.0)

    with pytest.raises(ValueError, match="time_scale must be positive"):
        await engine.run(time_scale=-1.0)


@pytest.mark.asyncio
async def test_empty_script_completes_immediately() -> None:
    """A script with no events should complete instantly."""
    bus = MessageBus()
    script = ScenarioScript(name="empty", description="No events", events=[])
    engine = ScenarioEngine(bus, script)

    await engine.run(time_scale=1.0)

    assert engine.progress == 1.0
    assert len(engine.fired_events) == 0
    assert not engine.is_running


def test_prebuilt_scenarios_are_valid() -> None:
    """All pre-built scenarios should have events and valid durations."""
    for scenario in (APOLLO_13_SCENARIO, SOLAR_STORM_SCENARIO, NORMAL_ORBIT_SCENARIO):
        assert scenario.name, "Scenario must have a name"
        assert scenario.description, "Scenario must have a description"
        assert len(scenario.events) >= 3, f"{scenario.name} should have at least 3 events"
        assert scenario.total_duration_s > 0, f"{scenario.name} must have positive duration"

        # Events should have valid time offsets
        for event in scenario.events:
            assert event.time_offset_s >= 0
            assert event.topic
            assert isinstance(event.payload, dict)
