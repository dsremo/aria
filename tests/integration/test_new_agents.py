"""Integration tests for PropulsionAgent, CommsAgent, ScienceAgent.

Tests:
  Propulsion: low fuel alert, thruster firing, stuck valve, maneuver execution
  Comms: link loss detection, message queuing, contact recovery
  Science: radiation emergency, observation, Dsremo scoring
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from aria.agents.comms import CommsAgent
from aria.agents.propulsion import PropulsionAgent
from aria.agents.science import ScienceAgent
from aria.bus.message_bus import Message, MessageBus
from aria.core.tool import ARIATool, ToolResult
from aria.core.types import AuthorityLevel, SafetyLevel, ToolCategory
from aria.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class MockDsremoIngest(ARIATool):
    name = "dsremo_ingest_telemetry"
    description = "Mock"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def __init__(self, score: float = 0.1) -> None:
        super().__init__()
        self.score = score

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object"}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"anomaly_score": self.score})


class MockDsremoBatch(ARIATool):
    name = "dsremo_ingest_batch"
    description = "Mock batch"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def __init__(self, score: float = 0.1) -> None:
        super().__init__()
        self.score = score

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "required": ["readings"], "properties": {"readings": {}}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        readings = params.get("readings", [])
        results = [
            {"channel_id": r["channel_id"], "anomaly_score": self.score}
            for r in readings
        ]
        return ToolResult(success=True, data={"results": results, "count": len(readings)})


class MockGenAstraBiosignature(ARIATool):
    name = "genastra_analyze_biosignature"
    description = "Mock biosignature"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object"}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"detection": False, "confidence": 0.1})


@pytest.fixture
async def bus(tmp_path, monkeypatch):
    # Wiring audit Pass 2 (F5.3) — PropulsionAgent and PowerAgent both
    # persist state to ``data/runtime/`` by default; without this
    # isolation, state from one test bleeds into the next via the
    # default-construction load path.
    monkeypatch.setenv("ARIA_RUNTIME_DIR", str(tmp_path))
    b = MessageBus(max_history=200)
    await b.start()
    yield b
    await b.stop()


def make_tools(score: float = 0.1) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(MockDsremoIngest(score=score))
    reg.register(MockDsremoBatch(score=score))
    reg.register(MockGenAstraBiosignature())
    return reg


# ---------------------------------------------------------------------------
# PropulsionAgent Tests
# ---------------------------------------------------------------------------

async def test_propulsion_low_fuel_alert(bus: MessageBus):
    """PropulsionAgent raises WARNING when fuel is low."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.propulsion", lambda m: alerts.append(m))

    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools)
    agent._initial_propellant_kg = 100.0
    await agent.start()

    # 12% fuel remaining
    await bus.publish(Message(
        topic="aria.sensor.propulsion.tank",
        payload={"propellant_kg": 12.0, "pressure_psi": 200.0, "temperature_c": 20.0},
    ))
    await asyncio.sleep(0.2)

    warning_alerts = [a for a in alerts if a.payload.get("severity") == "WARNING"]
    assert len(warning_alerts) >= 1
    assert "low" in warning_alerts[0].payload["message"].lower()
    await agent.stop()


async def test_propulsion_critical_fuel_emergency(bus: MessageBus):
    """PropulsionAgent raises EMERGENCY when fuel is critically low."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.propulsion", lambda m: alerts.append(m))

    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools)
    agent._initial_propellant_kg = 100.0
    await agent.start()

    # 3% fuel
    await bus.publish(Message(
        topic="aria.sensor.propulsion.tank",
        payload={"propellant_kg": 3.0, "pressure_psi": 40.0, "temperature_c": 20.0},
    ))
    await asyncio.sleep(0.2)

    emergency_alerts = [a for a in alerts if a.payload.get("severity") == "EMERGENCY"]
    assert len(emergency_alerts) >= 1
    await agent.stop()


async def test_propulsion_thruster_fire(bus: MessageBus):
    """PropulsionAgent fires a thruster and tracks fuel consumption."""
    responses: list[Message] = []
    bus.subscribe("aria.propulsion.fire.response", lambda m: responses.append(m))

    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools)
    await agent.start()

    initial_fuel = agent._propellant_kg

    await bus.publish(Message(
        topic="aria.command.propulsion.fire_thruster",
        payload={"thruster_id": "thruster_1", "duration_ms": 1000, "thrust_level_pct": 50.0},
    ))
    await asyncio.sleep(0.2)

    assert len(responses) >= 1
    assert responses[0].payload["success"] is True
    assert agent._propellant_kg < initial_fuel
    await agent.stop()


async def test_propulsion_stuck_valve_emergency(bus: MessageBus):
    """PropulsionAgent raises EMERGENCY on stuck-open thruster valve."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.propulsion", lambda m: alerts.append(m))

    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Report valve open with no active maneuver
    await bus.publish(Message(
        topic="aria.sensor.propulsion.thruster.thruster_2",
        payload={"chamber_pressure_psi": 50.0, "temperature_c": 150.0, "valve_state": "open"},
    ))
    await asyncio.sleep(0.2)

    emergency = [a for a in alerts if a.payload.get("severity") == "EMERGENCY"]
    assert len(emergency) >= 1
    assert "stuck" in emergency[0].payload["message"].lower()
    await agent.stop()


# ---------------------------------------------------------------------------
# CommsAgent Tests
# ---------------------------------------------------------------------------

async def test_comms_link_loss_detection(bus: MessageBus):
    """CommsAgent detects communication link loss."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.comms", lambda m: alerts.append(m))

    tools = make_tools()
    agent = CommsAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Strong signal loss
    await bus.publish(Message(
        topic="aria.sensor.comms.link",
        payload={"signal_dbm": -120.0, "snr_db": 1.0, "ber": 1e-3, "data_rate_kbps": 0.0},
    ))
    await asyncio.sleep(0.2)

    warning_alerts = [a for a in alerts if a.payload.get("severity") == "WARNING"]
    assert len(warning_alerts) >= 1
    assert "link lost" in warning_alerts[0].payload["message"].lower()
    assert not agent._link_active
    await agent.stop()


async def test_comms_message_queuing(bus: MessageBus):
    """CommsAgent queues messages when link is down."""
    tools = make_tools()
    agent = CommsAgent(bus=bus, tool_registry=tools)
    agent._link_active = False
    agent._in_contact = False
    await agent.start()

    await bus.publish(Message(
        topic="aria.command.comms.send",
        payload={"message_type": "telemetry", "priority": "NORMAL", "data": "test data"},
    ))
    await asyncio.sleep(0.2)

    assert len(agent._outbound_queue) == 1
    assert agent._messages_queued == 1
    await agent.stop()


async def test_comms_contact_recovery_flushes_queue(bus: MessageBus):
    """CommsAgent flushes queue when contact is restored."""
    downlink_events: list[Message] = []
    bus.subscribe("aria.comms.downlink.batch", lambda m: downlink_events.append(m))

    tools = make_tools()
    agent = CommsAgent(bus=bus, tool_registry=tools)
    agent._link_active = False
    agent._in_contact = False
    # Pre-load queue
    agent._outbound_queue = [
        {"type": "telemetry", "priority": "NORMAL", "data": "msg1"},
        {"type": "event", "priority": "HIGH", "data": "msg2"},
    ]
    await agent.start()

    # Restore link
    await bus.publish(Message(
        topic="aria.sensor.comms.link",
        payload={"signal_dbm": -80.0, "snr_db": 20.0, "ber": 1e-9, "data_rate_kbps": 256.0},
    ))
    await asyncio.sleep(0.2)

    assert agent._link_active
    assert len(agent._outbound_queue) == 0  # Queue flushed
    assert agent._messages_sent == 2
    await agent.stop()


# ---------------------------------------------------------------------------
# ScienceAgent Tests
# ---------------------------------------------------------------------------

async def test_science_radiation_emergency(bus: MessageBus):
    """ScienceAgent triggers EMERGENCY and shelter on radiation spike."""
    alerts: list[Message] = []
    shelter_events: list[Message] = []
    bus.subscribe("aria.anomaly.science", lambda m: alerts.append(m))
    bus.subscribe("aria.emergency.radiation.shelter", lambda m: shelter_events.append(m))

    tools = make_tools()
    agent = ScienceAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Solar particle event — 1500 μSv/hr
    await bus.publish(Message(
        topic="aria.sensor.science.radiation",
        payload={"dose_rate_usv_hr": 1500.0, "cumulative_dose_msv": 50.0},
    ))
    await asyncio.sleep(0.2)

    emergency = [a for a in alerts if a.payload.get("severity") == "EMERGENCY"]
    assert len(emergency) >= 1
    assert "radiation" in emergency[0].payload["message"].lower()
    assert len(shelter_events) >= 1
    assert "crew_to_shelter" in shelter_events[0].payload["actions"]
    await agent.stop()


async def test_science_radiation_warning(bus: MessageBus):
    """ScienceAgent raises WARNING on elevated radiation."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.science", lambda m: alerts.append(m))

    tools = make_tools()
    agent = ScienceAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.science.radiation",
        payload={"dose_rate_usv_hr": 300.0, "cumulative_dose_msv": 20.0},
    ))
    await asyncio.sleep(0.2)

    warning = [a for a in alerts if a.payload.get("severity") == "WARNING"]
    assert len(warning) >= 1
    await agent.stop()


async def test_science_observation_tracking(bus: MessageBus):
    """ScienceAgent tracks observation count."""
    tools = make_tools()
    agent = ScienceAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.science.spectrometer",
        payload={"status": "observing", "observation_complete": True, "data_size_mb": 15.5},
    ))
    await asyncio.sleep(0.2)

    assert agent._observations_count == 1
    assert agent._data_collected_mb == 15.5
    await agent.stop()


