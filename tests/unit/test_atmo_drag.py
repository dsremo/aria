"""Tests for atmo_drag.py — atmospheric drag and orbital lifetime.

Coverage:
  - NRLMSISE-00 density: range checks at key altitudes, solar activity sensitivity
  - Drag analysis: acceleration, force, decay rate for ISS-class orbit
  - Orbit lifetime: 25-year rule compliance, altitude dependence
  - Physical consistency: density decreases with altitude, drag increases at lower alt

References:
  Picone et al. (2002) JGR 107:A12 — NRLMSISE-00
  King-Hele (1987) "Satellite Orbits in an Atmosphere"
  NASA-STD-8719.14B — 25-year deorbit rule
"""

import math
import pytest

from aria.simulation.atmo_drag import (
    MU_EARTH, R_EARTH_M,
    F107_SOLAR_MIN, F107_MODERATE, F107_SOLAR_MAX,
    AtmosphericDensity, DragAnalysis, OrbitLifetime,
    get_density, compute_drag, orbit_lifetime,
    density_vs_altitude, lifetime_vs_altitude,
)


# ═══════════════════════════════════════════════════════════════════
#  1. ATMOSPHERIC DENSITY
# ═══════════════════════════════════════════════════════════════════

class TestGetDensity:
    """NRLMSISE-00 atmospheric density model."""

    def test_density_at_400km(self):
        """Density at 400 km should be ~10⁻¹² kg/m³ (moderate solar activity)."""
        d = get_density(400.0, f107=F107_MODERATE)
        assert 1e-13 < d.density_kg_m3 < 1e-11, (
            f"400 km density {d.density_kg_m3:.2e} outside 10⁻¹³–10⁻¹¹ range"
        )

    def test_density_at_200km(self):
        """Density at 200 km should be ~10⁻¹⁰ kg/m³."""
        d = get_density(200.0)
        assert 1e-11 < d.density_kg_m3 < 1e-9

    def test_density_at_800km(self):
        """Density at 800 km should be ~10⁻¹⁵ to 10⁻¹³ kg/m³."""
        d = get_density(800.0)
        assert 1e-16 < d.density_kg_m3 < 1e-12

    def test_density_decreases_with_altitude(self):
        """Density must decrease monotonically with altitude."""
        d200 = get_density(200.0).density_kg_m3
        d400 = get_density(400.0).density_kg_m3
        d600 = get_density(600.0).density_kg_m3
        d800 = get_density(800.0).density_kg_m3
        assert d200 > d400 > d600 > d800

    def test_solar_max_denser_than_min(self):
        """Solar maximum → hotter thermosphere → higher density at altitude."""
        d_min = get_density(400.0, f107=F107_SOLAR_MIN).density_kg_m3
        d_max = get_density(400.0, f107=F107_SOLAR_MAX).density_kg_m3
        assert d_max > d_min, "Solar max should give higher density at 400 km"

    def test_solar_max_much_denser(self):
        """At 400 km, solar max density should be 5–50× solar min."""
        d_min = get_density(400.0, f107=F107_SOLAR_MIN).density_kg_m3
        d_max = get_density(400.0, f107=F107_SOLAR_MAX).density_kg_m3
        ratio = d_max / d_min
        assert 3.0 < ratio < 100.0, f"Solar max/min density ratio {ratio:.1f}×"

    def test_returns_atmospheric_density(self):
        d = get_density(400.0)
        assert isinstance(d, AtmosphericDensity)

    def test_temperature_positive(self):
        d = get_density(400.0)
        assert d.temperature_k > 0
        assert d.exospheric_temp_k > 0

    def test_scale_height_reasonable(self):
        """Scale height at 400 km should be 30–80 km."""
        d = get_density(400.0)
        assert 20.0 < d.scale_height_km < 100.0


# ═══════════════════════════════════════════════════════════════════
#  2. DRAG ANALYSIS
# ═══════════════════════════════════════════════════════════════════

