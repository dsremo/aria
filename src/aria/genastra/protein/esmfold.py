"""ESMFold inference wrapper.

Runs in the GPU worker process ONLY — never in the API process.
ESMFold is O(L²) in both time and memory. A10G (24GB) handles up to ~2000 residues.

Model: ESMFold v1 from Meta (MIT license, commercial-OK).
Load: torch.hub.load("facebookresearch/esm:main", "esmfold_v1")
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass

import structlog

from aria.genastra.core.constants import MAX_SEQUENCE_LENGTH, VALID_AMINO_ACIDS_EXTENDED
from aria.genastra.core.exceptions import InvalidSequenceError, SequenceTooLongError

logger = structlog.get_logger()


@dataclass(frozen=True)
class FoldingResult:
    """Result of ESMFold structure prediction."""

    pdb_string: str
    mean_plddt: float
    per_residue_plddt: tuple[float, ...]
    ptm_score: float | None
    pae_matrix: tuple[tuple[float, ...], ...] | None  # Predicted Aligned Error (LxL)
    inference_time_ms: int
    sequence_length: int
    model_name: str = "esmfold_v1"
    model_version: str = "1.0.0"


class ESMFoldEngine:
    """Manages ESMFold model lifecycle and inference.

    The model is loaded lazily on first call. This class should exist
    once per GPU worker process — never in the API process.
    """

    def __init__(self) -> None:
        self._model = None
        self._device: str = "cpu"

    def load_model(self, device: str = "cuda") -> None:
        """Load the ESMFold model onto the specified device.

        This takes 30-60 seconds and ~8 GB GPU RAM.
        """
        import torch

        logger.info("esmfold_loading", device=device)
        start = time.monotonic()

        self._model = torch.hub.load("facebookresearch/esm:main", "esmfold_v1")
        self._model = self._model.eval()

        if device == "cuda" and torch.cuda.is_available():
            self._model = self._model.to(device)
            self._device = "cuda"
        else:
            self._device = "cpu"
            if device == "cuda":
                logger.warning("esmfold_cuda_unavailable", msg="Falling back to CPU")

        elapsed = time.monotonic() - start
        logger.info("esmfold_loaded", device=self._device, elapsed_s=round(elapsed, 1))

    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._model is not None

    def predict(self, sequence: str) -> FoldingResult:
        """Run ESMFold structure prediction on a protein sequence.

        Args:
            sequence: Amino acid sequence (uppercase, standard 20 + extended).

        Returns:
            FoldingResult with PDB string, pLDDT scores, and timing.

        Raises:
            SequenceTooLongError: Sequence > MAX_SEQUENCE_LENGTH.
            InvalidSequenceError: Invalid characters in sequence.
            RuntimeError: Model not loaded.
        """
        import torch

        if self._model is None:
            raise RuntimeError("ESMFold model not loaded. Call load_model() first.")

        # Validate
        sequence = sequence.upper().strip()
        if len(sequence) > MAX_SEQUENCE_LENGTH:
            raise SequenceTooLongError(len(sequence), MAX_SEQUENCE_LENGTH)

        invalid = set(sequence) - VALID_AMINO_ACIDS_EXTENDED
        if invalid:
            raise InvalidSequenceError(invalid)

        logger.info("esmfold_predict_start", seq_length=len(sequence))
        start = time.monotonic()

        # CRITICAL: Single inference call — extracts PDB + pTM + PAE all at once.
        # Previous code called infer_pdb() then infer() = 2x GPU time (P0-5 fix).
        with torch.no_grad():
            output = self._model.infer(sequence)

        # Convert output to PDB string
        # ESMFold output has .positions (atom coordinates) that we convert via
        # the model's output_to_pdb helper, or we use the raw atom37 positions.
        pdb_string = self._output_to_pdb(output, sequence)

        # Extract pLDDT — stored in output.plddt (per-residue, [1, L] tensor)
        per_residue_plddt: list[float] = []
        if hasattr(output, "plddt") and output.plddt is not None:
            plddt_tensor = output.plddt.squeeze()  # [L]
            per_residue_plddt = [float(v) * 100.0 for v in plddt_tensor.cpu()]
        else:
            # Fallback: extract from PDB B-factor column
            per_residue_plddt = self._extract_plddt_from_pdb(pdb_string)

        mean_plddt = sum(per_residue_plddt) / len(per_residue_plddt) if per_residue_plddt else 0.0

        # Extract pTM score (predicted TM-score, global fold quality)
        ptm_score: float | None = None
        if hasattr(output, "ptm") and output.ptm is not None:
            ptm_score = float(output.ptm)

        # Extract PAE matrix (Predicted Aligned Error, LxL)
        # Critical for multi-domain proteins — identifies uncertain domain orientations
        pae_matrix: tuple[tuple[float, ...], ...] | None = None
        if hasattr(output, "predicted_aligned_error") and output.predicted_aligned_error is not None:
            pae_tensor = output.predicted_aligned_error.squeeze().cpu()
            pae_matrix = tuple(
                tuple(float(v) for v in row) for row in pae_tensor
            )
        elif hasattr(output, "pae") and output.pae is not None:
            pae_tensor = output.pae.squeeze().cpu()
            pae_matrix = tuple(
                tuple(float(v) for v in row) for row in pae_tensor
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "esmfold_predict_done",
            seq_length=len(sequence),
            mean_plddt=round(mean_plddt, 1),
            ptm=round(ptm_score, 3) if ptm_score else None,
            has_pae=pae_matrix is not None,
            elapsed_ms=elapsed_ms,
        )

        return FoldingResult(
            pdb_string=pdb_string,
            mean_plddt=mean_plddt,
            per_residue_plddt=tuple(per_residue_plddt),
            ptm_score=ptm_score,
            pae_matrix=pae_matrix,
            inference_time_ms=elapsed_ms,
            sequence_length=len(sequence),
        )

    def _output_to_pdb(self, output: object, sequence: str) -> str:
        """Convert ESMFold raw output to PDB string.

        Tries multiple approaches since the ESM API has changed across versions:
        1. output_to_pdb() method on the model (ESMFold v1 standard)
        2. Direct atom37 coordinate extraction with manual PDB formatting
        3. Fallback to infer_pdb() if nothing else works
        """
        import torch

        # Method 1: Use the model's built-in converter
        if hasattr(self._model, "output_to_pdb"):
            try:
                return self._model.output_to_pdb(output)[0]
            except Exception:  # noqa: S110, BLE001
                pass

        # Method 2: Use esm.utils.structure if available
        try:
            from esm.utils.structure.protein import output_to_pdb
            return output_to_pdb(output)[0]
        except (ImportError, Exception):  # noqa: S110, BLE001
            pass

        # Method 3: Fallback — run infer_pdb (costs extra GPU time but guarantees output)
        logger.warning("esmfold_pdb_fallback", msg="Using infer_pdb fallback")
        with torch.no_grad():
            return self._model.infer_pdb(sequence)

    @staticmethod
    def _extract_plddt_from_pdb(pdb_string: str) -> list[float]:
        """Extract per-residue pLDDT from PDB B-factor column.

        ESMFold writes pLDDT into the B-factor field of ATOM records.
        We take the CA atom's B-factor for each residue.
        """
        plddt_values: list[float] = []
        seen_residues: set[int] = set()

        for line in io.StringIO(pdb_string):
            if line.startswith("ATOM") and line[12:16].strip() == "CA":
                res_seq = int(line[22:26].strip())
                if res_seq not in seen_residues:
                    b_factor = float(line[60:66].strip())
                    plddt_values.append(b_factor)
                    seen_residues.add(res_seq)

        return plddt_values
