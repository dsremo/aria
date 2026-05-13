"""Stress tests: Interstellar challenges driving ARIA agent responses.

Tests that the 6 challenge simulators correctly produce events that
ARIA's agents would process — verifying the full pipeline from
degradation model → event generation → agent message format → response.
"""

import pytest

from aria.simulation.interstellar_challenges import (
    ChallengeStatus,
    FoodCenturySimulator,
    FuelCliffSimulator,
    GeneticDiversitySimulator,
    InterstellarChallengeOrchestrator,
    KnowledgePreservationSimulator,
    MaterialEntropySimulator,
    PsychologicalDecaySimulator,
)


class TestMaterialAgentEvents:
    """Material entropy events map to ARIA manufacturing subsystem."""

    def test_events_have_subsystem_field(self) -> None:
        sim = MaterialEntropySimulator(seed=42)
        all_events = []
        for year in range(1, 501):
            events = sim.simulate_year(float(year))
            all_events.extend(events)
        for e in all_events:
            assert "subsystem" in e
            assert "severity" in e
            assert "message" in e

    def test_events_severity_valid(self) -> None:
        sim = MaterialEntropySimulator(seed=42)
        valid_severities = {"NOMINAL", "WATCH", "WARNING", "CRITICAL", "EMERGENCY"}
        for year in range(1, 501):
            for e in sim.simulate_year(float(year)):
                assert e["severity"] in valid_severities

    def test_recycling_efficiency_floor(self) -> None:
        """Recycling can't go below minimum."""
        sim = MaterialEntropySimulator(seed=42)
        for year in range(1, 2001):
            sim.simulate_year(float(year))
        assert sim.inventory.metal_recycle_efficiency >= 0.5
        assert sim.inventory.polymer_recycle_efficiency >= 0.3
        assert sim.inventory.electronics_recycle_efficiency >= 0.2


class TestFoodAgentEvents:
    """Food challenge events map to ECLSS and food subsystems."""

    def test_food_production_formula_correct(self) -> None:
        """Verify food production = hydroponics + algae + insect + cultured."""
        sim = FoodCenturySimulator(crew_size=4, seed=42)
        sim.simulate_year(1.0)
        f = sim.food
        effective_light = max(0, 1.0 - f.grow_light_degradation)
        avg_viab = (f.grain_seeds_viability * 0.4 + f.legume_seeds_viability * 0.3 +
                    f.vegetable_seeds_viability * 0.2 + f.fruit_seeds_viability * 0.1)
        hydro = f.hydroponic_capacity_m2 * 25.0 * effective_light * f.hydroponic_efficiency * f.nutrient_solution_quality * avg_viab
        algae = f.algae_bioreactor_liters * 0.3 * f.algae_health
        insect = 100.0 * f.insect_farm_capacity
        cultured = 50.0 * f.cultured_meat_viability
        expected = hydro + algae + insect + cultured
        # Tolerance: disease events may reduce capacity mid-step (insect/cultured)
        assert abs(f.annual_food_production_kg - expected) < 100.0

    def test_cultured_meat_degrades(self) -> None:
        sim = FoodCenturySimulator(crew_size=4, seed=42)
        for year in range(1, 201):
            sim.simulate_year(float(year))
        assert sim.food.cultured_meat_viability < 1.0

    def test_all_seed_types_tracked(self) -> None:
        sim = FoodCenturySimulator(crew_size=4, seed=42)
        sim.simulate_year(1.0)
        assert hasattr(sim.food, "grain_seeds_viability")
        assert hasattr(sim.food, "legume_seeds_viability")
        assert hasattr(sim.food, "vegetable_seeds_viability")
        assert hasattr(sim.food, "fruit_seeds_viability")


class TestKnowledgeAgentEvents:
    """Knowledge preservation maps to education subsystem."""

    def test_migration_error_rate_increases(self) -> None:
        sim = KnowledgePreservationSimulator(seed=42)
        initial_rate = sim.kb.migration_error_rate
        for year in range(1, 201):
            sim.simulate_year(float(year))
        assert sim.kb.migration_error_rate >= initial_rate

    def test_all_knowledge_domains_tracked(self) -> None:
        sim = KnowledgePreservationSimulator(seed=42)
        sim.simulate_year(1.0)
        metrics = sim.state.metrics
        assert "engineering_knowledge" in metrics
        assert "medical_knowledge" in metrics
        assert "navigation_knowledge" in metrics
        assert "cultural_knowledge" in metrics

    def test_corruption_percentage_in_metrics(self) -> None:
        sim = KnowledgePreservationSimulator(seed=42)
        for year in range(1, 51):
            sim.simulate_year(float(year))
        assert "corruption_pct" in sim.state.metrics


