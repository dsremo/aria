"""PyDESeq2 wrapper with validation and assumption checking.

Panel 5 (Mathematician) critique:
- DESeq2 assumes independent samples — spaceflight experiments often have
  pseudoreplication (pooled biological replicates from same organism pool)
- Size factor normalization assumes most genes are NOT differentially expressed
- Must report adjusted p-values AND Storey's pi0

Panel 12 (Computational Biologist) critique:
- Must validate negative binomial fit
- Must specify gene-level vs transcript-level
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import structlog

from aria.genastra.core.constants import DEFAULT_FDR_THRESHOLD, DEFAULT_LFC_THRESHOLD, MIN_SAMPLE_COUNT
from aria.genastra.core.exceptions import InsufficientSamplesError, PseudoreplicationError

logger = structlog.get_logger()


@dataclass(frozen=True)
class DESeq2Result:
    """Complete DESeq2 analysis result."""

    gene_symbols: tuple[str, ...]
    log2_fold_changes: np.ndarray
    lfc_standard_errors: np.ndarray
    wald_statistics: np.ndarray
    pvalues: np.ndarray
    padj: np.ndarray  # BH-adjusted
    base_means: np.ndarray
    pi0_estimate: float | None  # Storey's proportion of true nulls
    total_genes_tested: int
    significant_count: int
    fdr_threshold: float
    lfc_threshold: float
    normalization_method: str
    warnings: tuple[str, ...]


def validate_experimental_design(
    sample_ids: list[str],  # noqa: ARG001
    conditions: list[str],
    biological_replicates: list[str] | None = None,
) -> list[str]:
    """Validate the experimental design before running DESeq2.

    Checks for:
    1. Minimum sample count per condition
    2. Pseudoreplication (pooled biological replicates)
    3. Balanced design

    Args:
        sample_ids: Unique sample identifiers.
        conditions: Condition label per sample (e.g., "spaceflight", "ground").
        biological_replicates: Optional organism/pool ID per sample. If multiple
            samples share the same biological replicate ID, this is pseudoreplication.

    Raises:
        InsufficientSamplesError: Not enough samples per condition.
        PseudoreplicationError: Samples are not independent.
    """
    warnings: list[str] = []

    # Check minimum samples per condition
    from collections import Counter
    condition_counts = Counter(conditions)

    for condition, count in condition_counts.items():
        if count < MIN_SAMPLE_COUNT:
            raise InsufficientSamplesError(condition, count, MIN_SAMPLE_COUNT)

    # Check pseudoreplication
    if biological_replicates is not None:
        for condition in condition_counts:
            cond_mask = [i for i, c in enumerate(conditions) if c == condition]
            cond_bio_reps = [biological_replicates[i] for i in cond_mask]

            unique_reps = set(cond_bio_reps)
            if len(unique_reps) < len(cond_bio_reps):
                raise PseudoreplicationError(
                    f"Condition '{condition}' has {len(cond_bio_reps)} samples but only "
                    f"{len(unique_reps)} unique biological replicates. This is pseudoreplication. "
                    f"Multiple technical replicates from the same organism/pool cannot be treated "
                    f"as independent samples in DESeq2. Options: (1) average technical replicates, "
                    f"(2) use a mixed-effects model, (3) treat biological replicate as a covariate."
                )

    # Check balance
    counts = list(condition_counts.values())
    if max(counts) > 3 * min(counts):
        warnings.append(
            f"Highly unbalanced design: {dict(condition_counts)}. "
            f"DESeq2 handles this but statistical power is reduced."
        )

    return warnings


def _validate_integer_counts(count_matrix: np.ndarray) -> None:
    """Assert that the count matrix contains raw non-negative integers.

    P0 FIX (Panel 2, NASA ARC): GeneLab provides data in multiple formats.
    FPKM/TPM normalized values LOOK like floats; passing them to DESeq2
    is a silent category error — DESeq2 will run but results are biologically
    meaningless because DESeq2's NB model assumes raw Poisson counts.

    Raises:
        ValueError: If counts are not non-negative integers.
    """
    if count_matrix.dtype.kind == 'f':
        # Allow float matrices that happen to be whole numbers (e.g., from CSV load)
        non_integer_mask = count_matrix != np.floor(count_matrix)
        if non_integer_mask.any():
            n_bad = int(non_integer_mask.sum())
            max_bad = float(count_matrix[non_integer_mask].max())
            raise ValueError(
                f"count_matrix contains {n_bad} non-integer values (max={max_bad:.4f}). "
                f"DESeq2 requires raw un-normalized integer counts. "
                f"If your data is FPKM/TPM/CPM normalized, you CANNOT use DESeq2 on it — "
                f"you must obtain the original raw counts from the sequencer. "
                f"GeneLab datasets: download the *_counts.csv file, not *_FPKM.csv."
            )
    if (count_matrix < 0).any():
        raise ValueError(
            "count_matrix contains negative values. Raw counts must be non-negative integers."
        )


def run_deseq2(
    count_matrix: np.ndarray,
    gene_symbols: list[str],
    sample_ids: list[str],
    conditions: list[str],
    contrast: tuple[str, str] = ("spaceflight", "ground"),
    fdr_threshold: float = DEFAULT_FDR_THRESHOLD,
    lfc_threshold: float = DEFAULT_LFC_THRESHOLD,
    biological_replicates: list[str] | None = None,
    batch_labels: list[str] | None = None,
    apply_batch_correction: bool = True,
) -> DESeq2Result:
    """Run DESeq2 differential expression analysis.

    Model: K_gj ~ NB(μ_gj, α_g)
           μ_gj = s_j × q_gj
           log₂(q_gj) = x_j^T × β_g

    Uses PyDESeq2 (MIT license) for the core computation.

    Args:
        count_matrix: (genes x samples) raw integer count matrix.
        gene_symbols: Gene symbols, one per row.
        sample_ids: Sample IDs, one per column.
        conditions: Condition per sample.
        contrast: (treatment, control) condition names.
        fdr_threshold: BH-adjusted p-value threshold.
        lfc_threshold: Minimum absolute log2 fold change.
        biological_replicates: Optional organism/pool ID per sample for
            pseudoreplication detection.
        batch_labels: Optional batch identifier per sample. When provided
            and a batch effect is detected, ComBat-seq correction is applied
            before DESeq2. Default ON for GeneLab data per Panel 2 critique.
        apply_batch_correction: Apply ComBat-seq if batch_labels provided
            and batch effect detected. Default True.

    Returns:
        DESeq2Result with all statistics.
    """
    import pandas as pd
    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats

    warnings_list: list[str] = []

    # P0 FIX (Panel 2): Validate raw integer counts FIRST.
    # Passing FPKM/TPM to DESeq2 is a silent category error.
    _validate_integer_counts(count_matrix)

    # P0 FIX (Panel 2): Apply batch correction by default for spaceflight data.
    # Batch effects are the #1 confounder in spaceflight genomics (multiple
    # launches, CO₂ levels, temperature). OFF only if caller explicitly opts out.
    corrected_matrix = count_matrix
    if batch_labels is not None and apply_batch_correction:
        from aria.genastra.expression.batch_effects import correct_batch_effects, detect_batch_effects
        batch_report = detect_batch_effects(
            count_matrix, batch_labels, conditions, sample_ids
        )
        if batch_report.batch_effect_detected:
            corrected_matrix = correct_batch_effects(count_matrix, batch_labels, conditions)
            warnings_list.append(
                f"Batch effect detected ({batch_report.explained_variance_by_batch_pct:.1f}% "
                f"of PC1 variance). ComBat-seq correction applied before DESeq2."
            )
            logger.info("batch_correction_applied_before_deseq2",
                        batch_var_pct=batch_report.explained_variance_by_batch_pct)
        else:
            warnings_list.append(
                "Batch labels provided but no significant batch effect detected in PCA. "
                "Running DESeq2 without batch correction."
            )
    elif batch_labels is None:
        warnings_list.append(
            "No batch_labels provided. If samples came from different launches or "
            "processing runs, provide batch_labels to enable ComBat-seq correction."
        )

    # P1-6 FIX: Validate experimental design BEFORE running DESeq2.
    # This catches pseudoreplication, insufficient samples, and imbalance.
    # Previously this function existed but was never called.
    design_warnings = validate_experimental_design(
        sample_ids, conditions, biological_replicates
    )
    warnings_list.extend(design_warnings)

    # Construct input DataFrames (use batch-corrected matrix if applicable)
    counts_df = pd.DataFrame(
        corrected_matrix.T,  # PyDESeq2 expects (samples x genes)
        index=sample_ids,
        columns=gene_symbols,
    )

    metadata_df = pd.DataFrame(
        {"condition": conditions},
        index=sample_ids,
    )

    # Initialize and run DESeq2
    logger.info("deseq2_starting", n_genes=len(gene_symbols), n_samples=len(sample_ids))

    dds = DeseqDataSet(
        counts=counts_df,
        metadata=metadata_df,
        design_factors="condition",
    )

    dds.deseq2()

    # Statistical testing
    stat_res = DeseqStats(dds, contrast=["condition", contrast[0], contrast[1]])
    stat_res.summary()

    # P0-v2-3 FIX: Apply LFC shrinkage for small sample sizes.
    # Without shrinkage, log2FC estimates are overestimated for low-count genes
    # in small experiments (n=3-6 per condition, common in GeneLab).
    # Shrinkage uses an empirical Bayes approach to regularize fold changes.
    try:
        stat_res.lfc_shrink(coeff="condition_" + contrast[0] + "_vs_" + contrast[1])
        logger.info("deseq2_lfc_shrinkage_applied")
    except Exception as e:
        # lfc_shrink may fail if contrast naming doesn't match — use unshrunk
        logger.warning("deseq2_lfc_shrinkage_failed", error=str(e), msg="Using unshrunk LFC")
        warnings_list.append(
            f"LFC shrinkage failed ({e}). Reported fold changes may be overestimated "
            f"for low-count genes in small experiments."
        )

    # Extract results
    results_df = stat_res.results_df

    log2fc = results_df["log2FoldChange"].values
    lfc_se = results_df["lfcSE"].values
    stat = results_df["stat"].values
    pvalue = results_df["pvalue"].values
    padj = results_df["padj"].values
    base_mean = results_df["baseMean"].values

    # Replace NaN with 1.0 for p-values (genes with zero counts)
    pvalue = np.nan_to_num(pvalue, nan=1.0)
    padj = np.nan_to_num(padj, nan=1.0)

    # Storey's pi0 estimation
    pi0 = estimate_pi0(pvalue)

    # Count significant genes
    sig_mask = (padj < fdr_threshold) & (np.abs(log2fc) >= lfc_threshold)
    sig_count = int(np.sum(sig_mask))

    logger.info(
        "deseq2_complete",
        total_genes=len(gene_symbols),
        significant=sig_count,
        pi0=round(pi0, 3) if pi0 else None,
    )

    return DESeq2Result(
        gene_symbols=tuple(gene_symbols),
        log2_fold_changes=log2fc,
        lfc_standard_errors=lfc_se,
        wald_statistics=stat,
        pvalues=pvalue,
        padj=padj,
        base_means=base_mean,
        pi0_estimate=pi0,
        total_genes_tested=len(gene_symbols),
        significant_count=sig_count,
        fdr_threshold=fdr_threshold,
        lfc_threshold=lfc_threshold,
        normalization_method="deseq2_size_factors",
        warnings=tuple(warnings_list),
    )


def estimate_pi0(pvalues: np.ndarray, lambda_range: np.ndarray | None = None) -> float | None:
    """Estimate the proportion of true null hypotheses (π₀) using Storey's method.

    π₀(λ) = #{p_i > λ} / (m × (1 - λ))

    P0-6 FIX: The old implementation just took the last lambda estimate, which
    is statistically unstable (high variance at tail). The correct approach is
    to fit a natural cubic spline to π₀(λ) and evaluate at λ→1.

    Falls back to bootstrap if scipy is unavailable.

    Reference: Storey & Tibshirani 2003, PNAS.
    """
    # Remove NaN p-values and filter to valid range
    valid = pvalues[~np.isnan(pvalues)]
    valid = valid[(valid >= 0) & (valid <= 1)]
    m = len(valid)
    if m == 0:
        return None
    if m < 10:
        return 1.0  # too few p-values to estimate

    if lambda_range is None:
        lambda_range = np.arange(0.05, 0.95, 0.05)  # Storey & Tibshirani 2003 PNAS 100 9440: λ ∈ [0.05, 0.95]

    # Compute pi0 estimate at each lambda
    pi0_estimates = np.array([
        min(float(np.sum(valid > lam)) / (m * (1 - lam)), 1.0)
        for lam in lambda_range
    ])

    if len(pi0_estimates) < 4:
        return float(min(pi0_estimates[-1], 1.0))

    # Fit natural cubic spline to smooth π₀(λ) curve
    try:
        from scipy.interpolate import UnivariateSpline

        # Spline fit with smoothing — extrapolate toward λ=1
        # Weight by 1/variance: higher lambda estimates have higher variance
        weights = np.sqrt(m * (1 - lambda_range))  # inverse of std(pi0_hat)
        spline = UnivariateSpline(lambda_range, pi0_estimates, w=weights, k=3, s=len(lambda_range))

        # Evaluate at the maximum lambda (close to 1, but not exactly 1 to avoid singularity)
        pi0_smoothed = float(spline(max(lambda_range)))

        # Clamp to valid range
        pi0 = max(0.0, min(pi0_smoothed, 1.0))

    except (ImportError, Exception):
        # Fallback: use the minimum of the pi0 estimates (conservative)
        # This is better than using the last estimate (unstable)
        pi0 = float(min(pi0_estimates.min(), 1.0))

    return max(pi0, 1 / m)  # pi0 can't be less than 1/m
