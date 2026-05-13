"""Verification tests for Pod D1 (MHD + fusion plasma primitives).

Covers the closed-form portions of the D1 scope:
  - Plasma physics constants (CODATA 2018 + SI 2019)
  - Alfvén speed and ITER-scale magnitude
  - Ion gyroradius for a 10 keV deuteron in 5.3 T
  - Plasma beta and Troyon limit cross-check
  - Spitzer resistivity at 1 keV and 10 keV reference points
  - Kruskal-Shafranov safety-factor gate
  - Greenwald density limit for ITER baseline
  - Eich heat-flux width regression
  - Dreicer runaway field
  - Rosenbluth-Putvinski ITER avalanche amplification ~10^16
"""

from __future__ import annotations

import math

import pytest

from aria.physics.mhd_plasma import (
    ITER_BASELINE,
    PLASMA_CONSTANTS,
    alfven_speed,
    dreicer_field,
    eich_lambda_q,
    greenwald_density_limit,
    ion_gyroradius,
    kruskal_shafranov_limit_ok,
    plasma_beta,
    rosenbluth_putvinski_avalanche,
    spitzer_resistivity,
    troyon_beta_limit,
)
from aria.physics.mhd_plasma.constants import (
    kelvin_to_temperature_ev,
    temperature_ev_to_kelvin,
)


# ─────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────


class TestPlasmaConstants:
    def test_exact_si_2019_values(self) -> None:
        assert PLASMA_CONSTANTS.c_m_s == 2.99792458e8
        assert PLASMA_CONSTANTS.e_c == 1.602176634e-19
        assert PLASMA_CONSTANTS.k_b_j_k == 1.380649e-23

    def test_codata_2018_masses(self) -> None:
        assert PLASMA_CONSTANTS.m_p_kg == 1.67262192369e-27
        assert PLASMA_CONSTANTS.m_e_kg == 9.1093837015e-31

    def test_dt_mean_mass(self) -> None:
        # (m_d + m_t)/2 ≈ 4.175e-27 kg
        assert PLASMA_CONSTANTS.m_dt_avg_kg == pytest.approx(4.175e-27, rel=1e-3)

    def test_ev_kelvin_roundtrip(self) -> None:
        t_ev = 1_000.0
        t_k = temperature_ev_to_kelvin(t_ev)
        # 1 eV = 11604.52 K (e/k_B)
        assert t_k == pytest.approx(11_604_518.12, rel=1e-6)
        assert kelvin_to_temperature_ev(t_k) == pytest.approx(t_ev, rel=1e-12)


# ─────────────────────────────────────────────────────────────────────
# Alfvén speed, gyroradius, beta
# ─────────────────────────────────────────────────────────────────────


