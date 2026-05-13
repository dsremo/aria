"""Bayesian biosignature detection via nested sampling.

Panel 3 (NASA JPL Astrobiology) critique:
"The K2-18b DMS controversy is the perfect cautionary tale. Must implement
proper Bayesian model comparison: compute Bayes factor K = P(D|M1)/P(D|M0),
and require log10(K) > 3.2 for any detection claim."

Panel 5 (Mathematician) critique:
"Priors matter enormously. Must use empirically calibrated priors, not
flat/uninformative priors (which bias toward detection)."

Uses dynesty (MIT license) for nested sampling — the evidence integral Z
is the primary quantity of interest, not posterior samples.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import structlog

from aria.genastra.core.constants import (
    BAYES_FACTOR_NONE,
    BAYES_FACTOR_STRONG,
    BAYES_FACTOR_SUBSTANTIAL,
    BAYES_FACTOR_VERY_STRONG,
    BAYES_FACTOR_WEAK,
    DETECTION_CLAIM_THRESHOLD,
    NESTED_SAMPLING_LIVE_POINTS,
)
from aria.genastra.core.models import DetectionSignificance

logger = structlog.get_logger()


@dataclass(frozen=True)
class BayesianResult:
    """Result of Bayesian biosignature detection for a single molecule."""

    molecule: str
    log10_bayes_factor: float
    log10_bayes_factor_err: float  # BUILD-F1 (Tao): uncertainty on BF from dynesty logzerr
    significance: DetectionSignificance
    significance_reliable: bool  # False if δ(log₁₀K) > 0.5 (classification unreliable)
    log_evidence_with: float  # log Z₁ (model with molecule)
    log_evidence_without: float  # log Z₀ (model without molecule)
    posterior_abundance: float | None  # median mixing ratio
    abundance_ci_lower: float | None  # 95% CI lower
    abundance_ci_upper: float | None  # 95% CI upper
    false_positive_prob: float
    prior_type: str
    mutual_information_bits: float | None  # BUILD-F21 (Bialek): bits of info about abundance


def classify_bayes_factor(log10_k: float) -> DetectionSignificance:
    """Classify a Bayes factor on the Jeffreys' scale.

    | log10(K) | Interpretation |
    |----------|----------------|
    | < 0      | Favors null    |
    | 0-0.5    | Weak           |
    | 0.5-1.0  | Substantial    |
    | 1.0-1.5  | Strong         |
    | 1.5-2.0  | Very Strong    |
    | > 2.0    | Decisive       |
    """
    if log10_k < BAYES_FACTOR_NONE:
        return DetectionSignificance.NONE
    if log10_k < BAYES_FACTOR_WEAK:
        return DetectionSignificance.WEAK
    if log10_k < BAYES_FACTOR_SUBSTANTIAL:
        return DetectionSignificance.SUBSTANTIAL
    if log10_k < BAYES_FACTOR_STRONG:
        return DetectionSignificance.STRONG
    if log10_k < BAYES_FACTOR_VERY_STRONG:
        return DetectionSignificance.VERY_STRONG
    return DetectionSignificance.DECISIVE


def compute_false_positive_prob(log10_bayes_factor: float) -> float:
    """Compute false positive probability from Bayes factor.

    P(FP | D) = P(M₀ | D) = 1 / (1 + K × P(M₁)/P(M₀))

    With equal prior model probabilities: P(FP) = 1 / (1 + K)
    """
    k = 10.0 ** log10_bayes_factor
    return 1.0 / (1.0 + k)


def get_prior(
    prior_type: str,
    molecule: str,
) -> tuple[float, float]:
    """Get prior parameters for molecular mixing ratio.

    Returns (mu, sigma) for log10(mixing_ratio) ~ N(mu, sigma).

    Panel 5 (Mathematician): "Must use empirically calibrated priors."

    Three prior types:
    - empirical: calibrated from Solar System atmospheres
    - uninformative: log10(f) ~ U(-12, -1)
    - pessimistic: strongly disfavors high abundance
    """
    # P0-7 FIX: Empirical priors from ACTUAL Solar System measurements.
    # The old priors were fabricated (e.g., Mars CH₄ listed as "~10 ppb"
    # when actual measurement is 0.41 ppb). These are corrected values.
    #
    # Sources:
    #   CH₄: Mars=0.41 ppb (Curiosity TLS, Webster+2015), Titan=5.65% (Huygens GCMS)
    #   CO₂: Venus=96.5%, Mars=95.3%, Earth=420 ppm (2024)
    #   O₃:  Earth stratosphere peak ~10 ppm (NOAA)
    #   N₂O: Earth=336 ppb (2024 NOAA)
    #   H₂O: Earth ~0.4% surface avg, Mars ~200 ppm
    #   DMS: Earth ~0.1 ppb (marine avg, Kettle+1999)
    #   O₂:  Earth=20.95%
    #
    # mu = log10(geometric mean across known atmospheres where detected)
    # sigma = covers range from lowest to highest known detection
    empirical_priors: dict[str, tuple[float, float]] = {
        "CH4": (-5.0, 3.0),    # Mars: 4.1e-10, Titan: 5.65e-2 → geometric mean ~10⁻⁵
        "CO2": (-0.5, 1.5),    # Venus/Mars: ~0.95, Earth: 4.2e-4
        "O3": (-5.0, 1.5),     # Earth peak: ~1e-5 (10 ppm)
        "N2O": (-6.5, 1.0),    # Earth: 3.36e-7 (336 ppb)
        "H2O": (-3.5, 2.5),    # Earth: ~4e-3 (0.4%), Mars: ~2e-4
        "DMS": (-10.0, 1.0),   # Earth: ~1e-10 (0.1 ppb), narrow prior — rare molecule
        "DMDS": (-10.5, 1.0),  # Earth: ~1e-11 (~0.01 ppb), very narrow
        "O2": (-0.7, 1.5),     # Earth: 0.2095, Mars: ~0.13%
    }

    if prior_type == "empirical":
        return empirical_priors.get(molecule, (-6.0, 3.0))
    if prior_type == "uninformative":
        # Uniform in log space → wide Gaussian approximation
        return (-6.5, 3.2)  # covers -12 to -1
    if prior_type == "pessimistic":
        mu, sigma = empirical_priors.get(molecule, (-6.0, 3.0))
        return (mu - 3.0, sigma * 0.5)  # shift 3 orders of magnitude lower, tighten
    raise ValueError(f"Unknown prior type: {prior_type}")


def run_nested_sampling(
    wavelengths_um: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray,
    molecule: str,
    prior_type: str = "empirical",
    n_live: int = NESTED_SAMPLING_LIVE_POINTS,
) -> BayesianResult:
    """Run nested sampling for biosignature detection.

    Compares two models:
    M₀: Atmosphere WITHOUT molecule X (baseline continuum + known absorbers)
    M₁: Atmosphere WITH molecule X at mixing ratio f_X

    Uses dynesty for nested sampling. The evidence integral Z is computed
    directly — this is the primary advantage of nested sampling over MCMC.

    Z = ∫ P(D|θ,M) × π(θ|M) dθ
    """
    # P0-2 FIX: dynesty is REQUIRED, not optional.
    # The BIC approximation is unreliable by 10-100x for spectral data
    # (violates flat-prior and Gaussian-posterior assumptions).
    # Returning wrong Bayes factors is worse than returning nothing.
    try:
        import dynesty
    except ImportError as err:
        raise ImportError(
            "dynesty is required for biosignature detection. "
            "The BIC approximation is unreliable by 10-100x for spectral data "
            "(violates flat-prior and Gaussian-posterior assumptions). "
            "Install with: pip install dynesty"
        ) from err

    prior_mu, prior_sigma = get_prior(prior_type, molecule)

    # --- Pre-compute Rayleigh + H₂-H₂ CIA background (P0-v2-4 FIX) ─────────
    # These are present in EVERY H₂-rich atmosphere unconditionally.
    # The null model M₀ must include them; omitting them makes spurious detections
    # more likely by attributing physical background opacity to the test molecule.
    try:
        from aria.genastra.spectra.forward_model import (
            h2h2_cia_cross_section,
            rayleigh_scattering_cross_section,
        )
        _sigma_ray = rayleigh_scattering_cross_section(wavelengths_um)
        _sigma_ray_norm = _sigma_ray / (_sigma_ray.max() + 1e-40)
        # CIA at fiducial temperature 300K — varies slowly; OK as fixed background
        _sigma_cia = h2h2_cia_cross_section(wavelengths_um, temperature=300.0)
        _sigma_cia_norm = _sigma_cia / (_sigma_cia.max() + 1e-40)
        _has_physics_bg = True
    except ImportError:
        _has_physics_bg = False
        _sigma_ray_norm = np.zeros_like(wavelengths_um)
        _sigma_cia_norm = np.zeros_like(wavelengths_um)

    # --- Model M₀: continuum + physical background (Rayleigh + CIA) ----------
    def prior_m0(u: np.ndarray) -> np.ndarray:
        """Prior transform for M₀: 3 params (continuum level, slope, ray_amp).

        P0-v2-4 FIX: M₀ now includes Rayleigh + H₂-H₂ CIA as physically
        motivated background. Without them, any spectral slope is attributed
        to the test molecule, inflating Bayes factors by 10–100×.
        """
        theta = np.empty_like(u)
        theta[0] = u[0] * 0.01 + 0.99    # continuum: [0.99, 1.0]
        theta[1] = (u[1] - 0.5) * 0.001  # slope: [-0.0005, 0.0005]
        theta[2] = u[2] * 1e-3           # Rayleigh amplitude: [0, 1e-3]
        return theta

    def loglike_m0(theta: np.ndarray) -> float:
        """Log-likelihood for M₀: linear continuum + Rayleigh + CIA.

        P0-v2-4 FIX: Physical background opacity included. Rayleigh amplitude
        is a free parameter (accounts for cloud-top pressure uncertainty).
        CIA uses fiducial 300K temperature (contribution is small).
        """
        continuum, slope, ray_amp = theta
        model = continuum + slope * (wavelengths_um - wavelengths_um.mean())
        if _has_physics_bg:
            model = model - ray_amp * _sigma_ray_norm
            model = model - ray_amp * 0.1 * _sigma_cia_norm  # CIA ≈ 10% of Rayleigh
        residuals = (flux - model) / flux_err
        return float(-0.5 * np.sum(residuals ** 2))

    # --- Model M₁: with molecule (continuum + Rayleigh/CIA + absorption) -----
    def prior_m1(u: np.ndarray) -> np.ndarray:
        """Prior transform for M₁: 4 params (continuum, slope, ray_amp, log10_abundance).

        Same background parameters as M₀ plus the molecular abundance.
        Consistent dimensionality is required for valid Bayes factor computation.
        """
        from scipy.special import ndtri
        theta = np.empty_like(u)
        theta[0] = u[0] * 0.01 + 0.99
        theta[1] = (u[1] - 0.5) * 0.001
        theta[2] = u[2] * 1e-3           # Rayleigh amplitude (same prior as M₀)
        # Log10 mixing ratio with prior N(mu, sigma)
        theta[3] = prior_mu + prior_sigma * ndtri(np.clip(u[3], 1e-10, 1 - 1e-10))
        return theta

    def loglike_m1(theta: np.ndarray) -> float:
        """Log-likelihood for M₁: continuum + Rayleigh/CIA + molecular absorption.

        P0-v2-1 FIX: Voigt profiles instead of Gaussian bumps.
        P0-v2-4 FIX: Same Rayleigh + CIA background as M₀ (consistent null).
        """
        continuum, slope, ray_amp, log10_abundance = theta

        # Baseline continuum + physical background (same as M₀)
        model = continuum + slope * (wavelengths_um - wavelengths_um.mean())
        if _has_physics_bg:
            model = model - ray_amp * _sigma_ray_norm
            model = model - ray_amp * 0.1 * _sigma_cia_norm

        # Physics-based molecular absorption (Voigt profiles)
        try:
            from aria.genastra.spectra.forward_model import voigt_profile
            from aria.genastra.spectra.hitran_matcher import MOLECULAR_BANDS

            bands = MOLECULAR_BANDS.get(molecule, [])
            abundance = 10.0 ** log10_abundance

            for center, width, strength in bands:
                sigma_doppler = max(width / 5, 0.005)
                gamma_pressure = 0.01  # ESTIMATE — 0.01 µm Lorentzian half-width at 1 bar (Rothman 2013 JQSRT 130 4)
                x = wavelengths_um - center
                profile = voigt_profile(x, sigma_doppler, gamma_pressure)
                profile_norm = profile / (profile.max() + 1e-30)
                model = model - abundance * strength * 0.001 * profile_norm  # ESTIMATE — 1e-3 strength scaling factor

        except ImportError:
            from aria.genastra.spectra.hitran_matcher import MOLECULAR_BANDS
            bands = MOLECULAR_BANDS.get(molecule, [])
            abundance = 10.0 ** log10_abundance
            for center, width, strength in bands:
                absorption = abundance * strength * np.exp(
                    -0.5 * ((wavelengths_um - center) / (width / 2.355)) ** 2
                )
                model = model - absorption

        residuals = (flux - model) / flux_err
        return float(-0.5 * np.sum(residuals ** 2))

    # Run nested sampling for both models
    logger.info("nested_sampling_start", molecule=molecule, prior=prior_type, n_live=n_live)

    # P0-v2-4 FIX: M₀ now has 3 params (continuum, slope, ray_amp)
    sampler_m0 = dynesty.NestedSampler(loglike_m0, prior_m0, ndim=3, nlive=n_live)
    sampler_m0.run_nested(print_progress=False)
    results_m0 = sampler_m0.results

    # P0-v2-4 FIX: M₁ now has 4 params (continuum, slope, ray_amp, log10_abundance)
    sampler_m1 = dynesty.NestedSampler(loglike_m1, prior_m1, ndim=4, nlive=n_live)
    sampler_m1.run_nested(print_progress=False)
    results_m1 = sampler_m1.results

    # Extract log-evidence WITH UNCERTAINTY (BUILD-F1, Tao)
    log_z0 = float(results_m0.logz[-1])
    log_z1 = float(results_m1.logz[-1])
    log_z0_err = float(results_m0.logzerr[-1])
    log_z1_err = float(results_m1.logzerr[-1])

    # Bayes factor with propagated uncertainty
    log_bf = (log_z1 - log_z0) / math.log(10)  # convert ln to log10
    # δ(log₁₀K) = √(δlogZ₁² + δlogZ₀²) / ln(10)
    log_bf_err = math.sqrt(log_z1_err**2 + log_z0_err**2) / math.log(10)

    significance = classify_bayes_factor(log_bf)
    # If uncertainty exceeds 0.5 in log₁₀, the Jeffreys classification is unreliable
    significance_reliable = log_bf_err < 0.5

    fp_prob = compute_false_positive_prob(log_bf)

    # Extract posterior abundance from M₁
    weights = np.exp(results_m1.logwt - results_m1.logz[-1])
    weights /= weights.sum()
    abundance_samples = results_m1.samples[:, 3]  # log10(abundance) — index 3 after P0-v2-4 fix

    posterior_median = float(np.average(abundance_samples, weights=weights))
    ci_lower = float(np.percentile(abundance_samples, 2.5))
    ci_upper = float(np.percentile(abundance_samples, 97.5))

    # BUILD-F21 (Bialek): Mutual information between data and abundance
    # I(abundance; data) ≈ D_KL(posterior || prior) in nats, convert to bits
    mutual_info_bits = _compute_mutual_information(
        abundance_samples, weights, prior_mu, prior_sigma
    )

    if not significance_reliable:
        logger.warning(
            "nested_sampling_uncertainty_high",
            molecule=molecule,
            log10_bf=round(log_bf, 2),
            log10_bf_err=round(log_bf_err, 2),
            msg="Bayes factor uncertainty exceeds 0.5 — classification may be unreliable",
        )

    logger.info(
        "nested_sampling_done",
        molecule=molecule,
        log10_bf=f"{log_bf:.2f}±{log_bf_err:.2f}",
        significance=significance.value,
        reliable=significance_reliable,
        mutual_info_bits=round(mutual_info_bits, 2) if mutual_info_bits else None,
        fp_prob=round(fp_prob, 4),
    )

    return BayesianResult(
        molecule=molecule,
        log10_bayes_factor=round(log_bf, 3),
        log10_bayes_factor_err=round(log_bf_err, 3),
        significance=significance,
        significance_reliable=significance_reliable,
        log_evidence_with=log_z1,
        log_evidence_without=log_z0,
        posterior_abundance=10.0 ** posterior_median,
        abundance_ci_lower=10.0 ** ci_lower,
        abundance_ci_upper=10.0 ** ci_upper,
        false_positive_prob=round(fp_prob, 4),
        prior_type=prior_type,
        mutual_information_bits=mutual_info_bits,
    )


def _compute_mutual_information(
    posterior_samples: np.ndarray,
    weights: np.ndarray,
    prior_mu: float,
    prior_sigma: float,
) -> float | None:
    """Compute mutual information I(abundance; data) in bits.

    BUILD-F21 (Bialek): "How many BITS of information does this spectrum
    contain about atmospheric composition?"

    I ≈ D_KL(posterior || prior) = ∫ q(θ) log(q(θ)/p(θ)) dθ

    where q is the posterior and p is the prior. Computed via weighted
    samples from nested sampling.

    If I < 1 bit, the spectrum is essentially uninformative about this
    molecule regardless of the Bayes factor value.
    """
    try:
        if len(posterior_samples) < 10:
            return None

        # Weighted posterior statistics
        post_mean = float(np.average(posterior_samples, weights=weights))
        post_var = float(np.average((posterior_samples - post_mean)**2, weights=weights))

        if post_var <= 0:
            return 0.0

        post_sigma = math.sqrt(post_var)

        # KL divergence for two Gaussians:
        # D_KL(q || p) = log(σ_p/σ_q) + (σ_q² + (μ_q - μ_p)²)/(2σ_p²) - 1/2
        kl_nats = (
            math.log(max(prior_sigma, 1e-10) / max(post_sigma, 1e-10))
            + (post_sigma**2 + (post_mean - prior_mu)**2) / (2 * prior_sigma**2)
            - 0.5
        )

        # Convert nats to bits
        kl_bits = max(kl_nats / math.log(2), 0.0)
        return round(kl_bits, 3)

    except Exception:
        return None


def compute_combinatorial_biosignature(
    individual_results: list[BayesianResult],
    temperature_k: float = 300.0,
) -> dict:
    """Compute joint biosignature score for molecule COMBINATIONS.

    BUILD-F5 (Diaconis) + v2 P1-v2-1 (Sasselov):
    "O₂ + CH₄ together is 1000x stronger evidence for biology than either alone."

    Thermodynamically incompatible pairs (co-existing only if biology maintains them):
    - O₂ + CH₄: incompatible (CH₄ oxidized in O₂ atmosphere in ~10⁴ years)
    - O₂ + N₂O: N₂O destroyed by UV in ~100 years, only maintained biologically
    - O₃ + CH₄: O₃ requires O₂ which destroys CH₄

    The joint Bayes factor for "biology" given detections of both X and Y:
    K_joint ≈ K_X × K_Y × B_incompatibility

    where B_incompatibility is the boost from thermodynamic incompatibility.
    """
    from aria.genastra.spectra.thermodynamics import compute_disequilibrium

    # Known thermodynamically incompatible pairs
    incompatible_pairs: dict[tuple[str, str], float] = {
        ("O2", "CH4"): 1000.0,   # very strong: CH4 oxidized in O2 atmosphere
        ("O2", "N2O"): 100.0,    # strong: N2O photolyzed, needs continuous production
        ("O3", "CH4"): 500.0,    # strong: O3 requires O2 which destroys CH4
        ("O2", "DMS"): 50.0,     # moderate: DMS oxidized by O2/OH radicals
        ("O2", "DMDS"): 50.0,    # moderate: same as DMS
        ("CH4", "CO2"): 10.0,    # weak: can coexist in reducing atmospheres
    }

    # Build result
    detected_molecules = {
        r.molecule: r for r in individual_results
        if r.log10_bayes_factor > 0  # positive evidence
    }

    # Find incompatible pairs that are BOTH detected
    pair_scores: list[dict] = []
    for (mol_a, mol_b), boost in incompatible_pairs.items():
        if mol_a in detected_molecules and mol_b in detected_molecules:
            res_a = detected_molecules[mol_a]
            res_b = detected_molecules[mol_b]

            # Joint log₁₀(K) = log₁₀(K_A) + log₁₀(K_B) + log₁₀(B_incompatibility)
            joint_log10_k = (
                res_a.log10_bayes_factor
                + res_b.log10_bayes_factor
                + math.log10(boost)
            )

            pair_scores.append({
                "pair": f"{mol_a}+{mol_b}",
                "log10_k_individual_a": res_a.log10_bayes_factor,
                "log10_k_individual_b": res_b.log10_bayes_factor,
                "incompatibility_boost_log10": math.log10(boost),
                "joint_log10_k": round(joint_log10_k, 2),
                "joint_significance": classify_bayes_factor(joint_log10_k).value,
                "joint_fp_prob": round(compute_false_positive_prob(joint_log10_k), 6),
                "explanation": (
                    f"{mol_a} and {mol_b} are thermodynamically incompatible. "
                    f"Their coexistence requires a continuous production mechanism "
                    f"(on Earth: biology). Joint evidence log₁₀K = {joint_log10_k:.1f}."
                ),
            })

    # Compute atmospheric disequilibrium if enough molecules detected
    diseq = None
    if len(detected_molecules) >= 2:
        composition = {}
        for mol, res in detected_molecules.items():
            if res.posterior_abundance is not None:
                composition[mol] = res.posterior_abundance
        if composition:
            try:
                diseq_result = compute_disequilibrium(composition, temperature_k)
                diseq = {
                    "delta_g_j_per_mol": diseq_result.delta_g_j_per_mol,
                    "classification": diseq_result.classification,
                    "earth_comparison": diseq_result.earth_comparison,
                    "interpretation": diseq_result.interpretation,
                }
            except Exception:  # noqa: S110, BLE001
                pass

    return {
        "n_detected_molecules": len(detected_molecules),
        "detected": list(detected_molecules.keys()),
        "incompatible_pairs": pair_scores,
        "strongest_pair": max(pair_scores, key=lambda p: p["joint_log10_k"]) if pair_scores else None,
        "thermodynamic_disequilibrium": diseq,
        "overall_biosignature_assessment": _assess_overall(pair_scores, diseq),
    }


def _assess_overall(
    pair_scores: list[dict],
    diseq: dict | None,
) -> str:
    """Generate overall biosignature assessment from combinatorial analysis."""
    parts = []

    if not pair_scores:
        parts.append("No thermodynamically incompatible molecule pairs detected.")
        if diseq and diseq["classification"] != "near_equilibrium":
            parts.append(f"However, atmospheric disequilibrium is {diseq['classification']}.")
        return " ".join(parts)

    strongest = max(pair_scores, key=lambda p: p["joint_log10_k"])
    if strongest["joint_log10_k"] > DETECTION_CLAIM_THRESHOLD:
        parts.append(
            f"STRONG COMBINATORIAL BIOSIGNATURE: {strongest['pair']} pair has "
            f"joint log₁₀K = {strongest['joint_log10_k']:.1f}, exceeding the "
            f"detection threshold of {DETECTION_CLAIM_THRESHOLD}. "
            f"These molecules are thermodynamically incompatible and their "
            f"coexistence strongly suggests an active biological source."
        )
    else:
        parts.append(
            f"Tentative combinatorial signal: {strongest['pair']} pair has "
            f"joint log₁₀K = {strongest['joint_log10_k']:.1f}, below the "
            f"detection threshold. More data needed."
        )

    if diseq:
        parts.append(diseq["interpretation"])

    return " ".join(parts)


def _approximate_bayes_factor(
    wavelengths_um: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray,
    molecule: str,
    prior_type: str,
) -> BayesianResult:
    """Approximate Bayes factor using BIC (fallback when dynesty unavailable).

    BIC ≈ -2 log(L) + k log(n)
    log₁₀(BF) ≈ (BIC₀ - BIC₁) / (2 × ln(10))
    """
    from aria.genastra.spectra.hitran_matcher import MOLECULAR_BANDS

    n = len(wavelengths_um)
    wavelengths_um.mean()

    # M₀: linear continuum (2 params)
    continuum = np.median(flux)
    model_m0 = np.full_like(flux, continuum)
    chi2_m0 = np.sum(((flux - model_m0) / flux_err) ** 2)
    bic_m0 = chi2_m0 + 2 * np.log(n)

    # M₁: continuum + absorption (3 params)
    bands = MOLECULAR_BANDS.get(molecule, [])
    model_m1 = model_m0.copy()
    if bands:
        center, width, strength = bands[0]
        depth = 0.001 * strength
        model_m1 = model_m1 - depth * np.exp(-0.5 * ((wavelengths_um - center) / (width / 2.355)) ** 2)

    chi2_m1 = np.sum(((flux - model_m1) / flux_err) ** 2)
    bic_m1 = chi2_m1 + 3 * np.log(n)

    log10_bf = float((bic_m0 - bic_m1) / (2 * np.log(10)))

    return BayesianResult(
        molecule=molecule,
        log10_bayes_factor=round(log10_bf, 3),
        log10_bayes_factor_err=0.5,  # BIC approximation has no uncertainty estimate
        significance=classify_bayes_factor(log10_bf),
        significance_reliable=False,  # BIC approximation is unreliable
        log_evidence_with=float(-chi2_m1 / 2),
        log_evidence_without=float(-chi2_m0 / 2),
        posterior_abundance=None,
        abundance_ci_lower=None,
        abundance_ci_upper=None,
        false_positive_prob=compute_false_positive_prob(log10_bf),
        prior_type=prior_type,
        mutual_information_bits=None,
    )


def run_prior_sensitivity(
    wavelengths_um: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray,
    molecule: str,
    n_live: int = NESTED_SAMPLING_LIVE_POINTS,
) -> dict[str, float]:
    """Run nested sampling with all three prior types and report Bayes factors.

    Panel 5 (Mathematician): "Prior sensitivity analysis: run all three;
    report all three Bayes factors."
    """
    results: dict[str, float] = {}

    for prior_type in ["empirical", "uninformative", "pessimistic"]:
        result = run_nested_sampling(
            wavelengths_um, flux, flux_err, molecule,
            prior_type=prior_type, n_live=n_live,
        )
        results[prior_type] = result.log10_bayes_factor

    return results


@dataclass(frozen=True)
class JointRetrievalResult:
    """Joint retrieval of multiple molecules from a single spectral dataset.

    P1 FIX (Panel 3 NASA JPL, Panel 10 ESA): Independent per-molecule nested
    sampling ignores spectral degeneracies — if CH4 and CO2 overlap at 3.3 μm,
    independent fits can attribute the same absorption to the wrong molecule.
    Joint retrieval fits all molecules simultaneously with a single forward model,
    properly handling spectral blending and parameter correlations.
    """

    molecules: tuple[str, ...]
    individual_results: tuple[BayesianResult, ...]  # per-molecule from joint posterior
    joint_log_evidence: float          # log Z of the full joint model
    null_log_evidence: float           # log Z of continuum-only model
    joint_log10_bayes_factor: float    # log₁₀(K_joint / K_null)
    posterior_abundances: dict[str, float]        # mol → median mixing ratio
    abundance_cis: dict[str, tuple[float, float]] # mol → (lower, upper) 95% CI
    posterior_correlations: dict[str, float]      # "mol_a:mol_b" → Pearson r
    n_live_points: int
    prior_type: str


def run_joint_retrieval(
    wavelengths_um: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray,
    molecules: list[str],
    prior_type: str = "empirical",
    n_live: int = NESTED_SAMPLING_LIVE_POINTS,
) -> JointRetrievalResult:
    """Fit all molecules simultaneously in a single nested sampling run.

    P1 FIX (Panel 3 NASA JPL Astrobiology, Panel 10 ESA Astrobiology):
    Independent per-molecule Bayes factors assume spectral independence.
    This breaks down when molecules share absorption bands (e.g., CH4 at
    3.3 μm overlaps with H2O; DMS at 3.4 μm overlaps with CH4).

    Joint retrieval model M_joint has (3 + N_mol) parameters:
      θ[0] = continuum_level
      θ[1] = slope
      θ[2] = rayleigh_amplitude
      θ[3+i] = log10(f_mol_i)  for each molecule i

    The null model M₀ has 3 parameters (no molecules).

    The joint Bayes factor K_joint = Z_joint / Z_null correctly accounts
    for spectral blending; individual posterior marginals provide per-molecule
    abundance estimates with properly propagated covariance.

    Args:
        wavelengths_um: Wavelength grid (μm).
        flux: Observed transit depth (Rp/Rs)².
        flux_err: Flux uncertainties.
        molecules: List of molecule names to fit jointly (e.g. ["CH4","CO2","H2O"]).
        prior_type: "empirical" | "uninformative" | "pessimistic".
        n_live: Nested sampling live points.

    Returns:
        JointRetrievalResult with joint Bayes factor and per-molecule posteriors.
    """
    if not molecules:
        raise ValueError("molecules list must not be empty")

    try:
        import dynesty
    except ImportError as err:
        raise ImportError(
            "dynesty is required for joint molecular retrieval. "
            "Install with: pip install dynesty"
        ) from err

    n_mol = len(molecules)
    ndim_joint = 3 + n_mol   # continuum, slope, ray_amp, log10_f × N
    ndim_null = 3             # continuum, slope, ray_amp

    # Pre-compute background opacity (Rayleigh + H2-H2 CIA)
    try:
        from aria.genastra.spectra.forward_model import (
            h2h2_cia_cross_section,
            rayleigh_scattering_cross_section,
        )
        sigma_ray = rayleigh_scattering_cross_section(wavelengths_um)
        sigma_ray_norm = sigma_ray / (sigma_ray.max() + 1e-40)
        sigma_cia = h2h2_cia_cross_section(wavelengths_um, temperature=300.0)
        sigma_cia_norm = sigma_cia / (sigma_cia.max() + 1e-40)
        has_physics_bg = True
    except ImportError:
        sigma_ray_norm = np.zeros_like(wavelengths_um)
        sigma_cia_norm = np.zeros_like(wavelengths_um)
        has_physics_bg = False

    # Pre-fetch molecular band data
    from aria.genastra.spectra.hitran_matcher import MOLECULAR_BANDS
    try:
        from aria.genastra.spectra.forward_model import voigt_profile
        has_voigt = True
    except ImportError:
        has_voigt = False

    # Per-molecule prior parameters
    mol_priors = [get_prior(prior_type, m) for m in molecules]

    def _background_model(theta: np.ndarray) -> np.ndarray:
        continuum, slope, ray_amp = theta[0], theta[1], theta[2]
        model = continuum + slope * (wavelengths_um - wavelengths_um.mean())
        if has_physics_bg:
            model = model - ray_amp * sigma_ray_norm
            model = model - ray_amp * 0.1 * sigma_cia_norm
        return model

    def _add_molecular_absorption(
        model: np.ndarray,
        molecule: str,
        log10_abundance: float,
    ) -> np.ndarray:
        bands = MOLECULAR_BANDS.get(molecule, [])
        if not bands:
            return model
        abundance = 10.0 ** log10_abundance
        result = model.copy()
        for center, width, strength in bands:
            if has_voigt:
                sigma_doppler = max(width / 5, 0.005)
                gamma_pressure = 0.01  # ESTIMATE — Lorentzian half-width 0.01 µm at 1 bar (Rothman 2013 JQSRT 130 4)
                x = wavelengths_um - center
                profile = voigt_profile(x, sigma_doppler, gamma_pressure)
                profile_norm = profile / (profile.max() + 1e-30)
                result = result - abundance * strength * 0.001 * profile_norm  # ESTIMATE — 1e-3 strength scaling
            else:
                absorption = abundance * strength * np.exp(
                    -0.5 * ((wavelengths_um - center) / (width / 2.355)) ** 2
                )
                result = result - absorption
        return result

    # Null model: continuum + background only (no molecules)
    def prior_null(u: np.ndarray) -> np.ndarray:
        theta = np.empty_like(u)
        theta[0] = u[0] * 0.01 + 0.99
        theta[1] = (u[1] - 0.5) * 0.001
        theta[2] = u[2] * 1e-3
        return theta

    def loglike_null(theta: np.ndarray) -> float:
        model = _background_model(theta)
        residuals = (flux - model) / flux_err
        return float(-0.5 * np.sum(residuals ** 2))

    # Joint model: background + all N molecules simultaneously
    def prior_joint(u: np.ndarray) -> np.ndarray:
        from scipy.special import ndtri
        theta = np.empty_like(u)
        theta[0] = u[0] * 0.01 + 0.99
        theta[1] = (u[1] - 0.5) * 0.001
        theta[2] = u[2] * 1e-3
        for i, (mu, sigma) in enumerate(mol_priors):
            theta[3 + i] = mu + sigma * ndtri(np.clip(u[3 + i], 1e-10, 1 - 1e-10))
        return theta

    def loglike_joint(theta: np.ndarray) -> float:
        model = _background_model(theta)
        for i, mol in enumerate(molecules):
            model = _add_molecular_absorption(model, mol, theta[3 + i])
        residuals = (flux - model) / flux_err
        return float(-0.5 * np.sum(residuals ** 2))

    logger.info(
        "joint_retrieval_start",
        molecules=molecules,
        n_params=ndim_joint,
        prior=prior_type,
        n_live=n_live,
    )

    sampler_null = dynesty.NestedSampler(loglike_null, prior_null, ndim=ndim_null, nlive=n_live)
    sampler_null.run_nested(print_progress=False)
    results_null = sampler_null.results

    sampler_joint = dynesty.NestedSampler(loglike_joint, prior_joint, ndim=ndim_joint, nlive=n_live)
    sampler_joint.run_nested(print_progress=False)
    results_joint = sampler_joint.results

    log_z_null = float(results_null.logz[-1])
    log_z_joint = float(results_joint.logz[-1])
    log_z_null_err = float(results_null.logzerr[-1])
    log_z_joint_err = float(results_joint.logzerr[-1])

    joint_log_bf = (log_z_joint - log_z_null) / math.log(10)
    joint_log_bf_err = math.sqrt(log_z_joint_err**2 + log_z_null_err**2) / math.log(10)

    # Extract per-molecule posteriors from joint samples
    weights = np.exp(results_joint.logwt - results_joint.logz[-1])
    weights /= weights.sum()

    posterior_abundances: dict[str, float] = {}
    abundance_cis: dict[str, tuple[float, float]] = {}
    posterior_correlations: dict[str, float] = {}

    mol_samples = results_joint.samples[:, 3:]  # shape: (n_samples, n_mol)

    for i, mol in enumerate(molecules):
        log10_samples = mol_samples[:, i]
        posterior_abundances[mol] = float(10.0 ** np.average(log10_samples, weights=weights))
        ci_lo = float(np.percentile(log10_samples, 2.5))
        ci_hi = float(np.percentile(log10_samples, 97.5))
        abundance_cis[mol] = (10.0 ** ci_lo, 10.0 ** ci_hi)

    # Pairwise correlations between molecular abundances (spectral degeneracies)
    for i in range(n_mol):
        for j in range(i + 1, n_mol):
            key = f"{molecules[i]}:{molecules[j]}"
            si = mol_samples[:, i]
            sj = mol_samples[:, j]
            # Weighted Pearson correlation
            wi = weights
            mean_i = np.average(si, weights=wi)
            mean_j = np.average(sj, weights=wi)
            cov_ij = np.average((si - mean_i) * (sj - mean_j), weights=wi)
            std_i = math.sqrt(max(np.average((si - mean_i)**2, weights=wi), 1e-30))
            std_j = math.sqrt(max(np.average((sj - mean_j)**2, weights=wi), 1e-30))
            posterior_correlations[key] = round(cov_ij / (std_i * std_j), 3)

    # Build per-molecule BayesianResult from joint posteriors
    # Per-molecule BF from joint model vs null (marginalizing over other molecules)
    individual_results: list[BayesianResult] = []
    for i, mol in enumerate(molecules):
        # Effective per-molecule BF: divide joint BF equally as first-order estimate.
        # True marginal BF requires running N single-molecule models, which is expensive.
        # This approximation is labeled; callers should use run_nested_sampling() for
        # individual molecule BFs if needed.
        log10_samples_i = mol_samples[:, i]
        mi = _compute_mutual_information(log10_samples_i, weights, *mol_priors[i])
        fp_prob = compute_false_positive_prob(joint_log_bf / max(n_mol, 1))
        individual_results.append(BayesianResult(
            molecule=mol,
            log10_bayes_factor=round(joint_log_bf / max(n_mol, 1), 3),
            log10_bayes_factor_err=round(joint_log_bf_err, 3),
            significance=classify_bayes_factor(joint_log_bf / max(n_mol, 1)),
            significance_reliable=joint_log_bf_err < 0.5,
            log_evidence_with=log_z_joint,
            log_evidence_without=log_z_null,
            posterior_abundance=posterior_abundances[mol],
            abundance_ci_lower=abundance_cis[mol][0],
            abundance_ci_upper=abundance_cis[mol][1],
            false_positive_prob=round(fp_prob, 4),
            prior_type=prior_type,
            mutual_information_bits=mi,
        ))

    logger.info(
        "joint_retrieval_done",
        molecules=molecules,
        joint_log10_bf=f"{joint_log_bf:.2f}±{joint_log_bf_err:.2f}",
        correlations={k: v for k, v in posterior_correlations.items() if abs(v) > 0.3},
    )

    return JointRetrievalResult(
        molecules=tuple(molecules),
        individual_results=tuple(individual_results),
        joint_log_evidence=log_z_joint,
        null_log_evidence=log_z_null,
        joint_log10_bayes_factor=round(joint_log_bf, 3),
        posterior_abundances=posterior_abundances,
        abundance_cis=abundance_cis,
        posterior_correlations=posterior_correlations,
        n_live_points=n_live,
        prior_type=prior_type,
    )
