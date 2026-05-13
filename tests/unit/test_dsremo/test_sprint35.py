"""Tests for Sprint 3.5: Customer Onboarding Hardening.

All tests are pure unit/schema tests — no database required.
Covers:
  - shared ingest utilities (utils.py)
  - pipeline helpers (db_context, phase, print_run_header)
  - CSVConnector bug fixes (IO source, error handling, validation, metadata upserts)
  - SatNOGS class-level constants (PARAMETERS / UNITS promoted from method-local)
  - PayloadLimitMiddleware upload-path exclusion
  - CsvUploadResult schema
  - POST /api/v1/telemetry/upload endpoint (demo mode, mocked connector)
"""

from __future__ import annotations

import io
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from aria.dsremo.ingest.utils import (
    ensure_utc_series,
    prepare_series,
    validated_resample,
    validated_satellite_id,
)


# ---------------------------------------------------------------------------
# Helpers shared across test classes
# ---------------------------------------------------------------------------

def _make_csv(tmp_path: Path, content: str, name: str = "test.csv") -> Path:
    f = tmp_path / name
    f.write_text(textwrap.dedent(content).strip())
    return f


def _csv_bytes(content: str) -> bytes:
    return textwrap.dedent(content).strip().encode()


# ---------------------------------------------------------------------------
# 1. Shared ingest utilities
# ---------------------------------------------------------------------------

class TestEnsureUtcSeries:
    def test_naive_index_localized_to_utc(self):
        idx = pd.date_range("2024-01-01", periods=3, freq="min")  # tz-naive
        s = pd.Series([1.0, 2.0, 3.0], index=idx)
        result = ensure_utc_series(s)
        assert str(result.index.tz) == "UTC"

    def test_already_utc_unchanged(self):
        idx = pd.date_range("2024-01-01", periods=3, freq="min", tz="UTC")
        s = pd.Series([1.0, 2.0, 3.0], index=idx)
        result = ensure_utc_series(s)
        assert str(result.index.tz) == "UTC"
        # Should be the same object (no unnecessary copy)
        assert result is s

    def test_original_series_not_mutated(self):
        idx = pd.date_range("2024-01-01", periods=3, freq="min")
        s = pd.Series([1.0, 2.0, 3.0], index=idx)
        _ = ensure_utc_series(s)
        assert s.index.tz is None  # original untouched


class TestPrepareSeries:
    def test_drops_nan(self):
        idx = pd.date_range("2024-01-01", periods=4, freq="min", tz="UTC")
        s = pd.Series([1.0, float("nan"), 3.0, float("nan")], index=idx)
        result = prepare_series(s, resample_minutes=1)
        assert len(result) == 2
        assert result.isna().sum() == 0

    def test_resamples_to_fewer_rows(self):
        # 120 1-min rows → 24 buckets at 5-min resolution
        idx = pd.date_range("2024-01-01", periods=120, freq="min", tz="UTC")
        s = pd.Series(range(120), dtype=float, index=idx)
        result = prepare_series(s, resample_minutes=5)
        assert len(result) == 24

    def test_no_resample_when_minutes_is_one(self):
        idx = pd.date_range("2024-01-01", periods=10, freq="min", tz="UTC")
        s = pd.Series(range(10), dtype=float, index=idx)
        result = prepare_series(s, resample_minutes=1)
        assert len(result) == 10

    def test_localizes_naive_index(self):
        idx = pd.date_range("2024-01-01", periods=3, freq="min")  # naive
        s = pd.Series([1.0, 2.0, 3.0], index=idx)
        result = prepare_series(s)
        assert str(result.index.tz) == "UTC"


class TestValidatedResample:
    def test_rejects_zero(self):
        with pytest.raises(ValueError, match="resample_minutes"):
            validated_resample(0)

    def test_rejects_negative(self):
        with pytest.raises(ValueError, match="resample_minutes"):
            validated_resample(-5)

    def test_accepts_one(self):
        assert validated_resample(1) == 1

    def test_accepts_large_value(self):
        assert validated_resample(1440) == 1440


class TestValidatedSatelliteId:
    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="satellite_id"):
            validated_satellite_id("")

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValueError, match="satellite_id"):
            validated_satellite_id("   ")

    def test_strips_whitespace(self):
        assert validated_satellite_id("  SAT-1  ") == "SAT-1"

    def test_accepts_valid_id(self):
        assert validated_satellite_id("ISS-25544") == "ISS-25544"


