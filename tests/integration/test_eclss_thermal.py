"""Integration tests for ECLSS and Thermal agents."""

import asyncio
from typing import Any

import pytest

from aria.agents.eclss import EclssAgent
from aria.agents.thermal import ThermalAgent
from aria.bus.message_bus import Message, MessageBus
from aria.core.types import EventPriority
from aria.tools.registry import ToolRegistry


@pytest.fixture
async def bus():
    b = MessageBus(max_history=100)
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def tools():
    return ToolRegistry()


async def test_eclss_detects_low_o2(bus: MessageBus, tools: ToolRegistry):
    """EclssAgent raises CRITICAL when O2 drops below 19.5%."""
    alerts: list[Message] = []

    async def capture(msg: Message) -> None:
        alerts.append(msg)

    bus.subscribe("aria.anomaly.eclss", capture)

    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 18.5, "co2_mmhg": 2.5, "humidity_percent": 45.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(0.2)

    assert any(a.payload["severity"] == "CRITICAL" for a in alerts)
    assert any("O2" in a.payload.get("message", "") for a in alerts)
    await agent.stop()


async def test_eclss_co2_staged_response(bus: MessageBus, tools: ToolRegistry):
    """EclssAgent escalates CO2 alerts in stages."""
    alerts: list[Message] = []

    async def capture(msg: Message) -> None:
        alerts.append(msg)

    bus.subscribe("aria.anomaly.eclss", capture)

    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Stage 1: WATCH at 5.5 mmHg
    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 5.5, "humidity_percent": 45.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(0.1)
    assert any(a.payload["severity"] == "WATCH" for a in alerts)

    # Stage 2: CRITICAL at 11.0 mmHg
    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 11.0, "humidity_percent": 45.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(0.1)
    assert any(a.payload["severity"] == "CRITICAL" for a in alerts)

    await agent.stop()


async def test_eclss_fire_detection(bus: MessageBus, tools: ToolRegistry):
    """EclssAgent triggers EMERGENCY on smoke detection."""
    alerts: list[Message] = []
    fire_responses: list[Message] = []

    async def capture_alert(msg: Message) -> None:
        alerts.append(msg)

    async def capture_fire(msg: Message) -> None:
        fire_responses.append(msg)

    bus.subscribe("aria.anomaly.eclss", capture_alert)
    bus.subscribe("aria.emergency.fire.response", capture_fire)

    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.fire.smoke",
        payload={"detected": True, "zone": "module_a"},
    ))
    await asyncio.sleep(0.3)

    assert any(a.payload["severity"] == "EMERGENCY" for a in alerts)
    assert len(fire_responses) >= 1
    assert "activate_suppression" in fire_responses[0].payload["actions"]
    await agent.stop()


async def test_eclss_leak_detection(bus: MessageBus, tools: ToolRegistry):
    """EclssAgent detects cabin pressure leak from rate of change."""
    alerts: list[Message] = []

    async def capture(msg: Message) -> None:
        alerts.append(msg)

    bus.subscribe("aria.anomaly.eclss", capture)

    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Simulate pressure dropping (critical low)
    await bus.publish(Message(
        topic="aria.sensor.eclss.pressure", payload={"pressure_psi": 13.0},
    ))
    await asyncio.sleep(0.1)

    assert any(a.payload["severity"] == "EMERGENCY" for a in alerts)
    await agent.stop()


async def test_thermal_heater_control(bus: MessageBus, tools: ToolRegistry):
    """ThermalAgent turns on heaters when zone temperature drops below setpoint."""
    heater_commands: list[Message] = []

    async def capture(msg: Message) -> None:
        heater_commands.append(msg)

    bus.subscribe("aria.actuator.thermal.heater.*", capture)

    agent = ThermalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Send cold temperature for battery zone (setpoint=20, deadband=2 → heater on below 18)
    await bus.publish(Message(
        topic="aria.sensor.thermal.battery_pack",
        payload={"temperature_c": 15.0},
    ))
    await asyncio.sleep(0.2)

    assert len(heater_commands) >= 1
    assert heater_commands[0].payload["heater"] == "on"
    await agent.stop()


async def test_thermal_out_of_range_alert(bus: MessageBus, tools: ToolRegistry):
    """ThermalAgent raises WARNING when zone temperature exceeds limits."""
    alerts: list[Message] = []

    async def capture(msg: Message) -> None:
        alerts.append(msg)

    bus.subscribe("aria.anomaly.thermal", capture)

    agent = ThermalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Battery zone max is 45°C — send 48°C
    await bus.publish(Message(
        topic="aria.sensor.thermal.battery_pack",
        payload={"temperature_c": 48.0},
    ))
    await asyncio.sleep(0.2)

    assert len(alerts) >= 1
    assert alerts[0].payload["severity"] == "WARNING"
    await agent.stop()


async def test_thermal_eclipse_preheat(bus: MessageBus, tools: ToolRegistry):
    """ThermalAgent pre-heats critical zones on eclipse entry."""
    heater_commands: list[Message] = []

    async def capture(msg: Message) -> None:
        heater_commands.append(msg)

    bus.subscribe("aria.actuator.thermal.heater.*", capture)

    agent = ThermalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Simulate eclipse entry from PowerAgent
    await bus.publish(Message(
        topic="aria.power.eclipse.entered",
        payload={"solar_power_w": 0.0},
    ))
    await asyncio.sleep(0.2)

    # Should have pre-heated battery_pack and propulsion
    heated_zones = [c.payload["zone"] for c in heater_commands]
    assert "battery_pack" in heated_zones
    assert "propulsion" in heated_zones
    await agent.stop()