class TestIdealMHD:
    def test_alfven_speed_iter_scale(self) -> None:
        # ITER-scale numbers: B = 5.3 T, n = 10²⁰ m⁻³ D-T
        # ρ = n · m_DT = 10²⁰ · 4.175e-27 = 4.175e-7 kg/m³
        # v_A = 5.3 / sqrt(μ₀ · 4.175e-7)
        #     = 5.3 / sqrt(5.246e-13)
        #     ≈ 5.3 / 7.24e-7
        #     ≈ 7.31e6 m/s
        rho = 1e20 * PLASMA_CONSTANTS.m_dt_avg_kg
        v_a = alfven_speed(5.3, rho)
        # ITER Alfvén speed is ~7 × 10⁶ m/s (Freidberg 2014 §7 cite).
        assert 5e6 < v_a < 1e7, v_a

    def test_alfven_scales_with_field(self) -> None:
        v_a_low = alfven_speed(1.0, 1e-6)
        v_a_high = alfven_speed(2.0, 1e-6)
        assert v_a_high == pytest.approx(2.0 * v_a_low, rel=1e-12)

    def test_alfven_inverse_sqrt_density(self) -> None:
        v_a_sparse = alfven_speed(1.0, 1e-6)
        v_a_dense = alfven_speed(1.0, 4e-6)
        # v_A ∝ 1/√ρ → 4× density = 1/2 Alfvén speed
        assert v_a_dense == pytest.approx(v_a_sparse / 2.0, rel=1e-12)

    def test_gyroradius_10kev_deuteron_in_5_3t(self) -> None:
        # 10 keV deuteron: v_⊥ = √(2 · e · T / m_d) = √(2 · 1.6e-19 ·
        # 10000 / 3.344e-27) ≈ 9.79e5 m/s
        # ρ_i = m v_⊥ / (e B) = 3.344e-27 · 9.79e5 / (1.6e-19 · 5.3)
        #     ≈ 3.87e-3 m ≈ 3.87 mm
        m_d = PLASMA_CONSTANTS.m_d_kg
        v_perp = math.sqrt(2.0 * PLASMA_CONSTANTS.e_c * 10_000.0 / m_d)
        rho_i = ion_gyroradius(
            ion_mass_kg=m_d,
            perpendicular_velocity_m_s=v_perp,
            charge_number=1,
            magnetic_field_t=5.3,
        )
        # 2-5 mm ballpark for reactor-relevant conditions.
        assert 2e-3 < rho_i < 5e-3, rho_i

    def test_plasma_beta_canonical(self) -> None:
        # n = 10²⁰, T = 10 keV each species → p = 2 n e T_eV
        n = 1e20
        t_ev = 10_000.0
        # Pressure: p = 2 n k T = 2 n (e · T_eV) since k T = e T_eV
        p = 2.0 * n * PLASMA_CONSTANTS.e_c * t_ev
        beta = plasma_beta(p, 5.3)
        # Should be a few percent for reactor conditions.
        assert 0.005 < beta < 0.05, beta


# ─────────────────────────────────────────────────────────────────────
# Spitzer resistivity
# ─────────────────────────────────────────────────────────────────────


class TestSpitzer:
    def test_1kev_pure_hydrogen(self) -> None:
        # T_e = 1 keV = 1000 eV, Z_eff = 1, ln Λ = 17
        # η = 1 · 5.2e-5 · 17 / 1000^1.5
        #   = 8.84e-4 / 31623
        #   ≈ 2.80e-8 Ω·m
        eta = spitzer_resistivity(electron_temperature_ev=1000.0, z_eff=1.0)
        assert eta == pytest.approx(2.80e-8, rel=0.01)

    def test_10kev_hydrogen(self) -> None:
        # T_e = 10 keV → η ≈ 8.84e-4 / 10^6 = 8.84e-10 Ω·m
        # (the Wesson canonical value is ~1e-9)
        eta = spitzer_resistivity(electron_temperature_ev=10_000.0, z_eff=1.0)
        assert 5e-10 < eta < 2e-9, eta

    def test_resistivity_drops_as_t_to_minus_3_halves(self) -> None:
        eta_1 = spitzer_resistivity(1000.0, 1.0)
        eta_10 = spitzer_resistivity(10_000.0, 1.0)
        # Ratio should be 10^(3/2) ≈ 31.6
        assert eta_1 / eta_10 == pytest.approx(10.0 ** 1.5, rel=1e-9)

    def test_zeff_scales_linearly(self) -> None:
        eta_pure = spitzer_resistivity(1000.0, 1.0)
        eta_dirty = spitzer_resistivity(1000.0, 2.0)
        assert eta_dirty == pytest.approx(2.0 * eta_pure, rel=1e-12)

    def test_invalid_inputs_raise(self) -> None:
        with pytest.raises(ValueError):
            spitzer_resistivity(0.0, 1.0)
        with pytest.raises(ValueError):
            spitzer_resistivity(1000.0, 0.5)


# ─────────────────────────────────────────────────────────────────────
# Operational limits
# ─────────────────────────────────────────────────────────────────────


