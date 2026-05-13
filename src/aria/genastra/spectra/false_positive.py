"""False positive rate estimation for biosignature detections.

Panel 3 (NASA JPL): "Every claimed detection must report:
P(false positive | data, stellar type, atmospheric model)."

Carl Sagan's dictum: "Extraordinary claims require extraordinary evidence."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from aria.genastra.core.constants import (
    BAYES_FACTOR_SUBSTANTIAL,
    DETECTION_CLAIM_THRESHOLD,
)
from aria.genastra.spectra.atmospheric import check_abiotic_pathways, check_photochemical_stability

if TYPE_CHECKING:
    from aria.genastra.spectra.bayesian import BayesianResult


@dataclass(frozen=True)
class DetectionAssessment:
    """Complete assessment of a biosignature detection claim."""

    molecule: str
    bayesian_result: BayesianResult
    abiotic_flag: bool
    abiotic_explanation: str
    photochem_stable: bool
    photochem_explanation: str
    meets_detection_threshold: bool
    overall_assessment: str
    confidence_level: str  # "no_detection", "tentative", "robust", "extraordinary"


def assess_detection(
    bayesian_result: BayesianResult,
    stellar_type: str | None,
    stellar_teff_k: float | None,
) -> DetectionAssessment:
    """Comprehensive assessment of a biosignature detection.

    Combines Bayesian evidence with abiotic pathway checking and
    photochemical stability to produce a final assessment.
    """
    molecule = bayesian_result.molecule
    log10_bf = bayesian_result.log10_bayes_factor

    # Check abiotic pathways
    abiotic = check_abiotic_pathways(molecule)

    # Check photochemical stability
    photochem = check_photochemical_stability(molecule, stellar_type, stellar_teff_k)

    # Does it meet the extraordinary claims threshold?
    meets_threshold = log10_bf >= DETECTION_CLAIM_THRESHOLD

    # P2-E4b (Roberge): photochem_consistent: bool | None being None silently skips
    # one of the strongest biosignature checks (disequilibrium chemistry, e.g. O2+CH4).
    # For detections at or above SUBSTANTIAL evidence, the photochem check is mandatory.
    # If it was not run (photochem.is_stable is None-equivalent from the module),
    # we downgrade the confidence to at most "tentative" as a safety measure.
    photochem_run = photochem.explanation != "Photochemical stability check not performed"

    # Determine confidence level
    if log10_bf < 0:
        confidence = "no_detection"
    elif log10_bf < BAYES_FACTOR_SUBSTANTIAL:
        confidence = "tentative"
    elif log10_bf >= BAYES_FACTOR_SUBSTANTIAL and not photochem_run:
        # P2-E4b: downgrade any SUBSTANTIAL+ detection where photochem check was skipped
        confidence = "tentative"
    elif log10_bf < DETECTION_CLAIM_THRESHOLD:
        confidence = "robust"
    else:
        confidence = "extraordinary"

    # Generate overall assessment
    parts: list[str] = []

    if confidence == "no_detection":
        parts.append(f"{molecule} is NOT detected (Bayes factor favors null model).")
    elif confidence == "tentative":
        parts.append(
            f"{molecule} shows tentative evidence (log₁₀K = {log10_bf:.1f}), "
            f"below the threshold for a reliable detection."
        )
    elif confidence == "robust":
        parts.append(
            f"{molecule} is detected with robust evidence (log₁₀K = {log10_bf:.1f}). "
            f"However, this is below the extraordinary claims threshold of {DETECTION_CLAIM_THRESHOLD}."
        )
        if not photochem_run:
            parts.append(
                "WARNING: Photochemical stability check was not performed. "
                "Detection downgraded to 'tentative' pending photochem verification. "
                "(P2-E4b: photochem_consistent is required for SUBSTANTIAL+ detections.)"
            )
    else:
        parts.append(
            f"{molecule} is detected with extraordinary evidence (log₁₀K = {log10_bf:.1f}), "
            f"exceeding the detection threshold of {DETECTION_CLAIM_THRESHOLD}."
        )

    if abiotic.has_abiotic_source:
        parts.append(
            f"CAUTION: {molecule} has known abiotic production pathways. "
            f"{abiotic.explanation}"
        )

    if not photochem.is_stable:
        parts.append(
            f"CAUTION: {photochem.explanation} "
            f"This reduces the plausibility of a sustained biological source."
        )

    if meets_threshold and not abiotic.has_abiotic_source and photochem.is_stable:
        parts.append(
            "This detection passes all checks: strong Bayesian evidence, "
            "no known abiotic source, photochemically stable. "
            "Further investigation is warranted."
        )

    return DetectionAssessment(
        molecule=molecule,
        bayesian_result=bayesian_result,
        abiotic_flag=abiotic.has_abiotic_source,
        abiotic_explanation=abiotic.explanation,
        photochem_stable=photochem.is_stable,
        photochem_explanation=photochem.explanation,
        meets_detection_threshold=meets_threshold,
        overall_assessment=" ".join(parts),
        confidence_level=confidence,
    )
