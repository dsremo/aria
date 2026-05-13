"""Tests for the Magsail PIC interaction model."""

import math

from aria.simulation.magsail_pic import (
    MagsailPICSimulator,
    MagsailState,
    ISM_PHASES,
    C_LIGHT,
    MU_0,
)


class TestMagsailInit:
    def test_creates(self):
        sim = MagsailPICSimulator(seed=42)
        assert sim.state.loop_radius_m == 50_000.0

    def test_magnetic_moment_computed(self):
        sim = MagsailPICSimulator(loop_radius_m=50_000, current_a=1e9, seed=42)
        expected = 1e9 * math.pi * 50_000 ** 2
        assert abs(sim.state.magnetic_moment_am2 - expected) < 1e10

    def test_derived_quantities(self):
        sim = MagsailPICSimulator(seed=42)
        assert sim.state.magnetopause_radius_m > 0
        assert sim.state.effective_area_m2 > 0
        assert sim.state.drag_force_n > 0


class TestMagnetopause:
    def test_radius_scales_with_current(self):
        """Higher current → larger magnetopause → more drag."""
        sim_low = MagsailPICSimulator(current_a=1e8, seed=42)
        sim_high = MagsailPICSimulator(current_a=1e10, seed=42)
        sim_low._update_derived(0.1 * C_LIGHT)
        sim_high._update_derived(0.1 * C_LIGHT)
        assert sim_high.state.magnetopause_radius_m > sim_low.state.magnetopause_radius_m

    def test_radius_decreases_with_velocity(self):
        """Higher velocity → more ram pressure → compressed magnetopause."""
        sim = MagsailPICSimulator(seed=42)
        sim._update_derived(0.05 * C_LIGHT)
        r_slow = sim.state.magnetopause_radius_m
        sim._update_derived(0.2 * C_LIGHT)
        r_fast = sim.state.magnetopause_radius_m
        assert r_slow > r_fast

    def test_drag_increases_with_density(self):
        sim = MagsailPICSimulator(seed=42)
        sim.set_ism_phase("local_bubble")
        sim._update_derived(0.1 * C_LIGHT)
        f_low = sim.state.drag_force_n
        sim.set_ism_phase("warm_ionized")
        sim._update_derived(0.1 * C_LIGHT)
        f_high = sim.state.drag_force_n
        assert f_high > f_low


class TestISMPhases:
    def test_all_phases_exist(self):
        assert len(ISM_PHASES) == 5

    def test_set_ism_phase(self):
        sim = MagsailPICSimulator(seed=42)
        sim.set_ism_phase("cold_neutral")
        assert sim.state.ism_density_cm3 == 30.0
        assert sim.state.ism_ionization == 0.001

    def test_invalid_phase_no_crash(self):
        sim = MagsailPICSimulator(seed=42)
        sim.set_ism_phase("nonexistent")
        # Should not crash, state unchanged
        assert sim.state.ism_phase != "nonexistent"


class TestPICSnapshot:
    def test_pic_runs(self):
        sim = MagsailPICSimulator(seed=42)
        result = sim.run_pic_snapshot(0.01 * C_LIGHT, n_particles=50)
        assert result["n_particles"] == 50
        assert "deflected" in result
        assert "drag_force_n" in result

    def test_deflection_fraction_bounded(self):
        sim = MagsailPICSimulator(seed=42)
        result = sim.run_pic_snapshot(0.05 * C_LIGHT, n_particles=100)
        assert 0.0 <= result["deflection_fraction"] <= 1.0


class TestSimulateYear:
    def test_returns_events(self):
        sim = MagsailPICSimulator(seed=42)
        events = sim.simulate_year(1.0, velocity_c=0.1)
        assert isinstance(events, list)
        assert len(events) > 0

    def test_events_have_subsystem(self):
        sim = MagsailPICSimulator(seed=42)
        events = sim.simulate_year(1.0, velocity_c=0.1)
        for e in events:
            assert e["subsystem"] == "magsail"

    def test_coil_degrades(self):
        sim = MagsailPICSimulator(seed=42)
        for yr in range(1, 100):
            sim.simulate_year(float(yr), velocity_c=0.1)
        assert sim.state.coil_health < 1.0

    def test_deterministic_with_seed(self):
        sim1 = MagsailPICSimulator(seed=42)
        e1 = sim1.simulate_year(1.0)
        sim2 = MagsailPICSimulator(seed=42)
        e2 = sim2.simulate_year(1.0)
        assert len(e1) == len(e2)


class TestReport:
    def test_report_keys(self):
        sim = MagsailPICSimulator(seed=42)
        report = sim.get_report()
        assert "magnetic_moment_am2" in report
        assert "magnetopause_radius_km" in report
        assert "drag_force_n" in report
        assert "coil_health" in report
