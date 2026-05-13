"""Integration tests for multi-agent ARIA system."""

import asyncio
from typing import Any

import pytest

from aria.agents.base import SubsystemAgent
from aria.agents.navigation import NavigationAgent
from aria.agents.power import PowerAgent
from aria.agents.telemetry import TelemetryAgent
from aria.bus.message_bus import Message, MessageBus
from aria.core.coordinator import AriaCoordinator
from aria.core.config import AriaConfig
from aria.core.tool import ARIATool, ToolResult
from aria.core.types import AuthorityLevel, EventPriority, SafetyLevel, Severity, ToolCategory
from aria.tools.registry import ToolRegistry


class MockDsremoIngest(ARIATool):
    """Mock Dsremo single-reading ingest (fallback path)."""

    name = "dsremo_ingest_telemetry"
    description = "Mock Dsremo ingest"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def __init__(self, anomaly_score: float = 0.0) -> None:
        super().__init__()
        self.anomaly_score = anomaly_score
        self.call_count = 0

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        self.call_count += 1
        return ToolResult(
            success=True,
            data={"anomaly_score": self.anomaly_score, "detectors_triggered": ["CUSUM", "EWMA"]},
        )


class MockDsremoBatch(ARIATool):
    """Mock Dsremo batch ingest — returns per-channel scores."""

    name = "dsremo_ingest_batch"
    description = "Mock Dsremo batch ingest"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def __init__(self, anomaly_score: float = 0.0) -> None:
        super().__init__()
        self.anomaly_score = anomaly_score
        self.batch_count = 0

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "required": ["readings"], "properties": {"readings": {}}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        self.batch_count += 1
        readings = params.get("readings", [])
        results = [
            {
                "channel_id": r["channel_id"],
                "anomaly_score": self.anomaly_score,
                "detectors_triggered": ["CUSUM", "EWMA"],
            }
            for r in readings
        ]
        return ToolResult(
            success=True,
            data={"results": results, "count": len(readings)},
        )


@pytest.fixture
async def bus():
    b = MessageBus(max_history=100)
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def tools():
    return ToolRegistry()


async def test_telemetry_agent_processes_sensor_data(bus: MessageBus, tools: ToolRegistry):
    """TelemetryAgent forwards sensor data to Dsremo via batch ingest."""
    mock_batch = MockDsremoBatch(anomaly_score=0.0)
    tools.register(MockDsremoIngest(anomaly_score=0.0))
    tools.register(mock_batch)

    agent = TelemetryAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Send a power battery sensor reading (new universal topic format)
    await bus.publish(
        Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 85.0, "temperature_c": 25.0},
        )
    )
    await asyncio.sleep(0.8)  # Wait for batch flush

    assert mock_batch.batch_count >= 1
    await agent.stop()


async def test_telemetry_agent_publishes_anomaly_on_high_score(bus: MessageBus, tools: ToolRegistry):
    """When Dsremo returns high anomaly score, TelemetryAgent publishes anomaly event."""
    mock_batch = MockDsremoBatch(anomaly_score=0.87)  # CRITICAL level
    tools.register(MockDsremoIngest(anomaly_score=0.87))
    tools.register(mock_batch)

    anomaly_events: list[Message] = []

    async def capture_anomaly(msg: Message) -> None:
        anomaly_events.append(msg)

    bus.subscribe("aria.anomaly.detected", capture_anomaly)

    agent = TelemetryAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(
        Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 5.0, "temperature_c": 25.0},
        )
    )
    await asyncio.sleep(1.0)  # Wait for batch flush + delivery

    assert len(anomaly_events) >= 1
    assert anomaly_events[0].payload["severity"] == "CRITICAL"
    assert anomaly_events[0].payload["anomaly_score"] == 0.87
    await agent.stop()


async def test_power_agent_detects_low_battery(bus: MessageBus, tools: ToolRegistry):
    """PowerAgent raises WARNING on low battery SoC."""
    alerts: list[Message] = []

    async def capture(msg: Message) -> None:
        alerts.append(msg)

    bus.subscribe("aria.anomaly.power", capture)

    agent = PowerAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Send low battery reading
    await bus.publish(
        Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 15.0, "temperature_c": 25.0},
        )
    )
    await asyncio.sleep(0.2)

    assert len(alerts) >= 1
    assert alerts[0].payload["severity"] == "WARNING"
    assert "low" in alerts[0].payload["message"].lower()
    await agent.stop()


async def test_power_agent_triggers_load_shed_on_critical_soc(bus: MessageBus, tools: ToolRegistry):
    """PowerAgent executes load shed when battery is critically low."""
    shed_events: list[Message] = []

    async def capture(msg: Message) -> None:
        shed_events.append(msg)

    bus.subscribe("aria.power.load_shed.executed", capture)

    agent = PowerAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Send critical battery reading
    await bus.publish(
        Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 8.0, "temperature_c": 25.0},
        )
    )
    await asyncio.sleep(0.3)

    assert len(shed_events) >= 1
    assert "experiments" in shed_events[0].payload["shed_loads"]
    await agent.stop()


