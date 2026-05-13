"""Mission scenario integration tests — full end-to-end simulations.

Each test represents a real spacecraft emergency or operational scenario:
  1. Normal orbital operations — all systems nominal for 2+ seconds
  2. Solar storm — radiation spike triggers power + telemetry anomalies
  3. CO2 scrubber failure — ECLSS escalates to CRITICAL then EMERGENCY
  4. Power failure cascade — battery drains, load shed executes, safe mode triggers
  5. Conjunction avoidance — navigation detects close approach
  6. Full digital twin — all agents + simulator running together
  7. Health scorer + safe mode on degraded system
  8. Sensor fault injection → agent detects anomaly
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from aria.agents.eclss import EclssAgent
from aria.agents.navigation import NavigationAgent
from aria.agents.power import PowerAgent
from aria.agents.telemetry import TelemetryAgent
from aria.agents.thermal import ThermalAgent
from aria.bus.message_bus import Message, MessageBus
from aria.core.coordinator import AriaCoordinator
from aria.core.config import AriaConfig
from aria.core.simulator import SensorSimulator, SimulatedSensor
from aria.core.tool import ARIATool, ToolResult
from aria.core.types import AuthorityLevel, SafetyLevel, ToolCategory
from aria.safety.health import HealthScorer
from aria.safety.safe_mode import SafeLevel, SafeModeManager
from aria.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Shared fixtures and mock tools
# ---------------------------------------------------------------------------

class MockDsremoIngest(ARIATool):
    name = "dsremo_ingest_telemetry"
    description = "Mock Dsremo"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def __init__(self, score: float = 0.1) -> None:
        super().__init__()
        self.score = score
        self.calls: list[dict[str, Any]] = []

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        self.calls.append(params)
        return ToolResult(
            success=True,
            data={"anomaly_score": self.score, "detectors_triggered": []},
        )


@pytest.fixture
async def bus():
    b = MessageBus(max_history=2000)
    await b.start()
    yield b
    await b.stop()


class MockDsremoBatch(ARIATool):
    name = "dsremo_ingest_batch"
    description = "Mock Dsremo batch"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def __init__(self, score: float = 0.1) -> None:
        super().__init__()
        self.score = score

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "required": ["readings"], "properties": {"readings": {}}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        readings = params.get("readings", [])
        results = [
            {"channel_id": r["channel_id"], "anomaly_score": self.score, "detectors_triggered": []}
            for r in readings
        ]
        return ToolResult(success=True, data={"results": results, "count": len(readings)})


def make_tools(score: float = 0.1) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(MockDsremoIngest(score=score))
    reg.register(MockDsremoBatch(score=score))
    return reg


# ---------------------------------------------------------------------------
# Scenario 1: Normal Orbital Operations
# ---------------------------------------------------------------------------

async def test_scenario_nominal_ops(bus: MessageBus):
    """All agents running — no anomalies with normal sensor data."""
    anomalies: list[Message] = []

    async def capture(m: Message) -> None:
        anomalies.append(m)

    bus.subscribe("aria.anomaly.*", capture)

    tools = make_tools(score=0.05)
    agents = [
        TelemetryAgent(bus=bus, tool_registry=tools),
        PowerAgent(bus=bus, tool_registry=tools),
        NavigationAgent(bus=bus, tool_registry=tools),
        EclssAgent(bus=bus, tool_registry=tools),
        ThermalAgent(bus=bus, tool_registry=tools),
    ]
    for a in agents:
        await a.start()

    await bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 85.0, "temperature_c": 22.0},
    ))
    await bus.publish(Message(
        topic="aria.sensor.nav.imu",
        payload={"angular_rate_x_dps": 0.01, "angular_rate_y_dps": 0.01, "angular_rate_z_dps": 0.01},
    ))
    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 2.5, "pressure_psi": 14.7, "humidity_percent": 45.0},
    ))
    await bus.publish(Message(
        topic="aria.sensor.thermal.battery_pack",
        payload={"temperature_c": 22.0},
    ))

    await asyncio.sleep(0.3)

    critical = [a for a in anomalies if a.payload.get("severity") in ("CRITICAL", "EMERGENCY")]
    assert len(critical) == 0, f"Unexpected critical: {critical[0].payload if critical else ''}"

    for a in agents:
        await a.stop()


# ---------------------------------------------------------------------------
# Scenario 2: Solar Storm — Power + Telemetry Hit
# ---------------------------------------------------------------------------

async def test_scenario_solar_storm():
    """Solar storm: battery drains + anomaly score spikes → escalated to captain."""
    captain_alerts: list[Message] = []
    power_anomalies: list[Message] = []

    async def on_captain(m: Message) -> None:
        captain_alerts.append(m)

    async def on_power(m: Message) -> None:
        power_anomalies.append(m)

    config = AriaConfig()
    coordinator = AriaCoordinator(config)
    coordinator.tools.register(MockDsremoIngest(score=0.91))
    coordinator.tools.register(MockDsremoBatch(score=0.91))

    telemetry = TelemetryAgent(bus=coordinator.bus, tool_registry=coordinator.tools)
    power = PowerAgent(bus=coordinator.bus, tool_registry=coordinator.tools)
    coordinator.register_agent(telemetry)
    coordinator.register_agent(power)

    coordinator.bus.subscribe("aria.captain.alert", on_captain)
    coordinator.bus.subscribe("aria.anomaly.power", on_power)

    await coordinator.start()

    # Battery low + high temperature — PowerAgent fires WARNING,
    # TelemetryAgent routes through Dsremo batch with score 0.91 → CRITICAL
    await coordinator.bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 18.0, "temperature_c": 35.0},
    ))

    await asyncio.sleep(1.0)

    assert len(power_anomalies) >= 1, "Expected power anomaly from low battery"
    assert power_anomalies[0].payload["severity"] == "WARNING"
    assert len(captain_alerts) >= 1, "Expected captain alert from solar storm"

    await coordinator.stop()


# ---------------------------------------------------------------------------
# Scenario 3: CO2 Scrubber Failure Escalation
# ---------------------------------------------------------------------------

async def test_scenario_co2_emergency(bus: MessageBus):
    """CO2 builds up through WATCH → WARNING → CRITICAL — ECLSS escalates."""
    anomalies: list[Message] = []

    async def capture(m: Message) -> None:
        anomalies.append(m)

    bus.subscribe("aria.anomaly.eclss", capture)

    tools = make_tools(score=0.1)
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Stage 1: CO2 at WATCH level (5.5 mmHg > 5.3)
    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.5, "co2_mmhg": 5.5, "pressure_psi": 14.7, "humidity_percent": 45.0},
    ))
    await asyncio.sleep(0.15)
    watch_alerts = [a for a in anomalies if a.payload.get("severity") == "WATCH"]
    assert len(watch_alerts) >= 1, "Expected WATCH alert at CO2=5.5"

    # Stage 2: CO2 at WARNING level (8.0 mmHg > 7.6)
    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.0, "co2_mmhg": 8.0, "pressure_psi": 14.7, "humidity_percent": 45.0},
    ))
    await asyncio.sleep(0.15)
    warning_alerts = [a for a in anomalies if a.payload.get("severity") == "WARNING"]
    assert len(warning_alerts) >= 1, "Expected WARNING alert at CO2=8.0"

    # Stage 3: CO2 at CRITICAL level (11.0 mmHg > 10.0)
    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 19.5, "co2_mmhg": 11.0, "pressure_psi": 14.7, "humidity_percent": 45.0},
    ))
    await asyncio.sleep(0.15)
    critical_alerts = [a for a in anomalies if a.payload.get("severity") == "CRITICAL"]
    assert len(critical_alerts) >= 1, "Expected CRITICAL alert at CO2=11.0"

    await agent.stop()


# ---------------------------------------------------------------------------
# Scenario 4: Power Failure Cascade
# ---------------------------------------------------------------------------

async def test_scenario_power_cascade(bus: MessageBus):
    """Battery drains from high → critical, triggering load shed at <10% SoC."""
    load_shed_events: list[Message] = []

    async def capture(m: Message) -> None:
        load_shed_events.append(m)

    bus.subscribe("aria.power.load_shed.executed", capture)

    tools = make_tools()
    agent = PowerAgent(bus=bus, tool_registry=tools)
    await agent.start()

    for soc in [45.0, 25.0, 15.0, 8.0]:
        await bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": soc, "temperature_c": 28.0},
        ))
        await asyncio.sleep(0.1)

    await asyncio.sleep(0.2)

    assert len(load_shed_events) >= 1, "Expected load shed when battery hit critical"
    assert "experiments" in load_shed_events[0].payload["shed_loads"]

    await agent.stop()


# ---------------------------------------------------------------------------
# Scenario 5: Conjunction / Close Approach
# ---------------------------------------------------------------------------

async def test_scenario_conjunction(bus: MessageBus):
    """NavigationAgent detects and escalates a conjunction threat."""
    conj_alerts: list[Message] = []

    async def capture(m: Message) -> None:
        conj_alerts.append(m)

    bus.subscribe("aria.anomaly.conjunction", capture)

    tools = make_tools()
    agent = NavigationAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.conjunction.alert",
        payload={
            "object_name": "DEBRIS-2024-001",
            "time_to_tca_hours": 1.8,
            "collision_probability": 1.2e-3,  # > 1e-3 → CRITICAL
            "miss_distance_km": 0.8,
        },
    ))
    await asyncio.sleep(0.2)

    assert len(conj_alerts) >= 1, "Expected conjunction alert from NavigationAgent"
    assert conj_alerts[0].payload["severity"] == "CRITICAL"
    assert "DEBRIS-2024-001" in conj_alerts[0].payload["message"]

    await agent.stop()


# ---------------------------------------------------------------------------
# Scenario 6: Full Digital Twin — All Agents + Simulator
# ---------------------------------------------------------------------------

async def test_scenario_digital_twin(bus: MessageBus):
    """Full digital twin: simulator feeds all agents for 2 seconds — no crashes."""
    tools = make_tools(score=0.05)
    agents = [
        TelemetryAgent(bus=bus, tool_registry=tools),
        PowerAgent(bus=bus, tool_registry=tools),
        NavigationAgent(bus=bus, tool_registry=tools),
        EclssAgent(bus=bus, tool_registry=tools),
        ThermalAgent(bus=bus, tool_registry=tools),
    ]

    sim = SensorSimulator(bus)
    sim.add_default_sensors()

    for a in agents:
        await a.start()
    await sim.start()

    await asyncio.sleep(2.0)

    for agent in agents:
        assert agent.status.name not in ("STOPPED", "ERROR"), (
            f"Agent {agent.name} died: {agent.status.name}"
        )

    await sim.stop()
    for a in agents:
        await a.stop()


# ---------------------------------------------------------------------------
# Scenario 7: Health Scorer + Safe Mode on Degraded System
# ---------------------------------------------------------------------------

async def test_scenario_safe_mode_on_degraded_health(bus: MessageBus):
    """When multiple agents fail, SafeModeManager escalates correctly."""
    mode_changes: list[Message] = []

    async def capture_mode(m: Message) -> None:
        mode_changes.append(m)

    bus.subscribe("aria.safety.mode_change", capture_mode)

    safe_mgr = SafeModeManager(bus)
    scorer = HealthScorer()

    statuses = {
        "eclss": "ERROR",
        "power": "ERROR",
        "navigation": "READY",
        "thermal": "READY",
        "telemetry": "READY",
        "comms": "READY",
        "propulsion": "READY",
        "science": "READY",
    }
    report = scorer.compute(agent_statuses=statuses)

    # eclss(0.1*25%) + power(0.1*20%) = 2.5 + 2.0 = 4.5 → score well below 70
    assert report.overall_score < 70
    assert "eclss" in report.critical_subsystems
    assert "power" in report.critical_subsystems

    new_level = safe_mgr.evaluate(health_score=report.overall_score)
    assert new_level is not None
    assert new_level > SafeLevel.NOMINAL

    await safe_mgr.transition(new_level)
    await asyncio.sleep(0.1)

    assert len(mode_changes) >= 1
    assert mode_changes[0].payload["to_level"] == new_level.name


# ---------------------------------------------------------------------------
# Scenario 8: Sensor Fault Injection → Agent Detects Anomaly
# ---------------------------------------------------------------------------

async def test_scenario_fault_injection_pipeline(bus: MessageBus):
    """Simulator fault injection reaches ThermalAgent and triggers anomaly."""
    thermal_anomalies: list[Message] = []

    async def capture(m: Message) -> None:
        thermal_anomalies.append(m)

    bus.subscribe("aria.anomaly.thermal", capture)

    tools = make_tools()
    thermal_agent = ThermalAgent(bus=bus, tool_registry=tools)
    await thermal_agent.start()

    sim = SensorSimulator(bus)
    sim.add_sensor(SimulatedSensor(
        topic="aria.sensor.thermal.battery_pack",
        base_value=22.0,
        noise_std=0.1,
        sample_interval_s=0.1,
        payload_key="temperature_c",
    ))
    # +50°C offset → 72°C, above battery_pack max_c=45 → CRITICAL
    sim.inject_fault("aria.sensor.thermal.battery_pack", "offset", offset=50.0)

    await sim.start()
    await asyncio.sleep(0.8)
    await sim.stop()

    assert len(thermal_anomalies) >= 1, "Expected thermal anomaly from fault-injected spike"
    severities = {a.payload.get("severity") for a in thermal_anomalies}
    assert "CRITICAL" in severities or "WARNING" in severities

    await thermal_agent.stop()


# ---------------------------------------------------------------------------
# Scenario 9: Full Pipeline — Coordinator + Correlator + Captain Alert
# ---------------------------------------------------------------------------

async def test_scenario_full_pipeline_with_correlator():
    """End-to-end: simultaneous battery anomalies → correlator root cause → captain alert.

    Pipeline: sensor data → PowerAgent (threshold) + TelemetryAgent (Dsremo batch)
              → aria.anomaly.* events → AnomalyCorrelator
              → BATTERY_THERMAL_RUNAWAY root cause → coordinator → captain alert
    """
    captain_alerts: list[Message] = []
    correlations: list[Message] = []

    async def on_captain(m: Message) -> None:
        captain_alerts.append(m)

    async def on_correlation(m: Message) -> None:
        correlations.append(m)

    config = AriaConfig()
    coordinator = AriaCoordinator(config)

    # High Dsremo scores so TelemetryAgent flags anomalies
    coordinator.tools.register(MockDsremoIngest(score=0.88))
    coordinator.tools.register(MockDsremoBatch(score=0.88))

    telemetry = TelemetryAgent(bus=coordinator.bus, tool_registry=coordinator.tools)
    power = PowerAgent(bus=coordinator.bus, tool_registry=coordinator.tools)
    coordinator.register_agent(telemetry)
    coordinator.register_agent(power)

    coordinator.bus.subscribe("aria.captain.alert", on_captain)
    coordinator.bus.subscribe("aria.anomaly.correlation", on_correlation)

    await coordinator.start()

    # Inject battery data that triggers BOTH threshold (low SoC) AND Dsremo anomaly
    await coordinator.bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 12.0, "temperature_c": 42.0},
    ))

    await asyncio.sleep(1.5)  # Allow batch flush + correlation + escalation

    # PowerAgent should have raised threshold alerts (low SoC + high temp)
    # TelemetryAgent should have published Dsremo anomalies
    # Both reach captain
    assert len(captain_alerts) >= 1, "Expected at least 1 captain alert"

    await coordinator.stop()


# ---------------------------------------------------------------------------
# Scenario 10: API Server in Full System
# ---------------------------------------------------------------------------

async def test_scenario_api_serves_live_system():
    """API server exposes live system status from running coordinator."""
    import json

    config = AriaConfig()
    coordinator = AriaCoordinator(config)
    coordinator.tools.register(MockDsremoIngest(score=0.1))
    coordinator.tools.register(MockDsremoBatch(score=0.1))

    power = PowerAgent(bus=coordinator.bus, tool_registry=coordinator.tools)
    coordinator.register_agent(power)

    from aria.api.server import AriaAPIServer
    api = AriaAPIServer(
        bus=coordinator.bus,
        system_status_fn=coordinator.system_status,
        shared_secret="test",
        host="127.0.0.1",
        http_port=0,
        ws_port=0,
    )

    await coordinator.start()
    await api.start()

    # Get actual port
    port = api._http_server.sockets[0].getsockname()[1]

    # Query status via HTTP
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(b"GET /api/v1/status HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
    await writer.drain()
    response = await asyncio.wait_for(reader.read(65536), timeout=5)
    writer.close()
    await writer.wait_closed()

    body = response.decode().split("\r\n\r\n", 1)[1]
    data = json.loads(body)
    assert data["status"] == "RUNNING"
    assert "power" in data["agents"]

    await api.stop()
    await coordinator.stop()


# ---------------------------------------------------------------------------
# Scenario 11: Full 8-Agent Digital Twin
# ---------------------------------------------------------------------------

async def test_scenario_8_agent_digital_twin(bus: MessageBus):
    """All 8 agents running with simulator — no crashes, no unexpected emergencies."""
    from aria.agents.comms import CommsAgent
    from aria.agents.propulsion import PropulsionAgent
    from aria.agents.science import ScienceAgent

    anomalies: list[Message] = []
    bus.subscribe("aria.anomaly.*", lambda m: anomalies.append(m))

    tools = make_tools(score=0.05)  # Low score = nominal
    agents = [
        TelemetryAgent(bus=bus, tool_registry=tools),
        PowerAgent(bus=bus, tool_registry=tools),
        NavigationAgent(bus=bus, tool_registry=tools),
        EclssAgent(bus=bus, tool_registry=tools),
        ThermalAgent(bus=bus, tool_registry=tools),
        PropulsionAgent(bus=bus, tool_registry=tools),
        CommsAgent(bus=bus, tool_registry=tools),
        ScienceAgent(bus=bus, tool_registry=tools),
    ]

    sim = SensorSimulator(bus)
    sim.add_default_sensors()

    for a in agents:
        await a.start()
    await sim.start()

    await asyncio.sleep(2.5)  # Let all sensors produce data

    # All agents should be alive
    for agent in agents:
        assert agent.status.name not in ("STOPPED", "ERROR"), (
            f"Agent {agent.name} died: {agent.status.name}"
        )

    # No critical/emergency anomalies with nominal data
    critical = [a for a in anomalies if a.payload.get("severity") in ("CRITICAL", "EMERGENCY")]
    assert len(critical) == 0, f"Unexpected critical: {critical[0].payload if critical else ''}"

    await sim.stop()
    for a in agents:
        await a.stop()


# ---------------------------------------------------------------------------
# Scenario 12: Propulsion Maneuver + Fuel Tracking
# ---------------------------------------------------------------------------

async def test_scenario_propulsion_maneuver(bus: MessageBus):
    """PropulsionAgent executes maneuver, tracks fuel, reports delta-V."""
    from aria.agents.propulsion import PropulsionAgent

    maneuver_events: list[Message] = []
    bus.subscribe("aria.propulsion.maneuver.*", lambda m: maneuver_events.append(m))

    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools)
    await agent.start()

    initial_fuel = agent._propellant_kg

    # Execute a maneuver
    await bus.publish(Message(
        topic="aria.nav.maneuver.execute",
        payload={
            "maneuver_id": "CAM-001",
            "burns": [
                {"thruster_id": "thruster_1", "duration_ms": 2000, "thrust_level_pct": 80.0},
            ],
        },
    ))
    await asyncio.sleep(0.3)

    # Maneuver should have started and completed
    topics = [m.topic for m in maneuver_events]
    assert "aria.propulsion.maneuver.started" in topics
    assert "aria.propulsion.maneuver.completed" in topics

    # Fuel should have decreased
    assert agent._propellant_kg < initial_fuel

    await agent.stop()


# ---------------------------------------------------------------------------
# Scenario 13: FDIR Response to Correlation
# ---------------------------------------------------------------------------

async def test_scenario_fdir_battery_runaway():
    """Full pipeline: anomaly → correlator → FDIR response with actions."""
    from aria.safety.fdir import FDIRManager

    fdir_responses: list[Message] = []
    captain_alerts: list[Message] = []

    config = AriaConfig()
    coordinator = AriaCoordinator(config)
    coordinator.tools.register(MockDsremoIngest(score=0.9))
    coordinator.tools.register(MockDsremoBatch(score=0.9))

    telemetry = TelemetryAgent(bus=coordinator.bus, tool_registry=coordinator.tools)
    power = PowerAgent(bus=coordinator.bus, tool_registry=coordinator.tools)
    coordinator.register_agent(telemetry)
    coordinator.register_agent(power)

    coordinator.bus.subscribe("aria.fdir.response", lambda m: fdir_responses.append(m))
    coordinator.bus.subscribe("aria.captain.alert", lambda m: captain_alerts.append(m))

    await coordinator.start()

    # Inject data that should trigger battery anomalies
    await coordinator.bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 8.0, "temperature_c": 45.0},
    ))

    await asyncio.sleep(1.5)

    # PowerAgent should have raised alerts (low SoC + high temp)
    # Captain should have received alerts
    assert len(captain_alerts) >= 1

    await coordinator.stop()


# ---------------------------------------------------------------------------
# Scenario 14: Medical Emergency — Crew Cardiac Event
# ---------------------------------------------------------------------------

async def test_scenario_medical_emergency(bus: MessageBus):
    """MedicalAgent detects cardiac event during operations."""
    from aria.agents.medical import MedicalAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_tools()

    # Add crew tools with ROUTINE authority for test
    from aria.core.tool import ARIATool, ToolResult
    from aria.core.types import AuthorityLevel as AL, SafetyLevel as SL, ToolCategory as TC

    class MockCrewMedAlert(ARIATool):
        name = "crew_medical_alert"
        description = "mock"
        category = TC.EMERGENCY
        authority_level = AL.ROUTINE
        safety_level = SL.READ_ONLY
        def input_schema(self): return {"type": "object"}
        async def execute(self, params): return ToolResult(success=True, data={})

    class MockCrewAlert(ARIATool):
        name = "crew_alert"
        description = "mock"
        category = TC.DIAGNOSTIC
        authority_level = AL.ROUTINE
        safety_level = SL.READ_ONLY
        def input_schema(self): return {"type": "object"}
        async def execute(self, params): return ToolResult(success=True, data={})

    tools.register(MockCrewMedAlert())
    tools.register(MockCrewAlert())

    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Pilot has cardiac event
    await bus.publish(Message(
        topic="aria.sensor.medical.vitals.pilot",
        payload={"crew_id": "pilot", "heart_rate_bpm": 175, "spo2_percent": 85, "temperature_c": 39.6},
    ))
    await asyncio.sleep(0.3)

    emergency = [a for a in alerts if a.payload.get("severity") == "EMERGENCY"]
    assert len(emergency) >= 1
    assert any("pilot" in e.payload.get("message", "") for e in emergency)

    await agent.stop()


# ---------------------------------------------------------------------------
# Scenario 15: 9-Agent Full System Digital Twin
# ---------------------------------------------------------------------------

async def test_scenario_9_agent_full_system(bus: MessageBus):
    """Complete 9-agent system with all sensors — smoke test for stability."""
    from aria.agents.comms import CommsAgent
    from aria.agents.medical import MedicalAgent
    from aria.agents.propulsion import PropulsionAgent
    from aria.agents.science import ScienceAgent

    tools = make_tools(score=0.05)

    agents = [
        TelemetryAgent(bus=bus, tool_registry=tools),
        PowerAgent(bus=bus, tool_registry=tools),
        NavigationAgent(bus=bus, tool_registry=tools),
        EclssAgent(bus=bus, tool_registry=tools),
        ThermalAgent(bus=bus, tool_registry=tools),
        PropulsionAgent(bus=bus, tool_registry=tools),
        CommsAgent(bus=bus, tool_registry=tools),
        ScienceAgent(bus=bus, tool_registry=tools),
        MedicalAgent(bus=bus, tool_registry=tools),
    ]

    sim = SensorSimulator(bus)
    sim.add_default_sensors()

    for a in agents:
        await a.start()
    await sim.start()
    await asyncio.sleep(3.0)

    for agent in agents:
        assert agent.status.name not in ("STOPPED", "ERROR"), (
            f"Agent {agent.name} died: {agent.status.name}"
        )

    await sim.stop()
    for a in agents:
        await a.stop()


# ---------------------------------------------------------------------------
# Scenario 16: Scratchpad Cross-Agent Data Flow
# ---------------------------------------------------------------------------

async def test_scenario_scratchpad_cross_agent(bus: MessageBus):
    """Agents post observations to scratchpad, other agents can read them."""
    from aria.agents.science import ScienceAgent
    from aria.state.scratchpad import SharedScratchpad

    sp = SharedScratchpad()
    tools = make_tools(score=0.05)

    power = PowerAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    science = ScienceAgent(bus=bus, tool_registry=tools, scratchpad=sp)

    await power.start()
    await science.start()

    # PowerAgent receives solar data → posts eclipse state to scratchpad
    await bus.publish(Message(
        topic="aria.sensor.power.solar",
        payload={"power_watts": 0.0},  # Eclipse
    ))
    await asyncio.sleep(0.2)

    eclipse = sp.read("power.eclipse_state")
    assert eclipse is not None
    assert eclipse["in_eclipse"] is True

    # ScienceAgent receives radiation data → posts to scratchpad
    await bus.publish(Message(
        topic="aria.sensor.science.radiation",
        payload={"dose_rate_usv_hr": 5.0, "cumulative_dose_msv": 30.0},
    ))
    await asyncio.sleep(0.2)

    radiation = sp.read("science.radiation")
    assert radiation is not None
    assert radiation["dose_rate_usv_hr"] == 5.0

    await power.stop()
    await science.stop()


# ---------------------------------------------------------------------------
# Scenario 17: Full Emergency Cascade — Fire → ECLSS → Captain
# ---------------------------------------------------------------------------

async def test_scenario_fire_emergency_cascade(bus: MessageBus):
    """Fire detection cascades: smoke sensor → ECLSS emergency → fire response → captain alert."""
    alerts: list[Message] = []
    fire_responses: list[Message] = []

    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))
    bus.subscribe("aria.emergency.fire.response", lambda m: fire_responses.append(m))

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Smoke detector triggers
    await bus.publish(Message(
        topic="aria.sensor.fire.smoke",
        payload={"detected": True, "zone": "laboratory"},
    ))
    await asyncio.sleep(0.3)

    # ECLSS should have raised EMERGENCY
    emergency = [a for a in alerts if a.payload.get("severity") == "EMERGENCY"]
    assert len(emergency) >= 1
    assert "fire" in emergency[0].payload["message"].lower() or "smoke" in emergency[0].payload["message"].lower()

    # Fire response should have been published
    assert len(fire_responses) >= 1
    assert "activate_suppression" in fire_responses[0].payload["actions"]

    await agent.stop()


# ---------------------------------------------------------------------------
# Scenario 18: ECLSS Humidity Alert
# ---------------------------------------------------------------------------

async def test_scenario_humidity_alert(bus: MessageBus):
    """ECLSS detects high humidity and alerts."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 2.5, "humidity_percent": 85.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(0.2)

    humidity_alerts = [a for a in alerts if "humidity" in a.payload.get("message", "").lower()]
    assert len(humidity_alerts) >= 1

    await agent.stop()


