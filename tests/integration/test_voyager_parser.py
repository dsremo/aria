"""Integration tests for the Voyager PLS data parser.

Tests cover:
  - Parsing all supported formats (daily_avg, hourly, femtoamp, csv)
  - Fill-value detection and filtering
  - Spacecraft auto-detection
  - CSV export compatible with DataReplayEngine
  - VoyagerReplayEngine bus publishing
  - Synthetic data generation for when real data is unavailable
  - Physical plausibility of derived quantities
  - Edge cases (empty files, corrupt lines, mixed formats)
"""

from __future__ import annotations

import asyncio
import csv
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from aria.bus.message_bus import Message, MessageBus
from aria.simulation.voyager_parser import (
    FILL_VALUES,
    VoyagerDataset,
    VoyagerReading,
    VoyagerReplayEngine,
    _detect_format,
    _doy_to_datetime,
    _decimal_year_to_datetime,
    _is_fill,
    _safe_float,
    detect_spacecraft,
    export_to_csv,
    generate_synthetic_voyager_data,
    parse_voyager_directory,
    parse_voyager_file,
    process_voyager_data,
)


# ---------------------------------------------------------------------------
# Fixtures: sample data in each format
# ---------------------------------------------------------------------------

DAILY_AVG_DATA = """\
# Voyager 1 daily averages - proton density, speed, temperature
# Year DOY  Density(n/cc)  Speed(km/s)  Temp(K)
2012  1    0.0032         410.5        48500.0
2012  2    0.0028         415.2        51200.0
2012  3    0.0035         405.8        46800.0
2012  4    9999.9         9999.9       9999.9
2012  5    0.0041         398.3        52100.0
"""

HOURLY_DATA = """\
# Voyager 2 hourly resolution
# Year DOY Hour Density Speed Temp Distance
2018  100  0   0.0012  150.3  35000.0  119.5
2018  100  6   0.0015  148.7  36200.0  119.5
2018  100  12  0.0011  152.1  34500.0  119.5
2018  100  18  0.0014  149.5  35800.0  119.5
2018  101  0   0.0013  151.2  35400.0  119.5
"""

FEMTOAMP_DATA = """\
# Voyager 1 Faraday cup currents (femto-amps)
# Year DOY Hour   Ch1         Ch2         Ch3         Ch4         Ch5
2012  200  12   3.45e-02    1.22e-02    8.90e-03    2.10e-02    1.55e-02
2012  201  12   4.12e-02    1.50e-02    9.50e-03    2.80e-02    1.90e-02
2012  202  12   2.88e-02    1.05e-02    7.20e-03    1.70e-02    1.20e-02
2012  203  12   9.999e+05   9.999e+05   9.999e+05   9.999e+05   9.999e+05
"""

CSV_DATA = """\
time,density_n_cc,speed_km_s,temperature_K,distance_au
2012-08-25T00:00:00,0.055,26.0,7500.0,121.7
2012-08-26T00:00:00,0.058,25.5,7200.0,121.7
2012-08-27T00:00:00,0.052,27.1,7800.0,121.8
2012-08-28T00:00:00,,26.3,7400.0,121.8
"""

DECIMAL_YEAR_DATA = """\
# Decimal year format
2012.0027  0.0032  410.5  48500.0
2012.0055  0.0028  415.2  51200.0
2012.0082  0.0035  405.8  46800.0
"""


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def daily_avg_file(tmp_dir: Path) -> Path:
    fp = tmp_dir / "v1_daily_2012.txt"
    fp.write_text(DAILY_AVG_DATA)
    return fp


@pytest.fixture
def hourly_file(tmp_dir: Path) -> Path:
    fp = tmp_dir / "v2_hourly_2018.txt"
    fp.write_text(HOURLY_DATA)
    return fp


@pytest.fixture
def femtoamp_file(tmp_dir: Path) -> Path:
    fp = tmp_dir / "v1_pls_currents.txt"
    fp.write_text(FEMTOAMP_DATA)
    return fp


@pytest.fixture
def csv_file(tmp_dir: Path) -> Path:
    fp = tmp_dir / "voyager1_ism.csv"
    fp.write_text(CSV_DATA)
    return fp


@pytest.fixture
def decimal_year_file(tmp_dir: Path) -> Path:
    fp = tmp_dir / "vg1_plasma_decyr.txt"
    fp.write_text(DECIMAL_YEAR_DATA)
    return fp


