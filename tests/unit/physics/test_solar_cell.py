"""Tests for solar cell temperature + radiation degradation model.

Validates:
1.  temperature_factor: equals 1.0 at T_ref.
2.  temperature_factor: < 1 above T_ref (negative γ_P).
3.  temperature_factor: > 1 below T_ref (colder = more efficient).
4.  temperature_factor: clamped to 0 at extreme high T.
5.  radiation_degradation_factor: equals 1.0 at zero fluence.
6.  radiation_degradation_factor: decreases monotonically with fluence.
7.  radiation_degradation_factor: ≥ 0 at extreme fluence.
8.  irradiance_W_m2: equals G_AMO at 1 AU.
9.  irradiance_W_m2: scales as 1/r² (double distance → quarter irradiance).
10. irradiance_W_m2: raises ValueError at zero distance.
11. incidence_angle_factor: 1.0 at 0° incidence.
12. incidence_angle_factor: 0.0 at 90° incidence.
13. incidence_angle_factor: cos(60°) = 0.5 at 60°.
14. incidence_angle_factor: 0.0 beyond 90°.
15. solar_panel_power_W: positive at nominal conditions.
16. solar_panel_power_W: zero at 90° incidence.
17. solar_panel_power_W: decreases with high temperature.
18. solar_panel_power_W: decreases with high fluence.
19. solar_panel_power_W: decreases with greater solar distance.
20. bol_power_W: equals area × G_AMO × eta_bol × (1-soiling) at 1 AU.
21. eol_power_fraction: 1.0 at reference conditions.
22. eol_power_fraction: < 1 after radiation damage.
23. 30-year mission: 3J GaAs EOL fraction stays above 70%.
24. Irradiance at 5 AU (Jupiter) ≈ G_AMO / 25.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.electrical.solar_cell import (
    G_AMO_W_M2,
    RADIATION_C_RAD,
    RADIATION_PHI_0,
    TRIPLE_JUNCTION_GAAS_ETA_BOL,
    TRIPLE_JUNCTION_GAMMA_P_PER_K,
    TRIPLE_JUNCTION_T_REF_K,
    SolarCellConfig,
    bol_power_W,
    eol_power_fraction,
    incidence_angle_factor,
    irradiance_W_m2,
    radiation_degradation_factor,
    solar_panel_power_W,
    temperature_factor,
)


def _default_config():
    return SolarCellConfig(area_m2=100.0)


class TestTemperatureFactor:

    def test_unity_at_T_ref(self):
        f = temperature_factor(TRIPLE_JUNCTION_T_REF_K)
        assert abs(f - 1.0) < 1e-12

    def test_less_than_one_above_T_ref(self):
        f = temperature_factor(TRIPLE_JUNCTION_T_REF_K + 50.0)
        assert f < 1.0

    def test_greater_than_one_below_T_ref(self):
        f = temperature_factor(TRIPLE_JUNCTION_T_REF_K - 50.0)
        assert f > 1.0

    def test_linear_with_temperature(self):
        dT = 100.0
        f = temperature_factor(TRIPLE_JUNCTION_T_REF_K + dT)
        expected = 1.0 + TRIPLE_JUNCTION_GAMMA_P_PER_K * dT
        assert abs(f - expected) < 1e-12

    def test_clamped_at_zero_extreme_heat(self):
        f = temperature_factor(10000.0)
        assert f == 0.0

    def test_clamped_below_2(self):
        f = temperature_factor(0.0)
        assert f <= 2.0


class TestRadiationDegradationFactor:

    def test_unity_at_zero_fluence(self):
        assert abs(radiation_degradation_factor(0.0) - 1.0) < 1e-12

    def test_decreases_monotonically(self):
        f1 = radiation_degradation_factor(1e13)
        f2 = radiation_degradation_factor(1e14)
        f3 = radiation_degradation_factor(1e15)
        assert f1 > f2 > f3

    def test_nonnegative_extreme(self):
        assert radiation_degradation_factor(1e20) >= 0.0

    def test_at_phi0_roughly_known(self):
        # At Φ = Φ₀: D = 1 - C_rad × log10(2) ≈ 1 - 0.18 × 0.301 = 0.946
        expected = 1.0 - RADIATION_C_RAD * math.log10(2.0)
        D = radiation_degradation_factor(RADIATION_PHI_0)
        assert abs(D - expected) < 1e-9

    def test_less_than_one_with_any_fluence(self):
        assert radiation_degradation_factor(1e10) < 1.0 + 1e-9


class TestIrradiance:

    def test_g_amo_at_1_au(self):
        assert abs(irradiance_W_m2(1.0) - G_AMO_W_M2) < 0.01

    def test_inverse_square_law(self):
        G1 = irradiance_W_m2(1.0)
        G2 = irradiance_W_m2(2.0)
        assert abs(G2 / G1 - 0.25) < 1e-9

    def test_jupiter_approx(self):
        # Jupiter ~5.2 AU: G ≈ 1366/27 ≈ 50 W/m²
        G_j = irradiance_W_m2(5.2)
        assert 45 < G_j < 55

    def test_raises_zero_distance(self):
        with pytest.raises(ValueError):
            irradiance_W_m2(0.0)

    def test_raises_negative_distance(self):
        with pytest.raises(ValueError):
            irradiance_W_m2(-1.0)

    def test_at_5_au_equals_g_amo_over_25(self):
        G5 = irradiance_W_m2(5.0)
        expected = G_AMO_W_M2 / 25.0
        assert abs(G5 - expected) < 0.01


class TestIncidenceAngleFactor:

    def test_unity_at_zero_degrees(self):
        assert abs(incidence_angle_factor(0.0) - 1.0) < 1e-12

    def test_zero_at_ninety_degrees(self):
        assert incidence_angle_factor(90.0) == 0.0

    def test_zero_beyond_ninety(self):
        assert incidence_angle_factor(120.0) == 0.0

    def test_cos60_at_60_degrees(self):
        assert abs(incidence_angle_factor(60.0) - 0.5) < 1e-9

    def test_cos45_at_45_degrees(self):
        expected = math.cos(math.radians(45.0))
        assert abs(incidence_angle_factor(45.0) - expected) < 1e-12

    def test_decreasing_with_angle(self):
        f1 = incidence_angle_factor(20.0)
        f2 = incidence_angle_factor(50.0)
        assert f1 > f2


class TestSolarPanelPowerW:

    def test_positive_at_nominal(self):
        cfg = _default_config()
        P = solar_panel_power_W(cfg, T_K=cfg.T_ref_K, fluence_e_cm2=0.0,
                                distance_AU=1.0)
        assert P > 0.0

    def test_zero_at_90_incidence(self):
        cfg = _default_config()
        P = solar_panel_power_W(cfg, T_K=cfg.T_ref_K, fluence_e_cm2=0.0,
                                distance_AU=1.0, incidence_angle_deg=90.0)
        assert P == 0.0

    def test_decreases_with_high_temperature(self):
        cfg = _default_config()
        P_cold = solar_panel_power_W(cfg, T_K=200.0, fluence_e_cm2=0.0, distance_AU=1.0)
        P_hot = solar_panel_power_W(cfg, T_K=500.0, fluence_e_cm2=0.0, distance_AU=1.0)
        assert P_hot < P_cold

    def test_decreases_with_radiation(self):
        cfg = _default_config()
        P_fresh = solar_panel_power_W(cfg, T_K=cfg.T_ref_K, fluence_e_cm2=0.0, distance_AU=1.0)
        P_damaged = solar_panel_power_W(cfg, T_K=cfg.T_ref_K, fluence_e_cm2=1e15, distance_AU=1.0)
        assert P_damaged < P_fresh

    def test_decreases_with_distance(self):
        cfg = _default_config()
        P_near = solar_panel_power_W(cfg, T_K=cfg.T_ref_K, fluence_e_cm2=0.0, distance_AU=1.0)
        P_far = solar_panel_power_W(cfg, T_K=cfg.T_ref_K, fluence_e_cm2=0.0, distance_AU=2.0)
        assert P_far < P_near
        assert abs(P_far / P_near - 0.25) < 0.001

    def test_incidence_cos_scaling(self):
        cfg = _default_config()
        P_normal = solar_panel_power_W(cfg, T_K=cfg.T_ref_K, fluence_e_cm2=0.0,
                                       distance_AU=1.0, incidence_angle_deg=0.0)
        P_60deg = solar_panel_power_W(cfg, T_K=cfg.T_ref_K, fluence_e_cm2=0.0,
                                      distance_AU=1.0, incidence_angle_deg=60.0)
        assert abs(P_60deg / P_normal - 0.5) < 0.001


class TestBolPowerW:

    def test_matches_manual_calculation(self):
        cfg = SolarCellConfig(area_m2=100.0, eta_bol=0.295, soiling_factor=0.02)
        P = bol_power_W(cfg, distance_AU=1.0)
        expected = G_AMO_W_M2 * 100.0 * 0.295 * (1.0 - 0.02)
        assert abs(P - expected) < 0.1

    def test_scales_with_area(self):
        cfg1 = SolarCellConfig(area_m2=100.0)
        cfg2 = SolarCellConfig(area_m2=200.0)
        assert abs(bol_power_W(cfg2) / bol_power_W(cfg1) - 2.0) < 1e-6


class TestEolPowerFraction:

    def test_unity_at_bol_conditions(self):
        cfg = _default_config()
        frac = eol_power_fraction(cfg, T_K=cfg.T_ref_K, fluence_e_cm2=0.0,
                                  distance_AU=1.0)
        assert abs(frac - 1.0) < 1e-6

    def test_less_than_one_with_radiation(self):
        cfg = _default_config()
        frac = eol_power_fraction(cfg, T_K=cfg.T_ref_K, fluence_e_cm2=1e14,
                                  distance_AU=1.0)
        assert frac < 1.0

    def test_30yr_3j_gaas_above_70pct(self):
        """30-year mission behind moderate shielding: >70% power retained.

        Typical LEO-equivalent fluence over 30 years ~1e15 e/cm² (1 MeV eq.).
        Bett 2007 / Messenger 2001: 3J GaAs retains ~75–80% at this fluence.
        Temperature: 300 K (nominal operating).
        """
        cfg = _default_config()
        # 30-yr GEO/LEO equivalent: ~5e14 to 1e15 e/cm²
        frac = eol_power_fraction(
            cfg, T_K=300.0, fluence_e_cm2=1e15, distance_AU=1.0
        )
        assert frac > 0.70, f"30-yr EOL fraction = {frac:.2%}, expected > 70%"

    def test_temperature_effect_cold_higher(self):
        cfg = _default_config()
        frac_cold = eol_power_fraction(cfg, T_K=200.0, fluence_e_cm2=0.0, distance_AU=1.0)
        frac_hot = eol_power_fraction(cfg, T_K=400.0, fluence_e_cm2=0.0, distance_AU=1.0)
        assert frac_cold > frac_hot
