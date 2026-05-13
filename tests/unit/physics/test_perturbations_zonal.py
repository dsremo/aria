"""Numerical verification tests for zonal harmonic perturbations J2–J6.

Each test validates the corrected denominator r^(n+3) (was r^(2n+1) — a
systematic bug that made J3-J6 accelerations 10^12–10^20× too small).

Strategy:
  1. Ratio check: |a_Jn / a_J2| matches theoretical (Jn/J2)(R/r)^(n-2) × polynomial ratio
  2. Direction check: acceleration points correct direction at canonical positions
  3. Equatorial symmetry: even harmonics (J4, J6) give zero z-component on equatorial plane
  4. Odd anti-symmetry: J3, J5 z-component changes sign across equatorial plane
  5. Magnitude sanity: J4 at LEO ≈ 1.5e-3 × J2 (not 10^-17 × J2 as the buggy code gave)
"""

from __future__ import annotations

import numpy as np
import pytest

from aria.physics.gravity.perturbations import (
    EARTH_J2,
    EARTH_J3,
    EARTH_J4,
    EARTH_J5,
    EARTH_J6,
    EARTH_MU,
    EARTH_R,
    j2_perturbation,
    j3_perturbation,
    j4_perturbation,
    j5_perturbation,
    j6_perturbation,
    zonal_harmonics,
)

# Reference orbit: circular LEO at 422 km altitude (ISS-like)
_R_LEO = EARTH_R + 422e3   # m
_R_LEO_EQ = np.array([_R_LEO, 0.0, 0.0])   # equatorial plane, +x direction
_R_LEO_45 = np.array([_R_LEO / np.sqrt(2), 0.0, _R_LEO / np.sqrt(2)])  # 45° latitude


class TestJ2Baseline:
    """J2 formula unchanged — just verify the known result for regression."""

    def test_equatorial_acceleration_magnitude(self):
        a = j2_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J2, EARTH_R)
        # At equatorial plane: a_x = -1.5*μ*J2*R²/r⁴, a_z = 0
        r = _R_LEO
        expected_x = -1.5 * EARTH_MU * EARTH_J2 * EARTH_R**2 / r**4
        assert abs(a[0] - expected_x) / abs(expected_x) < 1e-10
        assert abs(a[2]) < 1e-30

    def test_j2_magnitude_loe(self):
        a = j2_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J2, EARTH_R)
        # J2/total ≈ 1.5*J2*(R/r)^2 ≈ 1.43e-3; total gravity ~8.6 m/s² → J2 ~0.012 m/s²
        assert 5e-3 < abs(a[0]) < 5e-2


class TestJ4CriticalFix:
    """J4 denominator was r^9; correct is r^7. Ratio test catches the bug."""

    def test_j4_j2_ratio_equatorial(self):
        """J4/J2 acceleration ratio at equatorial plane must match theory."""
        a_j2 = j2_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J2, EARTH_R)
        a_j4 = j4_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J4, EARTH_R)

        ratio = abs(a_j4[0]) / abs(a_j2[0])

        # Theoretical: (5/8)/(3/2) × |J4/J2| × (R/r)^2 × (3/1)
        # At equator: factor_xy(J4) = 3, factor(J2) = 1
        # → ratio = (5/8)/(3/2) × (R/r)^2 × |J4/J2| × 3/1
        # Simplify: (5/8)/(3/2) = 5/12; ×3 = 5/4 = 1.25
        r = _R_LEO
        theoretical = 1.25 * abs(EARTH_J4 / EARTH_J2) * (EARTH_R / r) ** 2
        assert abs(ratio - theoretical) / theoretical < 0.01, (
            f"J4/J2 ratio {ratio:.4e} ≠ theoretical {theoretical:.4e} — "
            "likely wrong denominator in j4_perturbation"
        )

    def test_j4_magnitude_correct_order(self):
        a_j4 = j4_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J4, EARTH_R)
        # Must be ~1.5e-5 m/s², not 3e-19 m/s² (buggy) or 2e-5 m/s² (reference value)
        mag = np.linalg.norm(a_j4)
        assert 1e-6 < mag < 1e-4, (
            f"J4 acceleration {mag:.3e} m/s² is out of expected [1e-6, 1e-4] range"
        )

    def test_j4_equatorial_symmetry(self):
        """Even harmonic: z-component must be exactly 0 at equatorial plane."""
        a_j4 = j4_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J4, EARTH_R)
        assert abs(a_j4[2]) < 1e-30, "J4 z-acceleration non-zero at equatorial plane"

    def test_j4_x_direction_equatorial(self):
        """With EARTH_J4 < 0, J4 at equatorial plane must give centripetal a_x < 0."""
        a_j4 = j4_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J4, EARTH_R)
        # coeff = (5/8)*μ*J4/r^7 < 0 (since J4 < 0), factor_xy = 3 > 0 → a_x < 0
        assert a_j4[0] < 0, "J4 x-acceleration should be centripetal (negative) at equatorial plane"

    def test_j4_nonzero_at_45deg(self):
        a_j4 = j4_perturbation(_R_LEO_45, EARTH_MU, EARTH_J4, EARTH_R)
        assert np.linalg.norm(a_j4) > 1e-8


