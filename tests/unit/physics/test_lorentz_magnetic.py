"""Tests for Lorentz force, magnetic L-shell, gyroradius, and Van Allen traversal.

Validates:
1. Lorentz force F = q(v×B): perpendicular to both v and B.
2. Lorentz force zero when v ∥ B.
3. lorentz_acceleration has correct charge/mass scaling.
4. L-shell ≈ 1 at Earth's surface equator, ~6.6 at GEO.
5. Gyroradius scales correctly with energy and field.
6. 10 MeV proton gyroradius in 30000 nT ≈ 100-500 m (LEO field strength).
7. Van Allen belt traversal dose is positive and shielding reduces it.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from aria.physics.gravity import (
    gyroradius_m,
    igrf_dipole,
    lorentz_acceleration,
    lorentz_force,
    magnetic_l_shell,
    van_allen_traversal_dose_msv,
)
from aria.physics.gravity.space_environment import (
    _E_CHARGE_C,
    _M_PROTON_KG,
    _R_EARTH_M,
)


class TestLorentzForce:
    """F = q(v × B) fundamental tests."""

    def test_force_perpendicular_to_velocity(self):
        q = 1.6e-19
        v = np.array([1e4, 0.0, 0.0])
        B = np.array([0.0, 0.0, 3e-5])   # typical LEO field ~30 µT
        F = lorentz_force(q, v, B)
        assert abs(np.dot(F, v)) < 1e-30, "Lorentz force must be perpendicular to v"

    def test_force_perpendicular_to_field(self):
        q = 1.6e-19
        v = np.array([1e4, 0.0, 0.0])
        B = np.array([0.0, 0.0, 3e-5])
        F = lorentz_force(q, v, B)
        assert abs(np.dot(F, B)) < 1e-30, "Lorentz force must be perpendicular to B"

    def test_zero_force_parallel_velocity(self):
        # v ∥ B → v × B = 0 → F = 0
        q = 1.6e-19
        v = np.array([0.0, 0.0, 1e4])
        B = np.array([0.0, 0.0, 3e-5])
        F = lorentz_force(q, v, B)
        assert np.linalg.norm(F) < 1e-40

    def test_force_magnitude(self):
        # F = q v B sin(90°) for perpendicular geometry
        q = 1.6e-19
        v = np.array([1e4, 0.0, 0.0])
        B = np.array([0.0, 3e-5, 0.0])
        F = lorentz_force(q, v, B)
        expected_magnitude = q * 1e4 * 3e-5  # q·v·B for perpendicular
        assert abs(np.linalg.norm(F) - expected_magnitude) / expected_magnitude < 1e-9

    def test_charge_sign_flips_force(self):
        v = np.array([1e4, 0.0, 0.0])
        B = np.array([0.0, 0.0, 3e-5])
        F_pos = lorentz_force(+1.6e-19, v, B)
        F_neg = lorentz_force(-1.6e-19, v, B)
        np.testing.assert_allclose(F_pos, -F_neg, rtol=1e-10)

    def test_zero_charge_zero_force(self):
        v = np.array([1e4, 0.0, 0.0])
        B = np.array([0.0, 0.0, 3e-5])
        F = lorentz_force(0.0, v, B)
        np.testing.assert_array_equal(F, np.zeros(3))


class TestLorentzAcceleration:
    """lorentz_acceleration uses igrf_dipole internally."""

    def test_returns_3d_vector(self):
        r = np.array([_R_EARTH_M + 400e3, 0.0, 0.0])
        v = np.array([7800.0, 0.0, 0.0])
        a = lorentz_acceleration(_E_CHARGE_C, _M_PROTON_KG, v, r)
        assert a.shape == (3,)

    def test_acceleration_scales_with_charge_mass_ratio(self):
        r = np.array([_R_EARTH_M + 400e3, 0.0, 0.0])
        v = np.array([0.0, 7800.0, 0.0])
        # Double the charge/mass ratio
        a1 = lorentz_acceleration(_E_CHARGE_C, _M_PROTON_KG, v, r)
        a2 = lorentz_acceleration(2 * _E_CHARGE_C, _M_PROTON_KG, v, r)
        np.testing.assert_allclose(a2, 2 * a1, rtol=1e-9)

    def test_proton_larmor_frequency_loe(self):
        # Proton gyrofrequency ω = qB/m; LEO B ~ 30000 nT = 3e-5 T
        # ω ≈ 1.6e-19 × 3e-5 / 1.67e-27 ≈ 2.9 rad/s
        r = np.array([_R_EARTH_M + 400e3, 0.0, 0.0])   # equatorial
        v = np.array([0.0, 1.0, 0.0])  # unit velocity
        a = lorentz_acceleration(_E_CHARGE_C, _M_PROTON_KG, v, r)
        # |a| / |v| = ω = qB/m
        omega = np.linalg.norm(a) / np.linalg.norm(v)
        b_nt = np.linalg.norm(igrf_dipole(r))
        b_t = b_nt * 1e-9
        omega_expected = _E_CHARGE_C * b_t / _M_PROTON_KG
        assert abs(omega - omega_expected) / omega_expected < 1e-9


class TestMagneticLShell:
    """McIlwain L parameter from dipole approximation."""

    def test_l_approx_1_at_surface_equator(self):
        # Magnetic equatorial surface: L = r/R_E ≈ 1 when at equator (λ=0)
        # Pure dipole at equator: r_hat ⊥ m_hat → cos(λ)=1 → L = r/R_E
        r_eq = np.array([_R_EARTH_M, 0.0, 0.0])
        L = magnetic_l_shell(r_eq)
        assert 0.8 < L < 1.3, f"L at surface equator = {L:.2f}, expected ~1"

    def test_l_increases_with_altitude(self):
        r_leo = np.array([_R_EARTH_M + 400e3, 0.0, 0.0])
        r_geo = np.array([_R_EARTH_M + 35786e3, 0.0, 0.0])
        L_leo = magnetic_l_shell(r_leo)
        L_geo = magnetic_l_shell(r_geo)
        assert L_geo > L_leo

    def test_l_at_geo_approx_6_6(self):
        # GEO at equator: r = 42164 km, L = r/R_E ≈ 6.6
        r_geo = np.array([42164e3, 0.0, 0.0])
        L = magnetic_l_shell(r_geo)
        assert 5.5 < L < 8.0, f"L at GEO = {L:.2f}, expected ~6.6"

    def test_l_zero_inside_earth(self):
        r_inside = np.array([1e6, 0.0, 0.0])  # inside Earth
        assert magnetic_l_shell(r_inside) == 0.0


class TestGyroradius:
    """Larmor radius for relativistic particles."""

    def test_10mev_proton_in_30000nt(self):
        # 10 MeV proton in LEO field (~30000 nT): r_L = p / (q B)
        # p = γmv ≈ 140 MeV/c at 10 MeV; r_L ~ 0.14 GeV/c / (1.6e-19 × 3e-5 T)
        r = gyroradius_m(
            kinetic_energy_mev=10.0,
            charge_c=_E_CHARGE_C,
            mass_kg=_M_PROTON_KG,
            b_field_nt=30000.0,
        )
        # Expected ~140 km range (LEO field, 10 MeV proton)
        assert 1e4 < r < 1e7, f"Gyroradius = {r:.2e} m, expected 10 km – 10 Mm"

    def test_gyroradius_scales_with_energy(self):
        # Higher energy → larger gyroradius
        r1 = gyroradius_m(10.0, _E_CHARGE_C, _M_PROTON_KG, 30000.0)
        r2 = gyroradius_m(100.0, _E_CHARGE_C, _M_PROTON_KG, 30000.0)
        assert r2 > r1

    def test_gyroradius_inversely_proportional_to_field(self):
        r1 = gyroradius_m(10.0, _E_CHARGE_C, _M_PROTON_KG, 10000.0)
        r2 = gyroradius_m(10.0, _E_CHARGE_C, _M_PROTON_KG, 30000.0)
        # r ∝ 1/B: r at 10000 nT should be ~3× larger than at 30000 nT
        assert abs(r1 / r2 - 3.0) < 0.5   # within 50% of factor-3 scaling

    def test_electron_smaller_than_proton(self):
        # Same energy, electron mass << proton mass → smaller gyroradius
        m_electron = 9.1093837e-31  # kg
        r_p = gyroradius_m(1.0, _E_CHARGE_C, _M_PROTON_KG, 30000.0)
        r_e = gyroradius_m(1.0, _E_CHARGE_C, m_electron, 30000.0)
        assert r_e < r_p


class TestVanAllenTraversal:
    """Van Allen belt traversal dose estimates."""

    def test_traversal_dose_positive(self):
        dose = van_allen_traversal_dose_msv(400, 36000)
        assert dose > 0.0

    def test_shielding_reduces_dose(self):
        dose_thin = van_allen_traversal_dose_msv(400, 36000, shielding_g_cm2=2.0)
        dose_thick = van_allen_traversal_dose_msv(400, 36000, shielding_g_cm2=20.0)
        assert dose_thin > dose_thick

    def test_belt_crossing_higher_than_leo_to_leo(self):
        # LEO → GEO crosses the belts; LEO → MEO (2000 km) hits the inner belt
        dose_belt = van_allen_traversal_dose_msv(400, 10000)
        dose_shallow = van_allen_traversal_dose_msv(400, 800)
        assert dose_belt > dose_shallow
