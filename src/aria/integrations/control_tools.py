"""Control, Emergency, Diagnostic, and Planning tools per CENTRAL_AI_MASTER_PLAN Part 5.

These are spacecraft-side tools that interact with hardware via the HAL.
In simulation mode, they return simulated results.

Tools implemented:
  Control:
    - read_sensor (Tool 4)
    - get_subsystem_state (Tool 5)
    - eps_set_heater (Tool 6)
    - eps_load_shed (Tool 7)
    - propulsion_fire_thruster (Tool 9)
  Communication:
    - comms_send_to_ground (Tool 17)
    - comms_get_link_status (Tool 18)
  Emergency:
    - emergency_safe_mode (Tool 28)
    - emergency_depressurization_response (Tool 29)
    - emergency_fire_suppression (Tool 46)
  Diagnostic:
    - diagnostic_run_subsystem_test (Tool 26)
  Planning:
    - planning_schedule_activity (Tool 31)
  Crew:
    - crew_alert (Tool 23)
    - crew_get_status (Tool 24)
"""

from __future__ import annotations

from typing import Any

from aria.core.tool import ARIATool, ToolResult, ValidationResult
from aria.core.types import AuthorityLevel, SafetyLevel, ToolCategory


# ---------------------------------------------------------------------------
# Control Tools
# ---------------------------------------------------------------------------

class ReadSensor(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    """Read current value from a specific sensor via the HAL."""

    name = "read_sensor"
    description = "Read current value from a sensor. Returns engineering-unit value with timestamp and quality flag."
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    timeout_ms = 500

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sensor_id": {"type": "string", "description": "Unique sensor identifier"},
                "include_raw": {"type": "boolean", "default": False},
            },
            "required": ["sensor_id"],
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("sensor_id"):
            return ValidationResult(valid=False, message="sensor_id is required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        # Simulated response — in production, this calls the HAL
        return ToolResult(success=True, data={
            "sensor_id": params["sensor_id"],
            "value": 0.0,
            "unit": "unknown",
            "quality": "GOOD",
            "timestamp": "",
        })


class GetSubsystemState(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    """Get complete current state of a subsystem."""

    name = "get_subsystem_state"
    description = "Get complete state of a subsystem: sensors, actuators, anomalies."
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    timeout_ms = 2000

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subsystem": {
                    "type": "string",
                    "enum": ["eps", "adcs", "thermal", "propulsion", "comms", "eclss", "navigation", "science"],
                },
                "detail_level": {"type": "string", "enum": ["summary", "standard", "detailed"], "default": "standard"},
            },
            "required": ["subsystem"],
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("subsystem"):
            return ValidationResult(valid=False, message="subsystem is required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "subsystem": params["subsystem"],
            "status": "NOMINAL",
            "sensors": {},
            "actuators": {},
            "anomalies": [],
        })


class EpsSetHeater(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    """Set heater power for a thermal zone."""

    name = "eps_set_heater"
    description = "Set heater power for a thermal zone. Requires AI_WITH_LOG authority."
    category = ToolCategory.POWER
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.REVERSIBLE
    timeout_ms = 1000

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "zone_id": {"type": "string"},
                "power_watts": {"type": "number", "minimum": 0},
                "mode": {"type": "string", "enum": ["manual", "pid_setpoint", "off"]},
            },
            "required": ["zone_id", "power_watts"],
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("zone_id"):
            return ValidationResult(valid=False, message="zone_id is required")
        if params.get("power_watts", 0) < 0:
            return ValidationResult(valid=False, message="power_watts must be >= 0")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "zone_id": params["zone_id"],
            "power_watts": params["power_watts"],
            "mode": params.get("mode", "manual"),
            "applied": True,
        })


class EpsLoadShed(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    """Shed loads according to priority table."""

    name = "eps_load_shed"
    description = "Shed loads when power budget is insufficient. IRREVERSIBLE within shed cycle."
    category = ToolCategory.POWER
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.REVERSIBLE
    timeout_ms = 5000

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "shed_amount_watts": {"type": "number", "minimum": 0},
                "min_priority": {"type": "integer", "minimum": 1, "maximum": 6},
                "reason": {"type": "string"},
            },
            "required": ["shed_amount_watts", "reason"],
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("reason"):
            return ValidationResult(valid=False, message="reason is required for load shed")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "shed_amount_watts": params["shed_amount_watts"],
            "loads_shed": ["experiments", "non_essential_lighting"],
            "actual_shed_watts": params["shed_amount_watts"],
        })