class TestLimits:
    def test_kruskal_shafranov_gate(self) -> None:
        # Below the absolute onset q_a = 1 → not ok
        assert not kruskal_shafranov_limit_ok(0.5)
        # Exactly at the onset with default margin 2 → still not ok
        assert not kruskal_shafranov_limit_ok(1.0)
        # ITER operates with q_95 ≈ 3 → ok
        assert kruskal_shafranov_limit_ok(3.0)
        # Custom margin: if we only need > 1 (absolute onset)
        assert kruskal_shafranov_limit_ok(1.5, margin=1.0)

    def test_greenwald_iter(self) -> None:
        # ITER: I_p = 15 MA, a = 2.0 m → n_G = 15 / (π·4) = 1.194 × 10²⁰
        n_g = greenwald_density_limit(
            plasma_current_ma=ITER_BASELINE.plasma_current_ma,
            minor_radius_m=ITER_BASELINE.minor_radius_m,
        )
        assert n_g == pytest.approx(1.194, rel=0.01)

    def test_troyon_iter(self) -> None:
        # ITER: β_max = 2.8 · 15 / (2.0 · 5.3) = 3.96 %
        beta_pct = troyon_beta_limit(
            plasma_current_ma=ITER_BASELINE.plasma_current_ma,
            minor_radius_m=ITER_BASELINE.minor_radius_m,
            toroidal_field_t=ITER_BASELINE.toroidal_field_t,
        )
        assert beta_pct == pytest.approx(3.96, rel=0.01)

    def test_iter_baseline_fields(self) -> None:
        # Spot-check the baseline dataclass against ITER Physics Basis.
        assert ITER_BASELINE.major_radius_m == 6.2
        assert ITER_BASELINE.minor_radius_m == 2.0
        assert ITER_BASELINE.plasma_current_ma == 15.0
        assert ITER_BASELINE.toroidal_field_t == 5.3
        assert ITER_BASELINE.fusion_power_mw == 500.0
        assert "ITER Physics Basis 1999" in ITER_BASELINE.source


# ─────────────────────────────────────────────────────────────────────
# Eich heat-flux width
# ─────────────────────────────────────────────────────────────────────


class TestEich:
    def test_iter_baseline_lambda_q_in_expected_band(self) -> None:
        # Eich 2013 formula at ITER-like parameters gives sub-millimetre
        # λ_q (the narrow footprint that makes divertor design so hard).
        lambda_q = eich_lambda_q(
            poloidal_field_t=1.2,
            cylindrical_safety_factor=3.1,
            sol_power_mw=100.0,
        )
        # Eich 2013 Table 2 regression #14 gives ~0.4-0.5 mm at ITER
        # baseline; the "rough 1.7 mm" figure in some tertiary sources
        # comes from a different fit year and dataset mix.
        assert 0.3 < lambda_q < 2.0, lambda_q

    def test_lambda_q_weakly_depends_on_sol_power(self) -> None:
        # P^0.09 means 10× power only gives 10^0.09 ≈ 1.23× λ_q.
        low = eich_lambda_q(1.0, 3.0, 10.0)
        high = eich_lambda_q(1.0, 3.0, 100.0)
        ratio = high / low
        assert ratio == pytest.approx(10.0 ** 0.09, rel=1e-9)
        assert 1.2 < ratio < 1.3

    def test_lambda_q_scales_as_bp_minus_point_85(self) -> None:
        low_b = eich_lambda_q(1.0, 3.0, 100.0)
        high_b = eich_lambda_q(2.0, 3.0, 100.0)
        assert high_b / low_b == pytest.approx(2.0 ** -0.85, rel=1e-9)


# ─────────────────────────────────────────────────────────────────────
# Runaway electrons
# ─────────────────────────────────────────────────────────────────────


