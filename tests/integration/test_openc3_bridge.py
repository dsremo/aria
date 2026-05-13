"""Integration tests for the OpenC3/COSMOS bridge.

Covers command definitions, parameter validation, command routing,
telemetry extraction, telemetry publishing, target definition generation,
mock mode operation, and the full round-trip command/telemetry cycle.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from aria.bus.message_bus import Message, MessageBus
from aria.core.types import EventPriority
from aria.integrations.openc3_bridge import (
    CommandDefinition,
    CommandParameter,
    CommandResult,
    CommandValidationError,
    Endianness,
    MockOpenC3ApiClient,
    OpenC3Bridge,
    OpenC3Config,
    ParamType,
    TelemetryItem,
    TelemetryPacketDefinition,
    TelemetrySnapshot,
    _build_aria_commands,
    _build_aria_telemetry,
    _command_params_to_bus_payload,
    _extract_navigation_attitude,
    _extract_navigation_orbit,
    _extract_power_battery,
    _extract_power_eclipse,
    _extract_power_solar,
    _extract_reaction_wheels,
    _extract_thermal,
    validate_command_params,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def bus(event_loop):
    """Create a fresh message bus."""
    return MessageBus()


@pytest.fixture
def config():
    """Default mock-mode configuration."""
    return OpenC3Config(mock_mode=True)


@pytest.fixture
def bridge(bus, config):
    """Create a bridge instance (not yet started)."""
    return OpenC3Bridge(bus, config)


@pytest.fixture
async def running_bridge(bus, config):
    """Create and start a bridge with the bus running."""
    await bus.start()
    br = OpenC3Bridge(bus, config)
    await br.start()
    yield br
    await br.stop()
    await bus.stop()


# ---------------------------------------------------------------------------
# Command definition tests
# ---------------------------------------------------------------------------

class TestCommandDefinitions:
    """Verify that all ARIA commands are properly defined."""

    def test_all_commands_present(self):
        commands = _build_aria_commands()
        names = {c.name for c in commands}
        expected = {"SAFE_MODE", "LOAD_SHED", "ATTITUDE_CHANGE", "ORBIT_MANEUVER", "ECLSS_ADJUST"}
        assert names == expected

    def test_every_command_has_bus_topic(self):
        for cmd in _build_aria_commands():
            assert cmd.bus_topic, f"Command {cmd.name} missing bus_topic"
            assert cmd.bus_topic.startswith("aria.command."), (
                f"Command {cmd.name} bus_topic should start with 'aria.command.'"
            )

    def test_every_command_has_description(self):
        for cmd in _build_aria_commands():
            assert cmd.description, f"Command {cmd.name} missing description"
            assert len(cmd.description) > 10, (
                f"Command {cmd.name} description too short"
            )

    def test_every_command_has_priority(self):
        for cmd in _build_aria_commands():
            assert isinstance(cmd.priority, EventPriority)

    def test_safe_mode_is_p0_emergency(self):
        commands = {c.name: c for c in _build_aria_commands()}
        assert commands["SAFE_MODE"].priority == EventPriority.P0_EMERGENCY

    def test_safe_mode_is_hazardous(self):
        commands = {c.name: c for c in _build_aria_commands()}
        assert commands["SAFE_MODE"].hazardous

    def test_orbit_maneuver_is_hazardous(self):
        commands = {c.name: c for c in _build_aria_commands()}
        assert commands["ORBIT_MANEUVER"].hazardous

    def test_attitude_change_is_not_hazardous(self):
        commands = {c.name: c for c in _build_aria_commands()}
        assert not commands["ATTITUDE_CHANGE"].hazardous

    def test_command_parameter_types(self):
        """Every parameter must have a valid ParamType."""
        for cmd in _build_aria_commands():
            for param in cmd.parameters:
                assert isinstance(param.param_type, ParamType), (
                    f"Command {cmd.name} param {param.name} has invalid type"
                )

    def test_safe_mode_parameters(self):
        commands = {c.name: c for c in _build_aria_commands()}
        safe = commands["SAFE_MODE"]
        param_names = [p.name for p in safe.parameters]
        assert "REASON" in param_names
        assert "SHED_LEVEL" in param_names
        assert "DURATION_S" in param_names

    def test_eclss_adjust_parameters(self):
        commands = {c.name: c for c in _build_aria_commands()}
        eclss = commands["ECLSS_ADJUST"]
        param_names = [p.name for p in eclss.parameters]
        assert "SUBSYSTEM" in param_names
        assert "TARGET_TEMP_K" in param_names
        assert "O2_FRACTION" in param_names
        assert "HUMIDITY_PERCENT" in param_names

    def test_attitude_change_quaternion_params(self):
        commands = {c.name: c for c in _build_aria_commands()}
        att = commands["ATTITUDE_CHANGE"]
        param_names = [p.name for p in att.parameters]
        for q in ["TARGET_QW", "TARGET_QX", "TARGET_QY", "TARGET_QZ"]:
            assert q in param_names

    def test_orbit_maneuver_delta_v_params(self):
        commands = {c.name: c for c in _build_aria_commands()}
        orb = commands["ORBIT_MANEUVER"]
        param_names = [p.name for p in orb.parameters]
        for dv in ["DELTA_V_X_MS", "DELTA_V_Y_MS", "DELTA_V_Z_MS"]:
            assert dv in param_names


# ---------------------------------------------------------------------------
# Telemetry definition tests
# ---------------------------------------------------------------------------

class TestTelemetryDefinitions:
    """Verify that all ARIA telemetry packets are properly defined."""

    def test_all_packets_present(self):
        packets = _build_aria_telemetry()
        names = {p.name for p in packets}
        expected = {"HEALTH_STATUS", "NAVIGATION", "POWER", "THERMAL", "PROPULSION", "ECLSS"}
        assert names == expected

    def test_every_packet_has_description(self):
        for pkt in _build_aria_telemetry():
            assert pkt.description, f"Packet {pkt.name} missing description"

    def test_every_packet_has_bus_topics(self):
        for pkt in _build_aria_telemetry():
            assert pkt.bus_topics, f"Packet {pkt.name} missing bus_topics"

    def test_every_packet_has_timestamp_item(self):
        for pkt in _build_aria_telemetry():
            item_names = [i.name for i in pkt.items]
            assert "TIMESTAMP" in item_names, (
                f"Packet {pkt.name} missing TIMESTAMP item"
            )

    def test_navigation_has_quaternion_items(self):
        packets = {p.name: p for p in _build_aria_telemetry()}
        nav = packets["NAVIGATION"]
        item_names = [i.name for i in nav.items]
        for q in ["QW", "QX", "QY", "QZ"]:
            assert q in item_names

    def test_power_has_battery_soc(self):
        packets = {p.name: p for p in _build_aria_telemetry()}
        power = packets["POWER"]
        item_names = [i.name for i in power.items]
        assert "BATTERY_SOC" in item_names

    def test_power_battery_soc_has_limits(self):
        packets = {p.name: p for p in _build_aria_telemetry()}
        power = packets["POWER"]
        soc_item = next(i for i in power.items if i.name == "BATTERY_SOC")
        assert soc_item.limits_enabled
        assert soc_item.limits

    def test_thermal_has_all_nodes(self):
        packets = {p.name: p for p in _build_aria_telemetry()}
        thermal = packets["THERMAL"]
        item_names = [i.name for i in thermal.items]
        expected_nodes = [
            "SOLAR_PANEL_1_K", "SOLAR_PANEL_2_K", "BATTERY_PACK_K",
            "PAYLOAD_BAY_K", "RW_CLUSTER_K", "STAR_TRACKER_K",
            "PROP_TANK_K", "AVIONICS_BAY_K",
        ]
        for node in expected_nodes:
            assert node in item_names

    def test_propulsion_has_four_reaction_wheels(self):
        packets = {p.name: p for p in _build_aria_telemetry()}
        prop = packets["PROPULSION"]
        item_names = [i.name for i in prop.items]
        for i in range(4):
            assert f"RW_{i}_RPM" in item_names

    def test_eclss_has_life_support_items(self):
        packets = {p.name: p for p in _build_aria_telemetry()}
        eclss = packets["ECLSS"]
        item_names = [i.name for i in eclss.items]
        for item in ["CABIN_TEMP_K", "CABIN_PRESSURE_KPA", "O2_FRACTION", "CO2_PPM"]:
            assert item in item_names


# ---------------------------------------------------------------------------
# Parameter validation tests
# ---------------------------------------------------------------------------

class TestParameterValidation:

    def test_valid_params_pass(self):
        commands = {c.name: c for c in _build_aria_commands()}
        errors = validate_command_params(
            commands["SAFE_MODE"],
            {"REASON": "test", "SHED_LEVEL": 3, "DURATION_S": 60},
        )
        assert errors == []

    def test_missing_required_param(self):
        cmd = CommandDefinition(
            name="TEST",
            description="test",
            parameters=[
                CommandParameter("PARAM1", 32, ParamType.UINT, 0, "test", required=True),
            ],
        )
        errors = validate_command_params(cmd, {})
        assert any("Required" in e for e in errors)

    def test_type_mismatch_rejected(self):
        commands = {c.name: c for c in _build_aria_commands()}
        errors = validate_command_params(
            commands["SAFE_MODE"],
            {"SHED_LEVEL": "not_a_number"},
        )
        assert any("numeric" in e for e in errors)

    def test_range_below_minimum(self):
        commands = {c.name: c for c in _build_aria_commands()}
        errors = validate_command_params(
            commands["ATTITUDE_CHANGE"],
            {"SLEW_RATE_DEG_S": 0.001},  # min is 0.01
        )
        assert any("below minimum" in e for e in errors)

    def test_range_above_maximum(self):
        commands = {c.name: c for c in _build_aria_commands()}
        errors = validate_command_params(
            commands["ATTITUDE_CHANGE"],
            {"SLEW_RATE_DEG_S": 100.0},  # max is 5.0
        )
        assert any("above maximum" in e for e in errors)

    def test_unknown_param_rejected(self):
        commands = {c.name: c for c in _build_aria_commands()}
        errors = validate_command_params(
            commands["SAFE_MODE"],
            {"NONEXISTENT_PARAM": 42},
        )
        assert any("Unknown" in e for e in errors)

    def test_valid_defaults_pass(self):
        """Every command's default values should pass validation."""
        for cmd in _build_aria_commands():
            defaults = {p.name: p.default for p in cmd.parameters}
            errors = validate_command_params(cmd, defaults)
            assert errors == [], (
                f"Command {cmd.name} defaults fail validation: {errors}"
            )


