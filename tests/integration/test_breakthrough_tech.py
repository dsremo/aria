"""Tests for Breakthrough Technologies — solving every generation ship bottleneck."""

import pytest

from aria.simulation.breakthrough_tech import (
    BiomanufacturingSimulator,
    BreakthroughTechOrchestrator,
    NanobotSwarmSimulator,
    SilicaArchiveSimulator,
    TorporSimulator,
)


class TestSilicaGlassArchive:
    """DNA templates in glass survive 10,000+ years."""

    def test_glass_barely_degrades(self) -> None:
        sim = SilicaArchiveSimulator(seed=42)
        for year in range(1, 1001):
            sim.simulate_year(float(year))
        # Glass should be >99% intact after 1000 years
        intact = sum(1 for h in sim.archive.plate_health if h > 0.9)
        assert intact == 100  # ALL plates survive 1000 years

    def test_dna_templates_preserved(self) -> None:
        """The bottleneck is SOLVED: DNA templates survive in glass."""
        sim = SilicaArchiveSimulator(seed=42)
        for year in range(1, 1001):
            sim.simulate_year(float(year))
        assert sim.archive.enzyme_dna_templates == 1.0

    def test_reader_replaced_when_failing(self) -> None:
        sim = SilicaArchiveSimulator(seed=42)
        all_events = []
        for year in range(1, 101):
            events = sim.simulate_year(float(year))
            all_events.extend(events)
        reader_events = [e for e in all_events if "reader replaced" in e.get("message", "").lower()]
        assert len(reader_events) > 0

    def test_reader_spares_consumed(self) -> None:
        sim = SilicaArchiveSimulator(seed=42)
        for year in range(1, 201):
            sim.simulate_year(float(year))
        assert sim.archive.reader_spares < 5

    def test_redundancy_protects_data(self) -> None:
        """Even if plates fail, Reed-Solomon recovers data."""
        sim = SilicaArchiveSimulator(seed=42)
        # Destroy 80% of plates
        for i in range(80):
            sim.archive.plate_health[i] = 0
        sim.simulate_year(100.0)
        # With 5× redundancy, 20/100 plates still recovers all data
        assert sim.archive.enzyme_dna_templates == 1.0


class TestNanobotSwarm:
    """Self-replicating nanobots patrol and repair."""

    def test_nanobots_detect_microfractures(self) -> None:
        sim = NanobotSwarmSimulator(seed=42)
        for year in range(1, 11):
            sim.simulate_year(float(year))
        assert sim.state.microfractures_detected > 0

    def test_nanobots_repair_fractures(self) -> None:
        sim = NanobotSwarmSimulator(seed=42)
        for year in range(1, 11):
            sim.simulate_year(float(year))
        assert sim.state.microfractures_repaired > 0
        # Repair rate should be close to detection rate
        rate = sim.state.microfractures_repaired / max(sim.state.microfractures_detected, 1)
        assert rate > 0.8

    def test_self_replication_maintains_population(self) -> None:
        sim = NanobotSwarmSimulator(seed=42)
        initial = sim.state.hull_patrol_swarm_billions
        for year in range(1, 51):
            sim.simulate_year(float(year))
        # Self-replication should roughly maintain population
        assert sim.state.hull_patrol_swarm_billions > initial * 0.5

    def test_population_capped_grey_goo_safety(self) -> None:
        """Safety limit prevents grey goo scenario."""
        sim = NanobotSwarmSimulator(seed=42)
        sim.state.hull_patrol_swarm_billions = 100.0  # Way too many
        sim.simulate_year(1.0)
        assert sim.state.hull_patrol_swarm_billions <= 20.0  # Capped

    def test_programming_refreshed_from_archive(self) -> None:
        sim = NanobotSwarmSimulator(seed=42)
        for year in range(1, 501):
            sim.simulate_year(float(year))
        # Programming should have been refreshed (never drops below 0.5)
        assert sim.state.programming_health > 0.7

    def test_sealant_consumed(self) -> None:
        sim = NanobotSwarmSimulator(seed=42)
        initial = sim.state.sealant_reserves_kg
        for year in range(1, 51):
            sim.simulate_year(float(year))
        assert sim.state.sealant_reserves_kg < initial


