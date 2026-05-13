"""Advanced mission scenarios — stress tests and edge cases.

Scenarios 17-22 covering advanced failure modes and recovery:
  17. Communication blackout — agents operate autonomously
  18. Multi-fault cascade — power + thermal + ECLSS simultaneous
  19. Agent restart recovery — agent crashes and recovers mid-operation
  20. Phase transition under load — phase change while processing data
  21. Scratchpad TTL expiry — stale data is properly discarded
  22. Correlator cooldown — prevents duplicate correlation events
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from aria.agents.comms import CommsAgent
from aria.agents.eclss import EclssAgent
from aria.agents.navigation import NavigationAgent
from aria.agents.power import PowerAgent
from aria.agents.telemetry import TelemetryAgent
from aria.agents.thermal import ThermalAgent
from aria.bus.message_bus import Message, MessageBus
from aria.core.config import AriaConfig
from aria.core.coordinator import AriaCoordinator
from aria.core.tool import ARIATool, ToolResult
from aria.core.types import AuthorityLevel, SafetyLevel, ToolCategory
from aria.integrations.dsremo.correlator import AnomalyCorrelator, AnomalyEvent
from aria.state.scratchpad import SharedScratchpad
from aria.tools.registry import ToolRegistry


class StubIngest(ARIATool):
    name = "dsremo_ingest_telemetry"
    description = "stub"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    def input_schema(self) -> dict[str, Any]: return {"type": "object"}
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"anomaly_score": 0.1})


class StubBatch(ARIATool):
    name = "dsremo_ingest_batch"
    description = "stub"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    def input_schema(self) -> dict[str, Any]: return {"type": "object", "required": ["readings"]}
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        readings = params.get("readings", [])
        return ToolResult(success=True, data={
            "results": [{"channel_id": r["channel_id"], "anomaly_score": 0.1} for r in readings],
            "count": len(readings),
        })


@pytest.fixture
async def bus():
    b = MessageBus(max_history=500)
    await b.start()
    yield b
    await b.stop()


def make_tools():
    reg = ToolRegistry()
    reg.register(StubIngest())
    reg.register(StubBatch())
    return reg


# ---------------------------------------------------------------------------
# Scenario 17: Communication Blackout
# ---------------------------------------------------------------------------

async def test_scenario_comms_blackout(bus: MessageBus):
    """CommsAgent detects blackout, queues messages, recovers on contact."""
    tools = make_tools()
    agent = CommsAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Enter blackout
    await bus.publish(Message(
        topic="aria.sensor.comms.link",
        payload={"signal_dbm": -130.0, "snr_db": 0.5, "ber": 0.1, "data_rate_kbps": 0.0},
    ))
    await asyncio.sleep(0.1)
    assert not agent._link_active

    # Queue messages during blackout
    for i in range(3):
        await bus.publish(Message(
            topic="aria.command.comms.send",
            payload={"message_type": "telemetry", "priority": "NORMAL", "data": f"msg-{i}"},
        ))
    await asyncio.sleep(0.1)
    assert len(agent._outbound_queue) == 3

    # Restore contact
    await bus.publish(Message(
        topic="aria.sensor.comms.link",
        payload={"signal_dbm": -80.0, "snr_db": 18.0, "ber": 1e-9, "data_rate_kbps": 256.0},
    ))
    await asyncio.sleep(0.2)
    assert agent._link_active
    assert len(agent._outbound_queue) == 0  # Flushed
    assert agent._messages_sent == 3

    await agent.stop()


# ---------------------------------------------------------------------------
# Scenario 18: Multi-Fault Cascade
# ---------------------------------------------------------------------------

async def test_scenario_multi_fault_cascade(bus: MessageBus):
    """Multiple subsystems fault simultaneously — system stays alive."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.*", lambda m: alerts.append(m))

    tools = make_tools()
    power = PowerAgent(bus=bus, tool_registry=tools)
    eclss = EclssAgent(bus=bus, tool_registry=tools)
    thermal = ThermalAgent(bus=bus, tool_registry=tools)

    await power.start()
    await eclss.start()
    await thermal.start()

    # Simultaneous faults
    await bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 5.0, "temperature_c": 50.0},
    ))
    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 18.0, "co2_mmhg": 12.0, "humidity_percent": 80.0, "temperature_c": 30.0},
    ))
    await bus.publish(Message(
        topic="aria.sensor.thermal.battery_pack",
        payload={"temperature_c": 55.0},
    ))
    await asyncio.sleep(0.3)

    # Multiple alerts should fire — system should not crash
    critical = [a for a in alerts if a.payload.get("severity") in ("CRITICAL", "EMERGENCY")]
    assert len(critical) >= 3  # At least one from each subsystem

    # All agents still alive
    for agent in [power, eclss, thermal]:
        assert agent.status.name != "ERROR", f"{agent.name} crashed"
        await agent.stop()


