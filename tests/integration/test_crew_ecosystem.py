"""Integration tests for Crew Lifecycle & Closed-Loop Ecosystem.

Tests cover:
  PART 1 — Crew lifecycle: birth, aging, death, role coverage, skill dynamics
  PART 2 — Education system: teacher ratios, knowledge decay, training pipelines
  PART 3 — Closed-loop ecosystem: element tracking, cycle closures, depletion
  INTEGRATED — Orchestrator feeding outputs between subsystems
"""

from __future__ import annotations

import pytest

from aria.simulation.crew_ecosystem import (
    ALL_SKILLS,
    ANNUAL_REQUIREMENT_PER_PERSON,
    CRITICAL_ROLES,
    INITIAL_ELEMENTS_KG,
    TRAINING_YEARS,
    ClosedLoopEcosystemSimulator,
    CrewEcosystemOrchestrator,
    CrewLifecycleSimulator,
    CrewMember,
    CrewRole,
    CycleEfficiency,
    DeathCause,
    EducationSystemSimulator,
    EcosystemState,
    PopulationState,
)


# ════════════════════════════════════════════════════════════════
#  FIXTURES
# ════════════════════════════════════════════════════════════════

@pytest.fixture
def lifecycle_sim() -> CrewLifecycleSimulator:
    return CrewLifecycleSimulator(seed=42)


@pytest.fixture
def education_sim() -> EducationSystemSimulator:
    return EducationSystemSimulator(seed=42)


@pytest.fixture
def ecosystem_sim() -> ClosedLoopEcosystemSimulator:
    return ClosedLoopEcosystemSimulator(seed=42)


@pytest.fixture
def orchestrator() -> CrewEcosystemOrchestrator:
    return CrewEcosystemOrchestrator(seed=42)


# ════════════════════════════════════════════════════════════════
#  PART 1: CREW LIFECYCLE TESTS
# ════════════════════════════════════════════════════════════════

class TestCrewMember:
    """Tests for the CrewMember dataclass."""

    def test_age_calculation(self) -> None:
        member = CrewMember(
            name="Test", birth_year=10.0, generation=1, role=CrewRole.ENGINEER,
        )
        assert member.age(40.0) == pytest.approx(30.0)
        assert member.age(10.0) == pytest.approx(0.0)

    def test_fertility_window(self) -> None:
        member = CrewMember(
            name="Test", birth_year=0.0, generation=1, role=CrewRole.SCIENTIST,
            health=0.8,
        )
        # Too young
        assert not member.is_fertile(15.0)
        # In window
        assert member.is_fertile(25.0)
        assert member.is_fertile(35.0)
        # Too old
        assert not member.is_fertile(45.0)

    def test_fertility_requires_health(self) -> None:
        member = CrewMember(
            name="Test", birth_year=0.0, generation=1, role=CrewRole.FARMER,
            health=0.2,
        )
        # In age window but health too low
        assert not member.is_fertile(25.0)

    def test_fertility_requires_alive(self) -> None:
        member = CrewMember(
            name="Test", birth_year=0.0, generation=1, role=CrewRole.FARMER,
            health=0.8, is_alive=False,
        )
        assert not member.is_fertile(25.0)

    def test_effective_lifespan_radiation_penalty(self) -> None:
        member = CrewMember(
            name="Test", birth_year=0.0, generation=1, role=CrewRole.MEDIC,
            base_lifespan=80.0, radiation_dose_msv=0.0,
        )
        base = member.effective_lifespan()

        member.radiation_dose_msv = 2000.0
        reduced = member.effective_lifespan()
        assert reduced < base
        # 2000 mSv = 10 year reduction
        assert base - reduced == pytest.approx(10.0, abs=1.0)

    def test_effective_lifespan_health_penalty(self) -> None:
        member = CrewMember(
            name="Test", birth_year=0.0, generation=1, role=CrewRole.MEDIC,
            base_lifespan=80.0, health=1.0,
        )
        healthy = member.effective_lifespan()
        member.health = 0.5
        unhealthy = member.effective_lifespan()
        assert unhealthy < healthy

    def test_effective_lifespan_minimum(self) -> None:
        member = CrewMember(
            name="Test", birth_year=0.0, generation=1, role=CrewRole.MEDIC,
            base_lifespan=80.0, radiation_dose_msv=100_000, health=0.0,
        )
        assert member.effective_lifespan() >= 40.0


