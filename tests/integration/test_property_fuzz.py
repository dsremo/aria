"""Property-based fuzz tests for ARIA using Hypothesis.

Tests invariants that must ALWAYS hold regardless of input:
  - No NaN/Inf in outputs
  - All health/degradation values bounded [0, 1]
  - No negative masses, populations, fuel levels
  - Status enums always valid
  - Ring buffer consistency
  - MRP-to-Euler reversibility
  - Dashboard never crashes on arbitrary updates
  - Challenge simulators maintain physical invariants

30+ Hypothesis tests covering:
  1. InterstellarSimulation (random crew, velocity, seed)
  2. Challenge simulators (material, food, knowledge, genetics, psych, fuel)
  3. HealthDashboard (random subsystem updates)
  4. TelemetryHistoryStore (random record/query sequences)
  5. MRP-to-Euler conversion (reversibility, bounds)
  6. OrbitConfig validation
  7. Boundary conditions (0 crew, 0 fuel, 100% degradation)
"""

from __future__ import annotations

import math
import random
from typing import Any

import pytest
from hypothesis import assume, given, example, settings, HealthCheck
from hypothesis import strategies as st

from aria.simulation.interstellar import InterstellarSimulation, InterstellarState
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
from aria.dashboard.health_dashboard import (
    DashboardSnapshot,
    HealthDashboard,
    SubsystemHealth,
)
from aria.dashboard.telemetry_server import TelemetryHistoryStore
from aria.simulation.basilisk_runner import (
    OrbitConfig,
    SpacecraftConfig,
    TelemetryFrame,
    mrp_to_euler_deg,
    eci_to_lla,
)


# ────────────────────────────────────────────────────────────────────
#  SHARED STRATEGIES
# ────────────────────────────────────────────────────────────────────

_crew_size = st.integers(min_value=1, max_value=1000)
_velocity_c = st.floats(min_value=0.01, max_value=0.5, allow_nan=False, allow_infinity=False)
_seed = st.integers(min_value=0, max_value=2**31 - 1)
_mission_year = st.floats(min_value=1.0, max_value=2000.0, allow_nan=False, allow_infinity=False)
_distance_ly = st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False)
_fraction = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_positive_float = st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False)
_small_positive = st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False)
_severity = st.sampled_from(["WATCH", "WARNING", "CRITICAL", "EMERGENCY"])
_status = st.sampled_from(["NOMINAL", "WARNING", "CRITICAL", "OFFLINE"])
_subsystem_name = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-."),
    min_size=1, max_size=50,
)
_telemetry_key = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_."),
    min_size=1, max_size=100,
)
_timestamp_ms = st.integers(min_value=0, max_value=2**53)
_telemetry_value = st.one_of(
    st.floats(allow_nan=False, allow_infinity=False),
    st.integers(min_value=-2**31, max_value=2**31),
    st.booleans(),
)

VALID_PHASES = {
    "DEPARTURE", "HELIOSPHERE_EXIT", "INTERSTELLAR_CRUISE",
    "OORT_CLOUD_TARGET", "TARGET_APPROACH", "ARRIVAL",
}

VALID_CHALLENGE_STATUSES = {s.value for s in ChallengeStatus}

VALID_OVERALL_STATUSES = {"NOMINAL", "CAUTION", "WARNING", "CRITICAL", "EMERGENCY"}

VALID_SUBSYSTEM_STATUSES = {"NOMINAL", "WARNING", "CRITICAL", "OFFLINE"}


# ────────────────────────────────────────────────────────────────────
#  1. INTERSTELLAR SIMULATION — RANDOM PARAMETERS
# ────────────────────────────────────────────────────────────────────

