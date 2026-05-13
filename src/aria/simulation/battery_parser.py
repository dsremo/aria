"""NASA Battery Aging Data Parser — converts Ames .mat files to ARIA-compatible CSV.

Dataset: NASA Ames Prognostics Center of Excellence — Battery Aging Dataset
Batteries: Li-ion 18650 cells (B0005, B0006, B0007, B0018)
Operations: charge (CC-CV 1.5A/4.2V), discharge (CC 2A to cutoff), impedance (EIS 0.1Hz-5kHz)
EOL criteria: 30% capacity fade (2.0 Ahr → 1.4 Ahr)

This data validates ARIA's PowerAgent battery degradation model:
  - Capacity fade rate vs cycle count
  - Temperature rise during discharge
  - Internal resistance growth (Rct from EIS)
  - Remaining useful life (RUL) prediction

Source: https://www.nasa.gov/content/prognostics-center-of-excellence-data-set-repository
Reference: B. Saha, K. Goebel (2007), "Battery Data Set", NASA Prognostics Data Repository
"""

from __future__ import annotations

import csv
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class BatteryCycle:
    """One charge/discharge/impedance cycle."""
    battery_id: str
    cycle_index: int
    cycle_type: str  # "charge", "discharge", "impedance"
    ambient_temperature_c: float
    time_vector: list[float] = field(default_factory=list)  # seconds
    # Charge/Discharge fields
    voltage_measured: list[float] = field(default_factory=list)
    current_measured: list[float] = field(default_factory=list)
    temperature_measured: list[float] = field(default_factory=list)
    current_load: list[float] = field(default_factory=list)
    voltage_load: list[float] = field(default_factory=list)
    capacity_ahr: float | None = None  # Discharge only
    # Impedance fields
    re_ohms: float | None = None  # Electrolyte resistance
    rct_ohms: float | None = None  # Charge transfer resistance


@dataclass
class BatteryAgingProfile:
    """Complete aging profile for one battery."""
    battery_id: str
    cycles: list[BatteryCycle] = field(default_factory=list)

    @property
    def discharge_cycles(self) -> list[BatteryCycle]:
        return [c for c in self.cycles if c.cycle_type == "discharge"]

    @property
    def charge_cycles(self) -> list[BatteryCycle]:
        return [c for c in self.cycles if c.cycle_type == "charge"]

    @property
    def impedance_cycles(self) -> list[BatteryCycle]:
        return [c for c in self.cycles if c.cycle_type == "impedance"]

    def capacity_fade_curve(self) -> list[tuple[int, float]]:
        """Returns (cycle_index, capacity_ahr) for each discharge cycle."""
        return [
            (c.cycle_index, c.capacity_ahr)
            for c in self.discharge_cycles
            if c.capacity_ahr is not None
        ]

    def resistance_growth_curve(self) -> list[tuple[int, float]]:
        """Returns (cycle_index, Rct_ohms) for each impedance cycle."""
        return [
            (c.cycle_index, c.rct_ohms)
            for c in self.impedance_cycles
            if c.rct_ohms is not None
        ]