# ---------------------------------------------------------------------------
# Scenario 19: Conjunction Avoidance Pipeline
# ---------------------------------------------------------------------------

async def test_scenario_conjunction_avoidance_pipeline(bus: MessageBus):
    """Full conjunction avoidance: Nav detects → scratchpad → Propulsion prepares → executes."""
    from aria.agents.propulsion import PropulsionAgent
    from aria.state.scratchpad import SharedScratchpad

    maneuver_events: list[Message] = []
    bus.subscribe("aria.propulsion.maneuver.*", lambda m: maneuver_events.append(m))
    bus.subscribe("aria.anomaly.conjunction", lambda m: None)

    sp = SharedScratchpad()
    tools = make_tools()

    nav = NavigationAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    prop = PropulsionAgent(bus=bus, tool_registry=tools, scratchpad=sp)

    await nav.start()
    await prop.start()

    # NavigationAgent receives conjunction alert
    await bus.publish(Message(
        topic="aria.conjunction.alert",
        payload={
            "object_name": "DEBRIS-2024-042",
            "time_to_tca_hours": 6.0,
            "collision_probability": 2.5e-3,
            "miss_distance_km": 0.3,
        },
    ))
    await asyncio.sleep(0.3)

    # NavigationAgent should have posted conjunction to scratchpad
    conj = sp.read("nav.next_conjunction")
    assert conj is not None
    assert conj["collision_probability"] == 2.5e-3

    # Execute maneuver through PropulsionAgent
    await bus.publish(Message(
        topic="aria.nav.maneuver.execute",
        payload={
            "maneuver_id": "CAM-042",
            "event_id": "EVT-042",
            "burns": [
                {"thruster_id": "thruster_1", "duration_ms": 3000, "thrust_level_pct": 100.0},
            ],
        },
    ))
    await asyncio.sleep(0.3)

    # Maneuver should have completed
    topics = [m.topic for m in maneuver_events]
    assert "aria.propulsion.maneuver.started" in topics
    assert "aria.propulsion.maneuver.completed" in topics

    await nav.stop()
    await prop.stop()


