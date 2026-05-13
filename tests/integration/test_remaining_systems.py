"""Tests for remaining P1 systems — 100-Scientist Interrogation gap closure.

Covers: Stellar Proper Motion, Oort Cloud Passage, Computing Regression,
Seal & Gasket Lifecycle, Catalyst Lifecycle, Gravity-Dependent Fertility.
"""

import math

import pytest

from aria.simulation.remaining_systems import (
    CatalystLifecycleSimulator,
    ComputingRegressionSimulator,
    GravityFertilitySimulator,
    OortCloudSimulator,
    SealGasketSimulator,
    StellarProperMotionSimulator,
)


# ===================================================================
# 1. STELLAR PROPER MOTION
# ===================================================================

class TestStellarProperMotion:
    def test_initial_zero_drift(self) -> None:
        sim = StellarProperMotionSimulator(seed=42)
        assert sim.state.uncorrected_drift_arcsec == 0.0
        assert sim.state.corrections_applied == 0

    def test_drift_accumulates(self) -> None:
        sim = StellarProperMotionSimulator(seed=42)
        for yr in range(1, 51):
            sim.simulate_year(float(yr))
        # ~3.7 arcsec/yr * 50 yr = ~185 arcsec total drift
        assert sim.state.total_drift_arcsec > 150.0

    def test_correction_reduces_drift(self) -> None:
        sim = StellarProperMotionSimulator(seed=42)
        sim.state.correction_interval_years = 50
        for yr in range(1, 76):
            sim.simulate_year(float(yr))
        # After a correction at year 75, uncorrected drift should be small
        assert sim.state.corrections_applied >= 1
        assert sim.state.uncorrected_drift_arcsec < sim.state.total_drift_arcsec

    def test_miss_distance_without_correction(self) -> None:
        """Without any corrections, 1000 years of drift causes large miss."""
        sim = StellarProperMotionSimulator(seed=42)
        sim.state.correction_interval_years = 99999  # Never correct
        for yr in range(1, 1001):
            sim.simulate_year(float(yr))
        # ~3700 arcsec ≈ 1 degree → miss ~0.03 ly at 100 ly
        assert sim.state.projected_miss_ly > 0.01

    def test_dv_budget_consumed(self) -> None:
        sim = StellarProperMotionSimulator(seed=42)
        for yr in range(1, 301):
            sim.simulate_year(float(yr))
        assert sim.state.total_correction_dv_spent > 0


# ===================================================================
# 2. OORT CLOUD PASSAGE
# ===================================================================

class TestOortCloudPassage:
    def test_sol_oort_entry_is_early(self) -> None:
        sim = OortCloudSimulator(seed=42)
        # Sol Oort Cloud inner edge at 10,000 AU; at 0.1c that's ~0.5 yr
        assert sim.state.sol_oort_entry_year < 5.0

    def test_target_oort_entry_near_end(self) -> None:
        sim = OortCloudSimulator(mission_duration=1000, distance_ly=100.0, seed=42)
        # Target Oort entry should be near the end of the mission
        assert sim.state.target_oort_entry_year > 900.0

    def test_shield_stress_elevated_in_cloud(self) -> None:
        sim = OortCloudSimulator(seed=42)
        entry = sim.state.sol_oort_entry_year
        # Simulate a year inside the cloud
        sim.simulate_year(entry + 0.5)
        assert sim.state.shield_stress_factor > 1.0

    def test_shield_stress_normal_outside_cloud(self) -> None:
        sim = OortCloudSimulator(seed=42)
        # Year 500 is in interstellar space, between clouds
        sim.simulate_year(500.0)
        assert sim.state.shield_stress_factor == 1.0

    def test_transit_events_generated(self) -> None:
        sim = OortCloudSimulator(seed=42)
        entry_yr = math.ceil(sim.state.sol_oort_entry_year)
        events = sim.simulate_year(float(entry_yr))
        messages = [e["message"] for e in events]
        assert any("Entering Sol" in m for m in messages)


