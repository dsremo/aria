"""Tests for reentry_skip.py — Skip/lifting reentry trajectory simulation.

Coverage:
  - Skip detection: φ=0° (lift up) produces at least one skip
  - Direct entry: φ=180° (lift down) produces no skip
  - Peak-g comparison: skip entry < direct entry
  - Atmosphere model: density matches US Standard Atmosphere at key altitudes
  - Trajectory: altitude, speed, deceleration are physically consistent

References:
  Loh (1963) §5 — skip entry theory
  NASA Artemis I blog (Dec 2022) — skip reentry data
  US Standard Atmosphere 1976 — density validation
"""

import math
import pytest

from aria.simulation.reentry_skip import (
    ARTEMIS1_ENTRY_SPEED_MS, ARTEMIS1_ENTRY_ANGLE_DEG,
    ARTEMIS1_PEAK_DECEL_G,
    EI_ALTITUDE_M,
    SkipReentryResult, EntryState,
    simulate_skip_entry, compare_entry_modes,
    _atmo_density,
)


# ═══════════════════════════════════════════════════════════════════
#  1. ATMOSPHERE MODEL
# ═══════════════════════════════════════════════════════════════════

class TestAtmoDensity:
    """US Standard Atmosphere 1976 tabulated model."""

    def test_sea_level_density(self):
        """Sea level density should be ~1.225 kg/m³."""
        rho = _atmo_density(0.0)
        assert rho == pytest.approx(1.225, rel=0.01)

    def test_122km_density(self):
        """Density at 122 km (EI) should be ~2.2×10⁻⁸ kg/m³."""
        rho = _atmo_density(122_000.0)
        assert 1e-8 < rho < 5e-8, f"EI density {rho:.2e} outside expected range"

    def test_density_decreases(self):
        """Density must decrease with altitude."""
        d0 = _atmo_density(0)
        d50 = _atmo_density(50_000)
        d100 = _atmo_density(100_000)
        d200 = _atmo_density(200_000)
        assert d0 > d50 > d100 > d200

    def test_density_at_70km(self):
        """70 km density should be ~8×10⁻⁵ kg/m³ (peak heating altitude)."""
        rho = _atmo_density(70_000.0)
        assert 3e-5 < rho < 2e-4

    def test_density_positive_at_all_altitudes(self):
        """Density must be positive at all altitudes."""
        for h_km in [0, 10, 50, 100, 200, 400]:
            assert _atmo_density(h_km * 1000) > 0


# ═══════════════════════════════════════════════════════════════════
#  2. SKIP ENTRY
# ═══════════════════════════════════════════════════════════════════

class TestSkipEntry:
    """Skip reentry with bank angle φ=0° (lift up)."""

    @pytest.fixture
    def skip_result(self):
        return simulate_skip_entry(
            ARTEMIS1_ENTRY_SPEED_MS, ARTEMIS1_ENTRY_ANGLE_DEG,
            lift_to_drag=0.3, bank_angle_deg=0.0,
        )

    def test_at_least_one_skip(self, skip_result):
        """With φ=0° and shallow entry, the capsule should skip at least once."""
        assert skip_result.n_skips >= 1, "Expected at least 1 skip with full lift-up"

    def test_skip_apex_above_ei(self, skip_result):
        """Skip apex should be above the sensible atmosphere (~80 km)."""
        assert skip_result.skip_apex_altitude_km > 80.0

    def test_peak_decel_reasonable(self, skip_result):
        """Skip entry peak-g should be < 10 g (much less than ballistic)."""
        assert skip_result.peak_decel_g < 10.0

    def test_returns_result(self, skip_result):
        assert isinstance(skip_result, SkipReentryResult)

    def test_trajectory_not_empty(self, skip_result):
        assert len(skip_result.trajectory) > 10

    def test_entry_speed_matches_input(self, skip_result):
        assert skip_result.entry_speed_ms == ARTEMIS1_ENTRY_SPEED_MS

    def test_heat_rate_positive(self, skip_result):
        assert skip_result.peak_heat_rate_w_cm2 > 0

    def test_total_heat_load_positive(self, skip_result):
        assert skip_result.total_heat_load_j_cm2 > 0


# ═══════════════════════════════════════════════════════════════════
#  3. DIRECT ENTRY (lift down)
# ═══════════════════════════════════════════════════════════════════

class TestDirectEntry:
    """Direct entry with bank angle φ=180° (lift down = steeper)."""

    @pytest.fixture
    def direct_result(self):
        return simulate_skip_entry(
            ARTEMIS1_ENTRY_SPEED_MS, ARTEMIS1_ENTRY_ANGLE_DEG,
            lift_to_drag=0.3, bank_angle_deg=180.0,
        )

    def test_no_skip(self, direct_result):
        """With φ=180° (lift down), should not skip."""
        assert direct_result.n_skips == 0

    def test_higher_peak_g_than_skip(self, direct_result):
        """Direct entry should have much higher peak-g than skip."""
        skip = simulate_skip_entry(
            ARTEMIS1_ENTRY_SPEED_MS, ARTEMIS1_ENTRY_ANGLE_DEG,
            lift_to_drag=0.3, bank_angle_deg=0.0,
        )
        assert direct_result.peak_decel_g > skip.peak_decel_g


# ═══════════════════════════════════════════════════════════════════
#  4. SKIP VS DIRECT COMPARISON
# ═══════════════════════════════════════════════════════════════════

class TestCompareEntryModes:
    """compare_entry_modes() comparison function."""

    def test_returns_dict(self):
        result = compare_entry_modes(11_000.0, -5.5)
        assert isinstance(result, dict)
        assert "skip" in result
        assert "direct" in result

    def test_g_ratio_less_than_one(self):
        """Skip peak-g should be less than direct peak-g."""
        result = compare_entry_modes(11_000.0, -5.5)
        assert result["g_ratio"] < 1.0, "Skip should have lower peak-g than direct"

    def test_skip_has_skips(self):
        result = compare_entry_modes(11_000.0, -5.5)
        assert result["skip"]["n_skips"] >= 1

    def test_direct_has_no_skips(self):
        result = compare_entry_modes(11_000.0, -5.5)
        assert result["direct"]["n_skips"] == 0


# ═══════════════════════════════════════════════════════════════════
#  5. PHYSICAL CONSISTENCY
# ═══════════════════════════════════════════════════════════════════

class TestPhysicalConsistency:
    """Entry trajectory should obey physical laws."""

    def test_speed_decreases_overall(self):
        """Final speed should be less than entry speed (drag slows vehicle)."""
        result = simulate_skip_entry(11_000.0, -6.0, lift_to_drag=0.0, bank_angle_deg=90.0)
        assert result.trajectory[-1].speed_ms < result.trajectory[0].speed_ms

    def test_steeper_entry_more_g(self):
        """Steeper entry angle → higher peak deceleration."""
        shallow = simulate_skip_entry(11_000.0, -3.0, lift_to_drag=0.0, bank_angle_deg=90.0)
        steep = simulate_skip_entry(11_000.0, -8.0, lift_to_drag=0.0, bank_angle_deg=90.0)
        assert steep.peak_decel_g > shallow.peak_decel_g

    def test_faster_entry_more_heat(self):
        """Higher entry speed → higher peak heat rate."""
        slow = simulate_skip_entry(9_000.0, -6.0, lift_to_drag=0.0, bank_angle_deg=90.0)
        fast = simulate_skip_entry(12_000.0, -6.0, lift_to_drag=0.0, bank_angle_deg=90.0)
        assert fast.peak_heat_rate_w_cm2 > slow.peak_heat_rate_w_cm2
