"""Verification tests for Pod C1 (rotating-frame kinematics).

Covers the four test cases from `docs/pods/C1_rotating_hab.md` §9 plus
invariant checks for vector-form agreement with scalar closed forms.

  9.1 Stanford Torus 1-g centrifugal at R = 830 m, ω = 1 rpm
  9.2 Coriolis deflection of a dropped object (Hall 2016)
  9.3 Stanford Torus spin-up Euler force over 1 hr cosine ramp
  9.4 Graybiel Pensacola Slow Rotation Room differential-g
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from aria.physics.rotating_frame import (
    RotatingRingConfig,
    centrifugal_acceleration_scalar,
    centrifugal_acceleration_vector,
    coriolis_acceleration_scalar,
    coriolis_acceleration_vector,
    coriolis_dropped_object_deflection,
    cosine_spinup_peak_alpha,
    cosine_spinup_profile,
    differential_g_head_to_foot,
    euler_acceleration_scalar,
    euler_acceleration_vector,
    fluid_paraboloid_height,
)
from aria.physics.rotating_frame.spinup_profile import (
    cosine_spinup_min_ramp_time,
)


STANDARD_GRAVITY_M_S2 = 9.80665  # ISO 80000-3:2019


# ─────────────────────────────────────────────────────────────────────
# Test 9.1 — Stanford Torus 1 g at the design radius
# Source: Johnson & Holbrow 1977 NASA SP-413 Table 2-1 (1 rpm, 830 m)
# ─────────────────────────────────────────────────────────────────────


class TestStanfordTorusCentrifugal:
    """A1 §9.1 — Stanford Torus reference design 1977.

    R = 830 m, ω = 1 rpm = 0.10472 rad/s → a_cf = ω²R ≈ 9.10 m/s²,
    within 8 % of Earth surface gravity. Johnson & Holbrow 1977 Table
    2-1 is the canonical numerical reference.
    """

    R_STANFORD_M = 830.0  # NASA SP-413 Table 2-1
    OMEGA_STANFORD_RAD_S = 2.0 * math.pi / 60.0  # 1 rpm exact
    PUBLISHED_G_M_S2 = 9.10  # NASA SP-413 Table 2-1

    def test_scalar_centrifugal_matches_stanford(self) -> None:
        a = centrifugal_acceleration_scalar(
            self.OMEGA_STANFORD_RAD_S, self.R_STANFORD_M
        )
        assert a == pytest.approx(self.PUBLISHED_G_M_S2, rel=0.005)

    def test_vector_form_matches_scalar(self) -> None:
        # Spin about +z, query point at (R, 0, 0).
        omega_vec = np.array([0.0, 0.0, self.OMEGA_STANFORD_RAD_S])
        r_vec = np.array([self.R_STANFORD_M, 0.0, 0.0])
        a_vec = centrifugal_acceleration_vector(omega_vec, r_vec)
        # Should be (a_cf, 0, 0) — radially outward along +x.
        assert a_vec[0] == pytest.approx(
            centrifugal_acceleration_scalar(
                self.OMEGA_STANFORD_RAD_S, self.R_STANFORD_M
            ),
            rel=1e-12,
        )
        assert a_vec[1] == pytest.approx(0.0, abs=1e-15)
        assert a_vec[2] == pytest.approx(0.0, abs=1e-15)

    def test_ring_config_reports_g_ratio(self) -> None:
        cfg = RotatingRingConfig(
            ring_radius_m=self.R_STANFORD_M,
            spin_rate_rad_s=self.OMEGA_STANFORD_RAD_S,
        )
        # 9.10 / 9.80665 ≈ 0.928 g₀
        assert cfg.design_g_art_in_g0 == pytest.approx(0.928, rel=0.005)


# ─────────────────────────────────────────────────────────────────────
# Test 9.2 — Coriolis deflection of a dropped object
# Source: Hall 2016 J Spacecr Rockets 53(4) 612–619 DOI 10.2514/1.A33430
# ─────────────────────────────────────────────────────────────────────


class TestCoriolisDroppedObject:
    """A1 §9.2 — Hall 2016 artificial-gravity visualization formula.

    A ball released at 2 m above the deck in a 56 m ring spinning at
    4 rpm falls under the deck-level centrifugal "gravity" ~9.82 m/s²,
    takes about 0.64 s to reach the deck, and is deflected tangentially
    by ~0.356 m (integral of a_cor = 2 ω v_fall over the fall time).
    """

    R_RING_M = 56.0
    OMEGA_RAD_S = 2.0 * math.pi * 4.0 / 60.0  # 4 rpm exact
    DROP_HEIGHT_M = 2.0

    def test_fall_time_and_deflection(self) -> None:
        g_art = centrifugal_acceleration_scalar(self.OMEGA_RAD_S, self.R_RING_M)
        t_fall, delta_x = coriolis_dropped_object_deflection(
            spin_rate_rad_s=self.OMEGA_RAD_S,
            g_art_m_s2=g_art,
            drop_height_m=self.DROP_HEIGHT_M,
        )
        # Fall time from kinematics: √(2h/g) ≈ √(4/9.82) ≈ 0.6384 s.
        expected_t = math.sqrt(2.0 * self.DROP_HEIGHT_M / g_art)
        assert t_fall == pytest.approx(expected_t, rel=1e-12)
        # Deflection: (1/3) · ω · g_art · t³
        expected_dx = (1.0 / 3.0) * self.OMEGA_RAD_S * g_art * (t_fall**3)
        assert delta_x == pytest.approx(expected_dx, rel=1e-12)
        # Absolute ballpark: 0.35 m ± 0.05 m.
        assert 0.30 < delta_x < 0.40, delta_x

    def test_prograde_vs_retrograde_symmetric_in_magnitude(self) -> None:
        # The magnitude is independent of walking direction; the sign
        # depends on the ω×v cross product. Here we verify the vector
        # form reverses when ω is reversed.
        omega_forward = np.array([0.0, 0.0, self.OMEGA_RAD_S])
        omega_reverse = np.array([0.0, 0.0, -self.OMEGA_RAD_S])
        v = np.array([0.0, 1.4, 0.0])
        a_fwd = coriolis_acceleration_vector(omega_forward, v)
        a_rev = coriolis_acceleration_vector(omega_reverse, v)
        assert np.allclose(a_fwd, -a_rev, atol=1e-12)

    def test_scalar_walking_coriolis_matches_scope_example(self) -> None:
        # Scope §4.3: ω=0.4189, v_w=1.4 → |a_cor| = 1.173 m/s².
        a = coriolis_acceleration_scalar(0.4189, 1.4)
        assert a == pytest.approx(1.173, abs=0.01)


# ─────────────────────────────────────────────────────────────────────
# Test 9.3 — Stanford Torus 1-hour cosine spin-up peak Euler force
# Source: Clark 1999 NASA/CR-1999-209574 §4.2 example
# ─────────────────────────────────────────────────────────────────────


class TestStanfordSpinupEulerForce:
    """A1 §9.3 — cosine-smoothed ramp 0 → 1 rpm over 1 hour on the
    Stanford Torus deck (R = 830 m). Peak Euler acceleration:

        α_peak = (π/2) · ω_target / T_ramp
               = (π/2) · 0.10472 / 3600
               ≈ 4.57e-5 rad/s²
        |a_E|_peak = R · α_peak ≈ 0.0379 m/s²
    """

    R_STANFORD_M = 830.0
    OMEGA_TARGET_RAD_S = 2.0 * math.pi / 60.0  # 1 rpm
    T_RAMP_S = 3600.0

    def test_peak_alpha_closed_form(self) -> None:
        alpha_peak = cosine_spinup_peak_alpha(
            self.OMEGA_TARGET_RAD_S, self.T_RAMP_S
        )
        expected = 0.5 * math.pi * self.OMEGA_TARGET_RAD_S / self.T_RAMP_S
        assert alpha_peak == pytest.approx(expected, rel=1e-12)

    def test_peak_euler_at_stanford_deck(self) -> None:
        alpha_peak = cosine_spinup_peak_alpha(
            self.OMEGA_TARGET_RAD_S, self.T_RAMP_S
        )
        a_e_peak = euler_acceleration_scalar(alpha_peak, self.R_STANFORD_M)
        # Scope §9.3 cites 0.0379 m/s².
        assert a_e_peak == pytest.approx(0.0379, rel=0.01)

    def test_profile_boundaries_are_smooth(self) -> None:
        # At t=0 and t=T_ramp the angular speed equals 0 and ω_target,
        # and the angular acceleration is exactly zero (the whole point
        # of using the cosine-smoothed form).
        omega0, alpha0 = cosine_spinup_profile(
            0.0, self.OMEGA_TARGET_RAD_S, self.T_RAMP_S
        )
        assert omega0 == 0.0
        assert alpha0 == 0.0

        omega_end, alpha_end = cosine_spinup_profile(
            self.T_RAMP_S, self.OMEGA_TARGET_RAD_S, self.T_RAMP_S
        )
        assert omega_end == pytest.approx(self.OMEGA_TARGET_RAD_S, rel=1e-12)
        assert alpha_end == pytest.approx(0.0, abs=1e-12)

    def test_profile_reaches_peak_at_midpoint(self) -> None:
        # At t = T_ramp / 2 the cosine phase is π/2 → sin = 1 → α peaks.
        _, alpha_mid = cosine_spinup_profile(
            0.5 * self.T_RAMP_S, self.OMEGA_TARGET_RAD_S, self.T_RAMP_S
        )
        alpha_peak = cosine_spinup_peak_alpha(
            self.OMEGA_TARGET_RAD_S, self.T_RAMP_S
        )
        assert alpha_mid == pytest.approx(alpha_peak, rel=1e-12)

    def test_before_and_after_ramp_clamped(self) -> None:
        # Negative t: (0, 0). After ramp: (ω_target, 0).
        omega, alpha = cosine_spinup_profile(
            -1.0, self.OMEGA_TARGET_RAD_S, self.T_RAMP_S
        )
        assert (omega, alpha) == (0.0, 0.0)
        omega, alpha = cosine_spinup_profile(
            self.T_RAMP_S * 2.0, self.OMEGA_TARGET_RAD_S, self.T_RAMP_S
        )
        assert omega == pytest.approx(self.OMEGA_TARGET_RAD_S, rel=1e-12)
        assert alpha == 0.0

    def test_min_ramp_for_naive_crew(self) -> None:
        # Young 2019 naive-crew limit 0.04 rad/s²; for 4 rpm ARIA target:
        omega_target = 2.0 * math.pi * 4.0 / 60.0  # 4 rpm
        t_min = cosine_spinup_min_ramp_time(omega_target, 0.04)
        # (π/2) · 0.4189 / 0.04 ≈ 16.4 s (scope §4.5 worked number).
        assert t_min == pytest.approx(16.4, rel=0.02)


# ─────────────────────────────────────────────────────────────────────
# Test 9.4 — Graybiel 1965 Pensacola Slow Rotation Room differential-g
# Source: Graybiel 1965 Aerospace Medicine 36 733–742
# ─────────────────────────────────────────────────────────────────────


class TestGraybielDifferentialG:
    """A1 §9.4 — Graybiel 1965 Pensacola SRR parameters. Subject
    height 1.80 m, room radius 4.6 m, ω = 10 rpm = 1.047 rad/s:

        Δg = ω² · h = (1.047)² · 1.80 ≈ 1.973 m/s²

    That is ~20 % of the foot-level centrifugal g at 5.04 m/s², right
    in the uncomfortable zone that Graybiel documented.
    """

    GRAYBIEL_R_M = 4.6
    GRAYBIEL_OMEGA_RAD_S = 2.0 * math.pi * 10.0 / 60.0  # 10 rpm
    GRAYBIEL_SUBJECT_HEIGHT_M = 1.80

    def test_differential_g_matches_graybiel(self) -> None:
        delta_g = differential_g_head_to_foot(
            self.GRAYBIEL_OMEGA_RAD_S, self.GRAYBIEL_SUBJECT_HEIGHT_M
        )
        assert delta_g == pytest.approx(1.973, rel=0.01)

    def test_fraction_of_foot_g(self) -> None:
        g_foot = centrifugal_acceleration_scalar(
            self.GRAYBIEL_OMEGA_RAD_S, self.GRAYBIEL_R_M
        )
        delta_g = differential_g_head_to_foot(
            self.GRAYBIEL_OMEGA_RAD_S, self.GRAYBIEL_SUBJECT_HEIGHT_M
        )
        fraction = delta_g / g_foot
        # For a centrifugal field g = ω² r, the algebraic identity
        # Δg / g_foot = h / r_foot holds exactly — completely
        # independent of ω. For the Pensacola SRR (h = 1.80 m, r = 4.6 m)
        # that's 1.80/4.6 = 0.391 — a staggering 39 % gradient that
        # is the primary reason Graybiel saw pervasive motion sickness
        # in a room that small. (The C1 scope note's "~20 %" remark
        # is an arithmetic slip; TODO: correct the scope text.)
        assert fraction == pytest.approx(
            self.GRAYBIEL_SUBJECT_HEIGHT_M / self.GRAYBIEL_R_M, rel=1e-12
        )
        assert fraction == pytest.approx(0.391, abs=0.005)

    def test_aria_baseline_differential_g(self) -> None:
        # ARIA: 4 rpm, 1.85 m body → Δg ≈ 0.325 m/s² (3.3 % of g₀).
        omega = 2.0 * math.pi * 4.0 / 60.0  # 4 rpm
        delta_g = differential_g_head_to_foot(omega, 1.85)
        assert delta_g == pytest.approx(0.325, rel=0.01)
        fraction_of_g0 = delta_g / STANDARD_GRAVITY_M_S2
        assert fraction_of_g0 == pytest.approx(0.033, abs=0.002)

    def test_dg_scales_as_omega_squared(self) -> None:
        # Doubling spin quadruples the differential.
        dg_low = differential_g_head_to_foot(0.5, 1.85)
        dg_high = differential_g_head_to_foot(1.0, 1.85)
        assert dg_high == pytest.approx(4.0 * dg_low, rel=1e-12)


# ─────────────────────────────────────────────────────────────────────
# Vector/scalar consistency checks
# ─────────────────────────────────────────────────────────────────────


class TestVectorScalarConsistency:
    def test_centrifugal_vector_on_generic_axis(self) -> None:
        # Spin about arbitrary axis, point perpendicular to it.
        omega_vec = np.array([1.0, 2.0, 3.0])  # rad/s
        omega_mag = float(np.linalg.norm(omega_vec))
        # Pick a position perpendicular to Ω.
        axis = omega_vec / omega_mag
        # Any vector perpendicular to axis:
        helper = np.array([0.0, 1.0, 0.0])
        r_vec = np.cross(axis, helper)
        r_vec = r_vec / np.linalg.norm(r_vec) * 10.0  # 10 m perpendicular
        a_vec = centrifugal_acceleration_vector(omega_vec, r_vec)
        # |a_vec| should equal ω² r for perpendicular geometry.
        expected = omega_mag * omega_mag * 10.0
        assert float(np.linalg.norm(a_vec)) == pytest.approx(expected, rel=1e-12)
        # And a_vec is parallel to +r_vec (outward).
        dot = float(np.dot(a_vec, r_vec)) / (
            float(np.linalg.norm(a_vec)) * float(np.linalg.norm(r_vec))
        )
        assert dot == pytest.approx(1.0, rel=1e-12)

    def test_coriolis_vector_matches_scalar_for_tangential_walk(self) -> None:
        omega_vec = np.array([0.0, 0.0, 0.4189])
        # Walker moving in +y at a point on the +x axis → prograde.
        v_walk = np.array([0.0, 1.4, 0.0])
        a_vec = coriolis_acceleration_vector(omega_vec, v_walk)
        mag_vec = float(np.linalg.norm(a_vec))
        mag_scalar = coriolis_acceleration_scalar(0.4189, 1.4)
        assert mag_vec == pytest.approx(mag_scalar, rel=1e-12)

    def test_euler_vector_matches_scalar_magnitude(self) -> None:
        alpha_vec = np.array([0.0, 0.0, 0.02])
        r_vec = np.array([56.0, 0.0, 0.0])
        a_vec = euler_acceleration_vector(alpha_vec, r_vec)
        mag_vec = float(np.linalg.norm(a_vec))
        mag_scalar = euler_acceleration_scalar(0.02, 56.0)
        assert mag_vec == pytest.approx(mag_scalar, rel=1e-12)


# ─────────────────────────────────────────────────────────────────────
# Fluid paraboloid
# ─────────────────────────────────────────────────────────────────────


class TestFluidParaboloid:
    def test_surface_at_axis_is_reference(self) -> None:
        # At r=0 the paraboloid height equals the reference z_0.
        z0 = 1.5
        z = fluid_paraboloid_height(
            spin_rate_rad_s=0.4189,
            radial_distance_m=0.0,
            reference_height_m=z0,
        )
        assert z == z0

    def test_surface_rises_parabolically(self) -> None:
        # z(2r) - z_0 = 4 × (z(r) - z_0) for a parabola.
        omega = 0.4189
        z_r = fluid_paraboloid_height(omega, 1.0)
        z_2r = fluid_paraboloid_height(omega, 2.0)
        assert z_2r == pytest.approx(4.0 * z_r, rel=1e-12)

    def test_aria_baseline_surface_depression(self) -> None:
        # At R=56 m, ω=0.4189 rad/s, the free-surface difference
        # between center (r=0) and outer edge is
        # Δz = ω² R² / (2 g) = 0.4189² · 56² / 19.613 ≈ 28 m.
        # (This is why you don't build open reservoirs in a 4 rpm ring.)
        omega = 0.4189
        delta_z = fluid_paraboloid_height(omega, 56.0) - fluid_paraboloid_height(
            omega, 0.0
        )
        assert delta_z == pytest.approx(28.0, rel=0.02)
