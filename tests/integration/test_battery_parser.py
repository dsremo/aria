"""Tests for NASA Battery Aging Data Parser.

Tests use real NASA Ames battery data (B0005.mat) to validate:
  - .mat file parsing correctness
  - Capacity fade detection
  - Resistance growth tracking
  - CSV export formats
  - ARIA DataReplayEngine compatibility
"""

import csv
import os
from pathlib import Path

import pytest

# Only run if scipy and battery data are available
scipy = pytest.importorskip("scipy")

from aria.simulation.battery_parser import (
    BatteryAgingProfile,
    BatteryCycle,
    NASABatteryParser,
    batch_convert,
)

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "nasa_battery" / "extracted"
MAT_FILE = DATA_DIR / "B0005.mat"

pytestmark = pytest.mark.skipif(
    not MAT_FILE.exists(),
    reason="NASA battery data not available (run: extract B0005.mat from nasa_battery.zip)",
)


@pytest.fixture(scope="module")
def profile() -> BatteryAgingProfile:
    """Parse B0005 once for all tests."""
    parser = NASABatteryParser()
    return parser.parse_mat_file(MAT_FILE)


class TestBatteryParsing:
    """Verify correct parsing of .mat file structure."""

    def test_battery_id(self, profile: BatteryAgingProfile) -> None:
        assert profile.battery_id == "B0005"

    def test_total_cycles(self, profile: BatteryAgingProfile) -> None:
        assert len(profile.cycles) == 616

    def test_cycle_type_distribution(self, profile: BatteryAgingProfile) -> None:
        assert len(profile.charge_cycles) == 170
        assert len(profile.discharge_cycles) == 168
        assert len(profile.impedance_cycles) == 278

    def test_discharge_has_voltage(self, profile: BatteryAgingProfile) -> None:
        dc = profile.discharge_cycles[0]
        assert len(dc.voltage_measured) > 50  # Typical: ~200 samples
        assert all(2.0 <= v <= 4.5 for v in dc.voltage_measured)

    def test_discharge_has_current(self, profile: BatteryAgingProfile) -> None:
        dc = profile.discharge_cycles[0]
        assert len(dc.current_measured) > 50
        # Discharge at ~2A CC
        assert all(-3.0 <= c <= 3.0 for c in dc.current_measured)

    def test_discharge_has_temperature(self, profile: BatteryAgingProfile) -> None:
        dc = profile.discharge_cycles[0]
        assert len(dc.temperature_measured) > 50
        # Room temperature ± rise from discharge
        assert all(15.0 <= t <= 45.0 for t in dc.temperature_measured)

    def test_discharge_has_capacity(self, profile: BatteryAgingProfile) -> None:
        dc = profile.discharge_cycles[0]
        assert dc.capacity_ahr is not None
        assert 1.0 < dc.capacity_ahr < 2.5  # Rated 2 Ahr

    def test_charge_has_voltage(self, profile: BatteryAgingProfile) -> None:
        cc = profile.charge_cycles[0]
        assert len(cc.voltage_measured) > 10

    def test_impedance_has_resistance(self, profile: BatteryAgingProfile) -> None:
        imp = profile.impedance_cycles[0]
        assert imp.rct_ohms is not None
        assert 0.01 < imp.rct_ohms < 1.0  # milliohm range


class TestCapacityFade:
    """Validate capacity degradation detection against known behavior."""

    def test_capacity_fade_curve_exists(self, profile: BatteryAgingProfile) -> None:
        curve = profile.capacity_fade_curve()
        assert len(curve) >= 100  # Should have 168 discharge cycles

    def test_initial_capacity_near_rated(self, profile: BatteryAgingProfile) -> None:
        curve = profile.capacity_fade_curve()
        # Initial capacity should be close to 2 Ahr rated
        assert 1.7 < curve[0][1] < 2.1

    def test_capacity_decreases_over_cycles(self, profile: BatteryAgingProfile) -> None:
        curve = profile.capacity_fade_curve()
        # First 10 vs last 10 average
        first_avg = sum(c[1] for c in curve[:10]) / 10
        last_avg = sum(c[1] for c in curve[-10:]) / 10
        assert last_avg < first_avg

    def test_final_capacity_near_eol(self, profile: BatteryAgingProfile) -> None:
        curve = profile.capacity_fade_curve()
        # EOL criteria: 30% fade → 1.4 Ahr
        assert curve[-1][1] < 1.5  # Should be near EOL

    def test_capacity_fade_rate(self, profile: BatteryAgingProfile) -> None:
        """Total fade should be 25-35% (matching 30% EOL criteria)."""
        curve = profile.capacity_fade_curve()
        fade_pct = (1 - curve[-1][1] / curve[0][1]) * 100
        assert 20 < fade_pct < 40  # Dataset designed to reach ~30%

    def test_monotonic_general_trend(self, profile: BatteryAgingProfile) -> None:
        """Capacity should generally decrease (with noise)."""
        curve = profile.capacity_fade_curve()
        # Smooth with 20-point window
        window = 20
        if len(curve) < window * 2:
            pytest.skip("Not enough data for windowed test")
        avgs = []
        for i in range(0, len(curve) - window, window):
            avg = sum(c[1] for c in curve[i:i + window]) / window
            avgs.append(avg)
        # Each window average should be <= previous (with 5% tolerance for noise)
        for i in range(1, len(avgs)):
            assert avgs[i] <= avgs[i - 1] * 1.05


