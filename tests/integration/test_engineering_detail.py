"""Tests for engineering detail subsystems: power distribution, EMC,
atmospheric chemistry, and structural fatigue."""

import math
import pytest

from aria.simulation.engineering_detail import (
    PowerBus,
    PowerLoad,
    PowerDistributionSimulator,
    EMSource,
    EMReceiver,
    EMCSimulator,
    AtmosphericChemistrySimulator,
    SMAC_LIMITS,
    StructuralFatigueSimulator,
    FatigueState,
)


# ============================================================================
# POWER DISTRIBUTION NETWORK
# ============================================================================

class TestPowerBus:
    def test_bus_capacity(self) -> None:
        bus = PowerBus(name="28V_DC", voltage=28.0, bus_type="DC", max_current_a=500.0)
        assert bus.power_capacity_w == 28.0 * 500.0

    def test_bus_utilization_zero_at_start(self) -> None:
        bus = PowerBus(name="28V_DC", voltage=28.0, bus_type="DC", max_current_a=500.0)
        assert bus.utilization == 0.0

    def test_bus_utilization_increases_with_load(self) -> None:
        bus = PowerBus(
            name="28V_DC", voltage=28.0, bus_type="DC",
            max_current_a=500.0, current_load_a=250.0,
        )
        assert abs(bus.utilization - 0.5) < 0.01


class TestPowerLoad:
    def test_breaker_trips_at_120_percent(self) -> None:
        load = PowerLoad(
            name="test", bus_name="28V_DC",
            rated_power_w=1000, current_power_w=1250,  # 125% > 120%
        )
        assert load.check_breaker() is True
        assert load.breaker_tripped is True
        assert load.active is False

    def test_breaker_does_not_trip_at_110_percent(self) -> None:
        load = PowerLoad(
            name="test", bus_name="28V_DC",
            rated_power_w=1000, current_power_w=1100,  # 110% < 120%
        )
        assert load.check_breaker() is False
        assert load.breaker_tripped is False


class TestPowerDistribution:
    def test_three_buses_exist(self) -> None:
        sim = PowerDistributionSimulator(seed=42)
        assert "28V_DC" in sim.state.buses
        assert "120V_AC" in sim.state.buses
        assert "400V_DC" in sim.state.buses

    def test_electrical_efficiency_approximately_90_percent(self) -> None:
        sim = PowerDistributionSimulator(seed=42)
        eff = sim.state.net_efficiency
        # (1-0.02)*(1-0.03)*(1-0.05) = 0.98*0.97*0.95 ≈ 0.9030
        assert 0.89 < eff < 0.92

    def test_total_available_less_than_reactor_output(self) -> None:
        sim = PowerDistributionSimulator(seed=42)
        assert sim.state.total_available_w < sim.state.reactor_output_w

    def test_load_shedding_removes_lowest_priority_first(self) -> None:
        # 400 kW covers priority 1+2 but not all loads (~534 kW total)
        sim = PowerDistributionSimulator(reactor_output_w=400_000, seed=42)
        events = sim.shed_loads()
        # Should have shed some loads
        assert sim.state.load_shed_events > 0
        # Life support (priority 1) should still be active
        life_support = [ld for ld in sim.state.loads if ld.priority == 1]
        assert all(ld.active for ld in life_support)

    def test_simulate_year_returns_events(self) -> None:
        sim = PowerDistributionSimulator(seed=42)
        events = sim.simulate_year(1.0)
        assert isinstance(events, list)

    def test_cable_degrades_over_centuries(self) -> None:
        sim = PowerDistributionSimulator(seed=42)
        for yr in range(1, 201):
            sim.simulate_year(float(yr))
        assert sim.state.cable_loss > 0.03  # started at 3%, should increase

    def test_ground_resistance_increases(self) -> None:
        sim = PowerDistributionSimulator(seed=42)
        for yr in range(1, 51):
            sim.simulate_year(float(yr))
        assert sim.state.ground_resistance_ohm > 0.01

    def test_report_contains_key_metrics(self) -> None:
        sim = PowerDistributionSimulator(seed=42)
        sim.simulate_year(1.0)
        report = sim.get_report()
        assert "reactor_output_kw" in report
        assert "efficiency" in report
        assert "bus_utilization" in report
        assert "breaker_trips" in report


# ============================================================================
# ELECTROMAGNETIC COMPATIBILITY
# ============================================================================

