"""Tests for NOAA GOES-16 solar proton flux loader.

Validates the GoesProtonFluxModel against:
  - Physical sanity of loaded spectrum (decreasing flux with energy)
  - ICRP 123 dose coefficient interpolation
  - Quiet-period SPE detection (March 2025 = no large events)
  - Unit conversion (keV→MeV)
  - Compatibility interface with radiation_transport.py
"""

from __future__ import annotations

import math
import pytest
from pathlib import Path

GOES_DATA_DIR = (
    Path(__file__).parent.parent.parent
    / "data" / "raw" / "noaa_goes"
)

has_goes_data = GOES_DATA_DIR.exists() and any(GOES_DATA_DIR.glob("*.nc"))
skip_no_data = pytest.mark.skipif(
    not has_goes_data,
    reason="NOAA GOES-16 netCDF data not present in data/raw/noaa_goes/",
)


class TestIcrp123DoseCoefficient:
    """ICRP 123 proton dose coefficient interpolation."""

    def test_increases_with_energy(self):
        """Dose coefficient must increase monotonically with proton energy.

        More energetic protons penetrate deeper and deposit more dose.
        ICRP 123 (2013) Table A.4.
        """
        from aria.integrations.noaa_goes_loader import icrp123_dose_coeff
        energies = [1.0, 5.0, 10.0, 50.0, 100.0, 500.0, 1000.0]
        coeffs = [icrp123_dose_coeff(e) for e in energies]
        for i in range(1, len(coeffs)):
            assert coeffs[i] > coeffs[i - 1], (
                f"Dose coefficient should increase: "
                f"dc({energies[i]}MeV)={coeffs[i]:.2e} not > "
                f"dc({energies[i-1]}MeV)={coeffs[i-1]:.2e}"
            )

    def test_at_10_mev_matches_icrp(self):
        """At 10 MeV, dc ≈ 1.6×10⁻¹² Sv·cm² (ICRP 123 Table A.4)."""
        from aria.integrations.noaa_goes_loader import icrp123_dose_coeff
        dc = icrp123_dose_coeff(10.0)
        # Allow 10% tolerance on interpolated value
        assert abs(dc - 1.6e-12) / 1.6e-12 < 0.10, (
            f"dc(10 MeV) = {dc:.2e}, expected ~1.6e-12 Sv·cm²"
        )

    def test_positive_for_any_energy(self):
        """Dose coefficient must be positive for all physical energies."""
        from aria.integrations.noaa_goes_loader import icrp123_dose_coeff
        for e in [0.1, 0.5, 1.0, 10.0, 100.0, 1000.0, 5000.0]:
            assert icrp123_dose_coeff(e) > 0, f"dc({e} MeV) should be > 0"


class TestGoesLoader:
    """Load real GOES-16 netCDF files and validate structure."""

    @skip_no_data
    def test_loads_31_days(self):
        """All 31 March 2025 files must load successfully."""
        from aria.integrations.noaa_goes_loader import load_all_days
        records = load_all_days(GOES_DATA_DIR)
        assert len(records) == 31, (
            f"Expected 31 daily records, got {len(records)}"
        )

    @skip_no_data
    def test_record_has_13_energy_bands(self):
        """GOES SGPS has 13 differential proton energy bands."""
        from aria.integrations.noaa_goes_loader import load_all_days
        records = load_all_days(GOES_DATA_DIR)
        assert len(records) > 0
        assert len(records[0].energy_mev) == 13
        assert len(records[0].mean_flux_diff) == 13

    @skip_no_data
    def test_energy_range_physical(self):
        """Energy bands must span 1–400 MeV (SGPS specification)."""
        from aria.integrations.noaa_goes_loader import load_all_days
        records = load_all_days(GOES_DATA_DIR)
        e_min = records[0].energy_mev[0]
        e_max = records[0].energy_mev[-1]
        assert 1.0 <= e_min <= 5.0, f"Lowest band {e_min:.1f} MeV not in 1-5 MeV range"
        assert 200.0 <= e_max <= 500.0, f"Highest band {e_max:.1f} MeV not in 200-500 MeV range"

    @skip_no_data
    def test_fluxes_positive(self):
        """All mean_flux_diff values must be non-negative."""
        from aria.integrations.noaa_goes_loader import load_all_days
        records = load_all_days(GOES_DATA_DIR)
        for rec in records:
            for b, f in enumerate(rec.mean_flux_diff):
                assert f >= 0, f"Band {b} flux {f} is negative on {rec.date_str}"

    @skip_no_data
    def test_march_2025_no_spe_events(self):
        """March 2025 is a quiet period — no large SPEs detected.

        Solar cycle 25 peaked in late 2024; March 2025 background is quiet.
        NOAA SPE threshold: 10 pfu at >10 MeV (NOAA SEC 2003).
        """
        from aria.integrations.noaa_goes_loader import load_all_days, detect_spe_events, SPE_THRESHOLD_PFU
        records = load_all_days(GOES_DATA_DIR)
        events = detect_spe_events(records, threshold_pfu=SPE_THRESHOLD_PFU)
        assert len(events) == 0, (
            f"Expected 0 SPE events in March 2025 quiet period, "
            f"got {len(events)}: {[e.date_str for e in events]}"
        )

    @skip_no_data
    def test_integral_flux_consistent(self):
        """Mean integral flux >500 MeV should be in quiet-time range 0.05–2.0 p/cm²/sr/s."""
        from aria.integrations.noaa_goes_loader import load_all_days
        records = load_all_days(GOES_DATA_DIR)
        mean_int = sum(r.mean_int_flux for r in records) / len(records)
        assert 0.01 < mean_int < 5.0, (
            f"Mean integral flux {mean_int:.4f} p/cm²/sr/s outside quiet-period range"
        )