# ---------------------------------------------------------------------------
# Telemetry extractor tests
# ---------------------------------------------------------------------------

class TestTelemetryExtractors:

    def test_attitude_extraction(self):
        payload = {
            "quaternion": [0.1, 0.2, 0.3, 0.9],
            "angular_velocity_rad_s": [0.01, 0.02, 0.03],
        }
        result = _extract_navigation_attitude(payload)
        assert result["QW"] == pytest.approx(0.9)
        assert result["QX"] == pytest.approx(0.1)
        assert result["QY"] == pytest.approx(0.2)
        assert result["QZ"] == pytest.approx(0.3)
        assert result["OMEGA_X"] == pytest.approx(0.01)
        assert result["OMEGA_Y"] == pytest.approx(0.02)
        assert result["OMEGA_Z"] == pytest.approx(0.03)

    def test_attitude_extraction_empty_payload(self):
        result = _extract_navigation_attitude({})
        assert result["QW"] == 1.0
        assert result["QX"] == 0.0

    def test_orbit_extraction(self):
        payload = {
            "altitude_km": 400.5,
            "true_anomaly_deg": 90.0,
            "inclination_deg": 51.6,
            "semi_major_axis_m": 6778000.0,
        }
        result = _extract_navigation_orbit(payload)
        assert result["ALTITUDE_KM"] == pytest.approx(400.5)
        assert result["TRUE_ANOMALY_DEG"] == pytest.approx(90.0)
        assert result["SMA_KM"] == pytest.approx(6778.0)

    def test_solar_extraction(self):
        payload = {
            "total_power_w": 3200.0,
            "panel_power_w": [1600.0, 1600.0],
            "eclipse": False,
            "sun_angle_deg": 45.0,
        }
        result = _extract_power_solar(payload)
        assert result["TOTAL_POWER_W"] == pytest.approx(3200.0)
        assert result["PANEL_0_W"] == pytest.approx(1600.0)
        assert result["IN_ECLIPSE"] == 0
        assert result["SUN_ANGLE_DEG"] == pytest.approx(45.0)

    def test_solar_extraction_eclipse(self):
        payload = {"eclipse": True}
        result = _extract_power_solar(payload)
        assert result["IN_ECLIPSE"] == 1

    def test_battery_extraction_converts_fraction_to_percent(self):
        payload = {"state_of_charge": 0.85}
        result = _extract_power_battery(payload)
        assert result["BATTERY_SOC"] == pytest.approx(85.0)

    def test_eclipse_extraction(self):
        payload = {"in_eclipse": True, "sun_angle_deg": 180.0}
        result = _extract_power_eclipse(payload)
        assert result["IN_ECLIPSE"] == 1
        assert result["SUN_ANGLE_DEG"] == pytest.approx(180.0)

    def test_thermal_extraction(self):
        payload = {
            "node_temps_k": [300.0, 310.0, 290.0],
            "node_names": ["solar_panel_1", "solar_panel_2", "battery_pack"],
        }
        result = _extract_thermal(payload)
        assert result["SOLAR_PANEL_1_K"] == pytest.approx(300.0)
        assert result["SOLAR_PANEL_2_K"] == pytest.approx(310.0)
        assert result["BATTERY_PACK_K"] == pytest.approx(290.0)

    def test_thermal_extraction_unknown_node_skipped(self):
        payload = {
            "node_temps_k": [300.0],
            "node_names": ["unknown_node"],
        }
        result = _extract_thermal(payload)
        assert len(result) == 0

    def test_reaction_wheels_extraction(self):
        payload = {"speeds_rpm": [1000.0, -2000.0, 1500.0, -500.0]}
        result = _extract_reaction_wheels(payload)
        assert result["RW_0_RPM"] == pytest.approx(1000.0)
        assert result["RW_1_RPM"] == pytest.approx(-2000.0)
        assert result["RW_2_RPM"] == pytest.approx(1500.0)
        assert result["RW_3_RPM"] == pytest.approx(-500.0)

    def test_reaction_wheels_caps_at_four(self):
        payload = {"speeds_rpm": [100, 200, 300, 400, 500, 600]}
        result = _extract_reaction_wheels(payload)
        assert len(result) == 4
        assert "RW_4_RPM" not in result


