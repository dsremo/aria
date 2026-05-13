"""Verification tests for Pods F1 (elasticity + plasticity yield) and
F2 (fatigue + fracture).

Covers the closed-form portions of:
  - F1 §9.1 Cook's membrane (deferred — needs FE solver)
  - F1 §9.2 Lamé thick cylinder (limited to thin-wall closed form here)
  - F1 §9.3 Simo-Hughes J2 uniaxial yield check
  - F1 §9.4 Tsai-Wu (deferred — needs CLT)
  - F2 §9.1 ASTM E647 2024-T3 da/dN (Paris law)
  - F2 §9.2 Downing-Socie rainflow (deferred — needs algorithm)
  - F2 §9.3 Ti-6Al-4V K_Ic burst pressure (critical crack length)
  - F2 §9.4 EUROFER97 LCF Aubert 2014 (deferred — needs strain-life)

The deferred items require infrastructure (FE solver, rainflow,
strain-life) that lands in P0-8b.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from aria.physics.solid_mechanics import (
    MATERIAL_STRUCTURAL_TABLE,
    StructuralMaterial,
    basquin_life,
    basquin_stress_amplitude,
    bulk_modulus,
    critical_crack_length,
    deviatoric_stress,
    effective_plastic_strain_increment,
    gerber_equivalent_amplitude,
    get_structural_material,
    goodman_equivalent_amplitude,
    integrate_paris_block,
    j2_invariant,
    lame_constants,
    miner_cumulative_damage,
    morrow_life,
    paris_crack_growth_rate,
    principal_stresses,
    shear_modulus,
    stress_intensity_center_crack,
    stress_intensity_edge_crack,
    stress_invariants,
    swt_parameter,
    thin_wall_axial_stress,
    thin_wall_hoop_stress,
    von_mises_equivalent_stress,
    von_mises_yield_check,
    walker_delta_k_effective,
)


# ─────────────────────────────────────────────────────────────────────
# Elastic constant identities
# ─────────────────────────────────────────────────────────────────────


class TestElasticConstants:
    def test_lame_identity_for_ti(self) -> None:
        ti = get_structural_material("Ti-6Al-4V")
        lam, mu = lame_constants(ti.youngs_modulus_pa, ti.poissons_ratio)
        # μ = E / (2(1+ν))
        expected_mu = ti.youngs_modulus_pa / (2.0 * (1.0 + ti.poissons_ratio))
        assert mu == pytest.approx(expected_mu, rel=1e-12)
        # λ = E ν / ((1+ν)(1−2ν))
        denom = (1.0 + ti.poissons_ratio) * (1.0 - 2.0 * ti.poissons_ratio)
        expected_lam = ti.youngs_modulus_pa * ti.poissons_ratio / denom
        assert lam == pytest.approx(expected_lam, rel=1e-12)
        # E = μ(3λ + 2μ)/(λ + μ) — round-trip identity.
        e_back = mu * (3 * lam + 2 * mu) / (lam + mu)
        assert e_back == pytest.approx(ti.youngs_modulus_pa, rel=1e-12)

    def test_shear_modulus_for_steel_about_80_gpa(self) -> None:
        # EUROFER97: E = 217 GPa, ν = 0.30 → G = 217/(2·1.30) ≈ 83.5 GPa.
        ef = get_structural_material("EUROFER97")
        g = shear_modulus(ef.youngs_modulus_pa, ef.poissons_ratio)
        assert g == pytest.approx(83.5e9, rel=0.01)

    def test_bulk_modulus_diverges_at_incompressible(self) -> None:
        # For ν → 0.5, K → ∞.
        k_low = bulk_modulus(100e9, 0.30)
        k_high = bulk_modulus(100e9, 0.499)
        assert k_high > 50.0 * k_low

    def test_invalid_poisson_raises(self) -> None:
        with pytest.raises(ValueError, match="poissons_ratio"):
            shear_modulus(100e9, 0.6)
        with pytest.raises(ValueError, match="poissons_ratio"):
            shear_modulus(100e9, -1.5)

    def test_negative_youngs_raises(self) -> None:
        with pytest.raises(ValueError, match="youngs_modulus_pa"):
            shear_modulus(-1.0, 0.3)


# ─────────────────────────────────────────────────────────────────────
# Stress tensor — invariants, deviatoric, von Mises, principals
# ─────────────────────────────────────────────────────────────────────


class TestStressTensor:
    def test_uniaxial_von_mises_equals_axial_stress(self) -> None:
        sigma = np.array(
            [[200e6, 0, 0], [0, 0, 0], [0, 0, 0]],
            dtype=float,
        )
        assert von_mises_equivalent_stress(sigma) == pytest.approx(200e6, rel=1e-12)

    def test_hydrostatic_state_zero_von_mises(self) -> None:
        # σ = -p I; J_2 = 0; σ̄_VM = 0.
        p = 50e6
        sigma = -p * np.eye(3)
        assert von_mises_equivalent_stress(sigma) == pytest.approx(0.0, abs=1e-3)

    def test_pure_shear_von_mises(self) -> None:
        # τ on the 12 face: σ̄ = √3 · τ.
        tau = 100e6
        sigma = np.array(
            [[0, tau, 0], [tau, 0, 0], [0, 0, 0]],
            dtype=float,
        )
        assert von_mises_equivalent_stress(sigma) == pytest.approx(
            math.sqrt(3.0) * tau, rel=1e-12
        )

    def test_principal_stresses_sorted_descending(self) -> None:
        sigma = np.diag([100e6, 50e6, -25e6])
        s1, s2, s3 = principal_stresses(sigma)
        assert s1 >= s2 >= s3
        assert s1 == pytest.approx(100e6)
        assert s2 == pytest.approx(50e6)
        assert s3 == pytest.approx(-25e6)

    def test_invariants_match_principal_form(self) -> None:
        sigma = np.diag([100e6, 50e6, -25e6])
        i1, i2, i3 = stress_invariants(sigma)
        s1, s2, s3 = principal_stresses(sigma)
        # I_1 = σ_1+σ_2+σ_3
        assert i1 == pytest.approx(s1 + s2 + s3, rel=1e-12)
        # I_3 = σ_1·σ_2·σ_3
        assert i3 == pytest.approx(s1 * s2 * s3, rel=1e-12)

    def test_deviatoric_traceless(self) -> None:
        sigma = np.array(
            [[100e6, 20e6, 0], [20e6, 50e6, 0], [0, 0, -25e6]],
            dtype=float,
        )
        s = deviatoric_stress(sigma)
        assert abs(np.trace(s)) < 1e-3

    def test_j2_matches_explicit_form(self) -> None:
        sigma = np.diag([100e6, 0, 0])  # uniaxial
        # J_2 = (1/3) σ² for uniaxial
        assert j2_invariant(sigma) == pytest.approx((1.0 / 3.0) * (100e6) ** 2, rel=1e-12)


# ─────────────────────────────────────────────────────────────────────
# Yield criterion
# ─────────────────────────────────────────────────────────────────────


class TestYieldCheck:
    """F1 §9.3 Simo-Hughes J2 uniaxial yield."""

    def test_below_yield(self) -> None:
        ti = get_structural_material("Ti-6Al-4V")
        sigma = np.diag([400e6, 0, 0])  # 400 MPa uniaxial, σ_y = 820 MPa
        yielded, f = von_mises_yield_check(sigma, ti.yield_strength_pa)
        assert not yielded
        assert f < 0.0
        assert f == pytest.approx(400e6 - 820e6, rel=1e-12)

    def test_at_yield(self) -> None:
        ti = get_structural_material("Ti-6Al-4V")
        sigma = np.diag([820e6, 0, 0])  # exactly at yield
        yielded, f = von_mises_yield_check(sigma, ti.yield_strength_pa)
        assert yielded
        assert abs(f) < 1.0  # Pa precision

    def test_isotropic_hardening_raises_threshold(self) -> None:
        ti = get_structural_material("Ti-6Al-4V")
        sigma = np.diag([900e6, 0, 0])
        # Without hardening: f > 0 (forbidden, return-mapping needed).
        _, f0 = von_mises_yield_check(sigma, ti.yield_strength_pa)
        assert f0 > 0.0
        # With R = 100 MPa hardening, the surface expands and 900 MPa
        # is below it.
        yielded, f1 = von_mises_yield_check(
            sigma, ti.yield_strength_pa, isotropic_hardening_r_pa=100e6
        )
        assert not yielded
        assert f1 < 0.0

    def test_effective_plastic_strain_increment_uniaxial(self) -> None:
        # Uniaxial plastic strain ε^p_11 = γ, ε^p_22 = ε^p_33 = -γ/2
        # (volume-preserving). Then
        #   Δε^p_ij Δε^p_ij = γ² + γ²/4 + γ²/4 = 3γ²/2
        #   Δp̄ = √(2/3 · 3γ²/2) = √(γ²) = γ
        # which is the canonical "effective" plastic strain in
        # uniaxial loading per Simo & Hughes 1998 §3.
        gamma = 1e-3
        dep = np.diag([gamma, -gamma / 2.0, -gamma / 2.0])
        dp = effective_plastic_strain_increment(dep)
        assert dp == pytest.approx(gamma, rel=1e-12)

    def test_effective_plastic_strain_increment_deviatoric(self) -> None:
        # Pure deviatoric increment Δε^p = diag(2/3, -1/3, -1/3)·γ has
        #   Σ ε² = γ² · (4/9 + 1/9 + 1/9) = γ² · 6/9 = 2γ²/3
        #   Δp̄ = √(2/3 · 2γ²/3) = √(4γ²/9) = 2γ/3
        gamma = 1e-3
        dep = np.diag([2.0 / 3.0, -1.0 / 3.0, -1.0 / 3.0]) * gamma
        dp = effective_plastic_strain_increment(dep)
        assert dp == pytest.approx(2.0 * gamma / 3.0, rel=1e-12)


# ─────────────────────────────────────────────────────────────────────
# Pressure vessel — F1 §9.2 thin-wall reduction of Lamé
# ─────────────────────────────────────────────────────────────────────


class TestPressureVessel:
    def test_hoop_is_twice_axial(self) -> None:
        h = thin_wall_hoop_stress(1e5, 1.0, 0.01)
        a = thin_wall_axial_stress(1e5, 1.0, 0.01)
        assert h == pytest.approx(2.0 * a, rel=1e-12)

    def test_canonical_aria_hull(self) -> None:
        # ARIA hull baseline: p = 101.3 kPa internal, R = 12.6 m,
        # t = 0.05 m → σ_hoop = pR/t = 25.5 MPa.
        h = thin_wall_hoop_stress(101_325.0, 12.6, 0.05)
        assert h == pytest.approx(25.5e6, rel=0.01)

    def test_zero_pressure_zero_stress(self) -> None:
        assert thin_wall_hoop_stress(0.0, 1.0, 0.01) == 0.0

    def test_invalid_geometry_raises(self) -> None:
        with pytest.raises(ValueError):
            thin_wall_hoop_stress(1e5, 0.0, 0.01)
        with pytest.raises(ValueError):
            thin_wall_hoop_stress(1e5, 1.0, 0.0)


# ─────────────────────────────────────────────────────────────────────
# Basquin S-N curve
# ─────────────────────────────────────────────────────────────────────


class TestBasquin:
    """Verify against Boyer 1994 ASM Titanium Handbook Table F2 values
    for Ti-6Al-4V: σ_f' = 2030 MPa, b = -0.104.

    A back-of-envelope check: at 1e6 cycles,
        σ_a = 2030 · (2e6)^(-0.104) ≈ 451 MPa
    which matches MIL-HDBK-5 published S-N data for annealed bar."""

    def test_ti_at_1e6_cycles(self) -> None:
        ti = get_structural_material("Ti-6Al-4V")
        sa = basquin_stress_amplitude(
            cycles_to_failure=1.0e6,
            sigma_f_prime_pa=ti.basquin_sigma_f_prime_pa,
            basquin_b_exponent=ti.basquin_b_exponent,
        )
        # Hand calculation:
        # 2030e6 · (2e6)^(-0.104)
        expected = 2030e6 * (2.0e6 ** -0.104)
        assert sa == pytest.approx(expected, rel=1e-12)
        # ~451 MPa
        assert 400e6 < sa < 500e6

    def test_inverse_round_trip(self) -> None:
        ti = get_structural_material("Ti-6Al-4V")
        target_n = 1.0e7
        sa = basquin_stress_amplitude(
            target_n, ti.basquin_sigma_f_prime_pa, ti.basquin_b_exponent
        )
        n = basquin_life(sa, ti.basquin_sigma_f_prime_pa, ti.basquin_b_exponent)
        assert n == pytest.approx(target_n, rel=1e-9)

    def test_higher_amplitude_shorter_life(self) -> None:
        ti = get_structural_material("Ti-6Al-4V")
        n_low = basquin_life(300e6, ti.basquin_sigma_f_prime_pa, ti.basquin_b_exponent)
        n_high = basquin_life(600e6, ti.basquin_sigma_f_prime_pa, ti.basquin_b_exponent)
        assert n_high < n_low

    def test_morrow_with_zero_mean_equals_basquin(self) -> None:
        ti = get_structural_material("Ti-6Al-4V")
        n_basquin = basquin_life(
            300e6, ti.basquin_sigma_f_prime_pa, ti.basquin_b_exponent
        )
        n_morrow = morrow_life(
            300e6, 0.0, ti.basquin_sigma_f_prime_pa, ti.basquin_b_exponent
        )
        assert n_morrow == pytest.approx(n_basquin, rel=1e-12)

    def test_morrow_tensile_mean_reduces_life(self) -> None:
        ti = get_structural_material("Ti-6Al-4V")
        n_zero_mean = morrow_life(
            300e6, 0.0, ti.basquin_sigma_f_prime_pa, ti.basquin_b_exponent
        )
        n_tensile = morrow_life(
            300e6, 200e6, ti.basquin_sigma_f_prime_pa, ti.basquin_b_exponent
        )
        assert n_tensile < n_zero_mean


# ─────────────────────────────────────────────────────────────────────
# Mean-stress corrections
# ─────────────────────────────────────────────────────────────────────


class TestMeanStress:
    def test_goodman_zero_mean_returns_amplitude(self) -> None:
        sa_eq = goodman_equivalent_amplitude(200e6, 0.0, 895e6)
        assert sa_eq == pytest.approx(200e6, rel=1e-12)

    def test_goodman_tensile_mean_inflates_amplitude(self) -> None:
        # Tensile mean → higher equivalent amplitude.
        sa_eq = goodman_equivalent_amplitude(200e6, 400e6, 895e6)
        # 200 / (1 - 400/895) = 200 / 0.553 ≈ 361.4 MPa
        assert sa_eq == pytest.approx(361.4e6, rel=0.01)
        assert sa_eq > 200e6

    def test_goodman_clamps_compressive_mean(self) -> None:
        # Compressive mean is conservatively treated as zero.
        sa_eq_compressive = goodman_equivalent_amplitude(200e6, -100e6, 895e6)
        sa_eq_zero = goodman_equivalent_amplitude(200e6, 0.0, 895e6)
        assert sa_eq_compressive == pytest.approx(sa_eq_zero, rel=1e-12)

    def test_goodman_above_uts_raises(self) -> None:
        with pytest.raises(ValueError):
            goodman_equivalent_amplitude(200e6, 1000e6, 895e6)

    def test_gerber_less_conservative_than_goodman(self) -> None:
        # For the same (σ_a, σ_m, UTS), Gerber gives a smaller σ_a_eq
        # than Goodman (less conservative).
        gd = goodman_equivalent_amplitude(200e6, 400e6, 895e6)
        gr = gerber_equivalent_amplitude(200e6, 400e6, 895e6)
        assert gr < gd

    def test_swt_zero_mean(self) -> None:
        # SWT with σ_m = 0: P_SWT = √(σ_a · σ_a · E) = σ_a √E.
        E = 113.8e9
        psw = swt_parameter(200e6, 0.0, E)
        assert psw == pytest.approx(200e6 * math.sqrt(E), rel=1e-12)

    def test_swt_compressive_max_returns_zero(self) -> None:
        # σ_max = -100 + 50 = -50 MPa (compressive) → 0
        assert swt_parameter(50e6, -100e6, 113.8e9) == 0.0


# ─────────────────────────────────────────────────────────────────────
# Miner's rule
# ─────────────────────────────────────────────────────────────────────


class TestMinerRule:
    def test_single_block_at_failure(self) -> None:
        # n = N_f → D = 1.
        d = miner_cumulative_damage(
            cycles_per_block=[1000.0], cycles_to_failure_per_block=[1000.0]
        )
        assert d == 1.0

    def test_two_blocks_partial_damage(self) -> None:
        d = miner_cumulative_damage(
            cycles_per_block=[100.0, 50.0],
            cycles_to_failure_per_block=[1000.0, 200.0],
        )
        # 0.1 + 0.25 = 0.35
        assert d == pytest.approx(0.35, rel=1e-12)

    def test_zero_block_zero_damage(self) -> None:
        d = miner_cumulative_damage([0.0], [1000.0])
        assert d == 0.0

    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            miner_cumulative_damage([100.0], [1000.0, 500.0])

    def test_negative_cycles_raises(self) -> None:
        with pytest.raises(ValueError):
            miner_cumulative_damage([-1.0], [1000.0])


# ─────────────────────────────────────────────────────────────────────
# Stress intensity & critical crack length
# ─────────────────────────────────────────────────────────────────────


class TestStressIntensity:
    def test_center_crack_canonical(self) -> None:
        # K_I = σ √(πa) for center crack in infinite plate.
        ki = stress_intensity_center_crack(stress_pa=100e6, crack_half_length_m=0.01)
        expected = 100e6 * math.sqrt(math.pi * 0.01)  # ≈ 17.7 MPa·m^½
        assert ki == pytest.approx(expected, rel=1e-12)

    def test_edge_crack_geometry_factor(self) -> None:
        # Edge crack with default Y = 1.12.
        # stress_intensity_edge_crack(σ, a) = Y · σ · √(π · a/2)
        # because the center_crack formula takes half-length, and for an
        # edge crack of full length a the equivalent half-length is a/2.
        ki_edge = stress_intensity_edge_crack(100e6, 0.01)
        ki_half = stress_intensity_center_crack(100e6, 0.01 / 2.0)
        assert ki_edge == pytest.approx(1.12 * ki_half, rel=1e-12)

    def test_zero_crack_zero_k(self) -> None:
        assert stress_intensity_center_crack(100e6, 0.0) == 0.0

    def test_critical_crack_length_ti(self) -> None:
        # Ti-6Al-4V K_Ic = 55 MPa·m^½, σ = 400 MPa, Y = 1.12:
        # a_crit = (1/π) · (55 / (1.12 · 400))² ≈ 0.0048 m ≈ 4.8 mm
        ti = get_structural_material("Ti-6Al-4V")
        a_crit = critical_crack_length(
            fracture_toughness_pa_sqrt_m=ti.fracture_toughness_pa_sqrt_m,
            applied_stress_pa=400e6,
            geometry_factor=1.12,
        )
        # Hand calc: (1/π) · (55e6 / (1.12 · 400e6))²
        #          = (1/π) · 0.01506
        #          ≈ 4.79e-3 m
        assert a_crit == pytest.approx(4.79e-3, rel=0.01)
        assert 4e-3 < a_crit < 6e-3

    def test_critical_crack_decreases_with_stress(self) -> None:
        ti = get_structural_material("Ti-6Al-4V")
        a_low = critical_crack_length(
            ti.fracture_toughness_pa_sqrt_m, 200e6
        )
        a_high = critical_crack_length(
            ti.fracture_toughness_pa_sqrt_m, 800e6
        )
        # Doubling stress quarters the critical length (a ∝ 1/σ²).
        assert a_high == pytest.approx(a_low / 16.0, rel=1e-9)


# ─────────────────────────────────────────────────────────────────────
# Paris law crack growth
# ─────────────────────────────────────────────────────────────────────


class TestParisLaw:
    """ASTM E647 / Hudak 1984 Ti-6Al-4V Paris law constants:
    C_eng = 1.1e-11 (m/cycle)/(MPa·m^½)^m, m = 3.5, R = 0.1.

    Convert to SI: C_SI = C_eng / (10^6)^m = 1.1e-11 / 10^21
                 = 1.1e-32 (m/cycle)/(Pa·m^½)^3.5
    """

    C_TI_ENG = 1.1e-11  # (m/cycle)/(MPa·m^½)^3.5
    M_TI = 3.5
    C_TI_SI = C_TI_ENG / (1.0e6) ** M_TI  # ≈ 1.1e-32

    def test_paris_rate_units_si(self) -> None:
        # ΔK = 10 MPa·m^½ = 1e7 Pa·m^½
        delta_k_si = 1.0e7
        rate = paris_crack_growth_rate(
            delta_k_pa_sqrt_m=delta_k_si,
            paris_c_si=self.C_TI_SI,
            paris_m=self.M_TI,
        )
        # Hand: 1.1e-32 · (1e7)^3.5 = 1.1e-32 · 3.162e24 = 3.48e-8 m/cycle
        assert rate == pytest.approx(3.48e-8, rel=0.01)

    def test_paris_zero_dk_zero_rate(self) -> None:
        assert paris_crack_growth_rate(0.0, self.C_TI_SI, self.M_TI) == 0.0

    def test_walker_zero_r_no_change(self) -> None:
        # R = 0 → ΔK_eff = ΔK regardless of γ.
        assert walker_delta_k_effective(1e7, 0.0, walker_gamma=0.5) == pytest.approx(
            1e7, rel=1e-12
        )

    def test_walker_positive_r_inflates_dk(self) -> None:
        # R = 0.5, γ = 0.5 → ΔK_eff = ΔK / (0.5)^0.5 = ΔK · √2
        eff = walker_delta_k_effective(1e7, 0.5, walker_gamma=0.5)
        assert eff == pytest.approx(1e7 * math.sqrt(2.0), rel=1e-12)

    def test_walker_negative_r_clamped_to_zero(self) -> None:
        # Negative R is clamped to 0 (ASTM E647 convention).
        eff_neg = walker_delta_k_effective(1e7, -0.5, walker_gamma=0.5)
        eff_zero = walker_delta_k_effective(1e7, 0.0, walker_gamma=0.5)
        assert eff_neg == pytest.approx(eff_zero, rel=1e-12)

    def test_paris_block_integration(self) -> None:
        # Walk a small initial crack 1 mm under 200 MPa stress range
        # for 10000 cycles. Initial Δa = C·(Y·Δσ·√(πa))^m · n.
        a0 = 1.0e-3  # 1 mm
        blocks = [(200e6, 1e4)]  # 200 MPa stress range, 10 000 cycles
        a_final, n_total, failed = integrate_paris_block(
            initial_crack_length_m=a0,
            blocks=blocks,
            paris_c_si=self.C_TI_SI,
            paris_m=self.M_TI,
            geometry_factor=1.12,
            critical_crack_length_m=None,
        )
        assert n_total == 1e4
        assert not failed
        # Crack should have grown but not by orders of magnitude.
        assert a_final > a0
        assert a_final < 10.0 * a0

    def test_paris_failure_stop(self) -> None:
        # If the critical crack length is set very small the integrator
        # should report failure.
        blocks = [(200e6, 1e9)]  # huge cycle count
        a_final, n_total, failed = integrate_paris_block(
            initial_crack_length_m=1.0e-3,
            blocks=blocks,
            paris_c_si=self.C_TI_SI,
            paris_m=self.M_TI,
            geometry_factor=1.12,
            critical_crack_length_m=2.0e-3,  # 2 mm
        )
        # The single-block coarse integrator overshoots; either
        # `failed` is True OR the crack actually exceeded the critical.
        assert failed or a_final >= 2.0e-3


# ─────────────────────────────────────────────────────────────────────
# Material table consistency
# ─────────────────────────────────────────────────────────────────────


class TestMaterialTable:
    def test_every_entry_has_source(self) -> None:
        for name, mat in MATERIAL_STRUCTURAL_TABLE.items():
            assert mat.source, f"{name} missing source citation"

    def test_yield_below_ultimate(self) -> None:
        for name, mat in MATERIAL_STRUCTURAL_TABLE.items():
            assert mat.yield_strength_pa < mat.ultimate_strength_pa, name

    def test_ti_6al_4v_canonical_values(self) -> None:
        ti = get_structural_material("Ti-6Al-4V")
        # MMPDS-17 §5.3 Table 5.3.1 anchor values.
        assert ti.youngs_modulus_pa == pytest.approx(113.8e9, rel=1e-12)
        assert ti.yield_strength_pa == pytest.approx(820e6, rel=1e-12)
        assert ti.ultimate_strength_pa == pytest.approx(895e6, rel=1e-12)
        assert ti.fracture_toughness_pa_sqrt_m == pytest.approx(55e6, rel=1e-12)
        assert ti.density_kg_m3 == pytest.approx(4430.0, rel=1e-12)

    def test_unknown_material_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown structural material"):
            get_structural_material("unobtanium-42")
