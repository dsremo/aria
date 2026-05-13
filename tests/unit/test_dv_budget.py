"""Tests for dv_budget.py — Delta-V budget tool.

Coverage:
  - Hohmann transfer ΔV: Earth-Mars, inner/outer planets
  - Planet departure/arrival ΔV: Oberth effect
  - Mission budgets: Moon, Mars, Jupiter
  - Propellant calculator: Tsiolkovsky, mass conservation
  - Solar system ΔV map: ordering, completeness

References:
  Wertz "SMAD" Table 6-4; Vallado 4th ed Table 6-3.
"""

import math
import pytest

from aria.simulation.dv_budget import (
    G0, MU_SUN, AU_M, PLANETS,
    DVPhase, DVBudget,
    hohmann_dv, hohmann_transfer_time,
    planet_departure_dv, planet_arrival_dv,
    moon_mission_budget, mars_mission_budget, jupiter_mission_budget,
    custom_mission_budget, compute_propellant, solar_system_dv_map,
)


class TestHohmannDV:

    def test_earth_mars_helio_dv(self):
        """Earth-Mars Hohmann heliocentric ΔVs should be ~2.9 + 2.6 km/s."""
        dep, arr = hohmann_dv(1.0, 1.524)
        assert 2500 < dep < 3500, f"Departure {dep:.0f} m/s"
        assert 2000 < arr < 3200, f"Arrival {arr:.0f} m/s"

    def test_outward_transfer_positive(self):
        dep, arr = hohmann_dv(1.0, 5.203)
        assert dep > 0 and arr > 0

    def test_inner_transfer_positive(self):
        dep, arr = hohmann_dv(1.0, 0.723)
        assert dep > 0 and arr > 0

    def test_symmetric_dvs(self):
        """Helio ΔV for A→B departure should equal B→A arrival (reversed)."""
        dep_ab, arr_ab = hohmann_dv(1.0, 1.524)
        dep_ba, arr_ba = hohmann_dv(1.524, 1.0)
        assert dep_ab == pytest.approx(arr_ba, rel=0.01)
        assert arr_ab == pytest.approx(dep_ba, rel=0.01)


class TestHohmannTransferTime:

    def test_earth_mars_time(self):
        """Earth-Mars Hohmann transit should be ~259 days."""
        t = hohmann_transfer_time(1.0, 1.524) / 86400.0
        assert 240 < t < 280

    def test_outer_planet_longer(self):
        """Jupiter transfer should be longer than Mars."""
        t_mars = hohmann_transfer_time(1.0, 1.524)
        t_jupiter = hohmann_transfer_time(1.0, 5.203)
        assert t_jupiter > t_mars


class TestPlanetDepartureDV:

    def test_earth_departure_for_mars(self):
        """Earth departure ΔV for Mars Hohmann should be ~3.6 km/s."""
        dv_helio, _ = hohmann_dv(1.0, 1.524)
        dv = planet_departure_dv("earth", dv_helio, 185.0)
        assert 3200 < dv < 4000

    def test_higher_v_inf_more_dv(self):
        dv_lo = planet_departure_dv("earth", 1000.0)
        dv_hi = planet_departure_dv("earth", 5000.0)
        assert dv_hi > dv_lo

    def test_lower_orbit_higher_dv_for_same_vinf(self):
        """Lower parking orbit → higher ΔV for same v∞ (deeper gravity well).

        The Oberth effect makes each m/s more energy-efficient at low altitude,
        but the total ΔV is greater because v_circ is higher and the spacecraft
        must climb out of a deeper potential well.
        """
        dv_lo = planet_departure_dv("earth", 3000.0, 185.0)
        dv_hi = planet_departure_dv("earth", 3000.0, 1000.0)
        assert dv_lo > dv_hi  # deeper well → more ΔV needed


class TestMissionBudgets:

    def test_moon_round_trip(self):
        """Moon round-trip should be ~4,900 m/s (Wertz SMAD)."""
        b = moon_mission_budget(True)
        assert 4_500 < b.total_dv_ms < 5_500

    def test_mars_round_trip(self):
        """Mars round-trip should be ~7,000–9,000 m/s."""
        b = mars_mission_budget(True)
        assert 6_500 < b.total_dv_ms < 9_500

    def test_mars_one_way_less_than_round_trip(self):
        one = mars_mission_budget(False)
        rnd = mars_mission_budget(True)
        assert one.total_dv_ms < rnd.total_dv_ms

    def test_jupiter_higher_than_mars(self):
        j = jupiter_mission_budget()
        m = mars_mission_budget(False)
        assert j.total_dv_ms > m.total_dv_ms

    def test_custom_venus(self):
        b = custom_mission_budget("venus")
        assert b.total_dv_ms > 0
        assert b.destination == "venus"

    def test_invalid_destination_raises(self):
        with pytest.raises(ValueError):
            custom_mission_budget("pluto")


class TestPropellant:

    def test_mass_conservation(self):
        b = moon_mission_budget()
        b = compute_propellant(b, 10_000.0, 450.0)
        assert b.initial_mass_kg == pytest.approx(b.payload_kg + b.propellant_kg, rel=1e-9)

    def test_higher_isp_less_propellant(self):
        b1 = compute_propellant(mars_mission_budget(), 50_000.0, 450.0)
        b2 = compute_propellant(mars_mission_budget(), 50_000.0, 900.0)
        assert b2.propellant_kg < b1.propellant_kg

    def test_mass_ratio_gt_one(self):
        b = compute_propellant(moon_mission_budget(), 10_000.0, 450.0)
        assert b.mass_ratio > 1.0

    def test_tsiolkovsky_formula(self):
        """Mass ratio should equal exp(ΔV / Ve)."""
        b = compute_propellant(moon_mission_budget(), 10_000.0, 450.0)
        ve = 450.0 * G0
        expected_ratio = math.exp(b.total_dv_ms / ve)
        assert b.mass_ratio == pytest.approx(expected_ratio, rel=1e-9)


class TestSolarSystemMap:

    def test_returns_list(self):
        m = solar_system_dv_map()
        assert isinstance(m, list)
        assert len(m) >= 6  # at least 6 planets (excl Earth + Moon)

    def test_mars_easiest(self):
        """Mars should have the lowest total ΔV (easiest target)."""
        m = solar_system_dv_map()
        assert m[0]["destination"] == "mars"

    def test_all_positive(self):
        for d in solar_system_dv_map():
            assert d["total_one_way_ms"] > 0
            assert d["transfer_time_days"] > 0
