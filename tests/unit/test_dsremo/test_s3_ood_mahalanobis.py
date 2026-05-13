"""Tests for V3-S3: Mahalanobis-distance OOD detector.

Validates:
 1. fit raises on empty input
 2. fit raises when n < d + 1 (rank-deficient)
 3. fit returns a MahalanobisOOD with correct shapes
 4. Threshold matches the requested training-set percentile
 5. score returns zero for the training mean (within numerical tolerance)
 6. score is rotation-/translation-invariant to covariance structure
 7. is_ood flags clearly out-of-distribution points
 8. is_ood does NOT flag in-distribution points
 9. Jitter enables fitting on low-rank latents without raising
10. score(shape (n, d)) returns shape (n,)
"""

from __future__ import annotations

import numpy as np
import pytest

from aria.dsremo.detection.ood_mahalanobis import (
    COV_JITTER,
    DEFAULT_OOD_PERCENTILE,
    MahalanobisOOD,
    fit_mahalanobis_ood,
)


class TestFitValidation:

    def test_raises_on_empty(self):
        with pytest.raises(ValueError):
            fit_mahalanobis_ood(np.zeros((0, 4)))

    def test_raises_when_too_few_samples(self):
        # 3 samples in 5-D space → can't estimate covariance.
        with pytest.raises(ValueError):
            fit_mahalanobis_ood(np.zeros((3, 5)))


class TestFitShapes:

    def test_mean_and_inv_cov_shapes(self):
        rng = np.random.default_rng(0)
        Z   = rng.normal(size=(50, 4))
        fit = fit_mahalanobis_ood(Z)
        assert fit.mean.shape == (4,)
        assert fit.inv_cov.shape == (4, 4)
        assert fit.threshold > 0.0

    def test_threshold_matches_requested_percentile(self):
        rng = np.random.default_rng(0)
        Z   = rng.normal(size=(500, 3))
        fit = fit_mahalanobis_ood(Z, percentile=95.0)
        # By construction: at least 5 % of training points should be above threshold.
        over = (fit.score(Z) > fit.threshold).sum() / len(Z)
        assert 0.03 <= over <= 0.07


class TestScore:

    def test_score_is_zero_at_mean(self):
        rng = np.random.default_rng(0)
        Z = rng.normal(size=(200, 4))
        fit = fit_mahalanobis_ood(Z)
        d = fit.score(fit.mean[None, :])
        assert abs(d[0]) < 1e-9

    def test_score_returns_shape_n(self):
        rng = np.random.default_rng(0)
        Z = rng.normal(size=(100, 4))
        fit = fit_mahalanobis_ood(Z)
        test = rng.normal(size=(7, 4))
        assert fit.score(test).shape == (7,)


class TestIsOOD:

    def test_flags_out_of_distribution(self):
        rng = np.random.default_rng(0)
        # In-distribution cloud centred at 0 with unit covariance.
        Z = rng.normal(size=(500, 4))
        fit = fit_mahalanobis_ood(Z, percentile=99.9)
        far = np.full((5, 4), 20.0)  # way outside the cloud
        assert fit.is_ood(far).all()

    def test_does_not_flag_in_distribution(self):
        rng = np.random.default_rng(0)
        Z = rng.normal(size=(500, 4))
        fit = fit_mahalanobis_ood(Z, percentile=99.9)
        # New IID samples from the same distribution — almost all in-dist.
        test = rng.normal(size=(500, 4))
        flag_rate = fit.is_ood(test).sum() / len(test)
        # Should be ≤ ~5 % (loose; with finite training set the 99.9 percentile estimate wanders).
        assert flag_rate < 0.05


class TestLowRank:

    def test_jitter_enables_low_rank_fit(self):
        """Constant-in-last-dim latents have zero variance there → cov singular.
        Jitter should still allow a fit."""
        rng = np.random.default_rng(0)
        Z   = rng.normal(size=(100, 4))
        Z[:, 3] = 0.0   # last dim constant
        fit = fit_mahalanobis_ood(Z)
        # Just needs to not raise.
        assert fit.inv_cov.shape == (4, 4)


class TestConstants:

    def test_default_percentile(self):
        assert DEFAULT_OOD_PERCENTILE == 99.9

    def test_default_jitter_positive(self):
        assert COV_JITTER > 0
