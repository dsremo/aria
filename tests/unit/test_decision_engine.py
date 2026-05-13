"""Tests for ARIA Decision Engine.

Tests:
  1. NOMINAL decisions auto-execute without captain
  2. WATCH decisions execute and notify captain
  3. EMERGENCY decisions execute immediately
  4. WARNING decisions wait for captain approval (with timeout fallback)
  5. Captain approve/reject flow
  6. Decision history tracking
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from aria.bus.message_bus import Message, MessageBus
from aria.core.decision_engine import Decision, DecisionEngine
from aria.core.types import Severity


@pytest.fixture
async def bus():
    b = MessageBus(max_history=100)
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def engine(bus: MessageBus) -> DecisionEngine:
    de = DecisionEngine(bus)
    # Shorten timeouts for testing
    de._timeouts = {
        Severity.WATCH: 0,
        Severity.WARNING: 1,   # 1s instead of 30s
        Severity.CRITICAL: 2,  # 2s instead of 60s
        Severity.EMERGENCY: 0.5,
    }
    return de


async def test_nominal_auto_executes(engine: DecisionEngine):
    """NOMINAL decisions auto-execute without captain involvement."""
    decision = Decision(
        category="routine_log",
        severity=Severity.NOMINAL,
        description="Routine telemetry log rotation",
    )
    result = await engine.submit_decision(decision)
    assert result.outcome == "executed"
    assert not result.captain_involved


async def test_watch_executes_and_notifies(engine: DecisionEngine, bus: MessageBus):
    """WATCH decisions execute and send info to captain."""
    alerts: list[Message] = []
    bus.subscribe("aria.captain.alert", lambda m: alerts.append(m))

    decision = Decision(
        category="minor_adjustment",
        severity=Severity.WATCH,
        description="Adjusting heater setpoint by 0.5C",
    )
    result = await engine.submit_decision(decision)
    await asyncio.sleep(0.1)

    assert result.outcome == "executed"
    assert len(alerts) >= 1
    assert alerts[0].payload["type"] == "info"


async def test_emergency_acts_immediately(engine: DecisionEngine, bus: MessageBus):
    """EMERGENCY decisions execute immediately without waiting."""
    alerts: list[Message] = []
    bus.subscribe("aria.captain.alert", lambda m: alerts.append(m))

    decision = Decision(
        category="emergency_response",
        severity=Severity.EMERGENCY,
        description="Battery disconnect — thermal runaway detected",
    )
    result = await engine.submit_decision(decision)
    await asyncio.sleep(0.1)

    assert result.outcome == "executed"
    assert result.captain_involved
    assert result.captain_approved is None  # Didn't wait for approval
    assert len(alerts) >= 1


async def test_warning_times_out_and_executes(engine: DecisionEngine, bus: MessageBus):
    """WARNING decisions timeout when captain doesn't respond, then AI acts."""
    decision = Decision(
        category="load_adjustment",
        severity=Severity.WARNING,
        description="Recommend reducing experiment power by 20%",
    )
    result = await engine.submit_decision(decision)

    # Should have timed out after 1s and executed
    assert result.outcome == "executed"
    assert result.captain_involved
    assert result.captain_approved is None
    assert "timeout" in result.reasoning.lower()


async def test_captain_approves_decision(engine: DecisionEngine, bus: MessageBus):
    """Captain approves a WARNING decision before timeout."""
    # Start decision in background
    async def approve_after_delay():
        await asyncio.sleep(0.2)
        await bus.publish(Message(
            topic="aria.captain.response",
            payload={"decision_id": decision.decision_id, "approved": True},
        ))

    decision = Decision(
        category="maneuver",
        severity=Severity.WARNING,
        description="Execute collision avoidance burn: delta-v 0.3 m/s",
    )
    asyncio.create_task(approve_after_delay())
    result = await engine.submit_decision(decision)

    assert result.outcome == "executed"
    assert result.captain_approved is True


