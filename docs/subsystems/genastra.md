# Genastra — biosignature spectroscopy, space radiation biology, and extremophile genomics

`src/aria/genastra/` is ARIA's research toolkit for the biological and astrobiological questions
that arise on long-duration missions — from ISS-class radiation modelling and spaceflight
transcriptomics to JWST-era exoplanet biosignature retrieval. The package name **GenAstra**
(Genome & Astrobiology) reflects that dual scope: it is simultaneously a proteomics / genomics
analysis service and a spectral-physics engine for target-world assessment.

It is entirely exploratory. Nothing in this package drives an actuator or sits in a safety-critical
path. It feeds scenario planning, crew-health monitoring, and the generation-ship simulation in
[`../../src/aria/simulation/`](../../src/aria/simulation/).

---

## Where it sits in the architecture

```
Cognitive engine
      │
      │ tool calls
      ▼
 ┌─────────────────────────────────────────────────────┐
 │               GenAstra FastAPI service              │
 │  POST /proteins/predict  POST /radiation/predict    │
 │  POST /spectra/analyze   POST /expression/run       │
 └───────┬──────────────────┬──────────────────────────┘
         │                  │
         ▼                  ▼
   GPU worker          Expression / Spectra
   (ESMFold v1)         workers (Redis Streams)
         │
         └──── Results → S3 → API → Cognitive engine
```

GenAstra is a **sidecar service**, not a real-time control loop.  Its outputs are advisory
(protein structural-change risk scores, biosignature detection odds, gene-expression pathway
summaries).  The cognitive engine decides what to do with them; the constitution and monitor
(see [./safety-and-monitor.md](./safety-and-monitor.md)) do not evaluate GenAstra results in
any safety gate.

The package contains **74 Python files** (72 at `maxdepth 2`, plus `radiation/training/__init__.py`
and `radiation/training/lora_finetune.py` one level deeper) totalling approximately 10,500 LOC
across eight sub-packages: `spectra`, `radiation`, `expression`, `protein`, `api`, `workers`,
`core`, and `upstream`.

Cross-links: physics constants shared with ARIA's broader physics layer live in
[./physics.md](./physics.md); simulation scenarios that consume GenAstra results
(including the generation-ship scenario) are in [./simulation.md](./simulation.md);
the digital-twin mass and power model is in [./digital-twin.md](./digital-twin.md).

---

## What's in the package

### Biosignature spectroscopy — `spectra/` (12 files)

This group handles the full pipeline from raw JWST data to a defensible detection claim.

**[`spectra/fits_reader.py`](../../src/aria/genastra/spectra/fits_reader.py)**
Reads JWST `x1d`/`x1dints`/`s2d` FITS products into wavelength–flux–uncertainty arrays.

**[`spectra/mast_client.py`](../../src/aria/genastra/spectra/mast_client.py)**
Queries the MAST archive (`astroquery.mast`) for JWST observations by target name and
downloads spectral data products. Rate-limited to 10 req/s per MAST documentation.

**[`spectra/hitran_matcher.py`](../../src/aria/genastra/spectra/hitran_matcher.py)**
Matches observed absorption features against a hardcoded `MOLECULAR_BANDS` table covering
CH₄, CO₂, O₃, N₂O, H₂O, O₂, DMS, and DMDS. Intended as a fast first-pass identification
step, not a substitute for the full Bayesian retrieval.

**[`spectra/hitran_cross_sections.py`](../../src/aria/genastra/spectra/hitran_cross_sections.py)**
Computes per-molecule absorption cross-sections (cm² per molecule) using the
HITRAN Application Programming Interface (HAPI) and locally downloaded HITRAN line data.
Four molecules currently have downloaded line data: H₂O (94,711 lines), CO₂ (127,657),
O₃ (169,155), CH₄ (221,660). Results are LRU-cached with T/P grid snapping for efficient
use inside nested-sampling loops.

**[`spectra/forward_model.py`](../../src/aria/genastra/spectra/forward_model.py)**
Physics-based transmission spectrum model: Voigt line profiles (Faddeeva function via
`scipy.special.wofz`), Rayleigh scattering (λ⁻⁴), H₂-H₂ collision-induced absorption
(Borysow 2002 parameterisation), gray cloud opacity, and a Guillot (2010) analytical
temperature-pressure profile. Delegates to petitRADTRANS for full line-by-line radiative
transfer when that optional library is installed; otherwise uses the built-in Voigt model.
Instrument LSF convolution is applied before returning spectra so that model line widths
match NIRSpec resolving powers (PRISM R~100 through G395H R~2700).