async def test_navigation_agent_detects_tumble(bus: MessageBus, tools: ToolRegistry):
    """NavigationAgent raises CRITICAL on high angular rates."""
    alerts: list[Message] = []

    async def capture(msg: Message) -> None:
        alerts.append(msg)

    bus.subscribe("aria.anomaly.navigation", capture)

    agent = NavigationAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Send tumbling IMU data
    await bus.publish(
        Message(
            topic="aria.sensor.nav.imu",
            payload={"angular_rate_x_dps": 8.0, "angular_rate_y_dps": 3.0, "angular_rate_z_dps": 2.0},
        )
    )
    await asyncio.sleep(0.2)

    assert len(alerts) >= 1
    assert alerts[0].payload["severity"] == "CRITICAL"
    assert "tumble" in alerts[0].payload["message"].lower()
    await agent.stop()


async def test_coordinator_starts_and_stops_agents():
    """AriaCoordinator manages agent lifecycle."""
    config = AriaConfig()
    coordinator = AriaCoordinator(config)

    # Register mock tools
    coordinator.tools.register(MockDsremoIngest())
    coordinator.tools.register(MockDsremoBatch())

    # Register agents
    telemetry = TelemetryAgent(bus=coordinator.bus, tool_registry=coordinator.tools)
    power = PowerAgent(bus=coordinator.bus, tool_registry=coordinator.tools)
    coordinator.register_agent(telemetry)
    coordinator.register_agent(power)

    assert coordinator.agent_count == 2

    await coordinator.start()
    assert coordinator.is_running

    status = coordinator.system_status()
    assert status["status"] == "RUNNING"
    assert len(status["agents"]) == 2

    await coordinator.stop()
    assert not coordinator.is_running


async def test_anomaly_escalates_to_captain(bus: MessageBus, tools: ToolRegistry):
    """Anomaly events with WARNING+ severity reach the captain alert topic."""
    captain_alerts: list[Message] = []

    async def capture(msg: Message) -> None:
        captain_alerts.append(msg)

    config = AriaConfig()
    coordinator = AriaCoordinator(config)
    coordinator.tools.register(MockDsremoIngest(anomaly_score=0.70))
    coordinator.tools.register(MockDsremoBatch(anomaly_score=0.70))  # WARNING level

    telemetry = TelemetryAgent(bus=coordinator.bus, tool_registry=coordinator.tools)
    coordinator.register_agent(telemetry)

    coordinator.bus.subscribe("aria.captain.alert", capture)

    await coordinator.start()

    # Inject telemetry that triggers WARNING via batch Dsremo scoring
    await coordinator.bus.publish(
        Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 50.0, "temperature_c": 22.0},
        )
    )
    await asyncio.sleep(1.0)  # Wait for batch flush + escalation

    # The coordinator should have escalated the anomaly to captain
    assert len(captain_alerts) >= 1

    await coordinator.stop()


async def test_correlation_escalates_to_captain():
    """High-confidence root cause correlation escalates to captain alert."""
    captain_alerts: list[Message] = []

    async def capture(msg: Message) -> None:
        captain_alerts.append(msg)

    config = AriaConfig()
    coordinator = AriaCoordinator(config)
    coordinator.tools.register(MockDsremoIngest())
    coordinator.tools.register(MockDsremoBatch())

    coordinator.bus.subscribe("aria.captain.alert", capture)

    await coordinator.start()

    # Simulate a correlation event (normally from AnomalyCorrelator)
    await coordinator.bus.publish(
        Message(
            topic="aria.anomaly.correlation",
            payload={
                "root_cause": "BATTERY_THERMAL_RUNAWAY",
                "confidence": 0.85,
                "severity": "CRITICAL",
                "description": "Battery thermal runaway precursor detected",
                "recommendation": "Execute emergency battery disconnect",
                "involved_channels": ["eps.battery.temperature_c", "eps.battery.soc_percent"],
            },
            source_agent="anomaly_correlator",
        )
    )
    await asyncio.sleep(0.3)

    # Coordinator should have escalated to captain
    root_cause_alerts = [
        a for a in captain_alerts
        if a.payload.get("type") == "root_cause_correlation"
    ]
    assert len(root_cause_alerts) >= 1
    assert "BATTERY_THERMAL_RUNAWAY" in root_cause_alerts[0].payload["message"]
    assert root_cause_alerts[0].payload["severity"] == "CRITICAL"

    await coordinator.stop()


async def test_low_confidence_correlation_not_escalated():
    """Low-confidence correlations (<0.80) don't escalate to captain."""
    captain_alerts: list[Message] = []

    async def capture(msg: Message) -> None:
        captain_alerts.append(msg)

    config = AriaConfig()
    coordinator = AriaCoordinator(config)
    coordinator.tools.register(MockDsremoIngest())
    coordinator.tools.register(MockDsremoBatch())

    coordinator.bus.subscribe("aria.captain.alert", capture)

    await coordinator.start()

    await coordinator.bus.publish(
        Message(
            topic="aria.anomaly.correlation",
            payload={
                "root_cause": "ECLIPSE_INDUCED_POWER_DROP",
                "confidence": 0.65,  # Below 0.80 threshold
                "severity": "WATCH",
                "description": "Normal eclipse pattern",
                "recommendation": "Monitor",
                "involved_channels": ["eps.solar.power_watts"],
            },
            source_agent="anomaly_correlator",
        )
    )
    await asyncio.sleep(0.3)

    # No root_cause_correlation alerts should appear
    root_cause_alerts = [
        a for a in captain_alerts
        if a.payload.get("type") == "root_cause_correlation"
    ]
    assert len(root_cause_alerts) == 0

    await coordinator.stop()