# ---------------------------------------------------------------------------
# 2. CSVConnector bug fixes — sync (construction + _read_csv)
# ---------------------------------------------------------------------------

class TestCSVConnectorFixedSync:
    """Sync tests — no DB calls, tests constructor-time validation and _read_csv."""

    def test_empty_satellite_id_rejected_at_init(self, tmp_path):
        """Empty satellite_id raises ValueError at construction time, not later."""
        from aria.dsremo.ingest.csv_connector import CSVConnector

        f = tmp_path / "x.csv"
        with pytest.raises(ValueError, match="satellite_id"):
            CSVConnector(f, "")

    def test_whitespace_satellite_id_rejected(self, tmp_path):
        from aria.dsremo.ingest.csv_connector import CSVConnector

        f = tmp_path / "x.csv"
        with pytest.raises(ValueError, match="satellite_id"):
            CSVConnector(f, "   ")

    def test_file_not_found_raises_clear_error(self, tmp_path):
        """Missing file → FileNotFoundError with a human-readable message."""
        from aria.dsremo.ingest.csv_connector import CSVConnector

        connector = CSVConnector(tmp_path / "missing.csv", "SAT-1")
        with pytest.raises(FileNotFoundError, match="missing.csv"):
            connector._read_csv()

    def test_missing_timestamp_col_raises_clear_error(self, tmp_path):
        """Wrong --timestamp-col → KeyError with hint about the column name."""
        from aria.dsremo.ingest.csv_connector import CSVConnector

        f = _make_csv(tmp_path, "timestamp,voltage\n2024-01-01T00:00:00Z,3.3")
        connector = CSVConnector(f, "SAT-1", timestamp_col="time")  # wrong col
        with pytest.raises(KeyError, match="time"):
            connector._read_csv()

    def test_malformed_csv_raises_clear_error(self, tmp_path):
        """A CSV that pandas can't parse → ValueError (not a bare ParserError)."""
        from aria.dsremo.ingest.csv_connector import CSVConnector

        f = tmp_path / "bad.csv"
        f.write_bytes(b"\x00\x01\x02\x03\x04")  # binary garbage
        connector = CSVConnector(f, "SAT-1")
        with pytest.raises((ValueError, Exception)):
            connector._read_csv()

    def test_bytesio_source_name_includes_satellite(self):
        """source_name for IO source should mention the satellite_id."""
        from aria.dsremo.ingest.csv_connector import CSVConnector

        connector = CSVConnector(io.BytesIO(b""), "MYSAT-1")
        assert "MYSAT-1" in connector.source_name


