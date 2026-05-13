"""Tests for nbody.py — N-body orbital integrator.

Coverage:
  - Moon ephemeris: position at J2000, distance range, period consistency
  - Sun ephemeris: position at J2000, distance ~1 AU, yearly period
  - Third-body acceleration: sign, magnitude, indirect term
  - J2 acceleration: sign, magnitude, equatorial vs polar
  - Propagation: energy conservation, LEO stability, multi-body consistency
  - Helpers: circular orbit speed, orbital period, SOI
  - Validation: LEO conservation test passes

References:
  Meeus J. (1991) "Astronomical Algorithms" ch. 25, 47
  Vallado (2013) 4th ed §8 — orbit propagation
  Montenbruck & Gill (2000) "Satellite Orbits" §3
"""

import math
import numpy as np
import pytest

from aria.simulation.nbody import (
    MU_EARTH, MU_MOON, MU_SUN, R_EARTH_M, J2_EARTH, AU_M, P_SUN_1AU,
    MOON_SEMI_MAJOR_M, MOON_ORBITAL_PERIOD,
    OrbitalState, PropagationResult,
    moon_position_eci, sun_position_eci,
    _third_body_accel, _j2_accel, _srp_accel,
    equations_of_motion, propagate,
    circular_orbit_state, distance_to_moon,
    orbital_period, specific_energy, sphere_of_influence,
    validate_leo_orbit,
)


# ═══════════════════════════════════════════════════════════════════
#  1. MOON EPHEMERIS
# ═══════════════════════════════════════════════════════════════════

class TestMoonEphemeris:
    """Simplified Meeus lunar ephemeris sanity checks."""

    def test_moon_distance_at_j2000(self):
        """Moon distance at J2000 should be 350,000–410,000 km (orbital range)."""
        r = moon_position_eci(0.0)
        d_km = np.linalg.norm(r) / 1000.0
        assert 350_000 < d_km < 410_000, (
            f"Moon distance {d_km:.0f} km outside 350,000–410,000 km range"
        )

    def test_moon_returns_3d(self):
        """Moon position should be a 3-element array."""
        r = moon_position_eci(0.0)
        assert r.shape == (3,)

    def test_moon_changes_over_time(self):
        """Moon position should change over one day."""
        r0 = moon_position_eci(0.0)
        r1 = moon_position_eci(86400.0)
        delta = np.linalg.norm(r1 - r0)
        # Moon moves ~1 km/s → ~86,000 km/day
        assert delta > 50_000_000, "Moon should move >50,000 km in one day"

    def test_moon_period_consistent(self):
        """After one sidereal month (~27.3 days), Moon should return near start."""
        r0 = moon_position_eci(0.0)
        r1 = moon_position_eci(MOON_ORBITAL_PERIOD)
        delta_km = np.linalg.norm(r1 - r0) / 1000.0
        # Should return within ~30,000 km (simplified ephemeris + eccentricity)
        assert delta_km < 50_000, (
            f"Moon after one sidereal month should be near start, got {delta_km:.0f} km away"
        )

    def test_moon_not_at_origin(self):
        """Moon should never be at Earth's center."""
        for t in [0, 86400, 7*86400, 14*86400]:
            r = moon_position_eci(float(t))
            assert np.linalg.norm(r) > 300_000_000, "Moon should be >300,000 km from Earth"


# ═══════════════════════════════════════════════════════════════════
#  2. SUN EPHEMERIS
# ═══════════════════════════════════════════════════════════════════

class TestSunEphemeris:
    """Simplified Meeus solar ephemeris sanity checks."""

    def test_sun_distance_approximately_1au(self):
        """Sun distance at J2000 should be ~0.98–1.02 AU."""
        r = sun_position_eci(0.0)
        d_au = np.linalg.norm(r) / AU_M
        assert 0.97 < d_au < 1.03, f"Sun distance {d_au:.4f} AU outside 0.97–1.03 range"

    def test_sun_returns_3d(self):
        r = sun_position_eci(0.0)
        assert r.shape == (3,)

    def test_sun_moves_over_6_months(self):
        """Sun should be roughly opposite after 6 months."""
        r0 = sun_position_eci(0.0)
        r1 = sun_position_eci(182.625 * 86400.0)
        # Dot product should be negative (opposite sides)
        dot = np.dot(r0, r1)
        assert dot < 0, "Sun should be on opposite side after 6 months"

    def test_sun_distance_range_over_year(self):
        """Sun distance should vary 0.983–1.017 AU over a year (Earth eccentricity)."""
        distances_au = []
        for day in range(0, 366, 30):
            r = sun_position_eci(day * 86400.0)
            distances_au.append(np.linalg.norm(r) / AU_M)
        assert min(distances_au) > 0.980
        assert max(distances_au) < 1.020


