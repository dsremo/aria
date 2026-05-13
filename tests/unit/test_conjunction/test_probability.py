"""Tests for collision probability calculation."""


import numpy as np

from aria.conjunction.probability.chan import chan_pc
from aria.conjunction.probability.covariance import (
    combine_covariances,
    generate_default_covariance,
    scale_covariance,
)
from aria.conjunction.probability.foster import foster_pc
from aria.conjunction.probability.mahalanobis import (
    mahalanobis_distance,
    maximum_pc,
    should_skip_pc,
)
from aria.conjunction.probability.monte_carlo import (
    monte_carlo_confidence_interval,
    monte_carlo_pc,
)


class TestMahalanobis:
    """Test Mahalanobis distance pre-filter."""

    def test_zero_miss(self):
        """Zero miss distance → D_M = 0."""
        d = mahalanobis_distance(np.array([0, 0]), np.eye(2))
        assert d == 0.0

    def test_unit_covariance(self):
        """With identity covariance, D_M = Euclidean distance."""
        miss = np.array([3.0, 4.0])
        d = mahalanobis_distance(miss, np.eye(2))
        assert abs(d - 5.0) < 1e-10

    def test_scaled_covariance(self):
        """Larger covariance → smaller D_M for same miss distance."""
        miss = np.array([3.0, 4.0])
        d1 = mahalanobis_distance(miss, np.eye(2))
        d2 = mahalanobis_distance(miss, np.eye(2) * 4)
        assert d2 < d1  # larger covariance → smaller normalized distance

    def test_skip_threshold(self):
        """Should recommend skipping when D_M > 5."""
        miss_far = np.array([100.0, 100.0])
        skip, d = should_skip_pc(miss_far, np.eye(2))
        assert skip is True
        assert d > 5.0

    def test_no_skip_close(self):
        miss_close = np.array([0.1, 0.1])
        skip, d = should_skip_pc(miss_close, np.eye(2))
        assert skip is False


class TestMaximumPc:
    def test_p_max_properties(self):
        """P_max should be in (0, 1] and decrease with larger covariance."""
        cov_small = np.diag([0.01, 0.01])
        cov_large = np.diag([100.0, 100.0])

        p_max_small = maximum_pc(0.01, cov_small)
        p_max_large = maximum_pc(0.01, cov_large)

        assert 0 < p_max_small <= 1
        assert 0 < p_max_large <= 1
        assert p_max_small > p_max_large  # dilution effect


class TestFosterPc:
    """Test Foster (1992) polar quadrature Pc."""

    def test_zero_miss_maximum_pc(self):
        """Zero miss distance should give maximum Pc."""
        pc = foster_pc(
            miss_vector_2d=np.array([0.0, 0.0]),
            covariance_2d=np.diag([1.0, 1.0]),
            combined_radius_km=0.01,
        )
        assert pc > 0

    def test_large_miss_negligible_pc(self):
        """Very large miss distance → Pc ≈ 0."""
        pc = foster_pc(
            miss_vector_2d=np.array([1000.0, 1000.0]),
            covariance_2d=np.diag([1.0, 1.0]),
            combined_radius_km=0.01,
        )
        assert pc < 1e-10

    def test_pc_bounds(self):
        """Pc should always be in [0, 1]."""
        for miss in [0.01, 0.1, 1.0, 10.0]:
            pc = foster_pc(
                np.array([miss, miss]),
                np.diag([1.0, 1.0]),
                0.01,
            )
            assert 0 <= pc <= 1

    def test_pc_decreases_with_distance(self):
        """Pc should decrease as miss distance increases (in non-dilution regime)."""
        pcs = []
        for miss in [0.1, 0.5, 1.0, 2.0, 5.0]:
            pc = foster_pc(
                np.array([miss, 0.0]),
                np.diag([1.0, 1.0]),
                0.01,
            )
            pcs.append(pc)

        # Each should be less than the previous
        for i in range(1, len(pcs)):
            assert pcs[i] <= pcs[i-1] + 1e-15


class TestChanPc:
    """Test Chan (1997) analytical Pc."""

    def test_pc_bounds(self):
        pc = chan_pc(np.array([1.0, 0.0]), np.diag([1.0, 1.0]), 0.01)
        assert 0 <= pc <= 1

    def test_zero_miss(self):
        pc = chan_pc(np.array([0.0, 0.0]), np.diag([1.0, 1.0]), 0.01)
        assert pc > 0

    def test_agreement_with_foster(self):
        """Chan and Foster should roughly agree for typical encounters."""
        miss = np.array([0.5, 0.3])
        cov = np.diag([1.0, 1.0])
        R = 0.01

        pc_foster = foster_pc(miss, cov, R)
        pc_chan = chan_pc(miss, cov, R)

        # Should agree within an order of magnitude for circular covariance
        if pc_foster > 1e-15:
            ratio = pc_chan / pc_foster
            assert 0.01 < ratio < 100, f"Foster={pc_foster:.2e}, Chan={pc_chan:.2e}"


class TestMonteCarloPc:
    """Test Monte Carlo Pc estimation."""

    def test_known_probability(self):
        """Large radius with tight covariance → Pc should be near 1."""
        pc = monte_carlo_pc(
            miss_vector_2d=np.array([0.0, 0.0]),
            covariance_2d=np.diag([0.001, 0.001]),
            combined_radius_km=1.0,  # huge compared to σ
            n_samples=100_000,
            seed=42,
        )
        assert pc > 0.99

    def test_negligible_probability(self):
        """Large miss with tiny radius → Pc ≈ 0."""
        pc = monte_carlo_pc(
            miss_vector_2d=np.array([100.0, 100.0]),
            covariance_2d=np.diag([1.0, 1.0]),
            combined_radius_km=0.001,
            n_samples=100_000,
            seed=42,
        )
        assert pc == 0.0

    def test_confidence_interval(self):
        """Confidence interval should bracket the estimate."""
        lo, hi = monte_carlo_confidence_interval(0.001, 1_000_000)
        assert lo < 0.001 < hi
        assert lo >= 0
        assert hi <= 1


class TestCovariance:
    def test_combine(self):
        c1 = np.diag([1.0, 2.0, 3.0])
        c2 = np.diag([0.5, 0.5, 0.5])
        combined = combine_covariances(c1, c2)
        np.testing.assert_array_almost_equal(combined, np.diag([1.5, 2.5, 3.5]))

    def test_default_covariance(self):
        cov = generate_default_covariance(position_sigma_km=1.0, in_track_scaling=5.0)
        assert cov.shape == (3, 3)
        # In-track (index 1) should be 25x radial (index 0)
        assert cov[1, 1] == 25.0  # (1*5)² = 25
        assert cov[0, 0] == 1.0

    def test_scale_covariance(self):
        cov = np.eye(3)
        scaled = scale_covariance(cov, 2.0)
        np.testing.assert_array_almost_equal(scaled, np.eye(3) * 4.0)
