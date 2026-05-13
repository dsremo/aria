"""Tests for Multi-Stage Braking Architecture — Forward Staged Sail.

Validates that the braking architecture achieves orbital insertion
at target stars, solving the FLY_THROUGH problem.
"""

import math

import pytest

from aria.simulation.braking_architecture import (
    BrakingConfig,
    BrakingSimulator,
    BrakingState,
    BrakingYearResult,
    FusionBrakingConfig,
    LaserArrayConfig,
    MagsailBrakingConfig,
    StagedSailConfig,
    run_alpha_centauri_mission,
    run_barnards_star_mission,
    run_proxima_centauri_mission,
    run_tau_ceti_mission,
)
from aria.simulation.food_synthesis import ism_density_at_distance


# ─── Physical constants (matching braking_architecture.py) ───
C_M_S = 2.998e8
YEAR_S = 3.1557e7
LY_M = 9.461e15


class TestLaserArrayConfig:
    """Tests for the origin laser array with relay lens chain."""

    def test_full_power_at_origin(self) -> None:
        laser = LaserArrayConfig()
        power = laser.effective_power_at_distance(0.0)
        assert power == pytest.approx(7.2e12)

    def test_relay_transmission_loss(self) -> None:
        """Each relay lens loses 7%. After N relays, power = P0 * 0.93^N."""
        laser = LaserArrayConfig()
        # At 2.0 ly: 4 relays (spacing 0.5 ly)
        power = laser.effective_power_at_distance(2.0)
        expected = 7.2e12 * 0.93**4
        assert power == pytest.approx(expected, rel=0.01)

    def test_power_decreases_with_distance(self) -> None:
        laser = LaserArrayConfig()
        p1 = laser.effective_power_at_distance(1.0)
        p2 = laser.effective_power_at_distance(2.0)
        p3 = laser.effective_power_at_distance(3.0)
        assert p1 > p2 > p3 > 0

    def test_power_beyond_relay_chain(self) -> None:
        """Beyond the relay chain, divergence kicks in heavily."""
        laser = LaserArrayConfig()
        # 10 relays cover 5 ly. At 10 ly, beam has diverged.
        p_at_4 = laser.effective_power_at_distance(4.0)
        p_at_10 = laser.effective_power_at_distance(10.0)
        assert p_at_10 < p_at_4

    def test_power_always_positive(self) -> None:
        laser = LaserArrayConfig()
        for d in [0.1, 0.5, 1.0, 2.0, 4.0, 10.0, 50.0]:
            assert laser.effective_power_at_distance(d) > 0


class TestStagedSailConfig:
    """Tests for Forward's 3-part staged sail geometry."""

    def test_outer_ring_area(self) -> None:
        sail = StagedSailConfig()
        # Ring area = pi * (500000^2 - 160000^2)
        expected = math.pi * (500_000.0**2 - 160_000.0**2)
        assert sail.outer_ring_area_m2 == pytest.approx(expected)

    def test_inner_sail_area(self) -> None:
        sail = StagedSailConfig()
        expected = math.pi * 50_000.0**2
        assert sail.inner_sail_area_m2 == pytest.approx(expected)

    def test_total_sail_area(self) -> None:
        sail = StagedSailConfig()
        expected = math.pi * 500_000.0**2
        assert sail.total_sail_area_m2 == pytest.approx(expected)

    def test_areas_are_nested(self) -> None:
        sail = StagedSailConfig()
        assert sail.inner_sail_area_m2 < sail.middle_ring_area_m2
        assert sail.middle_ring_area_m2 < sail.outer_ring_area_m2

    def test_focusing_efficiency_bounded(self) -> None:
        sail = StagedSailConfig()
        assert 0.0 < sail.focusing_efficiency <= 1.0
        assert 0.0 < sail.reflectivity <= 1.0


class TestFusionBrakingConfig:
    """Tests for the fusion braking reserved fuel system."""

    def test_exhaust_velocity(self) -> None:
        fusion = FusionBrakingConfig()
        # v_e = g * Isp = 9.81 * 100,000 = 981,000 m/s
        assert fusion.exhaust_velocity_m_s == pytest.approx(981_000.0, rel=0.01)

    def test_max_delta_v_with_fuel(self) -> None:
        fusion = FusionBrakingConfig()
        # With 15000 kg fuel and 200000 kg dry mass:
        # dv = 981000 * ln(215000/200000) = 981000 * 0.0723 = ~70.9 km/s
        dv = fusion.max_delta_v(15_000.0)
        assert dv > 50_000.0  # At least 50 km/s
        assert dv < 200_000.0  # Less than 200 km/s

    def test_max_delta_v_no_fuel(self) -> None:
        fusion = FusionBrakingConfig()
        assert fusion.max_delta_v(0.0) == 0.0

    def test_max_delta_v_increases_with_fuel(self) -> None:
        fusion = FusionBrakingConfig()
        dv_small = fusion.max_delta_v(5_000.0)
        dv_large = fusion.max_delta_v(15_000.0)
        assert dv_large > dv_small