# ═══════════════════════════════════════════════════════════════════
#  3. THIRD-BODY ACCELERATION
# ═══════════════════════════════════════════════════════════════════

class TestThirdBodyAccel:
    """Third-body gravitational perturbation calculation."""

    def test_moon_accel_magnitude(self):
        """Moon's tidal acceleration at Earth's surface should be ~10⁻⁵ m/s²."""
        r_sc = np.array([R_EARTH_M, 0, 0])
        r_moon = np.array([MOON_SEMI_MAJOR_M, 0, 0])
        a = _third_body_accel(r_sc, r_moon, MU_MOON)
        a_mag = np.linalg.norm(a)
        # Tidal acceleration ≈ 2 × μ_moon × R_earth / d_moon³ ≈ 1.1e-6 m/s²
        assert 1e-7 < a_mag < 1e-4, f"Moon tidal accel {a_mag:.2e} outside expected range"

    def test_sun_accel_magnitude(self):
        """Sun's tidal acceleration at Earth's surface should be ~5×10⁻⁷ m/s²."""
        r_sc = np.array([R_EARTH_M, 0, 0])
        r_sun = np.array([AU_M, 0, 0])
        a = _third_body_accel(r_sc, r_sun, MU_SUN)
        a_mag = np.linalg.norm(a)
        # Sun tidal accel ≈ 2 × μ_sun × R_earth / AU³ ≈ 5e-7 m/s²
        assert 1e-8 < a_mag < 1e-4

    def test_zero_at_body_location(self):
        """At the third body's location, direct and indirect terms should cancel."""
        r_moon = np.array([MOON_SEMI_MAJOR_M, 0, 0])
        # Spacecraft exactly at Moon position → r_rel = 0
        # But our function returns zero for r_rel < 1m (safety guard)
        a = _third_body_accel(r_moon, r_moon, MU_MOON)
        assert np.linalg.norm(a) < 1e-10


# ═══════════════════════════════════════════════════════════════════
#  4. J2 ACCELERATION
# ═══════════════════════════════════════════════════════════════════

class TestJ2Accel:
    """Earth J2 oblateness perturbation."""

    def test_j2_magnitude_at_leo(self):
        """J2 acceleration at 400 km should be ~0.01 m/s² (dominant perturbation)."""
        r = np.array([R_EARTH_M + 400_000, 0, 0])
        a = _j2_accel(r)
        a_mag = np.linalg.norm(a)
        # J2 at LEO: ~(3/2) × J2 × μ × R²/r⁴ ≈ 0.01 m/s²
        assert 0.001 < a_mag < 0.1, f"J2 accel {a_mag:.4f} m/s² outside expected range"

    def test_j2_points_toward_equator(self):
        """For a spacecraft above the equator, J2 should be purely radial (z=0)."""
        r = np.array([R_EARTH_M + 400_000, 0, 0])  # on x-axis, equatorial
        a = _j2_accel(r)
        # In the equatorial plane (z=0), the z-component of J2 should be zero
        assert abs(a[2]) < 1e-15, f"J2 z-component should be 0 at equator, got {a[2]}"

    def test_j2_stronger_closer(self):
        """J2 perturbation should be stronger at lower altitude."""
        r_lo = np.array([R_EARTH_M + 200_000, 0, 0])
        r_hi = np.array([R_EARTH_M + 2_000_000, 0, 0])
        a_lo = np.linalg.norm(_j2_accel(r_lo))
        a_hi = np.linalg.norm(_j2_accel(r_hi))
        assert a_lo > a_hi

    def test_j2_below_surface_returns_zero(self):
        """J2 acceleration below Earth's surface should return zero (guard)."""
        r = np.array([R_EARTH_M * 0.5, 0, 0])
        a = _j2_accel(r)
        assert np.allclose(a, 0.0)


# ═══════════════════════════════════════════════════════════════════
#  4b. SOLAR RADIATION PRESSURE
# ═══════════════════════════════════════════════════════════════════

