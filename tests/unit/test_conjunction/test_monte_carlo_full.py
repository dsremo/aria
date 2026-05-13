"""Tests for Monte Carlo utilities: importance sampling and confidence intervals."""

import math

import numpy as np
import pytest

from aria.conjunction.probability.monte_carlo import (
    importance_sampling_pc,
    monte_carlo_confidence_interval,
    monte_carlo_pc,
    monte_carlo_pc_3d,
)

# ---------------------------------------------------------------------------
# importance_sampling_pc
# ---------------------------------------------------------------------------

class TestImportanceSamplingPc:

    def test_returns_tuple(self):
        miss = np.array([1.0, 0.0])
        cov = np.eye(2) * 0.25
        result = importance_sampling_pc(miss, cov, combined_radius_km=0.1, n_samples=10_000, seed=0)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_pc_in_unit_interval(self):
        miss = np.array([0.5, 0.0])
        cov = np.eye(2) * 0.25
        pc, se = importance_sampling_pc(  # noqa: E501
            miss, cov, combined_radius_km=0.1, n_samples=50_000, seed=42)
        assert 0.0 <= pc <= 1.0

    def test_se_nonnegative(self):
        miss = np.array([0.5, 0.0])
        cov = np.eye(2) * 0.25
        pc, se = importance_sampling_pc(  # noqa: E501
            miss, cov, combined_radius_km=0.1, n_samples=50_000, seed=42)
        assert se >= 0.0

    def test_close_approach_nonzero_pc(self):
        """Zero miss, large radius → high Pc even with IS."""
        miss = np.array([0.0, 0.0])
        cov = np.eye(2) * 0.01  # σ = 0.1 km
        pc, se = importance_sampling_pc(miss, cov, combined_radius_km=0.3, n_samples=10_000, seed=7)
        assert pc > 0.5

    def test_large_miss_low_pc(self):
        """Very large miss → almost no samples inside disk → Pc ≈ 0."""
        miss = np.array([50.0, 0.0])
        cov = np.eye(2) * 0.01
        pc, se = importance_sampling_pc(miss, cov, combined_radius_km=0.01, n_samples=10_000, seed=0)  # noqa: E501
        assert pc < 1e-4

    def test_reproducibility_with_seed(self):
        miss = np.array([0.5, 0.0])
        cov = np.eye(2) * 0.25
        pc1, se1 = importance_sampling_pc(miss, cov, combined_radius_km=0.15, n_samples=20_000, seed=99)  # noqa: E501
        pc2, se2 = importance_sampling_pc(miss, cov, combined_radius_km=0.15, n_samples=20_000, seed=99)  # noqa: E501
        assert pc1 == pc2
        assert se1 == se2

    def test_larger_radius_higher_pc(self):
        """Larger hard-body radius → more samples inside → higher Pc."""
        miss = np.array([1.0, 0.0])
        cov = np.eye(2) * 1.0
        pc_small, _ = importance_sampling_pc(miss, cov, combined_radius_km=0.1, n_samples=50_000, seed=3)  # noqa: E501
        pc_large, _ = importance_sampling_pc(miss, cov, combined_radius_km=2.0, n_samples=50_000, seed=3)  # noqa: E501
        assert pc_large > pc_small

    def test_no_samples_inside_returns_zero_inf(self):
        """When no IS samples fall inside the disk, returns (0.0, inf)."""
        # Very small radius, very large miss → no samples inside
        miss = np.array([1000.0, 0.0])
        cov = np.eye(2) * 0.001
        pc, se = importance_sampling_pc(miss, cov, combined_radius_km=1e-6, n_samples=1_000, seed=0)
        assert pc == 0.0
        assert se == float("inf")

    def test_non_psd_covariance_regularized(self):
        """Near-singular covariance should be regularized, not crash."""
        miss = np.array([0.5, 0.0])
        cov = np.array([[1e-15, 0.0], [0.0, 1e-15]])
        pc, se = importance_sampling_pc(miss, cov, combined_radius_km=0.1, n_samples=10_000, seed=0)  # noqa: E501
        assert 0.0 <= pc <= 1.0

    def test_is_consistent_with_standard_mc(self):
        """IS estimate should be reasonably close to standard MC for moderate Pc."""
        miss = np.array([0.5, 0.0])
        cov = np.eye(2) * 0.5
        R = 0.2  # noqa: N806

        pc_mc = monte_carlo_pc(miss, cov, R, n_samples=200_000, seed=1)
        pc_is, _ = importance_sampling_pc(miss, cov, R, n_samples=100_000, seed=1)

        # Both estimates should be within a factor of 3 of each other
        if pc_mc > 0 and pc_is > 0:
            ratio = pc_is / pc_mc
            assert 0.3 < ratio < 3.0, f"IS={pc_is:.4e}, MC={pc_mc:.4e}, ratio={ratio:.2f}"


