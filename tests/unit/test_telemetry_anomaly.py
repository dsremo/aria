"""Tests for universal telemetry anomaly detection system.

Tests:
  1. DsremoChannelMapper: correct channel extraction for each sensor type
  2. DsremoIngestBatch: validation and schema
  3. DsremoGetChannelHealth / DsremoGetAnomalyScore: validation
  4. TelemetryAgent universal bridge: handles all sensor types
  5. DsremoAnomalyMixin: dsremo_score / dsremo_score_batch
  6. AnomalyCorrelator: signature matching, root cause identification
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from aria.bus.message_bus import Message, MessageBus
from aria.core.tool import ARIATool, ToolResult
from aria.core.types import AuthorityLevel, SafetyLevel, ToolCategory
from aria.integrations.dsremo.channel_mapper import DsremoChannelMapper, TelemetryReading
from aria.integrations.dsremo.correlator import AnomalyCorrelator, AnomalyEvent
from aria.integrations.dsremo.tools import (
    DsremoGetAnomalyScore,
    DsremoGetChannelHealth,
    DsremoIngestBatch,
)
from aria.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# 1. DsremoChannelMapper Tests
# ---------------------------------------------------------------------------

class TestDsremoChannelMapper:
    def setup_method(self):
        self.mapper = DsremoChannelMapper(satellite_id="sat-test")

    def test_power_battery_maps_all_fields(self):
        readings = self.mapper.extract(
            "aria.sensor.power.battery",
            {"soc_percent": 85.0, "temperature_c": 22.0},
        )
        channels = {r.channel_id for r in readings}
        assert "eps.battery.soc_percent" in channels
        assert "eps.battery.temperature_c" in channels
        assert all(r.satellite_id == "sat-test" for r in readings)
        assert all(r.subsystem == "power" for r in readings)

    def test_thermal_extracts_zone_name(self):
        readings = self.mapper.extract(
            "aria.sensor.thermal.electronics_bay",
            {"temperature_c": 45.0},
        )
        assert len(readings) == 1
        assert readings[0].channel_id == "thermal.electronics_bay.temperature_c"
        assert readings[0].value == 45.0

    def test_eclss_atmosphere_extracts_all_gases(self):
        readings = self.mapper.extract(
            "aria.sensor.eclss.atmosphere",
            {"o2_percent": 20.9, "co2_mmhg": 3.5, "humidity_percent": 45.0, "temperature_c": 22.0},
        )
        channels = {r.channel_id for r in readings}
        assert "eclss.atmosphere.o2_percent" in channels
        assert "eclss.atmosphere.co2_mmhg" in channels
        assert "eclss.atmosphere.humidity_percent" in channels
        assert "eclss.atmosphere.temperature_c" in channels
        assert all(r.subsystem == "eclss" for r in readings)

    def test_nav_imu_extracts_all_axes(self):
        readings = self.mapper.extract(
            "aria.sensor.nav.imu",
            {"angular_rate_x_dps": 0.01, "angular_rate_y_dps": 0.02, "angular_rate_z_dps": 0.01},
        )
        channels = {r.channel_id for r in readings}
        assert "nav.imu.angular_rate_x_dps" in channels
        assert "nav.imu.angular_rate_y_dps" in channels
        assert "nav.imu.angular_rate_z_dps" in channels

    def test_nav_gps_extracts_position(self):
        readings = self.mapper.extract(
            "aria.sensor.nav.gps",
            {"altitude_km": 400.0, "velocity_ms": 7660.0, "satellites": 8, "fix": True},
        )
        channels = {r.channel_id for r in readings}
        assert "nav.gps.altitude_km" in channels
        assert "nav.gps.velocity_ms" in channels
        assert "nav.gps.satellites" in channels
        # Boolean 'fix' should NOT be extracted (not numeric float)
        assert "nav.gps.fix" not in channels

    def test_power_solar_extracts_watts(self):
        readings = self.mapper.extract(
            "aria.sensor.power.solar",
            {"power_watts": 2500.0},
        )
        assert len(readings) == 1
        assert readings[0].channel_id == "eps.solar.power_watts"
        assert readings[0].value == 2500.0

    def test_unknown_topic_uses_generic_extractor(self):
        readings = self.mapper.extract(
            "aria.sensor.comms.signal_strength",
            {"dbm": -75.0, "snr_db": 12.5},
        )
        assert len(readings) == 2
        channels = {r.channel_id for r in readings}
        assert any("dbm" in c for c in channels)
        assert any("snr_db" in c for c in channels)

    def test_empty_payload_returns_empty(self):
        readings = self.mapper.extract(
            "aria.sensor.power.battery",
            {},
        )
        assert readings == []

    def test_non_numeric_values_excluded(self):
        readings = self.mapper.extract(
            "aria.sensor.nav.gps",
            {"fix": True, "status": "OK", "altitude_km": 400.0},
        )
        # Only altitude_km is numeric
        assert all(isinstance(r.value, float) for r in readings)
        channels = {r.channel_id for r in readings}
        assert "nav.gps.altitude_km" in channels

    def test_extract_single_creates_reading(self):
        r = self.mapper.extract_single("power", "battery", "soc_percent", 85.0)
        assert r.channel_id == "power.battery.soc_percent"
        assert r.value == 85.0
        assert r.satellite_id == "sat-test"

    def test_source_topic_preserved(self):
        readings = self.mapper.extract(
            "aria.sensor.thermal.crew_cabin",
            {"temperature_c": 22.0},
        )
        assert readings[0].source_topic == "aria.sensor.thermal.crew_cabin"


# ---------------------------------------------------------------------------
# 2. DsremoIngestBatch Tool Tests
# ---------------------------------------------------------------------------

class TestDsremoIngestBatch:
    def test_schema_has_readings(self):
        tool = DsremoIngestBatch()
        schema = tool.input_schema()
        assert "readings" in schema["properties"]
        assert schema["required"] == ["readings"]

    def test_validation_requires_readings(self):
        tool = DsremoIngestBatch()
        result = tool.validate_input({})
        assert not result.valid
        assert "readings" in result.message

    def test_validation_empty_readings_fails(self):
        tool = DsremoIngestBatch()
        result = tool.validate_input({"readings": []})
        assert not result.valid

    def test_validation_missing_channel_id_fails(self):
        tool = DsremoIngestBatch()
        result = tool.validate_input({
            "readings": [{"satellite_id": "sat-01", "value": 28.0}]  # Missing channel_id
        })
        assert not result.valid
        assert "channel_id" in result.message

    def test_validation_valid_batch(self):
        tool = DsremoIngestBatch()
        result = tool.validate_input({
            "readings": [
                {"satellite_id": "sat-01", "channel_id": "eps.battery.soc_percent", "value": 85.0},
                {"satellite_id": "sat-01", "channel_id": "thermal.battery_pack.temperature_c", "value": 22.0},
            ]
        })
        assert result.valid


# ---------------------------------------------------------------------------
# 3. DsremoGetChannelHealth / DsremoGetAnomalyScore Validation
# ---------------------------------------------------------------------------

class TestDsremoToolValidation:
    def test_channel_health_requires_channel_id(self):
        tool = DsremoGetChannelHealth()
        result = tool.validate_input({})
        assert not result.valid

    def test_channel_health_valid(self):
        tool = DsremoGetChannelHealth()
        result = tool.validate_input({"channel_id": "eps.battery.soc_percent"})
        assert result.valid

    def test_anomaly_score_requires_channel_id(self):
        tool = DsremoGetAnomalyScore()
        result = tool.validate_input({})
        assert not result.valid

    def test_anomaly_score_valid(self):
        tool = DsremoGetAnomalyScore()
        result = tool.validate_input({"channel_id": "thermal.battery_pack.temperature_c"})
        assert result.valid

    def test_all_dsremo_tools_registered(self):
        """All 6 Dsremo tools can be registered without conflicts."""
        from aria.integrations.dsremo.tools import (
            DsremoQueryAnomalies, DsremoIngestTelemetry, DsremoGetChannels,
            DsremoIngestBatch, DsremoGetChannelHealth, DsremoGetAnomalyScore,
        )
        reg = ToolRegistry()
        for cls in [
            DsremoQueryAnomalies, DsremoIngestTelemetry, DsremoGetChannels,
            DsremoIngestBatch, DsremoGetChannelHealth, DsremoGetAnomalyScore,
        ]:
            reg.register(cls())
        assert reg.count == 6


# ---------------------------------------------------------------------------
# 4. TelemetryAgent Universal Bridge Tests
# ---------------------------------------------------------------------------

class MockIngestTool(ARIATool):
    """Captures all ingest calls for verification."""
    name = "dsremo_ingest_telemetry"
    description = "Mock"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def __init__(self, score: float = 0.0) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []
        self.score = score

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object"}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        self.calls.append(params)
        return ToolResult(success=True, data={"anomaly_score": self.score})


class MockBatchTool(ARIATool):
    """Captures batch ingest calls."""
    name = "dsremo_ingest_batch"
    description = "Mock batch"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def __init__(self, scores: dict[str, float] | None = None) -> None:
        super().__init__()
        self.batches: list[list[dict]] = []
        self.scores = scores or {}

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "required": ["readings"], "properties": {"readings": {}}}

    def validate_input(self, params: dict[str, Any]) -> Any:
        from aria.core.tool import ValidationResult
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        readings = params.get("readings", [])
        self.batches.append(readings)
        results = [
            {
                "channel_id": r["channel_id"],
                "anomaly_score": self.scores.get(r["channel_id"], 0.0),
            }
            for r in readings
        ]
        return ToolResult(success=True, data={"results": results, "count": len(readings)})


@pytest.fixture
async def bus():
    b = MessageBus(max_history=500)
    await b.start()
    yield b
    await b.stop()


async def test_telemetry_agent_subscribes_to_all_sensors(bus: MessageBus):
    """TelemetryAgent subscribes to aria.sensor.* (all sensors)."""
    from aria.agents.telemetry import TelemetryAgent
    mock_batch = MockBatchTool()
    tools = ToolRegistry()
    tools.register(MockIngestTool())
    tools.register(mock_batch)

    agent = TelemetryAgent(bus=bus, tool_registry=tools)
    assert "aria.sensor.*" in agent.subscriptions
    await agent.start()

    # Send power sensor reading (non-telemetry topic)
    await bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 85.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(0.8)  # Wait for batch flush

    # Should have batched the power readings
    assert len(mock_batch.batches) >= 1
    all_channels = [r["channel_id"] for batch in mock_batch.batches for r in batch]
    assert "eps.battery.soc_percent" in all_channels

    await agent.stop()


async def test_telemetry_agent_handles_eclss(bus: MessageBus):
    """TelemetryAgent routes ECLSS atmosphere readings through Dsremo."""
    from aria.agents.telemetry import TelemetryAgent
    mock_batch = MockBatchTool()
    tools = ToolRegistry()
    tools.register(MockIngestTool())
    tools.register(mock_batch)

    agent = TelemetryAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.eclss.atmosphere",
        payload={"o2_percent": 20.9, "co2_mmhg": 3.5, "humidity_percent": 45.0},
    ))
    await asyncio.sleep(0.8)

    all_channels = [r["channel_id"] for batch in mock_batch.batches for r in batch]
    assert "eclss.atmosphere.co2_mmhg" in all_channels
    assert "eclss.atmosphere.o2_percent" in all_channels

    await agent.stop()


async def test_telemetry_agent_publishes_anomaly_on_high_score(bus: MessageBus):
    """TelemetryAgent publishes aria.anomaly.detected when Dsremo scores high."""
    from aria.agents.telemetry import TelemetryAgent

    # Return HIGH score for battery SoC channel
    mock_batch = MockBatchTool(scores={"eps.battery.soc_percent": 0.91})
    tools = ToolRegistry()
    tools.register(MockIngestTool(score=0.91))
    tools.register(mock_batch)

    anomalies: list[Message] = []

    async def capture(m: Message) -> None:
        anomalies.append(m)

    bus.subscribe("aria.anomaly.detected", capture)

    agent = TelemetryAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 5.0, "temperature_c": 22.0},
    ))
    await asyncio.sleep(1.0)  # Wait for batch flush + delivery

    assert len(anomalies) >= 1
    assert anomalies[0].payload["severity"] == "CRITICAL"
    assert "eps.battery.soc_percent" in anomalies[0].payload["channel_id"]

    await agent.stop()


async def test_telemetry_agent_publishes_scored_event(bus: MessageBus):
    """TelemetryAgent publishes aria.telemetry.scored for audit trail."""
    from aria.agents.telemetry import TelemetryAgent

    mock_batch = MockBatchTool(scores={"eps.battery.soc_percent": 0.3})
    tools = ToolRegistry()
    tools.register(MockIngestTool())
    tools.register(mock_batch)

    scored: list[Message] = []

    async def capture(m: Message) -> None:
        scored.append(m)

    bus.subscribe("aria.telemetry.scored", capture)

    agent = TelemetryAgent(bus=bus, tool_registry=tools)
    await agent.start()

    await bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 85.0},
    ))
    await asyncio.sleep(1.0)

    assert len(scored) >= 1
    assert "channel_scores" in scored[0].payload

    await agent.stop()


# ---------------------------------------------------------------------------
# 5. DsremoAnomalyMixin Tests
# ---------------------------------------------------------------------------

async def test_mixin_dsremo_score_returns_float(bus: MessageBus):
    """DsremoAnomalyMixin.dsremo_score returns a float from tool call."""
    from aria.agents.dsremo_mixin import DsremoAnomalyMixin
    from aria.agents.base import SubsystemAgent

    mock_ingest = MockIngestTool(score=0.72)
    tools = ToolRegistry()
    tools.register(mock_ingest)

    class TestAgent(SubsystemAgent, DsremoAnomalyMixin):
        name = "test_agent"
        subscriptions = []

        async def handle_message(self, msg: Message) -> None:
            pass

    agent = TestAgent(bus=bus, tool_registry=tools)
    score = await agent.dsremo_score("eps", "battery", "soc_percent", 85.0)
    assert score is not None
    assert abs(score - 0.72) < 0.01


async def test_mixin_dsremo_classify(bus: MessageBus):
    """DsremoAnomalyMixin.dsremo_classify correctly maps scores."""
    from aria.agents.dsremo_mixin import DsremoAnomalyMixin

    mixin = DsremoAnomalyMixin()
    assert mixin.dsremo_classify(0.91) == "CRITICAL"
    assert mixin.dsremo_classify(0.70) == "WARNING"
    assert mixin.dsremo_classify(0.55) == "WATCH"
    assert mixin.dsremo_classify(0.30) == "NOMINAL"


async def test_mixin_returns_none_when_no_tools(bus: MessageBus):
    """DsremoAnomalyMixin.dsremo_score returns None when tools unavailable."""
    from aria.agents.dsremo_mixin import DsremoAnomalyMixin
    mixin = DsremoAnomalyMixin()
    # No _tools attribute — should return None gracefully
    score = await mixin.dsremo_score("eps", "battery", "soc_percent", 85.0)
    assert score is None


# ---------------------------------------------------------------------------
# 6. AnomalyCorrelator Tests
# ---------------------------------------------------------------------------

async def test_correlator_identifies_battery_thermal_runaway(bus: MessageBus):
    """Correlator identifies BATTERY_THERMAL_RUNAWAY from simultaneous channels."""
    correlations: list[Message] = []

    async def capture(m: Message) -> None:
        correlations.append(m)

    bus.subscribe("aria.anomaly.correlation", capture)

    correlator = AnomalyCorrelator(bus, window_s=30.0, min_events=2)
    await correlator.start()

    # Inject two events that match BATTERY_THERMAL_RUNAWAY signature
    t = time.time()
    correlator._events.append(AnomalyEvent(
        channel_id="eps.battery.temperature_c",
        subsystem="power",
        severity="CRITICAL",
        score=0.88,
        timestamp=t,
    ))
    correlator._events.append(AnomalyEvent(
        channel_id="eps.battery.soc_percent",
        subsystem="power",
        severity="WARNING",
        score=0.72,
        timestamp=t,
    ))

    # Trigger correlation manually
    await correlator._correlate()
    await asyncio.sleep(0.1)

    assert len(correlations) >= 1
    assert correlations[0].payload["root_cause"] == "BATTERY_THERMAL_RUNAWAY"
    assert correlations[0].payload["confidence"] >= 0.80


async def test_correlator_identifies_co2_scrubber_failure(bus: MessageBus):
    """Correlator identifies CO2_SCRUBBER_FAILURE from atmosphere channels."""
    correlations: list[Message] = []

    async def capture(m: Message) -> None:
        correlations.append(m)

    bus.subscribe("aria.anomaly.correlation", capture)

    correlator = AnomalyCorrelator(bus, window_s=30.0, min_events=2)
    await correlator.start()

    t = time.time()
    correlator._events.extend([
        AnomalyEvent("eclss.atmosphere.co2_mmhg", "eclss", "WARNING", 0.70, t),
        AnomalyEvent("eclss.atmosphere.o2_percent", "eclss", "WATCH", 0.55, t),
        AnomalyEvent("eclss.atmosphere.humidity_percent", "eclss", "WATCH", 0.52, t),
    ])

    await correlator._correlate()
    await asyncio.sleep(0.1)

    assert len(correlations) >= 1
    assert correlations[0].payload["root_cause"] == "CO2_SCRUBBER_FAILURE"


async def test_correlator_no_false_positive_single_channel(bus: MessageBus):
    """Correlator does NOT fire on a single isolated anomaly."""
    correlations: list[Message] = []

    async def capture(m: Message) -> None:
        correlations.append(m)

    bus.subscribe("aria.anomaly.correlation", capture)

    correlator = AnomalyCorrelator(bus, window_s=30.0, min_events=2)
    await correlator.start()

    # Only one event — below min_events threshold
    correlator._events.append(AnomalyEvent(
        channel_id="eps.battery.temperature_c",
        subsystem="power",
        severity="WARNING",
        score=0.70,
        timestamp=time.time(),
    ))

    await correlator._correlate()
    await asyncio.sleep(0.1)

    assert len(correlations) == 0, "Should not correlate single-channel anomaly"


async def test_correlator_identifies_propulsion_leak(bus: MessageBus):
    """Correlator identifies PROPULSION_LEAK from tank channels."""
    correlations: list[Message] = []
    bus.subscribe("aria.anomaly.correlation", lambda m: correlations.append(m))

    correlator = AnomalyCorrelator(bus, window_s=30.0, min_events=2)
    await correlator.start()

    t = time.time()
    correlator._events.extend([
        AnomalyEvent("propulsion.tank.propellant_kg", "propulsion", "WARNING", 0.72, t),
        AnomalyEvent("propulsion.tank.pressure_psi", "propulsion", "WARNING", 0.68, t),
    ])

    await correlator._correlate()
    await asyncio.sleep(0.1)

    assert len(correlations) >= 1
    assert correlations[0].payload["root_cause"] == "PROPULSION_LEAK"


async def test_correlator_identifies_solar_particle_event(bus: MessageBus):
    """Correlator identifies SOLAR_PARTICLE_EVENT from radiation + comms."""
    correlations: list[Message] = []
    bus.subscribe("aria.anomaly.correlation", lambda m: correlations.append(m))

    correlator = AnomalyCorrelator(bus, window_s=30.0, min_events=2)
    await correlator.start()

    t = time.time()
    correlator._events.extend([
        AnomalyEvent("science.radiation.dose_rate_usv_hr", "science", "CRITICAL", 0.92, t),
        AnomalyEvent("comms.link.signal_dbm", "comms", "WARNING", 0.65, t),
    ])

    await correlator._correlate()
    await asyncio.sleep(0.1)

    assert len(correlations) >= 1
    assert correlations[0].payload["root_cause"] == "SOLAR_PARTICLE_EVENT"


async def test_correlator_get_recent_events(bus: MessageBus):
    """Correlator tracks recent events correctly."""
    correlator = AnomalyCorrelator(bus, window_s=10.0)

    # Add recent events
    now = time.time()
    correlator._events.extend([
        AnomalyEvent("ch1", "power", "WARNING", 0.7, now - 5),   # Within window
        AnomalyEvent("ch2", "eclss", "WATCH", 0.5, now - 15),    # Outside window
    ])

    recent = correlator.get_recent_events(window_s=10.0)
    channels = [e.channel_id for e in recent]
    assert "ch1" in channels
    assert "ch2" not in channels


class TestDsremoChannelMapperExtended:
    def setup_method(self):
        from aria.integrations.dsremo.channel_mapper import DsremoChannelMapper
        self.mapper = DsremoChannelMapper(satellite_id="sat-test")

    def test_propulsion_tank_mapping(self):
        readings = self.mapper.extract(
            "aria.sensor.propulsion.tank",
            {"propellant_kg": 90.0, "pressure_psi": 250.0, "temperature_c": 20.0},
        )
        channels = {r.channel_id for r in readings}
        assert "propulsion.tank.propellant_kg" in channels
        assert "propulsion.tank.pressure_psi" in channels

    def test_comms_link_mapping(self):
        readings = self.mapper.extract(
            "aria.sensor.comms.link",
            {"signal_dbm": -85.0, "snr_db": 15.0, "data_rate_kbps": 256.0},
        )
        channels = {r.channel_id for r in readings}
        assert "comms.link.signal_dbm" in channels
        assert "comms.link.snr_db" in channels

    def test_science_radiation_mapping(self):
        readings = self.mapper.extract(
            "aria.sensor.science.radiation",
            {"dose_rate_usv_hr": 0.5, "cumulative_dose_msv": 25.0},
        )
        channels = {r.channel_id for r in readings}
        assert "science.radiation.dose_rate_usv_hr" in channels

    def test_medical_vitals_mapping(self):
        readings = self.mapper.extract(
            "aria.sensor.medical.vitals.commander",
            {"crew_id": "commander", "heart_rate_bpm": 72.0, "spo2_percent": 98.0},
        )
        channels = {r.channel_id for r in readings}
        assert "medical.commander.heart_rate_bpm" in channels
        assert "medical.commander.spo2_percent" in channels


class TestDsremoChannelMapperGeneric:
    """Test the generic fallback extractor for unknown sensor types."""

    def setup_method(self):
        from aria.integrations.dsremo.channel_mapper import DsremoChannelMapper
        self.mapper = DsremoChannelMapper(satellite_id="sat-test")

    def test_unknown_sensor_uses_generic(self):
        readings = self.mapper.extract(
            "aria.sensor.custom.widget",
            {"value_a": 42.0, "value_b": 99.5},
        )
        assert len(readings) == 2
        channels = {r.channel_id for r in readings}
        assert any("value_a" in c for c in channels)

    def test_boolean_values_excluded(self):
        readings = self.mapper.extract(
            "aria.sensor.custom.flags",
            {"active": True, "temperature": 25.0},
        )
        # Only temperature should be extracted (boolean excluded)
        assert len(readings) == 1
        assert readings[0].value == 25.0

    def test_string_values_excluded(self):
        readings = self.mapper.extract(
            "aria.sensor.custom.mixed",
            {"mode": "auto", "level": 75.0},
        )
        assert len(readings) == 1
        assert readings[0].value == 75.0

    def test_nan_values_excluded(self):
        import math
        readings = self.mapper.extract(
            "aria.sensor.custom.nan",
            {"good": 10.0, "bad": float("nan")},
        )
        assert len(readings) == 1
        assert readings[0].value == 10.0

    def test_power_bus_mapping(self):
        readings = self.mapper.extract(
            "aria.sensor.power.bus",
            {"voltage_v": 28.0},
        )
        assert len(readings) == 1
        assert readings[0].channel_id == "eps.bus.voltage_v"

    def test_power_solar_mapping(self):
        readings = self.mapper.extract(
            "aria.sensor.power.solar",
            {"power_watts": 2500.0},
        )
        assert len(readings) == 1
        assert readings[0].channel_id == "eps.solar.power_watts"

    def test_eclss_pressure_mapping(self):
        readings = self.mapper.extract(
            "aria.sensor.eclss.pressure",
            {"pressure_psi": 14.7},
        )
        assert len(readings) == 1
        assert readings[0].channel_id == "eclss.cabin.pressure_psi"