class PropulsionFireThruster(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    """Fire a thruster — IRREVERSIBLE, consumes fuel."""

    name = "propulsion_fire_thruster"
    description = "Fire a thruster for specified duration. IRREVERSIBLE: consumes fuel."
    category = ToolCategory.PROPULSION
    authority_level = AuthorityLevel.CAPTAIN_ONLY
    safety_level = SafetyLevel.IRREVERSIBLE
    timeout_ms = 65000

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "thruster_id": {"type": "string"},
                "duration_ms": {"type": "integer", "minimum": 10, "maximum": 60000},
                "thrust_level_pct": {"type": "number", "minimum": 0, "maximum": 100},
                "reason": {"type": "string"},
                "approved_maneuver_id": {"type": "string"},
            },
            "required": ["thruster_id", "duration_ms", "thrust_level_pct", "reason"],
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("thruster_id"):
            return ValidationResult(valid=False, message="thruster_id is required")
        if not params.get("reason"):
            return ValidationResult(valid=False, message="reason is required for thruster firing")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "thruster_id": params["thruster_id"],
            "fired": True,
            "duration_ms": params["duration_ms"],
            "estimated_dv_ms": 0.1,
        })


# ---------------------------------------------------------------------------
# Communication Tools
# ---------------------------------------------------------------------------

class CommsSendToGround(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    """Send a message or data to ground control."""

    name = "comms_send_to_ground"
    description = "Send message to ground control. Queued if no current contact."
    category = ToolCategory.COMMUNICATION
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.IRREVERSIBLE
    timeout_ms = 10000

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message_type": {"type": "string", "enum": ["telemetry", "event", "science_data", "crew_message", "emergency"]},
                "priority": {"type": "string", "enum": ["LOW", "NORMAL", "HIGH", "EMERGENCY"]},
                "data": {"type": "string"},
                "compress": {"type": "boolean", "default": True},
            },
            "required": ["message_type", "data"],
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("data"):
            return ValidationResult(valid=False, message="data is required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "queued": True,
            "message_type": params["message_type"],
            "priority": params.get("priority", "NORMAL"),
            "size_bytes": len(params["data"].encode()),
        })


class CommsGetLinkStatus(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    """Get current communication link status."""

    name = "comms_get_link_status"
    description = "Get current link status: margin, data rate, next contact window."
    category = ToolCategory.COMMUNICATION
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    timeout_ms = 1000

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "link_active": True,
            "signal_dbm": -85.0,
            "snr_db": 15.0,
            "data_rate_kbps": 256.0,
            "next_contact_window": "",
            "queue_depth": 0,
        })


# ---------------------------------------------------------------------------
# Emergency Tools
# ---------------------------------------------------------------------------

class EmergencySafeMode(ARIATool):
    """Enter safe mode — the most critical tool."""

    name = "emergency_safe_mode"
    description = "Enter safe mode at specified level. Overrides all other operations."
    category = ToolCategory.EMERGENCY
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.REVERSIBLE
    timeout_ms = 1000

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "level": {"type": "integer", "minimum": 1, "maximum": 4},
                "affected_subsystem": {"type": "string"},
                "reason": {"type": "string"},
                "auto_recovery": {"type": "boolean", "default": True},
            },
            "required": ["level", "reason"],
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if "level" not in params:
            return ValidationResult(valid=False, message="level is required")
        if not params.get("reason"):
            return ValidationResult(valid=False, message="reason is required for safe mode")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        # Recovery audit R-7: previously this returned success=True
        # without publishing anything, so the LLM could "enter safe
        # mode" while SafeModeManager.current_level remained NOMINAL.
        # Now publishes ``aria.safety.request_safe_mode`` which the
        # coordinator picks up at coordinator.py:_on_safe_mode_request
        # and translates to a real SafeModeManager.transition().
        from aria.safety.safe_mode import (
            SafeLevel, get_safe_mode_singleton,
        )
        level_int = int(params["level"])
        try:
            target_level = SafeLevel(min(4, max(1, level_int)))
        except ValueError:
            target_level = SafeLevel.MONITORING_ONLY
        sm = get_safe_mode_singleton()
        if sm is None:
            return ToolResult(success=False, data={
                "level": level_int,
                "activated": False,
                "error": "no_safe_mode_singleton — coordinator not initialised",
            })
        # force_level is thread-safe and works from any caller (LLM
        # tool callbacks may run on the loop or off it).
        sm.force_level(target_level,
                       reason=str(params.get("reason", "tool:emergency_safe_mode")))
        return ToolResult(success=True, data={
            "level": target_level.value,
            "level_name": target_level.name,
            "activated": True,
            "affected_subsystem": params.get("affected_subsystem", "all"),
            "auto_recovery": params.get("auto_recovery", True),
            "current_level": sm.current_level.name,
        })


class EmergencyDepressurizationResponse(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    """Execute depressurization emergency response."""

    name = "emergency_depressurization_response"
    description = "Isolate compartment, alert crew, activate emergency air."
    category = ToolCategory.EMERGENCY
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.REVERSIBLE
    timeout_ms = 500

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "compartment": {"type": "string"},
                "leak_rate_kpa_per_min": {"type": "number"},
                "crew_in_compartment": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["compartment"],
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("compartment"):
            return ValidationResult(valid=False, message="compartment is required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "compartment": params["compartment"],
            "isolated": True,
            "crew_alerted": True,
            "emergency_air_activated": True,
        })


