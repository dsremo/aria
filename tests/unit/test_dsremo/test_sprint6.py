"""Sprint 6 tests — XTCE Parameter Import.

All tests are pure unit/integration tests — no real DB required.
Covers:
  - xtce_parser.py (TestXTCEParser)        — XML parsing, namespace variants,
      alarm ranges, nested SpaceSystems, type resolution, error cases
  - routes_parameters.py (TestXTCEImportAPI) — HTTP round-trip via demo_client
  - memory_store.py (TestMemoryStoreChannels) — upsert_channel_seen / satellite_seen stubs
"""

from __future__ import annotations

import textwrap

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Shared XTCE XML fixtures
# ---------------------------------------------------------------------------

def _xtce(body: str, ns: str = "urn:ccsds:schema:ndm:xtce", name: str = "MySat") -> bytes:
    """Wrap body inside a minimal SpaceSystem root."""
    ns_attr = f'xmlns="{ns}"' if ns else ""
    return textwrap.dedent(f"""\
        <?xml version="1.0"?>
        <SpaceSystem name="{name}" {ns_attr}>
          {body}
        </SpaceSystem>
    """).encode()


_MINIMAL_XTCE = _xtce("""
    <TelemetryMetaData>
      <ParameterTypeSet>
        <FloatParameterType name="voltage_t">
          <UnitSet><Unit>V</Unit></UnitSet>
        </FloatParameterType>
      </ParameterTypeSet>
      <ParameterSet>
        <Parameter name="battery_voltage" parameterTypeRef="voltage_t"/>
      </ParameterSet>
    </TelemetryMetaData>
""")

_FULL_XTCE = _xtce("""
    <TelemetryMetaData>
      <ParameterTypeSet>
        <FloatParameterType name="voltage_t">
          <UnitSet><Unit>V</Unit></UnitSet>
          <DefaultAlarm>
            <StaticAlarmRanges>
              <WatchRange minInclusive="6.0" maxInclusive="8.4"/>
              <WarningRange minInclusive="5.5" maxInclusive="8.8"/>
            </StaticAlarmRanges>
          </DefaultAlarm>
        </FloatParameterType>
        <FloatParameterType name="current_t">
          <UnitSet><Unit>A</Unit></UnitSet>
          <DefaultAlarm>
            <StaticAlarmRanges>
              <WatchRange minInclusive="0.0" maxInclusive="5.0"/>
              <CautionRange minInclusive="-0.5" maxInclusive="5.5"/>
            </StaticAlarmRanges>
          </DefaultAlarm>
        </FloatParameterType>
        <FloatParameterType name="temp_t">
          <UnitSet><Unit>degC</Unit></UnitSet>
        </FloatParameterType>
      </ParameterTypeSet>
      <ParameterSet>
        <Parameter name="bus_voltage" parameterTypeRef="voltage_t">
          <LongDescription>Main bus voltage</LongDescription>
        </Parameter>
        <Parameter name="solar_current" parameterTypeRef="current_t"/>
        <Parameter name="mcu_temp" parameterTypeRef="temp_t"/>
      </ParameterSet>
    </TelemetryMetaData>
""")

_NESTED_XTCE = _xtce("""
    <SpaceSystem name="EPS">
      <TelemetryMetaData>
        <ParameterTypeSet>
          <FloatParameterType name="volt_t">
            <UnitSet><Unit>V</Unit></UnitSet>
          </FloatParameterType>
        </ParameterTypeSet>
        <ParameterSet>
          <Parameter name="battery_v" parameterTypeRef="volt_t"/>
        </ParameterSet>
      </TelemetryMetaData>
    </SpaceSystem>
    <SpaceSystem name="COMMS">
      <TelemetryMetaData>
        <ParameterTypeSet>
          <FloatParameterType name="rssi_t">
            <UnitSet><Unit>dBm</Unit></UnitSet>
          </FloatParameterType>
        </ParameterTypeSet>
        <ParameterSet>
          <Parameter name="rssi" parameterTypeRef="rssi_t"/>
        </ParameterSet>
      </TelemetryMetaData>
    </SpaceSystem>
""")

_NO_NS_XTCE = _xtce("""
    <TelemetryMetaData>
      <ParameterTypeSet>
        <FloatParameterType name="f_t">
          <UnitSet><Unit>Hz</Unit></UnitSet>
        </FloatParameterType>
      </ParameterTypeSet>
      <ParameterSet>
        <Parameter name="freq" parameterTypeRef="f_t"/>
      </ParameterSet>
    </TelemetryMetaData>
""", ns="")   # no namespace


# ---------------------------------------------------------------------------
# 1. TestXTCEParser — pure parser unit tests
# ---------------------------------------------------------------------------

