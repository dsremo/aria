"""ETL pipeline for GeneLab/OSDR expression data.

Transforms raw GeneLab API responses into normalized count matrices
ready for DESeq2 analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger()


@dataclass
class ExpressionDataset:
    """Parsed and validated expression dataset."""

    count_matrix: np.ndarray  # (genes x samples)
    gene_symbols: list[str]
    ensembl_ids: list[str | None]
    sample_ids: list[str]
    conditions: list[str]
    batch_labels: list[str]
    organism: str
    platform: str
    confounders: list[str]


def parse_genelab_response(
    raw_data: dict[str, Any],
    accession: str,
) -> ExpressionDataset:
    """Parse GeneLab API expression data into a structured dataset.

    GeneLab provides data in various formats depending on the study.
    This function handles the common formats and normalizes them.
    """
    # Extract sample metadata
    samples = raw_data.get("samples", raw_data.get("columns", []))
    genes = raw_data.get("genes", raw_data.get("rows", []))
    values = raw_data.get("values", raw_data.get("data", []))

    sample_ids: list[str] = []
    conditions: list[str] = []
    batch_labels: list[str] = []

    for s in samples:
        if isinstance(s, dict):
            sample_ids.append(s.get("id", s.get("name", str(s))))
            conditions.append(s.get("condition", s.get("factor", "unknown")))
            batch_labels.append(s.get("batch", s.get("run", "batch_1")))
        else:
            sample_ids.append(str(s))
            conditions.append("unknown")
            batch_labels.append("batch_1")

    gene_symbols: list[str] = []
    ensembl_ids: list[str | None] = []

    for g in genes:
        if isinstance(g, dict):
            gene_symbols.append(g.get("symbol", g.get("gene_id", str(g))))
            ensembl_ids.append(g.get("ensembl_id"))
        else:
            gene_symbols.append(str(g))
            ensembl_ids.append(None)

    # Build count matrix
    if isinstance(values, list) and len(values) > 0:
        count_matrix = np.array(values, dtype=np.float64)
        # Ensure (genes x samples) orientation
        if count_matrix.shape[0] == len(sample_ids) and count_matrix.shape[1] == len(gene_symbols):
            count_matrix = count_matrix.T  # Transpose from (samples x genes) to (genes x samples)
    else:
        count_matrix = np.zeros((len(gene_symbols), len(sample_ids)), dtype=np.float64)

    # Round to integers (raw counts must be integers for DESeq2)
    count_matrix = np.maximum(count_matrix, 0).astype(int)

    # Detect known spaceflight confounders
    confounders = _detect_confounders(raw_data, accession)

    organism = raw_data.get("organism", "unknown")
    platform = raw_data.get("platform", raw_data.get("assay_type", "RNA-seq"))

    logger.info(
        "etl_parsed",
        accession=accession,
        genes=len(gene_symbols),
        samples=len(sample_ids),
        conditions=list(set(conditions)),
    )

    return ExpressionDataset(
        count_matrix=count_matrix,
        gene_symbols=gene_symbols,
        ensembl_ids=ensembl_ids,
        sample_ids=sample_ids,
        conditions=conditions,
        batch_labels=batch_labels,
        organism=organism,
        platform=platform,
        confounders=confounders,
    )


def _detect_confounders(raw_data: dict[str, Any], accession: str) -> list[str]:  # noqa: ARG001
    """Detect known confounders in spaceflight experiments.

    Spaceflight experiments systematically confound multiple variables.
    We flag known ones so users understand limitations.
    """
    confounders: list[str] = []

    description = str(raw_data.get("description", "")).lower()
    factors = raw_data.get("factors", [])

    # Common spaceflight confounders
    if "launch" in description or "vibration" in description:
        confounders.append("launch_vibration")

    if "co2" in description or "carbon dioxide" in description:
        confounders.append("co2_elevation")

    if any("temperature" in str(f).lower() for f in factors):
        confounders.append("temperature_variation")

    if "radiation" in description and "cosmic" in description:
        confounders.append("cosmic_radiation")

    if "microgravity" in description:
        confounders.append("microgravity")

    # Always add these for spaceflight experiments
    if any(kw in description for kw in ("iss", "space station", "spaceflight", "shuttle")):
        if "launch_vibration" not in confounders:
            confounders.append("launch_vibration")
        if "cosmic_radiation" not in confounders:
            confounders.append("cosmic_radiation")
        if "microgravity" not in confounders:
            confounders.append("microgravity")

    return confounders


def filter_low_count_genes(
    dataset: ExpressionDataset,
    min_total_count: int = 10,
    min_samples_with_counts: int = 2,
) -> ExpressionDataset:
    """Filter out genes with very low counts.

    DESeq2's independent filtering handles this internally, but
    pre-filtering improves speed and reduces multiple testing burden.
    """
    total_counts = dataset.count_matrix.sum(axis=1)
    samples_with_counts = (dataset.count_matrix > 0).sum(axis=1)

    keep_mask = (total_counts >= min_total_count) & (samples_with_counts >= min_samples_with_counts)

    filtered_genes = [g for g, k in zip(dataset.gene_symbols, keep_mask, strict=False) if k]
    filtered_ensembl = [e for e, k in zip(dataset.ensembl_ids, keep_mask, strict=False) if k]

    n_removed = len(dataset.gene_symbols) - len(filtered_genes)
    logger.info("etl_filtered_genes", removed=n_removed, remaining=len(filtered_genes))

    return ExpressionDataset(
        count_matrix=dataset.count_matrix[keep_mask],
        gene_symbols=filtered_genes,
        ensembl_ids=filtered_ensembl,
        sample_ids=dataset.sample_ids,
        conditions=dataset.conditions,
        batch_labels=dataset.batch_labels,
        organism=dataset.organism,
        platform=dataset.platform,
        confounders=dataset.confounders,
    )
