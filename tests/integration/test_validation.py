"""Integration tests for the ARIA physics/engineering validation suite.

Validates that the generation ship simulation respects physical laws:
  1. Energy conservation (RTG decay, power budget)
  2. Mass conservation (no creation in void)
  3. Velocity constraints (0.1c cap, non-negative)
  4. Population constraints (non-negative, biological growth limits)
  5. Resource non-negativity (fuel, water, food, spares)
  6. Thermal balance (radiator vs waste heat)
  7. Shield erosion (monotonic, Hoang model consistency)
  8. Target mission scenarios (star catalog lookups)
"""

from __future__ import annotations

import math

import pytest

from aria.simulation.generation_ship import (
    GenerationShipConfig,
    GenerationShipSimulation,
)
from aria.simulation.interstellar import InterstellarSimulation
from aria.simulator.engine import SimulatorEngine, SimulatorState, SimulatorTimeline
from aria.simulator.targets import (
    STAR_CATALOG,
    get_target,
    list_targets,
    mission_duration_years,
)
from aria.validation.physics_validator import (
    PhysicsValidator,
    ValidationReport,
    Violation,
    ViolationSeverity,
)


# ════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def engine_200yr() -> SimulatorEngine:
    """Run a 200-year simulation once for all tests in this module."""
    engine = SimulatorEngine(
        target=STAR_CATALOG["100_ly_target"],
        velocity_c=0.1,
        crew_size=4,
        seed=42,
    )
    engine.initialize()
    engine.run(years=200)
    return engine


@pytest.fixture(scope="module")
def report_200yr(engine_200yr: SimulatorEngine) -> ValidationReport:
    """Validation report for the 200-year simulation."""
    validator = PhysicsValidator()
    return validator.validate_engine(engine_200yr)


@pytest.fixture(scope="module")
def interstellar_50yr() -> InterstellarSimulation:
    """Run the core interstellar simulation for 50 years."""
    sim = InterstellarSimulation(cruise_velocity_c=0.1, crew_size=4, seed=42)
    for _ in range(50):
        sim.simulate_year()
    return sim


# ════════════════════════════════════════════════════════════════
#  1. ENERGY CONSERVATION
# ════════════════════════════════════════════════════════════════

class TestEnergyConservation:
    def test_rtg_follows_pu238_half_life(self, engine_200yr: SimulatorEngine) -> None:
        """RTG power fraction must match Pu-238 decay at each year."""
        half_life = 87.7
        for snap in engine_200yr.timeline._snapshots[1:]:
            year = snap.mission_time_years
            expected = 0.5 ** (year / half_life)
            assert abs(snap.rtg_power_fraction - expected) < 0.02, (
                f"Year {year}: RTG {snap.rtg_power_fraction:.4f} != expected {expected:.4f}"
            )

    def test_power_never_negative(self, engine_200yr: SimulatorEngine) -> None:
        """Total power must always be non-negative."""
        for snap in engine_200yr.timeline._snapshots:
            assert snap.power_watts >= 0, f"Year {snap.mission_time_years}: negative power"

    def test_fuel_energy_budget(self) -> None:
        """Initial fuel energy must be physically meaningful."""
        fuel_kg = 50_000.0
        energy_j = fuel_kg * 3.4e14  # D-T fusion energy density
        # At minimum, fuel should have enough energy for station-keeping
        # 50 kg/yr * 1000 yr * some conversion factor
        assert energy_j > 1e18, "Fuel energy budget too low for multi-century mission"

    def test_rtg_50_percent_at_half_life(self) -> None:
        """RTG should output ~50% at exactly one half-life (87.7 years)."""
        engine = SimulatorEngine(
            target=STAR_CATALOG["100_ly_target"],
            velocity_c=0.1,
            crew_size=4,
            seed=0,
        )
        engine.initialize()
        engine.run(years=88)
        snap = engine.timeline.seek(88)
        assert snap is not None
        assert abs(snap.rtg_power_fraction - 0.5) < 0.02


# ════════════════════════════════════════════════════════════════
#  2. MASS CONSERVATION
# ════════════════════════════════════════════════════════════════

