"""Expression analysis worker — Redis Streams consumer.

Consumes jobs from the ``expression`` stream and runs:
  1. NASA GeneLab / OSDR data fetch (via circuit breaker)
  2. DESeq2 differential expression analysis
  3. ComBat-seq batch correction (multi-mission experiments)
  4. GSEA against KEGG + Reactome + GO
  5. Stores results to PostgreSQL, signals completion

Redis stream: ``expression:jobs``
Result stream: ``expression:results``

Each job payload:
  {
    "job_id": "<uuid>",
    "tenant_id": "<uuid>",
    "experiment_id": "<str>",
    "sample_groups": {"control": [...], "treatment": [...]},
    "options": {
      "lfc_shrink": true,
      "fdr_threshold": 0.05,
      "gsea": true,
      "batch_correct": false
    }
  }
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from aria.genastra.workers.base import BaseWorker

logger = structlog.get_logger()


class ExpressionWorker(BaseWorker):
    """Processes differential expression analysis jobs from Redis Streams."""

    stream_name = "expression:jobs"
    group_name = "expression-workers"
    consumer_prefix = "expr-"

    async def process_job(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Run full expression analysis pipeline for one job.

        Args:
            job_id: Unique job identifier (UUID string).
            payload: Job parameters from Redis stream message.

        Returns:
            Result dict written back to ``expression:results`` stream.
        """
        tenant_id = payload["tenant_id"]
        experiment_id = payload["experiment_id"]
        sample_groups = payload["sample_groups"]
        options = payload.get("options", {})

        log = logger.bind(job_id=job_id, tenant_id=tenant_id, experiment_id=experiment_id)
        log.info("expression_job_start")

        await self._update_status(job_id, "running", "Fetching expression data")

        # ── Step 1: Fetch raw counts from NASA GeneLab ────────────────────────
        from aria.genastra.expression.genelab_client import GenelabClient
        async with GenelabClient() as client:
            raw_counts = await client.get_counts(experiment_id)

        log.info("expression_counts_fetched", n_genes=len(raw_counts))
        await self._update_status(job_id, "running", f"Loaded {len(raw_counts)} genes")

        # ── Step 2: Batch correction (optional) ──────────────────────────────
        if options.get("batch_correct", False):
            from aria.genastra.expression.batch_effects import combat_seq_correct
            await self._update_status(job_id, "running", "Applying ComBat-seq batch correction")
            raw_counts = combat_seq_correct(raw_counts, sample_groups)
            log.info("batch_correction_applied")

        # ── Step 3: DESeq2 differential expression ───────────────────────────
        from aria.genastra.expression.deseq2 import run_deseq2
        await self._update_status(job_id, "running", "Running DESeq2")

        deseq_result = run_deseq2(
            counts=raw_counts,
            sample_groups=sample_groups,
            lfc_shrink=options.get("lfc_shrink", True),
            fdr_threshold=options.get("fdr_threshold", 0.05),
        )

        n_sig = int((deseq_result["padj"] < options.get("fdr_threshold", 0.05)).sum())
        log.info("deseq2_done", n_significant=n_sig)
        await self._update_status(job_id, "running", f"DESeq2 complete — {n_sig} significant genes")

        # ── Step 4: Gene Set Enrichment Analysis ─────────────────────────────
        gsea_result: dict[str, Any] = {}
        if options.get("gsea", True):
            from aria.genastra.expression.enrichment import run_gsea
            await self._update_status(job_id, "running", "Running GSEA (KEGG + Reactome + GO)")
            gsea_result = run_gsea(
                deseq_result,
                gene_sets=["KEGG_2021_Human", "Reactome_2022", "GO_Biological_Process_2023"],
                fdr_threshold=options.get("fdr_threshold", 0.05),
            )
            n_pathways = sum(len(v) for v in gsea_result.values())
            log.info("gsea_done", n_enriched_pathways=n_pathways)

        # ── Step 5: Compile and return result ────────────────────────────────
        result = {
            "job_id": job_id,
            "experiment_id": experiment_id,
            "n_genes_tested": len(deseq_result),
            "n_significant": n_sig,
            "top_genes": _top_genes(deseq_result, n=20),
            "gsea": gsea_result,
            "deseq_summary": {
                "median_lfc": float(deseq_result["log2FoldChange"].median()),
                "min_padj": float(deseq_result["padj"].min()),
                "pi0": float(deseq_result.get("pi0", 1.0).iloc[0])
                       if "pi0" in deseq_result else None,
            },
        }

        log.info("expression_job_done", n_significant=n_sig)
        return result


def _top_genes(deseq_result: Any, n: int = 20) -> list[dict[str, Any]]:
    """Return the top N most significant genes by adjusted p-value."""
    try:
        top = deseq_result.nsmallest(n, "padj")
        return [
            {
                "gene": str(row.get("gene", idx)),
                "log2fc": round(float(row["log2FoldChange"]), 3),
                "padj": float(row["padj"]),
                "baseMean": float(row.get("baseMean", 0)),
            }
            for idx, row in top.iterrows()
        ]
    except Exception:
        return []


async def main() -> None:
    """Entry point for standalone worker process."""
    worker = ExpressionWorker()
    logger.info("expression_worker_starting")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
