"""NASA OSDR / GeneLab API client.

API base: https://visualization.osdr.nasa.gov/biodata/api/
Authentication: Free account registration (public data).
Data types: RNA-seq, DNA methylation, proteomics, metabolomics from ISS/shuttle.

The new OSDR Biological Data API (Jan 2026) replaces the old GLOpenAPI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from aria.genastra.upstream.retry import resilient_request

logger = structlog.get_logger()

OSDR_BASE_URL = "https://visualization.osdr.nasa.gov/biodata/api"
OSDR_REPO_URL = "https://osdr.nasa.gov/bio/repo"


@dataclass(frozen=True)
class GenelabDataset:
    """Metadata for a GeneLab/OSDR dataset."""

    accession: str  # e.g. "OSD-37", "GLDS-194"
    title: str
    organism: str
    platform: str  # e.g. "RNA-seq", "microarray"
    sample_count: int
    factors: list[str]
    description: str
    source_url: str


async def search_datasets(
    organism: str | None = None,
    tissue_type: str | None = None,
    assay_type: str | None = None,
    max_results: int = 50,
) -> list[GenelabDataset]:
    """Search OSDR for datasets matching criteria.

    Args:
        organism: e.g. "Mus musculus", "Homo sapiens", "Arabidopsis thaliana"
        tissue_type: e.g. "muscle", "liver", "blood"
        assay_type: e.g. "RNA-seq", "microarray"
        max_results: Maximum number of results.

    Returns:
        List of matching datasets.
    """
    params: dict[str, str] = {}
    if organism:
        params["organism"] = organism
    if tissue_type:
        params["tissue_type"] = tissue_type
    if assay_type:
        params["assay_type"] = assay_type

    url = f"{OSDR_BASE_URL}/"
    response = await resilient_request("nasa_osdr", "GET", url, params=params, timeout_s=30.0)
    response.raise_for_status()
    data = response.json()

    datasets: list[GenelabDataset] = []
    results = data if isinstance(data, list) else data.get("results", [])

    for entry in results[:max_results]:
        datasets.append(
            GenelabDataset(
                accession=entry.get("accession", entry.get("osd_accession", "")),
                title=entry.get("title", ""),
                organism=entry.get("organism", ""),
                platform=entry.get("assay_type", entry.get("platform", "")),
                sample_count=entry.get("sample_count", 0),
                factors=entry.get("factors", []),
                description=entry.get("description", ""),
                source_url=f"{OSDR_REPO_URL}/data/{entry.get('accession', '')}",
            )
        )

    logger.info("genelab_search", count=len(datasets), organism=organism)
    return datasets


async def fetch_dataset_metadata(accession: str) -> GenelabDataset | None:
    """Fetch metadata for a specific OSDR dataset.

    Args:
        accession: Dataset accession (e.g. "OSD-37", "GLDS-194").
    """
    url = f"{OSDR_BASE_URL}/{accession}/"

    try:
        response = await resilient_request("nasa_osdr", "GET", url, timeout_s=30.0)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        entry = response.json()

        return GenelabDataset(
            accession=accession,
            title=entry.get("title", ""),
            organism=entry.get("organism", ""),
            platform=entry.get("assay_type", ""),
            sample_count=entry.get("sample_count", 0),
            factors=entry.get("factors", []),
            description=entry.get("description", ""),
            source_url=f"{OSDR_REPO_URL}/data/{accession}",
        )
    except Exception:
        logger.warning("genelab_fetch_failed", accession=accession)
        return None


async def fetch_expression_data(accession: str) -> dict[str, Any] | None:
    """Fetch raw expression data (count matrix) for a dataset.

    Returns the raw JSON/tabular data from OSDR that needs to be parsed
    by the ETL module into a proper count matrix.
    """
    url = f"{OSDR_BASE_URL}/{accession}/expression/"

    try:
        response = await resilient_request("nasa_osdr", "GET", url, timeout_s=60.0)
        if response.status_code == 404:
            logger.warning("genelab_expression_not_found", accession=accession)
            return None
        response.raise_for_status()
        return response.json()
    except Exception:
        logger.warning("genelab_expression_fetch_failed", accession=accession)
        return None