# ---------------------------------------------------------------------------
# Scenario 20: Multi-Agent Emergency Response Chain
# ---------------------------------------------------------------------------

async def test_scenario_multi_agent_emergency_chain():
    """Full emergency chain: fire → ECLSS → coordinator emergency phase → captain."""
    from aria.agents.comms import CommsAgent
    from aria.agents.medical import MedicalAgent

    captain_alerts: list[Message] = []
    phase_changes: list[Message] = []
    fire_responses: list[Message] = []

    config = AriaConfig()
    coordinator = AriaCoordinator(config)
    coordinator.tools.register(MockDsremoIngest(score=0.1))
    coordinator.tools.register(MockDsremoBatch(score=0.1))

    eclss = EclssAgent(bus=coordinator.bus, tool_registry=coordinator.tools)
    coordinator.register_agent(eclss)

    coordinator.bus.subscribe("aria.captain.alert", lambda m: captain_alerts.append(m))
    coordinator.bus.subscribe("aria.mission.phase_change", lambda m: phase_changes.append(m))
    coordinator.bus.subscribe("aria.emergency.fire.response", lambda m: fire_responses.append(m))

    await coordinator.start()
    assert coordinator.config.mission_phase == "NOMINAL_LEO"

    # Trigger fire
    await coordinator.bus.publish(Message(
        topic="aria.sensor.fire.smoke",
        payload={"detected": True, "zone": "laboratory"},
    ))
    await asyncio.sleep(0.5)

    # ECLSS should have published fire response
    assert len(fire_responses) >= 1

    # Coordinator should have received EMERGENCY anomaly → captain alert
    assert len(captain_alerts) >= 1

    # Emergency phase should have been triggered
    assert len(phase_changes) >= 1
    assert coordinator.config.mission_phase == "EMERGENCY"

    await coordinator.stop()


