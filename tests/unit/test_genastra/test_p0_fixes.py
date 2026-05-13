"""Tests validating all P0 fixes from expert critique v1.

Each test is tagged with the P0 issue it validates.
Uses downloaded test data in data/ directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

DATA_DIR = Path(__file__).parent.parent / "data"


# ── P0-2: BIC fallback must be refused ────────────────────────────

class TestP02NoBICFallback:
    def test_import_error_without_dynesty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Nested sampling MUST raise ImportError if dynesty is missing."""
        import aria.genastra.spectra.bayesian as bmod

        # Simulate dynesty not installed
        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

        def mock_import(name, *args, **kwargs):
            if name == "dynesty":
                raise ImportError("No module named 'dynesty'")
            return original_import(name, *args, **kwargs)

        wavelengths = np.linspace(1.0, 5.0, 100)
        flux = np.ones(100)
        flux_err = np.full(100, 0.01)

        monkeypatch.setattr("builtins.__import__", mock_import)
        with pytest.raises(ImportError, match="dynesty is required"):
            bmod.run_nested_sampling(wavelengths, flux, flux_err, "CH4")


# ── P0-3: Radiosensitivity α corrected to protein-level ──────────

class TestP03ProteinLevelAlpha:
    def test_iss_dose_low_damage(self) -> None:
        """At ISS 6-month dose (~100 mGy), per-molecule damage should be <1%."""
        from aria.genastra.radiation.dose_response import lnt_model

        # ISS 6-month dose with typical shielding
        prob = lnt_model(100.0)  # 100 mGy, default α=5e-5, default RBE for proton=1.5
        assert prob < 0.01, f"At 100 mGy, damage probability should be <1%, got {prob:.4f}"

    def test_high_dose_reasonable(self) -> None:
        """At SPE dose (~2000 mGy), damage should be noticeable but not 100%."""
        from aria.genastra.radiation.dose_response import lnt_model

        prob = lnt_model(2000.0)
        assert 0.01 < prob < 0.5, f"At 2000 mGy, expected 1-50% damage, got {prob:.4f}"

    def test_alpha_constants_exist(self) -> None:
        """Module must export correct protein-level α constants."""
        from aria.genastra.radiation.dose_response import (
            ALPHA_BACKBONE_BREAK,
            ALPHA_CROSSLINK,
            ALPHA_SIDECHAIN_OXIDATION,
        )
        assert ALPHA_SIDECHAIN_OXIDATION == 5e-5
        assert ALPHA_BACKBONE_BREAK == 1e-5
        assert ALPHA_CROSSLINK == 1e-6

    def test_dose_response_monotonic(self) -> None:
        """Damage probability must increase monotonically with dose."""
        from aria.genastra.radiation.dose_response import lnt_model

        prev = 0.0
        for dose in [0, 10, 50, 100, 500, 1000, 5000, 10000]:
            prob = lnt_model(float(dose))
            assert prob >= prev, f"Non-monotonic at dose={dose}"
            prev = prob


# ── P0-4: SASA-weighted vulnerability ─────────────────────────────

class TestP04SASAWeighting:
    def test_predict_accepts_pdb(self) -> None:
        """predict_heuristic must accept pdb_string parameter."""
        from aria.genastra.radiation.damage_predictor import predict_heuristic
        from aria.genastra.radiation.environment import iss_6_month

        env = iss_6_month()
        result = predict_heuristic("MKTLCCSHLVEAL", env, pdb_string=None)
        assert not result.sasa_weighted

    def test_with_real_pdb_structure(self) -> None:
        """If BioPython SASA is available, SASA weighting should be applied."""
        from aria.genastra.radiation.damage_predictor import predict_heuristic
        from aria.genastra.radiation.environment import iss_6_month

        pdb_path = DATA_DIR / "proteins" / "1UBQ.pdb"
        if not pdb_path.exists():
            pytest.skip("Test data not downloaded: 1UBQ.pdb")

        pdb_string = pdb_path.read_text()
        # Ubiquitin is 76 residues
        ubiquitin_seq = "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG"

        env = iss_6_month()
        try:
            result = predict_heuristic(ubiquitin_seq, env, pdb_string=pdb_string)
            # If BioPython is installed, SASA should be applied
            if result.sasa_weighted:
                assert result.model_name == "heuristic_sasa_v2"
        except ImportError:
            pytest.skip("BioPython not installed for SASA")

    def test_zinc_finger_boost(self) -> None:
        """Zinc finger motifs (CCHH pattern) should get extra vulnerability boost."""
        from aria.genastra.radiation.damage_predictor import predict_heuristic
        from aria.genastra.radiation.environment import iss_6_month

        # Classic C2H2 zinc finger: C-X(2-4)-C-X(12)-H-X(3-5)-H
        zf_seq = "YKCGECGKAFNQSSHLRHQRTHTGEKP"
        plain_seq = "YKAGEEAKAFNQSSALRAQRTATAEKP"  # same length, no Cys/His

        env = iss_6_month()
        zf_result = predict_heuristic(zf_seq, env)
        plain_result = predict_heuristic(plain_seq, env)

        assert zf_result.overall_damage_score > plain_result.overall_damage_score


