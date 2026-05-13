"""FASTA file parsing for protein sequence upload.

Panel 12 (Giardini, ESA): "You support exactly ZERO real data formats.
The most common protein input format is FASTA, not JSON body."
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from aria.genastra.core.constants import MAX_BULK_SEQUENCES, MAX_SEQUENCE_LENGTH, VALID_AMINO_ACIDS_EXTENDED


@dataclass(frozen=True)
class FastaEntry:
    """A single entry from a FASTA file."""

    header: str  # full header line (after >)
    accession: str  # first word of header (UniProt ID, gene name, etc.)
    description: str  # rest of header
    sequence: str


class FastaParseError(Exception):
    """Error parsing FASTA file."""


def parse_fasta(content: str | bytes, max_entries: int = MAX_BULK_SEQUENCES) -> list[FastaEntry]:
    """Parse a FASTA-format string or bytes into sequence entries.

    Handles:
    - Standard single-sequence FASTA
    - Multi-sequence FASTA (up to max_entries)
    - UniProt-style headers (>sp|P04637|P53_HUMAN Cellular tumor antigen p53)
    - NCBI-style headers (>gi|12345|ref|NP_000537.3| cellular tumor antigen p53)
    - Simple headers (>my_protein)

    Validates:
    - Sequences contain only valid amino acid characters
    - No sequence exceeds MAX_SEQUENCE_LENGTH
    - At least one entry exists

    Raises:
        FastaParseError: On invalid FASTA format or validation failure.
    """
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")

    content = content.strip()
    if not content:
        raise FastaParseError("Empty FASTA input")

    # Handle case where user pastes raw sequence without header
    if not content.startswith(">"):
        seq = content.replace("\n", "").replace("\r", "").replace(" ", "").upper()
        invalid = set(seq) - VALID_AMINO_ACIDS_EXTENDED
        if invalid and len(invalid) < 5:
            raise FastaParseError(f"Invalid amino acid characters: {invalid}")
        if invalid:
            raise FastaParseError("Input doesn't look like FASTA (no '>' header) or a protein sequence")
        return [FastaEntry(header="unnamed", accession="unnamed", description="", sequence=seq)]

    entries: list[FastaEntry] = []
    current_header: str | None = None
    current_seq_parts: list[str] = []

    for line in io.StringIO(content):
        line = line.rstrip("\n\r")

        if line.startswith(">"):
            # Save previous entry
            if current_header is not None:
                seq = "".join(current_seq_parts).upper()
                if seq:
                    entries.append(_make_entry(current_header, seq))

            current_header = line[1:].strip()
            current_seq_parts = []

            if len(entries) >= max_entries:
                break
        else:
            # Sequence line — strip whitespace and numbers (some formats include residue numbers)
            cleaned = "".join(c for c in line if c.isalpha())
            if cleaned:
                current_seq_parts.append(cleaned)

    # Save last entry
    if current_header is not None:
        seq = "".join(current_seq_parts).upper()
        if seq:
            entries.append(_make_entry(current_header, seq))

    if not entries:
        raise FastaParseError("No valid sequences found in FASTA input")

    # Validate sequences
    for entry in entries:
        if len(entry.sequence) > MAX_SEQUENCE_LENGTH:
            raise FastaParseError(
                f"Sequence '{entry.accession}' has {len(entry.sequence)} residues, "
                f"exceeding the maximum of {MAX_SEQUENCE_LENGTH} "
                f"(ESMFold OOM limit on A10G 24GB)"
            )
        invalid = set(entry.sequence) - VALID_AMINO_ACIDS_EXTENDED
        if invalid:
            raise FastaParseError(
                f"Sequence '{entry.accession}' contains invalid characters: {invalid}"
            )

    return entries


def _make_entry(header: str, sequence: str) -> FastaEntry:
    """Create a FastaEntry from header and sequence."""
    # Parse accession from header
    # UniProt: >sp|P04637|P53_HUMAN Description
    # NCBI: >gi|12345|ref|NP_000537.3| Description
    # Simple: >my_protein Description here
    parts = header.split(None, 1)
    first_word = parts[0] if parts else header

    # Try UniProt-style pipe-separated
    if "|" in first_word:
        pipe_parts = first_word.split("|")
        accession = pipe_parts[1] if len(pipe_parts) >= 2 else first_word
    else:
        accession = first_word

    description = parts[1] if len(parts) > 1 else ""

    return FastaEntry(
        header=header,
        accession=accession,
        description=description,
        sequence=sequence,
    )