async def test_captain_rejects_decision(engine: DecisionEngine, bus: MessageBus):
    """Captain rejects a decision — outcome is cancelled."""
    async def reject_after_delay():
        await asyncio.sleep(0.2)
        await bus.publish(Message(
            topic="aria.captain.response",
            payload={"decision_id": decision.decision_id, "approved": False},
        ))

    decision = Decision(
        category="maneuver",
        severity=Severity.WARNING,
        description="Execute orbit raise maneuver",
    )
    asyncio.create_task(reject_after_delay())
    result = await engine.submit_decision(decision)

    assert result.outcome == "cancelled"
    assert result.captain_approved is False


async def test_captain_overrides_option(engine: DecisionEngine, bus: MessageBus):
    """Captain overrides with a different option."""
    async def override_after_delay():
        await asyncio.sleep(0.2)
        await bus.publish(Message(
            topic="aria.captain.response",
            payload={
                "decision_id": decision.decision_id,
                "approved": False,
                "override_option": "reduce_by_10_percent",
            },
        ))

    decision = Decision(
        category="load_shed",
        severity=Severity.WARNING,
        description="Load shed recommendation: cut experiments",
        chosen_option="cut_experiments",
        options=[
            {"id": "cut_experiments", "desc": "Full experiment shutdown"},
            {"id": "reduce_by_10_percent", "desc": "Reduce by 10%"},
        ],
    )
    asyncio.create_task(override_after_delay())
    result = await engine.submit_decision(decision)

    assert result.outcome == "overridden"
    assert result.chosen_option == "reduce_by_10_percent"


async def test_decision_history(engine: DecisionEngine):
    """Decision history is tracked."""
    for i in range(5):
        await engine.submit_decision(Decision(
            category=f"test_{i}",
            severity=Severity.NOMINAL,
            description=f"Test decision {i}",
        ))

    history = engine.get_history(limit=10)
    assert len(history) == 5
    assert all(d.outcome == "executed" for d in history)


async def test_pending_decisions(engine: DecisionEngine, bus: MessageBus):
    """Pending decisions are tracked while awaiting captain response."""
    # Start a WARNING decision in background (will wait for timeout)
    decision = Decision(
        category="test_pending",
        severity=Severity.WARNING,
        description="Pending test",
    )

    task = asyncio.create_task(engine.submit_decision(decision))
    await asyncio.sleep(0.1)

    pending = engine.get_pending()
    assert len(pending) == 1
    assert pending[0].decision_id == decision.decision_id

    # Let it timeout
    await task
    assert len(engine.get_pending()) == 0


async def test_critical_decision_timeout(engine: DecisionEngine, bus: MessageBus):
    """CRITICAL decisions also timeout and execute."""
    decision = Decision(
        category="emergency_response",
        severity=Severity.CRITICAL,
        description="Isolate damaged module",
    )
    result = await engine.submit_decision(decision)
    assert result.outcome == "executed"
    assert result.captain_involved
    assert "timeout" in result.reasoning.lower()


async def test_multiple_concurrent_decisions(engine: DecisionEngine, bus: MessageBus):
    """Multiple decisions can be pending simultaneously."""
    import asyncio

    decisions = [
        Decision(category=f"test_{i}", severity=Severity.WARNING, description=f"Decision {i}")
        for i in range(3)
    ]

    tasks = [asyncio.create_task(engine.submit_decision(d)) for d in decisions]
    results = await asyncio.gather(*tasks)

    assert all(r.outcome == "executed" for r in results)
    assert len(engine.get_history()) >= 3


async def test_emergency_decision_fast(engine: DecisionEngine, bus: MessageBus):
    """EMERGENCY decisions execute in under 1 second."""
    import time
    decision = Decision(
        category="fire_response",
        severity=Severity.EMERGENCY,
        description="Activate fire suppression",
    )
    start = time.perf_counter()
    result = await engine.submit_decision(decision)
    elapsed = time.perf_counter() - start

    assert result.outcome == "executed"
    assert elapsed < 1.0


async def test_nominal_no_captain(engine: DecisionEngine, bus: MessageBus):
    """NOMINAL decisions don't involve captain at all."""
    decision = Decision(severity=Severity.NOMINAL, description="Log rotation")
    result = await engine.submit_decision(decision)
    assert not result.captain_involved
    assert result.captain_approved is None
