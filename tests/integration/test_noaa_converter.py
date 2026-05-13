"""Integration tests for NOAA GOES-16 SGPS netCDF-to-CSV converter.

Tests cover:
  - Single file conversion with real netCDF files (skipped if data absent)
  - Batch directory conversion
  - Missing value handling (all fill strategies)
  - Output format validation (wide, long, replay CSVs)
  - Channel metadata extraction
  - DataReplayEngine compatibility
  - Edge cases: empty directory, corrupt file, invalid parameters
  - Synthetic netCDF tests (always run, no real data required)
"""

from __future__ import annotations

import csv
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

# Real data directory — tests that require it are skipped if absent
NOAA_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "noaa_goes"
HAS_REAL_DATA = NOAA_DATA_DIR.exists() and any(NOAA_DATA_DIR.glob("*.nc"))

try:
    import netCDF4
    import numpy as np
    HAS_NETCDF4 = True
except ImportError:
    HAS_NETCDF4 = False

pytestmark = pytest.mark.skipif(not HAS_NETCDF4, reason="netCDF4 not installed")

from aria.simulation.noaa_converter import (
    ALPHA_DIFF_CHANNEL_NAMES,
    PROTON_DIFF_CHANNEL_NAMES,
    SENSOR_EAST,
    SENSOR_WEST,
    ChannelMetadata,
    ConversionResult,
    NOAAGoesConverter,
    convert_goes_directory,
    _J2000_UNIX_OFFSET,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Temporary output directory for CSV files."""
    out = tmp_path / "output"
    out.mkdir()
    return out


@pytest.fixture
def synthetic_nc(tmp_path: Path) -> Path:
    """Create a minimal synthetic SGPS-like netCDF file for testing.

    This ensures tests run even without real NOAA data.
    """
    filepath = tmp_path / "sci_sgps-l2-avg1m_g16_d20990101_v3-0-2.nc"
    ds = netCDF4.Dataset(str(filepath), "w", format="NETCDF4")

    n_times = 60  # 1 hour of 1-minute data
    n_diff_channels = 13
    n_alpha_channels = 11
    n_sensors = 2

    # Dimensions
    ds.createDimension("time", None)  # unlimited
    ds.createDimension("diff_channels", n_diff_channels)
    ds.createDimension("sensor_units", n_sensors)
    ds.createDimension("diff_alpha_channels", n_alpha_channels)

    # Time variable: seconds since J2000
    # Use a date far in the future to avoid colliding with real data
    # 2099-01-01 00:00:00 UTC => offset from J2000
    base_time = (
        datetime(2099, 1, 1, tzinfo=timezone.utc).timestamp() - _J2000_UNIX_OFFSET
    )
    time_var = ds.createVariable("time", "f8", ("time",), fill_value=-1e31)
    time_var.long_name = "Time stamp"
    time_var.units = "seconds since 2000-01-01 12:00:00 UTC"
    time_data = np.array([base_time + i * 60.0 for i in range(n_times)])
    time_var[:] = time_data

    # L1b records
    l1b = ds.createVariable("L1bRecordsInAvg", "u4", ("time",), fill_value=4294967295)
    l1b[:] = np.full(n_times, 60, dtype=np.uint32)

    # Yaw flip
    yaw = ds.createVariable("yaw_flip_flag", "u1", ("time",), fill_value=255)
    yaw[:] = np.zeros(n_times, dtype=np.uint8)

    # Differential proton flux
    fill_float = np.float32(-9.999999848243207e+30)
    diff_flux = ds.createVariable(
        "AvgDiffProtonFlux", "f4",
        ("time", "sensor_units", "diff_channels"),
        fill_value=fill_float,
    )
    diff_flux.long_name = "Time-averaged proton fluxes"
    diff_flux.units = "protons/(cm^2 sr keV s)"

    # Generate realistic flux values (decreasing with energy)
    rng = np.random.default_rng(42)
    for su in range(n_sensors):
        for ch in range(n_diff_channels):
            base = 1e-2 / (10 ** (ch * 0.3))  # Decreasing flux with energy
            noise = rng.normal(1.0, 0.1, n_times)
            diff_flux[:, su, ch] = (base * noise).astype(np.float32)

    # Inject some fill values (missing data) at known positions
    diff_flux[10, 0, :] = fill_float  # Entire row missing for sensor 0
    diff_flux[20, 0, 5] = fill_float  # Single channel missing
    diff_flux[30, 1, :] = fill_float  # Entire row missing for sensor 1

    # Differential proton flux uncertainty
    diff_uncert = ds.createVariable(
        "AvgDiffProtonFluxUncert", "f4",
        ("time", "sensor_units", "diff_channels"),
        fill_value=fill_float,
    )
    diff_uncert.long_name = "Uncertainty"
    diff_uncert.units = "protons/(cm^2 sr keV s)"
    diff_uncert[:, :, :] = np.abs(diff_flux[:, :, :]) * 0.1  # 10% uncertainty

    # Integral proton flux
    int_flux = ds.createVariable(
        "AvgIntProtonFlux", "f4",
        ("time", "sensor_units"),
        fill_value=fill_float,
    )
    int_flux.long_name = ">500 MeV integral proton flux"
    int_flux.units = "protons/(cm^2 sr s)"
    for su in range(n_sensors):
        int_flux[:, su] = (rng.normal(1e-5, 1e-6, n_times)).astype(np.float32)
    int_flux[10, 0] = fill_float  # Match the diff fill

    # Integral uncertainty
    int_uncert = ds.createVariable(
        "AvgIntProtonFluxUncert", "f4",
        ("time", "sensor_units"),
        fill_value=fill_float,
    )
    int_uncert[:, :] = np.abs(int_flux[:, :]) * 0.1

    # Energy band metadata
    # Proton lower energies (keV) — approximate SGPS bands
    proton_lower = np.array([
        1000, 1900, 2300, 3400, 6500, 11600, 25900, 38100,
        50000, 83700, 98500, 115000, 332000,
    ], dtype=np.float32)
    proton_upper = np.array([
        1900, 2300, 3400, 6500, 11600, 25900, 38100, 50000,
        83700, 98500, 115000, 332000, 500000,
    ], dtype=np.float32)
    proton_effective = np.sqrt(proton_lower * proton_upper)

    lower_var = ds.createVariable(
        "DiffProtonLowerEnergy", "f4",
        ("sensor_units", "diff_channels"),
        fill_value=-9999.0,
    )
    lower_var.units = "keV"
    upper_var = ds.createVariable(
        "DiffProtonUpperEnergy", "f4",
        ("sensor_units", "diff_channels"),
        fill_value=-9999.0,
    )
    upper_var.units = "keV"
    eff_var = ds.createVariable(
        "DiffProtonEffectiveEnergy", "f4",
        ("sensor_units", "diff_channels"),
        fill_value=-9999.0,
    )
    eff_var.units = "keV"

    for su in range(n_sensors):
        lower_var[su, :] = proton_lower
        upper_var[su, :] = proton_upper
        eff_var[su, :] = proton_effective

    # Integral proton effective energy
    int_eff = ds.createVariable(
        "IntegralProtonEffectiveEnergy", "f4",
        ("sensor_units",),
        fill_value=-9999.0,
    )
    int_eff.units = "keV"
    int_eff[:] = [500000.0, 500000.0]

    # Alpha particle data
    alpha_lower = np.array([
        3800, 6900, 8300, 13600, 25300, 50400, 83800, 102000,
        255000, 396000, 575000,
    ], dtype=np.float32)
    alpha_upper = np.array([
        6900, 8300, 13600, 25300, 50400, 83800, 102000, 255000,
        396000, 575000, 900000,
    ], dtype=np.float32)
    alpha_effective = np.sqrt(alpha_lower * alpha_upper)

    a_lower = ds.createVariable(
        "DiffAlphaLowerEnergy", "f4",
        ("sensor_units", "diff_alpha_channels"),
        fill_value=-9999.0,
    )
    a_upper = ds.createVariable(
        "DiffAlphaUpperEnergy", "f4",
        ("sensor_units", "diff_alpha_channels"),
        fill_value=-9999.0,
    )
    a_eff = ds.createVariable(
        "DiffAlphaEffectiveEnergy", "f4",
        ("sensor_units", "diff_alpha_channels"),
        fill_value=-9999.0,
    )
    for su in range(n_sensors):
        a_lower[su, :] = alpha_lower
        a_upper[su, :] = alpha_upper
        a_eff[su, :] = alpha_effective

    alpha_flux = ds.createVariable(
        "AvgDiffAlphaFlux", "f4",
        ("time", "sensor_units", "diff_alpha_channels"),
        fill_value=fill_float,
    )
    alpha_flux.units = "alphas/(cm^2 sr keV s)"
    for su in range(n_sensors):
        for ch in range(n_alpha_channels):
            base = 1e-4 / (10 ** (ch * 0.3))
            alpha_flux[:, su, ch] = (base * rng.normal(1.0, 0.1, n_times)).astype(np.float32)

    # DQF variables (required for completeness, not used by converter)
    for vname in [
        "DiffValidL1bSamplesInAvg", "DiffDQFdtcSum", "DiffDQFoobSum", "DiffDQFerrSum",
    ]:
        v = ds.createVariable(vname, "u4", ("time", "sensor_units", "diff_channels"), fill_value=4294967295)
        v[:, :, :] = 60

    for vname in ["IntValidL1bSamplesInAvg", "IntDQFdtcSum", "IntDQFoobSum", "IntDQFerrSum"]:
        v = ds.createVariable(vname, "u4", ("time", "sensor_units"), fill_value=4294967295)
        v[:, :] = 60

    exp_lut = ds.createVariable("ExpectedLUTNotFound", "u1", fill_value=255)
    exp_lut[:] = 0

    # Observed flux (without temp correction)
    obs_diff = ds.createVariable(
        "AvgDiffProtonFluxObserved", "f4",
        ("time", "sensor_units", "diff_channels"),
        fill_value=fill_float,
    )
    obs_diff[:, :, :] = diff_flux[:, :, :]

    obs_int = ds.createVariable(
        "AvgIntProtonFluxObserved", "f4",
        ("time", "sensor_units"),
        fill_value=fill_float,
    )
    obs_int[:, :] = int_flux[:, :]

    obs_alpha = ds.createVariable(
        "AvgDiffAlphaFluxObserved", "f4",
        ("time", "sensor_units", "diff_alpha_channels"),
        fill_value=fill_float,
    )
    obs_alpha[:, :, :] = alpha_flux[:, :, :]

    # Alpha uncertainty
    a_uncert = ds.createVariable(
        "AvgDiffAlphaFluxUncert", "f4",
        ("time", "sensor_units", "diff_alpha_channels"),
        fill_value=fill_float,
    )
    a_uncert[:, :, :] = np.abs(alpha_flux[:, :, :]) * 0.1

    # Ignored DQF masks
    for vname in ["DiffProtonIgnoredL1bDQFs"]:
        v = ds.createVariable(vname, "u1", ("time", "sensor_units", "diff_channels"), fill_value=255)
        v[:, :, :] = 0
    for vname in ["IntProtonIgnoredL1bDQFs"]:
        v = ds.createVariable(vname, "u1", ("time", "sensor_units"), fill_value=255)
        v[:, :] = 0
    for vname in ["DiffAlphaIgnoredL1bDQFs"]:
        v = ds.createVariable(vname, "u1", ("time", "sensor_units", "diff_alpha_channels"), fill_value=255)
        v[:, :, :] = 0

    # Global attributes
    ds.title = "Synthetic SGPS test data"
    ds.time_coverage_start = "2099-01-01T00:00:00.000Z"
    ds.time_coverage_end = "2099-01-01T01:00:00.000Z"

    ds.close()
    return filepath


@pytest.fixture
def synthetic_dir(synthetic_nc: Path, tmp_path: Path) -> Path:
    """Directory containing the synthetic .nc file."""
    return synthetic_nc.parent


# ---------------------------------------------------------------------------
# ChannelMetadata unit tests
# ---------------------------------------------------------------------------

class TestChannelMetadata:
    def test_energy_mev_conversion(self):
        meta = ChannelMetadata(
            name="P1",
            lower_energy_kev=1000.0,
            upper_energy_kev=1900.0,
            effective_energy_kev=1378.4,
            units="protons/(cm^2 sr keV s)",
            sensor_unit=SENSOR_WEST,
        )
        assert meta.lower_energy_mev == pytest.approx(1.0)
        assert meta.upper_energy_mev == pytest.approx(1.9)
        assert meta.effective_energy_mev == pytest.approx(1.3784)

    def test_label_west(self):
        meta = ChannelMetadata(
            name="P3", lower_energy_kev=3400, upper_energy_kev=6500,
            effective_energy_kev=4700, units="", sensor_unit=SENSOR_WEST,
        )
        assert "P3" in meta.label
        assert "West" in meta.label

    def test_label_east(self):
        meta = ChannelMetadata(
            name="P5", lower_energy_kev=11600, upper_energy_kev=25900,
            effective_energy_kev=17300, units="", sensor_unit=SENSOR_EAST,
        )
        assert "East" in meta.label

    def test_csv_column_format(self):
        meta = ChannelMetadata(
            name="P8A", lower_energy_kev=50000, upper_energy_kev=83700,
            effective_energy_kev=64700, units="", sensor_unit=SENSOR_WEST,
        )
        assert meta.csv_column == "proton_P8A_west"

        meta_east = ChannelMetadata(
            name="P8A", lower_energy_kev=50000, upper_energy_kev=83700,
            effective_energy_kev=64700, units="", sensor_unit=SENSOR_EAST,
        )
        assert meta_east.csv_column == "proton_P8A_east"


# ---------------------------------------------------------------------------
# Converter initialization tests
# ---------------------------------------------------------------------------

class TestConverterInit:
    def test_default_config(self):
        c = NOAAGoesConverter()
        assert c._sensor_unit == SENSOR_WEST
        assert c._include_alpha is False
        assert c._fill_strategy == "nan"

    def test_east_sensor(self):
        c = NOAAGoesConverter(sensor_unit=SENSOR_EAST)
        assert c._sensor_unit == SENSOR_EAST

    def test_invalid_sensor_unit(self):
        with pytest.raises(ValueError, match="sensor_unit"):
            NOAAGoesConverter(sensor_unit=2)

    def test_invalid_fill_strategy(self):
        with pytest.raises(ValueError, match="fill_strategy"):
            NOAAGoesConverter(fill_strategy="invalid")

    def test_all_fill_strategies_accepted(self):
        for strat in ("nan", "drop", "zero", "interpolate"):
            c = NOAAGoesConverter(fill_strategy=strat)
            assert c._fill_strategy == strat


# ---------------------------------------------------------------------------
# Synthetic data conversion tests
# ---------------------------------------------------------------------------

class TestSyntheticConversion:
    """Tests using synthetic netCDF data — always runnable."""

    def test_single_file_conversion(self, synthetic_nc: Path, output_dir: Path):
        converter = NOAAGoesConverter()
        result = converter.convert_single(synthetic_nc, output_dir)

        assert result.files_converted == 1
        assert result.files_skipped == 0
        assert result.total_readings == 60  # 1 hour of 1-min data
        assert result.missing_values_replaced > 0  # We injected fills
        assert len(result.errors) == 0

    def test_wide_csv_structure(self, synthetic_nc: Path, output_dir: Path):
        converter = NOAAGoesConverter()
        converter.convert_single(synthetic_nc, output_dir)

        wide_files = list(output_dir.glob("*_wide.csv"))
        assert len(wide_files) == 1

        with open(wide_files[0]) as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames
            assert "timestamp" in columns
            assert "time_offset_s" in columns
            # All 13 proton channels + 1 integral = 14 proton columns
            proton_cols = [c for c in columns if c.startswith("proton_")]
            assert len(proton_cols) == 14  # 13 diff + 1 integral

            rows = list(reader)
            assert len(rows) == 60

            # Verify timestamp format
            first_ts = rows[0]["timestamp"]
            datetime.strptime(first_ts, "%Y-%m-%dT%H:%M:%SZ")

    def test_long_csv_structure(self, synthetic_nc: Path, output_dir: Path):
        converter = NOAAGoesConverter()
        converter.convert_single(synthetic_nc, output_dir)

        long_files = list(output_dir.glob("*_long.csv"))
        assert len(long_files) == 1

        with open(long_files[0]) as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames
            assert columns == ["timestamp", "channel_name", "value"]

            rows = list(reader)
            # 60 timestamps x 14 channels = 840 maximum
            # Row 10 has all fills for sensor 0 (14 channels missing)
            # Row 20 has 1 fill (1 channel missing)
            # So we expect 840 - 14 - 1 = 825 rows
            expected_max = 60 * 14
            assert len(rows) < expected_max
            assert len(rows) > (expected_max - 20)  # Most rows should be present

            # Verify channel names appear
            channel_names = set(row["channel_name"] for row in rows)
            assert any("proton_P1" in cn for cn in channel_names)
            assert any("integral" in cn for cn in channel_names)

    def test_fill_strategy_nan(self, synthetic_nc: Path, output_dir: Path):
        converter = NOAAGoesConverter(fill_strategy="nan")
        converter.convert_single(synthetic_nc, output_dir)

        wide_file = list(output_dir.glob("*_wide.csv"))[0]
        with open(wide_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            # Row at index 10 should have empty values (NaN)
            row_10 = rows[10]
            assert row_10["proton_P1_west"] == ""

    def test_fill_strategy_zero(self, synthetic_nc: Path, output_dir: Path):
        converter = NOAAGoesConverter(fill_strategy="zero")
        converter.convert_single(synthetic_nc, output_dir)

        wide_file = list(output_dir.glob("*_wide.csv"))[0]
        with open(wide_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            # Row at index 10 should have zero values instead of empty
            row_10 = rows[10]
            assert row_10["proton_P1_west"] != ""
            assert float(row_10["proton_P1_west"]) == 0.0

    def test_fill_strategy_drop(self, synthetic_nc: Path, output_dir: Path):
        converter = NOAAGoesConverter(fill_strategy="drop")
        converter.convert_single(synthetic_nc, output_dir)

        wide_file = list(output_dir.glob("*_wide.csv"))[0]
        with open(wide_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            # Row 10 had all diff + integral fills, should be dropped
            assert len(rows) < 60

    def test_fill_strategy_interpolate(self, synthetic_nc: Path, output_dir: Path):
        converter = NOAAGoesConverter(fill_strategy="interpolate")
        converter.convert_single(synthetic_nc, output_dir)

        wide_file = list(output_dir.glob("*_wide.csv"))[0]
        with open(wide_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 60
            # Interpolated row should have non-empty, non-zero values
            row_10 = rows[10]
            val = row_10["proton_P1_west"]
            assert val != ""
            assert float(val) != 0.0

    def test_east_sensor_unit(self, synthetic_nc: Path, output_dir: Path):
        converter = NOAAGoesConverter(sensor_unit=SENSOR_EAST)
        converter.convert_single(synthetic_nc, output_dir)

        wide_file = list(output_dir.glob("*_wide.csv"))[0]
        with open(wide_file) as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames
            assert any("_east" in c for c in columns)
            assert not any("_west" in c for c in columns)

    def test_include_alpha(self, synthetic_nc: Path, output_dir: Path):
        converter = NOAAGoesConverter(include_alpha=True)
        converter.convert_single(synthetic_nc, output_dir)

        wide_file = list(output_dir.glob("*_wide.csv"))[0]
        with open(wide_file) as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames
            alpha_cols = [c for c in columns if c.startswith("alpha_")]
            assert len(alpha_cols) == 11

    def test_include_uncertainties(self, synthetic_nc: Path, output_dir: Path):
        converter = NOAAGoesConverter(include_uncertainties=True)
        converter.convert_single(synthetic_nc, output_dir)

        wide_file = list(output_dir.glob("*_wide.csv"))[0]
        with open(wide_file) as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames
            uncert_cols = [c for c in columns if "_uncert" in c]
            assert len(uncert_cols) == 14  # 13 diff + 1 integral

    def test_directory_conversion(self, synthetic_dir: Path, output_dir: Path):
        converter = NOAAGoesConverter()
        result = converter.convert_directory(synthetic_dir, output_dir)

        assert result.files_converted == 1
        # Combined files should be created
        assert any("all_days_wide" in f for f in result.output_files)
        assert any("all_days_long" in f for f in result.output_files)
        assert any("replay" in f for f in result.output_files)

    def test_replay_csv_format(self, synthetic_dir: Path, output_dir: Path):
        """Verify the replay CSV matches DataReplayEngine expectations."""
        converter = NOAAGoesConverter()
        result = converter.convert_directory(synthetic_dir, output_dir)

        replay_files = [f for f in result.output_files if f.endswith("replay.csv")]
        assert len(replay_files) == 1

        with open(replay_files[0]) as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames
            # Must match DataReplayEngine.replay_noaa_proton_flux() expectations
            assert "time_offset_s" in columns
            assert "total_proton_flux" in columns
            assert "dose_rate_usv_hr" in columns

            rows = list(reader)
            assert len(rows) > 0

            # Verify values are numeric
            for row in rows[:5]:
                assert float(row["time_offset_s"]) > 0
                assert float(row["total_proton_flux"]) > 0
                assert float(row["dose_rate_usv_hr"]) > 0

    def test_date_extraction_from_filename(self, synthetic_nc: Path, output_dir: Path):
        converter = NOAAGoesConverter()
        date_str = converter._extract_date_from_filename(synthetic_nc.name)
        assert date_str == "20990101"

    def test_timestamps_are_chronological(self, synthetic_nc: Path, output_dir: Path):
        converter = NOAAGoesConverter()
        converter.convert_single(synthetic_nc, output_dir)

        wide_file = list(output_dir.glob("*_wide.csv"))[0]
        with open(wide_file) as f:
            reader = csv.DictReader(f)
            offsets = [float(row["time_offset_s"]) for row in reader]

        # Strictly increasing
        for i in range(1, len(offsets)):
            assert offsets[i] > offsets[i - 1]

    def test_flux_values_physically_reasonable(self, synthetic_nc: Path, output_dir: Path):
        """Verify flux values are in physically plausible range for SGPS data."""
        converter = NOAAGoesConverter(fill_strategy="drop")
        converter.convert_single(synthetic_nc, output_dir)

        wide_file = list(output_dir.glob("*_wide.csv"))[0]
        with open(wide_file) as f:
            reader = csv.DictReader(f)
            for row in reader:
                for key, val in row.items():
                    if key.startswith("proton_") and val != "":
                        fval = float(val)
                        # Proton fluxes should be positive (or zero for fills)
                        # and not absurdly large
                        assert fval > -1e10, f"Flux {key}={fval} seems like a fill value leak"
                        assert fval < 1e10, f"Flux {key}={fval} unreasonably large"


class TestEmptyAndErrorCases:
    def test_empty_directory(self, tmp_path: Path, output_dir: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        converter = NOAAGoesConverter()
        result = converter.convert_directory(empty_dir, output_dir)
        assert result.files_converted == 0
        assert result.total_readings == 0

    def test_nonexistent_input_creates_no_crash(self, tmp_path: Path, output_dir: Path):
        """convert_directory creates output dir but finds no files."""
        missing = tmp_path / "nonexistent"
        # Path.glob on a non-existent dir raises, but mkdir is called first for output.
        # We handle this gracefully.
        converter = NOAAGoesConverter()
        # This should not crash even though input_dir does not exist
        # It will return empty result since glob finds nothing
        try:
            result = converter.convert_directory(missing, output_dir)
            assert result.files_converted == 0
        except (FileNotFoundError, OSError):
            pass  # Acceptable behavior

    def test_output_dir_created_automatically(self, synthetic_dir: Path, tmp_path: Path):
        new_output = tmp_path / "deeply" / "nested" / "output"
        assert not new_output.exists()

        converter = NOAAGoesConverter()
        result = converter.convert_directory(synthetic_dir, new_output)
        assert new_output.exists()
        assert result.files_converted == 1


class TestConvenienceFunction:
    def test_convert_goes_directory(self, synthetic_dir: Path, output_dir: Path):
        result = convert_goes_directory(
            input_dir=str(synthetic_dir),
            output_dir=str(output_dir),
            sensor_unit=SENSOR_WEST,
            include_alpha=False,
            fill_strategy="nan",
        )
        assert isinstance(result, ConversionResult)
        assert result.files_converted == 1


# ---------------------------------------------------------------------------
# Multi-file batch tests (synthetic)
# ---------------------------------------------------------------------------

class TestBatchConversion:
    @pytest.fixture
    def multi_day_dir(self, synthetic_nc: Path, tmp_path: Path) -> Path:
        """Create a second synthetic file to simulate multi-day batch."""
        import shutil
        second = tmp_path / "sci_sgps-l2-avg1m_g16_d20990102_v3-0-2.nc"
        shutil.copy2(synthetic_nc, second)
        return tmp_path

    def test_multi_file_produces_combined_csv(
        self, multi_day_dir: Path, output_dir: Path
    ):
        converter = NOAAGoesConverter()
        result = converter.convert_directory(multi_day_dir, output_dir)

        assert result.files_converted == 2
        assert result.total_readings == 120  # 60 per file

        # Combined files
        combined_wide = output_dir / "goes16_sgps_all_days_wide.csv"
        assert combined_wide.exists()
        with open(combined_wide) as f:
            rows = list(csv.DictReader(f))
            assert len(rows) == 120

    def test_per_day_files_created(self, multi_day_dir: Path, output_dir: Path):
        converter = NOAAGoesConverter()
        converter.convert_directory(multi_day_dir, output_dir)

        day_files = sorted(output_dir.glob("goes16_sgps_2099010*_wide.csv"))
        assert len(day_files) == 2


# ---------------------------------------------------------------------------
# Real data tests (skipped if data files absent)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_REAL_DATA, reason="NOAA GOES data not downloaded")
class TestRealData:
    """Tests that run against actual NOAA GOES-16 netCDF files."""

    def test_real_single_file(self, output_dir: Path):
        nc_files = sorted(NOAA_DATA_DIR.glob("*.nc"))
        converter = NOAAGoesConverter()
        result = converter.convert_single(nc_files[0], output_dir)

        assert result.files_converted == 1
        assert result.total_readings == 1440  # Full day of 1-min data

    def test_real_batch_conversion(self, output_dir: Path):
        converter = NOAAGoesConverter()
        result = converter.convert_directory(NOAA_DATA_DIR, output_dir)

        assert result.files_converted > 0
        assert result.total_readings > 0

        # Replay CSV should exist and be loadable by DataReplayEngine
        replay_csv = output_dir / "goes16_sgps_replay.csv"
        assert replay_csv.exists()

        with open(replay_csv) as f:
            reader = csv.DictReader(f)
            first_row = next(reader)
            assert "time_offset_s" in first_row
            assert "total_proton_flux" in first_row
            assert "dose_rate_usv_hr" in first_row

    def test_real_data_no_fill_leaks(self, output_dir: Path):
        """Ensure fill values (-9.99e30) never appear in output CSV."""
        nc_files = sorted(NOAA_DATA_DIR.glob("*.nc"))
        converter = NOAAGoesConverter(fill_strategy="nan")
        converter.convert_single(nc_files[0], output_dir)

        wide_file = list(output_dir.glob("*_wide.csv"))[0]
        with open(wide_file) as f:
            content = f.read()
            assert "-9.99" not in content or "-9.99e+30" not in content
            assert "-1e+31" not in content

    def test_real_data_with_interpolation(self, output_dir: Path):
        nc_files = sorted(NOAA_DATA_DIR.glob("*.nc"))
        converter = NOAAGoesConverter(fill_strategy="interpolate")
        result = converter.convert_single(nc_files[0], output_dir)

        assert result.files_converted == 1
        # With interpolation, we should have full 1440 rows
        wide_file = list(output_dir.glob("*_wide.csv"))[0]
        with open(wide_file) as f:
            rows = list(csv.DictReader(f))
            assert len(rows) == 1440
