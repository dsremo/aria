"""FITS file reader for JWST spectral data.

P0-v2-2 FIX: The system had NO FITS parsing — could not read real JWST data.

JWST transmission spectra come as FITS files with:
- Stage 3 products: x1dints (integrated time-series 1D spectra)
- Wavelength in the WCS or a dedicated WAVELENGTH column
- Flux and flux error columns
- Multiple integrations per transit observation
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import structlog

logger = structlog.get_logger()


@dataclass(frozen=True)
class SpectralData:
    """Parsed spectral data from a FITS file."""

    wavelength_um: np.ndarray  # μm
    flux: np.ndarray  # transit depth or normalized flux
    flux_err: np.ndarray  # 1σ uncertainty
    instrument: str
    target: str
    obs_id: str
    n_integrations: int
    header_metadata: dict


def read_jwst_spectrum(filepath: str | Path) -> SpectralData:
    """Read a JWST spectral FITS file (x1d or x1dints product).

    Handles NIRSpec, NIRISS, and MIRI instrument formats.

    Args:
        filepath: Path to FITS file.

    Returns:
        SpectralData with wavelength, flux, and uncertainties.

    Raises:
        ImportError: If astropy is not installed.
        ValueError: If the FITS file format is not recognized.
    """
    try:
        from astropy.io import fits
    except ImportError as err:
        raise ImportError(
            "astropy is required for FITS file reading. "
            "Install with: pip install astropy"
        ) from err

    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"FITS file not found: {filepath}")

    with fits.open(filepath) as hdul:
        # Extract primary header metadata
        primary_hdr = hdul[0].header
        instrument = primary_hdr.get("INSTRUME", "UNKNOWN")
        target = primary_hdr.get("TARGNAME", primary_hdr.get("TARGPROP", "UNKNOWN"))
        obs_id = primary_hdr.get("OBS_ID", primary_hdr.get("FILENAME", ""))

        # Find the science data extension
        sci_ext = _find_science_extension(hdul)
        if sci_ext is None:
            raise ValueError(
                f"No recognized science extension in {filepath.name}. "
                f"Extensions: {[h.name for h in hdul]}"
            )

        data = hdul[sci_ext].data
        ext_hdr = hdul[sci_ext].header

        # Extract wavelength
        wavelength_um = _extract_wavelength(data, ext_hdr)

        # Extract flux and error
        flux, flux_err = _extract_flux(data)

        # Handle multi-integration data (x1dints)
        n_integrations = 1
        if flux.ndim > 1:
            n_integrations = flux.shape[0]
            # Average over integrations, propagate errors
            flux_err = np.sqrt(np.sum(flux_err**2, axis=0)) / n_integrations
            flux = np.mean(flux, axis=0)

        # Filter out NaN and invalid values
        valid = np.isfinite(flux) & np.isfinite(flux_err) & (flux_err > 0)
        wavelength_um = wavelength_um[valid]
        flux = flux[valid]
        flux_err = flux_err[valid]

        # Sort by wavelength
        sort_idx = np.argsort(wavelength_um)
        wavelength_um = wavelength_um[sort_idx]
        flux = flux[sort_idx]
        flux_err = flux_err[sort_idx]

        header_metadata = {
            "instrument": instrument,
            "filter": primary_hdr.get("FILTER", ""),
            "grating": primary_hdr.get("GRATING", ""),
            "program": primary_hdr.get("PROGRAM", primary_hdr.get("TITLE", "")),
            "date_obs": primary_hdr.get("DATE-OBS", ""),
            "exposure_time": primary_hdr.get("EFFEXPTM", primary_hdr.get("EXPTIME", 0)),
        }

        logger.info(
            "fits_read",
            file=filepath.name,
            instrument=instrument,
            target=target,
            n_wavelengths=len(wavelength_um),
            wl_range_um=(float(wavelength_um.min()), float(wavelength_um.max())),
            n_integrations=n_integrations,
        )

        return SpectralData(
            wavelength_um=wavelength_um,
            flux=flux,
            flux_err=flux_err,
            instrument=instrument,
            target=target,
            obs_id=obs_id,
            n_integrations=n_integrations,
            header_metadata=header_metadata,
        )


def _find_science_extension(hdul) -> int | None:
    """Find the science data extension in a JWST FITS file."""
    # Try known extension names in order of preference
    for name in ["EXTRACT1D", "SCI", "DATA", "SPEC"]:
        for i, hdu in enumerate(hdul):
            if hdu.name == name and hdu.data is not None:
                return i

    # Fall back to first extension with table data
    for i, hdu in enumerate(hdul):
        if i > 0 and hdu.data is not None:
            return i

    return None


def _extract_wavelength(data, header) -> np.ndarray:
    """Extract wavelength array from FITS data or WCS."""
    # Try column names (most common for x1d/x1dints)
    for col in ["WAVELENGTH", "wavelength", "WAVE", "wave", "LAMBDA"]:
        if hasattr(data, "columns") and col in data.columns.names:
            wl = np.array(data[col]).flatten()
            # Check units — JWST uses micrometers by default
            if wl.max() > 100:  # likely in Angstroms
                wl = wl / 10000.0
            elif wl.max() > 10:  # likely in nanometers
                wl = wl / 1000.0
            return wl

    # Try WCS (for 2D spectral images)
    try:
        from astropy.wcs import WCS
        wcs = WCS(header)
        n_pix = header.get("NAXIS1", data.shape[-1] if hasattr(data, "shape") else 100)
        pixel_coords = np.arange(n_pix)
        wavelength = wcs.pixel_to_world(pixel_coords)
        if hasattr(wavelength, "to"):
            import astropy.units as u
            return wavelength.to(u.um).value
        return np.array(wavelength)
    except Exception:  # noqa: S110, BLE001
        pass

    raise ValueError("Cannot extract wavelength from FITS file — no WAVELENGTH column or WCS")


def _extract_flux(data) -> tuple[np.ndarray, np.ndarray]:
    """Extract flux and flux error from FITS table data."""
    flux = None
    flux_err = None

    # Try column names
    for col in ["FLUX", "flux", "SPEC", "DATA", "COUNTS"]:
        if hasattr(data, "columns") and col in data.columns.names:
            flux = np.array(data[col], dtype=np.float64)
            break

    for col in ["FLUX_ERROR", "ERROR", "ERR", "flux_error", "UNCERTAINTY", "DQ"]:
        if hasattr(data, "columns") and col in data.columns.names:
            flux_err = np.array(data[col], dtype=np.float64)
            break

    if flux is None:
        raise ValueError("Cannot find flux column in FITS data")

    if flux_err is None:
        # Estimate error from flux scatter (last resort)
        flux_err = np.full_like(flux, np.nanstd(flux) * 0.1)
        logger.warning("fits_no_error_column", msg="Estimating flux error from scatter")

    return flux, flux_err


def bin_spectrum(
    wavelength_um: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray,
    target_resolution: int = 100,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bin a spectrum to a target spectral resolution.

    P2-v2-3 from critique: Raw JWST spectra have R=2700 but molecular
    features are broad. Binning to R~100 reduces correlated noise and
    computation time.

    Args:
        wavelength_um: Input wavelengths.
        flux: Input flux.
        flux_err: Input flux errors.
        target_resolution: Target R = λ/Δλ.

    Returns:
        (binned_wavelengths, binned_flux, binned_flux_err)
    """
    wl_min, wl_max = wavelength_um.min(), wavelength_um.max()

    # Generate bin edges at constant R
    bin_edges = [wl_min]
    while bin_edges[-1] < wl_max:
        bin_edges.append(bin_edges[-1] * (1 + 1.0 / target_resolution))
    bin_edges = np.array(bin_edges)

    n_bins = len(bin_edges) - 1
    binned_wl = np.zeros(n_bins)
    binned_flux = np.zeros(n_bins)
    binned_err = np.zeros(n_bins)

    for i in range(n_bins):
        mask = (wavelength_um >= bin_edges[i]) & (wavelength_um < bin_edges[i + 1])
        if np.any(mask):
            weights = 1.0 / flux_err[mask]**2
            binned_wl[i] = np.average(wavelength_um[mask], weights=weights)
            binned_flux[i] = np.average(flux[mask], weights=weights)
            binned_err[i] = 1.0 / np.sqrt(np.sum(weights))
        else:
            binned_wl[i] = (bin_edges[i] + bin_edges[i + 1]) / 2
            binned_flux[i] = np.nan
            binned_err[i] = np.nan

    # Remove empty bins
    valid = np.isfinite(binned_flux)
    return binned_wl[valid], binned_flux[valid], binned_err[valid]
