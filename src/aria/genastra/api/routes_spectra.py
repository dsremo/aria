"""Biosignature spectral analysis API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from aria.genastra.api.schemas import AnalyzeSpectraRequest, ImportSpectraRequest, JobResponse
from aria.genastra.core.models import JobStatus, JobType, new_id

if TYPE_CHECKING:
    from aria.genastra.api.dependencies import Auth, DbPool

router = APIRouter(prefix="/spectra", tags=["spectra"])


@router.post("/import", response_model=JobResponse, status_code=202)
async def import_spectra(
    body: ImportSpectraRequest,
    auth: Auth,
    pool: DbPool,
) -> JobResponse:
    """Import JWST spectral observation from MAST or direct upload."""
    auth.require_scope("spectra:write")

    job_id = new_id()
    import json

    await pool.execute(
        """
        INSERT INTO jobs (id, tenant_id, job_type, status, input_params, provenance)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        job_id, auth.tenant_id, JobType.SPECTRAL_ANALYSIS.value,
        JobStatus.PENDING.value,
        json.dumps({
            "action": "import",
            "target_name": body.target_name,
            "mast_obs_id": body.mast_obs_id,
            "instrument": body.instrument,
            "stellar_type": body.stellar_type,
        }),
        json.dumps({"source": "mast"}),
    )

    return JobResponse(job_id=job_id, status=JobStatus.QUEUED, estimated_time_seconds=60)


@router.post("/analyze", response_model=JobResponse, status_code=202)
async def analyze_spectra(
    body: AnalyzeSpectraRequest,
    auth: Auth,
    pool: DbPool,
) -> JobResponse:
    """Run Bayesian biosignature detection on an imported spectrum.

    Uses nested sampling (dynesty) to compute Bayes factors for each
    target molecule. Requires log₁₀(K) > 3.2 for a detection claim.
    """
    auth.require_scope("spectra:write")

    job_id = new_id()
    import json

    await pool.execute(
        """
        INSERT INTO jobs (id, tenant_id, job_type, status, input_params, provenance)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        job_id, auth.tenant_id, JobType.SPECTRAL_ANALYSIS.value,
        JobStatus.PENDING.value,
        json.dumps({
            "action": "analyze",
            "observation_id": str(body.observation_id),
            "target_molecules": body.target_molecules,
            "bayes_factor_threshold": body.bayes_factor_threshold,
            "prior_type": body.prior_type,
            "run_prior_sensitivity": body.run_prior_sensitivity,
            "check_abiotic_pathways": body.check_abiotic_pathways,
            "check_photochemical_stability": body.check_photochemical_stability,
        }),
        json.dumps({"method": "nested_sampling_dynesty", "n_live": 500}),
    )

    # Spectral analysis with nested sampling takes longer
    n_molecules = len(body.target_molecules)
    sensitivity_multiplier = 3 if body.run_prior_sensitivity else 1
    estimated = n_molecules * 120 * sensitivity_multiplier

    return JobResponse(job_id=job_id, status=JobStatus.QUEUED, estimated_time_seconds=estimated)
