"""Physical constants, thresholds, and domain limits."""

from __future__ import annotations

# ── Protein Structure ──────────────────────────────────────────────
MAX_SEQUENCE_LENGTH = 2000  # A10G 24GB OOM above ~2000 residues (ESMFold O(L²))
MIN_SEQUENCE_LENGTH = 10
VALID_AMINO_ACIDS = set("ACDEFGHIKLMNPQRSTVWY")
VALID_AMINO_ACIDS_EXTENDED = VALID_AMINO_ACIDS | {"X", "U", "B", "Z", "O"}  # ambiguous + rare

# pLDDT interpretation thresholds (ESMFold / AlphaFold)
# Reference: Jumper 2021 Nature 596 583 (AlphaFold2) Table 1; Lin 2023 Science 379 1123 (ESMFold)
PLDDT_VERY_HIGH = 90.0   # pLDDT ≥ 90: very high confidence (Jumper 2021)
PLDDT_CONFIDENT = 70.0   # pLDDT ≥ 70: confident (Jumper 2021)
PLDDT_LOW = 50.0          # pLDDT < 50: low — likely disordered (Jumper 2021)

# ── Radiation Physics ──────────────────────────────────────────────
# Linear Energy Transfer saturation (keV/μm) — Katz track structure
LET_SATURATION_KEV_UM = 100.0  # Katz 1971 Radiat Res 47 402: track saturation >100 keV/μm

# Galactic Cosmic Ray chronic dose rate (mGy/day) — ISS shielded average
GCR_CHRONIC_DOSE_RATE = 0.5  # Cucinotta 2014 NASA/TP-2013-217375: ~0.4-0.6 mGy/day ISS average

# Relative Biological Effectiveness reference radiation (250 keV X-rays)
RBE_REFERENCE = 1.0  # ICRP Pub.60 (1990): 250 keV X-rays = RBE reference radiation

# ── Gene Expression ────────────────────────────────────────────────
DEFAULT_FDR_THRESHOLD = 0.05   # Benjamini & Hochberg 1995 J R Stat Soc B 57 289: standard FDR 5%
DEFAULT_LFC_THRESHOLD = 1.0    # log2 fold change: 2-fold minimum (Love 2014 Genome Biol 15 550)
MIN_SAMPLE_COUNT = 3  # per condition for DESeq2 (Love 2014: minimum 3 replicates per condition)
MAX_GENES_PER_QUERY = 50_000

# ── Biosignature Detection ─────────────────────────────────────────
# Jeffreys' scale for Bayes factors (log10).
# Reference: Jeffreys H. (1961) "Theory of Probability" 3rd ed., App. B;
# also Trotta R. (2008) Contemp. Phys. 49:71–104, Table 1.
BAYES_FACTOR_NONE = 0.0         # log10 K < 0: favors null
BAYES_FACTOR_WEAK = 0.5         # 0.0–0.5: weak evidence
BAYES_FACTOR_SUBSTANTIAL = 1.0  # 0.5–1.0: substantial evidence
BAYES_FACTOR_STRONG = 1.5       # 1.0–1.5: strong evidence
BAYES_FACTOR_VERY_STRONG = 2.0  # 1.5–2.0: very strong evidence
BAYES_FACTOR_DECISIVE = 2.0     # >2.0: decisive (Jeffreys "definite")

# Extraordinary claims threshold — log10(K) > 3.2.
# Derivation: Benneke & Seager (2012) ApJ 753:100, §4.2 establish that for
# JWST-class spectral retrievals, a SNR of ~20 per spectral channel yields
# a detection threshold of log10(K) ≈ 3.2, corresponding to >5σ frequentist
# significance under the Gaussian approximation. This is the "Carl Sagan
# criterion": extraordinary claims require extraordinary evidence.
# Note: the exact value is SNR- and model-dependent. For lower-resolution
# spectra (e.g., JWST NIRSpec PRISM R~100), the effective threshold may
# increase to 3.5–4.0. Adjust via DETECTION_CLAIM_THRESHOLD_HIGH_RES and
# DETECTION_CLAIM_THRESHOLD_LOW_RES if the spectral resolution is known.
DETECTION_CLAIM_THRESHOLD = 3.2           # default (R~1000, JWST NIRSpec G140M)
DETECTION_CLAIM_THRESHOLD_HIGH_RES = 3.0  # high-res (R>3000, JWST NIRSpec G395H)
DETECTION_CLAIM_THRESHOLD_LOW_RES = 3.5   # low-res (R<100, JWST NIRSpec PRISM)

# Nested sampling default live points
NESTED_SAMPLING_LIVE_POINTS = 500

# Abiotic production pathways — molecules and known non-biological sources
ABIOTIC_PATHWAYS: dict[str, list[dict[str, str]]] = {
    "CH4": [
        {"source": "Serpentinization", "condition": "Ultramafic rock + H₂O + CO₂"},
        {"source": "Fischer-Tropsch synthesis", "condition": "CO + H₂ on mineral catalysts"},
    ],
    "N2O": [
        {"source": "Lightning", "condition": "N₂ + O₂ atmosphere"},
        {"source": "Chemodenitrification", "condition": "Fe²⁺ + NO₂⁻ reactions"},
    ],
    "O3": [
        {"source": "Photolysis of CO₂", "condition": "UV irradiation of CO₂-rich atmosphere"},
    ],
    "CO2": [
        {"source": "Volcanic outgassing", "condition": "Geologically active interior"},
        {"source": "Carbonate weathering", "condition": "Silicate weathering cycle"},
    ],
    "O2": [
        {"source": "Photolysis of H₂O", "condition": "Strong UV + hydrogen escape"},
        {"source": "Photolysis of CO₂", "condition": "UV-driven CO₂ splitting"},
    ],
    "DMS": [],   # No known abiotic source — biological only on Earth
    "DMDS": [],  # No known abiotic source — biological only on Earth
}

# ── System Limits ──────────────────────────────────────────────────
MAX_BULK_SEQUENCES = 10_000
JOB_TTL_HOURS = 72
STRUCTURE_CACHE_MAX_LOCAL = 10_000  # LFU local cache entries
UPSTREAM_CIRCUIT_BREAKER_FAILURES = 5
UPSTREAM_CIRCUIT_BREAKER_TIMEOUT_S = 30.0
UPSTREAM_CIRCUIT_BREAKER_RECOVERY_S = 60.0

# ── Tenant Plan Limits ─────────────────────────────────────────────
PLAN_LIMITS: dict[str, dict[str, int]] = {
    "free": {"structures_per_month": 100, "expressions_per_month": 5, "spectra_per_month": 5},
    "pro": {"structures_per_month": 10_000, "expressions_per_month": 100, "spectra_per_month": 50},
    "enterprise": {"structures_per_month": 1_000_000, "expressions_per_month": 10_000, "spectra_per_month": 5_000},
}

# ── Disclaimer ─────────────────────────────────────────────────────
RESEARCH_DISCLAIMER = "FOR RESEARCH USE ONLY. NOT FOR CLINICAL OR DIAGNOSTIC USE."
