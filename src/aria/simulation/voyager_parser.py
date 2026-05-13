"""Voyager PLS (Plasma Science) Data Parser for ARIA.

Parses NASA Voyager 1 and Voyager 2 Plasma Science experiment data and converts
it to CSV timeseries compatible with ARIA's DataReplayEngine.

Voyager PLS data comes from NASA PDS / LASP in two common formats:
  1. Daily-average ASCII tables (fixed-width or space-delimited) with columns for
     year, day-of-year, hour, plasma density (n/cm^3), speed (km/s), and
     temperature (K).  Some files include Faraday cup currents in femto-amps.
  2. Hourly-resolution ASCII with additional fields (flow angles, component
     velocities, etc.).

This parser handles both and normalises them into a consistent schema for
ARIA bus replay as navigation / radiation-environment telemetry.

Data sources:
  - NASA PDS PPI: https://pds-ppi.igpp.ucla.edu/
  - LASP Interactive Solar Irradiance Datacenter (Voyager section)
  - Format documentation: Voyager PLS User's Guide (MIT/GSFC)

Supported spacecraft: Voyager 1 ("V1"), Voyager 2 ("V2").
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import structlog

from aria.bus.message_bus import Message, MessageBus
from aria.core.types import EventPriority

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Physical constants used for unit conversions
# ---------------------------------------------------------------------------
BOLTZMANN_K = 1.380649e-23       # J/K
PROTON_MASS = 1.67262192e-27     # kg
EV_TO_KELVIN = 11604.518         # 1 eV = 11604.518 K
FEMTOAMP_TO_AMP = 1e-15          # fA -> A

# Voyager PLS fill/missing-data sentinel values used by NASA PDS
FILL_VALUES = {9999.0, 9999.9, 99999.0, 99999.9, 999.99, 9.999e5, 1e32, -1e31}

# ---------------------------------------------------------------------------
# ARIA bus topic mapping for Voyager measurements
# ---------------------------------------------------------------------------
VOYAGER_CHANNEL_MAP: dict[str, dict[str, Any]] = {
    "plasma_density": {
        "topic": "aria.sensor.navigation.plasma",
        "key": "plasma_density_per_cm3",
        "unit": "particles/cm^3",
        "description": "Solar wind / ISM proton density from PLS Faraday cups",
    },
    "plasma_speed": {
        "topic": "aria.sensor.navigation.plasma",
        "key": "plasma_speed_km_s",
        "unit": "km/s",
        "description": "Bulk plasma flow speed (radial component dominant)",
    },
    "plasma_temperature": {
        "topic": "aria.sensor.navigation.plasma",
        "key": "plasma_temperature_k",
        "unit": "K",
        "description": "Proton temperature derived from Faraday cup current spectrum",
    },
    "plasma_pressure": {
        "topic": "aria.sensor.science.radiation",
        "key": "plasma_pressure_npa",
        "unit": "nPa",
        "description": "Dynamic plasma pressure (derived: 0.5 * n * m_p * v^2)",
    },
    "heliocentric_distance": {
        "topic": "aria.sensor.navigation.position",
        "key": "heliocentric_distance_au",
        "unit": "AU",
        "description": "Spacecraft distance from Sun (from trajectory files)",
    },
}


@dataclass(frozen=True)
class VoyagerReading:
    """A single parsed Voyager PLS measurement."""

    spacecraft: str                    # "V1" or "V2"
    timestamp: datetime                # UTC
    density_per_cm3: float | None      # proton density [particles / cm^3]
    speed_km_s: float | None           # bulk speed [km/s]
    temperature_k: float | None        # proton temperature [K]
    heliocentric_distance_au: float | None = None  # [AU] if available
    current_femtoamp: float | None = None  # raw Faraday cup current [fA]

    @property
    def pressure_npa(self) -> float | None:
        """Dynamic plasma pressure in nanopascals: P = 0.5 * n * m_p * v^2."""
        if self.density_per_cm3 is None or self.speed_km_s is None:
            return None
        n_m3 = self.density_per_cm3 * 1e6      # cm^-3 -> m^-3
        v_ms = self.speed_km_s * 1e3            # km/s -> m/s
        pressure_pa = 0.5 * n_m3 * PROTON_MASS * v_ms * v_ms
        return pressure_pa * 1e9                # Pa -> nPa

    @property
    def is_valid(self) -> bool:
        """True if at least one physical measurement is present and non-fill."""
        return any(v is not None for v in (
            self.density_per_cm3, self.speed_km_s, self.temperature_k,
        ))


@dataclass
class VoyagerDataset:
    """Collection of parsed Voyager readings with summary statistics."""

    spacecraft: str
    readings: list[VoyagerReading] = field(default_factory=list)
    parse_errors: int = 0
    fill_values_skipped: int = 0

    @property
    def valid_readings(self) -> list[VoyagerReading]:
        return [r for r in self.readings if r.is_valid]

    @property
    def time_range(self) -> tuple[datetime | None, datetime | None]:
        valid = self.valid_readings
        if not valid:
            return None, None
        return valid[0].timestamp, valid[-1].timestamp

    def summary(self) -> dict[str, Any]:
        valid = self.valid_readings
        densities = [r.density_per_cm3 for r in valid if r.density_per_cm3 is not None]
        speeds = [r.speed_km_s for r in valid if r.speed_km_s is not None]
        temps = [r.temperature_k for r in valid if r.temperature_k is not None]
        t_start, t_end = self.time_range
        return {
            "spacecraft": self.spacecraft,
            "total_readings": len(self.readings),
            "valid_readings": len(valid),
            "parse_errors": self.parse_errors,
            "fill_values_skipped": self.fill_values_skipped,
            "time_start": t_start.isoformat() if t_start else None,
            "time_end": t_end.isoformat() if t_end else None,
            "density_range": (min(densities), max(densities)) if densities else None,
            "speed_range": (min(speeds), max(speeds)) if speeds else None,
            "temperature_range": (min(temps), max(temps)) if temps else None,
        }


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _is_fill(value: float) -> bool:
    """Check if a numeric value is a NASA PDS fill/missing sentinel."""
    if math.isnan(value) or math.isinf(value):
        return True
    return any(abs(value - fv) < 0.1 for fv in FILL_VALUES)


def _safe_float(raw: str) -> float | None:
    """Parse a float, returning None for fill values or unparseable strings."""
    raw = raw.strip()
    if not raw or raw in ("", "-", "N/A", "nan", "NaN"):
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    if _is_fill(val):
        return None
    return val


def _doy_to_datetime(year: int, doy: int, hour: int = 0,
                     minute: int = 0, second: int = 0) -> datetime:
    """Convert year + day-of-year to a UTC datetime."""
    base = datetime(year, 1, 1, hour, minute, second, tzinfo=timezone.utc)
    return base + timedelta(days=doy - 1)


def _decimal_year_to_datetime(decimal_year: float) -> datetime:
    """Convert decimal year (e.g. 2012.5432) to UTC datetime."""
    year = int(decimal_year)
    remainder = decimal_year - year
    base = datetime(year, 1, 1, tzinfo=timezone.utc)
    year_length = (datetime(year + 1, 1, 1, tzinfo=timezone.utc) - base).total_seconds()
    return base + timedelta(seconds=remainder * year_length)


# ---------------------------------------------------------------------------
# Format-specific parsers
# ---------------------------------------------------------------------------

def _detect_format(lines: list[str]) -> str:
    """Detect the Voyager PLS data format from file content.

    Returns one of:
        "daily_avg"   - Daily averages (year, doy, density, speed, temp)
        "hourly"      - Hourly resolution (year, doy, hour, ...)
        "pds_table"   - PDS fixed-width table with header
        "femtoamp"    - Raw Faraday cup currents in femto-amps
        "csv"         - Already in CSV format
        "unknown"
    """
    # Skip blank/comment lines to find data
    data_lines = [l for l in lines if l.strip() and not l.strip().startswith("#")]
    if not data_lines:
        return "unknown"

    first_data = data_lines[0]

    # CSV detection
    if "," in first_data and any(h in lines[0].lower() for h in
                                  ("density", "speed", "temperature", "time")):
        return "csv"

    # Check for PDS table header markers
    for line in lines[:30]:
        ll = line.lower()
        if "pds_version_id" in ll or "object = table" in ll:
            return "pds_table"

    # Check for femto-amp current columns (very small float values with e-notation)
    if re.search(r"\d+\.\d+[eE][+-]?\d+", first_data):
        tokens = first_data.split()
        # Femto-amp files typically have many columns of small exponent values
        exp_count = sum(1 for t in tokens if re.match(r"[+-]?\d+\.\d+[eE][+-]?\d+$", t))
        if exp_count >= 3:
            return "femtoamp"

    # Count numeric columns
    tokens = first_data.split()
    if len(tokens) >= 5:
        # Check if first two look like year/doy
        try:
            yr = int(tokens[0])
            doy = int(tokens[1])
            if 1977 <= yr <= 2030 and 1 <= doy <= 366:
                # Third column: could be hour (0-23) or density
                third = float(tokens[2])
                if 0 <= third <= 23 and third == int(third):
                    return "hourly"
                return "daily_avg"
        except (ValueError, IndexError):
            pass

    # Decimal year format (e.g. 2012.1234)
    try:
        first_val = float(tokens[0])
        if 1977.0 <= first_val <= 2030.0:
            return "daily_avg"
    except (ValueError, IndexError):
        pass

    return "unknown"


def _parse_daily_avg(lines: list[str], spacecraft: str) -> VoyagerDataset:
    """Parse daily-average format: year doy [hour] density speed temperature [distance].

    Also handles decimal-year first column.
    """
    dataset = VoyagerDataset(spacecraft=spacecraft)

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("*"):
            continue
        tokens = line.split()
        if len(tokens) < 4:
            dataset.parse_errors += 1
            continue

        try:
            # Detect decimal year vs integer year
            first = float(tokens[0])
            if first > 2100 or first < 1970:
                dataset.parse_errors += 1
                continue

            if "." in tokens[0] and float(tokens[0]) != int(float(tokens[0])):
                # Decimal year format
                ts = _decimal_year_to_datetime(first)
                col_offset = 1
            else:
                year = int(first)
                doy = int(tokens[1])
                # Detect if third column is hour
                col_offset = 2
                hour = 0
                if len(tokens) >= 6:
                    try:
                        maybe_hour = float(tokens[2])
                        if 0 <= maybe_hour <= 23 and maybe_hour == int(maybe_hour):
                            hour = int(maybe_hour)
                            col_offset = 3
                    except ValueError:
                        pass
                ts = _doy_to_datetime(year, doy, hour)

            density = _safe_float(tokens[col_offset]) if col_offset < len(tokens) else None
            speed = _safe_float(tokens[col_offset + 1]) if col_offset + 1 < len(tokens) else None
            temp = _safe_float(tokens[col_offset + 2]) if col_offset + 2 < len(tokens) else None
            distance = _safe_float(tokens[col_offset + 3]) if col_offset + 3 < len(tokens) else None

            # Track fill values
            raw_vals = tokens[col_offset:col_offset + 3]
            for rv in raw_vals:
                v = _safe_float(rv)
                if v is None and rv.strip() not in ("", "-"):
                    try:
                        float(rv)
                        dataset.fill_values_skipped += 1
                    except ValueError:
                        pass

            reading = VoyagerReading(
                spacecraft=spacecraft,
                timestamp=ts,
                density_per_cm3=density,
                speed_km_s=speed,
                temperature_k=temp,
                heliocentric_distance_au=distance,
            )
            dataset.readings.append(reading)

        except (ValueError, IndexError):
            dataset.parse_errors += 1

    return dataset


def _parse_femtoamp(lines: list[str], spacecraft: str) -> VoyagerDataset:
    """Parse raw Faraday cup current data in femto-amps.

    These files contain time columns followed by current measurements from
    multiple Faraday cup channels.  We derive approximate plasma parameters
    from the total collected current using PLS calibration relationships.

    The dominant current collector (main cup, D-cup side A) gives:
        I_total ~ n_e * e * v * A_eff
    where A_eff ~ 100 cm^2 for the Voyager PLS main cup.
    """
    dataset = VoyagerDataset(spacecraft=spacecraft)
    A_EFF_CM2 = 100.0       # Effective area of main Faraday cup [cm^2]
    A_EFF_M2 = A_EFF_CM2 * 1e-4
    ELECTRON_CHARGE = 1.602176634e-19  # C

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("*"):
            continue
        tokens = line.split()
        if len(tokens) < 5:
            dataset.parse_errors += 1
            continue

        try:
            # Time columns: year, doy, hour (or decimal year)
            first = float(tokens[0])
            col_offset = 0
            hour = 0

            if "." in tokens[0] and first != int(first):
                ts = _decimal_year_to_datetime(first)
                col_offset = 1
            else:
                year = int(first)
                doy = int(tokens[1])
                col_offset = 2
                if len(tokens) > 5:
                    try:
                        maybe_hour = float(tokens[2])
                        if 0 <= maybe_hour <= 23:
                            hour = int(maybe_hour)
                            col_offset = 3
                    except ValueError:
                        pass
                ts = _doy_to_datetime(year, doy, hour)

            # Remaining columns are current values in scientific notation
            currents_fa = []
            for t in tokens[col_offset:]:
                val = _safe_float(t)
                if val is not None and val > 0:
                    currents_fa.append(val)

            if not currents_fa:
                dataset.fill_values_skipped += 1
                continue

            # Peak current -> approximate density and speed
            peak_current_fa = max(currents_fa)
            total_current_fa = sum(currents_fa)
            peak_current_a = peak_current_fa * FEMTOAMP_TO_AMP

            # For a Maxwellian distribution incident on a Faraday cup:
            #   I = n * e * v * A_eff
            # Assume nominal solar wind speed to bootstrap density
            # (iterative refinement possible but overkill for replay).
            assumed_speed_km_s = 400.0  # Typical solar wind speed
            assumed_speed_m_s = assumed_speed_km_s * 1e3

            # Density from peak current
            if peak_current_a > 0 and assumed_speed_m_s > 0:
                n_m3 = peak_current_a / (ELECTRON_CHARGE * assumed_speed_m_s * A_EFF_M2)
                density = n_m3 * 1e-6  # m^-3 -> cm^-3
            else:
                density = None

            # Width of the current distribution -> temperature
            # Rough: T ~ (width/peak)^2 * m_p * v^2 / (2*k)
            if len(currents_fa) >= 3:
                mean_current = total_current_fa / len(currents_fa)
                variance = sum((c - mean_current) ** 2 for c in currents_fa) / len(currents_fa)
                width_ratio = math.sqrt(variance) / peak_current_fa if peak_current_fa > 0 else 0
                temperature = width_ratio ** 2 * PROTON_MASS * assumed_speed_m_s ** 2 / (2 * BOLTZMANN_K)
                # Clamp to physically reasonable range
                if temperature < 1e3 or temperature > 1e8:
                    temperature = None
            else:
                temperature = None

            reading = VoyagerReading(
                spacecraft=spacecraft,
                timestamp=ts,
                density_per_cm3=density,
                speed_km_s=assumed_speed_km_s,
                temperature_k=temperature,
                current_femtoamp=peak_current_fa,
            )
            dataset.readings.append(reading)

        except (ValueError, IndexError):
            dataset.parse_errors += 1

    return dataset


def _parse_csv_format(lines: list[str], spacecraft: str) -> VoyagerDataset:
    """Parse already-CSV-formatted Voyager data."""
    dataset = VoyagerDataset(spacecraft=spacecraft)

    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    if reader.fieldnames is None:
        return dataset

    # Normalise column names
    col_map: dict[str, str] = {}
    for col in reader.fieldnames:
        lc = col.lower().strip()
        if "density" in lc or "n_p" in lc:
            col_map["density"] = col
        elif "speed" in lc or "velocity" in lc or "v_p" in lc:
            col_map["speed"] = col
        elif "temp" in lc or "t_p" in lc:
            col_map["temperature"] = col
        elif "dist" in lc or "au" in lc:
            col_map["distance"] = col
        elif "time" in lc or "date" in lc or "year" in lc:
            col_map["time"] = col

    for row in reader:
        try:
            # Time parsing — try multiple formats
            ts = None
            time_val = row.get(col_map.get("time", ""), "").strip()
            if time_val:
                for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                            "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
                    try:
                        ts = datetime.strptime(time_val, fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue
                if ts is None:
                    # Try decimal year
                    try:
                        ts = _decimal_year_to_datetime(float(time_val))
                    except ValueError:
                        pass

            if ts is None:
                dataset.parse_errors += 1
                continue

            density = _safe_float(row.get(col_map.get("density", ""), ""))
            speed = _safe_float(row.get(col_map.get("speed", ""), ""))
            temp = _safe_float(row.get(col_map.get("temperature", ""), ""))
            dist = _safe_float(row.get(col_map.get("distance", ""), ""))

            reading = VoyagerReading(
                spacecraft=spacecraft,
                timestamp=ts,
                density_per_cm3=density,
                speed_km_s=speed,
                temperature_k=temp,
                heliocentric_distance_au=dist,
            )
            dataset.readings.append(reading)

        except (ValueError, KeyError):
            dataset.parse_errors += 1

    return dataset


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_spacecraft(filepath: Path) -> str:
    """Guess spacecraft from filename: 'v1' -> 'V1', 'v2'/'vg2' -> 'V2'."""
    name = filepath.stem.lower()
    if "v1" in name or "vg1" in name or "voyager1" in name or "voyager_1" in name:
        return "V1"
    if "v2" in name or "vg2" in name or "voyager2" in name or "voyager_2" in name:
        return "V2"
    # Check parent directory chain (up to 2 levels)
    for ancestor in (filepath.parent, filepath.parent.parent):
        aname = ancestor.name.lower()
        if "v2" in aname or "vg2" in aname or "voyager2" in aname or "voyager_2" in aname:
            return "V2"
        if "v1" in aname or "vg1" in aname or "voyager1" in aname or "voyager_1" in aname:
            return "V1"
    return "V1"  # Default


def parse_voyager_file(filepath: Path | str, spacecraft: str | None = None) -> VoyagerDataset:
    """Parse a single Voyager PLS data file.

    Args:
        filepath: Path to a Voyager PLS data file (TXT, TAB, CSV, or DAT).
        spacecraft: "V1" or "V2".  Auto-detected from filename if not given.

    Returns:
        VoyagerDataset with parsed readings.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file format cannot be determined.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Voyager data file not found: {filepath}")

    if spacecraft is None:
        spacecraft = detect_spacecraft(filepath)

    text = filepath.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    if not lines:
        return VoyagerDataset(spacecraft=spacecraft)

    fmt = _detect_format(lines)
    logger.debug("voyager.parse.format_detected", file=str(filepath), format=fmt)

    if fmt == "csv":
        return _parse_csv_format(lines, spacecraft)
    elif fmt == "femtoamp":
        return _parse_femtoamp(lines, spacecraft)
    elif fmt in ("daily_avg", "hourly"):
        return _parse_daily_avg(lines, spacecraft)
    elif fmt == "pds_table":
        # PDS tables have a header section; skip to data lines
        data_start = 0
        for i, line in enumerate(lines):
            if line.strip().upper() in ("END_OBJECT", "END"):
                data_start = i + 1
                break
        return _parse_daily_avg(lines[data_start:], spacecraft)
    else:
        raise ValueError(
            f"Cannot determine Voyager PLS data format for {filepath}. "
            f"Expected daily_avg, hourly, femtoamp, csv, or pds_table format."
        )


