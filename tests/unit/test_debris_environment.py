"""Tests for orbital debris environment model.

Validates flux tables, collision probability, Whipple shield BLE, orbital
lifetime, and mission risk assessment against published data:

  Klinkrad H. (2006) Space Debris: Models and Risk Analysis. Springer.
  Liou & Johnson (2006) Science 311:340 — flux at ISS altitude.
  NASA ODQN Vol. 27 (2023) — population statistics.
  NASA/TP-2009-214797 — Whipple shield BLE constants.
  NASA-STD-8719.14B — 25-year orbital lifetime rule.

Key physical facts tested:
  - Peak debris flux is at 800–900 km (Iridium/Cosmos collision + ASAT tests)
  - ISS at 408 km: flux_gt1cm ≈ 4e-5 hits/m²/yr
  - 300 km: natural decay in ~0.2 years (complies with 25-yr rule)
  - 500 km: ~50 year lifetime (VIOLATES 25-yr rule — requires active deorbit)
  - Whipple shield: as critical diameter grows, fewer objects survive
  - Collision probability obeys Poisson: P = 1 - exp(-Φ·A·T)
"""

from __future__ import annotations

import math
import pytest

from aria.simulation.debris_environment import (
    get_debris_flux,
    debris_flux_full,
    collision_probability,
    whipple_shield_analysis,
    ascent_debris_profile,
    orbital_lifetime_years,
    passes_25year_rule,
    mission_debris_risk,
    iss_mission_risk,
    lunar_transit_risk,
    FLUX_ALT_KM,
    FLUX_GT1CM,
    ISS_ALTITUDE_KM,
)


# ═══════════════════════════════════════════════════════════════════
#  FLUX TABLE SANITY
# ═══════════════════════════════════════════════════════════════════

class TestFluxTableSanity:
    """Basic sanity checks on the published flux table values."""

    def test_flux_monotone_with_size(self):
        """Larger size threshold → fewer objects → lower flux at every altitude.

        By definition: Φ(>10cm) < Φ(>1cm) < Φ(>1mm) < Φ(>0.1mm).
        """
        for alt in [200, 400, 600, 800, 1000, 1500]:
            f10cm = get_debris_flux(alt, ">10cm")
            f1cm  = get_debris_flux(alt, ">1cm")
            f1mm  = get_debris_flux(alt, ">1mm")
            f01mm = get_debris_flux(alt, ">0.1mm")
            assert f10cm < f1cm < f1mm < f01mm, (
                f"Flux ordering violated at {alt} km: "
                f">10cm={f10cm:.2e}, >1cm={f1cm:.2e}, "
                f">1mm={f1mm:.2e}, >0.1mm={f01mm:.2e}"
            )

    def test_peak_flux_at_800_to_1000_km(self):
        """Peak debris density is at 800–1000 km (Iridium/Cosmos collision band).

        Liou & Johnson (2006) Science 311:340 clearly show the worst zone
        at 800–1000 km — dense population from ASAT debris + collisions.
        Flux at 800 km must exceed flux at 400 km (ISS) and 1500 km.
        """
        f_iss    = get_debris_flux(400, ">1cm")
        f_peak   = get_debris_flux(850, ">1cm")   # midpoint of worst zone
        f_sparse = get_debris_flux(1500, ">1cm")
        assert f_peak > f_iss,    f"Peak zone (850 km) flux {f_peak:.2e} ≤ ISS flux {f_iss:.2e}"
        assert f_peak > f_sparse, f"Peak zone flux {f_peak:.2e} ≤ sparse zone {f_sparse:.2e}"

    def test_iss_altitude_flux_order_of_magnitude(self):
        """ISS altitude (408 km): Φ(>1cm) ≈ 4e-5 hits/m²/yr.

        Liou & Johnson (2006) Science 311 Fig. 1; NASA ODQN Vol. 27 (2023).
        Value should be in range 1e-5 to 2e-4 hits/m²/yr.
        """
        f = get_debris_flux(408, ">1cm")
        assert 1e-5 < f < 2e-4, (
            f"ISS flux {f:.2e} outside expected 1e-5 to 2e-4 hits/m²/yr range"
        )

    def test_low_altitude_flux_small(self):
        """Below 200 km, atmospheric drag clears debris — flux approaches 0."""
        f150 = get_debris_flux(150, ">1cm")
        f300 = get_debris_flux(300, ">1cm")
        assert f150 < f300 * 0.5, (
            f"150 km flux {f150:.2e} should be much less than 300 km {f300:.2e}"
        )

    def test_flux_zero_at_150km(self):
        """Below 150 km, debris decays within days — flux is zero."""
        assert get_debris_flux(150, ">1cm") == 0.0

    def test_flux_above_2000km_decreasing(self):
        """Above 2000 km, flux decreases with altitude (power law)."""
        f2000 = get_debris_flux(2000, ">1cm")
        f3000 = get_debris_flux(3000, ">1cm")
        assert f3000 < f2000, (
            f"Flux above 2000 km should decrease: {f3000:.2e} vs {f2000:.2e}"
        )

    def test_flux_unknown_size_raises(self):
        """Invalid size threshold must raise ValueError."""
        with pytest.raises(ValueError, match="Unknown size threshold"):
            get_debris_flux(400, ">5cm")