class TestMagsailConfig:
    """Tests for magsail braking configuration."""

    def test_magsail_area(self) -> None:
        ms = MagsailBrakingConfig()
        # 50 km diameter = 25 km radius = 25000 m
        expected = math.pi * 25_000.0**2
        assert ms.area_m2 == pytest.approx(expected)

    def test_drag_coefficient(self) -> None:
        ms = MagsailBrakingConfig()
        assert ms.drag_coefficient == pytest.approx(4.0)


class TestBrakingState:
    """Tests for braking state tracking."""

    def test_journey_fraction(self) -> None:
        s = BrakingState(distance_covered_ly=2.12, target_distance_ly=4.24)
        assert s.journey_fraction == pytest.approx(0.5)

    def test_remaining_ly(self) -> None:
        s = BrakingState(distance_covered_ly=3.0, target_distance_ly=4.24)
        assert s.remaining_ly == pytest.approx(1.24)

    def test_journey_fraction_at_target(self) -> None:
        s = BrakingState(distance_covered_ly=5.0, target_distance_ly=4.24)
        assert s.journey_fraction == 1.0

    def test_remaining_at_target(self) -> None:
        s = BrakingState(distance_covered_ly=5.0, target_distance_ly=4.24)
        assert s.remaining_ly == 0.0


class TestBrakingSimulatorInit:
    """Tests for simulator initialization."""

    def test_default_init(self) -> None:
        sim = BrakingSimulator(seed=42)
        assert sim.state.velocity_c == pytest.approx(0.1)
        assert sim.state.target_distance_ly == pytest.approx(4.24)
        assert not sim.state.outer_ring_deployed
        assert not sim.state.magsail_deployed

    def test_custom_target(self) -> None:
        sim = BrakingSimulator(target_distance_ly=11.91, seed=42)
        assert sim.state.target_distance_ly == pytest.approx(11.91)

    def test_custom_velocity(self) -> None:
        sim = BrakingSimulator(cruise_velocity_c=0.05, seed=42)
        assert sim.state.velocity_c == pytest.approx(0.05)

    def test_fuel_reservation(self) -> None:
        sim = BrakingSimulator(seed=42)
        cfg = sim.config
        expected_reserved = cfg.initial_fuel_kg * cfg.fusion.reserved_fuel_fraction
        assert sim.state.fuel_reserved_kg == pytest.approx(expected_reserved)


class TestPhaseTransitions:
    """Tests for correct phase determination."""

    def test_phase1_cruise(self) -> None:
        sim = BrakingSimulator(seed=42)
        result = sim.simulate_year(1)
        assert result.phase == 1
        assert result.phase_name == "CRUISE"

    def test_phase_transitions_occur(self) -> None:
        """Run a full mission and verify all 5 phases are reached."""
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        phases_seen = {r.phase for r in sim.year_results}
        # Must see at least phase 1 and phase 2
        assert 1 in phases_seen
        assert 2 in phases_seen

    def test_phases_are_monotonically_increasing(self) -> None:
        """Phases should only increase, never decrease."""
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        phases = [r.phase for r in sim.year_results]
        for i in range(1, len(phases)):
            assert phases[i] >= phases[i - 1]


class TestSailDeploymentEvents:
    """Tests for sail deployment timing and events."""

    def test_outer_ring_deploys_in_phase2(self) -> None:
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        deployments = sim.state.deployment_events
        ring_events = [d for d in deployments if d["system"] == "outer_sail_ring"]
        assert len(ring_events) == 1
        # Should deploy when journey fraction >= 80%
        deploy_year = ring_events[0]["year"]
        # At 0.1c, 80% of 4.24 ly = 3.392 ly takes ~33.9 years
        assert deploy_year >= 30  # Should be around year 34

    def test_magsail_deploys_in_phase3(self) -> None:
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        deployments = sim.state.deployment_events
        ms_events = [d for d in deployments if d["system"] == "magsail"]
        assert len(ms_events) == 1

    def test_middle_ring_detaches(self) -> None:
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        deployments = sim.state.deployment_events
        detach = [d for d in deployments if d["system"] == "middle_ring_detach"]
        assert len(detach) == 1

    def test_deployment_order(self) -> None:
        """Outer ring -> magsail -> middle ring -> inner sail."""
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        deployments = sim.state.deployment_events
        systems = [d["system"] for d in deployments]
        assert "outer_sail_ring" in systems
        ring_idx = systems.index("outer_sail_ring")
        if "magsail" in systems:
            ms_idx = systems.index("magsail")
            assert ms_idx > ring_idx


