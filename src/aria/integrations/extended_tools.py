"""Extended tools per CENTRAL_AI_MASTER_PLAN Part 5, Tools 33-52.

These complete the 52-tool registry. Each tool follows the same pattern:
input_schema, validate_input, execute with simulated response.

Tools:
  Navigation: navigation_get_orbit_state (15), navigation_propagate_orbit (16),
              conjwatch_compute_pc (12), conjwatch_generate_cdm (14),
              navigation_orbit_determination (42), conjwatch_fleet_risk (37)
  Control: adcs_slew_to_attitude (8), adcs_desaturate_wheels (34),
           eclss_set_o2_rate (10)
  Communication: comms_point_antenna (33), comms_store_and_forward (43)
  Science: genastra_radiation_damage (20), genastra_gene_expression (21),
           genastra_protein_structure (22), genastra_air_quality (39),
           science_schedule_observation (44)
  Diagnostic: thermal_predict_temperature (35), eps_get_power_budget (36),
              diagnostic_radiation_check (45), diagnostic_memory_scrub (27)
  Emergency: emergency_collision_avoidance (30), emergency_evacuation_alert (47)
  Crew: crew_intercom (25), crew_schedule_update (40), crew_medical_alert (41)
  Learning: learning_update_model (48), learning_calibrate_sensor (49)
  Planning: planning_optimize_schedule (32), planning_resource_forecast (50)
"""

from __future__ import annotations

from typing import Any

from aria.core.tool import ARIATool, ToolResult, ValidationResult
from aria.core.types import AuthorityLevel, SafetyLevel, ToolCategory


# ---------------------------------------------------------------------------
# Navigation Tools
# ---------------------------------------------------------------------------

class NavigationGetOrbitState(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "navigation_get_orbit_state"
    description = "Get current orbit state vector (position, velocity) in ECI frame."
    category = ToolCategory.NAVIGATION
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "frame": {"type": "string", "enum": ["ECI_J2000", "ECEF", "LVLH"]},
            "include_covariance": {"type": "boolean", "default": False},
        }}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "frame": params.get("frame", "ECI_J2000"),
            "position_km": [6778.0, 0.0, 0.0],
            "velocity_kms": [0.0, 7.66, 0.0],
            "epoch": "",
        })


class NavigationPropagateOrbit(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "navigation_propagate_orbit"
    description = "Propagate orbit to future time using SGP4/SDP4."
    category = ToolCategory.NAVIGATION
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "target_time": {"type": "string"},
            "propagator": {"type": "string", "enum": ["sgp4", "sdp4", "numerical"]},
        }, "required": ["target_time"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("target_time"):
            return ValidationResult(valid=False, message="target_time required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "target_time": params["target_time"],
            "position_km": [6778.0, 0.0, 0.0],
            "velocity_kms": [0.0, 7.66, 0.0],
        })


class ConjwatchComputePc(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "conjwatch_compute_pc"
    description = "Compute collision probability using Foster (2D), Chan (3D), or Monte Carlo."
    category = ToolCategory.NAVIGATION
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "event_id": {"type": "string"},
            "methods": {"type": "array", "items": {"type": "string"}},
            "monte_carlo_samples": {"type": "integer", "default": 10000},
        }, "required": ["event_id"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("event_id"):
            return ValidationResult(valid=False, message="event_id required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "event_id": params["event_id"],
            "pc_foster": 1.2e-5, "pc_chan": 1.5e-5,
            "miss_distance_m": 850.0, "relative_velocity_ms": 14200.0,
        })


class ConjwatchGenerateCdm(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "conjwatch_generate_cdm"
    description = "Generate Conjunction Data Message per CCSDS 508.0-B-2."
    category = ToolCategory.NAVIGATION
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "event_id": {"type": "string"},
            "format": {"type": "string", "enum": ["xml", "kvn", "json"]},
        }, "required": ["event_id"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("event_id"):
            return ValidationResult(valid=False, message="event_id required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "event_id": params["event_id"],
            "format": params.get("format", "xml"),
            "cdm_generated": True,
        })


class NavigationOrbitDetermination(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "navigation_orbit_determination"
    description = "Run orbit determination filter from tracking data."
    category = ToolCategory.NAVIGATION
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"converged": True, "residual_rms_m": 5.2})


class ConjwatchFleetRisk(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "conjwatch_fleet_risk"
    description = "Run fleet-wide conjunction risk analysis."
    category = ToolCategory.NAVIGATION
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"fleet_risk_score": 0.02, "high_risk_events": 0})


# ---------------------------------------------------------------------------
# Control Tools
# ---------------------------------------------------------------------------

