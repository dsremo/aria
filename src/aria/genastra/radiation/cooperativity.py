"""Contact-map cooperativity model for radiation damage.

BUILD-F18 (Onuchic): "Protein folding is COOPERATIVE. Damaging 3 nearby
residues in a folding nucleus is catastrophic; damaging 3 distant surface
residues is negligible."

Uses the protein's contact map (from predicted structure) to amplify
vulnerability at densely-connected folding nuclei.
"""

from __future__ import annotations

import io

import numpy as np
import structlog

logger = structlog.get_logger()


def compute_contact_map(
    pdb_string: str,
    distance_cutoff_angstrom: float = 8.0,  # Vendruscolo 2002 J Mol Biol 319 1209: 8 Å Cα-Cα standard contact threshold
) -> np.ndarray:
    """Compute residue-residue contact map from PDB structure.

    Two residues are "in contact" if their Cα atoms are within
    the distance cutoff. Default 8 Å captures both direct contacts
    and next-shell interactions.

    Args:
        pdb_string: PDB format string.
        distance_cutoff_angstrom: Cα-Cα distance threshold.

    Returns:
        Boolean contact map (N×N) where N = number of residues.
    """
    # Extract Cα coordinates
    ca_coords: list[tuple[float, float, float]] = []
    for line in io.StringIO(pdb_string):
        if line.startswith("ATOM") and line[12:16].strip() == "CA":
            x = float(line[30:38])
            y = float(line[38:46])
            z = float(line[46:54])
            ca_coords.append((x, y, z))

    n = len(ca_coords)
    if n == 0:
        return np.zeros((0, 0), dtype=bool)

    coords = np.array(ca_coords)

    # Pairwise distance matrix
    diff = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
    dist = np.sqrt(np.sum(diff**2, axis=2))

    # Contact map (exclude self-contacts and sequential neighbors ±1)
    contact_map = dist < distance_cutoff_angstrom
    for i in range(n):
        contact_map[i, i] = False
        if i > 0:
            contact_map[i, i - 1] = False
        if i < n - 1:
            contact_map[i, i + 1] = False

    return contact_map


def cooperative_damage_score(
    vulnerability_scores: np.ndarray,
    contact_map: np.ndarray,
    cooperativity_weight: float = 0.3,  # ESTIMATE — 0.3 neighbor weight; Onuchic & Wolynes 2004 Curr Opin Struct Biol 14 70: folding nucleus cooperativity
) -> np.ndarray:
    """Amplify vulnerability at densely-connected damaged regions.

    For each residue i, the cooperative score is:

        v_coop(i) = v(i) + w × Σⱼ contact(i,j) × v(j) / n_contacts(i)

    This means: if residue i is vulnerable AND its structural neighbors
    are also vulnerable, the effective damage at i is amplified.

    A folding nucleus (8-12 residues densely connected in 3D) with
    multiple radiation-sensitive amino acids becomes a critical failure point.

    Args:
        vulnerability_scores: Per-residue vulnerability [0, 1].
        contact_map: Boolean contact map (N×N).
        cooperativity_weight: How much neighbor damage amplifies (0-1).

    Returns:
        Cooperativity-adjusted vulnerability scores.
    """
    n = len(vulnerability_scores)
    if n == 0 or contact_map.shape[0] != n:
        return vulnerability_scores.copy()

    # Number of contacts per residue
    n_contacts = contact_map.sum(axis=1).astype(float)
    n_contacts[n_contacts == 0] = 1.0  # avoid division by zero

    # Mean vulnerability of structural neighbors
    neighbor_vuln = contact_map.astype(float) @ vulnerability_scores / n_contacts

    # Cooperative score: own vulnerability + weighted neighbor vulnerability
    coop_scores = vulnerability_scores + cooperativity_weight * neighbor_vuln

    return np.clip(coop_scores, 0.0, 1.0)


def identify_folding_nuclei(
    contact_map: np.ndarray,
    min_contacts: int = 6,  # ESTIMATE — ≥6 contacts in a 5-residue window defines nucleus (Shakhnovich 1994 Phys Rev Lett 72 3907)
    window: int = 5,         # ESTIMATE — 5-residue sliding window (Shakhnovich 1994; Abkevich 1994 Biochemistry 33 10026)
) -> list[tuple[int, int, int]]:
    """Identify putative folding nuclei from the contact map.

    Folding nuclei are clusters of residues with high contact density
    in 3D space. Radiation damage to a folding nucleus is especially
    devastating because it can prevent the protein from folding entirely.

    Returns: List of (start_residue, end_residue, n_internal_contacts)
    """
    n = contact_map.shape[0]
    nuclei: list[tuple[int, int, int]] = []

    for start in range(n - window):
        region = contact_map[start:start + window, start:start + window]
        # Count non-sequential contacts within this region
        internal_contacts = 0
        for i in range(window):
            for j in range(i + 2, window):  # skip sequential neighbors
                if region[i, j]:
                    internal_contacts += 1

        if internal_contacts >= min_contacts:
            nuclei.append((start, start + window - 1, internal_contacts))

    # Merge overlapping nuclei
    if not nuclei:
        return nuclei

    merged: list[tuple[int, int, int]] = [nuclei[0]]
    for start, end, contacts in nuclei[1:]:
        if start <= merged[-1][1]:
            # Overlapping — merge
            merged[-1] = (merged[-1][0], max(merged[-1][1], end), max(merged[-1][2], contacts))
        else:
            merged.append((start, end, contacts))

    return merged
