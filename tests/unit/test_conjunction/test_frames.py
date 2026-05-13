"""Tests for coordinate frame math — rotation matrix properties."""

import math
from datetime import datetime

import numpy as np
import pytest

from aria.conjunction.propagation.frames import (
    _gmst_rad,
    _julian_date,
    _precession_matrix,
    eci_to_rtn,
    project_to_encounter_plane,
)


class TestJulianDate:
    def test_j2000_epoch(self):
        """J2000.0 = 2000-01-01T12:00:00 → JD 2451545.0"""
        jd = _julian_date(datetime(2000, 1, 1, 12, 0, 0))
        assert abs(jd - 2451545.0) < 0.001

    def test_known_date(self):
        """1999-01-01T00:00 → JD 2451179.5"""
        jd = _julian_date(datetime(1999, 1, 1, 0, 0, 0))
        assert abs(jd - 2451179.5) < 0.01


class TestGMST:
    def test_range(self):
        """GMST should be in [0, 2π)."""
        for year in [2000, 2010, 2020, 2024]:
            gmst = _gmst_rad(datetime(year, 6, 15, 12, 0, 0))
            assert 0 <= gmst < 2 * math.pi


class TestPrecession:
    def test_identity_at_j2000(self):
        """Precession matrix should be near identity at J2000."""
        P = _precession_matrix(0.0)
        np.testing.assert_array_almost_equal(P, np.eye(3), decimal=8)

    def test_orthogonality(self):
        """Precession matrix should be orthogonal for any epoch."""
        for T in [0.0, 0.1, 0.24, 1.0]:
            P = _precession_matrix(T)
            identity = P @ P.T
            np.testing.assert_array_almost_equal(identity, np.eye(3), decimal=8)


class TestRTN:
    def test_degenerate_position(self):
        """Should raise for zero position vector."""
        with pytest.raises(ValueError):
            eci_to_rtn(np.array([0, 0, 0]), np.array([1, 0, 0]))

    def test_circular_orbit(self):
        """For circular orbit in XY plane, R=x, T=y, N=z (approximately)."""
        r = np.array([7000.0, 0.0, 0.0])
        v = np.array([0.0, 7.5, 0.0])

        R = eci_to_rtn(r, v)

        # R should be along x
        np.testing.assert_array_almost_equal(R[0], [1, 0, 0], decimal=10)
        # T should be along y
        np.testing.assert_array_almost_equal(R[1], [0, 1, 0], decimal=10)
        # N should be along z
        np.testing.assert_array_almost_equal(R[2], [0, 0, 1], decimal=10)


class TestEncounterPlane:
    def test_miss_perpendicular_to_velocity(self):
        """Component of miss along velocity should be removed in projection."""
        miss = np.array([0.0, 0.0, 1.0])  # purely along z
        v_rel = np.array([0.0, 0.0, 10.0])  # velocity along z
        cov = np.eye(3)

        miss_2d, _ = project_to_encounter_plane(miss, v_rel, cov)
        # Miss is along velocity → projection should be near zero
        assert np.linalg.norm(miss_2d) < 0.01

    def test_covariance_psd(self):
        """Projected covariance must be positive semi-definite."""
        miss = np.array([1.0, 2.0, 0.5])
        v_rel = np.array([7.0, 1.0, 0.0])
        cov = np.diag([1.0, 25.0, 4.0])

        _, cov_2d = project_to_encounter_plane(miss, v_rel, cov)
        eigenvalues = np.linalg.eigvalsh(cov_2d)
        assert np.all(eigenvalues >= -1e-12)  # allow tiny numerical noise
