"""Minimal PDB/mmCIF parsing utilities.

We only need to extract metadata from PDB files — full parsing is done
by Mol* on the frontend and BioPython for deeper analysis.
"""

from __future__ import annotations

import io
from dataclasses import dataclass


@dataclass(frozen=True)
class PDBMetadata:
    """Basic metadata extracted from a PDB file."""

    num_atoms: int
    num_residues: int
    num_chains: int
    chain_ids: tuple[str, ...]
    resolution: float | None


def extract_pdb_metadata(pdb_string: str) -> PDBMetadata:
    """Extract basic metadata from a PDB-format string."""
    atoms = 0
    residues: set[tuple[str, int]] = set()
    chains: set[str] = set()
    resolution: float | None = None

    for line in io.StringIO(pdb_string):
        if line.startswith(("ATOM", "HETATM")):
            atoms += 1
            chain_id = line[21].strip()
            res_seq = int(line[22:26].strip())
            chains.add(chain_id)
            residues.add((chain_id, res_seq))

        elif line.startswith("REMARK   2 RESOLUTION."):
            try:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "RESOLUTION.":
                        resolution = float(parts[i + 1])
                        break
            except (IndexError, ValueError):
                pass

    return PDBMetadata(
        num_atoms=atoms,
        num_residues=len(residues),
        num_chains=len(chains),
        chain_ids=tuple(sorted(chains)),
        resolution=resolution,
    )


def sequence_from_pdb(pdb_string: str, chain: str = "A") -> str:
    """Extract the amino acid sequence from a PDB file for a given chain.

    Uses CA atoms to identify residues and their order.
    """
    three_to_one = {
        "ALA": "A", "CYS": "C", "ASP": "D", "GLU": "E", "PHE": "F",
        "GLY": "G", "HIS": "H", "ILE": "I", "LYS": "K", "LEU": "L",
        "MET": "M", "ASN": "N", "PRO": "P", "GLN": "Q", "ARG": "R",
        "SER": "S", "THR": "T", "VAL": "V", "TRP": "W", "TYR": "Y",
    }

    residues: dict[int, str] = {}
    for line in io.StringIO(pdb_string):
        if line.startswith("ATOM") and line[12:16].strip() == "CA":
            chain_id = line[21].strip()
            if chain_id == chain:
                res_name = line[17:20].strip()
                res_seq = int(line[22:26].strip())
                residues[res_seq] = three_to_one.get(res_name, "X")

    return "".join(residues[k] for k in sorted(residues))