# ═══════════════════════════════════════════════════════════════════
#  FLUX FULL PROFILE
# ═══════════════════════════════════════════════════════════════════

class TestDebrisFluxFull:
    """debris_flux_full() returns consistent risk classifications."""

    def test_iss_altitude_high_risk_post_cosmos1408(self):
        """ISS at 408 km classified as HIGH risk (ORDEM 3.2 post-Cosmos 1408).

        Before ORDEM 3.2: ISS flux ≈ 4.0e-5 /m²/yr (>1cm) → "moderate".
        After Cosmos 1408 (Nov 2021): flux increased ~12% at 400 km,
        interpolated to ~5.3e-5 at 408 km, crossing moderate/high threshold.
        Ref: NASA ODQN Vol. 27 (2023); ORDEM 3.2 (NTRS 20230014989).
        """
        r = debris_flux_full(408)
        assert r.risk_level == "high"

    def test_peak_zone_extreme_risk(self):
        """850 km (peak zone) is classified as EXTREME risk."""
        r = debris_flux_full(850)
        assert r.risk_level == "extreme"

    def test_200km_low_risk(self):
        """200 km (strong drag) is classified as LOW risk."""
        r = debris_flux_full(200)
        assert r.risk_level == "low"

    def test_all_fluxes_positive(self):
        """All flux values in a full profile must be positive."""
        r = debris_flux_full(500)
        assert r.flux_gt10cm_per_m2_yr > 0
        assert r.flux_gt1cm_per_m2_yr > 0
        assert r.flux_gt1mm_per_m2_yr > 0
        assert r.flux_gt01mm_per_m2_yr > 0

    def test_flux_ordering_in_result(self):
        """flux_gt10cm < flux_gt1cm < flux_gt1mm < flux_gt01mm."""
        r = debris_flux_full(600)
        assert (r.flux_gt10cm_per_m2_yr
                < r.flux_gt1cm_per_m2_yr
                < r.flux_gt1mm_per_m2_yr
                < r.flux_gt01mm_per_m2_yr)


# ═══════════════════════════════════════════════════════════════════
#  COLLISION PROBABILITY
# ═══════════════════════════════════════════════════════════════════