class TestSRP:
    """Solar radiation pressure perturbation."""

    def test_srp_magnitude_at_1au(self):
        """SRP acceleration for a 1 m² plate (1 kg) at 1 AU should be ~10⁻⁵ m/s²."""
        r_sc = np.array([R_EARTH_M + 400_000, 0, 0])
        r_sun = np.array([AU_M, 0, 0])
        a = _srp_accel(r_sc, r_sun, area_m2=1.0, mass_kg=1.0, cr=1.5)
        a_mag = np.linalg.norm(a)
        # P_sun = 4.56e-6 N/m² × Cr × A/m = 4.56e-6 × 1.5 × 1.0 = 6.84e-6 m/s²
        assert 1e-6 < a_mag < 1e-4, f"SRP accel {a_mag:.2e} outside expected range"

    def test_srp_points_away_from_sun(self):
        """SRP should push spacecraft away from the Sun."""
        r_sc = np.array([0, 0, 0])  # at Earth center (for simplicity)
        r_sun = np.array([AU_M, 0, 0])  # Sun in +x direction
        a = _srp_accel(r_sc, r_sun, area_m2=10.0, mass_kg=100.0, cr=1.5)
        # Force away from Sun → in -x direction (Sun→spacecraft is -x)
        assert a[0] < 0, "SRP should push away from Sun (anti-sunward)"

    def test_srp_decreases_with_distance(self):
        """SRP follows inverse-square law with distance to Sun."""
        r_sun = np.array([AU_M, 0, 0])
        # Close to Sun
        r_sc_close = np.array([0.5 * AU_M, 0, 0])
        a_close = np.linalg.norm(_srp_accel(r_sc_close, r_sun, 1.0, 1.0, 1.5))
        # Far from Sun
        r_sc_far = np.array([-AU_M, 0, 0])
        a_far = np.linalg.norm(_srp_accel(r_sc_far, r_sun, 1.0, 1.0, 1.5))
        assert a_close > a_far

    def test_srp_zero_for_zero_area(self):
        """SRP with area=0 should give zero acceleration."""
        r_sc = np.array([R_EARTH_M, 0, 0])
        r_sun = np.array([AU_M, 0, 0])
        a = _srp_accel(r_sc, r_sun, area_m2=0.0, mass_kg=100.0, cr=1.5)
        assert np.allclose(a, 0.0)

    def test_propagate_with_srp_includes_srp_body(self):
        """Propagation with SRP should list 'srp' in bodies_included."""
        state0 = circular_orbit_state(400.0)
        r = propagate(state0, 60.0, srp_area_m2=10.0, srp_mass_kg=1000.0)
        assert "srp" in r.bodies_included


# ═══════════════════════════════════════════════════════════════════
#  5. PROPAGATION
# ═══════════════════════════════════════════════════════════════════

class TestPropagate:
    """Full n-body propagation tests."""

    def test_leo_energy_conservation(self):
        """LEO orbit energy should be conserved to <1e-6 relative over 1 orbit."""
        state0 = circular_orbit_state(400.0)
        T = orbital_period(400.0)
        result = propagate(state0, T, dt_output_s=T/50.0)

        energies = [specific_energy(s.r_mag, s.v_mag) for s in result.states]
        e0 = energies[0]
        max_drift = max(abs(e - e0) for e in energies) / abs(e0)
        assert max_drift < 1e-6, f"Energy drift {max_drift:.2e} exceeds 1e-6"

    def test_returns_propagation_result(self):
        state0 = circular_orbit_state(400.0)
        result = propagate(state0, 3600.0, dt_output_s=600.0)
        assert isinstance(result, PropagationResult)
        assert len(result.states) >= 2

    def test_output_times_match(self):
        """Output times should match requested dt_output_s spacing."""
        state0 = circular_orbit_state(400.0)
        result = propagate(state0, 3600.0, dt_output_s=600.0)
        dt_actual = np.diff(result.t_seconds)
        assert np.allclose(dt_actual, 600.0, rtol=0.01)

    def test_moon_positions_tracked(self):
        """Moon positions should be computed at each output time."""
        state0 = circular_orbit_state(400.0)
        result = propagate(state0, 3600.0, dt_output_s=600.0)
        assert result.moon_positions_m.shape[0] == len(result.states)
        assert result.moon_positions_m.shape[1] == 3

    def test_bodies_included_list(self):
        """Bodies list should reflect what was included."""
        state0 = circular_orbit_state(400.0)
        r1 = propagate(state0, 60.0, include_moon=True, include_sun=False)
        assert "moon" in r1.bodies_included
        assert "sun" not in r1.bodies_included

        r2 = propagate(state0, 60.0, include_moon=False, include_sun=True, include_j2=True)
        assert "moon" not in r2.bodies_included
        assert "sun" in r2.bodies_included
        assert "earth_j2" in r2.bodies_included

    def test_earth_only_is_keplerian(self):
        """With only Earth gravity, orbit should be purely Keplerian (closed)."""
        state0 = circular_orbit_state(400.0)
        T = orbital_period(400.0)
        result = propagate(state0, T, dt_output_s=T/50.0,
                           include_moon=False, include_sun=False, include_j2=False)

        # Should return to within meters of start
        dr = np.linalg.norm(result.positions_m[-1] - result.positions_m[0])
        assert dr < 10.0, (  # 10 meters tolerance
            f"Pure Keplerian orbit should close: gap = {dr:.1f} m"
        )

    def test_altitude_stable_for_circular_orbit(self):
        """Circular orbit altitude should stay nearly constant."""
        state0 = circular_orbit_state(400.0)
        T = orbital_period(400.0)
        result = propagate(state0, 2 * T, dt_output_s=T/100.0,
                           include_moon=False, include_sun=False)

        alts_km = [s.altitude_m / 1000.0 for s in result.states]
        variation = max(alts_km) - min(alts_km)
        assert variation < 1.0, f"Altitude variation {variation:.3f} km exceeds 1 km"