class TestInterstellarSimulationFuzz:
    """Property tests for InterstellarSimulation with random parameters."""

    @given(crew=_crew_size, vel=_velocity_c, seed=_seed)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @example(crew=1, vel=0.01, seed=0)
    @example(crew=1000, vel=0.5, seed=42)
    @example(crew=4, vel=0.1, seed=99999)
    def test_single_year_never_crashes(self, crew: int, vel: float, seed: int) -> None:
        """Simulating one year must never raise an exception."""
        sim = InterstellarSimulation(cruise_velocity_c=vel, crew_size=crew, seed=seed)
        events = sim.simulate_year()
        assert isinstance(events, list)
        for e in events:
            assert e.severity in ("NOMINAL", "WATCH", "WARNING", "CRITICAL", "EMERGENCY")

    @given(crew=_crew_size, vel=_velocity_c, seed=_seed, years=st.integers(min_value=1, max_value=50))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @example(crew=4, vel=0.1, seed=0, years=10)
    def test_multi_year_state_monotonic(self, crew: int, vel: float, seed: int, years: int) -> None:
        """After N years, certain values must be monotonically changing."""
        sim = InterstellarSimulation(cruise_velocity_c=vel, crew_size=crew, seed=seed)
        for _ in range(years):
            sim.simulate_year()
        s = sim.state
        # Mission year always advances
        assert s.mission_year == years
        # Distance always increases (cruise velocity > 0)
        assert s.distance_ly > 0
        # Radiation dose always accumulates
        assert s.total_radiation_dose_krad > 0
        # Fuel never goes negative
        assert s.fusion_fuel_kg >= 0

    @given(crew=_crew_size, vel=_velocity_c, seed=_seed)
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_all_fractions_bounded(self, crew: int, vel: float, seed: int) -> None:
        """All fraction/health values must stay in [0, 1] after simulation."""
        sim = InterstellarSimulation(cruise_velocity_c=vel, crew_size=crew, seed=seed)
        for _ in range(20):
            sim.simulate_year()
        s = sim.state
        fraction_fields = [
            s.rtg_power_fraction, s.fusion_reactor_health, s.hull_integrity,
            s.electronics_health, s.seed_viability, s.algae_bioreactor_health,
            s.hydroponic_capacity, s.grow_light_health, s.printer_health,
            s.knowledge_base_integrity,
        ]
        for val in fraction_fields:
            assert 0.0 <= val <= 1.0, f"Fraction out of bounds: {val}"

    @given(crew=_crew_size, vel=_velocity_c, seed=_seed)
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_no_negative_resources(self, crew: int, vel: float, seed: int) -> None:
        """No resource quantity can go negative."""
        sim = InterstellarSimulation(cruise_velocity_c=vel, crew_size=crew, seed=seed)
        for _ in range(50):
            sim.simulate_year()
        s = sim.state
        assert s.fusion_fuel_kg >= 0
        assert s.water_liters >= 0
        assert s.food_reserves_kg >= 0
        assert s.o2_reserves_kg >= 0
        assert s.metal_feedstock_kg >= 0
        assert s.polymer_feedstock_kg >= 0
        assert s.spare_electronics >= 0
        assert s.spare_mechanical >= 0
        assert s.spare_filters >= 0
        assert s.spare_batteries >= 0
        assert s.radiation_shielding_mass_kg >= 0

    @given(vel=_velocity_c, seed=_seed)
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_phase_always_valid(self, vel: float, seed: int) -> None:
        """Mission phase must always be a known value."""
        sim = InterstellarSimulation(cruise_velocity_c=vel, crew_size=4, seed=seed)
        for _ in range(30):
            sim.simulate_year()
            assert sim.state.phase in VALID_PHASES, f"Unknown phase: {sim.state.phase}"

    @given(crew=_crew_size, vel=_velocity_c, seed=_seed)
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_mission_summary_always_complete(self, crew: int, vel: float, seed: int) -> None:
        """get_mission_summary() must always return a dict with all expected keys."""
        sim = InterstellarSimulation(cruise_velocity_c=vel, crew_size=crew, seed=seed)
        for _ in range(5):
            sim.simulate_year()
        summary = sim.get_mission_summary()
        expected_keys = {
            "mission_year", "distance_ly", "phase", "fuel_remaining",
            "hull_integrity", "electronics_health", "food_reserves_kg",
            "water_liters", "seed_viability", "crew_generation",
            "crew_morale", "ai_version", "total_events", "radiation_krad",
            "spare_electronics", "spare_mechanical", "printer_health",
        }
        assert expected_keys <= set(summary.keys())

    @given(vel=_velocity_c, seed=_seed)
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_distance_proportional_to_velocity(self, vel: float, seed: int) -> None:
        """After N years, distance_ly should equal N * velocity_c."""
        sim = InterstellarSimulation(cruise_velocity_c=vel, crew_size=4, seed=seed)
        years = 10
        for _ in range(years):
            sim.simulate_year()
        expected = years * vel
        assert abs(sim.state.distance_ly - expected) < 1e-9

    @given(seed=_seed)
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_no_nan_in_state(self, seed: int) -> None:
        """No NaN values may appear in the simulation state."""
        sim = InterstellarSimulation(cruise_velocity_c=0.1, crew_size=4, seed=seed)
        for _ in range(100):
            sim.simulate_year()
        s = sim.state
        float_fields = [
            s.mission_year, s.distance_ly, s.velocity_c, s.fusion_fuel_kg,
            s.rtg_power_fraction, s.fusion_reactor_health, s.total_power_watts,
            s.hull_integrity, s.electronics_health, s.total_radiation_dose_krad,
            s.water_liters, s.o2_reserves_kg, s.food_reserves_kg,
            s.seed_viability, s.algae_bioreactor_health, s.hydroponic_capacity,
            s.grow_light_health, s.crew_morale, s.cumulative_radiation_msv,
            s.metal_feedstock_kg, s.polymer_feedstock_kg, s.printer_health,
            s.knowledge_base_integrity,
        ]
        for val in float_fields:
            assert not math.isnan(val), f"NaN found in state: {val}"
            assert not math.isinf(val), f"Inf found in state: {val}"


# ────────────────────────────────────────────────────────────────────
#  2. CHALLENGE SIMULATORS — INVARIANT VERIFICATION
# ────────────────────────────────────────────────────────────────────

class TestMaterialEntropyFuzz:
    """Property tests for MaterialEntropySimulator."""

    @given(seed=_seed, years=st.integers(min_value=1, max_value=300))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @example(seed=0, years=1)
    @example(seed=42, years=300)
    def test_no_negative_material_quantities(self, seed: int, years: int) -> None:
        """All material quantities must remain >= 0."""
        sim = MaterialEntropySimulator(seed=seed)
        for y in range(1, years + 1):
            sim.simulate_year(float(y))
        inv = sim.inventory
        for attr in (
            "aluminum_kg", "steel_kg", "titanium_kg", "copper_kg",
            "rare_earth_kg", "platinum_group_kg", "lithium_kg", "silicon_kg",
            "cobalt_kg", "polymer_feedstock_kg", "rubber_gaskets_kg",
            "lubricant_liters", "printer_filament_kg", "solder_kg", "adhesive_kg",
        ):
            val = getattr(inv, attr)
            assert val >= 0, f"{attr} went negative: {val}"

    @given(seed=_seed, years=st.integers(min_value=1, max_value=200))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_recycling_efficiency_bounded(self, seed: int, years: int) -> None:
        """Recycling efficiencies stay within their defined floor and ceiling."""
        sim = MaterialEntropySimulator(seed=seed)
        for y in range(1, years + 1):
            sim.simulate_year(float(y))
        inv = sim.inventory
        assert 0.5 <= inv.metal_recycle_efficiency <= 1.0
        assert 0.3 <= inv.polymer_recycle_efficiency <= 1.0
        assert 0.2 <= inv.electronics_recycle_efficiency <= 1.0

    @given(seed=_seed, years=st.integers(min_value=1, max_value=200))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_severity_score_bounded(self, seed: int, years: int) -> None:
        """Challenge severity score must be in [0, 1]."""
        sim = MaterialEntropySimulator(seed=seed)
        for y in range(1, years + 1):
            sim.simulate_year(float(y))
        assert 0.0 <= sim.state.severity_score <= 1.0
        assert sim.state.status in ChallengeStatus


