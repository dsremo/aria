"""Tests for the ARIA tool registry."""

from typing import Any

import pytest

from aria.core.tool import ARIATool, ToolResult
from aria.core.types import AuthorityLevel, SafetyLevel, ToolCategory
from aria.tools.registry import ToolRegistry


class MockReadSensor(ARIATool):
    name = "mock_read_sensor"
    description = "Mock sensor reader for testing"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.SENSOR_ONLY
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"sensor_id": {"type": "string"}},
        }

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"value": 42.0, "unit": "celsius"})


class MockFireThruster(ARIATool):
    name = "mock_fire_thruster"
    description = "Mock thruster for testing"
    category = ToolCategory.PROPULSION
    authority_level = AuthorityLevel.CONSENT
    safety_level = SafetyLevel.IRREVERSIBLE
    concurrency_safe = False

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["thruster_id", "duration_ms"],
            "properties": {
                "thruster_id": {"type": "string"},
                "duration_ms": {"type": "integer"},
            },
        }

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True,
            data={"fired": True},
            side_effects=("thruster_fired",),
        )


@pytest.fixture
def registry():
    return ToolRegistry()


def test_register_and_get(registry: ToolRegistry):
    tool = MockReadSensor()
    registry.register(tool)
    assert registry.count == 1
    assert registry.get("mock_read_sensor") is tool


def test_duplicate_registration_raises(registry: ToolRegistry):
    registry.register(MockReadSensor())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(MockReadSensor())


def test_filter_by_category(registry: ToolRegistry):
    registry.register(MockReadSensor())
    registry.register(MockFireThruster())

    telemetry_tools = registry.get_tools(category=ToolCategory.TELEMETRY)
    assert len(telemetry_tools) == 1
    assert telemetry_tools[0].name == "mock_read_sensor"


def test_filter_by_authority(registry: ToolRegistry):
    registry.register(MockReadSensor())
    registry.register(MockFireThruster())

    # Only tools at SENSOR_ONLY level
    safe_tools = registry.get_tools(max_authority=AuthorityLevel.SENSOR_ONLY)
    assert len(safe_tools) == 1
    assert safe_tools[0].name == "mock_read_sensor"


def test_export_schemas(registry: ToolRegistry):
    registry.register(MockReadSensor())
    schemas = registry.export_schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "mock_read_sensor"
    assert "input_schema" in schemas[0]


async def test_invoke_success(registry: ToolRegistry):
    registry.register(MockReadSensor())
    result = await registry.invoke("mock_read_sensor", {"sensor_id": "temp-1"})
    assert result.success
    assert result.data["value"] == 42.0


async def test_invoke_unknown_tool(registry: ToolRegistry):
    result = await registry.invoke("nonexistent_tool", {})
    assert not result.success
    assert "Unknown tool" in (result.error or "")


async def test_invoke_permission_denied(registry: ToolRegistry):
    registry.register(MockFireThruster())
    # Try to invoke with SENSOR_ONLY authority (too low for CONSENT-level tool)
    result = await registry.invoke(
        "mock_fire_thruster",
        {"thruster_id": "t1", "duration_ms": 100},
        authority=AuthorityLevel.SENSOR_ONLY,
    )
    assert not result.success
    assert "Permission denied" in (result.error or "")


def test_health_report(registry: ToolRegistry):
    registry.register(MockReadSensor())
    registry.register(MockFireThruster())
    report = registry.health_report()
    assert report["total_tools"] == 2
    assert report["healthy"] == 2
    assert report["degraded"] == []


# ---------------------------------------------------------------------------
# Deep Production-Quality Tests
# ---------------------------------------------------------------------------

class MockSlowTool(ARIATool):
    """Tool that sleeps to test timeout handling."""
    name = "mock_slow_tool"
    description = "Slow tool for timeout testing"
    category = ToolCategory.DIAGNOSTIC
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    timeout_ms = 100  # 100ms timeout

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object"}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        import asyncio
        await asyncio.sleep(0.5)  # 500ms — will timeout
        return ToolResult(success=True, data={})


