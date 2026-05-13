"""Closed-loop LLM decision test.

Exercises the full path:
    agent.request_reasoning(question)
        → bus: aria.agent.reasoning_request
            → coordinator._on_reasoning_request
                → CognitiveEngine.reason() (rule-based fallback — no API key needed)
                    → tools invoked
                        → response published to aria.agent.reasoning_response.{agent}
                            → agent.on_reasoning_response stores it
                            → coordinator.ai_decisions() trace has the entry

This is the production-grade feature: the LLM isn't just "advisor text" any
more — it's a request/response loop with tool invocation that agents can
actually receive.
"""

from __future__ import annotations

import asyncio

import pytest

from aria.agents.base import SubsystemAgent
from aria.bus.message_bus import MessageBus, Message
from aria.core.types import EventPriority
from aria.core.coordinator import AriaCoordinator, AgentRecord  # noqa: F401
from aria.tools.registry import ToolRegistry


class _ProbeAgent(SubsystemAgent):
    """Minimal agent used to exercise the reasoning roundtrip."""

    name = "probe"
    subscriptions: list[str] = []

    async def handle_message(self, message: Message) -> None:
        # Non-reasoning traffic just gets counted.
        pass


@pytest.mark.asyncio
async def test_reasoning_request_roundtrip_records_decision(tmp_path, monkeypatch):
    """An agent's request_reasoning() must produce a coordinator-logged
    decision *and* end up on the requesting agent's last_reasoning_response."""
    from aria.core.config import AriaConfig

    # Minimal in-memory config
    cfg = AriaConfig()
    coord = AriaCoordinator(cfg)
    # Point persistence somewhere benign for this test.
    coord.state._persist_path = tmp_path / "state.json"

    # Ensure we don't hit a live Anthropic API during tests
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    await coord.start()
    try:
        # Register the probe agent against the real bus + tools
        agent = _ProbeAgent(coord.bus, coord.tools)
        coord.register_agent(agent)
        await agent.start()

        # Ask the LLM something. With no API key, the coordinator wires the
        # RuleBasedFallback, which returns a text response for unmatched
        # queries. Either way we should get a final response back.
        await agent.request_reasoning(
            "Is power margin nominal? Check and recommend action.",
            context={"reason": "unit-test"},
        )

        for _ in range(60):
            if agent._last_reasoning_response is not None:
                break
            await asyncio.sleep(0.1)

        assert agent._last_reasoning_response is not None, \
            "agent.on_reasoning_response was never called"
        rr = agent._last_reasoning_response
        assert "response" in rr
        assert rr["response"], "LLM produced an empty response"

        decisions = coord.ai_decisions()
        assert len(decisions) >= 1
        last = decisions[-1]
        assert last["agent"] == "probe"
        assert last["question"].startswith("Is power margin nominal?")
        assert last["response"]

    finally:
        await coord.stop()


@pytest.mark.asyncio
async def test_power_agent_acts_on_llm_shed_load_directive(tmp_path, monkeypatch):
    """Closed-loop end-to-end: a reasoning_response carrying a shed_load
    directive must cause PowerAgent to publish aria.power.load_shed.executed
    *and* aria.power.llm_action.executed within a couple of seconds.

    This is what the README has implied for months but didn't actually do —
    Track 3 Phase 1 of ROADMAP_THREE_GAPS.md.
    """
    from aria.agents.power import PowerAgent
    from aria.core.config import AriaConfig

    cfg = AriaConfig()
    coord = AriaCoordinator(cfg)
    coord.state._persist_path = tmp_path / "state.json"
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    captured: dict[str, list[dict]] = {
        "load_shed": [],
        "llm_action": [],
    }

    async def _on_load_shed(msg: Message) -> None:
        captured["load_shed"].append(msg.payload or {})

    async def _on_llm_action(msg: Message) -> None:
        captured["llm_action"].append(msg.payload or {})

    await coord.start()
    try:
        coord.bus.subscribe("aria.power.load_shed.executed", _on_load_shed)
        coord.bus.subscribe("aria.power.llm_action.executed", _on_llm_action)

        agent = PowerAgent(coord.bus, coord.tools)
        coord.register_agent(agent)
        await agent.start()

        # Simulate the engine's response landing on the agent.
        # parse_recommendation matches "shed_load science" → ActionIntent(shed_load, {subsystem: science}).
        await agent.on_reasoning_response({
            "agent": "power",
            "question": "Battery low during eclipse, what to do?",
            "response": "Recommend: shed_load science to preserve crew loads.",
            "tools_used": ["eps_get_power_budget"],
            "steps": 1,
        })

        # Drain events
        for _ in range(40):
            if captured["load_shed"] and captured["llm_action"]:
                break
            await asyncio.sleep(0.05)

        assert captured["load_shed"], "PowerAgent did not execute the load shed"
        assert captured["llm_action"], "llm_action.executed was never published"
        ev = captured["llm_action"][0]
        assert ev["action"] == "shed_load"
        assert ev["subsystem"] == "science"

    finally:
        await coord.stop()


@pytest.mark.asyncio
async def test_power_agent_safe_mode_directive(tmp_path, monkeypatch):
    """A 'safe_mode' directive in the LLM response must publish
    aria.command.power.safe_mode and the audit-trail llm_action event."""
    from aria.agents.power import PowerAgent
    from aria.core.config import AriaConfig

    cfg = AriaConfig()
    coord = AriaCoordinator(cfg)
    coord.state._persist_path = tmp_path / "state.json"
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    captured: dict[str, list[dict]] = {"safe_mode": [], "llm_action": []}

    async def _on_safe(msg: Message) -> None:
        captured["safe_mode"].append(msg.payload or {})

    async def _on_act(msg: Message) -> None:
        captured["llm_action"].append(msg.payload or {})

    await coord.start()
    try:
        coord.bus.subscribe("aria.command.power.safe_mode", _on_safe)
        coord.bus.subscribe("aria.power.llm_action.executed", _on_act)

        agent = PowerAgent(coord.bus, coord.tools)
        coord.register_agent(agent)
        await agent.start()

        await agent.on_reasoning_response({
            "agent": "power",
            "question": "Bus brownout — recommendation?",
            "response": "Enter safe_mode immediately and monitor.",
            "tools_used": [],
            "steps": 0,
        })

        for _ in range(40):
            if captured["safe_mode"] and captured["llm_action"]:
                break
            await asyncio.sleep(0.05)

        assert captured["safe_mode"], "safe_mode command was never dispatched"
        assert any(a.get("action") == "safe_mode" for a in captured["llm_action"])
    finally:
        await coord.stop()


@pytest.mark.asyncio
async def test_engine_unavailable_still_publishes_ack(tmp_path, monkeypatch):
    """If the engine can't be built, a reasoning_response is still published
    so the agent doesn't wait forever."""
    from aria.core.config import AriaConfig

    cfg = AriaConfig()
    coord = AriaCoordinator(cfg)
    coord.state._persist_path = tmp_path / "state.json"

    # Force _get_cognitive_engine to return None
    coord._cognitive_engine = None
    monkeypatch.setattr(coord, "_get_cognitive_engine", lambda: None)

    await coord.start()
    try:
        agent = _ProbeAgent(coord.bus, coord.tools)
        coord.register_agent(agent)
        await agent.start()

        await agent.request_reasoning("any question", context={})
        for _ in range(30):
            if agent._last_reasoning_response is not None:
                break
            await asyncio.sleep(0.05)
        assert agent._last_reasoning_response is not None
        assert "unavailable" in agent._last_reasoning_response["response"].lower()
    finally:
        await coord.stop()
