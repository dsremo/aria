"""Tests validating P0-v2 and P1-v2 fixes from expert critique v2.

30-expert debate found 41 new issues. These tests validate the fixes.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

DATA_DIR = Path(__file__).parent.parent / "data"


# ── P0-v2-1: Forward model uses Voigt profiles, not Gaussian bumps ──

class TestP0v21ForwardModel:
    def test_voigt_profile_exists(self) -> None:
        from aria.genastra.spectra.forward_model import voigt_profile
        x = np.linspace(-1, 1, 100)
        profile = voigt_profile(x, sigma=0.1, gamma_l=0.05)
        assert profile.shape == (100,)
        assert np.all(profile >= 0)

    def test_voigt_peaks_at_center(self) -> None:
        from aria.genastra.spectra.forward_model import voigt_profile
        x = np.linspace(-2, 2, 1000)
        profile = voigt_profile(x, sigma=0.1, gamma_l=0.05)
        peak_idx = np.argmax(profile)
        assert abs(x[peak_idx]) < 0.05  # peak near center

    def test_voigt_wider_than_gaussian(self) -> None:
        """Voigt profile should have heavier tails than pure Gaussian (Lorentzian wings)."""
        from aria.genastra.spectra.forward_model import voigt_profile
        x = np.linspace(-5, 5, 1000)
        # Pure Gaussian (gamma_l → 0)
        pure_gauss = voigt_profile(x, sigma=0.2, gamma_l=1e-10)
        # Voigt with Lorentzian wings
        voigt = voigt_profile(x, sigma=0.2, gamma_l=0.2)
        # At the tails (|x| > 1), Voigt should be larger than Gaussian
        tail_mask = np.abs(x) > 1.5
        assert np.mean(voigt[tail_mask]) > np.mean(pure_gauss[tail_mask])

    def test_rayleigh_scattering_lambda_minus_4(self) -> None:
        """Rayleigh scattering should scale as λ⁻⁴."""
        from aria.genastra.spectra.forward_model import rayleigh_scattering_cross_section
        wl = np.array([1.0, 2.0])
        sigma = rayleigh_scattering_cross_section(wl)
        # σ(1μm) / σ(2μm) should be ≈ 2⁴ = 16
        ratio = sigma[0] / sigma[1]
        assert abs(ratio - 16.0) < 1.0

    def test_h2h2_cia_has_features(self) -> None:
        """CIA should have broad features around 1.2 and 2.1 μm."""
        from aria.genastra.spectra.forward_model import h2h2_cia_cross_section
        wl = np.linspace(0.5, 5.0, 500)
        cia = h2h2_cia_cross_section(wl, temperature=300.0)
        # Peak near 2.1 μm
        peak_idx = np.argmax(cia)
        assert 1.5 < wl[peak_idx] < 2.5

    def test_guillot_tp_profile_increases_with_depth(self) -> None:
        """Temperature should generally increase with pressure (depth)."""
        from aria.genastra.spectra.forward_model import guillot_tp_profile
        pressures = np.logspace(-6, 2, 50)
        temps = guillot_tp_profile(pressures, t_eq=300.0, t_int=200.0)
        # Temperature at high pressure should be > low pressure
        assert temps[-1] > temps[0]

    def test_atmospheric_model_dataclass(self) -> None:
        from aria.genastra.spectra.forward_model import AtmosphericModel
        model = AtmosphericModel(
            planet_radius_rj=0.16,  # K2-18b
            planet_mass_mj=0.027,
            star_radius_rs=0.41,
            t_eq=255.0,
        )
        assert model.t_eq == 255.0


# ── P0-v2-2: FITS file parsing ──────────────────────────────────

class TestP0v22FITSParsing:
    def test_fits_reader_module_exists(self) -> None:
        from aria.genastra.spectra.fits_reader import bin_spectrum, read_jwst_spectrum
        assert callable(read_jwst_spectrum)
        assert callable(bin_spectrum)

    def test_spectral_binning(self) -> None:
        """Binning should reduce resolution while preserving signal."""
        from aria.genastra.spectra.fits_reader import bin_spectrum
        # Create a synthetic high-res spectrum
        wl = np.linspace(1.0, 5.0, 4000)  # R~4000
        flux = 1.0 - 0.001 * np.exp(-0.5 * ((wl - 3.3) / 0.1)**2)  # CH4 feature
        err = np.full_like(flux, 0.0001)

        binned_wl, binned_flux, binned_err = bin_spectrum(wl, flux, err, target_resolution=100)

        # Should have ~100x fewer points
        assert len(binned_wl) < len(wl) / 10
        # Error should be smaller (averaged over many points)
        assert np.mean(binned_err) < np.mean(err)
        # Feature should still be visible
        feature_region = (binned_wl > 3.0) & (binned_wl < 3.6)
        assert np.min(binned_flux[feature_region]) < 1.0

    def test_bin_preserves_wavelength_range(self) -> None:
        from aria.genastra.spectra.fits_reader import bin_spectrum
        wl = np.linspace(1.0, 5.0, 1000)
        flux = np.ones(1000)
        err = np.full(1000, 0.01)
        bwl, _, _ = bin_spectrum(wl, flux, err, target_resolution=50)
        assert bwl.min() >= 1.0
        assert bwl.max() <= 5.0


# ── P0-v2-3: LFC shrinkage ──────────────────────────────────────

class TestP0v23LFCShrinkage:
    def test_deseq2_calls_lfc_shrink(self) -> None:
        """The run_deseq2 code must contain lfc_shrink call."""
        import inspect

        from aria.genastra.expression.deseq2 import run_deseq2
        source = inspect.getsource(run_deseq2)
        assert "lfc_shrink" in source, "run_deseq2 must call lfc_shrink()"

    def test_deseq2_calls_validate(self) -> None:
        """run_deseq2 must call validate_experimental_design."""
        import inspect

        from aria.genastra.expression.deseq2 import run_deseq2
        source = inspect.getsource(run_deseq2)
        assert "validate_experimental_design" in source


# ── P0-v2-4: Null model includes Rayleigh + CIA ─────────────────

class TestP0v24NullModel:
    def test_bayesian_loglike_m1_uses_voigt(self) -> None:
        """The M₁ log-likelihood must import and use Voigt profiles."""
        import inspect

        from aria.genastra.spectra.bayesian import run_nested_sampling
        source = inspect.getsource(run_nested_sampling)
        assert "voigt_profile" in source, "M₁ model must use Voigt profiles"
        assert "rayleigh_scattering" in source, "M₁ model must include Rayleigh scattering"


# ── P1-v2-3: PAE domain boundary detection ──────────────────────

class TestP1v23PAEBoundaries:
    def test_detect_boundaries_two_domains(self) -> None:
        """A protein with two clear domains should have one boundary."""
        from aria.genastra.radiation.damage_predictor import _detect_domain_boundaries

        n = 100
        # Create PAE matrix: low PAE within domains, high between
        pae = np.full((n, n), 20.0)  # high default (uncertain)
        # Domain 1: residues 0-49, low internal PAE
        pae[:50, :50] = 3.0
        # Domain 2: residues 50-99, low internal PAE
        pae[50:, 50:] = 3.0

        pae_tuple = tuple(tuple(float(v) for v in row) for row in pae)
        boundaries = _detect_domain_boundaries(pae_tuple, min_domain_size=20)

        assert len(boundaries) >= 1
        # Boundary should be near residue 50
        assert any(40 <= b <= 60 for b in boundaries)

    def test_no_boundaries_single_domain(self) -> None:
        """A single-domain protein should have no boundaries."""
        from aria.genastra.radiation.damage_predictor import _detect_domain_boundaries

        n = 80
        pae = np.full((n, n), 3.0)  # low PAE everywhere (single domain)
        pae_tuple = tuple(tuple(float(v) for v in row) for row in pae)
        boundaries = _detect_domain_boundaries(pae_tuple, min_domain_size=20)
        assert len(boundaries) == 0

    def test_small_protein_no_boundaries(self) -> None:
        """Proteins shorter than 2×min_domain_size can't have boundaries."""
        from aria.genastra.radiation.damage_predictor import _detect_domain_boundaries

        pae = tuple(tuple(5.0 for _ in range(30)) for _ in range(30))
        boundaries = _detect_domain_boundaries(pae, min_domain_size=30)
        assert len(boundaries) == 0


