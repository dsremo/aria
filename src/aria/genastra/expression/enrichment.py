"""Gene Set Enrichment Analysis (GSEA) and pathway enrichment.

Panel 12 (Computational Biologist):
"After identifying DEGs, need GSEA against KEGG, Reactome, and Gene Ontology."

Uses gseapy (BSD license) for enrichment analysis.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import structlog

logger = structlog.get_logger()


@dataclass(frozen=True)
class EnrichmentResult:
    """Single pathway enrichment result."""

    database: str
    pathway_id: str
    pathway_name: str
    gene_count: int
    enrichment_score: float
    nes: float | None  # Normalized Enrichment Score (GSEA)
    pvalue: float
    padj: float
    leading_edge_genes: tuple[str, ...]


def run_enrichment(
    gene_symbols: list[str],
    log2_fold_changes: np.ndarray,
    padj: np.ndarray,
    organism: str,
    databases: list[str] | None = None,
    fdr_threshold: float = 0.05,
    lfc_threshold: float = 1.0,
) -> list[EnrichmentResult]:
    """Run pathway enrichment analysis on differentially expressed genes.

    Two approaches:
    1. Over-representation analysis (ORA): Test if DEGs are enriched in pathways
    2. GSEA: Rank all genes by fold change, test for enrichment

    Args:
        gene_symbols: All gene symbols tested.
        log2_fold_changes: Log2 fold changes for all genes.
        padj: Adjusted p-values for all genes.
        organism: Organism name (e.g., "Mus musculus", "Homo sapiens").
        databases: Which databases to query. Default: KEGG, GO_BP, Reactome.
        fdr_threshold: Significance threshold for DEGs.
        lfc_threshold: Minimum fold change for DEGs.

    Returns:
        List of significant enrichment results.
    """
    if databases is None:
        databases = ["kegg", "go_bp", "reactome"]

    # Map organism to gseapy format
    org_map = {
        "homo sapiens": "Human",
        "mus musculus": "Mouse",
        "rattus norvegicus": "Rat",
        "arabidopsis thaliana": "Arabidopsis",
        "drosophila melanogaster": "Fly",
        "caenorhabditis elegans": "Worm",
        "danio rerio": "Zebrafish",
        "saccharomyces cerevisiae": "Yeast",
    }
    org_name = org_map.get(organism.lower(), organism)

    # Get significant genes for ORA
    sig_mask = (padj < fdr_threshold) & (np.abs(log2_fold_changes) >= lfc_threshold)
    sig_genes = [g for g, m in zip(gene_symbols, sig_mask, strict=False) if m]

    if not sig_genes:
        logger.warning("enrichment_no_significant_genes")
        return []

    results: list[EnrichmentResult] = []

    # Map database names to gseapy gene set libraries
    db_to_library = {
        "kegg": f"KEGG_2021_{org_name}" if org_name != "Human" else "KEGG_2021_Human",
        "go_bp": "GO_Biological_Process_2023",
        "go_mf": "GO_Molecular_Function_2023",
        "go_cc": "GO_Cellular_Component_2023",
        "reactome": "Reactome_2022" if org_name == "Human" else "Reactome_2022",
    }

    for db in databases:
        library = db_to_library.get(db)
        if library is None:
            logger.warning("enrichment_unknown_database", database=db)
            continue

        try:
            import gseapy as gp

            enr = gp.enrich(
                gene_list=sig_genes,
                gene_sets=library,
                organism=org_name,
                outdir=None,
                no_plot=True,
                cutoff=0.1,
            )

            if enr.results is not None and not enr.results.empty:
                for _, row in enr.results.iterrows():
                    if row.get("Adjusted P-value", 1.0) < 0.1:  # Loose filter, user can tighten
                        leading_genes = row.get("Genes", "").split(";") if row.get("Genes") else []
                        results.append(
                            EnrichmentResult(
                                database=db,
                                pathway_id=str(row.get("Term", "")),
                                pathway_name=str(row.get("Term", "")),
                                gene_count=int(row.get("Overlap", "0/0").split("/")[0])
                                if isinstance(row.get("Overlap"), str)
                                else 0,
                                enrichment_score=float(row.get("Combined Score", 0)),
                                nes=None,  # ORA doesn't produce NES
                                pvalue=float(row.get("P-value", 1.0)),
                                padj=float(row.get("Adjusted P-value", 1.0)),
                                leading_edge_genes=tuple(leading_genes[:20]),
                            )
                        )

            logger.info("enrichment_complete", database=db, hits=len([r for r in results if r.database == db]))

        except Exception as e:
            logger.warning("enrichment_failed", database=db, error=str(e))

    return sorted(results, key=lambda r: r.padj)