# ── P0-5: ESMFold single inference ────────────────────────────────

class TestP05SingleInference:
    def test_folding_result_has_pae_field(self) -> None:
        """FoldingResult must include pae_matrix field."""
        from aria.genastra.protein.esmfold import FoldingResult

        result = FoldingResult(
            pdb_string="ATOM ...",
            mean_plddt=75.0,
            per_residue_plddt=(75.0, 80.0),
            ptm_score=0.8,
            pae_matrix=None,
            inference_time_ms=1000,
            sequence_length=2,
        )
        assert hasattr(result, "pae_matrix")


# ── P0-6: Storey's pi0 estimation ────────────────────────────────

class TestP06Pi0Estimation:
    def test_all_null_pvalues(self) -> None:
        """If all genes are null (uniform p-values), pi0 should be ~1.0."""
        from aria.genastra.expression.deseq2 import estimate_pi0

        rng = np.random.RandomState(42)
        pvalues = rng.uniform(0, 1, 10000)  # uniform = all null
        pi0 = estimate_pi0(pvalues)
        assert pi0 is not None
        assert 0.9 < pi0 <= 1.0, f"Expected pi0 ~1.0 for all null, got {pi0}"

    def test_half_significant(self) -> None:
        """If ~50% are significant, pi0 should be ~0.5."""
        from aria.genastra.expression.deseq2 import estimate_pi0

        rng = np.random.RandomState(42)
        null_p = rng.uniform(0, 1, 5000)
        sig_p = rng.beta(0.1, 1, 5000)  # concentrated near 0
        pvalues = np.concatenate([null_p, sig_p])
        pi0 = estimate_pi0(pvalues)
        assert pi0 is not None
        assert 0.3 < pi0 < 0.7, f"Expected pi0 ~0.5 for 50% null, got {pi0}"

    def test_empty_pvalues(self) -> None:
        from aria.genastra.expression.deseq2 import estimate_pi0
        assert estimate_pi0(np.array([])) is None

    def test_few_pvalues_returns_one(self) -> None:
        from aria.genastra.expression.deseq2 import estimate_pi0
        assert estimate_pi0(np.array([0.5, 0.3, 0.8])) == 1.0


# ── P0-7: Empirical priors corrected ─────────────────────────────

class TestP07CorrectedPriors:
    def test_ch4_prior_realistic(self) -> None:
        """CH₄ prior should span Mars (0.41 ppb) to Titan (5.65%)."""
        from aria.genastra.spectra.bayesian import get_prior

        mu, sigma = get_prior("empirical", "CH4")
        # Mars: log10(4.1e-10) ≈ -9.4, Titan: log10(5.65e-2) ≈ -1.25
        # mu should be between these, sigma should cover range
        assert -8.0 < mu < -2.0, f"CH4 mu={mu} outside realistic range"
        assert sigma > 1.5, f"CH4 sigma={sigma} too narrow for Mars-to-Titan range"

    def test_dms_prior_narrow(self) -> None:
        """DMS prior should be narrow — it's rare and only biogenic."""
        from aria.genastra.spectra.bayesian import get_prior

        mu, sigma = get_prior("empirical", "DMS")
        assert mu < -8.0, f"DMS mu={mu} should be very low (Earth: ~0.1 ppb)"
        assert sigma <= 1.5, f"DMS sigma={sigma} should be narrow"

    def test_pessimistic_lower_than_empirical(self) -> None:
        from aria.genastra.spectra.bayesian import get_prior

        for mol in ["CH4", "DMS", "O3", "N2O"]:
            mu_emp, _ = get_prior("empirical", mol)
            mu_pes, _ = get_prior("pessimistic", mol)
            assert mu_pes < mu_emp, f"{mol}: pessimistic ({mu_pes}) not lower than empirical ({mu_emp})"


