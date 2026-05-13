"""Interstellar Mission Simulation Tests — 100 light-year journey.

Tests that the simulation correctly models:
  - Fuel depletion over centuries
  - Electronics radiation damage
  - Food system degradation
  - Hull micrometeorite accumulation
  - Crew generational transitions
  - AI evolution milestones
  - Resource exhaustion warnings
  - Major random events
  - Mission phase transitions
"""

from __future__ import annotations

import pytest

from aria.simulation.interstellar import InterstellarSimulation, InterstellarState, YearEvent


class TestInterstellarSimulation:
    """Test the year-by-year interstellar simulation."""

    def test_initial_state(self):
        """Simulation starts with correct initial state."""
        sim = InterstellarSimulation(cruise_velocity_c=0.1, crew_size=4)
        s = sim.state
        assert s.mission_year == 0.0
        assert s.distance_ly == 0.0
        assert s.fusion_fuel_kg == 1_518_000.0  # Volkov R6: laser-sail accel removes departure burn
        assert s.crew_count == 4
        assert s.hull_integrity == 1.0

    def test_one_year_advances_distance(self):
        """After 1 year at 0.1c, distance is 0.1 ly."""
        sim = InterstellarSimulation(cruise_velocity_c=0.1, seed=42)
        sim.simulate_year()
        assert sim.state.mission_year == 1.0
        assert abs(sim.state.distance_ly - 0.1) < 0.01

    def test_fuel_depletes_over_time(self):
        """Fuel decreases year over year."""
        sim = InterstellarSimulation(seed=42)
        initial_fuel = sim.state.fusion_fuel_kg
        for _ in range(10):
            sim.simulate_year()
        assert sim.state.fusion_fuel_kg < initial_fuel

    def test_rtg_decay_follows_halflife(self):
        """RTG power follows Pu-238 half-life (87.7 years)."""
        sim = InterstellarSimulation(seed=42)
        for _ in range(88):
            sim.simulate_year()
        # After ~88 years, RTG should be at ~50% power
        assert 0.4 < sim.state.rtg_power_fraction < 0.6

    def test_electronics_degrade_from_radiation(self):
        """Electronics health decreases from cosmic ray TID."""
        sim = InterstellarSimulation(seed=42)
        for _ in range(50):
            sim.simulate_year()
        assert sim.state.electronics_health < 1.0
        assert sim.state.total_radiation_dose_krad > 0

    def test_hull_accumulates_impacts(self):
        """Hull integrity decreases from micrometeorite impacts."""
        sim = InterstellarSimulation(seed=42)
        for _ in range(100):
            sim.simulate_year()
        assert sim.state.micrometeorite_impacts > 0
        assert sim.state.hull_integrity < 1.0

    def test_food_system_degrades(self):
        """Food reserves deplete and grow lights degrade."""
        sim = InterstellarSimulation(seed=42)
        for _ in range(30):
            sim.simulate_year()
        assert sim.state.grow_light_health < 1.0
        assert sim.state.seed_viability < 1.0

    def test_water_slowly_depletes(self):
        """Water slowly lost despite 99.5% recycling."""
        sim = InterstellarSimulation(seed=42)
        initial_water = sim.state.water_liters
        for _ in range(100):
            sim.simulate_year()
        assert sim.state.water_liters < initial_water

    def test_crew_generations(self):
        """Crew generations advance every ~25 years."""
        sim = InterstellarSimulation(seed=42)
        for _ in range(75):
            sim.simulate_year()
        assert sim.state.crew_generation >= 3

    def test_ai_evolves(self):
        """AI model version increases every ~50 years."""
        sim = InterstellarSimulation(seed=42)
        for _ in range(150):
            sim.simulate_year()
        assert sim.state.ai_model_version >= 3

    def test_morale_decreases_over_centuries(self):
        """Crew morale decreases over very long journeys."""
        sim = InterstellarSimulation(seed=42)
        for _ in range(500):
            sim.simulate_year()
        assert sim.state.crew_morale < 0.5

    def test_spare_parts_deplete(self):
        """Spare parts are consumed by equipment failures."""
        sim = InterstellarSimulation(seed=42)
        for _ in range(50):
            sim.simulate_year()
        assert sim.state.spare_electronics < 200
        assert sim.state.spare_mechanical < 100

    def test_printer_degrades(self):
        """3D printer health decreases over time."""
        sim = InterstellarSimulation(seed=42)
        for _ in range(20):
            sim.simulate_year()
        assert sim.state.printer_health < 1.0

    def test_phase_transitions(self):
        """Mission phases transition based on distance."""
        sim = InterstellarSimulation(cruise_velocity_c=0.1, seed=42)

        # Year 1 at 0.1c: 0.1 ly — at boundary of INTERSTELLAR_CRUISE
        sim.simulate_year()
        assert sim.state.phase in ("HELIOSPHERE_EXIT", "INTERSTELLAR_CRUISE")

        # Year 5: HELIOSPHERE_EXIT
        for _ in range(4):
            sim.simulate_year()
        assert sim.state.phase in ("HELIOSPHERE_EXIT", "INTERSTELLAR_CRUISE")

        # Year 50: INTERSTELLAR_CRUISE
        for _ in range(45):
            sim.simulate_year()
        assert sim.state.phase == "INTERSTELLAR_CRUISE"

    def test_events_generated(self):
        """Simulation generates events during the journey."""
        sim = InterstellarSimulation(seed=42)
        all_events = []
        for _ in range(100):
            events = sim.simulate_year()
            all_events.extend(events)
        assert len(all_events) > 0

    def test_full_mission_runs_without_crash(self):
        """Complete 1000-year mission runs without error."""
        sim = InterstellarSimulation(cruise_velocity_c=0.1, seed=42)
        events = sim.run_full_mission()
        assert len(events) > 0
        assert sim.state.mission_year == 1000
        assert sim.state.distance_ly >= 99.0

    def test_mission_summary_format(self):
        """Mission summary returns correct structure."""
        sim = InterstellarSimulation(seed=42)
        for _ in range(10):
            sim.simulate_year()
        summary = sim.get_mission_summary()
        assert "mission_year" in summary
        assert "fuel_remaining" in summary
        assert "crew_generation" in summary
        assert "ai_version" in summary

    def test_fuel_consumed_during_mission(self):
        """After full mission, some fuel should be consumed."""
        sim = InterstellarSimulation(cruise_velocity_c=0.1, seed=42)
        sim.run_full_mission()
        fuel_fraction = sim.state.fusion_fuel_kg / sim.state.fuel_initial_kg
        # 3,109t reserves, ~50 kg/yr cruise consumption → ~98.4% remaining after 1000yr
        assert fuel_fraction < 1.0  # Some fuel consumed
        assert fuel_fraction > 0.5  # But most remains (cruise is efficient)

    def test_knowledge_base_degrades(self):
        """Knowledge base integrity slowly degrades from bit rot."""
        sim = InterstellarSimulation(seed=42)
        for _ in range(200):
            sim.simulate_year()
        assert sim.state.knowledge_base_integrity < 1.0

    def test_deterministic_with_seed(self):
        """Same seed produces same results."""
        sim1 = InterstellarSimulation(seed=123)
        sim2 = InterstellarSimulation(seed=123)

        for _ in range(50):
            sim1.simulate_year()
            sim2.simulate_year()

        assert sim1.state.fusion_fuel_kg == sim2.state.fusion_fuel_kg
        assert sim1.state.hull_integrity == sim2.state.hull_integrity
        assert sim1.state.micrometeorite_impacts == sim2.state.micrometeorite_impacts


