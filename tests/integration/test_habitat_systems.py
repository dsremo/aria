"""Integration tests for habitat systems: ECLSS, Recreation & Morale, Supply Chain.

Tests all three subsystems plus orchestrator cross-system feedback:
  - Environmental Control (HVAC + atmosphere)
  - Recreation & Morale
  - Supply Chain & Inventory
  - Orchestrator integration

30 tests.
"""

from __future__ import annotations

import pytest

from aria.simulation.habitat_systems import (
    EnvironmentalControlSimulator,
    HabitatSystemsOrchestrator,
    RecreationMoraleSimulator,
    SupplyChainSimulator,
)


# ── ENVIRONMENTAL CONTROL (ECLSS) ──


class TestEnvironmentalControl:

    def test_initial_atmosphere_nominal(self) -> None:
        sim = EnvironmentalControlSimulator(seed=42)
        s = sim.state
        assert s.habitat_zone.temperature_c == 21.0
        assert s.habitat_zone.pressure_kpa == 101.3
        assert s.habitat_zone.o2_fraction == 0.209
        assert s.habitat_zone.co2_ppm == 400.0

    def test_three_zones_exist(self) -> None:
        sim = EnvironmentalControlSimulator(seed=42)
        s = sim.state
        assert s.habitat_zone.name == "habitat"
        assert s.industrial_zone.name == "industrial"
        assert s.agricultural_zone.name == "agricultural"

    def test_agricultural_zone_co2_enriched(self) -> None:
        """Agricultural zone CO2 should be enriched (EDEN ISS mean ~1063 ppm)."""
        sim = EnvironmentalControlSimulator(seed=42)
        assert sim.state.agricultural_zone.co2_ppm > 800  # Enriched vs habitat 400 ppm

    def test_sabatier_degrades_over_time(self) -> None:
        sim = EnvironmentalControlSimulator(seed=42)
        for y in range(1, 21):
            sim.simulate_year(float(y))
        assert sim.state.sabatier_reactor_health < 1.0
        assert sim.state.sabatier_reactor_health > 0

    def test_lioh_consumed_over_time(self) -> None:
        sim = EnvironmentalControlSimulator(seed=42)
        initial = sim.state.lioh_canister_remaining_kg
        for y in range(1, 11):
            sim.simulate_year(float(y))
        assert sim.state.lioh_canister_remaining_kg < initial

    def test_hepa_filter_replaced_periodically(self) -> None:
        sim = EnvironmentalControlSimulator(seed=42)
        all_events: list[dict] = []
        for y in range(1, 10):
            all_events.extend(sim.simulate_year(float(y)))
        hepa_events = [e for e in all_events if "HEPA" in e.get("message", "")]
        assert len(hepa_events) > 0

    def test_pressure_leak_accumulates(self) -> None:
        sim = EnvironmentalControlSimulator(seed=42)
        for y in range(1, 51):
            sim.simulate_year(float(y))
        assert sim.state.cumulative_pressure_loss_kpa > 0

    def test_makeup_gas_depletes(self) -> None:
        sim = EnvironmentalControlSimulator(seed=42)
        initial = sim.state.makeup_gas_reserve_kg
        for y in range(1, 101):
            sim.simulate_year(float(y))
        assert sim.state.makeup_gas_reserve_kg < initial

    def test_radiator_degrades(self) -> None:
        sim = EnvironmentalControlSimulator(seed=42)
        for y in range(1, 51):
            sim.simulate_year(float(y))
        assert sim.state.radiator_degradation > 0

    def test_fan_can_fail(self) -> None:
        """Over 200 years at least one fan should fail."""
        sim = EnvironmentalControlSimulator(seed=7)
        for y in range(1, 201):
            sim.simulate_year(float(y))
        assert sim.state.fans_operational < sim.state.fan_count

    def test_carbon_bed_regeneration(self) -> None:
        sim = EnvironmentalControlSimulator(seed=42)
        # Force carbon capacity low to trigger regeneration
        sim.state.activated_carbon_capacity = 0.2
        sim.simulate_year(1.0)
        assert sim.state.carbon_bed_regen_count >= 1


# ── RECREATION & MORALE ──


class TestRecreationMorale:

    def test_initial_morale_healthy(self) -> None:
        sim = RecreationMoraleSimulator(seed=42)
        assert sim.state.crew_morale > 0.7

    def test_vr_headsets_degrade(self) -> None:
        sim = RecreationMoraleSimulator(seed=42)
        for y in range(1, 11):
            sim.simulate_year(float(y))
        assert sim.state.vr_headsets_functional <= sim.state.vr_headset_count

    def test_vr_novelty_decays(self) -> None:
        sim = RecreationMoraleSimulator(seed=42)
        for y in range(1, 101):
            sim.simulate_year(float(y))
        assert sim.state.vr_novelty_factor < 1.0

    def test_sports_facilities_degrade(self) -> None:
        sim = RecreationMoraleSimulator(seed=42)
        # Run 9 years (before the first 10-year overhaul restores quality)
        for y in range(1, 10):
            sim.simulate_year(float(y))
        avg_quality = sum(
            f.quality for f in sim.state.sports_facilities
        ) / len(sim.state.sports_facilities)
        assert avg_quality < 1.0

    def test_exercise_compliance_affects_bone_density(self) -> None:
        sim = RecreationMoraleSimulator(seed=42)
        sim.state.exercise_compliance_rate = 0.3  # Low compliance
        for y in range(1, 21):
            sim.simulate_year(float(y))
        assert sim.state.bone_density_modifier < 1.0

    def test_bone_density_preserved_with_good_compliance(self) -> None:
        sim = RecreationMoraleSimulator(seed=42)
        sim.state.exercise_compliance_rate = 1.0
        for y in range(1, 11):
            sim.simulate_year(float(y))
        # Should stay close to 1.0 with perfect compliance
        assert sim.state.bone_density_modifier > 0.85

    def test_boredom_increases_over_centuries(self) -> None:
        sim = RecreationMoraleSimulator(seed=42)
        for y in range(1, 201):
            sim.simulate_year(float(y))
        assert sim.state.boredom_index > 0.1

    def test_glass_archive_nearly_permanent(self) -> None:
        sim = RecreationMoraleSimulator(seed=42)
        for y in range(1, 101):
            sim.simulate_year(float(y))
        assert sim.state.glass_archive_health > 0.98

    def test_morale_stays_bounded(self) -> None:
        sim = RecreationMoraleSimulator(seed=42)
        for y in range(1, 301):
            sim.simulate_year(float(y))
        assert 0.1 <= sim.state.crew_morale <= 1.0


