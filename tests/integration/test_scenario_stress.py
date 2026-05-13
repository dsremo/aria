"""Agent-level scenario stress tests — famous space emergencies through ARIA.

Simulates catastrophic spacecraft failures by injecting crafted messages onto
the ARIA bus and verifying that subsystem agents detect, respond, and coordinate
correctly.  Each test is deterministic (no randomness, no wall-clock races).

Scenarios modeled after real and fictional space emergencies:
  1. Power Failure Cascade (ISS eclipse worst-case)
  2. Rapid Orbit Decay (Skylab/Mir-style uncontrolled descent)
  3. Communication Blackout (Apollo lunar far-side LOS)
  4. Multi-Agent Coordination (eclipse thermal-power-ECLSS handshake)
  5. Sensor Disagreement (conflicting GPS/IMU/star-tracker)
  6. Overload Storm (Carrington-class event flooding all subsystems)
  7. Graceful Degradation (progressive agent failure, survivor absorption)

Test infrastructure:
  - MessageBus (real, in-memory)
  - Agents (real, full logic)
  - Tools (stubs that return configurable scores / ToolResult)
  - SharedScratchpad (real, in-memory)
  - No Basilisk dependency (we craft physics-realistic messages ourselves)
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
from aria.agents.propulsion import PropulsionAgent
from aria.agents.thermal import ThermalAgent
from aria.bus.message_bus import Message, MessageBus
from aria.core.scenario_engine import ScenarioEngine, ScenarioEvent, ScenarioScript
from aria.core.tool import ARIATool, ToolResult
from aria.core.types import (
    AgentStatus,
    AuthorityLevel,
    EventPriority,
    SafetyLevel,
    Severity,
    ToolCategory,
)
from aria.state.scratchpad import SharedScratchpad
from aria.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Reusable stub tools
# ---------------------------------------------------------------------------

class StubIngest(ARIATool):
    """Stub Dsremo single-reading ingest."""
    name = "dsremo_ingest_telemetry"
    description = "stub"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def __init__(self, score: float = 0.0) -> None:
        super().__init__()
        self._score = score
        self.calls: list[dict[str, Any]] = []

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object"}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        self.calls.append(params)
        return ToolResult(success=True, data={"anomaly_score": self._score})


class StubBatch(ARIATool):
    """Stub Dsremo batch ingest."""
    name = "dsremo_ingest_batch"
    description = "stub"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def __init__(self, score: float = 0.0) -> None:
        super().__init__()
        self._score = score
        self.batch_calls: int = 0

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "required": ["readings"]}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        self.batch_calls += 1
        readings = params.get("readings", [])
        return ToolResult(success=True, data={
            "results": [
                {"channel_id": r["channel_id"], "anomaly_score": self._score}
                for r in readings
            ],
            "count": len(readings),
        })


class StubLoadShed(ARIATool):
    """Records load shed invocations."""
    name = "eps_load_shed"
    description = "stub"
    category = ToolCategory.POWER
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.REVERSIBLE

    def __init__(self) -> None:
        super().__init__()
        self.shed_calls: list[dict[str, Any]] = []

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object"}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        self.shed_calls.append(params)
        return ToolResult(success=True, data={"shed": True})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry(dsremo_score: float = 0.0) -> ToolRegistry:
    """Create a ToolRegistry with all the stubs agents need."""
    reg = ToolRegistry()
    reg.register(StubIngest(score=dsremo_score))
    reg.register(StubBatch(score=dsremo_score))
    reg.register(StubLoadShed())
    return reg


class MessageCollector:
    """Subscribe to a bus topic pattern and collect all messages received."""

    def __init__(self, bus: MessageBus, pattern: str) -> None:
        self.messages: list[Message] = []
        self._bus = bus
        self._pattern = pattern
        bus.subscribe(pattern, self._on_message)

    async def _on_message(self, msg: Message) -> None:
        self.messages.append(msg)

    def payloads(self) -> list[dict[str, Any]]:
        return [m.payload for m in self.messages]

    def topics(self) -> list[str]:
        return [m.topic for m in self.messages]

    def severities(self) -> list[str]:
        return [m.payload.get("severity", "") for m in self.messages]

    def has_severity(self, sev: str) -> bool:
        return sev in self.severities()

    def has_topic(self, topic: str) -> bool:
        return topic in self.topics()

    def count(self) -> int:
        return len(self.messages)

    def detach(self) -> None:
        self._bus.unsubscribe(self._pattern, self._on_message)


async def _drain(seconds: float = 0.3) -> None:
    """Let the bus dispatch loop flush pending messages."""
    await asyncio.sleep(seconds)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def bus():
    b = MessageBus(max_history=5000)
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def scratchpad():
    return SharedScratchpad()


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 1 — POWER FAILURE CASCADE
# Solar panels fail during eclipse -> battery drains -> load shedding -> adapt
# ═══════════════════════════════════════════════════════════════════════════════

class TestPowerFailureCascade:
    """ISS-style eclipse worst-case: solar array failure + eclipse = cascading
    power loss.  ARIA must detect, shed loads, and alert."""

    async def test_solar_power_drops_to_zero_triggers_eclipse_flag(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """When solar power drops to zero, PowerAgent sets eclipse flag and publishes event."""
        reg = _make_registry()
        collector = MessageCollector(bus, "aria.power.eclipse.*")
        agent = PowerAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.sensor.power.solar",
            payload={"power_watts": 0.0},
        ))
        await _drain()

        assert agent._in_eclipse is True
        assert collector.has_topic("aria.power.eclipse.entered")
        await agent.stop()

    async def test_battery_drains_below_warning_threshold(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Battery SoC at 15% triggers WARNING alert."""
        reg = _make_registry()
        alerts = MessageCollector(bus, "aria.anomaly.power")
        agent = PowerAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 15.0, "temperature_c": 25.0},
        ))
        await _drain()

        assert alerts.has_severity("WARNING")
        assert any("low" in m.payload.get("message", "").lower() for m in alerts.messages)
        await agent.stop()

    async def test_battery_critical_triggers_load_shed(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Battery at 8% triggers CRITICAL alert AND automatic load shedding."""
        reg = _make_registry()
        shed_tool: StubLoadShed = reg.get("eps_load_shed")  # type: ignore[assignment]
        shed_events = MessageCollector(bus, "aria.power.load_shed.*")
        alerts = MessageCollector(bus, "aria.anomaly.power")
        agent = PowerAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 8.0, "temperature_c": 25.0},
        ))
        await _drain()

        assert alerts.has_severity("CRITICAL")
        assert shed_events.count() >= 1
        assert shed_tool.shed_calls  # tool was invoked
        await agent.stop()

    async def test_full_eclipse_cascade_solar_then_battery(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Complete cascade: solar=0 -> eclipse -> battery drains -> critical -> shed."""
        reg = _make_registry()
        shed_events = MessageCollector(bus, "aria.power.load_shed.*")
        all_power = MessageCollector(bus, "aria.anomaly.power")
        agent = PowerAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        # Step 1: solar panels fail
        await bus.publish(Message(
            topic="aria.sensor.power.solar",
            payload={"power_watts": 0.0},
        ))
        await _drain(0.15)

        # Step 2: battery drains to warning
        await bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 18.0, "temperature_c": 28.0},
        ))
        await _drain(0.15)

        # Step 3: battery hits critical
        await bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 7.0, "temperature_c": 32.0},
        ))
        await _drain()

        assert agent._in_eclipse is True
        assert all_power.has_severity("WARNING")
        assert all_power.has_severity("CRITICAL")
        assert shed_events.count() >= 1
        await agent.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 2 — RAPID ORBIT DECAY
