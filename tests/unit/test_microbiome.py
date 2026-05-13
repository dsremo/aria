"""Tests for microbiome evolution simulation."""

from __future__ import annotations

import math

import pytest

from aria.simulation.microbiome_evolution import (
    AMR_CLASSES,
    COLONIZATION_RATE,
    DYSBIOSIS_THRESHOLD,
    GENERATIONS_PER_YEAR,
    GutMicrobiomeSimulator,
    MicrobiomeEvolutionSimulator,
    SoilMicrobiomeSimulator,
    SurfaceMicrobiomeSimulator,
    WaterMicrobiomeSimulator,
    shannon_index,
)


# ── Shannon index ──────────────────────────────────────────────

class TestShannonIndex:
    def test_uniform_distribution(self):
        """Uniform distribution of N species → H' = ln(N)."""
        n = 100
        abundances = [1 / n] * n
        h = shannon_index(abundances)
        assert math.isclose(h, math.log(n), rel_tol=1e-6)

    def test_single_species_dominance(self):
        """Single species at 100% → H' = 0."""
        assert shannon_index([1.0]) == 0.0

    def test_empty_input(self):
        assert shannon_index([]) == 0.0


# ── Gut microbiome ─────────────────────────────────────────────

class TestGutMicrobiome:
    def test_initial_state(self):
        sim = GutMicrobiomeSimulator(crew_size=1000, seed=42)
        assert sim.state.species_count == 1000
        assert sim.state.shannon_diversity > 3.0
        assert sim.state.dysbiosis_risk == 0.0
        assert len(sim.state.species_abundances) == 1000

    def test_diversity_declines_over_centuries(self):
        """Shannon diversity should decline due to drift + diet pressure."""
        sim = GutMicrobiomeSimulator(crew_size=1000, seed=42)
        initial_h = sim.state.shannon_diversity

        for yr in range(1, 201):
            sim.simulate_year(float(yr))

        assert sim.state.shannon_diversity < initial_h
        assert sim.state.species_count < 1000

    def test_diet_diversity_declines(self):
        sim = GutMicrobiomeSimulator(crew_size=1000, seed=42)
        initial_diet = sim.state.diet_diversity_index

        for yr in range(1, 51):
            sim.simulate_year(float(yr))

        assert sim.state.diet_diversity_index < initial_diet
        assert sim.state.diet_diversity_index >= 0.3  # floor

    def test_hgt_rate_increases_over_time(self):
        sim = GutMicrobiomeSimulator(crew_size=1000, seed=42)
        sim.simulate_year(1.0)
        early_hgt = sim.state.hgt_rate

        for yr in range(2, 301):
            sim.simulate_year(float(yr))

        assert sim.state.hgt_rate > early_hgt

    def test_simulate_year_returns_events(self):
        sim = GutMicrobiomeSimulator(crew_size=1000, seed=42)
        events = sim.simulate_year(1.0)
        assert isinstance(events, list)
        for e in events:
            assert "year" in e
            assert "severity" in e
            assert "subsystem" in e


# ── Surface microbiome ─────────────────────────────────────────

class TestSurfaceMicrobiome:
    def test_colonization_increases(self):
        sim = SurfaceMicrobiomeSimulator(seed=42)
        for yr in range(1, 51):
            sim.simulate_year(float(yr))

        for material in COLONIZATION_RATE:
            assert sim.state.surface_colonization[material] > 0.0

    def test_amr_prevalence_increases(self):
        sim = SurfaceMicrobiomeSimulator(seed=42)
        initial_amr = dict(sim.state.amr_prevalence)

        for yr in range(1, 101):
            sim.simulate_year(float(yr))

        for drug_class in AMR_CLASSES:
            assert sim.state.amr_prevalence[drug_class] > initial_amr[drug_class]

    def test_stainless_steel_colonizes_faster_than_glass(self):
        sim = SurfaceMicrobiomeSimulator(seed=42)
        for yr in range(1, 31):
            sim.simulate_year(float(yr))

        steel = sim.state.surface_colonization["stainless_steel"]
        glass = sim.state.surface_colonization["glass"]
        assert steel > glass