# ---------------------------------------------------------------------------
# Scenario 19: Agent Restart Recovery
# ---------------------------------------------------------------------------

async def test_scenario_agent_restart_recovery():
    """Coordinator restarts a failed agent and it resumes processing."""
    config = AriaConfig()
    config.agent.restart_backoff_s = 0.1
    coord = AriaCoordinator(config)
    coord.tools.register(StubIngest())
    coord.tools.register(StubBatch())

    power = PowerAgent(bus=coord.bus, tool_registry=coord.tools)
    coord.register_agent(power)
    await coord.start()

    # Verify agent is running
    assert power.status.name == "READY"

    # Stop agent (simulate crash)
    await power.stop()

    # Coordinator restarts it
    success = await coord.restart_agent("power")
    assert success

    # Agent should be running again
    await asyncio.sleep(0.2)

    await coord.stop()


# ---------------------------------------------------------------------------
# Scenario 20: Phase Transition Under Load
# ---------------------------------------------------------------------------

async def test_scenario_phase_transition_under_load():
    """Phase transition while system is processing sensor data."""
    config = AriaConfig()
    coord = AriaCoordinator(config)
    coord.tools.register(StubIngest())
    coord.tools.register(StubBatch())

    power = PowerAgent(bus=coord.bus, tool_registry=coord.tools)
    coord.register_agent(power)
    await coord.start()

    # Send sensor data
    await coord.bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 85.0, "temperature_c": 22.0},
    ))

    # Transition phase while processing
    success = await coord.transition_phase("ORBIT_TRANSFER")
    assert success
    assert coord.config.mission_phase == "ORBIT_TRANSFER"

    # System should still be running
    assert coord.is_running
    assert power.status.name != "ERROR"

    await coord.stop()


# ---------------------------------------------------------------------------
# Scenario 21: Scratchpad TTL Expiry
# ---------------------------------------------------------------------------

def test_scenario_scratchpad_ttl():
    """Scratchpad entries expire after TTL and are not returned."""
    sp = SharedScratchpad()

    # Write entry with very short TTL
    sp.write("test.ephemeral", {"value": 42}, "test", ttl_s=0.05)
    assert sp.read("test.ephemeral") == {"value": 42}

    # Wait for expiry
    time.sleep(0.06)
    assert sp.read("test.ephemeral") is None
    assert sp.size == 0


# ---------------------------------------------------------------------------
# Scenario 22: Correlator Cooldown
# ---------------------------------------------------------------------------