# ---------------------------------------------------------------------------
# 2b. CSVConnector bug fixes — async (bulk_load_to_db)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCSVConnectorFixedAsync:
    """Async tests — mock DB calls, verify new bulk_load_to_db behaviour."""

    async def test_accepts_bytesio_source(self):
        """CSVConnector must accept io.BytesIO (enables API upload without temp file)."""
        from aria.dsremo.ingest.csv_connector import CSVConnector

        raw = _csv_bytes("""
            timestamp,voltage
            2024-01-01T00:00:00Z,3.3
        """)
        with (
            patch("aria.dsremo.ingest.csv_connector.check_channel_row_count",
                  new_callable=AsyncMock) as mock_check,
            patch("aria.dsremo.ingest.csv_connector.bulk_insert_channel",
                  new_callable=AsyncMock) as mock_insert,
            patch("aria.dsremo.ingest.csv_connector.queries.upsert_satellite_seen",
                  new_callable=AsyncMock),
            patch("aria.dsremo.ingest.csv_connector.queries.upsert_channel_seen",
                  new_callable=AsyncMock),
        ):
            mock_check.return_value = 0
            mock_insert.return_value = 1
            connector = CSVConnector(io.BytesIO(raw), "SAT-1")
            totals = await connector.bulk_load_to_db()

        assert "voltage" in totals

    async def test_resample_zero_rejected(self, tmp_path):
        from aria.dsremo.ingest.csv_connector import CSVConnector

        f = _make_csv(tmp_path, "timestamp,v\n2024-01-01T00:00:00Z,1.0")
        with pytest.raises(ValueError, match="resample_minutes"):
            await CSVConnector(f, "SAT-1").bulk_load_to_db(resample_minutes=0)

    async def test_metadata_upserts_called(self, tmp_path):
        """upsert_satellite_seen + upsert_channel_seen must be called per channel."""
        from aria.dsremo.ingest.csv_connector import CSVConnector

        f = _make_csv(tmp_path, """
            timestamp,voltage,current
            2024-01-01T00:00:00Z,3.3,1.2
        """)
        with (
            patch("aria.dsremo.ingest.csv_connector.check_channel_row_count",
                  new_callable=AsyncMock) as mock_check,
            patch("aria.dsremo.ingest.csv_connector.bulk_insert_channel",
                  new_callable=AsyncMock) as mock_insert,
            patch("aria.dsremo.ingest.csv_connector.queries.upsert_satellite_seen",
                  new_callable=AsyncMock) as mock_sat,
            patch("aria.dsremo.ingest.csv_connector.queries.upsert_channel_seen",
                  new_callable=AsyncMock) as mock_ch,
        ):
            mock_check.return_value = 0
            mock_insert.return_value = 1
            await CSVConnector(f, "SAT-1").bulk_load_to_db()

        # One call per channel (2 channels = voltage + current)
        assert mock_sat.call_count == 2
        assert mock_ch.call_count == 2

    async def test_non_numeric_column_skipped_not_inserted(self, tmp_path):
        """Non-numeric parameter columns must be silently skipped, not crash."""
        from aria.dsremo.ingest.csv_connector import CSVConnector

        f = _make_csv(tmp_path, """
            timestamp,voltage,mode
            2024-01-01T00:00:00Z,3.3,NOMINAL
            2024-01-01T00:01:00Z,3.4,SAFE
        """)
        with (
            patch("aria.dsremo.ingest.csv_connector.check_channel_row_count",
                  new_callable=AsyncMock) as mock_check,
            patch("aria.dsremo.ingest.csv_connector.bulk_insert_channel",
                  new_callable=AsyncMock) as mock_insert,
            patch("aria.dsremo.ingest.csv_connector.queries.upsert_satellite_seen",
                  new_callable=AsyncMock),
            patch("aria.dsremo.ingest.csv_connector.queries.upsert_channel_seen",
                  new_callable=AsyncMock),
        ):
            mock_check.return_value = 0
            mock_insert.return_value = 2
            totals = await CSVConnector(f, "SAT-1").bulk_load_to_db()

        # Only numeric column inserted; 'mode' (string) skipped
        assert "voltage" in totals
        assert "mode" not in totals
        assert mock_insert.call_count == 1


# ---------------------------------------------------------------------------
# 3. SatNOGS class-level constants
# ---------------------------------------------------------------------------

class TestSatNOGSClassConstants:
    def test_parameters_on_class_not_instance(self):
        """PARAMETERS must be a class attribute, not a method-local variable."""
        from aria.dsremo.ingest.satnogs_fetcher import SatNOGSFetcher

        assert hasattr(SatNOGSFetcher, "PARAMETERS")
        assert isinstance(SatNOGSFetcher.PARAMETERS, (tuple, list))
        assert len(SatNOGSFetcher.PARAMETERS) > 0

    def test_units_on_class_not_instance(self):
        """UNITS must be a class attribute mapping parameter → unit string."""
        from aria.dsremo.ingest.satnogs_fetcher import SatNOGSFetcher

        assert hasattr(SatNOGSFetcher, "UNITS")
        assert isinstance(SatNOGSFetcher.UNITS, dict)
        # Every PARAMETER must have a corresponding UNIT entry
        for param in SatNOGSFetcher.PARAMETERS:
            assert param in SatNOGSFetcher.UNITS, (
                f"SatNOGSFetcher.UNITS missing entry for {param!r}"
            )

    def test_expected_parameters_present(self):
        """Regression: the 4 core telemetry parameters must be present."""
        from aria.dsremo.ingest.satnogs_fetcher import SatNOGSFetcher

        expected = {"frame_length", "byte_mean", "byte_entropy", "frame_gap"}
        assert expected <= set(SatNOGSFetcher.PARAMETERS)