# ---------------------------------------------------------------------------
# OpenC3 definition generation tests
# ---------------------------------------------------------------------------

class TestDefinitionGeneration:

    def test_command_definition_text(self):
        cmd = _build_aria_commands()[0]  # SAFE_MODE
        text = cmd.to_openc3_definition("ARIA")
        assert "COMMAND ARIA SAFE_MODE BIG_ENDIAN" in text
        assert "HAZARDOUS" in text
        assert "PARAMETER" in text
        assert "REASON" in text
        assert "SHED_LEVEL" in text
        assert "DURATION_S" in text

    def test_telemetry_definition_text(self):
        pkt = _build_aria_telemetry()[0]  # HEALTH_STATUS
        text = pkt.to_openc3_definition("ARIA")
        assert "TELEMETRY ARIA HEALTH_STATUS BIG_ENDIAN" in text
        assert "APPEND_ITEM" in text
        assert "TIMESTAMP" in text

    def test_command_parameter_states_rendered(self):
        commands = {c.name: c for c in _build_aria_commands()}
        text = commands["SAFE_MODE"].to_openc3_definition("ARIA")
        assert "STATE MINIMAL" in text
        assert "STATE SURVIVAL" in text

    def test_telemetry_limits_rendered(self):
        packets = {p.name: p for p in _build_aria_telemetry()}
        text = packets["POWER"].to_openc3_definition("ARIA")
        assert "LIMITS DEFAULT 1 ENABLED" in text

    def test_telemetry_units_rendered(self):
        packets = {p.name: p for p in _build_aria_telemetry()}
        text = packets["NAVIGATION"].to_openc3_definition("ARIA")
        assert "UNITS" in text

    def test_format_string_rendered(self):
        packets = {p.name: p for p in _build_aria_telemetry()}
        text = packets["NAVIGATION"].to_openc3_definition("ARIA")
        assert "FORMAT_STRING" in text


