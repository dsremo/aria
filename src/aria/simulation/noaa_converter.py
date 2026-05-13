"""Batch NOAA GOES-16 SGPS netCDF-to-CSV converter for ARIA DataReplayEngine.

Converts GOES-16 SEISS/SGPS Level-2 1-minute-averaged proton and alpha flux
netCDF files into CSV format compatible with ARIA's DataReplayEngine.

GOES-16 SGPS data reference:
  - Instrument: Solar & Galactic Proton Sensor (SGPS), part of SEISS
  - Product: L2 avg1m (1-minute flux averages)
  - Proton channels: P1..P10 (differential, 1-500 MeV) + P11 (integral, >500 MeV)
  - Alpha channels: A1..A11 (differential, 1-500 MeV)
  - Two sensor units: -X (West-looking) and +X (East-looking)
  - Time reference: seconds since 2000-01-01 12:00:00 UTC

Output CSV columns for DataReplayEngine compatibility:
  Wide format (per-day and combined): timestamp, time_offset_s, channel columns...
  Long format (for flexible replay): timestamp, channel_name, value

Usage:
    converter = NOAAGoesConverter()
    result = converter.convert_directory(
        input_dir="data/raw/noaa_goes",
        output_dir="data/processed/noaa_goes",
    )
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# J2000 epoch: 2000-01-01T12:00:00 UTC — the time reference for GOES-16 netCDF
_J2000_EPOCH = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_J2000_UNIX_OFFSET = _J2000_EPOCH.timestamp()

# SGPS differential proton channel names (13 channels, 1-500 MeV)
PROTON_DIFF_CHANNEL_NAMES: list[str] = [
    "P1", "P2A", "P2B", "P3", "P4", "P5", "P6", "P7",
    "P8A", "P8B", "P8C", "P9", "P10",
]

# SGPS differential alpha channel names (11 channels)
ALPHA_DIFF_CHANNEL_NAMES: list[str] = [
    "A1", "A2A", "A2B", "A3", "A4", "A5", "A6", "A7",
    "A9", "A10", "A11",
]

# Sensor unit indices
SENSOR_WEST = 0  # -X, West-looking when spacecraft upright
SENSOR_EAST = 1  # +X, East-looking when spacecraft upright


@dataclass
class ChannelMetadata:
    """Energy band metadata for a single flux channel."""
    name: str
    lower_energy_kev: float
    upper_energy_kev: float
    effective_energy_kev: float
    units: str
    sensor_unit: int  # 0=West, 1=East

    @property
    def lower_energy_mev(self) -> float:
        return self.lower_energy_kev / 1000.0

    @property
    def upper_energy_mev(self) -> float:
        return self.upper_energy_kev / 1000.0

    @property
    def effective_energy_mev(self) -> float:
        return self.effective_energy_kev / 1000.0

    @property
    def label(self) -> str:
        """Human-readable label: e.g. 'P1_1.0-1.9MeV_West'."""
        side = "West" if self.sensor_unit == SENSOR_WEST else "East"
        return f"{self.name}_{self.lower_energy_mev:.1f}-{self.upper_energy_mev:.1f}MeV_{side}"

    @property
    def csv_column(self) -> str:
        """Short column name for wide CSV: e.g. 'proton_P1_west'."""
        side = "west" if self.sensor_unit == SENSOR_WEST else "east"
        return f"proton_{self.name}_{side}"


@dataclass
class ConversionResult:
    """Summary of a batch conversion run."""
    files_converted: int = 0
    files_skipped: int = 0
    total_readings: int = 0
    missing_values_replaced: int = 0
    output_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _import_netcdf4():
    """Import netCDF4 with a clear error if unavailable."""
    try:
        import netCDF4  # noqa: N811
        return netCDF4
    except ImportError:
        raise ImportError(
            "netCDF4 is required for NOAA GOES conversion. "
            "Install with: pip install netCDF4"
        )


def _import_numpy():
    """Import numpy with a clear error if unavailable."""
    try:
        import numpy as np
        return np
    except ImportError:
        raise ImportError("numpy is required for NOAA GOES conversion.")


class NOAAGoesConverter:
    """Converts NOAA GOES-16 SGPS netCDF files to ARIA-compatible CSV.

    Extracts proton and alpha particle flux measurements from GOES-16 SEISS/SGPS
    Level-2 1-minute average files and produces CSVs that feed directly into
    ARIA's DataReplayEngine.replay_noaa_proton_flux().

    Output formats:
      1. Per-day wide CSV: one row per minute, columns per channel
      2. Per-day long CSV: (timestamp, channel_name, value) triples
      3. Combined wide CSV: all days concatenated chronologically
      4. Combined replay CSV: simplified format matching existing DataReplayEngine
         expectations (time_offset_s, total_proton_flux, dose_rate_usv_hr)
    """

    def __init__(
        self,
        sensor_unit: int = SENSOR_WEST,
        include_alpha: bool = False,
        include_uncertainties: bool = False,
        fill_strategy: str = "nan",
    ) -> None:
        """
        Args:
            sensor_unit: Which sensor to extract (0=West/-X, 1=East/+X).
                West is the default as it provides better galactic cosmic ray
                measurements when the spacecraft is in normal orientation.
            include_alpha: Whether to include alpha particle channels.
            include_uncertainties: Whether to include flux uncertainty columns.
            fill_strategy: How to handle missing/fill values.
                "nan" = write NaN (default), "drop" = skip rows,
                "zero" = replace with 0.0, "interpolate" = linear interpolation.
        """
        if sensor_unit not in (SENSOR_WEST, SENSOR_EAST):
            raise ValueError(f"sensor_unit must be 0 (West) or 1 (East), got {sensor_unit}")
        if fill_strategy not in ("nan", "drop", "zero", "interpolate"):
            raise ValueError(
                f"fill_strategy must be 'nan', 'drop', 'zero', or 'interpolate', "
                f"got '{fill_strategy}'"
            )

        self._sensor_unit = sensor_unit
        self._include_alpha = include_alpha
        self._include_uncertainties = include_uncertainties
        self._fill_strategy = fill_strategy

    def convert_directory(
        self,
        input_dir: str | Path,
        output_dir: str | Path,
    ) -> ConversionResult:
        """Convert all SGPS netCDF files in a directory to CSV.

        Args:
            input_dir: Directory containing .nc files.
            output_dir: Directory to write CSV files. Created if it does not exist.

        Returns:
            ConversionResult with statistics and output file paths.
        """
        np = _import_numpy()
        nc4 = _import_netcdf4()

        input_path = Path(input_dir)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        nc_files = sorted(input_path.glob("*.nc"))
        if not nc_files:
            logger.warning("noaa_converter.no_nc_files", dir=str(input_path))
            return ConversionResult()

        result = ConversionResult()

        # Accumulate all days for the combined output
        all_timestamps: list[float] = []
        all_rows_wide: list[dict[str, Any]] = []
        all_rows_long: list[tuple[str, str, float]] = []
        channel_columns: list[str] = []

        for nc_file in nc_files:
            try:
                day_result = self._convert_single_file(
                    nc_file, output_path, nc4, np,
                )
                if day_result is None:
                    result.files_skipped += 1
                    continue

                timestamps, rows_wide, rows_long, columns, missing_count = day_result
                all_timestamps.extend(timestamps)
                all_rows_wide.extend(rows_wide)
                all_rows_long.extend(rows_long)
                if not channel_columns:
                    channel_columns = columns

                result.files_converted += 1
                result.total_readings += len(timestamps)
                result.missing_values_replaced += missing_count

                logger.info(
                    "noaa_converter.file_done",
                    file=nc_file.name,
                    readings=len(timestamps),
                    missing=missing_count,
                )

            except Exception as exc:
                msg = f"{nc_file.name}: {exc}"
                result.errors.append(msg)
                result.files_skipped += 1
                logger.error("noaa_converter.file_error", file=nc_file.name, error=str(exc))

        if not all_rows_wide:
            logger.warning("noaa_converter.no_data_extracted")
            return result

        # Write combined wide CSV (all days)
        combined_wide_path = output_path / "goes16_sgps_all_days_wide.csv"
        self._write_wide_csv(combined_wide_path, all_rows_wide, channel_columns)
        result.output_files.append(str(combined_wide_path))

        # Write combined long CSV (all days)
        combined_long_path = output_path / "goes16_sgps_all_days_long.csv"
        self._write_long_csv(combined_long_path, all_rows_long)
        result.output_files.append(str(combined_long_path))

        # Write combined replay CSV (DataReplayEngine-compatible)
        replay_path = output_path / "goes16_sgps_replay.csv"
        self._write_replay_csv(replay_path, all_rows_wide, np)
        result.output_files.append(str(replay_path))

        logger.info(
            "noaa_converter.batch_complete",
            files_converted=result.files_converted,
            files_skipped=result.files_skipped,
            total_readings=result.total_readings,
            output_files=len(result.output_files),
        )

        return result

    def convert_single(
        self,
        nc_path: str | Path,
        output_dir: str | Path,
    ) -> ConversionResult:
        """Convert a single netCDF file to CSV.

        Convenience method when you only need one file converted.
        """
        np = _import_numpy()
        nc4 = _import_netcdf4()

        nc_path = Path(nc_path)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        result = ConversionResult()

        try:
            day_result = self._convert_single_file(nc_path, output_path, nc4, np)
            if day_result is None:
                result.files_skipped += 1
                return result

            timestamps, rows_wide, rows_long, columns, missing_count = day_result
            result.files_converted = 1
            result.total_readings = len(timestamps)
            result.missing_values_replaced = missing_count

        except Exception as exc:
            result.errors.append(f"{nc_path.name}: {exc}")
            result.files_skipped = 1

        return result

    def _convert_single_file(
        self,
        nc_path: Path,
        output_dir: Path,
        nc4: Any,
        np: Any,
    ) -> tuple[list[float], list[dict[str, Any]], list[tuple[str, str, float]], list[str], int] | None:
        """Convert one netCDF file, write per-day CSVs, return accumulated data.

        Returns:
            (timestamps, wide_rows, long_rows, channel_columns, missing_count)
            or None if the file cannot be processed.
        """
        ds = nc4.Dataset(str(nc_path), "r")
        try:
            return self._extract_and_write(ds, nc_path, output_dir, np)
        finally:
            ds.close()

    def _extract_and_write(
        self,
        ds: Any,
        nc_path: Path,
        output_dir: Path,
        np: Any,
    ) -> tuple[list[float], list[dict[str, Any]], list[tuple[str, str, float]], list[str], int] | None:
        """Core extraction logic from an open netCDF4 Dataset."""
        # Validate expected variables exist
        required_vars = ["time", "AvgDiffProtonFlux", "AvgIntProtonFlux"]
        for var_name in required_vars:
            if var_name not in ds.variables:
                logger.warning(
                    "noaa_converter.missing_variable",
                    file=nc_path.name,
                    variable=var_name,
                )
                return None

        su = self._sensor_unit

        # --- Extract time axis ---
        time_var = ds.variables["time"]
        raw_times = time_var[:]  # seconds since J2000
        fill_val = getattr(time_var, "_FillValue", -1e31)

        # --- Extract channel metadata ---
        proton_meta = self._extract_proton_metadata(ds, su, np)

        # --- Extract proton differential flux: shape (time, sensor_units, 13) ---
        diff_flux_raw = ds.variables["AvgDiffProtonFlux"][:, su, :]
        diff_fill = getattr(ds.variables["AvgDiffProtonFlux"], "_FillValue", -1e31)

        # --- Extract proton integral flux: shape (time, sensor_units) ---
        int_flux_raw = ds.variables["AvgIntProtonFlux"][:, su]
        int_fill = getattr(ds.variables["AvgIntProtonFlux"], "_FillValue", -1e31)

        # --- Optional: uncertainties ---
        diff_uncert_raw = None
        int_uncert_raw = None
        if self._include_uncertainties:
            if "AvgDiffProtonFluxUncert" in ds.variables:
                diff_uncert_raw = ds.variables["AvgDiffProtonFluxUncert"][:, su, :]
            if "AvgIntProtonFluxUncert" in ds.variables:
                int_uncert_raw = ds.variables["AvgIntProtonFluxUncert"][:, su]

        # --- Optional: alpha particles ---
        alpha_meta: list[ChannelMetadata] = []
        alpha_flux_raw = None
        if self._include_alpha and "AvgDiffAlphaFlux" in ds.variables:
            alpha_meta = self._extract_alpha_metadata(ds, su, np)
            alpha_flux_raw = ds.variables["AvgDiffAlphaFlux"][:, su, :]

        # --- Build channel column list ---
        channel_columns: list[str] = []
        for meta in proton_meta:
            channel_columns.append(meta.csv_column)
        channel_columns.append(f"proton_P11_integral_{'west' if su == 0 else 'east'}")

        if self._include_uncertainties:
            for meta in proton_meta:
                channel_columns.append(f"{meta.csv_column}_uncert")
            channel_columns.append(
                f"proton_P11_integral_{'west' if su == 0 else 'east'}_uncert"
            )

        for meta in alpha_meta:
            side = "west" if su == 0 else "east"
            channel_columns.append(f"alpha_{meta.name}_{side}")

        # --- Process rows ---
        timestamps: list[float] = []
        rows_wide: list[dict[str, Any]] = []
        rows_long: list[tuple[str, str, float]] = []
        missing_count = 0
        n_times = len(raw_times)

        # Mask fill values -> NaN
        # SGPS fill values are huge negatives (~-1e30). Real proton/alpha fluxes
        # are always positive, so any value < -1e20 is unambiguously a fill.
        # This is more robust than np.isclose against float32/64 rounding.
        _FILL_THRESHOLD = -1e20

        diff_flux = np.where(
            diff_flux_raw < _FILL_THRESHOLD,
            np.nan,
            diff_flux_raw,
        ).astype(np.float64)

        int_flux = np.where(
            int_flux_raw < _FILL_THRESHOLD,
            np.nan,
            int_flux_raw,
        ).astype(np.float64)

        if diff_uncert_raw is not None:
            diff_uncert = np.where(
                diff_uncert_raw < _FILL_THRESHOLD,
                np.nan,
                diff_uncert_raw,
            ).astype(np.float64)
        else:
            diff_uncert = None

        if int_uncert_raw is not None:
            int_uncert = np.where(
                int_uncert_raw < _FILL_THRESHOLD,
                np.nan,
                int_uncert_raw,
            ).astype(np.float64)
        else:
            int_uncert = None

        if alpha_flux_raw is not None:
            alpha_flux = np.where(
                alpha_flux_raw < _FILL_THRESHOLD,
                np.nan,
                alpha_flux_raw,
            ).astype(np.float64)
        else:
            alpha_flux = None

        # Apply fill strategy
        missing_count = int(
            np.count_nonzero(np.isnan(diff_flux))
            + np.count_nonzero(np.isnan(int_flux))
        )

        if self._fill_strategy == "zero":
            diff_flux = np.nan_to_num(diff_flux, nan=0.0)
            int_flux = np.nan_to_num(int_flux, nan=0.0)
            if diff_uncert is not None:
                diff_uncert = np.nan_to_num(diff_uncert, nan=0.0)
            if int_uncert is not None:
                int_uncert = np.nan_to_num(int_uncert, nan=0.0)
            if alpha_flux is not None:
                alpha_flux = np.nan_to_num(alpha_flux, nan=0.0)
        elif self._fill_strategy == "interpolate":
            diff_flux = self._interpolate_nans(diff_flux, np)
            int_flux_2d = int_flux.reshape(-1, 1)
            int_flux = self._interpolate_nans(int_flux_2d, np).ravel()
            if diff_uncert is not None:
                diff_uncert = self._interpolate_nans(diff_uncert, np)
            if int_uncert is not None:
                int_uncert_2d = int_uncert.reshape(-1, 1)
                int_uncert = self._interpolate_nans(int_uncert_2d, np).ravel()
            if alpha_flux is not None:
                alpha_flux = self._interpolate_nans(alpha_flux, np)

        # Build rows
        int_col_name = f"proton_P11_integral_{'west' if su == 0 else 'east'}"

        for i in range(n_times):
            t_j2000 = float(raw_times[i])
            if t_j2000 < _FILL_THRESHOLD:
                continue

            t_unix = t_j2000 + _J2000_UNIX_OFFSET
            t_iso = datetime.fromtimestamp(t_unix, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

            # Check if entire row is NaN (drop strategy)
            row_diff = diff_flux[i, :]
            row_int = float(int_flux[i])
            if self._fill_strategy == "drop":
                if np.all(np.isnan(row_diff)) and np.isnan(row_int):
                    continue

            # Wide row
            row: dict[str, Any] = {
                "timestamp": t_iso,
                "time_offset_s": f"{t_j2000:.1f}",
            }
            for ch_idx, meta in enumerate(proton_meta):
                val = float(row_diff[ch_idx])
                row[meta.csv_column] = self._format_flux(val)

            row[int_col_name] = self._format_flux(row_int)

            if self._include_uncertainties and diff_uncert is not None:
                for ch_idx, meta in enumerate(proton_meta):
                    row[f"{meta.csv_column}_uncert"] = self._format_flux(
                        float(diff_uncert[i, ch_idx])
                    )
                if int_uncert is not None:
                    row[f"{int_col_name}_uncert"] = self._format_flux(
                        float(int_uncert[i])
                    )

            if alpha_flux is not None:
                side = "west" if su == 0 else "east"
                for ch_idx, meta in enumerate(alpha_meta):
                    col = f"alpha_{meta.name}_{side}"
                    row[col] = self._format_flux(float(alpha_flux[i, ch_idx]))

            rows_wide.append(row)
            timestamps.append(t_j2000)

            # Long rows — one per channel per timestamp
            for ch_idx, meta in enumerate(proton_meta):
                val = float(row_diff[ch_idx])
                if not np.isnan(val):
                    rows_long.append((t_iso, meta.csv_column, val))

            if not np.isnan(row_int):
                rows_long.append((t_iso, int_col_name, row_int))

            if alpha_flux is not None:
                side = "west" if su == 0 else "east"
                for ch_idx, meta in enumerate(alpha_meta):
                    aval = float(alpha_flux[i, ch_idx])
                    if not np.isnan(aval):
                        rows_long.append((t_iso, f"alpha_{meta.name}_{side}", aval))

        # Write per-day CSVs
        date_str = self._extract_date_from_filename(nc_path.name)
        day_wide_path = output_dir / f"goes16_sgps_{date_str}_wide.csv"
        self._write_wide_csv(day_wide_path, rows_wide, channel_columns)

        day_long_path = output_dir / f"goes16_sgps_{date_str}_long.csv"
        self._write_long_csv(day_long_path, rows_long)

        return timestamps, rows_wide, rows_long, channel_columns, missing_count

    def _extract_proton_metadata(
        self, ds: Any, sensor_unit: int, np: Any
    ) -> list[ChannelMetadata]:
        """Extract energy band metadata for differential proton channels."""
        metadata: list[ChannelMetadata] = []
        lower = ds.variables["DiffProtonLowerEnergy"][sensor_unit, :]
        upper = ds.variables["DiffProtonUpperEnergy"][sensor_unit, :]
        effective = ds.variables["DiffProtonEffectiveEnergy"][sensor_unit, :]

        for i, name in enumerate(PROTON_DIFF_CHANNEL_NAMES):
            metadata.append(ChannelMetadata(
                name=name,
                lower_energy_kev=float(lower[i]),
                upper_energy_kev=float(upper[i]),
                effective_energy_kev=float(effective[i]),
                units="protons/(cm^2 sr keV s)",
                sensor_unit=sensor_unit,
            ))
        return metadata

    def _extract_alpha_metadata(
        self, ds: Any, sensor_unit: int, np: Any
    ) -> list[ChannelMetadata]:
        """Extract energy band metadata for differential alpha channels."""
        metadata: list[ChannelMetadata] = []
        lower = ds.variables["DiffAlphaLowerEnergy"][sensor_unit, :]
        upper = ds.variables["DiffAlphaUpperEnergy"][sensor_unit, :]
        effective = ds.variables["DiffAlphaEffectiveEnergy"][sensor_unit, :]

        for i, name in enumerate(ALPHA_DIFF_CHANNEL_NAMES):
            metadata.append(ChannelMetadata(
                name=name,
                lower_energy_kev=float(lower[i]),
                upper_energy_kev=float(upper[i]),
                effective_energy_kev=float(effective[i]),
                units="alphas/(cm^2 sr keV s)",
                sensor_unit=sensor_unit,
            ))
        return metadata

    @staticmethod
    def _interpolate_nans(data: Any, np: Any) -> Any:
        """Linear interpolation along the time axis for NaN values.

        Edge NaNs are forward/backward filled. If an entire column is NaN,
        it remains NaN.
        """
        result = data.copy()
        n_rows, n_cols = result.shape

        for col in range(n_cols):
            series = result[:, col]
            nans = np.isnan(series)
            if np.all(nans):
                continue
            if not np.any(nans):
                continue

            valid_idx = np.where(~nans)[0]
            valid_vals = series[valid_idx]

            # Interpolate
            all_idx = np.arange(n_rows)
            interpolated = np.interp(all_idx, valid_idx, valid_vals)
            result[:, col] = interpolated

        return result

    @staticmethod
    def _format_flux(value: float) -> str:
        """Format a flux value for CSV output."""
        import math

        if math.isnan(value):
            return ""
        return f"{value:.8e}"

    @staticmethod
    def _extract_date_from_filename(filename: str) -> str:
        """Extract date string from SGPS filename.

        Expected pattern: sci_sgps-l2-avg1m_g16_d20250301_v3-0-2.nc
        Returns: '20250301'
        """
        parts = filename.replace(".nc", "").split("_")
        for part in parts:
            if part.startswith("d") and len(part) == 9 and part[1:].isdigit():
                return part[1:]  # Strip the 'd' prefix
        # Fallback: use the stem
        return filename.replace(".nc", "")

    @staticmethod
    def _write_wide_csv(
        path: Path,
        rows: list[dict[str, Any]],
        channel_columns: list[str],
    ) -> None:
        """Write wide-format CSV (one column per channel)."""
        if not rows:
            return

        fieldnames = ["timestamp", "time_offset_s"] + channel_columns

        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    @staticmethod
    def _write_long_csv(
        path: Path,
        rows: list[tuple[str, str, float]],
    ) -> None:
        """Write long-format CSV (timestamp, channel_name, value)."""
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "channel_name", "value"])
            for ts, channel, value in rows:
                writer.writerow([ts, channel, f"{value:.8e}"])

    @staticmethod
    def _write_replay_csv(
        path: Path,
        rows_wide: list[dict[str, Any]],
        np: Any,
    ) -> None:
        """Write DataReplayEngine-compatible CSV.

        Produces the same columns as the existing goes16_proton_flux_*.csv:
            time_offset_s, total_proton_flux, dose_rate_usv_hr

        total_proton_flux: sum of all differential proton channel fluxes
        dose_rate_usv_hr: rough dose rate estimate from total flux.
            Conversion uses a simplified model: dose_rate ~ total_flux * 1000
            (scaled to match the existing data convention in ARIA).
        """
        import math

        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time_offset_s", "total_proton_flux", "dose_rate_usv_hr"])

            for row in rows_wide:
                time_offset = row["time_offset_s"]

                # Sum all proton differential flux channels
                total_flux = 0.0
                any_valid = False
                for key, val in row.items():
                    if key.startswith("proton_P") and "_uncert" not in key and val != "":
                        try:
                            fval = float(val)
                            if not math.isnan(fval):
                                total_flux += fval
                                any_valid = True
                        except (ValueError, TypeError):
                            continue

                if not any_valid:
                    continue

                # Dose rate: scale total flux to match existing ARIA convention
                # The existing CSV shows dose_rate ~ total_flux * 1000
                dose_rate = total_flux * 1000.0

                writer.writerow([
                    time_offset,
                    f"{total_flux:.8e}",
                    f"{dose_rate:.4f}",
                ])


def convert_goes_directory(
    input_dir: str = "data/raw/noaa_goes",
    output_dir: str = "data/processed/noaa_goes",
    sensor_unit: int = SENSOR_WEST,
    include_alpha: bool = False,
    fill_strategy: str = "nan",
) -> ConversionResult:
    """Convenience function for command-line or scripted usage.

    Args:
        input_dir: Path to directory with .nc files.
        output_dir: Path to write CSVs.
        sensor_unit: 0=West, 1=East.
        include_alpha: Include alpha particle channels.
        fill_strategy: "nan", "drop", "zero", or "interpolate".

    Returns:
        ConversionResult with statistics.
    """
    converter = NOAAGoesConverter(
        sensor_unit=sensor_unit,
        include_alpha=include_alpha,
        fill_strategy=fill_strategy,
    )
    return converter.convert_directory(input_dir, output_dir)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Convert NOAA GOES-16 SGPS netCDF files to ARIA-compatible CSV",
    )
    parser.add_argument(
        "--input-dir", "-i",
        default="data/raw/noaa_goes",
        help="Directory containing .nc files (default: data/raw/noaa_goes)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="data/processed/noaa_goes",
        help="Output directory for CSVs (default: data/processed/noaa_goes)",
    )
    parser.add_argument(
        "--sensor", "-s",
        type=int, default=0, choices=[0, 1],
        help="Sensor unit: 0=West (default), 1=East",
    )
    parser.add_argument(
        "--include-alpha", action="store_true",
        help="Include alpha particle channels",
    )
    parser.add_argument(
        "--fill-strategy", "-f",
        default="nan", choices=["nan", "drop", "zero", "interpolate"],
        help="Missing value strategy (default: nan)",
    )

    args = parser.parse_args()

    result = convert_goes_directory(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        sensor_unit=args.sensor,
        include_alpha=args.include_alpha,
        fill_strategy=args.fill_strategy,
    )

    print(f"\nConversion complete:")
    print(f"  Files converted: {result.files_converted}")
    print(f"  Files skipped:   {result.files_skipped}")
    print(f"  Total readings:  {result.total_readings}")
    print(f"  Missing values:  {result.missing_values_replaced}")
    print(f"  Output files:    {len(result.output_files)}")
    for path in result.output_files:
        print(f"    - {path}")
    if result.errors:
        print(f"  Errors:")
        for err in result.errors:
            print(f"    - {err}")
        sys.exit(1)
