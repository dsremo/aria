"""Verification tests for Pod A3 (Earth/Sol escape + Oberth departure).

Covers the five published test cases named in
``docs/pods/A3_oberth_departure.md`` §9. Each test reproduces a
published experiment or mission result, so a failure indicates either
a bug in our implementation or a subsequent data release we have not
tracked.

Sources for expected values are cited inline on every assert.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.departure import (
    DepartureDeltaVBudget,
    GM_EARTH_M3_S2,
    GM_SUN_M3_S2,
    SPEED_OF_LIGHT_M_S,
    STANDARD_GRAVITY_M_S2,
    escape_velocity,
    laser_sail_acceleration,
    oberth_multiplier,
    oberth_v_infinity_after_burn,
    oberth_v_infinity_gain_squared,
    slingshot_delta_v,
    sphere_of_influence_radius,
    stacked_delta_v,
    tsiolkovsky_delta_v,
    v_infinity_from_v,
    vis_viva_speed,
)
from aria.physics.departure.escape import (
    V_EARTH_HELIOCENTRIC_M_S,
    R_SOI_EARTH_M,
    circular_orbit_speed,
)
from aria.physics.departure.tsiolkovsky import exhaust_velocity_from_isp


# ─────────────────────────────────────────────────────────────────────
# Test 9.1 — Saturn V Trans-Lunar Injection Δv
# Source: NASA Apollo 15 Mission Report, NASA MR-15, NTRS 19720005108
# Expected: Δv = I_sp · g_0 · ln(m_0 / m_f) ≈ 3.18 km/s ± 0.02
# ─────────────────────────────────────────────────────────────────────


class TestSaturnVTLI:
    """A3 §9.1 — canonical closed-form Tsiolkovsky test against a
    flight-reconstructed Δv."""

    # Apollo 15 S-IVB reignition parameters (Apollo 15 Mission Report
    # NASA MR-15 Table 6-I, NTRS 19720005108; J-2 engine spec sheet,
    # Rocketdyne 1969). The wet/dry mass pair here is the canonical
    # textbook reduction — Curtis 3rd ed §6.6 example 6.1, ISBN
    # 978-0080977478 — not the raw mission-report numbers, so the
    # published Δv we target is Curtis' 3.18 km/s.
    INITIAL_MASS_KG = 136_500.0  # wet mass at S-IVB reignition
    FINAL_MASS_KG = 63_200.0  # dry mass after TLI burn
    SPECIFIC_IMPULSE_S = 421.0  # J-2 LH2/LOX vacuum I_sp (Rocketdyne datasheet)

    def test_tli_delta_v_matches_curtis(self) -> None:
        v_e = exhaust_velocity_from_isp(self.SPECIFIC_IMPULSE_S)
        dv = tsiolkovsky_delta_v(self.INITIAL_MASS_KG, self.FINAL_MASS_KG, v_e)
        # Curtis 3rd ed §6.6 Example 6.1 gives 3.18 km/s.
        assert dv == pytest.approx(3180.0, abs=20.0), dv


# ─────────────────────────────────────────────────────────────────────
# Test 9.2 — Parker Solar Probe perihelion speed from vis-viva
# Source: Fox 2016 Space Sci. Rev. 204 7, DOI 10.1007/s11214-015-0211-6
# Expected: v_p ≈ 192 km/s at perihelion #24 (r_p ≈ 9.86 R_sun)
# ─────────────────────────────────────────────────────────────────────


class TestParkerSolarProbePerihelion:
    """A3 §9.2 — vis-viva predicts the perihelion speed of PSP's final
    orbit to better than 1 km/s from its semi-major axis."""

    R_SUN_M = 6.957e8  # IAU 2015 Resolution B3
    R_P_M = 9.86 * R_SUN_M  # Fox 2016 Table 1 (final perihelion)
    # PSP final orbit semi-major axis = (r_p + r_a) / 2 with r_a ≈ 0.73 AU
    # (Venus flyby #7 target, Fox 2016 Fig. 2). 1 AU = 1.495978707e11 m
    # (IAU 2012 Resolution B2).
    AU_M = 1.495978707e11  # IAU 2012 Res. B2
    R_A_M = 0.73 * AU_M
    SEMI_MAJOR_AXIS_M = (R_P_M + R_A_M) / 2.0
    PUBLISHED_V_P_M_S = 1.92e5  # Fox 2016 — ~192 km/s at perihelion #24

    def test_psp_perihelion_speed(self) -> None:
        v_p = vis_viva_speed(GM_SUN_M3_S2, self.R_P_M, self.SEMI_MAJOR_AXIS_M)
        # Published nominal: 192 km/s. Match within 2 km/s (1%) — the
        # published r_a value has ~1% uncertainty due to flyby scheduling.
        assert v_p == pytest.approx(self.PUBLISHED_V_P_M_S, rel=0.01), v_p


# ─────────────────────────────────────────────────────────────────────
# Test 9.3 — LEO → solar-system-escape Δv (vis-viva analytic)
# Source: Vallado 4th ed §8.1 ISBN 978-1881883180
# Expected: ~8.8 km/s total Δv split across Earth escape + heliocentric
# ─────────────────────────────────────────────────────────────────────


class TestLEOtoSolEscape:
    """A3 §9.3 — closed-form sanity check of the patched-conic
    departure pipeline."""

    LEO_RADIUS_M = 6.778e6  # Earth-centered, 400 km altitude + R_earth
    # Earth-escape Δv from circular LEO is the classical 3.18 km/s.
    EXPECTED_EARTH_ESCAPE_DV_M_S = 3177.0  # Vallado 4th ed Table 8-2
    # Heliocentric Sol-escape v_inf (Earth starting speed to leave the
    # solar system) = v_escape(1 AU) − v_earth_heliocentric
    #                = √(2 · GM_sun / 1 AU) − 29.78 km/s
    # = 42.12 − 29.78 = 12.34 km/s (Vallado Example 8-1).
    AU_M = 1.495978707e11  # IAU 2012 B2
    EXPECTED_HELIO_ESCAPE_DV_M_S = 12_340.0  # Vallado Example 8-1

    def test_earth_escape_delta_v(self) -> None:
        v_c = circular_orbit_speed(GM_EARTH_M3_S2, self.LEO_RADIUS_M)
        v_esc = escape_velocity(GM_EARTH_M3_S2, self.LEO_RADIUS_M)
        dv = v_esc - v_c
        assert dv == pytest.approx(self.EXPECTED_EARTH_ESCAPE_DV_M_S, abs=50.0), dv

    def test_heliocentric_sol_escape(self) -> None:
        v_esc_1au = escape_velocity(GM_SUN_M3_S2, self.AU_M)
        helio_dv = v_esc_1au - V_EARTH_HELIOCENTRIC_M_S
        # Allow 150 m/s tolerance: V_EARTH_HELIOCENTRIC_M_S is rounded
        # to 29.78 km/s in our constants table, while Vallado used
        # 29.785 km/s in his example.
        assert helio_dv == pytest.approx(
            self.EXPECTED_HELIO_ESCAPE_DV_M_S, abs=150.0
        ), helio_dv

    def test_combined_leo_sol_escape_ballpark(self) -> None:
        # A3 §4.5 — order-of-magnitude check that LEO→Sol escape is in
        # the 8–9 km/s range (Vallado §8.1 worked example).
        v_c_leo = circular_orbit_speed(GM_EARTH_M3_S2, self.LEO_RADIUS_M)
        # Post-Earth-escape heliocentric speed matches Earth's motion
        # (v_∞ = 0 for a minimum Earth escape).
        # Additional heliocentric Δv needed: v_escape(1 AU) − v_earth
        helio_dv = (
            escape_velocity(GM_SUN_M3_S2, self.AU_M) - V_EARTH_HELIOCENTRIC_M_S
        )
        # The *naive* sum overcounts kinetic energy; the proper patched
        # conic uses C3. Vallado reports the minimum total as
        # ~8.8 km/s; see §8.1 example.
        v_esc_earth = escape_velocity(GM_EARTH_M3_S2, self.LEO_RADIUS_M)
        # Proper patched conic: shoot Earth-escape hyperbola with
        # v_∞_earth = helio_dv; then
        # v_at_LEO = √(v_∞² + 2μ_E/r)
        v_at_leo_needed = math.sqrt(
            helio_dv * helio_dv + 2.0 * GM_EARTH_M3_S2 / self.LEO_RADIUS_M
        )
        total_dv = v_at_leo_needed - v_c_leo
        assert total_dv == pytest.approx(8800.0, abs=200.0), total_dv


# ─────────────────────────────────────────────────────────────────────
# Test 9.4 — Oberth gain at PSP perihelion
# Source: §4.3 of A3 scope + Fox 2016 Table 1
# Expected: Δv_∞_gain² ≈ 2 v_p Δv_burn for Δv_burn ≪ v_p
# ─────────────────────────────────────────────────────────────────────


class TestOberthGainAtPSP:
    """A3 §9.4 — exercises the central Oberth formula Δ(v_∞²) ≈ 2 v_p Δv
    against PSP's published perihelion velocity."""

    R_SUN_M = 6.957e8  # IAU 2015 B3
    R_P_M = 9.86 * R_SUN_M
    V_P_M_S = 1.92e5  # Fox 2016 PSP perihelion #24
    BURN_DELTA_V_M_S = 1000.0  # 1 km/s representative impulse

    def test_oberth_multiplier_value(self) -> None:
        mult = oberth_multiplier(self.V_P_M_S, self.BURN_DELTA_V_M_S)
        # 1 + 2 · 192000 / 1000 = 1 + 384 = 385×
        assert mult == pytest.approx(385.0, rel=1e-6)

    def test_oberth_v_inf_gain_leading_term(self) -> None:
        gain_sq = oberth_v_infinity_gain_squared(self.V_P_M_S, self.BURN_DELTA_V_M_S)
        # Leading term: 2 v_p Δv = 2 · 1.92e5 · 1e3 = 3.84e8 m²/s²
        # Plus Δv² = 1e6, negligible
        assert gain_sq == pytest.approx(3.84e8 + 1e6, rel=1e-6)

    def test_post_burn_v_infinity_exact(self) -> None:
        # Sanity: PSP at 9.86 R_sun is on a bound orbit (v_p² < 2μ/r_p),
        # so the minimum Δv to escape is √(2μ/r_p) − v_p ≈ 4.7 km/s.
        # A 10 km/s burn clears that threshold with margin.
        escape_threshold = math.sqrt(2.0 * GM_SUN_M3_S2 / self.R_P_M)
        assert escape_threshold - self.V_P_M_S == pytest.approx(4_700.0, abs=200.0)

        burn = 10_000.0  # 10 km/s Oberth impulse
        v_inf = oberth_v_infinity_after_burn(
            v_perihelion_m_s=self.V_P_M_S,
            burn_delta_v_m_s=burn,
            perihelion_radius_m=self.R_P_M,
            gravitational_parameter_m3_s2=GM_SUN_M3_S2,
        )
        # Hand calculation:
        # (v_p + Δv)² − 2μ/r_p = (202000)² − 2·GM_sun/r_p
        post = self.V_P_M_S + burn
        expected_sq = post * post - 2.0 * GM_SUN_M3_S2 / self.R_P_M
        assert v_inf == pytest.approx(math.sqrt(expected_sq), rel=1e-9)
        # At this configuration the physics gives ~45.9 km/s of v_∞ for
        # 10 km/s of burn — a ~4.6× Oberth multiplier. That's a wide but
        # tight-enough range to catch sign/factor-of-2 errors.
        assert 40_000.0 < v_inf < 55_000.0, v_inf

    def test_oberth_only_linear_in_dv_when_small(self) -> None:
        # Sanity of the scaling law: doubling Δv_burn approximately
        # doubles Δ(v_∞²) for Δv ≪ v_p (the Δv² correction is small).
        a = oberth_v_infinity_gain_squared(self.V_P_M_S, 1000.0)
        b = oberth_v_infinity_gain_squared(self.V_P_M_S, 2000.0)
        # b/a should be ~2 up to the quadratic correction
        ratio = b / a
        assert 2.0 <= ratio <= 2.01, ratio


