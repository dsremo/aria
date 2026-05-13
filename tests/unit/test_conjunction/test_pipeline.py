"""Tests for the end-to-end pipeline and CDM writer."""

from datetime import datetime

import numpy as np

from aria.conjunction.core.types import (
    CloseApproach,
    ObjectType,
    OrbitalElements,
    RiskLevel,
    SpaceObject,
    StateVector,
)
from aria.conjunction.pipeline.alerts import AlertClassifier
from aria.conjunction.pipeline.cdm_writer import CDMWriter


def _make_approach(
    miss_km: float = 1.0,
    pc: float = 1e-6,
    rel_vel: float = 7.5,
    tca_dt: datetime | None = None,
) -> CloseApproach:
    """Create a synthetic CloseApproach for testing."""
    if tca_dt is None:
        tca_dt = datetime(2024, 3, 15, 12, 0, 0)

    primary = SpaceObject(
        norad_id="25544", name="ISS", tle_line1="1 25544U ...", tle_line2="2 25544 ...",
        object_type=ObjectType.PAYLOAD, radius_m=50.0,
        elements=OrbitalElements(6780, 0.001, 0.9, 0, 0, 0, tca_dt),
    )
    secondary = SpaceObject(
        norad_id="99999", name="DEBRIS", tle_line1="1 99999U ...", tle_line2="2 99999 ...",
        object_type=ObjectType.DEBRIS, radius_m=0.1,
        elements=OrbitalElements(6782, 0.001, 0.9, 0.01, 0, 0, tca_dt),
    )

    return CloseApproach(
        primary=primary,
        secondary=secondary,
        tca=tca_dt,
        miss_distance_km=miss_km,
        miss_distance_rtn=np.array([0.1, miss_km * 0.9, miss_km * 0.1]),
        relative_velocity_km_s=rel_vel,
        relative_position=np.array([miss_km, 0, 0]),
        relative_velocity_vec=np.array([0, rel_vel, 0]),
        probability_of_collision=pc,
        risk_level=RiskLevel.GREEN,
    )


class TestAlertClassifier:
    def test_red_alert(self):
        approach = _make_approach(pc=5e-4)
        classifier = AlertClassifier()
        alerts = classifier.classify([approach])

        assert len(alerts) == 1
        assert alerts[0].risk_level == RiskLevel.RED
        assert alerts[0].requires_maneuver is True

    def test_yellow_alert(self):
        approach = _make_approach(pc=5e-5)
        classifier = AlertClassifier()
        alerts = classifier.classify([approach])

        assert len(alerts) == 1
        assert alerts[0].risk_level == RiskLevel.YELLOW

    def test_green_no_alert(self):
        approach = _make_approach(pc=1e-7)
        classifier = AlertClassifier()
        alerts = classifier.classify([approach])

        assert len(alerts) == 0  # GREEN events don't generate alerts

    def test_critical_miss_distance(self):
        """Very close miss should trigger alert even with low Pc."""
        approach = _make_approach(miss_km=0.5, pc=1e-7)
        classifier = AlertClassifier()
        alerts = classifier.classify([approach])

        assert len(alerts) == 1  # miss < 1 km overrides

    def test_sorting_red_first(self):
        """RED alerts should come before YELLOW."""
        red = _make_approach(pc=5e-4)
        yellow = _make_approach(pc=5e-5)
        classifier = AlertClassifier()
        alerts = classifier.classify([yellow, red])  # yellow first in input

        assert alerts[0].risk_level == RiskLevel.RED  # but RED comes first


class TestCDMWriter:
    def test_cdm_format(self):
        approach = _make_approach()
        approach.primary_state = StateVector(
            position=np.array([6780, 0, 0]),
            velocity=np.array([0, 7.66, 0]),
            epoch=approach.tca,
        )
        approach.secondary_state = StateVector(
            position=np.array([6781, 0, 0]),
            velocity=np.array([0, 7.65, 0]),
            epoch=approach.tca,
        )

        writer = CDMWriter(originator="TEST")
        cdm = writer.write(approach)

        assert "CCSDS_CDM_VERS" in cdm
        assert "2.0" in cdm
        assert "25544" in cdm
        assert "MISS_DISTANCE" in cdm
        assert "COLLISION_PROBABILITY" in cdm
        assert "OBJECT1" in cdm
        assert "OBJECT2" in cdm

    def test_cdm_batch(self):
        approaches = [_make_approach() for _ in range(3)]
        writer = CDMWriter()
        cdms = writer.write_many(approaches)
        assert len(cdms) == 3