def parse_voyager_directory(data_dir: Path | str,
                            spacecraft: str | None = None) -> VoyagerDataset:
    """Parse all Voyager PLS data files in a directory.

    Scans for .txt, .tab, .csv, and .dat files, parses each, and merges
    into a single VoyagerDataset sorted by timestamp.

    Args:
        data_dir: Directory containing Voyager PLS data files.
        spacecraft: "V1" or "V2".  Auto-detected per file if not given.

    Returns:
        Merged VoyagerDataset.
    """
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise NotADirectoryError(f"Not a directory: {data_dir}")

    extensions = {".txt", ".tab", ".csv", ".dat", ".asc"}
    files = sorted(
        f for f in data_dir.iterdir()
        if f.suffix.lower() in extensions and f.is_file()
    )

    if not files:
        logger.warning("voyager.parse.no_files", dir=str(data_dir))
        return VoyagerDataset(spacecraft=spacecraft or "V1")

    merged = VoyagerDataset(spacecraft=spacecraft or detect_spacecraft(files[0]))

    for fp in files:
        try:
            sc = spacecraft or detect_spacecraft(fp)
            ds = parse_voyager_file(fp, spacecraft=sc)
            merged.readings.extend(ds.readings)
            merged.parse_errors += ds.parse_errors
            merged.fill_values_skipped += ds.fill_values_skipped
        except (ValueError, OSError) as exc:
            logger.warning("voyager.parse.file_error", file=str(fp), error=str(exc))
            merged.parse_errors += 1

    # Sort by timestamp
    merged.readings.sort(key=lambda r: r.timestamp)
    return merged