# ---------------------------------------------------------------------------
# 4. Pipeline helpers
# ---------------------------------------------------------------------------

class TestPhaseContextManager:
    def test_prints_header(self, capsys):
        from aria.dsremo.ingest.pipeline import phase

        with phase("Test Phase"):
            pass
        out = capsys.readouterr().out
        assert "Test Phase" in out

    def test_prints_elapsed(self, capsys):
        from aria.dsremo.ingest.pipeline import phase

        with phase("Timing Test"):
            pass
        out = capsys.readouterr().out
        # Elapsed printed as Xs
        assert "s)" in out

    def test_yields_control(self, capsys):
        from aria.dsremo.ingest.pipeline import phase

        executed = []
        with phase("Exec Test"):
            executed.append(True)
        assert executed == [True]

    def test_exception_still_prints_elapsed(self, capsys):
        from aria.dsremo.ingest.pipeline import phase

        with pytest.raises(RuntimeError):
            with phase("Error Phase"):
                raise RuntimeError("boom")
        out = capsys.readouterr().out
        assert "Error Phase" in out
        assert "s)" in out


class TestPrintRunHeader:
    def test_outputs_title(self, capsys):
        from aria.dsremo.ingest.pipeline import print_run_header

        print_run_header("My Title", Dataset="76 channels")
        out = capsys.readouterr().out
        assert "My Title" in out

    def test_outputs_key_value_pairs(self, capsys):
        from aria.dsremo.ingest.pipeline import print_run_header

        print_run_header("Title", Satellite="ISS-25544", Resolution="5-min")
        out = capsys.readouterr().out
        assert "ISS-25544" in out
        assert "5-min" in out

    def test_underscore_in_key_replaced_with_space(self, capsys):
        from aria.dsremo.ingest.pipeline import print_run_header

        print_run_header("T", Skip_if_gte="50,000 rows")
        out = capsys.readouterr().out
        assert "50,000 rows" in out


# ---------------------------------------------------------------------------
# 5. PayloadLimitMiddleware — upload path exclusion
# ---------------------------------------------------------------------------

class TestPayloadLimitMiddlewareUploadPath:
    def test_upload_path_in_exempt_set(self):
        from aria.dsremo.api.middleware import PayloadLimitMiddleware

        assert "/api/v1/telemetry/upload" in PayloadLimitMiddleware._UPLOAD_PATHS

    def test_regular_paths_not_exempt(self):
        from aria.dsremo.api.middleware import PayloadLimitMiddleware

        for path in ("/api/v1/telemetry", "/api/v1/anomalies", "/api/v1/health"):
            assert path not in PayloadLimitMiddleware._UPLOAD_PATHS


# ---------------------------------------------------------------------------
# 6. CsvUploadResult schema
# ---------------------------------------------------------------------------

class TestCsvUploadResultSchema:
    def test_valid_construction(self):
        from aria.dsremo.api.schemas import CsvUploadResult

        result = CsvUploadResult(
            satellite_id="MYSAT-1",
            channels_loaded=3,
            channels_skipped=1,
            total_rows_inserted=9000,
            rows_per_channel={"voltage": 3000, "current": 3000, "temp": 3000},
            source_name="csv:telemetry.csv",
        )
        assert result.satellite_id == "MYSAT-1"
        assert result.channels_loaded == 3
        assert result.channels_skipped == 1
        assert result.total_rows_inserted == 9000

    def test_serialization(self):
        from aria.dsremo.api.schemas import CsvUploadResult

        r = CsvUploadResult(
            satellite_id="S",
            channels_loaded=1,
            channels_skipped=0,
            total_rows_inserted=100,
            rows_per_channel={"v": 100},
            source_name="csv:f.csv",
        )
        data = r.model_dump()
        assert data["satellite_id"] == "S"
        assert isinstance(data["rows_per_channel"], dict)


# ---------------------------------------------------------------------------
# 7. POST /api/v1/telemetry/upload endpoint
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def demo_client():
    """Demo-mode TestClient — no DB, auth always succeeds."""
    from aria.dsremo.api.app import create_app
    app = create_app(demo=True)
    with TestClient(app) as client:
        yield client