async def test_scenario_extended_stability_with_faults(bus: MessageBus):
    """Extended run: 9 agents + simulator + fault injection for 5 seconds.

    Verifies system stability under realistic conditions with mid-run faults.
    """
    from aria.agents.comms import CommsAgent
    from aria.agents.medical import MedicalAgent
    from aria.agents.propulsion import PropulsionAgent
    from aria.agents.science import ScienceAgent
    from aria.core.simulator import SensorSimulator, SimulatedSensor
    from aria.state.scratchpad import SharedScratchpad

    sp = SharedScratchpad()
    tools = make_tools()

    agents = [
        TelemetryAgent(bus=bus, tool_registry=tools, scratchpad=sp),
        PowerAgent(bus=bus, tool_registry=tools, scratchpad=sp),
        NavigationAgent(bus=bus, tool_registry=tools, scratchpad=sp),
        EclssAgent(bus=bus, tool_registry=tools, scratchpad=sp),
        ThermalAgent(bus=bus, tool_registry=tools, scratchpad=sp),
        PropulsionAgent(bus=bus, tool_registry=tools, scratchpad=sp),
        CommsAgent(bus=bus, tool_registry=tools, scratchpad=sp),
        ScienceAgent(bus=bus, tool_registry=tools, scratchpad=sp),
        MedicalAgent(bus=bus, tool_registry=tools, scratchpad=sp),
    ]

    sim = SensorSimulator(bus)
    sim.add_default_sensors()

    for a in agents:
        await a.start()
    await sim.start()

    # Normal ops for 2 seconds
    await asyncio.sleep(2.0)

    # Inject fault: thermal spike on battery
    sim.inject_fault("aria.sensor.thermal.battery_pack", "offset", offset=30.0)

    # Continue with fault for 2 more seconds
    await asyncio.sleep(2.0)

    # Clear fault
    sim.clear_fault("aria.sensor.thermal.battery_pack")
    await asyncio.sleep(1.0)

    # All agents should still be alive
    for agent in agents:
        assert agent.status.name not in ("STOPPED", "ERROR"), (
            f"Agent {agent.name} died: {agent.status.name}"
        )

    # Scratchpad should have data from agents
    assert sp.size > 0, "Scratchpad should have cross-agent data"

    await sim.stop()
    for a in agents:
        await a.stop()


async def test_scenario_correlator_cooldown(bus: MessageBus):
    """Correlator doesn't spam with duplicate correlation events."""
    correlations: list[Message] = []
    bus.subscribe("aria.anomaly.correlation", lambda m: correlations.append(m))

    correlator = AnomalyCorrelator(bus, window_s=30.0, min_events=2)
    correlator._correlation_cooldown_s = 1.0  # 1 second cooldown
    await correlator.start()

    t = time.time()

    # First correlation should fire
    correlator._events = [
        AnomalyEvent("eps.battery.temperature_c", "power", "CRITICAL", 0.88, t),
        AnomalyEvent("eps.battery.soc_percent", "power", "WARNING", 0.72, t),
    ]
    await correlator._correlate()
    await asyncio.sleep(0.1)
    assert len(correlations) == 1

    # Second attempt within cooldown should be suppressed
    await correlator._correlate()
    await asyncio.sleep(0.1)
    assert len(correlations) == 1  # Still 1 — cooldown active


async def test_scenario_anomaly_storm_safe_mode():
    """Rapid CRITICAL anomalies trigger anomaly storm detection and safe mode."""
    from aria.core.config import AriaConfig
    from aria.core.coordinator import AriaCoordinator

    safe_mode_events: list[Message] = []

    config = AriaConfig()
    coordinator = AriaCoordinator(config)
    coordinator.tools.register(StubIngest())
    coordinator.tools.register(StubBatch())

    # Lower storm threshold for testing
    coordinator._anomaly_storm_threshold = 3
    coordinator._anomaly_storm_window_s = 60.0

    coordinator.bus.subscribe("aria.safety.mode_change", lambda m: safe_mode_events.append(m))

    await coordinator.start()

    # Simulate rapid CRITICAL anomalies
    for i in range(5):
        await coordinator.bus.publish(Message(
            topic=f"aria.anomaly.test_{i}",
            payload={"severity": "CRITICAL", "message": f"Storm anomaly {i}"},
            source_agent="test",
        ))
    await asyncio.sleep(0.5)

    # Safe mode should have been triggered
    assert len(safe_mode_events) >= 1 or coordinator.safe_mode.current_level.name != "NOMINAL"

    await coordinator.stop()