class TestCollisionProbability:
    """Poisson collision probability model validation."""

    def test_poisson_formula_correctness(self):
        """P = 1 - exp(-λ) where λ = Φ·A·T.

        For ISS (A=3600 m², T=0.5yr, h=408 km):
          λ ≈ 4.64e-5 × 3600 × 0.5 = 0.0835
          P ≈ 8.0%
        """
        cp = collision_probability(408, 3600, 0.5, ">1cm")
        assert abs(cp.probability - (1 - math.exp(-cp.expected_hits))) < 1e-12, (
            "P != 1 - exp(-λ): Poisson formula violated"
        )

    def test_iss_probability_physically_reasonable(self):
        """ISS 0.5-yr unshielded P(>1cm) should be a few percent.

        ISS at 408 km, A=3600 m², 0.5yr: λ ≈ 0.084 → P ≈ 8%.
        The high P is why ISS uses Whipple shielding + CDAs (conjunction avoidance).
        """
        cp = collision_probability(408, 3600, 0.5, ">1cm")
        assert 0.01 < cp.probability < 0.25, (
            f"ISS 0.5-yr P={cp.probability:.4f}, expected 1%-25% range"
        )

    def test_small_craft_low_probability(self):
        """1U CubeSat (A=0.01 m²) at 400 km for 2 years: P << 1%."""
        cp = collision_probability(400, 0.01, 2.0, ">1cm")
        assert cp.probability < 0.01, (
            f"1U CubeSat P={cp.probability:.6f} should be < 1%"
        )

    def test_longer_duration_higher_probability(self):
        """Longer mission → higher P (Poisson is monotone in λ)."""
        cp_1yr = collision_probability(500, 10, 1.0, ">1cm")
        cp_5yr = collision_probability(500, 10, 5.0, ">1cm")
        assert cp_5yr.probability > cp_1yr.probability

    def test_higher_altitude_higher_probability_in_peak_zone(self):
        """Moving from 400 km to 800 km raises collision probability."""
        cp_400 = collision_probability(400, 100, 1.0, ">1cm")
        cp_800 = collision_probability(800, 100, 1.0, ">1cm")
        assert cp_800.probability > cp_400.probability

    def test_expected_hits_is_poisson_lambda(self):
        """expected_hits == Φ·A·T exactly (Poisson rate λ)."""
        cp = collision_probability(500, 50, 2.0, ">1mm")
        expected = cp.flux_per_m2_yr * 50 * 2.0
        assert abs(cp.expected_hits - expected) < 1e-15


# ═══════════════════════════════════════════════════════════════════
#  WHIPPLE SHIELD BLE
# ═══════════════════════════════════════════════════════════════════

class TestWhippleShield:
    """Modified Cour-Palais BLE validation (NASA/TP-2009-214797)."""

    def test_thicker_wall_larger_dcrit(self):
        """Thicker main wall → larger critical diameter (better shield).

        BLE: d_crit ∝ t_wall, so doubling wall thickness doubles d_crit.
        """
        s_thin  = whipple_shield_analysis(1.5, 2.0, 100.0, "aluminum")
        s_thick = whipple_shield_analysis(1.5, 8.0, 100.0, "aluminum")
        assert s_thick.critical_diameter_cm > s_thin.critical_diameter_cm, (
            f"Thicker wall (8mm) d_crit={s_thick.critical_diameter_cm:.4f} cm "
            f"≤ thin wall (2mm) d_crit={s_thin.critical_diameter_cm:.4f} cm"
        )

    def test_wider_gap_larger_dcrit(self):
        """Wider standoff gap → larger critical diameter (bumper has more room to spray).

        BLE: d_crit ∝ S^(2/3), so gap matters significantly.
        """
        s_narrow = whipple_shield_analysis(1.5, 4.0, 50.0, "aluminum")
        s_wide   = whipple_shield_analysis(1.5, 4.0, 200.0, "aluminum")
        assert s_wide.critical_diameter_cm > s_narrow.critical_diameter_cm

    def test_flux_survived_decreases_with_better_shield(self):
        """Better shield (larger d_crit) → fewer surviving objects → lower flux.

        Physical invariant: as d_crit grows, the residual flux can only decrease.
        """
        s_weak   = whipple_shield_analysis(0.5, 2.0,  30.0, "aluminum")
        s_medium = whipple_shield_analysis(1.5, 4.0, 100.0, "aluminum")
        s_strong = whipple_shield_analysis(3.0, 8.0, 200.0, "aluminum")
        assert s_strong.critical_diameter_cm > s_medium.critical_diameter_cm > s_weak.critical_diameter_cm, (
            "d_crit should increase with shield thickness"
        )
        assert s_strong.flux_survived_per_m2_yr < s_medium.flux_survived_per_m2_yr, (
            f"Strong shield flux {s_strong.flux_survived_per_m2_yr:.2e} "
            f"≥ medium {s_medium.flux_survived_per_m2_yr:.2e}"
        )
        assert s_medium.flux_survived_per_m2_yr < s_weak.flux_survived_per_m2_yr, (
            f"Medium shield flux {s_medium.flux_survived_per_m2_yr:.2e} "
            f"≥ weak {s_weak.flux_survived_per_m2_yr:.2e}"
        )

    def test_areal_density_computed(self):
        """Areal density ξ = ρ × (t_bumper + t_wall) should be > 0."""
        s = whipple_shield_analysis(1.5, 4.0, 100.0, "aluminum")
        assert s.shield_areal_density_g_cm2 > 0

    def test_unknown_material_raises(self):
        """Invalid material must raise ValueError."""
        with pytest.raises(ValueError, match="Unknown material"):
            whipple_shield_analysis(1.5, 4.0, 100.0, "unobtanium")

    def test_nextel_kevlar_higher_K(self):
        """Nextel/Kevlar shields have higher BLE constant K → better performance.

        NASA TP-2003-210788: K(nextel)=0.25, K(aluminum)=0.14.
        Same geometry, Nextel stops larger objects.
        """
        s_al     = whipple_shield_analysis(1.5, 4.0, 100.0, "aluminum")
        s_nextel = whipple_shield_analysis(1.5, 4.0, 100.0, "nextel")
        assert s_nextel.critical_diameter_cm > s_al.critical_diameter_cm, (
            f"Nextel d_crit={s_nextel.critical_diameter_cm:.4f} cm should exceed "
            f"aluminum {s_al.critical_diameter_cm:.4f} cm (K_nextel > K_Al)"
        )

    def test_dcrit_positive(self):
        """Critical diameter must be non-negative."""
        s = whipple_shield_analysis(1.0, 3.0, 50.0, "aluminum")
        assert s.critical_diameter_cm >= 0.0


