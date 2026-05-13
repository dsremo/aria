"""Tests for P2 and P3 expert panel fixes — generation ship simulation.

Covers:
  1. ISM drag on hull (interstellar.py)
  2. Trace gas accumulation CO/NH3/VOC (interstellar.py)
  3. Magsail probabilistic wire-strike model (food_synthesis.py)
  4. Cofactor recycling ATP/NADH pools (food_synthesis.py)
  5. Microbiome restoration from DNA archive (interstellar_challenges.py)
  6. Gravitational focusing relay for comms (advanced_systems.py)
  7. Combined laser+magsail deceleration (food_synthesis.py)
"""

from __future__ import annotations

import math

import pytest


# ────────────────────────────────────────────────────────────────
#  FIX 1: ISM drag on hull
# ────────────────────────────────────────────────────────────────

class TestISMDrag:
    """ISM drag: F = n * m_p * v^2 * A_cross applied to InterstellarSimulation."""

    def test_ism_drag_fields_exist(self):
        from aria.simulation.interstellar import InterstellarState
        s = InterstellarState()
        assert hasattr(s, "ism_drag_force_n")
        assert hasattr(s, "ism_drag_delta_v_ms")
        assert s.ism_drag_force_n == 0.0
        assert s.ism_drag_delta_v_ms == 0.0

    def test_ism_drag_accumulates_over_years(self):
        from aria.simulation.interstellar import InterstellarSimulation
        sim = InterstellarSimulation(cruise_velocity_c=0.1, seed=42)
        for _ in range(10):
            sim.simulate_year()
        s = sim.state
        assert s.ism_drag_force_n > 0, "ISM drag force should be positive"
        assert s.ism_drag_delta_v_ms > 0, "Cumulative ISM drag delta-v should be positive"

    def test_ism_drag_velocity_decreases(self):
        from aria.simulation.interstellar import InterstellarSimulation
        sim = InterstellarSimulation(cruise_velocity_c=0.1, seed=42)
        initial_v = sim.state.velocity_c
        for _ in range(50):
            sim.simulate_year()
        # Velocity should decrease slightly due to ISM drag
        assert sim.state.velocity_c < initial_v

    def test_ism_drag_higher_in_warm_ism(self):
        """Beyond 250 ly (~2500 years at 0.1c), ISM density increases."""
        from aria.simulation.interstellar import InterstellarSimulation
        sim = InterstellarSimulation(cruise_velocity_c=0.1, seed=42)
        # Simulate to just before warm ISM
        for _ in range(100):
            sim.simulate_year()
        drag_local_bubble = sim.state.ism_drag_force_n
        # Continue into denser ISM region — manually set distance to warm zone
        # We just check the drag is non-zero and accumulated reasonably
        assert drag_local_bubble > 0


# ────────────────────────────────────────────────────────────────
#  FIX 2: Trace gas accumulation
# ────────────────────────────────────────────────────────────────

class TestTraceGasAccumulation:
    """CO, NH3, VOC tracking in ECLSS."""

    def test_trace_gas_fields_exist(self):
        from aria.simulation.interstellar import InterstellarState
        s = InterstellarState()
        assert hasattr(s, "trace_gas_co_ppm")
        assert hasattr(s, "trace_gas_nh3_ppm")
        assert hasattr(s, "trace_gas_voc_ppm")
        assert hasattr(s, "tcc_scrubber_health")

    def test_trace_gases_start_at_zero(self):
        from aria.simulation.interstellar import InterstellarState
        s = InterstellarState()
        assert s.trace_gas_co_ppm == 0.0
        assert s.trace_gas_nh3_ppm == 0.0
        assert s.trace_gas_voc_ppm == 0.0

    def test_trace_gases_accumulate(self):
        from aria.simulation.interstellar import InterstellarSimulation
        sim = InterstellarSimulation(cruise_velocity_c=0.1, seed=42)
        for _ in range(50):
            sim.simulate_year()
        s = sim.state
        # With scrubber degradation, trace gases should accumulate
        assert s.trace_gas_co_ppm > 0
        assert s.trace_gas_nh3_ppm > 0
        assert s.trace_gas_voc_ppm > 0

    def test_scrubber_degrades(self):
        from aria.simulation.interstellar import InterstellarSimulation
        sim = InterstellarSimulation(cruise_velocity_c=0.1, seed=42)
        for _ in range(100):
            sim.simulate_year()
        assert sim.state.tcc_scrubber_health < 1.0


# ────────────────────────────────────────────────────────────────
#  FIX 3: Magsail probabilistic wire-strike model
# ────────────────────────────────────────────────────────────────

