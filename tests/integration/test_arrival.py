"""Tests for arrival and colonization."""
import pytest
from aria.simulation.arrival_colonization import ArrivalSimulator, CompleteInterstellarMission


class TestArrivalSimulator:
    def test_survey_year_1(self):
        sim = ArrivalSimulator(seed=42)
        events = sim.simulate_year(60.0)
        assert sim.state.phase == "SURVEY"
        assert len(sim.state.planets_discovered) > 0

    def test_orbit_established_year_3(self):
        sim = ArrivalSimulator(seed=42)
        for yr in range(1, 4):
            sim.simulate_year(float(59 + yr))
        assert sim.state.orbit_established

    def test_habitat_deployed_year_4(self):
        sim = ArrivalSimulator(seed=42)
        for yr in range(1, 5):
            sim.simulate_year(float(59 + yr))
        assert sim.state.habitat_deployed
        assert sim.state.solar_panels_deployed
        assert sim.state.colony_power_kw > 0

    def test_colony_decision_year_15(self):
        sim = ArrivalSimulator(seed=42)
        for yr in range(1, 16):
            sim.simulate_year(float(59 + yr))
        assert sim.state.colony_decision_made
        assert sim.state.colony_type in ("surface", "orbital")

    def test_colony_grows(self):
        sim = ArrivalSimulator(crew_size=4, seed=42)
        for yr in range(1, 25):
            sim.simulate_year(float(59 + yr))
        assert sim.state.colony_population > 4

    def test_signal_sent_to_sol(self):
        sim = ArrivalSimulator(star_distance_ly=4.24, seed=42)
        sim.simulate_year(60.0)
        assert sim.state.signal_sent_to_sol

    def test_resource_mining(self):
        sim = ArrivalSimulator(seed=42)
        for yr in range(1, 11):
            sim.simulate_year(float(59 + yr))
        assert sim.state.water_ice_found_tonnes > 0
        assert sim.state.minerals_found.get("iron", 0) > 0


class TestCompleteInterstellarMission:
    def test_proxima_mission(self):
        mission = CompleteInterstellarMission(target_distance_ly=4.24, seed=42)
        result = mission.run(colonization_years=20)
        assert result["travel_survived"]
        assert result["colony_type"] in ("surface", "orbital")
        assert result["colony_population"] > 0
        assert result["signal_sent"]
        assert result["total_events"] > 100

    def test_barnards_star_mission(self):
        mission = CompleteInterstellarMission(target_distance_ly=5.96, seed=42)
        result = mission.run(colonization_years=15)
        assert result["travel_survived"]

    def test_total_years_calculated(self):
        mission = CompleteInterstellarMission(target_distance_ly=4.24, seed=42)
        result = mission.run(colonization_years=30)
        assert result["total_years"] == 59 + 30  # travel + colonization