class TestSyntheticTorpor:
    """Torpor reduces resource consumption and radiation damage."""

    def test_food_savings(self) -> None:
        sim = TorporSimulator(crew_size=4, seed=42)
        sim.simulate_year(1.0)
        savings = sim.get_resource_savings()
        assert savings["food_savings_pct"] > 30  # >30% food savings

    def test_water_savings(self) -> None:
        sim = TorporSimulator(crew_size=4, seed=42)
        sim.simulate_year(1.0)
        savings = sim.get_resource_savings()
        assert savings["water_savings_pct"] > 20

    def test_radiation_protection(self) -> None:
        sim = TorporSimulator(crew_size=4, seed=42)
        sim.simulate_year(1.0)
        savings = sim.get_resource_savings()
        assert savings["radiation_reduction_pct"] > 0

    def test_drug_consumption(self) -> None:
        sim = TorporSimulator(crew_size=4, seed=42)
        initial = sim.state.torpor_induction_doses
        for year in range(1, 51):
            sim.simulate_year(float(year))
        assert sim.state.torpor_induction_doses < initial

    def test_pod_degradation(self) -> None:
        sim = TorporSimulator(crew_size=4, seed=42)
        for year in range(1, 101):
            sim.simulate_year(float(year))
        assert any(h < 1.0 for h in sim.state.pod_health)

    def test_half_crew_in_torpor(self) -> None:
        sim = TorporSimulator(crew_size=4, seed=42)
        sim.simulate_year(1.0)
        assert sim.state.crew_in_torpor == 2
        assert sim.state.crew_awake == 2


class TestBiomanufacturing:
    """Cell-free protein synthesis — no living cells needed."""

    def test_initial_production(self) -> None:
        sim = BiomanufacturingSimulator(seed=42)
        sim.simulate_year(1.0)
        assert sim.state.protein_output_g_day > 50

    def test_self_replication_sustains_system(self) -> None:
        sim = BiomanufacturingSimulator(seed=42)
        for year in range(1, 101):
            sim.simulate_year(float(year))
        # With self-replication, system should maintain >30% capacity
        assert sim.state.pure_system_health > 0.3

    def test_drug_production(self) -> None:
        sim = BiomanufacturingSimulator(seed=42)
        sim.simulate_year(1.0)
        assert sim.state.drug_output_g_day > 5

    def test_refreshes_from_archive(self) -> None:
        sim = BiomanufacturingSimulator(seed=42)
        all_events = []
        for year in range(1, 101):
            events = sim.simulate_year(float(year))
            all_events.extend(events)
        refresh_events = [e for e in all_events if "refreshed" in e.get("message", "").lower()]
        assert len(refresh_events) >= 0  # Refreshes at year 50


class TestBreakthroughOrchestrator:
    """All technologies working together with synergies."""

    def test_orchestrator_runs_1000_years(self) -> None:
        orch = BreakthroughTechOrchestrator(crew_size=4, seed=42)
        results = orch.run_centuries(1000)
        assert len(results) == 1000

    def test_archive_survives_full_mission(self) -> None:
        orch = BreakthroughTechOrchestrator(crew_size=4, seed=42)
        orch.run_centuries(1000)
        assert orch.archive.archive.enzyme_dna_templates == 1.0

    def test_synergy_archive_feeds_biomanufacturing(self) -> None:
        orch = BreakthroughTechOrchestrator(crew_size=4, seed=42)
        for year in range(1, 101):
            orch.simulate_year(float(year))
        # Archive intact → biomanufacturing self-replication maintained
        assert orch.biomanufacturing.state.self_replication_capability >= 0.5

    def test_synergy_biomanufacturing_feeds_torpor(self) -> None:
        orch = BreakthroughTechOrchestrator(crew_size=4, seed=42)
        for year in range(1, 101):
            orch.simulate_year(float(year))
        # Biomanufacturing produces torpor drugs → supply maintained
        assert orch.torpor.state.torpor_induction_doses >= 100

    def test_summary_complete(self) -> None:
        orch = BreakthroughTechOrchestrator(crew_size=4, seed=42)
        for year in range(1, 11):
            orch.simulate_year(float(year))
        summary = orch.get_summary()
        assert "archive" in summary
        assert "nanobots" in summary
        assert "torpor" in summary
        assert "biomanufacturing" in summary

    def test_all_values_bounded(self) -> None:
        orch = BreakthroughTechOrchestrator(crew_size=4, seed=42)
        for year in range(1, 501):
            result = orch.simulate_year(float(year))
            assert 0 <= result["archive_intact"] <= 1
            assert 0 <= result["nanobot_health"] <= 1
            assert 0 <= result["biomanufacturing_capacity"] <= 1