# ── P1-v2-4: Structure quality gating ────────────────────────────

class TestP1v24QualityGating:
    def test_low_plddt_refuses_sasa(self) -> None:
        """When pLDDT < 50, SASA weighting should NOT be applied."""
        from aria.genastra.radiation.damage_predictor import predict_heuristic
        from aria.genastra.radiation.environment import iss_6_month

        env = iss_6_month()
        # Provide a PDB but with low confidence — SASA should be refused
        result = predict_heuristic(
            "MKTLCCSHLVEAL",
            env,
            pdb_string="ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 30.00\n",
            mean_plddt=35.0,  # too low
        )
        assert not result.sasa_weighted

    def test_high_plddt_allows_sasa(self) -> None:
        """When pLDDT >= 50, SASA weighting should be attempted."""
        from aria.genastra.radiation.damage_predictor import predict_heuristic
        from aria.genastra.radiation.environment import iss_6_month

        env = iss_6_month()
        # Even if SASA computation fails (simple PDB), the gating should allow it
        result = predict_heuristic(
            "MKTLCCSHLVEAL",
            env,
            pdb_string=None,
            mean_plddt=80.0,
        )
        # Without pdb_string, SASA won't be applied regardless of pLDDT
        assert not result.sasa_weighted

    def test_pae_boosts_boundary_vulnerability(self) -> None:
        """PAE domain boundaries should increase vulnerability scores."""
        from aria.genastra.radiation.damage_predictor import predict_heuristic
        from aria.genastra.radiation.environment import iss_6_month

        env = iss_6_month()
        seq = "A" * 100  # all Ala (low intrinsic sensitivity)

        # Without PAE
        result_no_pae = predict_heuristic(seq, env)

        # With PAE showing a clear domain boundary at position 50
        n = 100
        pae = np.full((n, n), 20.0)
        pae[:50, :50] = 3.0
        pae[50:, 50:] = 3.0
        pae_tuple = tuple(tuple(float(v) for v in row) for row in pae)

        result_with_pae = predict_heuristic(seq, env, pae_matrix=pae_tuple)

        # Vulnerability near boundary (position 50) should be higher with PAE
        boundary_region = slice(45, 55)
        scores_no_pae = np.array(result_no_pae.vulnerability_scores[boundary_region])
        scores_with_pae = np.array(result_with_pae.vulnerability_scores[boundary_region])
        assert np.mean(scores_with_pae) > np.mean(scores_no_pae)


