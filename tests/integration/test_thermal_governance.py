"""Tests for thermal management and governance systems."""

import math
import pytest

from aria.simulation.thermal_management import (
    RadiatorPanel, ThermalManagementSimulator, STEFAN_BOLTZMANN,
)
from aria.simulation.governance import GovernanceSimulator


class TestRadiatorPhysics:
    def test_stefan_boltzmann_rejection(self) -> None:
        p = RadiatorPanel(panel_id=0, area_m2=50.0, temperature_k=500.0, emissivity=0.9)
        expected = 0.9 * STEFAN_BOLTZMANN * 50.0 * 500.0**4
        assert abs(p.rejection_watts - expected) < 1

    def test_higher_temp_more_rejection(self) -> None:
        p1 = RadiatorPanel(panel_id=0, temperature_k=300.0)
        p2 = RadiatorPanel(panel_id=1, temperature_k=500.0)
        assert p2.rejection_watts > p1.rejection_watts

    def test_damaged_panel_less_rejection(self) -> None:
        p = RadiatorPanel(panel_id=0, health=0.5)
        full = RadiatorPanel(panel_id=1, health=1.0)
        assert p.rejection_watts < full.rejection_watts

    def test_dead_panel_zero_rejection(self) -> None:
        p = RadiatorPanel(panel_id=0, health=0.0)
        assert p.rejection_watts == 0.0

    def test_fin_efficiency_reduces_rejection_when_opted_in(self) -> None:
        """use_fin_efficiency=True applies the Gardner 1945 derating
        via the Phase-4 thermal_radiator bridge. For a 0.1 m × 10 mm
        Al fin at 500 K the derating is ~13 %."""
        iso = RadiatorPanel(
            panel_id=0,
            area_m2=100.0,
            temperature_k=500.0,
            fin_length_m=0.1,
            use_fin_efficiency=False,
        )
        finned = RadiatorPanel(
            panel_id=1,
            area_m2=100.0,
            temperature_k=500.0,
            fin_length_m=0.1,
            use_fin_efficiency=True,
        )
        assert finned.rejection_watts < iso.rejection_watts
        assert finned.rejection_watts > 0.8 * iso.rejection_watts

    def test_cmb_sink_barely_affects_hot_panel(self) -> None:
        """T_sink⁴ correction at 500 K is ppb-level — the bridge
        routes through the Phase-4 radiator module."""
        from aria.physics.thermal_radiator import CMB_TEMPERATURE_K
        no_sink = RadiatorPanel(
            panel_id=0, area_m2=50.0, temperature_k=500.0, sink_temperature_k=0.0
        )
        cmb = RadiatorPanel(
            panel_id=1,
            area_m2=50.0,
            temperature_k=500.0,
            sink_temperature_k=CMB_TEMPERATURE_K,
        )
        rel = abs(no_sink.rejection_watts - cmb.rejection_watts) / no_sink.rejection_watts
        assert rel < 1.0e-8


class TestThermalSimulator:
    def test_initial_thermal_balance(self) -> None:
        """100 panels × 500 m² at 500 K rejects ~142 MW, matching 140 MW waste."""
        sim = ThermalManagementSimulator(num_panels=100, seed=42)
        assert sim.state.thermal_margin_w > 0  # Initially balanced

    def test_panels_degrade_over_time(self) -> None:
        """Panels degrade from micrometeorite impacts and coating loss, but
        are continuously refurbished by crew EVA (ISS ORU model). Confirm
        the wear-and-repair loop is active: either impact damage events were
        logged, or spares were consumed, or coolant-loop health has drifted."""
        sim = ThermalManagementSimulator(num_panels=100, seed=42)
        all_events: list[dict] = []
        for yr in range(1, 101):
            all_events.extend(sim.simulate_year(float(yr)))
        wear_evidence = (
            any("damaged" in e.get("message", "") for e in all_events)
            or sim.state.spare_panels_available < 20
            or sim.state.coolant_loop_health < 1.0
            or sim.state.pump_health < 1.0
        )
        assert wear_evidence

    def test_overheating_with_few_panels(self) -> None:
        sim = ThermalManagementSimulator(num_panels=3, seed=42)
        events = sim.simulate_year(1.0)
        # 3 panels can't reject 140 MW — should overheat
        critical = [e for e in events if e.get("severity") == "CRITICAL"]
        assert len(critical) > 0

    def test_cabin_temp_stays_normal(self) -> None:
        sim = ThermalManagementSimulator(num_panels=100, seed=42)
        sim.simulate_year(1.0)
        assert 15 < sim.state.cabin_temp_c < 30

    def test_thermal_report(self) -> None:
        sim = ThermalManagementSimulator(num_panels=100, seed=42)
        sim.simulate_year(1.0)
        report = sim.get_thermal_report()
        assert "heat_generated_mw" in report
        assert "heat_rejected_mw" in report
        assert "thermal_margin_kw" in report

    def test_140mw_needs_large_radiator(self) -> None:
        """Verify Stefan-Boltzmann: 140 MW at 500 K, ε=0.9 → ~49,400 m²."""
        area_needed = 140e6 / (0.9 * STEFAN_BOLTZMANN * 500**4)
        assert 40_000 < area_needed < 50_000  # ~43,893 m²


class TestGovernance:
    def test_initial_state(self) -> None:
        gov = GovernanceSimulator(crew_size=100, seed=42)
        assert gov.state.trust_in_government == 0.8
        assert gov.state.freedom_index == 0.9

    def test_elections_happen(self) -> None:
        gov = GovernanceSimulator(crew_size=100, seed=42)
        for yr in range(1, 11):
            gov.simulate_year(float(yr))
        assert gov.state.council_election_year > 0

    def test_consent_decays_across_generations(self) -> None:
        gov = GovernanceSimulator(crew_size=100, seed=42)
        for yr in range(1, 101):
            gov.simulate_year(float(yr))
        assert gov.state.generation_consent_score < 1.0

    def test_crime_occurs(self) -> None:
        gov = GovernanceSimulator(crew_size=100, seed=42)
        for yr in range(1, 51):
            gov.simulate_year(float(yr))
        assert gov.state.crimes_total > 0

    def test_leadership_transitions(self) -> None:
        gov = GovernanceSimulator(crew_size=100, seed=42)
        for yr in range(1, 101):
            gov.simulate_year(float(yr))
        assert gov.state.leadership_transitions > 0

    def test_governance_report(self) -> None:
        gov = GovernanceSimulator(crew_size=100, seed=42)
        gov.simulate_year(1.0)
        report = gov.get_governance_report()
        assert "trust" in report
        assert "voter_participation" in report

    def test_no_authoritarianism(self) -> None:
        gov = GovernanceSimulator(crew_size=100, seed=42)
        for yr in range(1, 201):
            gov.simulate_year(float(yr))
        assert gov.state.freedom_index > 0.3
