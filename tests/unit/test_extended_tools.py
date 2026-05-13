"""Tests for extended tools (master plan tools 33-52)."""

from __future__ import annotations

import pytest

from aria.integrations.extended_tools import ALL_EXTENDED_TOOLS
from aria.tools.registry import ToolRegistry


class TestExtendedToolRegistration:
    def test_all_extended_tools_register(self):
        """All 30 extended tools register without conflicts."""
        reg = ToolRegistry()
        for cls in ALL_EXTENDED_TOOLS:
            reg.register(cls())
        assert reg.count == len(ALL_EXTENDED_TOOLS)

    def test_unique_names(self):
        names = [cls().name for cls in ALL_EXTENDED_TOOLS]
        assert len(names) == len(set(names)), f"Duplicate tool names: {[n for n in names if names.count(n) > 1]}"


class TestFullToolRegistry:
    def test_all_55_tools_register(self):
        """Complete ARIA tool registry: all 55 tools register."""
        from aria.integrations.dsremo.tools import (
            DsremoQueryAnomalies, DsremoIngestTelemetry, DsremoGetChannels,
            DsremoIngestBatch, DsremoGetChannelHealth, DsremoGetAnomalyScore,
        )
        from aria.integrations.conjunction_watch.tools import (
            ConjunctionWatchRunScreening, ConjunctionWatchGetHighRisk, ConjunctionWatchPlanManeuver,
        )
        from aria.integrations.genastra.tools import (
            GenAstraAnalyzeBiosignature, GenAstraCrewRadiationDose,
        )
        from aria.integrations.control_tools import ALL_CONTROL_TOOLS

        reg = ToolRegistry()
        for cls in [
            DsremoQueryAnomalies, DsremoIngestTelemetry, DsremoGetChannels,
            DsremoIngestBatch, DsremoGetChannelHealth, DsremoGetAnomalyScore,
            ConjunctionWatchRunScreening, ConjunctionWatchGetHighRisk, ConjunctionWatchPlanManeuver,
            GenAstraAnalyzeBiosignature, GenAstraCrewRadiationDose,
        ]:
            reg.register(cls())
        for cls in ALL_CONTROL_TOOLS:
            reg.register(cls())
        for cls in ALL_EXTENDED_TOOLS:
            reg.register(cls())

        assert reg.count == 55, f"Expected 55 tools, got {reg.count}"


class TestKeyToolValidation:
    async def test_orbit_propagation_requires_time(self):
        from aria.integrations.extended_tools import NavigationPropagateOrbit
        tool = NavigationPropagateOrbit()
        assert not tool.validate_input({}).valid
        assert tool.validate_input({"target_time": "2026-04-06T12:00:00Z"}).valid

    async def test_adcs_slew_requires_quaternion(self):
        from aria.integrations.extended_tools import AdcsSlewToAttitude
        tool = AdcsSlewToAttitude()
        assert not tool.validate_input({}).valid
        assert tool.validate_input({"target_quaternion": {"q0": 1, "q1": 0, "q2": 0, "q3": 0}}).valid

    async def test_collision_avoidance_requires_event(self):
        from aria.integrations.extended_tools import EmergencyCollisionAvoidance
        tool = EmergencyCollisionAvoidance()
        assert not tool.validate_input({}).valid
        result = await tool.execute({"event_id": "EVT-001"})
        assert result.success
        assert result.data["maneuver_executed"]

    async def test_gene_expression_requires_sample(self):
        from aria.integrations.extended_tools import GenAstraGeneExpression
        tool = GenAstraGeneExpression()
        assert not tool.validate_input({}).valid
        result = await tool.execute({"sample_id": "S001", "analysis_type": "deseq2"})
        assert result.success
        assert result.data["differentially_expressed_genes"] > 0

    async def test_eclss_o2_rate_validation(self):
        from aria.integrations.extended_tools import EclssSetO2Rate
        tool = EclssSetO2Rate()
        assert not tool.validate_input({"rate_liters_per_hour": -1}).valid
        assert tool.validate_input({"rate_liters_per_hour": 50}).valid


class TestNavigationTools:
    async def test_orbit_state(self):
        from aria.integrations.extended_tools import NavigationGetOrbitState
        tool = NavigationGetOrbitState()
        result = await tool.execute({"frame": "ECI_J2000"})
        assert result.success
        assert "position_km" in result.data

    async def test_orbit_propagation(self):
        from aria.integrations.extended_tools import NavigationPropagateOrbit
        tool = NavigationPropagateOrbit()
        result = await tool.execute({"target_time": "2026-04-07T12:00:00Z"})
        assert result.success

    async def test_fleet_risk(self):
        from aria.integrations.extended_tools import ConjwatchFleetRisk
        tool = ConjwatchFleetRisk()
        result = await tool.execute({})
        assert result.success
        assert result.data["fleet_risk_score"] >= 0