**[`spectra/bayesian.py`](../../src/aria/genastra/spectra/bayesian.py)**
The core detection engine. Runs `dynesty` nested sampling to compute the log-evidence ratio
(Bayes factor) between a model *with* a molecule and a baseline model *without* it. The
detection threshold is log₁₀(K) > 3.2, calibrated against the Benneke & Seager (2012)
"Carl Sagan criterion" for JWST-class spectral retrievals. Three prior types are available
(`empirical`, `uninformative`, `pessimistic`) and the module enforces prior sensitivity
analysis — all three Bayes factors are reported. A `run_joint_retrieval` function fits
multiple molecules simultaneously in a single nested-sampling run, correctly handling
spectral degeneracies (e.g. CH₄/H₂O overlap near 3.3 μm). Mutual information between the
spectrum and each molecular abundance is reported in bits as an independent informativeness
check. The `dynesty` package is a hard dependency; the BIC fallback is labelled unreliable.

**[`spectra/false_positive.py`](../../src/aria/genastra/spectra/false_positive.py)**
Wraps a `BayesianResult` with abiotic pathway and photochemical stability checks to
produce a final `DetectionAssessment` with confidence levels: `no_detection`, `tentative`,
`robust`, `extraordinary`. A `SUBSTANTIAL`-or-higher detection without a completed
photochemical stability check is automatically downgraded to `tentative`.

**[`spectra/atmospheric.py`](../../src/aria/genastra/spectra/atmospheric.py)**
Checks whether a detected molecule has known abiotic production pathways
(serpentinization → CH₄, lightning → N₂O, UV photolysis → O₂/O₃) and estimates
photodissociation lifetimes by stellar spectral type, drawing on Rugheimer et al. (2015)
and Segura et al. (2005) photochemistry models.

**[`spectra/thermodynamics.py`](../../src/aria/genastra/spectra/thermodynamics.py)**
Computes the Gibbs free energy of atmospheric disequilibrium ΔG = G_actual − G_equilibrium,
following Krissansen-Totton, Bergsman & Catling (2016). Chemical potentials from NIST-JANAF
(Chase 1998) cover 14 species. Equilibrium composition is found via SLSQP minimisation with
elemental-conservation constraints. Reference values: Earth ≈ −2326 J/mol, Mars ≈ −4 J/mol,
Venus ≈ −0.2 J/mol. Both `EARTH_ATMOSPHERE` and `MARS_ATMOSPHERE` reference dictionaries
are included for validation, sourced from Mahaffy et al. (2013 MSL SAM) and NOAA GML 2024.

**[`spectra/stellar_contamination.py`](../../src/aria/genastra/spectra/stellar_contamination.py)**
Corrects transmission spectra for the transit light source effect (TLSE): unocculted stellar
spots and faculae produce a wavelength-dependent contamination factor C(λ) that inflates or
suppresses apparent absorption depths. Applies the Rackham et al. (2018) blackbody
approximation. Pre-tabulated spot/faculae parameters by stellar spectral type (F–M),
with M-dwarf subtype scaling.

**[`spectra/stellar_uv.py`](../../src/aria/genastra/spectra/stellar_uv.py)**
UV environment profiles for F, G, K, M spectral types, including quiescent UV flux relative
to solar, flare frequency, and habitable zone boundaries from Kopparapu et al. (2013).

---

### Radiation biology — `radiation/` (9 files + `training/` sub-package)

The radiation group models how ionising radiation damages proteins aboard spacecraft.
The scope is *protein-level* biology, not whole-body cancer risk or shielding design
(those are in [`./physics.md`](./physics.md)).

**[`radiation/environment.py`](../../src/aria/genastra/radiation/environment.py)**
Validates and constructs `RadiationEnvironment` objects. Four ready-made reference
environments are provided: `iss_6_month()` (90 mGy, Cucinotta 2014), `mars_transit()`
(160 mGy, Zeitlin 2013 MSL/RAD), `spe_event()` (2000 mGy, Aug 1972 SPE), and
`lunar_surface_1_year()` (~380 mGy ESTIMATE, LRO/CRaTER). LET is enforced as a required
parameter for HZE ions; without it the model refuses to proceed.