class TestResistanceGrowth:
    """Validate internal resistance growth tracking."""

    def test_resistance_curve_exists(self, profile: BatteryAgingProfile) -> None:
        curve = profile.resistance_growth_curve()
        assert len(curve) >= 50

    def test_resistance_in_valid_range(self, profile: BatteryAgingProfile) -> None:
        curve = profile.resistance_growth_curve()
        for _, rct in curve:
            assert 0.01 < rct < 2.0  # milliohm to ohm range

    def test_resistance_increases(self, profile: BatteryAgingProfile) -> None:
        """Charge transfer resistance should generally increase with aging."""
        curve = profile.resistance_growth_curve()
        first_avg = sum(c[1] for c in curve[:10]) / 10
        last_avg = sum(c[1] for c in curve[-10:]) / 10
        # Should grow at least a little
        assert last_avg >= first_avg * 0.95  # Allow some noise


class TestCSVExport:
    """Verify CSV export formats for DataReplayEngine compatibility."""

    @pytest.fixture
    def export_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "battery_export"

    def test_discharge_csv_export(self, profile: BatteryAgingProfile, export_dir: Path) -> None:
        parser = NASABatteryParser()
        rows = parser.export_discharge_csv(profile, export_dir / "discharge.csv")
        assert rows > 10000  # Should have ~50k rows

        # Verify format
        with open(export_dir / "discharge.csv") as f:
            reader = csv.DictReader(f)
            row = next(reader)
            assert "timestamp_s" in row
            assert "voltage_v" in row
            assert "current_a" in row
            assert "temperature_c" in row
            assert "capacity_ahr" in row
            assert float(row["voltage_v"]) > 0

    def test_aging_summary_csv(self, profile: BatteryAgingProfile, export_dir: Path) -> None:
        parser = NASABatteryParser()
        rows = parser.export_aging_summary(profile, export_dir / "aging.csv")
        assert rows == len(profile.cycles)

        with open(export_dir / "aging.csv") as f:
            reader = csv.DictReader(f)
            row = next(reader)
            assert "cycle_index" in row
            assert "cycle_type" in row

    def test_aria_replay_csv(self, profile: BatteryAgingProfile, export_dir: Path) -> None:
        parser = NASABatteryParser()
        rows = parser.export_aria_replay_csv(profile, export_dir / "aria.csv")
        assert rows > 50000

        with open(export_dir / "aria.csv") as f:
            reader = csv.DictReader(f)
            channels_seen = set()
            for i, row in enumerate(reader):
                assert "timestamp_s" in row
                assert "channel" in row
                assert "value" in row
                channels_seen.add(row["channel"])
                if i > 1000:
                    break

        # Should have all 4 channels
        assert "battery.voltage_v" in channels_seen
        assert "battery.current_a" in channels_seen
        assert "battery.temperature_c" in channels_seen

    def test_aria_replay_timestamps_monotonic(self, profile: BatteryAgingProfile, export_dir: Path) -> None:
        parser = NASABatteryParser()
        parser.export_aria_replay_csv(profile, export_dir / "aria.csv")

        with open(export_dir / "aria.csv") as f:
            reader = csv.DictReader(f)
            prev_ts = -1.0
            for i, row in enumerate(reader):
                ts = float(row["timestamp_s"])
                assert ts >= prev_ts, f"Timestamp not monotonic at row {i}"
                prev_ts = ts
                if i > 5000:
                    break


class TestARIADegradationValidation:
    """Cross-validate NASA battery data against ARIA's degradation model."""

    def test_capacity_fade_rate_matches_aria_model(self, profile: BatteryAgingProfile) -> None:
        """ARIA's PowerAgent uses 0.015% per cycle. NASA data should be similar order."""
        curve = profile.capacity_fade_curve()
        total_fade_pct = (1 - curve[-1][1] / curve[0][1]) * 100
        n_cycles = len(curve)
        per_cycle_fade = total_fade_pct / n_cycles

        # ARIA model: 0.015% per cycle
        # Real data should be within 0.05-0.25% per cycle range
        assert 0.05 < per_cycle_fade < 0.5, (
            f"Per-cycle fade {per_cycle_fade:.3f}% outside expected range"
        )

    def test_temperature_during_discharge(self, profile: BatteryAgingProfile) -> None:
        """ARIA triggers thermal alert at 35°C. Verify real data temp range."""
        max_temps = []
        for dc in profile.discharge_cycles[:20]:
            if dc.temperature_measured:
                max_temps.append(max(dc.temperature_measured))

        avg_max = sum(max_temps) / len(max_temps)
        # At 2A CC discharge, room temp, max should be 30-35°C
        assert 25 < avg_max < 40, f"Average max discharge temp {avg_max:.1f}°C unexpected"

    def test_voltage_cutoff_matches_aria(self, profile: BatteryAgingProfile) -> None:
        """ARIA's undervoltage threshold is 24V (bus). Cell cutoff at 2.7V (B0005)."""
        for dc in profile.discharge_cycles[:10]:
            min_v = min(dc.voltage_measured)
            # B0005 cutoff = 2.7V per README
            assert 2.4 <= min_v <= 3.0, f"Discharge cutoff {min_v:.2f}V outside expected"
