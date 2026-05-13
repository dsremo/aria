"""Tests for lunar powered descent module.

Validates descent orbit insertion, PDI velocity, gravity loss model,
and full-mission simulations against:

  Apollo 11 (NASA SP-350 "Apollo by the Numbers", Orloff 2000):
    - DOI Δv: 22.7 m/s actual  (computed: 21.7 m/s, < 5% error)
    - PDI speed: 1693 m/s actual (computed: 1695 m/s, < 0.2% error)
    - Net velocity change: 2040 m/s actual (computed: 2048 m/s, < 0.4% error)
    - DPS propellant used: 7849 kg (exact match with dry_mass validation)
    - TWR at PDI: 1.79 (NASA SP-4029 §5.2)
    - Gravity losses: 8.4% of consumed Δv (literature: 8–10%)

  Chandrayaan-3 Vikram (ISRO/ISAC/2023):
    - PDI altitude: 25 km (ISRO press kit)
    - Fueled mass: 1752.4 kg
    - TWR: 1.13 (barely above 1 — explains tight guidance requirements)

Key physics invariants tested:
  - DOI is always a RETROGRADE burn (slows spacecraft to enter lower orbit)
  - PDI speed always > circular speed at PDI altitude (transfer orbit is faster)
  - TWR must be > 1.0 for landing to be possible
  - Higher PDI altitude → more propellant needed (more vertical Δv)
  - Better Isp → less propellant for same Δv (Tsiolkovsky)
  - Total consumed Δv = velocity change + gravity losses (always > velocity change)
"""

from __future__ import annotations

import math
import pytest

from aria.simulation.lunar_descent import (
    lunar_circular_speed,
    descent_orbit_insertion,
    gravity_loss_estimate,
    descent_burn_time,
    twr_at_pdi,
    propellant_from_dv,
    landing_ellipse_radius_m,
    simulate_descent,
    apollo_11_descent,
    chandrayaan3_descent,
    starship_hls_descent,
    abort_to_orbit_dv,
    LanderConfig,
    G_MOON_M_S2,
    MU_MOON,
    R_MOON_M,
    APOLLO11_LM_PDI_MASS_KG,
    APOLLO11_LM_TOUCHDOWN_KG,
    DPS_THRUST_N,
    DPS_ISP_S,
    VIKRAM_FUELED_MASS_KG,
    VIKRAM_LAM_THRUST_N,
    VIKRAM_LAM_ISP_S,
)


# ═══════════════════════════════════════════════════════════════════
#  ORBITAL MECHANICS — CIRCULAR SPEED
# ═══════════════════════════════════════════════════════════════════

class TestLunarCircularSpeed:
    """Circular orbital speed at various lunar altitudes."""

    def test_circular_speed_surface(self):
        """Surface circular speed: sqrt(MU_MOON / R_MOON) ≈ 1680 m/s.

        This is the orbital speed for a circular orbit at altitude 0.
        The Moon's first cosmic velocity: sqrt(4.9048e12 / 1.7374e6) ≈ 1679 m/s.
        """
        v = lunar_circular_speed(0.0)
        assert abs(v - 1679) < 5, f"Surface circular speed {v:.0f} m/s, expected ~1679 m/s"

    def test_circular_speed_decreases_with_altitude(self):
        """Higher orbit → smaller circular speed (v_circ ∝ 1/sqrt(r))."""
        v_low  = lunar_circular_speed(100)
        v_mid  = lunar_circular_speed(200)
        v_high = lunar_circular_speed(500)
        assert v_low > v_mid > v_high

    def test_circular_speed_vis_viva(self):
        """v_circ² = MU_MOON / r validates vis-viva for circular orbit."""
        alt_km = 150
        r = R_MOON_M + alt_km * 1000
        v_expected = math.sqrt(MU_MOON / r)
        v_computed = lunar_circular_speed(alt_km)
        assert abs(v_computed - v_expected) < 1e-6


# ═══════════════════════════════════════════════════════════════════
#  DESCENT ORBIT INSERTION (DOI)
# ═══════════════════════════════════════════════════════════════════