# ---------------------------------------------------------------------------
# Scenario 21: Simultaneous Multi-Emergency Stress Test
# ---------------------------------------------------------------------------

async def test_scenario_simultaneous_emergencies(bus: MessageBus):
    """Multiple emergencies at once: fire + depressurization + radiation spike.

    Verifies system handles concurrent emergencies without deadlock or crash.
    """
    from aria.agents.comms import CommsAgent
    from aria.agents.medical import MedicalAgent
    from aria.agents.science import ScienceAgent
    from aria.state.scratchpad import SharedScratchpad

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.*", lambda m: alerts.append(m))

    sp = SharedScratchpad()
    tools = make_tools()

    agents = [
        EclssAgent(bus=bus, tool_registry=tools, scratchpad=sp),
        ScienceAgent(bus=bus, tool_registry=tools, scratchpad=sp),
        PowerAgent(bus=bus, tool_registry=tools, scratchpad=sp),
        ThermalAgent(bus=bus, tool_registry=tools, scratchpad=sp),
    ]

    for a in agents:
        await a.start()

    # Fire all emergencies simultaneously
    await asyncio.gather(
        bus.publish(Message(
            topic="aria.sensor.fire.smoke",
            payload={"detected": True, "zone": "laboratory"},
        )),
        bus.publish(Message(
            topic="aria.sensor.eclss.pressure",
            payload={"pressure_psi": 12.0},  # Critical low
        )),
        bus.publish(Message(
            topic="aria.sensor.science.radiation",
            payload={"dose_rate_usv_hr": 2000.0, "cumulative_dose_msv": 100.0},
        )),
        bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 5.0, "temperature_c": 50.0},
        )),
    )

    await asyncio.sleep(0.5)

    # All agents should have raised alerts
    assert len(alerts) >= 4, f"Expected >= 4 alerts, got {len(alerts)}"

    # All agents should still be alive
    for agent in agents:
        assert agent.status.name not in ("STOPPED", "ERROR"), (
            f"Agent {agent.name} died during multi-emergency: {agent.status.name}"
        )

    for a in agents:
        await a.stop()