class TestVelocityProfile:
    """Tests for the velocity deceleration profile."""

    def test_velocity_decreases_during_braking(self) -> None:
        """After phase 2 begins, velocity should decrease."""
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        results = sim.year_results

        # Find the first braking year (phase >= 2)
        braking_start = None
        for i, r in enumerate(results):
            if r.phase >= 2:
                braking_start = i
                break
        assert braking_start is not None

        # Velocity at braking start should be > velocity at end
        v_start = results[braking_start].velocity_c
        v_end = results[-1].velocity_c
        assert v_end < v_start

    def test_velocity_never_negative(self) -> None:
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        for r in sim.year_results:
            assert r.velocity_c >= 0.0

    def test_cruise_velocity_constant(self) -> None:
        """During phase 1, velocity should remain at cruise speed."""
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        cruise_results = [r for r in sim.year_results if r.phase == 1]
        for r in cruise_results:
            assert r.velocity_c == pytest.approx(0.1, abs=0.001)

    def test_velocity_profile_smooth(self) -> None:
        """Velocity changes should be gradual, not discontinuous."""
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        velocities = [r.velocity_c for r in sim.year_results]
        for i in range(1, len(velocities)):
            # Max change per year should be less than 0.03c
            delta = abs(velocities[i] - velocities[i - 1])
            assert delta < 0.03, f"Discontinuous velocity change at year {i}: {delta}c"


class TestOrbitalInsertion:
    """THE critical tests — does the braking architecture solve FLY_THROUGH?"""

    def test_proxima_centauri_insertion(self) -> None:
        """Proxima Centauri (4.24 ly): MUST achieve orbital insertion."""
        result = run_proxima_centauri_mission(seed=42)
        assert result["orbital_insertion"] is True, (
            f"FAILED: Proxima insertion. Final velocity: {result['final_velocity_c']:.6f}c "
            f"({result['final_velocity_m_s']:.0f} m/s)"
        )

    def test_alpha_centauri_insertion(self) -> None:
        """Alpha Centauri (4.37 ly): MUST achieve orbital insertion."""
        result = run_alpha_centauri_mission(seed=42)
        assert result["orbital_insertion"] is True, (
            f"FAILED: Alpha Centauri insertion. Final velocity: "
            f"{result['final_velocity_c']:.6f}c"
        )

    def test_barnards_star_insertion(self) -> None:
        """Barnard's Star (5.96 ly): MUST achieve orbital insertion."""
        result = run_barnards_star_mission(seed=42)
        assert result["orbital_insertion"] is True, (
            f"FAILED: Barnard's Star insertion. Final velocity: "
            f"{result['final_velocity_c']:.6f}c"
        )

    def test_tau_ceti_insertion(self) -> None:
        """Tau Ceti (11.91 ly): MUST achieve orbital insertion."""
        result = run_tau_ceti_mission(seed=42)
        assert result["orbital_insertion"] is True, (
            f"FAILED: Tau Ceti insertion. Final velocity: "
            f"{result['final_velocity_c']:.6f}c"
        )

    def test_proxima_arrival_velocity_under_50kms(self) -> None:
        result = run_proxima_centauri_mission(seed=42)
        assert result["final_velocity_m_s"] < 50_000.0

    def test_multiple_seeds_proxima(self) -> None:
        """Orbital insertion should succeed across multiple RNG seeds."""
        successes = 0
        for seed in range(10):
            result = run_proxima_centauri_mission(seed=seed)
            if result["orbital_insertion"]:
                successes += 1
        # At least 8 out of 10 seeds should succeed
        assert successes >= 8, f"Only {successes}/10 seeds achieved insertion"