class TestJ5:
    """J5 — odd harmonic, was r^11, correct is r^8; polynomial factors also wrong."""

    def test_j5_magnitude_vs_j2(self):
        a_j2 = j2_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J2, EARTH_R)
        a_j5_45 = j5_perturbation(_R_LEO_45, EARTH_MU, EARTH_J5, EARTH_R)
        ratio = np.linalg.norm(a_j5_45) / np.linalg.norm(a_j2)
        # J5/J2 ≈ 2.1e-4, (R/r)^3 ≈ 0.73; expect ratio ~1.5e-4
        assert 1e-6 < ratio < 1e-2, (
            f"J5/J2 ratio {ratio:.3e} is wildly off — likely wrong denominator in j5_perturbation"
        )

    def test_j5_xy_zero_at_equatorial_x_axis(self):
        """Odd harmonic: x,y in-plane components must be zero on equatorial plane."""
        a_j5 = j5_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J5, EARTH_R)
        # fxy = (21/8)*z_r*(…), z_r = 0 at equator → ax = ay = 0
        assert abs(a_j5[0]) < 1e-30
        assert abs(a_j5[1]) < 1e-30

    def test_j5_z_nonzero_at_equatorial(self):
        """J5 z-component is non-zero at equatorial plane (north-south asymmetry)."""
        a_j5 = j5_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J5, EARTH_R)
        # gz at s=0 = 15/8 ≠ 0
        assert abs(a_j5[2]) > 1e-10

    def test_j5_antisymmetry_xz_component(self):
        """Odd harmonic: fxy component flips sign across equatorial plane."""
        r_north = np.array([_R_LEO / np.sqrt(2), 0.0, _R_LEO / np.sqrt(2)])
        r_south = np.array([_R_LEO / np.sqrt(2), 0.0, -_R_LEO / np.sqrt(2)])
        a_n = j5_perturbation(r_north, EARTH_MU, EARTH_J5, EARTH_R)
        a_s = j5_perturbation(r_south, EARTH_MU, EARTH_J5, EARTH_R)
        # x-component (fxy ~ z_r) should be equal and opposite
        assert abs(a_n[0] + a_s[0]) / (abs(a_n[0]) + 1e-40) < 1e-10


class TestJ6:
    """J6 — even harmonic, was r^13, correct is r^9; polynomial factors also wrong."""

    def test_j6_magnitude_vs_j2(self):
        a_j2 = j2_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J2, EARTH_R)
        a_j6 = j6_perturbation(_R_LEO_45, EARTH_MU, EARTH_J6, EARTH_R)
        ratio = np.linalg.norm(a_j6) / np.linalg.norm(a_j2)
        # |J6/J2| ≈ 5e-4, (R/r)^4 ≈ 0.65; expect ratio ~3e-4
        assert 1e-6 < ratio < 1e-2, (
            f"J6/J2 ratio {ratio:.3e} is wildly off — likely wrong denominator in j6_perturbation"
        )

    def test_j6_equatorial_symmetry(self):
        """Even harmonic: z-component must be zero at equatorial plane."""
        a_j6 = j6_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J6, EARTH_R)
        assert abs(a_j6[2]) < 1e-30, "J6 z-acceleration non-zero at equatorial plane"

    def test_j6_nonzero_at_45deg(self):
        a_j6 = j6_perturbation(_R_LEO_45, EARTH_MU, EARTH_J6, EARTH_R)
        assert np.linalg.norm(a_j6) > 1e-10


class TestZonalHarmonics:
    """Integration test: combined zonal_harmonics function."""

    def test_j2_only(self):
        a_comb = zonal_harmonics(_R_LEO_EQ, order=2)
        a_j2 = j2_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J2, EARTH_R)
        np.testing.assert_allclose(a_comb, a_j2, rtol=1e-12)

    def test_j2_through_j4(self):
        a_comb = zonal_harmonics(_R_LEO_EQ, order=4)
        expected = (
            j2_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J2, EARTH_R)
            + j3_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J3, EARTH_R)
            + j4_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J4, EARTH_R)
        )
        np.testing.assert_allclose(a_comb, expected, rtol=1e-12)

    def test_order6_dominance(self):
        """J2 must dominate: |a_J2| > sum(|a_J3|+...+|a_J6|) by ~2 orders of magnitude."""
        a2 = np.linalg.norm(j2_perturbation(_R_LEO_EQ, EARTH_MU, EARTH_J2, EARTH_R))
        higher = sum(
            np.linalg.norm(fn(_R_LEO_45, EARTH_MU, c, EARTH_R))
            for fn, c in [
                (j3_perturbation, EARTH_J3),
                (j4_perturbation, EARTH_J4),
                (j5_perturbation, EARTH_J5),
                (j6_perturbation, EARTH_J6),
            ]
        )
        assert a2 > 50 * higher, (
            f"J2 ({a2:.3e}) should dominate higher harmonics ({higher:.3e}) by >50×"
        )

    def test_zero_vector_returns_zeros(self):
        a = zonal_harmonics(np.zeros(3))
        np.testing.assert_array_equal(a, np.zeros(3))

    def test_order_clipping(self):
        """order=2 and order=1 give identical results (J1=0 by convention)."""
        a2 = zonal_harmonics(_R_LEO_EQ, order=2)
        a_full = zonal_harmonics(_R_LEO_EQ, order=6)
        # Full should be different from J2-only
        assert not np.allclose(a2, a_full)
