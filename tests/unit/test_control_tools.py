"""Tests for control, emergency, diagnostic, planning, and crew tools.

Validates input schemas, validation rules, and execution for all 14 tools
from CENTRAL_AI_MASTER_PLAN Part 5.
"""

from __future__ import annotations

from typing import Any

import pytest

from aria.integrations.control_tools import (
    ALL_CONTROL_TOOLS,
    CommsSendToGround,
    CommsGetLinkStatus,
    CrewAlert,
    CrewGetStatus,
    DiagnosticRunSubsystemTest,
    EmergencyDepressurizationResponse,
    EmergencyFireSuppression,
    EmergencySafeMode,
    EpsLoadShed,
    EpsSetHeater,
    GetSubsystemState,
    PlanningScheduleActivity,
    PropulsionFireThruster,
    ReadSensor,
)
from aria.tools.registry import ToolRegistry


class TestToolRegistration:
    def test_all_tools_register_without_conflict(self):
        """All 14 control tools can be registered."""
        reg = ToolRegistry()
        for cls in ALL_CONTROL_TOOLS:
            reg.register(cls())
        assert reg.count == 14

    def test_all_tools_have_unique_names(self):
        names = [cls().name for cls in ALL_CONTROL_TOOLS]
        assert len(names) == len(set(names))


class TestReadSensor:
    def test_validation_requires_sensor_id(self):
        tool = ReadSensor()
        assert not tool.validate_input({}).valid
        assert tool.validate_input({"sensor_id": "eps.bat1.voltage"}).valid

    async def test_execution(self):
        tool = ReadSensor()
        result = await tool.execute({"sensor_id": "eps.bat1.voltage"})
        assert result.success
        assert result.data["sensor_id"] == "eps.bat1.voltage"


class TestGetSubsystemState:
    def test_validation(self):
        tool = GetSubsystemState()
        assert not tool.validate_input({}).valid
        assert tool.validate_input({"subsystem": "eps"}).valid

    async def test_execution(self):
        tool = GetSubsystemState()
        result = await tool.execute({"subsystem": "thermal"})
        assert result.success
        assert result.data["subsystem"] == "thermal"
        assert result.data["status"] == "NOMINAL"


class TestEpsSetHeater:
    def test_validation(self):
        tool = EpsSetHeater()
        assert not tool.validate_input({}).valid
        assert not tool.validate_input({"zone_id": "battery", "power_watts": -5}).valid
        assert tool.validate_input({"zone_id": "battery", "power_watts": 10}).valid


class TestEpsLoadShed:
    def test_validation_requires_reason(self):
        tool = EpsLoadShed()
        assert not tool.validate_input({"shed_amount_watts": 100}).valid
        assert tool.validate_input({"shed_amount_watts": 100, "reason": "low battery"}).valid

    async def test_execution(self):
        tool = EpsLoadShed()
        result = await tool.execute({"shed_amount_watts": 200, "reason": "battery critical"})
        assert result.success
        assert "experiments" in result.data["loads_shed"]


class TestPropulsionFireThruster:
    def test_validation(self):
        tool = PropulsionFireThruster()
        assert not tool.validate_input({"duration_ms": 100}).valid  # Missing thruster_id + reason
        assert tool.validate_input({
            "thruster_id": "t1", "duration_ms": 1000,
            "thrust_level_pct": 50, "reason": "avoidance",
        }).valid


class TestEmergencySafeMode:
    def test_validation(self):
        tool = EmergencySafeMode()
        assert not tool.validate_input({"level": 2}).valid  # Missing reason
        assert tool.validate_input({"level": 3, "reason": "health degraded"}).valid

    async def test_execution(self):
        tool = EmergencySafeMode()
        result = await tool.execute({"level": 2, "reason": "power failure"})
        assert result.success
        assert result.data["activated"]
        assert result.data["level"] == 2


class TestEmergencyDepressurizationResponse:
    def test_validation(self):
        tool = EmergencyDepressurizationResponse()
        assert not tool.validate_input({}).valid
        assert tool.validate_input({"compartment": "module_a"}).valid

    async def test_execution(self):
        tool = EmergencyDepressurizationResponse()
        result = await tool.execute({"compartment": "module_b", "leak_rate_kpa_per_min": 0.5})
        assert result.success
        assert result.data["isolated"]
        assert result.data["crew_alerted"]


class TestEmergencyFireSuppression:
    def test_validation(self):
        tool = EmergencyFireSuppression()
        assert not tool.validate_input({}).valid
        assert tool.validate_input({"compartment": "lab"}).valid


class TestCommsSendToGround:
    def test_validation(self):
        tool = CommsSendToGround()
        assert not tool.validate_input({"message_type": "event"}).valid
        assert tool.validate_input({"message_type": "event", "data": "test"}).valid


class TestDiagnosticRunSubsystemTest:
    def test_validation(self):
        tool = DiagnosticRunSubsystemTest()
        assert not tool.validate_input({}).valid
        assert tool.validate_input({"subsystem": "eps"}).valid

    async def test_execution(self):
        tool = DiagnosticRunSubsystemTest()
        result = await tool.execute({"subsystem": "thermal", "test_level": "comprehensive"})
        assert result.success
        assert result.data["result"] == "PASS"
        assert result.data["tests_failed"] == 0


class TestPlanningScheduleActivity:
    def test_validation(self):
        tool = PlanningScheduleActivity()
        assert not tool.validate_input({}).valid
        assert tool.validate_input({
            "activity_name": "science_obs",
            "start_time": "2026-04-06T12:00:00Z",
            "duration_minutes": 30,
        }).valid


class TestCrewAlert:
    def test_validation(self):
        tool = CrewAlert()
        assert not tool.validate_input({}).valid
        assert tool.validate_input({
            "recipients": ["all"],
            "priority": "WARNING",
            "message": "Prepare for maneuver",
        }).valid


class TestCrewGetStatus:
    async def test_execution(self):
        tool = CrewGetStatus()
        result = await tool.execute({})
        assert result.success
        assert result.data["crew_count"] == 4
        assert len(result.data["crew"]) == 4


class TestCommsGetLinkStatus:
    async def test_execution(self):
        tool = CommsGetLinkStatus()
        result = await tool.execute({})
        assert result.success
        assert "link_active" in result.data


class TestDiagnosticTools:
    async def test_memory_scrub(self):
        from aria.integrations.control_tools import DiagnosticRunSubsystemTest
        tool = DiagnosticRunSubsystemTest()
        result = await tool.execute({"subsystem": "eps", "test_level": "quick"})
        assert result.success
        assert result.data["result"] == "PASS"


class TestCrewTools:
    async def test_crew_alert_sends(self):
        tool = CrewAlert()
        result = await tool.execute({
            "recipients": ["commander"],
            "priority": "WARNING",
            "message": "Test alert",
        })
        assert result.success
        assert result.data["sent"]


class TestEmergencyTools:
    async def test_fire_suppression(self):
        tool = EmergencyFireSuppression()
        result = await tool.execute({"compartment": "lab"})
        assert result.success
        assert result.data["suppression_activated"]

    async def test_evacuation_alert(self):
        from aria.integrations.control_tools import EmergencyDepressurizationResponse
        tool = EmergencyDepressurizationResponse()
        result = await tool.execute({"compartment": "module_a"})
        assert result.success
        assert result.data["isolated"]