# ─────────────────────────────────────────────────────────────────────
# Test 9.5 — Forward 1984 laser-sail acceleration
# Source: Forward 1984 J. Spacecraft 21(2) 187 DOI 10.2514/3.8632 Table 2
# Expected: a = 2P/(mc); 10 GW, 1000 kg → 0.0667 m/s²
# ─────────────────────────────────────────────────────────────────────


class TestForwardLaserSail:
    """A3 §9.5 — verifies the §4.5 laser-sail force law and the
    unit-reduction W/(kg·m/s) = m/s² that is the most common error in
    sail-sizing code."""

    def test_forward_1984_example_ten_gigawatts(self) -> None:
        a = laser_sail_acceleration(
            laser_power_w=1.0e10,  # 10 GW
            sail_mass_kg=1000.0,  # 1 tonne
            reflectivity=1.0,  # perfect mirror
        )
        # 2 · 1e10 / (1e3 · 3e8) = 2e10 / 3e11 = 6.667e-2 m/s²
        expected = 2.0 * 1.0e10 / (1.0e3 * SPEED_OF_LIGHT_M_S)
        assert a == pytest.approx(expected, rel=1e-9)
        assert a == pytest.approx(0.06671, abs=1.0e-4), a

    def test_zero_reflectivity_half_thrust(self) -> None:
        # R = 0 → only the photon's initial momentum transfers,
        # halving the acceleration compared to R = 1.
        a_mirror = laser_sail_acceleration(1.0e10, 1000.0, reflectivity=1.0)
        a_black = laser_sail_acceleration(1.0e10, 1000.0, reflectivity=0.0)
        assert a_black == pytest.approx(a_mirror / 2.0, rel=1e-12)

    def test_zero_power_zero_acceleration(self) -> None:
        assert laser_sail_acceleration(0.0, 1000.0) == 0.0


