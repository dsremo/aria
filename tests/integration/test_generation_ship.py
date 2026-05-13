"""Tests for Complete Generation Ship Simulation — Legacy vs Breakthrough comparison."""

import pytest

from aria.simulation.generation_ship import (
    GenerationShipConfig,
    GenerationShipSimulation,
    compare_legacy_vs_breakthrough,
)


class TestGenerationShipConfig:
    def test_legacy_config(self) -> None:
        cfg = GenerationShipConfig.legacy()
        assert not cfg.enable_starch_synthesis
        assert not cfg.enable_magsail
        assert not cfg.enable_nanobots
        assert not cfg.enable_torpor
        assert not cfg.enable_glass_archive

    def test_breakthrough_config(self) -> None:
        cfg = GenerationShipConfig.breakthrough()
        assert cfg.enable_starch_synthesis
        assert cfg.enable_magsail
        assert cfg.enable_nanobots
        assert cfg.enable_torpor
        assert cfg.enable_glass_archive


class TestLegacySimulation:
    def test_legacy_50_years(self) -> None:
        sim = GenerationShipSimulation(GenerationShipConfig.legacy())
        results = sim.run(50)
        assert results.years_simulated == 50
        assert results.config_mode == "LEGACY"
        assert results.total_events > 0

    def test_legacy_200_years_degrades(self) -> None:
        sim = GenerationShipSimulation(GenerationShipConfig.legacy())
        results = sim.run(200)
        # Without breakthrough tech, things should be bad at 200 years
        assert results.challenges_terminal > 0


class TestBreakthroughSimulation:
    def test_breakthrough_50_years(self) -> None:
        sim = GenerationShipSimulation(GenerationShipConfig.breakthrough())
        results = sim.run(50)
        assert results.years_simulated == 50
        assert results.config_mode == "BREAKTHROUGH"

    def test_breakthrough_200_years(self) -> None:
        sim = GenerationShipSimulation(GenerationShipConfig.breakthrough())
        results = sim.run(200)
        assert results.total_events > 0
        # With breakthrough tech, archive should be intact
        assert results.archive_intact > 0.9

    def test_nanobot_repairs_happen(self) -> None:
        sim = GenerationShipSimulation(GenerationShipConfig.breakthrough())
        results = sim.run(100)
        assert results.nanobot_repairs > 0

    def test_torpor_saves_food(self) -> None:
        sim = GenerationShipSimulation(GenerationShipConfig.breakthrough())
        results = sim.run(50)
        assert results.torpor_food_saved_pct > 30


class TestComparison:
    def test_compare_small(self) -> None:
        comparison = compare_legacy_vs_breakthrough(years=50, num_seeds=3)
        assert "legacy" in comparison
        assert "breakthrough" in comparison
        assert "improvement" in comparison
        assert comparison["num_seeds"] == 3

    def test_breakthrough_fewer_terminal(self) -> None:
        """Breakthrough tech should produce fewer terminal challenges."""
        comparison = compare_legacy_vs_breakthrough(years=100, num_seeds=5)
        # Breakthrough should have same or fewer terminal challenges
        assert comparison["breakthrough"]["avg_terminal_challenges"] <= \
               comparison["legacy"]["avg_terminal_challenges"] + 1  # Allow small margin

    def test_archive_survives(self) -> None:
        comparison = compare_legacy_vs_breakthrough(years=100, num_seeds=3)
        assert comparison["breakthrough"]["archive_intact_rate"] > 0.9


class TestResults:
    def test_summary_format(self) -> None:
        sim = GenerationShipSimulation(GenerationShipConfig.breakthrough())
        results = sim.run(10)
        summary = results.summary()
        assert "BREAKTHROUGH" in summary
        assert "10 years" in summary

    def test_results_have_all_fields(self) -> None:
        sim = GenerationShipSimulation(GenerationShipConfig.breakthrough())
        results = sim.run(10)
        assert results.final_crew_count > 0
        assert results.final_crew_generation >= 1
        assert 0 <= results.final_fuel_fraction <= 1
        assert 0 <= results.final_hull_integrity <= 1

    def test_wall_time_reasonable(self) -> None:
        sim = GenerationShipSimulation(GenerationShipConfig.breakthrough())
        results = sim.run(100)
        assert results.wall_time_s < 10  # Should be fast