# ---------------------------------------------------------------------------
# CSV export (DataReplayEngine compatible)
# ---------------------------------------------------------------------------

def export_to_csv(dataset: VoyagerDataset, output_path: Path | str) -> int:
    """Export VoyagerDataset to a CSV file compatible with DataReplayEngine.

    Output columns:
        time_offset_s  — seconds since Unix epoch (matches NOAA replay format)
        plasma_density_per_cm3
        plasma_speed_km_s
        plasma_temperature_k
        plasma_pressure_npa
        heliocentric_distance_au
        spacecraft

    Args:
        dataset: Parsed Voyager data.
        output_path: Output CSV file path.

    Returns:
        Number of rows written.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "time_offset_s",
        "plasma_density_per_cm3",
        "plasma_speed_km_s",
        "plasma_temperature_k",
        "plasma_pressure_npa",
        "heliocentric_distance_au",
        "spacecraft",
    ]

    rows_written = 0
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for reading in dataset.valid_readings:
            epoch_s = reading.timestamp.timestamp()
            writer.writerow({
                "time_offset_s": f"{epoch_s:.1f}",
                "plasma_density_per_cm3": f"{reading.density_per_cm3:.6g}" if reading.density_per_cm3 is not None else "",
                "plasma_speed_km_s": f"{reading.speed_km_s:.2f}" if reading.speed_km_s is not None else "",
                "plasma_temperature_k": f"{reading.temperature_k:.1f}" if reading.temperature_k is not None else "",
                "plasma_pressure_npa": f"{reading.pressure_npa:.6g}" if reading.pressure_npa is not None else "",
                "heliocentric_distance_au": f"{reading.heliocentric_distance_au:.4f}" if reading.heliocentric_distance_au is not None else "",
                "spacecraft": reading.spacecraft,
            })
            rows_written += 1

    logger.info(
        "voyager.export.csv_complete",
        output=str(output_path),
        rows=rows_written,
        spacecraft=dataset.spacecraft,
    )
    return rows_written


def generate_synthetic_voyager_data(
    spacecraft: str = "V1",
    days: int = 365,
    start_year: int = 2012,
    start_doy: int = 1,
) -> VoyagerDataset:
    """Generate synthetic Voyager-like plasma data for testing.

    Produces physically plausible daily measurements that mimic the transition
    from solar wind to interstellar medium (for V1: ~2012 heliopause crossing).

    This is used when real data files are not available (e.g. the .zip downloads
    from LASP came as HTML pages rather than actual data).
    """
    dataset = VoyagerDataset(spacecraft=spacecraft)
    base_ts = _doy_to_datetime(start_year, start_doy)

    # V1 crossed the heliopause around day 238 of 2012 (~Aug 25, 2012).
    # Model: solar wind -> transition -> ISM
    crossing_day = 238 if spacecraft == "V1" and start_year == 2012 else days // 2

    import random
    rng = random.Random(42 if spacecraft == "V1" else 137)

    for day in range(days):
        ts = base_ts + timedelta(days=day)
        phase = day / max(crossing_day, 1)

        if phase < 0.9:
            # Solar wind regime
            base_density = 0.002 * (1 + 0.5 * math.sin(day * 0.05))
            base_speed = 400 + 50 * math.sin(day * 0.03)
            base_temp = 50000 + 20000 * math.sin(day * 0.02)
        elif phase < 1.1:
            # Transition / heliosheath
            base_density = 0.002 + 0.04 * (phase - 0.9) / 0.2
            base_speed = 400 - 350 * (phase - 0.9) / 0.2
            base_temp = 50000 + 200000 * (phase - 0.9) / 0.2
        else:
            # Interstellar medium
            base_density = 0.055 + 0.01 * math.sin(day * 0.01)
            base_speed = 26.0 + 5 * math.sin(day * 0.02)  # ISM flow ~26 km/s
            base_temp = 7500 + 1000 * math.sin(day * 0.015)  # ~7500 K in local ISM

        # Add measurement noise
        density = max(0.0001, base_density * (1 + rng.gauss(0, 0.15)))
        speed = max(1.0, base_speed * (1 + rng.gauss(0, 0.08)))
        temp = max(100.0, base_temp * (1 + rng.gauss(0, 0.12)))

        # Heliocentric distance (V1 was ~121 AU at heliopause crossing)
        distance = 120.0 + day * 0.0467  # ~17 km/s = 0.0467 AU/day roughly

        # Occasional fill values (data gaps)
        if rng.random() < 0.03:
            density = None
        if rng.random() < 0.02:
            speed = None

        dataset.readings.append(VoyagerReading(
            spacecraft=spacecraft,
            timestamp=ts,
            density_per_cm3=density,
            speed_km_s=speed,
            temperature_k=temp,
            heliocentric_distance_au=distance,
        ))

    return dataset


# ---------------------------------------------------------------------------
# ARIA bus replay integration
# ---------------------------------------------------------------------------

class VoyagerReplayEngine:
    """Replays parsed Voyager PLS data through the ARIA message bus.

    Follows the same pattern as DataReplayEngine.replay_noaa_proton_flux but
    publishes navigation/plasma and radiation-environment telemetry.
    """

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._readings_published: int = 0
        self._running = False

    @property
    def stats(self) -> dict[str, int]:
        return {"readings_published": self._readings_published}

    async def replay(
        self,
        dataset: VoyagerDataset,
        time_scale: float = 100.0,
        max_readings: int = 0,
    ) -> dict[str, int]:
        """Replay a VoyagerDataset through the ARIA bus.

        Args:
            dataset: Parsed Voyager readings.
            time_scale: Speed multiplier (100 = 100x real-time).
            max_readings: Max readings to publish (0 = unlimited).

        Returns:
            Stats dict with readings_published count.
        """
        self._running = True
        valid = dataset.valid_readings
        count = 0

        logger.info(
            "voyager.replay.starting",
            spacecraft=dataset.spacecraft,
            readings=len(valid),
            time_scale=time_scale,
        )

        for reading in valid:
            if not self._running:
                break
            if max_readings > 0 and count >= max_readings:
                break

            # Build payload
            payload: dict[str, Any] = {"spacecraft": reading.spacecraft}
            if reading.density_per_cm3 is not None:
                payload["plasma_density_per_cm3"] = reading.density_per_cm3
            if reading.speed_km_s is not None:
                payload["plasma_speed_km_s"] = reading.speed_km_s
            if reading.temperature_k is not None:
                payload["plasma_temperature_k"] = reading.temperature_k
            if reading.pressure_npa is not None:
                payload["plasma_pressure_npa"] = reading.pressure_npa
            if reading.heliocentric_distance_au is not None:
                payload["heliocentric_distance_au"] = reading.heliocentric_distance_au

            # Publish plasma navigation data
            await self._bus.publish(Message(
                topic="aria.sensor.navigation.plasma",
                payload=payload,
                priority=EventPriority.P4_BULK,
                source_agent="voyager_replay",
            ))

            # Also publish radiation-environment data if pressure available
            if reading.pressure_npa is not None:
                radiation_payload = {
                    "plasma_pressure_npa": reading.pressure_npa,
                    "dose_rate_usv_hr": self._estimate_gcr_dose(reading),
                    "spacecraft": reading.spacecraft,
                }
                await self._bus.publish(Message(
                    topic="aria.sensor.science.radiation",
                    payload=radiation_payload,
                    priority=EventPriority.P4_BULK,
                    source_agent="voyager_replay",
                ))

            self._readings_published += 1
            count += 1

            # Throttle
            if count % 20 == 0:
                await asyncio.sleep(0.01 / max(time_scale, 1))

        logger.info(
            "voyager.replay.complete",
            spacecraft=dataset.spacecraft,
            readings_published=self._readings_published,
        )
        return self.stats

    def stop(self) -> None:
        self._running = False

    @staticmethod
    def _estimate_gcr_dose(reading: VoyagerReading) -> float:
        """Estimate GCR dose rate from plasma parameters.

        Lower plasma pressure (outside heliosphere) correlates with higher GCR
        flux.  This is a simplified inverse relationship for simulation.
        In the heliosheath, solar modulation reduces GCR flux; outside it,
        the full galactic cosmic ray flux reaches the spacecraft.

        Returns dose rate in uSv/hr.
        """
        if reading.pressure_npa is None or reading.pressure_npa <= 0:
            return 50.0  # Default ISM GCR level

        # Solar wind pressure -> GCR modulation
        # High pressure (solar wind) -> low GCR (~10 uSv/hr)
        # Low pressure (ISM) -> high GCR (~50 uSv/hr)
        pressure = reading.pressure_npa
        if pressure > 0.01:
            # Inside heliosphere
            return max(5.0, 50.0 - 40.0 * min(pressure / 0.1, 1.0))
        else:
            # Outside heliosphere or heliosheath
            return 50.0 + 10.0 * min(1.0 / max(pressure, 1e-6), 100.0)


# ---------------------------------------------------------------------------
# Convenience: parse + export in one call
# ---------------------------------------------------------------------------

def process_voyager_data(
    input_path: Path | str,
    output_dir: Path | str,
    spacecraft: str | None = None,
) -> dict[str, Any]:
    """Parse Voyager data and export to ARIA-compatible CSV.

    Args:
        input_path: File or directory containing Voyager PLS data.
        output_dir: Directory for output CSV files.
        spacecraft: "V1" or "V2" (auto-detected if None).

    Returns:
        Dict with parse summary and output file paths.
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if input_path.is_dir():
        dataset = parse_voyager_directory(input_path, spacecraft)
    else:
        dataset = parse_voyager_file(input_path, spacecraft)

    sc = dataset.spacecraft.lower()
    csv_path = output_dir / f"voyager_{sc}_plasma.csv"
    rows = export_to_csv(dataset, csv_path)

    return {
        "csv_path": str(csv_path),
        "rows_written": rows,
        **dataset.summary(),
    }
