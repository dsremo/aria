"""Tests for Bayesian biosignature detection."""

from __future__ import annotations

import numpy as np
import pytest

from aria.genastra.core.models import DetectionSignificance
from aria.genastra.spectra.atmospheric import check_abiotic_pathways, check_photochemical_stability
from aria.genastra.spectra.bayesian import (
    BayesianResult,
    JointRetrievalResult,
    _approximate_bayes_factor,
    classify_bayes_factor,
    compute_false_positive_prob,
    get_prior,
    run_joint_retrieval,
)


class TestBayesFactorClassification:
    def test_negative_is_none(self) -> None:
        assert classify_bayes_factor(-1.0) == DetectionSignificance.NONE

    def test_zero_is_weak(self) -> None:
        # 0 is at the boundary between NONE (<0) and WEAK (0-0.5)
        assert classify_bayes_factor(0.0) == DetectionSignificance.WEAK

    def test_weak(self) -> None:
        assert classify_bayes_factor(0.3) == DetectionSignificance.WEAK

    def test_substantial(self) -> None:
        assert classify_bayes_factor(0.7) == DetectionSignificance.SUBSTANTIAL

    def test_strong(self) -> None:
        assert classify_bayes_factor(1.2) == DetectionSignificance.STRONG

    def test_very_strong(self) -> None:
        assert classify_bayes_factor(1.7) == DetectionSignificance.VERY_STRONG

    def test_decisive(self) -> None:
        assert classify_bayes_factor(2.5) == DetectionSignificance.DECISIVE


class TestFalsePositiveProb:
    def test_equal_models(self) -> None:
        # log10(K) = 0 → K = 1 → P(FP) = 0.5
        assert abs(compute_false_positive_prob(0.0) - 0.5) < 1e-10

    def test_strong_detection(self) -> None:
        # log10(K) = 3 → K = 1000 → P(FP) ≈ 0.001
        fp = compute_false_positive_prob(3.0)
        assert fp < 0.002

    def test_anti_detection(self) -> None:
        # log10(K) = -3 → K = 0.001 → P(FP) ≈ 0.999
        fp = compute_false_positive_prob(-3.0)
        assert fp > 0.99

    def test_monotonically_decreasing(self) -> None:
        prev = 1.0
        for bf in [-2, -1, 0, 1, 2, 3, 4]:
            fp = compute_false_positive_prob(float(bf))
            assert fp <= prev
            prev = fp


class TestPriors:
    def test_empirical_prior_exists(self) -> None:
        mu, sigma = get_prior("empirical", "CH4")
        assert isinstance(mu, float)
        assert sigma > 0

    def test_uninformative_wider(self) -> None:
        _, sigma_emp = get_prior("empirical", "CH4")
        _, sigma_uni = get_prior("uninformative", "CH4")
        assert sigma_uni > sigma_emp

    def test_pessimistic_lower_mu(self) -> None:
        mu_emp, _ = get_prior("empirical", "CH4")
        mu_pes, _ = get_prior("pessimistic", "CH4")
        assert mu_pes < mu_emp

    def test_unknown_prior_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown prior type"):
            get_prior("invalid_prior", "CH4")


class TestAbioticPathways:
    def test_ch4_has_abiotic(self) -> None:
        result = check_abiotic_pathways("CH4")
        assert result.has_abiotic_source
        assert "serpentinization" in result.explanation.lower()

    def test_dms_no_abiotic(self) -> None:
        result = check_abiotic_pathways("DMS")
        assert not result.has_abiotic_source

    def test_dmds_no_abiotic(self) -> None:
        result = check_abiotic_pathways("DMDS")
        assert not result.has_abiotic_source

    def test_o3_has_abiotic(self) -> None:
        result = check_abiotic_pathways("O3")
        assert result.has_abiotic_source


class TestPhotochemStability:
    def test_ch4_stable_around_g_star(self) -> None:
        result = check_photochemical_stability("CH4", "G2V", 5800.0)
        assert result.is_stable

    def test_dms_unstable_around_m_dwarf(self) -> None:
        result = check_photochemical_stability("DMS", "M2.5V", 3400.0)
        assert not result.is_stable

    def test_unknown_molecule(self) -> None:
        result = check_photochemical_stability("UNKNOWN", "G2V", 5800.0)
        assert result.is_stable  # No data = assume stable


