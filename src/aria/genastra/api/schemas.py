"""Pydantic request/response models for the API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator

from aria.genastra.core.constants import (
    MAX_BULK_SEQUENCES,
    MAX_SEQUENCE_LENGTH,
    MIN_SEQUENCE_LENGTH,
    RESEARCH_DISCLAIMER,
    VALID_AMINO_ACIDS_EXTENDED,
)
from aria.genastra.core.models import (
    DetectionSignificance,
    DoseResponseModel,
    JobStatus,
    JobType,
    ParticleType,
    RadiationType,
)

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

# ── Common ─────────────────────────────────────────────────────────

class JobResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    estimated_time_seconds: int | None = None

    model_config = {"from_attributes": True}


class JobDetailResponse(BaseModel):
    id: UUID
    job_type: JobType
    status: JobStatus
    progress_pct: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    estimated_completion: datetime | None = None
    result_url: str | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total_pages: int
    total_items: int


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadinessResponse(BaseModel):
    status: str
    gpu: bool
    db: bool
    redis: bool


# ── Auth ───────────────────────────────────────────────────────────

class CreateApiKeyRequest(BaseModel):
    label: str = Field(max_length=100)
    scopes: list[str] = Field(
        default=["protein:read", "protein:write", "expression:read", "expression:write",
                 "radiation:read", "radiation:write", "spectra:read", "spectra:write"]
    )


class CreateApiKeyResponse(BaseModel):
    key: str  # full key — shown ONCE
    id: UUID
    prefix: str


class ApiKeyInfo(BaseModel):
    id: UUID
    prefix: str
    label: str
    scopes: list[str]
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime


# ── Protein ────────────────────────────────────────────────────────

class PredictStructureRequest(BaseModel):
    sequence: str = Field(min_length=MIN_SEQUENCE_LENGTH, max_length=MAX_SEQUENCE_LENGTH)
    uniprot_id: str | None = None
    organism: str | None = None
    gene_name: str | None = None
    webhook_url: str | None = None

    @field_validator("sequence")
    @classmethod
    def validate_sequence(cls, v: str) -> str:
        v = v.upper().strip()
        invalid = set(v) - VALID_AMINO_ACIDS_EXTENDED
        if invalid:
            raise ValueError(f"Invalid amino acid characters: {invalid}")
        return v


class BulkPredictRequest(BaseModel):
    sequences: list[dict[str, str]] = Field(max_length=MAX_BULK_SEQUENCES)
    webhook_url: str | None = None


class StructureResponse(BaseModel):
    protein_id: UUID
    model: str
    model_version: str
    mean_plddt: float
    ptm_score: float | None
    pdb_url: str
    per_residue_plddt: list[float]
    confidence_interpretation: str
    disclaimer: str = RESEARCH_DISCLAIMER

    model_config = {"from_attributes": True}


class ProteinLookupResponse(BaseModel):
    protein_id: UUID | None
    uniprot_id: str
    source: str  # 'cache', 'esm_atlas', 'alphafold_ebi'
    pdb_url: str | None
    mean_plddt: float | None


# ── Gene Expression ────────────────────────────────────────────────

class ImportExpressionRequest(BaseModel):
    genelab_accession: str | None = None
    title: str
    organism: str


class AnalyzeExpressionRequest(BaseModel):
    experiment_id: UUID
    contrast: list[str] = Field(min_length=2, max_length=2)
    fdr_threshold: float = Field(default=0.05, gt=0, lt=1)
    lfc_threshold: float = Field(default=1.0, ge=0)
    batch_correction: bool = True
    enrichment_databases: list[str] = Field(default=["kegg", "go_bp", "reactome"])


class DEGResult(BaseModel):
    gene_symbol: str
    ensembl_id: str | None
    log2_fold_change: float
    lfc_se: float
    padj: float
    base_mean: float


class ExpressionResultsResponse(BaseModel):
    experiment_id: UUID
    total_genes_tested: int
    significant_genes: int
    pi0_estimate: float | None
    fdr_method: str = "benjamini_hochberg"
    normalization: str
    batch_corrected: bool
    confounders_noted: list[str]
    genes: list[DEGResult]
    pagination: PaginationMeta
    disclaimer: str = RESEARCH_DISCLAIMER


class EnrichmentResult(BaseModel):
    pathway_id: str
    pathway_name: str
    nes: float | None
    padj: float
    gene_count: int
    leading_edge_genes: list[str]


class EnrichmentResponse(BaseModel):
    kegg: list[EnrichmentResult] = []
    go_bp: list[EnrichmentResult] = []
    reactome: list[EnrichmentResult] = []
    disclaimer: str = RESEARCH_DISCLAIMER


class QCResponse(BaseModel):
    pca_plot_url: str | None
    batch_effect_detected: bool
    sample_correlation_heatmap_url: str | None
    normalization_size_factors: dict[str, float]
    warnings: list[str]
    disclaimer: str = RESEARCH_DISCLAIMER


# ── Radiation ──────────────────────────────────────────────────────

class RadiationEnvironmentInput(BaseModel):
    type: RadiationType
    dose_mgy: float = Field(gt=0, description="Total dose in milliGray")
    dose_rate_mgy_per_day: float = Field(gt=0, description="Dose rate (chronic vs acute)")
    let_kev_per_um: float | None = Field(default=None, ge=0, description="Linear Energy Transfer")
    particle_type: ParticleType = ParticleType.PROTON
    shielding_g_per_cm2: float = Field(default=20.0, ge=0)
    duration_days: float | None = Field(default=None, gt=0)


class PredictRadiationRequest(BaseModel):
    protein_id: UUID | None = None
    sequence: str | None = None
    radiation_environment: RadiationEnvironmentInput
    dose_response_model: DoseResponseModel = DoseResponseModel.LNT
    genotype_variants: list[str] | None = None
    webhook_url: str | None = None

    @field_validator("sequence")
    @classmethod
    def validate_sequence(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.upper().strip()
        invalid = set(v) - VALID_AMINO_ACIDS_EXTENDED
        if invalid:
            raise ValueError(f"Invalid amino acid characters: {invalid}")
        if len(v) > MAX_SEQUENCE_LENGTH:
            raise ValueError(f"Sequence too long: {len(v)} > {MAX_SEQUENCE_LENGTH}")
        return v


class VulnerableRegion(BaseModel):
    residue_range: list[int]
    max_vulnerability_score: float
    residue_types: str
    mechanism: str
    functional_annotation: str | None


class RadiationResultsResponse(BaseModel):
    protein_id: UUID
    radiation_environment: RadiationEnvironmentInput
    model: str
    model_version: str
    overall_damage_score: float
    confidence_interval_95: list[float]
    dose_response_model: str
    vulnerable_regions: list[VulnerableRegion]
    per_residue_vulnerability: list[float]
    comparison_note: str | None
    disclaimer: str = RESEARCH_DISCLAIMER


# ── Spectra / Biosignatures ───────────────────────────────────────

class ImportSpectraRequest(BaseModel):
    target_name: str
    mast_obs_id: str | None = None
    instrument: str
    stellar_type: str | None = None
    stellar_teff_k: float | None = None
    planet_teq_k: float | None = None


class AnalyzeSpectraRequest(BaseModel):
    observation_id: UUID
    target_molecules: list[str] = Field(
        default=["DMS", "CH4", "O3", "N2O", "DMDS", "CO2", "H2O"]
    )
    bayes_factor_threshold: float = Field(default=3.2, description="log10(K) for strong evidence")
    prior_type: str = Field(default="empirical", pattern="^(empirical|uninformative|pessimistic)$")
    run_prior_sensitivity: bool = True
    check_abiotic_pathways: bool = True
    check_photochemical_stability: bool = True
    webhook_url: str | None = None


class MoleculeDetection(BaseModel):
    molecule: str
    log10_bayes_factor: float
    log_evidence_biotic: float    # log Z₁ (biotic model)
    log_evidence_abiotic: float   # log Z₀ (abiotic model)
    significance: DetectionSignificance
    posterior_abundance_ppm: float | None
    credible_interval_95_ppm: list[float] | None
    false_positive_probability: float
    # P1-E2: probability that this detection has an abiotic explanation (0.0–1.0)
    abiotic_pathway_prob: float
    abiotic_model_name: str       # e.g. "VULCAN-v2.1", "photolysis-CO2"
    abiotic_explanation: str | None
    photochem_consistent: bool | None
    note: str | None = None


class SpectraResultsResponse(BaseModel):
    target: str
    stellar_type: str | None
    molecules_analyzed: int
    detections: list[MoleculeDetection]
    prior_sensitivity: dict[str, dict[str, float]] | None
    methodology_note: str
    disclaimer: str = RESEARCH_DISCLAIMER


# ── Reports ────────────────────────────────────────────────────────

class GenerateReportRequest(BaseModel):
    type: str = Field(pattern="^(protein_radiation|expression|biosignature)$")
    resource_ids: list[UUID]
    format: str = Field(default="pdf", pattern="^(pdf|json)$")
    include_provenance: bool = True