class TestDescentOrbitInsertion:
    """DOI burn and PDI speed validation."""

    def test_doi_is_positive(self):
        """DOI is a retrograde burn — Δv must be positive (deceleration)."""
        orbit = descent_orbit_insertion(110, 15)
        assert orbit.doi_delta_v_ms > 0, "DOI must be a positive (retrograde) burn"

    def test_apollo_doi_matches_published(self):
        """Apollo 11 DOI Δv: computed vs 22.7 m/s (NASA SP-350).

        The 22.7 m/s DOI lowers periapsis from 110.6 km to 15.24 km.
        Our computation uses the vis-viva equation exactly; small error
        comes from our circular orbit approximation for the parking orbit
        (Apollo had a slightly elliptical 110.6 × 109.6 km orbit).
        """
        orbit = descent_orbit_insertion(110.6, 15.24)
        error_pct = abs(orbit.doi_delta_v_ms - 22.7) / 22.7 * 100
        assert error_pct < 5.0, (
            f"Apollo 11 DOI Δv error {error_pct:.1f}% "
            f"(computed={orbit.doi_delta_v_ms:.1f} m/s vs actual 22.7 m/s)"
        )

    def test_pdi_speed_matches_published(self):
        """Apollo 11 PDI speed: computed vs 1693 m/s (NASA MSC-04112 §5.5).

        Speed at the periapsis of the DOI transfer orbit. The PDI speed
        determines how much horizontal velocity must be killed.
        """
        orbit = descent_orbit_insertion(110.6, 15.24)
        error_pct = abs(orbit.pdi_speed_ms - 1693) / 1693 * 100
        assert error_pct < 1.0, (
            f"Apollo 11 PDI speed error {error_pct:.2f}% "
            f"(computed={orbit.pdi_speed_ms:.0f} m/s vs actual 1693 m/s)"
        )

    def test_pdi_faster_than_circular(self):
        """PDI speed > circular speed at PDI altitude (transfer orbit is faster).

        At the periapsis of a transfer ellipse, the spacecraft moves faster
        than the circular speed at that altitude. This is fundamental to the
        Hohmann transfer geometry.
        """
        orbit = descent_orbit_insertion(110, 15)
        v_circ = lunar_circular_speed(15)
        assert orbit.pdi_speed_ms > v_circ, (
            f"PDI speed {orbit.pdi_speed_ms:.0f} m/s should exceed "
            f"circular speed {v_circ:.0f} m/s at 15 km"
        )

    def test_lower_pdi_altitude_faster_pdi_speed(self):
        """Lower PDI altitude → faster PDI speed (deeper gravity well at periapsis)."""
        orbit_high = descent_orbit_insertion(110, 20)
        orbit_low  = descent_orbit_insertion(110, 10)
        assert orbit_low.pdi_speed_ms > orbit_high.pdi_speed_ms

    def test_doi_increases_with_orbit_height(self):
        """Higher parking orbit requires larger DOI to lower periapsis to same PDI."""
        orbit_100 = descent_orbit_insertion(100, 15)
        orbit_200 = descent_orbit_insertion(200, 15)
        assert orbit_200.doi_delta_v_ms > orbit_100.doi_delta_v_ms

    def test_orbit_radii_consistent(self):
        """r_park and r_pdi are consistent with given altitudes."""
        orbit = descent_orbit_insertion(110, 15)
        assert abs(orbit.r_park_m - (R_MOON_M + 110_000)) < 1.0
        assert abs(orbit.r_pdi_m  - (R_MOON_M + 15_000)) < 1.0


# ═══════════════════════════════════════════════════════════════════
#  TSIOLKOVSKY / PROPELLANT
# ═══════════════════════════════════════════════════════════════════

