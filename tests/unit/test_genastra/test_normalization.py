"""Tests for gene expression normalization."""

from __future__ import annotations

import numpy as np

from aria.genastra.expression.normalization import (
    compute_size_factors,
    normalize_counts,
    validate_count_matrix,
)


class TestSizeFactors:
    def test_uniform_counts(self) -> None:
        """If all samples have identical counts, size factors should be ~1.0."""
        matrix = np.array([[10, 10, 10], [20, 20, 20], [30, 30, 30]])
        sf = compute_size_factors(matrix)
        np.testing.assert_allclose(sf, [1.0, 1.0, 1.0], atol=0.01)

    def test_one_sample_doubled(self) -> None:
        """If one sample has 2x all counts, its size factor should be ~2.0."""
        matrix = np.array([[10, 20], [20, 40], [30, 60], [40, 80]])
        sf = compute_size_factors(matrix)
        ratio = sf[1] / sf[0]
        assert abs(ratio - 2.0) < 0.1

    def test_size_factors_positive_normal(self) -> None:
        """Size factors must be positive for samples with counts."""
        matrix = np.random.RandomState(42).randint(1, 100, size=(100, 5))
        sf = compute_size_factors(matrix)
        assert np.all(sf > 0)

    def test_zero_sample_handled(self) -> None:
        """A sample with all zeros gets size factor 0 (correctly flagged)."""
        matrix = np.random.RandomState(42).randint(0, 100, size=(100, 5))
        matrix[:, 0] = 0  # One sample all zeros
        sf = compute_size_factors(matrix)
        # The zero-count sample will have SF=0 from total count normalization
        # Non-zero samples should have positive SFs
        assert np.all(sf[1:] > 0)


class TestNormalization:
    def test_preserves_shape(self) -> None:
        matrix = np.array([[10, 20], [30, 40]])
        sf = np.array([1.0, 2.0])
        norm = normalize_counts(matrix, sf)
        assert norm.shape == matrix.shape

    def test_divides_by_size_factor(self) -> None:
        matrix = np.array([[10, 20]])
        sf = np.array([1.0, 2.0])
        norm = normalize_counts(matrix, sf)
        np.testing.assert_allclose(norm, [[10.0, 10.0]])

    def test_preserves_rank_order(self) -> None:
        """Normalization should preserve rank order within each sample."""
        matrix = np.array([[10, 20], [30, 40], [50, 60]])
        sf = np.array([1.5, 0.8])
        norm = normalize_counts(matrix, sf)
        for col in range(norm.shape[1]):
            assert np.all(np.diff(norm[:, col]) > 0)


class TestValidation:
    def test_empty_matrix(self) -> None:
        warnings = validate_count_matrix(np.array([]).reshape(0, 0))
        assert any("empty" in w.lower() for w in warnings)

    def test_negative_values(self) -> None:
        matrix = np.array([[10, -5], [20, 30]])
        warnings = validate_count_matrix(matrix)
        assert any("negative" in w.lower() for w in warnings)

    def test_all_zeros(self) -> None:
        matrix = np.zeros((10, 3))
        warnings = validate_count_matrix(matrix)
        assert any("zero" in w.lower() for w in warnings)

    def test_valid_matrix_no_warnings(self) -> None:
        matrix = np.random.RandomState(42).randint(100, 10000, size=(1000, 6))
        warnings = validate_count_matrix(matrix)
        assert len(warnings) == 0

    def test_low_count_sample_warning(self) -> None:
        matrix = np.array([[1000, 5], [2000, 3], [3000, 2]])
        warnings = validate_count_matrix(matrix)
        assert any("1000" in w or "low" in w.lower() for w in warnings)