# ─────────────────────────────────────────────────────────────────────
# Extra: Earth sphere-of-influence matches Vallado Table 1-3 (Pod A3
# §5 constants row)
# ─────────────────────────────────────────────────────────────────────


class TestEarthSOI:
    """Sanity check for the Laplace SOI formula against Vallado Table
    1-3, which gives r_SOI(Earth) ≈ 9.245e8 m."""

    M_EARTH_KG = 5.9722e24  # IAU 2015 B3
    M_SUN_KG = 1.98892e30  # IAU 2015 B3
    A_EARTH_M = 1.495978707e11  # 1 AU (IAU 2012 B2)

    def test_earth_soi_radius(self) -> None:
        r_soi = sphere_of_influence_radius(
            self.A_EARTH_M, self.M_EARTH_KG, self.M_SUN_KG
        )
        # Vallado 4th ed Table 1-3: 9.245e8 m.
        assert r_soi == pytest.approx(R_SOI_EARTH_M, rel=5e-3), r_soi


# ─────────────────────────────────────────────────────────────────────
# Extra: gravitational slingshot upper bound 2 v_∞ (Vallado §12.3)
# ─────────────────────────────────────────────────────────────────────


class TestSlingshotBound:
    """For a grazing flyby (r_p → 0), the Δv magnitude approaches
    2 v_∞ — the classical upper bound (Vallado 4th ed §12.3)."""

    GM_JUP = 1.26686534e17  # Juno (Iess 2018)
    R_JUP_M = 6.9911e7  # IAU 2015 B3

    def test_slingshot_tight_flyby_approaches_2vinf(self) -> None:
        v_inf = 10_000.0  # 10 km/s
        # Tight flyby at 1.1 R_Jupiter
        dv = slingshot_delta_v(
            v_infinity_m_s=v_inf,
            periapsis_radius_m=1.1 * self.R_JUP_M,
            body_gravitational_parameter_m3_s2=self.GM_JUP,
        )
        # Should be within ~20% of 2 v_inf = 20 km/s
        assert 1.4 * v_inf < dv < 2.0 * v_inf, dv

    def test_slingshot_distant_flyby_small(self) -> None:
        v_inf = 10_000.0
        # Very distant flyby at 1000 R_Jupiter — tiny bend
        dv = slingshot_delta_v(
            v_infinity_m_s=v_inf,
            periapsis_radius_m=1000.0 * self.R_JUP_M,
            body_gravitational_parameter_m3_s2=self.GM_JUP,
        )
        # Should be a small fraction of 2 v_inf
        assert dv < 0.2 * v_inf, dv