class TestTargetGeneration:

    def test_generate_target_files(self, bridge):
        files = bridge.generate_target_cmd_tlm()
        assert "aria_cmds.txt" in files
        assert "aria_tlm.txt" in files
        assert "COMMAND ARIA" in files["aria_cmds.txt"]
        assert "TELEMETRY ARIA" in files["aria_tlm.txt"]

    def test_generate_target_txt(self, bridge):
        txt = bridge.generate_target_txt()
        assert "ARIA" in txt
        assert "REQUIRE aria_cmds.txt" in txt
        assert "REQUIRE aria_tlm.txt" in txt

    def test_generate_plugin_txt(self, bridge):
        txt = bridge.generate_plugin_txt()
        assert "TARGET ARIA" in txt
        assert "INTERFACE ARIA_INT" in txt
        assert "MAP_TARGET ARIA" in txt

    def test_cmd_file_contains_all_commands(self, bridge):
        files = bridge.generate_target_cmd_tlm()
        cmd_text = files["aria_cmds.txt"]
        for cmd_name in ["SAFE_MODE", "LOAD_SHED", "ATTITUDE_CHANGE",
                         "ORBIT_MANEUVER", "ECLSS_ADJUST"]:
            assert f"COMMAND ARIA {cmd_name}" in cmd_text

    def test_tlm_file_contains_all_packets(self, bridge):
        files = bridge.generate_target_cmd_tlm()
        tlm_text = files["aria_tlm.txt"]
        for pkt_name in ["HEALTH_STATUS", "NAVIGATION", "POWER",
                         "THERMAL", "PROPULSION", "ECLSS"]:
            assert f"TELEMETRY ARIA {pkt_name}" in tlm_text


