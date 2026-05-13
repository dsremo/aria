"""Tests for aria.simulation.weibull_fitted — Weibull parameters fitted from NASA IMS data."""

from __future__ import annotations

import math
import random

import pytest

from aria.simulation.weibull_fitted import (
    FITTED_BEARING_BETA,
    FITTED_BEARING_ETA_YEARS,
    FITTED_WEIBULL_PARAMS,
    FIT_REPORT,
    IMS_FAILURE_DATA,
    WeibullReliability,
    fit_weibull_from_ims,
    get_ship_reliability_models,
    _ims_to_ship_years,
)


# ---- IMS data integrity ---------------------------------------------------

class TestIMSData:
    def test_four_failure_records(self):
        """IMS dataset has 4 documented bearing failures across 3 test runs."""
        assert len(IMS_FAILURE_DATA) == 4

    def test_operating_hours_positive(self):
        for rec in IMS_FAILURE_DATA:
            assert rec["operating_hours"] > 0, f"Test {rec['test']} bearing {rec['bearing']}"

    def test_recordings_match_hours(self):
        """Operating hours = recordings * 10 / 60."""
        for rec in IMS_FAILURE_DATA:
            expected = rec["recordings"] * 10 / 60
            assert abs(rec["operating_hours"] - expected) < 1.0


# ---- Weibull fit quality ---------------------------------------------------

class TestWeibullFit:
    def test_beta_positive(self):
        assert FITTED_BEARING_BETA > 0

    def test_eta_positive(self):
        assert FITTED_BEARING_ETA_YEARS > 0

    def test_beta_in_wearout_range(self):
        """Bearing failures are wear-out dominated: beta should be > 1."""
        assert FITTED_BEARING_BETA > 1.0, (
            f"Expected beta > 1 for wear-out, got {FITTED_BEARING_BETA}"
        )

    def test_eta_reasonable_range(self):
        """Eta should be in a plausible range for ship mechanical components.

        Too low (<5 yr) means unrealistically short life.
        Too high (>200 yr) means the scaling is off.
        """
        assert 5.0 < FITTED_BEARING_ETA_YEARS < 200.0, (
            f"eta={FITTED_BEARING_ETA_YEARS} outside plausible range"
        )

    def test_ks_pvalue_acceptable(self):
        """KS test should not reject the Weibull fit at alpha=0.05."""
        assert FIT_REPORT["ks_pvalue"] > 0.05, (
            f"KS p-value {FIT_REPORT['ks_pvalue']:.4f} < 0.05 — poor fit"
        )

    def test_fit_is_reproducible(self):
        """Calling fit_weibull_from_ims() twice gives same results."""
        r1 = fit_weibull_from_ims()
        r2 = fit_weibull_from_ims()
        assert r1["beta"] == pytest.approx(r2["beta"])
        assert r1["eta_years"] == pytest.approx(r2["eta_years"])


# ---- FITTED_WEIBULL_PARAMS ------------------------------------------------

class TestFittedParams:
    def test_all_categories_present(self):
        expected = {"bearing", "mechanical", "pump", "fan", "electronics",
                    "structural", "seal", "motor"}
        assert expected == set(FITTED_WEIBULL_PARAMS.keys())

    def test_bearing_matches_mle(self):
        beta, eta = FITTED_WEIBULL_PARAMS["bearing"]
        assert beta == pytest.approx(FITTED_BEARING_BETA, rel=1e-3)
        assert eta == pytest.approx(FITTED_BEARING_ETA_YEARS, rel=1e-3)

    def test_mechanical_equals_bearing(self):
        """Generic mechanical category should match bearing baseline."""
        assert FITTED_WEIBULL_PARAMS["mechanical"] == FITTED_WEIBULL_PARAMS["bearing"]

    def test_electronics_lower_beta(self):
        """Electronics should have lower beta (more random failures)."""
        e_beta, _ = FITTED_WEIBULL_PARAMS["electronics"]
        m_beta, _ = FITTED_WEIBULL_PARAMS["mechanical"]
        assert e_beta < m_beta

    def test_structural_higher_eta(self):
        """Structural components should have longer characteristic life."""
        _, s_eta = FITTED_WEIBULL_PARAMS["structural"]
        _, m_eta = FITTED_WEIBULL_PARAMS["mechanical"]
        assert s_eta > m_eta * 2

    def test_all_params_positive(self):
        for cat, (beta, eta) in FITTED_WEIBULL_PARAMS.items():
            assert beta > 0, f"{cat} beta={beta}"
            assert eta > 0, f"{cat} eta={eta}"


# ---- WeibullReliability class ----------------------------------------------

