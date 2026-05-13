"""Gene expression analysis API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from aria.genastra.api.schemas import (
    AnalyzeExpressionRequest,
    ImportExpressionRequest,
    JobResponse,
)
from aria.genastra.core.models import JobStatus, JobType, new_id

if TYPE_CHECKING:
    from aria.genastra.api.dependencies import Auth, DbPool

router = APIRouter(prefix="/expression", tags=["expression"])


@router.post("/import", response_model=JobResponse, status_code=202)
async def import_expression(
    body: ImportExpressionRequest,
    auth: Auth,
    pool: DbPool,
) -> JobResponse:
    """Import a gene expression dataset from NASA GeneLab/OSDR."""
    auth.require_scope("expression:write")

    job_id = new_id()
    import json

    await pool.execute(
        """
        INSERT INTO jobs (id, tenant_id, job_type, status, input_params, provenance)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        job_id, auth.tenant_id, JobType.GENE_EXPRESSION.value,
        JobStatus.PENDING.value,
        json.dumps({
            "action": "import",
            "genelab_accession": body.genelab_accession,
            "title": body.title,
            "organism": body.organism,
        }),
        json.dumps({"source": "nasa_osdr"}),
    )

    return JobResponse(job_id=job_id, status=JobStatus.QUEUED, estimated_time_seconds=120)


@router.post("/analyze", response_model=JobResponse, status_code=202)
async def analyze_expression(
    body: AnalyzeExpressionRequest,
    auth: Auth,
    pool: DbPool,
) -> JobResponse:
    """Run differential expression analysis on an imported dataset."""
    auth.require_scope("expression:write")

    job_id = new_id()
    import json

    await pool.execute(
        """
        INSERT INTO jobs (id, tenant_id, job_type, status, input_params, provenance)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        job_id, auth.tenant_id, JobType.GENE_EXPRESSION.value,
        JobStatus.PENDING.value,
        json.dumps({
            "action": "analyze",
            "experiment_id": str(body.experiment_id),
            "contrast": body.contrast,
            "fdr_threshold": body.fdr_threshold,
            "lfc_threshold": body.lfc_threshold,
            "batch_correction": body.batch_correction,
            "enrichment_databases": body.enrichment_databases,
        }),
        json.dumps({"method": "deseq2", "enrichment": "gseapy"}),
    )

    return JobResponse(job_id=job_id, status=JobStatus.QUEUED, estimated_time_seconds=300)