# ---------------------------------------------------------------------------
# Mock API client tests
# ---------------------------------------------------------------------------

class TestMockApiClient:

    @pytest.mark.asyncio
    async def test_cmd_recorded(self):
        client = MockOpenC3ApiClient()
        result = await client.cmd("ARIA", "SAFE_MODE", {"REASON": "test"})
        assert result["target_name"] == "ARIA"
        assert result["cmd_name"] == "SAFE_MODE"
        assert len(client.sent_commands) == 1

    @pytest.mark.asyncio
    async def test_inject_tlm_recorded(self):
        client = MockOpenC3ApiClient()
        await client.inject_tlm("ARIA", "POWER", {"BATTERY_SOC": 85.0})
        assert len(client.injected_telemetry) == 1
        assert client.injected_telemetry[0]["packet_name"] == "POWER"

    @pytest.mark.asyncio
    async def test_clear_resets_state(self):
        client = MockOpenC3ApiClient()
        await client.cmd("ARIA", "TEST", {})
        await client.inject_tlm("ARIA", "TEST", {})
        client.clear()
        assert len(client.sent_commands) == 0
        assert len(client.injected_telemetry) == 0

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        client = MockOpenC3ApiClient()
        assert client.connected
        await client.disconnect()
        assert not client.connected
        await client.connect()
        assert client.connected


# ---------------------------------------------------------------------------
# Bridge command sending tests
# ---------------------------------------------------------------------------