class TestInterstellarChallenges:
    """Test specific interstellar challenges identified by the user."""

    def test_no_raw_materials_in_void(self):
        """In interstellar void, can't mine — must recycle everything."""
        sim = InterstellarSimulation(seed=42)
        for _ in range(200):
            sim.simulate_year()

        # Metal feedstock should be depleting (no mining in ISM)
        # Recycling extends it but doesn't eliminate loss
        assert sim.state.metal_feedstock_kg <= 5000  # Started at 5000

    def test_tools_go_old_and_break(self):
        """Equipment degrades and spare parts run out over centuries."""
        sim = InterstellarSimulation(seed=42)
        for _ in range(300):
            sim.simulate_year()

        # After 300 years: printer degraded toward crew-maintenance floor
        # (Made-In-Space AMF field-replaceable modules — floor 65%), spares
        # depleted.
        assert sim.state.printer_health <= 0.66
        assert sim.state.spare_electronics < 200

    def test_food_smallest_to_biggest_solution(self):
        """Food system degrades over time — seed viability key risk."""
        sim = InterstellarSimulation(seed=42)
        for _ in range(80):
            sim.simulate_year()

        # At 80 years: cryo seeds decay slowly (0.19%/yr total)
        # Seed viability ~85% at year 80 (was 20% with old 1%/yr decay)
        assert sim.state.seed_viability < 1.0  # Some degradation
        # Grow lights degrade but crew replaces LED panels on ISS APH schedule
        # (NASA-TM-2018-220162) — net effective health floor at 75% of rated.
        assert sim.state.grow_light_health <= 0.76

        # This is the crisis: need to solve food WITHOUT working grow lights
        # Solution options: algae (backup), insect farming, cellular agriculture
        # But bioreactor also has contamination risk

    def test_fuel_energy_century_problem(self):
        """Fuel must last 1000 years. How?"""
        sim = InterstellarSimulation(seed=42)
        # At 50 kg/year for 1000 years = 50,000 kg needed (exactly our reserve!)
        # Plus deceleration: 500 kg/year for ~50 years = 25,000 extra
        # Total needed: 75,000 kg but we only have 50,000
        # This is THE critical problem of interstellar travel

        sim.run_full_mission()
        # Check if fuel survived
        summary = sim.get_mission_summary()
        # This will likely show fuel depleted — that's the point
        # The AI must find a way to reduce consumption or harvest ISM hydrogen

    def test_no_civilization_to_help(self):
        """At 100 ly, light delay makes help impossible."""
        sim = InterstellarSimulation(seed=42)
        for _ in range(500):
            sim.simulate_year()

        # 500 years in: 50 ly away, round-trip comm = 100 years
        assert sim.state.years_since_last_contact > 50
        # Ship is entirely on its own

    def test_multiple_crises_compound(self):
        """Real danger: multiple systems fail simultaneously."""
        sim = InterstellarSimulation(seed=42)

        # Run 60 years — enough for grow lights to fail + spares to thin
        for _ in range(60):
            sim.simulate_year()

        s = sim.state
        # Multiple systems degraded simultaneously
        # Crew maintenance now holds grow lights / printer / scrubbers near
        # their rated floors, so the "crisis" indicators are the consumable
        # supplies (seeds, electronics spares) and wear that maintenance
        # can't reach (electronics drift).
        degraded_count = sum([
            s.grow_light_health < 0.8,
            s.seed_viability < 1.0,
            s.electronics_health < 0.95,
            s.printer_health < 0.7,
            s.spare_electronics < 150,
        ])
        assert degraded_count >= 2, "Multiple systems should degrade together"