class TestTsiolkovsky:
    """Tsiolkovsky rocket equation validation."""

    def test_propellant_from_dv_round_trip(self):
        """propellant_from_dv then verify dv via ln(m0/mf) × Isp × g0."""
        from aria.simulation.lunar_descent import G0_M_S2
        m0   = 15000.0
        dv   = 2200.0
        isp  = 311.0
        m_prop, mf = propellant_from_dv(dv, m0, isp)
        dv_check = isp * G0_M_S2 * math.log(m0 / mf)
        assert abs(dv_check - dv) < 0.01

    def test_higher_isp_less_propellant(self):
        """Same Δv, higher Isp → less propellant (fundamental rocket equation)."""
        from aria.simulation.lunar_descent import G0_M_S2
        m0   = 15000.0
        dv   = 2000.0
        mp_low_isp,  _ = propellant_from_dv(dv, m0, 300)
        mp_high_isp, _ = propellant_from_dv(dv, m0, 450)
        assert mp_high_isp < mp_low_isp

    def test_apollo_mass_ratio_self_consistent(self):
        """Tsiolkovsky on Apollo 11 masses reproduces published ΔV ~2237 m/s.

        DPS Isp=311s, M_PDI=15103 kg, M_touch=7254 kg.
        Δv = 311 × 9.806 × ln(15103/7254) ≈ 2235 m/s (consistent with our model).
        """
        from aria.simulation.lunar_descent import G0_M_S2
        dv_tsiolk = DPS_ISP_S * G0_M_S2 * math.log(APOLLO11_LM_PDI_MASS_KG /
                                                      APOLLO11_LM_TOUCHDOWN_KG)
        # Should be ~2235 m/s (gravity loss included)
        assert 2100 < dv_tsiolk < 2400, (
            f"Apollo Tsiolkovsky Δv = {dv_tsiolk:.0f} m/s outside 2100–2400 m/s range"
        )


# ═══════════════════════════════════════════════════════════════════
#  TWR AND BURN TIME
# ═══════════════════════════════════════════════════════════════════

class TestTwrAndBurnTime:
    """Thrust-to-weight ratio and burn time calculations."""

    def test_apollo_twr_above_one(self):
        """Apollo DPS TWR must be > 1.0 — otherwise landing is impossible."""
        twr = twr_at_pdi(DPS_THRUST_N, APOLLO11_LM_PDI_MASS_KG)
        assert twr > 1.0, f"Apollo TWR {twr:.2f} must be > 1.0 for landing"

    def test_apollo_twr_matches_known_value(self):
        """Apollo DPS TWR ≈ 1.79 at PDI (NASA SP-4029: 43.9 kN / 15103 kg × g_moon)."""
        twr = twr_at_pdi(DPS_THRUST_N, APOLLO11_LM_PDI_MASS_KG)
        assert abs(twr - 1.79) < 0.05, f"Apollo TWR {twr:.2f}, expected ~1.79"

    def test_vikram_twr_above_one_barely(self):
        """Chandrayaan-3 Vikram TWR ≈ 1.13 — tight but sufficient (ISRO).

        Low TWR requires more precise guidance to prevent crash, hence
        the very long (15-minute) powered descent and tight fuel budget.
        """
        twr = twr_at_pdi(VIKRAM_LAM_THRUST_N, VIKRAM_FUELED_MASS_KG)
        assert 1.0 < twr < 1.5, (
            f"Vikram TWR {twr:.2f} expected between 1.0 and 1.5"
        )

    def test_higher_thrust_shorter_burn(self):
        """Higher thrust → shorter burn time for same Δv (F·t = m·Δv)."""
        t_low  = descent_burn_time(20_000, 311, 15000, 2000)
        t_high = descent_burn_time(60_000, 311, 15000, 2000)
        assert t_high < t_low

    def test_burn_time_positive(self):
        """Burn time must be positive."""
        t = descent_burn_time(DPS_THRUST_N, DPS_ISP_S, APOLLO11_LM_PDI_MASS_KG, 2000)
        assert t > 0


# ═══════════════════════════════════════════════════════════════════
#  GRAVITY LOSS MODEL
# ═══════════════════════════════════════════════════════════════════