class TestBridgeCommandSending:

    @pytest.mark.asyncio
    async def test_send_valid_command(self, running_bridge):
        result = await running_bridge.send_command(
            "SAFE_MODE",
            {"REASON": "test_entry", "SHED_LEVEL": 3, "DURATION_S": 120},
        )
        assert result.ok
        assert result.command_name == "SAFE_MODE"
        assert result.message_id

    @pytest.mark.asyncio
    async def test_send_command_with_defaults(self, running_bridge):
        result = await running_bridge.send_command("SAFE_MODE")
        assert result.ok
        assert result.params["REASON"] == "operator_commanded"
        assert result.params["SHED_LEVEL"] == 3
        assert result.params["DURATION_S"] == 0

    @pytest.mark.asyncio
    async def test_send_unknown_command_fails(self, running_bridge):
        result = await running_bridge.send_command("NONEXISTENT_CMD")
        assert not result.ok
        assert any("Unknown" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_send_invalid_params_fails(self, running_bridge):
        result = await running_bridge.send_command(
            "ATTITUDE_CHANGE",
            {"SLEW_RATE_DEG_S": 999.0},  # Way above max
        )
        assert not result.ok
        assert any("above maximum" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_send_command_updates_stats(self, running_bridge):
        await running_bridge.send_command("LOAD_SHED")
        stats = running_bridge.stats
        assert stats["commands_received"] >= 1
        assert stats["commands_dispatched"] >= 1

    @pytest.mark.asyncio
    async def test_send_command_records_in_history(self, running_bridge):
        await running_bridge.send_command("ECLSS_ADJUST")
        history = running_bridge.command_history
        assert len(history) >= 1
        assert history[-1].command_name == "ECLSS_ADJUST"

    @pytest.mark.asyncio
    async def test_send_command_routed_to_mock_api(self, running_bridge):
        await running_bridge.send_command("SAFE_MODE", {"REASON": "api_test"})
        api = running_bridge.api_client
        assert isinstance(api, MockOpenC3ApiClient)
        assert len(api.sent_commands) >= 1
        assert api.sent_commands[-1]["cmd_name"] == "SAFE_MODE"

    @pytest.mark.asyncio
    async def test_skip_validation(self, running_bridge):
        result = await running_bridge.send_command(
            "ATTITUDE_CHANGE",
            {"SLEW_RATE_DEG_S": 999.0},
            validate=False,
        )
        assert result.ok  # Passes because validation skipped

    @pytest.mark.asyncio
    async def test_all_commands_sendable_with_defaults(self, running_bridge):
        """Every defined command should succeed with default parameters."""
        for cmd_name in running_bridge.command_definitions:
            result = await running_bridge.send_command(cmd_name)
            assert result.ok, f"Command {cmd_name} failed: {result.errors}"


# ---------------------------------------------------------------------------
# Bridge telemetry tests
# ---------------------------------------------------------------------------

class TestBridgeTelemetry:

    @pytest.mark.asyncio
    async def test_telemetry_ingestion(self, running_bridge):
        """Publish a sensor message and verify it updates the packet state."""
        message = Message(
            topic="aria.sensor.navigation.orbit",
            payload={
                "altitude_km": 405.0,
                "true_anomaly_deg": 123.4,
                "inclination_deg": 51.6,
                "semi_major_axis_m": 6783000.0,
            },
            priority=EventPriority.P3_ROUTINE,
            source_agent="test",
        )
        bus = running_bridge._bus
        await bus.publish(message)

        # Allow bus to deliver
        await asyncio.sleep(0.1)

        snap = running_bridge.get_telemetry_snapshot("NAVIGATION")
        assert snap is not None
        assert snap.packet_name == "NAVIGATION"
        assert snap.items["ALTITUDE_KM"] == pytest.approx(405.0)
        assert snap.items["SMA_KM"] == pytest.approx(6783.0)

    @pytest.mark.asyncio
    async def test_telemetry_multiple_topics_merge(self, running_bridge):
        """Multiple topics feeding the same packet should merge items."""
        bus = running_bridge._bus

        # Attitude data
        await bus.publish(Message(
            topic="aria.sensor.navigation.attitude",
            payload={
                "quaternion": [0.0, 0.0, 0.0, 1.0],
                "angular_velocity_rad_s": [0.001, 0.002, 0.003],
            },
            priority=EventPriority.P3_ROUTINE,
            source_agent="test",
        ))

        # Orbit data
        await bus.publish(Message(
            topic="aria.sensor.navigation.orbit",
            payload={"altitude_km": 400.0},
            priority=EventPriority.P3_ROUTINE,
            source_agent="test",
        ))

        await asyncio.sleep(0.1)

        snap = running_bridge.get_telemetry_snapshot("NAVIGATION")
        assert snap is not None
        # Both attitude and orbit items should be present
        assert "QW" in snap.items
        assert "ALTITUDE_KM" in snap.items

    @pytest.mark.asyncio
    async def test_no_snapshot_for_empty_packet(self, running_bridge):
        snap = running_bridge.get_telemetry_snapshot("ECLSS")
        assert snap is None

    @pytest.mark.asyncio
    async def test_snapshot_for_unknown_packet_returns_none(self, running_bridge):
        snap = running_bridge.get_telemetry_snapshot("NONEXISTENT")
        assert snap is None

    @pytest.mark.asyncio
    async def test_get_all_snapshots(self, running_bridge):
        bus = running_bridge._bus
        await bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"state_of_charge": 0.92},
            priority=EventPriority.P3_ROUTINE,
            source_agent="test",
        ))
        await asyncio.sleep(0.1)

        snapshots = running_bridge.get_all_telemetry_snapshots()
        assert "POWER" in snapshots
        assert snapshots["POWER"].items["BATTERY_SOC"] == pytest.approx(92.0)

    @pytest.mark.asyncio
    async def test_telemetry_published_to_mock_api(self, running_bridge):
        """Telemetry publish loop should inject into the API client."""
        bus = running_bridge._bus
        await bus.publish(Message(
            topic="aria.sensor.thermal.nodes",
            payload={
                "node_temps_k": [300.0, 310.0],
                "node_names": ["solar_panel_1", "solar_panel_2"],
            },
            priority=EventPriority.P3_ROUTINE,
            source_agent="test",
        ))

        # Wait for bus delivery + one publish cycle
        await asyncio.sleep(running_bridge.config.telemetry_publish_interval + 0.2)

        api = running_bridge.api_client
        assert isinstance(api, MockOpenC3ApiClient)
        assert len(api.injected_telemetry) > 0

    @pytest.mark.asyncio
    async def test_telemetry_sequence_increments(self, running_bridge):
        bus = running_bridge._bus
        for _ in range(3):
            await bus.publish(Message(
                topic="aria.sensor.power.solar_panels",
                payload={"total_power_w": 3000.0, "panel_power_w": [1500, 1500]},
                priority=EventPriority.P3_ROUTINE,
                source_agent="test",
            ))
        await asyncio.sleep(0.1)

        snap = running_bridge.get_telemetry_snapshot("POWER")
        assert snap is not None
        assert snap.sequence_count >= 3