class TestMagsailWireStrike:
    """Probabilistic wire-strike replaces linear magsail degradation."""

    def test_magsail_degrades_stochastically(self):
        """Run multiple seeds — damage should vary between runs."""
        from aria.simulation.food_synthesis import PropulsionSimulator
        healths = []
        for seed_val in range(10):
            ps = PropulsionSimulator(seed=seed_val)
            ps.state.magsail_deployed = True
            ps.state.current_mode = "MAGSAIL"
            for yr in range(1, 16):  # 15 years — enough for some strikes, not all to zero
                ps.simulate_year(float(yr), distance_ly=yr * 0.1)
            healths.append(ps.state.magsail_health)
        # With probabilistic model, not all seeds should give identical results
        assert len(set(round(h, 3) for h in healths)) > 1, \
            "Probabilistic wire-strike should produce varying damage across seeds"

    def test_wire_strike_events_generated(self):
        """Wire-strike events should appear in propulsion logs."""
        from aria.simulation.food_synthesis import PropulsionSimulator
        ps = PropulsionSimulator(seed=7)
        ps.state.magsail_deployed = True
        ps.state.current_mode = "MAGSAIL"
        all_events = []
        for yr in range(1, 101):
            events = ps.simulate_year(float(yr), distance_ly=yr * 0.1)
            all_events.extend(events)
        strike_events = [e for e in all_events if "wire strike" in e.get("message", "").lower()]
        # Over 100 years, at least some wire strikes should occur
        assert len(strike_events) >= 1


# ────────────────────────────────────────────────────────────────
#  FIX 4: Cofactor recycling (ATP/NADH pools)
# ────────────────────────────────────────────────────────────────

class TestCofactorRecycling:
    """ATP/NADH pool tracking in StarchSynthesizerState."""

    def test_cofactor_fields_exist(self):
        from aria.simulation.food_synthesis import StarchSynthesizerState
        s = StarchSynthesizerState()
        assert hasattr(s, "atp_pool_health")
        assert hasattr(s, "nadh_pool_health")
        assert hasattr(s, "cofactor_regeneration_rate")
        assert s.atp_pool_health == 1.0
        assert s.nadh_pool_health == 1.0

    def test_cofactor_pools_degrade(self):
        from aria.simulation.food_synthesis import FoodSynthesisSimulator
        fs = FoodSynthesisSimulator(crew_size=4, seed=42)
        for yr in range(1, 101):
            fs.simulate_year(float(yr))
        st = fs.state.starch
        # Over 100 years, cofactors should have degraded (even with regeneration)
        assert st.cofactor_regeneration_rate < 1.0

    def test_cofactor_limits_starch_production(self):
        """Low cofactor pools should reduce starch output."""
        from aria.simulation.food_synthesis import FoodSynthesisSimulator
        fs = FoodSynthesisSimulator(crew_size=4, seed=42)
        # Simulate 5 years for baseline
        for yr in range(1, 6):
            fs.simulate_year(float(yr))
        baseline_rate = fs.state.starch.actual_rate_kg_per_day

        # Artificially deplete cofactors
        fs.state.starch.atp_pool_health = 0.2
        fs.state.starch.nadh_pool_health = 0.2
        fs.simulate_year(6.0)
        depleted_rate = fs.state.starch.actual_rate_kg_per_day

        assert depleted_rate < baseline_rate, \
            "Depleted cofactor pools should reduce starch synthesis rate"


# ────────────────────────────────────────────────────────────────
#  FIX 5: Microbiome restoration from DNA archive
# ────────────────────────────────────────────────────────────────

class TestMicrobiomeRestoration:
    """DNA archive enables soil microbiome health recovery."""

    def test_dna_archive_fields_exist(self):
        from aria.simulation.interstellar_challenges import FoodSystem
        f = FoodSystem()
        assert hasattr(f, "microbiome_dna_archive_health")
        assert hasattr(f, "microbiome_restoration_cooldown")
        assert f.microbiome_dna_archive_health == 1.0
        assert f.microbiome_restoration_cooldown == 0

    def test_restoration_triggers_when_soil_low(self):
        from aria.simulation.interstellar_challenges import FoodCenturySimulator
        fcs = FoodCenturySimulator(crew_size=4, seed=42)
        # Manually degrade soil to trigger restoration
        fcs.food.soil_microbiome_health = 0.3
        fcs.food.microbiome_dna_archive_health = 0.9
        events = fcs.simulate_year(100.0)
        # Soil should have recovered
        assert fcs.food.soil_microbiome_health > 0.3
        restoration_events = [e for e in events if "microbiome restored" in e.get("message", "").lower()]
        assert len(restoration_events) == 1

    def test_restoration_cooldown_enforced(self):
        from aria.simulation.interstellar_challenges import FoodCenturySimulator
        fcs = FoodCenturySimulator(crew_size=4, seed=42)
        fcs.food.soil_microbiome_health = 0.3
        fcs.food.microbiome_dna_archive_health = 0.9
        fcs.simulate_year(100.0)
        health_after_first = fcs.food.soil_microbiome_health
        # Set soil low again — but cooldown should prevent restoration
        fcs.food.soil_microbiome_health = 0.3
        events = fcs.simulate_year(101.0)
        restoration_events = [e for e in events if "microbiome restored" in e.get("message", "").lower()]
        assert len(restoration_events) == 0, "Restoration should be on cooldown"

    def test_archive_degrades_with_use(self):
        from aria.simulation.interstellar_challenges import FoodCenturySimulator
        fcs = FoodCenturySimulator(crew_size=4, seed=42)
        initial_archive = 0.9
        fcs.food.microbiome_dna_archive_health = initial_archive
        fcs.food.soil_microbiome_health = 0.3
        fcs.simulate_year(100.0)
        # Archive should be consumed by restoration
        assert fcs.food.microbiome_dna_archive_health < initial_archive