**[`radiation/let_model.py`](../../src/aria/genastra/radiation/let_model.py)**
Linear Energy Transfer tables and interpolation for protons, helium, carbon, and iron ions
at multiple energies (sourced from ICRP 103 and NASA-STD-3001 Vol 1). Provides
`estimate_let()` and `classify_damage_type()` (isolated / mixed / clustered).

**[`radiation/dose_response.py`](../../src/aria/genastra/radiation/dose_response.py)**
Two dose-response models for protein-level damage:
- Linear No-Threshold: P(damage) = 1 − exp(−α × D × RBE(L))
- Threshold: identical form but zeroed below a repair threshold (~50 mGy ESTIMATE)

The radiosensitivity coefficient α = 5×10⁻⁵ per mGy is the *protein sidechain oxidation*
rate (Stadtman & Levine 2003), not the ICRP cancer risk coefficient. RBE is computed via
a Katz-style saturation model (Katz 1971). NASA OCHMO career limits (NSCR-2019) and ICRP
103 tissue weighting factors are embedded for career-limit fraction reporting.

**[`radiation/damage_predictor.py`](../../src/aria/genastra/radiation/damage_predictor.py)**
Structure-aware heuristic vulnerability scorer. Per-residue base sensitivity from Stadtman
& Levine (2003) and Davies (2016) is weighted by solvent-accessible surface area (SASA,
Shrake-Rupley via BioPython) so that buried cysteines are protected and surface-exposed
ones are amplified. Domain boundaries are detected from the PAE matrix and receive a
vulnerability boost. Cysteine clusters (potential disulfide bonds, zinc fingers) get an
additional empirical boost. Predictions from low-confidence structures (pLDDT < 50) refuse
SASA weighting. The module notes that a LoRA fine-tune of ESM-2 is the intended upgrade
path; the current heuristic is the working implementation.

**[`radiation/ros_diffusion.py`](../../src/aria/genastra/radiation/ros_diffusion.py)**
Indirect damage model: ionising radiation radiolysis of water produces •OH, O₂•⁻, H₂O₂,
and ¹O₂ radicals that diffuse and attack proteins over nanometre distances. G-values from
ICRU Report 31 (1979), diffusion coefficients from Spinks & Woods (1990), and second-order
reaction rate constants from Buxton (1988). The module quantifies the indirect/direct ratio
and identifies the dominant ROS species, which for most space environments is •OH.

**[`radiation/fractionation.py`](../../src/aria/genastra/radiation/fractionation.py)**
Lea-Catcheside dose-rate effectiveness factor G, which accounts for biological repair
between radiation events during chronic chronic space radiation. For ISS-class protein
oxidation repair (λ = 2/hr), a 90 mGy 6-month dose has G ≈ 0.00046, reducing the
effective dose to ~1.9 mGy — a 47× difference from the acute equivalent. Repair endpoints
cover DNA DSB (Cucinotta 2006), protein sidechain oxidation (Davies 2016 ESTIMATE),
protein refolding (Tyedmers 2010 ESTIMATE), and protein replacement via proteasome
(Schwanhäusser 2011 ESTIMATE).

**[`radiation/cooperativity.py`](../../src/aria/genastra/radiation/cooperativity.py)**
Contact-map cooperativity model based on Onuchic & Wolynes (2004): damage at a densely
connected folding nucleus is disproportionately catastrophic. Computes Cα-Cα contact maps
from PDB coordinates (8 Å cutoff, Vendruscolo 2002) and amplifies vulnerability scores
at residues with many damaged structural neighbours. Also identifies putative folding nuclei
(Shakhnovich 1994) as especially high-risk sites.

**[`radiation/training/lora_finetune.py`](../../src/aria/genastra/radiation/training/lora_finetune.py)**
Training script for a planned LoRA fine-tune of ESM-2 on radiation-damage experimental
data. Not used at inference time; it is a research artefact kept under `training/` to
indicate the intended upgrade path from the current heuristic to a learned model.

---

### Spaceflight gene expression — `expression/` (7 files)

**[`expression/genelab_client.py`](../../src/aria/genastra/expression/genelab_client.py)**
Async client for the NASA Open Science Data Repository (OSDR) Biological Data API
(`visualization.osdr.nasa.gov/biodata/api/`). Searches and fetches RNA-seq / microarray
datasets from ISS and shuttle experiments (OSD-* / GLDS-* accessions).