# ---------------------------------------------------------------------------
# Bridge lifecycle tests
# ---------------------------------------------------------------------------

class TestBridgeLifecycle:

    @pytest.mark.asyncio
    async def test_start_stop(self, bus, config):
        await bus.start()
        bridge = OpenC3Bridge(bus, config)
        await bridge.start()
        assert bridge.stats["running"]
        await bridge.stop()
        assert not bridge.stats["running"]
        await bus.stop()

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self, bus, config):
        await bus.start()
        bridge = OpenC3Bridge(bus, config)
        await bridge.start()
        await bridge.start()  # Should not raise
        assert bridge.stats["running"]
        await bridge.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_stop_without_start_is_safe(self, bus, config):
        bridge = OpenC3Bridge(bus, config)
        await bridge.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_mock_mode_flag(self, bridge):
        assert bridge.stats["mock_mode"]

    def test_definitions_accessible_before_start(self, bridge):
        assert len(bridge.command_definitions) == 5
        assert len(bridge.telemetry_definitions) == 6


# ---------------------------------------------------------------------------
# Bus payload conversion tests
# ---------------------------------------------------------------------------

class TestBusPayloadConversion:

    def test_params_lowercased(self):
        cmd = _build_aria_commands()[0]  # SAFE_MODE
        payload = _command_params_to_bus_payload(
            cmd,
            {"REASON": "test", "SHED_LEVEL": 3, "DURATION_S": 60},
        )
        assert "reason" in payload
        assert "shed_level" in payload
        assert "duration_s" in payload
        assert payload["reason"] == "test"

    def test_missing_params_use_defaults(self):
        cmd = _build_aria_commands()[0]  # SAFE_MODE
        payload = _command_params_to_bus_payload(cmd, {})
        assert payload["reason"] == "operator_commanded"
        assert payload["shed_level"] == 3
        assert payload["duration_s"] == 0


# ---------------------------------------------------------------------------
# Full round-trip integration test
# ---------------------------------------------------------------------------