class TestWeibullReliability:
    @pytest.fixture
    def mech(self) -> WeibullReliability:
        return WeibullReliability.from_category("mechanical", name="test_bearing")

    def test_survival_at_zero(self, mech: WeibullReliability):
        assert mech.survival_probability(0) == 1.0

    def test_survival_decreases(self, mech: WeibullReliability):
        r1 = mech.survival_probability(5)
        r2 = mech.survival_probability(20)
        assert r1 > r2

    def test_survival_at_eta(self, mech: WeibullReliability):
        """R(eta) = exp(-1) ~ 0.368 for any Weibull."""
        r = mech.survival_probability(mech.eta_years)
        assert r == pytest.approx(math.exp(-1), abs=1e-6)

    def test_failure_complement(self, mech: WeibullReliability):
        """F(t) + R(t) = 1."""
        for t in [0.1, 1, 5, 10, 25, 50, 100]:
            assert mech.failure_probability(t) + mech.survival_probability(t) == pytest.approx(1.0)

    def test_hazard_rate_positive(self, mech: WeibullReliability):
        for t in [0.1, 1, 5, 10, 25, 50]:
            assert mech.hazard_rate(t) > 0

    def test_hazard_increasing_for_wearout(self):
        """For beta > 1, hazard rate should increase with age."""
        model = WeibullReliability(beta=2.0, eta_years=30.0)
        h1 = model.hazard_rate(5)
        h2 = model.hazard_rate(20)
        assert h2 > h1

    def test_hazard_decreasing_for_infant_mortality(self):
        """For beta < 1, hazard rate should decrease with age."""
        model = WeibullReliability(beta=0.5, eta_years=30.0)
        h1 = model.hazard_rate(1)
        h2 = model.hazard_rate(20)
        assert h1 > h2

    def test_sample_failure_time_positive(self, mech: WeibullReliability):
        rng = random.Random(42)
        for _ in range(100):
            t = mech.sample_failure_time(rng)
            assert t > 0

    def test_sample_mean_near_mtbf(self, mech: WeibullReliability):
        """Large sample mean should converge to theoretical MTBF."""
        rng = random.Random(12345)
        samples = [mech.sample_failure_time(rng) for _ in range(10_000)]
        sample_mean = sum(samples) / len(samples)
        theoretical_mtbf = mech.mtbf()
        assert sample_mean == pytest.approx(theoretical_mtbf, rel=0.05)

    def test_mtbf_positive(self, mech: WeibullReliability):
        assert mech.mtbf() > 0

    def test_median_life_less_than_mtbf_for_beta_gt1(self):
        """For beta > 1, median < mean (right-skewed distribution)."""
        model = WeibullReliability(beta=2.0, eta_years=30.0)
        assert model.median_life() < model.mtbf()

    def test_b10_less_than_median(self, mech: WeibullReliability):
        """B10 life should be less than median (B50) life."""
        assert mech.b_life(10) < mech.b_life(50)

    def test_b_life_monotonic(self, mech: WeibullReliability):
        """Higher percentile = longer b-life."""
        b10 = mech.b_life(10)
        b50 = mech.b_life(50)
        b90 = mech.b_life(90)
        assert b10 < b50 < b90

    def test_from_category_invalid(self):
        with pytest.raises(KeyError, match="Unknown category"):
            WeibullReliability.from_category("unobtanium")

    def test_invalid_beta(self):
        with pytest.raises(ValueError):
            WeibullReliability(beta=0, eta_years=10)

    def test_invalid_eta(self):
        with pytest.raises(ValueError):
            WeibullReliability(beta=1.5, eta_years=-5)


# ---- get_ship_reliability_models -------------------------------------------

class TestShipModels:
    def test_returns_all_categories(self):
        models = get_ship_reliability_models()
        assert set(models.keys()) == set(FITTED_WEIBULL_PARAMS.keys())

    def test_models_are_weibull(self):
        models = get_ship_reliability_models()
        for name, model in models.items():
            assert isinstance(model, WeibullReliability), f"{name} is not WeibullReliability"


# ---- Scaling sanity --------------------------------------------------------

class TestScaling:
    def test_ims_to_ship_years_positive(self):
        assert _ims_to_ship_years(100) > 0

    def test_ims_to_ship_years_monotonic(self):
        assert _ims_to_ship_years(200) > _ims_to_ship_years(100)

    def test_acceleration_produces_plausible_lifetimes(self):
        """IMS test 1 (359h) should map to ~20-50 years of ship service."""
        years = _ims_to_ship_years(359.3)
        assert 10 < years < 100, f"Got {years:.1f} years — outside plausible range"
