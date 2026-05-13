"""JWST MAST (Mikulski Archive for Space Telescopes) client.

Fetches JWST transmission spectra via astroquery.mast.
Rate limit: 10 req/s (documented).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

logger = structlog.get_logger()

MAST_BASE_URL = "https://mast.stsci.edu/api/v0.1"


@dataclass(frozen=True)
class JWSTObservation:
    """Metadata for a JWST observation."""

    obs_id: str
    target_name: str
    instrument: str
    filters: str
    wavelength_min_um: float
    wavelength_max_um: float
    exposure_time_s: float
    date_obs: str
    proposal_id: str


async def search_jwst_observations(
    target_name: str,
    instrument: str | None = None,
    max_results: int = 50,
) -> list[JWSTObservation]:
    """Search MAST for JWST observations of a target.

    Args:
        target_name: Target name (e.g., "K2-18 b", "TRAPPIST-1 e").
        instrument: Optional instrument filter (e.g., "NIRSpec", "MIRI", "NIRISS").
        max_results: Maximum results to return.
    """
    try:
        from astroquery.mast import Observations

        # Search by target name, filtered to JWST
        obs_table = Observations.query_criteria(
            objectname=target_name,
            obs_collection="JWST",
            intentType="science",
        )

        if obs_table is None or len(obs_table) == 0:
            logger.info("mast_no_results", target=target_name)
            return []

        results: list[JWSTObservation] = []
        for row in obs_table[:max_results]:
            inst = str(row.get("instrument_name", ""))
            if instrument and instrument.lower() not in inst.lower():
                continue

            results.append(
                JWSTObservation(
                    obs_id=str(row.get("obs_id", "")),
                    target_name=str(row.get("target_name", target_name)),
                    instrument=inst,
                    filters=str(row.get("filters", "")),
                    wavelength_min_um=float(row.get("wavelength_min", 0)) / 10000,  # Å to μm
                    wavelength_max_um=float(row.get("wavelength_max", 0)) / 10000,
                    exposure_time_s=float(row.get("t_exptime", 0)),
                    date_obs=str(row.get("t_obs_release", "")),
                    proposal_id=str(row.get("proposal_id", "")),
                )
            )

        logger.info("mast_search_complete", target=target_name, results=len(results))
        return results

    except ImportError:
        logger.warning("astroquery_not_installed", msg="Install with pip install astroquery")
        return []
    except Exception as e:
        logger.warning("mast_search_failed", target=target_name, error=str(e))
        return []


async def download_spectrum(obs_id: str, output_dir: str = "/tmp") -> str | None:  # noqa: S108  # nosec B108 (test/dev fixture path; not a security boundary)
    """Download a JWST spectrum FITS file from MAST.

    Returns the local file path, or None on failure.
    """
    try:

        from astroquery.mast import Observations

        # Get data products for this observation
        products = Observations.get_product_list(obs_id)

        if products is None or len(products) == 0:
            logger.warning("mast_no_products", obs_id=obs_id)
            return None

        # Filter for spectrum products (x1d = extracted 1D spectra)
        spec_products = Observations.filter_products(
            products,
            productSubGroupDescription=["X1D", "X1DINTS", "S2D"],
        )

        if spec_products is None or len(spec_products) == 0:
            # Fall back to any FITS file
            spec_products = Observations.filter_products(
                products,
                extension="fits",
            )

        if spec_products is None or len(spec_products) == 0:
            return None

        # Download the first matching product
        manifest = Observations.download_products(
            spec_products[:1],
            download_dir=output_dir,
        )

        if manifest is not None and len(manifest) > 0:
            local_path = str(manifest["Local Path"][0])
            logger.info("mast_downloaded", obs_id=obs_id, path=local_path)
            return local_path

        return None

    except Exception as e:
        logger.warning("mast_download_failed", obs_id=obs_id, error=str(e))
        return None