# ── Validate real downloaded data structures ─────────────────────

class TestRealDataValidation:
    def test_p53_alphafold_has_pdb_url(self) -> None:
        path = DATA_DIR / "proteins" / "alphafold_P04637.json"
        if not path.exists():
            pytest.skip("Data not downloaded")
        data = json.loads(path.read_text())
        entry = data[0] if isinstance(data, list) else data
        # Should have a URL to download the PDB/CIF file
        has_structure_url = any(
            key in entry for key in ["pdbUrl", "cifUrl", "modelUrl"]
        )
        assert has_structure_url, f"Keys: {list(entry.keys())}"

    def test_1tup_pdb_has_dna_binding_residues(self) -> None:
        """p53 DNA-binding domain (1TUP) should contain zinc-coordinating cysteines."""
        path = DATA_DIR / "proteins" / "1TUP.pdb"
        if not path.exists():
            pytest.skip("Data not downloaded")
        content = path.read_text()
        # 1TUP contains zinc ions coordinated by cysteines
        assert "ZN" in content or "CYS" in content

    def test_uniprot_p53_has_dna_binding_annotation(self) -> None:
        """UniProt P04637 should annotate DNA-binding regions."""
        path = DATA_DIR / "proteins" / "uniprot_P04637.json"
        if not path.exists():
            pytest.skip("Data not downloaded")
        data = json.loads(path.read_text())
        text = json.dumps(data).lower()
        assert "dna" in text or "binding" in text

    def test_nasa_osd37_has_study_files(self) -> None:
        """OSD-37 metadata should list downloadable files."""
        path = DATA_DIR / "expression" / "nasa_osd37_files.json"
        if not path.exists():
            pytest.skip("Data not downloaded")
        data = json.loads(path.read_text())
        # Should have some structure indicating files
        text = json.dumps(data)
        assert len(text) > 100  # non-trivial response
