"""Tests for ARIA Telemetry Server (OpenMCT integration).

Tests verify:
  - Telemetry dictionary completeness
  - History store operations
  - Basilisk frame conversion
  - Server endpoint functionality
"""

import time

import pytest

from aria.dashboard.telemetry_server import (
    ARIA_TELEMETRY_DICTIONARY,
    ARIATelemetryServer,
    TelemetryHistoryStore,
)


class TestTelemetryDictionary:
    """Verify telemetry dictionary is complete and valid."""

    def test_dictionary_not_empty(self) -> None:
        assert len(ARIA_TELEMETRY_DICTIONARY) > 15

    def test_all_entries_have_required_fields(self) -> None:
        required = {"key", "name", "unit", "subsystem", "format"}
        for entry in ARIA_TELEMETRY_DICTIONARY:
            missing = required - set(entry.keys())
            assert not missing, f"Entry {entry.get('key')} missing: {missing}"

    def test_keys_are_unique(self) -> None:
        keys = [e["key"] for e in ARIA_TELEMETRY_DICTIONARY]
        assert len(keys) == len(set(keys))

    def test_subsystems_covered(self) -> None:
        subsystems = {e["subsystem"] for e in ARIA_TELEMETRY_DICTIONARY}
        assert "power" in subsystems
        assert "navigation" in subsystems
        assert "adcs" in subsystems
        assert "eclss" in subsystems

    def test_power_points_exist(self) -> None:
        power_keys = [e["key"] for e in ARIA_TELEMETRY_DICTIONARY if e["subsystem"] == "power"]
        assert "aria.power.battery_soc" in power_keys
        assert "aria.power.solar_watts" in power_keys
        assert "aria.power.bus_voltage" in power_keys

    def test_navigation_points_exist(self) -> None:
        nav_keys = [e["key"] for e in ARIA_TELEMETRY_DICTIONARY if e["subsystem"] == "navigation"]
        assert "aria.nav.altitude" in nav_keys
        assert "aria.nav.velocity" in nav_keys
        assert "aria.nav.latitude" in nav_keys

    def test_format_types_valid(self) -> None:
        valid_formats = {"float", "integer", "enum", "string"}
        for entry in ARIA_TELEMETRY_DICTIONARY:
            assert entry["format"] in valid_formats, f"{entry['key']} has invalid format: {entry['format']}"

    def test_enum_entries_have_enumerations(self) -> None:
        for entry in ARIA_TELEMETRY_DICTIONARY:
            if entry["format"] == "enum":
                assert "enumerations" in entry, f"{entry['key']} is enum but missing enumerations"
                assert len(entry["enumerations"]) > 0

    def test_limits_have_valid_structure(self) -> None:
        for entry in ARIA_TELEMETRY_DICTIONARY:
            if "limits" in entry:
                limits = entry["limits"]
                for lkey in limits:
                    assert lkey in ("warning_low", "warning_high", "critical_low", "critical_high")
                    assert isinstance(limits[lkey], (int, float))


class TestHistoryStore:
    """Verify telemetry history store operations."""

    def test_record_and_query(self) -> None:
        store = TelemetryHistoryStore()
        store.record("test.key", 1000, 42.0)
        store.record("test.key", 2000, 43.0)
        result = store.query("test.key")
        assert len(result) == 2
        assert result[0]["value"] == 42.0

    def test_latest_value(self) -> None:
        store = TelemetryHistoryStore()
        store.record("test.key", 1000, 42.0)
        store.record("test.key", 2000, 99.0)
        latest = store.latest("test.key")
        assert latest is not None
        assert latest["value"] == 99.0

    def test_time_range_query(self) -> None:
        store = TelemetryHistoryStore()
        for i in range(100):
            store.record("test.key", i * 1000, float(i))
        result = store.query("test.key", start_ms=50000, end_ms=60000)
        assert all(50000 <= r["timestamp"] <= 60000 for r in result)

    def test_limit_query(self) -> None:
        store = TelemetryHistoryStore()
        for i in range(100):
            store.record("test.key", i * 1000, float(i))
        result = store.query("test.key", limit=10)
        assert len(result) == 10

    def test_ring_buffer_max(self) -> None:
        store = TelemetryHistoryStore(max_per_key=50)
        for i in range(100):
            store.record("test.key", i, float(i))
        result = store.query("test.key")
        assert len(result) == 50
        # Should have the latest 50
        assert result[0]["value"] == 50.0

    def test_multiple_keys(self) -> None:
        store = TelemetryHistoryStore()
        store.record("key1", 1000, 1.0)
        store.record("key2", 1000, 2.0)
        assert store.latest("key1")["value"] == 1.0
        assert store.latest("key2")["value"] == 2.0
        assert len(store.keys) == 2

    def test_nonexistent_key(self) -> None:
        store = TelemetryHistoryStore()
        assert store.latest("nonexistent") is None
        assert store.query("nonexistent") == []


class TestServerPush:
    """Test server push and frame conversion."""

    def test_push_records_to_history(self) -> None:
        server = ARIATelemetryServer()
        server.push("aria.power.battery_soc", 85.0)
        latest = server._history.latest("aria.power.battery_soc")
        assert latest is not None
        assert latest["value"] == 85.0

    def test_push_with_custom_timestamp(self) -> None:
        server = ARIATelemetryServer()
        server.push("aria.nav.altitude", 400.5, timestamp_ms=1234567890)
        latest = server._history.latest("aria.nav.altitude")
        assert latest["timestamp"] == 1234567890

    def test_push_basilisk_frame(self) -> None:
        """Test conversion of Basilisk frame to telemetry keys."""
        from aria.simulation.basilisk_runner import TelemetryFrame

        server = ARIATelemetryServer()
        frame = TelemetryFrame(
            timestamp_s=100.0,
            position_eci_m=[6771000.0, 0.0, 0.0],
            velocity_eci_m_s=[0.0, 4766.0, 6014.0],
            altitude_km=400.0,
            attitude_mrp=[0.01, 0.02, 0.03],
            attitude_rate_rad_s=[0.0, 0.0, 0.001],
            roll_deg=1.2,
            pitch_deg=2.3,
            yaw_deg=3.4,
            solar_power_w=2722.0,
            battery_soc=0.8,
            power_draw_w=200.0,
            in_eclipse=False,
            orbital_velocity_m_s=7673.0,
            ground_track_lat_deg=10.5,
            ground_track_lon_deg=25.3,
        )
        server.push_basilisk_frame(frame)

        # Check all keys were populated
        assert server._history.latest("aria.power.battery_soc")["value"] == 80.0  # 0.8 * 100
        assert server._history.latest("aria.power.solar_watts")["value"] == 2722.0
        assert server._history.latest("aria.nav.altitude")["value"] == 400.0
        assert server._history.latest("aria.nav.velocity")["value"] == 7673.0
        assert server._history.latest("aria.nav.latitude")["value"] == 10.5
        assert server._history.latest("aria.adcs.roll")["value"] == 1.2
        assert server._history.latest("aria.power.in_eclipse")["value"] == 0

    def test_push_eclipse_frame(self) -> None:
        from aria.simulation.basilisk_runner import TelemetryFrame

        server = ARIATelemetryServer()
        frame = TelemetryFrame(
            timestamp_s=200.0,
            in_eclipse=True,
            solar_power_w=0.0,
        )
        server.push_basilisk_frame(frame)
        assert server._history.latest("aria.power.in_eclipse")["value"] == 1
        assert server._history.latest("aria.power.solar_watts")["value"] == 0.0