# ── Soil microbiome ────────────────────────────────────────────

class TestSoilMicrobiome:
    def test_initial_healthy_state(self):
        sim = SoilMicrobiomeSimulator(seed=42)
        assert sim.state.mycorrhizal_health == 1.0
        assert sim.state.crop_yield_modifier == 1.0
        assert sim.state.soil_organic_matter_pct == 5.0

    def test_mycorrhizal_species_can_decline(self):
        """Over long periods, AMF species count should decrease (drift)."""
        sim = SoilMicrobiomeSimulator(seed=42)
        initial = sim.state.mycorrhizal_species_count

        for yr in range(1, 501):
            sim.simulate_year(float(yr))

        assert sim.state.mycorrhizal_species_count <= initial

    def test_crop_yield_bounded(self):
        sim = SoilMicrobiomeSimulator(seed=42)
        for yr in range(1, 101):
            sim.simulate_year(float(yr))

        assert 0.0 <= sim.state.crop_yield_modifier <= 1.5


# ── Water microbiome ───────────────────────────────────────────

class TestWaterMicrobiome:
    def test_legionella_temperature_dependence(self):
        """Growth factor should peak near 37°C and be zero below 20°C."""
        sim = WaterMicrobiomeSimulator(seed=42)
        assert sim._legionella_growth_factor(37.0) > sim._legionella_growth_factor(25.0)
        assert sim._legionella_growth_factor(15.0) == 0.0
        assert sim._legionella_growth_factor(65.0) == 0.0

    def test_chloramine_resistance_increases(self):
        sim = WaterMicrobiomeSimulator(seed=42)
        initial = sim.state.chloramine_resistant_fraction

        for yr in range(1, 101):
            sim.simulate_year(float(yr))

        assert sim.state.chloramine_resistant_fraction > initial


# ── Unified simulator ──────────────────────────────────────────

class TestMicrobiomeEvolutionSimulator:
    def test_init_defaults(self):
        sim = MicrobiomeEvolutionSimulator()
        assert sim.crew_size == 1000
        assert sim.mission_year == 0.0

    def test_simulate_year_produces_events(self):
        sim = MicrobiomeEvolutionSimulator(crew_size=1000, seed=42)
        events = sim.simulate_year(1.0)
        assert isinstance(events, list)

    def test_get_report_structure(self):
        sim = MicrobiomeEvolutionSimulator(crew_size=1000, seed=42)
        sim.simulate_year(1.0)
        report = sim.get_report()

        assert "gut_diversity_index" in report
        assert "resistance_genes" in report
        assert "pathogen_risk" in report
        assert "soil_health" in report
        assert "gut" in report
        assert "surface" in report
        assert "soil" in report
        assert "water" in report
        assert report["mission_year"] == 1.0
        assert report["crew_size"] == 1000

    def test_multi_year_simulation(self):
        sim = MicrobiomeEvolutionSimulator(crew_size=1000, seed=42)
        all_events = []
        for yr in range(1, 51):
            all_events.extend(sim.simulate_year(float(yr)))

        report = sim.get_report()
        assert report["history_length"] == 50
        assert report["mission_year"] == 50.0

    def test_reproducibility_with_seed(self):
        """Same seed should produce identical results."""
        sim1 = MicrobiomeEvolutionSimulator(crew_size=1000, seed=99)
        sim2 = MicrobiomeEvolutionSimulator(crew_size=1000, seed=99)

        events1 = sim1.simulate_year(1.0)
        events2 = sim2.simulate_year(1.0)

        r1 = sim1.get_report()
        r2 = sim2.get_report()

        assert r1["gut_diversity_index"] == r2["gut_diversity_index"]
        assert r1["soil_health"] == r2["soil_health"]
        assert len(events1) == len(events2)

    def test_biological_constants(self):
        """Verify key biological constants are realistic."""
        # E. coli: ~26,000 generations per year (20min generation time)
        assert 25_000 < GENERATIONS_PER_YEAR < 30_000
        # Dysbiosis threshold is clinically reasonable
        assert 2.0 < DYSBIOSIS_THRESHOLD < 3.5
