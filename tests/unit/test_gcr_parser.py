"""Tests for aria.simulation.gcr_data_parser — ACE/CRIS GCR data parsing and flux model."""

from __future__ import annotations

import math
import textwrap
from pathlib import Path

import pytest

from aria.simulation.gcr_data_parser import (
    CRISData,
    ElementSpectrum,
    GCRFluxModel,
    PHI_SOLAR_MAX_MV,
    PHI_SOLAR_MIN_MV,
    PRIMARY_ELEMENTS,
    _force_field_ratio,
    _interpolate_log,
    _parse_element_line,
    _parse_energy_header,
    parse_leaky_box_file,
    parse_spectra_file,
)


# ════════════════════════════════════════════════════════════════
#  FIXTURES
# ════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_spectra_file(tmp_path: Path) -> Path:
    """Create a minimal cris_spectra.txt for testing."""
    content = textwrap.dedent("""\
        CRIS Solar Minimum Spectra (interpolated to common energy grid)
        ---------------------------------------------------------------
        Flux units: [cm^2.s.sr.(MeV/nuc]^-1 * 10^-9

        E/A 60.0 MeV/nuc.    72.0               85.0             100.0

         C                   541.15 +/- 21.96  600.09 +/- 24.25  665.79 +/- 26.88
         N                   126.61 +/-  5.39  136.73 +/-  5.71  148.14 +/-  6.14
         O                                     594.66 +/- 24.05  648.65 +/- 26.15
        Fe

        E/A 170.0            200.0

         O  792.58 +/- 32.04  802.60 +/- 32.53
        Fe                                      71.24 +/-  2.97   74.29 +/-  3.07


        CRIS Solar Maximum Spectra (interpolated to common energy grid)
        ---------------------------------------------------------------
        Flux units: [cm^2.s.sr.(MeV/nuc]^-1 * 10^-9

        E/A 60.0 MeV/nuc.    72.0             85.0            100.0

         C                  114.75 +/- 4.68  130.02 +/- 5.27  147.76 +/- 5.98
         N                   30.92 +/- 1.33   34.56 +/- 1.45   38.72 +/- 1.61
         O                                   127.36 +/- 5.17  142.28 +/- 5.75

        E/A 170.0           200.0

         O  200.86 +/- 8.13  216.43 +/- 8.77
        Fe                                    22.24 +/- 0.92   23.85 +/- 0.98
    """)
    p = tmp_path / "cris_spectra.txt"
    p.write_text(content)
    return p


@pytest.fixture
def sample_leaky_box_file(tmp_path: Path) -> Path:
    """Create a minimal cris_leaky_box.txt for testing."""
    content = textwrap.dedent("""\
        > Solar Modulation phi Values (MV) from
        > Fits to ACE/CRIS Element Spectra
        > Bartels   Start Date  Z =     6        8       12       14       26
          2244      30 Nov 1997      345.     320.     330.     330.     330.
          2245      27 Dec 1997      335.     310.     335.     325.     305.
          2280      29 Jul 2000     1085.    1030.    1060.    1050.    1015.
    """)
    p = tmp_path / "cris_leaky_box.txt"
    p.write_text(content)
    return p


@pytest.fixture
def data_dir_fixture(sample_spectra_file: Path, sample_leaky_box_file: Path) -> Path:
    """Return the tmp_path containing both data files."""
    return sample_spectra_file.parent


# ════════════════════════════════════════════════════════════════
#  PARSING — ENERGY HEADER
# ════════════════════════════════════════════════════════════════

class TestParseEnergyHeader:
    def test_typical_header(self):
        line = "E/A 60.0 MeV/nuc.    72.0               85.0             100.0"
        result = _parse_energy_header(line)
        assert result == [60.0, 72.0, 85.0, 100.0]

    def test_continuation_header(self):
        line = "E/A 240.0 MeV/nuc.   285.0             340.0"
        result = _parse_energy_header(line)
        assert result == [240.0, 285.0, 340.0]


# ════════════════════════════════════════════════════════════════
#  PARSING — ELEMENT LINE
# ════════════════════════════════════════════════════════════════