class TestXTCEParser:
    """Unit tests for dsremo.ingest.xtce_parser.parse_xtce()."""

    def _parse(self, xml: bytes):
        from aria.dsremo.ingest.xtce_parser import parse_xtce
        return parse_xtce(xml)

    # --- Basic correctness ---

    def test_returns_list_of_parameter_defs(self):
        from aria.dsremo.ingest.xtce_parser import ParameterDef
        result = self._parse(_MINIMAL_XTCE)
        assert isinstance(result, list)
        assert all(isinstance(p, ParameterDef) for p in result)

    def test_minimal_xtce_yields_one_parameter(self):
        result = self._parse(_MINIMAL_XTCE)
        assert len(result) == 1
        assert result[0].name == "battery_voltage"

    def test_unit_extracted_correctly(self):
        result = self._parse(_MINIMAL_XTCE)
        assert result[0].unit == "V"

    def test_subsystem_is_root_spacesystem_name_lowercased(self):
        result = self._parse(_MINIMAL_XTCE)
        # Root SpaceSystem name="MySat" → subsystem "mysat"
        assert result[0].subsystem == "mysat"

    def test_description_extracted(self):
        result = self._parse(_FULL_XTCE)
        bus_v = next(p for p in result if p.name == "bus_voltage")
        assert bus_v.description == "Main bus voltage"

    def test_description_empty_when_absent(self):
        result = self._parse(_FULL_XTCE)
        solar = next(p for p in result if p.name == "solar_current")
        assert solar.description == ""

    # --- Multiple parameters ---

    def test_full_xtce_yields_three_parameters(self):
        result = self._parse(_FULL_XTCE)
        assert len(result) == 3

    def test_all_parameter_names_present(self):
        result = self._parse(_FULL_XTCE)
        names = {p.name for p in result}
        assert names == {"bus_voltage", "solar_current", "mcu_temp"}

    # --- Alarm ranges ---

    def test_watch_range_extracted(self):
        result = self._parse(_FULL_XTCE)
        bus_v = next(p for p in result if p.name == "bus_voltage")
        assert bus_v.watch_range is not None
        assert bus_v.watch_range.low == pytest.approx(6.0)
        assert bus_v.watch_range.high == pytest.approx(8.4)

    def test_warning_range_extracted(self):
        result = self._parse(_FULL_XTCE)
        bus_v = next(p for p in result if p.name == "bus_voltage")
        assert bus_v.warning_range is not None
        assert bus_v.warning_range.low == pytest.approx(5.5)
        assert bus_v.warning_range.high == pytest.approx(8.8)

    def test_caution_range_treated_as_warning(self):
        """CautionRange is a YAMCS alias for WarningRange."""
        result = self._parse(_FULL_XTCE)
        solar = next(p for p in result if p.name == "solar_current")
        assert solar.warning_range is not None
        assert solar.warning_range.low == pytest.approx(-0.5)

    def test_no_alarm_range_when_absent(self):
        result = self._parse(_FULL_XTCE)
        temp = next(p for p in result if p.name == "mcu_temp")
        assert temp.watch_range is None
        assert temp.warning_range is None

    # --- Nested SpaceSystems ---

    def test_nested_spacesystems_yield_two_parameters(self):
        result = self._parse(_NESTED_XTCE)
        assert len(result) == 2

    def test_subsystem_from_child_spacesystem_lowercased(self):
        result = self._parse(_NESTED_XTCE)
        by_name = {p.name: p for p in result}
        assert by_name["battery_v"].subsystem == "eps"
        assert by_name["rssi"].subsystem == "comms"

    def test_unit_correct_in_nested_system(self):
        result = self._parse(_NESTED_XTCE)
        by_name = {p.name: p for p in result}
        assert by_name["rssi"].unit == "dBm"

    # --- Namespace variants ---

    def test_xtce_1_1_namespace_parsed(self):
        xml = _xtce("<TelemetryMetaData><ParameterSet/></TelemetryMetaData>",
                    ns="urn:ccsds:schema:ndm:xtce")
        result = self._parse(xml)
        assert result == []  # no parameters — just checking no exception

    def test_xtce_1_2_namespace_parsed(self):
        xml = _xtce("""
            <TelemetryMetaData>
              <ParameterTypeSet>
                <FloatParameterType name="t">
                  <UnitSet><Unit>W</Unit></UnitSet>
                </FloatParameterType>
              </ParameterTypeSet>
              <ParameterSet>
                <Parameter name="power" parameterTypeRef="t"/>
              </ParameterSet>
            </TelemetryMetaData>
        """, ns="urn:ccsds:schema:ndm:xtce-1.2")
        result = self._parse(xml)
        assert len(result) == 1
        assert result[0].name == "power"
        assert result[0].unit == "W"

    def test_no_namespace_variant_parsed(self):
        result = self._parse(_NO_NS_XTCE)
        assert len(result) == 1
        assert result[0].name == "freq"
        assert result[0].unit == "Hz"

    # --- Error cases ---

    def test_malformed_xml_raises_parse_error(self):
        import xml.etree.ElementTree as ET
        with pytest.raises(ET.ParseError):
            self._parse(b"<not valid xml")

    def test_empty_bytes_raises_value_error(self):
        with pytest.raises(ValueError):
            self._parse(b"")

    def test_whitespace_only_raises_value_error(self):
        with pytest.raises(ValueError):
            self._parse(b"   \n  ")

    def test_non_xtce_root_raises_value_error(self):
        with pytest.raises(ValueError, match="SpaceSystem"):
            self._parse(b"<root><child/></root>")

    def test_empty_parameter_set_returns_empty_list(self):
        xml = _xtce("<TelemetryMetaData><ParameterSet/></TelemetryMetaData>")
        result = self._parse(xml)
        assert result == []

    def test_parameter_without_type_ref_gets_empty_unit(self):
        xml = _xtce("""
            <TelemetryMetaData>
              <ParameterSet>
                <Parameter name="mystery"/>
              </ParameterSet>
            </TelemetryMetaData>
        """)
        result = self._parse(xml)
        assert len(result) == 1
        assert result[0].unit == ""
        assert result[0].watch_range is None

    def test_accepts_path_input(self, tmp_path):
        p = tmp_path / "mission.xml"
        p.write_bytes(_MINIMAL_XTCE)
        from aria.dsremo.ingest.xtce_parser import parse_xtce
        result = parse_xtce(p)
        assert len(result) == 1

    def test_accepts_io_bytes_input(self):
        import io
        from aria.dsremo.ingest.xtce_parser import parse_xtce
        result = parse_xtce(io.BytesIO(_MINIMAL_XTCE))
        assert len(result) == 1