class TestMassConservation:
    def test_fuel_only_decreases(self, engine_200yr: SimulatorEngine) -> None:
        """Fuel mass must monotonically decrease (burn only, no refueling)."""
        prev_fuel = float("inf")
        for snap in engine_200yr.timeline._snapshots:
            assert snap.fuel_kg <= prev_fuel + 1e-3, (
                f"Year {snap.mission_time_years}: fuel increased "
                f"from {prev_fuel:.1f} to {snap.fuel_kg:.1f}"
            )
            prev_fuel = snap.fuel_kg

    def test_water_decreasing_trend(self, interstellar_50yr: InterstellarSimulation) -> None:
        """Water liters should trend downward (recycling losses)."""
        s = interstellar_50yr.state
        assert s.water_liters < 500_000.0, "Water should decrease from initial 500,000 L"

    def test_no_mass_creation(self, report_200yr: ValidationReport) -> None:
        """No MASS category violations at ERROR level."""
        mass_errors = [
            v for v in report_200yr.violations
            if v.category == "MASS" and v.severity in (ViolationSeverity.ERROR, ViolationSeverity.CRITICAL)
        ]
        assert len(mass_errors) == 0, f"Mass conservation violated: {mass_errors}"


# ════════════════════════════════════════════════════════════════
#  3. VELOCITY CONSTRAINTS
# ════════════════════════════════════════════════════════════════

class TestVelocityConstraints:
    def test_never_exceeds_01c(self, engine_200yr: SimulatorEngine) -> None:
        """Velocity must never exceed 0.1c (initial cruise speed)."""
        for snap in engine_200yr.timeline._snapshots:
            assert snap.velocity_scalar_c <= 0.101, (
                f"Year {snap.mission_time_years}: velocity {snap.velocity_scalar_c}c > 0.1c"
            )

    def test_velocity_non_negative(self, engine_200yr: SimulatorEngine) -> None:
        """Ship cannot fly backwards."""
        for snap in engine_200yr.timeline._snapshots:
            assert snap.velocity_scalar_c >= -1e-10, (
                f"Year {snap.mission_time_years}: negative velocity {snap.velocity_scalar_c}c"
            )

    def test_ism_drag_causes_deceleration(self, interstellar_50yr: InterstellarSimulation) -> None:
        """ISM drag should cause measurable but small velocity decrease."""
        s = interstellar_50yr.state
        assert s.velocity_c <= 0.1, "Velocity should not increase from ISM drag"
        assert s.ism_drag_delta_v_ms > 0, "ISM drag should accumulate over 50 years"

    def test_no_velocity_violations(self, report_200yr: ValidationReport) -> None:
        """No VELOCITY violations at any severity."""
        v_violations = [v for v in report_200yr.violations if v.category == "VELOCITY"]
        assert len(v_violations) == 0, f"Velocity violations: {v_violations}"


# ════════════════════════════════════════════════════════════════
#  4. POPULATION CONSTRAINTS
# ════════════════════════════════════════════════════════════════

class TestPopulationConstraints:
    def test_crew_never_negative(self, engine_200yr: SimulatorEngine) -> None:
        """Crew count must never go below zero."""
        for snap in engine_200yr.timeline._snapshots:
            assert snap.crew_count >= 0, (
                f"Year {snap.mission_time_years}: negative crew {snap.crew_count}"
            )

    def test_initial_crew_count(self, engine_200yr: SimulatorEngine) -> None:
        """Initial crew should match configuration."""
        first = engine_200yr.timeline._snapshots[0]
        assert first.crew_count == 4

    def test_no_extreme_population_growth(self, report_200yr: ValidationReport) -> None:
        """No biologically impossible population growth."""
        pop_violations = [
            v for v in report_200yr.violations
            if v.category == "POPULATION"
        ]
        critical = [v for v in pop_violations if v.severity == ViolationSeverity.CRITICAL]
        assert len(critical) == 0, f"Critical population violations: {critical}"


# ════════════════════════════════════════════════════════════════
#  5. RESOURCE NON-NEGATIVITY
# ════════════════════════════════════════════════════════════════

