"""Tests for SGP4 propagation and coordinate frame transformations."""

import math
from datetime import datetime, timedelta

import numpy as np

from aria.conjunction.core.types import CoordinateFrame, OrbitalElements
from aria.conjunction.data.tle_parser import TLEParser
from aria.conjunction.propagation.frames import (
    eci_to_ecef,
    eci_to_rtn,
    project_to_encounter_plane,
    teme_to_eci_j2000,
)
from aria.conjunction.propagation.sgp4_propagator import SGP4Propagator
from aria.conjunction.propagation.state_vector import elements_to_state, state_to_elements

# ISS TLE for testing (2008 epoch, known valid checksums)
ISS_LINE1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
ISS_LINE2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"


class TestSGP4Propagator:
    """Test SGP4/SDP4 propagation."""

    def setup_method(self):
        self.iss = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2, name="ISS")

    def test_propagate_at_epoch(self):
        """Propagation at TLE epoch should give a valid state."""
        state = SGP4Propagator.propagate(self.iss, self.iss.elements.epoch)

        # ISS should be at ~6780 km from Earth center
        r_mag = np.linalg.norm(state.position)
        assert 6500 < r_mag < 7000, f"Position magnitude {r_mag} km out of range"

        # Velocity ~7.66 km/s
        v_mag = np.linalg.norm(state.velocity)
        assert 7.0 < v_mag < 8.0, f"Velocity magnitude {v_mag} km/s out of range"

        # Frame should be TEME
        assert state.frame == CoordinateFrame.TEME

    def test_propagate_forward(self):
        """Propagation forward should give different positions."""
        epoch = self.iss.elements.epoch
        state1 = SGP4Propagator.propagate(self.iss, epoch)
        state2 = SGP4Propagator.propagate(self.iss, epoch + timedelta(minutes=45))

        # After half an orbit, position should be very different
        dist = np.linalg.norm(state1.position - state2.position)
        assert dist > 1000, "Position should change significantly after 45 minutes"

    def test_propagate_batch(self):
        """Batch propagation should return multiple states."""
        epoch = self.iss.elements.epoch
        states = SGP4Propagator.propagate_batch(
            self.iss, epoch, epoch + timedelta(hours=1), step_seconds=600
        )
        # 1 hour / 10 min = 7 steps (including start)
        assert len(states) >= 6

    def test_altitude_property(self):
        """StateVector altitude should be reasonable for ISS."""
        state = SGP4Propagator.propagate(self.iss, self.iss.elements.epoch)
        assert 300 < state.altitude_km < 500

    def test_propagate_many(self):
        """Propagate multiple objects to same epoch."""
        # Same TLE but different objects — dict keyed by norad_id, so same ID → 1 result
        iss2 = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2, name="ISS-copy")
        epoch = self.iss.elements.epoch
        results = SGP4Propagator.propagate_many([self.iss, iss2], epoch)
        # Both have same NORAD ID 25544, so dict has 1 entry
        assert len(results) == 1
        assert "25544" in results


class TestCoordinateFrames:
    """Test coordinate frame transformations."""

    def setup_method(self):
        self.iss = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2)
        self.state = SGP4Propagator.propagate(self.iss, self.iss.elements.epoch)

    def test_teme_to_eci(self):
        """TEME→ECI should preserve magnitude (rotation only)."""
        eci_state = teme_to_eci_j2000(self.state)

        # Position magnitude should be preserved (rotation doesn't change length)
        r_teme = np.linalg.norm(self.state.position)
        r_eci = np.linalg.norm(eci_state.position)
        assert abs(r_teme - r_eci) < 0.01, "Position magnitude changed in rotation"

        # Frame should be updated
        assert eci_state.frame == CoordinateFrame.ECI_J2000

    def test_eci_to_ecef(self):
        """ECI→ECEF should preserve magnitude."""
        ecef_state = eci_to_ecef(self.state)

        r_orig = np.linalg.norm(self.state.position)
        r_ecef = np.linalg.norm(ecef_state.position)
        assert abs(r_orig - r_ecef) < 0.1

        assert ecef_state.frame == CoordinateFrame.ECEF

    def test_rtn_orthogonal(self):
        """RTN matrix should be orthogonal (det = 1, R^T R = I)."""
        R = eci_to_rtn(self.state.position, self.state.velocity)

        # Orthogonality: R^T R = I
        identity = R @ R.T
        np.testing.assert_array_almost_equal(identity, np.eye(3), decimal=10)

        # Proper rotation: det = 1
        assert abs(np.linalg.det(R) - 1.0) < 1e-10

    def test_rtn_radial_direction(self):
        """R-hat should be along the position vector."""
        R = eci_to_rtn(self.state.position, self.state.velocity)
        r_hat = R[0]  # first row is radial

        # Should be parallel to position
        r_unit = self.state.position / np.linalg.norm(self.state.position)
        dot = abs(np.dot(r_hat, r_unit))
        assert dot > 0.999

    def test_encounter_plane_projection(self):
        """Encounter plane projection should reduce 3D to 2D."""
        miss = np.array([1.0, 2.0, 3.0])
        v_rel = np.array([7.0, 0.5, 0.1])
        cov = np.diag([1.0, 25.0, 1.0])

        miss_2d, cov_2d = project_to_encounter_plane(miss, v_rel, cov)

        assert miss_2d.shape == (2,)
        assert cov_2d.shape == (2, 2)

        # 2D covariance should be positive semi-definite
        eigenvalues = np.linalg.eigvalsh(cov_2d)
        assert np.all(eigenvalues >= 0)


class TestStateVectorConversion:
    """Test Cartesian ↔ Keplerian element conversion."""

    def test_roundtrip_circular(self):
        """Elements → State → Elements should roundtrip for circular orbit."""
        elements = OrbitalElements(
            semi_major_axis=7000.0,  # ~622 km altitude
            eccentricity=0.001,
            inclination=math.radians(51.6),
            raan=math.radians(100.0),
            arg_perigee=math.radians(45.0),
            true_anomaly=math.radians(90.0),
            epoch=datetime(2024, 2, 14),
        )

        state = elements_to_state(elements)
        recovered = state_to_elements(state)

        assert abs(recovered.semi_major_axis - elements.semi_major_axis) < 0.1
        assert abs(recovered.eccentricity - elements.eccentricity) < 0.001
        assert abs(recovered.inclination - elements.inclination) < 1e-6

    def test_roundtrip_eccentric(self):
        """Roundtrip for moderately eccentric orbit."""
        elements = OrbitalElements(
            semi_major_axis=10000.0,
            eccentricity=0.3,
            inclination=math.radians(28.5),
            raan=math.radians(200.0),
            arg_perigee=math.radians(120.0),
            true_anomaly=math.radians(45.0),
            epoch=datetime(2024, 2, 14),
        )

        state = elements_to_state(elements)
        recovered = state_to_elements(state)

        assert abs(recovered.semi_major_axis - elements.semi_major_axis) < 1.0
        assert abs(recovered.eccentricity - elements.eccentricity) < 0.001