# ---------------------------------------------------------------------------
# 2. TestXTCEImportAPI — HTTP round-trip via demo_client
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def demo_client():
    from aria.dsremo.api.app import create_app
    app = create_app(demo=True)
    with TestClient(app) as client:
        yield client


class TestXTCEImportAPI:
    """API-level tests: POST /api/v1/parameters/import-xtce."""

    def _post(self, client, xml: bytes = _MINIMAL_XTCE, satellite_id: str = "TEST-SAT-01"):
        return client.post(
            "/api/v1/parameters/import-xtce",
            data={"satellite_id": satellite_id},
            files={"file": ("mission.xml", xml, "application/xml")},
        )

    def test_import_returns_200(self, demo_client):
        resp = self._post(demo_client)
        assert resp.status_code == 200

    def test_import_returns_correct_count(self, demo_client):
        resp = self._post(demo_client)
        data = resp.json()
        assert data["parameters_imported"] == 1

    def test_import_returns_satellite_id(self, demo_client):
        resp = self._post(demo_client)
        assert resp.json()["satellite_id"] == "TEST-SAT-01"

    def test_import_returns_parameter_list(self, demo_client):
        resp = self._post(demo_client)
        params = resp.json()["parameters"]
        assert len(params) == 1
        assert params[0]["name"] == "battery_voltage"

    def test_import_preserves_unit(self, demo_client):
        resp = self._post(demo_client)
        assert resp.json()["parameters"][0]["unit"] == "V"

    def test_import_preserves_subsystem(self, demo_client):
        resp = self._post(demo_client)
        # Root SpaceSystem name="MySat" → subsystem "mysat"
        assert resp.json()["parameters"][0]["subsystem"] == "mysat"

    def test_import_full_xtce_returns_all_params(self, demo_client):
        resp = self._post(demo_client, _FULL_XTCE)
        assert resp.json()["parameters_imported"] == 3

    def test_import_alarm_ranges_in_response(self, demo_client):
        resp = self._post(demo_client, _FULL_XTCE)
        bus_v = next(p for p in resp.json()["parameters"] if p["name"] == "bus_voltage")
        assert bus_v["watch_range"]["low"] == pytest.approx(6.0)
        assert bus_v["watch_range"]["high"] == pytest.approx(8.4)
        assert bus_v["warning_range"]["low"] == pytest.approx(5.5)

    def test_import_nested_spacesystems(self, demo_client):
        resp = self._post(demo_client, _NESTED_XTCE)
        data = resp.json()
        assert data["parameters_imported"] == 2
        subsystems = {p["subsystem"] for p in data["parameters"]}
        assert "eps" in subsystems
        assert "comms" in subsystems

    def test_import_missing_satellite_id_returns_422(self, demo_client):
        resp = demo_client.post(
            "/api/v1/parameters/import-xtce",
            files={"file": ("m.xml", _MINIMAL_XTCE, "application/xml")},
        )
        assert resp.status_code == 422

    def test_import_empty_satellite_id_returns_422(self, demo_client):
        resp = demo_client.post(
            "/api/v1/parameters/import-xtce",
            data={"satellite_id": ""},
            files={"file": ("m.xml", _MINIMAL_XTCE, "application/xml")},
        )
        assert resp.status_code == 422

    def test_import_invalid_xml_returns_400(self, demo_client):
        resp = self._post(demo_client, b"<bad xml")
        assert resp.status_code == 400
        assert "XML" in resp.json()["detail"]

    def test_import_empty_file_returns_400(self, demo_client):
        resp = self._post(demo_client, b"")
        assert resp.status_code == 400

    def test_import_non_xtce_xml_returns_400(self, demo_client):
        resp = self._post(demo_client, b"<html><body>not xtce</body></html>")
        assert resp.status_code == 400
        assert "SpaceSystem" in resp.json()["detail"]

    def test_import_no_parameters_returns_400(self, demo_client):
        empty = _xtce("<TelemetryMetaData><ParameterSet/></TelemetryMetaData>")
        resp = self._post(demo_client, empty)
        assert resp.status_code == 400

    def test_import_idempotent_no_error_on_repeat(self, demo_client):
        """Re-importing the same file must not raise."""
        resp1 = self._post(demo_client, _FULL_XTCE, satellite_id="IDEM-SAT")
        resp2 = self._post(demo_client, _FULL_XTCE, satellite_id="IDEM-SAT")
        assert resp1.status_code == 200
        assert resp2.status_code == 200

    def test_import_no_namespace_variant(self, demo_client):
        resp = self._post(demo_client, _NO_NS_XTCE)
        assert resp.status_code == 200
        assert resp.json()["parameters_imported"] == 1