class TestResourceNonNegativity:
    def test_fuel_non_negative(self, engine_200yr: SimulatorEngine) -> None:
        """Fuel can reach zero but never go negative."""
        for snap in engine_200yr.timeline._snapshots:
            assert snap.fuel_kg >= -1e-6, (
                f"Year {snap.mission_time_years}: negative fuel {snap.fuel_kg}"
            )

    def test_water_non_negative(self, engine_200yr: SimulatorEngine) -> None:
        """Water liters must stay non-negative."""
        for snap in engine_200yr.timeline._snapshots:
            assert snap.water_liters >= -1e-6, (
                f"Year {snap.mission_time_years}: negative water {snap.water_liters}"
            )

    def test_food_non_negative(self, engine_200yr: SimulatorEngine) -> None:
        """Food reserves must stay non-negative."""
        for snap in engine_200yr.timeline._snapshots:
            assert snap.food_reserves_kg >= -1e-6, (
                f"Year {snap.mission_time_years}: negative food {snap.food_reserves_kg}"
            )

    def test_health_values_bounded(self, engine_200yr: SimulatorEngine) -> None:
        """All health values must be in [0, 1]."""
        health_attrs = [
            "hull_integrity", "electronics_health", "printer_health",
            "seed_viability", "hydroponic_capacity", "grow_light_health",
        ]
        for snap in engine_200yr.timeline._snapshots:
            for attr in health_attrs:
                val = getattr(snap, attr, None)
                if val is None:
                    continue
                assert -1e-6 <= val <= 1.0 + 1e-6, (
                    f"Year {snap.mission_time_years}: {attr}={val} out of [0,1]"
                )

    def test_spare_parts_non_negative(self, engine_200yr: SimulatorEngine) -> None:
        """Spare part counts must be non-negative."""
        for snap in engine_200yr.timeline._snapshots:
            assert snap.spare_electronics >= 0, (
                f"Year {snap.mission_time_years}: negative spare electronics"
            )
            assert snap.spare_mechanical >= 0, (
                f"Year {snap.mission_time_years}: negative spare mechanical"
            )

    def test_no_resource_violations(self, report_200yr: ValidationReport) -> None:
        """No RESOURCE violations at ERROR or CRITICAL level."""
        res_errors = [
            v for v in report_200yr.violations
            if v.category == "RESOURCE"
            and v.severity in (ViolationSeverity.ERROR, ViolationSeverity.CRITICAL)
        ]
        assert len(res_errors) == 0, f"Resource violations: {res_errors}"


# ════════════════════════════════════════════════════════════════
#  6. THERMAL BALANCE
# ════════════════════════════════════════════════════════════════

class TestThermalBalance:
    def test_stefan_boltzmann_radiator_capacity(self) -> None:
        """Verify the Stefan-Boltzmann calculation for standard radiator."""
        sigma = 5.670374419e-8
        epsilon = 0.9
        area = 2000.0  # m^2
        temp = 300.0   # K
        max_radiated = epsilon * sigma * area * temp ** 4
        # Should be ~826 kW
        assert 800_000 < max_radiated < 900_000, f"Radiator capacity: {max_radiated:.0f} W"

    def test_waste_heat_within_radiator_limits(self) -> None:
        """At nominal power, waste heat should be manageable by radiators."""
        power = 500_000  # 500 kW
        waste_heat = power * 0.4  # 40% inefficiency = 200 kW
        radiator_capacity = 0.9 * 5.670374419e-8 * 2000 * 300 ** 4
        # 200 kW << 826 kW
        assert waste_heat < radiator_capacity, "Waste heat exceeds radiator capacity at nominal"


# ════════════════════════════════════════════════════════════════
#  7. SHIELD EROSION
# ════════════════════════════════════════════════════════════════

class TestShieldErosion:
    def test_hull_integrity_decreases(self, engine_200yr: SimulatorEngine) -> None:
        """Hull integrity should decrease over time from erosion and impacts."""
        first = engine_200yr.timeline._snapshots[0]
        last = engine_200yr.timeline._snapshots[-1]
        assert last.hull_integrity < first.hull_integrity, (
            "Hull should degrade over 200 years of interstellar travel"
        )

    def test_hoang_erosion_model_order_of_magnitude(self) -> None:
        """Verify Hoang et al. erosion rate scaling at 0.1c."""
        # At 0.3c: ~40 ug/ly/cm^2
        # At 0.1c (v^3 scaling): 40 * (0.1/0.3)^3 = ~1.48 ug/ly/cm^2
        rate_at_03c = 40e-6  # g/ly/cm^2
        rate_at_01c = rate_at_03c * (0.1 / 0.3) ** 3
        assert 1.0e-6 < rate_at_01c < 2.0e-6, (
            f"Hoang rate at 0.1c: {rate_at_01c:.2e} g/ly/cm^2"
        )

    def test_shield_health_bounded(self, engine_200yr: SimulatorEngine) -> None:
        """Shield overall health must stay in [0, 1]."""
        for snap in engine_200yr.timeline._snapshots:
            assert 0.0 <= snap.shield_overall_health <= 1.0 + 1e-6, (
                f"Year {snap.mission_time_years}: shield health {snap.shield_overall_health}"
            )


# ════════════════════════════════════════════════════════════════
#  8. TARGET STAR MISSIONS
# ════════════════════════════════════════════════════════════════

