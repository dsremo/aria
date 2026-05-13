"""
Space weather data loader.

Parses CelesTrak space weather CSV files (SW-Last5Years.csv) to extract:
  - Kp index (3-hourly geomagnetic disturbance, 0-9 scale)
  - Ap index (daily geomagnetic, linear scale)
  - F10.7 solar radio flux (solar activity proxy)

These indices drive atmospheric density variations that affect:
  - Orbital drag → TCA prediction accuracy
  - Covariance realism → Pc accuracy
  - Orbital lifetime → debris persistence

Data source: https://celestrak.org/SpaceData/SW-Last5Years.csv
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from aria.conjunction.propagation.space_weather import SpaceWeatherState


@dataclass
class DailySpaceWeather:
    """Space weather data for one day."""

    date: datetime
    kp_values: list[float]  # 8 three-hourly Kp values
    kp_sum: float
    ap_values: list[float]  # 8 three-hourly Ap values
    ap_avg: float
    f107_obs: float  # observed F10.7
    f107_adj: float  # adjusted F10.7
    f107_center81: float  # 81-day centered average
    f107_last81: float  # 81-day trailing average

    @property
    def max_kp(self) -> float:
        return max(self.kp_values) if self.kp_values else 0.0

    def to_space_weather_state(self) -> SpaceWeatherState:
        """Convert to the SpaceWeatherState used by drag models."""
        return SpaceWeatherState(
            kp_index=self.max_kp / 10.0,  # CSV has Kp×10
            f107_index=self.f107_obs,
            f107_avg=self.f107_center81 or self.f107_obs,
            ap_index=self.ap_avg,
        )


class SpaceWeatherLoader:
    """Load and query space weather data from CelesTrak CSV files."""

    def __init__(self):
        self._data: dict[str, DailySpaceWeather] = {}  # key = "YYYY-MM-DD"

    def load_csv(self, filepath: str | Path) -> int:
        """Load space weather data from a CelesTrak SW CSV file.

        Args:
            filepath: Path to SW-Last5Years.csv or similar

        Returns:
            Number of days loaded
        """
        filepath = Path(filepath)
        count = 0

        with open(filepath) as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    date_str = row["DATE"].strip()
                    dt = datetime.strptime(date_str, "%Y-%m-%d")

                    kp_vals = [float(row.get(f"KP{i}", 0)) for i in range(1, 9)]
                    ap_vals = [float(row.get(f"AP{i}", 0)) for i in range(1, 9)]

                    day = DailySpaceWeather(
                        date=dt,
                        kp_values=kp_vals,
                        kp_sum=float(row.get("KP_SUM", sum(kp_vals))),
                        ap_values=ap_vals,
                        ap_avg=float(row.get("AP_AVG", 0)),
                        f107_obs=float(row.get("F10.7_OBS", 150)),
                        f107_adj=float(row.get("F10.7_ADJ", 150)),
                        f107_center81=float(row.get("F10.7_OBS_CENTER81", 0) or 0),
                        f107_last81=float(row.get("F10.7_OBS_LAST81", 0) or 0),
                    )

                    self._data[date_str] = day
                    count += 1
                except (KeyError, ValueError):
                    continue

        return count

    def get(self, date: datetime) -> DailySpaceWeather | None:
        """Get space weather for a specific date."""
        key = date.strftime("%Y-%m-%d")
        return self._data.get(key)

    def get_nearest(self, date: datetime) -> DailySpaceWeather | None:
        """Get space weather for the nearest available date."""
        # Try exact match first
        result = self.get(date)
        if result:
            return result

        # Search backward up to 7 days
        for delta in range(1, 8):
            result = self.get(date - timedelta(days=delta))
            if result:
                return result

        # Return most recent available
        if self._data:
            latest_key = max(self._data.keys())
            return self._data[latest_key]
        return None

    def get_state(self, date: datetime) -> SpaceWeatherState:
        """Get SpaceWeatherState for the drag uncertainty model.

        Falls back to moderate conditions if no data available.
        """
        day = self.get_nearest(date)
        if day:
            return day.to_space_weather_state()
        return SpaceWeatherState()  # defaults to moderate

    def storm_periods(self, kp_threshold: float = 50.0) -> list[DailySpaceWeather]:
        """Find all days with geomagnetic storms (max Kp > threshold).

        Note: CelesTrak Kp is ×10, so Kp=5 → 50 in the CSV.
        """
        return [d for d in self._data.values() if d.max_kp >= kp_threshold]

    @property
    def date_range(self) -> tuple[datetime, datetime] | None:
        if not self._data:
            return None
        dates = sorted(self._data.keys())
        return (
            datetime.strptime(dates[0], "%Y-%m-%d"),
            datetime.strptime(dates[-1], "%Y-%m-%d"),
        )

    @property
    def size(self) -> int:
        return len(self._data)
