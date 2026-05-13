"""Space Novel Scenario Tests — Would ARIA survive famous space emergencies?

Each test recreates a famous spacecraft emergency from movies, books, or real
history and verifies ARIA would detect it, respond correctly, and keep crew alive.

Sources:
  - Apollo 13 (1970, real): O2 tank explosion → power crisis → CO2 scrubber
  - The Martian (2015, Weir): habitat breach → depressurization
  - Gravity (2013, film): debris strike → tumble → comm loss
  - 2001: A Space Odyssey (1968, Clarke): AI turns against crew (ARIA must NOT)
  - ISS Ammonia Leak (2013, real): toxic atmosphere detection
  - Soyuz MS-09 Drill Hole (2018, real): slow pressure leak
  - Columbia STS-107 (2003, real): thermal protection failure
  - Mir Fire (1997, real): oxygen generator fire
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from aria.agents.comms import CommsAgent
from aria.agents.eclss import EclssAgent
from aria.agents.medical import MedicalAgent
from aria.agents.navigation import NavigationAgent
from aria.agents.power import PowerAgent
from aria.agents.propulsion import PropulsionAgent
from aria.agents.science import ScienceAgent
from aria.agents.telemetry import TelemetryAgent
from aria.agents.thermal import ThermalAgent
from aria.bus.message_bus import Message, MessageBus
from aria.core.tool import ARIATool, ToolResult
from aria.core.types import AuthorityLevel, SafetyLevel, ToolCategory
from aria.state.scratchpad import SharedScratchpad
from aria.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

class StubTool(ARIATool):
    name = "dsremo_ingest_telemetry"
    description = "stub"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    def input_schema(self) -> dict[str, Any]: return {"type": "object"}
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"anomaly_score": 0.1})


class StubBatch(ARIATool):
    name = "dsremo_ingest_batch"
    description = "stub"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    def input_schema(self) -> dict[str, Any]: return {"type": "object", "required": ["readings"]}
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        readings = params.get("readings", [])
        return ToolResult(success=True, data={
            "results": [{"channel_id": r["channel_id"], "anomaly_score": 0.1} for r in readings],
            "count": len(readings),
        })


@pytest.fixture
async def bus():
    b = MessageBus(max_history=2000)
    await b.start()
    yield b
    await b.stop()


def make_tools():
    reg = ToolRegistry()
    reg.register(StubTool())
    reg.register(StubBatch())
    return reg


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO: Apollo 13 — "Houston, we've had a problem"
# ═══════════════════════════════════════════════════════════════════════════

async def test_apollo_13_o2_tank_explosion(bus: MessageBus):
    """Apollo 13: O2 tank explosion causes cascading power + ECLSS failure.

    Timeline:
      T+0:  O2 tank 2 explodes — O2 drops, power drops (fuel cells need O2)
      T+1:  Bus voltage plummets (fuel cells failing)
      T+2:  CO2 starts rising (scrubber capacity overwhelmed)

    ARIA should:
      1. Detect O2 drop → CRITICAL alert
      2. Detect power failure → load shed
      3. Detect CO2 rise → activate backup scrubber
      4. All agents survive the cascade
    """
    alerts: list[Message] = []
    shed_events: list[Message] = []
    bus.subscribe("aria.anomaly.*", lambda m: alerts.append(m))
    bus.subscribe("aria.power.load_shed.executed", lambda m: shed_events.append(m))

    sp = SharedScratchpad()
    tools = make_tools()

    power = PowerAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    eclss = EclssAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    thermal = ThermalAgent(bus=bus, tool_registry=tools, scratchpad=sp)

    await power.start()
    await eclss.start()
    await thermal.start()

    # T+0: O2 tank explosion — O2 drops dramatically
    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 16.0, "co2_mmhg": 4.0, "humidity_percent": 50.0, "temperature_c": 18.0},
    ))

    # T+1: Power failure — fuel cells die, bus voltage drops
    await bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 8.0, "temperature_c": 15.0},
    ))
    await bus.publish(Message(
        topic="aria.sensor.power.bus",
        payload={"voltage_v": 22.0},
    ))

    # T+2: CO2 rising — scrubber overwhelmed
    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 15.5, "co2_mmhg": 12.0, "humidity_percent": 55.0, "temperature_c": 15.0},
    ))

    await asyncio.sleep(0.5)

    # ARIA should have detected the cascade
    critical = [a for a in alerts if a.payload.get("severity") in ("CRITICAL", "EMERGENCY")]
    assert len(critical) >= 2, f"Expected multiple CRITICAL alerts, got {len(critical)}"

    # Load shed should have triggered
    assert len(shed_events) >= 1, "Expected load shed on critical SoC"

    # All agents should still be alive (no crash during cascade)
    for agent in [power, eclss, thermal]:
        assert agent.status.name not in ("STOPPED", "ERROR"), f"{agent.name} died"

    await power.stop()
    await eclss.stop()
    await thermal.stop()


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO: The Martian — Habitat breach during storm
# ═══════════════════════════════════════════════════════════════════════════

async def test_the_martian_habitat_breach(bus: MessageBus):
    """The Martian: Habitat canvas tears in storm → rapid depressurization.

    ARIA should:
      1. Detect rapid pressure drop → EMERGENCY
      2. Invoke depressurization response
      3. Alert crew to seal suits
    """
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    eclss = EclssAgent(bus=bus, tool_registry=tools)
    await eclss.start()

    # Rapid pressure drop — 14.7 psi → 11.0 psi (habitat breach)
    await bus.publish(Message(
        topic="aria.sensor.eclss.pressure",
        payload={"pressure_psi": 11.0},
    ))
    await asyncio.sleep(0.3)

    emergency = [a for a in alerts if a.payload.get("severity") == "EMERGENCY"]
    assert len(emergency) >= 1, "ARIA should detect depressurization as EMERGENCY"
    assert any("pressure" in a.payload.get("message", "").lower() for a in emergency)

    await eclss.stop()


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO: Gravity — Debris strike causes tumble + comm loss
# ═══════════════════════════════════════════════════════════════════════════

async def test_gravity_debris_strike(bus: MessageBus):
    """Gravity: Kessler syndrome debris strike → uncontrolled tumble + comm loss.

    ARIA should:
      1. Detect high angular rates → CRITICAL tumble
      2. Detect communication loss → WARNING
      3. Both happen simultaneously — system must handle both
    """
    nav_alerts: list[Message] = []
    comms_alerts: list[Message] = []
    bus.subscribe("aria.anomaly.navigation", lambda m: nav_alerts.append(m))
    bus.subscribe("aria.anomaly.comms", lambda m: comms_alerts.append(m))

    tools = make_tools()
    nav = NavigationAgent(bus=bus, tool_registry=tools)
    comms = CommsAgent(bus=bus, tool_registry=tools)

    await nav.start()
    await comms.start()

    # Simultaneous: debris strike causes tumble + antenna damage
    await asyncio.gather(
        bus.publish(Message(
            topic="aria.sensor.nav.imu",
            payload={"angular_rate_x_dps": 15.0, "angular_rate_y_dps": 12.0, "angular_rate_z_dps": 8.0},
        )),
        bus.publish(Message(
            topic="aria.sensor.comms.link",
            payload={"signal_dbm": -130.0, "snr_db": 0.5, "ber": 0.1, "data_rate_kbps": 0.0},
        )),
    )
    await asyncio.sleep(0.3)

    # Tumble detected
    tumble = [a for a in nav_alerts if a.payload.get("severity") == "CRITICAL"]
    assert len(tumble) >= 1, "Should detect tumble from debris strike"

    # Comm loss detected
    comm_loss = [a for a in comms_alerts if a.payload.get("severity") == "WARNING"]
    assert len(comm_loss) >= 1, "Should detect comm loss from antenna damage"

    await nav.stop()
    await comms.stop()


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO: 2001 — HAL turns against crew (ARIA must NOT)
# ═══════════════════════════════════════════════════════════════════════════

async def test_2001_aria_does_not_harm_crew(bus: MessageBus):
    """2001: HAL 9000 turns against crew. ARIA must NEVER do this.

    Verify: Even with conflicting objectives, ARIA prioritizes crew safety.
    The conflict resolver must always rank crew_safety highest.
    """
    from aria.core.conflict import ConflictRequest, ConflictResolver

    resolver = ConflictResolver(bus)

    # Scenario: "mission_critical" wants to vent atmosphere for some reason
    # vs "crew_safety" wants to keep crew alive
    result = await resolver.resolve(
        ConflictRequest(
            agent_name="mission_control",
            action="vent_atmosphere",
            priority="mission_critical",
            reason="Mission requires atmosphere venting",
        ),
        ConflictRequest(
            agent_name="eclss",
            action="maintain_atmosphere",
            priority="crew_safety",
            reason="Crew needs breathable air to survive",
        ),
    )

    # crew_safety MUST always win over mission_critical
    assert result.winner is not None, "There must be a winner"
    assert result.winner.agent_name == "eclss", "ECLSS (crew safety) must win"
    assert result.winner.priority == "crew_safety"


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO: ISS Ammonia Leak (2013) — Toxic atmosphere
# ═══════════════════════════════════════════════════════════════════════════

async def test_iss_ammonia_leak_toxic_atmosphere(bus: MessageBus):
    """ISS 2013: Ammonia leak warning in US segment.

    Simulated as elevated CO + degraded air quality.
    ARIA should: detect CO rise, alert crew, trigger fire response protocol.
    """
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    eclss = EclssAgent(bus=bus, tool_registry=tools)
    await eclss.start()

    # CO rising rapidly (simulating toxic gas leak)
    await bus.publish(Message(
        topic="aria.sensor.fire.co",
        payload={"co_ppm": 80.0},
    ))
    await asyncio.sleep(0.2)

    co_alerts = [a for a in alerts if "co" in a.payload.get("message", "").lower()]
    assert len(co_alerts) >= 1, "Should detect CO elevation"

    # Verify severity is at least CRITICAL
    critical = [a for a in co_alerts if a.payload.get("severity") in ("CRITICAL", "EMERGENCY")]
    assert len(critical) >= 1, "CO > 50 ppm should be CRITICAL"

    await eclss.stop()


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO: Soyuz MS-09 Drill Hole (2018) — Slow pressure leak
# ═══════════════════════════════════════════════════════════════════════════

async def test_soyuz_drill_hole_slow_leak(bus: MessageBus):
    """Soyuz MS-09 2018: 2mm drill hole causes slow pressure leak.

    The leak was so slow it took hours to notice.
    ARIA should: detect the pressure trend over multiple readings.
    """
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    eclss = EclssAgent(bus=bus, tool_registry=tools)
    await eclss.start()

    # Slow pressure drop over multiple readings
    pressures = [14.70, 14.65, 14.58, 14.50, 14.40, 14.28, 14.15, 14.00, 13.85, 13.65, 13.40]
    for p in pressures:
        await bus.publish(Message(
            topic="aria.sensor.eclss.pressure",
            payload={"pressure_psi": p},
        ))
        await asyncio.sleep(0.05)  # Simulate time passing

    await asyncio.sleep(0.2)

    # Should have detected pressure drop trend or critical threshold
    pressure_alerts = [a for a in alerts if "pressure" in a.payload.get("message", "").lower() or "leak" in a.payload.get("message", "").lower()]
    assert len(pressure_alerts) >= 1, "ARIA should detect slow pressure leak"

    await eclss.stop()


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO: Mir Fire (1997) — Oxygen generator fire
# ═══════════════════════════════════════════════════════════════════════════

async def test_mir_fire_oxygen_generator(bus: MessageBus):
    """Mir 1997: Oxygen candle generator catches fire.

    ARIA should: detect smoke + CO + temperature rise → EMERGENCY fire response.
    """
    alerts: list[Message] = []
    fire_responses: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))
    bus.subscribe("aria.emergency.fire.response", lambda m: fire_responses.append(m))

    tools = make_tools()
    eclss = EclssAgent(bus=bus, tool_registry=tools)
    await eclss.start()

    # Smoke detected in oxygen generator module
    await bus.publish(Message(
        topic="aria.sensor.fire.smoke",
        payload={"detected": True, "zone": "oxygen_generator"},
    ))

    # CO rising from combustion
    await bus.publish(Message(
        topic="aria.sensor.fire.co",
        payload={"co_ppm": 150.0},
    ))

    # Temperature spike
    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 22.0, "co2_mmhg": 5.0, "humidity_percent": 60.0, "temperature_c": 35.0},
    ))

    await asyncio.sleep(0.5)

    # Fire response should have triggered
    assert len(fire_responses) >= 1, "ARIA should trigger fire response"

    # Multiple emergency alerts
    emergency = [a for a in alerts if a.payload.get("severity") in ("CRITICAL", "EMERGENCY")]
    assert len(emergency) >= 2, "Should have multiple emergency alerts (smoke + CO)"

    await eclss.stop()


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO: Solar Particle Event — Crew radiation emergency
# ═══════════════════════════════════════════════════════════════════════════

async def test_solar_particle_event_crew_shelter(bus: MessageBus):
    """Real-world SPE: sudden radiation spike from solar flare.

    ARIA should: detect dose rate spike, shelter crew, reduce electronics exposure.
    """
    shelter_events: list[Message] = []
    bus.subscribe("aria.emergency.radiation.shelter", lambda m: shelter_events.append(m))

    sp = SharedScratchpad()
    tools = make_tools()
    science = ScienceAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    medical = MedicalAgent(bus=bus, tool_registry=tools, scratchpad=sp)

    await science.start()
    await medical.start()

    # SPE hits — dose rate spikes to 2000 µSv/hr
    await bus.publish(Message(
        topic="aria.sensor.science.radiation",
        payload={"dose_rate_usv_hr": 2000.0, "cumulative_dose_msv": 50.0},
    ))
    await asyncio.sleep(0.3)

    # Shelter should have been activated
    assert len(shelter_events) >= 1, "ARIA should activate radiation shelter"
    assert "crew_to_shelter" in shelter_events[0].payload["actions"]

    # Science should have posted radiation data to scratchpad
    rad = sp.read("science.radiation")
    assert rad is not None
    assert rad["dose_rate_usv_hr"] == 2000.0

    await science.stop()
    await medical.stop()
