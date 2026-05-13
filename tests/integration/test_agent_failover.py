"""Agent failover tests — verify coordinator detects and restarts failed agents.

Per CENTRAL_AI_MASTER_PLAN Section 3.4.5:
  - Agent health is monitored via heartbeat + status
  - Failed agents (ERROR or STOPPED) are automatically restarted
  - Restart has backoff and max attempts
  - Exhausted restarts log error and continue degraded
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from aria.agents.base import SubsystemAgent
from aria.bus.message_bus import Message, MessageBus
from aria.core.config import AriaConfig
from aria.core.coordinator import AriaCoordinator
from aria.core.tool import ARIATool, ToolResult
from aria.core.types import AgentStatus, AuthorityLevel, SafetyLevel, ToolCategory
from aria.tools.registry import ToolRegistry


class StubTool(ARIATool):
    name = "dsremo_ingest_telemetry"
    description = "stub"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    def input_schema(self) -> dict[str, Any]: return {"type": "object"}
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={})


class StubBatch(ARIATool):
    name = "dsremo_ingest_batch"
    description = "stub"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    def input_schema(self) -> dict[str, Any]: return {"type": "object", "required": ["readings"]}
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"results": [], "count": 0})


class HealthyAgent(SubsystemAgent):
    """Always-healthy test agent."""
    name = "healthy_test"
    subscriptions = []
    async def handle_message(self, message: Message) -> None:
        pass


class CrashableAgent(SubsystemAgent):
    """Agent that can be manually crashed for testing."""
    name = "crashable_test"
    subscriptions = []
    crash_on_start: bool = False
    start_count: int = 0

    async def on_start(self) -> None:
        self.start_count += 1
        if self.crash_on_start:
            raise RuntimeError("Simulated crash")

    async def handle_message(self, message: Message) -> None:
        pass


async def test_coordinator_restarts_stopped_agent():
    """Coordinator detects STOPPED agent and restarts it."""
    config = AriaConfig()
    config.agent.restart_backoff_s = 0.1  # Fast for testing
    coord = AriaCoordinator(config)
    coord.tools.register(StubTool())
    coord.tools.register(StubBatch())

    agent = CrashableAgent(bus=coord.bus, tool_registry=coord.tools)
    coord.register_agent(agent)

    await coord.start()
    assert agent.status == AgentStatus.READY

    # Simulate agent crash by stopping it
    await agent.stop()
    assert agent.status == AgentStatus.STOPPED

    # Trigger health evaluation (normally runs on 30s interval)
    await coord._evaluate_system_health()
    await asyncio.sleep(0.3)  # Allow restart backoff

    # Agent should have been restarted
    record = coord._agents["crashable_test"]
    assert record.restart_count >= 1

    await coord.stop()


async def test_coordinator_respects_max_restart_attempts():
    """Coordinator stops trying after max_restart_attempts."""
    config = AriaConfig()
    config.agent.max_restart_attempts = 2
    config.agent.restart_backoff_s = 0.1

    coord = AriaCoordinator(config)
    coord.tools.register(StubTool())
    coord.tools.register(StubBatch())

    agent = CrashableAgent(bus=coord.bus, tool_registry=coord.tools)
    coord.register_agent(agent)

    await coord.start()

    # Exhaust restart attempts
    record = coord._agents["crashable_test"]
    record.restart_count = 2  # Already at max

    await agent.stop()
    result = await coord.restart_agent("crashable_test")

    assert result is False  # Should refuse to restart

    await coord.stop()


async def test_restart_nonexistent_agent():
    """Restarting a non-existent agent returns False."""
    config = AriaConfig()
    coord = AriaCoordinator(config)
    coord.tools.register(StubTool())
    coord.tools.register(StubBatch())

    await coord.start()
    result = await coord.restart_agent("nonexistent")
    assert result is False
    await coord.stop()


async def test_phase_transition():
    """Coordinator transitions mission phases and publishes event."""
    phase_events: list[Message] = []

    config = AriaConfig()
    coord = AriaCoordinator(config)
    coord.tools.register(StubTool())
    coord.tools.register(StubBatch())

    coord.bus.subscribe("aria.mission.phase_change", lambda m: phase_events.append(m))

    await coord.start()
    assert coord.config.mission_phase == "NOMINAL_LEO"

    success = await coord.transition_phase("DEEP_SPACE_CRUISE")
    await asyncio.sleep(0.1)

    assert success
    assert coord.config.mission_phase == "DEEP_SPACE_CRUISE"
    assert len(phase_events) >= 1
    assert phase_events[0].payload["old_phase"] == "NOMINAL_LEO"
    assert phase_events[0].payload["new_phase"] == "DEEP_SPACE_CRUISE"

    await coord.stop()


async def test_invalid_phase_transition():
    """Invalid phase name returns False."""
    config = AriaConfig()
    coord = AriaCoordinator(config)
    coord.tools.register(StubTool())
    coord.tools.register(StubBatch())

    await coord.start()
    result = await coord.transition_phase("WARP_SPEED")
    assert result is False
    assert coord.config.mission_phase == "NOMINAL_LEO"  # Unchanged
    await coord.stop()


async def test_healthy_agent_not_restarted():
    """Healthy (READY) agents are not restarted during health check."""
    config = AriaConfig()
    coord = AriaCoordinator(config)
    coord.tools.register(StubTool())
    coord.tools.register(StubBatch())

    agent = HealthyAgent(bus=coord.bus, tool_registry=coord.tools)
    coord.register_agent(agent)

    await coord.start()
    assert agent.status == AgentStatus.READY

    # Health evaluation should not restart healthy agent
    await coord._evaluate_system_health()
    await asyncio.sleep(0.1)

    record = coord._agents["healthy_test"]
    assert record.restart_count == 0

    await coord.stop()


async def test_coordinator_diagnostics_complete():
    """Coordinator diagnostics returns comprehensive system info."""
    config = AriaConfig()
    coord = AriaCoordinator(config)
    coord.tools.register(StubTool())
    coord.tools.register(StubBatch())

    from aria.agents.power import PowerAgent
    coord.register_agent(PowerAgent(bus=coord.bus, tool_registry=coord.tools))

    await coord.start()

    diag = coord.diagnostics()
    assert diag["status"] == "RUNNING"
    assert "agents" in diag["uptime_components"]
    assert "power" in diag["uptime_components"]["agents"]
    assert diag["uptime_components"]["scratchpad_entries"] >= 0
    assert diag["health"]["safe_mode"] == "NOMINAL"

    await coord.stop()


async def test_coordinator_readiness_after_phase_change():
    """Readiness check works after phase transition."""
    config = AriaConfig()
    coord = AriaCoordinator(config)
    coord.tools.register(StubTool())
    coord.tools.register(StubBatch())

    await coord.start()
    await coord.transition_phase("EMERGENCY")

    check = coord.readiness_check()
    assert "go_for_operations" in check

    await coord.stop()
