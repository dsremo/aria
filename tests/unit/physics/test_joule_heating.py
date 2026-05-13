"""Tests for Joule heating and eddy current loss models.

Validates:
1.  resistivity_at_temperature: Cu at 293K matches Matula 1979 (1.724e-8 Ω·m).
2.  resistivity_at_temperature: increases with temperature for metals.
3.  resistivity_at_temperature: clamped above zero at very low T.
4.  dc_resistance: R = ρL/A for a known case.
5.  dc_resistance: doubles when length doubles.
6.  dc_resistance: halves when area doubles.
7.  joule_power_dc: P = I²R for known current and resistance.
8.  joule_power_dc: scales with I² (double I → 4× power).
9.  skin_depth_m: returns inf at f=0.
10. skin_depth_m: decreases with increasing frequency.
11. skin_depth_m: Cu at 60 Hz ≈ 8.5 mm (textbook value).
12. ac_resistance_factor: returns 1.0 at DC (f=0).
13. ac_resistance_factor: ≥ 1.0 for all positive frequencies.
14. ac_resistance_factor: increases with frequency (larger skin effect).
15. joule_power_ac ≥ joule_power_dc for same geometry.
16. eddy_current_power_density: scales with σ (proportional to conductivity).
17. eddy_current_power_density: scales with B² (double B → 4× power).
18. eddy_current_power_density: scales with f² (double f → 4× power).
19. eddy_current_power_density: scales with d² (double d → 4× power).
20. eddy_current_power_total: total = density × volume.
21. cable_temperature_rise_K: ΔT = P × R_th.
22. cylindrical_insulation_thermal_resistance: positive for valid geometry.
23. cylindrical_insulation_thermal_resistance: raises ValueError for r_in >= r_out.
24. Kapton cable test: known 1m conductor, 10A, temperature rise is physically small.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.electrical.joule_heating import (
    ALUMINIUM,
    COPPER,
    SILVER,
    ac_resistance_factor,
    cable_temperature_rise_K,
    cylindrical_insulation_thermal_resistance,
    dc_resistance,
    eddy_current_power_density,
    eddy_current_power_total,
    joule_power_ac,
    joule_power_dc,
    resistivity_at_temperature,
    skin_depth_m,
)


class TestResistivity:

    def test_cu_at_293k_matches_matula(self):
        rho = resistivity_at_temperature(COPPER, 293.0)
        assert abs(rho - 1.724e-8) < 1e-11  # Matula 1979

    def test_increases_with_temperature(self):
        rho_cold = resistivity_at_temperature(COPPER, 200.0)
        rho_warm = resistivity_at_temperature(COPPER, 400.0)
        assert rho_warm > rho_cold

    def test_al_at_293k_matches_matula(self):
        rho = resistivity_at_temperature(ALUMINIUM, 293.0)
        assert abs(rho - 2.65e-8) < 1e-11

    def test_clamped_above_zero_at_low_temperature(self):
        rho = resistivity_at_temperature(COPPER, 10.0)
        assert rho > 0.0

    def test_silver_lower_than_copper(self):
        rho_cu = resistivity_at_temperature(COPPER, 293.0)
        rho_ag = resistivity_at_temperature(SILVER, 293.0)
        assert rho_ag < rho_cu  # Silver is best conductor (Matula 1979)


class TestDcResistance:

    def test_known_value(self):
        # 1 m, 1 mm² Cu at 293 K: R = 1.724e-8 × 1 / 1e-6 = 0.01724 Ω
        R = dc_resistance(COPPER, length_m=1.0, cross_section_m2=1e-6,
                          temperature_K=293.0)
        assert abs(R - 0.01724) < 1e-5

    def test_doubles_with_length(self):
        R1 = dc_resistance(COPPER, 1.0, 1e-6)
        R2 = dc_resistance(COPPER, 2.0, 1e-6)
        assert abs(R2 / R1 - 2.0) < 1e-9

    def test_halves_with_doubled_area(self):
        R1 = dc_resistance(COPPER, 1.0, 1e-6)
        R2 = dc_resistance(COPPER, 1.0, 2e-6)
        assert abs(R2 / R1 - 0.5) < 1e-9

    def test_higher_temp_higher_resistance(self):
        R_cold = dc_resistance(COPPER, 1.0, 1e-6, temperature_K=273.0)
        R_warm = dc_resistance(COPPER, 1.0, 1e-6, temperature_K=373.0)
        assert R_warm > R_cold


class TestJoulePowerDc:

    def test_ohms_law(self):
        # P = I²R = 10² × 0.01724 = 1.724 W
        P = joule_power_dc(
            current_A=10.0,
            material=COPPER,
            length_m=1.0,
            cross_section_m2=1e-6,
            temperature_K=293.0,
        )
        assert abs(P - 1.724) < 0.001

    def test_scales_with_current_squared(self):
        P1 = joule_power_dc(1.0, COPPER, 1.0, 1e-6)
        P2 = joule_power_dc(2.0, COPPER, 1.0, 1e-6)
        assert abs(P2 / P1 - 4.0) < 1e-9

    def test_nonnegative(self):
        assert joule_power_dc(5.0, COPPER, 10.0, 1e-4) >= 0.0

    def test_zero_current_zero_power(self):
        assert joule_power_dc(0.0, COPPER, 1.0, 1e-6) == 0.0


class TestSkinDepth:

    def test_inf_at_dc(self):
        assert skin_depth_m(COPPER, 0.0) == math.inf

    def test_decreases_with_frequency(self):
        d60 = skin_depth_m(COPPER, 60.0)
        d1000 = skin_depth_m(COPPER, 1000.0)
        assert d60 > d1000

    def test_cu_at_60hz_approx_8_5mm(self):
        # Textbook: δ = sqrt(ρ/(π×f×μ₀)) ≈ 8.5 mm for Cu at 60 Hz
        d = skin_depth_m(COPPER, 60.0)
        assert 7.5e-3 < d < 10.0e-3, f"skin_depth = {d*1000:.2f} mm, expected ~8.5 mm"

    def test_nonnegative(self):
        assert skin_depth_m(COPPER, 50.0) > 0.0

    def test_al_deeper_than_cu_same_freq(self):
        # Al has higher resistivity → larger skin depth
        d_cu = skin_depth_m(COPPER, 50.0)
        d_al = skin_depth_m(ALUMINIUM, 50.0)
        assert d_al > d_cu


class TestAcResistanceFactor:

    def test_unity_at_dc(self):
        assert ac_resistance_factor(5e-3, COPPER, 0.0) == 1.0

    def test_unity_or_above_all_frequencies(self):
        for f in [50.0, 60.0, 400.0, 1000.0, 1e6]:
            factor = ac_resistance_factor(5e-3, COPPER, f)
            assert factor >= 1.0, f"factor = {factor} < 1 at f = {f} Hz"

    def test_increases_with_frequency(self):
        f1 = ac_resistance_factor(5e-3, COPPER, 60.0)
        f2 = ac_resistance_factor(5e-3, COPPER, 10000.0)
        assert f2 > f1

    def test_thin_conductor_near_unity_at_low_freq(self):
        # Very thin conductor (r << δ): R_ac ≈ R_dc
        factor = ac_resistance_factor(0.1e-3, COPPER, 50.0)
        assert factor < 1.01, f"thin conductor factor = {factor}"


class TestJoulePowerAc:

    def test_ac_ge_dc(self):
        kwargs = dict(material=COPPER, length_m=1.0, temperature_K=293.0)
        P_dc = joule_power_dc(10.0, COPPER, 1.0, math.pi * 5e-3 ** 2)
        P_ac = joule_power_ac(10.0, frequency_hz=400.0, radius_m=5e-3, **kwargs)
        assert P_ac >= P_dc

    def test_dc_limit_at_zero_freq(self):
        r = 2e-3
        area = math.pi * r ** 2
        P_dc = joule_power_dc(5.0, COPPER, 2.0, area)
        P_ac = joule_power_ac(5.0, COPPER, 2.0, r, 0.0)
        assert abs(P_ac - P_dc) < 1e-9


class TestEddyCurrentPowerDensity:

    def test_scales_with_b_squared(self):
        kw = dict(material=COPPER, frequency_hz=50.0,
                  strand_diameter_m=1e-3, temperature_K=293.0)
        p1 = eddy_current_power_density(**kw, B_peak_T=0.1)
        p2 = eddy_current_power_density(**kw, B_peak_T=0.2)
        assert abs(p2 / p1 - 4.0) < 1e-6

    def test_scales_with_f_squared(self):
        kw = dict(material=COPPER, B_peak_T=0.1,
                  strand_diameter_m=1e-3, temperature_K=293.0)
        p1 = eddy_current_power_density(**kw, frequency_hz=50.0)
        p2 = eddy_current_power_density(**kw, frequency_hz=100.0)
        assert abs(p2 / p1 - 4.0) < 1e-6

    def test_scales_with_d_squared(self):
        kw = dict(material=COPPER, B_peak_T=0.1,
                  frequency_hz=50.0, temperature_K=293.0)
        p1 = eddy_current_power_density(**kw, strand_diameter_m=1e-3)
        p2 = eddy_current_power_density(**kw, strand_diameter_m=2e-3)
        assert abs(p2 / p1 - 4.0) < 1e-6

    def test_nonnegative(self):
        p = eddy_current_power_density(COPPER, 1.0, 50.0, 1e-3)
        assert p >= 0.0


class TestEddyCurrentTotal:

    def test_total_equals_density_times_volume(self):
        d = 1e-3
        L = 0.5
        density = eddy_current_power_density(COPPER, 0.5, 100.0, d)
        volume = math.pi * (d / 2) ** 2 * L
        expected = density * volume
        total = eddy_current_power_total(COPPER, 0.5, 100.0, d, L)
        assert abs(total - expected) < 1e-15


class TestThermalRise:

    def test_temperature_rise_ohms_thermal(self):
        P = 10.0  # W
        R_th = 2.0  # K/W
        dT = cable_temperature_rise_K(P, R_th)
        assert abs(dT - 20.0) < 1e-9

    def test_zero_power_zero_rise(self):
        assert cable_temperature_rise_K(0.0, 5.0) == 0.0


class TestInsulationResistance:

    def test_positive_for_valid_geometry(self):
        R_th = cylindrical_insulation_thermal_resistance(
            inner_radius_m=2e-3,
            outer_radius_m=3e-3,
            length_m=1.0,
            conductivity_W_per_mK=0.12,  # Kapton ~0.12 W/(m·K); DuPont datasheet
        )
        assert R_th > 0.0

    def test_raises_invalid_radii(self):
        with pytest.raises(ValueError):
            cylindrical_insulation_thermal_resistance(3e-3, 2e-3, 1.0, 0.12)

    def test_raises_inner_zero(self):
        with pytest.raises(ValueError):
            cylindrical_insulation_thermal_resistance(0.0, 3e-3, 1.0, 0.12)

    def test_longer_cable_lower_resistance(self):
        R1 = cylindrical_insulation_thermal_resistance(2e-3, 3e-3, 1.0, 0.12)
        R2 = cylindrical_insulation_thermal_resistance(2e-3, 3e-3, 10.0, 0.12)
        assert R2 < R1

    def test_thicker_insulation_higher_resistance(self):
        R_thin = cylindrical_insulation_thermal_resistance(2e-3, 2.5e-3, 1.0, 0.12)
        R_thick = cylindrical_insulation_thermal_resistance(2e-3, 5e-3, 1.0, 0.12)
        assert R_thick > R_thin


class TestEndToEndKaptonCable:

    def test_10a_1m_cu_cable_temperature_rise_small(self):
        """10 A through 1 m, AWG-16 (~1.3mm dia) Cu wire with Kapton insulation.

        Expectation: temperature rise < 20 K (thermally safe).
        AWG-16: r_conductor ≈ 0.65 mm, Kapton insulation ≈ 0.5 mm thick → r_outer = 1.15 mm.
        """
        r_inner = 0.65e-3  # AWG-16 conductor radius
        r_outer = 1.15e-3  # + 0.5 mm Kapton insulation
        L = 1.0

        P_joule = joule_power_dc(
            current_A=10.0,
            material=COPPER,
            length_m=L,
            cross_section_m2=math.pi * r_inner ** 2,
        )
        R_th = cylindrical_insulation_thermal_resistance(
            inner_radius_m=r_inner,
            outer_radius_m=r_outer,
            length_m=L,
            conductivity_W_per_mK=0.12,  # Kapton; DuPont datasheet
        )
        dT = cable_temperature_rise_K(P_joule, R_th)
        assert dT < 20.0, f"ΔT = {dT:.1f} K — cable overheating"