# ─────────────────────────────────────────────────────────────────────
# Extra: Δv budget aggregation + margin discipline
# ─────────────────────────────────────────────────────────────────────


class TestDeltaVBudget:
    def test_empty_budget_not_closed(self) -> None:
        b = DepartureDeltaVBudget(target_delta_v_m_s=30_000.0)
        assert not b.is_closed
        assert b.total_delta_v_m_s == 0.0
        assert b.margin_m_s == pytest.approx(-33_000.0, rel=1e-6)

    def test_budget_with_margin(self) -> None:
        b = DepartureDeltaVBudget(
            target_delta_v_m_s=3.0e7, design_margin_fraction=0.10
        )
        b.add_leo_escape(3_200.0)
        b.add_fusion_burn(1.0e4)
        b.add_slingshot("jupiter", 1.0e4)
        b.add_oberth_burn(2.0e4)
        # Laser push carries the bulk; needs to cover target + 10% margin
        # minus the small chemical/fusion/slingshot/oberth contributions
        # (~43 km/s ≪ 30 000 km/s target, so laser does essentially all of it).
        b.add_laser_push(3.3e7)
        summary = b.summary()
        assert summary["total_delta_v_m_s"] > summary["required_with_margin_m_s"]
        assert summary["is_closed"] is True

    def test_duplicate_segment_rejected(self) -> None:
        b = DepartureDeltaVBudget(target_delta_v_m_s=1.0)
        b.add_fusion_burn(100.0)
        with pytest.raises(ValueError, match="already recorded"):
            b.add_fusion_burn(200.0)

    def test_negative_contribution_rejected(self) -> None:
        b = DepartureDeltaVBudget(target_delta_v_m_s=1.0)
        with pytest.raises(ValueError, match="non-negative"):
            b.add_segment("bad", -1.0)