async def test_comms_beacon_activates_on_extended_loss(bus: MessageBus):
    """CommsAgent activates emergency beacon after extended signal loss."""
    import time

    beacon_events: list[Message] = []
    bus.subscribe("aria.comms.beacon.activated", lambda m: beacon_events.append(m))

    tools = make_tools()
    agent = CommsAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Simulate link loss
    await bus.publish(Message(
        topic="aria.sensor.comms.link",
        payload={"signal_dbm": -120.0, "snr_db": 1.0, "ber": 1e-3, "data_rate_kbps": 0.0},
    ))
    await asyncio.sleep(0.1)
    assert not agent._link_active

    # Backdate the signal loss start to simulate 31 minutes ago
    agent._signal_loss_start = time.time() - 1860  # 31 minutes

    # Trigger periodic task (would normally run on interval)
    await agent.periodic_task()
    await asyncio.sleep(0.1)

    assert agent._beacon_active
    assert len(beacon_events) >= 1
    await agent.stop()


async def test_propulsion_fuel_readiness_warning(bus: MessageBus):
    """PropulsionAgent warns about insufficient fuel for conjunction avoidance."""
    from aria.state.scratchpad import SharedScratchpad

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.propulsion", lambda m: alerts.append(m))

    sp = SharedScratchpad()
    # Simulate NavigationAgent posting a high-risk conjunction
    sp.write("nav.next_conjunction", {
        "object_name": "DEBRIS-2024-999",
        "collision_probability": 5e-4,  # High risk
        "time_to_tca_hours": 8.0,  # Within 24h
    }, "navigation")

    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    agent._propellant_kg = 0.5  # Very low fuel
    agent._initial_propellant_kg = 100.0
    await agent.start()

    # Trigger periodic task
    await agent.periodic_task()
    await asyncio.sleep(0.1)

    # Should warn about insufficient fuel
    fuel_warnings = [a for a in alerts if "fuel" in a.payload.get("message", "").lower() or "avoidance" in a.payload.get("message", "").lower()]
    assert len(fuel_warnings) >= 1
    await agent.stop()


async def test_science_radiation_shelter_all_clear(bus: MessageBus):
    """ScienceAgent publishes all-clear when radiation drops."""
    all_clear: list[Message] = []
    bus.subscribe("aria.science.radiation.all_clear", lambda m: all_clear.append(m))

    tools = make_tools()
    agent = ScienceAgent(bus=bus, tool_registry=tools)
    agent._radiation_shelter_active = True
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.science.radiation",
        payload={"dose_rate_usv_hr": 5.0, "cumulative_dose_msv": 55.0},
    ))
    await asyncio.sleep(0.2)

    assert len(all_clear) >= 1
    assert not agent._radiation_shelter_active
    await agent.stop()


async def test_science_defers_observation_during_eclipse(bus: MessageBus):
    """ScienceAgent defers observations when power is low during eclipse."""
    from aria.agents.science import ScienceAgent
    from aria.state.scratchpad import SharedScratchpad

    deferred: list[Message] = []
    started: list[Message] = []
    bus.subscribe("aria.science.observation.deferred", lambda m: deferred.append(m))
    bus.subscribe("aria.science.observation.started", lambda m: started.append(m))

    sp = SharedScratchpad()
    # PowerAgent says we're in eclipse with low battery
    sp.write("power.eclipse_state", {
        "in_eclipse": True,
        "solar_power_w": 0.0,
        "battery_soc": 35.0,
    }, "power")

    tools = make_tools()
    agent = ScienceAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    await agent.start()

    # Request observation — should be deferred
    await bus.publish(Message(
        topic="aria.command.science.observe",
        payload={"target": "Alpha Centauri", "instrument": "spectrometer"},
    ))
    await asyncio.sleep(0.2)

    assert len(deferred) >= 1
    assert "eclipse" in deferred[0].payload.get("reason", "").lower()
    assert len(started) == 0  # Should NOT have started

    await agent.stop()


async def test_medical_reads_co2_from_eclss_scratchpad(bus: MessageBus):
    """MedicalAgent reads ECLSS CO2 data and alerts on cognitive risk."""
    from aria.agents.medical import MedicalAgent
    from aria.state.scratchpad import SharedScratchpad

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    sp = SharedScratchpad()
    # ECLSS reports high CO2
    sp.write("eclss.atmosphere", {
        "o2_percent": 20.5,
        "co2_mmhg": 8.5,  # Above 7 mmHg threshold
        "humidity_percent": 45.0,
        "temperature_c": 22.0,
    }, "eclss")

    tools = make_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    # Need at least one crew member tracked
    agent._crew_vitals["commander"] = {"heart_rate_bpm": 72}
    await agent.start()

    # Trigger periodic task
    await agent.periodic_task()
    await asyncio.sleep(0.1)

    co2_alerts = [a for a in alerts if "co2" in a.payload.get("message", "").lower() or "cognitive" in a.payload.get("message", "").lower()]
    assert len(co2_alerts) >= 1

    await agent.stop()


async def test_science_defers_on_battery_depletion_prediction(bus: MessageBus):
    """ScienceAgent defers observations when battery depletion is predicted."""
    from aria.agents.science import ScienceAgent
    from aria.state.scratchpad import SharedScratchpad

    deferred: list[Message] = []
    bus.subscribe("aria.science.observation.deferred", lambda m: deferred.append(m))

    sp = SharedScratchpad()
    # PowerAgent predicts battery depletion in 1.5 hours
    sp.write("power.prediction", {
        "battery_soc": 25.0,
        "power_margin_w": -200,
        "hours_to_depletion": 1.5,
        "in_eclipse": False,
        "load_shed_active": False,
    }, "power")

    tools = make_tools()
    agent = ScienceAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    await agent.start()

    await bus.publish(Message(
        topic="aria.command.science.observe",
        payload={"target": "Kepler-442b", "instrument": "spectrometer"},
    ))
    await asyncio.sleep(0.2)

    assert len(deferred) >= 1
    assert "depletion" in deferred[0].payload.get("reason", "").lower()

    await agent.stop()


async def test_thermal_coolant_low_pressure(bus: MessageBus):
    """ThermalAgent detects coolant loop low pressure."""
    from aria.agents.thermal import ThermalAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.thermal", lambda m: alerts.append(m))

    tools = make_tools()
    agent = ThermalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.thermal.coolant",
        payload={"pressure_psi": 10.0, "flow_rate_lpm": 5.0, "temperature_c": 15.0},
    ))
    await asyncio.sleep(0.2)

    critical = [a for a in alerts if a.payload.get("severity") == "CRITICAL"]
    assert len(critical) >= 1
    assert "coolant" in critical[0].payload["message"].lower()
    await agent.stop()


async def test_eclss_water_recycling_warning(bus: MessageBus):
    """EclssAgent warns on low water recycling rate."""
    from aria.agents.eclss import EclssAgent
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.water",
        payload={"conductivity_us_cm": 100, "ph": 7.0, "recycling_rate_percent": 88.0},
    ))
    await asyncio.sleep(0.2)

    warnings = [a for a in alerts if a.payload.get("severity") == "WARNING"]
    assert any("recycling" in w.payload.get("message", "").lower() for w in warnings)
    await agent.stop()


async def test_medical_bone_density_warning(bus: MessageBus):
    """MedicalAgent alerts on osteopenia-range bone density."""
    from aria.agents.medical import MedicalAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.medical.bone_density",
        payload={"crew_id": "commander", "t_score": -1.5},
    ))
    await asyncio.sleep(0.2)

    warnings = [a for a in alerts if a.payload.get("severity") == "WARNING"]
    assert len(warnings) >= 1
    assert "osteopenia" in warnings[0].payload["message"].lower()
    await agent.stop()


async def test_navigation_gps_degraded_warning(bus: MessageBus):
    """NavigationAgent warns when GPS constellation is degraded."""
    from aria.agents.navigation import NavigationAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.navigation", lambda m: alerts.append(m))

    tools = make_tools()
    agent = NavigationAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Only 4 satellites — degraded accuracy
    await bus.publish(Message(
        topic="aria.sensor.nav.gps",
        payload={"fix": True, "satellites": 4, "altitude_km": 400.0, "velocity_ms": 7660.0},
    ))
    await asyncio.sleep(0.2)

    watch = [a for a in alerts if "constellation" in a.payload.get("message", "").lower() or "satellites" in a.payload.get("message", "").lower()]
    assert len(watch) >= 1
    await agent.stop()


async def test_comms_science_discovery_auto_downlink(bus: MessageBus):
    """CommsAgent auto-queues science discoveries for priority downlink."""
    tools = make_tools()
    agent = CommsAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Science discovery published on bus
    await bus.publish(Message(
        topic="aria.science.discovery.candidate",
        payload={"type": "biosignature", "sample_id": "S042", "confidence": 0.72},
    ))
    await asyncio.sleep(0.2)

    # CommsAgent should have queued and sent the discovery
    assert agent._messages_queued >= 1
    # If link is active, message was flushed immediately (sent)
    assert agent._messages_sent >= 1 or len(agent._outbound_queue) >= 1
    await agent.stop()


async def test_medical_vision_sans_warning(bus: MessageBus):
    """MedicalAgent warns on elevated ICP (SANS risk)."""
    from aria.agents.medical import MedicalAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.medical.vision",
        payload={"crew_id": "pilot", "icp_estimate_mmhg": 22.0, "visual_acuity": 0.75},
    ))
    await asyncio.sleep(0.2)

    sans_alerts = [a for a in alerts if "sans" in a.payload.get("message", "").lower() or "icp" in a.payload.get("message", "").lower()]
    assert len(sans_alerts) >= 1
    await agent.stop()