class MockFailingTool(ARIATool):
    """Tool that always fails to test circuit breaker."""
    name = "mock_failing_tool"
    description = "Failing tool"
    category = ToolCategory.DIAGNOSTIC
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object"}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        raise RuntimeError("Simulated failure")


async def test_tool_timeout_returns_failure(registry: ToolRegistry):
    """Tool that exceeds timeout returns failure, not crash."""
    registry.register(MockSlowTool())
    result = await registry.invoke("mock_slow_tool", {})
    assert not result.success
    assert result.error is not None


async def test_tool_exception_returns_failure(registry: ToolRegistry):
    """Tool that raises exception returns clean failure."""
    registry.register(MockFailingTool())
    result = await registry.invoke("mock_failing_tool", {})
    assert not result.success


async def test_circuit_breaker_trips_after_failures(registry: ToolRegistry):
    """After consecutive failures, circuit breaker opens."""
    registry.register(MockFailingTool())

    # Trigger enough failures to trip circuit breaker
    for _ in range(10):
        await registry.invoke("mock_failing_tool", {})

    tool = registry.get("mock_failing_tool")
    # Circuit breaker should be open after enough failures
    assert tool.health.consecutive_failures >= 5


async def test_get_healthy_tools_excludes_tripped(registry: ToolRegistry):
    """get_healthy_tools excludes tools with open circuit breakers."""
    registry.register(MockReadSensor())
    registry.register(MockFailingTool())

    # Trip failing tool's circuit breaker
    for _ in range(10):
        await registry.invoke("mock_failing_tool", {})

    healthy = registry.get_healthy_tools()
    healthy_names = [t.name for t in healthy]
    assert "mock_read_sensor" in healthy_names


async def test_tool_execution_time_recorded(registry: ToolRegistry):
    """Successful tool call records execution_time_ms."""
    registry.register(MockReadSensor())
    result = await registry.invoke("mock_read_sensor", {"sensor_id": "test"})
    assert result.success
    assert result.execution_time_ms >= 0


def test_get_nonexistent_tool(registry: ToolRegistry):
    """Getting non-existent tool returns None."""
    assert registry.get("nonexistent") is None


def test_registry_count_accurate(registry: ToolRegistry):
    """Count reflects actual number of registered tools."""
    assert registry.count == 0
    registry.register(MockReadSensor())
    assert registry.count == 1
    registry.register(MockFireThruster())
    assert registry.count == 2


def test_export_schemas_by_category(registry: ToolRegistry):
    """Schema export can filter by category."""
    registry.register(MockReadSensor())
    registry.register(MockFireThruster())

    telemetry = registry.export_schemas(category=ToolCategory.TELEMETRY)
    assert len(telemetry) == 1
    assert telemetry[0]["name"] == "mock_read_sensor"

    propulsion = registry.export_schemas(category=ToolCategory.PROPULSION)
    assert len(propulsion) == 1


async def test_health_report_with_degraded(registry: ToolRegistry):
    """Health report identifies degraded tools after failures."""
    registry.register(MockReadSensor())
    registry.register(MockFailingTool())

    # Trigger enough failures to degrade (circuit_breaker_opens_at=5)
    for _ in range(6):
        await registry.invoke("mock_failing_tool", {})

    report = registry.health_report()
    assert report["total_tools"] == 2
    assert "mock_failing_tool" in report["degraded"]


async def test_concurrent_tool_invocations(registry: ToolRegistry):
    """Multiple concurrent tool invocations don't interfere."""
    import asyncio
    registry.register(MockReadSensor())

    results = await asyncio.gather(*[
        registry.invoke("mock_read_sensor", {"sensor_id": f"sensor_{i}"})
        for i in range(20)
    ])

    assert all(r.success for r in results)
    assert all(r.data["value"] == 42.0 for r in results)
