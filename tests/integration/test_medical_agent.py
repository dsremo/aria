"""Integration tests for MedicalAgent — crew health monitoring."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from aria.agents.medical import MedicalAgent
from aria.bus.message_bus import Message, MessageBus
from aria.core.tool import ARIATool, ToolResult
from aria.core.types import AuthorityLevel, SafetyLevel, ToolCategory
from aria.tools.registry import ToolRegistry


class MockDsremoIngest(ARIATool):
    name = "dsremo_ingest_telemetry"
    description = "Mock"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object"}
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"anomaly_score": 0.1})


class MockDsremoBatch(ARIATool):
    name = "dsremo_ingest_batch"
    description = "Mock batch"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "required": ["readings"], "properties": {"readings": {}}}
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        readings = params.get("readings", [])
        results = [{"channel_id": r["channel_id"], "anomaly_score": 0.1} for r in readings]
        return ToolResult(success=True, data={"results": results, "count": len(readings)})


class MockCrewMedicalAlert(ARIATool):
    name = "crew_medical_alert"
    description = "Mock"
    category = ToolCategory.EMERGENCY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    def __init__(self):
        super().__init__()
        self.calls: list[dict] = []
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object"}
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        self.calls.append(params)
        return ToolResult(success=True, data={"alert_issued": True})


class MockCrewAlert(ARIATool):
    name = "crew_alert"
    description = "Mock"
    category = ToolCategory.DIAGNOSTIC
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    def __init__(self):
        super().__init__()
        self.calls: list[dict] = []
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object"}
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        self.calls.append(params)
        return ToolResult(success=True, data={"sent": True})


@pytest.fixture
async def bus():
    b = MessageBus(max_history=200)
    await b.start()
    yield b
    await b.stop()


def make_medical_tools():
    reg = ToolRegistry()
    reg.register(MockDsremoIngest())
    reg.register(MockDsremoBatch())
    reg.register(MockCrewMedicalAlert())
    reg.register(MockCrewAlert())
    return reg


async def test_normal_vitals_no_alert(bus: MessageBus):
    """Normal vital signs produce no alerts."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_medical_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.medical.vitals.commander",
        payload={"crew_id": "commander", "heart_rate_bpm": 72, "spo2_percent": 98, "temperature_c": 36.8},
    ))
    await asyncio.sleep(0.2)

    critical = [a for a in alerts if a.payload.get("severity") in ("CRITICAL", "EMERGENCY")]
    assert len(critical) == 0
    assert "commander" in agent._crew_vitals
    await agent.stop()


async def test_high_heart_rate_warning(bus: MessageBus):
    """Elevated heart rate triggers WARNING."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_medical_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.medical.vitals.pilot",
        payload={"crew_id": "pilot", "heart_rate_bpm": 120, "spo2_percent": 97},
    ))
    await asyncio.sleep(0.2)

    warning = [a for a in alerts if a.payload.get("severity") == "WARNING"]
    assert len(warning) >= 1
    assert "heart_rate" in warning[0].payload.get("vital", "") or "heart_rate" in warning[0].payload.get("message", "")
    await agent.stop()


async def test_cardiac_emergency(bus: MessageBus):
    """Extremely high heart rate triggers EMERGENCY + medical alert."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_medical_tools()
    medical_alert_tool = tools.get("crew_medical_alert")
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.medical.vitals.ms1",
        payload={"crew_id": "ms1", "heart_rate_bpm": 160, "spo2_percent": 85, "temperature_c": 39.8},
    ))
    await asyncio.sleep(0.3)

    emergency = [a for a in alerts if a.payload.get("severity") == "EMERGENCY"]
    assert len(emergency) >= 1
    # Medical alert tool should have been called
    assert len(medical_alert_tool.calls) >= 1
    assert medical_alert_tool.calls[0]["crew_member"] == "ms1"
    await agent.stop()


async def test_low_spo2_emergency(bus: MessageBus):
    """SpO2 below 90% triggers EMERGENCY."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_medical_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.medical.vitals.ms2",
        payload={"crew_id": "ms2", "spo2_percent": 87},
    ))
    await asyncio.sleep(0.2)

    emergency = [a for a in alerts if a.payload.get("severity") == "EMERGENCY"]
    assert len(emergency) >= 1
    await agent.stop()


async def test_sleep_fatigue_tracking(bus: MessageBus):
    """Poor sleep triggers fatigue WARNING."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_medical_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.medical.sleep",
        payload={"crew_id": "commander", "quality_score": 25, "duration_hours": 3.5},
    ))
    await asyncio.sleep(0.2)

    assert agent._crew_fatigue.get("commander") == "critical"
    warning = [a for a in alerts if a.payload.get("severity") == "WARNING"]
    assert len(warning) >= 1
    await agent.stop()


async def test_exercise_tracking(bus: MessageBus):
    """Exercise duration is accumulated per crew member."""
    tools = make_medical_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.medical.exercise",
        payload={"crew_id": "pilot", "type": "treadmill", "duration_min": 30, "intensity": "moderate"},
    ))
    await bus.publish(Message(
        topic="aria.sensor.medical.exercise",
        payload={"crew_id": "pilot", "type": "ared", "duration_min": 45, "intensity": "high"},
    ))
    await asyncio.sleep(0.2)

    assert agent._crew_exercise_min_today["pilot"] == 75.0
    await agent.stop()


async def test_radiation_career_limit_warning(bus: MessageBus):
    """High cumulative radiation dose triggers WARNING/CRITICAL."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_medical_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.medical.radiation",
        payload={"crew_id": "ms1", "cumulative_dose_msv": 520},
    ))
    await asyncio.sleep(0.2)

    critical = [a for a in alerts if a.payload.get("severity") == "CRITICAL"]
    assert len(critical) >= 1
    assert "career limit" in critical[0].payload["message"].lower()
    await agent.stop()