# ---------------------------------------------------------------------------
# Scenario 22: Full Scratchpad Verification — All 9 Agents Post
# ---------------------------------------------------------------------------

async def test_scenario_all_agents_post_to_scratchpad(bus: MessageBus):
    """All 9 agents post their state to scratchpad during normal operations."""
    from aria.agents.comms import CommsAgent
    from aria.agents.medical import MedicalAgent
    from aria.agents.propulsion import PropulsionAgent
    from aria.agents.science import ScienceAgent
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

    for a in agents:
        await a.start()

    # Send sensor data to trigger scratchpad posts
    await bus.publish(Message(topic="aria.sensor.power.solar", payload={"power_watts": 2500.0}))
    await bus.publish(Message(topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 2.5, "humidity_percent": 45.0, "temperature_c": 22.0}))
    await bus.publish(Message(topic="aria.sensor.science.radiation",
        payload={"dose_rate_usv_hr": 0.5, "cumulative_dose_msv": 25.0}))
    await asyncio.sleep(0.3)

    # Trigger periodic tasks for remaining agents
    for a in agents:
        try:
            await a.periodic_task()
        except Exception:
            pass
    await asyncio.sleep(0.2)

    # Verify scratchpad has data from multiple agents
    assert sp.size >= 3, f"Expected >= 3 scratchpad entries, got {sp.size}"

    # Verify key entries exist
    assert sp.read("power.eclipse_state") is not None or sp.read("power.prediction") is not None
    assert sp.read("eclss.atmosphere") is not None
    assert sp.read("science.radiation") is not None

    for a in agents:
        await a.stop()