# ---------------------------------------------------------------------------
# monte_carlo_confidence_interval
# ---------------------------------------------------------------------------

class TestMCConfidenceInterval:

    def test_returns_tuple_of_two_floats(self):
        lo, hi = monte_carlo_confidence_interval(pc=0.001, n_samples=100_000)
        assert isinstance(lo, float)
        assert isinstance(hi, float)

    def test_lower_le_upper(self):
        lo, hi = monte_carlo_confidence_interval(pc=0.001, n_samples=100_000)
        assert lo <= hi

    def test_bounds_contain_pc(self):
        """The point estimate should lie within its own CI."""
        pc = 0.01
        lo, hi = monte_carlo_confidence_interval(pc=pc, n_samples=10_000)
        assert lo <= pc <= hi

    def test_zero_pc_returns_zero_interval(self):
        """Pc = 0 → standard error = 0 → degenerate interval [0, 0]."""
        lo, hi = monte_carlo_confidence_interval(pc=0.0, n_samples=10_000)
        assert lo == 0.0
        assert hi == 0.0

    def test_one_pc_returns_one_interval(self):
        """Pc = 1 → standard error = 0 → degenerate interval [1, 1]."""
        lo, hi = monte_carlo_confidence_interval(pc=1.0, n_samples=10_000)
        assert lo == pytest.approx(1.0)
        assert hi == pytest.approx(1.0)

    def test_lower_bound_nonnegative(self):
        """Lower bound should never go below 0."""
        lo, hi = monte_carlo_confidence_interval(pc=0.0001, n_samples=100)
        assert lo >= 0.0

    def test_upper_bound_not_exceed_one(self):
        """Upper bound should never exceed 1."""
        lo, hi = monte_carlo_confidence_interval(pc=0.999, n_samples=100)
        assert hi <= 1.0

    def test_more_samples_tighter_interval(self):
        """More samples → smaller confidence interval width."""
        pc = 0.01
        lo_few, hi_few = monte_carlo_confidence_interval(pc=pc, n_samples=100)
        lo_many, hi_many = monte_carlo_confidence_interval(pc=pc, n_samples=1_000_000)
        width_few = hi_few - lo_few
        width_many = hi_many - lo_many
        assert width_many < width_few

    def test_99_percent_wider_than_95_percent(self):
        """Higher confidence → wider interval."""
        pc = 0.01
        lo_95, hi_95 = monte_carlo_confidence_interval(pc=pc, n_samples=10_000, confidence=0.95)
        lo_99, hi_99 = monte_carlo_confidence_interval(pc=pc, n_samples=10_000, confidence=0.99)
        assert (hi_99 - lo_99) > (hi_95 - lo_95)

    def test_interval_width_formula(self):
        """Width should match 2 × z × se = 2 × 1.96 × sqrt(p(1-p)/n) for 95%."""
        pc = 0.01
        n = 100_000
        lo, hi = monte_carlo_confidence_interval(pc=pc, n_samples=n, confidence=0.95)
        se = math.sqrt(pc * (1 - pc) / n)
        expected_width = 2 * 1.96 * se
        assert (hi - lo) == pytest.approx(expected_width, rel=1e-3)