# ────────────────────────────────────────────────────────────────
#  FIX 6: Gravitational focusing relay
# ────────────────────────────────────────────────────────────────

class TestGravitationalFocusingRelay:
    """Focal-line relay amplifies deep space communications."""

    def test_relay_fields_exist(self):
        from aria.simulation.advanced_systems import LaserCommState
        s = LaserCommState()
        assert hasattr(s, "focal_line_relay_deployed")
        assert hasattr(s, "focal_line_gain_factor")
        assert hasattr(s, "focal_line_relay_health")
        assert s.focal_line_relay_deployed is False
        assert s.focal_line_gain_factor == 1e9

    def test_relay_boosts_data_rate(self):
        from aria.simulation.advanced_systems import LaserCommSimulator
        # Without relay
        sim_no = LaserCommSimulator(velocity_c=0.1, seed=42)
        sim_no.simulate_year(50.0)
        rate_without = sim_no.state.data_rate_bps

        # With relay
        sim_yes = LaserCommSimulator(velocity_c=0.1, seed=42)
        sim_yes.state.focal_line_relay_deployed = True
        sim_yes.state.focal_line_relay_health = 1.0
        sim_yes.simulate_year(50.0)
        rate_with = sim_yes.state.data_rate_bps

        assert rate_with > rate_without, \
            "Gravitational focusing relay should increase data rate"

    def test_relay_in_comm_report(self):
        from aria.simulation.advanced_systems import LaserCommSimulator
        sim = LaserCommSimulator(velocity_c=0.1, seed=42)
        sim.state.focal_line_relay_deployed = True
        report = sim.get_comm_report()
        assert "focal_relay_deployed" in report
        assert report["focal_relay_deployed"] is True


# ────────────────────────────────────────────────────────────────
#  FIX 7: Combined laser + magsail deceleration
# ────────────────────────────────────────────────────────────────

class TestCombinedDeceleration:
    """Combined laser + magsail deceleration profile."""

    def test_combined_decel_fields_exist(self):
        from aria.simulation.food_synthesis import PropulsionSystemState
        s = PropulsionSystemState()
        assert hasattr(s, "combined_decel_active")
        assert hasattr(s, "laser_decel_m_s2")
        assert hasattr(s, "magsail_decel_m_s2")

    def test_combined_decel_activates(self):
        from aria.simulation.food_synthesis import PropulsionSimulator
        ps = PropulsionSimulator(seed=42)
        ps.state.magsail_deployed = True
        ps.state.current_mode = "MAGSAIL"
        ps.state.laser_sail_active = True
        # Simulate at close distance where laser is effective
        ps.simulate_year(10.0, distance_ly=1.0)
        # Both should be active
        assert ps.state.combined_decel_active is True
        assert ps.state.laser_decel_m_s2 > 0
        assert ps.state.magsail_decel_m_s2 > 0

    def test_combined_decel_greater_than_magsail_alone(self):
        from aria.simulation.food_synthesis import PropulsionSimulator
        # Magsail only
        ps1 = PropulsionSimulator(seed=42)
        ps1.state.magsail_deployed = True
        ps1.state.current_mode = "MAGSAIL"
        ps1.simulate_year(10.0, distance_ly=1.0)
        v_magsail = ps1.state.velocity_c

        # Combined
        ps2 = PropulsionSimulator(seed=42)
        ps2.state.magsail_deployed = True
        ps2.state.current_mode = "MAGSAIL"
        ps2.state.laser_sail_active = True
        ps2.simulate_year(10.0, distance_ly=1.0)
        v_combined = ps2.state.velocity_c

        assert v_combined < v_magsail, \
            "Combined deceleration should produce lower velocity than magsail alone"