async def test_propulsion_maneuver_abort(bus: MessageBus):
    """PropulsionAgent aborts maneuver on command."""
    abort_events: list[Message] = []
    bus.subscribe("aria.propulsion.maneuver.aborted", lambda m: abort_events.append(m))

    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools)
    agent._active_maneuver = {"maneuver_id": "TEST-001"}
    await agent.start()

    await bus.publish(Message(
        topic="aria.command.propulsion.abort",
        payload={"reason": "captain_override"},
    ))
    await asyncio.sleep(0.2)

    assert len(abort_events) >= 1
    assert agent._active_maneuver is None
    await agent.stop()


async def test_comms_antenna_pointing_error(bus: MessageBus):
    """CommsAgent warns on antenna pointing error."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.comms", lambda m: alerts.append(m))

    tools = make_tools()
    agent = CommsAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.comms.antenna",
        payload={"pointing_error_deg": 3.5, "temperature_c": 25.0},
    ))
    await asyncio.sleep(0.2)

    warnings = [a for a in alerts if "pointing" in a.payload.get("message", "").lower()]
    assert len(warnings) >= 1
    await agent.stop()


async def test_science_radiation_all_clear_published(bus: MessageBus):
    """ScienceAgent publishes all-clear when radiation drops from shelter level."""
    from aria.agents.science import ScienceAgent

    all_clear: list[Message] = []
    bus.subscribe("aria.science.radiation.all_clear", lambda m: all_clear.append(m))

    tools = make_tools()
    agent = ScienceAgent(bus=bus, tool_registry=tools)
    agent._radiation_shelter_active = True  # Was in shelter
    await agent.start()

    # Radiation drops below warning threshold
    await bus.publish(Message(
        topic="aria.sensor.science.radiation",
        payload={"dose_rate_usv_hr": 10.0, "cumulative_dose_msv": 60.0},
    ))
    await asyncio.sleep(0.2)

    assert len(all_clear) >= 1
    assert not agent._radiation_shelter_active
    await agent.stop()


async def test_power_battery_prediction_scratchpad(bus: MessageBus):
    """PowerAgent posts battery depletion prediction to scratchpad."""
    from aria.agents.power import PowerAgent
    from aria.state.scratchpad import SharedScratchpad

    sp = SharedScratchpad()
    tools = make_tools()
    agent = PowerAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    agent._battery_soc = 40.0
    agent._solar_power_w = 0.0
    agent._in_eclipse = True
    agent._total_load_w = 500.0
    await agent.start()

    await agent.periodic_task()
    await asyncio.sleep(0.1)

    pred = sp.read("power.prediction")
    assert pred is not None
    assert pred["battery_soc"] == 40.0
    assert pred["in_eclipse"] is True
    assert pred["hours_to_depletion"] is not None
    assert pred["hours_to_depletion"] > 0

    await agent.stop()


async def test_thermal_gradient_alert(bus: MessageBus):
    """ThermalAgent detects high gradient between adjacent zones."""
    from aria.agents.thermal import ThermalAgent
    from aria.state.scratchpad import SharedScratchpad

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.thermal", lambda m: alerts.append(m))

    sp = SharedScratchpad()
    tools = make_tools()
    agent = ThermalAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    await agent.start()

    # Set extreme temperatures on adjacent zones
    await bus.publish(Message(
        topic="aria.sensor.thermal.battery_pack",
        payload={"temperature_c": 45.0},
    ))
    await bus.publish(Message(
        topic="aria.sensor.thermal.electronics_bay",
        payload={"temperature_c": 10.0},
    ))
    await asyncio.sleep(0.1)

    # Trigger periodic task for gradient check
    await agent.periodic_task()
    await asyncio.sleep(0.1)

    gradient_alerts = [a for a in alerts if "gradient" in a.payload.get("message", "").lower()]
    assert len(gradient_alerts) >= 1

    await agent.stop()


async def test_propulsion_defers_burn_during_low_power(bus: MessageBus):
    """PropulsionAgent defers maneuver when battery is near depletion."""
    from aria.state.scratchpad import SharedScratchpad

    deferred: list[Message] = []
    bus.subscribe("aria.propulsion.maneuver.deferred", lambda m: deferred.append(m))

    sp = SharedScratchpad()
    sp.write("power.prediction", {
        "battery_soc": 10.0,
        "power_margin_w": -300,
        "hours_to_depletion": 0.5,
        "in_eclipse": True,
    }, "power")

    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    await agent.start()

    await bus.publish(Message(
        topic="aria.nav.maneuver.execute",
        payload={"maneuver_id": "CAM-LOW-POWER", "burns": [{"thruster_id": "thruster_1", "duration_ms": 1000, "thrust_level_pct": 50}]},
    ))
    await asyncio.sleep(0.3)

    assert len(deferred) >= 1
    assert deferred[0].payload["reason"] == "low_power"
    assert agent._active_maneuver is None  # Should NOT have started

    await agent.stop()


async def test_thermal_coolant_low_flow_warning(bus: MessageBus):
    """ThermalAgent warns on low coolant flow rate (pump degradation)."""
    from aria.agents.thermal import ThermalAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.thermal", lambda m: alerts.append(m))

    tools = make_tools()
    agent = ThermalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.thermal.coolant",
        payload={"pressure_psi": 25.0, "flow_rate_lpm": 1.5, "temperature_c": 15.0},
    ))
    await asyncio.sleep(0.2)

    warnings = [a for a in alerts if "flow" in a.payload.get("message", "").lower()]
    assert len(warnings) >= 1
    await agent.stop()


async def test_eclss_low_humidity_warning(bus: MessageBus):
    """EclssAgent warns on critically low humidity."""
    from aria.agents.eclss import EclssAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 2.5, "humidity_percent": 15.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(0.2)

    humidity_warnings = [a for a in alerts if "humidity" in a.payload.get("message", "").lower()]
    assert len(humidity_warnings) >= 1
    await agent.stop()


async def test_power_battery_thermal_runaway_precursor(bus: MessageBus):
    """PowerAgent detects thermal runaway precursor: high temp + low SoC."""
    from aria.agents.power import PowerAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.power", lambda m: alerts.append(m))

    tools = make_tools()
    agent = PowerAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 22.0, "temperature_c": 43.0},
    ))
    await asyncio.sleep(0.2)

    critical = [a for a in alerts if a.payload.get("severity") == "CRITICAL" and "thermal" in a.payload.get("message", "").lower()]
    assert len(critical) >= 1
    await agent.stop()


async def test_navigation_tle_staleness(bus: MessageBus):
    """NavigationAgent warns when TLE data is stale."""
    from aria.agents.navigation import NavigationAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.navigation", lambda m: alerts.append(m))

    tools = make_tools()
    agent = NavigationAgent(bus=bus, tool_registry=tools)
    agent._tle_age_hours = 73.0  # > 72h threshold
    await agent.start()

    await agent.periodic_task()
    await asyncio.sleep(0.1)

    tle_alerts = [a for a in alerts if "tle" in a.payload.get("message", "").lower() or "stale" in a.payload.get("message", "").lower()]
    assert len(tle_alerts) >= 1
    await agent.stop()


async def test_eclss_rapid_temp_change_warning(bus: MessageBus):
    """EclssAgent warns on rapid cabin temperature change."""
    from aria.agents.eclss import EclssAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    agent._temperature_c = 22.0  # Starting temperature
    await agent.start()

    # Sudden temp jump to 28°C (delta=6°C > 3°C threshold)
    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 2.5, "humidity_percent": 45.0, "temperature_c": 28.0},
    ))
    await asyncio.sleep(0.2)

    temp_alerts = [a for a in alerts if "rapid" in a.payload.get("message", "").lower() or "temperature change" in a.payload.get("message", "").lower()]
    assert len(temp_alerts) >= 1
    await agent.stop()


async def test_medical_psych_stress_alert(bus: MessageBus):
    """MedicalAgent alerts on high psychological stress."""
    from aria.agents.medical import MedicalAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.medical.psych",
        payload={"crew_id": "ms1", "stress_score": 8.5, "isolation_hours": 12.0},
    ))
    await asyncio.sleep(0.2)

    stress_alerts = [a for a in alerts if "stress" in a.payload.get("message", "").lower()]
    assert len(stress_alerts) >= 1
    await agent.stop()


async def test_medical_isolation_alert(bus: MessageBus):
    """MedicalAgent warns on extended crew isolation."""
    from aria.agents.medical import MedicalAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.medical.psych",
        payload={"crew_id": "pilot", "stress_score": 3.0, "isolation_hours": 55.0},
    ))
    await asyncio.sleep(0.2)

    isolation_alerts = [a for a in alerts if "isolation" in a.payload.get("message", "").lower()]
    assert len(isolation_alerts) >= 1
    await agent.stop()


async def test_power_solar_degradation_dsremo(bus: MessageBus):
    """PowerAgent runs Dsremo scoring on solar power."""
    from aria.agents.power import PowerAgent

    tools = make_tools(score=0.75)  # High Dsremo score
    agent = PowerAgent(bus=bus, tool_registry=tools)
    await agent.start()

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.power", lambda m: alerts.append(m))

    # Send solar data — agent should run Dsremo scoring
    await bus.publish(Message(
        topic="aria.sensor.power.solar",
        payload={"power_watts": 2000.0},
    ))
    await asyncio.sleep(0.2)

    # With score=0.75, should get a Dsremo anomaly alert
    dsremo_alerts = [a for a in alerts if "dsremo" in a.payload.get("message", "").lower()]
    assert len(dsremo_alerts) >= 1
    await agent.stop()


async def test_propulsion_low_tank_pressure(bus: MessageBus):
    """PropulsionAgent detects critically low tank pressure."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.propulsion", lambda m: alerts.append(m))

    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools)
    agent._initial_propellant_kg = 100.0
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.propulsion.tank",
        payload={"propellant_kg": 80.0, "pressure_psi": 40.0, "temperature_c": 20.0},
    ))
    await asyncio.sleep(0.2)

    pressure_alerts = [a for a in alerts if "pressure" in a.payload.get("message", "").lower()]
    assert len(pressure_alerts) >= 1
    await agent.stop()