class NASABatteryParser:
    """Parses NASA Ames battery aging .mat files into ARIA-compatible structures.

    Usage:
        parser = NASABatteryParser()
        profile = parser.parse_mat_file("data/raw/nasa_battery/extracted/B0005.mat")

        # Export to CSV for DataReplayEngine
        parser.export_discharge_csv(profile, "data/processed/battery_B0005_discharge.csv")
        parser.export_aging_summary(profile, "data/processed/battery_B0005_aging.csv")
    """

    def parse_mat_file(self, mat_path: str | Path) -> BatteryAgingProfile:
        """Parse a single NASA battery .mat file."""
        try:
            import scipy.io
        except ImportError:
            raise ImportError("scipy required: pip install scipy")

        mat_path = Path(mat_path)
        battery_id = mat_path.stem  # e.g., "B0005"

        logger.info("battery_parser.loading", file=str(mat_path), battery_id=battery_id)
        mat = scipy.io.loadmat(str(mat_path))

        if battery_id not in mat:
            raise ValueError(f"Expected key '{battery_id}' in .mat file, found: {list(mat.keys())}")

        cycle_array = mat[battery_id][0, 0]["cycle"]
        total_cycles = cycle_array.shape[1]
        logger.info("battery_parser.cycles_found", battery_id=battery_id, total=total_cycles)

        profile = BatteryAgingProfile(battery_id=battery_id)

        for i in range(total_cycles):
            raw = cycle_array[0, i]
            cycle_type = str(raw["type"][0])
            ambient_temp = float(raw["ambient_temperature"][0, 0])

            cycle = BatteryCycle(
                battery_id=battery_id,
                cycle_index=i,
                cycle_type=cycle_type,
                ambient_temperature_c=ambient_temp,
            )

            data = raw["data"][0, 0]

            if cycle_type in ("charge", "discharge"):
                cycle.voltage_measured = data["Voltage_measured"].flatten().tolist()
                cycle.current_measured = data["Current_measured"].flatten().tolist()
                cycle.temperature_measured = data["Temperature_measured"].flatten().tolist()
                cycle.time_vector = data["Time"].flatten().tolist()

                # Current/Voltage load naming varies between charge and discharge
                if "Current_load" in data.dtype.names:
                    cycle.current_load = data["Current_load"].flatten().tolist()
                    cycle.voltage_load = data["Voltage_load"].flatten().tolist()
                elif "Current_charge" in data.dtype.names:
                    cycle.current_load = data["Current_charge"].flatten().tolist()
                    cycle.voltage_load = data["Voltage_charge"].flatten().tolist()

                if cycle_type == "discharge" and "Capacity" in data.dtype.names:
                    cap = data["Capacity"]
                    if cap.size > 0:
                        # Capacity is the last value (cumulative)
                        cycle.capacity_ahr = float(cap.flatten()[-1])

            elif cycle_type == "impedance":
                if "Re" in data.dtype.names:
                    re_val = data["Re"].flatten()
                    if re_val.size > 0:
                        cycle.re_ohms = float(re_val[0])
                if "Rct" in data.dtype.names:
                    rct_val = data["Rct"].flatten()
                    if rct_val.size > 0:
                        cycle.rct_ohms = float(rct_val[0])

            profile.cycles.append(cycle)

        logger.info(
            "battery_parser.parsed",
            battery_id=battery_id,
            charges=len(profile.charge_cycles),
            discharges=len(profile.discharge_cycles),
            impedances=len(profile.impedance_cycles),
        )
        return profile

    def export_discharge_csv(
        self,
        profile: BatteryAgingProfile,
        output_path: str | Path,
    ) -> int:
        """Export discharge cycles as CSV for ARIA DataReplayEngine.

        Format: timestamp_s, battery_id, cycle, voltage_v, current_a, temperature_c, capacity_ahr
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        rows_written = 0
        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp_s", "battery_id", "cycle_index",
                "voltage_v", "current_a", "temperature_c", "capacity_ahr",
            ])

            for cycle in profile.discharge_cycles:
                cap = cycle.capacity_ahr or 0.0
                for j, t in enumerate(cycle.time_vector):
                    if j < len(cycle.voltage_measured):
                        writer.writerow([
                            f"{t:.2f}",
                            cycle.battery_id,
                            cycle.cycle_index,
                            f"{cycle.voltage_measured[j]:.4f}",
                            f"{cycle.current_measured[j]:.4f}" if j < len(cycle.current_measured) else "",
                            f"{cycle.temperature_measured[j]:.2f}" if j < len(cycle.temperature_measured) else "",
                            f"{cap:.4f}",
                        ])
                        rows_written += 1

        logger.info("battery_parser.exported_discharge", path=str(output_path), rows=rows_written)
        return rows_written

    def export_aging_summary(
        self,
        profile: BatteryAgingProfile,
        output_path: str | Path,
    ) -> int:
        """Export aging summary (capacity fade + resistance growth) as CSV.

        Format: cycle_index, cycle_type, capacity_ahr, re_ohms, rct_ohms, max_temp_c
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        rows = 0
        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "cycle_index", "cycle_type", "capacity_ahr",
                "re_ohms", "rct_ohms", "max_temp_c", "ambient_temp_c",
            ])

            for cycle in profile.cycles:
                max_temp = max(cycle.temperature_measured) if cycle.temperature_measured else None
                writer.writerow([
                    cycle.cycle_index,
                    cycle.cycle_type,
                    f"{cycle.capacity_ahr:.4f}" if cycle.capacity_ahr else "",
                    f"{cycle.re_ohms:.6f}" if cycle.re_ohms else "",
                    f"{cycle.rct_ohms:.6f}" if cycle.rct_ohms else "",
                    f"{max_temp:.2f}" if max_temp else "",
                    f"{cycle.ambient_temperature_c:.1f}",
                ])
                rows += 1

        logger.info("battery_parser.exported_aging", path=str(output_path), rows=rows)
        return rows

    def export_aria_replay_csv(
        self,
        profile: BatteryAgingProfile,
        output_path: str | Path,
    ) -> int:
        """Export in ARIA DataReplayEngine format: timestamp, channel, value.

        Maps battery data to ARIA power bus topics:
          - Voltage → aria.sensor.power.battery.voltage_v
          - Current → aria.sensor.power.battery.current_a
          - Temperature → aria.sensor.power.battery.temperature_c
          - Capacity → aria.sensor.power.battery.soc_percent (normalized)
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Get initial capacity for SoC normalization
        capacities = [c.capacity_ahr for c in profile.discharge_cycles if c.capacity_ahr]
        initial_cap = max(capacities) if capacities else 2.0  # Rated 2 Ahr

        rows = 0
        cumulative_time = 0.0

        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp_s", "channel", "value"])

            for cycle in profile.discharge_cycles:
                soc_percent = ((cycle.capacity_ahr or 0) / initial_cap) * 100.0

                for j, t in enumerate(cycle.time_vector):
                    ts = cumulative_time + t
                    if j < len(cycle.voltage_measured):
                        writer.writerow([f"{ts:.2f}", "battery.voltage_v", f"{cycle.voltage_measured[j]:.4f}"])
                        rows += 1
                    if j < len(cycle.current_measured):
                        writer.writerow([f"{ts:.2f}", "battery.current_a", f"{cycle.current_measured[j]:.4f}"])
                        rows += 1
                    if j < len(cycle.temperature_measured):
                        writer.writerow([f"{ts:.2f}", "battery.temperature_c", f"{cycle.temperature_measured[j]:.2f}"])
                        rows += 1

                # End of discharge: publish SoC
                if cycle.time_vector:
                    writer.writerow([
                        f"{cumulative_time + cycle.time_vector[-1]:.2f}",
                        "battery.soc_percent",
                        f"{soc_percent:.1f}",
                    ])
                    rows += 1
                    cumulative_time += cycle.time_vector[-1] + 10.0  # 10s gap between cycles

        logger.info("battery_parser.exported_aria", path=str(output_path), rows=rows)
        return rows

    @staticmethod
    def extract_from_zip(
        zip_path: str | Path,
        extract_dir: str | Path,
        battery_ids: list[str] | None = None,
    ) -> list[Path]:
        """Extract .mat files from NASA battery zip archive."""
        zip_path = Path(zip_path)
        extract_dir = Path(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)

        extracted = []
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                if not name.endswith(".mat"):
                    continue
                basename = Path(name).name
                bat_id = basename.replace(".mat", "")
                if battery_ids and bat_id not in battery_ids:
                    continue
                target = extract_dir / basename
                with zf.open(name) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                extracted.append(target)
                logger.info("battery_parser.extracted", file=basename)

        return extracted


def batch_convert(
    raw_dir: str | Path,
    output_dir: str | Path,
    battery_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Convert all NASA battery .mat files in a directory to ARIA-compatible CSV.

    Returns summary statistics.
    """
    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    parser = NASABatteryParser()
    results: dict[str, Any] = {"batteries": {}, "total_rows": 0}

    mat_files = sorted(raw_dir.glob("*.mat"))
    if battery_ids:
        mat_files = [f for f in mat_files if f.stem in battery_ids]

    for mat_file in mat_files:
        try:
            profile = parser.parse_mat_file(mat_file)

            # Export all formats
            discharge_rows = parser.export_discharge_csv(
                profile, output_dir / f"{profile.battery_id}_discharge.csv"
            )
            aging_rows = parser.export_aging_summary(
                profile, output_dir / f"{profile.battery_id}_aging.csv"
            )
            aria_rows = parser.export_aria_replay_csv(
                profile, output_dir / f"{profile.battery_id}_aria_replay.csv"
            )

            fade_curve = profile.capacity_fade_curve()
            results["batteries"][profile.battery_id] = {
                "total_cycles": len(profile.cycles),
                "discharge_cycles": len(profile.discharge_cycles),
                "charge_cycles": len(profile.charge_cycles),
                "impedance_cycles": len(profile.impedance_cycles),
                "initial_capacity_ahr": fade_curve[0][1] if fade_curve else None,
                "final_capacity_ahr": fade_curve[-1][1] if fade_curve else None,
                "capacity_fade_pct": (
                    (1 - fade_curve[-1][1] / fade_curve[0][1]) * 100
                    if len(fade_curve) >= 2 else None
                ),
                "discharge_csv_rows": discharge_rows,
                "aging_csv_rows": aging_rows,
                "aria_replay_rows": aria_rows,
            }
            results["total_rows"] += discharge_rows + aging_rows + aria_rows

        except Exception as e:
            logger.error("battery_parser.failed", file=str(mat_file), error=str(e))
            results["batteries"][mat_file.stem] = {"error": str(e)}

    return results
