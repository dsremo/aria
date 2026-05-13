"""pLDDT interpretation and confidence reporting.

Critical: pLDDT is NOT a probability of structural correctness.
It is a model-internal confidence metric. This module provides
clear, honest interpretation text for every prediction.

Panel 5 (Mathematician) critique: "Must not present pLDDT as a p-value."
"""

from __future__ import annotations

from aria.genastra.core.constants import PLDDT_CONFIDENT, PLDDT_LOW, PLDDT_VERY_HIGH


def interpret_plddt(mean_plddt: float, per_residue: tuple[float, ...]) -> str:
    """Generate human-readable interpretation of pLDDT scores.

    Returns a multi-sentence interpretation that honestly conveys
    confidence level and limitations.
    """
    total = len(per_residue)
    if total == 0:
        return "No residues predicted."

    very_high = sum(1 for p in per_residue if p >= PLDDT_VERY_HIGH)
    confident = sum(1 for p in per_residue if PLDDT_CONFIDENT <= p < PLDDT_VERY_HIGH)
    low = sum(1 for p in per_residue if PLDDT_LOW <= p < PLDDT_CONFIDENT)
    disordered = sum(1 for p in per_residue if p < PLDDT_LOW)

    pct_confident = (very_high + confident) / total * 100

    parts: list[str] = []

    if mean_plddt >= PLDDT_VERY_HIGH:
        parts.append(f"Very high confidence prediction (mean pLDDT = {mean_plddt:.1f}).")
    elif mean_plddt >= PLDDT_CONFIDENT:
        parts.append(f"Confident prediction (mean pLDDT = {mean_plddt:.1f}).")
    elif mean_plddt >= PLDDT_LOW:
        parts.append(f"Low confidence prediction (mean pLDDT = {mean_plddt:.1f}). Interpret with caution.")
    else:
        parts.append(
            f"Very low confidence (mean pLDDT = {mean_plddt:.1f}). "
            f"This protein may be intrinsically disordered or lack homologs in training data."
        )

    parts.append(
        f"{pct_confident:.0f}% of residues have confident folds "
        f"({very_high} very high, {confident} confident, {low} low, {disordered} likely disordered)."
    )

    # Mandatory honesty statement
    parts.append(
        "NOTE: pLDDT is a model confidence metric, not a probability of structural "
        "correctness. The mapping between pLDDT and actual structural accuracy is "
        "non-linear and model-specific (Lin et al., Science 2023). High pLDDT regions "
        "are generally reliable for backbone conformation; sidechain positions may vary."
    )

    return " ".join(parts)


def classify_residue_confidence(plddt: float) -> str:
    """Classify a single residue's pLDDT into a confidence category."""
    if plddt >= PLDDT_VERY_HIGH:
        return "very_high"
    if plddt >= PLDDT_CONFIDENT:
        return "confident"
    if plddt >= PLDDT_LOW:
        return "low"
    return "disordered"


def identify_low_confidence_regions(
    per_residue: tuple[float, ...],
    threshold: float = PLDDT_LOW,
    min_length: int = 5,
) -> list[tuple[int, int]]:
    """Find contiguous regions with pLDDT below threshold.

    Returns list of (start, end) 0-indexed residue ranges.
    Useful for flagging potentially disordered loops.
    """
    regions: list[tuple[int, int]] = []
    start: int | None = None

    for i, p in enumerate(per_residue):
        if p < threshold:
            if start is None:
                start = i
        else:
            if start is not None and (i - start) >= min_length:
                regions.append((start, i - 1))
            start = None

    # Handle region extending to end
    if start is not None and (len(per_residue) - start) >= min_length:
        regions.append((start, len(per_residue) - 1))

    return regions