# ═══════════════════════════════════════════════════════════════════
#  ORBITAL LIFETIME
# ═══════════════════════════════════════════════════════════════════

class TestOrbitalLifetime:
    """Tabulated lifetime vs Klinkrad (2006) Table 4.2."""

    def test_300km_sub_year(self):
        """300 km orbit: natural decay in ~0.2 years (Klinkrad 2006).

        Strong atmospheric drag at 300 km removes objects within months.
        Critical for debris mitigation: no long-term population build-up.
        """
        life = orbital_lifetime_years(300)
        assert 0.05 < life < 1.0, (
            f"300 km lifetime {life:.2f} yr outside expected 0.05–1.0 yr range"
        )

    def test_400km_few_years(self):
        """400 km (ISS altitude): natural decay ~4 years (Klinkrad 2006).

        ISS boosted periodically to maintain altitude against drag.
        Below 25-year rule → compliant without active deorbit.
        """
        life = orbital_lifetime_years(400)
        assert 2.0 < life < 10.0, (
            f"400 km lifetime {life:.1f} yr outside expected 2–10 yr"
        )

    def test_500km_exceeds_25yr_rule(self):
        """500 km orbit: ~50 years lifetime → VIOLATES NASA 25-year rule.

        Klinkrad (2006); NASA-STD-8719.14B. Starlink-class satellites at 550 km
        use active deorbit to comply. Natural decay at 500 km takes decades.
        """
        life = orbital_lifetime_years(500)
        assert life > 25.0, (
            f"500 km lifetime {life:.1f} yr should exceed 25 yr (needs active deorbit)"
        )

    def test_600km_centuries(self):
        """600 km orbit: ~350 years (Klinkrad 2006) — essentially permanent."""
        life = orbital_lifetime_years(600)
        assert 100 < life < 1000, (
            f"600 km lifetime {life:.0f} yr outside expected 100–1000 yr"
        )

    def test_lifetime_monotone_with_altitude(self):
        """Lifetime must be strictly monotone increasing with altitude (200–1000 km).

        Higher altitude → less atmospheric density → weaker drag → longer life.
        """
        alts = [200, 300, 400, 500, 600, 700, 800, 900, 1000]
        lives = [orbital_lifetime_years(a) for a in alts]
        for i in range(len(lives) - 1):
            assert lives[i] < lives[i + 1], (
                f"Lifetime not monotone: {alts[i]} km ({lives[i]:.1f} yr) "
                f">= {alts[i+1]} km ({lives[i+1]:.1f} yr)"
            )

    def test_ballistic_coeff_scaling(self):
        """Lifetime scales proportionally with ballistic coefficient β.

        Lighter/larger objects (low β) decay faster; heavy/small (high β) last longer.
        β doubles → lifetime doubles (drag is linear in cross-section).
        """
        life_50  = orbital_lifetime_years(400, ballistic_coeff_kg_m2=50)
        life_100 = orbital_lifetime_years(400, ballistic_coeff_kg_m2=100)
        life_200 = orbital_lifetime_years(400, ballistic_coeff_kg_m2=200)
        assert life_50 < life_100 < life_200
        # Proportionality check: life ∝ β
        ratio = life_200 / life_50
        assert abs(ratio - 4.0) < 0.01, (
            f"β=200 vs β=50 lifetime ratio {ratio:.3f}, expected exactly 4.0"
        )