# ---------------------------------------------------------------------------
# monte_carlo_pc_3d — velocity covariance path
# ---------------------------------------------------------------------------

class TestMonteCarloPc3DWithVelocityCovariance:

    def test_velocity_covariance_path_returns_valid(self):
        """When velocity_covariance_3d is provided, code takes the 6D path."""
        miss = np.array([0.5, 0.0, 0.0])
        cov_pos = np.eye(3) * 0.25
        cov_vel = np.eye(3) * 0.001  # small velocity uncertainty
        v_rel = np.array([0.0, 7.5, 0.0])

        pc = monte_carlo_pc_3d(
            miss, cov_pos, combined_radius_km=0.05,
            relative_velocity=v_rel,
            n_samples=20_000, seed=0,
            velocity_covariance_3d=cov_vel,
        )
        assert 0.0 <= pc <= 1.0

    def test_stationary_objects_path(self):
        """Near-zero relative velocity triggers the stationary-case branch."""
        miss = np.array([0.05, 0.0, 0.0])
        cov = np.eye(3) * 0.01  # σ = 0.1 km
        v_rel = np.array([0.0, 0.0, 0.0])  # stationary
        pc = monte_carlo_pc_3d(
            miss, cov, combined_radius_km=0.1,
            relative_velocity=v_rel,
            n_samples=50_000, seed=42,
        )
        assert 0.0 <= pc <= 1.0

    def test_encounter_duration_window_clamping(self):
        """Trajectories should be clamped to ±half_duration — no crash."""
        miss = np.array([1.0, 0.0, 0.0])
        cov = np.eye(3) * 0.5
        v_rel = np.array([0.01, 0.0, 0.0])  # very slow — encounter spans long time
        pc = monte_carlo_pc_3d(
            miss, cov, combined_radius_km=0.05,
            relative_velocity=v_rel,
            encounter_duration_s=1.0,   # very short window
            n_samples=10_000, seed=7,
        )
        assert 0.0 <= pc <= 1.0

    def test_3d_reproducibility_with_seed(self):
        miss = np.array([0.5, 0.0, 0.0])
        cov = np.eye(3) * 0.25
        v_rel = np.array([0.0, 7.5, 0.0])
        kwargs = dict(combined_radius_km=0.1, relative_velocity=v_rel, n_samples=10_000, seed=55)
        pc1 = monte_carlo_pc_3d(miss, cov, **kwargs)
        pc2 = monte_carlo_pc_3d(miss, cov, **kwargs)
        assert pc1 == pc2

    def test_3d_close_approach_high_pc(self):
        """Zero miss, radius >> sigma → high Pc."""
        miss = np.array([0.0, 0.0, 0.0])
        cov = np.eye(3) * 0.001  # σ = ~31 m
        v_rel = np.array([0.0, 7.5, 0.0])
        pc = monte_carlo_pc_3d(
            miss, cov, combined_radius_km=0.1,
            relative_velocity=v_rel,
            n_samples=50_000, seed=0,
        )
        assert pc > 0.01  # should be detectable

    def test_non_psd_velocity_covariance_regularized(self):
        """Non-PSD velocity covariance should be regularized, not crash."""
        miss = np.array([0.5, 0.0, 0.0])
        cov_pos = np.eye(3) * 0.25
        cov_vel = np.zeros((3, 3))  # all-zero → not PD → triggers regularization
        v_rel = np.array([0.0, 7.5, 0.0])
        pc = monte_carlo_pc_3d(
            miss, cov_pos, combined_radius_km=0.1,
            relative_velocity=v_rel,
            n_samples=10_000, seed=0,
            velocity_covariance_3d=cov_vel,
        )
        assert 0.0 <= pc <= 1.0
