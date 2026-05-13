"""Real HITRAN cross-sections computed via HAPI (HITRAN Application Programming Interface).

BUILD-F7 (Blandford / Schwartz): "Molecular cross-sections from first principles.
Use real HITRAN line data instead of approximate Gaussian band models. The Voigt
profile with actual HITRAN line parameters is the gold standard for
line-by-line radiative transfer."

Uses:
  - HAPI (hitran-api) to read downloaded HITRAN .data + .header files
  - absorptionCoefficient_Voigt() for Voigt line profiles with actual
    HITRAN line parameters (intensity, air-broadening, self-broadening,
    temperature exponent, pressure shift)
  - Results cached in-memory for performance

Reference:
  Kochanov et al. (2016), "HITRAN Application Programming Interface (HAPI)",
  J. Quant. Spectrosc. Radiat. Transfer 177, 15-30.
  DOI: 10.1016/j.jqsrt.2016.03.005

MOLECULES AVAILABLE (downloaded to data/spectra/hitran_data/):
  H2O  (94,711 lines)
  CO2  (127,657 lines)
  O3   (169,155 lines)
  CH4  (221,660 lines)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import structlog

logger = structlog.get_logger()

# Path to the downloaded HITRAN data directory
_HITRAN_DIR: Path = (
    Path(__file__).parent.parent.parent.parent  # project root (GenomeAstrobiology/)
    / "data" / "spectra" / "hitran_data"
)

# Molecules available in the downloaded HITRAN data
AVAILABLE_MOLECULES: set[str] = {"H2O", "CO2", "O3", "CH4"}

# Cache for the HAPI table listing (populated on first use)
_hapi_initialized: bool = False


def _init_hapi() -> bool:
    """Initialize HAPI with the local HITRAN data directory.

    Returns True if HAPI and data are available, False otherwise.
    """
    global _hapi_initialized
    if _hapi_initialized:
        return True

    if not _HITRAN_DIR.exists():
        logger.warning("hitran_dir_not_found", path=str(_HITRAN_DIR))
        return False

    try:
        import hapi
        hapi.db_begin(str(_HITRAN_DIR))
        _hapi_initialized = True
        logger.info("hapi_initialized", hitran_dir=str(_HITRAN_DIR))
        return True
    except ImportError:
        logger.warning("hapi_not_installed", hint="pip install hitran-api")
        return False
    except Exception as e:
        logger.warning("hapi_init_failed", error=str(e))
        return False


def compute_cross_sections(
    molecule: str,
    wavelengths_um: np.ndarray,
    temperature_k: float = 296.0,
    pressure_bar: float = 1.0,
    wavenumber_step: float = 5.0,
) -> np.ndarray | None:
    """Compute absorption cross-sections for a molecule using real HITRAN line data.

    Uses the Voigt profile with actual HITRAN parameters:
      - Line center position (ν₀)
      - Line intensity at 296K (S₀)
      - Air-broadened Lorentzian half-width (γ_air)
      - Self-broadened half-width (γ_self)
      - Temperature dependence exponent (n)
      - Pressure shift coefficient (δ)

    The cross-section is integrated onto the requested wavelength grid.

    Args:
        molecule: Molecule name (e.g., "CH4", "H2O", "CO2", "O3").
        wavelengths_um: Wavelength grid in micrometers (must be monotonic).
        temperature_k: Atmospheric temperature in Kelvin.
        pressure_bar: Atmospheric pressure in bar (1 bar ≈ 1 atm).
        wavenumber_step: Resolution of internal wavenumber grid (cm⁻¹).
            Smaller values = more accurate but slower. Default 1.0 cm⁻¹
            gives adequate accuracy for broadband JWST observations.

    Returns:
        Cross-section array (cm² per molecule) on the wavelength_um grid,
        or None if HAPI/data is unavailable.
    """
    if molecule not in AVAILABLE_MOLECULES:
        logger.debug("hitran_molecule_not_available", molecule=molecule,
                     available=list(AVAILABLE_MOLECULES))
        return None

    if not _init_hapi():
        return None

    try:
        import hapi

        # Convert wavelength range to wavenumber range (cm⁻¹ = 10000/μm)
        wav_min = float(wavelengths_um.min())
        wav_max = float(wavelengths_um.max())

        # Wavenumber range (reversed: shorter wavelength = higher wavenumber)
        nu_min = 10000.0 / wav_max  # lower wavenumber
        nu_max = 10000.0 / wav_min  # higher wavenumber

        # Add buffer for line wings
        buffer = 5.0  # ESTIMATE — 5 cm⁻¹ wing buffer (Rothman 2013 JQSRT 130 4: standard HITRAN wing cutoff)
        nu_min_buf = max(nu_min - buffer, 1.0)
        nu_max_buf = nu_max + buffer

        # Compute absorption coefficient [cm⁻¹] via Voigt profile
        # HAPI absorptionCoefficient_Voigt returns (nu_grid, absorption_coeff)
        # where absorption_coeff is in cm⁻¹ at the given number density (1 molec/cm³)
        nu_grid, alpha = hapi.absorptionCoefficient_Voigt(
            SourceTables=molecule,
            Environment={"T": float(temperature_k), "p": float(pressure_bar)},
            WavenumberRange=[nu_min_buf, nu_max_buf],
            WavenumberStep=float(wavenumber_step),
            HITRAN_units=True,  # output in cm⁻¹/(molec/cm²)
        )

        # Convert wavenumber grid to wavelength grid (μm)
        wav_grid_um = 10000.0 / nu_grid  # reverse order: nu high → wav low

        # Reverse arrays so wavelengths are monotonically increasing
        wav_grid_um = wav_grid_um[::-1]
        alpha = alpha[::-1]

        # Clip to requested wavelength range
        mask = (wav_grid_um >= wav_min) & (wav_grid_um <= wav_max)
        if not np.any(mask):
            logger.debug("no_lines_in_range", molecule=molecule,
                         wav_min=wav_min, wav_max=wav_max, nu_min=nu_min, nu_max=nu_max)
            return np.zeros_like(wavelengths_um)

        wav_in_range = wav_grid_um[mask]
        alpha_in_range = alpha[mask]

        # Interpolate to the requested wavelength grid
        cross_sections = np.interp(wavelengths_um, wav_in_range, alpha_in_range,
                                   left=0.0, right=0.0)

        logger.debug(
            "hitran_cross_sections_computed",
            molecule=molecule,
            temperature_k=temperature_k,
            pressure_bar=pressure_bar,
            wavelength_range_um=f"{wav_min:.2f}-{wav_max:.2f}",
            max_cross_section=float(cross_sections.max()),
            n_lines_in_range=int(np.sum(mask)),
        )

        return cross_sections

    except Exception as e:
        logger.warning("hitran_cross_section_failed", molecule=molecule, error=str(e))
        return None


@lru_cache(maxsize=256)
def _cached_cross_sections(
    molecule: str,
    wav_min: float,
    wav_max: float,
    n_points: int,
    temperature_k: float,
    pressure_bar: float,
) -> np.ndarray | None:
    """LRU-cached version for performance during nested sampling (many evaluations).

    Caches on (molecule, wavelength grid shape, T, P) — adequate for Bayesian
    inference where T and P are sampled on a discrete grid.
    """
    wavelengths = np.linspace(wav_min, wav_max, n_points)
    return compute_cross_sections(molecule, wavelengths, temperature_k, pressure_bar)


def get_cross_sections_cached(
    molecule: str,
    wavelengths_um: np.ndarray,
    temperature_k: float = 296.0,
    pressure_bar: float = 1.0,
    temperature_grid_k: np.ndarray | None = None,
    pressure_grid_bar: np.ndarray | None = None,
) -> np.ndarray | None:
    """Cross-sections with cache, snapping T/P to a coarse grid for LRU efficiency.

    During nested sampling, temperature and pressure vary continuously. This
    function snaps them to a coarse grid (50K steps in T, factors of 3 in P)
    so the LRU cache is effective.

    Args:
        molecule: Molecule name.
        wavelengths_um: Wavelength grid.
        temperature_k: Temperature. Snapped to nearest 50K.
        pressure_bar: Pressure. Snapped to nearest factor of √10.
        temperature_grid_k: Optional custom temperature grid for snapping.
        pressure_grid_bar: Optional custom pressure grid for snapping.

    Returns:
        Cross-section array (cm² per molecule), or None.
    """
    # Snap temperature to coarse grid (50K steps)
    if temperature_grid_k is not None:
        t_snapped = float(temperature_grid_k[
            np.argmin(np.abs(temperature_grid_k - temperature_k))
        ])
    else:
        t_snapped = round(temperature_k / 50.0) * 50.0

    # Snap pressure to coarse log grid (√10 ≈ 3.16 steps)
    if pressure_grid_bar is not None:
        p_snapped = float(pressure_grid_bar[
            np.argmin(np.abs(np.log10(pressure_grid_bar) - np.log10(pressure_bar)))
        ])
    else:
        log_p_snapped = round(np.log10(pressure_bar) / 0.5) * 0.5
        p_snapped = 10.0**log_p_snapped

    return _cached_cross_sections(
        molecule,
        float(wavelengths_um.min()),
        float(wavelengths_um.max()),
        len(wavelengths_um),
        t_snapped,
        p_snapped,
    )


def list_available_bands(
    molecule: str,
    wavelength_min_um: float = 0.5,
    wavelength_max_um: float = 20.0,
    temperature_k: float = 296.0,
    pressure_bar: float = 0.01,
    min_cross_section: float = 1e-24,
) -> list[dict[str, float]]:
    """Find significant absorption bands for a molecule in the JWST wavelength range.

    Computes cross-sections and identifies local maxima (band centers) with
    cross-section above the threshold. Useful for generating molecular band
    tables from actual HITRAN data.

    Args:
        molecule: Molecule name.
        wavelength_min_um: Minimum wavelength.
        wavelength_max_um: Maximum wavelength.
        temperature_k: Temperature for cross-section computation.
        pressure_bar: Pressure (low pressure = narrow lines = better peak resolution).
        min_cross_section: Minimum peak cross-section to report a band.

    Returns:
        List of dicts with 'center_um', 'width_um', 'peak_cross_section'.
    """
    n_points = int((wavelength_max_um - wavelength_min_um) / 0.01) + 1
    n_points = min(n_points, 5000)  # cap for performance
    wavelengths = np.linspace(wavelength_min_um, wavelength_max_um, n_points)
    xsec = compute_cross_sections(molecule, wavelengths, temperature_k, pressure_bar)

    if xsec is None or xsec.max() == 0:
        return []

    # Smooth over ~0.1 μm to find broad band features
    window = max(int(n_points * 0.1 / (wavelength_max_um - wavelength_min_um)), 3)
    from numpy import convolve, ones
    smooth = convolve(xsec, ones(window) / window, mode="same")

    # Find local maxima
    bands = []
    for i in range(1, len(smooth) - 1):
        if smooth[i] > smooth[i - 1] and smooth[i] > smooth[i + 1] and smooth[i] >= min_cross_section:
            # Estimate band width (half-max width)
            half_max = smooth[i] / 2.0
            left = i
            while left > 0 and smooth[left] > half_max:
                left -= 1
            right = i
            while right < len(smooth) - 1 and smooth[right] > half_max:
                right += 1
            width_um = wavelengths[right] - wavelengths[left]
            bands.append({
                "center_um": float(wavelengths[i]),
                "width_um": float(max(width_um, 0.01)),
                "peak_cross_section": float(smooth[i]),
            })

    return bands
