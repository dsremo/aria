"""Tests for Stage 2: Orbital Plane (MOID) filter."""

import math
from datetime import datetime

import numpy as np
import pytest

from aria.conjunction.core.types import ObjectType, OrbitalElements, SpaceObject
from aria.conjunction.screening.orbital_plane import (
    OrbitalPlaneFilter,
    _j2_secular_rates,
    _orbit_positions_vectorized,
    compute_moid,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_obj(norad_id: str, sma: float, ecc: float, inc_deg: float,
              raan_deg: float = 0.0, argp_deg: float = 0.0) -> SpaceObject:
    elements = OrbitalElements(
        semi_major_axis=sma,
        eccentricity=ecc,
        inclination=math.radians(inc_deg),
        raan=math.radians(raan_deg),
        arg_perigee=math.radians(argp_deg),
        true_anomaly=0.0,
        epoch=datetime(2024, 2, 14),
    )
    return SpaceObject(
        norad_id=norad_id,
        name=f"OBJ-{norad_id}",
        tle_line1="",
        tle_line2="",
        object_type=ObjectType.DEBRIS,
        elements=elements,
    )


# ---------------------------------------------------------------------------
# _orbit_positions_vectorized
# ---------------------------------------------------------------------------

class TestOrbitPositionsVectorized:

    def test_shape(self):
        pos = _orbit_positions_vectorized(7000.0, 0.001, math.radians(51.6), 0.0, 0.0, 180)
        assert pos.shape == (180, 3)

    def test_circular_orbit_constant_radius(self):
        """All points on a circular orbit should be at the same radius."""
        pos = _orbit_positions_vectorized(7000.0, 0.0, math.radians(30.0), 0.0, 0.0, 360)
        radii = np.linalg.norm(pos, axis=1)
        assert np.allclose(radii, 7000.0, atol=1.0)

    def test_equatorial_orbit_z_near_zero(self):
        """Equatorial orbit (inc=0) should have z ≈ 0."""
        pos = _orbit_positions_vectorized(7000.0, 0.0, 0.0, 0.0, 0.0, 180)
        assert np.all(np.abs(pos[:, 2]) < 1e-6)

    def test_eccentric_orbit_radius_variation(self):
        """Eccentric orbit: apogee > SMA > perigee."""
        sma, ecc = 8000.0, 0.3
        pos = _orbit_positions_vectorized(sma, ecc, math.radians(45.0), 0.0, 0.0, 360)
        radii = np.linalg.norm(pos, axis=1)
        expected_apogee = sma * (1 + ecc)
        expected_perigee = sma * (1 - ecc)
        assert radii.max() == pytest.approx(expected_apogee, rel=1e-3)
        assert radii.min() == pytest.approx(expected_perigee, rel=1e-3)

    def test_default_n_points(self):
        pos = _orbit_positions_vectorized(7000.0, 0.0, 0.5, 0.0, 0.0)
        assert pos.shape == (180, 3)


# ---------------------------------------------------------------------------
# _j2_secular_rates
# ---------------------------------------------------------------------------

class TestJ2SecularRates:

    def test_raan_regression_prograde(self):
        """Prograde orbit: RAAN should regress (negative rate)."""
        raan_rate, _ = _j2_secular_rates(7000.0, 0.001, math.radians(51.6))
        assert raan_rate < 0

    def test_raan_advance_retrograde(self):
        """Retrograde orbit: RAAN should advance (positive rate)."""
        raan_rate, _ = _j2_secular_rates(7000.0, 0.001, math.radians(130.0))
        assert raan_rate > 0

    def test_polar_orbit_zero_raan_rate(self):
        """Polar orbit (i=90°): RAAN drift should be zero."""
        raan_rate, _ = _j2_secular_rates(7000.0, 0.001, math.radians(90.0))
        assert abs(raan_rate) < 1e-12

    def test_argp_rate_nonzero(self):
        """Argument of perigee should drift for non-critical inclinations."""
        _, argp_rate = _j2_secular_rates(7000.0, 0.001, math.radians(51.6))
        assert argp_rate != 0.0

    def test_higher_altitude_slower_rates(self):
        """Higher orbit → weaker J2 effect → smaller drift rates."""
        r1, _ = _j2_secular_rates(7000.0, 0.001, math.radians(51.6))
        r2, _ = _j2_secular_rates(42164.0, 0.001, math.radians(51.6))
        assert abs(r2) < abs(r1)


# ---------------------------------------------------------------------------
# compute_moid
# ---------------------------------------------------------------------------

class TestComputeMOID:

    def test_coplanar_orbits_returns_zero(self):
        """Coplanar orbits (rel_inc < 0.1°) should return 0 (conservative)."""
        obj1 = _make_obj("1", sma=7000.0, ecc=0.0, inc_deg=51.6, raan_deg=0.0)
        obj2 = _make_obj("2", sma=7200.0, ecc=0.0, inc_deg=51.600001, raan_deg=0.0)
        moid = compute_moid(obj1, obj2)
        assert moid == 0.0

    def test_same_orbit_moid_near_zero(self):
        """Two objects on nearly identical orbits → MOID ~ 0."""
        obj1 = _make_obj("1", 7000.0, 0.001, 51.6, raan_deg=0.0)
        obj2 = _make_obj("2", 7000.0, 0.001, 51.7, raan_deg=1.0)
        moid = compute_moid(obj1, obj2)
        assert moid >= 0.0
        assert moid < 200.0  # should be small

    def test_leo_vs_geo_large_moid(self):
        """LEO vs GEO should have huge MOID."""
        obj_leo = _make_obj("1", 6800.0, 0.001, 51.6)
        obj_geo = _make_obj("2", 42164.0, 0.001, 0.1)
        moid = compute_moid(obj_leo, obj_geo)
        assert moid > 1000.0

    def test_missing_elements_returns_zero(self):
        """Object without elements → return 0 (conservative — don't filter)."""
        obj_with = _make_obj("1", 7000.0, 0.001, 51.6)
        obj_no_el = SpaceObject(norad_id="2", name="X", tle_line1="", tle_line2="",
                                elements=None)
        assert compute_moid(obj_with, obj_no_el) == 0.0
        assert compute_moid(obj_no_el, obj_with) == 0.0

    def test_crossing_orbits_much_smaller_than_leo_geo(self):
        """Two LEO crossing orbits should have far smaller MOID than LEO vs GEO."""
        obj_leo1 = _make_obj("1", 7000.0, 0.0, 45.0, raan_deg=0.0)
        obj_leo2 = _make_obj("2", 7000.0, 0.0, 45.0, raan_deg=90.0)
        obj_geo = _make_obj("3", 42164.0, 0.001, 0.1)

        moid_leo_leo = compute_moid(obj_leo1, obj_leo2)
        moid_leo_geo = compute_moid(obj_leo1, obj_geo)
        # Both LEO orbits should have much smaller MOID than LEO vs GEO
        assert moid_leo_leo < moid_leo_geo

    def test_returns_float(self):
        obj1 = _make_obj("1", 7000.0, 0.001, 51.6)
        obj2 = _make_obj("2", 7100.0, 0.001, 60.0)
        result = compute_moid(obj1, obj2)
        assert isinstance(result, float)
        assert result >= 0.0


# ---------------------------------------------------------------------------
# OrbitalPlaneFilter
# ---------------------------------------------------------------------------

class TestOrbitalPlaneFilter:

    def test_close_orbits_pass(self):
        """Objects in nearly identical orbits (slightly different SMA) should survive."""
        obj1 = _make_obj("1", 7000.0, 0.001, 51.6, raan_deg=0.0)
        obj2 = _make_obj("2", 7001.0, 0.001, 51.7, raan_deg=0.5)

        filt = OrbitalPlaneFilter(threshold_km=200.0)
        surviving = filt.filter([obj1, obj2], [(0, 1)])
        assert (0, 1) in surviving

    def test_leo_vs_geo_eliminated(self):
        """LEO vs GEO pair should be eliminated by MOID filter."""
        obj_leo = _make_obj("1", 6800.0, 0.001, 51.6)
        obj_geo = _make_obj("2", 42164.0, 0.001, 0.1)

        filt = OrbitalPlaneFilter(threshold_km=100.0)
        surviving = filt.filter([obj_leo, obj_geo], [(0, 1)])
        assert len(surviving) == 0

    def test_empty_pairs_returns_empty(self):
        obj1 = _make_obj("1", 7000.0, 0.001, 51.6)
        filt = OrbitalPlaneFilter()
        assert filt.filter([obj1], []) == []

    def test_j2_drift_check_runs(self):
        """Filter should not crash when checking MOID with J2 drift."""
        obj1 = _make_obj("1", 7000.0, 0.001, 51.6, raan_deg=0.0)
        obj2 = _make_obj("2", 7010.0, 0.001, 51.7, raan_deg=5.0)

        # Use very large threshold so current MOID fails but J2 drift check runs
        filt = OrbitalPlaneFilter(threshold_km=0.001, window_hours=72.0)
        # Should not raise
        surviving = filt.filter([obj1, obj2], [(0, 1)])
        assert isinstance(surviving, list)

    def test_multiple_pairs_partial_survival(self):
        """Some pairs should be eliminated, others survive."""
        obj_leo = _make_obj("1", 6800.0, 0.001, 51.6)
        obj_leo2 = _make_obj("2", 6820.0, 0.001, 45.0, raan_deg=90.0)  # crossing
        obj_geo = _make_obj("3", 42164.0, 0.001, 0.1)

        filt = OrbitalPlaneFilter(threshold_km=200.0)
        # Pair (0,1) = LEO vs LEO crossing → should survive
        # Pair (0,2) = LEO vs GEO → should be eliminated
        surviving = filt.filter([obj_leo, obj_leo2, obj_geo], [(0, 1), (0, 2)])

        assert (0, 1) in surviving
        assert (0, 2) not in surviving
