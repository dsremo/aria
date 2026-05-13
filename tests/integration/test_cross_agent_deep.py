"""Deep cross-agent integration tests — verify intelligence pipelines via SharedScratchpad.

Each test exercises a real cross-agent communication pathway:
  Agent A posts state to SharedScratchpad -> Agent B reads it -> Agent B reacts

These tests prove that the scratchpad-mediated intelligence sharing actually
works end-to-end, not just that individual agents can read/write.

Tested pipelines:
  1.  Power eclipse -> Thermal preheat
  2.  Power battery prediction -> Science observation deferral
  3.  Nav conjunction -> Propulsion fuel readiness check
  4.  Science radiation -> Medical dose accumulation
  5.  ECLSS CO2 -> Medical cognitive alert
  6.  ECLSS fire -> Medical smoke inhalation risk
  7.  Propulsion low fuel -> Thermal freeze protection
  8.  Nav orbital state -> Comms contact prediction
  9.  Power critical battery -> Thermal heater shed
  10. Propulsion low delta-V -> Navigation warning
  11. Science biosignature -> Comms HIGH priority downlink
  12. Multiple simultaneous pipelines
  13. Scratchpad entry expiry
  14. All agents post after sensor data
  15. Cognitive engine includes scratchpad in LLM context
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
from aria.cognitive.engine import CognitiveEngine
from aria.core.tool import ARIATool, ToolResult
from aria.core.types import AuthorityLevel, EventPriority, SafetyLevel, ToolCategory
from aria.state.scratchpad import SharedScratchpad
from aria.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Mock tools — all agents call Dsremo/diagnostic/etc tools at startup or on
# sensor data. We stub everything to keep tests focused on cross-agent logic.
# ---------------------------------------------------------------------------

class _MockTool(ARIATool):
    """Generic mock tool that records calls and returns configurable data."""
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def __init__(self, tool_name: str, data: Any = None, description: str = "mock") -> None:
        self.name = tool_name  # type: ignore[assignment]
        self.description = description  # type: ignore[assignment]
        self._data = data or {}
        self.calls: list[dict[str, Any]] = []
        super().__init__()

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        self.calls.append(params)
        return ToolResult(success=True, data=self._data)


class _MockDsremoIngest(_MockTool):
    def __init__(self, score: float = 0.05) -> None:
        super().__init__(
            tool_name="dsremo_ingest_telemetry",
            data={"anomaly_score": score, "detectors_triggered": []},
        )


class _MockDsremoBatch(_MockTool):
    def __init__(self, score: float = 0.05) -> None:
        self._score = score
        super().__init__(tool_name="dsremo_ingest_batch", data={})

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        self.calls.append(params)
        readings = params.get("readings", [])
        results = [
            {"channel_id": r["channel_id"], "anomaly_score": self._score, "detectors_triggered": []}
            for r in readings
        ]
        return ToolResult(success=True, data={"results": results, "count": len(readings)})


def _make_tools(score: float = 0.05) -> ToolRegistry:
    """Build a ToolRegistry loaded with every mock tool that agents may call."""
    reg = ToolRegistry()
    reg.register(_MockDsremoIngest(score=score))
    reg.register(_MockDsremoBatch(score=score))
    # Diagnostic tool used by on_start() of most agents
    reg.register(_MockTool("diagnostic_run_subsystem_test", data={"result": "PASS"}))
    # Power tools
    reg.register(_MockTool("eps_load_shed", data={"shed": True}))
    reg.register(_MockTool("eps_get_power_budget", data={"margin_w": 200, "consumption_w": 800}))
    # Navigation tools
    reg.register(_MockTool("conjunction_watch_run_screening", data={"high_risk_events": []}))
    reg.register(_MockTool("navigation_orbit_determination", data={"converged": True}))
    reg.register(_MockTool("conjunction_watch_plan_maneuver", data={}))
    reg.register(_MockTool("adcs_desaturate_wheels", data={}))
    reg.register(_MockTool("emergency_safe_mode", data={}))
    # ECLSS tools
    reg.register(_MockTool("eclss_set_o2_rate", data={}))
    reg.register(_MockTool("emergency_depressurization_response", data={}))
    reg.register(_MockTool("emergency_fire_suppression", data={}))
    reg.register(_MockTool("emergency_evacuation_alert", data={}))
    reg.register(_MockTool("genastra_air_quality_analysis", data={}))
    # Medical tools
    reg.register(_MockTool("crew_medical_alert", data={}))
    reg.register(_MockTool("crew_alert", data={}))
    # Science / GenAstra tools
    reg.register(_MockTool("genastra_analyze_biosignature", data={
        "detection": True, "confidence": 0.85, "markers": ["amino_acid"],
    }))
    reg.register(_MockTool("genastra_crew_radiation_dose", data={"risk": "low"}))
    reg.register(_MockTool("learning_calibrate_sensor", data={}))
    # Propulsion tools
    reg.register(_MockTool("conjwatch_compute_pc", data={"pc_foster": 1e-7}))
    return reg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def bus() -> MessageBus:  # type: ignore[misc]
    b = MessageBus(max_history=5000)
    await b.start()
    yield b  # type: ignore[misc]
    await b.stop()


@pytest.fixture
def scratchpad() -> SharedScratchpad:
    return SharedScratchpad()


@pytest.fixture
def tools() -> ToolRegistry:
    return _make_tools()


# ---------------------------------------------------------------------------
# Helper: collect messages on a topic pattern
# ---------------------------------------------------------------------------

class _Collector:
    """Subscribe to a topic pattern and collect delivered messages."""
    def __init__(self, bus: MessageBus, pattern: str) -> None:
        self.messages: list[Message] = []
        bus.subscribe(pattern, self._on_msg)

    async def _on_msg(self, msg: Message) -> None:
        self.messages.append(msg)


# ---------------------------------------------------------------------------
# 1. Power eclipse -> Thermal preheat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_power_eclipse_triggers_thermal_preheat(
    bus: MessageBus, scratchpad: SharedScratchpad, tools: ToolRegistry,
) -> None:
    """PowerAgent posts eclipse state to scratchpad; ThermalAgent reads it and
    pre-heats battery_pack and propulsion zones."""
    heater_cmds = _Collector(bus, "aria.actuator.thermal.*")

    power = PowerAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    thermal = ThermalAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    await power.start()
    await thermal.start()

    # Send solar data showing eclipse (0 watts)
    await bus.publish(Message(
        topic="aria.sensor.power.solar",
        payload={"power_watts": 0.0},
    ))
    await asyncio.sleep(0.3)

    # Verify scratchpad has eclipse state
    eclipse = scratchpad.read("power.eclipse_state")
    assert eclipse is not None, "PowerAgent should post eclipse state"
    assert eclipse["in_eclipse"] is True

    # Force thermal periodic to read scratchpad
    # Set zones below setpoint to trigger preheat logic
    thermal._zones["battery_pack"].temperature_c = 10.0
    thermal._zones["propulsion"].temperature_c = 5.0
    await thermal.periodic_task()
    await asyncio.sleep(0.3)

    # Verify heater commands were published for battery_pack and propulsion
    heater_zones = {m.payload.get("zone") for m in heater_cmds.messages
                    if m.payload.get("heater") == "on"}
    assert "battery_pack" in heater_zones, "Thermal should preheat battery_pack during eclipse"
    assert "propulsion" in heater_zones, "Thermal should preheat propulsion during eclipse"

    await power.stop()
    await thermal.stop()


# ---------------------------------------------------------------------------
# 2. Power prediction -> Science observation deferral
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_power_prediction_defers_science_observation(
    bus: MessageBus, scratchpad: SharedScratchpad, tools: ToolRegistry,
) -> None:
    """When PowerAgent predicts battery depletion < 2h, ScienceAgent defers
    observation requests."""
    deferred = _Collector(bus, "aria.science.observation.deferred")

    # Pre-populate power prediction showing imminent depletion
    scratchpad.write("power.prediction", {
        "battery_soc": 12.0,
        "power_margin_w": -200,
        "hours_to_depletion": 1.5,
        "in_eclipse": True,
        "load_shed_active": False,
    }, "power", ttl_s=120)

    science = ScienceAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    await science.start()

    # Request an observation
    await bus.publish(Message(
        topic="aria.command.science.observe",
        payload={"target": "NGC-1234", "instrument": "spectrometer"},
        correlation_id="obs-001",
    ))
    await asyncio.sleep(0.3)

    assert len(deferred.messages) >= 1, "Science should defer observation when battery < 2h"
    payload = deferred.messages[0].payload
    assert "1.5" in payload["reason"] or "depletion" in payload["reason"].lower()

    await science.stop()


# ---------------------------------------------------------------------------
# 3. Nav conjunction -> Propulsion fuel readiness
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nav_conjunction_triggers_propulsion_readiness(
    bus: MessageBus, scratchpad: SharedScratchpad, tools: ToolRegistry,
) -> None:
    """NavigationAgent posts high-risk conjunction; PropulsionAgent checks fuel
    readiness during periodic_task."""
    prop_alerts = _Collector(bus, "aria.anomaly.propulsion")

    nav = NavigationAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    prop = PropulsionAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    await nav.start()
    await prop.start()

    # NavigationAgent receives conjunction alert
    await bus.publish(Message(
        topic="aria.conjunction.alert",
        payload={
            "collision_probability": 5e-4,
            "time_to_tca_hours": 12.0,
            "object_name": "COSMOS-DEBRIS-42",
        },
    ))
    await asyncio.sleep(0.3)

    # Verify conjunction landed in scratchpad
    conj = scratchpad.read("nav.next_conjunction")
    assert conj is not None, "Nav should post conjunction to scratchpad"
    assert conj["collision_probability"] == 5e-4

    # Set propulsion fuel very low so the readiness check triggers a warning
    prop._propellant_kg = 0.5
    prop._initial_propellant_kg = 100.0
    await prop.periodic_task()
    await asyncio.sleep(0.3)

    # PropulsionAgent should warn about low fuel for avoidance
    fuel_warnings = [m for m in prop_alerts.messages
                     if "fuel" in m.payload.get("message", "").lower()
                     or "avoidance" in m.payload.get("message", "").lower()]
    assert len(fuel_warnings) >= 1, "Propulsion should warn about low fuel for conjunction avoidance"

    await nav.stop()
    await prop.stop()


# ---------------------------------------------------------------------------
# 4. Science radiation -> Medical dose accumulation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_science_radiation_updates_medical_dose(
    bus: MessageBus, scratchpad: SharedScratchpad, tools: ToolRegistry,
) -> None:
    """ScienceAgent posts radiation data; MedicalAgent accumulates crew dose
    during periodic_task."""
    science = ScienceAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    medical = MedicalAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    await science.start()
    await medical.start()

    # Register a crew member in medical
    medical._crew_vitals["crew_a"] = {"heart_rate_bpm": 72.0}
    medical._crew_radiation_msv["crew_a"] = 50.0

    # ScienceAgent receives elevated radiation
    await bus.publish(Message(
        topic="aria.sensor.science.radiation",
        payload={"dose_rate_usv_hr": 300.0, "cumulative_dose_msv": 120.0},
    ))
    await asyncio.sleep(0.3)

    # Verify scratchpad
    rad = scratchpad.read("science.radiation")
    assert rad is not None, "Science should post radiation to scratchpad"
    assert rad["dose_rate_usv_hr"] == 300.0

    # Medical periodic reads scratchpad and accumulates dose
    initial_dose = medical._crew_radiation_msv["crew_a"]
    await medical.periodic_task()
    await asyncio.sleep(0.1)
    new_dose = medical._crew_radiation_msv["crew_a"]
    assert new_dose > initial_dose, "Medical should accumulate crew radiation from scratchpad"

    await science.stop()
    await medical.stop()


# ---------------------------------------------------------------------------
# 5. ECLSS CO2 -> Medical cognitive alert
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_eclss_co2_triggers_medical_cognitive_alert(
    bus: MessageBus, scratchpad: SharedScratchpad, tools: ToolRegistry,
) -> None:
    """ECLSS posts high CO2 to scratchpad; MedicalAgent raises cognitive
    degradation alert during periodic_task."""
    med_alerts = _Collector(bus, "aria.anomaly.medical")

    eclss = EclssAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    medical = MedicalAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    await eclss.start()
    await medical.start()

    # Register a crew member
    medical._crew_vitals["crew_b"] = {"heart_rate_bpm": 68.0}

    # ECLSS receives atmosphere data with high CO2
    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 8.0, "humidity_percent": 45.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(0.3)

    # Verify scratchpad has atmosphere data
    atmo = scratchpad.read("eclss.atmosphere")
    assert atmo is not None, "ECLSS should post atmosphere to scratchpad"
    assert atmo["co2_mmhg"] == 8.0

    # Medical reads scratchpad in periodic_task
    await medical.periodic_task()
    await asyncio.sleep(0.3)

    # Should have cognitive alert
    co2_alerts = [m for m in med_alerts.messages
                  if "co2" in m.payload.get("message", "").lower()
                  or "cognitive" in m.payload.get("message", "").lower()]
    assert len(co2_alerts) >= 1, "Medical should alert about CO2 cognitive impact"

    await eclss.stop()
    await medical.stop()


# ---------------------------------------------------------------------------
# 6. ECLSS fire -> Medical smoke inhalation risk
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_eclss_fire_triggers_medical_inhalation(
    bus: MessageBus, scratchpad: SharedScratchpad, tools: ToolRegistry,
) -> None:
    """ECLSS posts fire/smoke state; MedicalAgent warns about smoke inhalation
    risk for each crew member."""
    med_alerts = _Collector(bus, "aria.anomaly.medical")

    eclss = EclssAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    medical = MedicalAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    await eclss.start()
    await medical.start()

    # Register crew
    medical._crew_vitals["crew_c"] = {"heart_rate_bpm": 75.0}

    # Fire detected
    await bus.publish(Message(
        topic="aria.sensor.fire.smoke",
        payload={"detected": True, "zone": "lab_module"},
    ))
    await asyncio.sleep(0.3)

    # Verify fire state in scratchpad
    fire = scratchpad.read("eclss.fire_state")
    assert fire is not None, "ECLSS should post fire state to scratchpad"
    assert fire["smoke_detected"] is True
    assert fire["zone"] == "lab_module"

    # Medical reads fire state in periodic
    await medical.periodic_task()
    await asyncio.sleep(0.3)

    smoke_alerts = [m for m in med_alerts.messages
                    if "smoke" in m.payload.get("message", "").lower()
                    or "inhalation" in m.payload.get("message", "").lower()]
    assert len(smoke_alerts) >= 1, "Medical should alert about smoke inhalation risk"

    await eclss.stop()
    await medical.stop()


# ---------------------------------------------------------------------------
# 7. Propulsion low fuel -> Thermal freeze protection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_propulsion_fuel_triggers_thermal_freeze_protect(
    bus: MessageBus, scratchpad: SharedScratchpad, tools: ToolRegistry,
) -> None:
    """PropulsionAgent posts low fuel status; ThermalAgent turns on propulsion
    zone heater to protect fuel lines from freezing."""
    heater_cmds = _Collector(bus, "aria.actuator.thermal.*")

    prop = PropulsionAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    thermal = ThermalAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    await prop.start()
    await thermal.start()

    # Set propulsion fuel very low
    prop._propellant_kg = 10.0
    prop._initial_propellant_kg = 100.0
    await prop.periodic_task()
    await asyncio.sleep(0.2)

    # Verify fuel status in scratchpad
    fuel = scratchpad.read("propulsion.fuel_status")
    assert fuel is not None, "Propulsion should post fuel status"
    assert fuel["fuel_fraction"] < 0.15

    # Ensure propulsion zone heater is off initially
    thermal._zones["propulsion"].heater_on = False
    await thermal.periodic_task()
    await asyncio.sleep(0.3)

    # ThermalAgent should turn on propulsion heater
    prop_heater_on = [m for m in heater_cmds.messages
                      if m.payload.get("zone") == "propulsion"
                      and m.payload.get("heater") == "on"]
    assert len(prop_heater_on) >= 1, "Thermal should protect fuel lines when fuel is low"

    await prop.stop()
    await thermal.stop()


# ---------------------------------------------------------------------------
# 8. Nav orbital state -> Comms contact prediction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nav_orbital_state_helps_comms_prediction(
    bus: MessageBus, scratchpad: SharedScratchpad, tools: ToolRegistry,
) -> None:
    """NavigationAgent posts orbital state (period); CommsAgent reads it to
    estimate next ground contact window."""
    nav = NavigationAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    comms = CommsAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    await nav.start()
    await comms.start()

    # Nav periodic posts orbital state
    await nav.periodic_task()
    await asyncio.sleep(0.2)

    # Verify orbital state in scratchpad
    orb = scratchpad.read("nav.orbital_state")
    assert orb is not None, "Nav should post orbital state"
    assert "orbital_period_min" in orb

    # Comms periodic reads it and posts link status with contact estimate
    await comms.periodic_task()
    await asyncio.sleep(0.2)

    link = scratchpad.read("comms.link_status")
    assert link is not None, "Comms should post link status"
    assert link.get("next_contact_est_min") is not None, (
        "Comms should estimate next contact from orbital period"
    )

    await nav.stop()
    await comms.stop()


# ---------------------------------------------------------------------------
# 9. Power critical battery -> Thermal sheds non-essential heaters
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_power_critical_battery_sheds_thermal_heaters(
    bus: MessageBus, scratchpad: SharedScratchpad, tools: ToolRegistry,
) -> None:
    """When battery < 15%, ThermalAgent turns off non-essential heaters
    (science_instruments, antenna_assembly) to conserve power."""
    heater_cmds = _Collector(bus, "aria.actuator.thermal.*")

    # Write critical power prediction to scratchpad
    scratchpad.write("power.prediction", {
        "battery_soc": 10.0,
        "power_margin_w": -300,
        "hours_to_depletion": 0.5,
        "in_eclipse": True,
        "load_shed_active": False,
    }, "power", ttl_s=120)

    thermal = ThermalAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    await thermal.start()

    # Turn on heaters that should be shed
    thermal._zones["science_instruments"].heater_on = True
    thermal._zones["antenna_assembly"].heater_on = True

    await thermal.periodic_task()
    await asyncio.sleep(0.3)

    # Verify heaters were turned off
    off_cmds = {m.payload["zone"] for m in heater_cmds.messages
                if m.payload.get("heater") == "off"
                and m.payload.get("reason") == "critical_battery_power_save"}
    assert "science_instruments" in off_cmds, "Science heater should be shed"
    assert "antenna_assembly" in off_cmds, "Antenna heater should be shed"
    assert not thermal._zones["science_instruments"].heater_on
    assert not thermal._zones["antenna_assembly"].heater_on

    await thermal.stop()


# ---------------------------------------------------------------------------
# 10. Propulsion low delta-V -> Navigation warning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_propulsion_low_dv_triggers_nav_warning(
    bus: MessageBus, scratchpad: SharedScratchpad, tools: ToolRegistry,
) -> None:
    """PropulsionAgent posts low delta-V; NavigationAgent warns about limited
    collision avoidance capability."""
    nav_alerts = _Collector(bus, "aria.anomaly.navigation")

    # Pre-populate fuel status with low delta-V
    scratchpad.write("propulsion.fuel_status", {
        "propellant_kg": 5.0,
        "fuel_fraction": 0.05,
        "delta_v_remaining_ms": 8.0,
    }, "propulsion", ttl_s=120)

    nav = NavigationAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    await nav.start()

    await nav.periodic_task()
    await asyncio.sleep(0.3)

    dv_warnings = [m for m in nav_alerts.messages
                   if "delta" in m.payload.get("message", "").lower()
                   or "avoidance" in m.payload.get("message", "").lower()]
    assert len(dv_warnings) >= 1, "Nav should warn about limited avoidance with low delta-V"

    await nav.stop()


# ---------------------------------------------------------------------------
# 11. Science biosignature -> Comms HIGH priority downlink
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_science_biosignature_triggers_comms_downlink(
    bus: MessageBus, scratchpad: SharedScratchpad, tools: ToolRegistry,
) -> None:
    """ScienceAgent discovers biosignature; CommsAgent queues HIGH priority
    downlink message via the discovery.candidate event."""
    comms_queued = _Collector(bus, "aria.comms.message.queued")

    science = ScienceAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    comms = CommsAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    await science.start()
    await comms.start()

    # Trigger biosignature analysis (mock tool returns detection=True, confidence=0.85)
    await bus.publish(Message(
        topic="aria.command.science.analyze",
        payload={
            "sample_id": "SAMPLE-MARS-001",
            "analysis_type": "biosignature",
            "data": {"spectral_peaks": [3400, 1650]},
        },
        correlation_id="bio-001",
    ))
    await asyncio.sleep(0.5)

    # The discovery event should trigger CommsAgent to queue a HIGH priority message
    assert len(comms_queued.messages) >= 1, "Comms should queue biosignature downlink"

    # Verify the comms queue contains a HIGH priority science message
    assert any(
        m.payload.get("type", "") == "science_data"
        for m in comms._outbound_queue
    ) or comms._messages_sent > 0, (
        "Comms should have processed or queued a science_data message"
    )

    await science.stop()
    await comms.stop()


# ---------------------------------------------------------------------------
# 12. Multiple pipelines simultaneously
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiple_pipelines_simultaneous(
    bus: MessageBus, scratchpad: SharedScratchpad, tools: ToolRegistry,
) -> None:
    """Trigger 3 cross-agent pipelines at once; all should complete without
    interference."""
    med_alerts = _Collector(bus, "aria.anomaly.medical")
    heater_cmds = _Collector(bus, "aria.actuator.thermal.*")
    nav_alerts = _Collector(bus, "aria.anomaly.navigation")

    power = PowerAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    thermal = ThermalAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    eclss = EclssAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    medical = MedicalAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    nav = NavigationAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    prop = PropulsionAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)

    for agent in [power, thermal, eclss, medical, nav, prop]:
        await agent.start()

    # Register crew for medical
    medical._crew_vitals["crew_d"] = {"heart_rate_bpm": 70.0}

    # Pipeline 1: Power eclipse -> Thermal preheat
    await bus.publish(Message(
        topic="aria.sensor.power.solar",
        payload={"power_watts": 0.0},
    ))
    # Pipeline 2: ECLSS CO2 -> Medical cognitive alert
    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 9.0, "humidity_percent": 45.0, "temperature_c": 22.0},
    ))
    # Pipeline 3: Low delta-V -> Nav warning
    scratchpad.write("propulsion.fuel_status", {
        "propellant_kg": 3.0,
        "fuel_fraction": 0.03,
        "delta_v_remaining_ms": 5.0,
    }, "propulsion", ttl_s=120)

    await asyncio.sleep(0.5)

    # Force periodic tasks to read scratchpad
    thermal._zones["battery_pack"].temperature_c = 10.0
    thermal._zones["propulsion"].temperature_c = 5.0
    await thermal.periodic_task()
    await medical.periodic_task()
    await nav.periodic_task()
    await asyncio.sleep(0.5)

    # Pipeline 1: thermal preheat happened
    preheat_zones = {m.payload.get("zone") for m in heater_cmds.messages
                     if m.payload.get("heater") == "on"}
    assert "battery_pack" in preheat_zones or "propulsion" in preheat_zones, (
        "Pipeline 1 (eclipse preheat) should work"
    )

    # Pipeline 2: medical CO2 alert
    co2_alerts = [m for m in med_alerts.messages
                  if "co2" in m.payload.get("message", "").lower()]
    assert len(co2_alerts) >= 1, "Pipeline 2 (CO2 -> medical) should work"

    # Pipeline 3: nav delta-V warning
    dv_warns = [m for m in nav_alerts.messages
                if "delta" in m.payload.get("message", "").lower()
                or "avoidance" in m.payload.get("message", "").lower()]
    assert len(dv_warns) >= 1, "Pipeline 3 (low dV -> nav warning) should work"

    for agent in [power, thermal, eclss, medical, nav, prop]:
        await agent.stop()


# ---------------------------------------------------------------------------
# 13. Scratchpad expiry handled gracefully
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scratchpad_expiry_handled_gracefully(
    bus: MessageBus, scratchpad: SharedScratchpad, tools: ToolRegistry,
) -> None:
    """Expired scratchpad entries return None and do not cause agent errors."""
    # Write an entry with immediate expiry
    scratchpad.write("power.eclipse_state", {
        "in_eclipse": True,
        "solar_power_w": 0.0,
        "battery_soc": 80.0,
    }, "power", ttl_s=0.01)  # 10 ms TTL

    # Wait for expiry
    await asyncio.sleep(0.05)

    # Reading should return None, not crash
    result = scratchpad.read("power.eclipse_state")
    assert result is None, "Expired entry should return None"

    # ThermalAgent periodic should handle the None gracefully
    thermal = ThermalAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    await thermal.start()

    # This should not raise any exceptions
    await thermal.periodic_task()

    # Also test that MedicalAgent handles expired radiation data
    medical = MedicalAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
    await medical.start()
    medical._crew_vitals["crew_e"] = {"heart_rate_bpm": 72.0}

    # Write and expire radiation entry
    scratchpad.write("science.radiation", {"dose_rate_usv_hr": 500.0}, "science", ttl_s=0.01)
    await asyncio.sleep(0.05)

    # periodic_task should not crash
    await medical.periodic_task()

    # Verify scratchpad properly pruned
    assert scratchpad.read("science.radiation") is None

    await thermal.stop()
    await medical.stop()


# ---------------------------------------------------------------------------
# 14. All agents post to scratchpad after sensor data
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_agents_post_to_scratchpad_after_sensor_data(
    bus: MessageBus, scratchpad: SharedScratchpad, tools: ToolRegistry,
) -> None:
    """All 9 agents write at least one entry to the scratchpad after processing
    sensor data and/or running their periodic tasks."""
    agents = [
        TelemetryAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad),
        PowerAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad),
        ThermalAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad),
        EclssAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad),
        NavigationAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad),
        PropulsionAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad),
        CommsAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad),
        ScienceAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad),
        MedicalAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad),
    ]
    for a in agents:
        await a.start()

    # Register crew for medical
    agents[-1]._crew_vitals["crew_f"] = {"heart_rate_bpm": 70.0}  # type: ignore[union-attr]
    agents[-1]._crew_fatigue["crew_f"] = "low"  # type: ignore[union-attr]

    # Send sensor data to trigger scratchpad writes
    sensor_messages = [
        Message(topic="aria.sensor.power.solar", payload={"power_watts": 1500.0}),
        Message(topic="aria.sensor.power.battery", payload={"soc_percent": 80.0, "temperature_c": 22.0}),
        Message(topic="aria.sensor.thermal.battery_pack", payload={"temperature_c": 22.0}),
        Message(topic="aria.sensor.eclss.atmosphere",
                payload={"o2_percent": 20.9, "co2_mmhg": 3.0, "humidity_percent": 45.0, "temperature_c": 22.0}),
        Message(topic="aria.sensor.nav.gps",
                payload={"fix": True, "satellites": 10, "altitude_km": 400.0, "velocity_ms": 7660.0}),
        Message(topic="aria.sensor.propulsion.tank",
                payload={"propellant_kg": 80.0, "pressure_psi": 250.0, "temperature_c": 20.0}),
        Message(topic="aria.sensor.comms.link",
                payload={"signal_dbm": -85.0, "snr_db": 15.0, "ber": 1e-9, "data_rate_kbps": 256.0}),
        Message(topic="aria.sensor.science.radiation",
                payload={"dose_rate_usv_hr": 0.5, "cumulative_dose_msv": 10.0}),
        Message(topic="aria.sensor.medical.vitals",
                payload={"crew_id": "crew_f", "heart_rate_bpm": 70.0, "spo2_percent": 98.0}),
    ]
    for msg in sensor_messages:
        await bus.publish(msg)
    await asyncio.sleep(0.5)

    # Run periodic tasks for agents that write to scratchpad in periodic
    for a in agents:
        try:
            await a.periodic_task()
        except Exception:
            pass  # Some periodic tasks may require state we haven't set
    await asyncio.sleep(0.3)

    # Count which agents wrote to scratchpad
    all_entries = scratchpad.all_entries()

    # Power should write eclipse_state and/or prediction
    power_keys = scratchpad.keys_by_prefix("power.")
    assert len(power_keys) >= 1, f"Power should write to scratchpad, got keys: {list(all_entries.keys())}"

    # Thermal should write zones
    thermal_keys = scratchpad.keys_by_prefix("thermal.")
    assert len(thermal_keys) >= 1, f"Thermal should write zones, got keys: {list(all_entries.keys())}"

    # ECLSS should write atmosphere
    eclss_keys = scratchpad.keys_by_prefix("eclss.")
    assert len(eclss_keys) >= 1, f"ECLSS should write atmosphere, got keys: {list(all_entries.keys())}"

    # Nav should write orbital state
    nav_keys = scratchpad.keys_by_prefix("nav.")
    assert len(nav_keys) >= 1, f"Nav should write orbital state, got keys: {list(all_entries.keys())}"

    # Propulsion should write fuel status
    prop_keys = scratchpad.keys_by_prefix("propulsion.")
    assert len(prop_keys) >= 1, f"Propulsion should write fuel status, got keys: {list(all_entries.keys())}"

    # Comms should write link status
    comms_keys = scratchpad.keys_by_prefix("comms.")
    assert len(comms_keys) >= 1, f"Comms should write link status, got keys: {list(all_entries.keys())}"

    # Science should write radiation
    science_keys = scratchpad.keys_by_prefix("science.")
    assert len(science_keys) >= 1, f"Science should write radiation, got keys: {list(all_entries.keys())}"

    # Medical should write crew health (needs vitals + fatigue populated)
    medical_keys = scratchpad.keys_by_prefix("medical.")
    assert len(medical_keys) >= 1, f"Medical should write crew health, got keys: {list(all_entries.keys())}"

    # Overall: at least 8 prefixes should have entries (telemetry may not write to scratchpad)
    prefix_count = sum(1 for pfx in ["power.", "thermal.", "eclss.", "nav.", "propulsion.",
                                      "comms.", "science.", "medical."]
                       if scratchpad.keys_by_prefix(pfx))
    assert prefix_count >= 7, f"At least 7 agent prefixes should have entries, got {prefix_count}"

    for a in agents:
        await a.stop()


# ---------------------------------------------------------------------------
# 15. Cognitive engine includes scratchpad in LLM context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cognitive_engine_includes_scratchpad_in_context(
    scratchpad: SharedScratchpad, tools: ToolRegistry,
) -> None:
    """CognitiveEngine includes scratchpad entries in the prompt sent to the LLM."""
    # Populate scratchpad with cross-agent data
    scratchpad.write("power.eclipse_state", {
        "in_eclipse": True,
        "solar_power_w": 0.0,
        "battery_soc": 45.0,
    }, "power")
    scratchpad.write("nav.next_conjunction", {
        "object_name": "DEBRIS-99",
        "collision_probability": 2e-4,
        "time_to_tca_hours": 8.0,
    }, "navigation")
    scratchpad.write("eclss.atmosphere", {
        "o2_percent": 20.9,
        "co2_mmhg": 3.5,
    }, "eclss")

    engine = CognitiveEngine(
        tool_registry=tools,
        scratchpad=scratchpad,
    )

    # Access the prompt builder
    from aria.core.types import MissionPhase, AuthorityLevel as AL
    from aria.cognitive.engine import ReasoningContext

    ctx = ReasoningContext(
        system_state={"overall": "nominal"},
        mission_phase=MissionPhase.NOMINAL_LEO,
        authority=AL.SUPERVISED,
    )

    prompt = engine._build_system_prompt(ctx, "What is the current status?")

    # Verify scratchpad data appears in the prompt
    assert "Scratchpad" in prompt or "scratchpad" in prompt or "Cross-Agent" in prompt, (
        "Prompt should mention scratchpad/cross-agent observations"
    )
    assert "power.eclipse_state" in prompt or "in_eclipse" in prompt, (
        "Eclipse state should appear in context"
    )
    assert "DEBRIS-99" in prompt or "nav.next_conjunction" in prompt, (
        "Conjunction data should appear in context"
    )

    # Verify scratchpad size check works
    assert scratchpad.size >= 3, "Scratchpad should have at least 3 entries"
