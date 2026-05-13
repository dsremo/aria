"""Radiation damage prediction API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from aria.genastra.api.schemas import JobResponse, PredictRadiationRequest
from aria.genastra.core.models import JobStatus, JobType, ParticleType, RadiationEnvironment, RadiationType, new_id

if TYPE_CHECKING:
    from aria.genastra.api.dependencies import Auth, DbPool

router = APIRouter(prefix="/radiation", tags=["radiation"])


@router.post("/predict", response_model=JobResponse, status_code=202)
async def predict_radiation_damage(
    body: PredictRadiationRequest,
    auth: Auth,
    pool: DbPool,
) -> JobResponse:
    """Predict radiation damage on a protein.

    Requires either protein_id (existing protein) or sequence (inline).
    Radiation environment MUST be fully specified — radiation is NOT binary.
    """
    auth.require_scope("radiation:write")

    if body.protein_id is None and body.sequence is None:
        from aria.genastra.core.exceptions import GenAstraError
        raise GenAstraError("Either protein_id or sequence must be provided")

    # Validate radiation environment
    env = RadiationEnvironment(
        radiation_type=RadiationType(body.radiation_environment.type),
        dose_mgy=body.radiation_environment.dose_mgy,
        dose_rate_mgy_per_day=body.radiation_environment.dose_rate_mgy_per_day,
        particle_type=ParticleType(body.radiation_environment.particle_type),
        shielding_g_per_cm2=body.radiation_environment.shielding_g_per_cm2,
        let_kev_per_um=body.radiation_environment.let_kev_per_um,
        duration_days=body.radiation_environment.duration_days,
    )

    from aria.genastra.radiation.environment import validate_radiation_environment
    warnings = validate_radiation_environment(env)

    job_id = new_id()
    import json

    await pool.execute(
        """
        INSERT INTO jobs (id, tenant_id, job_type, status, input_params, provenance)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        job_id, auth.tenant_id, JobType.RADIATION_DAMAGE.value,
        JobStatus.PENDING.value,
        json.dumps({
            "protein_id": str(body.protein_id) if body.protein_id else None,
            "sequence_length": len(body.sequence) if body.sequence else None,
            "radiation_type": body.radiation_environment.type.value,
            "dose_mgy": body.radiation_environment.dose_mgy,
            "dose_response_model": body.dose_response_model.value,
            "validation_warnings": warnings,
        }),
        json.dumps({"model": "heuristic_v1"}),
    )

    return JobResponse(job_id=job_id, status=JobStatus.QUEUED, estimated_time_seconds=60)
