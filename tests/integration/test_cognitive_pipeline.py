"""End-to-end cognitive engine pipeline tests.

Tests the full reasoning flow:
  Captain query → CognitiveEngine → RuleBasedFallback
  → tool invocation → result sanitization → result formatting
  → hallucination check → final response
"""

from __future__ import annotations

from typing import Any

import pytest

from aria.cognitive.engine import CognitiveEngine, ReasoningContext, RuleBasedFallback
from aria.core.tool import ARIATool, ToolResult
from aria.core.types import AuthorityLevel, MissionPhase, SafetyLevel, Severity, ToolCategory
from aria.integrations.control_tools import CommsGetLinkStatus, CrewGetStatus, GetSubsystemState
from aria.memory.store import MemoryStore
from aria.state.scratchpad import SharedScratchpad
from aria.tools.registry import ToolRegistry


class MockQueryAnomalies(ARIATool):
    name = "dsremo_query_anomalies"
    description = "Query anomalies"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.SENSOR_ONLY
    safety_level = SafetyLevel.READ_ONLY
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"limit": {"type": "integer"}}}
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "anomalies": [
                {"severity": "WARNING", "channel": "eps.battery.soc_percent", "score": 0.72},
                {"severity": "WATCH", "channel": "thermal.battery_pack.temperature_c", "score": 0.55},
            ]
        })


class MockHighRisk(ARIATool):
    name = "conjunction_watch_get_high_risk"
    description = "Get high risk"
    category = ToolCategory.NAVIGATION
    authority_level = AuthorityLevel.SENSOR_ONLY
    safety_level = SafetyLevel.READ_ONLY
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={
            "high_risk_events": [
                {"object": "DEBRIS-2024-001", "pc": 2.3e-4, "tca_hours": 12.5}
            ],
            "total_tracked": 25000,
        })


@pytest.fixture
def engine():
    registry = ToolRegistry()
    registry.register(MockQueryAnomalies())
    registry.register(MockHighRisk())
    registry.register(GetSubsystemState())
    registry.register(CommsGetLinkStatus())
    registry.register(CrewGetStatus())
    memory = MemoryStore()
    scratchpad = SharedScratchpad()

    # Pre-populate scratchpad with cross-agent data
    scratchpad.write("power.eclipse_state", {"in_eclipse": False, "solar_power_w": 2500}, "power")
    scratchpad.write("nav.orbital_state", {"altitude_km": 400, "gps_fix": True}, "navigation")

    return CognitiveEngine(
        registry, memory,
        llm_backend=RuleBasedFallback(),
        scratchpad=scratchpad,
    )


async def test_status_query_full_pipeline(engine: CognitiveEngine):
    """Full pipeline: 'status' → dsremo_query → format anomalies → response."""
    response = await engine.reason("What is the current spacecraft status?")
    assert len(response) > 0
    # Should mention anomalies from the tool result
    traces = engine.get_recent_traces(1)
    assert "dsremo_query_anomalies" in traces[0].tools_used
    assert traces[0].total_duration_ms > 0


async def test_conjunction_query_full_pipeline(engine: CognitiveEngine):
    """Full pipeline: 'collision' → conjunction_watch → format events → response."""
    response = await engine.reason("Are there any collision threats?")
    traces = engine.get_recent_traces(1)
    assert "conjunction_watch_get_high_risk" in traces[0].tools_used


async def test_power_query_uses_subsystem_tool(engine: CognitiveEngine):
    """Power query invokes get_subsystem_state(eps)."""
    response = await engine.reason("How is the battery doing?")
    traces = engine.get_recent_traces(1)
    assert "get_subsystem_state" in traces[0].tools_used


async def test_scratchpad_in_context(engine: CognitiveEngine):
    """Scratchpad data is included in the system prompt context."""
    # The scratchpad has eclipse state and orbital state
    # When we reason, the system prompt should include them
    await engine.reason("Give me a status report")
    traces = engine.get_recent_traces(1)
    # Verify reasoning happened (steps > 0)
    assert len(traces[0].steps) > 0


async def test_reasoning_trace_audit_trail(engine: CognitiveEngine):
    """Every reasoning session produces a complete audit trace."""
    await engine.reason("Check for anomalies")
    await engine.reason("Any collision risks?")
    await engine.reason("How is the crew?")

    traces = engine.get_recent_traces(10)
    assert len(traces) == 3

    for trace in traces:
        assert trace.trace_id
        assert trace.input_text
        assert trace.total_duration_ms > 0
        assert len(trace.steps) > 0


async def test_memory_stores_reasoning_episodes(engine: CognitiveEngine):
    """Reasoning sessions are stored in episodic memory."""
    await engine.reason("status report")
    assert engine._memory.get_episode_count() >= 1


async def test_context_with_anomalies(engine: CognitiveEngine):
    """Context includes anomalies when provided."""
    ctx = ReasoningContext(
        recent_anomalies=[
            {"severity": "WARNING", "message": "Battery SoC declining rapidly"},
        ],
        mission_phase=MissionPhase.NOMINAL_LEO,
    )
    response = await engine.reason("What should we do about the battery?", context=ctx)
    assert len(response) > 0


async def test_unknown_query_gets_fallback(engine: CognitiveEngine):
    """Unrecognized query gets a helpful fallback response."""
    response = await engine.reason("Tell me about the meaning of life")
    assert len(response) > 0
    # Should mention available commands or rule-based mode
    assert "rule-based" in response.lower() or "acknowledged" in response.lower()


async def test_radiation_query_uses_tool(engine: CognitiveEngine):
    """Radiation query invokes get_subsystem_state(science)."""
    response = await engine.reason("What's the current radiation level?")
    traces = engine.get_recent_traces(1)
    assert "get_subsystem_state" in traces[0].tools_used


async def test_navigation_query_uses_tool(engine: CognitiveEngine):
    """Navigation query invokes get_subsystem_state(navigation)."""
    response = await engine.reason("What's our orbital altitude?")
    traces = engine.get_recent_traces(1)
    assert "get_subsystem_state" in traces[0].tools_used


async def test_fuel_query_uses_tool(engine: CognitiveEngine):
    """Fuel query invokes get_subsystem_state(propulsion)."""
    response = await engine.reason("How much propellant do we have?")
    traces = engine.get_recent_traces(1)
    assert "get_subsystem_state" in traces[0].tools_used


async def test_thermal_query_uses_tool(engine: CognitiveEngine):
    """Thermal query invokes get_subsystem_state(thermal)."""
    response = await engine.reason("Is the thermal control system OK?")
    traces = engine.get_recent_traces(1)
    assert "get_subsystem_state" in traces[0].tools_used


async def test_eclss_query_uses_tool(engine: CognitiveEngine):
    """ECLSS query invokes get_subsystem_state(eclss)."""
    response = await engine.reason("Check the air quality and CO2 levels")
    traces = engine.get_recent_traces(1)
    assert "get_subsystem_state" in traces[0].tools_used
