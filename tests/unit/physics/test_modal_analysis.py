"""Tests for structural modal analysis: beams, shells, plates, and resonance.

Validates:
1. Cantilever beam (clamped-free) fundamental frequency matches Blevins Table 8-1.
2. Pinned-pinned beam: f₁ = π²/(2πL²) × √(EI/ρA) (exact formula).
3. Axial frequency: clamped-free f₁ = c/(4L); clamped-clamped f₁ = c/(2L).
4. Ring frequency scales correctly with E, ρ, R.
5. Plate mode (1,1) frequency scales as thickness and inversely as area.
6. Critical spin speed: N_crit = 60 × f / k [RPM].
7. DMF at resonance = Q = 1/(2ζ) within 1%.
8. DMF off-resonance < Q.
9. hull_modal_budget returns finite positive frequencies.
10. Higher beam modes have higher frequencies.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.solid_mechanics import (
    HullModalBudget,
    ResonanceAmplification,
    beam_axial_frequency_hz,
    beam_flexural_frequency_hz,
    critical_spin_speed_rpm,
    cylindrical_shell_flexural_frequency_hz,
    cylindrical_shell_ring_frequency_hz,
    dynamic_magnification_factor,
    hull_modal_budget,
    plate_natural_frequency_hz,
)


# ── Material constants (Ti-6Al-4V, MMPDS-17) ──────────────────────────────────
_E_TI = 113.8e9   # Pa
_RHO_TI = 4430.0  # kg/m³
_NU_TI = 0.342

# Steel (AISI 304, MatWeb for convenient round numbers)
_E_STEEL = 200e9   # Pa
_RHO_STEEL = 7900.0  # kg/m³


class TestBeamFlexuralFrequency:
    """Euler-Bernoulli beam natural frequencies."""

    def test_cantilever_fundamental_order_of_magnitude(self):
        # 1 m steel beam 0.01 × 0.01 m cross section
        # I = bh³/12 = (0.01)⁴/12 ≈ 8.33e-10 m⁴; ρA = 7900 × 1e-4 = 0.79 kg/m
        I = (0.01 ** 4) / 12.0
        rho_a = _RHO_STEEL * 1e-4
        f = beam_flexural_frequency_hz(_E_STEEL, I, rho_a, 1.0, mode=1, boundary="clamped-free")
        # Blevins Table 8-1: f₁ = (1.8751)² / (2π) × √(EI/ρA) / L²
        beta_l = 1.8751
        f_expected = (beta_l ** 2) / (2 * math.pi) * math.sqrt(_E_STEEL * I / rho_a) / (1.0 ** 2)
        assert abs(f - f_expected) / f_expected < 1e-9, f"f={f:.3f} expected={f_expected:.3f}"

    def test_cantilever_reasonable_range(self):
        # 1 m long, 10 mm square steel beam → expect ~8–15 Hz
        I = (0.01 ** 4) / 12.0
        rho_a = _RHO_STEEL * 1e-4
        f = beam_flexural_frequency_hz(_E_STEEL, I, rho_a, 1.0, boundary="clamped-free")
        assert 5.0 < f < 30.0, f"f₁ cantilever = {f:.2f} Hz, expected 5–30 Hz"

    def test_pinned_pinned_exact_formula(self):
        # PP beam: f_n = n² π² / (2π L²) × √(EI/ρA)
        E, I, rho_a, L = 200e9, 1e-8, 5.0, 2.0
        f1 = beam_flexural_frequency_hz(E, I, rho_a, L, mode=1, boundary="pinned-pinned")
        f_expected = (math.pi ** 2) / (2 * math.pi * L ** 2) * math.sqrt(E * I / rho_a)
        assert abs(f1 - f_expected) / f_expected < 1e-9

    def test_higher_modes_higher_frequency(self):
        E, I, rho_a, L = 200e9, 1e-8, 5.0, 2.0
        f1 = beam_flexural_frequency_hz(E, I, rho_a, L, mode=1)
        f2 = beam_flexural_frequency_hz(E, I, rho_a, L, mode=2)
        f3 = beam_flexural_frequency_hz(E, I, rho_a, L, mode=3)
        assert f1 < f2 < f3

    def test_clamped_clamped_higher_than_cantilever(self):
        E, I, rho_a, L = _E_STEEL, 1e-8, 5.0, 1.0
        f_cf = beam_flexural_frequency_hz(E, I, rho_a, L, boundary="clamped-free")
        f_cc = beam_flexural_frequency_hz(E, I, rho_a, L, boundary="clamped-clamped")
        assert f_cc > f_cf

    def test_frequency_inversely_proportional_to_length_squared(self):
        # For mode 1: f ∝ 1/L² (C-F beam)
        E, I, rho_a = _E_STEEL, 1e-8, 5.0
        f1 = beam_flexural_frequency_hz(E, I, rho_a, 1.0)
        f2 = beam_flexural_frequency_hz(E, I, rho_a, 2.0)
        # f(L=1) / f(L=2) = 4 for same mode and BC
        ratio = f1 / f2
        assert abs(ratio - 4.0) < 0.01, f"ratio = {ratio:.3f}, expected 4.0"

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            beam_flexural_frequency_hz(200e9, 1e-8, 5.0, 1.0, mode=4)

    def test_invalid_boundary_raises(self):
        with pytest.raises(ValueError):
            beam_flexural_frequency_hz(200e9, 1e-8, 5.0, 1.0, boundary="unknown")

    def test_invalid_length_raises(self):
        with pytest.raises(ValueError):
            beam_flexural_frequency_hz(200e9, 1e-8, 5.0, 0.0)


class TestBeamAxialFrequency:
    """Longitudinal (axial) bar frequencies."""

    def test_clamped_free_quarter_wave(self):
        # f₁ = c / (4L) where c = √(E/ρ)
        E, rho, L = _E_STEEL, _RHO_STEEL, 1.0
        c = math.sqrt(E / rho)
        f_expected = c / (4.0 * L)
        f = beam_axial_frequency_hz(E, rho, L, "clamped-free")
        assert abs(f - f_expected) / f_expected < 1e-9

    def test_clamped_clamped_half_wave(self):
        E, rho, L = _E_STEEL, _RHO_STEEL, 1.0
        c = math.sqrt(E / rho)
        f_expected = c / (2.0 * L)
        f = beam_axial_frequency_hz(E, rho, L, "clamped-clamped")
        assert abs(f - f_expected) / f_expected < 1e-9

    def test_cc_double_cf(self):
        # clamped-clamped f₁ = 2 × clamped-free f₁
        E, rho, L = _E_STEEL, _RHO_STEEL, 2.0
        f_cf = beam_axial_frequency_hz(E, rho, L, "clamped-free")
        f_cc = beam_axial_frequency_hz(E, rho, L, "clamped-clamped")
        assert abs(f_cc / f_cf - 2.0) < 1e-9

    def test_steel_1m_bar_kilohertz_range(self):
        # Steel c ≈ 5031 m/s; clamped-free 1 m bar → f₁ ≈ 1258 Hz
        f = beam_axial_frequency_hz(_E_STEEL, _RHO_STEEL, 1.0, "clamped-free")
        assert 1000 < f < 2000, f"f₁ axial = {f:.0f} Hz, expected ~1258 Hz"


class TestCylindricalShellRingFrequency:
    """Ring (breathing) mode of cylindrical shell."""

    def test_ring_freq_positive(self):
        f = cylindrical_shell_ring_frequency_hz(_E_TI, _RHO_TI, 12.6, _NU_TI)
        assert f > 0.0

    def test_ring_freq_decreases_with_radius(self):
        # f_ring ∝ 1/R
        f1 = cylindrical_shell_ring_frequency_hz(_E_STEEL, _RHO_STEEL, 1.0)
        f2 = cylindrical_shell_ring_frequency_hz(_E_STEEL, _RHO_STEEL, 2.0)
        assert f1 > f2

    def test_ring_freq_inversely_proportional_to_radius(self):
        # f ∝ 1/R
        f1 = cylindrical_shell_ring_frequency_hz(_E_STEEL, _RHO_STEEL, 1.0)
        f2 = cylindrical_shell_ring_frequency_hz(_E_STEEL, _RHO_STEEL, 2.0)
        assert abs(f1 / f2 - 2.0) < 0.05  # within 5% of exact 2× due to ν correction

    def test_aria_hull_ring_hz_range(self):
        # ARIA hull: R=12.6 m Ti-6Al-4V → expect O(10) Hz
        f = cylindrical_shell_ring_frequency_hz(_E_TI, _RHO_TI, 12.6, _NU_TI)
        assert 1.0 < f < 1000.0, f"Ring freq = {f:.2f} Hz"


class TestCylindricalShellFlexuralFrequency:
    """Flexural modes of a simply-supported cylindrical shell (Donnell simplified)."""

    def test_positive_frequency(self):
        f = cylindrical_shell_flexural_frequency_hz(
            _E_STEEL, _RHO_STEEL, 1.0, 0.01, 5.0, n_circ=2, m_long=1
        )
        assert f > 0.0

    def test_higher_circ_number_increases_freq(self):
        f2 = cylindrical_shell_flexural_frequency_hz(
            _E_STEEL, _RHO_STEEL, 1.0, 0.01, 5.0, n_circ=2
        )
        f4 = cylindrical_shell_flexural_frequency_hz(
            _E_STEEL, _RHO_STEEL, 1.0, 0.01, 5.0, n_circ=4
        )
        assert f4 > f2

    def test_higher_longitudinal_mode_increases_freq(self):
        f1 = cylindrical_shell_flexural_frequency_hz(
            _E_STEEL, _RHO_STEEL, 1.0, 0.01, 5.0, m_long=1
        )
        f2 = cylindrical_shell_flexural_frequency_hz(
            _E_STEEL, _RHO_STEEL, 1.0, 0.01, 5.0, m_long=2
        )
        assert f2 > f1


class TestPlateNaturalFrequency:
    """Kirchhoff simply-supported plate natural frequencies."""

    def test_fundamental_mode_positive(self):
        f = plate_natural_frequency_hz(_E_STEEL, _RHO_STEEL, 0.01, 1.0, 1.0)
        assert f > 0.0

    def test_mode_11_less_than_mode_12(self):
        kw = dict(youngs_modulus_pa=_E_STEEL, density_kg_m3=_RHO_STEEL,
                  thickness_m=0.01, length_x_m=1.0, length_y_m=1.0)
        f11 = plate_natural_frequency_hz(**kw, mode_m=1, mode_n=1)
        f12 = plate_natural_frequency_hz(**kw, mode_m=1, mode_n=2)
        assert f12 > f11

    def test_square_plate_modes_symmetric(self):
        # For square plate: f(1,2) = f(2,1)
        kw = dict(youngs_modulus_pa=_E_STEEL, density_kg_m3=_RHO_STEEL,
                  thickness_m=0.01, length_x_m=1.0, length_y_m=1.0)
        f12 = plate_natural_frequency_hz(**kw, mode_m=1, mode_n=2)
        f21 = plate_natural_frequency_hz(**kw, mode_m=2, mode_n=1)
        assert abs(f12 - f21) < 1e-6

    def test_freq_scales_with_thickness(self):
        # f ∝ h (Kirchhoff): thicker plate → higher frequency
        kw = dict(youngs_modulus_pa=_E_STEEL, density_kg_m3=_RHO_STEEL,
                  length_x_m=1.0, length_y_m=1.0)
        f_thin = plate_natural_frequency_hz(**kw, thickness_m=0.005)
        f_thick = plate_natural_frequency_hz(**kw, thickness_m=0.010)
        assert f_thick > f_thin

    def test_freq_decreases_with_plate_size(self):
        kw = dict(youngs_modulus_pa=_E_STEEL, density_kg_m3=_RHO_STEEL, thickness_m=0.01)
        f_small = plate_natural_frequency_hz(**kw, length_x_m=0.5, length_y_m=0.5)
        f_large = plate_natural_frequency_hz(**kw, length_x_m=1.0, length_y_m=1.0)
        assert f_small > f_large

    def test_invalid_dimension_raises(self):
        with pytest.raises(ValueError):
            plate_natural_frequency_hz(_E_STEEL, _RHO_STEEL, 0.0, 1.0, 1.0)


class TestCriticalSpinSpeed:
    """Campbell diagram critical spin speed."""

    def test_first_harmonic(self):
        # N_crit = 60 × f / k; f=10 Hz, k=1 → 600 RPM
        N = critical_spin_speed_rpm(10.0, harmonic_order=1)
        assert abs(N - 600.0) < 1e-9

    def test_second_harmonic(self):
        N = critical_spin_speed_rpm(10.0, harmonic_order=2)
        assert abs(N - 300.0) < 1e-9

    def test_higher_harmonic_lower_critical_speed(self):
        N1 = critical_spin_speed_rpm(50.0, harmonic_order=1)
        N4 = critical_spin_speed_rpm(50.0, harmonic_order=4)
        assert N1 > N4

    def test_invalid_harmonic_raises(self):
        with pytest.raises(ValueError):
            critical_spin_speed_rpm(10.0, harmonic_order=0)


class TestDynamicMagnificationFactor:
    """DMF = Q = 1/(2ζ) at resonance; less elsewhere."""

    def test_at_resonance_dmf_equals_q(self):
        zeta = 0.02
        result = dynamic_magnification_factor(100.0, 100.0, zeta)
        Q = 1.0 / (2.0 * zeta)  # = 25
        assert abs(result.dmf - Q) / Q < 1e-9

    def test_quality_factor_attribute(self):
        zeta = 0.05
        result = dynamic_magnification_factor(50.0, 50.0, zeta)
        Q_expected = 1.0 / (2.0 * zeta)
        assert abs(result.quality_factor - Q_expected) < 1e-9

    def test_is_resonant_flag_at_resonance(self):
        result = dynamic_magnification_factor(100.0, 100.0, 0.02)
        assert result.is_resonant is True

    def test_is_resonant_false_far_from_resonance(self):
        result = dynamic_magnification_factor(50.0, 100.0, 0.02)
        assert result.is_resonant is False

    def test_dmf_less_than_q_off_resonance(self):
        zeta = 0.02
        Q = 1.0 / (2.0 * zeta)
        # Far below resonance: DMF ≈ 1
        result_low = dynamic_magnification_factor(1.0, 100.0, zeta)
        assert result_low.dmf < Q
        # Far above resonance: DMF → 0
        result_high = dynamic_magnification_factor(1000.0, 100.0, zeta)
        assert result_high.dmf < Q

    def test_dmf_near_1_at_dc(self):
        # ω → 0: DMF = 1/√(1) = 1.0
        result = dynamic_magnification_factor(0.001, 100.0, 0.02)
        assert abs(result.dmf - 1.0) < 0.01

    def test_frequency_ratio_attribute(self):
        result = dynamic_magnification_factor(30.0, 60.0, 0.02)
        assert abs(result.frequency_ratio - 0.5) < 1e-9

    def test_invalid_damping_raises(self):
        with pytest.raises(ValueError):
            dynamic_magnification_factor(100.0, 100.0, 0.0)

    def test_invalid_natural_freq_raises(self):
        with pytest.raises(ValueError):
            dynamic_magnification_factor(100.0, 0.0, 0.02)


class TestHullModalBudget:
    """Integration test for ARIA hull modal audit."""

    def test_returns_hull_modal_budget(self):
        result = hull_modal_budget()
        assert isinstance(result, HullModalBudget)

    def test_all_frequencies_positive(self):
        b = hull_modal_budget()
        assert b.ring_breathing_hz > 0.0
        assert b.truss_panel_hz > 0.0
        assert b.beam_mode1_hz > 0.0

    def test_beam_mode_lower_than_ring(self):
        # Long beam (100 m) fundamental is lower than the ring breathing mode
        b = hull_modal_budget()
        assert b.beam_mode1_hz < b.ring_breathing_hz

    def test_notes_is_list(self):
        b = hull_modal_budget()
        assert isinstance(b.notes, list)

    def test_custom_geometry(self):
        # Smaller radius → higher ring frequency
        b_small = hull_modal_budget(hull_radius_m=5.0)
        b_large = hull_modal_budget(hull_radius_m=20.0)
        assert b_small.ring_breathing_hz > b_large.ring_breathing_hz
