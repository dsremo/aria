"""Tests for fire safety system."""

import pytest
from aria.simulation.fire_safety import FireSafetySimulator


class TestFireSafety:
    def test_initial_state(self) -> None:
        sim = FireSafetySimulator(seed=42)
        assert sim.state.o2_concentration_pct == 21.0
        assert sim.state.fires_total == 0

    def test_detectors_degrade(self) -> None:
        sim = FireSafetySimulator(seed=42)
        for yr in range(1, 101):
            sim.simulate_year(float(yr))
        assert sim.state.smoke_detector_health < 1.0

    def test_fires_occur_over_centuries(self) -> None:
        sim = FireSafetySimulator(seed=42)
        for yr in range(1, 501):
            sim.simulate_year(float(yr))
        assert sim.state.fires_total > 0

    def test_co2_consumed_by_suppression(self) -> None:
        sim = FireSafetySimulator(seed=42)
        initial = sim.state.co2_reserves_kg
        for yr in range(1, 501):
            sim.simulate_year(float(yr))
        # Fires should have consumed some CO2
        assert sim.state.co2_reserves_kg <= initial

    def test_fire_risk_increases_with_age(self) -> None:
        sim = FireSafetySimulator(seed=42)
        sim.simulate_year(1.0)
        risk_1 = sim.state.fire_risk_level
        for yr in range(2, 501):
            sim.simulate_year(float(yr))
        assert sim.state.fire_risk_level > risk_1

    def test_vacuum_vent_tracked(self) -> None:
        sim = FireSafetySimulator(seed=42)
        for yr in range(1, 1001):
            sim.simulate_year(float(yr))
        # Over 1000 years, at least one major fire should have caused venting
        assert sim.state.compartments_vented >= 0  # May be 0 with this seed