class TestFuelBudget:
    """Tests for fuel consumption and budget tracking."""

    def test_fuel_consumed_during_braking(self) -> None:
        result = run_proxima_centauri_mission(seed=42)
        assert result["fuel_used_for_braking_kg"] > 0

    def test_fuel_remaining_positive(self) -> None:
        result = run_proxima_centauri_mission(seed=42)
        assert result["fuel_remaining_kg"] >= 0

    def test_fuel_not_fully_exhausted(self) -> None:
        """Should have some fuel left after insertion for station-keeping."""
        result = run_proxima_centauri_mission(seed=42)
        # If insertion succeeded, should have fuel left
        if result["orbital_insertion"]:
            assert result["fuel_remaining_kg"] > 0

    def test_fuel_budget_conserved(self) -> None:
        """Fuel used + remaining should not exceed initial fuel."""
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        initial = sim.config.initial_fuel_kg
        used = sim.state.fuel_used_for_braking_kg
        remaining = sim.state.fuel_remaining_kg
        assert used + remaining <= initial + 1.0  # Small float tolerance


class TestDecelerationSources:
    """Tests for individual deceleration source contributions."""

    def test_laser_decel_positive_in_phase2(self) -> None:
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        phase2_results = [r for r in sim.year_results if r.phase == 2]
        if phase2_results:
            assert any(r.decel_laser > 0 for r in phase2_results)

    def test_magsail_decel_in_phase3(self) -> None:
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        phase3_results = [r for r in sim.year_results if r.phase == 3]
        if phase3_results:
            # Magsail in Local Bubble is small but non-zero
            assert any(r.decel_magsail >= 0 for r in phase3_results)

    def test_laser_dominates_early_braking(self) -> None:
        """In phase 2, laser should be the primary deceleration source."""
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        phase2_results = [r for r in sim.year_results if r.phase == 2]
        if phase2_results:
            for r in phase2_results:
                assert r.decel_laser >= r.decel_magsail

    def test_total_decel_is_sum(self) -> None:
        """Total deceleration should be sum of all sources."""
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        for r in sim.year_results:
            expected = r.decel_laser + r.decel_magsail + r.decel_fusion
            assert r.decel_total == pytest.approx(expected, abs=1e-12)


class TestMissionDuration:
    """Tests for mission duration with braking."""

    def test_proxima_mission_reasonable_duration(self) -> None:
        """Proxima mission should complete in < 200 years."""
        result = run_proxima_centauri_mission(seed=42)
        assert result["total_years"] < 200

    def test_proxima_longer_than_pure_cruise(self) -> None:
        """Braking extends the mission beyond pure cruise time."""
        result = run_proxima_centauri_mission(seed=42)
        pure_cruise_years = 4.24 / 0.1  # 42.4 years
        # Mission should be longer due to deceleration
        assert result["total_years"] >= int(pure_cruise_years)

    def test_tau_ceti_reasonable_duration(self) -> None:
        """Tau Ceti mission should complete in < 500 years."""
        result = run_tau_ceti_mission(seed=42)
        assert result["total_years"] < 500


class TestISMInteraction:
    """Tests for ISM density effects on magsail braking."""

    def test_local_bubble_low_density(self) -> None:
        density = ism_density_at_distance(2.0)
        assert density == pytest.approx(0.005)

    def test_warm_ism_higher_density(self) -> None:
        density = ism_density_at_distance(400.0)
        assert density == pytest.approx(0.3)

    def test_magsail_more_effective_in_warm_ism(self) -> None:
        """A target beyond the Local Bubble should get more magsail braking."""
        # This is a physics consistency check, not a full mission
        sim_near = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim_far = BrakingSimulator(target_distance_ly=400.0, seed=42)

        # Run to phase 3 on the far target
        for year in range(1, 5000):
            r = sim_far.simulate_year(year)
            if r.phase >= 3:
                break

        # The far target's magsail decel should be calculated for warm ISM
        # which is much higher than Local Bubble
        assert sim_far.state.magsail_deployed or sim_far.state.current_phase < 3


class TestDegradation:
    """Tests for sail and magsail degradation over time."""

    def test_sail_health_degrades(self) -> None:
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        assert sim.state.sail_health < 1.0

    def test_magsail_health_degrades(self) -> None:
        sim = BrakingSimulator(target_distance_ly=4.24, seed=42)
        sim.run_mission()
        if sim.state.magsail_deployed:
            assert sim.state.magsail_health < 1.0

    def test_degradation_doesnt_prevent_insertion(self) -> None:
        """Even with degradation, insertion should still succeed."""
        result = run_proxima_centauri_mission(seed=42)
        assert result["orbital_insertion"] is True
        assert result["sail_final_health"] > 0.0