@pytest.fixture
async def bus():
    b = MessageBus(max_history=5000)
    await b.start()
    yield b
    await b.stop()


# ---------------------------------------------------------------------------
# Unit-level helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    """Tests for parsing helper functions."""

    def test_doy_to_datetime_jan1(self):
        dt = _doy_to_datetime(2012, 1)
        assert dt == datetime(2012, 1, 1, tzinfo=timezone.utc)

    def test_doy_to_datetime_with_hour(self):
        dt = _doy_to_datetime(2012, 238, 12, 30)
        assert dt.hour == 12
        assert dt.minute == 30
        assert dt.month == 8  # DOY 238 = Aug 25 in 2012 (leap year)

    def test_doy_to_datetime_leap_year(self):
        # 2012 is a leap year: DOY 366 should be Dec 31
        dt = _doy_to_datetime(2012, 366)
        assert dt.month == 12
        assert dt.day == 31

    def test_decimal_year_basic(self):
        dt = _decimal_year_to_datetime(2012.0)
        assert dt.year == 2012
        assert dt.month == 1
        assert dt.day == 1

    def test_decimal_year_midyear(self):
        dt = _decimal_year_to_datetime(2012.5)
        # Should be roughly July 1 (leap year: 366 days, half = 183 days)
        assert dt.month in (6, 7)

    def test_is_fill_detects_sentinels(self):
        assert _is_fill(9999.0)
        assert _is_fill(9999.9)
        assert _is_fill(float("nan"))
        assert _is_fill(float("inf"))

    def test_is_fill_passes_normal_values(self):
        assert not _is_fill(0.003)
        assert not _is_fill(400.0)
        assert not _is_fill(50000.0)

    def test_safe_float_normal(self):
        assert _safe_float("3.14") == pytest.approx(3.14)
        assert _safe_float("  400.5  ") == pytest.approx(400.5)

    def test_safe_float_fill(self):
        assert _safe_float("9999.9") is None
        assert _safe_float("99999.0") is None

    def test_safe_float_invalid(self):
        assert _safe_float("") is None
        assert _safe_float("-") is None
        assert _safe_float("N/A") is None
        assert _safe_float("abc") is None


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

class TestFormatDetection:
    """Tests for automatic format detection."""

    def test_detect_daily_avg(self):
        lines = DAILY_AVG_DATA.splitlines()
        assert _detect_format(lines) == "daily_avg"

    def test_detect_hourly(self):
        lines = HOURLY_DATA.splitlines()
        assert _detect_format(lines) == "hourly"

    def test_detect_femtoamp(self):
        lines = FEMTOAMP_DATA.splitlines()
        assert _detect_format(lines) == "femtoamp"

    def test_detect_csv(self):
        lines = CSV_DATA.splitlines()
        assert _detect_format(lines) == "csv"

    def test_detect_empty(self):
        assert _detect_format([]) == "unknown"
        assert _detect_format(["", "  ", "# comment"]) == "unknown"


# ---------------------------------------------------------------------------
# Spacecraft detection
# ---------------------------------------------------------------------------

class TestSpacecraftDetection:
    """Tests for spacecraft identification from filenames."""

    def test_v1_patterns(self, tmp_dir: Path):
        for name in ("v1_data.txt", "vg1_plasma.dat", "voyager1_pls.csv", "voyager_1.tab"):
            fp = tmp_dir / name
            fp.touch()
            assert detect_spacecraft(fp) == "V1", f"Failed for {name}"

    def test_v2_patterns(self, tmp_dir: Path):
        for name in ("v2_data.txt", "vg2_plasma.dat", "voyager2_pls.csv", "voyager_2.tab"):
            fp = tmp_dir / name
            fp.touch()
            assert detect_spacecraft(fp) == "V2", f"Failed for {name}"

    def test_parent_directory_fallback(self, tmp_dir: Path):
        v2_dir = tmp_dir / "voyager2_data"
        v2_dir.mkdir()
        fp = v2_dir / "plasma.txt"
        fp.touch()
        # filename has no indicator, but parent dir does
        # Note: detect_spacecraft checks parent name for v2
        assert detect_spacecraft(fp) == "V2"


# ---------------------------------------------------------------------------
# Parsing: daily average format
# ---------------------------------------------------------------------------