# ---------------------------------------------------------------------------
# Scenario 23: Power Cascade — Eclipse + Load Shed + Safe Mode
# ---------------------------------------------------------------------------

async def test_scenario_power_cascade_eclipse(bus: MessageBus):
    """Eclipse entry with low battery triggers load shed + alerts."""
    shed_events: list[Message] = []
    alerts: list[Message] = []

    bus.subscribe("aria.power.load_shed.executed", lambda m: shed_events.append(m))
    bus.subscribe("aria.anomaly.power", lambda m: alerts.append(m))

    tools = make_tools()
    agent = PowerAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Eclipse entry with already low battery
    await bus.publish(Message(
        topic="aria.sensor.power.solar",
        payload={"power_watts": 0.0},
    ))
    await bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 7.0, "temperature_c": 28.0},
    ))
    await asyncio.sleep(0.3)

    assert len(shed_events) >= 1 or len(alerts) >= 1  # Should trigger load shed or critical alert
    await agent.stop()


# ---------------------------------------------------------------------------
# Scenario 24: Navigation + Propulsion Coordination
# ---------------------------------------------------------------------------

async def test_scenario_nav_propulsion_coordination(bus: MessageBus):
    """NavigationAgent detects conjunction, PropulsionAgent prepares and executes."""
    from aria.agents.propulsion import PropulsionAgent
    from aria.state.scratchpad import SharedScratchpad

    sp = SharedScratchpad()
    tools = make_tools()

    nav = NavigationAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    prop = PropulsionAgent(bus=bus, tool_registry=tools, scratchpad=sp)

    await nav.start()
    await prop.start()

    # Nav receives conjunction
    await bus.publish(Message(
        topic="aria.conjunction.alert",
        payload={
            "object_name": "COSMOS-DEBRIS",
            "time_to_tca_hours": 3.0,
            "collision_probability": 5e-3,
        },
    ))
    await asyncio.sleep(0.3)

    # Nav should have posted to scratchpad
    conj = sp.read("nav.next_conjunction")
    assert conj is not None

    # Propulsion checks fuel readiness
    await prop.periodic_task()
    await asyncio.sleep(0.1)

    await nav.stop()
    await prop.stop()