**[`expression/etl.py`](../../src/aria/genastra/expression/etl.py)**
Parses OSDR response payloads into (genes × samples) count matrices, validates that counts
are raw non-negative integers (not FPKM/TPM), and constructs sample metadata.

**[`expression/batch_effects.py`](../../src/aria/genastra/expression/batch_effects.py)**
PCA-based batch effect detection and ComBat-seq correction (Zhang et al. 2020). Spaceflight
experiments confound launch stress, elevated CO₂, temperature variation, and vibration.
Batch is detected when batch labels explain more PC1 variance than condition labels; the
threshold is 30 %. Falls back to median-centering if `pycombat` is absent.

**[`expression/deseq2.py`](../../src/aria/genastra/expression/deseq2.py)**
PyDESeq2 wrapper with experimental-design validation, pseudoreplication detection, LFC
shrinkage for small experiments (n = 3–6 per condition, common in GeneLab), and Storey's
π₀ estimation via a smoothing spline (Storey & Tibshirani 2003). Raw integer counts are
validated before analysis; FPKM/TPM data raises an explicit error. Default FDR 5 %,
log₂ fold-change threshold 1.0.

**[`expression/normalization.py`](../../src/aria/genastra/expression/normalization.py)**
Library-size normalisation, variance-stabilising transformation, and quality-control metrics
(detected genes, inter-sample correlation) for exploratory visualisation prior to DESeq2.

**[`expression/enrichment.py`](../../src/aria/genastra/expression/enrichment.py)**
Over-representation analysis via `gseapy` against KEGG 2021, GO Biological Process 2023,
GO Molecular Function 2023, and Reactome 2022. Supports human, mouse, rat, Arabidopsis,
fly, worm, zebrafish, and yeast. Returns enrichment results sorted by adjusted p-value.

---

### Protein structure — `protein/` (7 files)

**[`protein/fasta_parser.py`](../../src/aria/genastra/protein/fasta_parser.py)**
Parses single and multi-sequence FASTA input with character validation (standard 20 +
ambiguous residues B, Z, X, O, U).

**[`protein/uniprot_client.py`](../../src/aria/genastra/protein/uniprot_client.py)**
Looks up pre-computed structures via AlphaFold EBI (200 M+ models), then falls back to
RCSB PDB experimental structures. The ESM Metagenomic Atlas client is present but marked
as decommissioned (API returns 403 as of 2026-03).

**[`protein/esmfold.py`](../../src/aria/genastra/protein/esmfold.py)**
ESMFold v1 inference wrapper (Meta, MIT licence). Runs in the isolated GPU worker process
only; the A10G (24 GB) handles sequences up to ~2000 residues (O(L²) memory). Returns PDB
string, per-residue pLDDT, pTM score, and PAE matrix in a single `infer()` call.

**[`protein/confidence.py`](../../src/aria/genastra/protein/confidence.py)**
Interprets pLDDT scores using the AlphaFold2 / ESMFold thresholds from Jumper et al.
(2021) and Lin et al. (2023): ≥90 very high confidence, ≥70 confident, <50 likely
disordered.

**[`protein/pdb_parser.py`](../../src/aria/genastra/protein/pdb_parser.py)**
Lightweight PDB ATOM record parser (no BioPython dependency) for sequence extraction
and basic geometry.

**[`protein/structure_cache.py`](../../src/aria/genastra/protein/structure_cache.py)**
Two-tier cache: S3 for persistence, LFU in-process cache (up to 10,000 entries). Avoids
redundant ESMFold GPU inference for repeated sequences.

---

### Service infrastructure — `api/`, `workers/`, `core/`, `upstream/`

**`api/`** (15 files) — FastAPI application with routes for protein structure prediction
(`/proteins/`), radiation damage (`/radiation/`), gene expression (`/expression/`),
spectral analysis (`/spectra/`), async jobs (`/jobs/`), and report generation (`/reports/`).
Multi-tenant with per-tenant plan limits (free / pro / enterprise). Jobs are enqueued via
Redis Streams and picked up by the appropriate background worker.

**`workers/`** (5 files) — `base.py` implements a Redis Streams consumer with graceful
shutdown and health endpoints. `gpu_worker.py` runs ESMFold in an isolated subprocess.
`expression_worker.py` and `spectra_worker.py` handle their respective analysis pipelines.

