"""Tests for laser_sail.py — photon-driven interstellar propulsion."""

import math
import pytest

from aria.simulation.laser_sail import (
    C_LIGHT, AU_M, LY_M,
    LaserSailConfig, LaserSailResult, SailThermalAnalysis,
    compute_sail_acceleration, sail_thermal_analysis,
    breakthrough_starshot, solar_system_sail,
)


class TestSailAcceleration:

    def test_radiation_pressure_formula(self):
        """F = (1+R) × P/c for perfect reflector: F = 2P/c."""
        config = LaserSailConfig(1e9, 1e-6, 1000, 10, 1.0, 1.0)  # R=1 perfect
        r = compute_sail_acceleration(config)
        expected_force = 2 * 1e9 / C_LIGHT
        expected_accel = expected_force / 1.0
        assert r.initial_accel_ms2 == pytest.approx(expected_accel, rel=0.01)

    def test_more_power_more_accel(self):
        c1 = LaserSailConfig(1e9, 1e-6, 1000, 10, 1.0, 0.99)
        c2 = LaserSailConfig(10e9, 1e-6, 1000, 10, 1.0, 0.99)
        assert compute_sail_acceleration(c2).initial_accel_ms2 > \
               compute_sail_acceleration(c1).initial_accel_ms2

    def test_heavier_sail_less_accel(self):
        c1 = LaserSailConfig(1e9, 1e-6, 1000, 10, 1.0, 0.99)
        c2 = LaserSailConfig(1e9, 1e-6, 1000, 10, 100.0, 0.99)
        assert compute_sail_acceleration(c1).initial_accel_ms2 > \
               compute_sail_acceleration(c2).initial_accel_ms2

    def test_speed_below_c(self):
        """Final speed must be below speed of light (non-relativistic model)."""
        r = breakthrough_starshot()
        assert r.final_speed_ms < C_LIGHT

    def test_beam_riding_distance_positive(self):
        r = breakthrough_starshot()
        assert r.beam_riding_distance_m > 0

    def test_accel_time_positive(self):
        r = breakthrough_starshot()
        assert r.accel_time_s > 0


class TestBreakthroughStarshot:

    def test_reaches_significant_fraction_of_c(self):
        """Starshot should reach > 0.1c with 100 GW laser on 1g sail."""
        r = breakthrough_starshot()
        assert r.final_speed_c > 0.1

    def test_alpha_centauri_under_50_years(self):
        """Should reach Alpha Centauri in < 50 years (Lubin target: ~20 yr)."""
        r = breakthrough_starshot()
        assert r.time_to_alpha_centauri_yr < 50

    def test_accel_time_minutes(self):
        """Acceleration phase should be minutes, not hours."""
        r = breakthrough_starshot()
        assert r.accel_time_s < 3600  # less than 1 hour

    def test_extreme_g_force(self):
        """Starshot acceleration exceeds 10,000 g (no crew possible)."""
        r = breakthrough_starshot()
        assert r.initial_accel_g > 10_000


class TestSolarSystemSail:

    def test_100au_under_10_years(self):
        """Solar system sail should reach 100 AU in < 10 years."""
        r = solar_system_sail()
        assert r.time_to_100au_yr < 10

    def test_speed_over_50_kms(self):
        """Should exceed 50 km/s (faster than any current probe)."""
        r = solar_system_sail()
        assert r.final_speed_ms > 50_000

    def test_gentle_acceleration(self):
        """100 kg sail should have < 1 g acceleration."""
        r = solar_system_sail()
        assert r.initial_accel_g < 1.0


class TestThermalAnalysis:

    def test_higher_reflectivity_cooler(self):
        """Higher reflectivity → less absorption → lower temperature."""
        c1 = LaserSailConfig(1e9, 1e-6, 1000, 10, 1, 0.9)
        c2 = LaserSailConfig(1e9, 1e-6, 1000, 10, 1, 0.999)
        t1 = sail_thermal_analysis(c1)
        t2 = sail_thermal_analysis(c2)
        assert t2.equilibrium_temp_k < t1.equilibrium_temp_k

    def test_starshot_thermal_crisis(self):
        """Starshot 100 GW with R=0.999 should exceed 1500 K (melting)."""
        config = LaserSailConfig(100e9, 1.06e-6, 10000, 4.1, 0.001, 0.999)
        th = sail_thermal_analysis(config, emissivity=0.5, max_temp_k=1500)
        assert th.equilibrium_temp_k > 1500, (
            "100 GW on R=0.999 sail should overheat (the key Starshot challenge)"
        )

    def test_absorbed_power_positive(self):
        config = LaserSailConfig(1e9, 1e-6, 1000, 10, 1, 0.99)
        th = sail_thermal_analysis(config)
        assert th.absorbed_power_w > 0

    def test_max_safe_power_positive(self):
        config = LaserSailConfig(1e9, 1e-6, 1000, 10, 1, 0.99)
        th = sail_thermal_analysis(config)
        assert th.max_safe_power_w > 0