class TestCrewLifecycle:
    """Tests for CrewLifecycleSimulator."""

    def test_founding_crew_size(self, lifecycle_sim: CrewLifecycleSimulator) -> None:
        alive = lifecycle_sim.get_alive()
        assert len(alive) >= 100

    def test_founding_crew_has_all_roles(self, lifecycle_sim: CrewLifecycleSimulator) -> None:
        alive = lifecycle_sim.get_alive()
        roles_present = {c.role for c in alive}
        for role in CrewRole:
            assert role in roles_present, f"Missing role: {role.value}"

    def test_founding_crew_critical_roles_redundant(self, lifecycle_sim: CrewLifecycleSimulator) -> None:
        for role in CRITICAL_ROLES:
            count = lifecycle_sim.get_role_count(role)
            assert count >= 2, f"Critical role {role.value} has only {count} members"

    def test_simulate_year_returns_events(self, lifecycle_sim: CrewLifecycleSimulator) -> None:
        events = lifecycle_sim.simulate_year(1.0)
        assert isinstance(events, list)

    def test_population_state_updated(self, lifecycle_sim: CrewLifecycleSimulator) -> None:
        lifecycle_sim.simulate_year(1.0)
        s = lifecycle_sim.state
        assert s.total_alive > 0
        assert s.mean_health > 0
        assert s.mean_age > 0

    def test_radiation_accumulates(self, lifecycle_sim: CrewLifecycleSimulator) -> None:
        member = lifecycle_sim.crew[0]
        initial_dose = member.radiation_dose_msv
        lifecycle_sim.simulate_year(1.0)
        assert member.radiation_dose_msv > initial_dose

    def test_skills_degrade_without_practice(self) -> None:
        member = CrewMember(
            name="Test", birth_year=-30.0, generation=1, role=CrewRole.ENGINEER,
            skills={"engineering": 0.8, "medicine": 0.5, "agriculture": 0.3},
        )
        sim = CrewLifecycleSimulator(initial_crew=[member], seed=99)
        # Medicine and agriculture should degrade (not primary)
        initial_med = member.skills["medicine"]
        sim.simulate_year(1.0)
        # Engineering is primary for ENGINEER so maintained/boosted
        # Medicine should have degraded
        assert member.skills["medicine"] < initial_med

    def test_death_by_old_age(self) -> None:
        """A very old crew member should die."""
        old = CrewMember(
            name="Elder", birth_year=-95.0, generation=1, role=CrewRole.TEACHER,
            base_lifespan=80.0, health=0.3,
        )
        sim = CrewLifecycleSimulator(initial_crew=[old], seed=42)
        events = sim.simulate_year(1.0)
        assert not old.is_alive
        assert old.death_cause == DeathCause.OLD_AGE

    def test_births_when_below_target(self) -> None:
        """Population below target should produce births over time."""
        sim = CrewLifecycleSimulator(seed=42)
        initial_count = len(sim.crew)
        total_births = 0
        for y in range(1, 30):
            sim.simulate_year(float(y))
            total_births = sim.state.total_births
        # Over 30 years some births should occur
        assert total_births > 0

    def test_role_coverage_emergency_when_no_members(self) -> None:
        """If a critical role has ZERO qualified members and no trainees, EMERGENCY."""
        # Create crew with NO engineer at all
        crew = [
            CrewMember(name="Med1", birth_year=-30.0, generation=1, role=CrewRole.MEDIC,
                       skills={"medicine": 0.9}),
            CrewMember(name="Med2", birth_year=-30.0, generation=1, role=CrewRole.MEDIC,
                       skills={"medicine": 0.8}),
            CrewMember(name="Cmd1", birth_year=-30.0, generation=1, role=CrewRole.COMMANDER,
                       skills={"leadership": 0.9}),
            CrewMember(name="Cmd2", birth_year=-30.0, generation=1, role=CrewRole.COMMANDER,
                       skills={"leadership": 0.8}),
            CrewMember(name="Pil1", birth_year=-30.0, generation=1, role=CrewRole.PILOT,
                       skills={"piloting": 0.9}),
            CrewMember(name="Pil2", birth_year=-30.0, generation=1, role=CrewRole.PILOT,
                       skills={"piloting": 0.8}),
        ]
        sim = CrewLifecycleSimulator(initial_crew=crew, seed=42)
        events = sim.simulate_year(1.0)
        # Should emit EMERGENCY about no engineer
        emergencies = [e for e in events if "engineer" in e["message"].lower()
                       and e["severity"] == "EMERGENCY"]
        assert len(emergencies) > 0

    def test_skill_inheritance(self) -> None:
        """Children should partially inherit parent skills."""
        sim = CrewLifecycleSimulator(seed=42)
        # Run enough years for births
        for y in range(1, 40):
            sim.simulate_year(float(y))

        children = [c for c in sim.crew if c.generation > 1]
        if children:
            child = children[0]
            # Skills should be non-zero (inherited + noise)
            assert any(v > 0 for v in child.skills.values())

    def test_get_alive_excludes_dead(self) -> None:
        member = CrewMember(
            name="Dead", birth_year=-30.0, generation=1, role=CrewRole.FARMER,
            is_alive=False,
        )
        alive_member = CrewMember(
            name="Alive", birth_year=-30.0, generation=1, role=CrewRole.FARMER,
        )
        sim = CrewLifecycleSimulator(initial_crew=[member, alive_member], seed=42)
        assert len(sim.get_alive()) == 1