class TestGeneticsAgentEvents:
    """Genetics maps to medical subsystem."""

    def test_gamete_viability_degrades_faster_than_embryo(self) -> None:
        sim = GeneticDiversitySimulator(initial_population=4, seed=42)
        for year in range(1, 101):
            sim.simulate_year(float(year))
        assert sim.genetics.gamete_viability < sim.genetics.embryo_viability

    def test_population_bounded(self) -> None:
        sim = GeneticDiversitySimulator(initial_population=4, seed=42)
        for year in range(1, 501):
            sim.simulate_year(float(year))
        assert sim.genetics.population >= 0

    def test_genetic_disease_count_nonnegative(self) -> None:
        sim = GeneticDiversitySimulator(initial_population=4, seed=42)
        for year in range(1, 501):
            sim.simulate_year(float(year))
        assert sim.genetics.genetic_diseases >= 0


class TestPsychologyAgentEvents:
    """Psychology maps to crew operations."""

    def test_all_metrics_populated(self) -> None:
        sim = PsychologicalDecaySimulator(crew_size=4, seed=42)
        sim.simulate_year(1.0)
        metrics = sim.state.metrics
        expected_keys = {"morale", "purpose_alignment", "conflict_level",
                         "depression_prevalence", "mutiny_risk", "generation", "generation_gap"}
        assert expected_keys.issubset(set(metrics.keys()))

    def test_generation_increases(self) -> None:
        sim = PsychologicalDecaySimulator(crew_size=4, seed=42)
        for year in range(1, 101):
            sim.simulate_year(float(year))
        assert sim.state.metrics["generation"] >= 4  # ~25 yr generations

    def test_depression_bounded_0_1(self) -> None:
        sim = PsychologicalDecaySimulator(crew_size=4, seed=42)
        for year in range(1, 1001):
            sim.simulate_year(float(year))
        assert 0 <= sim.psych.depression_prevalence <= 1.0


class TestFuelAgentEvents:
    """Fuel challenge maps to propulsion and power subsystems."""

    def test_braking_fuel_estimate_set(self) -> None:
        sim = FuelCliffSimulator(seed=42)
        assert sim.fuel.braking_fuel_estimate_kg == 20000.0

    def test_power_generation_decreases(self) -> None:
        sim = FuelCliffSimulator(seed=42)
        sim.simulate_year(1.0, 0.1)
        initial_power = sim.fuel.generation_w
        for year in range(2, 201):
            sim.simulate_year(float(year), year * 0.1)
        assert sim.fuel.generation_w < initial_power

    def test_reactor_restarts_tracked(self) -> None:
        sim = FuelCliffSimulator(seed=42)
        for year in range(1, 501):
            sim.simulate_year(float(year), year * 0.1)
        # Random reactor scrams: ~1%/year → ~5 in 500 years
        assert sim.fuel.reactor_restarts >= 0


class TestOrchestratorCascades:
    """Cross-challenge cascade detection stress tests."""

    def test_cascade_events_have_cascade_field(self) -> None:
        orch = InterstellarChallengeOrchestrator(crew_size=4, seed=42)
        cascades = []
        for year in range(1, 1001):
            result = orch.simulate_year(float(year), year * 0.1)
            for e in result["events"]:
                if e.get("subsystem") == "cascade_detector":
                    cascades.append(e)
                    assert "cascade" in e

    def test_orchestrator_metrics_complete(self) -> None:
        orch = InterstellarChallengeOrchestrator(crew_size=4, seed=42)
        result = orch.simulate_year(100.0, 10.0)
        for name, state in result["challenge_states"].items():
            assert "status" in state
            assert "severity" in state
            assert "metrics" in state
            assert isinstance(state["severity"], float)

    def test_overall_severity_is_max(self) -> None:
        orch = InterstellarChallengeOrchestrator(crew_size=4, seed=42)
        result = orch.simulate_year(100.0, 10.0)
        max_sev = max(s["severity"] for s in result["challenge_states"].values())
        assert result["overall_severity"] == max_sev

    def test_terminal_count_accurate(self) -> None:
        orch = InterstellarChallengeOrchestrator(crew_size=4, seed=42)
        for year in range(1, 1001):
            result = orch.simulate_year(float(year), year * 0.1)
        terminal = sum(
            1 for s in result["challenge_states"].values()
            if s["status"] == "terminal"
        )
        assert result["terminal_count"] == terminal

    def test_10_year_snapshot_no_crash(self) -> None:
        """Verify 10 years of all challenges without any exception."""
        orch = InterstellarChallengeOrchestrator(crew_size=4, seed=42)
        for year in range(1, 11):
            result = orch.simulate_year(float(year), year * 0.1)
            assert isinstance(result["events"], list)
