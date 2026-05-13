"""Tests for the Smart Sieve conjunction screening cascade."""

import math
from datetime import datetime

from aria.conjunction.core.types import ObjectType, OrbitalElements, SpaceObject
from aria.conjunction.screening.apogee_perigee import ApogeePerigeeFilter


def _make_object(norad_id: str, sma: float, ecc: float, inc_deg: float = 51.6,
                 raan_deg: float = 0.0) -> SpaceObject:
    """Helper to create a SpaceObject with specified orbital elements."""
    elements = OrbitalElements(
        semi_major_axis=sma,
        eccentricity=ecc,
        inclination=math.radians(inc_deg),
        raan=math.radians(raan_deg),
        arg_perigee=0.0,
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


class TestApogeePerigeeFilter:
    """Test Stage 1: altitude band overlap."""

    def test_overlapping_orbits(self):
        """Two objects at similar altitudes should pass the filter."""
        obj1 = _make_object("1", sma=6800.0, ecc=0.001)  # ~420 km
        obj2 = _make_object("2", sma=6805.0, ecc=0.001)  # ~425 km

        filt = ApogeePerigeeFilter(pad_km=10.0)
        pairs = filt.filter([obj1, obj2])

        assert len(pairs) == 1
        assert pairs[0] == (0, 1)

    def test_non_overlapping_orbits(self):
        """LEO vs GEO should not pass the filter."""
        obj_leo = _make_object("1", sma=6800.0, ecc=0.001)  # ~420 km
        obj_geo = _make_object("2", sma=42164.0, ecc=0.001)  # ~35,786 km

        filt = ApogeePerigeeFilter(pad_km=10.0)
        pairs = filt.filter([obj_leo, obj_geo])

        assert len(pairs) == 0

    def test_eccentric_overlap(self):
        """Eccentric orbit whose perigee overlaps with circular orbit."""
        obj_circular = _make_object("1", sma=7000.0, ecc=0.001)  # ~622 km, r ≈ 7000
        # Eccentric: perigee = 6500, apogee = 9500 → overlaps with 7000
        obj_eccentric = _make_object("2", sma=8000.0, ecc=0.1875)  # perigee=6500

        filt = ApogeePerigeeFilter(pad_km=10.0)
        pairs = filt.filter([obj_circular, obj_eccentric])

        assert len(pairs) == 1

    def test_many_objects_scaling(self):
        """Filter should handle many objects efficiently."""
        # Create 100 objects spread across LEO
        objects = [
            _make_object(str(i), sma=6700 + i * 2, ecc=0.001)
            for i in range(100)
        ]

        filt = ApogeePerigeeFilter(pad_km=10.0)
        pairs = filt.filter(objects)

        # Nearby objects should match, distant ones shouldn't
        total_possible = 100 * 99 // 2  # 4950
        assert len(pairs) < total_possible  # not all pairs
        assert len(pairs) > 0  # some pairs should match

    def test_empty_catalog(self):
        filt = ApogeePerigeeFilter()
        assert filt.filter([]) == []

    def test_single_object(self):
        obj = _make_object("1", sma=7000.0, ecc=0.001)
        filt = ApogeePerigeeFilter()
        assert filt.filter([obj]) == []
