"""Tests for internal compartment layout geometry.

Covers zone definitions, bulkhead placement, assembly structure,
and parametric consistency with ShipParameters.
"""

from __future__ import annotations

import math

import cadquery as cq
import pytest

from aria.digital_twin.parameters import ShipParameters
from aria.digital_twin.geometry.compartments import (
    BULKHEAD_THICKNESS_M,
    ZONE_SPECS,
    ZoneSpec,
    create_compartments,
    get_zone_specs,
    _create_bulkhead,
    _create_compartment_solid,
)


@pytest.fixture
def params() -> ShipParameters:
    return ShipParameters()


# ── Zone spec tests ──────────────────────────────────────────────────────

class TestZoneSpecs:
    """Verify the canonical zone layout."""

    def test_seven_zones(self):
        """There must be exactly 7 zones (A-G)."""
        assert len(ZONE_SPECS) == 7

    def test_zones_contiguous(self):
        """Each zone's start must equal the previous zone's end."""
        for i in range(1, len(ZONE_SPECS)):
            assert ZONE_SPECS[i].z_start_m == ZONE_SPECS[i - 1].z_end_m, (
                f"Gap between zone {ZONE_SPECS[i - 1].label} and {ZONE_SPECS[i].label}"
            )

    def test_zones_start_at_zero(self):
        """First zone starts at z = 0 (bow)."""
        assert ZONE_SPECS[0].z_start_m == 0.0

    def test_zone_labels_sequential(self):
        """Zone labels must be A through G."""
        expected = list("ABCDEFG")
        actual = [z.label for z in ZONE_SPECS]
        assert actual == expected

    def test_zone_length_property(self):
        """ZoneSpec.length_m must equal z_end - z_start."""
        for z in ZONE_SPECS:
            assert z.length_m == z.z_end_m - z.z_start_m

    def test_all_lengths_positive(self):
        """Every zone must have a positive length (proportionally scaled)."""
        zones = get_zone_specs(ShipParameters())
        for z in zones:
            assert z.length_m > 0, f"Zone {z.label} has non-positive length"


# ── Adjusted specs tests ────────────────────────────────────────────────

class TestGetZoneSpecs:
    """Verify zone proportional scaling to hull length."""

    def test_last_zone_matches_hull(self, params: ShipParameters):
        """Final zone G must end at hull_length_m."""
        zones = get_zone_specs(params)
        assert abs(zones[-1].z_end_m - params.hull_length_m) < 0.2

    def test_adjusted_zone_g_positive_length(self, params: ShipParameters):
        """Adjusted Zone G must still have a positive length."""
        zones = get_zone_specs(params)
        assert zones[-1].length_m > 0

    def test_zones_are_contiguous(self, params: ShipParameters):
        """Each zone starts where the previous one ends."""
        zones = get_zone_specs(params)
        for i in range(1, len(zones)):
            assert zones[i].z_start_m == zones[i - 1].z_end_m

    def test_all_zones_within_hull(self, params: ShipParameters):
        """Every zone must be within [0, hull_length]."""
        zones = get_zone_specs(params)
        for z in zones:
            assert z.z_start_m >= 0
            assert z.z_end_m <= params.hull_length_m + 0.2


# ── Geometry builder tests ──────────────────────────────────────────────

class TestGeometryBuilders:
    """Test individual compartment and bulkhead creation."""

    def test_compartment_is_solid(self, params: ShipParameters):
        """A compartment solid must have positive volume."""
        solid = _create_compartment_solid(
            params.hull_inner_radius_m, 100.0, 0.0,
        )
        vol = solid.val().Volume()
        expected = math.pi * params.hull_inner_radius_m ** 2 * 100.0
        assert vol == pytest.approx(expected, rel=0.01)

    def test_bulkhead_volume(self, params: ShipParameters):
        """Bulkhead disc volume should match pi*r^2*t."""
        bh = _create_bulkhead(
            params.hull_inner_radius_m, BULKHEAD_THICKNESS_M, 50.0,
        )
        vol = bh.val().Volume()
        expected = math.pi * params.hull_inner_radius_m ** 2 * BULKHEAD_THICKNESS_M
        assert vol == pytest.approx(expected, rel=0.01)


# ── Assembly integration ────────────────────────────────────────────────

class TestCreateCompartments:
    """Integration tests for the full compartment assembly."""

    def test_returns_assembly(self, params: ShipParameters):
        """create_compartments must return a cq.Assembly."""
        assy = create_compartments(params)
        assert isinstance(assy, cq.Assembly)

    def test_assembly_has_zones_and_bulkheads(self, params: ShipParameters):
        """Assembly should contain 7 zone children + 8 bulkhead children."""
        assy = create_compartments(params)
        names = [child.name for child in assy.objects.values()]
        zone_names = [n for n in names if n.startswith("zone_")]
        bh_names = [n for n in names if n.startswith("bulkhead_")]
        assert len(zone_names) == 7, f"Expected 7 zones, got {len(zone_names)}"
        assert len(bh_names) == 8, f"Expected 8 bulkheads, got {len(bh_names)}"

    def test_zone_names_contain_labels(self, params: ShipParameters):
        """Each zone child should contain its label letter."""
        assy = create_compartments(params)
        names = [c.name for c in assy.objects.values() if c.name.startswith("zone_")]
        for label in "ABCDEFG":
            assert any(label in n for n in names), f"Zone {label} missing"

    def test_bulkhead_thickness_constant(self):
        """Bulkhead thickness should be 10 mm."""
        assert BULKHEAD_THICKNESS_M == 0.010