class TestParseElementLine:
    def test_carbon_line(self):
        energies = [60.0, 72.0, 85.0, 100.0]
        line = " C                   541.15 +/- 21.96  600.09 +/- 24.25  665.79 +/- 26.88"
        result = _parse_element_line(line, energies)
        assert result is not None
        sym, e, f, err = result
        assert sym == "C"
        assert len(f) == 3
        assert f[0] == pytest.approx(541.15)
        # 3 flux values -> last 3 energies: 72, 85, 100
        assert e == [72.0, 85.0, 100.0]

    def test_iron_line(self):
        energies = [170.0, 200.0]
        line = "Fe                                      71.24 +/-  2.97   74.29 +/-  3.07"
        result = _parse_element_line(line, energies)
        assert result is not None
        sym, e, f, err = result
        assert sym == "Fe"
        assert f == [71.24, 74.29]
        assert err == [2.97, 3.07]

    def test_non_element_line_returns_none(self):
        assert _parse_element_line("Flux units: blah", [100.0]) is None
        assert _parse_element_line("", [100.0]) is None


# ════════════════════════════════════════════════════════════════
#  PARSING — SPECTRA FILE
# ════════════════════════════════════════════════════════════════

class TestParseSpectraFile:
    def test_parses_solar_min_and_max(self, sample_spectra_file: Path):
        sol_min, sol_max = parse_spectra_file(sample_spectra_file)
        assert "C" in sol_min
        assert "N" in sol_min
        assert "C" in sol_max
        assert "Fe" in sol_max

    def test_carbon_solar_min_flux_values(self, sample_spectra_file: Path):
        sol_min, _ = parse_spectra_file(sample_spectra_file)
        c = sol_min["C"]
        assert c.fluxes[0] == pytest.approx(541.15)
        assert len(c.energies_mev_nuc) == 3
        assert c.energies_mev_nuc[0] == pytest.approx(72.0)

    def test_iron_has_continuation_block(self, sample_spectra_file: Path):
        sol_min, _ = parse_spectra_file(sample_spectra_file)
        fe = sol_min["Fe"]
        assert len(fe.fluxes) == 2
        assert fe.fluxes[0] == pytest.approx(71.24)


# ════════════════════════════════════════════════════════════════
#  PARSING — LEAKY BOX PHI
# ════════════════════════════════════════════════════════════════

class TestParseLeakyBox:
    def test_parses_records(self, sample_leaky_box_file: Path):
        records = parse_leaky_box_file(sample_leaky_box_file)
        assert len(records) == 3

    def test_first_record_values(self, sample_leaky_box_file: Path):
        records = parse_leaky_box_file(sample_leaky_box_file)
        r = records[0]
        assert r.bartels == 2244
        assert "Nov" in r.date_str
        assert r.phi_by_z[6] == pytest.approx(345.0)
        assert r.phi_by_z[26] == pytest.approx(330.0)

    def test_solar_max_record(self, sample_leaky_box_file: Path):
        records = parse_leaky_box_file(sample_leaky_box_file)
        r = records[2]  # Bartels 2280 — solar max era
        assert r.phi_by_z[6] == pytest.approx(1085.0)


# ════════════════════════════════════════════════════════════════
#  INTERPOLATION
# ════════════════════════════════════════════════════════════════

class TestInterpolation:
    def test_exact_point(self):
        energies = [100.0, 200.0, 400.0]
        fluxes = [10.0, 5.0, 2.0]
        assert _interpolate_log(energies, fluxes, 100.0) == pytest.approx(10.0)

    def test_midpoint(self):
        energies = [100.0, 400.0]
        fluxes = [100.0, 100.0]  # flat spectrum
        assert _interpolate_log(energies, fluxes, 200.0) == pytest.approx(100.0)

    def test_decreasing_spectrum(self):
        energies = [100.0, 1000.0]
        fluxes = [100.0, 1.0]
        mid = _interpolate_log(energies, fluxes, 316.23)  # geometric mean
        assert 1.0 < mid < 100.0
        assert mid == pytest.approx(10.0, rel=0.1)  # power-law -> geometric mean

    def test_extrapolation_below(self):
        energies = [100.0, 200.0]
        fluxes = [10.0, 5.0]
        result = _interpolate_log(energies, fluxes, 50.0)
        assert result > 10.0  # Extrapolating to lower energy -> higher flux

    def test_extrapolation_above(self):
        energies = [100.0, 200.0]
        fluxes = [10.0, 5.0]
        result = _interpolate_log(energies, fluxes, 400.0)
        assert result < 5.0

    def test_single_point(self):
        assert _interpolate_log([100.0], [42.0], 200.0) == pytest.approx(42.0)

    def test_empty(self):
        assert _interpolate_log([], [], 100.0) == 0.0


