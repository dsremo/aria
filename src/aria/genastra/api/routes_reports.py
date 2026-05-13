"""Report generation API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from aria.genastra.api.schemas import GenerateReportRequest, JobResponse
from aria.genastra.core.models import JobStatus, JobType, new_id

if TYPE_CHECKING:
    from aria.genastra.api.dependencies import Auth, DbPool

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/generate", response_model=JobResponse, status_code=202)
async def generate_report(
    body: GenerateReportRequest,
    auth: Auth,
    pool: DbPool,
) -> JobResponse:
    """Generate a PDF/JSON report for analysis results."""
    auth.require_scope("protein:read")

    job_id = new_id()
    import json

    await pool.execute(
        """
        INSERT INTO jobs (id, tenant_id, job_type, status, input_params, provenance)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        job_id, auth.tenant_id, JobType.REPORT_GENERATION.value,
        JobStatus.PENDING.value,
        json.dumps({
            "report_type": body.type,
            "resource_ids": [str(rid) for rid in body.resource_ids],
            "format": body.format,
            "include_provenance": body.include_provenance,
        }),
        json.dumps({}),
    )

    return JobResponse(job_id=job_id, status=JobStatus.QUEUED, estimated_time_seconds=30)
