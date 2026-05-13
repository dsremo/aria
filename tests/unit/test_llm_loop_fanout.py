"""Closed-loop LLM regression harness — Track 3 P3 fan-out.

For each agent that owns concrete actions (Power, Thermal, ECLSS,
Comms, Navigation, Propulsion), feed an `on_reasoning_response`
payload carrying a domain-specific directive and assert the matching
``aria.{agent}.llm_action.executed`` event is published.

This is what closes the "LLM advice-only" gap end-to-end across the
agent fleet (Roadmap Track 3 P4 in docs/ROADMAP_THREE_GAPS.md).
"""

from __future__ import annotations

import asyncio

import pytest

from aria.bus.message_bus import Message
from aria.core.coordinator import AriaCoordinator
from aria.core.config import AriaConfig


async def _wait_for(events: list, *, timeout_s: float = 1.5) -> bool:
    """Poll until at least one event lands or timeout."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if events:
            return True
        await asyncio.sleep(0.02)
    return False


async def _drive(monkeypatch, tmp_path, agent_factory, response_text: str,
                 listen_topics: list[str]) -> dict[str, list[dict]]:
    """Spin up coordinator + agent, deliver the response, capture topics."""
    cfg = AriaConfig()
    coord = AriaCoordinator(cfg)
    coord.state._persist_path = tmp_path / "state.json"
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    captured: dict[str, list[dict]] = {t: [] for t in listen_topics}

    def _make_handler(topic: str):
        async def _handler(msg: Message) -> None:
            captured[topic].append(msg.payload or {})
        return _handler

    await coord.start()
    try:
        for t in listen_topics:
            coord.bus.subscribe(t, _make_handler(t))

        agent = agent_factory(coord.bus, coord.tools)
        coord.register_agent(agent)
        await agent.start()

        await agent.on_reasoning_response({
            "agent": agent.name,
            "question": "regression-harness probe",
            "response": response_text,
            "tools_used": [],
            "steps": 0,
        })

        # Give the bus a few cycles to fan events out.
        for _ in range(50):
            if all(captured[t] for t in listen_topics):
                break
            await asyncio.sleep(0.02)

    finally:
        await coord.stop()
    return captured


@pytest.mark.asyncio
async def test_thermal_set_setpoint(tmp_path, monkeypatch):
    from aria.agents.thermal import ThermalAgent
    captured = await _drive(
        monkeypatch, tmp_path,
        lambda bus, tools: ThermalAgent(bus, tools),
        "Thermal: set_setpoint battery_pack 12.0 C to slow degradation.",
        ["aria.thermal.llm_action.executed"],
    )
    ev = captured["aria.thermal.llm_action.executed"]
    assert ev, "ThermalAgent did not execute set_setpoint"
    assert ev[0]["action"] == "set_setpoint"
    assert ev[0]["zone"] == "battery_pack"
    assert ev[0]["celsius"] == 12.0


@pytest.mark.asyncio
async def test_thermal_safe_mode(tmp_path, monkeypatch):
    from aria.agents.thermal import ThermalAgent
    captured = await _drive(
        monkeypatch, tmp_path,
        lambda bus, tools: ThermalAgent(bus, tools),
        "Recommend safe_mode immediately.",
        ["aria.thermal.llm_action.executed"],
    )
    ev = captured["aria.thermal.llm_action.executed"]
    assert ev, "ThermalAgent did not execute safe_mode"
    assert ev[0]["action"] == "safe_mode"


@pytest.mark.asyncio
async def test_eclss_boost_scrubber(tmp_path, monkeypatch):
    from aria.agents.eclss import EclssAgent
    captured = await _drive(
        monkeypatch, tmp_path,
        lambda bus, tools: EclssAgent(bus, tools),
        "boost_scrubber to handle CO2 breakthrough.",
        ["aria.eclss.llm_action.executed",
         "aria.actuator.eclss.scrubber_backup"],
    )
    assert captured["aria.eclss.llm_action.executed"], "ECLSS llm_action.executed missing"
    assert captured["aria.actuator.eclss.scrubber_backup"], "backup scrubber not activated"


@pytest.mark.asyncio
async def test_eclss_pressurize_cabin(tmp_path, monkeypatch):
    from aria.agents.eclss import EclssAgent
    captured = await _drive(
        monkeypatch, tmp_path,
        lambda bus, tools: EclssAgent(bus, tools),
        "pressurize_cabin 101.3 kpa following decompression alarm.",
        ["aria.eclss.llm_action.executed",
         "aria.actuator.eclss.cabin_pressure"],
    )
    ev = captured["aria.actuator.eclss.cabin_pressure"]
    assert ev, "cabin pressure command not published"
    assert abs(ev[0]["target_kpa"] - 101.3) < 1e-6


@pytest.mark.asyncio
async def test_comms_switch_antenna(tmp_path, monkeypatch):
    from aria.agents.comms import CommsAgent
    captured = await _drive(
        monkeypatch, tmp_path,
        lambda bus, tools: CommsAgent(bus, tools),
        "switch_antenna LGA — HGA pointing lost.",
        ["aria.comms.llm_action.executed",
         "aria.actuator.comms.switch_antenna"],
    )
    ev = captured["aria.actuator.comms.switch_antenna"]
    assert ev, "switch antenna actuator not commanded"
    assert ev[0]["antenna"] == "lga"


@pytest.mark.asyncio
async def test_navigation_attitude_hold(tmp_path, monkeypatch):
    from aria.agents.navigation import NavigationAgent
    captured = await _drive(
        monkeypatch, tmp_path,
        lambda bus, tools: NavigationAgent(bus, tools),
        "Recommend attitude_hold while we re-acquire star tracker.",
        ["aria.nav.llm_action.executed",
         "aria.actuator.nav.attitude_hold"],
    )
    assert captured["aria.actuator.nav.attitude_hold"], "attitude_hold actuator not commanded"
    assert captured["aria.nav.llm_action.executed"][0]["action"] == "attitude_hold"


@pytest.mark.asyncio
async def test_propulsion_throttle_engine(tmp_path, monkeypatch):
    """throttle_engine is now a gated action per the sealed
    constitution (1 operator approval, 0 s cooldown). Post-R29
    failsafe wiring, the LLM directive parses and enters the approval
    queue rather than firing immediately. Verify the proposal exists."""
    from aria.agents.propulsion import PropulsionAgent
    from aria.safety.approval_queue import get_approval_queue, reset_for_test
    reset_for_test()
    await _drive(
        monkeypatch, tmp_path,
        lambda bus, tools: PropulsionAgent(bus, tools),
        "throttle_engine 0.6 to extend coast.",
        [],   # No bus topics expected — proposal is the artefact.
    )
    pending = get_approval_queue().list_pending()
    matching = [p for p in pending if p["action"] == "throttle_engine"]
    assert matching, "throttle_engine proposal not enqueued"
    assert matching[0]["params"]["fraction"] == 0.6


@pytest.mark.asyncio
async def test_propulsion_safe_mode_zeros_throttle(tmp_path, monkeypatch):
    from aria.agents.propulsion import PropulsionAgent
    captured = await _drive(
        monkeypatch, tmp_path,
        lambda bus, tools: PropulsionAgent(bus, tools),
        "Enter safe_mode and stop the burn.",
        ["aria.propulsion.llm_action.executed",
         "aria.actuator.propulsion.throttle"],
    )
    ev = captured["aria.actuator.propulsion.throttle"]
    assert ev, "throttle command not published"
    assert ev[0]["fraction"] == 0.0
