"""Verification tests for Pod F5 (thermal expansion and thermal stress).

Covers the five test cases from `docs/pods/F5_thermal_stress.md` §9
plus invariant checks on sign conventions and material-table
consistency.

  9.1 Ti-6Al-4V 1 m bar, ΔT = 300 K, σ = −E α ΔT = −294 MPa
  9.2 Al 7075-T6 plane-stress plate, ΔT = 100 K, σ = −251 MPa
  9.3 EUROFER97 10 mm plate, linear gradient 293→373 K,
      σ_max = ±(E α ΔT)/(2(1−ν)) ≈ 131.4 MPa
  9.4 Bimetallic strip (Timoshenko 1925), κ = 1.50 1/m
  9.5 Ti-6Al-4V radiator shutdown, ΔT_crit = σ_UTS(1−ν)/(Eα) ≈ 601 K
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from aria.physics.thermal_stress import (
    MATERIAL_CTE_TABLE,
    bimetallic_curvature,
    get_material_properties,
    linear_gradient_peak_stress,
    linear_gradient_stress_profile,
    linear_thermal_strain,
    plane_stress_constrained,
    thermal_shock_delta_t_crit,
    thermal_shock_margin,
    thermal_strain_anisotropic,
    thermal_strain_tensor,
    triaxial_constrained_stress,
    uniaxial_constrained_stress,
)


# ─────────────────────────────────────────────────────────────────────
# Test 9.1 — Ti-6Al-4V 1 m bar, both ends fixed, ΔT = +300 K
# Source: Boley & Weiner 1960 §3.1 worked example; MMPDS-17 for constants
# ─────────────────────────────────────────────────────────────────────


class TestTi64RestrainedBar:
    """F5 §9.1 — the simplest closed-form test of σ = −E α ΔT."""

    DELTA_T_K = 300.0

    def test_uniaxial_stress_matches_closed_form(self) -> None:
        ti = get_material_properties("Ti-6Al-4V")  # MMPDS-17 values
        sigma = uniaxial_constrained_stress(
            youngs_modulus_pa=ti.youngs_modulus_pa,
            cte_k_inv=ti.cte_k_inv,
            delta_t_k=self.DELTA_T_K,
        )
        # −113.8 GPa · 8.6e-6 · 300 = −293.6 MPa
        assert sigma == pytest.approx(-293.6e6, rel=5e-3)
        # Sign is compressive (heating a restrained bar).
        assert sigma < 0.0

    def test_free_expansion_strain(self) -> None:
        # If the bar were free, it would strain by α · ΔT.
        ti = get_material_properties("Ti-6Al-4V")
        eps = linear_thermal_strain(
            cte_k_inv=ti.cte_k_inv,
            temperature_k=293.15 + self.DELTA_T_K,
        )
        # 8.6e-6 · 300 = 2.58e-3 → 2.58 mm over a 1 m bar.
        assert eps == pytest.approx(2.58e-3, rel=5e-3)
        length_change_m = eps * 1.0
        assert length_change_m == pytest.approx(2.58e-3, abs=1e-5)

    def test_cooling_produces_tension(self) -> None:
        ti = get_material_properties("Ti-6Al-4V")
        sigma = uniaxial_constrained_stress(
            youngs_modulus_pa=ti.youngs_modulus_pa,
            cte_k_inv=ti.cte_k_inv,
            delta_t_k=-100.0,  # cooling
        )
        assert sigma > 0.0  # tensile on a restrained bar that is cooled


# ─────────────────────────────────────────────────────────────────────
# Test 9.2 — Al 7075-T6 plane-stress plate, ΔT = 100 K
# Source: Timoshenko & Goodier 1970 §150 p. 445
# ─────────────────────────────────────────────────────────────────────


class TestAlPlaneStress:
    """F5 §9.2 — biaxial plane-stress constrained plate."""

    DELTA_T_K = 100.0
    AL = get_material_properties("Al-7075-T6")
    PUBLISHED_SIGMA_PA = -251e6  # Scope §9.2 expected value

    def test_plane_stress_matches_closed_form(self) -> None:
        sigma = plane_stress_constrained(
            youngs_modulus_pa=self.AL.youngs_modulus_pa,
            cte_k_inv=self.AL.cte_k_inv,
            delta_t_k=self.DELTA_T_K,
            poissons_ratio=self.AL.poissons_ratio,
        )
        # −71.7e9 · 23.4e-6 · 100 / (1 − 0.33)
        # = −71.7e9 · 23.4e-6 · 100 / 0.67
        # = −167_778 / 0.67 ≈ −250_415 ≈ −250 MPa
        expected = (
            -self.AL.youngs_modulus_pa
            * self.AL.cte_k_inv
            * self.DELTA_T_K
            / (1.0 - self.AL.poissons_ratio)
        )
        assert sigma == pytest.approx(expected, rel=1e-12)
        assert sigma == pytest.approx(-250e6, rel=0.01)

    def test_plane_stress_greater_in_magnitude_than_uniaxial(self) -> None:
        # The (1−ν) factor makes the plane-stress value larger than
        # the uniaxial value by 1/(1−ν) ≈ 1.49×.
        uni = uniaxial_constrained_stress(
            self.AL.youngs_modulus_pa, self.AL.cte_k_inv, self.DELTA_T_K
        )
        biax = plane_stress_constrained(
            self.AL.youngs_modulus_pa,
            self.AL.cte_k_inv,
            self.DELTA_T_K,
            self.AL.poissons_ratio,
        )
        ratio = abs(biax) / abs(uni)
        assert ratio == pytest.approx(1.0 / (1.0 - self.AL.poissons_ratio), rel=1e-12)

    def test_triaxial_larger_still(self) -> None:
        # The fully confined case gets the (1−2ν) factor → even larger.
        tri = triaxial_constrained_stress(
            self.AL.youngs_modulus_pa,
            self.AL.cte_k_inv,
            self.DELTA_T_K,
            self.AL.poissons_ratio,
        )
        biax = plane_stress_constrained(
            self.AL.youngs_modulus_pa,
            self.AL.cte_k_inv,
            self.DELTA_T_K,
            self.AL.poissons_ratio,
        )
        assert abs(tri) > abs(biax)


# ─────────────────────────────────────────────────────────────────────
# Test 9.3 — EUROFER97 10 mm plate with linear through-thickness
# temperature gradient 293 K (inner) → 373 K (outer)
# Source: Boley & Weiner 1960 §10.4 closed form
# ─────────────────────────────────────────────────────────────────────


class TestEuroferLinearGradient:
    """F5 §9.3 — through-thickness Boley-Weiner result."""

    INNER_T_K = 293.0
    OUTER_T_K = 373.0

    def test_peak_stress_closed_form(self) -> None:
        ef = get_material_properties("EUROFER97")
        sigma = linear_gradient_peak_stress(
            youngs_modulus_pa=ef.youngs_modulus_pa,
            cte_k_inv=ef.cte_k_inv,
            delta_t_outer_inner_k=self.OUTER_T_K - self.INNER_T_K,
            poissons_ratio=ef.poissons_ratio,
        )
        # E α ΔT / (2(1−ν)) = 217e9 · 10.6e-6 · 80 / (2·0.70)
        #                    = 1.840e8 / 1.4
        #                    ≈ 131.4 MPa
        # (Note: the scope note says 64 MPa — that's an arithmetic
        # error in the scope. The Boley-Weiner §10.4 formula gives
        # 131 MPa for these exact numbers. TODO: correct the scope text.)
        expected = (
            ef.youngs_modulus_pa
            * ef.cte_k_inv
            * 80.0
            / (2.0 * (1.0 - ef.poissons_ratio))
        )
        assert sigma == pytest.approx(expected, rel=1e-12)
        assert sigma == pytest.approx(131.4e6, rel=0.005)

    def test_profile_antisymmetric_about_midplane(self) -> None:
        # The Boley-Weiner result is pure bending: σ(+z) = −σ(−z)
        # and σ(0) = 0.
        ef = get_material_properties("EUROFER97")
        z, sigma = linear_gradient_stress_profile(
            youngs_modulus_pa=ef.youngs_modulus_pa,
            cte_k_inv=ef.cte_k_inv,
            inner_temperature_k=self.INNER_T_K,
            outer_temperature_k=self.OUTER_T_K,
            poissons_ratio=ef.poissons_ratio,
            n_samples=11,
        )
        # Midplane stress is zero.
        assert sigma[5] == pytest.approx(0.0, abs=1e-6)
        # Antisymmetric: σ(-z) = -σ(+z).
        for i in range(5):
            assert sigma[i] == pytest.approx(-sigma[10 - i], rel=1e-12)
        # Peak magnitude at the outer surface matches the closed form.
        peak = linear_gradient_peak_stress(
            ef.youngs_modulus_pa,
            ef.cte_k_inv,
            self.OUTER_T_K - self.INNER_T_K,
            ef.poissons_ratio,
        )
        assert abs(sigma[-1]) == pytest.approx(peak, rel=1e-12)
        assert abs(sigma[0]) == pytest.approx(peak, rel=1e-12)


# ─────────────────────────────────────────────────────────────────────
# Test 9.4 — Bimetallic strip curvature (Timoshenko 1925)
# Source: Timoshenko 1925 J. Opt. Soc. Am. 11(3) 233-255 Eq. (9)
# ─────────────────────────────────────────────────────────────────────


class TestBimetallicStrip:
    """F5 §9.4 — classical Timoshenko 1925 bimetal result."""

    def test_equal_layers_equal_moduli(self) -> None:
        # α_1 = 10e-6, α_2 = 20e-6, E_1 = E_2 = 100 GPa, each layer
        # 0.5 mm thick → total 1 mm, ΔT = 100 K.
        kappa = bimetallic_curvature(
            cte_1_k_inv=10.0e-6,
            cte_2_k_inv=20.0e-6,
            youngs_modulus_1_pa=100e9,
            youngs_modulus_2_pa=100e9,
            thickness_1_m=0.5e-3,
            thickness_2_m=0.5e-3,
            delta_t_k=100.0,
        )
        # Timoshenko 1925 Eq. (9) → κ = 1.50 1/m for this geometry.
        assert kappa == pytest.approx(1.50, rel=0.005)

    def test_curvature_proportional_to_delta_t(self) -> None:
        def kappa_for(dt: float) -> float:
            return bimetallic_curvature(
                10e-6, 20e-6, 100e9, 100e9, 0.5e-3, 0.5e-3, dt
            )

        assert kappa_for(200.0) == pytest.approx(2.0 * kappa_for(100.0), rel=1e-12)

    def test_equal_cte_gives_zero_curvature(self) -> None:
        # If both layers have the same CTE, the strip stays flat.
        kappa = bimetallic_curvature(
            cte_1_k_inv=15e-6,
            cte_2_k_inv=15e-6,
            youngs_modulus_1_pa=100e9,
            youngs_modulus_2_pa=100e9,
            thickness_1_m=0.5e-3,
            thickness_2_m=0.5e-3,
            delta_t_k=100.0,
        )
        assert kappa == pytest.approx(0.0, abs=1e-15)

    def test_sign_follows_higher_cte_layer(self) -> None:
        # Swapping which layer has the higher CTE should flip the sign.
        pos = bimetallic_curvature(10e-6, 20e-6, 100e9, 100e9, 0.5e-3, 0.5e-3, 100.0)
        neg = bimetallic_curvature(20e-6, 10e-6, 100e9, 100e9, 0.5e-3, 0.5e-3, 100.0)
        assert pos == pytest.approx(-neg, rel=1e-12)


# ─────────────────────────────────────────────────────────────────────
# Test 9.5 — Thermal shock margin on Ti-6Al-4V radiator shutdown
# Source: Kingery 1955 J. Am. Ceram. Soc. 38, 3 + MMPDS-17 constants
# ─────────────────────────────────────────────────────────────────────


class TestRadiatorThermalShock:
    """F5 §9.5 — Kingery figure of merit for the radiator shutdown."""

    def test_delta_t_crit_for_ti_6al_4v(self) -> None:
        ti = get_material_properties("Ti-6Al-4V")
        dt_crit = thermal_shock_delta_t_crit(
            fracture_strength_pa=ti.ultimate_strength_pa,
            youngs_modulus_pa=ti.youngs_modulus_pa,
            cte_k_inv=ti.cte_k_inv,
            poissons_ratio=ti.poissons_ratio,
        )
        # 895e6 · (1 − 0.342) / (113.8e9 · 8.6e-6)
        # = 5.89e8 / 9.787e5
        # ≈ 601 K
        expected = (
            ti.ultimate_strength_pa
            * (1.0 - ti.poissons_ratio)
            / (ti.youngs_modulus_pa * ti.cte_k_inv)
        )
        assert dt_crit == pytest.approx(expected, rel=1e-12)
        assert dt_crit == pytest.approx(601.0, rel=0.02)

    def test_margin_for_250k_shock(self) -> None:
        ti = get_material_properties("Ti-6Al-4V")
        margin = thermal_shock_margin(
            fracture_strength_pa=ti.ultimate_strength_pa,
            youngs_modulus_pa=ti.youngs_modulus_pa,
            cte_k_inv=ti.cte_k_inv,
            poissons_ratio=ti.poissons_ratio,
            delta_t_applied_k=250.0,
        )
        # 601 / 250 ≈ 2.4 — safe margin per scope P0-6
        assert margin == pytest.approx(2.4, rel=0.05)
        assert margin > 2.0  # safe margin for spacecraft structural metal

    def test_margin_raises_on_zero_applied_shock(self) -> None:
        ti = get_material_properties("Ti-6Al-4V")
        with pytest.raises(ValueError):
            thermal_shock_margin(
                ti.ultimate_strength_pa,
                ti.youngs_modulus_pa,
                ti.cte_k_inv,
                ti.poissons_ratio,
                delta_t_applied_k=0.0,
            )


# ─────────────────────────────────────────────────────────────────────
# Additional invariant checks
# ─────────────────────────────────────────────────────────────────────


class TestThermalStrain:
    def test_isotropic_strain_is_diagonal(self) -> None:
        eps = thermal_strain_tensor(
            cte_k_inv=10e-6, temperature_k=500.0, reference_temperature_k=300.0
        )
        assert eps.shape == (3, 3)
        # Diagonal = α·ΔT.
        for i in range(3):
            assert eps[i, i] == pytest.approx(10e-6 * 200.0, rel=1e-12)
        # Off-diagonal zero.
        assert abs(eps[0, 1]) < 1e-15
        assert abs(eps[0, 2]) < 1e-15
        assert abs(eps[1, 2]) < 1e-15

    def test_reference_temperature_gives_zero_strain(self) -> None:
        eps = linear_thermal_strain(
            cte_k_inv=10e-6, temperature_k=293.15
        )
        assert eps == 0.0

    def test_anisotropic_non_symmetric_raises(self) -> None:
        alpha = np.array(
            [[10e-6, 1e-6, 0.0], [2e-6, 20e-6, 0.0], [0.0, 0.0, 30e-6]]
        )
        with pytest.raises(ValueError, match="symmetric"):
            thermal_strain_anisotropic(alpha, 400.0, 293.15)

    def test_anisotropic_diagonal_case_matches_isotropic(self) -> None:
        # A diagonal α tensor with all entries equal reproduces the
        # isotropic thermal_strain_tensor result.
        alpha = 10e-6 * np.eye(3)
        eps_aniso = thermal_strain_anisotropic(alpha, 500.0, 300.0)
        eps_iso = thermal_strain_tensor(10e-6, 500.0, 300.0)
        assert np.allclose(eps_aniso, eps_iso, atol=1e-15)


class TestMaterialTable:
    def test_every_entry_has_a_source(self) -> None:
        for name, mat in MATERIAL_CTE_TABLE.items():
            assert mat.source, f"material {name} missing source citation"
            assert mat.cte_k_inv > 0.0, f"{name} CTE must be positive"
            assert mat.youngs_modulus_pa > 0.0, f"{name} E must be positive"
            assert 0.0 <= mat.poissons_ratio < 0.5

    def test_ti_6al_4v_mmpds_values(self) -> None:
        ti = get_material_properties("Ti-6Al-4V")
        # MMPDS-17 §5.3 (typical annealed bar):
        #   α = 8.6e-6 /K  (20-200 °C)
        #   E = 113.8 GPa
        #   ν = 0.342
        assert ti.cte_k_inv == pytest.approx(8.6e-6, rel=1e-12)
        assert ti.youngs_modulus_pa == pytest.approx(113.8e9, rel=1e-12)
        assert ti.poissons_ratio == pytest.approx(0.342, rel=1e-12)

    def test_unknown_material_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown material"):
            get_material_properties("unobtanium-42")