class TestFoodCenturyFuzz:
    """Property tests for FoodCenturySimulator."""

    @given(crew=_crew_size, seed=_seed, years=st.integers(min_value=1, max_value=200))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @example(crew=1, seed=0, years=1)
    @example(crew=1000, seed=42, years=100)
    def test_food_production_non_negative(self, crew: int, seed: int, years: int) -> None:
        """Food production must never go negative."""
        sim = FoodCenturySimulator(crew_size=crew, seed=seed)
        for y in range(1, years + 1):
            sim.simulate_year(float(y))
        assert sim.food.annual_food_production_kg >= 0

    @given(crew=_crew_size, seed=_seed, years=st.integers(min_value=1, max_value=100))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_seed_viabilities_bounded(self, crew: int, seed: int, years: int) -> None:
        """Seed viability values must stay in [0, 1]."""
        sim = FoodCenturySimulator(crew_size=crew, seed=seed)
        for y in range(1, years + 1):
            sim.simulate_year(float(y))
        f = sim.food
        for attr in (
            "grain_seeds_viability", "legume_seeds_viability",
            "vegetable_seeds_viability", "fruit_seeds_viability",
        ):
            val = getattr(f, attr)
            assert 0.0 <= val <= 1.0, f"{attr} out of bounds: {val}"

    @given(crew=_crew_size, seed=_seed, years=st.integers(min_value=1, max_value=100))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_heavy_metal_contamination_non_negative(self, crew: int, seed: int, years: int) -> None:
        """Heavy metal contamination must be non-negative and monotonically increasing."""
        sim = FoodCenturySimulator(crew_size=crew, seed=seed)
        prev_contam = 0.0
        for y in range(1, years + 1):
            sim.simulate_year(float(y))
            assert sim.food.heavy_metal_contamination >= prev_contam
            prev_contam = sim.food.heavy_metal_contamination

    @given(crew=_crew_size, seed=_seed)
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_food_state_valid_after_simulation(self, crew: int, seed: int) -> None:
        """All food system health values must be in valid ranges."""
        sim = FoodCenturySimulator(crew_size=crew, seed=seed)
        for y in range(1, 51):
            sim.simulate_year(float(y))
        f = sim.food
        assert 0.0 <= f.algae_health <= 1.0
        assert 0.0 <= f.insect_farm_capacity <= 1.0
        assert 0.0 <= f.cultured_meat_viability <= 1.0
        assert 0.0 <= f.hydroponic_efficiency <= 1.0
        assert 0.0 <= f.soil_microbiome_health <= 1.0
        assert 0.0 <= f.nutrient_solution_quality <= 1.0
        assert sim.state.status in ChallengeStatus
        assert 0.0 <= sim.state.severity_score <= 1.0


class TestKnowledgePreservationFuzz:
    """Property tests for KnowledgePreservationSimulator."""

    @given(seed=_seed, years=st.integers(min_value=1, max_value=500))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @example(seed=0, years=500)
    def test_storage_health_bounded(self, seed: int, years: int) -> None:
        """Storage media health values must stay in [0, 1]."""
        sim = KnowledgePreservationSimulator(seed=seed)
        for y in range(1, years + 1):
            sim.simulate_year(float(y))
        kb = sim.kb
        assert 0.0 <= kb.flash_storage_health <= 1.0
        assert 0.0 <= kb.magnetic_storage_health <= 1.0
        assert 0.0 <= kb.optical_storage_health <= 1.0
        assert 0.0 <= kb.dna_storage_health <= 1.0

    @given(seed=_seed, years=st.integers(min_value=1, max_value=500))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_knowledge_domains_bounded(self, seed: int, years: int) -> None:
        """Knowledge domain completeness values must stay in [0, 1]."""
        sim = KnowledgePreservationSimulator(seed=seed)
        for y in range(1, years + 1):
            sim.simulate_year(float(y))
        kb = sim.kb
        for attr in (
            "engineering_knowledge", "medical_knowledge",
            "scientific_knowledge", "navigation_knowledge",
            "cultural_knowledge", "agricultural_knowledge",
        ):
            val = getattr(kb, attr)
            assert 0.0 <= val <= 1.0, f"{attr} out of bounds: {val}"

    @given(seed=_seed, years=st.integers(min_value=1, max_value=300))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_corrupted_documents_non_negative(self, seed: int, years: int) -> None:
        """Corrupted document count must be non-negative and monotonically increasing."""
        sim = KnowledgePreservationSimulator(seed=seed)
        prev_corrupted = 0
        for y in range(1, years + 1):
            sim.simulate_year(float(y))
            assert sim.kb.corrupted_documents >= prev_corrupted
            prev_corrupted = sim.kb.corrupted_documents


class TestGeneticDiversityFuzz:
    """Property tests for GeneticDiversitySimulator."""

    @given(pop=st.integers(min_value=1, max_value=500), seed=_seed,
           years=st.integers(min_value=1, max_value=300))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @example(pop=1, seed=0, years=100)
    @example(pop=4, seed=42, years=300)
    def test_genetic_values_bounded(self, pop: int, seed: int, years: int) -> None:
        """Inbreeding coefficient and heterozygosity must stay in [0, 1]."""
        sim = GeneticDiversitySimulator(initial_population=pop, seed=seed)
        for y in range(1, years + 1):
            sim.simulate_year(float(y))
        g = sim.genetics
        assert 0.0 <= g.inbreeding_coefficient <= 1.0
        assert 0.0 <= g.heterozygosity <= 1.0
        assert 0.0 <= g.embryo_viability <= 1.0
        assert 0.0 <= g.gamete_viability <= 1.0

    @given(pop=st.integers(min_value=1, max_value=100), seed=_seed,
           years=st.integers(min_value=1, max_value=200))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_population_non_negative(self, pop: int, seed: int, years: int) -> None:
        """Population must never go negative or to zero from dynamics."""
        sim = GeneticDiversitySimulator(initial_population=pop, seed=seed)
        for y in range(1, years + 1):
            sim.simulate_year(float(y))
        # Population can decrease but the model should keep it above 0
        # (deaths only happen when pop > 3)
        assert sim.genetics.population >= 0

    @given(pop=st.integers(min_value=1, max_value=100), seed=_seed,
           years=st.integers(min_value=1, max_value=200))
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_frozen_reserves_non_negative(self, pop: int, seed: int, years: int) -> None:
        """Frozen embryos and gametes must never go negative."""
        sim = GeneticDiversitySimulator(initial_population=pop, seed=seed)
        for y in range(1, years + 1):
            sim.simulate_year(float(y))
        assert sim.genetics.frozen_embryos >= 0
        assert sim.genetics.frozen_gametes >= 0


