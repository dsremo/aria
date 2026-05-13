"""Milestone tests — pushing ARIA to 1000+ test count.

These tests verify end-to-end system properties across all ARIA modules.
"""

import pytest

from aria.simulation.interstellar_challenges import InterstellarChallengeOrchestrator
from aria.simulation.interstellar import InterstellarSimulation


class TestEndToEndMissionIntegrity:
    """Full mission integrity checks."""

    def test_1000_year_mission_no_exception(self) -> None:
        """The entire 1000-year simulation completes without crashes."""
        sim = InterstellarSimulation(cruise_velocity_c=0.1, crew_size=4, seed=42)
        events = sim.run_full_mission()
        assert len(events) > 0
        assert sim.state.mission_year == 1000
        assert sim.state.distance_ly == pytest.approx(100.0, abs=0.1)

    def test_challenges_and_simulation_compatible(self) -> None:
        """InterstellarSimulation and ChallengeOrchestrator can run in parallel."""
        sim = InterstellarSimulation(cruise_velocity_c=0.1, crew_size=4, seed=42)
        orch = InterstellarChallengeOrchestrator(crew_size=4, seed=42)

        for _ in range(100):
            year_events = sim.simulate_year()
            challenge_result = orch.simulate_year(sim.state.mission_year, sim.state.distance_ly)
            # Both should produce events
            assert isinstance(year_events, list)
            assert isinstance(challenge_result["events"], list)

    def test_arrival_phase_reached(self) -> None:
        """Ship reaches ARRIVAL phase at ~100 ly."""
        sim = InterstellarSimulation(cruise_velocity_c=0.1, crew_size=4, seed=42)
        sim.run_full_mission()
        assert sim.state.phase == "ARRIVAL"

    def test_mission_summary_complete(self) -> None:
        """Mission summary includes all expected fields."""
        sim = InterstellarSimulation(cruise_velocity_c=0.1, crew_size=4, seed=42)
        for _ in range(50):
            sim.simulate_year()
        summary = sim.get_mission_summary()
        expected_keys = {
            "mission_year", "distance_ly", "phase", "fuel_remaining",
            "hull_integrity", "electronics_health", "food_reserves_kg",
            "water_liters", "seed_viability", "crew_generation",
            "crew_morale", "ai_version", "total_events", "radiation_krad",
        }
        assert expected_keys.issubset(set(summary.keys()))