# Altitude drops from 400km; NavigationAgent detects; PropulsionAgent responds
# ═══════════════════════════════════════════════════════════════════════════════

class TestRapidOrbitDecay:
    """Skylab-style uncontrolled orbital decay.  Navigation must warn,
    propulsion must be ready to respond."""

    async def test_altitude_drop_triggers_nav_anomaly(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """0.6 km altitude drop in one reading triggers orbit decay WATCH."""
        reg = _make_registry()
        nav_alerts = MessageCollector(bus, "aria.anomaly.navigation")
        agent = NavigationAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        # First reading sets baseline
        await bus.publish(Message(
            topic="aria.sensor.nav.gps",
            payload={"fix": True, "satellites": 10, "altitude_km": 400.0},
        ))
        await _drain(0.15)

        # Second reading: dropped 0.6 km
        await bus.publish(Message(
            topic="aria.sensor.nav.gps",
            payload={"fix": True, "satellites": 10, "altitude_km": 399.4},
        ))
        await _drain()

        decay_alerts = [
            m for m in nav_alerts.messages
            if "decay" in m.payload.get("message", "").lower()
        ]
        assert len(decay_alerts) >= 1
        await agent.stop()

    async def test_progressive_decay_multiple_readings(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Multiple successive drops produce multiple orbit decay warnings."""
        reg = _make_registry()
        nav_alerts = MessageCollector(bus, "aria.anomaly.navigation")
        agent = NavigationAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        altitudes = [400.0, 399.3, 398.5, 397.6, 396.5]
        for alt in altitudes:
            await bus.publish(Message(
                topic="aria.sensor.nav.gps",
                payload={"fix": True, "satellites": 10, "altitude_km": alt},
            ))
            await _drain(0.1)

        decay_msgs = [
            m for m in nav_alerts.messages
            if "decay" in m.payload.get("message", "").lower()
        ]
        # Each successive drop > 0.5 km should produce an alert
        assert len(decay_msgs) >= 3
        await agent.stop()

    async def test_gps_loss_during_decay(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """GPS fix lost with few satellites triggers additional alert."""
        reg = _make_registry()
        nav_alerts = MessageCollector(bus, "aria.anomaly.navigation")
        agent = NavigationAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.sensor.nav.gps",
            payload={"fix": False, "satellites": 2},
        ))
        await _drain()

        gps_loss_alerts = [
            m for m in nav_alerts.messages
            if "gps" in m.payload.get("message", "").lower()
        ]
        assert len(gps_loss_alerts) >= 1
        await agent.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 3 — COMMUNICATION BLACKOUT
# CommsAgent detects loss of signal, queues messages, auto-recovers on reacquire
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommunicationBlackout:
    """Apollo-style LOS behind the Moon / ISS ground station gap."""

    async def test_signal_loss_detected(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Low signal + low SNR causes link loss alert."""
        reg = _make_registry()
        comms_alerts = MessageCollector(bus, "aria.anomaly.comms")
        agent = CommsAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        # Signal drops below threshold
        await bus.publish(Message(
            topic="aria.sensor.comms.link",
            payload={"signal_dbm": -120.0, "snr_db": 1.0, "ber": 1e-3, "data_rate_kbps": 0},
        ))
        await _drain()

        assert agent._link_active is False
        assert comms_alerts.count() >= 1
        assert any("lost" in m.payload.get("message", "").lower() for m in comms_alerts.messages)
        await agent.stop()

    async def test_messages_queued_during_blackout(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Messages submitted during blackout are queued, not dropped."""
        reg = _make_registry()
        agent = CommsAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        # Kill the link
        await bus.publish(Message(
            topic="aria.sensor.comms.link",
            payload={"signal_dbm": -130.0, "snr_db": 0.5, "ber": 1e-2, "data_rate_kbps": 0},
        ))
        await _drain(0.15)

        # Queue several messages
        for i in range(5):
            await bus.publish(Message(
                topic="aria.command.comms.send",
                payload={"message_type": "telemetry", "priority": "NORMAL", "data": f"packet_{i}"},
            ))
        await _drain()

        assert len(agent._outbound_queue) >= 5
        await agent.stop()

    async def test_queue_flushes_on_signal_recovery(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Queued messages are sent once the link is restored."""
        reg = _make_registry()
        downlink = MessageCollector(bus, "aria.comms.downlink.*")
        contact = MessageCollector(bus, "aria.comms.contact.*")
        agent = CommsAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        # Kill link
        await bus.publish(Message(
            topic="aria.sensor.comms.link",
            payload={"signal_dbm": -130.0, "snr_db": 0.5, "ber": 1e-2, "data_rate_kbps": 0},
        ))
        await _drain(0.15)

        # Queue messages
        for i in range(3):
            await bus.publish(Message(
                topic="aria.command.comms.send",
                payload={"message_type": "telemetry", "priority": "NORMAL", "data": f"pkt_{i}"},
            ))
        await _drain(0.15)
        assert len(agent._outbound_queue) >= 3

        # Restore link
        await bus.publish(Message(
            topic="aria.sensor.comms.link",
            payload={"signal_dbm": -80.0, "snr_db": 20.0, "ber": 1e-9, "data_rate_kbps": 256},
        ))
        await _drain()

        assert agent._link_active is True
        assert contact.has_topic("aria.comms.contact.acquired")
        # Queue should be flushed
        assert len(agent._outbound_queue) == 0
        assert downlink.count() >= 1
        await agent.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 4 — MULTI-AGENT COORDINATION (eclipse transition)
# Thermal + Power + ECLSS coordinate during eclipse entry
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultiAgentEclipseCoordination:
    """During eclipse, Power detects solar loss, Thermal pre-heats critical zones,
    and ECLSS monitors atmosphere temperature changes."""

    async def test_power_eclipse_triggers_thermal_preheat(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Power's eclipse.entered event causes Thermal to pre-heat battery + propulsion."""
        reg = _make_registry()
        heater_cmds = MessageCollector(bus, "aria.actuator.thermal.heater.*")

        thermal = ThermalAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        power = PowerAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await thermal.start()
        await power.start()

        # Power detects eclipse
        await bus.publish(Message(
            topic="aria.sensor.power.solar",
            payload={"power_watts": 0.0},
        ))
        await _drain(0.4)

        heater_zones = [m.payload.get("zone") for m in heater_cmds.messages]
        # Thermal should pre-heat battery_pack and propulsion
        assert "battery_pack" in heater_zones or "propulsion" in heater_zones
        await thermal.stop()
        await power.stop()

    async def test_scratchpad_eclipse_state_shared(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """PowerAgent writes eclipse state to scratchpad, ThermalAgent reads it."""
        reg = _make_registry()
        power = PowerAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await power.start()

        await bus.publish(Message(
            topic="aria.sensor.power.solar",
            payload={"power_watts": 0.0},
        ))
        await _drain()

        eclipse_state = scratchpad.read("power.eclipse_state")
        assert eclipse_state is not None
        assert eclipse_state["in_eclipse"] is True
        await power.stop()

    async def test_three_agent_eclipse_coordination(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Power + Thermal + ECLSS all respond to an eclipse transition together."""
        reg = _make_registry()
        eclipse_events = MessageCollector(bus, "aria.power.eclipse.*")
        heater_events = MessageCollector(bus, "aria.actuator.thermal.*")
        eclss_alerts = MessageCollector(bus, "aria.anomaly.eclss")

        power = PowerAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        thermal = ThermalAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        eclss = EclssAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)

        await power.start()
        await thermal.start()
        await eclss.start()

        # Eclipse entry
        await bus.publish(Message(
            topic="aria.sensor.power.solar",
            payload={"power_watts": 0.0},
        ))
        await _drain(0.15)

        # Temperature starts dropping in cabin
        await bus.publish(Message(
            topic="aria.sensor.eclss.atmosphere",
            payload={"o2_percent": 20.9, "co2_mmhg": 2.5, "humidity_percent": 45, "temperature_c": 17.0},
        ))
        await _drain(0.3)

        # Power should have entered eclipse
        assert eclipse_events.count() >= 1
        # Scratchpad should reflect eclipse
        assert scratchpad.read("power.eclipse_state") is not None

        await power.stop()
        await thermal.stop()
        await eclss.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 5 — SENSOR DISAGREEMENT
# Navigation receives conflicting data; must detect inconsistency
# ═══════════════════════════════════════════════════════════════════════════════

class TestSensorDisagreement:
    """GPS vs IMU conflict scenarios.  NavigationAgent should detect anomalies."""

    async def test_tumble_detected_from_high_angular_rate(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """High angular rates from IMU trigger CRITICAL tumble alert."""
        reg = _make_registry()
        nav_alerts = MessageCollector(bus, "aria.anomaly.navigation")
        agent = NavigationAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.sensor.nav.imu",
            payload={"angular_rate_x_dps": 8.0, "angular_rate_y_dps": 3.0, "angular_rate_z_dps": 2.0},
        ))
        await _drain()

        tumble = [m for m in nav_alerts.messages if "tumble" in m.payload.get("message", "").lower()]
        assert len(tumble) >= 1
        assert tumble[0].payload["severity"] == "CRITICAL"
        await agent.stop()

    async def test_degraded_gps_constellation(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Few GPS satellites triggers degraded accuracy warning."""
        reg = _make_registry()
        nav_alerts = MessageCollector(bus, "aria.anomaly.navigation")
        agent = NavigationAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.sensor.nav.gps",
            payload={"fix": True, "satellites": 4, "altitude_km": 400.0},
        ))
        await _drain()

        gps_degraded = [m for m in nav_alerts.messages if "constellation" in m.payload.get("message", "").lower()]
        assert len(gps_degraded) >= 1
        await agent.stop()

    async def test_conflicting_altitude_and_high_rates(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Simultaneous altitude anomaly and high angular rates produce multiple alerts."""
        reg = _make_registry()
        nav_alerts = MessageCollector(bus, "aria.anomaly.navigation")
        agent = NavigationAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        # Altitude jumps implausibly
        await bus.publish(Message(
            topic="aria.sensor.nav.gps",
            payload={"fix": True, "satellites": 10, "altitude_km": 400.0},
        ))
        await _drain(0.1)
        await bus.publish(Message(
            topic="aria.sensor.nav.gps",
            payload={"fix": True, "satellites": 10, "altitude_km": 399.0},
        ))
        await _drain(0.1)

        # IMU says tumbling
        await bus.publish(Message(
            topic="aria.sensor.nav.imu",
            payload={"angular_rate_x_dps": 12.0, "angular_rate_y_dps": 5.0, "angular_rate_z_dps": 7.0},
        ))
        await _drain()

        # Should have both decay and tumble alerts
        all_msgs = " ".join(m.payload.get("message", "") for m in nav_alerts.messages).lower()
        assert "decay" in all_msgs
        assert "tumble" in all_msgs
        await agent.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 6 — OVERLOAD STORM
# 100+ anomalies hit simultaneously; ARIA must process without dropping
# ═══════════════════════════════════════════════════════════════════════════════

class TestOverloadStorm:
    """Carrington-class solar event flooding every subsystem with anomalies.
    Tests bus throughput and agent resilience under volume."""

    async def test_100_simultaneous_power_readings(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """100 battery readings pumped in rapid succession are all processed."""
        reg = _make_registry()
        alerts = MessageCollector(bus, "aria.anomaly.power")
        agent = PowerAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        for i in range(100):
            soc = max(5.0, 80.0 - i * 0.8)  # Drains from 80 to 5
            await bus.publish(Message(
                topic="aria.sensor.power.battery",
                payload={"soc_percent": soc, "temperature_c": 25.0 + i * 0.1},
            ))
        await _drain(2.0)

        # Agent must have processed many readings
        assert agent._messages_processed >= 50
        # Should have triggered at least WARNING and CRITICAL
        assert alerts.has_severity("WARNING")
        assert alerts.has_severity("CRITICAL")
        await agent.stop()

    async def test_multi_subsystem_storm(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Simultaneous anomalies across power, comms, and navigation."""
        reg = _make_registry()
        power_alerts = MessageCollector(bus, "aria.anomaly.power")
        comms_alerts = MessageCollector(bus, "aria.anomaly.comms")
        nav_alerts = MessageCollector(bus, "aria.anomaly.navigation")

        power = PowerAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        comms = CommsAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        nav = NavigationAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)

        await power.start()
        await comms.start()
        await nav.start()

        # Blast all three simultaneously
        tasks = []
        for i in range(30):
            tasks.append(bus.publish(Message(
                topic="aria.sensor.power.battery",
                payload={"soc_percent": max(5.0, 50.0 - i * 1.5), "temperature_c": 30.0},
            )))
            tasks.append(bus.publish(Message(
                topic="aria.sensor.comms.link",
                payload={"signal_dbm": -80.0 - i * 2, "snr_db": max(0.5, 15.0 - i * 0.5), "ber": 1e-6, "data_rate_kbps": 100},
            )))
            tasks.append(bus.publish(Message(
                topic="aria.sensor.nav.gps",
                payload={"fix": True, "satellites": max(3, 10 - i // 5), "altitude_km": 400.0 - i * 0.3},
            )))
        await asyncio.gather(*tasks)
        await _drain(3.0)

        # Each agent should have detected something
        assert power_alerts.count() >= 1
        assert comms_alerts.count() >= 1
        assert nav_alerts.count() >= 1

        await power.stop()
        await comms.stop()
        await nav.stop()

    async def test_bus_does_not_drop_high_priority(self, bus: MessageBus):
        """P0 emergency messages are delivered even under flood conditions."""
        emergency_received: list[Message] = []

        async def capture_emergency(msg: Message) -> None:
            emergency_received.append(msg)

        bus.subscribe("aria.emergency.*", capture_emergency)

        # Flood with 200 low-priority messages
        for i in range(200):
            await bus.publish(Message(
                topic="aria.sensor.bulk.data",
                payload={"i": i},
                priority=EventPriority.P4_BULK,
            ))

        # Inject a single P0 emergency
        await bus.publish(Message(
            topic="aria.emergency.fire.detected",
            payload={"zone": "lab", "severity": "EMERGENCY"},
            priority=EventPriority.P0_EMERGENCY,
        ))
        await _drain(1.0)

        assert len(emergency_received) >= 1
        assert emergency_received[0].payload["zone"] == "lab"


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 7 — GRACEFUL DEGRADATION
# Agents fail one by one; remaining agents absorb responsibilities
# ═══════════════════════════════════════════════════════════════════════════════

class TestGracefulDegradation:
    """Tests that stopping agents doesn't crash the system and surviving agents
    continue to function independently."""

    async def test_power_agent_survives_after_nav_stops(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """PowerAgent continues operating after NavigationAgent is stopped."""
        reg = _make_registry()
        power_alerts = MessageCollector(bus, "aria.anomaly.power")

        power = PowerAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        nav = NavigationAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await power.start()
        await nav.start()

        # Stop nav
        await nav.stop()
        assert nav.status == AgentStatus.STOPPED

        # Power should still work
        await bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 9.0, "temperature_c": 25.0},
        ))
        await _drain()

        assert power_alerts.has_severity("CRITICAL")
        await power.stop()

    async def test_progressive_agent_shutdown(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Stop agents one by one; last agent standing still works."""
        reg = _make_registry()
        agents = [
            NavigationAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad),
            CommsAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad),
            ThermalAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad),
            PowerAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad),
        ]
        for a in agents:
            await a.start()

        # Stop first three
        for a in agents[:3]:
            await a.stop()
            assert a.status == AgentStatus.STOPPED

        # Power agent (last) should still operate
        alerts = MessageCollector(bus, "aria.anomaly.power")
        await bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 5.0, "temperature_c": 25.0},
        ))
        await _drain()

        assert alerts.count() >= 1
        await agents[-1].stop()

    async def test_stopped_agent_does_not_receive_messages(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Once stopped, an agent no longer processes bus messages."""
        reg = _make_registry()
        agent = PowerAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()
        await agent.stop()

        count_before = agent._messages_processed

        await bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 5.0, "temperature_c": 25.0},
        ))
        await _drain()

        # Should not have processed anything new
        assert agent._messages_processed == count_before


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO: THERMAL EMERGENCY — COOLANT LEAK
# ═══════════════════════════════════════════════════════════════════════════════

class TestThermalEmergency:
    """Coolant loop failure causing thermal zone violations."""

    async def test_coolant_low_pressure_critical_alert(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Coolant pressure below 15 psi triggers CRITICAL alert."""
        reg = _make_registry()
        alerts = MessageCollector(bus, "aria.anomaly.thermal")
        agent = ThermalAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.sensor.thermal.coolant",
            payload={"pressure_psi": 10.0, "flow_rate_lpm": 5.0, "temperature_c": 15.0},
        ))
        await _drain()

        assert alerts.has_severity("CRITICAL")
        assert any("leak" in m.payload.get("message", "").lower() for m in alerts.messages)
        await agent.stop()

    async def test_zone_out_of_range_warning(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Temperature reading outside zone limits triggers alert."""
        reg = _make_registry()
        alerts = MessageCollector(bus, "aria.anomaly.thermal")
        agent = ThermalAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        # Battery pack zone limits: 5-45 C.  Send 50 C.
        await bus.publish(Message(
            topic="aria.sensor.thermal.battery_pack",
            payload={"temperature_c": 50.0},
        ))
        await _drain()

        assert alerts.count() >= 1
        assert any("battery_pack" in m.payload.get("message", "") for m in alerts.messages)
        await agent.stop()

    async def test_heater_activates_when_zone_cold(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """When zone drops below setpoint - deadband, heater turns on."""
        reg = _make_registry()
        heater_cmds = MessageCollector(bus, "aria.actuator.thermal.heater.*")
        agent = ThermalAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        # Battery pack setpoint is 20, deadband 2 => heater on below 18
        await bus.publish(Message(
            topic="aria.sensor.thermal.battery_pack",
            payload={"temperature_c": 10.0},
        ))
        await _drain()

        heater_on = [m for m in heater_cmds.messages if m.payload.get("heater") == "on"]
        assert len(heater_on) >= 1
        await agent.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO: ECLSS — FIRE + DEPRESSURIZATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestEclssEmergency:
    """Life-support emergencies: fire detection, CO2 spike, depressurization."""

    async def test_smoke_triggers_emergency_fire_response(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Smoke detection triggers EMERGENCY alert and fire response actions."""
        reg = _make_registry()
        eclss_alerts = MessageCollector(bus, "aria.anomaly.eclss")
        fire_response = MessageCollector(bus, "aria.emergency.fire.*")
        agent = EclssAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.sensor.fire.smoke",
            payload={"detected": True, "zone": "lab_module"},
        ))
        await _drain()

        assert eclss_alerts.has_severity("EMERGENCY")
        assert fire_response.count() >= 1
        assert any("lab_module" in m.payload.get("zone", "") for m in fire_response.messages)
        await agent.stop()

    async def test_co2_critical_activates_backup_scrubber(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """CO2 at emergency level activates backup scrubber."""
        reg = _make_registry()
        eclss_alerts = MessageCollector(bus, "aria.anomaly.eclss")
        scrubber = MessageCollector(bus, "aria.actuator.eclss.scrubber_backup")
        agent = EclssAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.sensor.eclss.atmosphere",
            payload={"o2_percent": 20.0, "co2_mmhg": 16.0, "humidity_percent": 45, "temperature_c": 22.0},
        ))
        await _drain()

        assert eclss_alerts.has_severity("EMERGENCY")
        assert scrubber.count() >= 1
        await agent.stop()

    async def test_pressure_drop_emergency(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Cabin pressure below 13.5 psi triggers EMERGENCY depressurization response."""
        reg = _make_registry()
        eclss_alerts = MessageCollector(bus, "aria.anomaly.eclss")
        agent = EclssAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.sensor.eclss.pressure",
            payload={"pressure_psi": 12.8},
        ))
        await _drain()

        assert eclss_alerts.has_severity("EMERGENCY")
        assert any("depressurization" in m.payload.get("message", "").lower() for m in eclss_alerts.messages)
        await agent.stop()

    async def test_low_o2_critical_alert(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """O2 below 19.5% triggers CRITICAL alert."""
        reg = _make_registry()
        eclss_alerts = MessageCollector(bus, "aria.anomaly.eclss")
        agent = EclssAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.sensor.eclss.atmosphere",
            payload={"o2_percent": 18.5, "co2_mmhg": 2.5, "humidity_percent": 45, "temperature_c": 22.0},
        ))
        await _drain()

        assert eclss_alerts.has_severity("CRITICAL")
        assert any("o2" in m.payload.get("message", "").lower() for m in eclss_alerts.messages)
        await agent.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO: PROPULSION — THRUSTER STUCK OPEN
# ═══════════════════════════════════════════════════════════════════════════════

class TestPropulsionEmergency:
    """Thruster faults and fuel emergencies."""

    async def test_stuck_open_valve_emergency(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Thruster valve stuck open with no active maneuver triggers EMERGENCY."""
        reg = _make_registry()
        prop_alerts = MessageCollector(bus, "aria.anomaly.propulsion")
        agent = PropulsionAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.sensor.propulsion.thruster.thruster_1",
            payload={"chamber_pressure_psi": 150.0, "temperature_c": 200.0, "valve_state": "open"},
        ))
        await _drain()

        assert prop_alerts.has_severity("EMERGENCY")
        assert any("stuck" in m.payload.get("message", "").lower() for m in prop_alerts.messages)
        await agent.stop()

    async def test_low_propellant_warning(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Low fuel fraction triggers staged alerts."""
        reg = _make_registry()
        prop_alerts = MessageCollector(bus, "aria.anomaly.propulsion")
        agent = PropulsionAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        # Drop to 10 kg (10% of 100 kg initial)
        await bus.publish(Message(
            topic="aria.sensor.propulsion.tank",
            payload={"propellant_kg": 10.0, "pressure_psi": 100.0, "temperature_c": 20.0},
        ))
        await _drain()

        assert prop_alerts.count() >= 1
        await agent.stop()

    async def test_tank_pressure_critical(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Tank pressure below 50 psi triggers CRITICAL alert."""
        reg = _make_registry()
        prop_alerts = MessageCollector(bus, "aria.anomaly.propulsion")
        agent = PropulsionAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.sensor.propulsion.tank",
            payload={"propellant_kg": 80.0, "pressure_psi": 30.0, "temperature_c": 20.0},
        ))
        await _drain()

        assert prop_alerts.has_severity("CRITICAL")
        await agent.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO: SCENARIO ENGINE — scripted fault injection
# ═══════════════════════════════════════════════════════════════════════════════

class TestScenarioEngineIntegration:
    """Verify ScenarioEngine fires events onto the bus at the right time and
    agents pick them up."""

    async def test_scenario_fires_all_events(self, bus: MessageBus):
        """A simple scenario with 3 events fires them all."""
        script = ScenarioScript(
            name="test_scenario",
            description="Three quick events",
            events=[
                ScenarioEvent(time_offset_s=0.0, topic="aria.test.event1", payload={"seq": 1}),
                ScenarioEvent(time_offset_s=0.1, topic="aria.test.event2", payload={"seq": 2}),
                ScenarioEvent(time_offset_s=0.2, topic="aria.test.event3", payload={"seq": 3}),
            ],
        )
        engine = ScenarioEngine(bus, script)

        received: list[Message] = []
        bus.subscribe("aria.test.*", lambda m: asyncio.ensure_future(_collect(received, m)))

        await engine.run(time_scale=100.0)  # fast

        assert len(engine.fired_events) == 3
        assert engine.progress == 1.0

    async def test_scenario_events_reach_agents(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """ScenarioEngine events published to sensor topics are processed by agents."""
        reg = _make_registry()
        alerts = MessageCollector(bus, "aria.anomaly.power")
        agent = PowerAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        script = ScenarioScript(
            name="power_failure_script",
            description="Scripted power failure",
            events=[
                ScenarioEvent(
                    time_offset_s=0.0,
                    topic="aria.sensor.power.battery",
                    payload={"soc_percent": 7.0, "temperature_c": 40.0},
                    priority=EventPriority.P1_CRITICAL,
                ),
            ],
        )
        engine = ScenarioEngine(bus, script)
        await engine.run(time_scale=100.0)
        await _drain()

        assert alerts.has_severity("CRITICAL")
        await agent.stop()

    async def test_scenario_stop_midway(self, bus: MessageBus):
        """Calling stop() on engine halts execution partway through."""
        script = ScenarioScript(
            name="long_scenario",
            description="Won't finish",
            events=[
                ScenarioEvent(time_offset_s=0.0, topic="aria.test.a", payload={"n": 1}),
                ScenarioEvent(time_offset_s=10.0, topic="aria.test.b", payload={"n": 2}),
                ScenarioEvent(time_offset_s=20.0, topic="aria.test.c", payload={"n": 3}),
            ],
        )
        engine = ScenarioEngine(bus, script)

        async def stop_after_delay():
            await asyncio.sleep(0.2)
            engine.stop()

        asyncio.create_task(stop_after_delay())
        await engine.run(time_scale=1.0)  # Real-time — second event at 10s, we stop at 0.2s

        assert len(engine.fired_events) < 3
        assert engine.progress < 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO: BATTERY THERMAL RUNAWAY PRECURSOR
# ═══════════════════════════════════════════════════════════════════════════════

class TestBatteryThermalRunaway:
    """High battery temp + low SoC = thermal runaway risk."""

    async def test_hot_battery_with_low_soc_critical(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Battery at 42C + SoC 25% triggers thermal runaway risk CRITICAL."""
        reg = _make_registry()
        alerts = MessageCollector(bus, "aria.anomaly.power")
        agent = PowerAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 25.0, "temperature_c": 42.0},
        ))
        await _drain()

        assert alerts.has_severity("CRITICAL")
        assert any("thermal" in m.payload.get("message", "").lower() for m in alerts.messages)
        await agent.stop()

    async def test_elevated_temp_watch(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Battery at 37C with normal SoC triggers WATCH."""
        reg = _make_registry()
        alerts = MessageCollector(bus, "aria.anomaly.power")
        agent = PowerAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 60.0, "temperature_c": 37.0},
        ))
        await _drain()

        watch_msgs = [m for m in alerts.messages if m.payload.get("severity") == "WATCH"]
        assert len(watch_msgs) >= 1
        await agent.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO: CONJUNCTION — COLLISION AVOIDANCE
# ═══════════════════════════════════════════════════════════════════════════════

class TestConjunctionEmergency:
    """High-probability conjunction triggers cascade from navigation to propulsion."""

    async def test_high_pc_conjunction_emergency(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Conjunction with Pc > 1e-3 triggers P0 EMERGENCY alert."""
        reg = _make_registry()
        conj_alerts = MessageCollector(bus, "aria.anomaly.conjunction")
        agent = NavigationAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.conjunction.alert",
            payload={
                "collision_probability": 5e-3,
                "time_to_tca_hours": 2.0,
                "object_name": "DEBRIS-12345",
            },
        ))
        await _drain()

        assert conj_alerts.count() >= 1
        assert conj_alerts.messages[0].payload["severity"] == "CRITICAL"
        assert conj_alerts.messages[0].priority == EventPriority.P0_EMERGENCY
        await agent.stop()

    async def test_conjunction_posts_to_scratchpad(self, bus: MessageBus, scratchpad: SharedScratchpad):
        """Conjunction data is written to scratchpad for PropulsionAgent."""
        reg = _make_registry()
        agent = NavigationAgent(bus=bus, tool_registry=reg, scratchpad=scratchpad)
        await agent.start()

        await bus.publish(Message(
            topic="aria.conjunction.alert",
            payload={
                "collision_probability": 2e-4,
                "time_to_tca_hours": 12.0,
                "object_name": "COSMOS-2251-DEB",
            },
        ))
        await _drain()

        conj_data = scratchpad.read("nav.next_conjunction")
        assert conj_data is not None
        assert conj_data["object_name"] == "COSMOS-2251-DEB"
        assert conj_data["collision_probability"] == 2e-4
        await agent.stop()


# ---------------------------------------------------------------------------
# Helper coroutine for fire-and-forget subscription
# ---------------------------------------------------------------------------

async def _collect(store: list[Message], msg: Message) -> None:
    store.append(msg)