**`core/`** (8 files) — frozen domain dataclasses (`models.py`), physical constants with
full citation metadata (`constants.py`), domain exceptions, multi-tenant security
(`security.py`, `tenant.py`), and a compatibility shim for Python 3.10 `StrEnum`.

**`upstream/`** (4 files) — circuit breaker (`UPSTREAM_CIRCUIT_BREAKER_FAILURES = 5`),
exponential-backoff retry, and token-bucket rate limiter for outbound calls to AlphaFold
EBI, RCSB PDB, MAST, and NASA OSDR.

---

## Data and citations

All data consumed by this package is public-source:

| Dataset | Location | Reference |
|---------|----------|-----------|
| NASA Exoplanet Archive confirmed planets | `data/raw/exoplanets/` (repo root) | NASA Exoplanet Archive (Akeson et al. 2013 PASP 125:989) |
| NASA ACE/CRIS Galactic Cosmic Ray spectra | `data/raw/gcr/` (repo root) | ACE/CRIS instrument team; Stone et al. 1998 Space Sci Rev 86:357 |
| HITRAN line data (H₂O, CO₂, O₃, CH₄) | `data/spectra/hitran_data/` | Gordon et al. 2022 JQSRT 277:107949 (HITRAN2020) |

Key external references embedded as constants or docstrings in source code:

- **Cucinotta & Durante (2006)** Lancet Oncol 7:431 — GCR dose rates, HZE RBE, career risk
- **Zeitlin et al. (2013)** Science 340:1080 — MSL/RAD Mars transit dose
- **Stadtman & Levine (2003)** Protein Sci 12:2005 — amino acid ROS reactivity ranking
- **Jumper et al. (2021)** Nature 596:583 (AlphaFold2) — pLDDT thresholds
- **Krissansen-Totton, Bergsman & Catling (2016)** ApJ 817:31 — disequilibrium metric
- **Rackham et al. (2018)** ApJ 853:122 — stellar contamination / TLSE
- **Kopparapu et al. (2013)** ApJ 765:131 — habitable zone boundaries
- **Benneke & Seager (2012)** ApJ 753:100 — JWST detection threshold log₁₀(K) > 3.2
- **Jeffreys (1961)** "Theory of Probability" 3rd ed.; Trotta (2008) Contemp Phys 49:71 — Bayes factor scale
- **Love et al. (2014)** Genome Biol 15:550 (DESeq2); Storey & Tibshirani (2003) PNAS 100:9440 — expression stats
- **ICRP Publication 103 (2007)** — RBE reference radiation, tissue weights
- **ICRU Report 31 (1979)** — water radiolysis G-values

---

## Current limitations

This package is research-grade (TRL 3–5). Specific caveats:

**Radiation models**

- The protein damage predictor is a heuristic, not a trained model. The intended ESM-2
  LoRA fine-tune (`radiation/training/lora_finetune.py`) has not been trained against
  experimental irradiation data; no such training set is included.
- RBE values for HZE ions (e.g. Fe-56 at ~150–200 keV/μm, RBE ~25–40) are highly endpoint-
  and energy-dependent. The Katz-model parameterisation used here is a simplification.
  Cucinotta & Durante (2006) and ICRP 103 should be consulted for any mission-planning use.
- Most dose-rate and shielding constants carry `# ESTIMATE` tags; they are derived from
  published mean values rather than vehicle-specific Monte Carlo transport calculations.
  The `mars_transit()` environment is sourced from MSL/RAD, which used a particular hull
  geometry. A different vehicle will have a different dose rate.
- Protein repair rate constants (λ for proteasomal clearance, chaperone refolding, protein
  turnover) are all estimates from in-vitro mammalian cell studies, not from spaceflight
  conditions or extremophile organisms.

**Biosignature spectroscopy**

- HITRAN line data is downloaded locally for four molecules only (H₂O, CO₂, O₃, CH₄).
  DMS and DMDS use parametric Gaussian band models because they are not in standard HITRAN.
- The forward model's T-P profile (Guillot 2010) is calibrated for hot-Jupiter atmospheres.
  Application to terrestrial-planet atmospheres with surface pressures far from 1 bar
  (Venus at 92 bar, Mars at 0.006 bar) gives qualitative results only.
- Nested-sampling convergence depends on `n_live` (default 500). Low-SNR spectra or wide
  parameter ranges may require more live points to produce reliable log-evidence values.