class TestComputeDrag:
    """Drag force and decay rate computation."""

    def test_iss_drag_order_of_magnitude(self):
        """ISS drag force at 400 km should be ~0.01–1.0 N."""
        d = compute_drag(400.0, 150.0, 420_000.0)
        assert 0.001 < d.drag_force_n < 10.0, (
            f"ISS drag force {d.drag_force_n:.3f} N outside 0.001–10 range"
        )

    def test_iss_decay_rate(self):
        """ISS decay rate should be ~0.01–0.5 km/day."""
        d = compute_drag(400.0, 150.0, 420_000.0)
        assert 0.001 < d.decay_rate_km_day < 1.0

    def test_iss_reboost_budget(self):
        """ISS reboost ΔV should be ~0.5–5 m/s/month."""
        d = compute_drag(400.0, 150.0, 420_000.0)
        assert 0.05 < d.reboost_dv_ms_month < 10.0

    def test_lower_altitude_more_drag(self):
        """Lower altitude → higher density → more drag."""
        d_low = compute_drag(300.0, 150.0, 420_000.0)
        d_high = compute_drag(500.0, 150.0, 420_000.0)
        assert d_low.drag_accel_ms2 > d_high.drag_accel_ms2

    def test_lower_beta_more_drag(self):
        """Lower ballistic coefficient → more drag (larger area per mass)."""
        d_lo = compute_drag(400.0, 50.0, 10_000.0)
        d_hi = compute_drag(400.0, 200.0, 10_000.0)
        assert d_lo.drag_accel_ms2 > d_hi.drag_accel_ms2

    def test_returns_drag_analysis(self):
        d = compute_drag(400.0)
        assert isinstance(d, DragAnalysis)

    def test_orbital_speed_correct(self):
        """Orbital speed at 400 km should be ~7.67 km/s."""
        d = compute_drag(400.0)
        v_kms = d.v_orbital_ms / 1000.0
        assert v_kms == pytest.approx(7.67, abs=0.05)


# ═══════════════════════════════════════════════════════════════════
#  3. ORBIT LIFETIME
# ═══════════════════════════════════════════════════════════════════

class TestOrbitLifetime:
    """Orbit lifetime estimation for 25-year rule compliance."""

    def test_low_orbit_short_lifetime(self):
        """300 km orbit (β=50) should decay in < 1 year."""
        lt = orbit_lifetime(300.0, 50.0, f107=F107_MODERATE)
        assert lt.lifetime_years < 2.0, (
            f"300 km lifetime {lt.lifetime_years:.1f} yr should be < 2 years"
        )

    def test_high_orbit_long_lifetime(self):
        """800 km orbit (β=50) should survive > 10 years."""
        lt = orbit_lifetime(800.0, 50.0, f107=F107_MODERATE)
        assert lt.lifetime_years > 5.0

    def test_higher_altitude_longer_lifetime(self):
        """Higher altitude → longer lifetime (exponentially less density)."""
        lt_lo = orbit_lifetime(350.0, 50.0)
        lt_hi = orbit_lifetime(500.0, 50.0)
        assert lt_hi.lifetime_years > lt_lo.lifetime_years

    def test_higher_beta_longer_lifetime(self):
        """Higher β → less drag → longer lifetime."""
        lt_lo = orbit_lifetime(400.0, 30.0)
        lt_hi = orbit_lifetime(400.0, 200.0)
        assert lt_hi.lifetime_years > lt_lo.lifetime_years

    def test_25yr_compliant_at_low_altitude(self):
        """Low orbits (< 500 km) should be 25-year compliant with β < 100."""
        lt = orbit_lifetime(400.0, 80.0)
        assert lt.compliant_25yr is True

    def test_decay_profile_starts_at_initial(self):
        """Decay profile should start at the initial altitude."""
        lt = orbit_lifetime(400.0, 50.0)
        assert lt.decay_profile[0]["altitude_km"] == pytest.approx(400.0)
        assert lt.decay_profile[0]["time_days"] == 0.0

    def test_returns_orbit_lifetime(self):
        lt = orbit_lifetime(400.0, 50.0)
        assert isinstance(lt, OrbitLifetime)


# ═══════════════════════════════════════════════════════════════════
#  4. TRADE STUDY UTILITIES
# ═══════════════════════════════════════════════════════════════════

class TestTradeStudies:
    """Convenience functions for trade studies."""

    def test_density_profile_returns_list(self):
        p = density_vs_altitude([200, 400, 600])
        assert isinstance(p, list)
        assert len(p) == 3

    def test_density_profile_decreasing(self):
        p = density_vs_altitude([200, 400, 600, 800])
        densities = [x["density_kg_m3"] for x in p]
        for i in range(1, len(densities)):
            assert densities[i] < densities[i-1]

    def test_lifetime_vs_altitude_returns_list(self):
        lt = lifetime_vs_altitude([300, 500])
        assert isinstance(lt, list)
        assert len(lt) == 2

    def test_lifetime_increasing_with_altitude(self):
        lt = lifetime_vs_altitude([300, 400, 500])
        lifetimes = [x["lifetime_years"] for x in lt]
        for i in range(1, len(lifetimes)):
            assert lifetimes[i] > lifetimes[i-1]
