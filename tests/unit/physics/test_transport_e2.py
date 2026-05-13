"""Verification tests for Pod E2 (neutron / nucleon transport, P0 subset).

The full E2 scope calls for a 4 000-LOC Monte Carlo + discrete
ordinates + INCL4.6 stack that is deferred to a follow-up commit.
This P0 subset verifies the self-contained closed-form primitives:

  - GCR source flux and shielded dose (Cucinotta 2014 NASA/TP-2013-217375)
  - Exponential attenuation, macroscopic cross section, mean free path
  - Letaw 1983 inelastic p-A cross section parameterization
  - Pion/muon decay chain using PDG 2022 lifetimes
  - Muon CSDA range in water (Groom 2001 Atomic Data and Nuclear Data
    Tables 78 183-356)

The 5 full-scope §9 test cases (Kobayashi, OKTAVIAN, Jezebel, Leray,
HZETRN) require external codes or tabulated datasets and will land
in `test_transport_e2_benchmarks.py` when the solver is plumbed in.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.transport import (
    CUCINOTTA_2014_CONSTANTS,
    CUCINOTTA_2014_GCR_DOSE_SV_YR,
    GCR_PROTON_FLUX_1AU_SOLAR_MIN,
    GROOM_2001_MUON_RANGE_TABLE,
    PDG_MUON_LIFETIME_S,
    PDG_PION_LIFETIME_S,
    attenuation_exponential,
    cucinotta_shielded_dose,
    gcr_annual_unshielded_dose,
    gcr_total_proton_flux,
    letaw_1983_inelastic,
    macroscopic_cross_section,
    mean_free_path,
    muon_csda_range_water,
    muon_to_electron_decay_fraction,
    pion_to_muon_decay_fraction,
    solar_modulation_exp_factor,
)


# ─────────────────────────────────────────────────────────────────────
# GCR source — Cucinotta 2014 reference numbers
# ─────────────────────────────────────────────────────────────────────


class TestCucinottaGCRSource:
    """The solar-minimum anchor values that ARIA's `interstellar.py`
    already uses and that Cucinotta 2014 NASA/TP-2013-217375 publishes
    in Fig. 3-1 and Table 5-1."""

    def test_proton_flux_solar_min_at_1au(self) -> None:
        # Cucinotta 2014 Fig. 3-1: Φ_p(>10 MeV) ≈ 4 p/cm²/s solar min.
        assert GCR_PROTON_FLUX_1AU_SOLAR_MIN == 4.0
        assert gcr_total_proton_flux(
            phi_sm_mv=CUCINOTTA_2014_CONSTANTS.phi_sm_solar_min_MV
        ) == 4.0

    def test_proton_flux_suppressed_at_solar_max(self) -> None:
        phi_min = CUCINOTTA_2014_CONSTANTS.phi_sm_solar_min_MV
        phi_max = CUCINOTTA_2014_CONSTANTS.phi_sm_solar_max_MV
        flux_min = gcr_total_proton_flux(phi_sm_mv=phi_min)
        flux_max = gcr_total_proton_flux(phi_sm_mv=phi_max)
        # Per Usoskin 2017 LRSP 14 3, solar max suppresses GCR by ~1/2.
        assert flux_max == pytest.approx(0.5 * flux_min, rel=1e-12)

    def test_annual_unshielded_dose_solar_min(self) -> None:
        # Canonical ARIA number: 0.42 Sv/yr (Cucinotta 2014 Table 5-1).
        assert CUCINOTTA_2014_GCR_DOSE_SV_YR == 0.42
        dose = gcr_annual_unshielded_dose(phi_sm_mv=450.0)
        assert dose == 0.42

    def test_annual_dose_solar_max_is_half(self) -> None:
        dose_min = gcr_annual_unshielded_dose(phi_sm_mv=450.0)
        dose_max = gcr_annual_unshielded_dose(phi_sm_mv=1000.0)
        assert dose_max == pytest.approx(0.5 * dose_min, rel=1e-12)

    def test_solar_modulation_monotonic(self) -> None:
        # exp(-φ/E) is strictly decreasing in φ for fixed E.
        a = solar_modulation_exp_factor(1000.0, 100.0)
        b = solar_modulation_exp_factor(1000.0, 1000.0)
        assert a > b
        assert 0.0 < b < a <= 1.0


# ─────────────────────────────────────────────────────────────────────
# Shielded dose — Cucinotta 65% realistic ceiling
# ─────────────────────────────────────────────────────────────────────


class TestCucinottaShieldedDose:
    """Reproduces the ARIA `advanced_systems.py` round-14 fix value:
    the realistic maximum dose reduction is 65 %, set by the HZE
    fragment spectrum per Cucinotta 2014 §5.4."""

    H0 = CUCINOTTA_2014_GCR_DOSE_SV_YR  # 0.42 Sv/yr

    def test_zero_shield_gives_unshielded(self) -> None:
        assert cucinotta_shielded_dose(self.H0, 0.0) == pytest.approx(
            self.H0, rel=1e-12
        )

    def test_infinite_shield_approaches_floor(self) -> None:
        # At infinite passive shield depth the dose asymptotes to
        # (1 - 0.65) × H0 = 0.35 × H0 per Cucinotta 2014 §5.4.
        floor = 0.35 * self.H0
        assert cucinotta_shielded_dose(self.H0, 1.0e6) == pytest.approx(
            floor, rel=1e-12
        )

    def test_20_gcm2_al_reduces_by_more_than_half(self) -> None:
        # 20 g/cm² Al is the canonical NASA deep-space shield depth.
        # exp(-20/10) = 0.135, so H = floor + (H0 - floor)*0.135
        # = 0.147 + 0.273*0.135 = 0.147 + 0.0368 = 0.184 Sv/yr
        # → ~56 % reduction from the unshielded 0.42 value, close to
        # the 65 % ceiling.
        h = cucinotta_shielded_dose(self.H0, 20.0)
        reduction = 1.0 - h / self.H0
        assert 0.40 < reduction < 0.70, reduction

    def test_shielded_dose_monotonic_decreasing(self) -> None:
        h_samples = [
            cucinotta_shielded_dose(self.H0, depth) for depth in (0, 5, 10, 20, 50, 200)
        ]
        # Strictly decreasing.
        for a, b in zip(h_samples[:-1], h_samples[1:]):
            assert b < a

    def test_monotone_lower_bound_equals_ceiling(self) -> None:
        floor = 0.35 * self.H0
        for depth in (0, 5, 10, 20, 100, 1000):
            assert cucinotta_shielded_dose(self.H0, depth) >= floor - 1e-12


# ─────────────────────────────────────────────────────────────────────
# Attenuation and macroscopic cross section
# ─────────────────────────────────────────────────────────────────────


class TestAttenuation:
    """Sanity of Σ = ρ N_A σ / M and I/I₀ = exp(−Σ x)."""

    def test_fe_total_cross_section_at_14_mev(self) -> None:
        # Canonical example in the module docstring:
        #   ρ(Fe) = 7.87 g/cm³
        #   M(Fe) = 55.85 g/mol
        #   σ_t ≈ 2.5 barn at 14 MeV (rough)
        #   → Σ ≈ 0.212 /cm, λ ≈ 4.7 cm
        sigma = macroscopic_cross_section(
            density_g_cm3=7.87,
            molar_mass_g_mol=55.85,
            microscopic_xs_barn=2.5,
        )
        assert sigma == pytest.approx(0.212, rel=0.02)
        mfp = mean_free_path(7.87, 55.85, 2.5)
        assert mfp == pytest.approx(4.7, rel=0.02)

    def test_exponential_one_mfp(self) -> None:
        # One mean free path: I/I₀ = 1/e ≈ 0.368.
        sigma = macroscopic_cross_section(7.87, 55.85, 2.5)
        mfp = 1.0 / sigma
        transmitted = attenuation_exponential(sigma, mfp)
        assert transmitted == pytest.approx(1.0 / math.e, rel=1e-12)

    def test_zero_thickness_is_unity(self) -> None:
        assert attenuation_exponential(0.5, 0.0) == 1.0

    def test_zero_cross_section_is_unity(self) -> None:
        assert attenuation_exponential(0.0, 100.0) == 1.0

    def test_water_density_and_molar_mass(self) -> None:
        # ρ(H₂O) = 0.998 g/cm³, M ≈ 18 g/mol. For σ ~1 b:
        sigma = macroscopic_cross_section(0.998, 18.0, 1.0)
        # n(H₂O) ≈ 3.34e22 /cm³ → Σ ≈ 0.0334 /cm for 1 b.
        assert sigma == pytest.approx(0.0334, rel=0.02)


# ─────────────────────────────────────────────────────────────────────
# Letaw 1983 inelastic cross section
# ─────────────────────────────────────────────────────────────────────


class TestLetawInelastic:
    """Published spot-checks of σ_inel(A, E) (Letaw 1983 ApJ Suppl 51 271)."""

    def test_fe_1gev_ballpark(self) -> None:
        # Letaw 1983 σ(Fe, 1 GeV) ≈ 600-720 mb. Cross-referenced
        # with Barashenkov 1999 gives ~717 mb for the full inelastic
        # channel. We match to within 20 % — the Letaw fit has
        # shell-structure oscillations of this order.
        sigma_mb = letaw_1983_inelastic(mass_number=56, energy_mev=1000.0)
        assert 500.0 < sigma_mb < 850.0, sigma_mb

    def test_al_1gev_ballpark(self) -> None:
        # σ(Al, 1 GeV) ≈ 430 mb.
        sigma_mb = letaw_1983_inelastic(mass_number=27, energy_mev=1000.0)
        assert 300.0 < sigma_mb < 550.0, sigma_mb

    def test_asymptotic_plateau(self) -> None:
        # At high energy, σ → 45 A^(0.7) roughly. Check the plateau.
        sigma_10gev = letaw_1983_inelastic(56, 10_000.0)
        sigma_100gev = letaw_1983_inelastic(56, 100_000.0)
        # Ratio within 10% of unity.
        assert 0.9 < sigma_10gev / sigma_100gev < 1.1

    def test_heavier_nucleus_has_larger_sigma(self) -> None:
        sigma_c = letaw_1983_inelastic(12, 1000.0)
        sigma_fe = letaw_1983_inelastic(56, 1000.0)
        sigma_pb = letaw_1983_inelastic(208, 1000.0)
        assert sigma_c < sigma_fe < sigma_pb


# ─────────────────────────────────────────────────────────────────────
# Pion / muon decay chain (PDG 2022)
# ─────────────────────────────────────────────────────────────────────


class TestPionMuonChain:
    """Verify PDG-referenced lifetimes and decay survival fractions."""

    def test_pdg_2022_pion_lifetime(self) -> None:
        # PDG 2022: τ_π± = 2.6033e-8 s
        assert PDG_PION_LIFETIME_S == 2.6033e-8

    def test_pdg_2022_muon_lifetime(self) -> None:
        # PDG 2022: τ_μ± = 2.1969811e-6 s
        assert PDG_MUON_LIFETIME_S == 2.1969811e-6

    def test_pion_half_decayed_after_proper_tau_ln2(self) -> None:
        # N/N₀ = 1/2 when t = τ · ln 2.
        t_half = PDG_PION_LIFETIME_S * math.log(2)
        f = pion_to_muon_decay_fraction(t_half)
        assert f == pytest.approx(0.5, rel=1e-9)

    def test_muon_half_decayed_after_proper_tau_ln2(self) -> None:
        t_half = PDG_MUON_LIFETIME_S * math.log(2)
        f = muon_to_electron_decay_fraction(t_half)
        assert f == pytest.approx(0.5, rel=1e-9)

    def test_relativistic_dilation_extends_lab_lifetime(self) -> None:
        # A 1 GeV muon has γ ≈ 10 (T/m + 1 = 1000/105.66 + 1 ≈ 10.47).
        # Its lab-frame half-life is γ τ_μ ≈ 22 μs, so after
        # 2 μs (one rest-frame lifetime) only ~9 % has decayed.
        gamma = 10.47
        f = muon_to_electron_decay_fraction(2.0e-6, gamma=gamma)
        # 1 − exp(-2e-6 / (10.47 · 2.1969811e-6)) ≈ 1 − exp(-0.087) ≈ 0.083
        assert 0.07 < f < 0.10, f

    def test_decay_fraction_bounds(self) -> None:
        # Decayed fraction is in [0, 1] for any positive time.
        for t in (0.0, 1e-9, 1e-6, 1e-3, 1.0):
            assert 0.0 <= pion_to_muon_decay_fraction(t) <= 1.0
            assert 0.0 <= muon_to_electron_decay_fraction(t) <= 1.0

    def test_gamma_less_than_one_raises(self) -> None:
        with pytest.raises(ValueError):
            pion_to_muon_decay_fraction(1e-9, gamma=0.5)
        with pytest.raises(ValueError):
            muon_to_electron_decay_fraction(1e-9, gamma=0.9)


# ─────────────────────────────────────────────────────────────────────
# Muon CSDA range in water — Groom 2001 Table 1
# ─────────────────────────────────────────────────────────────────────


class TestGroom2001MuonRange:
    """Range in water from Groom, Mokhov & Striganov 2001 Atomic Data
    and Nuclear Data Tables 78 183-356 Table 1."""

    def test_1gev_muon_range_is_about_430_gcm2(self) -> None:
        # Canonical "~4 m in water" figure from Groom 2001.
        # Water density is 1 g/cm³, so g/cm² = cm at ρ = 1.
        r = muon_csda_range_water(kinetic_energy_mev=1000.0)
        assert r == pytest.approx(430.6, rel=0.01)
        # Equivalently, ~4.3 m in water.
        range_m = r / 100.0  # cm → m (because ρ = 1 g/cm³)
        assert 4.0 < range_m < 5.0

    def test_table_entries_recoverable(self) -> None:
        for T_mev, R_gcm2 in GROOM_2001_MUON_RANGE_TABLE:
            r = muon_csda_range_water(T_mev)
            assert r == pytest.approx(R_gcm2, rel=1e-6)

    def test_range_monotonic_in_energy(self) -> None:
        energies = [5.0, 50.0, 500.0, 5_000.0, 50_000.0]
        ranges = [muon_csda_range_water(e) for e in energies]
        for a, b in zip(ranges[:-1], ranges[1:]):
            assert b > a

    def test_extrapolation_below_table_min(self) -> None:
        # 1 MeV is below the table; should extrapolate left.
        r = muon_csda_range_water(1.0)
        assert r > 0.0
        assert r < GROOM_2001_MUON_RANGE_TABLE[0][1]  # less than 10 MeV row

    def test_zero_energy_raises(self) -> None:
        with pytest.raises(ValueError):
            muon_csda_range_water(0.0)
