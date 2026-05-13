"""Tests for conflict resolution between agents."""

from __future__ import annotations

import asyncio

import pytest

from aria.bus.message_bus import Message, MessageBus
from aria.core.conflict import ConflictRequest, ConflictResolver


@pytest.fixture
async def bus():
    b = MessageBus(max_history=100)
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def resolver(bus: MessageBus) -> ConflictResolver:
    return ConflictResolver(bus)


async def test_safety_wins_over_science(resolver: ConflictResolver):
    """Crew safety priority beats science priority."""
    result = await resolver.resolve(
        ConflictRequest(agent_name="eclss", action="increase_o2", priority="crew_safety"),
        ConflictRequest(agent_name="science", action="keep_instruments_on", priority="science"),
    )
    assert result.winner is not None
    assert result.winner.agent_name == "eclss"
    assert not result.compromise
    assert not result.escalated


async def test_spacecraft_safety_wins_over_mission(resolver: ConflictResolver):
    """Spacecraft safety beats mission-nominal."""
    result = await resolver.resolve(
        ConflictRequest(agent_name="power", action="shed_loads", priority="spacecraft_safety"),
        ConflictRequest(agent_name="comms", action="keep_hga_on", priority="mission_nominal"),
    )
    assert result.winner.agent_name == "power"


async def test_same_priority_finds_compromise(resolver: ConflictResolver):
    """Same priority with known resource type finds compromise."""
    result = await resolver.resolve(
        ConflictRequest(agent_name="power", action="shed_science", resource="power_budget"),
        ConflictRequest(agent_name="thermal", action="keep_heaters", resource="power_budget"),
    )
    assert result.compromise
    assert "partial_reduction" in result.compromise_plan.get("action", "")


async def test_same_priority_attitude_compromise(resolver: ConflictResolver):
    """Attitude conflict finds time-share compromise."""
    result = await resolver.resolve(
        ConflictRequest(agent_name="science", action="point_at_target", resource="attitude", priority="science"),
        ConflictRequest(agent_name="comms", action="point_at_ground", resource="attitude", priority="science"),
    )
    assert result.compromise
    assert "time_share" in result.compromise_plan.get("action", "")


async def test_escalation_when_no_compromise(resolver: ConflictResolver, bus: MessageBus):
    """Unknown resource type escalates to captain."""
    escalations: list[Message] = []
    bus.subscribe("aria.captain.alert", lambda m: escalations.append(m))

    result = await resolver.resolve(
        ConflictRequest(agent_name="propulsion", action="fire_thruster", priority="mission_critical", resource="unknown"),
        ConflictRequest(agent_name="navigation", action="maintain_attitude", priority="mission_critical", resource="unknown"),
    )
    await asyncio.sleep(0.1)

    assert result.escalated
    assert not result.compromise
    assert len(escalations) >= 1
    assert escalations[0].payload["type"] == "conflict_escalation"


async def test_default_priority_from_subsystem(resolver: ConflictResolver):
    """Agent gets default priority based on subsystem name."""
    result = await resolver.resolve(
        ConflictRequest(agent_name="medical", action="shelter_crew"),  # default: crew_safety
        ConflictRequest(agent_name="science", action="continue_obs"),  # default: science
    )
    assert result.winner.agent_name == "medical"


async def test_conflict_history_tracked(resolver: ConflictResolver):
    """Conflict history is maintained."""
    await resolver.resolve(
        ConflictRequest(agent_name="power", action="shed", priority="spacecraft_safety"),
        ConflictRequest(agent_name="science", action="keep", priority="science"),
    )
    assert len(resolver.history) == 1
    assert resolver.history[0]["agent_a"] == "power"


async def test_downlink_bandwidth_compromise(resolver: ConflictResolver):
    """Downlink bandwidth conflict finds interleave compromise."""
    result = await resolver.resolve(
        ConflictRequest(agent_name="telemetry", action="downlink_anomalies", resource="downlink_bandwidth", priority="mission_nominal"),
        ConflictRequest(agent_name="science", action="downlink_science_data", resource="downlink_bandwidth", priority="mission_nominal"),
    )
    assert result.compromise
    assert "interleave" in result.compromise_plan.get("action", "")


async def test_history_limit(resolver: ConflictResolver):
    """Conflict history doesn't grow unbounded."""
    for i in range(250):
        await resolver.resolve(
            ConflictRequest(agent_name="a", action=f"act_{i}", priority="science"),
            ConflictRequest(agent_name="b", action=f"act_{i}", priority="comfort"),
        )
    assert len(resolver.history) <= 200


async def test_medical_always_wins_over_comfort(resolver: ConflictResolver):
    """Medical (crew_safety) always wins over comfort."""
    result = await resolver.resolve(
        ConflictRequest(agent_name="medical", action="shelter_crew", priority="crew_safety"),
        ConflictRequest(agent_name="science", action="continue_experiment", priority="comfort"),
    )
    assert result.winner.agent_name == "medical"


async def test_both_crew_safety_escalates(resolver: ConflictResolver, bus: MessageBus):
    """Two crew_safety conflicts with unknown resource escalate."""
    escalations: list[Message] = []
    bus.subscribe("aria.captain.alert", lambda m: escalations.append(m))

    result = await resolver.resolve(
        ConflictRequest(agent_name="medical", action="treat_crew", priority="crew_safety", resource="unknown"),
        ConflictRequest(agent_name="eclss", action="isolate_zone", priority="crew_safety", resource="unknown"),
    )
    await asyncio.sleep(0.1)

    assert result.escalated
