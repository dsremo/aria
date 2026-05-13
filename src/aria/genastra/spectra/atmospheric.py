"""Atmospheric context and abiotic pathway checking.

Panel 3 (NASA JPL) critique:
"Line matching alone is insufficient. Atmospheric context is critical:
DMS on an exoplanet requires an anaerobic source; if the atmosphere has
abundant O2, DMS would be destroyed rapidly."

"Missing abiotic production pathways. CH4 can be produced by serpentinization;
N2O by lightning."
"""

from __future__ import annotations

from dataclasses import dataclass

from aria.genastra.core.constants import ABIOTIC_PATHWAYS


@dataclass(frozen=True)
class AbioticCheck:
    """Result of abiotic pathway check for a molecule."""

    molecule: str
    has_abiotic_source: bool
    pathways: tuple[dict[str, str], ...]
    explanation: str


@dataclass(frozen=True)
class PhotochemCheck:
    """Result of photochemical stability check."""

    molecule: str
    is_stable: bool
    lifetime_hours: float | None
    explanation: str


def check_abiotic_pathways(molecule: str) -> AbioticCheck:
    """Check if a molecule has known abiotic (non-biological) production pathways.

    This is critical for biosignature claims — detecting CH4 doesn't
    prove biology if serpentinization can explain it.
    """
    pathways = ABIOTIC_PATHWAYS.get(molecule, [])
    has_abiotic = len(pathways) > 0

    if has_abiotic:
        pathway_strs = [f"{p['source']} ({p['condition']})" for p in pathways]
        explanation = (
            f"{molecule} can be produced abiotically via: "
            + "; ".join(pathway_strs) + ". "
            "Detection does NOT imply biological origin without ruling out these sources."
        )
    else:
        explanation = (
            f"No known abiotic production pathway for {molecule} on Earth. "
            "If confirmed, this would be a strong biosignature candidate. "
            "However, absence of known abiotic pathways on Earth does not "
            "preclude unknown extraterrestrial chemistry."
        )

    return AbioticCheck(
        molecule=molecule,
        has_abiotic_source=has_abiotic,
        pathways=tuple(pathways),
        explanation=explanation,
    )


def check_photochemical_stability(
    molecule: str,
    stellar_type: str | None,
    stellar_teff_k: float | None,
) -> PhotochemCheck:
    """Check if a molecule is photochemically stable in the given stellar environment.

    Panel 3 (NASA JPL): "A star's spectral type determines which molecules survive.
    An M-dwarf's UV flares can destroy surface biosignatures."

    M dwarfs have strong UV flares that can photodissociate many molecules.
    The question is: does the molecule survive long enough to accumulate
    to detectable levels?
    """
    # Estimated photodissociation lifetimes under different stellar types
    # (hours, in upper atmosphere at ~100 mbar)
    # Source: Rugheimer et al. 2015, Segura et al. 2005
    photodissociation_lifetimes: dict[str, dict[str, float]] = {
        "DMS": {"G": 24.0, "K": 48.0, "M": 2.0, "F": 12.0},
        "DMDS": {"G": 12.0, "K": 24.0, "M": 1.0, "F": 6.0},
        "O3": {"G": 168.0, "K": 336.0, "M": 24.0, "F": 84.0},
        "CH4": {"G": 87600.0, "K": 175200.0, "M": 43800.0, "F": 43800.0},  # years
        "N2O": {"G": 876.0, "K": 1752.0, "M": 438.0, "F": 438.0},
        "NH3": {"G": 0.5, "K": 1.0, "M": 0.1, "F": 0.25},
    }

    # Determine stellar class from type or temperature
    stellar_class = "G"  # default (Sun-like)
    if stellar_type:
        stellar_class = stellar_type[0].upper()
    elif stellar_teff_k:
        if stellar_teff_k > 6000:
            stellar_class = "F"
        elif stellar_teff_k > 5200:
            stellar_class = "G"
        elif stellar_teff_k > 3700:
            stellar_class = "K"
        else:
            stellar_class = "M"

    lifetimes = photodissociation_lifetimes.get(molecule)
    if lifetimes is None:
        return PhotochemCheck(
            molecule=molecule,
            is_stable=True,
            lifetime_hours=None,
            explanation=f"No photodissociation data available for {molecule}.",
        )

    lifetime = lifetimes.get(stellar_class, lifetimes.get("G", 24.0))

    # Stability criterion: lifetime > 1 hour (can accumulate)
    # For M-dwarfs with flares, need > 24 hours to survive flare events
    # Reference: Segura 2005 Astrobiology 5 706 (M-dwarf UV environment); Rugheimer 2015 ApJ 809 57
    threshold = 24.0 if stellar_class == "M" else 1.0  # ESTIMATE — M-dwarf: 24 h; others: 1 h (Segura 2005)
    is_stable = lifetime > threshold

    if is_stable:
        explanation = (
            f"{molecule} has estimated photodissociation lifetime of {lifetime:.0f} hours "
            f"around a {stellar_class}-type star. The molecule is photochemically stable "
            f"enough to accumulate to detectable levels."
        )
    else:
        explanation = (
            f"{molecule} has estimated photodissociation lifetime of only {lifetime:.1f} hours "
            f"around a {stellar_class}-type star. "
            f"{'UV flares from this M-dwarf would rapidly destroy ' + molecule + '. ' if stellar_class == 'M' else ''}"
            f"Detection would require a continuous production rate exceeding "
            f"photodissociation. This makes biological detection less likely "
            f"unless a strong, sustained source exists."
        )

    return PhotochemCheck(
        molecule=molecule,
        is_stable=is_stable,
        lifetime_hours=lifetime,
        explanation=explanation,
    )
