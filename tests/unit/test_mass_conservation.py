"""Tests for element-balance mass conservation ledger."""

from aria.simulation.mass_conservation import (
    MassConservationSimulator,
    MassLedger,
    BVAD_O2_CONSUMED,
    BVAD_CO2_PRODUCED,
)


class TestMassLedger:
    def test_initial_mass_positive(self):
        sim = MassConservationSimulator(crew_size=1000, seed=42)
        assert sim.state.total_mass_initial_kg > 0

    def test_initial_closure_100_pct(self):
        sim = MassConservationSimulator(seed=42)
        assert sim.state.mass_closure_pct == 100.0

    def test_bvad_o2_realistic(self):
        assert 0.8 < BVAD_O2_CONSUMED < 0.9  # NASA BVAD: 0.84 kg/day

    def test_bvad_co2_realistic(self):
        assert 0.9 < BVAD_CO2_PRODUCED < 1.1  # NASA BVAD: ~1.0 kg/day


class TestYearlySimulation:
    def test_mass_decreases_over_time(self):
        """Some mass is always lost to leaks + CH4 venting."""
        sim = MassConservationSimulator(crew_size=100, seed=42)
        sim.simulate_year(1.0)
        assert sim.state.total_mass_current_kg < sim.state.total_mass_initial_kg

    def test_closure_stays_above_70_for_short_mission(self):
        """Mass loss over 10 years is limited (hull leak + recycling losses)."""
        sim = MassConservationSimulator(crew_size=100, seed=42)
        for yr in range(1, 11):
            sim.simulate_year(float(yr))
        assert sim.state.mass_closure_pct > 70.0

    def test_o2_stays_positive(self):
        sim = MassConservationSimulator(crew_size=100, seed=42)
        for yr in range(1, 51):
            sim.simulate_year(float(yr))
        assert sim.state.o2_kg > 0

    def test_n2_decreases_after_makeup_depleted(self):
        """Once makeup gas runs out, N2 drops from hull leaks."""
        sim = MassConservationSimulator(crew_size=1000, seed=42)
        for yr in range(1, 150):  # Makeup depletes around year 68
            sim.simulate_year(float(yr))
        assert sim.state.makeup_gas_reserve_kg == 0
        initial_n2_after_depletion = sim.state.n2_kg
        for yr in range(150, 160):
            sim.simulate_year(float(yr))
        assert sim.state.n2_kg < initial_n2_after_depletion

    def test_hull_leak_tracked(self):
        sim = MassConservationSimulator(crew_size=100, seed=42)
        sim.simulate_year(1.0)
        assert sim.state.total_leaked_kg > 0

    def test_ch4_vented(self):
        sim = MassConservationSimulator(crew_size=100, seed=42)
        for yr in range(1, 11):
            sim.simulate_year(float(yr))
        assert sim.state.total_vented_ch4_kg > 0

    def test_makeup_gas_depletes(self):
        """Over centuries, makeup gas should run out."""
        sim = MassConservationSimulator(crew_size=1000, seed=42)
        for yr in range(1, 200):
            sim.simulate_year(float(yr))
        # 50,000 kg makeup / (2 kg/day × 365) = ~68 years to depletion
        assert sim.state.makeup_gas_reserve_kg == 0

    def test_critical_alert_on_low_mass_closure(self):
        """Should alert when mass drops below 95%."""
        sim = MassConservationSimulator(crew_size=1000, seed=42)
        events_all = []
        for yr in range(1, 500):
            events_all.extend(sim.simulate_year(float(yr)))
        critical = [e for e in events_all if e["severity"] == "CRITICAL"]
        assert len(critical) > 0


class TestReport:
    def test_report_keys(self):
        sim = MassConservationSimulator(seed=42)
        sim.simulate_year(1.0)
        report = sim.get_report()
        assert "o2_kg" in report
        assert "mass_closure_pct" in report
        assert "total_leaked_kg" in report

    def test_deterministic(self):
        sim1 = MassConservationSimulator(crew_size=100, seed=42)
        sim1.simulate_year(1.0)
        sim2 = MassConservationSimulator(crew_size=100, seed=42)
        sim2.simulate_year(1.0)
        assert sim1.state.o2_kg == sim2.state.o2_kg