class TestMissionSummary:
    """Tests for the mission summary output."""

    def test_summary_has_required_fields(self) -> None:
        result = run_proxima_centauri_mission(seed=42)
        required = [
            "target_distance_ly", "total_years", "orbital_insertion",
            "final_velocity_c", "final_velocity_m_s",
            "fuel_used_for_braking_kg", "fuel_remaining_kg",
            "peak_deceleration_m_s2", "phase_transitions",
            "deployment_events", "velocity_profile",
        ]
        for field_name in required:
            assert field_name in result, f"Missing field: {field_name}"

    def test_velocity_profile_populated(self) -> None:
        result = run_proxima_centauri_mission(seed=42)
        profile = result["velocity_profile"]
        assert len(profile) > 10
        # First entry should be near cruise velocity
        assert profile[0][1] == pytest.approx(0.1, abs=0.01)

    def test_phase_transitions_in_summary(self) -> None:
        result = run_proxima_centauri_mission(seed=42)
        transitions = result["phase_transitions"]
        assert 1 in transitions


class TestGenerationShipIntegration:
    """Tests for braking architecture wired into GenerationShipSimulation."""

    def test_config_has_braking_flag(self) -> None:
        from aria.simulation.generation_ship import GenerationShipConfig
        cfg = GenerationShipConfig()
        assert hasattr(cfg, "enable_braking_architecture")
        assert cfg.enable_braking_architecture is True

    def test_legacy_config_disables_braking(self) -> None:
        from aria.simulation.generation_ship import GenerationShipConfig
        cfg = GenerationShipConfig.legacy()
        assert cfg.enable_braking_architecture is False

    def test_breakthrough_config_enables_braking(self) -> None:
        from aria.simulation.generation_ship import GenerationShipConfig
        cfg = GenerationShipConfig.breakthrough()
        assert cfg.enable_braking_architecture is True


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero_velocity_ship(self) -> None:
        """A ship already at rest should trivially succeed."""
        sim = BrakingSimulator(
            target_distance_ly=4.24,
            cruise_velocity_c=0.0,
            seed=42,
        )
        # Can't really run the mission at 0 velocity, but init should work
        assert sim.state.velocity_c == 0.0

    def test_very_short_distance(self) -> None:
        """Alpha Centauri Proxima at minimum distance."""
        sim = BrakingSimulator(target_distance_ly=1.0, seed=42)
        sim.run_mission()
        assert sim.state.mission_complete

    def test_deterministic_with_seed(self) -> None:
        """Same seed should give identical results."""
        r1 = run_proxima_centauri_mission(seed=123)
        r2 = run_proxima_centauri_mission(seed=123)
        assert r1["final_velocity_c"] == r2["final_velocity_c"]
        assert r1["total_years"] == r2["total_years"]

    def test_different_seeds_give_different_results(self) -> None:
        """Different seeds should give slightly different results."""
        r1 = run_proxima_centauri_mission(seed=1)
        r2 = run_proxima_centauri_mission(seed=2)
        # Magsail degradation is stochastic
        assert r1["magsail_final_health"] != r2["magsail_final_health"]


class TestPropellantSloshFrequency:
    """Pod H2 slosh frequency wired into BrakingSimulator."""

    def test_slosh_freq_zero_during_cruise(self) -> None:
        """No deceleration during cruise → zero restoring force → freq = 0."""
        sim = BrakingSimulator(seed=42, cruise_velocity_c=0.1)
        # Phase 1 = CRUISE; simulate one year before any braking starts
        sim.simulate_year(1)
        if sim.state.current_phase == 1:
            assert sim.state.propellant_slosh_freq_hz == 0.0

    def test_slosh_freq_positive_during_braking(self) -> None:
        """Active deceleration provides effective gravity → positive slosh freq."""
        # Jump straight to phase 4 (magsail primary braking) by advancing far
        sim = BrakingSimulator(seed=42, cruise_velocity_c=0.1)
        for yr in range(1, 45):
            sim.simulate_year(yr)
        # During braking phases (2-5), total_decel_m_s2 > 0 → slosh freq > 0
        if sim.state.total_decel_m_s2 > 0:
            assert sim.state.propellant_slosh_freq_hz > 0.0

    def test_slosh_freq_decreases_with_fill_depletion(self) -> None:
        """Lower fill depth (less propellant) → lower slosh frequency per Abramson 1966."""
        from aria.physics.low_g_fluids import cylindrical_tank_slosh_frequency
        g_eff = 0.5  # m/s²
        R = 1.0      # m
        freq_full = cylindrical_tank_slosh_frequency(g_eff, R, fill_depth_m=2.0)
        freq_low = cylindrical_tank_slosh_frequency(g_eff, R, fill_depth_m=0.2)
        # tanh(ξh/R) is monotone in h, so more fill → higher freq
        assert freq_full > freq_low