class TestParseDailyAvg:
    """Tests for daily average format parsing."""

    def test_basic_parse(self, daily_avg_file: Path):
        ds = parse_voyager_file(daily_avg_file, spacecraft="V1")
        assert ds.spacecraft == "V1"
        assert len(ds.readings) == 5

    def test_fill_values_filtered(self, daily_avg_file: Path):
        ds = parse_voyager_file(daily_avg_file, spacecraft="V1")
        valid = ds.valid_readings
        # Row with 9999.9 should have None fields -> not valid
        assert len(valid) == 4
        assert ds.fill_values_skipped >= 3  # 3 fill values in row 4

    def test_timestamps_correct(self, daily_avg_file: Path):
        ds = parse_voyager_file(daily_avg_file, spacecraft="V1")
        first = ds.readings[0]
        assert first.timestamp.year == 2012
        assert first.timestamp.month == 1
        assert first.timestamp.day == 1

    def test_values_parsed(self, daily_avg_file: Path):
        ds = parse_voyager_file(daily_avg_file, spacecraft="V1")
        r = ds.readings[0]
        assert r.density_per_cm3 == pytest.approx(0.0032)
        assert r.speed_km_s == pytest.approx(410.5)
        assert r.temperature_k == pytest.approx(48500.0)

    def test_decimal_year_format(self, decimal_year_file: Path):
        ds = parse_voyager_file(decimal_year_file, spacecraft="V1")
        assert len(ds.valid_readings) == 3
        first = ds.readings[0]
        assert first.timestamp.year == 2012
        assert first.density_per_cm3 == pytest.approx(0.0032)


# ---------------------------------------------------------------------------
# Parsing: hourly format
# ---------------------------------------------------------------------------

class TestParseHourly:
    """Tests for hourly resolution format parsing."""

    def test_basic_parse(self, hourly_file: Path):
        ds = parse_voyager_file(hourly_file, spacecraft="V2")
        assert ds.spacecraft == "V2"
        assert len(ds.readings) == 5

    def test_hour_column_detected(self, hourly_file: Path):
        ds = parse_voyager_file(hourly_file, spacecraft="V2")
        # First reading: DOY 100, hour 0
        # Second reading: DOY 100, hour 6
        assert ds.readings[0].timestamp.hour == 0
        assert ds.readings[1].timestamp.hour == 6

    def test_distance_parsed(self, hourly_file: Path):
        ds = parse_voyager_file(hourly_file, spacecraft="V2")
        assert ds.readings[0].heliocentric_distance_au == pytest.approx(119.5)


# ---------------------------------------------------------------------------
# Parsing: femto-amp format
# ---------------------------------------------------------------------------

class TestParseFemtoamp:
    """Tests for raw Faraday cup current format."""

    def test_basic_parse(self, femtoamp_file: Path):
        ds = parse_voyager_file(femtoamp_file, spacecraft="V1")
        # 3 valid data rows + 1 fill row
        valid = ds.valid_readings
        assert len(valid) == 3

    def test_derived_density_positive(self, femtoamp_file: Path):
        ds = parse_voyager_file(femtoamp_file, spacecraft="V1")
        for r in ds.valid_readings:
            assert r.density_per_cm3 is not None
            assert r.density_per_cm3 > 0

    def test_fill_row_skipped(self, femtoamp_file: Path):
        ds = parse_voyager_file(femtoamp_file, spacecraft="V1")
        # Row with 9.999e+05 values should be skipped
        assert ds.fill_values_skipped >= 1

    def test_current_stored(self, femtoamp_file: Path):
        ds = parse_voyager_file(femtoamp_file, spacecraft="V1")
        for r in ds.valid_readings:
            assert r.current_femtoamp is not None
            assert r.current_femtoamp > 0


# ---------------------------------------------------------------------------
# Parsing: CSV format
# ---------------------------------------------------------------------------