class AdcsSlewToAttitude(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "adcs_slew_to_attitude"
    description = "Command ADCS to slew to target attitude quaternion."
    category = ToolCategory.NAVIGATION
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.REVERSIBLE

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "target_quaternion": {"type": "object"},
            "slew_rate_dps": {"type": "number", "default": 0.5},
        }, "required": ["target_quaternion"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("target_quaternion"):
            return ValidationResult(valid=False, message="target_quaternion required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"slew_started": True, "estimated_time_s": 120})


class AdcsDesaturateWheels(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "adcs_desaturate_wheels"
    description = "Initiate reaction wheel momentum desaturation."
    category = ToolCategory.NAVIGATION
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.REVERSIBLE

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"desaturation_started": True})


class EclssSetO2Rate(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "eclss_set_o2_rate"
    description = "Adjust O2 generation rate."
    category = ToolCategory.LIFE_SUPPORT
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.REVERSIBLE

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "rate_liters_per_hour": {"type": "number", "minimum": 0, "maximum": 100},
            "reason": {"type": "string"},
        }, "required": ["rate_liters_per_hour"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        rate = params.get("rate_liters_per_hour", -1)
        if rate < 0 or rate > 100:
            return ValidationResult(valid=False, message="rate must be 0-100")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "rate_liters_per_hour": params["rate_liters_per_hour"],
            "applied": True,
        })


# ---------------------------------------------------------------------------
# Communication Tools
# ---------------------------------------------------------------------------

class CommsPointAntenna(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "comms_point_antenna"
    description = "Point high-gain antenna to target."
    category = ToolCategory.COMMUNICATION
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.REVERSIBLE

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "target": {"type": "string", "enum": ["ground_station", "relay_satellite", "stow"]},
            "azimuth_deg": {"type": "number"},
            "elevation_deg": {"type": "number"},
        }, "required": ["target"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("target"):
            return ValidationResult(valid=False, message="target required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"target": params["target"], "pointing": True})


class CommsStoreAndForward(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "comms_store_and_forward"
    description = "Manage store-and-forward buffer for delayed relay."
    category = ToolCategory.COMMUNICATION
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.REVERSIBLE

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["status", "flush", "prioritize"]},
        }}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "buffer_size_mb": 128.5, "messages_queued": 42, "oldest_hours": 2.3,
        })


# ---------------------------------------------------------------------------
# Science Tools
# ---------------------------------------------------------------------------

class GenAstraRadiationDamage(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "genastra_radiation_damage"
    description = "Model radiation damage using ESM-2 fine-tuned model with LET/RBE."
    category = ToolCategory.SCIENCE
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "sample_type": {"type": "string", "enum": ["protein", "dna", "cell_culture", "crew_tissue"]},
            "dose_gy": {"type": "number"},
            "radiation_type": {"type": "string", "enum": ["proton", "heavy_ion", "gamma", "mixed"]},
        }, "required": ["sample_type", "dose_gy"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("sample_type"):
            return ValidationResult(valid=False, message="sample_type required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "damage_score": 0.15, "survival_fraction": 0.85,
            "repair_probability": 0.72,
        })


class GenAstraGeneExpression(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "genastra_gene_expression"
    description = "Run gene expression analysis (DESeq2, GSEA) on biological samples."
    category = ToolCategory.SCIENCE
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "sample_id": {"type": "string"},
            "analysis_type": {"type": "string", "enum": ["deseq2", "gsea", "both"]},
        }, "required": ["sample_id", "analysis_type"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("sample_id"):
            return ValidationResult(valid=False, message="sample_id required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "sample_id": params["sample_id"],
            "differentially_expressed_genes": 42,
            "top_pathways": ["DNA_REPAIR", "OXIDATIVE_STRESS"],
        })


class GenAstraProteinStructure(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "genastra_protein_structure"
    description = "Predict protein structure using ESMFold. Returns 3D coords + confidence."
    category = ToolCategory.SCIENCE
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "sequence": {"type": "string"},
        }, "required": ["sequence"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("sequence"):
            return ValidationResult(valid=False, message="sequence required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "plddt_mean": 0.85, "num_residues": len(params.get("sequence", "")),
            "structure_predicted": True,
        })


class GenAstraAirQuality(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "genastra_air_quality_analysis"
    description = "Analyze air quality for biological contaminants."
    category = ToolCategory.SCIENCE
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "quality": "NOMINAL", "contaminants_detected": [],
            "particulate_ug_m3": 12.5,
        })