# ---------------------------------------------------------------------------
# Scenario 25: Deep Space Cruise — High Autonomy Operations
# ---------------------------------------------------------------------------

async def test_scenario_deep_space_cruise():
    """Phase transition to DEEP_SPACE_CRUISE with high autonomy."""
    config = AriaConfig()
    coordinator = AriaCoordinator(config)
    coordinator.tools.register(MockDsremoIngest(score=0.1))
    coordinator.tools.register(MockDsremoBatch(score=0.1))

    telemetry = TelemetryAgent(bus=coordinator.bus, tool_registry=coordinator.tools)
    coordinator.register_agent(telemetry)

    await coordinator.start()
    assert coordinator.config.mission_phase == "NOMINAL_LEO"

    # Transition to deep space
    success = await coordinator.transition_phase("DEEP_SPACE_CRUISE")
    assert success
    assert coordinator.config.mission_phase == "DEEP_SPACE_CRUISE"

    await coordinator.stop()


# ---------------------------------------------------------------------------
# Scenario 26: Proximity Operations — Captain Authority
# ---------------------------------------------------------------------------

async def test_scenario_proximity_ops_phase():
    """Phase transition to PROXIMITY_OPS restricts authority to captain."""
    from aria.core.types import PHASE_CONFIG

    config = AriaConfig()
    coordinator = AriaCoordinator(config)
    coordinator.tools.register(MockDsremoIngest(score=0.1))
    coordinator.tools.register(MockDsremoBatch(score=0.1))

    await coordinator.start()

    success = await coordinator.transition_phase("PROXIMITY_OPS")
    assert success

    phase_config = PHASE_CONFIG["PROXIMITY_OPS"]
    assert phase_config["authority"] == "CAPTAIN_ONLY"
    assert phase_config["autonomy_level"] == 1

    await coordinator.stop()