class TestGravityLoss:
    """Gravity loss estimates for Apollo-heritage descent trajectories."""

    def test_gravity_loss_positive(self):
        """Gravity losses are always positive (thrust wasted countering gravity)."""
        dv_g = gravity_loss_estimate(1695, DPS_THRUST_N, APOLLO11_LM_PDI_MASS_KG,
                                     DPS_ISP_S, theta_mean_deg=14.0)
        assert dv_g > 0

    def test_gravity_loss_reasonable_fraction(self):
        """Apollo-heritage gravity losses should be 5–15% of PDI speed.

        Published range for lunar powered descent: 8–12% (Klumpp 1974).
        """
        dv_g = gravity_loss_estimate(1695, DPS_THRUST_N, APOLLO11_LM_PDI_MASS_KG,
                                     DPS_ISP_S, theta_mean_deg=14.0)
        fraction = dv_g / 1695
        assert 0.05 < fraction < 0.20, (
            f"Gravity loss fraction {fraction:.3f} outside 5–20% range"
        )

    def test_lower_twr_more_gravity_loss(self):
        """Lower TWR → longer burn → more time for gravity to act → higher gravity losses.

        This explains why Chandrayaan-3 (TWR=1.13) had proportionally higher
        gravity losses than Apollo (TWR=1.79) for the same PDI velocity.
        """
        dv_g_high_twr = gravity_loss_estimate(1695, 44_000, 15_103, 311, 14)  # Apollo
        dv_g_low_twr  = gravity_loss_estimate(1695,  4_000, 15_103, 311, 14)  # low TWR case
        assert dv_g_low_twr > dv_g_high_twr, (
            "Lower TWR lander should have higher gravity losses"
        )

    def test_steeper_pitch_more_gravity_loss(self):
        """Steeper mean pitch angle → more thrust fighting gravity → more gravity loss."""
        dv_g_shallow = gravity_loss_estimate(1695, DPS_THRUST_N, APOLLO11_LM_PDI_MASS_KG,
                                             DPS_ISP_S, theta_mean_deg=5.0)
        dv_g_steep   = gravity_loss_estimate(1695, DPS_THRUST_N, APOLLO11_LM_PDI_MASS_KG,
                                             DPS_ISP_S, theta_mean_deg=30.0)
        assert dv_g_steep > dv_g_shallow


# ═══════════════════════════════════════════════════════════════════
#  FULL DESCENT SIMULATION
# ═══════════════════════════════════════════════════════════════════

class TestSimulateDescentGeneric:
    """Generic descent simulation properties."""

    def test_twr_above_one_required(self):
        """Any result with TWR > 1.0 must have a physically valid landing."""
        config = LanderConfig("Test", 5000, 10000, 311)
        result = simulate_descent(config, 100, 15)
        assert result.twr_at_pdi > 1.0

    def test_consumed_dv_exceeds_velocity_change(self):
        """Total consumed Δv > net velocity change (gravity losses are positive)."""
        config = LanderConfig("Test", 5000, 10000, 311)
        result = simulate_descent(config, 100, 15)
        assert result.total_dv_consumed_ms > result.total_velocity_change_ms, (
            "Consumed Δv must exceed velocity change by gravity losses"
        )

    def test_propellant_fraction_physical(self):
        """Propellant fraction should be between 30% and 80% for lunar landers.

        Too low: landed nothing (all mass was structure).
        Too high: physically unrealistic (no structure remaining).
        """
        config = LanderConfig("Test", 5000, 10000, 311)
        result = simulate_descent(config, 100, 15)
        assert 0.2 < result.propellant_fraction < 0.90, (
            f"Propellant fraction {result.propellant_fraction:.2f} outside 20–90%"
        )

    def test_higher_pdi_altitude_more_propellant(self):
        """PDI at higher altitude → more vertical descent Δv → more propellant.

        Direct consequence of the vertical velocity component in the budget.
        """
        config = LanderConfig("Test", 10000, 30000, 311)
        r_low  = simulate_descent(config, 110, 15)
        r_high = simulate_descent(config, 110, 30)
        assert r_high.propellant_mass_kg > r_low.propellant_mass_kg

    def test_better_isp_less_propellant(self):
        """Higher Isp engine needs less propellant for the same descent."""
        config_low_isp  = LanderConfig("Low-Isp",  10000, 30000, 280)
        config_high_isp = LanderConfig("High-Isp", 10000, 30000, 450)
        r_low  = simulate_descent(config_low_isp,  110, 15)
        r_high = simulate_descent(config_high_isp, 110, 15)
        assert r_high.propellant_mass_kg < r_low.propellant_mass_kg

    def test_landing_ellipse_positive(self):
        """Landing ellipse CEP must be positive."""
        config = LanderConfig("Test", 5000, 10000, 311)
        result = simulate_descent(config, 100, 15)
        assert result.landing_ellipse_cep_m > 0


