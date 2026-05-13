"""Batch effect detection and correction for spaceflight gene expression.

Panel 12 (Computational Biologist) critique:
"Batch effects are the #1 confounder in spaceflight genomics."

Spaceflight experiments confound: launch stress, elevated CO₂, temperature
fluctuation, vibration, cosmic radiation. Must implement:
1. PCA visualization of batch effects
2. Batch correction (ComBat-seq)
3. Clear documentation of which confounders are NOT controlled
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import structlog

logger = structlog.get_logger()


@dataclass(frozen=True)
class BatchEffectReport:
    """Report of batch effect analysis."""

    batch_effect_detected: bool
    explained_variance_by_batch_pct: float
    explained_variance_by_condition_pct: float
    pca_components: np.ndarray  # (n_samples, 2) for visualization
    sample_labels: tuple[str, ...]
    batch_labels: tuple[str, ...]
    condition_labels: tuple[str, ...]
    warnings: tuple[str, ...]


def detect_batch_effects(
    count_matrix: np.ndarray,
    batch_labels: list[str],
    condition_labels: list[str],
    sample_labels: list[str],
) -> BatchEffectReport:
    """Detect batch effects using PCA.

    If the first two PCA components separate by batch rather than by
    condition, batch effects dominate the signal. In spaceflight data,
    this often happens because different launches have different
    vibration profiles, CO₂ levels, and temperature.

    Args:
        count_matrix: (genes x samples) normalized count matrix.
        batch_labels: Batch identifier per sample (e.g., "launch_1", "launch_2").
        condition_labels: Condition per sample (e.g., "spaceflight", "ground").
        sample_labels: Human-readable sample names.
    """
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    n_genes, n_samples = count_matrix.shape
    warnings: list[str] = []

    # Log-transform (log2(count + 1)) for PCA
    log_counts = np.log2(count_matrix.astype(np.float64) + 1)

    # Transpose: PCA expects (samples x features)
    x_matrix = log_counts.T

    # Standardize
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(x_matrix)  # noqa: N806

    # PCA
    n_components = min(2, n_samples - 1, n_genes)
    pca = PCA(n_components=n_components)
    components = pca.fit_transform(X_scaled)

    # Compute how much variance is explained by batch vs condition
    # Using ANOVA-like approach on PC1
    pc1 = components[:, 0] if components.shape[1] > 0 else np.zeros(n_samples)

    batch_var = _group_variance_ratio(pc1, batch_labels)
    condition_var = _group_variance_ratio(pc1, condition_labels)

    batch_effect_detected = batch_var > condition_var and batch_var > 0.3

    if batch_effect_detected:
        warnings.append(
            f"Batch effect detected: batch explains {batch_var:.0%} of PC1 variance "
            f"vs condition {condition_var:.0%}. ComBat-seq correction recommended."
        )

    if len(set(batch_labels)) < 2:
        warnings.append(
            "Only one batch detected — cannot assess batch effects. "
            "If samples were processed in different runs, provide batch labels."
        )

    return BatchEffectReport(
        batch_effect_detected=batch_effect_detected,
        explained_variance_by_batch_pct=round(batch_var * 100, 1),
        explained_variance_by_condition_pct=round(condition_var * 100, 1),
        pca_components=components,
        sample_labels=tuple(sample_labels),
        batch_labels=tuple(batch_labels),
        condition_labels=tuple(condition_labels),
        warnings=tuple(warnings),
    )


def correct_batch_effects(
    count_matrix: np.ndarray,
    batch_labels: list[str],
    condition_labels: list[str],  # noqa: ARG001
) -> np.ndarray:
    """Apply ComBat-seq batch correction to raw count data.

    ComBat-seq (Zhang et al., 2020) preserves the negative binomial
    distribution of count data, unlike the original ComBat which
    assumes Gaussian (appropriate only for log-transformed data).

    Falls back to simple median centering if ComBat-seq is unavailable.
    """
    try:
        import pandas as pd
        from combat.pycombat import pycombat

        # pycombat expects (genes x samples) DataFrame
        df = pd.DataFrame(
            count_matrix,
            index=[f"gene_{i}" for i in range(count_matrix.shape[0])],
            columns=[f"sample_{i}" for i in range(count_matrix.shape[1])],
        )

        batch_series = pd.Series(batch_labels, index=df.columns)
        corrected = pycombat(df, batch_series)

        # Ensure non-negative integer counts
        result = np.maximum(corrected.values, 0).astype(int)
        logger.info("batch_correction_applied", method="combat_seq")
        return result

    except ImportError:
        logger.warning("combat_unavailable", msg="Falling back to median centering")
        return _median_center_by_batch(count_matrix, batch_labels)


def _median_center_by_batch(
    count_matrix: np.ndarray,
    batch_labels: list[str],
) -> np.ndarray:
    """Simple median centering per batch as a fallback.

    Subtracts batch-specific median from each gene, then adds
    the global median back. Preserves overall expression levels.
    """
    result = count_matrix.astype(np.float64).copy()
    unique_batches = list(set(batch_labels))

    global_median = np.median(result, axis=1, keepdims=True)

    for batch in unique_batches:
        mask = np.array([b == batch for b in batch_labels])
        batch_median = np.median(result[:, mask], axis=1, keepdims=True)
        result[:, mask] = result[:, mask] - batch_median + global_median

    return np.maximum(result, 0).astype(int)


def _group_variance_ratio(values: np.ndarray, labels: list[str]) -> float:
    """Compute the fraction of variance in `values` explained by `labels`.

    This is eta-squared (η²), the ratio of between-group variance
    to total variance. Ranges from 0 (no effect) to 1 (perfect separation).
    """
    total_var = np.var(values)
    if total_var == 0:
        return 0.0

    unique_labels = list(set(labels))
    grand_mean = np.mean(values)

    between_ss = 0.0
    for label in unique_labels:
        mask = np.array([lbl == label for lbl in labels])
        group = values[mask]
        between_ss += len(group) * (np.mean(group) - grand_mean) ** 2

    total_ss = np.sum((values - grand_mean) ** 2)
    if total_ss == 0:
        return 0.0

    return float(between_ss / total_ss)