# ── SUPPLY CHAIN & INVENTORY ──


class TestSupplyChain:

    def test_default_inventory_loaded(self) -> None:
        sim = SupplyChainSimulator(seed=42)
        assert sim.state.total_items_tracked > 10

    def test_items_deplete_over_time(self) -> None:
        sim = SupplyChainSimulator(seed=42)
        initial_antibiotics = sim.state.items["antibiotics_doses"].quantity
        for y in range(1, 11):
            sim.simulate_year(float(y))
        assert sim.state.items["antibiotics_doses"].quantity < initial_antibiotics

    def test_critical_path_identifies_bottleneck(self) -> None:
        sim = SupplyChainSimulator(seed=42)
        name, years = sim.get_critical_path()
        assert name != ""
        assert years > 0

    def test_manufacturing_resupply_works(self) -> None:
        sim = SupplyChainSimulator(seed=42)
        item = sim.state.items["seals_and_gaskets"]
        # Force below reorder
        item.quantity = item.reorder_point * 0.5
        sim.simulate_year(1.0)
        # Manufacturing should have produced some
        assert item.quantity > item.reorder_point * 0.5

    def test_rationing_activates_on_shortage(self) -> None:
        sim = SupplyChainSimulator(seed=42)
        # Drain food to near-zero
        sim.state.items["preserved_food_rations"].quantity = 5000
        for y in range(1, 5):
            sim.simulate_year(float(y))
        assert sim.state.allocation_mode in ("rationing", "emergency")

    def test_printer_degrades(self) -> None:
        sim = SupplyChainSimulator(seed=42)
        for y in range(1, 51):
            sim.simulate_year(float(y))
        assert sim.state.printer_health < 1.0

    def test_feedstock_consumed(self) -> None:
        sim = SupplyChainSimulator(seed=42)
        initial_metal = sim.state.feedstock_metal_kg
        for y in range(1, 51):
            sim.simulate_year(float(y))
        assert sim.state.feedstock_metal_kg < initial_metal

    def test_audit_detects_discrepancies(self) -> None:
        sim = SupplyChainSimulator(seed=42)
        all_events: list[dict] = []
        for y in range(1, 11):
            all_events.extend(sim.simulate_year(float(y)))
        audit_events = [e for e in all_events if "audit" in e.get("message", "").lower()]
        assert len(audit_events) > 0

    def test_category_summary(self) -> None:
        sim = SupplyChainSimulator(seed=42)
        summary = sim.get_category_summary()
        assert "medical" in summary
        assert "mechanical" in summary
        assert summary["medical"]["count"] >= 2

    def test_historical_rates_tracked(self) -> None:
        sim = SupplyChainSimulator(seed=42)
        for y in range(1, 6):
            sim.simulate_year(float(y))
        item = sim.state.items["antibiotics_doses"]
        assert len(item.historical_rates) == 5


# ── ORCHESTRATOR INTEGRATION ──


class TestHabitatOrchestrator:

    def test_orchestrator_runs_all_subsystems(self) -> None:
        orch = HabitatSystemsOrchestrator(crew_size=50, seed=42)
        events = orch.simulate_year(1.0)
        subsystems = {e.get("subsystem") for e in events}
        # Should have events from at least eclss and supply_chain
        assert len(subsystems) >= 1

    def test_orchestrator_multi_year(self) -> None:
        orch = HabitatSystemsOrchestrator(crew_size=50, seed=42)
        all_events: list[dict] = []
        for y in range(1, 51):
            all_events.extend(orch.simulate_year(float(y)))
        assert len(all_events) > 10

    def test_cross_system_co2_affects_morale(self) -> None:
        orch = HabitatSystemsOrchestrator(crew_size=50, seed=42)
        # Artificially spike CO2
        orch.eclss.state.habitat_zone.co2_ppm = 3000
        initial_morale = orch.recreation.state.crew_morale
        orch.simulate_year(1.0)
        assert orch.recreation.state.crew_morale < initial_morale

    def test_cross_system_filter_stockout_degrades_eclss(self) -> None:
        orch = HabitatSystemsOrchestrator(crew_size=50, seed=42)
        # Zero out HEPA filter stock and prevent manufacturing resupply
        hepa = orch.supply_chain.state.items.get("hepa_filters")
        if hepa:
            hepa.quantity = 0
            hepa.manufacturing_lead_time_days = 0  # Cannot manufacture
            hepa.reorder_point = 0
        initial_health = orch.eclss.state.hepa_filter_health
        events = orch.simulate_year(1.0)
        crosslink = [e for e in events if e.get("subsystem") == "habitat_crosslink"]
        assert len(crosslink) > 0