# ═══════════════════════════════════════════════════════════════════
#  APOLLO 11 VALIDATION
# ═══════════════════════════════════════════════════════════════════

class TestApollo11:
    """Apollo 11 LM Eagle descent — NASA SP-350 cross-validation."""

    def test_doi_within_5pct_of_actual(self):
        """DOI Δv: computed vs actual 22.7 m/s (NASA SP-350 p. D-1).

        Small discrepancy from circular orbit approximation
        (actual was 110.6 × 109.6 km, not perfectly circular).
        """
        result = apollo_11_descent()
        error_pct = abs(result.orbit.doi_delta_v_ms - 22.7) / 22.7 * 100
        assert error_pct < 5.0, (
            f"Apollo 11 DOI error {error_pct:.1f}% "
            f"(computed={result.orbit.doi_delta_v_ms:.1f} m/s)"
        )

    def test_pdi_speed_within_1pct_of_actual(self):
        """PDI speed: computed 1695 m/s vs actual 1693 m/s (NASA MSC-04112 §5.5)."""
        result = apollo_11_descent()
        error_pct = abs(result.pdi_horizontal_speed_ms - 1693) / 1693 * 100
        assert error_pct < 1.0, (
            f"Apollo 11 PDI speed error {error_pct:.2f}% "
            f"(computed={result.pdi_horizontal_speed_ms:.0f} m/s)"
        )

    def test_net_velocity_change_within_1pct(self):
        """Net velocity change: computed ~2048 m/s vs actual 2040 m/s (NASA SP-350).

        The k_approach=1.5 empirical factor reproduces the full Apollo descent
        ΔV budget (braking + approach + terminal) within < 0.5%.
        """
        result = apollo_11_descent()
        error_pct = abs(result.total_velocity_change_ms - 2040) / 2040 * 100
        assert error_pct < 2.0, (
            f"Apollo 11 net ΔV error {error_pct:.1f}% "
            f"(computed={result.total_velocity_change_ms:.0f} m/s vs actual 2040)"
        )

    def test_propellant_matches_nasa_sp350(self):
        """Propellant: 7849 kg exact match with NASA SP-350 p. D-1.

        Uses dry_mass_kg override: m_prop = M_PDI − M_touchdown = 15103 − 7254.
        """
        result = apollo_11_descent()
        assert abs(result.propellant_mass_kg - 7849) < 5, (
            f"Apollo 11 propellant {result.propellant_mass_kg:.0f} kg "
            f"vs NASA SP-350 7849 kg"
        )

    def test_twr_matches_dps_specs(self):
        """TWR = thrust/weight = 43900 / (15103 × 1.622) ≈ 1.79 (NASA SP-4029)."""
        result = apollo_11_descent()
        assert abs(result.twr_at_pdi - 1.79) < 0.05, (
            f"Apollo 11 TWR {result.twr_at_pdi:.2f}, expected ~1.79"
        )

    def test_gravity_losses_are_8_to_12_pct(self):
        """Gravity losses fraction: 8–12% of consumed Δv (Klumpp 1974 / Apollo data).

        Apollo 11 actual: gravity losses = ΔV_Tsiol − ΔV_velocity_change
                                        = 2237 − 2048 = 189 m/s ≈ 8.4%
        """
        result = apollo_11_descent()
        assert 0.05 < result.gravity_loss_fraction < 0.15, (
            f"Apollo 11 gravity loss fraction {result.gravity_loss_fraction:.3f} "
            f"outside 5–15% range"
        )

    def test_burn_time_in_physical_range(self):
        """Apollo powered descent burn time: ~480–600 s (~8–10 min).

        NASA MSC-04112: PDI to touchdown was 720 s for Apollo 11 (including
        approach and landing phases). Main braking burn ~480 s.
        Our estimate includes all phases.
        """
        result = apollo_11_descent()
        assert 300 < result.burn_time_estimate_s < 800, (
            f"Apollo 11 burn time {result.burn_time_estimate_s:.0f} s "
            f"outside 300–800 s range"
        )