# ════════════════════════════════════════════════════════════════
#  PART 2: EDUCATION SYSTEM TESTS
# ════════════════════════════════════════════════════════════════

class TestEducationSystem:
    """Tests for EducationSystemSimulator."""

    def test_initial_state(self, education_sim: EducationSystemSimulator) -> None:
        s = education_sim.state
        assert s.glass_archive_health == pytest.approx(1.0)
        assert s.vr_system_health == pytest.approx(1.0)

    def test_teacher_ratio_calculated(self) -> None:
        sim = EducationSystemSimulator(seed=42)
        teachers = [
            CrewMember(name="T1", birth_year=-30.0, generation=1, role=CrewRole.TEACHER),
            CrewMember(name="T2", birth_year=-35.0, generation=1, role=CrewRole.TEACHER),
        ]
        students = [
            CrewMember(name="S1", birth_year=-5.0, generation=2, role=CrewRole.ENGINEER,
                       is_trainee=True, training_role=CrewRole.ENGINEER),
            CrewMember(name="S2", birth_year=-5.0, generation=2, role=CrewRole.MEDIC,
                       is_trainee=True, training_role=CrewRole.MEDIC),
        ]
        crew = teachers + students
        sim.simulate_year(1.0, crew)
        assert sim.state.teacher_count == 2
        assert sim.state.student_count == 2
        assert sim.state.teacher_student_ratio == pytest.approx(1.0)

    def test_ai_supplementation(self, education_sim: EducationSystemSimulator) -> None:
        s = education_sim.state
        # AI supplementation should be positive even without teachers
        crew: list[CrewMember] = []
        education_sim.simulate_year(1.0, crew)
        assert s.ai_supplementation > 0

    def test_vr_degrades(self, education_sim: EducationSystemSimulator) -> None:
        crew: list[CrewMember] = []
        for y in range(1, 50):
            education_sim.simulate_year(float(y), crew)
        assert education_sim.state.vr_system_health < 1.0

    def test_glass_archive_nearly_permanent(self, education_sim: EducationSystemSimulator) -> None:
        crew: list[CrewMember] = []
        for y in range(1, 100):
            education_sim.simulate_year(float(y), crew)
        assert education_sim.state.glass_archive_health > 0.99

    def test_knowledge_gap_creates_relearn_penalty(self) -> None:
        """If a skill has no practitioners, a relearn penalty should appear."""
        sim = EducationSystemSimulator(seed=42)
        # Crew with no one skilled in 'piloting'
        crew = [
            CrewMember(name="E1", birth_year=-30.0, generation=1, role=CrewRole.ENGINEER,
                       skills={s: 0.0 for s in ALL_SKILLS}),
        ]
        crew[0].skills["engineering"] = 0.8

        # Run enough years for gap to form
        for y in range(1, 20):
            sim.simulate_year(float(y), crew)

        # 'piloting' should have low continuity
        assert sim.state.domain_continuity.get("piloting", 1.0) < 0.5

    def test_training_duration_constants(self) -> None:
        assert TRAINING_YEARS[CrewRole.ENGINEER] == 5
        assert TRAINING_YEARS[CrewRole.MEDIC] == 7
        assert TRAINING_YEARS[CrewRole.FARMER] == 3