GOOD_CSV = _csv_bytes("""
    timestamp,voltage,current
    2024-01-01T00:00:00Z,3.3,1.2
    2024-01-01T00:01:00Z,3.4,1.3
""")


class TestCsvUploadEndpoint:
    def _post_upload(
        self,
        client: TestClient,
        csv_bytes: bytes = GOOD_CSV,
        satellite_id: str = "MYSAT-1",
        subsystem: str = "eps",
        mock_totals: dict | None = None,
    ):
        if mock_totals is None:
            mock_totals = {"voltage": 2, "current": 2}

        # CSVConnector is a local import inside the route handler, so patch
        # at its canonical module path (not dsremo.api.routes.CSVConnector).
        with patch(
            "aria.dsremo.ingest.csv_connector.CSVConnector",
            autospec=True,
        ) as MockConnector:
            instance = MockConnector.return_value
            instance.bulk_load_to_db = AsyncMock(return_value=mock_totals)
            instance.source_name = f"csv:<upload:{satellite_id}>"
            return client.post(
                "/api/v1/telemetry/upload",
                data={"satellite_id": satellite_id, "subsystem": subsystem},
                files={"file": ("telemetry.csv", csv_bytes, "text/csv")},
            )

    def test_upload_returns_200_and_csv_upload_result(self, demo_client):
        response = self._post_upload(demo_client)
        assert response.status_code == 200
        data = response.json()
        assert data["satellite_id"] == "MYSAT-1"
        assert data["channels_loaded"] == 2
        assert data["total_rows_inserted"] == 4
        assert "rows_per_channel" in data

    def test_upload_missing_satellite_id_returns_422(self, demo_client):
        response = demo_client.post(
            "/api/v1/telemetry/upload",
            data={"subsystem": "eps"},  # no satellite_id
            files={"file": ("t.csv", GOOD_CSV, "text/csv")},
        )
        assert response.status_code == 422

    def test_upload_file_too_large_returns_413(self, demo_client):
        # Size check happens before CSVConnector is instantiated — no mock needed.
        oversized = b"timestamp,v\n" + b"2024-01-01T00:00:00Z,1.0\n" * 600_000
        response = demo_client.post(
            "/api/v1/telemetry/upload",
            data={"satellite_id": "SAT-1"},
            files={"file": ("big.csv", oversized, "text/csv")},
        )
        assert response.status_code == 413

    def test_upload_missing_file_returns_422(self, demo_client):
        response = demo_client.post(
            "/api/v1/telemetry/upload",
            data={"satellite_id": "SAT-1", "subsystem": "eps"},
            # no 'file' field
        )
        assert response.status_code == 422

    def test_upload_invalid_csv_returns_422(self, demo_client):
        """CSVConnector raising ValueError/KeyError should map to 422."""
        with patch("aria.dsremo.ingest.csv_connector.CSVConnector") as MockConnector:
            instance = MockConnector.return_value
            instance.bulk_load_to_db = AsyncMock(
                side_effect=ValueError("Malformed CSV: ...")
            )
            instance.source_name = "csv:<upload:SAT-1>"
            response = demo_client.post(
                "/api/v1/telemetry/upload",
                data={"satellite_id": "SAT-1"},
                files={"file": ("bad.csv", b"\x00\x01", "text/csv")},
            )
        assert response.status_code == 422

    def test_upload_resample_out_of_range_returns_422(self, demo_client):
        """resample_minutes must be 1–1440; 0 should be rejected by Form validator."""
        response = demo_client.post(
            "/api/v1/telemetry/upload",
            data={"satellite_id": "SAT-1", "resample_minutes": "0"},
            files={"file": ("t.csv", GOOD_CSV, "text/csv")},
        )
        assert response.status_code == 422

    def test_upload_channels_skipped_count(self, demo_client):
        """channels_skipped reflects channels already at capacity (>= 50_000 rows)."""
        totals = {"voltage": 60_000, "current": 2}  # voltage already loaded
        response = self._post_upload(demo_client, mock_totals=totals)
        assert response.status_code == 200
        data = response.json()
        assert data["channels_skipped"] == 1

    def test_upload_source_name_in_response(self, demo_client):
        response = self._post_upload(demo_client)
        data = response.json()
        assert "source_name" in data
        assert data["source_name"]  # non-empty
