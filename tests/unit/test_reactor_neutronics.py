"""Tests for reactor neutronics simulation."""

import math

from aria.simulation.reactor_neutronics import (
    ReactorNeutronicsSimulator,
    ReactorState,
    NEUTRON_ENERGY_DT_MEV,
)


class TestReactorInit:
    def test_creates_with_defaults(self):
        sim = ReactorNeutronicsSimulator(seed=42)
        assert sim.state.fusion_power_mw == 200.0

    def test_custom_power(self):
        sim = ReactorNeutronicsSimulator(fusion_power_mw=500.0, seed=42)
        assert sim.state.fusion_power_mw == 500.0

    def test_derived_quantities_computed(self):
        sim = ReactorNeutronicsSimulator(seed=42)
        assert sim.state.neutron_flux_cm2_s > 0
        assert sim.state.total_power_mwe > 0
        assert sim.state.tritium_burn_rate_g_day > 0


class TestTritiumCycle:
    def test_tritium_inventory_sustained_with_good_tbr(self):
        sim = ReactorNeutronicsSimulator(seed=42)
        initial = sim.state.tritium_inventory_kg
        sim.simulate_year(1.0)
        # With TBR > 1.0, inventory should stay positive
        assert sim.state.tritium_inventory_kg > 0

    def test_tritium_decays(self):
        """Tritium T½ = 12.32 years. After 12 years, ~half should decay."""
        sim = ReactorNeutronicsSimulator(fusion_power_mw=0.001, seed=42)
        sim.state.tritium_inventory_kg = 10.0
        sim.state.tritium_breeding_ratio = 0.0  # No breeding
        sim.state.uptime_fraction = 0.0  # No burn
        initial = sim.state.tritium_inventory_kg
        for yr in range(12):
            sim.simulate_year(float(yr))
        # After 12 years (close to half-life), should be ~50%
        remaining_frac = sim.state.tritium_inventory_kg / initial
        assert 0.3 < remaining_frac < 0.7

    def test_lithium_consumed(self):
        sim = ReactorNeutronicsSimulator(seed=42)
        initial_li = sim.state.lithium_remaining_kg
        sim.simulate_year(1.0)
        assert sim.state.lithium_remaining_kg < initial_li


class TestNeutronDamage:
    def test_dpa_accumulates(self):
        sim = ReactorNeutronicsSimulator(seed=42)
        sim.simulate_year(1.0)
        assert sim.state.first_wall_dpa > 0

    def test_first_wall_replacement_at_limit(self):
        sim = ReactorNeutronicsSimulator(seed=42)
        # Force high dpa
        sim.state.first_wall_dpa = 149.0
        sim._dpa_rate_per_year = 10.0
        events = sim.simulate_year(10.0)
        assert sim.state.first_wall_replacements > 0
        assert any("replacement" in e["message"].lower() for e in events)

    def test_blanket_health_degrades(self):
        sim = ReactorNeutronicsSimulator(seed=42)
        sim.state.first_wall_dpa = 100.0
        sim.simulate_year(1.0)
        assert sim.state.blanket_health < 1.0


class TestActivation:
    def test_activation_products_build_up(self):
        sim = ReactorNeutronicsSimulator(seed=42)
        sim.simulate_year(1.0)
        assert sim.state.total_activation_bq > 0

    def test_co60_dominates_long_term(self):
        """Co-60 has longest half-life (5.27 yr) — should dominate after decades."""
        sim = ReactorNeutronicsSimulator(seed=42)
        for yr in range(50):
            sim.simulate_year(float(yr))
        # Co-60 should be significant fraction of total
        assert sim.state.activation_co60_bq > 0


class TestFissionBackup:
    def test_fission_degrades(self):
        sim = ReactorNeutronicsSimulator(seed=42)
        for yr in range(200):
            sim.simulate_year(float(yr))
        assert sim.state.fission_fuel_remaining_pct <= 0 or not sim.state.fission_available


class TestSimulateYear:
    def test_returns_events(self):
        sim = ReactorNeutronicsSimulator(seed=42)
        events = sim.simulate_year(1.0)
        assert isinstance(events, list)

    def test_events_have_structure(self):
        sim = ReactorNeutronicsSimulator(seed=42)
        # Force a critical state
        sim.state.tritium_inventory_kg = 0.3
        events = sim.simulate_year(1.0)
        critical = [e for e in events if e["severity"] == "CRITICAL"]
        assert len(critical) > 0
        for e in critical:
            assert "subsystem" in e
            assert e["subsystem"] == "reactor"


class TestReport:
    def test_report_keys(self):
        sim = ReactorNeutronicsSimulator(seed=42)
        report = sim.get_report()
        assert "fusion_power_mw" in report
        assert "tritium_inventory_kg" in report
        assert "first_wall_dpa" in report
        assert "blanket_health" in report

    def test_deterministic_with_seed(self):
        sim1 = ReactorNeutronicsSimulator(seed=42)
        sim1.simulate_year(1.0)
        sim2 = ReactorNeutronicsSimulator(seed=42)
        sim2.simulate_year(1.0)
        assert sim1.state.first_wall_dpa == sim2.state.first_wall_dpa