class TestRunawayElectrons:
    def test_dreicer_field_at_1_keV_matches_wesson(self) -> None:
        # Wesson 2011 §2.16 Table 2.16.1: E_D ≈ 44 V/m at
        # n_e = 10²⁰ m⁻³, T_e = 1 keV, ln Λ = 17. Hand calculation:
        #   E_D = n_e e³ lnΛ / (4π ε₀² T_e)
        #       = 10²⁰ · (1.6022e-19)³ · 17 /
        #         (4π · (8.854e-12)² · 1000 · 1.6022e-19)
        #       ≈ 44.3 V/m
        e_d = dreicer_field(
            electron_density_m3=1e20,
            electron_temperature_ev=1_000.0,
            coulomb_logarithm=17.0,
        )
        assert e_d == pytest.approx(44.3, rel=0.02), e_d

    def test_dreicer_field_at_10_keV(self) -> None:
        # E_D ∝ 1/T_e, so at 10 keV it should be ~4.43 V/m.
        e_d = dreicer_field(
            electron_density_m3=1e20,
            electron_temperature_ev=10_000.0,
            coulomb_logarithm=17.0,
        )
        assert e_d == pytest.approx(4.43, rel=0.02), e_d

    def test_dreicer_scales_linearly_in_density(self) -> None:
        low = dreicer_field(1e19, 10_000.0)
        high = dreicer_field(1e20, 10_000.0)
        assert high == pytest.approx(10.0 * low, rel=1e-12)

    def test_dreicer_scales_inverse_temperature(self) -> None:
        hot = dreicer_field(1e20, 20_000.0)
        cool = dreicer_field(1e20, 10_000.0)
        # E_D ∝ 1/T_e → doubling T halves the field
        assert hot == pytest.approx(0.5 * cool, rel=1e-12)

    def test_rosenbluth_putvinski_iter_amplification(self) -> None:
        # ITER: I_p = 15 MA, seed = 1 → exp(15 · 2.5) = exp(37.5)
        amp = rosenbluth_putvinski_avalanche(
            plasma_current_ma=15.0, seed_electrons=1.0
        )
        # Hand: exp(37.5) ≈ 1.94 × 10¹⁶
        assert amp == pytest.approx(math.exp(37.5), rel=1e-12)
        assert 1e16 < amp < 2e17

    def test_amplification_exponential_in_current(self) -> None:
        a_small = rosenbluth_putvinski_avalanche(plasma_current_ma=1.0)
        a_big = rosenbluth_putvinski_avalanche(plasma_current_ma=2.0)
        # Ratio = exp(2.5) ≈ 12.18
        assert a_big / a_small == pytest.approx(math.exp(2.5), rel=1e-12)

    def test_zero_seed_zero_final(self) -> None:
        assert rosenbluth_putvinski_avalanche(15.0, seed_electrons=0.0) == 0.0

    def test_invalid_current_raises(self) -> None:
        with pytest.raises(ValueError):
            rosenbluth_putvinski_avalanche(0.0)


# ─────────────────────────────────────────────────────────────────────
# Cross-cutting ITER sanity
# ─────────────────────────────────────────────────────────────────────


class TestITERBaselineIntegration:
    """End-to-end sanity: ITER should sit *inside* the Greenwald and
    Troyon envelopes with reasonable margin, per ITER Physics Basis
    1999."""

    def test_iter_inside_greenwald_at_typical_density(self) -> None:
        n_g = greenwald_density_limit(15.0, 2.0)
        # ITER operates at n ~ 10²⁰ m⁻³; Greenwald limit is 1.194 ×
        # 10²⁰, so ITER sits at ~84% of n_G.
        operating_fraction = 1.0 / n_g
        assert 0.7 < operating_fraction < 0.95

    def test_iter_beta_below_troyon(self) -> None:
        beta_max = troyon_beta_limit(15.0, 2.0, 5.3)
        # ITER target β ≈ 2.5% is below Troyon 3.96%.
        assert beta_max > 2.5

    def test_iter_edge_q_95_safe(self) -> None:
        # q_95 = 3.0 is comfortably above the Kruskal-Shafranov onset.
        assert kruskal_shafranov_limit_ok(ITER_BASELINE.q_95_target)
