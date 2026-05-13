"""Tests for the spacecraft simulator and fault injector."""

import numpy as np
import pytest

from aria.dsremo.simulate.spacecraft import SpacecraftSimulator
from aria.dsremo.simulate.injector import SCENARIOS, apply_scenario, list_scenarios


class TestSpacecraftSimulator:
    def test_generates_all_subsystems(self, simulator):
        points = simulator.generate_tick()
        subsystems = {p.subsystem for p in points}
        assert subsystems == {"eps", "adcs", "thermal", "comms"}

    def test_generates_expected_parameters(self, simulator):
        points = simulator.generate_tick()
        params = {p.parameter for p in points}
        assert "battery_voltage" in params
        assert "wheel_speed_x" in params
        assert "panel_temp_sun" in params
        assert "signal_strength" in params

    def test_battery_voltage_in_range(self, simulator):
        for _ in range(100):
            points = simulator.generate_tick()
            battery_points = [p for p in points if p.parameter == "battery_voltage"]
            for p in battery_points:
                assert 4.0 <= p.value <= 10.0, f"battery_voltage out of range: {p.value}"

    def test_orbital_phase_progresses(self, simulator):
        phase_start = simulator.orbital_phase
        for _ in range(100):
            simulator.generate_tick()
        phase_end = simulator.orbital_phase
        assert phase_end != phase_start

    def test_eclipse_cycle(self, simulator):
        sun_states = []
        for _ in range(5400):  # one full orbit at 1Hz
            simulator.generate_tick()
            sun_states.append(simulator.in_sunlight)
        # Should have both sunlight and eclipse
        assert True in sun_states
        assert False in sun_states

    def test_deterministic_with_seed(self):
        sim1 = SpacecraftSimulator(seed=123)
        sim2 = SpacecraftSimulator(seed=123)
        points1 = sim1.generate_tick()
        points2 = sim2.generate_tick()
        for p1, p2 in zip(points1, points2):
            assert p1.value == p2.value

    def test_fault_injection_changes_values(self, simulator):
        # Generate baseline
        baseline = {}
        for _ in range(50):
            for p in simulator.generate_tick():
                if p.parameter == "battery_voltage":
                    baseline.setdefault("battery_voltage", []).append(p.value)

        # Inject fault
        simulator.inject_fault("drift", "eps", "battery_voltage", 0.8, 100)

        # Generate with fault
        faulted = {}
        for _ in range(50):
            for p in simulator.generate_tick():
                if p.parameter == "battery_voltage":
                    faulted.setdefault("battery_voltage", []).append(p.value)

        # Faulted values should diverge from baseline
        assert np.mean(faulted["battery_voltage"]) != pytest.approx(
            np.mean(baseline["battery_voltage"]), abs=0.1
        )

    def test_satellite_id_matches(self, simulator):
        points = simulator.generate_tick()
        for p in points:
            assert p.satellite_id == "TEST-SAT-01"


class TestFaultInjector:
    def test_all_scenarios_exist(self):
        names = list(SCENARIOS.keys())
        assert "battery_degradation" in names
        assert "reaction_wheel_friction" in names
        assert "thermal_runaway" in names
        assert "solar_panel_failure" in names
        assert "sensor_spike" in names
        assert "comms_degradation" in names

    def test_apply_scenario(self):
        sim = SpacecraftSimulator(seed=42)
        scenario = apply_scenario(sim, "battery_degradation")
        assert scenario.name == "battery_degradation"
        assert len(sim._active_faults) > 0

    def test_apply_unknown_scenario(self):
        sim = SpacecraftSimulator(seed=42)
        with pytest.raises(KeyError):
            apply_scenario(sim, "nonexistent_scenario")

    def test_list_scenarios(self):
        scenarios = list_scenarios()
        assert len(scenarios) >= 6
        for s in scenarios:
            assert "name" in s
            assert "description" in s