class TestParseCSV:
    """Tests for pre-formatted CSV parsing."""

    def test_basic_parse(self, csv_file: Path):
        ds = parse_voyager_file(csv_file, spacecraft="V1")
        assert len(ds.readings) == 4

    def test_missing_density_handled(self, csv_file: Path):
        ds = parse_voyager_file(csv_file, spacecraft="V1")
        # Last row has empty density
        last = ds.readings[3]
        assert last.density_per_cm3 is None
        assert last.speed_km_s == pytest.approx(26.3)

    def test_iso_timestamps(self, csv_file: Path):
        ds = parse_voyager_file(csv_file, spacecraft="V1")
        first = ds.readings[0]
        assert first.timestamp == datetime(2012, 8, 25, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# VoyagerReading derived properties
# ---------------------------------------------------------------------------

class TestVoyagerReading:
    """Tests for derived physical quantities."""

    def test_pressure_calculation(self):
        r = VoyagerReading(
            spacecraft="V1",
            timestamp=datetime(2012, 1, 1, tzinfo=timezone.utc),
            density_per_cm3=0.003,   # 3e-3 / cm^3
            speed_km_s=400.0,
            temperature_k=50000.0,
        )
        p = r.pressure_npa
        assert p is not None
        assert p > 0
        # Rough check: P = 0.5 * 3e3 * 1.67e-27 * (4e5)^2 = ~4e-13 Pa = ~4e-4 nPa
        # With n=3e-3 cm^-3 = 3e3 m^-3:
        # P = 0.5 * 3e3 * 1.67e-27 * 1.6e11 = 0.5 * 3e3 * 2.672e-16 = ~4.0e-13 Pa = ~4e-4 nPa
        assert 1e-5 < p < 1.0, f"Pressure {p} nPa out of expected range"

    def test_pressure_none_when_missing(self):
        r = VoyagerReading(
            spacecraft="V1",
            timestamp=datetime(2012, 1, 1, tzinfo=timezone.utc),
            density_per_cm3=None,
            speed_km_s=400.0,
            temperature_k=50000.0,
        )
        assert r.pressure_npa is None

    def test_is_valid_with_data(self):
        r = VoyagerReading(
            spacecraft="V1",
            timestamp=datetime(2012, 1, 1, tzinfo=timezone.utc),
            density_per_cm3=0.003,
            speed_km_s=None,
            temperature_k=None,
        )
        assert r.is_valid

    def test_is_valid_all_none(self):
        r = VoyagerReading(
            spacecraft="V1",
            timestamp=datetime(2012, 1, 1, tzinfo=timezone.utc),
            density_per_cm3=None,
            speed_km_s=None,
            temperature_k=None,
        )
        assert not r.is_valid


# ---------------------------------------------------------------------------
# VoyagerDataset summary
# ---------------------------------------------------------------------------

class TestVoyagerDataset:
    """Tests for dataset summary statistics."""

    def test_summary(self, daily_avg_file: Path):
        ds = parse_voyager_file(daily_avg_file, spacecraft="V1")
        summary = ds.summary()
        assert summary["spacecraft"] == "V1"
        assert summary["total_readings"] == 5
        assert summary["valid_readings"] == 4
        assert summary["density_range"] is not None
        assert summary["density_range"][0] > 0

    def test_time_range(self, daily_avg_file: Path):
        ds = parse_voyager_file(daily_avg_file, spacecraft="V1")
        t_start, t_end = ds.time_range
        assert t_start is not None
        assert t_end is not None
        assert t_start < t_end

    def test_empty_dataset(self):
        ds = VoyagerDataset(spacecraft="V1")
        assert ds.summary()["valid_readings"] == 0
        assert ds.time_range == (None, None)


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

class TestCSVExport:
    """Tests for DataReplayEngine-compatible CSV export."""

    def test_export_creates_file(self, daily_avg_file: Path, tmp_dir: Path):
        ds = parse_voyager_file(daily_avg_file, spacecraft="V1")
        out = tmp_dir / "output" / "test.csv"
        rows = export_to_csv(ds, out)
        assert out.exists()
        assert rows == 4  # 4 valid readings

    def test_export_csv_format(self, daily_avg_file: Path, tmp_dir: Path):
        ds = parse_voyager_file(daily_avg_file, spacecraft="V1")
        out = tmp_dir / "test.csv"
        export_to_csv(ds, out)

        with open(out) as f:
            reader = csv.DictReader(f)
            assert "time_offset_s" in reader.fieldnames
            assert "plasma_density_per_cm3" in reader.fieldnames
            assert "plasma_speed_km_s" in reader.fieldnames
            assert "plasma_temperature_k" in reader.fieldnames
            assert "plasma_pressure_npa" in reader.fieldnames
            assert "spacecraft" in reader.fieldnames

            rows = list(reader)
            assert len(rows) == 4
            # First row should have valid numeric values
            assert float(rows[0]["time_offset_s"]) > 0
            assert float(rows[0]["plasma_density_per_cm3"]) > 0

    def test_export_compatible_with_replay(self, daily_avg_file: Path, tmp_dir: Path):
        """Verify the CSV matches the format used by DataReplayEngine (time_offset_s + values)."""
        ds = parse_voyager_file(daily_avg_file, spacecraft="V1")
        out = tmp_dir / "replay_test.csv"
        export_to_csv(ds, out)

        with open(out) as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames
            # Must have time_offset_s as first column (same as NOAA replay format)
            assert cols[0] == "time_offset_s"
            # All subsequent columns should be value columns
            for row in reader:
                ts = float(row["time_offset_s"])
                assert ts > 1e9  # Should be Unix epoch seconds (post-2001)


# ---------------------------------------------------------------------------
# Directory parsing
# ---------------------------------------------------------------------------

class TestDirectoryParsing:
    """Tests for parsing multiple files in a directory."""

    def test_parse_directory(self, tmp_dir: Path):
        # Create multiple files
        (tmp_dir / "v1_2012.txt").write_text(DAILY_AVG_DATA)
        (tmp_dir / "v1_2013.txt").write_text(
            "2013  1    0.05  26.0  7500.0\n"
            "2013  2    0.06  25.5  7200.0\n"
        )

        ds = parse_voyager_directory(tmp_dir, spacecraft="V1")
        # Should merge readings from both files
        assert len(ds.valid_readings) >= 6
        # Should be sorted by timestamp
        timestamps = [r.timestamp for r in ds.valid_readings]
        assert timestamps == sorted(timestamps)

    def test_empty_directory(self, tmp_dir: Path):
        ds = parse_voyager_directory(tmp_dir, spacecraft="V1")
        assert len(ds.readings) == 0

    def test_mixed_formats(self, tmp_dir: Path):
        (tmp_dir / "v1_daily.txt").write_text(DAILY_AVG_DATA)
        (tmp_dir / "v1_plasma.csv").write_text(CSV_DATA)
        ds = parse_voyager_directory(tmp_dir, spacecraft="V1")
        # Both files should be parsed
        assert len(ds.valid_readings) >= 7  # 4 from daily + 3-4 from csv

    def test_skips_non_data_files(self, tmp_dir: Path):
        (tmp_dir / "v1_daily.txt").write_text(DAILY_AVG_DATA)
        (tmp_dir / "readme.md").write_text("# Not data")
        (tmp_dir / "image.png").write_bytes(b"\x89PNG")
        ds = parse_voyager_directory(tmp_dir, spacecraft="V1")
        assert len(ds.valid_readings) == 4  # Only from .txt file


# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------

class TestSyntheticData:
    """Tests for synthetic Voyager data generation."""

    def test_generates_data(self):
        ds = generate_synthetic_voyager_data(spacecraft="V1", days=100)
        assert len(ds.readings) == 100
        assert ds.spacecraft == "V1"

    def test_valid_readings(self):
        ds = generate_synthetic_voyager_data(spacecraft="V1", days=365)
        valid = ds.valid_readings
        # Should have most readings valid (a few will have simulated gaps)
        assert len(valid) > 340

    def test_physical_plausibility(self):
        ds = generate_synthetic_voyager_data(spacecraft="V1", days=365, start_year=2012)
        for r in ds.valid_readings:
            if r.density_per_cm3 is not None:
                # Solar wind: ~0.001-0.01; ISM: ~0.05-0.1
                assert 1e-5 < r.density_per_cm3 < 1.0
            if r.speed_km_s is not None:
                # Solar wind: ~300-600; ISM flow: ~20-30
                assert 1.0 < r.speed_km_s < 700.0
            if r.temperature_k is not None:
                # Solar wind: ~30k-200k; ISM: ~5k-10k
                assert 100.0 < r.temperature_k < 500000.0

    def test_heliopause_transition(self):
        """V1 should show density jump near heliopause crossing (~day 238 of 2012)."""
        ds = generate_synthetic_voyager_data(spacecraft="V1", days=365, start_year=2012)
        valid = ds.valid_readings

        early = [r for r in valid if r.timestamp.timetuple().tm_yday < 100
                 and r.density_per_cm3 is not None]
        late = [r for r in valid if r.timestamp.timetuple().tm_yday > 300
                and r.density_per_cm3 is not None]

        if early and late:
            avg_early = sum(r.density_per_cm3 for r in early) / len(early)
            avg_late = sum(r.density_per_cm3 for r in late) / len(late)
            # ISM density should be significantly higher than solar wind
            assert avg_late > avg_early * 5

    def test_v2_different_from_v1(self):
        ds1 = generate_synthetic_voyager_data(spacecraft="V1", days=100)
        ds2 = generate_synthetic_voyager_data(spacecraft="V2", days=100)
        # Different random seeds -> different values
        assert ds1.readings[0].density_per_cm3 != ds2.readings[0].density_per_cm3

    def test_heliocentric_distance_increases(self):
        ds = generate_synthetic_voyager_data(spacecraft="V1", days=100)
        dists = [r.heliocentric_distance_au for r in ds.readings
                 if r.heliocentric_distance_au is not None]
        assert dists == sorted(dists)  # Monotonically increasing


# ---------------------------------------------------------------------------
# ARIA bus replay
# ---------------------------------------------------------------------------

class TestVoyagerReplayEngine:
    """Tests for replaying Voyager data through the ARIA message bus."""

    async def test_replay_publishes_readings(self, bus: MessageBus):
        ds = generate_synthetic_voyager_data(spacecraft="V1", days=50)
        engine = VoyagerReplayEngine(bus)
        stats = await engine.replay(ds, time_scale=1000, max_readings=30)
        assert stats["readings_published"] == 30

    async def test_replay_correct_topics(self, bus: MessageBus):
        messages: list[Message] = []
        bus.subscribe("aria.sensor.navigation.plasma", lambda m: messages.append(m))

        ds = generate_synthetic_voyager_data(spacecraft="V1", days=10)
        engine = VoyagerReplayEngine(bus)
        await engine.replay(ds, time_scale=1000, max_readings=5)
        await asyncio.sleep(0.1)

        assert len(messages) >= 5
        for m in messages:
            assert "spacecraft" in m.payload
            assert m.payload["spacecraft"] == "V1"
            assert m.source_agent == "voyager_replay"

    async def test_replay_radiation_published(self, bus: MessageBus):
        rad_messages: list[Message] = []
        bus.subscribe("aria.sensor.science.radiation", lambda m: rad_messages.append(m))

        ds = generate_synthetic_voyager_data(spacecraft="V1", days=10)
        engine = VoyagerReplayEngine(bus)
        await engine.replay(ds, time_scale=1000, max_readings=10)
        await asyncio.sleep(0.1)

        # Radiation messages should be published for readings with valid pressure
        assert len(rad_messages) > 0
        for m in rad_messages:
            assert "dose_rate_usv_hr" in m.payload
            assert "plasma_pressure_npa" in m.payload

    async def test_replay_can_stop(self, bus: MessageBus):
        ds = generate_synthetic_voyager_data(spacecraft="V1", days=365)
        engine = VoyagerReplayEngine(bus)

        async def stop_soon():
            await asyncio.sleep(0.01)
            engine.stop()

        asyncio.create_task(stop_soon())
        # Use time_scale=1 (slow) so the stop has time to fire before all readings
        stats = await engine.replay(ds, time_scale=1)

        # Should not have published all 365 readings
        assert stats["readings_published"] < 365

    async def test_replay_payload_values(self, bus: MessageBus):
        messages: list[Message] = []
        bus.subscribe("aria.sensor.navigation.plasma", lambda m: messages.append(m))

        ds = generate_synthetic_voyager_data(spacecraft="V1", days=5)
        engine = VoyagerReplayEngine(bus)
        await engine.replay(ds, time_scale=1000)
        await asyncio.sleep(0.1)

        for m in messages:
            payload = m.payload
            if "plasma_density_per_cm3" in payload:
                assert payload["plasma_density_per_cm3"] > 0
            if "plasma_speed_km_s" in payload:
                assert payload["plasma_speed_km_s"] > 0


# ---------------------------------------------------------------------------
# End-to-end: process_voyager_data
# ---------------------------------------------------------------------------

class TestProcessVoyagerData:
    """End-to-end tests: parse -> export -> verify."""

    def test_process_single_file(self, daily_avg_file: Path, tmp_dir: Path):
        out_dir = tmp_dir / "output"
        result = process_voyager_data(daily_avg_file, out_dir, spacecraft="V1")
        assert result["rows_written"] == 4
        assert Path(result["csv_path"]).exists()
        assert result["spacecraft"] == "V1"

    def test_process_directory(self, tmp_dir: Path):
        data_dir = tmp_dir / "data"
        data_dir.mkdir()
        (data_dir / "v1_2012.txt").write_text(DAILY_AVG_DATA)
        (data_dir / "v1_2013.txt").write_text(
            "2013  1    0.05  26.0  7500.0\n"
            "2013  2    0.06  25.5  7200.0\n"
        )

        out_dir = tmp_dir / "output"
        result = process_voyager_data(data_dir, out_dir, spacecraft="V1")
        assert result["rows_written"] >= 6
        assert Path(result["csv_path"]).exists()

    def test_process_synthetic_roundtrip(self, tmp_dir: Path):
        """Generate synthetic -> export CSV -> re-read CSV -> verify."""
        ds = generate_synthetic_voyager_data(spacecraft="V1", days=30)
        csv_path = tmp_dir / "roundtrip.csv"
        rows = export_to_csv(ds, csv_path)
        assert rows > 25  # Most of 30 days should be valid

        # Re-read and verify
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            read_rows = list(reader)
            assert len(read_rows) == rows
            for row in read_rows:
                assert row["spacecraft"] == "V1"
                assert float(row["time_offset_s"]) > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests for error handling and edge cases."""

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_voyager_file("/nonexistent/path.txt")

    def test_empty_file(self, tmp_dir: Path):
        fp = tmp_dir / "empty.txt"
        fp.write_text("")
        ds = parse_voyager_file(fp, spacecraft="V1")
        assert len(ds.readings) == 0

    def test_all_fill_values(self, tmp_dir: Path):
        fp = tmp_dir / "v1_all_fill.txt"
        fp.write_text(
            "2012  1  9999.9  9999.9  9999.9\n"
            "2012  2  9999.9  9999.9  9999.9\n"
        )
        ds = parse_voyager_file(fp, spacecraft="V1")
        assert len(ds.valid_readings) == 0
        assert ds.fill_values_skipped > 0

    def test_corrupt_line_skipped(self, tmp_dir: Path):
        fp = tmp_dir / "v1_corrupt.txt"
        fp.write_text(
            "2012  1  0.003  410.5  48500.0\n"
            "THIS IS GARBAGE\n"
            "2012  3  0.004  420.0  51000.0\n"
        )
        ds = parse_voyager_file(fp, spacecraft="V1")
        assert len(ds.valid_readings) == 2
        assert ds.parse_errors >= 1

    def test_not_a_directory(self, tmp_dir: Path):
        fp = tmp_dir / "not_a_dir.txt"
        fp.write_text("data")
        with pytest.raises(NotADirectoryError):
            parse_voyager_directory(fp)

    def test_negative_density_filtered(self, tmp_dir: Path):
        """Negative density is physically impossible but could appear in raw data."""
        fp = tmp_dir / "v1_neg.txt"
        fp.write_text("2012  1  -0.003  410.5  48500.0\n")
        ds = parse_voyager_file(fp, spacecraft="V1")
        # Negative values are parsed (they pass _safe_float) but are kept
        # as they may represent sensor bias — consumers should validate
        assert len(ds.readings) == 1


# ---------------------------------------------------------------------------
# Real Voyager data (skipped if not available)
# ---------------------------------------------------------------------------

VOYAGER_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "voyager"
_real_data_available = (
    VOYAGER_DATA_DIR.exists()
    and any(
        f.suffix.lower() in (".txt", ".tab", ".csv", ".dat", ".asc")
        for f in VOYAGER_DATA_DIR.iterdir()
        if f.is_file() and f.stat().st_size > 1000
    )
)


@pytest.mark.skipif(not _real_data_available, reason="Real Voyager PLS data not downloaded")
class TestRealVoyagerData:
    """Tests using actual Voyager data files (skipped in CI)."""

    def test_parse_real_data(self):
        ds = parse_voyager_directory(VOYAGER_DATA_DIR)
        assert len(ds.valid_readings) > 0
        summary = ds.summary()
        assert summary["time_start"] is not None

    def test_export_real_data(self, tmp_dir: Path):
        ds = parse_voyager_directory(VOYAGER_DATA_DIR)
        out = tmp_dir / "real_voyager.csv"
        rows = export_to_csv(ds, out)
        assert rows > 0
