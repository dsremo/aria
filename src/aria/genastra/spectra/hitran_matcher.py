"""HITRAN molecular absorption line matching.

Matches observed spectral features against the HITRAN database
of molecular absorption lines for biosignature molecules.

HITRAN (High-resolution Transmission Molecular Absorption Database)
contains spectral parameters for 55+ molecules.
URL: https://hitran.org/
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import structlog

logger = structlog.get_logger()

# HITRAN molecule IDs for key biosignature molecules
HITRAN_MOLECULE_IDS: dict[str, int] = {
    "H2O": 1,
    "CO2": 2,
    "O3": 3,
    "N2O": 4,
    "CO": 5,
    "CH4": 6,
    "O2": 7,
    "NO": 8,
    "SO2": 9,
    "NO2": 10,
    "NH3": 11,
    "H2S": 28,
    "DMS": -1,   # Not in standard HITRAN — use custom cross-sections
    "DMDS": -2,  # Not in standard HITRAN — use custom cross-sections
}

# Key absorption bands for biosignature molecules (wavelength in μm)
# These are the primary spectral features JWST can detect
MOLECULAR_BANDS: dict[str, list[tuple[float, float, float]]] = {
    # molecule: [(center_um, width_um, relative_strength), ...]  # noqa: ERA001
    "CH4": [
        (1.65, 0.1, 0.5),   # 1.65 μm band
        (2.32, 0.15, 0.7),  # 2.3 μm band
        (3.30, 0.2, 1.0),   # 3.3 μm ν₃ fundamental
        (7.66, 0.4, 0.8),   # 7.7 μm ν₄ fundamental
    ],
    "CO2": [
        (2.00, 0.1, 0.6),
        (2.70, 0.15, 0.8),  # 2.7 μm
        (4.25, 0.2, 1.0),   # 4.3 μm ν₃ asymmetric stretch
        (15.0, 1.0, 0.9),   # 15 μm ν₂ bending
    ],
    "O3": [
        (4.75, 0.3, 0.5),   # 4.7 μm
        (9.60, 0.5, 1.0),   # 9.6 μm ν₃ Hartley/Huggins
    ],
    "N2O": [
        (4.50, 0.2, 1.0),   # 4.5 μm ν₃
        (7.78, 0.3, 0.7),   # 7.8 μm ν₁
    ],
    "H2O": [
        (1.38, 0.1, 0.6),   # 1.4 μm
        (1.87, 0.1, 0.7),   # 1.9 μm
        (2.70, 0.2, 1.0),   # 2.7 μm ν₁, ν₃
        (6.27, 0.5, 0.9),   # 6.3 μm ν₂ bending
    ],
    "DMS": [
        (3.34, 0.05, 0.8),  # C-H stretch
        (6.90, 0.1, 0.5),   # S-C stretch
        (9.70, 0.2, 1.0),   # C-S-C asymmetric stretch
    ],
    "DMDS": [
        (3.35, 0.05, 0.7),
        (6.85, 0.1, 0.5),
        (10.2, 0.2, 1.0),   # S-S stretch + C-S
    ],
    "O2": [
        (0.76, 0.02, 1.0),  # A-band (visible, not JWST range)
        (1.27, 0.03, 0.5),  # 1.27 μm band
    ],
}


@dataclass(frozen=True)
class SpectralMatch:
    """A match between an observed feature and a molecular absorption band."""

    molecule: str
    hitran_id: int | None
    band_center_um: float
    band_width_um: float
    observed_center_um: float
    wavelength_offset_um: float
    relative_strength: float
    match_confidence: float  # [0, 1] based on wavelength match quality


def match_features(
    wavelengths_um: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray,
    target_molecules: list[str],
    snr_threshold: float = 2.0,
) -> list[SpectralMatch]:
    """Match observed spectral features against known molecular absorption bands.

    This is a preliminary identification step. Rigorous detection requires
    Bayesian model comparison (see bayesian.py).

    Args:
        wavelengths_um: Wavelength array in micrometers.
        flux: Observed flux (transmission spectrum).
        flux_err: Flux uncertainties.
        target_molecules: Molecules to search for.
        snr_threshold: Minimum SNR for a feature to be considered.

    Returns:
        List of spectral matches, sorted by confidence.
    """
    matches: list[SpectralMatch] = []

    # Find absorption features (dips in transmission spectrum)
    features = _find_absorption_features(wavelengths_um, flux, flux_err, snr_threshold)

    for mol in target_molecules:
        bands = MOLECULAR_BANDS.get(mol, [])
        hitran_id = HITRAN_MOLECULE_IDS.get(mol)

        for center, width, strength in bands:
            # Check if this band falls within our wavelength range
            if center < wavelengths_um.min() or center > wavelengths_um.max():
                continue

            # Find the closest observed feature
            for feat_center, _feat_depth, feat_snr in features:
                offset = abs(feat_center - center)
                # Match if within band width
                if offset <= width:
                    confidence = (1.0 - offset / width) * min(feat_snr / 5.0, 1.0) * strength
                    matches.append(
                        SpectralMatch(
                            molecule=mol,
                            hitran_id=hitran_id if hitran_id and hitran_id > 0 else None,
                            band_center_um=center,
                            band_width_um=width,
                            observed_center_um=feat_center,
                            wavelength_offset_um=offset,
                            relative_strength=strength,
                            match_confidence=min(confidence, 1.0),
                        )
                    )

    return sorted(matches, key=lambda m: m.match_confidence, reverse=True)


def _find_absorption_features(
    wavelengths: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray,
    snr_threshold: float,
) -> list[tuple[float, float, float]]:
    """Find significant absorption features in a transmission spectrum.

    Returns: [(center_wavelength, depth, snr), ...]
    """
    features: list[tuple[float, float, float]] = []

    if len(flux) < 5:
        return features

    # Smooth the spectrum to find broad features
    kernel_size = min(5, len(flux) // 2)
    if kernel_size < 3:
        return features

    smoothed = np.convolve(flux, np.ones(kernel_size) / kernel_size, mode="same")
    residuals = smoothed - flux  # positive = absorption dip

    # Find local maxima in residuals (absorption features)
    for i in range(1, len(residuals) - 1):
        if residuals[i] > residuals[i - 1] and residuals[i] > residuals[i + 1]:
            depth = residuals[i]
            err = flux_err[i] if flux_err[i] > 0 else 1e-10
            snr = depth / err

            if snr >= snr_threshold:
                features.append((float(wavelengths[i]), float(depth), float(snr)))

    return features
