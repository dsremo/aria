"""Gene expression normalization methods.

Panel 12 (Computational Biologist) critique:
- DESeq2 uses its own size factor normalization internally
- For CROSS-experiment comparison, need TPM or batch-corrected methods
- Raw counts from GeneLab must be normalized before any analysis
"""

from __future__ import annotations

import numpy as np
import structlog

logger = structlog.get_logger()


def compute_size_factors(count_matrix: np.ndarray) -> np.ndarray:
    """Compute DESeq2-style size factors using the median-of-ratios method.

    s_j = median_g(K_gj / geometric_mean_g)

    Args:
        count_matrix: (genes x samples) raw count matrix.

    Returns:
        Array of size factors, one per sample.
    """
    # Filter out genes with zero counts in any sample (for geometric mean)
    nonzero_mask = np.all(count_matrix > 0, axis=1)
    filtered = count_matrix[nonzero_mask].astype(np.float64)

    if filtered.shape[0] == 0:
        logger.warning("size_factors_no_nonzero_genes", msg="Falling back to total count normalization")
        totals = count_matrix.sum(axis=0).astype(np.float64)
        return totals / np.median(totals)

    # Geometric mean per gene (across samples)
    log_counts = np.log(filtered)
    geo_means = np.exp(log_counts.mean(axis=1))

    # Ratio of each sample's count to the geometric mean
    ratios = filtered / geo_means[:, np.newaxis]

    # Size factor = median ratio per sample
    size_factors = np.median(ratios, axis=0)

    # Guard against zero size factors
    size_factors[size_factors == 0] = 1.0

    return size_factors


def normalize_counts(count_matrix: np.ndarray, size_factors: np.ndarray) -> np.ndarray:
    """Normalize raw counts by size factors.

    Args:
        count_matrix: (genes x samples) raw count matrix.
        size_factors: Per-sample size factors.

    Returns:
        Normalized count matrix.
    """
    return count_matrix.astype(np.float64) / size_factors[np.newaxis, :]


def counts_to_tpm(count_matrix: np.ndarray, gene_lengths: np.ndarray) -> np.ndarray:
    """Convert raw counts to Transcripts Per Million (TPM).

    TPM = (count / gene_length) / sum(count / gene_length) * 1e6

    Used for cross-experiment comparison where size factor normalization
    is insufficient (different library compositions).

    Args:
        count_matrix: (genes x samples) raw count matrix.
        gene_lengths: Gene lengths in bp, one per gene.

    Returns:
        TPM-normalized matrix.
    """
    # Rate = counts / length (in kb)
    gene_lengths_kb = gene_lengths.astype(np.float64) / 1000.0
    rate = count_matrix.astype(np.float64) / gene_lengths_kb[:, np.newaxis]

    # Normalize to sum = 1e6 per sample
    col_sums = rate.sum(axis=0)
    col_sums[col_sums == 0] = 1.0  # avoid division by zero

    return rate / col_sums[np.newaxis, :] * 1e6


def validate_count_matrix(count_matrix: np.ndarray) -> list[str]:
    """Validate a count matrix and return warnings.

    Checks:
    - No negative values
    - Not all zeros
    - Reasonable range
    - Gene count vs sample count ratio
    """
    warnings: list[str] = []

    if count_matrix.size == 0:
        warnings.append("Count matrix is empty.")
        return warnings

    if np.any(count_matrix < 0):
        warnings.append("Count matrix contains negative values — raw counts must be non-negative.")

    if np.all(count_matrix == 0):
        warnings.append("Count matrix is all zeros — check data import.")

    n_genes, n_samples = count_matrix.shape

    if n_samples < 2:
        warnings.append(f"Only {n_samples} sample(s) — need at least 2 for differential expression.")

    if n_genes < 100:
        warnings.append(f"Only {n_genes} genes — this is unusually low for RNA-seq.")

    # Check for samples with very low total counts
    sample_totals = count_matrix.sum(axis=0)
    low_count_samples = np.sum(sample_totals < 1000)  # ESTIMATE — 1000 total counts minimum (Love 2014 Genome Biol 15 550)
    if low_count_samples > 0:
        warnings.append(
            f"{low_count_samples} sample(s) have < 1000 total counts — "
            f"possible library preparation failure."
        )

    return warnings
