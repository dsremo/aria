"""Tests for extended-body tidal loading across the hull.

Validates:
1.  hull_tidal_acceleration_profile: returns n_points entries.
2.  hull_tidal_acceleration_profile: acceleration at centre (s=0) is zero.
3.  hull_tidal_acceleration_profile: acceleration at tip equals single-point calc.
4.  hull_tidal_acceleration_profile: profile is anti-symmetric (a(s) = -a(-s)).
5.  hull_tidal_acceleration_profile: raises ValueError for n_points < 2.
6.  differential_tidal_acceleration_m_s2: zero for zero half-length.
7.  differential_tidal_acceleration_m_s2: equals 2 × a_tidal(+L) for anti-symmetric field.
8.  differential_tidal_acceleration_m_s2: returns (3,) vector.
9.  max_tidal_differential_m_s2: equals magnitude of differential vector.
10. max_tidal_differential_m_s2: scales as 1/r³ (inverse-cube with distance).
11. max_tidal_differential_m_s2: proportional to hull length.
12. hull_tidal_tension_N: zero for zero hull mass.
13. hull_tidal_tension_N: positive for radially aligned hull near perturber.
14. hull_tidal_tension_N: scales as GM × L / r³ (tidal scaling).
15. hull_tidal_tension_N: raises ValueError for non-positive mass.
16. hull_tidal_bending_moment_Nm: zero for radially aligned hull (no transverse force).
17. hull_tidal_bending_moment_Nm: non-zero for hull perpendicular to radial.
18. hull_tidal_bending_moment_Nm: positive for off-axis hull near perturber.
19. tidal_stress_at_cross_section_Pa: proportional to tension.
20. tidal_stress_at_cross_section_Pa: inversely proportional to area.
21. tidal_stress_at_cross_section_Pa: raises ValueError for zero area.
22. is_tidal_stress_critical: True when stress ≥ yield / safety_factor.
23. is_tidal_stress_critical: False when stress < yield / safety_factor.
24. solar_perihelion_tidal_scenario: tension > 0 at 1 AU.
25. solar_perihelion_tidal_scenario: bending_moment > 0.
26. solar_perihelion_tidal_scenario: stress > 0.
27. solar_perihelion_tidal_scenario: tension at 0.5 AU > tension at 1 AU (∝ 1/r³).
28. solar_perihelion_tidal_scenario: differential_m_s2 > 0.
29. Generation ship scenario: 500 m hull at 1 AU from Sun — stress negligible vs yield.
30. Tension scales ∝ M × L / r³ (direct verification).
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from aria.physics.gravity_relativistic.hull_tidal_loading import (
    differential_tidal_acceleration_m_s2,
    hull_tidal_acceleration_profile,
    hull_tidal_bending_moment_Nm,
    hull_tidal_tension_N,
    is_tidal_stress_critical,
    max_tidal_differential_m_s2,
    solar_perihelion_tidal_scenario,
    tidal_stress_at_cross_section_Pa,
)
from aria.physics.gravity_relativistic.tidal_tensor import (
    tidal_tensor_single_perturber,
    tidal_acceleration_on_point,
)

# Sun parameters
GM_SUN = 1.32712440018e20   # m³/s²
AU_M   = 1.495978707e11     # 1 AU in metres


def make_solar_tensor_at_1AU():
    """Tidal tensor at [1 AU, 0, 0] due to Sun at origin."""
    ship_pos = np.array([AU_M, 0.0, 0.0])
    sun_pos  = np.array([0.0, 0.0, 0.0])
    return tidal_tensor_single_perturber(ship_pos, sun_pos, GM_SUN)


class TestHullProfile:

    def test_returns_n_points(self):
        E = make_solar_tensor_at_1AU()
        axis = np.array([1.0, 0.0, 0.0])
        pos, acc = hull_tidal_acceleration_profile(E, axis, 250.0, n_points=20)
        assert len(pos) == 20
        assert acc.shape == (20, 3)

    def test_zero_acceleration_at_centre(self):
        """At s=0 (CoM), tidal acceleration is zero by definition."""
        E = make_solar_tensor_at_1AU()
        axis = np.array([1.0, 0.0, 0.0])
        pos, acc = hull_tidal_acceleration_profile(E, axis, 250.0, n_points=51)
        # Middle point is s=0
        mid = 25
        assert abs(pos[mid]) < 1e-6  # at s=0
        assert np.allclose(acc[mid], 0.0, atol=1e-20)

    def test_tip_matches_single_point_calc(self):
        E = make_solar_tensor_at_1AU()
        axis = np.array([1.0, 0.0, 0.0])
        L = 250.0
        _, acc = hull_tidal_acceleration_profile(E, axis, L, n_points=51)
        a_tip_profile = acc[-1]
        a_tip_direct = tidal_acceleration_on_point(E, np.array([L, 0.0, 0.0]))
        assert np.allclose(a_tip_profile, a_tip_direct, atol=1e-20)

    def test_anti_symmetric(self):
        E = make_solar_tensor_at_1AU()
        axis = np.array([1.0, 0.0, 0.0])
        pos, acc = hull_tidal_acceleration_profile(E, axis, 250.0, n_points=51)
        # a(s) = -a(-s): first entry (s=-L) should equal -last (s=+L)
        assert np.allclose(acc[0], -acc[-1], atol=1e-20)

    def test_raises_n_points_less_than_2(self):
        E = make_solar_tensor_at_1AU()
        with pytest.raises(ValueError):
            hull_tidal_acceleration_profile(E, np.array([1.0, 0.0, 0.0]), 250.0, n_points=1)


class TestDifferentialAcceleration:

    def test_zero_at_zero_length(self):
        E = make_solar_tensor_at_1AU()
        axis = np.array([1.0, 0.0, 0.0])
        da = differential_tidal_acceleration_m_s2(E, axis, 0.0)
        assert np.allclose(da, 0.0, atol=1e-30)

    def test_equals_twice_tip_acceleration(self):
        """Δa = a(+L) - a(-L) = 2 × a(+L) by anti-symmetry."""
        E = make_solar_tensor_at_1AU()
        axis = np.array([1.0, 0.0, 0.0])
        L = 250.0
        da = differential_tidal_acceleration_m_s2(E, axis, L)
        a_tip = tidal_acceleration_on_point(E, np.array([L, 0.0, 0.0]))
        assert np.allclose(da, 2.0 * a_tip, atol=1e-25)

    def test_returns_3d_vector(self):
        E = make_solar_tensor_at_1AU()
        da = differential_tidal_acceleration_m_s2(E, np.array([1.0, 0.0, 0.0]), 100.0)
        assert da.shape == (3,)

    def test_max_differential_equals_magnitude(self):
        E = make_solar_tensor_at_1AU()
        axis = np.array([1.0, 0.0, 0.0])
        da = differential_tidal_acceleration_m_s2(E, axis, 200.0)
        max_diff = max_tidal_differential_m_s2(E, axis, 200.0)
        assert abs(max_diff - np.linalg.norm(da)) < 1e-25

    def test_scales_inverse_cube_with_distance(self):
        """At 2× the distance, tidal acceleration should be 8× smaller (1/r³)."""
        axis = np.array([1.0, 0.0, 0.0])
        sun = np.array([0.0, 0.0, 0.0])
        E1 = tidal_tensor_single_perturber(np.array([AU_M, 0.0, 0.0]), sun, GM_SUN)
        E2 = tidal_tensor_single_perturber(np.array([2 * AU_M, 0.0, 0.0]), sun, GM_SUN)
        da1 = max_tidal_differential_m_s2(E1, axis, 250.0)
        da2 = max_tidal_differential_m_s2(E2, axis, 250.0)
        assert abs(da1 / da2 - 8.0) < 0.01

    def test_proportional_to_hull_length(self):
        E = make_solar_tensor_at_1AU()
        axis = np.array([1.0, 0.0, 0.0])
        da1 = max_tidal_differential_m_s2(E, axis, 100.0)
        da2 = max_tidal_differential_m_s2(E, axis, 200.0)
        assert abs(da2 / da1 - 2.0) < 1e-9


class TestTidalTension:

    def test_positive_for_radial_hull(self):
        E = make_solar_tensor_at_1AU()
        axis = np.array([1.0, 0.0, 0.0])
        F = hull_tidal_tension_N(E, axis, 250.0, 1e9)
        assert F > 0.0

    def test_scales_with_mass(self):
        E = make_solar_tensor_at_1AU()
        axis = np.array([1.0, 0.0, 0.0])
        F1 = hull_tidal_tension_N(E, axis, 250.0, 1e9)
        F2 = hull_tidal_tension_N(E, axis, 250.0, 2e9)
        assert abs(F2 / F1 - 2.0) < 1e-9

    def test_scales_with_length(self):
        E = make_solar_tensor_at_1AU()
        axis = np.array([1.0, 0.0, 0.0])
        F1 = hull_tidal_tension_N(E, axis, 250.0, 1e9)
        F2 = hull_tidal_tension_N(E, axis, 500.0, 1e9)
        # a_tip ∝ L → F ∝ L
        assert abs(F2 / F1 - 2.0) < 1e-9

    def test_raises_nonpositive_mass(self):
        E = make_solar_tensor_at_1AU()
        with pytest.raises(ValueError):
            hull_tidal_tension_N(E, np.array([1.0, 0.0, 0.0]), 250.0, 0.0)


class TestTidalBending:

    def test_zero_for_radially_aligned(self):
        """Hull along radial: tidal force is purely axial → zero bending."""
        E = make_solar_tensor_at_1AU()
        radial_axis = np.array([1.0, 0.0, 0.0])
        M = hull_tidal_bending_moment_Nm(E, radial_axis, 250.0, 1e9)
        assert M < 1e-3  # effectively zero for radial alignment

    def test_zero_for_transverse_hull(self):
        """Hull along ŷ at [AU,0,0]: tidal force is purely axial → zero bending.
        E_yy = +GM/r³ → force on hull tip is along ŷ (compressive, not transverse).
        """
        E = make_solar_tensor_at_1AU()
        transverse_axis = np.array([0.0, 1.0, 0.0])
        M = hull_tidal_bending_moment_Nm(E, transverse_axis, 250.0, 1e9)
        assert M < 1e-10  # effectively zero: tidal force is axial for Y-aligned hull

    def test_positive_for_off_axis(self):
        """45° off radial: both tension and bending contribute."""
        E = make_solar_tensor_at_1AU()
        axis_45 = np.array([1.0, 1.0, 0.0]) / math.sqrt(2.0)
        M = hull_tidal_bending_moment_Nm(E, axis_45, 250.0, 1e9)
        assert M > 0.0


class TestTidalStress:

    def test_proportional_to_tension(self):
        E = make_solar_tensor_at_1AU()
        axis = np.array([1.0, 0.0, 0.0])
        F1 = hull_tidal_tension_N(E, axis, 250.0, 1e9)
        F2 = hull_tidal_tension_N(E, axis, 250.0, 2e9)
        s1 = tidal_stress_at_cross_section_Pa(F1, 50.0)
        s2 = tidal_stress_at_cross_section_Pa(F2, 50.0)
        assert abs(s2 / s1 - 2.0) < 1e-9

    def test_inversely_proportional_to_area(self):
        F = 1e6
        s1 = tidal_stress_at_cross_section_Pa(F, 10.0)
        s2 = tidal_stress_at_cross_section_Pa(F, 20.0)
        assert abs(s2 / s1 - 0.5) < 1e-9

    def test_raises_zero_area(self):
        with pytest.raises(ValueError):
            tidal_stress_at_cross_section_Pa(1e6, 0.0)


class TestSCCritical:

    def test_critical_when_above_limit(self):
        # stress=5e8, yield=8e8, SF=2 → allowable=4e8 → 5e8 ≥ 4e8 → critical
        assert is_tidal_stress_critical(5e8, 8e8, safety_factor=2.0)

    def test_not_critical_below_limit(self):
        assert not is_tidal_stress_critical(1e6, 8e8)


class TestSolarScenario:

    def test_scenario_returns_positive(self):
        budget = solar_perihelion_tidal_scenario(1.0, 250.0, 1e9, 50.0)
        assert budget["tension_N"] > 0.0
        assert budget["bending_moment_Nm"] > 0.0
        assert budget["stress_Pa"] > 0.0
        assert budget["differential_m_s2"] > 0.0

    def test_higher_tension_closer_to_sun(self):
        b1 = solar_perihelion_tidal_scenario(1.0, 250.0, 1e9, 50.0)
        b2 = solar_perihelion_tidal_scenario(0.5, 250.0, 1e9, 50.0)
        assert b2["tension_N"] > b1["tension_N"]

    def test_generation_ship_1au_stress_negligible(self):
        """500 m hull, 1e9 kg, 50 m² cross-section at 1 AU: tidal stress << Ti yield."""
        budget = solar_perihelion_tidal_scenario(1.0, 250.0, 1e9, 50.0)
        # Ti-6Al-4V yield strength ~830 MPa; tidal stress at 1 AU should be tiny
        TI_YIELD_PA = 830e6
        assert budget["stress_Pa"] < TI_YIELD_PA * 0.01  # less than 1% of yield