async def test_eclss_high_o2_fire_risk(bus: MessageBus):
    """EclssAgent warns when O2 is high (fire risk)."""
    from aria.agents.eclss import EclssAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 24.0, "co2_mmhg": 2.5, "humidity_percent": 45.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(0.2)

    o2_alerts = [a for a in alerts if "o2" in a.payload.get("message", "").lower() or "fire risk" in a.payload.get("message", "").lower()]
    assert len(o2_alerts) >= 1
    await agent.stop()


async def test_navigation_gps_fix_lost(bus: MessageBus):
    """NavigationAgent warns when GPS fix is lost."""
    from aria.agents.navigation import NavigationAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.navigation", lambda m: alerts.append(m))

    tools = make_tools()
    agent = NavigationAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.nav.gps",
        payload={"fix": False, "satellites": 2, "altitude_km": 400.0},
    ))
    await asyncio.sleep(0.2)

    gps_alerts = [a for a in alerts if "gps" in a.payload.get("message", "").lower() or "fix" in a.payload.get("message", "").lower()]
    assert len(gps_alerts) >= 1
    await agent.stop()


async def test_comms_high_ber_warning(bus: MessageBus):
    """CommsAgent warns on high bit error rate."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.comms", lambda m: alerts.append(m))

    tools = make_tools()
    agent = CommsAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.comms.link",
        payload={"signal_dbm": -90.0, "snr_db": 10.0, "ber": 1e-4, "data_rate_kbps": 128.0},
    ))
    await asyncio.sleep(0.2)

    ber_alerts = [a for a in alerts if "ber" in a.payload.get("message", "").lower()]
    assert len(ber_alerts) >= 1
    await agent.stop()


async def test_propulsion_thruster_over_temperature(bus: MessageBus):
    """PropulsionAgent detects thruster over-temperature."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.propulsion", lambda m: alerts.append(m))

    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.propulsion.thruster.thruster_3",
        payload={"chamber_pressure_psi": 100.0, "temperature_c": 350.0, "valve_state": "closed"},
    ))
    await asyncio.sleep(0.2)

    temp_alerts = [a for a in alerts if "temperature" in a.payload.get("message", "").lower()]
    assert len(temp_alerts) >= 1
    await agent.stop()


async def test_eclss_critical_co2(bus: MessageBus):
    """EclssAgent raises CRITICAL on high CO2."""
    from aria.agents.eclss import EclssAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.0, "co2_mmhg": 11.0, "humidity_percent": 45.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(0.2)

    critical = [a for a in alerts if a.payload.get("severity") == "CRITICAL"]
    assert len(critical) >= 1
    await agent.stop()


async def test_power_load_shed_on_critical_soc(bus: MessageBus):
    """PowerAgent executes load shed on critically low SoC."""
    from aria.agents.power import PowerAgent

    shed_events: list[Message] = []
    bus.subscribe("aria.power.load_shed.executed", lambda m: shed_events.append(m))

    tools = make_tools()
    agent = PowerAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 7.0, "temperature_c": 25.0},
    ))
    await asyncio.sleep(0.3)

    assert len(shed_events) >= 1
    await agent.stop()


async def test_thermal_heater_on_cold_zone(bus: MessageBus):
    """ThermalAgent turns on heater for cold zone."""
    from aria.agents.thermal import ThermalAgent

    heater_events: list[Message] = []
    bus.subscribe("aria.actuator.thermal.heater.*", lambda m: heater_events.append(m))

    tools = make_tools()
    agent = ThermalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Battery pack setpoint=20, deadband=2, so heater on below 18
    await bus.publish(Message(
        topic="aria.sensor.thermal.battery_pack",
        payload={"temperature_c": 14.0},
    ))
    await asyncio.sleep(0.2)

    assert len(heater_events) >= 1
    assert heater_events[0].payload["heater"] == "on"
    await agent.stop()


async def test_navigation_tumble_detection(bus: MessageBus):
    """NavigationAgent raises CRITICAL on high angular rates (tumble)."""
    from aria.agents.navigation import NavigationAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.navigation", lambda m: alerts.append(m))

    tools = make_tools()
    agent = NavigationAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.nav.imu",
        payload={"angular_rate_x_dps": 8.0, "angular_rate_y_dps": 5.0, "angular_rate_z_dps": 3.0},
    ))
    await asyncio.sleep(0.2)

    critical = [a for a in alerts if a.payload.get("severity") == "CRITICAL"]
    assert len(critical) >= 1
    assert "tumble" in critical[0].payload["message"].lower()
    await agent.stop()


async def test_science_spectrometer_observation_count(bus: MessageBus):
    """ScienceAgent tracks observation count."""
    from aria.agents.science import ScienceAgent

    tools = make_tools()
    agent = ScienceAgent(bus=bus, tool_registry=tools)
    await agent.start()

    for i in range(3):
        await bus.publish(Message(
            topic="aria.sensor.science.spectrometer",
            payload={"status": "observing", "observation_complete": True, "data_size_mb": 10.0},
        ))
    await asyncio.sleep(0.2)

    assert agent._observations_count == 3
    assert agent._data_collected_mb == 30.0
    await agent.stop()


async def test_medical_cardiac_emergency_low_spo2(bus: MessageBus):
    """MedicalAgent EMERGENCY on critically low SpO2."""
    from aria.agents.medical import MedicalAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_tools()
    # Add crew tools with ROUTINE auth for test
    from aria.core.tool import ARIATool, ToolResult
    from aria.core.types import AuthorityLevel as AL, SafetyLevel as SL, ToolCategory as TC

    class StubMedAlert(ARIATool):
        name = "crew_medical_alert"
        description = "s"
        category = TC.EMERGENCY
        authority_level = AL.ROUTINE
        safety_level = SL.READ_ONLY
        def input_schema(self): return {"type": "object"}
        async def execute(self, p): return ToolResult(success=True, data={})

    class StubCrewAlert(ARIATool):
        name = "crew_alert"
        description = "s"
        category = TC.DIAGNOSTIC
        authority_level = AL.ROUTINE
        safety_level = SL.READ_ONLY
        def input_schema(self): return {"type": "object"}
        async def execute(self, p): return ToolResult(success=True, data={})

    tools.register(StubMedAlert())
    tools.register(StubCrewAlert())

    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.medical.vitals.ms2",
        payload={"crew_id": "ms2", "spo2_percent": 82, "heart_rate_bpm": 130},
    ))
    await asyncio.sleep(0.3)

    emergency = [a for a in alerts if a.payload.get("severity") == "EMERGENCY"]
    assert len(emergency) >= 1
    await agent.stop()


async def test_comms_link_recovery_and_flush(bus: MessageBus):
    """CommsAgent flushes queue on link recovery."""
    tools = make_tools()
    agent = CommsAgent(bus=bus, tool_registry=tools)
    agent._link_active = False
    agent._in_contact = False
    agent._outbound_queue = [
        {"type": "telemetry", "priority": "NORMAL", "data": "msg1"},
        {"type": "event", "priority": "HIGH", "data": "msg2"},
        {"type": "science_data", "priority": "HIGH", "data": "msg3"},
    ]
    await agent.start()

    # Restore link
    await bus.publish(Message(
        topic="aria.sensor.comms.link",
        payload={"signal_dbm": -80.0, "snr_db": 18.0, "ber": 1e-9, "data_rate_kbps": 256.0},
    ))
    await asyncio.sleep(0.2)

    assert agent._link_active
    assert agent._messages_sent == 3
    assert len(agent._outbound_queue) == 0
    await agent.stop()


async def test_eclss_cabin_high_temp_comfort(bus: MessageBus):
    """EclssAgent warns on high cabin temperature (crew comfort)."""
    from aria.agents.eclss import EclssAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 2.5, "humidity_percent": 45.0, "temperature_c": 32.0},
    ))
    await asyncio.sleep(0.2)

    temp_alerts = [a for a in alerts if "temperature" in a.payload.get("message", "").lower() and "comfort" in a.payload.get("message", "").lower()]
    assert len(temp_alerts) >= 1
    await agent.stop()