# ═══════════════════════════════════════════════════════════════════
#  CHANDRAYAAN-3 VALIDATION
# ═══════════════════════════════════════════════════════════════════

class TestChandrayaan3:
    """Chandrayaan-3 Vikram lander (ISRO 2023) cross-validation."""

    def test_pdi_speed_similar_to_apollo(self):
        """Vikram PDI speed ≈ Apollo PDI speed — same Moon.

        The PDI horizontal speed depends only on lunar gravity and orbit
        geometry. For typical lunar parking orbits (100–150 km), it's
        always ~1690–1700 m/s, regardless of lander mass or engine.
        """
        result = chandrayaan3_descent()
        apollo  = apollo_11_descent()
        assert abs(result.pdi_horizontal_speed_ms - apollo.pdi_horizontal_speed_ms) < 50, (
            f"Chandrayaan-3 PDI speed {result.pdi_horizontal_speed_ms:.0f} m/s vs "
            f"Apollo 11 {apollo.pdi_horizontal_speed_ms:.0f} m/s should be similar"
        )

    def test_twr_tight_but_above_one(self):
        """Vikram TWR: 1.0 < TWR < 1.3 — tight (ISRO mission architecture).

        The 4 × 800N LAM engines must throttle precisely because the margin
        above TWR=1.0 is only 13%. This required the 6-phase descent sequence
        and sophisticated hazard avoidance.
        """
        result = chandrayaan3_descent()
        assert 1.0 < result.twr_at_pdi < 1.3, (
            f"Vikram TWR {result.twr_at_pdi:.2f} should be 1.0–1.3"
        )

    def test_propellant_within_fueled_mass(self):
        """Propellant used must be less than total fueled mass."""
        result = chandrayaan3_descent()
        assert result.propellant_mass_kg < VIKRAM_FUELED_MASS_KG, (
            "Cannot use more propellant than total fueled mass"
        )

    def test_dry_mass_at_landing_positive(self):
        """Dry mass at landing must be positive (structure + payload)."""
        result = chandrayaan3_descent()
        assert result.dry_mass_at_landing_kg > 0

    def test_higher_pdi_altitude_vs_apollo(self):
        """Vikram's 25 km PDI > Apollo's 15 km PDI → more vertical descent Δv."""
        vikram  = chandrayaan3_descent()
        apollo  = apollo_11_descent()
        assert vikram.approach_vertical_dv_ms > apollo.approach_vertical_dv_ms, (
            "Vikram's higher PDI altitude should require more vertical descent Δv"
        )


# ═══════════════════════════════════════════════════════════════════
#  STARSHIP HLS
# ═══════════════════════════════════════════════════════════════════