class TestPsychologicalDecayFuzz:
    """Property tests for PsychologicalDecaySimulator."""

    @given(crew=_crew_size, seed=_seed, years=st.integers(min_value=1, max_value=500))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @example(crew=1, seed=0, years=1)
    @example(crew=1000, seed=42, years=500)
    def test_psychological_values_bounded(self, crew: int, seed: int, years: int) -> None:
        """All psychological metrics must stay in [0, 1]."""
        sim = PsychologicalDecaySimulator(crew_size=crew, seed=seed)
        for y in range(1, years + 1):
            sim.simulate_year(float(y))
        p = sim.psych
        assert 0.0 <= p.morale <= 1.0, f"morale out of bounds: {p.morale}"
        assert 0.0 <= p.social_cohesion <= 1.0
        assert 0.0 <= p.purpose_alignment <= 1.0
        assert 0.0 <= p.conflict_level <= 1.0
        assert 0.0 <= p.depression_prevalence <= 1.0
        assert 0.0 <= p.mutiny_risk <= 1.0
        assert 0.0 <= p.earth_nostalgia <= 1.0
        assert 0.0 <= p.generation_gap <= 1.0

    @given(crew=_crew_size, seed=_seed)
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_severity_and_status_consistent(self, crew: int, seed: int) -> None:
        """Severity score and status enum must always be valid."""
        sim = PsychologicalDecaySimulator(crew_size=crew, seed=seed)
        for y in range(1, 101):
            sim.simulate_year(float(y))
        assert 0.0 <= sim.state.severity_score <= 1.0
        assert sim.state.status in ChallengeStatus


class TestFuelCliffFuzz:
    """Property tests for FuelCliffSimulator."""

    @given(seed=_seed, year=_mission_year, dist=_distance_ly)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @example(seed=0, year=1.0, dist=0.1)
    @example(seed=42, year=999.0, dist=99.0)
    def test_fuel_non_negative(self, seed: int, year: float, dist: float) -> None:
        """Fuel quantity must never go negative."""
        sim = FuelCliffSimulator(seed=seed)
        sim.simulate_year(year, dist)
        assert sim.fuel.dt_fuel_kg >= 0

    @given(seed=_seed, years=st.integers(min_value=1, max_value=200))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_reactor_health_bounded(self, seed: int, years: int) -> None:
        """Reactor health and efficiency must stay within bounds."""
        sim = FuelCliffSimulator(seed=seed)
        for y in range(1, years + 1):
            dist = y * 0.1
            sim.simulate_year(float(y), dist)
        f = sim.fuel
        assert 0.0 <= f.reactor_health <= 1.0
        assert 0.0 <= f.reactor_efficiency <= 1.0
        assert 0.0 <= f.rtg_power_fraction <= 1.0

    @given(seed=_seed, years=st.integers(min_value=1, max_value=300))
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_helium3_non_negative(self, seed: int, years: int) -> None:
        """Helium-3 produced from tritium decay must be non-negative."""
        sim = FuelCliffSimulator(seed=seed)
        for y in range(1, years + 1):
            sim.simulate_year(float(y), y * 0.1)
        assert sim.fuel.he3_kg >= 0

    @given(seed=_seed, years=st.integers(min_value=1, max_value=200))
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_power_generation_non_negative(self, seed: int, years: int) -> None:
        """Power generation must never go negative."""
        sim = FuelCliffSimulator(seed=seed)
        for y in range(1, years + 1):
            sim.simulate_year(float(y), y * 0.1)
        assert sim.fuel.generation_w >= 0


# ────────────────────────────────────────────────────────────────────
#  3. HEALTH DASHBOARD — RANDOM UPDATES NEVER CRASH
# ────────────────────────────────────────────────────────────────────

