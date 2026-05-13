"""EDEN ISS Real Telemetry Loader for Dsremo Anomaly Detection.

EDEN ISS (European Development and Evolution of Nutrition for long-duration
space exploration missions) was a greenhouse module installed in the
Columbus module of the ISS in 2018. It operated through 2020.

The 2020 dataset contains real plant growth telemetry at 5-minute intervals
from January-December 2020:
  - CO2 sensors (ppm) — atmospheric CO2 concentration in grow chambers
  - Temperature (°C) — air temperature in grow sections
  - Relative Humidity (%) — humidity in grow sections
  - PAR (μmol/m²/s) — photosynthetically active radiation (grow lights)
  - VPD (kPa) — vapour pressure deficit (plant stress indicator)
  - ICS irrigation control sensors — valve state, timing

This data is a direct analog for ECLSS (Environmental Control and Life
Support) monitoring on a real spacecraft.

The dataset is publicly available at:
  Zenodo record 11485183 (Romberg et al. 2024)

Reference:
    Romberg, O. et al. (2024) EDEN ISS 2020 telemetry dataset.
    Zenodo. https://doi.org/10.5281/zenodo.11485183
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import structlog

logger = structlog.get_logger()

EDEN_ISS_BASE = Path(__file__).parent.parent.parent.parent / "data" / "raw" / "eden_iss" / "edeniss2020"


@dataclass
class TelemetryPoint:
    """A single telemetry reading from EDEN ISS."""
    timestamp: str     # ISO 8601 e.g. '2020-01-01 00:05:00'
    channel:   str     # e.g. 'ams-feg:co2-1'
    value:     float   # engineering value
    unit:      str     # 'ppm', 'degrees_celsius', 'percent', etc.


@dataclass
class ChannelStats:
    """Basic statistics for a single channel."""
    channel: str
    n_samples: int
    mean: float
    std: float
    min_val: float
    max_val: float
    n_missing: int
    n_large_jumps: int   # |delta| > 3σ
    unit: str


def _unit_for(sensor_short: str) -> str:
    """Map sensor short-name to unit string."""
    units = {
        "CO2": "ppm",
        "T":   "degrees_celsius",
        "RH":  "percent",
        "PAR": "umol_m2_s",
        "VPD": "kPa",
    }
    for key, unit in units.items():
        if key in sensor_short.upper():
            return unit
    return "unknown"


def load_channel(csv_path: Path, channel_name: str) -> list[TelemetryPoint]:
    """Load a single EDEN ISS CSV file into TelemetryPoint list.

    EDEN ISS CSV format:
        time,<sensor-name>
        2020-01-01 00:05:00,1441.0
        ...

    Args:
        csv_path:     path to the CSV file
        channel_name: logical channel name (e.g. 'ams-feg:co2-1')

    Returns:
        list of TelemetryPoint, NaN values excluded
    """
    unit = _unit_for(channel_name)
    points = []
    try:
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            col = None
            for row in reader:
                if col is None:
                    col = [k for k in row if k != "time"][0]
                raw = row.get(col, "")
                try:
                    v = float(raw)
                    if not (v != v):  # exclude NaN
                        points.append(TelemetryPoint(
                            timestamp=row["time"],
                            channel=channel_name,
                            value=v,
                            unit=unit,
                        ))
                except (ValueError, TypeError):
                    pass
    except FileNotFoundError:
        logger.warning("eden_iss.file_not_found", path=str(csv_path))
    return points


def iter_all_channels(
    base_dir: Path | None = None,
    subsystems: list[str] | None = None,
) -> Iterator[tuple[str, list[TelemetryPoint]]]:
    """Yield (channel_name, points) for all EDEN ISS channels.

    Args:
        base_dir:   override default data directory
        subsystems: filter to specific subsystem dirs
                    (e.g. ['ams-feg', 'ams-ses']); None = all

    Yields:
        (channel_name, list[TelemetryPoint]) for each CSV found
    """
    root = base_dir or EDEN_ISS_BASE
    if not root.exists():
        logger.error("eden_iss.base_dir_missing", path=str(root))
        return

    for subdir in sorted(root.iterdir()):
        if not subdir.is_dir():
            continue
        if subsystems and subdir.name not in subsystems:
            continue
        for csv_file in sorted(subdir.glob("*.csv")):
            channel = f"{subdir.name}:{csv_file.stem}"
            points = load_channel(csv_file, channel)
            if points:
                yield channel, points


def compute_channel_stats(channel: str, points: list[TelemetryPoint]) -> ChannelStats:
    """Compute basic statistics and anomaly indicators for a channel."""
    if not points:
        return ChannelStats(channel, 0, 0, 0, 0, 0, 0, 0, "unknown")

    values = [p.value for p in points]
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    std = variance ** 0.5
    threshold = 3.0 * std if std > 0 else float("inf")

    n_jumps = sum(
        1 for i in range(1, n) if abs(values[i] - values[i - 1]) > threshold
    )

    return ChannelStats(
        channel=channel,
        n_samples=n,
        mean=round(mean, 3),
        std=round(std, 3),
        min_val=min(values),
        max_val=max(values),
        n_missing=0,
        n_large_jumps=n_jumps,
        unit=points[0].unit,
    )


def load_for_dsremo(
    base_dir: Path | None = None,
    subsystems: list[str] | None = None,
    max_channels: int = 20,
) -> list[tuple[str, list[tuple[str, float]]]]:
    """Load EDEN ISS data in format suitable for Dsremo anomaly detection.

    Returns list of (channel_name, [(timestamp, value), ...]) tuples,
    ready to feed into Dsremo's detection pipeline.

    Args:
        base_dir:     override default data directory
        subsystems:   filter to specific subsystems
        max_channels: limit number of channels (for quick testing)

    Returns:
        list of (channel_key, [(ts_str, value), ...])
    """
    result = []
    for channel, points in iter_all_channels(base_dir, subsystems):
        ts_val = [(p.timestamp, p.value) for p in points]
        result.append((channel, ts_val))
        if len(result) >= max_channels:
            break
    return result


def print_eden_summary(base_dir: Path | None = None) -> None:
    """Print a summary of the EDEN ISS dataset."""
    print("=" * 65)
    print("  EDEN ISS 2020 — Real ISS Telemetry Summary")
    print("=" * 65)
    total_points = 0
    for channel, points in iter_all_channels(base_dir):
        stats = compute_channel_stats(channel, points)
        total_points += stats.n_samples
        flag = " *** ANOMALIES" if stats.n_large_jumps > 10 else ""
        print(f"  {channel:35s}  n={stats.n_samples:>7,}  "
              f"μ={stats.mean:>8.2f}  σ={stats.std:>7.3f}  "
              f"jumps={stats.n_large_jumps:>4}{flag}")
    print(f"\n  Total data points: {total_points:,}")
    print("=" * 65)


if __name__ == "__main__":
    print_eden_summary()