class ScienceScheduleObservation(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "science_schedule_observation"
    description = "Schedule a science observation campaign."
    category = ToolCategory.SCIENCE
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.REVERSIBLE

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "target": {"type": "string"},
            "instrument": {"type": "string"},
            "start_time": {"type": "string"},
            "duration_minutes": {"type": "integer"},
        }, "required": ["target", "instrument"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("target"):
            return ValidationResult(valid=False, message="target required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"scheduled": True, "target": params["target"]})


# ---------------------------------------------------------------------------
# Diagnostic Tools
# ---------------------------------------------------------------------------

class ThermalPredictTemperature(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "thermal_predict_temperature"
    description = "Predict future temperature using thermal model."
    category = ToolCategory.DIAGNOSTIC
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "zone": {"type": "string"},
            "hours_ahead": {"type": "number", "default": 1.0},
        }, "required": ["zone"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("zone"):
            return ValidationResult(valid=False, message="zone required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "zone": params["zone"],
            "predicted_temperature_c": 24.5,
            "hours_ahead": params.get("hours_ahead", 1.0),
            "confidence": 0.92,
        })


class EpsGetPowerBudget(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "eps_get_power_budget"
    description = "Get detailed power budget: generation, consumption, margin."
    category = ToolCategory.POWER
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "generation_w": 2500.0, "consumption_w": 1800.0,
            "margin_w": 700.0, "battery_soc_percent": 85.0,
            "eclipse_in_minutes": 45.0,
        })


class DiagnosticRadiationCheck(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "diagnostic_radiation_check"
    description = "Check radiation environment and dose rates."
    category = ToolCategory.DIAGNOSTIC
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "dose_rate_usv_hr": 0.5,
            "cumulative_dose_msv": 25.0,
            "environment": "NOMINAL",
            "trapped_particle_flux": "LOW",
        })


class DiagnosticMemoryScrub(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "diagnostic_memory_scrub"
    description = "Trigger memory scrub to detect/correct radiation-induced bit errors."
    category = ToolCategory.DIAGNOSTIC
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "memory_bank": {"type": "string", "enum": ["main", "backup", "model_store", "all"]},
            "priority": {"type": "string", "enum": ["background", "immediate"]},
        }}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "memory_bank": params.get("memory_bank", "all"),
            "errors_found": 0, "errors_corrected": 0, "scrub_complete": True,
        })


# ---------------------------------------------------------------------------
# Emergency Tools
# ---------------------------------------------------------------------------

class EmergencyCollisionAvoidance(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "emergency_collision_avoidance"
    description = "Execute emergency collision avoidance maneuver (short TCA)."
    category = ToolCategory.EMERGENCY
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.IRREVERSIBLE

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "event_id": {"type": "string"},
            "max_dv_ms": {"type": "number", "default": 5.0},
        }, "required": ["event_id"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("event_id"):
            return ValidationResult(valid=False, message="event_id required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "event_id": params["event_id"],
            "maneuver_executed": True,
            "dv_ms": 1.2,
            "new_pc": 1e-8,
        })


class EmergencyEvacuationAlert(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "emergency_evacuation_alert"
    description = "Trigger compartment evacuation alert."
    category = ToolCategory.EMERGENCY
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.REVERSIBLE

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "compartment": {"type": "string"},
            "reason": {"type": "string"},
        }, "required": ["compartment", "reason"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("compartment"):
            return ValidationResult(valid=False, message="compartment required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "compartment": params["compartment"],
            "alert_issued": True,
            "hatches_sealed": True,
        })


# ---------------------------------------------------------------------------
# Crew Tools
# ---------------------------------------------------------------------------

class CrewIntercom(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "crew_intercom"
    description = "Broadcast voice message over intercom (TTS synthesis)."
    category = ToolCategory.DIAGNOSTIC
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "zones": {"type": "array", "items": {"type": "string"}},
            "message_text": {"type": "string"},
            "urgency": {"type": "string", "enum": ["normal", "attention", "emergency"]},
        }, "required": ["message_text"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("message_text"):
            return ValidationResult(valid=False, message="message_text required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "broadcast": True,
            "zones": params.get("zones", ["all"]),
            "urgency": params.get("urgency", "normal"),
        })


class CrewScheduleUpdate(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "crew_schedule_update"
    description = "Update crew schedule / activity assignment."
    category = ToolCategory.PLANNING
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.REVERSIBLE

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "crew_member": {"type": "string"},
            "activity": {"type": "string"},
            "start_time": {"type": "string"},
            "duration_minutes": {"type": "integer"},
        }, "required": ["crew_member", "activity"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("crew_member"):
            return ValidationResult(valid=False, message="crew_member required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "updated": True,
            "crew_member": params["crew_member"],
            "activity": params["activity"],
        })


