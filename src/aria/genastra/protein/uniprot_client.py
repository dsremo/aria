"""UniProt and AlphaFold EBI / ESM Atlas structure lookup.

Checks existing databases before running expensive GPU inference:
1. AlphaFold EBI DB (200M+ structures)
2. ESM Metagenomic Atlas (600M+ structures)
3. RCSB PDB (experimental structures)
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from aria.genastra.upstream.retry import resilient_request

logger = structlog.get_logger()


@dataclass(frozen=True)
class ExternalStructure:
    """A structure found in an external database."""

    source: str  # 'alphafold_ebi', 'esm_atlas', 'rcsb_pdb'
    uniprot_id: str
    pdb_url: str
    mean_plddt: float | None
    method: str | None  # 'predicted' or 'experimental'


async def lookup_alphafold_ebi(uniprot_id: str) -> ExternalStructure | None:
    """Look up a predicted structure in the AlphaFold EBI database.

    API: GET https://alphafold.ebi.ac.uk/api/prediction/{uniprot_id}
    No authentication required.
    """
    url = f"https://alphafold.ebi.ac.uk/api/prediction/{uniprot_id}"

    try:
        response = await resilient_request("alphafold_ebi", "GET", url, timeout_s=15.0)
        if response.status_code == 404:
            return None
        response.raise_for_status()

        data = response.json()
        entry = data[0] if isinstance(data, list) and len(data) > 0 else data

        pdb_url = entry.get("pdbUrl", "")
        mean_plddt = entry.get("globalMetricValue")

        return ExternalStructure(
            source="alphafold_ebi",
            uniprot_id=uniprot_id,
            pdb_url=pdb_url,
            mean_plddt=float(mean_plddt) if mean_plddt else None,
            method="predicted",
        )
    except Exception:
        logger.warning("alphafold_ebi_lookup_failed", uniprot_id=uniprot_id)
        return None


async def lookup_esm_atlas(uniprot_id: str) -> ExternalStructure | None:  # noqa: ARG001
    """Look up a structure in the ESM Metagenomic Atlas.

    DEPRECATED: The ESM Atlas API (api.esmatlas.com) returns 403 as of 2026-03.
    This function is kept for future re-enablement but currently always returns None.
    Use AlphaFold EBI instead.
    """
    # ESM Atlas API is dead (verified 2026-03-31, returns 403 Forbidden).
    # Do not waste time/bandwidth hitting a dead endpoint.
    logger.debug("esm_atlas_skipped", reason="API decommissioned (403), use AlphaFold EBI")
    return None


async def lookup_rcsb_pdb(uniprot_id: str) -> ExternalStructure | None:
    """Look up experimental structures in the RCSB PDB via UniProt mapping.

    API: https://data.rcsb.org/rest/v1/core/uniprot/{uniprot_id}
    """
    url = f"https://data.rcsb.org/rest/v1/core/uniprot/{uniprot_id}"

    try:
        response = await resilient_request("rcsb_pdb", "GET", url, timeout_s=15.0)
        if response.status_code == 404:
            return None
        response.raise_for_status()

        data = response.json()
        # Get first associated PDB entry
        pdb_ids = data.get("rcsb_uniprot_container_identifiers", {}).get("entry_ids", [])
        if not pdb_ids:
            return None

        pdb_id = pdb_ids[0]
        return ExternalStructure(
            source="rcsb_pdb",
            uniprot_id=uniprot_id,
            pdb_url=f"https://files.rcsb.org/download/{pdb_id}.pdb",
            mean_plddt=None,
            method="experimental",
        )
    except Exception:
        logger.warning("rcsb_pdb_lookup_failed", uniprot_id=uniprot_id)
        return None


async def lookup_structure(uniprot_id: str) -> ExternalStructure | None:
    """Try all external databases in order: AlphaFold EBI -> ESM Atlas -> RCSB PDB.

    Returns the first hit, preferring predicted (AlphaFold) then experimental.
    """
    # Try AlphaFold EBI first (most comprehensive for known proteins)
    result = await lookup_alphafold_ebi(uniprot_id)
    if result is not None:
        return result

    # Try ESM Atlas (metagenomic proteins)
    result = await lookup_esm_atlas(uniprot_id)
    if result is not None:
        return result

    # Try RCSB PDB (experimental structures)
    return await lookup_rcsb_pdb(uniprot_id)