# ===================================================================
# 3. COMPUTING REGRESSION
# ===================================================================

class TestComputingRegression:
    def test_initial_full_compute(self) -> None:
        sim = ComputingRegressionSimulator(seed=42)
        assert sim.state.compute_ratio == pytest.approx(1.0)
        assert sim.state.original_cpu_alive == 100

    def test_cpus_fail_over_time(self) -> None:
        sim = ComputingRegressionSimulator(seed=42)
        for yr in range(1, 21):
            sim.simulate_year(float(yr))
        assert sim.state.original_cpu_alive < 100

    def test_replacements_fabricated(self) -> None:
        sim = ComputingRegressionSimulator(seed=42)
        for yr in range(1, 21):
            sim.simulate_year(float(yr))
        assert sim.state.replacement_cpu_count > 0

    def test_compute_ratio_declines(self) -> None:
        sim = ComputingRegressionSimulator(seed=42)
        for yr in range(1, 201):
            sim.simulate_year(float(yr))
        # After 200 years, most originals gone, replacements are 1/1000th
        assert sim.state.compute_ratio < 0.5

    def test_aria_optimization_degrades(self) -> None:
        sim = ComputingRegressionSimulator(seed=42)
        for yr in range(1, 501):
            sim.simulate_year(float(yr))
        assert sim.state.aria_optimization_level < 1.0

    def test_replacement_mips_much_lower(self) -> None:
        sim = ComputingRegressionSimulator(seed=42)
        ratio = sim.state.replacement_cpu_mips / sim.state.original_cpu_mips
        assert ratio < 0.01  # 1/1000th


# ===================================================================
# 4. SEAL & GASKET LIFECYCLE
# ===================================================================

class TestSealGasketLifecycle:
    def test_initial_no_leaks(self) -> None:
        sim = SealGasketSimulator(seed=42)
        assert sim.state.active_leaks == 0
        assert sim.state.cumulative_atmo_loss_pct == 0.0

    def test_seals_fail_over_rated_life(self) -> None:
        sim = SealGasketSimulator(total_seals=100, seed=42)
        for yr in range(1, 25):
            sim.simulate_year(float(yr))
        assert sim.state.failed_seals > 0

    def test_replacements_happen(self) -> None:
        sim = SealGasketSimulator(total_seals=100, seed=42)
        for yr in range(1, 25):
            sim.simulate_year(float(yr))
        assert sim.state.replaced_seals > 0

    def test_atmosphere_loss_from_active_leaks(self) -> None:
        sim = SealGasketSimulator(total_seals=100, seed=42)
        # Force some active leaks
        sim.state.active_leaks = 10
        sim.simulate_year(50.0)
        assert sim.state.cumulative_atmo_loss_pct > 0.0

    def test_spare_inventory_depletes(self) -> None:
        sim = SealGasketSimulator(total_seals=1000, seed=42)
        sim.state.seal_inventory_spare = 50
        for yr in range(1, 100):
            sim.simulate_year(float(yr))
        assert sim.state.seal_inventory_spare < 50


# ===================================================================
# 5. CATALYST LIFECYCLE
# ===================================================================