class CrewMedicalAlert(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "crew_medical_alert"
    description = "Trigger medical alert with vital signs for a crew member."
    category = ToolCategory.EMERGENCY
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "crew_member": {"type": "string"},
            "condition": {"type": "string"},
            "vital_signs": {"type": "object"},
        }, "required": ["crew_member", "condition"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("crew_member"):
            return ValidationResult(valid=False, message="crew_member required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "alert_issued": True,
            "crew_member": params["crew_member"],
            "medical_officer_notified": True,
        })


# ---------------------------------------------------------------------------
# Learning Tools
# ---------------------------------------------------------------------------

class LearningUpdateModel(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "learning_update_model"
    description = "Update an on-board ML model with new training data."
    category = ToolCategory.DIAGNOSTIC
    authority_level = AuthorityLevel.CAPTAIN_ONLY
    safety_level = SafetyLevel.REVERSIBLE

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "model_name": {"type": "string"},
            "update_source": {"type": "string", "enum": ["ground_upload", "on_board_data"]},
            "validation_required": {"type": "boolean", "default": True},
        }, "required": ["model_name", "update_source"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("model_name"):
            return ValidationResult(valid=False, message="model_name required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "model_name": params["model_name"],
            "update_applied": True,
            "validation_passed": True,
        })


class LearningCalibrateSensor(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "learning_calibrate_sensor"
    description = "Run sensor calibration routine."
    category = ToolCategory.DIAGNOSTIC
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.REVERSIBLE

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "sensor_id": {"type": "string"},
            "calibration_type": {"type": "string", "enum": ["zero", "span", "full"]},
        }, "required": ["sensor_id"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("sensor_id"):
            return ValidationResult(valid=False, message="sensor_id required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "sensor_id": params["sensor_id"],
            "calibrated": True,
            "offset_applied": 0.001,
        })


# ---------------------------------------------------------------------------
# Planning Tools
# ---------------------------------------------------------------------------

class PlanningOptimizeSchedule(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "planning_optimize_schedule"
    description = "Optimize mission schedule using constraint satisfaction."
    category = ToolCategory.PLANNING
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.REVERSIBLE

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "time_horizon_hours": {"type": "number", "default": 24},
            "optimization_goal": {"type": "string", "enum": ["science_max", "resource_min", "balanced"]},
        }}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "optimized": True,
            "activities_scheduled": 15,
            "conflicts_resolved": 2,
            "utilization_percent": 78.5,
        })


class PlanningResourceForecast(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "planning_resource_forecast"
    description = "Forecast resource usage (power, fuel, data, crew time)."
    category = ToolCategory.PLANNING
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "hours_ahead": {"type": "number", "default": 24},
        }}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "hours_ahead": params.get("hours_ahead", 24),
            "power_margin_w": 500.0,
            "fuel_margin_kg": 85.0,
            "data_volume_mb": 2500.0,
            "crew_hours_available": 32.0,
        })


# ---------------------------------------------------------------------------
# Dsremo Extended Tools
# ---------------------------------------------------------------------------

class DsremoConfigureDetector(ARIATool):
    # Pass 4 F9.5 — advisory only (no bus publish / no actuator).
    effect = "advisory"
    name = "dsremo_configure_detector"
    description = "Adjust Dsremo detector parameters (thresholds, windows)."
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.SUPERVISED
    safety_level = SafetyLevel.REVERSIBLE

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "detector": {"type": "string"},
            "parameter": {"type": "string"},
            "value": {"type": "number"},
        }, "required": ["detector", "parameter", "value"]}

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("detector"):
            return ValidationResult(valid=False, message="detector required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "detector": params["detector"],
            "parameter": params["parameter"],
            "value": params["value"],
            "applied": True,
        })


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

ALL_EXTENDED_TOOLS = [
    # Navigation
    NavigationGetOrbitState, NavigationPropagateOrbit,
    ConjwatchComputePc, ConjwatchGenerateCdm,
    NavigationOrbitDetermination, ConjwatchFleetRisk,
    # Control
    AdcsSlewToAttitude, AdcsDesaturateWheels, EclssSetO2Rate,
    # Communication
    CommsPointAntenna, CommsStoreAndForward,
    # Science
    GenAstraRadiationDamage, GenAstraGeneExpression,
    GenAstraProteinStructure, GenAstraAirQuality,
    ScienceScheduleObservation,
    # Diagnostic
    ThermalPredictTemperature, EpsGetPowerBudget,
    DiagnosticRadiationCheck, DiagnosticMemoryScrub,
    # Emergency
    EmergencyCollisionAvoidance, EmergencyEvacuationAlert,
    # Crew
    CrewIntercom, CrewScheduleUpdate, CrewMedicalAlert,
    # Learning
    LearningUpdateModel, LearningCalibrateSensor,
    # Planning
    PlanningOptimizeSchedule, PlanningResourceForecast,
    # Dsremo extended
    DsremoConfigureDetector,
]