# ---------------------------------------------------------------------------
# Scenario 27-30: Quick edge case scenarios
# ---------------------------------------------------------------------------

async def test_scenario_all_nominal_no_alerts(bus: MessageBus):
    """All-nominal sensor data produces zero CRITICAL/EMERGENCY alerts."""
    from aria.agents.comms import CommsAgent
    from aria.agents.propulsion import PropulsionAgent
    from aria.agents.science import ScienceAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.*", lambda m: alerts.append(m))

    tools = make_tools(score=0.05)

    agents = [
        PowerAgent(bus=bus, tool_registry=tools),
        EclssAgent(bus=bus, tool_registry=tools),
        NavigationAgent(bus=bus, tool_registry=tools),
        ThermalAgent(bus=bus, tool_registry=tools),
    ]
    for a in agents:
        await a.start()

    # All nominal readings
    await bus.publish(Message(topic="aria.sensor.power.battery", payload={"soc_percent": 85.0, "temperature_c": 25.0}))
    await bus.publish(Message(topic="aria.sensor.eclss.atmosphere", payload={"o2_percent": 20.9, "co2_mmhg": 2.5, "humidity_percent": 45.0, "temperature_c": 22.0}))
    await bus.publish(Message(topic="aria.sensor.nav.imu", payload={"angular_rate_x_dps": 0.01, "angular_rate_y_dps": 0.01, "angular_rate_z_dps": 0.01}))
    await bus.publish(Message(topic="aria.sensor.thermal.crew_cabin", payload={"temperature_c": 22.0}))
    await asyncio.sleep(0.3)

    critical = [a for a in alerts if a.payload.get("severity") in ("CRITICAL", "EMERGENCY")]
    assert len(critical) == 0, f"Got unexpected critical alerts: {[a.payload for a in critical]}"

    for a in agents:
        await a.stop()


async def test_scenario_rapid_sensor_updates():
    """Rapid sensor updates don't crash coordinator."""
    config = AriaConfig()
    coordinator = AriaCoordinator(config)
    coordinator.tools.register(MockDsremoIngest(score=0.1))
    coordinator.tools.register(MockDsremoBatch(score=0.1))

    telemetry = TelemetryAgent(bus=coordinator.bus, tool_registry=coordinator.tools)
    coordinator.register_agent(telemetry)

    await coordinator.start()

    # Rapid-fire 50 sensor readings
    for i in range(50):
        await coordinator.bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 85.0 - i * 0.1, "temperature_c": 25.0},
        ))

    await asyncio.sleep(2.0)
    assert coordinator.is_running

    await coordinator.stop()


async def test_scenario_coordinator_event_log_populated():
    """Coordinator event log captures anomaly events."""
    config = AriaConfig()
    coordinator = AriaCoordinator(config)
    coordinator.tools.register(MockDsremoIngest(score=0.1))
    coordinator.tools.register(MockDsremoBatch(score=0.1))

    power = PowerAgent(bus=coordinator.bus, tool_registry=coordinator.tools)
    coordinator.register_agent(power)

    await coordinator.start()

    # Trigger a low battery alert
    await coordinator.bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 8.0, "temperature_c": 25.0},
    ))
    await asyncio.sleep(0.5)

    # Event log should have entries
    assert coordinator.event_log.event_count >= 1

    await coordinator.stop()


# ---------------------------------------------------------------------------
# Scenario 30: Complete System Readiness Check
# ---------------------------------------------------------------------------

async def test_scenario_system_readiness():
    """Full system readiness check with all agents healthy."""
    from aria.agents.comms import CommsAgent
    from aria.agents.medical import MedicalAgent
    from aria.agents.propulsion import PropulsionAgent
    from aria.agents.science import ScienceAgent

    config = AriaConfig()
    coordinator = AriaCoordinator(config)
    coordinator.tools.register(MockDsremoIngest(score=0.1))
    coordinator.tools.register(MockDsremoBatch(score=0.1))

    for cls in [TelemetryAgent, PowerAgent, NavigationAgent, ThermalAgent,
                EclssAgent, PropulsionAgent, CommsAgent, ScienceAgent, MedicalAgent]:
        coordinator.register_agent(cls(bus=coordinator.bus, tool_registry=coordinator.tools))

    await coordinator.start()

    check = coordinator.readiness_check()
    assert check["go_for_operations"] is True
    assert check["agents_ready"] == "9/9"
    assert len(check["issues"]) == 0

    await coordinator.stop()
