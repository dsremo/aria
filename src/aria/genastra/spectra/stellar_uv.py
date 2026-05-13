"""Stellar UV environment modeling.

Panel 3 (NASA JPL): "Stellar UV matters. A star's spectral type determines
which molecules survive. An M-dwarf's UV flares can destroy surface biosignatures."
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StellarUVProfile:
    """UV characteristics of a host star."""

    spectral_type: str
    effective_temp_k: float
    uv_flux_ratio_to_sun: float  # relative to Sun at 1 AU
    flare_frequency: str  # "none", "low", "moderate", "high"
    habitable_zone_inner_au: float
    habitable_zone_outer_au: float
    notes: str


# Reference stellar UV profiles
# HZ limits: Kopparapu et al. (2013) ApJ 765 131 (moist greenhouse / maximum greenhouse)
# UV flux ratios: Segura et al. (2005) Astrobiology 5 706 (relative to solar at 1 AU)
STELLAR_PROFILES: dict[str, StellarUVProfile] = {
    "F": StellarUVProfile(
        spectral_type="F",
        effective_temp_k=6500,    # ESTIMATE — mid-F star Teff (Pecaut & Mamajek 2013 ApJS 208 9)
        uv_flux_ratio_to_sun=3.0, # ESTIMATE — F-star UV ~3× solar at HZ (Segura 2005 Astrobiology 5 706)
        flare_frequency="none",
        habitable_zone_inner_au=1.5, # Kopparapu 2013 ApJ 765 131: F-star moist greenhouse limit
        habitable_zone_outer_au=2.5, # Kopparapu 2013: F-star maximum greenhouse limit
        notes="Higher UV than Sun. Faster photodissociation of biosignatures.",
    ),
    "G": StellarUVProfile(
        spectral_type="G",
        effective_temp_k=5800,    # Sun Teff = 5778 K (Prša 2016 AJ 152 41)
        uv_flux_ratio_to_sun=1.0, # Solar reference (by definition)
        flare_frequency="low",
        habitable_zone_inner_au=0.95, # Kopparapu 2013 ApJ 765 131: solar moist greenhouse limit
        habitable_zone_outer_au=1.67, # Kopparapu 2013: solar maximum greenhouse limit
        notes="Solar analog. Reference for all photochemistry models.",
    ),
    "K": StellarUVProfile(
        spectral_type="K",
        effective_temp_k=4500,    # ESTIMATE — mid-K star Teff (Pecaut & Mamajek 2013)
        uv_flux_ratio_to_sun=0.3, # ESTIMATE — K-star NUV ~0.3× solar (Segura 2005)
        flare_frequency="low",
        habitable_zone_inner_au=0.5, # Kopparapu 2013 ApJ 765 131: K-star HZ inner limit
        habitable_zone_outer_au=1.0, # Kopparapu 2013: K-star HZ outer limit
        notes="Lower UV than Sun. Biosignatures persist longer.",
    ),
    "M": StellarUVProfile(
        spectral_type="M",
        effective_temp_k=3300,     # ESTIMATE — mid-M star Teff (Pecaut & Mamajek 2013)
        uv_flux_ratio_to_sun=0.01, # ESTIMATE — M-star quiescent UV ~1% solar (Segura 2005 Astrobiology 5 706)
        flare_frequency="high",
        habitable_zone_inner_au=0.1, # Kopparapu 2013 ApJ 765 131: M-star HZ inner limit
        habitable_zone_outer_au=0.3, # Kopparapu 2013: M-star HZ outer limit
        notes=(
            "Very low quiescent UV but frequent intense flares. "
            "Flares can be 100-1000x solar UV for minutes to hours. "
            "Habitable zone is tidally locked. "
            "Biosignature survival depends on atmospheric shielding."
        ),
    ),
}


def get_stellar_profile(
    spectral_type: str | None = None,
    teff_k: float | None = None,
) -> StellarUVProfile:
    """Get the UV profile for a star by spectral type or temperature."""
    if spectral_type:
        key = spectral_type[0].upper()
        if key in STELLAR_PROFILES:
            return STELLAR_PROFILES[key]

    if teff_k:
        if teff_k > 6000:
            return STELLAR_PROFILES["F"]
        if teff_k > 5200:
            return STELLAR_PROFILES["G"]
        if teff_k > 3700:
            return STELLAR_PROFILES["K"]
        return STELLAR_PROFILES["M"]

    return STELLAR_PROFILES["G"]  # default to solar