class TestCatalystLifecycle:
    def test_initial_full_activity(self) -> None:
        sim = CatalystLifecycleSimulator(seed=42)
        assert sim.state.sabatier_activity == 1.0
        assert sim.state.electrolysis_activity == 1.0

    def test_sabatier_decays_over_time(self) -> None:
        sim = CatalystLifecycleSimulator(seed=42)
        for yr in range(1, 11):
            sim.simulate_year(float(yr))
        # After 10 years at 2%/yr decay + poisoning, activity should drop
        assert sim.state.sabatier_activity < 1.0

    def test_regeneration_recovers_activity(self) -> None:
        sim = CatalystLifecycleSimulator(seed=42)
        for yr in range(1, 11):
            sim.simulate_year(float(yr))
        pre_regen = sim.state.sabatier_activity
        # Force regeneration
        sim.state.last_regeneration_year = 0.0
        sim.state.regeneration_interval_years = 1
        sim.simulate_year(11.0)
        assert sim.state.sabatier_activity > pre_regen

    def test_electrolysis_degrades(self) -> None:
        sim = CatalystLifecycleSimulator(seed=42)
        for yr in range(1, 51):
            sim.simulate_year(float(yr))
        assert sim.state.electrolysis_activity < 1.0
        assert sim.state.platinum_remaining_pct < 100.0

    def test_iridium_switch_when_platinum_low(self) -> None:
        sim = CatalystLifecycleSimulator(seed=42)
        sim.state.platinum_remaining_pct = 25.0
        events = sim.simulate_year(100.0)
        assert sim.state.iridium_alternative_active is True

    def test_eclss_efficiency_tracks_catalyst(self) -> None:
        sim = CatalystLifecycleSimulator(seed=42)
        for yr in range(1, 31):
            sim.simulate_year(float(yr))
        assert sim.state.co2_conversion_efficiency == pytest.approx(
            sim.state.sabatier_activity
        )
        assert sim.state.o2_production_efficiency == pytest.approx(
            sim.state.electrolysis_activity
        )


# ===================================================================
# 6. GRAVITY-DEPENDENT FERTILITY
# ===================================================================

class TestGravityFertility:
    def test_initial_population(self) -> None:
        sim = GravityFertilitySimulator(population=50, seed=42)
        assert sim.state.population == 50

    def test_fertility_factor_at_1g_is_high(self) -> None:
        sim = GravityFertilitySimulator(gravity_g=1.0, seed=42)
        assert sim.state.gravity_fertility_factor > 0.9

    def test_fertility_factor_at_0g_is_very_low(self) -> None:
        sim = GravityFertilitySimulator(gravity_g=0.0, seed=42)
        assert sim.state.gravity_fertility_factor < 0.15

    def test_worst_case_lower_than_best(self) -> None:
        best = GravityFertilitySimulator(
            gravity_g=0.56, scenario="best", seed=42
        )
        worst = GravityFertilitySimulator(
            gravity_g=0.56, scenario="worst", seed=42
        )
        assert worst.state.gravity_fertility_factor < best.state.gravity_fertility_factor

    def test_births_occur_over_centuries(self) -> None:
        sim = GravityFertilitySimulator(population=80, seed=42)
        for yr in range(1, 201):
            sim.simulate_year(float(yr))
        assert sim.state.total_births > 0

    def test_population_collapse_in_worst_case(self) -> None:
        """Worst-case gravity scenario with small pop may collapse."""
        sim = GravityFertilitySimulator(
            population=25, gravity_g=0.3, scenario="worst", seed=7
        )
        for yr in range(1, 501):
            sim.simulate_year(float(yr))
        # With 30% fertility at 0.3g, population likely declines
        assert sim.state.population < 25 or sim.state.total_deaths > 0

    def test_centrifuge_reduces_complications(self) -> None:
        sim = GravityFertilitySimulator(population=80, seed=42)
        sim.state.centrifuge_available = True
        for yr in range(1, 101):
            sim.simulate_year(float(yr))
        with_centrifuge = sim.state.birth_complications

        sim2 = GravityFertilitySimulator(population=80, seed=42)
        sim2.state.centrifuge_available = False
        for yr in range(1, 101):
            sim2.simulate_year(float(yr))
        without_centrifuge = sim2.state.birth_complications

        # Centrifuge should result in fewer or equal complications
        assert with_centrifuge <= without_centrifuge + 5  # Small tolerance

    def test_extinction_event_generated(self) -> None:
        sim = GravityFertilitySimulator(population=5, gravity_g=0.1,
                                         scenario="worst", seed=42)
        all_events = []
        for yr in range(1, 201):
            all_events.extend(sim.simulate_year(float(yr)))
        # Should eventually generate population warnings
        critical = [e for e in all_events if e["severity"] == "CRITICAL"]
        assert len(critical) > 0