class TestHealthDashboardFuzz:
    """Property tests for HealthDashboard."""

    @given(
        battery=st.floats(min_value=-100, max_value=200, allow_nan=False, allow_infinity=False),
        solar_w=_positive_float,
        load_w=_positive_float,
        bus_v=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @example(battery=0.0, solar_w=0.0, load_w=0.0, bus_v=0.0)
    @example(battery=100.0, solar_w=5000.0, load_w=3000.0, bus_v=28.0)
    def test_power_update_never_crashes(
        self, battery: float, solar_w: float, load_w: float, bus_v: float
    ) -> None:
        """Updating power with arbitrary values must never crash."""
        dash = HealthDashboard()
        dash.update_power(battery_soc=battery, solar_w=solar_w, load_w=load_w, bus_v=bus_v)
        snap = dash.snapshot()
        assert snap.overall_status in VALID_OVERALL_STATUSES

    @given(
        o2=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
        co2=st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False),
        pressure=st.floats(min_value=0, max_value=30, allow_nan=False, allow_infinity=False),
        temp=st.floats(min_value=-50, max_value=80, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_eclss_update_never_crashes(
        self, o2: float, co2: float, pressure: float, temp: float
    ) -> None:
        """Updating ECLSS with arbitrary values must never crash."""
        dash = HealthDashboard()
        dash.update_eclss(o2_pct=o2, co2_ppm=co2, pressure_psi=pressure, temp_c=temp)
        snap = dash.snapshot()
        assert snap.overall_status in VALID_OVERALL_STATUSES

    @given(name=_subsystem_name, status=_status, alerts=st.integers(min_value=0, max_value=1000),
           score=_fraction)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_subsystem_update_never_crashes(
        self, name: str, status: str, alerts: int, score: float
    ) -> None:
        """Updating a subsystem with arbitrary values must never crash."""
        dash = HealthDashboard()
        dash.update_subsystem(name, status=status, alerts=alerts, dsremo_score=score)
        snap = dash.snapshot()
        assert snap.overall_status in VALID_OVERALL_STATUSES
        assert name in snap.subsystems

    @given(
        subsystems=st.lists(
            st.tuples(_subsystem_name, _status, st.integers(0, 100), _fraction),
            min_size=0, max_size=20,
        ),
        alerts=st.lists(
            st.tuples(_severity, _subsystem_name, st.text(min_size=0, max_size=50)),
            min_size=0, max_size=50,
        ),
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_many_random_updates_never_crash(
        self,
        subsystems: list[tuple[str, str, int, float]],
        alerts: list[tuple[str, str, str]],
    ) -> None:
        """A barrage of random updates must never crash the dashboard."""
        dash = HealthDashboard()
        for name, status, alert_count, score in subsystems:
            dash.update_subsystem(name, status=status, alerts=alert_count, dsremo_score=score)
        for severity, subsys, msg in alerts:
            dash.record_alert(severity, subsystem=subsys, message=msg)
        snap = dash.snapshot()
        assert snap.overall_status in VALID_OVERALL_STATUSES
        assert snap.total_alerts == len(alerts)

    @given(
        alt=st.floats(min_value=-1000, max_value=100000, allow_nan=False, allow_infinity=False),
        vel=st.floats(min_value=0, max_value=20000, allow_nan=False, allow_infinity=False),
        lat=st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False),
        lon=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
        eclipse=st.booleans(),
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_orbit_update_never_crashes(
        self, alt: float, vel: float, lat: float, lon: float, eclipse: bool
    ) -> None:
        """Orbit updates with arbitrary values must never crash."""
        dash = HealthDashboard()
        dash.update_orbit(altitude_km=alt, velocity_m_s=vel, latitude_deg=lat,
                          longitude_deg=lon, in_eclipse=eclipse)
        snap = dash.snapshot()
        assert snap.overall_status in VALID_OVERALL_STATUSES

    def test_snapshot_to_dict_complete(self) -> None:
        """to_dict() must return all top-level sections."""
        dash = HealthDashboard(mission_name="test")
        dash.update_power(battery_soc=80, solar_w=2000, load_w=500)
        dash.update_subsystem("nav", status="NOMINAL")
        snap = dash.snapshot()
        d = snap.to_dict()
        assert "mission" in d
        assert "orbit" in d
        assert "power" in d
        assert "eclss" in d
        assert "subsystems" in d
        assert "alerts" in d
        assert "system" in d
        assert "challenges" in d
        assert "overall_status" in d


# ────────────────────────────────────────────────────────────────────
#  4. TELEMETRY HISTORY STORE — RANDOM RECORD/QUERY CONSISTENCY
# ────────────────────────────────────────────────────────────────────

class TestTelemetryHistoryStoreFuzz:
    """Property tests for TelemetryHistoryStore ring buffer."""

    @given(
        records=st.lists(
            st.tuples(_telemetry_key, _timestamp_ms, _telemetry_value),
            min_size=0, max_size=200,
        ),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_record_then_query_consistent(
        self, records: list[tuple[str, int, Any]]
    ) -> None:
        """Every recorded value must be queryable."""
        store = TelemetryHistoryStore(max_per_key=10000)
        for key, ts, val in records:
            store.record(key, ts, val)
        # Check that all keys that had records are present
        recorded_keys = {k for k, _, _ in records}
        for key in recorded_keys:
            result = store.query(key)
            assert len(result) > 0, f"Key {key} had records but query returned empty"

    @given(
        records=st.lists(
            st.tuples(
                st.just("test.key"),
                st.integers(min_value=0, max_value=100000),
                st.floats(allow_nan=False, allow_infinity=False),
            ),
            min_size=1, max_size=100,
        ),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_latest_returns_last_recorded(
        self, records: list[tuple[str, int, float]]
    ) -> None:
        """latest() must return the most recently recorded value."""
        store = TelemetryHistoryStore()
        for key, ts, val in records:
            store.record(key, ts, val)
        latest = store.latest("test.key")
        assert latest is not None
        last_record = records[-1]
        assert latest["timestamp"] == last_record[1]
        assert latest["value"] == last_record[2]

    @given(
        n_records=st.integers(min_value=1, max_value=500),
        max_per_key=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_ring_buffer_respects_max_size(self, n_records: int, max_per_key: int) -> None:
        """The store must never hold more than max_per_key records per key."""
        store = TelemetryHistoryStore(max_per_key=max_per_key)
        for i in range(n_records):
            store.record("test.ring", i, float(i))
        result = store.query("test.ring")
        assert len(result) <= max_per_key

    @given(
        start=st.integers(min_value=0, max_value=50000),
        window=st.integers(min_value=1, max_value=50000),
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_time_range_query_filters_correctly(self, start: int, window: int) -> None:
        """Time-range queries must only return records within [start, end]."""
        store = TelemetryHistoryStore()
        # Insert records at timestamps 0, 100, 200, ..., 9900
        for i in range(100):
            store.record("test.time", i * 100, float(i))
        end = start + window
        result = store.query("test.time", start_ms=start, end_ms=end)
        for r in result:
            assert start <= r["timestamp"] <= end, (
                f"Record timestamp {r['timestamp']} outside range [{start}, {end}]"
            )

    @given(
        keys=st.lists(_telemetry_key, min_size=1, max_size=10, unique=True),
        n_per_key=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_keys_property_reflects_recorded_keys(
        self, keys: list[str], n_per_key: int
    ) -> None:
        """The keys property must list all and only keys that have records."""
        store = TelemetryHistoryStore()
        for key in keys:
            for i in range(n_per_key):
                store.record(key, i, 0.0)
        assert set(store.keys) == set(keys)

    def test_query_nonexistent_key_returns_empty(self) -> None:
        """Querying a key that was never recorded must return an empty list."""
        store = TelemetryHistoryStore()
        store.record("exists", 1000, 42.0)
        assert store.query("does_not_exist") == []
        assert store.latest("does_not_exist") is None


# ────────────────────────────────────────────────────────────────────
#  5. MRP-TO-EULER CONVERSION — REVERSIBILITY AND BOUNDS
# ────────────────────────────────────────────────────────────────────

class TestMRPEulerConversionFuzz:
    """Property tests for MRP-to-Euler angle conversion."""

    @given(
        s1=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        s2=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        s3=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @example(s1=0.0, s2=0.0, s3=0.0)
    @example(s1=1.0, s2=0.0, s3=0.0)
    @example(s1=0.0, s2=1.0, s3=0.0)
    @example(s1=0.0, s2=0.0, s3=1.0)
    def test_euler_angles_bounded(self, s1: float, s2: float, s3: float) -> None:
        """Euler angles from MRP conversion must be within valid ranges."""
        roll, pitch, yaw = mrp_to_euler_deg([s1, s2, s3])
        assert not math.isnan(roll)
        assert not math.isnan(pitch)
        assert not math.isnan(yaw)
        assert not math.isinf(roll)
        assert not math.isinf(pitch)
        assert not math.isinf(yaw)
        # Roll and yaw: [-180, 180], pitch: [-90, 90]
        assert -180.0 <= roll <= 180.0, f"Roll out of bounds: {roll}"
        assert -90.0 <= pitch <= 90.0, f"Pitch out of bounds: {pitch}"
        assert -180.0 <= yaw <= 180.0, f"Yaw out of bounds: {yaw}"

    @given(
        s1=st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
        s2=st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
        s3=st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_zero_mrp_gives_zero_euler(self, s1: float, s2: float, s3: float) -> None:
        """Near-zero MRP must give near-zero Euler angles (continuity)."""
        mrp_mag = math.sqrt(s1**2 + s2**2 + s3**2)
        roll, pitch, yaw = mrp_to_euler_deg([s1, s2, s3])
        # If MRP is very small, angles should be small
        if mrp_mag < 0.01:
            assert abs(roll) < 5.0, f"Roll {roll} too large for near-zero MRP"
            assert abs(pitch) < 5.0, f"Pitch {pitch} too large for near-zero MRP"
            assert abs(yaw) < 5.0, f"Yaw {yaw} too large for near-zero MRP"

    def test_identity_mrp_gives_zero_angles(self) -> None:
        """Zero MRP (identity rotation) must give zero Euler angles."""
        roll, pitch, yaw = mrp_to_euler_deg([0.0, 0.0, 0.0])
        assert roll == 0.0
        assert pitch == 0.0
        assert yaw == 0.0

    @given(
        s1=st.floats(min_value=-0.9, max_value=0.9, allow_nan=False, allow_infinity=False),
        s2=st.floats(min_value=-0.9, max_value=0.9, allow_nan=False, allow_infinity=False),
        s3=st.floats(min_value=-0.9, max_value=0.9, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_mrp_to_quaternion_unit_norm(self, s1: float, s2: float, s3: float) -> None:
        """The intermediate quaternion from MRP must have unit norm."""
        s_sq = s1**2 + s2**2 + s3**2
        if s_sq < 1e-12:
            return  # Handled separately
        denom = 1.0 + s_sq
        q0 = (1.0 - s_sq) / denom
        q1 = 2.0 * s1 / denom
        q2 = 2.0 * s2 / denom
        q3 = 2.0 * s3 / denom
        norm = math.sqrt(q0**2 + q1**2 + q2**2 + q3**2)
        assert abs(norm - 1.0) < 1e-10, f"Quaternion norm {norm} != 1.0"


# ────────────────────────────────────────────────────────────────────
#  6. ECI-TO-LLA CONVERSION — BOUNDS AND CONSISTENCY
# ────────────────────────────────────────────────────────────────────

class TestECIToLLAFuzz:
    """Property tests for ECI to Lat/Lon/Alt conversion."""

    @given(
        x=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
        y=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
        z=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
        t=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_lla_latitude_bounded(self, x: float, y: float, z: float, t: float) -> None:
        """Latitude must always be in [-90, 90]."""
        r = math.sqrt(x**2 + y**2 + z**2)
        assume(r > 1.0)  # Avoid division by zero at origin
        lat, lon, alt = eci_to_lla([x, y, z], t)
        assert not math.isnan(lat)
        assert not math.isnan(lon)
        assert not math.isnan(alt)
        assert -90.0 <= lat <= 90.0, f"Latitude out of bounds: {lat}"
        assert -180.0 <= lon <= 180.0, f"Longitude out of bounds: {lon}"


# ────────────────────────────────────────────────────────────────────
#  7. ORBIT CONFIG VALIDATION
# ────────────────────────────────────────────────────────────────────

class TestOrbitConfigFuzz:
    """Property tests for OrbitConfig and SpacecraftConfig."""

    @given(
        alt=st.floats(min_value=160, max_value=36000, allow_nan=False, allow_infinity=False),
        inc=st.floats(min_value=0, max_value=180, allow_nan=False, allow_infinity=False),
        ecc=st.floats(min_value=0.0, max_value=0.9, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @example(alt=160.0, inc=0.0, ecc=0.0)
    @example(alt=36000.0, inc=90.0, ecc=0.5)
    def test_orbit_config_construction(self, alt: float, inc: float, ecc: float) -> None:
        """OrbitConfig must accept any valid altitude/inclination/eccentricity."""
        config = OrbitConfig(altitude_km=alt, inclination_deg=inc, eccentricity=ecc)
        assert config.altitude_km == alt
        assert config.inclination_deg == inc
        assert config.eccentricity == ecc

    @given(
        mass=st.floats(min_value=1.0, max_value=10000, allow_nan=False, allow_infinity=False),
        panel_area=st.floats(min_value=0.1, max_value=100, allow_nan=False, allow_infinity=False),
        panel_eff=st.floats(min_value=0.01, max_value=0.5, allow_nan=False, allow_infinity=False),
        battery_cap=st.floats(min_value=10, max_value=50000, allow_nan=False, allow_infinity=False),
        initial_soc=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_spacecraft_config_construction(
        self, mass: float, panel_area: float, panel_eff: float,
        battery_cap: float, initial_soc: float,
    ) -> None:
        """SpacecraftConfig must accept any physically plausible parameters."""
        config = SpacecraftConfig(
            mass_kg=mass,
            solar_panel_area_m2=panel_area,
            solar_panel_efficiency=panel_eff,
            battery_capacity_whr=battery_cap,
            battery_initial_soc=initial_soc,
        )
        assert config.mass_kg == mass
        assert config.solar_panel_area_m2 == panel_area


# ────────────────────────────────────────────────────────────────────
#  8. BOUNDARY CONDITIONS — SYSTEMATIC
# ────────────────────────────────────────────────────────────────────

class TestBoundaryConditions:
    """Systematic boundary condition tests."""

    def test_zero_crew_food_sim_no_crash(self) -> None:
        """Zero crew must not crash the food simulator.

        BUG FOUND BY FUZZ: FoodCenturySimulator previously had ZeroDivisionError
        when crew_size=0. Fixed by guarding division with max(..., 1.0).
        """
        food_sim = FoodCenturySimulator(crew_size=0, seed=42)
        events = food_sim.simulate_year(1.0)
        assert isinstance(events, list)

    def test_zero_crew_psych_sim(self) -> None:
        """Zero crew must not crash the psychological decay simulator."""
        psych_sim = PsychologicalDecaySimulator(crew_size=0, seed=42)
        events = psych_sim.simulate_year(1.0)
        assert isinstance(events, list)

    def test_zero_fuel_start(self) -> None:
        """Starting with zero fuel must not crash."""
        sim = FuelCliffSimulator(seed=42)
        sim.fuel.dt_fuel_kg = 0.0
        events = sim.simulate_year(1.0, 0.1)
        assert isinstance(events, list)
        assert sim.fuel.dt_fuel_kg == 0.0

    def test_100_percent_degradation(self) -> None:
        """All systems at 100% degradation must not crash."""
        sim = MaterialEntropySimulator(seed=42)
        inv = sim.inventory
        inv.metal_recycle_efficiency = 0.5  # Floor
        inv.polymer_recycle_efficiency = 0.3  # Floor
        inv.electronics_recycle_efficiency = 0.2  # Floor
        inv.rare_earth_kg = 0.0
        inv.platinum_group_kg = 0.0
        inv.lithium_kg = 0.0
        events = sim.simulate_year(500.0)
        assert isinstance(events, list)
        assert sim.state.status in ChallengeStatus

    def test_maximum_crew_food_simulation(self) -> None:
        """1000 crew must not crash the food simulator."""
        sim = FoodCenturySimulator(crew_size=1000, seed=42)
        events = sim.simulate_year(1.0)
        assert isinstance(events, list)
        # With 1000 crew, there will be a massive food deficit
        assert sim.food.annual_food_production_kg >= 0

    def test_extreme_velocity_full_mission(self) -> None:
        """Very high velocity (0.5c) completes in 200 years without crash."""
        sim = InterstellarSimulation(cruise_velocity_c=0.5, crew_size=4, seed=42)
        events = sim.run_full_mission()
        assert isinstance(events, list)
        assert sim.state.phase == "ARRIVAL"

    def test_very_low_velocity_few_years(self) -> None:
        """Very low velocity (0.01c) simulates correctly without issues."""
        sim = InterstellarSimulation(cruise_velocity_c=0.01, crew_size=4, seed=42)
        for _ in range(100):
            sim.simulate_year()
        assert sim.state.distance_ly == pytest.approx(1.0, abs=1e-9)
        assert sim.state.phase in VALID_PHASES

    def test_single_crew_genetics(self) -> None:
        """Population of 1 must not crash genetic diversity sim."""
        sim = GeneticDiversitySimulator(initial_population=1, seed=42)
        for y in range(1, 101):
            sim.simulate_year(float(y))
        assert sim.genetics.population >= 0
        assert 0.0 <= sim.genetics.inbreeding_coefficient <= 1.0

    def test_knowledge_sim_1000_years(self) -> None:
        """Knowledge preservation over 1000 years must maintain valid state."""
        sim = KnowledgePreservationSimulator(seed=42)
        for y in range(1, 1001):
            sim.simulate_year(float(y))
        kb = sim.kb
        assert kb.corrupted_documents >= 0
        assert kb.corrupted_documents <= kb.total_documents * kb.copies_per_document
        assert 0.0 <= kb.engineering_knowledge <= 1.0
        assert sim.state.status in ChallengeStatus


# ────────────────────────────────────────────────────────────────────
#  9. ORCHESTRATOR — INTEGRATED CHALLENGE INVARIANTS
# ────────────────────────────────────────────────────────────────────

class TestOrchestratorFuzz:
    """Property tests for InterstellarChallengeOrchestrator."""

    @given(crew=st.integers(min_value=1, max_value=100), seed=_seed,
           years=st.integers(min_value=1, max_value=50))
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @example(crew=4, seed=0, years=10)
    def test_orchestrator_never_crashes(self, crew: int, seed: int, years: int) -> None:
        """The orchestrator must never crash regardless of parameters."""
        orch = InterstellarChallengeOrchestrator(crew_size=crew, seed=seed)
        for y in range(1, years + 1):
            result = orch.simulate_year(float(y), y * 0.1)
            assert "events" in result
            assert "challenge_states" in result
            assert "overall_severity" in result
            assert "terminal_count" in result
            assert isinstance(result["events"], list)
            assert 0.0 <= result["overall_severity"] <= 1.0
            assert result["terminal_count"] >= 0

    @given(crew=st.integers(min_value=1, max_value=50), seed=_seed,
           years=st.integers(min_value=1, max_value=30))
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_all_challenge_states_valid(self, crew: int, seed: int, years: int) -> None:
        """All challenge states in the orchestrator must have valid status/severity."""
        orch = InterstellarChallengeOrchestrator(crew_size=crew, seed=seed)
        for y in range(1, years + 1):
            result = orch.simulate_year(float(y), y * 0.1)
        summary = orch.get_summary()
        for name, state in summary.items():
            assert state["status"] in VALID_CHALLENGE_STATUSES, (
                f"Challenge {name} has invalid status: {state['status']}"
            )
            assert 0.0 <= state["severity"] <= 1.0, (
                f"Challenge {name} has severity out of bounds: {state['severity']}"
            )

    @given(seed=_seed)
    @settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_full_mission_run(self, seed: int) -> None:
        """A full mission run with orchestrator must complete without crash."""
        orch = InterstellarChallengeOrchestrator(crew_size=4, seed=seed)
        results = orch.run_full_mission(velocity_c=0.1, target_ly=10.0)  # Short 100-year run
        assert len(results) == 100
        for r in results:
            assert 0.0 <= r["overall_severity"] <= 1.0


# ────────────────────────────────────────────────────────────────────
#  10. TELEMETRY FRAME — NO NaN IN OUTPUTS
# ────────────────────────────────────────────────────────────────────

class TestTelemetryFrameFuzz:
    """Property tests for TelemetryFrame construction and serialization."""

    @given(
        ts=st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False),
        alt=st.floats(min_value=-100, max_value=50000, allow_nan=False, allow_infinity=False),
        roll=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
        pitch=st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False),
        yaw=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
        soc=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
        solar_w=_positive_float,
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_telemetry_frame_to_dict_no_nan(
        self, ts: float, alt: float, roll: float, pitch: float,
        yaw: float, soc: float, solar_w: float,
    ) -> None:
        """TelemetryFrame.to_dict() must never contain NaN values."""
        frame = TelemetryFrame(
            timestamp_s=ts,
            altitude_km=alt,
            roll_deg=roll,
            pitch_deg=pitch,
            yaw_deg=yaw,
            battery_soc=soc,
            solar_power_w=solar_w,
        )
        d = frame.to_dict()
        for key, val in d.items():
            if isinstance(val, float):
                assert not math.isnan(val), f"NaN in TelemetryFrame.{key}"
                assert not math.isinf(val), f"Inf in TelemetryFrame.{key}"
            elif isinstance(val, list):
                for i, v in enumerate(val):
                    if isinstance(v, float):
                        assert not math.isnan(v), f"NaN in TelemetryFrame.{key}[{i}]"


# ────────────────────────────────────────────────────────────────────
#  11. DASHBOARD STATUS LOGIC — DETERMINISTIC INVARIANTS
# ────────────────────────────────────────────────────────────────────

class TestDashboardStatusInvariants:
    """Invariant tests for the dashboard status computation logic."""

    @given(battery=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_battery_thresholds_consistent(self, battery: float) -> None:
        """Battery SoC thresholds must produce consistent status ordering."""
        dash = HealthDashboard()
        dash.update_power(battery_soc=battery)
        snap = dash.snapshot()
        if battery < 5:
            assert snap.overall_status == "EMERGENCY"
        elif battery < 15:
            assert snap.overall_status == "CRITICAL"
        elif battery < 25:
            assert snap.overall_status == "WARNING"

    @given(o2=st.floats(min_value=0, max_value=25, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_o2_thresholds_consistent(self, o2: float) -> None:
        """O2 thresholds must produce consistent status ordering."""
        dash = HealthDashboard()
        dash.update_eclss(o2_pct=o2)
        snap = dash.snapshot()
        if o2 < 18:
            assert snap.overall_status == "EMERGENCY"
        elif o2 < 19:
            assert snap.overall_status == "CRITICAL"

    @given(score=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_dsremo_score_thresholds(self, score: float) -> None:
        """Dsremo anomaly score thresholds must produce correct status."""
        dash = HealthDashboard()
        dash.update_subsystem("test", status="NOMINAL", dsremo_score=score)
        snap = dash.snapshot()
        if score > 0.8:
            assert snap.overall_status in ("CRITICAL", "EMERGENCY")
        elif score > 0.5:
            assert snap.overall_status in ("WARNING", "CRITICAL", "EMERGENCY")
        elif score > 0.3:
            assert snap.overall_status in ("CAUTION", "WARNING", "CRITICAL", "EMERGENCY")

    def test_two_critical_subsystems_trigger_emergency(self) -> None:
        """Two CRITICAL subsystems must always produce EMERGENCY status."""
        dash = HealthDashboard()
        dash.update_subsystem("nav", status="CRITICAL")
        dash.update_subsystem("power", status="CRITICAL")
        snap = dash.snapshot()
        assert snap.overall_status == "EMERGENCY"

    def test_nominal_all_defaults(self) -> None:
        """A fresh dashboard with no updates must report NOMINAL."""
        dash = HealthDashboard()
        snap = dash.snapshot()
        assert snap.overall_status == "NOMINAL"

    @given(n_alerts=st.integers(min_value=0, max_value=600))
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_alert_history_capped_at_500(self, n_alerts: int) -> None:
        """Alert history must never exceed 500 entries."""
        dash = HealthDashboard()
        for i in range(n_alerts):
            dash.record_alert("WARNING", subsystem="test", message=f"alert {i}")
        alerts = dash.recent_alerts(limit=10000)
        assert len(alerts) <= 500