class TestApproximateBayesFactor:
    """BIC-based approximate BF must have correct BayesianResult shape (all fields)."""

    def _synthetic_spectrum(self, n: int = 50) -> tuple:
        rng = np.random.default_rng(42)
        wavelengths = np.linspace(1.0, 5.0, n)
        flux = np.ones(n) + rng.normal(0, 0.001, n)
        flux_err = np.full(n, 0.001)
        return wavelengths, flux, flux_err

    def test_returns_bayesian_result(self) -> None:
        w, f, fe = self._synthetic_spectrum()
        result = _approximate_bayes_factor(w, f, fe, "CH4", "empirical")
        assert isinstance(result, BayesianResult)

    def test_significance_reliable_is_false(self) -> None:
        # BIC approximation is flagged as unreliable
        w, f, fe = self._synthetic_spectrum()
        result = _approximate_bayes_factor(w, f, fe, "CH4", "empirical")
        assert result.significance_reliable is False

    def test_mutual_info_is_none(self) -> None:
        w, f, fe = self._synthetic_spectrum()
        result = _approximate_bayes_factor(w, f, fe, "CH4", "empirical")
        assert result.mutual_information_bits is None

    def test_log10_bf_err_is_0_5(self) -> None:
        w, f, fe = self._synthetic_spectrum()
        result = _approximate_bayes_factor(w, f, fe, "CH4", "empirical")
        assert result.log10_bayes_factor_err == 0.5


class TestJointRetrieval:
    """Joint molecular retrieval fits all molecules simultaneously."""

    @pytest.fixture
    def synthetic_spectrum(self):
        rng = np.random.default_rng(0)
        wavelengths = np.linspace(1.0, 5.0, 30)
        flux = np.ones(30) + rng.normal(0, 0.002, 30)
        flux_err = np.full(30, 0.002)
        return wavelengths, flux, flux_err

    @pytest.mark.skipif(
        __import__("importlib.util", fromlist=["find_spec"]).find_spec("dynesty") is None,
        reason="dynesty not installed",
    )
    def test_returns_joint_result(self, synthetic_spectrum) -> None:
        w, f, fe = synthetic_spectrum
        result = run_joint_retrieval(w, f, fe, ["CH4", "CO2"], n_live=50)
        assert isinstance(result, JointRetrievalResult)

    @pytest.mark.skipif(
        __import__("importlib.util", fromlist=["find_spec"]).find_spec("dynesty") is None,
        reason="dynesty not installed",
    )
    def test_result_has_all_molecules(self, synthetic_spectrum) -> None:
        w, f, fe = synthetic_spectrum
        result = run_joint_retrieval(w, f, fe, ["CH4", "CO2"], n_live=50)
        assert set(result.molecules) == {"CH4", "CO2"}
        assert "CH4" in result.posterior_abundances
        assert "CO2" in result.posterior_abundances

    @pytest.mark.skipif(
        __import__("importlib.util", fromlist=["find_spec"]).find_spec("dynesty") is None,
        reason="dynesty not installed",
    )
    def test_abundances_positive(self, synthetic_spectrum) -> None:
        w, f, fe = synthetic_spectrum
        result = run_joint_retrieval(w, f, fe, ["CH4"], n_live=50)
        for mol, abundance in result.posterior_abundances.items():
            assert abundance > 0.0, f"{mol} abundance must be positive"

    @pytest.mark.skipif(
        __import__("importlib.util", fromlist=["find_spec"]).find_spec("dynesty") is None,
        reason="dynesty not installed",
    )
    def test_correlation_computed_for_pairs(self, synthetic_spectrum) -> None:
        w, f, fe = synthetic_spectrum
        result = run_joint_retrieval(w, f, fe, ["CH4", "CO2"], n_live=50)
        assert "CH4:CO2" in result.posterior_correlations
        assert -1.0 <= result.posterior_correlations["CH4:CO2"] <= 1.0

    def test_empty_molecules_raises(self, synthetic_spectrum) -> None:
        w, f, fe = synthetic_spectrum
        with pytest.raises(ValueError, match="molecules list must not be empty"):
            run_joint_retrieval(w, f, fe, [])