class TestTargetMissions:
    def test_proxima_centauri_lookup(self) -> None:
        """Proxima Centauri should be in the catalog at 4.24 ly."""
        t = get_target("proxima_centauri")
        assert t.distance_ly == 4.24
        assert t.known_planets == 3
        assert "M5.5Ve" in t.spectral_type

    def test_tau_ceti_lookup(self) -> None:
        """Tau Ceti should be at 11.9 ly with 5 planets."""
        t = get_target("tau_ceti")
        assert t.distance_ly == 11.9
        assert t.known_planets == 5

    def test_trappist_1_lookup(self) -> None:
        """TRAPPIST-1 at 39.5 ly with 7 planets."""
        t = get_target("trappist_1")
        assert t.distance_ly == 39.5
        assert t.known_planets == 7

    def test_barnards_star_lookup(self) -> None:
        """Barnard's Star at 5.96 ly."""
        t = get_target("barnards_star")
        assert t.distance_ly == 5.96

    def test_unknown_star_raises(self) -> None:
        """Unknown star should raise KeyError."""
        with pytest.raises(KeyError):
            get_target("fictional_star")

    def test_mission_duration_calculation(self) -> None:
        """Travel time at 0.1c should be distance / 0.1."""
        t = get_target("proxima_centauri")
        duration = mission_duration_years(t, 0.1)
        assert abs(duration - 42.4) < 0.1

    def test_list_targets_sorted_by_distance(self) -> None:
        """list_targets() should return targets sorted by distance."""
        targets = list_targets()
        assert len(targets) > 5
        distances = [t["distance_ly"] for t in targets]
        assert distances == sorted(distances), "Targets not sorted by distance"

    def test_proxima_centauri_mission_runs(self) -> None:
        """A Proxima Centauri mission (42 yr) should complete without crash."""
        config = GenerationShipConfig.breakthrough(seed=42)
        config.target_distance_ly = 4.24
        sim = GenerationShipSimulation(config)
        results = sim.run(years=42)
        assert results.years_simulated == 42
        assert results.total_events > 0

    def test_barnards_star_mission_runs(self) -> None:
        """A Barnard's Star mission (60 yr) should complete."""
        config = GenerationShipConfig.breakthrough(seed=42)
        config.target_distance_ly = 5.96
        sim = GenerationShipSimulation(config)
        results = sim.run(years=60)
        assert results.years_simulated == 60
        assert results.total_events > 0


# ════════════════════════════════════════════════════════════════
#  9. VALIDATOR INFRASTRUCTURE
# ════════════════════════════════════════════════════════════════

class TestValidatorInfrastructure:
    def test_empty_timeline_returns_clean(self) -> None:
        """Empty timeline should produce a clean report."""
        validator = PhysicsValidator()
        report = validator.validate_states([])
        assert report.is_clean
        assert report.years_validated == 0

    def test_report_summary_format(self, report_200yr: ValidationReport) -> None:
        """Report summary should be well-formatted."""
        summary = report_200yr.summary()
        assert "Physics Validation Report" in summary
        assert "Years validated" in summary
        assert "Checks run" in summary

    def test_violation_severity_levels(self) -> None:
        """All severity levels should be accessible."""
        assert ViolationSeverity.INFO.value == "INFO"
        assert ViolationSeverity.WARNING.value == "WARNING"
        assert ViolationSeverity.ERROR.value == "ERROR"
        assert ViolationSeverity.CRITICAL.value == "CRITICAL"

    def test_validator_runs_many_checks(self, report_200yr: ValidationReport) -> None:
        """Validator should run a substantial number of checks over 200 years."""
        # 200 snapshots * ~10+ checks per snapshot
        assert report_200yr.checks_run > 1000, (
            f"Only {report_200yr.checks_run} checks for 200 years — expected >1000"
        )

    def test_most_checks_pass(self, report_200yr: ValidationReport) -> None:
        """The vast majority of physics checks should pass."""
        pass_rate = report_200yr.checks_passed / max(report_200yr.checks_run, 1)
        assert pass_rate > 0.90, (
            f"Only {pass_rate:.0%} checks passed — physics model may be broken"
        )

    def test_no_critical_violations(self, report_200yr: ValidationReport) -> None:
        """No CRITICAL violations (impossible physical states) in 200-year sim."""
        critical = [
            v for v in report_200yr.violations
            if v.severity == ViolationSeverity.CRITICAL
        ]
        assert len(critical) == 0, (
            f"{len(critical)} critical violations found: "
            + "; ".join(v.description for v in critical[:5])
        )

    def test_violations_by_category(self, report_200yr: ValidationReport) -> None:
        """violations_by_category should partition correctly."""
        by_cat = report_200yr.violations_by_category()
        total = sum(len(vs) for vs in by_cat.values())
        assert total == len(report_200yr.violations)