# ════════════════════════════════════════════════════════════════
#  PART 3: CLOSED-LOOP ECOSYSTEM TESTS
# ════════════════════════════════════════════════════════════════

class TestClosedLoopEcosystem:
    """Tests for ClosedLoopEcosystemSimulator."""

    def test_initial_elements(self, ecosystem_sim: ClosedLoopEcosystemSimulator) -> None:
        for element, expected in INITIAL_ELEMENTS_KG.items():
            assert ecosystem_sim.state.elements_kg[element] == pytest.approx(expected)

    def test_elements_decrease_over_time(self, ecosystem_sim: ClosedLoopEcosystemSimulator) -> None:
        initial = dict(ecosystem_sim.state.elements_kg)
        for y in range(1, 20):
            ecosystem_sim.simulate_year(float(y), population=100)
        for element in INITIAL_ELEMENTS_KG:
            assert ecosystem_sim.state.elements_kg[element] <= initial[element]

    def test_water_cycle_98_percent(self) -> None:
        sim = ClosedLoopEcosystemSimulator(seed=42)
        initial_water = sim.state.water_total_liters
        sim.simulate_year(1.0, population=100)
        # Water should decrease but only by ~2% of usage
        assert sim.state.water_total_liters < initial_water
        assert sim.state.water_total_liters > initial_water * 0.5  # Not catastrophic in 1 year

    def test_oxygen_cycle_99_percent(self) -> None:
        sim = ClosedLoopEcosystemSimulator(seed=42)
        initial_o2 = sim.state.o2_atmosphere_kg
        sim.simulate_year(1.0, population=100)
        # O2 loss should be small (1% of demand)
        loss = initial_o2 - sim.state.o2_atmosphere_kg
        annual_demand = 0.84 * 365 * 100
        assert loss < annual_demand * 0.02  # Less than 2% of demand lost

    def test_trace_elements_deplete_faster_than_bulk_by_ratio(self) -> None:
        """Trace elements have low absolute stock but also low demand.
        Carbon has huge demand relative to stock and depletes fastest.
        Verify iodine outlasts carbon due to tiny per-person requirement."""
        sim = ClosedLoopEcosystemSimulator(seed=42)
        iodine_years = sim.years_until_depletion("I", 100)
        carbon_years = sim.years_until_depletion("C", 100)
        # Carbon: 20000 kg, 110 kg/person/year, 5% loss = 550 kg/yr -> ~36 years
        # Iodine: 5 kg, 0.00005 kg/person/year, 25% loss = ~0.00125 kg/yr -> ~4000 years
        assert iodine_years > carbon_years
        assert carbon_years < 100  # Carbon is the bottleneck

    def test_zero_population_no_losses(self) -> None:
        sim = ClosedLoopEcosystemSimulator(seed=42)
        initial = dict(sim.state.elements_kg)
        sim.simulate_year(1.0, population=0)
        for el in INITIAL_ELEMENTS_KG:
            assert sim.state.elements_kg[el] == pytest.approx(initial[el])

    def test_emergency_on_depletion(self) -> None:
        """Depleting an element should trigger EMERGENCY."""
        # Start with almost no iodine
        elements = dict(INITIAL_ELEMENTS_KG)
        elements["I"] = 0.001
        sim = ClosedLoopEcosystemSimulator(initial_elements=elements, seed=42)
        events = sim.simulate_year(1.0, population=100)
        emergencies = [e for e in events if e["severity"] == "EMERGENCY" and "I" in e["message"]]
        assert len(emergencies) > 0

    def test_cycle_efficiency_degrades(self, ecosystem_sim: ClosedLoopEcosystemSimulator) -> None:
        eff = ecosystem_sim.state.cycle_efficiency
        initial_water = eff.water
        for y in range(1, 50):
            ecosystem_sim.simulate_year(float(y), population=100)
        assert eff.water < initial_water

    def test_locked_elements_accumulate(self) -> None:
        sim = ClosedLoopEcosystemSimulator(seed=42)
        for y in range(1, 20):
            sim.simulate_year(float(y), population=100)
        # Some elements should have locked compounds
        total_locked = sum(sim.state.locked_elements_kg.values())
        assert total_locked > 0

    def test_co2_accumulation_with_poor_scrubbing(self) -> None:
        sim = ClosedLoopEcosystemSimulator(seed=42)
        # Degrade carbon cycle
        sim.state.cycle_efficiency.carbon = 0.5
        sim.simulate_year(1.0, population=100)
        # CO2 should have risen
        assert sim.state.co2_atmosphere_kg > 200  # Initial is 200

    def test_get_element_status(self, ecosystem_sim: ClosedLoopEcosystemSimulator) -> None:
        status = ecosystem_sim.get_element_status()
        assert "C" in status
        assert "remaining_pct" in status["C"]
        assert status["C"]["remaining_pct"] == pytest.approx(100.0)

    def test_years_until_depletion_positive(self, ecosystem_sim: ClosedLoopEcosystemSimulator) -> None:
        for element in INITIAL_ELEMENTS_KG:
            years = ecosystem_sim.years_until_depletion(element, 100)
            assert years > 0

    def test_custom_initial_elements(self) -> None:
        custom = {"C": 100.0, "O": 200.0}
        sim = ClosedLoopEcosystemSimulator(initial_elements=custom, seed=42)
        assert sim.state.elements_kg["C"] == pytest.approx(100.0)
        assert sim.state.elements_kg["O"] == pytest.approx(200.0)


