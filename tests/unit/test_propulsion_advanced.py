"""Tests for propulsion_advanced.py — NTP, ion, fusion propulsion.

References:
  Borowski (2012) NASA/TM-2012-217772 — NERVA/NTP
  Patterson (2007) AIAA-2007-5199 — NEXT-C ion engine
  Cassibry (2015) — fusion propulsion concepts
"""

import math
import pytest

from aria.simulation.propulsion_advanced import (
    G0, ENGINES,
    PropulsionResult, LowThrustTransfer, MissionComparison,
    tsiolkovsky, engine_burn, low_thrust_transfer,
    compare_engines_for_mission, mars_propulsion_comparison,
    interstellar_precursor_comparison,
)


class TestTsiolkovsky:

    def test_mass_conservation(self):
        r = tsiolkovsky(3000.0, 10_000.0, 450.0)
        assert r.initial_mass_kg == pytest.approx(r.payload_kg + r.propellant_kg, rel=1e-9)

    def test_mass_ratio_formula(self):
        r = tsiolkovsky(3000.0, 10_000.0, 450.0)
        expected = math.exp(3000.0 / (450.0 * G0))
        assert r.mass_ratio == pytest.approx(expected, rel=1e-9)

    def test_higher_isp_less_propellant(self):
        r1 = tsiolkovsky(5000.0, 1000.0, 300.0)
        r2 = tsiolkovsky(5000.0, 1000.0, 3000.0)
        assert r2.propellant_kg < r1.propellant_kg

    def test_higher_dv_more_propellant(self):
        r1 = tsiolkovsky(1000.0, 1000.0, 450.0)
        r2 = tsiolkovsky(5000.0, 1000.0, 450.0)
        assert r2.propellant_kg > r1.propellant_kg

    def test_zero_dv_no_propellant(self):
        r = tsiolkovsky(0.0, 1000.0, 450.0)
        assert r.propellant_kg == pytest.approx(0.0, abs=0.001)
        assert r.mass_ratio == pytest.approx(1.0)

    def test_exhaust_velocity(self):
        r = tsiolkovsky(1000.0, 100.0, 450.0)
        assert r.exhaust_velocity_ms == pytest.approx(450.0 * G0, rel=1e-9)


class TestEngineBurn:

    def test_nerva_exists(self):
        r = engine_burn("nerva", 3000.0, 10_000.0)
        assert r.engine_name == "NERVA XE-Prime"
        assert r.isp_s == 825.0

    def test_burn_time_positive(self):
        r = engine_burn("nerva", 3000.0, 10_000.0)
        assert r.burn_time_s > 0

    def test_unknown_engine_raises(self):
        with pytest.raises(ValueError):
            engine_burn("warp_drive", 1000.0, 100.0)

    def test_draco_higher_isp_than_nerva(self):
        """DRACO (2025+ design) should have higher Isp than 1960s NERVA."""
        n = engine_burn("nerva", 5000.0, 1000.0)
        d = engine_burn("draco", 5000.0, 1000.0)
        assert d.propellant_kg < n.propellant_kg

    def test_ion_engine_very_long_burn(self):
        """Ion engines burn for months/years due to low thrust."""
        r = engine_burn("next_c", 5000.0, 1000.0)
        assert r.burn_time_s > 86400 * 30  # more than a month


class TestLowThrustTransfer:

    def test_spiral_dv_higher_than_impulsive(self):
        lt = low_thrust_transfer("next_c", 3000.0, 1000.0)
        assert lt.dv_spiral_ms > lt.dv_impulsive_ms

    def test_gravity_loss_factor(self):
        lt = low_thrust_transfer("next_c", 3000.0, 1000.0, gravity_loss_factor=1.41)
        assert lt.dv_spiral_ms == pytest.approx(3000.0 * 1.41)

    def test_burn_time_in_days(self):
        lt = low_thrust_transfer("next_c", 3000.0, 1000.0)
        assert lt.burn_time_days > 0

    def test_power_required_positive(self):
        lt = low_thrust_transfer("next_c", 3000.0, 1000.0)
        assert lt.power_required_kw > 0


class TestMissionComparisons:

    def test_mars_comparison_returns_results(self):
        comp = mars_propulsion_comparison()
        assert isinstance(comp, MissionComparison)
        assert len(comp.results) >= 4

    def test_fusion_least_propellant_for_mars(self):
        """Fusion drive should need the least propellant for Mars."""
        comp = mars_propulsion_comparison()
        fusion = [r for r in comp.results if "fusion" in r.engine_type]
        chemical = [r for r in comp.results if "chemical" in r.engine_type]
        if fusion and chemical:
            assert fusion[0].propellant_kg < chemical[0].propellant_kg

    def test_ntp_less_than_chemical_for_mars(self):
        """NTP should need less propellant than chemical for Mars."""
        comp = mars_propulsion_comparison()
        by_type = {}
        for r in comp.results:
            by_type[r.engine_type] = r
        if "ntp" in by_type and "chemical_lox_lh2" in by_type:
            assert by_type["ntp"].propellant_kg < by_type["chemical_lox_lh2"].propellant_kg

    def test_interstellar_chemical_infeasible(self):
        """Chemical/NTP cannot reach 100 km/s (mass ratio > 1000)."""
        comp = interstellar_precursor_comparison()
        ntp_results = [r for r in comp.results if r.engine_type == "ntp"]
        for r in ntp_results:
            assert r.mass_ratio > 1000, (
                f"NTP at 100 km/s should be infeasible, got ratio {r.mass_ratio:.0f}"
            )

    def test_ion_feasible_for_interstellar_precursor(self):
        """Ion drives CAN reach 100 km/s (mass ratio < 100)."""
        comp = interstellar_precursor_comparison()
        ion = [r for r in comp.results if "ion" in r.engine_type or "plasma" in r.engine_type]
        for r in ion:
            assert r.mass_ratio < 100


class TestEngineDatabase:

    def test_all_engines_have_required_fields(self):
        required = {"name", "type", "isp_s", "thrust_n", "mass_kg", "propellant", "source"}
        for key, eng in ENGINES.items():
            for field in required:
                assert field in eng, f"Engine {key} missing field {field}"

    def test_all_isp_positive(self):
        for key, eng in ENGINES.items():
            assert eng["isp_s"] > 0, f"Engine {key} has non-positive Isp"

    def test_isp_ordering(self):
        """Chemical < NTP < Ion < Fusion for Isp."""
        chem = ENGINES["rl10b2"]["isp_s"]
        ntp = ENGINES["nerva"]["isp_s"]
        ion = ENGINES["next_c"]["isp_s"]
        fusion = ENGINES["icf_dthe3"]["isp_s"]
        assert chem < ntp < ion < fusion