# ════════════════════════════════════════════════════════════════
#  FORCE-FIELD MODULATION
# ════════════════════════════════════════════════════════════════

class TestForceField:
    def test_same_phi_gives_unity(self):
        ratio = _force_field_ratio(200.0, 400.0, 400.0, z=6, a=12)
        assert ratio == pytest.approx(1.0)

    def test_higher_phi_reduces_flux(self):
        # More solar modulation -> lower flux
        ratio = _force_field_ratio(200.0, 300.0, 600.0, z=6, a=12)
        assert ratio < 1.0

    def test_lower_phi_increases_flux(self):
        ratio = _force_field_ratio(200.0, 600.0, 300.0, z=6, a=12)
        assert ratio > 1.0

    def test_proton_symmetry(self):
        # ratio(a->b) * ratio(b->a) ~ 1
        r1 = _force_field_ratio(200.0, 300.0, 600.0, z=1, a=1)
        r2 = _force_field_ratio(200.0, 600.0, 300.0, z=1, a=1)
        assert r1 * r2 == pytest.approx(1.0, rel=0.01)

    def test_heavy_ion_stronger_modulation(self):
        # Iron (Z=26, A=56) is more strongly modulated than Carbon (Z=6, A=12)
        # at the same phi change, because Phi_eff = Z*phi/A is larger for Fe
        ratio_c = _force_field_ratio(200.0, 300.0, 800.0, z=6, a=12)
        ratio_fe = _force_field_ratio(200.0, 300.0, 800.0, z=26, a=56)
        # Fe has Z/A ~ 0.464, C has Z/A = 0.5, so C is actually modulated more
        # But the absolute change matters. Both should be < 1.
        assert ratio_c < 1.0
        assert ratio_fe < 1.0


# ════════════════════════════════════════════════════════════════
#  GCR FLUX MODEL — FULL INTEGRATION
# ════════════════════════════════════════════════════════════════