class TestEMC:
    def test_sources_and_receivers_populated(self) -> None:
        sim = EMCSimulator(seed=42)
        assert len(sim.state.sources) >= 5
        assert len(sim.state.receivers) >= 5

    def test_frequency_overlap_detection(self) -> None:
        sim = EMCSimulator(seed=42)
        # Same frequency should overlap
        assert sim._freq_overlap(1e9, 1e9) is True
        # 100x apart should not
        assert sim._freq_overlap(1e6, 1e9) is False

    def test_emi_filters_reduce_violations(self) -> None:
        sim_no_filter = EMCSimulator(seed=42)
        events_no = sim_no_filter.check_interference()

        sim_filtered = EMCSimulator(seed=42)
        sim_filtered.add_emi_filters()
        events_yes = sim_filtered.check_interference()

        # Filtered should have fewer or equal violations
        assert len(events_yes) <= len(events_no)

    def test_shielding_degradation_increases_interference(self) -> None:
        sim = EMCSimulator(seed=42)
        sim.state.shielding_degradation = 0.0
        events_good = sim.check_interference()

        sim2 = EMCSimulator(seed=42)
        sim2.state.shielding_degradation = 0.4
        events_bad = sim2.check_interference()

        assert len(events_bad) >= len(events_good)

    def test_simulate_year_degrades_shielding(self) -> None:
        sim = EMCSimulator(seed=42)
        for yr in range(1, 101):
            sim.simulate_year(float(yr))
        assert sim.state.shielding_degradation > 0

    def test_plasma_charging_budget_scatha_eclipse(self) -> None:
        """The plasma_charging_budget_v helper wires to the Pod D2
        sc_charging.equilibrium_surface_potential primitive. For a
        SCATHA-class GEO substorm in eclipse (n_e = 1e6 m^-3,
        T_e = 10 keV, unsunlit), the helper should return a
        strongly negative potential in the -5 kV to -50 kV band.
        """
        sim = EMCSimulator(seed=42)
        phi = sim.plasma_charging_budget_v(
            electron_density_m3=1.0e6,
            electron_temperature_ev=1.0e4,
            sunlit=False,
        )
        assert -5.0e4 < phi < -1.0e3, f"phi = {phi:.0f} V"

    def test_report_structure(self) -> None:
        sim = EMCSimulator(seed=42)
        sim.simulate_year(1.0)
        report = sim.get_report()
        assert "interference_events" in report
        assert "conducted_violations" in report
        assert "shielding_degradation_pct" in report


# ============================================================================
# ATMOSPHERIC CHEMISTRY
# ============================================================================

class TestAtmosphericChemistry:
    def test_initial_concentrations_below_smac(self) -> None:
        sim = AtmosphericChemistrySimulator(seed=42)
        eq = sim.get_equilibrium()
        for gas, limit in SMAC_LIMITS.items():
            assert eq[gas] <= limit, f"{gas} exceeds SMAC at start"

    def test_co_removal_by_oh_reaction(self) -> None:
        sim = AtmosphericChemistrySimulator(seed=42)
        initial_co = sim.state.co_ppm
        # Increase OH to drive CO removal
        sim.state.oh_radical_ppb = 1.0
        sim.state.crew_ch2o_rate = 0  # no CH₂O producing CO
        for _ in range(50):
            sim._step_hour()
        assert sim.state.co_ppm < initial_co

    def test_formaldehyde_photolysis_produces_co(self) -> None:
        sim = AtmosphericChemistrySimulator(seed=42)
        sim.state.ch2o_ppm = 1.0
        sim.state.uv_intensity_factor = 0.5
        sim.state.oh_radical_ppb = 0.0  # no OH removal of CO
        initial_co = sim.state.co_ppm
        for _ in range(20):
            sim._step_hour()
        # CO should increase from CH₂O decomposition
        assert sim.state.co_ppm > initial_co

    def test_ozone_reaches_equilibrium(self) -> None:
        sim = AtmosphericChemistrySimulator(seed=42)
        for _ in range(500):
            sim._step_hour()
        o3_1 = sim.state.o3_ppm
        for _ in range(500):
            sim._step_hour()
        o3_2 = sim.state.o3_ppm
        # Should be roughly stable (within 50%)
        if o3_1 > 0.001:
            assert abs(o3_2 - o3_1) / o3_1 < 0.5

    def test_tccs_degradation_over_time(self) -> None:
        sim = AtmosphericChemistrySimulator(seed=42)
        sim.simulate_year(100.0)
        assert sim.state.tccs_health < 1.0

    def test_ventilation_rate_affects_concentrations(self) -> None:
        sim_high = AtmosphericChemistrySimulator(seed=42)
        sim_high.state.ventilation_rate_ach = 15.0
        sim_high.simulate_year(1.0)
        co2_high_vent = sim_high.state.co2_ppm

        sim_low = AtmosphericChemistrySimulator(seed=42)
        sim_low.state.ventilation_rate_ach = 2.0
        sim_low.simulate_year(1.0)
        co2_low_vent = sim_low.state.co2_ppm

        # Lower ventilation → higher CO₂ accumulation
        assert co2_low_vent > co2_high_vent

    def test_smac_violation_detected(self) -> None:
        sim = AtmosphericChemistrySimulator(seed=42)
        sim.state.co_ppm = 50.0  # way above 10 ppm SMAC
        violations = sim.check_smac()
        co_violations = [v for v in violations if v["gas"] == "co_ppm"]
        assert len(co_violations) > 0

    def test_report_contains_all_gases(self) -> None:
        sim = AtmosphericChemistrySimulator(seed=42)
        report = sim.get_report()
        for gas in SMAC_LIMITS:
            assert gas in report


# ============================================================================
# STRUCTURAL FATIGUE
# ============================================================================