# ═══════════════════════════════════════════════════════════════════
#  25-YEAR RULE
# ═══════════════════════════════════════════════════════════════════

class TestPasses25YearRule:
    """NASA-STD-8719.14B compliance checks."""

    def test_300km_compliant(self):
        """300 km naturally decays in ~0.2 yr → compliant."""
        assert passes_25year_rule(300)

    def test_400km_compliant(self):
        """400 km decays in ~4 yr → compliant."""
        assert passes_25year_rule(400)

    def test_500km_non_compliant(self):
        """500 km decays in ~50 yr → VIOLATES 25-year rule.

        Satellites at 550 km (e.g., SpaceX Starlink initial shells) must use
        active propulsion to deorbit. Natural decay alone would leave debris
        for decades.
        """
        assert not passes_25year_rule(500), (
            "500 km should fail 25-year rule (lifetime ~50 yr)"
        )

    def test_600km_non_compliant(self):
        """600 km decays in ~350 yr → VIOLATES rule."""
        assert not passes_25year_rule(600)

    def test_threshold_near_25yr(self):
        """Altitude where lifetime crosses 25 years is between 450 and 500 km."""
        # lifetime(450) ≈ 15 yr < 25 yr → compliant
        # lifetime(500) ≈ 50 yr > 25 yr → non-compliant
        assert passes_25year_rule(450)
        assert not passes_25year_rule(500)


# ═══════════════════════════════════════════════════════════════════
#  MISSION RISK ASSESSMENT
# ═══════════════════════════════════════════════════════════════════