# ---------------------------------------------------------------------------
# 3. TestMemoryStoreChannels — upsert_satellite_seen + upsert_channel_seen
# ---------------------------------------------------------------------------

class TestMemoryStoreChannels:
    """Verify the new demo-mode stubs behave correctly."""

    @pytest.mark.asyncio
    async def test_upsert_satellite_seen_stores_satellite(self):
        from datetime import datetime, timezone
        from aria.dsremo.db.memory_store import (
            _satellites_seen, upsert_satellite_seen
        )
        ts = datetime.now(timezone.utc)
        await upsert_satellite_seen("TEST-MEMSAT", ts)
        assert "TEST-MEMSAT" in _satellites_seen

    @pytest.mark.asyncio
    async def test_upsert_channel_seen_stores_channel(self):
        from aria.dsremo.db.memory_store import (
            _channels_seen, upsert_channel_seen
        )
        await upsert_channel_seen("MEM-SAT", "volt", "eps", "V")
        assert ("MEM-SAT", "volt") in _channels_seen

    @pytest.mark.asyncio
    async def test_upsert_channel_seen_updates_existing(self):
        from aria.dsremo.db.memory_store import (
            _channels_seen, upsert_channel_seen
        )
        await upsert_channel_seen("UPD-SAT", "temp", "eps", "degC")
        # Second call with new unit — should overwrite
        await upsert_channel_seen("UPD-SAT", "temp", "thermal", "K")
        row = _channels_seen[("UPD-SAT", "temp")]
        assert row["subsystem"] == "thermal"
        assert row["unit"] == "K"

    @pytest.mark.asyncio
    async def test_get_channel_stats_returns_upserted_channels(self):
        from aria.dsremo.db.memory_store import get_channel_stats, upsert_channel_seen
        await upsert_channel_seen("STATS-SAT", "gyro_x", "adcs", "deg/s")
        rows = await get_channel_stats(satellite_id="STATS-SAT")
        names = [r["parameter"] for r in rows]
        assert "gyro_x" in names

    @pytest.mark.asyncio
    async def test_get_channel_stats_filters_by_satellite(self):
        from aria.dsremo.db.memory_store import get_channel_stats, upsert_channel_seen
        await upsert_channel_seen("FILTER-A", "p1", "s1", "")
        await upsert_channel_seen("FILTER-B", "p2", "s2", "")
        rows_a = await get_channel_stats(satellite_id="FILTER-A")
        assert all(r["satellite_id"] == "FILTER-A" for r in rows_a)