# ═══════════════════════════════════════════════════════════════════
#  6. HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

class TestHelpers:
    """Utility function tests."""

    def test_circular_orbit_speed(self):
        """Circular orbit at 400 km should have v ≈ 7.67 km/s."""
        state = circular_orbit_state(400.0)
        v_kms = state.v_mag / 1000.0
        assert v_kms == pytest.approx(7.67, abs=0.05), (
            f"LEO circular speed {v_kms:.2f} km/s, expected ≈ 7.67 km/s"
        )

    def test_circular_orbit_altitude(self):
        """Circular orbit state should have correct altitude."""
        state = circular_orbit_state(400.0)
        alt_km = state.altitude_m / 1000.0
        assert alt_km == pytest.approx(400.0, abs=0.1)

    def test_orbital_period_iss(self):
        """ISS orbital period at 400 km should be ≈ 92.4 minutes."""
        T = orbital_period(400.0)
        T_min = T / 60.0
        assert T_min == pytest.approx(92.4, abs=0.5)

    def test_orbital_period_geo(self):
        """GEO orbital period at 35,786 km should be ≈ 24 hours (1436 min)."""
        T = orbital_period(35_786.0)
        T_hr = T / 3600.0
        assert T_hr == pytest.approx(24.0, abs=0.1)

    def test_specific_energy_bound_orbit(self):
        """LEO orbit should have negative specific energy (bound)."""
        r = R_EARTH_M + 400_000
        v = math.sqrt(MU_EARTH / r)
        e = specific_energy(r, v)
        assert e < 0

    def test_specific_energy_escape(self):
        """At escape velocity, specific energy should be ≈ 0."""
        r = R_EARTH_M + 400_000
        v_esc = math.sqrt(2 * MU_EARTH / r)
        e = specific_energy(r, v_esc)
        assert abs(e) < 1.0  # within 1 J/kg of zero

    def test_soi_moon(self):
        """Moon's SOI relative to Earth should be ~66,000 km."""
        soi = sphere_of_influence(MU_MOON, MOON_SEMI_MAJOR_M, MU_EARTH)
        soi_km = soi / 1000.0
        assert 60_000 < soi_km < 70_000, f"Moon SOI {soi_km:.0f} km, expected ~66,000 km"

    def test_soi_earth(self):
        """Earth's SOI relative to Sun should be ~925,000 km."""
        soi = sphere_of_influence(MU_EARTH, AU_M, MU_SUN)
        soi_km = soi / 1000.0
        assert 900_000 < soi_km < 950_000, f"Earth SOI {soi_km:.0f} km, expected ~925,000 km"

    def test_distance_to_moon_positive(self):
        """Distance from LEO spacecraft to Moon should be ~384,000 km."""
        state = circular_orbit_state(400.0)
        d = distance_to_moon(state) / 1000.0
        assert 300_000 < d < 420_000


# ═══════════════════════════════════════════════════════════════════
#  7. VALIDATION FUNCTION
# ═══════════════════════════════════════════════════════════════════

class TestValidation:
    """validate_leo_orbit() integration test."""

    def test_validation_passes(self):
        """The built-in LEO validation test should pass."""
        result = validate_leo_orbit(400.0, n_orbits=1)
        assert result["valid"] is True

    def test_energy_drift_small(self):
        """Energy drift should be < 1e-6 relative."""
        result = validate_leo_orbit(400.0, n_orbits=2)
        assert result["energy_relative_drift"] < 1e-6
