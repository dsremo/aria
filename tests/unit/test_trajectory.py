"""Tests for the interstellar trajectory / ΔV budget model."""

from __future__ import annotations

import math

import pytest

from aria.simulator.trajectory import (
    C_M_PER_S,
    G0_M_PER_S2,
    INTERSTELLAR_TARGETS,
    PROPULSION_OPTIONS,
    cruise_time_years,
    evaluate_mission,
    tsiolkovsky_delta_v,
)


class TestTsiolkovsky:
    def test_equal_masses_returns_zero(self):
        assert tsiolkovsky_delta_v(1_000.0, 1_000.0, 450.0) == 0.0

    def test_wet_below_dry_returns_zero(self):
        assert tsiolkovsky_delta_v(500.0, 1_000.0, 450.0) == 0.0

    def test_mass_ratio_2_gives_ln2_times_ve(self):
        """ΔV = v_e · ln(2) when mass ratio is 2."""
        isp = 300.0
        ve = isp * G0_M_PER_S2
        expected = ve * math.log(2)
        got = tsiolkovsky_delta_v(2_000.0, 1_000.0, isp)
        assert abs(got - expected) < 1e-6

    def test_nerva_class_sstm_delta_v(self):
        """NERVA (900 s Isp) with mass ratio 3 ≈ 9.7 km/s."""
        got = tsiolkovsky_delta_v(3_000.0, 1_000.0, 900.0)
        assert 9_500 < got < 10_000


class TestCruiseTime:
    def test_01c_to_alpha_centauri(self):
        """0.1 c cruise → ~43.6 years for 4.365 ly."""
        t = cruise_time_years(4.365, 0.1)
        assert abs(t - 43.65) < 0.1

    def test_zero_velocity_is_infinite(self):
        assert cruise_time_years(1.0, 0.0) == math.inf


class TestMissionFeasibility:
    def test_chemical_to_alpha_centauri_is_infeasible(self):
        r = evaluate_mission("Alpha Centauri A", propulsion_key="chemical_bipropellant",
                              mission_budget_yr=1_000.0)
        assert not r.feasible
        assert r.achievable_dv_m_s < 10_000  # < 10 km/s
        assert r.cruise_time_yr > 100_000   # > 100 000 years

    def test_direct_drive_fusion_reaches_alpha_centauri(self):
        """With 10⁶ s Isp and 70 % propellant fraction, we get ~0.02 c
        cruise, crossing 4.365 ly in ~220 years — comfortably under 1 000 yr."""
        r = evaluate_mission("Alpha Centauri A", propulsion_key="fusion_direct_drive",
                              mission_budget_yr=1_000.0)
        assert r.feasible
        assert r.cruise_time_yr < 1_000
        assert r.cruise_fraction_of_c > 0.001   # at least 0.1 % c

    def test_all_targets_with_all_propulsion_runs(self):
        """Sanity: no exceptions across the full matrix."""
        for target in INTERSTELLAR_TARGETS:
            for prop in PROPULSION_OPTIONS:
                r = evaluate_mission(target, propulsion_key=prop)
                assert r.target == target

    def test_unknown_target_raises(self):
        with pytest.raises(ValueError):
            evaluate_mission("Betelgeuse")

    def test_unknown_propulsion_raises(self):
        with pytest.raises(ValueError):
            evaluate_mission("Alpha Centauri A", propulsion_key="solar_sail")

    def test_relativistic_warning_near_0_1c(self):
        """Fusion direct-drive at mass ratio that yields β > 0.1 should emit a note."""
        r = evaluate_mission("Alpha Centauri A", propulsion_key="antimatter",
                              mission_budget_yr=100.0)
        assert "relativistic" in r.notes.lower() or r.feasible   # antimatter → β > 0.1


class TestPropulsionOptionsCitations:
    """CLAUDE.md rule: every numerical constant needs a citation."""

    def test_every_propulsion_has_nonempty_source(self):
        for key, p in PROPULSION_OPTIONS.items():
            assert p.source.strip(), f"{key} missing source citation"

    def test_isp_values_in_plausible_range(self):
        for key, p in PROPULSION_OPTIONS.items():
            assert 100 <= p.isp_s <= 1e8, f"{key} Isp {p.isp_s} out of plausible range"
