"""Job status and management API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from aria.genastra.api.schemas import JobDetailResponse
from aria.genastra.core.exceptions import JobAlreadyCompletedError, JobNotFoundError

if TYPE_CHECKING:
    from uuid import UUID

    from aria.genastra.api.dependencies import Auth, DbPool

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: UUID, auth: Auth, pool: DbPool) -> JobDetailResponse:
    """Get job status and details."""
    row = await pool.fetchrow(
        """
        SELECT id, job_type, status, input_params, result_s3_key,
               error_message, created_at, started_at, completed_at
        FROM jobs
        WHERE id = $1 AND tenant_id = $2
        """,
        job_id, auth.tenant_id,
    )

    if row is None:
        raise JobNotFoundError(f"Job {job_id} not found")

    result_url = row["result_s3_key"]  # Would be a pre-signed URL in production

    return JobDetailResponse(
        id=row["id"],
        job_type=row["job_type"],
        status=row["status"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        result_url=result_url,
        error_message=row["error_message"],
    )


@router.post("/{job_id}/cancel", status_code=200)
async def cancel_job(job_id: UUID, auth: Auth, pool: DbPool) -> dict[str, str]:
    """Cancel a pending or queued job."""
    row = await pool.fetchrow(
        "SELECT status FROM jobs WHERE id = $1 AND tenant_id = $2",
        job_id, auth.tenant_id,
    )

    if row is None:
        raise JobNotFoundError(f"Job {job_id} not found")

    if row["status"] in ("completed", "failed", "cancelled"):
        raise JobAlreadyCompletedError(f"Job {job_id} is already {row['status']}")

    await pool.execute(
        "UPDATE jobs SET status = 'cancelled' WHERE id = $1",
        job_id,
    )

    return {"status": "cancelled", "job_id": str(job_id)}


@router.get("/", response_model=list[JobDetailResponse])
async def list_jobs(
    auth: Auth,
    pool: DbPool,
    status: str | None = None,
    job_type: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> list[JobDetailResponse]:
    """List jobs for the current tenant with optional filters."""
    conditions = ["tenant_id = $1"]
    params: list = [auth.tenant_id]
    idx = 2

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    if job_type:
        conditions.append(f"job_type = ${idx}")
        params.append(job_type)
        idx += 1

    where = " AND ".join(conditions)
    offset = (page - 1) * per_page

    sql = (
        "SELECT id, job_type, status, input_params, result_s3_key, "
        "error_message, created_at, started_at, completed_at "
        f"FROM jobs WHERE {where} ORDER BY created_at DESC "
        f"LIMIT {per_page} OFFSET {offset}"  # nosec B608
    )
    rows = await pool.fetch(sql, *params)

    return [
        JobDetailResponse(
            id=row["id"],
            job_type=row["job_type"],
            status=row["status"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            result_url=row["result_s3_key"],
            error_message=row["error_message"],
        )
        for row in rows
    ]
