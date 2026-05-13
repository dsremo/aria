"""Tests for Sprint 3: DataConnector ABC.

All tests are pure unit tests — no database required.
Tests cover:
  - DataConnector ABC interface compliance (SatNOGSFetcher, ESADataLoader, CSVConnector)
  - source_name property for each connector
  - SatNOGSFetcher constructor norad_ids parameter
  - ESADataLoader constructor channels parameter
  - CSVConnector: wide CSV parsing, NaN handling, resampling,
    UTC localization, empty file, skip threshold
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from aria.dsremo.ingest.connector import DataConnector
from aria.dsremo.ingest.csv_connector import CSVConnector
from aria.dsremo.ingest.esa_loader import ESADataLoader
from aria.dsremo.ingest.satnogs_fetcher import SatNOGSFetcher


# ---------------------------------------------------------------------------
# ABC interface compliance
# ---------------------------------------------------------------------------

class TestDataConnectorABC:
    def test_satnogs_is_connector(self):
        assert isinstance(SatNOGSFetcher(), DataConnector)

    def test_esa_is_connector(self):
        assert isinstance(ESADataLoader(), DataConnector)

    def test_csv_is_connector(self, tmp_path):
        f = tmp_path / "t.csv"
        f.write_text("timestamp,v\n2024-01-01T00:00:00Z,1.0\n")
        assert isinstance(CSVConnector(f, "SAT-1"), DataConnector)

    def test_source_name_satnogs(self):
        assert SatNOGSFetcher().source_name == "satnogs"

    def test_source_name_esa(self):
        assert ESADataLoader().source_name == "esa-mission1"

    def test_source_name_csv_includes_filename(self, tmp_path):
        f = tmp_path / "mydata.csv"
        f.write_text("timestamp,v\n")
        assert CSVConnector(f, "SAT-1").source_name == "csv:mydata.csv"

    def test_cannot_instantiate_abc_directly(self):
        with pytest.raises(TypeError):
            DataConnector()  # type: ignore[abstract]

    def test_all_connectors_have_bulk_load_to_db(self):
        for cls in (SatNOGSFetcher, ESADataLoader):
            assert callable(getattr(cls, "bulk_load_to_db", None))
        assert callable(getattr(CSVConnector, "bulk_load_to_db", None))


# ---------------------------------------------------------------------------
# SatNOGSFetcher constructor changes
# ---------------------------------------------------------------------------

class TestSatNOGSFetcherConstructor:
    def test_norad_ids_stored_from_constructor(self):
        fetcher = SatNOGSFetcher(norad_ids=["25544", "43017"])
        assert fetcher.norad_ids == ["25544", "43017"]

    def test_norad_ids_defaults_to_none(self):
        assert SatNOGSFetcher().norad_ids is None

    def test_api_token_still_works(self):
        fetcher = SatNOGSFetcher(api_token="tok123")
        assert fetcher.api_token == "tok123"

    def test_norad_ids_and_token_together(self):
        fetcher = SatNOGSFetcher(api_token="t", norad_ids=["25544"])
        assert fetcher.norad_ids == ["25544"]
        assert fetcher.api_token == "t"


# ---------------------------------------------------------------------------
# ESADataLoader constructor changes
# ---------------------------------------------------------------------------

class TestESADataLoaderConstructor:
    def test_channels_stored_from_constructor(self):
        loader = ESADataLoader(channels=["channel_1", "channel_2"])
        assert loader._default_channels == ["channel_1", "channel_2"]

    def test_channels_defaults_to_none(self):
        assert ESADataLoader()._default_channels is None

    def test_data_dir_still_works(self, tmp_path):
        loader = ESADataLoader(data_dir=tmp_path)
        assert loader.data_dir == tmp_path

    def test_both_constructor_params(self, tmp_path):
        loader = ESADataLoader(data_dir=tmp_path, channels=["ch1"])
        assert loader.data_dir == tmp_path
        assert loader._default_channels == ["ch1"]


# ---------------------------------------------------------------------------
# CSVConnector: constructor and source_name
# ---------------------------------------------------------------------------

class TestCSVConnectorConstructor:
    def test_file_path_is_path_object(self, tmp_path):
        f = tmp_path / "data.csv"
        c = CSVConnector(str(f), "SAT-1")
        assert isinstance(c.file_path, Path)
        assert c.file_path == f

    def test_satellite_id_stored(self, tmp_path):
        f = tmp_path / "x.csv"
        c = CSVConnector(f, "TEST-SAT")
        assert c.satellite_id == "TEST-SAT"

    def test_subsystem_default(self, tmp_path):
        f = tmp_path / "x.csv"
        assert CSVConnector(f, "S").subsystem == "unknown"

    def test_subsystem_custom(self, tmp_path):
        f = tmp_path / "x.csv"
        assert CSVConnector(f, "S", subsystem="eps").subsystem == "eps"

    def test_timestamp_col_default(self, tmp_path):
        f = tmp_path / "x.csv"
        assert CSVConnector(f, "S").timestamp_col == "timestamp"

    def test_timestamp_col_custom(self, tmp_path):
        f = tmp_path / "x.csv"
        assert CSVConnector(f, "S", timestamp_col="time").timestamp_col == "time"

    def test_source_name_uses_stem(self, tmp_path):
        f = tmp_path / "telemetry_eps.csv"
        assert CSVConnector(f, "S").source_name == "csv:telemetry_eps.csv"


# ---------------------------------------------------------------------------
# CSVConnector: bulk_load_to_db (async, mocked DB calls)
# ---------------------------------------------------------------------------

def _make_csv(tmp_path: Path, content: str, name: str = "test.csv") -> Path:
    f = tmp_path / name
    f.write_text(textwrap.dedent(content).strip())
    return f


@pytest.mark.asyncio
class TestCSVConnectorBulkLoad:
    # Sprint 3.5 added upsert_satellite_seen + upsert_channel_seen calls to
    # CSVConnector.bulk_load_to_db().  Auto-mock them so these unit tests
    # stay DB-free without modifying every individual test.
    @pytest.fixture(autouse=True)
    def _mock_upserts(self):
        with (
            patch("aria.dsremo.ingest.csv_connector.queries.upsert_satellite_seen",
                  new_callable=AsyncMock),
            patch("aria.dsremo.ingest.csv_connector.queries.upsert_channel_seen",
                  new_callable=AsyncMock),
        ):
            yield

    async def test_inserts_two_columns(self, tmp_path):
        f = _make_csv(tmp_path, """
            timestamp,voltage,current
            2024-01-01T00:00:00Z,3.3,1.2
            2024-01-01T00:01:00Z,3.4,1.3
        """)
        with (
            patch("aria.dsremo.ingest.csv_connector.check_channel_row_count", new_callable=AsyncMock) as mock_check,
            patch("aria.dsremo.ingest.csv_connector.bulk_insert_channel", new_callable=AsyncMock) as mock_insert,
        ):
            mock_check.return_value = 0
            mock_insert.return_value = 2
            totals = await CSVConnector(f, "SAT-1").bulk_load_to_db()

        assert set(totals.keys()) == {"voltage", "current"}
        assert totals["voltage"] == 2
        assert totals["current"] == 2
        assert mock_insert.call_count == 2

    async def test_skips_channel_when_rows_gte_threshold(self, tmp_path):
        f = _make_csv(tmp_path, """
            timestamp,voltage,current
            2024-01-01T00:00:00Z,3.3,1.2
        """)
        with (
            patch("aria.dsremo.ingest.csv_connector.check_channel_row_count", new_callable=AsyncMock) as mock_check,
            patch("aria.dsremo.ingest.csv_connector.bulk_insert_channel", new_callable=AsyncMock) as mock_insert,
        ):
            mock_check.return_value = 60_000   # above default 50_000
            totals = await CSVConnector(f, "SAT-1").bulk_load_to_db()

        assert mock_insert.call_count == 0
        assert totals["voltage"] == 60_000
        assert totals["current"] == 60_000

    async def test_partial_skip(self, tmp_path):
        """First column already loaded, second is new."""
        f = _make_csv(tmp_path, """
            timestamp,voltage,current
            2024-01-01T00:00:00Z,3.3,1.2
        """)
        def check_side_effect(satellite_id: str, param: str) -> int:
            return 60_000 if param == "voltage" else 0

        with (
            patch("aria.dsremo.ingest.csv_connector.check_channel_row_count",
                  side_effect=check_side_effect),
            patch("aria.dsremo.ingest.csv_connector.bulk_insert_channel",
                  new_callable=AsyncMock) as mock_insert,
        ):
            mock_insert.return_value = 1
            totals = await CSVConnector(f, "SAT-1").bulk_load_to_db()

        assert mock_insert.call_count == 1
        assert totals["voltage"] == 60_000
        assert totals["current"] == 1

    async def test_nan_rows_dropped(self, tmp_path):
        f = _make_csv(tmp_path, """
            timestamp,voltage
            2024-01-01T00:00:00Z,3.3
            2024-01-01T00:01:00Z,
            2024-01-01T00:02:00Z,3.5
        """)
        captured_series: list[pd.Series] = []

        async def fake_insert(**kwargs):
            captured_series.append(kwargs["series"])
            return len(kwargs["series"])

        with (
            patch("aria.dsremo.ingest.csv_connector.check_channel_row_count", new_callable=AsyncMock) as mock_check,
            patch("aria.dsremo.ingest.csv_connector.bulk_insert_channel", side_effect=fake_insert),
        ):
            mock_check.return_value = 0
            totals = await CSVConnector(f, "SAT-1").bulk_load_to_db()

        # 1 NaN row dropped → only 2 inserted
        assert totals["voltage"] == 2
        assert len(captured_series[0]) == 2

    async def test_naive_timestamps_localized_to_utc(self, tmp_path):
        f = _make_csv(tmp_path, """
            timestamp,voltage
            2024-01-01 00:00:00,3.3
            2024-01-01 00:01:00,3.4
        """)
        captured_series: list[pd.Series] = []

        async def fake_insert(**kwargs):
            captured_series.append(kwargs["series"])
            return len(kwargs["series"])

        with (
            patch("aria.dsremo.ingest.csv_connector.check_channel_row_count", new_callable=AsyncMock) as mock_check,
            patch("aria.dsremo.ingest.csv_connector.bulk_insert_channel", side_effect=fake_insert),
        ):
            mock_check.return_value = 0
            await CSVConnector(f, "SAT-1").bulk_load_to_db()

        assert captured_series[0].index.tz is not None
        assert str(captured_series[0].index.tz) == "UTC"

    async def test_resample_reduces_rows(self, tmp_path):
        rows = "\n".join(
            f"2024-01-01T{h:02d}:{m:02d}:00Z,{h + m * 0.01:.2f}"
            for h in range(2)
            for m in range(60)
        )
        f = _make_csv(tmp_path, f"timestamp,voltage\n{rows}")
        captured_series: list[pd.Series] = []

        async def fake_insert(**kwargs):
            captured_series.append(kwargs["series"])
            return len(kwargs["series"])

        with (
            patch("aria.dsremo.ingest.csv_connector.check_channel_row_count", new_callable=AsyncMock) as mock_check,
            patch("aria.dsremo.ingest.csv_connector.bulk_insert_channel", side_effect=fake_insert),
        ):
            mock_check.return_value = 0
            # 120 1-min rows → 24 rows at 5-min resolution
            await CSVConnector(f, "SAT-1").bulk_load_to_db(resample_minutes=5)

        # 120 minutes / 5-min bins = 24 buckets
        assert len(captured_series[0]) == 24

    async def test_empty_csv_returns_empty_dict(self, tmp_path):
        f = _make_csv(tmp_path, "timestamp,voltage\n")
        with (
            patch("aria.dsremo.ingest.csv_connector.check_channel_row_count", new_callable=AsyncMock),
            patch("aria.dsremo.ingest.csv_connector.bulk_insert_channel", new_callable=AsyncMock),
        ):
            totals = await CSVConnector(f, "SAT-1").bulk_load_to_db()
        assert totals == {}

    async def test_custom_timestamp_col(self, tmp_path):
        f = _make_csv(tmp_path, """
            time,voltage
            2024-01-01T00:00:00Z,3.3
        """)
        with (
            patch("aria.dsremo.ingest.csv_connector.check_channel_row_count", new_callable=AsyncMock) as mock_check,
            patch("aria.dsremo.ingest.csv_connector.bulk_insert_channel", new_callable=AsyncMock) as mock_insert,
        ):
            mock_check.return_value = 0
            mock_insert.return_value = 1
            totals = await CSVConnector(f, "SAT-1", timestamp_col="time").bulk_load_to_db()

        assert "voltage" in totals
        assert "time" not in totals   # timestamp col must not appear as a parameter

    async def test_subsystem_passed_to_insert(self, tmp_path):
        f = _make_csv(tmp_path, """
            timestamp,current
            2024-01-01T00:00:00Z,1.5
        """)
        calls: list[dict] = []

        async def fake_insert(**kwargs):
            calls.append(kwargs)
            return 1

        with (
            patch("aria.dsremo.ingest.csv_connector.check_channel_row_count", new_callable=AsyncMock) as mock_check,
            patch("aria.dsremo.ingest.csv_connector.bulk_insert_channel", side_effect=fake_insert),
        ):
            mock_check.return_value = 0
            await CSVConnector(f, "SAT-1", subsystem="eps").bulk_load_to_db()

        assert calls[0]["subsystem"] == "eps"
        assert calls[0]["satellite_id"] == "SAT-1"