class TestStructuralFatigue:
    def test_cycles_per_year_at_1rpm(self) -> None:
        sim = StructuralFatigueSimulator(rpm=1.0, seed=42)
        expected = 1.0 * 60 * 24 * 365.25
        assert abs(sim.state.cycles_per_year - expected) < 1

    def test_fatigue_limit_at_19_years(self) -> None:
        sim = StructuralFatigueSimulator(rpm=1.0, seed=42)
        years = sim.state.fatigue_limit_cycles / sim.state.cycles_per_year
        assert 18 < years < 20  # ~19.01 years

    def test_weld_damage_exists(self) -> None:
        """Welds accumulate fatigue damage at elevated stress.
        Round 15: Goodman correction means nominal 1 RPM gives zero fatigue.
        Use elevated stress to confirm welds track damage. Welds are
        inspected and partially repaired (×0.5), so at steady state they
        may be LESS than base metal — both should be > 0 under stress."""
        sim = StructuralFatigueSimulator(rpm=1.0, seed=42)
        sim.state.total_cyclic_stress_mpa = 300.0  # Above endurance limit
        for yr in range(1, 51):
            sim.simulate_year(float(yr))
        assert sim.state.miner_damage > 0
        assert sim.state.weld_miner_damage > 0

    def test_miner_damage_increases_monotonically(self) -> None:
        sim = StructuralFatigueSimulator(rpm=1.0, seed=42)
        prev = 0.0
        for yr in range(1, 21):
            sim.simulate_year(float(yr))
            assert sim.state.miner_damage >= prev
            prev = sim.state.miner_damage

    def test_factor_of_safety_is_4(self) -> None:
        sim = StructuralFatigueSimulator(seed=42)
        assert sim.state.factor_of_safety == 4.0

    def test_first_year_info_event(self) -> None:
        sim = StructuralFatigueSimulator(rpm=1.0, seed=42)
        events = sim.simulate_year(1.0)
        info_events = [e for e in events if e.get("severity") == "INFO"]
        assert len(info_events) >= 1

    def test_higher_rpm_means_faster_fatigue(self) -> None:
        """Higher RPM → more cycles → more damage, at fixed elevated stress.
        Round 15: Goodman-corrected nominal stress is below endurance limit,
        so override to elevated stress to make the comparison meaningful."""
        sim_slow = StructuralFatigueSimulator(rpm=0.5, seed=42)
        sim_fast = StructuralFatigueSimulator(rpm=2.0, seed=42)
        sim_slow.state.total_cyclic_stress_mpa = 300.0
        sim_fast.state.total_cyclic_stress_mpa = 300.0
        for yr in range(1, 31):
            sim_slow.simulate_year(float(yr))
            sim_fast.simulate_year(float(yr))
        assert sim_fast.state.miner_damage >= sim_slow.state.miner_damage

    def test_report_structure(self) -> None:
        sim = StructuralFatigueSimulator(seed=42)
        sim.simulate_year(1.0)
        report = sim.get_report()
        assert "material" in report
        assert report["material"] == "Ti-6Al-4V"
        assert "miner_damage_base" in report
        assert "miner_damage_weld" in report
        assert "years_to_fatigue_limit" in report
        assert "factor_of_safety" in report

    def test_cycles_to_failure_below_endurance_limit_is_infinite(self) -> None:
        sim = StructuralFatigueSimulator(seed=42)
        # Stress well below fatigue_limit / FoS
        n = sim._cycles_to_failure(10.0)  # 10 MPa << 510/4 = 127.5 MPa
        assert n == float("inf")

    def test_hull_panel_fatigue_bridge_in_report(self) -> None:
        """get_report() routes through hull_fatigue bridge (Pod F2+F5).

        Pressure cycles: 365/yr × 50 kPa, R=12.6m, t=0.05m.
        Thermal cycles: 365/yr × 80 K, Ti-6Al-4V E=113.8 GPa, α=8.6e-6/K.
        Combined hull_panel_damage_per_year should be positive but finite.
        years_to_failure should be >> 100 yr (not a short-life part).
        """
        sim = StructuralFatigueSimulator(seed=42)
        sim.simulate_year(1.0)
        report = sim.get_report()
        assert "hull_panel_damage_per_year" in report
        assert "hull_panel_years_to_failure" in report
        assert report["hull_panel_damage_per_year"] > 0.0
        assert report["hull_panel_years_to_failure"] > 100.0

    def test_hull_panel_damage_higher_with_more_cycles(self) -> None:
        """More airlock cycles per year → more hull panel damage."""
        sim_low = StructuralFatigueSimulator(seed=42)
        sim_high = StructuralFatigueSimulator(seed=42)
        sim_low.state.hull_pressure_cycles_yr = 100.0
        sim_high.state.hull_pressure_cycles_yr = 1000.0
        sim_low.simulate_year(1.0)
        sim_high.simulate_year(1.0)
        r_low = sim_low.get_report()
        r_high = sim_high.get_report()
        assert r_high["hull_panel_damage_per_year"] > r_low["hull_panel_damage_per_year"]