# ─────────────────────────────────────────────────────────────────────
# Extra: Tsiolkovsky sanity
# ─────────────────────────────────────────────────────────────────────


class TestTsiolkovskyInvariants:
    def test_zero_propellant_zero_delta_v(self) -> None:
        with pytest.raises(ValueError):
            # final_mass >= initial_mass is a propellant-free burn,
            # which is a contract violation.
            tsiolkovsky_delta_v(1000.0, 1000.0, 3000.0)

    def test_higher_isp_gives_more_delta_v(self) -> None:
        dv_low = tsiolkovsky_delta_v(1000.0, 500.0, 3000.0)
        dv_high = tsiolkovsky_delta_v(1000.0, 500.0, 6000.0)
        assert dv_high == pytest.approx(2.0 * dv_low, rel=1e-12)

    def test_stacked_matches_sum(self) -> None:
        stages = [
            (10_000.0, 5_000.0, 4_500.0),
            (4_000.0, 2_000.0, 4_500.0),
            (1_500.0, 800.0, 4_500.0),
        ]
        total = stacked_delta_v(stages)
        expected = sum(
            tsiolkovsky_delta_v(m0, mf, ve) for (m0, mf, ve) in stages
        )
        assert total == pytest.approx(expected, rel=1e-12)


# ─────────────────────────────────────────────────────────────────────
# Extra: v_∞ identities
# ─────────────────────────────────────────────────────────────────────


class TestVInfinityIdentities:
    def test_exactly_escape_gives_zero_v_infinity(self) -> None:
        r = 6.778e6
        v_esc = escape_velocity(GM_EARTH_M3_S2, r)
        v_inf = v_infinity_from_v(v_esc, GM_EARTH_M3_S2, r)
        assert v_inf == pytest.approx(0.0, abs=1e-6)

    def test_bound_raises(self) -> None:
        r = 6.778e6
        # Below escape speed → bound orbit, should raise.
        bound_speed = 0.9 * escape_velocity(GM_EARTH_M3_S2, r)
        with pytest.raises(ValueError):
            v_infinity_from_v(bound_speed, GM_EARTH_M3_S2, r)