class EmergencyFireSuppression(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    """Activate fire suppression in a compartment."""

    name = "emergency_fire_suppression"
    description = "Activate fire suppression system in specified compartment."
    category = ToolCategory.EMERGENCY
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.IRREVERSIBLE
    timeout_ms = 500

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "compartment": {"type": "string"},
                "agent_type": {"type": "string", "enum": ["co2", "halon", "water_mist"], "default": "co2"},
            },
            "required": ["compartment"],
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("compartment"):
            return ValidationResult(valid=False, message="compartment is required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "compartment": params["compartment"],
            "suppression_activated": True,
            "agent_type": params.get("agent_type", "co2"),
        })


# ---------------------------------------------------------------------------
# Diagnostic Tools
# ---------------------------------------------------------------------------

class DiagnosticRunSubsystemTest(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    """Run built-in self-test (BIST) for a subsystem."""

    name = "diagnostic_run_subsystem_test"
    description = "Run BIST for a subsystem. Returns pass/fail with details."
    category = ToolCategory.DIAGNOSTIC
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.READ_ONLY
    timeout_ms = 300000

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subsystem": {"type": "string"},
                "test_level": {"type": "string", "enum": ["quick", "standard", "comprehensive"]},
                "non_intrusive": {"type": "boolean", "default": True},
            },
            "required": ["subsystem"],
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("subsystem"):
            return ValidationResult(valid=False, message="subsystem is required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "subsystem": params["subsystem"],
            "test_level": params.get("test_level", "quick"),
            "result": "PASS",
            "tests_run": 12,
            "tests_passed": 12,
            "tests_failed": 0,
            "details": [],
        })


# ---------------------------------------------------------------------------
# Planning Tools
# ---------------------------------------------------------------------------

class PlanningScheduleActivity(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    """Schedule an activity in the mission timeline."""

    name = "planning_schedule_activity"
    description = "Schedule an activity with resource requirements and constraints."
    category = ToolCategory.PLANNING
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.REVERSIBLE
    timeout_ms = 5000

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "activity_name": {"type": "string"},
                "start_time": {"type": "string"},
                "duration_minutes": {"type": "integer"},
                "priority": {"type": "integer", "minimum": 1, "maximum": 10},
                "resources_required": {"type": "object"},
            },
            "required": ["activity_name", "start_time", "duration_minutes"],
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("activity_name"):
            return ValidationResult(valid=False, message="activity_name is required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "scheduled": True,
            "activity_name": params["activity_name"],
            "start_time": params["start_time"],
            "duration_minutes": params["duration_minutes"],
            "conflicts": [],
        })


# ---------------------------------------------------------------------------
# Crew Tools
# ---------------------------------------------------------------------------

class CrewAlert(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    """Send an alert to crew members."""

    name = "crew_alert"
    description = "Send alert to specific crew members or all crew."
    category = ToolCategory.DIAGNOSTIC
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.READ_ONLY
    timeout_ms = 2000

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "recipients": {"type": "array", "items": {"type": "string"}},
                "priority": {"type": "string", "enum": ["INFO", "CAUTION", "WARNING", "EMERGENCY"]},
                "message": {"type": "string"},
                "audio_alarm": {"type": "boolean", "default": False},
                "require_acknowledgment": {"type": "boolean", "default": False},
            },
            "required": ["recipients", "priority", "message"],
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("recipients"):
            return ValidationResult(valid=False, message="recipients is required")
        if not params.get("message"):
            return ValidationResult(valid=False, message="message is required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "sent": True,
            "recipients": params["recipients"],
            "priority": params["priority"],
            "audio_alarm": params.get("audio_alarm", False),
        })


class CrewGetStatus(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    """Get current status of crew members."""

    name = "crew_get_status"
    description = "Get crew status: location, activity, health metrics, fatigue."
    category = ToolCategory.DIAGNOSTIC
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    timeout_ms = 1000

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "crew": [
                {"name": "Commander", "location": "flight_deck", "activity": "monitoring", "fatigue": "low"},
                {"name": "Pilot", "location": "flight_deck", "activity": "navigation", "fatigue": "low"},
                {"name": "Mission Specialist 1", "location": "lab", "activity": "experiment", "fatigue": "medium"},
                {"name": "Mission Specialist 2", "location": "crew_quarters", "activity": "rest", "fatigue": "none"},
            ],
            "crew_count": 4,
        })


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

ALL_CONTROL_TOOLS = [
    ReadSensor,
    GetSubsystemState,
    EpsSetHeater,
    EpsLoadShed,
    PropulsionFireThruster,
    CommsSendToGround,
    CommsGetLinkStatus,
    EmergencySafeMode,
    EmergencyDepressurizationResponse,
    EmergencyFireSuppression,
    DiagnosticRunSubsystemTest,
    PlanningScheduleActivity,
    CrewAlert,
    CrewGetStatus,
]