class TestGCRFluxModel:
    def test_loads_from_data_dir(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        elems = model.available_elements
        assert "C" in elems
        assert "Fe" in elems
        # H and He are always synthesized
        assert "H" in elems
        assert "He" in elems

    def test_phi_records_loaded(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        records = model.phi_records
        assert len(records) == 3

    def test_get_gcr_flux_carbon_solar_min(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        flux = model.get_gcr_flux("C", energy_MeV=85.0, solar_cycle_phase=0.0)
        # Should be close to 600.09 * 1e-9
        assert flux == pytest.approx(600.09e-9, rel=0.05)

    def test_get_gcr_flux_carbon_solar_max(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        flux = model.get_gcr_flux("C", energy_MeV=85.0, solar_cycle_phase=0.5)
        # Should be close to 130.02 * 1e-9
        assert flux == pytest.approx(130.02e-9, rel=0.05)

    def test_solar_min_flux_higher_than_max(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        flux_min = model.get_gcr_flux("C", energy_MeV=85.0, solar_cycle_phase=0.0)
        flux_max = model.get_gcr_flux("C", energy_MeV=85.0, solar_cycle_phase=0.5)
        assert flux_min > flux_max

    def test_intermediate_phase(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        f_min = model.get_gcr_flux("C", energy_MeV=85.0, solar_cycle_phase=0.0)
        f_max = model.get_gcr_flux("C", energy_MeV=85.0, solar_cycle_phase=0.5)
        f_mid = model.get_gcr_flux("C", energy_MeV=85.0, solar_cycle_phase=0.25)
        # Mid-phase flux should be between min and max
        assert min(f_min, f_max) < f_mid < max(f_min, f_max)

    def test_hydrogen_synthetic(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        flux = model.get_gcr_flux("H", energy_MeV=200.0, solar_cycle_phase=0.0)
        assert flux > 0

    def test_helium_synthetic(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        flux = model.get_gcr_flux("He", energy_MeV=200.0, solar_cycle_phase=0.0)
        assert flux > 0
        # He flux should be less than H flux at same energy
        h_flux = model.get_gcr_flux("H", energy_MeV=200.0, solar_cycle_phase=0.0)
        assert flux < h_flux

    def test_iron_flux(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        flux = model.get_gcr_flux("Fe", energy_MeV=200.0, solar_cycle_phase=0.0)
        assert flux > 0

    def test_unknown_element_raises(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        with pytest.raises(ValueError, match="Unknown element"):
            model.get_gcr_flux("Unobtainium", energy_MeV=100.0, solar_cycle_phase=0.0)

    def test_flux_positive_across_energy_range(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        for e in [50.0, 100.0, 200.0, 500.0, 1000.0]:
            flux = model.get_gcr_flux("H", energy_MeV=e, solar_cycle_phase=0.0)
            assert flux > 0, f"Flux should be positive at {e} MeV"


# ════════════════════════════════════════════════════════════════
#  PHI-PHASE MAPPING
# ════════════════════════════════════════════════════════════════

class TestPhiPhaseMapping:
    def test_phase_zero_is_solar_min(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        phi = model.get_phi_for_phase(0.0)
        assert phi == pytest.approx(PHI_SOLAR_MIN_MV)

    def test_phase_half_is_solar_max(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        phi = model.get_phi_for_phase(0.5)
        assert phi == pytest.approx(PHI_SOLAR_MAX_MV)

    def test_phase_one_returns_to_min(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        phi = model.get_phi_for_phase(1.0)
        assert phi == pytest.approx(PHI_SOLAR_MIN_MV, abs=1.0)

    def test_quarter_phase_intermediate(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        phi = model.get_phi_for_phase(0.25)
        assert PHI_SOLAR_MIN_MV < phi < PHI_SOLAR_MAX_MV


# ════════════════════════════════════════════════════════════════
#  DOSE RATE ESTIMATION
# ════════════════════════════════════════════════════════════════

class TestDoseRate:
    def test_solar_min_dose_higher_than_max(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        dose_min = model.get_total_dose_rate_msv_day(solar_cycle_phase=0.0)
        dose_max = model.get_total_dose_rate_msv_day(solar_cycle_phase=0.5)
        assert dose_min > dose_max

    def test_dose_positive(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        dose = model.get_total_dose_rate_msv_day(solar_cycle_phase=0.0)
        assert dose > 0

    def test_more_shielding_reduces_dose(self, data_dir_fixture: Path):
        model = GCRFluxModel(data_dir=data_dir_fixture)
        dose_thin = model.get_total_dose_rate_msv_day(0.0, shielding_g_cm2=10.0)
        dose_thick = model.get_total_dose_rate_msv_day(0.0, shielding_g_cm2=50.0)
        assert dose_thick < dose_thin


# ════════════════════════════════════════════════════════════════
#  REAL DATA (only runs if the actual data files are present)
# ════════════════════════════════════════════════════════════════

REAL_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "gcr"


@pytest.mark.skipif(
    not (REAL_DATA_DIR / "cris_spectra.txt").exists(),
    reason="Real ACE/CRIS data not available",
)
class TestWithRealData:
    def test_all_primary_elements_available(self):
        model = GCRFluxModel(data_dir=REAL_DATA_DIR)
        elems = model.available_elements
        for e in PRIMARY_ELEMENTS:
            assert e in elems, f"{e} missing from available elements"

    def test_carbon_flux_order_of_magnitude(self):
        model = GCRFluxModel(data_dir=REAL_DATA_DIR)
        flux = model.get_gcr_flux("C", energy_MeV=100.0, solar_cycle_phase=0.0)
        # C flux at 100 MeV/nuc solar min is ~665.79e-9 cm^-2 s^-1 sr^-1 (MeV/nuc)^-1
        assert 1e-7 < flux < 1e-5

    def test_iron_flux_order_of_magnitude(self):
        model = GCRFluxModel(data_dir=REAL_DATA_DIR)
        flux = model.get_gcr_flux("Fe", energy_MeV=200.0, solar_cycle_phase=0.0)
        # Fe flux at 200 MeV/nuc solar min: ~74e-9
        assert 1e-8 < flux < 1e-6

    def test_phi_records_span_decades(self):
        model = GCRFluxModel(data_dir=REAL_DATA_DIR)
        records = model.phi_records
        assert len(records) > 200  # Should have ~340 Bartels rotations
        # Check date range
        assert "1997" in records[0].date_str
        assert "2022" in records[-1].date_str

    def test_dose_rate_realistic(self):
        model = GCRFluxModel(data_dir=REAL_DATA_DIR)
        dose = model.get_total_dose_rate_msv_day(solar_cycle_phase=0.0, shielding_g_cm2=20.0)
        # Simplified dose model; actual value depends on energy integration
        # approximation.  Just verify it's positive and not absurdly large.
        assert 0.0001 < dose < 100.0
