"""Protein structure prediction API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from aria.genastra.api.schemas import (
    BulkPredictRequest,
    JobResponse,
    PredictStructureRequest,
    ProteinLookupResponse,
)
from aria.genastra.core.models import JobStatus, JobType, new_id

if TYPE_CHECKING:
    from aria.genastra.api.dependencies import Auth, DbPool

router = APIRouter(prefix="/proteins", tags=["proteins"])


@router.post("/predict", response_model=JobResponse, status_code=202)
async def predict_structure(
    body: PredictStructureRequest,
    auth: Auth,
    pool: DbPool,
) -> JobResponse:
    """Submit a protein sequence for structure prediction.

    Returns a job ID immediately. Poll /jobs/{job_id} for results,
    or provide a webhook_url for async notification.
    """
    auth.require_scope("protein:write")

    job_id = new_id()
    protein_id = new_id()

    # Store protein sequence
    import hashlib
    seq_hash = hashlib.sha256(body.sequence.encode()).hexdigest()

    await pool.execute(
        """
        INSERT INTO proteins (id, tenant_id, uniprot_id, sequence, sequence_hash, sequence_length, organism, gene_name)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (tenant_id, sequence_hash) DO NOTHING
        """,
        protein_id, auth.tenant_id, body.uniprot_id, body.sequence,
        seq_hash, len(body.sequence), body.organism, body.gene_name,
    )

    # Create job
    import json
    await pool.execute(
        """
        INSERT INTO jobs (id, tenant_id, job_type, status, input_params, webhook_url, provenance)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        job_id, auth.tenant_id, JobType.STRUCTURE_PREDICTION.value,
        JobStatus.PENDING.value,
        json.dumps({"protein_id": str(protein_id), "sequence_length": len(body.sequence)}),
        body.webhook_url,
        json.dumps({"model": "esmfold_v1"}),
    )

    # Enqueue to Redis Stream for GPU worker
    from aria.genastra.db.connection import get_redis
    r = get_redis()
    if r:
        await r.xadd("genastra:gpu_jobs", {
            "job_id": str(job_id),
            "sequence": body.sequence,
            "tenant_id": str(auth.tenant_id),
            "protein_id": str(protein_id),
        })

    estimated = max(30, len(body.sequence) // 20)

    return JobResponse(job_id=job_id, status=JobStatus.QUEUED, estimated_time_seconds=estimated)


@router.get("/lookup", response_model=ProteinLookupResponse)
async def lookup_protein(
    uniprot_id: str,
    auth: Auth,
    pool: DbPool,
) -> ProteinLookupResponse:
    """Look up an existing structure by UniProt ID.

    Checks local cache, then AlphaFold EBI DB, then ESM Atlas.
    """
    auth.require_scope("protein:read")

    # Check local DB first
    row = await pool.fetchrow(
        """
        SELECT p.id, sp.pdb_s3_key, sp.mean_plddt
        FROM proteins p
        JOIN structure_predictions sp ON sp.protein_id = p.id
        WHERE p.tenant_id = $1 AND p.uniprot_id = $2
        ORDER BY sp.created_at DESC LIMIT 1
        """,
        auth.tenant_id, uniprot_id,
    )

    if row:
        return ProteinLookupResponse(
            protein_id=row["id"],
            uniprot_id=uniprot_id,
            source="cache",
            pdb_url=row["pdb_s3_key"],
            mean_plddt=row["mean_plddt"],
        )

    # Try external databases
    from aria.genastra.protein.uniprot_client import lookup_structure
    ext = await lookup_structure(uniprot_id)

    if ext:
        return ProteinLookupResponse(
            protein_id=None,
            uniprot_id=uniprot_id,
            source=ext.source,
            pdb_url=ext.pdb_url,
            mean_plddt=ext.mean_plddt,
        )

    return ProteinLookupResponse(
        protein_id=None,
        uniprot_id=uniprot_id,
        source="not_found",
        pdb_url=None,
        mean_plddt=None,
    )


@router.post("/bulk", response_model=JobResponse, status_code=202)
async def bulk_predict(
    body: BulkPredictRequest,
    auth: Auth,
    pool: DbPool,
) -> JobResponse:
    """Submit up to 10,000 sequences for bulk structure prediction."""
    auth.require_scope("protein:write")

    job_id = new_id()
    import json

    await pool.execute(
        """
        INSERT INTO jobs (id, tenant_id, job_type, status, input_params, webhook_url, provenance)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        job_id, auth.tenant_id, JobType.BULK_STRUCTURE.value,
        JobStatus.PENDING.value,
        json.dumps({"total_sequences": len(body.sequences)}),
        body.webhook_url,
        json.dumps({"model": "esmfold_v1"}),
    )

    estimated_minutes = len(body.sequences) * 45 // 60  # ~45s per sequence

    return JobResponse(
        job_id=job_id,
        status=JobStatus.QUEUED,
        estimated_time_seconds=estimated_minutes * 60,
    )