async def test_propulsion_fuel_fraction_critical(bus: MessageBus):
    """PropulsionAgent CRITICAL on <10% fuel."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.propulsion", lambda m: alerts.append(m))

    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools)
    agent._initial_propellant_kg = 100.0
    agent._propellant_kg = 8.0  # 8%
    await agent.start()

    await agent.periodic_task()
    await asyncio.sleep(0.1)

    critical = [a for a in alerts if a.payload.get("severity") == "CRITICAL" and "fuel" in a.payload.get("message", "").lower()]
    assert len(critical) >= 1
    await agent.stop()


async def test_eclss_smoke_and_co_confirmed_fire(bus: MessageBus):
    """EclssAgent detects confirmed fire: smoke + elevated CO."""
    from aria.agents.eclss import EclssAgent

    alerts: list[Message] = []
    fire_responses: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))
    bus.subscribe("aria.emergency.fire.response", lambda m: fire_responses.append(m))

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # First: set CO level high
    await bus.publish(Message(
        topic="aria.sensor.fire.co",
        payload={"co_ppm": 60.0},
    ))
    await asyncio.sleep(0.1)

    # Then: smoke detected — should trigger confirmed fire
    await bus.publish(Message(
        topic="aria.sensor.fire.smoke",
        payload={"detected": True, "zone": "engineering"},
    ))
    await asyncio.sleep(0.3)

    confirmed = [a for a in alerts if "confirmed" in a.payload.get("message", "").lower()]
    assert len(confirmed) >= 1 or len(fire_responses) >= 1
    await agent.stop()


async def test_power_solar_sudden_drop(bus: MessageBus):
    """PowerAgent detects sudden solar power drop (possible string failure)."""
    from aria.agents.power import PowerAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.power", lambda m: alerts.append(m))

    tools = make_tools()
    agent = PowerAgent(bus=bus, tool_registry=tools)
    agent._solar_power_w = 2500.0  # Starting power
    await agent.start()

    # Sudden drop of 600W (24% drop)
    await bus.publish(Message(
        topic="aria.sensor.power.solar",
        payload={"power_watts": 1900.0},
    ))
    await asyncio.sleep(0.2)

    drop_alerts = [a for a in alerts if "drop" in a.payload.get("message", "").lower() or "string" in a.payload.get("message", "").lower()]
    assert len(drop_alerts) >= 1
    await agent.stop()


async def test_navigation_critical_conjunction(bus: MessageBus):
    """NavigationAgent escalates critical conjunction (Pc > 1e-3)."""
    from aria.agents.navigation import NavigationAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.conjunction", lambda m: alerts.append(m))

    tools = make_tools()
    agent = NavigationAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.conjunction.alert",
        payload={
            "object_name": "FENGYUN-DEBRIS",
            "time_to_tca_hours": 2.0,
            "collision_probability": 5e-3,
        },
    ))
    await asyncio.sleep(0.2)

    critical = [a for a in alerts if a.payload.get("severity") == "CRITICAL"]
    assert len(critical) >= 1
    assert "FENGYUN" in critical[0].payload["message"]
    await agent.stop()


async def test_medical_critical_cardiac(bus: MessageBus):
    """MedicalAgent EMERGENCY on very low heart rate (bradycardia)."""
    from aria.agents.medical import MedicalAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_tools()
    # Add crew tools
    from aria.core.tool import ARIATool, ToolResult
    from aria.core.types import AuthorityLevel as AL, SafetyLevel as SL, ToolCategory as TC
    class S1(ARIATool):
        name = "crew_medical_alert"
        description = "s"
        category = TC.EMERGENCY
        authority_level = AL.ROUTINE
        safety_level = SL.READ_ONLY
        def input_schema(self): return {"type": "object"}
        async def execute(self, p): return ToolResult(success=True, data={})
    class S2(ARIATool):
        name = "crew_alert"
        description = "s"
        category = TC.DIAGNOSTIC
        authority_level = AL.ROUTINE
        safety_level = SL.READ_ONLY
        def input_schema(self): return {"type": "object"}
        async def execute(self, p): return ToolResult(success=True, data={})
    tools.register(S1())
    tools.register(S2())

    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.medical.vitals.commander",
        payload={"crew_id": "commander", "heart_rate_bpm": 30, "spo2_percent": 95},
    ))
    await asyncio.sleep(0.3)

    emergency = [a for a in alerts if a.payload.get("severity") == "EMERGENCY"]
    assert len(emergency) >= 1
    await agent.stop()


async def test_navigation_orbit_decay_warning(bus: MessageBus):
    """NavigationAgent warns on significant altitude drop."""
    from aria.agents.navigation import NavigationAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.navigation", lambda m: alerts.append(m))

    tools = make_tools()
    agent = NavigationAgent(bus=bus, tool_registry=tools)
    agent._altitude_km = 400.0  # Starting altitude
    await agent.start()

    # GPS reports lower altitude (0.6 km drop)
    await bus.publish(Message(
        topic="aria.sensor.nav.gps",
        payload={"fix": True, "satellites": 8, "altitude_km": 399.3, "velocity_ms": 7660.0},
    ))
    await asyncio.sleep(0.2)

    decay = [a for a in alerts if "decay" in a.payload.get("message", "").lower() or "orbit" in a.payload.get("message", "").lower()]
    assert len(decay) >= 1
    await agent.stop()


async def test_eclss_emergency_co(bus: MessageBus):
    """EclssAgent EMERGENCY on very high CO (IDLH level)."""
    from aria.agents.eclss import EclssAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    # Add crew alert tool
    from aria.core.tool import ARIATool, ToolResult
    from aria.core.types import AuthorityLevel as AL, SafetyLevel as SL, ToolCategory as TC
    class S(ARIATool):
        name = "crew_alert"
        description = "s"
        category = TC.DIAGNOSTIC
        authority_level = AL.ROUTINE
        safety_level = SL.READ_ONLY
        def input_schema(self): return {"type": "object"}
        async def execute(self, p): return ToolResult(success=True, data={})
    tools.register(S())

    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.fire.co",
        payload={"co_ppm": 250.0},
    ))
    await asyncio.sleep(0.3)

    emergency = [a for a in alerts if a.payload.get("severity") == "EMERGENCY"]
    assert len(emergency) >= 1
    assert "idlh" in emergency[0].payload["message"].lower() or "co" in emergency[0].payload["message"].lower()
    await agent.stop()


async def test_medical_exercise_compliance_reminder(bus: MessageBus):
    """MedicalAgent sends exercise reminder for fatigued crew with low exercise."""
    from aria.agents.medical import MedicalAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_tools()
    from aria.core.tool import ARIATool, ToolResult
    from aria.core.types import AuthorityLevel as AL, SafetyLevel as SL, ToolCategory as TC
    class CA(ARIATool):
        name = "crew_alert"
        description = "s"
        category = TC.DIAGNOSTIC
        authority_level = AL.ROUTINE
        safety_level = SL.READ_ONLY
        def input_schema(self): return {"type": "object"}
        async def execute(self, p): return ToolResult(success=True, data={})
    tools.register(CA())

    agent = MedicalAgent(bus=bus, tool_registry=tools)
    agent._crew_fatigue["commander"] = "high"
    agent._crew_exercise_min_today["commander"] = 30.0
    await agent.start()

    await agent.periodic_task()
    await asyncio.sleep(0.1)

    exercise_alerts = [a for a in alerts if "exercise" in a.payload.get("message", "").lower()]
    assert len(exercise_alerts) >= 1
    await agent.stop()


async def test_thermal_heater_off_on_warm_zone(bus: MessageBus):
    """ThermalAgent turns heater off when zone warms past setpoint."""
    from aria.agents.thermal import ThermalAgent

    heater_events: list[Message] = []
    bus.subscribe("aria.actuator.thermal.heater.*", lambda m: heater_events.append(m))

    tools = make_tools()
    agent = ThermalAgent(bus=bus, tool_registry=tools)
    # Set battery_pack heater on initially
    zone = agent._zones["battery_pack"]
    zone.heater_on = True
    zone.temperature_c = 18.0  # Below setpoint
    await agent.start()

    # Zone warms above setpoint + deadband
    await bus.publish(Message(
        topic="aria.sensor.thermal.battery_pack",
        payload={"temperature_c": 26.0},
    ))
    await asyncio.sleep(0.2)

    # Heater should turn off
    off_events = [e for e in heater_events if e.payload.get("heater") == "off"]
    assert len(off_events) >= 1
    await agent.stop()


async def test_power_bus_undervoltage(bus: MessageBus):
    """PowerAgent detects bus undervoltage."""
    from aria.agents.power import PowerAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.power", lambda m: alerts.append(m))

    tools = make_tools()
    agent = PowerAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.power.bus",
        payload={"voltage_v": 22.0},  # Well below 28V nominal
    ))
    await asyncio.sleep(0.2)

    # Should trigger undervoltage alert or Dsremo anomaly
    assert len(alerts) >= 1
    await agent.stop()


async def test_comms_low_snr_warning(bus: MessageBus):
    """CommsAgent warns on low SNR."""
    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.comms", lambda m: alerts.append(m))

    tools = make_tools()
    agent = CommsAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.comms.link",
        payload={"signal_dbm": -95.0, "snr_db": 4.0, "ber": 1e-7, "data_rate_kbps": 64.0},
    ))
    await asyncio.sleep(0.2)

    snr_alerts = [a for a in alerts if "snr" in a.payload.get("message", "").lower()]
    assert len(snr_alerts) >= 1
    await agent.stop()


async def test_propulsion_maneuver_completed_event(bus: MessageBus):
    """PropulsionAgent publishes maneuver.completed after execution."""
    completed: list[Message] = []
    bus.subscribe("aria.propulsion.maneuver.completed", lambda m: completed.append(m))

    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.nav.maneuver.execute",
        payload={
            "maneuver_id": "MAN-TEST",
            "burns": [{"thruster_id": "thruster_1", "duration_ms": 500, "thrust_level_pct": 30.0}],
        },
    ))
    await asyncio.sleep(0.3)

    assert len(completed) >= 1
    assert completed[0].payload["maneuver_id"] == "MAN-TEST"
    await agent.stop()


async def test_science_sample_analysis_count(bus: MessageBus):
    """ScienceAgent tracks analyzed sample count."""
    from aria.agents.science import ScienceAgent

    tools = make_tools()
    agent = ScienceAgent(bus=bus, tool_registry=tools)
    await agent.start()

    for _ in range(5):
        await bus.publish(Message(
            topic="aria.sensor.science.sample.bio",
            payload={"analysis_complete": True},
        ))
    await asyncio.sleep(0.2)

    assert agent._samples_analyzed == 5
    await agent.stop()


async def test_eclss_pressure_history_tracking(bus: MessageBus):
    """EclssAgent tracks pressure history for leak detection."""
    from aria.agents.eclss import EclssAgent

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    for pressure in [14.7, 14.65, 14.6, 14.55, 14.5]:
        await bus.publish(Message(
            topic="aria.sensor.eclss.pressure",
            payload={"pressure_psi": pressure},
        ))
        await asyncio.sleep(0.05)

    assert len(agent._pressure_history) >= 3
    await agent.stop()


async def test_medical_multiple_crew_tracking(bus: MessageBus):
    """MedicalAgent tracks vitals for multiple crew members."""
    from aria.agents.medical import MedicalAgent

    tools = make_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    for crew in ["commander", "pilot", "ms1", "ms2"]:
        await bus.publish(Message(
            topic=f"aria.sensor.medical.vitals.{crew}",
            payload={"crew_id": crew, "heart_rate_bpm": 72, "spo2_percent": 98},
        ))
    await asyncio.sleep(0.2)

    assert len(agent._crew_vitals) == 4
    assert "commander" in agent._crew_vitals
    assert "ms2" in agent._crew_vitals
    await agent.stop()


async def test_thermal_radiator_deploy_on_overheat(bus: MessageBus):
    """ThermalAgent deploys radiator when zone exceeds max temp."""
    from aria.agents.thermal import ThermalAgent

    radiator_events: list[Message] = []
    bus.subscribe("aria.actuator.thermal.radiator", lambda m: radiator_events.append(m))

    tools = make_tools()
    agent = ThermalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Electronics bay max is 60°C — send 62°C
    await bus.publish(Message(
        topic="aria.sensor.thermal.electronics_bay",
        payload={"temperature_c": 62.0},
    ))
    await asyncio.sleep(0.2)

    deploy = [e for e in radiator_events if e.payload.get("action") == "deploy"]
    assert len(deploy) >= 1
    await agent.stop()


async def test_navigation_star_tracker_quaternion(bus: MessageBus):
    """NavigationAgent updates quaternion from star tracker."""
    from aria.agents.navigation import NavigationAgent

    tools = make_tools()
    agent = NavigationAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.nav.star_tracker",
        payload={"quaternion": [0.707, 0.0, 0.707, 0.0]},
    ))
    await asyncio.sleep(0.1)

    assert agent._quaternion == (0.707, 0.0, 0.707, 0.0)
    await agent.stop()


async def test_eclss_water_microbial_critical(bus: MessageBus):
    """EclssAgent CRITICAL on high microbial count in water."""
    from aria.agents.eclss import EclssAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.water",
        payload={"conductivity_us_cm": 200, "ph": 7.0, "microbial_cfu_ml": 100},
    ))
    await asyncio.sleep(0.2)

    critical = [a for a in alerts if a.payload.get("severity") == "CRITICAL" and "microbial" in a.payload.get("message", "").lower()]
    assert len(critical) >= 1
    await agent.stop()


async def test_power_negative_margin_warning(bus: MessageBus):
    """PowerAgent warns on negative power margin."""
    from aria.agents.power import PowerAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.power", lambda m: alerts.append(m))

    tools = make_tools()
    agent = PowerAgent(bus=bus, tool_registry=tools)
    agent._solar_power_w = 1000.0
    agent._total_load_w = 1500.0  # 500W negative margin
    await agent.start()

    await agent.periodic_task()
    await asyncio.sleep(0.1)

    margin_alerts = [a for a in alerts if "margin" in a.payload.get("message", "").lower()]
    assert len(margin_alerts) >= 1
    await agent.stop()


async def test_medical_bone_density_critical(bus: MessageBus):
    """MedicalAgent CRITICAL on osteoporosis-range bone density."""
    from aria.agents.medical import MedicalAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.medical.bone_density",
        payload={"crew_id": "ms1", "t_score": -3.0},
    ))
    await asyncio.sleep(0.2)

    critical = [a for a in alerts if a.payload.get("severity") == "CRITICAL"]
    assert len(critical) >= 1
    assert "osteoporosis" in critical[0].payload["message"].lower()
    await agent.stop()


async def test_science_radiation_emergency_shelter(bus: MessageBus):
    """ScienceAgent activates radiation shelter on SPE."""
    from aria.agents.science import ScienceAgent

    shelter: list[Message] = []
    bus.subscribe("aria.emergency.radiation.shelter", lambda m: shelter.append(m))

    tools = make_tools()
    agent = ScienceAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.science.radiation",
        payload={"dose_rate_usv_hr": 1500.0, "cumulative_dose_msv": 80.0},
    ))
    await asyncio.sleep(0.2)

    assert len(shelter) >= 1
    assert "crew_to_shelter" in shelter[0].payload["actions"]
    assert agent._radiation_shelter_active
    await agent.stop()


async def test_propulsion_fire_count_tracking(bus: MessageBus):
    """PropulsionAgent tracks total thruster fire count."""
    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools)
    await agent.start()

    for _ in range(3):
        await bus.publish(Message(
            topic="aria.command.propulsion.fire_thruster",
            payload={"thruster_id": "thruster_1", "duration_ms": 200, "thrust_level_pct": 50.0},
        ))
    await asyncio.sleep(0.3)

    assert agent._thrusters["thruster_1"]["fire_count"] == 3
    await agent.stop()


async def test_comms_message_priority_sorting(bus: MessageBus):
    """CommsAgent sorts outbound queue by priority."""
    tools = make_tools()
    agent = CommsAgent(bus=bus, tool_registry=tools)
    agent._link_active = False
    agent._in_contact = False
    await agent.start()

    # Queue messages in wrong order
    for priority in ["LOW", "EMERGENCY", "NORMAL", "HIGH"]:
        await bus.publish(Message(
            topic="aria.command.comms.send",
            payload={"message_type": "event", "priority": priority, "data": f"msg_{priority}"},
        ))
    await asyncio.sleep(0.2)

    # Queue should be sorted: EMERGENCY, HIGH, NORMAL, LOW
    priorities = [m["priority"] for m in agent._outbound_queue]
    assert priorities == ["EMERGENCY", "HIGH", "NORMAL", "LOW"]
    await agent.stop()


async def test_eclss_high_cabin_temperature_warning(bus: MessageBus):
    """EclssAgent warns on high cabin temperature."""
    from aria.agents.eclss import EclssAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 2.5, "humidity_percent": 45.0, "temperature_c": 33.0},
    ))
    await asyncio.sleep(0.2)

    temp_alerts = [a for a in alerts if "cabin" in a.payload.get("message", "").lower() and "temperature" in a.payload.get("message", "").lower()]
    assert len(temp_alerts) >= 1
    await agent.stop()


async def test_medical_career_dose_warning(bus: MessageBus):
    """MedicalAgent warns on approaching career radiation limit."""
    from aria.agents.medical import MedicalAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    tools = make_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.medical.radiation",
        payload={"crew_id": "pilot", "cumulative_dose_msv": 350.0},
    ))
    await asyncio.sleep(0.2)

    dose_alerts = [a for a in alerts if "radiation" in a.payload.get("message", "").lower() and "msv" in a.payload.get("message", "").lower()]
    assert len(dose_alerts) >= 1
    await agent.stop()


async def test_navigation_conjunction_warning_severity(bus: MessageBus):
    """NavigationAgent classifies conjunction by Pc: WARNING for 1e-4 to 1e-3."""
    from aria.agents.navigation import NavigationAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.conjunction", lambda m: alerts.append(m))

    tools = make_tools()
    agent = NavigationAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.conjunction.alert",
        payload={"object_name": "SAT-X", "time_to_tca_hours": 12.0, "collision_probability": 5e-4},
    ))
    await asyncio.sleep(0.2)

    assert len(alerts) >= 1
    assert alerts[0].payload["severity"] == "WARNING"
    await agent.stop()


async def test_navigation_conjunction_watch_severity(bus: MessageBus):
    """NavigationAgent classifies low-Pc conjunction as WATCH."""
    from aria.agents.navigation import NavigationAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.conjunction", lambda m: alerts.append(m))

    tools = make_tools()
    agent = NavigationAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.conjunction.alert",
        payload={"object_name": "DEBRIS-LOW", "time_to_tca_hours": 48.0, "collision_probability": 5e-5},
    ))
    await asyncio.sleep(0.2)

    assert len(alerts) >= 1
    assert alerts[0].payload["severity"] == "WATCH"
    await agent.stop()


async def test_thermal_eclipse_preheat_activates(bus: MessageBus):
    """ThermalAgent pre-heats battery zone during eclipse when cold."""
    from aria.agents.thermal import ThermalAgent
    from aria.state.scratchpad import SharedScratchpad

    heater_events: list[Message] = []
    bus.subscribe("aria.actuator.thermal.heater.*", lambda m: heater_events.append(m))

    sp = SharedScratchpad()
    sp.write("power.eclipse_state", {"in_eclipse": True, "solar_power_w": 0, "battery_soc": 70}, "power")

    tools = make_tools()
    agent = ThermalAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    # Set battery zone cold
    agent._zones["battery_pack"].temperature_c = 15.0
    agent._zones["battery_pack"].heater_on = False
    await agent.start()

    await agent.periodic_task()
    await asyncio.sleep(0.1)

    preheat = [e for e in heater_events if e.payload.get("reason") == "eclipse_preheat"]
    assert len(preheat) >= 1
    await agent.stop()


async def test_power_eclipse_detection(bus: MessageBus):
    """PowerAgent correctly detects eclipse from zero solar power."""
    from aria.agents.power import PowerAgent

    tools = make_tools()
    agent = PowerAgent(bus=bus, tool_registry=tools)
    assert not agent._in_eclipse

    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.power.solar",
        payload={"power_watts": 0.0},
    ))
    await asyncio.sleep(0.1)

    assert agent._in_eclipse
    await agent.stop()


async def test_eclss_low_o2_critical(bus: MessageBus):
    """EclssAgent raises CRITICAL on dangerously low O2."""
    from aria.agents.eclss import EclssAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 18.0, "co2_mmhg": 3.0, "humidity_percent": 45.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(0.2)

    critical = [a for a in alerts if a.payload.get("severity") == "CRITICAL" and "o2" in a.payload.get("message", "").lower()]
    assert len(critical) >= 1
    await agent.stop()


async def test_propulsion_delta_v_tracking(bus: MessageBus):
    """PropulsionAgent tracks cumulative delta-V across burns."""
    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools)
    initial_dv = agent._delta_v_used_ms
    await agent.start()

    # Two burns
    for _ in range(2):
        await bus.publish(Message(
            topic="aria.command.propulsion.fire_thruster",
            payload={"thruster_id": "thruster_2", "duration_ms": 500, "thrust_level_pct": 80.0},
        ))
    await asyncio.sleep(0.3)

    assert agent._delta_v_used_ms > initial_dv
    await agent.stop()


async def test_comms_bytes_tracking(bus: MessageBus):
    """CommsAgent tracks bytes sent."""
    tools = make_tools()
    agent = CommsAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.command.comms.send",
        payload={"message_type": "telemetry", "priority": "NORMAL", "data": "x" * 1000},
    ))
    await asyncio.sleep(0.2)

    assert agent._bytes_downlinked >= 1000 or agent._bytes_queued >= 1000
    await agent.stop()


async def test_science_data_collected_tracking(bus: MessageBus):
    """ScienceAgent tracks total data collected in MB."""
    from aria.agents.science import ScienceAgent

    tools = make_tools()
    agent = ScienceAgent(bus=bus, tool_registry=tools)
    await agent.start()

    for mb in [10.5, 25.0, 5.5]:
        await bus.publish(Message(
            topic="aria.sensor.science.spectrometer",
            payload={"status": "complete", "observation_complete": True, "data_size_mb": mb},
        ))
    await asyncio.sleep(0.2)

    assert agent._data_collected_mb == 41.0
    await agent.stop()


async def test_medical_fatigue_classification(bus: MessageBus):
    """MedicalAgent correctly classifies fatigue levels."""
    from aria.agents.medical import MedicalAgent

    tools = make_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Good sleep
    await bus.publish(Message(
        topic="aria.sensor.medical.sleep",
        payload={"crew_id": "commander", "quality_score": 80, "duration_hours": 8.0},
    ))
    await asyncio.sleep(0.1)
    assert agent._crew_fatigue.get("commander") == "low"

    # Bad sleep
    await bus.publish(Message(
        topic="aria.sensor.medical.sleep",
        payload={"crew_id": "pilot", "quality_score": 20, "duration_hours": 3.0},
    ))
    await asyncio.sleep(0.1)
    assert agent._crew_fatigue.get("pilot") == "critical"

    await agent.stop()


async def test_eclss_co2_watch_level(bus: MessageBus):
    """EclssAgent raises WATCH at CO2 threshold."""
    from aria.agents.eclss import EclssAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 5.5, "humidity_percent": 45.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(0.2)

    watch = [a for a in alerts if a.payload.get("severity") == "WATCH" and "co2" in a.payload.get("message", "").lower()]
    assert len(watch) >= 1
    await agent.stop()


async def test_thermal_zone_status_tracking(bus: MessageBus):
    """ThermalAgent tracks multiple zone temperatures."""
    from aria.agents.thermal import ThermalAgent

    tools = make_tools()
    agent = ThermalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    zones = {"battery_pack": 22.0, "electronics_bay": 30.0, "crew_cabin": 23.0}
    for zone, temp in zones.items():
        await bus.publish(Message(
            topic=f"aria.sensor.thermal.{zone}",
            payload={"temperature_c": temp},
        ))
    await asyncio.sleep(0.2)

    for zone, temp in zones.items():
        assert agent._zones[zone].temperature_c == temp
    await agent.stop()


async def test_navigation_active_conjunction_tracking(bus: MessageBus):
    """NavigationAgent tracks active conjunction count."""
    from aria.agents.navigation import NavigationAgent

    tools = make_tools()
    agent = NavigationAgent(bus=bus, tool_registry=tools)
    await agent.start()

    for i in range(3):
        await bus.publish(Message(
            topic="aria.conjunction.alert",
            payload={"object_name": f"OBJ-{i}", "time_to_tca_hours": 10 + i, "collision_probability": 1e-5},
        ))
    await asyncio.sleep(0.2)

    assert len(agent._active_conjunctions) == 3
    await agent.stop()


async def test_comms_status_response(bus: MessageBus):
    """CommsAgent responds to status command."""
    responses: list[Message] = []
    bus.subscribe("aria.comms.status.response", lambda m: responses.append(m))

    tools = make_tools()
    agent = CommsAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.command.comms.status",
        payload={},
    ))
    await asyncio.sleep(0.2)

    assert len(responses) >= 1
    assert "link_active" in responses[0].payload
    await agent.stop()


async def test_eclss_scratchpad_includes_fire_state(bus: MessageBus):
    """EclssAgent scratchpad includes N2, smoke, and CO data."""
    from aria.agents.eclss import EclssAgent
    from aria.state.scratchpad import SharedScratchpad

    sp = SharedScratchpad()
    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 2.5, "humidity_percent": 45.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(0.1)

    atmo = sp.read("eclss.atmosphere")
    assert atmo is not None
    assert "n2_percent" in atmo
    assert "smoke_detected" in atmo
    assert "co_ppm" in atmo
    await agent.stop()


async def test_propulsion_fuel_efficiency_tracking(bus: MessageBus):
    """PropulsionAgent tracks total fuel used for efficiency analysis."""
    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools)
    assert agent._total_fuel_used_kg == 0.0
    await agent.start()

    await bus.publish(Message(
        topic="aria.command.propulsion.fire_thruster",
        payload={"thruster_id": "thruster_1", "duration_ms": 2000, "thrust_level_pct": 100.0},
    ))
    await asyncio.sleep(0.2)

    assert agent._total_fuel_used_kg > 0
    assert agent._theoretical_dv_ms > 0
    await agent.stop()


async def test_eclss_scratchpad_atmosphere_complete(bus: MessageBus):
    """EclssAgent scratchpad has all atmosphere fields."""
    from aria.agents.eclss import EclssAgent
    from aria.state.scratchpad import SharedScratchpad

    sp = SharedScratchpad()
    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 2.5, "humidity_percent": 45.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(0.1)

    atmo = sp.read("eclss.atmosphere")
    assert atmo is not None
    required_fields = ["o2_percent", "co2_mmhg", "humidity_percent", "temperature_c", "pressure_psi", "n2_percent", "smoke_detected", "co_ppm"]
    for field in required_fields:
        assert field in atmo, f"Missing field: {field}"
    await agent.stop()


async def test_power_scratchpad_eclipse_and_prediction(bus: MessageBus):
    """PowerAgent posts both eclipse state AND prediction to scratchpad."""
    from aria.agents.power import PowerAgent
    from aria.state.scratchpad import SharedScratchpad

    sp = SharedScratchpad()
    tools = make_tools()
    agent = PowerAgent(bus=bus, tool_registry=tools, scratchpad=sp)
    agent._battery_soc = 60.0
    agent._total_load_w = 800.0
    await agent.start()

    # Send solar data to trigger eclipse state post
    await bus.publish(Message(
        topic="aria.sensor.power.solar",
        payload={"power_watts": 2000.0},
    ))
    await asyncio.sleep(0.1)

    # Trigger periodic for prediction
    await agent.periodic_task()
    await asyncio.sleep(0.1)

    eclipse = sp.read("power.eclipse_state")
    assert eclipse is not None

    pred = sp.read("power.prediction")
    assert pred is not None
    assert "battery_soc" in pred

    await agent.stop()


async def test_power_battery_soh_warning(bus: MessageBus):
    """PowerAgent warns when battery SoH drops below 80%."""
    from aria.agents.power import PowerAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.power", lambda m: alerts.append(m))

    tools = make_tools()
    agent = PowerAgent(bus=bus, tool_registry=tools)
    agent._battery_soh = 78.0  # Already degraded
    agent._charge_cycles = 1500
    await agent.start()

    # Any battery update triggers SoH check
    await bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 85.0, "temperature_c": 25.0},
    ))
    await asyncio.sleep(0.2)

    soh_alerts = [a for a in alerts if "soh" in a.payload.get("message", "").lower()]
    assert len(soh_alerts) >= 1
    await agent.stop()


async def test_navigation_nav_state_response(bus: MessageBus):
    """NavigationAgent responds to nav status command."""
    from aria.agents.navigation import NavigationAgent

    responses: list[Message] = []
    bus.subscribe("aria.nav.state.response", lambda m: responses.append(m))

    tools = make_tools()
    agent = NavigationAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.command.nav.status",
        payload={},
    ))
    await asyncio.sleep(0.2)

    assert len(responses) >= 1
    assert "altitude_km" in responses[0].payload
    assert "orbital_period_min" in responses[0].payload
    await agent.stop()


async def test_propulsion_status_published(bus: MessageBus):
    """PropulsionAgent publishes fuel status periodically."""
    fuel_status: list[Message] = []
    bus.subscribe("aria.propulsion.status", lambda m: fuel_status.append(m))

    tools = make_tools()
    agent = PropulsionAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await agent.periodic_task()
    await asyncio.sleep(0.1)

    assert len(fuel_status) >= 1
    assert "propellant_kg" in fuel_status[0].payload
    assert "delta_v_remaining_ms" in fuel_status[0].payload
    await agent.stop()


async def test_thermal_multiple_zone_heater_control(bus: MessageBus):
    """ThermalAgent independently controls heaters per zone."""
    from aria.agents.thermal import ThermalAgent

    heater_events: list[Message] = []
    bus.subscribe("aria.actuator.thermal.heater.*", lambda m: heater_events.append(m))

    tools = make_tools()
    agent = ThermalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    # Cold battery zone → heater on
    await bus.publish(Message(
        topic="aria.sensor.thermal.battery_pack",
        payload={"temperature_c": 14.0},
    ))
    # Warm electronics → no heater change  
    await bus.publish(Message(
        topic="aria.sensor.thermal.electronics_bay",
        payload={"temperature_c": 30.0},
    ))
    await asyncio.sleep(0.2)

    # Only battery_pack should have heater event
    battery_events = [e for e in heater_events if "battery_pack" in e.topic]
    assert len(battery_events) >= 1
    assert battery_events[0].payload["heater"] == "on"
    await agent.stop()


async def test_medical_stats_property(bus: MessageBus):
    """MedicalAgent stats include crew monitoring info."""
    from aria.agents.medical import MedicalAgent

    tools = make_tools()
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    agent._crew_vitals["commander"] = {"heart_rate_bpm": 72}
    await agent.start()

    stats = agent.stats
    assert stats["crew_monitored"] == 1
    assert "fatigue_levels" in stats
    await agent.stop()


async def test_science_stats_property(bus: MessageBus):
    """ScienceAgent stats include observation and radiation data."""
    from aria.agents.science import ScienceAgent

    tools = make_tools()
    agent = ScienceAgent(bus=bus, tool_registry=tools)
    agent._observations_count = 5
    agent._data_collected_mb = 75.0
    await agent.start()

    stats = agent.stats
    assert stats["observations"] == 5
    assert stats["data_collected_mb"] == 75.0
    await agent.stop()


async def test_eclss_co2_emergency_level(bus: MessageBus):
    """EclssAgent raises EMERGENCY on life-threatening CO2."""
    from aria.agents.eclss import EclssAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 19.0, "co2_mmhg": 16.0, "humidity_percent": 45.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(0.2)

    emergency = [a for a in alerts if a.payload.get("severity") == "EMERGENCY" and "co2" in a.payload.get("message", "").lower()]
    assert len(emergency) >= 1
    await agent.stop()


async def test_navigation_imu_dsremo_scoring(bus: MessageBus):
    """NavigationAgent runs Dsremo ML on IMU data."""
    from aria.agents.navigation import NavigationAgent

    tools = make_tools(score=0.75)  # High anomaly score
    agent = NavigationAgent(bus=bus, tool_registry=tools)
    await agent.start()

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.navigation", lambda m: alerts.append(m))

    await bus.publish(Message(
        topic="aria.sensor.nav.imu",
        payload={"angular_rate_x_dps": 0.5, "angular_rate_y_dps": 0.3, "angular_rate_z_dps": 0.2},
    ))
    await asyncio.sleep(0.2)

    dsremo_alerts = [a for a in alerts if "dsremo" in a.payload.get("message", "").lower()]
    assert len(dsremo_alerts) >= 1
    await agent.stop()


async def test_telemetry_agent_stats(bus: MessageBus):
    """TelemetryAgent stats include readings and anomaly counts."""
    from aria.agents.telemetry import TelemetryAgent

    tools = make_tools()
    agent = TelemetryAgent(bus=bus, tool_registry=tools)
    await agent.start()

    stats = agent.stats
    assert "readings_processed" in stats
    assert "anomalies_detected" in stats
    assert "channels_tracked" in stats
    await agent.stop()


async def test_eclss_depressurization_invokes_tool(bus: MessageBus):
    """EclssAgent invokes depressurization tool on critical pressure."""
    from aria.agents.eclss import EclssAgent

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    tools = make_tools()
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.pressure",
        payload={"pressure_psi": 12.0},
    ))
    await asyncio.sleep(0.2)

    emergency = [a for a in alerts if a.payload.get("severity") == "EMERGENCY"]
    assert len(emergency) >= 1
    await agent.stop()


async def test_power_dsremo_battery_scoring(bus: MessageBus):
    """PowerAgent runs Dsremo batch scoring on battery parameters."""
    from aria.agents.power import PowerAgent

    tools = make_tools(score=0.72)  # WARNING-level score
    agent = PowerAgent(bus=bus, tool_registry=tools)
    await agent.start()

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.power", lambda m: alerts.append(m))

    await bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 50.0, "temperature_c": 25.0},
    ))
    await asyncio.sleep(0.2)

    dsremo_alerts = [a for a in alerts if "dsremo" in a.payload.get("message", "").lower()]
    assert len(dsremo_alerts) >= 1
    await agent.stop()


async def test_eclss_dsremo_atmosphere_scoring(bus: MessageBus):
    """EclssAgent runs Dsremo batch scoring on atmosphere parameters."""
    from aria.agents.eclss import EclssAgent

    tools = make_tools(score=0.70)  # WARNING level
    agent = EclssAgent(bus=bus, tool_registry=tools)
    await agent.start()

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.eclss", lambda m: alerts.append(m))

    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 2.5, "humidity_percent": 45.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(0.2)

    dsremo_alerts = [a for a in alerts if "dsremo" in a.payload.get("message", "").lower()]
    assert len(dsremo_alerts) >= 1
    await agent.stop()


async def test_propulsion_dsremo_tank_scoring(bus: MessageBus):
    """PropulsionAgent runs Dsremo batch scoring on tank parameters."""
    tools = make_tools(score=0.68)  # WARNING level
    agent = PropulsionAgent(bus=bus, tool_registry=tools)
    agent._initial_propellant_kg = 100.0
    await agent.start()

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.propulsion", lambda m: alerts.append(m))

    await bus.publish(Message(
        topic="aria.sensor.propulsion.tank",
        payload={"propellant_kg": 80.0, "pressure_psi": 250.0, "temperature_c": 20.0},
    ))
    await asyncio.sleep(0.2)

    dsremo_alerts = [a for a in alerts if "dsremo" in a.payload.get("message", "").lower()]
    assert len(dsremo_alerts) >= 1
    await agent.stop()


async def test_comms_dsremo_link_scoring(bus: MessageBus):
    """CommsAgent runs Dsremo ML on link parameters."""
    tools = make_tools(score=0.70)
    agent = CommsAgent(bus=bus, tool_registry=tools)
    await agent.start()

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.comms", lambda m: alerts.append(m))

    await bus.publish(Message(
        topic="aria.sensor.comms.link",
        payload={"signal_dbm": -90.0, "snr_db": 12.0, "ber": 1e-8, "data_rate_kbps": 128.0},
    ))
    await asyncio.sleep(0.2)

    dsremo = [a for a in alerts if "dsremo" in a.payload.get("message", "").lower()]
    assert len(dsremo) >= 1
    await agent.stop()


async def test_thermal_dsremo_coolant_scoring(bus: MessageBus):
    """ThermalAgent runs Dsremo on coolant parameters."""
    from aria.agents.thermal import ThermalAgent

    tools = make_tools(score=0.72)
    agent = ThermalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.thermal", lambda m: alerts.append(m))

    await bus.publish(Message(
        topic="aria.sensor.thermal.coolant",
        payload={"pressure_psi": 25.0, "flow_rate_lpm": 4.0, "temperature_c": 18.0},
    ))
    await asyncio.sleep(0.2)

    dsremo = [a for a in alerts if "dsremo" in a.payload.get("message", "").lower()]
    assert len(dsremo) >= 1
    await agent.stop()


async def test_science_dsremo_radiation_scoring(bus: MessageBus):
    """ScienceAgent runs Dsremo on radiation data."""
    from aria.agents.science import ScienceAgent

    tools = make_tools(score=0.68)
    agent = ScienceAgent(bus=bus, tool_registry=tools)
    await agent.start()

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.science", lambda m: alerts.append(m))

    await bus.publish(Message(
        topic="aria.sensor.science.radiation",
        payload={"dose_rate_usv_hr": 2.0, "cumulative_dose_msv": 30.0},
    ))
    await asyncio.sleep(0.2)

    dsremo = [a for a in alerts if "dsremo" in a.payload.get("message", "").lower()]
    assert len(dsremo) >= 1
    await agent.stop()


async def test_medical_dsremo_vitals_scoring(bus: MessageBus):
    """MedicalAgent runs Dsremo on crew vital signs."""
    from aria.agents.medical import MedicalAgent

    tools = make_tools(score=0.66)
    agent = MedicalAgent(bus=bus, tool_registry=tools)
    await agent.start()

    alerts: list[Message] = []
    bus.subscribe("aria.anomaly.medical", lambda m: alerts.append(m))

    await bus.publish(Message(
        topic="aria.sensor.medical.vitals.test",
        payload={"crew_id": "test", "heart_rate_bpm": 75, "spo2_percent": 97, "temperature_c": 36.8},
    ))
    await asyncio.sleep(0.2)

    dsremo = [a for a in alerts if "dsremo" in a.payload.get("message", "").lower()]
    assert len(dsremo) >= 1
    await agent.stop()