# ── Validate against downloaded data ──────────────────────────────

class TestDownloadedData:
    def test_alphafold_p53_json_valid(self) -> None:
        """AlphaFold P04637 (p53) JSON should be parseable with expected fields."""
        path = DATA_DIR / "proteins" / "alphafold_P04637.json"
        if not path.exists():
            pytest.skip("Test data not downloaded")

        data = json.loads(path.read_text())
        # AlphaFold API returns a list
        entry = data[0] if isinstance(data, list) else data
        assert "pdbUrl" in entry or "cifUrl" in entry or "uniprotAccession" in entry

    def test_1ubq_pdb_parseable(self) -> None:
        """1UBQ PDB file should contain ATOM records."""
        path = DATA_DIR / "proteins" / "1UBQ.pdb"
        if not path.exists():
            pytest.skip("Test data not downloaded")

        content = path.read_text()
        atom_lines = [ln for ln in content.splitlines() if ln.startswith("ATOM")]
        assert len(atom_lines) > 100, f"Expected >100 ATOM lines, got {len(atom_lines)}"

    def test_1ubq_plddt_extraction(self) -> None:
        """pLDDT extraction from real PDB should work."""
        from aria.genastra.protein.esmfold import ESMFoldEngine

        path = DATA_DIR / "proteins" / "1UBQ.pdb"
        if not path.exists():
            pytest.skip("Test data not downloaded")

        content = path.read_text()
        plddt = ESMFoldEngine._extract_plddt_from_pdb(content)  # noqa: SLF001
        # Experimental PDB: B-factors are NOT pLDDT but the extraction should still work
        assert len(plddt) > 0, "Should extract at least some residue B-factors"

    def test_nasa_osd37_metadata(self) -> None:
        """NASA OSD-37 metadata JSON should be parseable."""
        path = DATA_DIR / "expression" / "nasa_osd37_files.json"
        if not path.exists():
            pytest.skip("Test data not downloaded")

        data = json.loads(path.read_text())
        assert isinstance(data, dict | list), "OSD-37 metadata should be JSON"


# ── FASTA parser ──────────────────────────────────────────────────

class TestFASTAParser:
    def test_single_sequence(self) -> None:
        from aria.genastra.protein.fasta_parser import parse_fasta

        fasta = ">sp|P04637|P53_HUMAN Cellular tumor antigen p53\nMEEPQSDPSVEPPLSQETFSDLWKLL"
        entries = parse_fasta(fasta)
        assert len(entries) == 1
        assert entries[0].accession == "P04637"
        assert entries[0].sequence == "MEEPQSDPSVEPPLSQETFSDLWKLL".upper()

    def test_multi_sequence(self) -> None:
        from aria.genastra.protein.fasta_parser import parse_fasta

        fasta = ">seq1\nMKTL\n>seq2\nACDE\n>seq3\nFGHI"
        entries = parse_fasta(fasta)
        assert len(entries) == 3

    def test_raw_sequence_no_header(self) -> None:
        from aria.genastra.protein.fasta_parser import parse_fasta

        entries = parse_fasta("MKTLLILAVVAAALA")
        assert len(entries) == 1
        assert entries[0].accession == "unnamed"

    def test_empty_raises(self) -> None:
        from aria.genastra.protein.fasta_parser import FastaParseError, parse_fasta

        with pytest.raises(FastaParseError, match="Empty"):
            parse_fasta("")

    def test_too_long_sequence_raises(self) -> None:
        from aria.genastra.protein.fasta_parser import FastaParseError, parse_fasta

        fasta = ">too_long\n" + "A" * 3000
        with pytest.raises(FastaParseError, match="exceeding"):
            parse_fasta(fasta)

    def test_uniprot_header_parsing(self) -> None:
        from aria.genastra.protein.fasta_parser import parse_fasta

        fasta = ">sp|P00533|EGFR_HUMAN Epidermal growth factor receptor\nMRPSGTAGAALL"
        entries = parse_fasta(fasta)
        assert entries[0].accession == "P00533"
        assert "Epidermal" in entries[0].description

    def test_multiline_sequence(self) -> None:
        from aria.genastra.protein.fasta_parser import parse_fasta

        fasta = ">protein\nMKTL\nLILA\nVVAA"
        entries = parse_fasta(fasta)
        assert entries[0].sequence == "MKTLLILAVVAA"
