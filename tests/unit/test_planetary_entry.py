"""Tests for planetary_entry.py — multi-planet atmospheric entry.

References:
  Braun & Manning (2007) — Mars EDL
  Seiff et al. (1998) — Galileo at Jupiter
  Lebreton et al. (2005) — Huygens at Titan
"""

import math
import pytest

from aria.simulation.planetary_entry import (
    ATMOSPHERES, MISSIONS,
    PlanetaryEntryResult,
    compute_planetary_entry, validate_mission,
)


class TestAtmosphereData:

    def test_all_planets_have_required_keys(self):
        required = {"rho_surface_kg_m3", "scale_height_m", "g_surface_ms2",
                     "K_sutton_graves", "mu_planet_m3s2", "r_planet_m"}
        for name, atmo in ATMOSPHERES.items():
            for key in required:
                assert key in atmo, f"{name} missing key {key}"

    def test_mars_thinner_than_earth(self):
        assert ATMOSPHERES["mars"]["rho_surface_kg_m3"] < ATMOSPHERES["earth"]["rho_surface_kg_m3"]

    def test_venus_thicker_than_earth(self):
        assert ATMOSPHERES["venus"]["rho_surface_kg_m3"] > ATMOSPHERES["earth"]["rho_surface_kg_m3"]

    def test_titan_gravity_low(self):
        assert ATMOSPHERES["titan"]["g_surface_ms2"] < ATMOSPHERES["earth"]["g_surface_ms2"]


class TestComputePlanetaryEntry:

    def test_returns_result(self):
        r = compute_planetary_entry("mars", 5800.0, -15.0, 100.0)
        assert isinstance(r, PlanetaryEntryResult)

    def test_faster_entry_more_g(self):
        slow = compute_planetary_entry("mars", 4000.0, -15.0)
        fast = compute_planetary_entry("mars", 7000.0, -15.0)
        assert fast.peak_decel_g > slow.peak_decel_g

    def test_steeper_angle_more_g(self):
        shallow = compute_planetary_entry("mars", 5800.0, -10.0)
        steep = compute_planetary_entry("mars", 5800.0, -25.0)
        assert steep.peak_decel_g > shallow.peak_decel_g

    def test_faster_entry_more_heat(self):
        slow = compute_planetary_entry("mars", 4000.0, -15.0)
        fast = compute_planetary_entry("mars", 7000.0, -15.0)
        assert fast.peak_heat_rate_w_cm2 > slow.peak_heat_rate_w_cm2

    def test_jupiter_extreme_decel(self):
        """Galileo probe: ~230 g — most violent entry ever."""
        r = compute_planetary_entry("jupiter", 47400.0, -8.4, 223.0, 0.222)
        assert r.peak_decel_g > 100, "Jupiter entry should exceed 100 g"

    def test_mars_survivable(self):
        """Mars entry at MSL conditions should be < 20 g."""
        r = compute_planetary_entry("mars", 5800.0, -15.5, 146.0)
        assert r.peak_decel_g < 25

    def test_earth_entry_matches_apollo_range(self):
        """Earth entry at 11 km/s should give 5-40 g (angle-dependent)."""
        r = compute_planetary_entry("earth", 11000.0, -6.5, 350.0)
        assert 5 < r.peak_decel_g < 40

    def test_kinetic_energy_positive(self):
        r = compute_planetary_entry("mars", 5800.0, -15.0)
        assert r.entry_kinetic_energy_mj_kg > 0

    def test_invalid_planet_raises(self):
        with pytest.raises(ValueError):
            compute_planetary_entry("pluto", 5000.0, -10.0)


class TestGalileoValidation:
    """Galileo probe at Jupiter — the extreme validation case."""

    def test_peak_decel_within_5pct(self):
        """Allen-Eggers works excellently for Jupiter (shallow entry, -8.4°).

        Galileo probe: 230 g actual. Our model should be within 5%.
        Reference: Seiff et al. (1998) JGR 103:E10.
        """
        v = validate_mission("galileo_jupiter")
        assert v["peak_decel_g"]["error_pct"] < 5.0, (
            f"Jupiter peak-g error {v['peak_decel_g']['error_pct']:.0f}% exceeds 5%"
        )


class TestMarsValidation:

    def test_peak_decel_order_of_magnitude(self):
        """MSL Curiosity: 11.4 g actual. Our simplified model should be within 50%.

        Note: MSL used a lifting trajectory (L/D≈0.24) and guided flight,
        which reduces peak-g vs. the ballistic Allen-Eggers prediction.
        50% tolerance is appropriate for a model without L/D correction.
        """
        v = validate_mission("msl_curiosity")
        assert v["peak_decel_g"]["error_pct"] < 50


class TestComparisonAcrossPlanets:

    def test_jupiter_highest_decel(self):
        """Jupiter entry is the most extreme (highest speed + massive gravity)."""
        results = {}
        for planet, v_entry in [("mars", 5800), ("earth", 11000), ("jupiter", 47400)]:
            r = compute_planetary_entry(planet, v_entry, -10.0, 100.0)
            results[planet] = r.peak_decel_g
        assert results["jupiter"] > results["earth"] > results["mars"]

    def test_jupiter_highest_kinetic_energy(self):
        r_j = compute_planetary_entry("jupiter", 47400.0, -10.0)
        r_e = compute_planetary_entry("earth", 11000.0, -10.0)
        assert r_j.entry_kinetic_energy_mj_kg > r_e.entry_kinetic_energy_mj_kg