# ════════════════════════════════════════════════════════════════
#  INTEGRATED ORCHESTRATOR TESTS
# ════════════════════════════════════════════════════════════════

class TestCrewEcosystemOrchestrator:
    """Tests for the integrated orchestrator."""

    def test_simulate_year_returns_dict(self, orchestrator: CrewEcosystemOrchestrator) -> None:
        result = orchestrator.simulate_year(1.0)
        assert isinstance(result, dict)
        assert "year" in result
        assert "population" in result
        assert "events" in result
        assert "ecosystem" in result

    def test_population_feeds_ecosystem(self, orchestrator: CrewEcosystemOrchestrator) -> None:
        result = orchestrator.simulate_year(1.0)
        # Population should be > 0 and ecosystem should have processed demands
        assert result["population"] > 0
        assert result["o2_kg"] > 0

    def test_nutrition_quality_feeds_crew(self, orchestrator: CrewEcosystemOrchestrator) -> None:
        result = orchestrator.simulate_year(1.0)
        assert "nutrition_quality" in result
        assert 0.0 <= result["nutrition_quality"] <= 1.0

    def test_medical_care_from_medic_count(self, orchestrator: CrewEcosystemOrchestrator) -> None:
        result = orchestrator.simulate_year(1.0)
        assert "medical_care" in result
        assert result["medical_care"] > 0

    def test_run_centuries(self, orchestrator: CrewEcosystemOrchestrator) -> None:
        results = orchestrator.run_centuries(years=10)
        assert len(results) == 10
        assert results[0]["year"] == pytest.approx(1.0)
        assert results[-1]["year"] == pytest.approx(10.0)

    def test_get_summary(self, orchestrator: CrewEcosystemOrchestrator) -> None:
        orchestrator.simulate_year(1.0)
        summary = orchestrator.get_summary()
        assert "population" in summary
        assert "education" in summary
        assert "ecosystem" in summary

    def test_multi_year_population_survives(self) -> None:
        """Over 50 years, population should survive (not go to zero)."""
        orch = CrewEcosystemOrchestrator(seed=42)
        for y in range(1, 51):
            orch.simulate_year(float(y))
        pop = orch.lifecycle.state.total_alive
        assert pop >= 1  # At least someone survives

    def test_ecosystem_elements_tracked_after_run(self) -> None:
        orch = CrewEcosystemOrchestrator(seed=42)
        for y in range(1, 11):
            orch.simulate_year(float(y))
        status = orch.ecosystem.get_element_status()
        for element in INITIAL_ELEMENTS_KG:
            assert element in status
            # After 10 years, nothing should be fully depleted
            assert status[element]["current_kg"] > 0

    def test_education_quality_reported(self) -> None:
        orch = CrewEcosystemOrchestrator(seed=42)
        result = orch.simulate_year(1.0)
        assert "education_quality" in result
        assert result["education_quality"] > 0

    def test_role_coverage_reported(self) -> None:
        orch = CrewEcosystemOrchestrator(seed=42)
        result = orch.simulate_year(1.0)
        assert "role_coverage" in result
        for role in CrewRole:
            assert role.value in result["role_coverage"]
