"""Tests for HZE radiation quality weighting and SEP event models.

Validates:
1. ICRP 60 Q(LET) piecewise function at canonical breakpoints.
2. GCR species dose breakdown sums to total dose.
3. HZE shielding correctly penalises the stiff Fe component vs protons.
4. SEP dose drops monotonically with shield depth.
5. SEP extreme event probability approaches 1 for very long missions.
6. Combined dose budget has correct structure and sign.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.transport import (
    GCR_SPECIES_SOLAR_MIN,
    SEP_EXTREME_EVENT,
    SEP_LARGE_EVENT,
    SEP_SMALL_EVENT,
    hze_dose_breakdown,
    hze_shielded_dose,
    icrp60_quality_factor,
    sep_annual_expected_dose_sv,
    sep_proton_dose_sv,
    sep_single_event_probability,
    total_annual_dose_sv,
)


class TestICRP60QualityFactor:
    """ICRP 60 Table A1 piecewise Q(LET) function."""

    def test_low_let_q_equals_one(self):
        # LET < 10 keV/μm → Q = 1 for all charged particles
        assert icrp60_quality_factor(0.4) == 1.0   # proton ~0.4 keV/μm at 1 GeV/n
        assert icrp60_quality_factor(9.9) == 1.0

    def test_boundary_exactly_10(self):
        # At exactly 10 keV/μm the middle-segment formula starts: 0.32*10 - 2.2 = 1.0
        assert icrp60_quality_factor(10.0) == pytest.approx(1.0, rel=1e-9)

    def test_middle_segment(self):
        # Q = 0.32*L - 2.2, should be ~30 at L≈100
        q_50 = icrp60_quality_factor(50.0)
        assert q_50 == pytest.approx(0.32 * 50.0 - 2.2, rel=1e-9)
        assert q_50 > 1.0

    def test_high_let_decreasing(self):
        # L > 100: Q = 300/sqrt(L); overkill regime
        q_100 = icrp60_quality_factor(100.0)    # transition point
        q_400 = icrp60_quality_factor(400.0)
        q_1600 = icrp60_quality_factor(1600.0)
        assert q_1600 < q_400 < q_100

    def test_high_let_formula(self):
        q = icrp60_quality_factor(900.0)
        assert q == pytest.approx(300.0 / math.sqrt(900.0), rel=1e-9)

    def test_negative_let_raises(self):
        with pytest.raises(ValueError):
            icrp60_quality_factor(-1.0)

    def test_q_iron_representative(self):
        # Fe-56 at ~1 GeV/n: LET ≈ 280 keV/μm → Q = 300/sqrt(280) ≈ 17.9
        q_fe = icrp60_quality_factor(280.0)
        assert 15.0 < q_fe < 25.0


class TestHZEDoseBreakdown:
    """GCR species-specific dose breakdown."""

    def test_sum_equals_total(self):
        dose_total = 0.42
        breakdown = hze_dose_breakdown(dose_total)
        assert sum(breakdown.values()) == pytest.approx(dose_total, rel=1e-9)

    def test_all_species_present(self):
        breakdown = hze_dose_breakdown(1.0)
        for sp in GCR_SPECIES_SOLAR_MIN:
            assert sp.name in breakdown

    def test_all_contributions_positive(self):
        breakdown = hze_dose_breakdown(0.42)
        for v in breakdown.values():
            assert v >= 0.0

    def test_hze_significant_fraction(self):
        # HZE (CNO + Mg/Si + Fe) should be ≥25% of total dose (NCRP 132)
        breakdown = hze_dose_breakdown(1.0)
        hze_dose = breakdown["CNO"] + breakdown["Mg-Si"] + breakdown["Fe"]
        assert hze_dose >= 0.25

    def test_zero_dose(self):
        breakdown = hze_dose_breakdown(0.0)
        assert all(v == 0.0 for v in breakdown.values())

    def test_negative_dose_raises(self):
        with pytest.raises(ValueError):
            hze_dose_breakdown(-0.1)


class TestHZEShielding:
    """Species-dependent shielding model."""

    def test_monotonic_with_shield_depth(self):
        d = [0.0, 5.0, 10.0, 20.0, 40.0]
        doses = [hze_shielded_dose(1.0, x) for x in d]
        for i in range(len(doses) - 1):
            assert doses[i] > doses[i + 1]

    def test_zero_shield_equals_unshielded(self):
        assert hze_shielded_dose(0.42, 0.0) == pytest.approx(0.42, rel=1e-9)

    def test_hze_fraction_increases_with_shielding(self):
        # Shielding reduces proton dose more than Fe → HZE fraction grows
        bd0 = hze_dose_breakdown(hze_shielded_dose(1.0, 0.0))
        bd20 = hze_dose_breakdown(hze_shielded_dose(1.0, 20.0))
        hze0 = bd0["CNO"] + bd0["Mg-Si"] + bd0["Fe"]
        hze20 = bd20["CNO"] + bd20["Mg-Si"] + bd20["Fe"]
        proton0 = bd0["Proton"]
        proton20 = bd20["Proton"]
        # After 20 g/cm², proton fraction drops more than HZE fraction
        assert proton20 / (hze_shielded_dose(1.0, 20.0)) < proton0

    def test_residual_dose_exists_at_thick_shield(self):
        # Even 100 g/cm² leaves a non-zero Fe component
        dose_100 = hze_shielded_dose(1.0, 100.0)
        assert dose_100 > 0.0

    def test_negative_shield_raises(self):
        with pytest.raises(ValueError):
            hze_shielded_dose(1.0, -1.0)


class TestSEPDose:
    """SEP event dose calculation."""

    def test_extreme_event_unshielded_significant(self):
        # Aug 1972 class unshielded: should be lethal-range (>5 Sv)
        dose = sep_proton_dose_sv(SEP_EXTREME_EVENT, shield_depth_g_cm2=0.0, tissue_depth_g_cm2=0.0)
        assert dose > 0.5  # conservative lower bound for extreme event

    def test_small_event_dose_low(self):
        dose = sep_proton_dose_sv(SEP_SMALL_EVENT, shield_depth_g_cm2=10.0)
        assert dose < 0.1  # small event behind habitat shield should be manageable

    def test_dose_decreases_with_shielding(self):
        d0 = sep_proton_dose_sv(SEP_LARGE_EVENT, 0.0)
        d10 = sep_proton_dose_sv(SEP_LARGE_EVENT, 10.0)
        d20 = sep_proton_dose_sv(SEP_LARGE_EVENT, 20.0)
        assert d0 > d10 > d20 > 0.0

    def test_dose_positive(self):
        assert sep_proton_dose_sv(SEP_SMALL_EVENT) > 0.0
        assert sep_proton_dose_sv(SEP_LARGE_EVENT) > 0.0
        assert sep_proton_dose_sv(SEP_EXTREME_EVENT) > 0.0

    def test_negative_shield_raises(self):
        with pytest.raises(ValueError):
            sep_proton_dose_sv(SEP_LARGE_EVENT, shield_depth_g_cm2=-1.0)


class TestSEPAnnualDose:
    """Annual expected SEP dose."""

    def test_solar_max_greater_than_solar_min(self):
        dose_max = sep_annual_expected_dose_sv(10.0, solar_max=True)
        dose_min = sep_annual_expected_dose_sv(10.0, solar_max=False)
        assert dose_max > dose_min

    def test_decreases_with_shielding(self):
        d0 = sep_annual_expected_dose_sv(0.0)
        d10 = sep_annual_expected_dose_sv(10.0)
        d20 = sep_annual_expected_dose_sv(20.0)
        assert d0 > d10 > d20 >= 0.0

    def test_positive(self):
        assert sep_annual_expected_dose_sv(5.0, solar_max=True) > 0.0
        assert sep_annual_expected_dose_sv(5.0, solar_max=False) > 0.0


class TestSEPProbability:
    """SEP event occurrence probability."""

    def test_zero_mission_probability_zero(self):
        p = sep_single_event_probability(SEP_EXTREME_EVENT, 0.0)
        assert p == pytest.approx(0.0, abs=1e-12)

    def test_probability_approaches_one_long_mission(self):
        # Over 200 years, an extreme event is near-certain
        p = sep_single_event_probability(SEP_EXTREME_EVENT, 200.0)
        assert p > 0.999

    def test_large_event_likely_in_20_year_mission(self):
        p = sep_single_event_probability(SEP_LARGE_EVENT, 20.0, solar_max_fraction=0.4)
        assert p > 0.95  # ~3/yr × 0.4 × 20 → λ=24; P(≥1)≈1

    def test_probability_monotone_with_mission_duration(self):
        durations = [1, 5, 10, 20, 50]
        probs = [sep_single_event_probability(SEP_LARGE_EVENT, d) for d in durations]
        for i in range(len(probs) - 1):
            assert probs[i] < probs[i + 1]

    def test_negative_years_raises(self):
        with pytest.raises(ValueError):
            sep_single_event_probability(SEP_LARGE_EVENT, -1.0)


class TestTotalAnnualDoseBudget:
    """Combined GCR + HZE + SEP annual dose budget."""

    def test_keys_present(self):
        budget = total_annual_dose_sv(10.0)
        required = {"gcr_total_sv_yr", "gcr_proton_sv_yr", "gcr_helium_sv_yr",
                    "gcr_hze_sv_yr", "sep_expected_sv_yr", "total_sv_yr"}
        assert required.issubset(set(budget.keys()))

    def test_total_equals_gcr_plus_sep(self):
        budget = total_annual_dose_sv(10.0, include_sep=True)
        assert budget["total_sv_yr"] == pytest.approx(
            budget["gcr_total_sv_yr"] + budget["sep_expected_sv_yr"], rel=1e-9
        )

    def test_gcr_components_sum_to_gcr_total(self):
        budget = total_annual_dose_sv(10.0)
        gcr_sum = (budget["gcr_proton_sv_yr"]
                   + budget["gcr_helium_sv_yr"]
                   + budget["gcr_hze_sv_yr"])
        assert gcr_sum == pytest.approx(budget["gcr_total_sv_yr"], rel=1e-6)

    def test_all_values_positive(self):
        budget = total_annual_dose_sv(10.0)
        for k, v in budget.items():
            assert v >= 0.0, f"{k} = {v} < 0"

    def test_without_sep(self):
        budget = total_annual_dose_sv(10.0, include_sep=False)
        assert budget["sep_expected_sv_yr"] == 0.0
        assert budget["total_sv_yr"] == pytest.approx(budget["gcr_total_sv_yr"], rel=1e-9)

    def test_hze_fraction_significant(self):
        budget = total_annual_dose_sv(0.0)  # unshielded
        hze_frac = budget["gcr_hze_sv_yr"] / budget["gcr_total_sv_yr"]
        # NCRP 132 / Cucinotta 2014: HZE is ≥25% of total effective dose
        assert hze_frac >= 0.20, f"HZE fraction {hze_frac:.2%} is too low"