class TestScienceTools:
    async def test_radiation_damage(self):
        from aria.integrations.extended_tools import GenAstraRadiationDamage
        tool = GenAstraRadiationDamage()
        result = await tool.execute({"sample_type": "dna", "dose_gy": 1.5})
        assert result.success
        assert result.data["survival_fraction"] > 0

    async def test_air_quality(self):
        from aria.integrations.extended_tools import GenAstraAirQuality
        tool = GenAstraAirQuality()
        result = await tool.execute({})
        assert result.success
        assert result.data["quality"] == "NOMINAL"

    async def test_protein_structure(self):
        from aria.integrations.extended_tools import GenAstraProteinStructure
        tool = GenAstraProteinStructure()
        result = await tool.execute({"sequence": "MKFLILLFNILCLFPVLAADNH"})
        assert result.success
        assert result.data["num_residues"] == 22


class TestPlanningTools:
    async def test_resource_forecast(self):
        from aria.integrations.extended_tools import PlanningResourceForecast
        tool = PlanningResourceForecast()
        result = await tool.execute({"hours_ahead": 48})
        assert result.success
        assert result.data["hours_ahead"] == 48

    async def test_optimize_schedule(self):
        from aria.integrations.extended_tools import PlanningOptimizeSchedule
        tool = PlanningOptimizeSchedule()
        result = await tool.execute({})
        assert result.success
        assert result.data["optimized"]


class TestLearningTools:
    async def test_calibrate_sensor(self):
        from aria.integrations.extended_tools import LearningCalibrateSensor
        tool = LearningCalibrateSensor()
        result = await tool.execute({"sensor_id": "thermal.battery_pack", "calibration_type": "span"})
        assert result.success
        assert result.data["calibrated"]


class TestEmergencyExtendedTools:
    async def test_collision_avoidance(self):
        from aria.integrations.extended_tools import EmergencyCollisionAvoidance
        tool = EmergencyCollisionAvoidance()
        result = await tool.execute({"event_id": "EVT-999"})
        assert result.success
        assert result.data["maneuver_executed"]

    async def test_evacuation_alert(self):
        from aria.integrations.extended_tools import EmergencyEvacuationAlert
        tool = EmergencyEvacuationAlert()
        result = await tool.execute({"compartment": "hab", "reason": "fire"})
        assert result.success
        assert result.data["alert_issued"]


class TestCrewExtendedTools:
    async def test_intercom(self):
        from aria.integrations.extended_tools import CrewIntercom
        tool = CrewIntercom()
        result = await tool.execute({"message_text": "Prepare for maneuver", "urgency": "attention"})
        assert result.success
        assert result.data["broadcast"]

    async def test_medical_alert(self):
        from aria.integrations.extended_tools import CrewMedicalAlert
        tool = CrewMedicalAlert()
        result = await tool.execute({"crew_member": "pilot", "condition": "cardiac"})
        assert result.success
        assert result.data["alert_issued"]


class TestDsremoWebSocketTools:
    async def test_subscribe(self):
        from aria.integrations.dsremo.websocket_tool import DsremoWebSocketSubscribe
        tool = DsremoWebSocketSubscribe()
        result = await tool.execute({"min_severity": "WARNING"})
        assert result.success
        assert result.data["subscribed"]
        assert result.data["min_severity"] == "WARNING"

    async def test_unsubscribe(self):
        from aria.integrations.dsremo.websocket_tool import DsremoWebSocketUnsubscribe
        tool = DsremoWebSocketUnsubscribe()
        result = await tool.execute({})
        assert result.success
        assert result.data["unsubscribed"]


class TestDsremoConfigureDetector:
    async def test_configure(self):
        from aria.integrations.extended_tools import DsremoConfigureDetector
        tool = DsremoConfigureDetector()
        assert tool.validate_input({"detector": "CUSUM", "parameter": "h", "value": 5.0}).valid
        result = await tool.execute({"detector": "CUSUM", "parameter": "h", "value": 5.0})
        assert result.success
        assert result.data["applied"]

    async def test_validation(self):
        from aria.integrations.extended_tools import DsremoConfigureDetector
        tool = DsremoConfigureDetector()
        assert not tool.validate_input({}).valid