- The K2-18b DMS controversy (Madhusudhan et al. 2023 vs. subsequent re-analyses) is
  a case study in why every prior sensitivity, abiotic pathway check, and stellar
  contamination correction must be reported alongside any Bayes factor. This pipeline
  implements all three checks but they are only as good as the input data quality.

**Gene expression**

- DESeq2 assumes independent biological replicates. Spaceflight experiments frequently have
  small sample sizes (n = 3–6 per condition) and batch effects from different launches.
  Results should be treated as exploratory signals rather than definitive findings.
- `enrichment.py` uses over-representation analysis, not ranked GSEA. This is appropriate
  for the small gene sets typical in spaceflight data but is less sensitive than full GSEA.

**Protein structure**

- ESMFold sequence length limit is ~2000 residues (A10G 24 GB memory limit). Large
  multi-domain complexes common in extremophile proteomes require splitting.
- pLDDT alone is insufficient for quality assessment of multi-domain proteins.
  PAE (Predicted Aligned Error) is required for domain-interface reliability; `pae_matrix`
  is extracted from ESMFold output and propagated through the damage predictor.
- The ESM Metagenomic Atlas API (600 M metagenomic structure models) is currently returning
  403 Forbidden; only AlphaFold EBI and RCSB PDB are reachable.

---

## Where to start reading

**Entry points**

| Start here | What it demonstrates |
|---|---|
| [`radiation/environment.py`](../../src/aria/genastra/radiation/environment.py) | Build and validate a `RadiationEnvironment`; use `iss_6_month()` or `mars_transit()` as reference objects |
| [`radiation/damage_predictor.py`](../../src/aria/genastra/radiation/damage_predictor.py) | Call `predict_heuristic(sequence, env, pdb_string)` to get per-residue vulnerability scores |
| [`spectra/bayesian.py`](../../src/aria/genastra/spectra/bayesian.py) | Call `run_nested_sampling(wavelengths, flux, flux_err, molecule)` for a single-molecule Bayes factor; `run_joint_retrieval()` for multi-molecule joint retrieval |
| [`spectra/thermodynamics.py`](../../src/aria/genastra/spectra/thermodynamics.py) | Call `compute_disequilibrium(mixing_ratios, temperature_k)` and compare to `EARTH_ATMOSPHERE` / `MARS_ATMOSPHERE` reference dictionaries |
| [`expression/deseq2.py`](../../src/aria/genastra/expression/deseq2.py) | Call `run_deseq2(count_matrix, gene_symbols, sample_ids, conditions)` for spaceflight differential expression |
| [`api/app.py`](../../src/aria/genastra/api/app.py) | FastAPI application factory; start with `genastra serve` |
| [`cli.py`](../../src/aria/genastra/cli.py) | Typer CLI: `genastra serve`, `genastra worker gpu`, `genastra migrate` |

**Tests**

```
tests/unit/test_genastra/
├── test_radiation.py       dose-response, LET, environment validation, damage heuristic
├── test_bayesian.py        nested-sampling biosignature detection
├── test_models.py          frozen domain dataclasses and RadiationEnvironment
├── test_p0_fixes.py        regression tests for physics-correctness bug fixes
├── test_p0v2_fixes.py      second-round physics fixes (joint retrieval, fractionation)
├── test_v3_math_physics.py thermodynamics, ROS diffusion, cooperativity
├── test_normalization.py   expression normalisation and QC
├── test_confidence.py      pLDDT interpretation thresholds
├── test_security.py        API authentication and scope enforcement
└── test_circuit_breaker.py upstream resilience layer
```

The test suite uses no real network calls; external APIs (AlphaFold EBI, MAST, NASA OSDR)
are mocked. Tests that require GPU hardware are skipped automatically when `torch.cuda` is
unavailable.

**Optional heavy dependencies**

- `dynesty` — required for biosignature nested sampling (hard requirement; BIC fallback is
  labelled unreliable and will not be used silently)
- `petitRADTRANS` — full line-by-line radiative transfer (optional; built-in Voigt model
  is used when absent)
- `hitran-api` (hapi) — HITRAN cross-sections (optional; falls back to parametric bands)
- `biopython` — SASA computation for structure-aware damage prediction (optional; heuristic
  degrades gracefully to sequence-only mode with wider confidence intervals)
- `torch` — ESMFold inference (GPU worker only)
- `pydeseq2`, `gseapy` — gene expression analysis
- `dynesty`, `scipy` — spectral retrieval and statistical testing