class TestFullRoundTrip:

    @pytest.mark.asyncio
    async def test_command_then_telemetry_cycle(self):
        """Full cycle: send command -> ARIA bus delivers -> telemetry update -> OpenC3."""
        bus = MessageBus()
        await bus.start()

        config = OpenC3Config(
            mock_mode=True,
            telemetry_publish_interval=0.2,
        )
        bridge = OpenC3Bridge(bus, config)
        await bridge.start()

        # 1. Send attitude change command
        result = await bridge.send_command("ATTITUDE_CHANGE", {
            "TARGET_QW": 0.707,
            "TARGET_QX": 0.707,
            "TARGET_QY": 0.0,
            "TARGET_QZ": 0.0,
            "SLEW_RATE_DEG_S": 1.0,
            "MODE": "EIGENAXIS",
        })
        assert result.ok

        # 2. Simulate resulting attitude telemetry on the bus
        await bus.publish(Message(
            topic="aria.sensor.navigation.attitude",
            payload={
                "quaternion": [0.707, 0.0, 0.0, 0.707],
                "angular_velocity_rad_s": [0.01, 0.0, 0.0],
            },
            priority=EventPriority.P3_ROUTINE,
            source_agent="nav_agent",
        ))

        # Allow bus delivery + publish cycle
        await asyncio.sleep(0.5)

        # 3. Verify telemetry arrived at bridge
        snap = bridge.get_telemetry_snapshot("NAVIGATION")
        assert snap is not None
        assert snap.items["QW"] == pytest.approx(0.707)
        assert snap.items["QX"] == pytest.approx(0.707)

        # 4. Verify mock API received both command and telemetry
        api = bridge.api_client
        assert isinstance(api, MockOpenC3ApiClient)
        assert len(api.sent_commands) >= 1
        assert len(api.injected_telemetry) >= 1

        # 5. Verify stats
        stats = bridge.stats
        assert stats["commands_dispatched"] >= 1
        assert stats["telemetry_messages_ingested"] >= 1

        await bridge.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_multiple_subsystem_telemetry(self):
        """Verify that telemetry from multiple subsystems arrives correctly."""
        bus = MessageBus()
        await bus.start()
        bridge = OpenC3Bridge(bus, OpenC3Config(mock_mode=True))
        await bridge.start()

        # Publish from multiple subsystems
        messages = [
            Message(
                topic="aria.sensor.power.solar_panels",
                payload={"total_power_w": 3100.0, "panel_power_w": [1550, 1550],
                         "eclipse": False, "sun_angle_deg": 30.0},
                priority=EventPriority.P3_ROUTINE,
                source_agent="power_agent",
            ),
            Message(
                topic="aria.sensor.thermal.nodes",
                payload={
                    "node_temps_k": [305.0, 302.0, 295.0, 290.0, 310.0, 280.0, 288.0, 305.0],
                    "node_names": [
                        "solar_panel_1", "solar_panel_2", "battery_pack",
                        "payload_bay", "reaction_wheel_cluster", "star_tracker",
                        "propellant_tank", "avionics_bay",
                    ],
                },
                priority=EventPriority.P3_ROUTINE,
                source_agent="thermal_agent",
            ),
            Message(
                topic="aria.sensor.propulsion.reaction_wheels",
                payload={"speeds_rpm": [1200.0, -800.0, 950.0, -1100.0]},
                priority=EventPriority.P3_ROUTINE,
                source_agent="prop_agent",
            ),
        ]

        for msg in messages:
            await bus.publish(msg)

        await asyncio.sleep(0.15)

        # Check all three packets populated
        power_snap = bridge.get_telemetry_snapshot("POWER")
        thermal_snap = bridge.get_telemetry_snapshot("THERMAL")
        prop_snap = bridge.get_telemetry_snapshot("PROPULSION")

        assert power_snap is not None
        assert power_snap.items["TOTAL_POWER_W"] == pytest.approx(3100.0)

        assert thermal_snap is not None
        assert thermal_snap.items["BATTERY_PACK_K"] == pytest.approx(295.0)

        assert prop_snap is not None
        assert prop_snap.items["RW_0_RPM"] == pytest.approx(1200.0)

        await bridge.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_command_rejection_does_not_affect_telemetry(self):
        """A rejected command should not interfere with telemetry flow."""
        bus = MessageBus()
        await bus.start()
        bridge = OpenC3Bridge(bus, OpenC3Config(mock_mode=True))
        await bridge.start()

        # Send invalid command
        result = await bridge.send_command("NONEXISTENT")
        assert not result.ok

        # Telemetry should still work
        await bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"state_of_charge": 0.75},
            priority=EventPriority.P3_ROUTINE,
            source_agent="test",
        ))
        await asyncio.sleep(0.1)

        snap = bridge.get_telemetry_snapshot("POWER")
        assert snap is not None
        assert snap.items["BATTERY_SOC"] == pytest.approx(75.0)

        await bridge.stop()
        await bus.stop()