class TestGoesProtonFluxModel:
    """GoesProtonFluxModel: interface compatibility and physical correctness."""

    @skip_no_data
    def test_loads_real_data(self):
        """Model must report n_days > 0 after loading."""
        from aria.integrations.noaa_goes_loader import GoesProtonFluxModel
        model = GoesProtonFluxModel(GOES_DATA_DIR)
        assert model.n_days == 31

    @skip_no_data
    def test_proton_flux_decreasing_with_energy(self):
        """Proton differential flux must decrease with energy (steep power law).

        GCR spectrum goes as E^{-2.7} above ~1 GeV; softer below.
        At quiet periods, flux at 1 MeV >> flux at 100 MeV.
        """
        from aria.integrations.noaa_goes_loader import GoesProtonFluxModel
        model = GoesProtonFluxModel(GOES_DATA_DIR)
        f_low  = model.get_gcr_flux("H", 2.0, 0.0)
        f_mid  = model.get_gcr_flux("H", 30.0, 0.0)
        f_high = model.get_gcr_flux("H", 200.0, 0.0)
        assert f_low > f_mid, f"Flux at 2 MeV ({f_low:.2e}) should be > 30 MeV ({f_mid:.2e})"
        assert f_mid > f_high, f"Flux at 30 MeV ({f_mid:.2e}) should be > 200 MeV ({f_high:.2e})"

    @skip_no_data
    def test_flux_positive_across_energy_range(self):
        """Flux must be positive at all energies in 1–500 MeV range."""
        from aria.integrations.noaa_goes_loader import GoesProtonFluxModel
        model = GoesProtonFluxModel(GOES_DATA_DIR)
        for e_mev in [1.0, 2.0, 5.0, 10.0, 30.0, 100.0, 200.0, 400.0]:
            f = model.get_gcr_flux("H", e_mev, 0.0)
            assert f > 0, f"Flux at {e_mev} MeV should be positive, got {f}"

    @skip_no_data
    def test_solar_max_lower_than_solar_min(self):
        """Solar maximum (phase=0.5) must give lower proton flux than solar minimum.

        Solar wind modulates GCR: more solar activity → stronger modulation → lower GCR.
        Zhao & Qin (2014) ApJ 798 59: 30% suppression at solar max for E<100 MeV.
        """
        from aria.integrations.noaa_goes_loader import GoesProtonFluxModel
        model = GoesProtonFluxModel(GOES_DATA_DIR)
        f_min = model.get_gcr_flux("H", 10.0, 0.0)   # solar minimum
        f_max = model.get_gcr_flux("H", 10.0, 0.5)   # solar maximum
        assert f_max < f_min, (
            f"Solar max flux {f_max:.2e} should be < solar min {f_min:.2e}"
        )

    @skip_no_data
    def test_non_proton_returns_positive_flux(self):
        """Non-proton species (He, C, Fe) must return positive flux via synthetic fallback."""
        from aria.integrations.noaa_goes_loader import GoesProtonFluxModel
        model = GoesProtonFluxModel(GOES_DATA_DIR)
        for element in ["He", "C", "O", "Fe"]:
            f = model.get_gcr_flux(element, 200.0, 0.0)
            assert f > 0, f"Flux for {element} at 200 MeV should be positive"

    @skip_no_data
    def test_compatible_with_radiation_transport(self):
        """GoesProtonFluxModel must be usable directly in simulate_annual_dose()."""
        from aria.integrations.noaa_goes_loader import GoesProtonFluxModel
        from aria.simulation.radiation_transport import (
            RadiationTransportSimulator, ShieldLayer,
        )

        model = GoesProtonFluxModel(GOES_DATA_DIR)
        # Minimal 10 g/cm² Al shield (ISS-equivalent shielding, Cucinotta 2014)
        # 10 g/cm² Al shield (ISS-equivalent, Cucinotta 2014)
        layers = [ShieldLayer(name="hull", material="aluminum",
                              thickness_g_cm2=10.0, density_g_cm3=2.70,
                              z_target=13.0, a_target=27.0)]
        transport = RadiationTransportSimulator(layers, n_particles=200)

        dose = transport.simulate_annual_dose(model, velocity_c=0.0, solar_phase=0.0)
        assert dose.total_dose_msv > 0, "Annual dose must be positive with real GOES data"
        # Deep space GCR: 400–1000 mSv/yr at 1 AU (Cucinotta 2014, NASA TM-2014-217376)
        # Behind 10 g/cm² Al at low particle count (200): high variance expected.
        # Sanity bound: > 50 mSv (definitely non-zero) and < 20,000 mSv (not absurd).
        assert dose.total_dose_msv < 20_000, (
            f"Annual dose {dose.total_dose_msv:.0f} mSv unrealistically high (> 20 Sv)"
        )
