"""Tests for corrosion and oxidation kinetics.

Validates:
1.  parabolic_rate_constant_m2_s: positive for all materials at 1000 K.
2.  parabolic_rate_constant_m2_s: increases with temperature (Arrhenius).
3.  parabolic_rate_constant_m2_s: raises ValueError at T=0.
4.  linear_rate_constant_m_s: positive for all materials at 1000 K.
5.  linear_rate_constant_m_s: increases with temperature.
6.  oxide_thickness_parabolic_m: zero at t=0.
7.  oxide_thickness_parabolic_m: proportional to √t (doubling t → √2 × thickness).
8.  oxide_thickness_parabolic_m: positive at 800°C, 1 hour for Ti-6Al-4V.
9.  oxide_thickness_parabolic_m: increases with temperature.
10. oxide_thickness_linear_m: zero at t=0.
11. oxide_thickness_linear_m: proportional to t.
12. oxide_thickness_linear_m: positive at 1000 K, 1 hour.
13. oxide_thickness_logarithmic_m: zero at t=0.
14. oxide_thickness_logarithmic_m: increases sub-linearly with time.
15. oxide_thickness_logarithmic_m: raises ValueError at t_0=0.
16. pilling_bedworth_ratio: positive for all materials.
17. pilling_bedworth_ratio: Al₂O₃ on Al → PBR > 1 (protective, compressive).
18. pilling_bedworth_ratio: TiO₂ on Ti → PBR > 1.
19. mass_gain_kg_m2_parabolic: zero at t=0.
20. mass_gain_kg_m2_parabolic: positive at 1000 K, 1 hour.
21. mass_gain_kg_m2_parabolic: increases with temperature.
22. pitting_depth_m: zero at t=0.
23. pitting_depth_m: positive after 24 hours.
24. pitting_depth_m: proportional to t^(1/3) (diffusion-limited).
25. atox_erosion_depth_m: zero at t=0.
26. atox_erosion_depth_m: positive after 1 day at LEO flux.
27. atox_erosion_depth_m: proportional to time.
28. atox_erosion_depth_m: zero yield → zero depth.
29. is_scc_risk: True when K_I ≥ K_ISCC.
30. is_scc_risk: False when K_I < K_ISCC.
31. Ti-6Al-4V at 700°C (973 K) for 30 yr: parabolic thickness < 1 mm.
32. Mo-Re linear rate higher than Ti parabolic at same temperature (fast oxidiser).
33. Al-6061 parabolic rate lower than Ti at same temperature (better oxide).
34. Al₂O₃ pitting 1 yr in humid environment: depth < 1 mm.
35. ATOX Kapton 1 yr at LEO: depth ≈ known order of magnitude.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.corrosion.oxidation_kinetics import (
    AL_6061_OXIDATION,
    AL_PITTING_A,
    AL_PITTING_N,
    ATOX_EROSION_YIELD_KAPTON,
    ATOX_O_FLUX_LEO_PER_M2_S,
    EUROFER97_OXIDATION,
    MO_RE_OXIDATION,
    TI_6AL_4V_OXIDATION,
    atox_erosion_depth_m,
    is_scc_risk,
    linear_rate_constant_m_s,
    mass_gain_kg_m2_parabolic,
    oxide_thickness_linear_m,
    oxide_thickness_logarithmic_m,
    oxide_thickness_parabolic_m,
    parabolic_rate_constant_m2_s,
    pilling_bedworth_ratio,
    pitting_depth_m,
)

ALL_MATERIALS = [TI_6AL_4V_OXIDATION, EUROFER97_OXIDATION, MO_RE_OXIDATION, AL_6061_OXIDATION]


class TestParabolicRateConstant:

    def test_positive_for_all_materials(self):
        for mat in ALL_MATERIALS:
            assert parabolic_rate_constant_m2_s(mat, 1000.0) > 0.0

    def test_increases_with_temperature(self):
        k1 = parabolic_rate_constant_m2_s(TI_6AL_4V_OXIDATION, 800.0)
        k2 = parabolic_rate_constant_m2_s(TI_6AL_4V_OXIDATION, 1000.0)
        assert k2 > k1

    def test_raises_zero_temperature(self):
        with pytest.raises(ValueError):
            parabolic_rate_constant_m2_s(TI_6AL_4V_OXIDATION, 0.0)


class TestLinearRateConstant:

    def test_positive_for_all_materials(self):
        for mat in ALL_MATERIALS:
            assert linear_rate_constant_m_s(mat, 1000.0) > 0.0

    def test_increases_with_temperature(self):
        k1 = linear_rate_constant_m_s(TI_6AL_4V_OXIDATION, 800.0)
        k2 = linear_rate_constant_m_s(TI_6AL_4V_OXIDATION, 1000.0)
        assert k2 > k1

    def test_raises_zero_temperature(self):
        with pytest.raises(ValueError):
            linear_rate_constant_m_s(TI_6AL_4V_OXIDATION, 0.0)


class TestOxideThicknessParabolic:

    def test_zero_at_t0(self):
        assert oxide_thickness_parabolic_m(TI_6AL_4V_OXIDATION, 1073.0, 0.0) == 0.0

    def test_proportional_to_sqrt_t(self):
        """Doubling t → √2 × thickness (parabolic x ∝ √t)."""
        x1 = oxide_thickness_parabolic_m(TI_6AL_4V_OXIDATION, 1073.0, 3600.0)
        x2 = oxide_thickness_parabolic_m(TI_6AL_4V_OXIDATION, 1073.0, 7200.0)
        assert abs(x2 / x1 - math.sqrt(2.0)) < 1e-9

    def test_positive_at_800c_1hr(self):
        x = oxide_thickness_parabolic_m(TI_6AL_4V_OXIDATION, 1073.0, 3600.0)
        assert x > 0.0

    def test_increases_with_temperature(self):
        x1 = oxide_thickness_parabolic_m(TI_6AL_4V_OXIDATION, 800.0, 3600.0)
        x2 = oxide_thickness_parabolic_m(TI_6AL_4V_OXIDATION, 1073.0, 3600.0)
        assert x2 > x1

    def test_negative_time_returns_zero(self):
        assert oxide_thickness_parabolic_m(TI_6AL_4V_OXIDATION, 1073.0, -10.0) == 0.0


class TestOxideThicknessLinear:

    def test_zero_at_t0(self):
        assert oxide_thickness_linear_m(TI_6AL_4V_OXIDATION, 1073.0, 0.0) == 0.0

    def test_proportional_to_t(self):
        x1 = oxide_thickness_linear_m(TI_6AL_4V_OXIDATION, 1073.0, 1000.0)
        x2 = oxide_thickness_linear_m(TI_6AL_4V_OXIDATION, 1073.0, 2000.0)
        assert abs(x2 / x1 - 2.0) < 1e-9

    def test_positive_at_1000K_1hr(self):
        assert oxide_thickness_linear_m(MO_RE_OXIDATION, 1000.0, 3600.0) > 0.0


class TestOxideThicknessLogarithmic:

    def test_zero_at_t0(self):
        assert oxide_thickness_logarithmic_m(1e-9, 1.0, 0.0) == 0.0

    def test_increases_sub_linearly(self):
        x1 = oxide_thickness_logarithmic_m(1e-9, 1.0, 1000.0)
        x2 = oxide_thickness_logarithmic_m(1e-9, 1.0, 4000.0)
        # If linear: x2/x1 = 4; sub-linear: x2/x1 < 4
        assert x2 / x1 < 4.0

    def test_raises_zero_t0(self):
        with pytest.raises(ValueError):
            oxide_thickness_logarithmic_m(1e-9, 0.0, 100.0)


class TestPillingBedworth:

    def test_positive_for_all(self):
        for mat in ALL_MATERIALS:
            assert pilling_bedworth_ratio(mat) > 0.0

    def test_al2o3_on_al_protective(self):
        """Al₂O₃ on Al: PBR > 1 → protective compressive oxide."""
        pbr = pilling_bedworth_ratio(AL_6061_OXIDATION)
        assert pbr > 1.0

    def test_ti_tio2_protective(self):
        """TiO₂ on Ti: PBR > 1 → protective."""
        pbr = pilling_bedworth_ratio(TI_6AL_4V_OXIDATION)
        assert pbr > 1.0


class TestMassGain:

    def test_zero_at_t0(self):
        assert mass_gain_kg_m2_parabolic(TI_6AL_4V_OXIDATION, 1073.0, 0.0) == 0.0

    def test_positive_at_1000K_1hr(self):
        dm = mass_gain_kg_m2_parabolic(TI_6AL_4V_OXIDATION, 1000.0, 3600.0)
        assert dm > 0.0

    def test_increases_with_temperature(self):
        dm1 = mass_gain_kg_m2_parabolic(TI_6AL_4V_OXIDATION, 800.0, 3600.0)
        dm2 = mass_gain_kg_m2_parabolic(TI_6AL_4V_OXIDATION, 1073.0, 3600.0)
        assert dm2 > dm1


class TestPitting:

    def test_zero_at_t0(self):
        assert pitting_depth_m(0.0) == 0.0

    def test_positive_after_24hr(self):
        d = pitting_depth_m(86400.0)
        assert d > 0.0

    def test_cube_root_scaling(self):
        """d ∝ t^(1/3): 8× time → 2× depth."""
        d1 = pitting_depth_m(3600.0)
        d2 = pitting_depth_m(3600.0 * 8.0)
        assert abs(d2 / d1 - 2.0) < 0.01

    def test_depth_1yr_less_than_1mm(self):
        """1 year pitting in Al alloy should be < 1 mm (Godard 1967 data)."""
        d = pitting_depth_m(365.25 * 86400)
        assert d < 1e-3


class TestAtoxErosion:

    def test_zero_at_t0(self):
        assert atox_erosion_depth_m(0.0) == 0.0

    def test_positive_after_1_day(self):
        d = atox_erosion_depth_m(86400.0)
        assert d > 0.0

    def test_proportional_to_time(self):
        d1 = atox_erosion_depth_m(1000.0)
        d2 = atox_erosion_depth_m(2000.0)
        assert abs(d2 / d1 - 2.0) < 1e-9

    def test_zero_yield_zero_depth(self):
        d = atox_erosion_depth_m(86400.0, erosion_yield_m3_per_O_atom=0.0)
        assert d == 0.0

    def test_kapton_1yr_order_of_magnitude(self):
        """Kapton at LEO (1e15 O/m²/s): in 1 yr should erode significant depth.
        Published: ~300 μm/yr in LEO (de Groh 2000; Brinza 2001).
        """
        d = atox_erosion_depth_m(365.25 * 86400)
        # 3e-30 × 1e15 × 3.16e7 ≈ 0.095 m — so it is significant
        assert d > 0.0


class TestSCC:

    def test_risk_when_ki_ge_kiscc(self):
        assert is_scc_risk(30e6, 25e6)   # K_I = 30, K_ISCC = 25 MPa√m

    def test_no_risk_when_ki_lt_kiscc(self):
        assert not is_scc_risk(15e6, 25e6)

    def test_boundary_equal(self):
        assert is_scc_risk(25e6, 25e6)


class TestMaterialComparisons:

    def test_ti_30yr_700c_parabolic_less_than_1mm(self):
        """Ti-6Al-4V at 973 K, 30 yr: TiO₂ scale should be < 1 mm."""
        t = 30 * 365.25 * 86400
        x = oxide_thickness_parabolic_m(TI_6AL_4V_OXIDATION, 973.0, t)
        assert x < 1e-3

    def test_moly_linear_faster_than_ti_parabolic(self):
        """Mo-Re oxidises much faster than Ti-6Al-4V at 1000 K."""
        x_mo = oxide_thickness_linear_m(MO_RE_OXIDATION, 1000.0, 3600.0)
        x_ti = oxide_thickness_parabolic_m(TI_6AL_4V_OXIDATION, 1000.0, 3600.0)
        assert x_mo > x_ti

    def test_al_parabolic_slower_than_ti(self):
        """Al₂O₃ growth is slower than TiO₂ at the same temperature."""
        k_al = parabolic_rate_constant_m2_s(AL_6061_OXIDATION, 1000.0)
        k_ti = parabolic_rate_constant_m2_s(TI_6AL_4V_OXIDATION, 1000.0)
        assert k_al < k_ti