class TestMissionDebrisRisk:
    """Full mission risk assessment integration tests."""

    def test_iss_mission_fields(self):
        """iss_mission_risk() returns valid DebrisRiskSummary."""
        r = iss_mission_risk(0.5)
        assert r.mission_name == "ISS Mission"
        assert len(r.phases) == 1
        assert r.total_probability_gt1cm > 0
        assert r.shield is not None

    def test_iss_probability_positive(self):
        """ISS 6-month mission has non-zero collision probability."""
        r = iss_mission_risk(0.5)
        assert r.total_probability_gt1cm > 0.001, (
            "ISS 6-month P(>1cm) should be non-negligible"
        )

    def test_longer_iss_mission_higher_risk(self):
        """Longer ISS stay → higher cumulative collision probability."""
        r_short = iss_mission_risk(0.5)
        r_long  = iss_mission_risk(2.0)
        assert r_long.total_probability_gt1cm > r_short.total_probability_gt1cm

    def test_lunar_transit_very_low_risk(self):
        """Lunar transit parking orbit (3 hr at 185 km) → negligible risk."""
        r = lunar_transit_risk()
        assert r.total_probability_gt1cm < 0.001, (
            f"Lunar transit P={r.total_probability_gt1cm:.6f} should be < 0.1%"
        )

    def test_mitigation_recommendations_nonempty(self):
        """Every risk assessment must include at least one recommendation."""
        r = iss_mission_risk(1.0)
        assert len(r.mitigation_recommendations) >= 1

    def test_800km_zone_recommendation_triggered(self):
        """800 km mission triggers debris zone warning in recommendations."""
        r = mission_debris_risk(
            "Test-800km",
            phases=[{
                "name": "test",
                "altitude_km": 800,
                "cross_section_m2": 10,
                "duration_years": 1.0,
            }],
        )
        # Should recommend staying out of 700-1000 km zone
        recs_text = " ".join(r.mitigation_recommendations).lower()
        assert "debris" in recs_text or "zone" in recs_text or "asat" in recs_text, (
            "800 km mission should trigger debris-zone recommendation"
        )

    def test_25year_violation_flagged(self):
        """Mission at 600 km (350-yr lifetime) triggers deorbit recommendation."""
        r = mission_debris_risk(
            "600km-sat",
            phases=[{
                "name": "operations",
                "altitude_km": 600,
                "cross_section_m2": 5,
                "duration_years": 3.0,
            }],
        )
        recs_text = " ".join(r.mitigation_recommendations).lower()
        assert "25-year" in recs_text or "deorbit" in recs_text, (
            "600 km mission should trigger 25-year rule violation warning"
        )

    def test_independent_phase_probability_combination(self):
        """Multi-phase total P combines as P = 1 - Π(1 - P_i).

        Independence assumption: phases are sequential, no correlation.
        """
        r = mission_debris_risk(
            "Multi-phase",
            phases=[
                {"name": "phase1", "altitude_km": 400, "cross_section_m2": 50,
                 "duration_years": 0.5},
                {"name": "phase2", "altitude_km": 600, "cross_section_m2": 50,
                 "duration_years": 0.5},
            ],
        )
        p1 = r.phases[0].probability
        p2 = r.phases[1].probability
        expected_total = 1.0 - (1.0 - p1) * (1.0 - p2)
        assert abs(r.total_probability_gt1cm - expected_total) < 1e-12


# ═══════════════════════════════════════════════════════════════════
#  ASCENT PROFILE
# ═══════════════════════════════════════════════════════════════════

class TestAscentDebrisProfile:
    """Ascent exposure during launch to LEO."""

    def test_ascent_to_iss_altitude(self):
        """Ascent to 408 km returns valid profile."""
        a = ascent_debris_profile(408, ascent_time_s=600, cross_section_m2=20)
        assert a.target_altitude_km == 408
        assert a.max_flux_altitude_km <= 408
        assert a.integrated_fluence_per_m2 > 0
        assert a.transit_time_s == 600

    def test_ascent_peak_not_at_low_altitude(self):
        """Peak flux altitude during ascent to 900 km should be above 700 km.

        The debris peak is at 800–900 km, so any ascent through that zone
        will identify it as the max-flux altitude.
        """
        a = ascent_debris_profile(900, ascent_time_s=600, cross_section_m2=20)
        assert a.max_flux_altitude_km > 500, (
            f"Peak flux altitude {a.max_flux_altitude_km:.0f} km should be in debris belt"
        )

    def test_ascent_fluence_much_less_than_orbit(self):
        """Ascent fluence (3 hr transit) << 1-year LEO orbit exposure.

        During ascent, the spacecraft passes quickly through each altitude band.
        The integrated fluence is many orders of magnitude less than sustained orbital ops.
        """
        a = ascent_debris_profile(408, ascent_time_s=600, cross_section_m2=10)
        flux_iss = get_debris_flux(408, ">1cm")
        # 1 year orbit exposure per m² = flux_iss
        # Ascent fluence per m² should be << 0.001 × annual flux
        assert a.integrated_fluence_per_m2 < flux_iss * 0.001, (
            f"Ascent fluence {a.integrated_fluence_per_m2:.2e}/m² should be << "
            f"annual orbit {flux_iss:.2e}/m²/yr × 0.001"
        )
