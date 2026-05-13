"""Frozen domain dataclasses — immutable value objects for the GenAstra domain."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from aria.genastra.core._compat import StrEnum

if TYPE_CHECKING:
    from datetime import datetime

# ── Enums ──────────────────────────────────────────────────────────

class JobStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(StrEnum):
    STRUCTURE_PREDICTION = "structure_prediction"
    RADIATION_DAMAGE = "radiation_damage"
    GENE_EXPRESSION = "gene_expression"
    SPECTRAL_ANALYSIS = "spectral_analysis"
    BULK_STRUCTURE = "bulk_structure"
    REPORT_GENERATION = "report_generation"


class RadiationType(StrEnum):
    GCR = "gcr"
    SPE = "spe"
    TRAPPED_BELT = "trapped_belt"
    MIXED = "mixed"


class ParticleType(StrEnum):
    PROTON = "proton"
    HZE_ION = "hze_ion"
    NEUTRON = "neutron"
    MIXED = "mixed"


class DoseResponseModel(StrEnum):
    LNT = "lnt"  # Linear No-Threshold
    THRESHOLD = "threshold"
    BOTH = "both"


class DetectionSignificance(StrEnum):
    NONE = "none"
    WEAK = "weak"
    SUBSTANTIAL = "substantial"
    STRONG = "strong"
    VERY_STRONG = "very_strong"
    DECISIVE = "decisive"


class TenantPlan(StrEnum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# ── Domain Objects (frozen) ────────────────────────────────────────

@dataclass(frozen=True)
class Tenant:
    id: UUID
    name: str
    slug: str
    plan: TenantPlan
    monthly_structure_limit: int
    monthly_expression_limit: int
    created_at: datetime


@dataclass(frozen=True)
class ApiKey:
    id: UUID
    tenant_id: UUID
    key_hash: bytes
    prefix: str
    label: str
    scopes: tuple[str, ...]
    is_active: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class Job:
    id: UUID
    tenant_id: UUID
    job_type: JobType
    status: JobStatus
    priority: int
    input_params: dict[str, Any]
    result_summary: dict[str, Any] | None
    result_s3_key: str | None
    error_message: str | None
    worker_id: str | None
    webhook_url: str | None
    provenance: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True)
class ProteinSequence:
    """Validated protein sequence with precomputed hash."""

    sequence: str
    sequence_hash: str = field(init=False)
    length: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence_hash", hashlib.sha256(self.sequence.encode()).hexdigest())
        object.__setattr__(self, "length", len(self.sequence))


@dataclass(frozen=True)
class StructurePrediction:
    id: UUID
    protein_id: UUID
    job_id: UUID | None
    model_name: str
    model_version: str
    pdb_s3_key: str
    mean_plddt: float
    per_residue_plddt: tuple[float, ...]
    ptm_score: float | None
    inference_time_ms: int | None
    created_at: datetime
    # P0-E8 (Shenkar): pLDDT alone is insufficient for quality assessment.
    # PAE (Predicted Aligned Error) is required to assess domain-domain
    # interfaces and multi-chain assemblies. High-pLDDT regions can still be
    # functionally wrong for low-homology sequences (common in extremophile
    # proteomes). Reference: Jumper et al. (2021) Nature 596:583–589.
    pae_matrix_s3_key: str | None = None  # NxN matrix stored as .npy in S3
    template_coverage: float | None = None  # 0.0–1.0: fraction covered by homologs


@dataclass(frozen=True)
class RadiationEnvironment:
    """Structured radiation exposure model — NOT binary.

    Encodes particle type, dose, dose rate, LET, shielding, RBE, and exposure pattern.
    Required by SpaceX Starshield panel critique: radiation damage is
    a function of all these parameters, not just on/off.
    """

    radiation_type: RadiationType
    dose_mgy: float  # total dose in milliGray (physical dose)
    dose_rate_mgy_per_day: float  # chronic vs acute
    particle_type: ParticleType
    shielding_g_per_cm2: float = 20.0  # aluminum-equivalent
    let_kev_per_um: float | None = None  # Linear Energy Transfer (REQUIRED for HZE_ION)
    duration_days: float | None = None
    # P1-E3 (Limoli): biological dose = physical_dose × RBE. Mixing particle
    # types without RBE weighting produces physically invalid comparisons.
    # Reference: ICRP Publication 103 (2007); Cucinotta & Durante (2006).
    # For protons: RBE ≈ 1.1; for HZE Fe-56: RBE ≈ 25–40 depending on endpoint.
    rbe: float | None = None  # Relative Biological Effectiveness (dimensionless)
    # P2-E4 (Limoli): acute vs fractionated exposure affects DNA repair kinetics.
    # 1 Gy acute ≠ 1 Gy over 30 days for DSB repair half-time.
    # Reference: Lea-Catcheside factor; Thames & Hendry (1987).
    exposure_pattern: str = "chronic"  # "acute" | "fractionated" | "chronic"

    @property
    def dose_msv(self) -> float | None:
        """Biological equivalent dose in milliSievert (mGy × RBE).

        Returns None if RBE is not set — do not use physical dose as biological dose proxy.
        """
        if self.rbe is None:
            return None
        return self.dose_mgy * self.rbe


@dataclass(frozen=True)
class RadiationAnalysis:
    id: UUID
    protein_id: UUID
    job_id: UUID | None
    radiation_env: RadiationEnvironment
    model_name: str
    model_version: str
    vulnerable_residues: tuple[int, ...]
    vulnerability_scores: tuple[float, ...]
    predicted_structural_impact: float  # 0.0–1.0 probability of structural disruption
    confidence_interval_95: tuple[float, float]
    dose_response_model: DoseResponseModel
    created_at: datetime
    # P1-E3: calibration metadata — raw model scores must be calibrated against
    # experimental measurements before being treated as probabilities.
    calibration_method: str | None = None   # e.g. "platt_scaling", "isotonic_regression"
    calibration_dataset: str | None = None  # e.g. "NASA_NSRL_2023_Fe56"


@dataclass(frozen=True)
class DifferentialExpressionResult:
    gene_symbol: str
    ensembl_id: str | None
    base_mean: float
    log2_fold_change: float
    lfc_se: float
    stat: float
    pvalue: float
    padj: float


@dataclass(frozen=True)
class PathwayEnrichment:
    database: str
    pathway_id: str
    pathway_name: str
    gene_count: int
    enrichment_score: float
    nes: float | None
    pvalue: float
    padj: float
    leading_edge_genes: tuple[str, ...]


@dataclass(frozen=True)
class BiosignatureDetection:
    """Single molecule biosignature detection result."""

    molecule: str
    log10_bayes_factor: float
    log_evidence_biotic: float    # log Z₁ (model WITH molecule) — from dynesty
    log_evidence_abiotic: float   # log Z₀ (model WITHOUT molecule) — from dynesty
    detection_significance: DetectionSignificance
    posterior_abundance: float | None
    abundance_ci_lower: float | None
    abundance_ci_upper: float | None
    false_positive_prob: float
    # P1-E2 (Harrison): abiotic_pathway_flag was binary (bool). Photochemistry
    # models (VULCAN, ATMO) give probability ranges — e.g. O2 from CO2 photolysis
    # on M-dwarfs can produce abundances indistinguishable from biotic O2.
    # Reference: Schwieterman et al. (2018) Astrobiology 18:663–708.
    abiotic_pathway_prob: float       # 0.0–1.0: probability this detection has an abiotic explanation
    abiotic_model_name: str           # e.g. "VULCAN-v2.1", "photolysis-CO2", "serpentinization"
    abiotic_explanation: str | None
    photochem_consistent: bool | None
    nested_sampling_log_evidence: float | None
    prior_sensitivity: dict[str, float] | None


@dataclass(frozen=True)
class SpectralObservation:
    id: UUID
    tenant_id: UUID
    target_name: str
    mast_obs_id: str | None
    instrument: str
    wavelength_min_um: float
    wavelength_max_um: float
    spectral_resolution: float | None
    stellar_type: str | None
    stellar_teff_k: float | None
    planet_teq_k: float | None
    spectrum_s3_key: str
    created_at: datetime
    # P2-E3 (Harrison): HITRAN line matching without pressure broadening produces
    # incorrect line widths. Venus (90 bar) vs Mars (0.006 bar) vs Earth (1 bar)
    # require different Voigt profile Lorentzian widths for the same molecule.
    # Reference: Gordon et al. (2022) JQSRT 277:107949 (HITRAN2020).
    atmosphere_pressure_bar: float | None = None  # None = unknown / not retrieved
    # P1-E7 extension: stellar contamination parameters for JWST M-dwarf targets
    stellar_spot_fraction: float | None = None   # unocculted starspot covering fraction
    flare_contamination_flag: bool = False        # whether active flare emission was detected


def new_id() -> UUID:
    """Generate a new UUID4."""
    return uuid4()