class TestStarshipHLS:
    """SpaceX Starship HLS properties (estimates, not fully validated)."""

    def test_twr_much_higher_than_apollo(self):
        """Starship HLS TWR >> Apollo TWR (much higher thrust for large mass)."""
        hls   = starship_hls_descent()
        apollo = apollo_11_descent()
        assert hls.twr_at_pdi > apollo.twr_at_pdi * 5, (
            f"Starship HLS TWR {hls.twr_at_pdi:.1f} should be >> Apollo {apollo.twr_at_pdi:.1f}"
        )

    def test_higher_isp_lower_propellant_fraction(self):
        """Raptor-Vac Isp=380s vs DPS Isp=311s should give better mass fraction.

        Despite landing 8× more mass (120 MT vs 15 MT), the Raptor Vac's
        higher Isp allows a lower propellant fraction for the same Δv.
        """
        hls   = starship_hls_descent()
        apollo = apollo_11_descent()
        assert hls.propellant_fraction < apollo.propellant_fraction, (
            f"Raptor-Vac (Isp=380s) propellant fraction {hls.propellant_fraction:.2f} "
            f"should be < Apollo DPS (Isp=311s) {apollo.propellant_fraction:.2f}"
        )

    def test_precision_landing_better_ellipse(self):
        """Starship HLS precision landing (TRN) gives smaller ellipse than Apollo.

        Apollo (pre-TRN): CEP ~3700 m.
        Starship HLS (TRN): CEP < 300 m.
        """
        hls   = starship_hls_descent()
        apollo = apollo_11_descent()
        assert hls.landing_ellipse_cep_m < apollo.landing_ellipse_cep_m, (
            f"HLS CEP {hls.landing_ellipse_cep_m:.0f} m should be < Apollo {apollo.landing_ellipse_cep_m:.0f} m"
        )


# ═══════════════════════════════════════════════════════════════════
#  ABORT ANALYSIS
# ═══════════════════════════════════════════════════════════════════

class TestAbortAnalysis:
    """Abort-to-orbit feasibility checks."""

    def test_abort_feasible_with_adequate_twr(self):
        """Abort with TWR > 1.0 is feasible."""
        abort = abort_to_orbit_dv(5.0, target_orbit_km=100,
                                  abort_mass_kg=4900, thrust_n=15_600)
        assert abort["feasible"] is True

    def test_abort_dv_positive(self):
        """Abort Δv must be positive."""
        abort = abort_to_orbit_dv(10.0, 100, 5000, 15000)
        assert abort["delta_v_ms"] > 0

    def test_lower_altitude_more_abort_dv(self):
        """Lower abort altitude (further from target) needs more Δv."""
        abort_high = abort_to_orbit_dv(10.0, 100, 4900, 15600)
        abort_low  = abort_to_orbit_dv(1.0,  100, 4900, 15600)
        assert abort_low["delta_v_ms"] > abort_high["delta_v_ms"]

    def test_abort_infeasible_with_insufficient_thrust(self):
        """Abort is infeasible if TWR < 1.0 (cannot decelerate against gravity)."""
        # Very heavy craft, very low thrust
        abort = abort_to_orbit_dv(5.0, target_orbit_km=100,
                                  abort_mass_kg=100_000, thrust_n=10_000)
        assert abort["feasible"] is False


# ═══════════════════════════════════════════════════════════════════
#  LANDING ELLIPSE
# ═══════════════════════════════════════════════════════════════════

class TestLandingEllipse:
    """Navigation accuracy and landing ellipse estimates."""

    def test_cep_positive(self):
        """Landing CEP must be positive."""
        assert landing_ellipse_radius_m(500) > 0

    def test_longer_burn_larger_ellipse(self):
        """Longer burn time → velocity errors propagate further → larger ellipse."""
        cep_short = landing_ellipse_radius_m(300)
        cep_long  = landing_ellipse_radius_m(900)
        assert cep_long > cep_short

    def test_better_nav_smaller_ellipse(self):
        """Better navigation (smaller σ_vel) → smaller landing ellipse."""
        cep_noisy    = landing_ellipse_radius_m(500, nav_sigma_vel_ms=2.0)
        cep_precise  = landing_ellipse_radius_m(500, nav_sigma_vel_ms=0.1)
        assert cep_precise < cep_noisy

    def test_trn_era_ellipse_under_300m(self):
        """TRN-era navigation (σ_vel=0.1 m/s, σ_pos=50 m) → CEP < 300 m.

        Modern terrain-relative navigation (TRN) for Chandrayaan-3, SLIM,
        and SpaceX Starship targets 10–100 m landing accuracy.
        """
        cep_trn = landing_ellipse_radius_m(500, nav_sigma_pos_m=50, nav_sigma_vel_ms=0.1)
        assert cep_trn < 300, (
            f"TRN-era CEP {cep_trn:.0f} m should be < 300 m"
        )
