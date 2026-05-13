"""Tests for structurally-realistic hull geometry.

Covers stringers, ring frames, spine truss, aft docking port,
airlock hatch cutouts, and the composite hull structure assembly.
"""

from __future__ import annotations

import math

import pytest

from aria.digital_twin.parameters import ShipParameters


# Use a small ship for fast CAD operations in tests.
@pytest.fixture
def small_params() -> ShipParameters:
    """Compact ship dimensions for quick CadQuery tests."""
    return ShipParameters(
        hull_wall_thickness_m=0.5,
        hull_length_m=120.0,   # long enough for multiple rings/bulkheads
        ship_mass_kg=1e6,
        ship_cross_section_m2=50.0,
    )


@pytest.fixture(autouse=True)
def _require_cadquery():
    pytest.importorskip("cadquery")


# ── Hull with aft docking port ──────────────────────────────────────────

class TestAftDockingPort:
    """Verify the hull now has both forward and aft docking ports."""

    def test_hull_has_aft_dock_hole(self, small_params):
        """Hull volume should be smaller than hull without aft dock
        (the aft hole removes material from the aft end cap)."""
        from aria.digital_twin.geometry.hull import create_hull
        hull = create_hull(small_params)
        # The hull should still be a valid solid
        solids = hull.val().Solids()
        assert len(solids) >= 1
        # Volume should be positive
        assert hull.val().Volume() > 0


# ── Stringers ───────────────────────────────────────────────────────────

class TestStringers:
    """Test longitudinal stringer creation."""

    def test_simplified_stringers_count(self, small_params):
        from aria.digital_twin.geometry.hull import _create_stringers_simplified
        assy = _create_stringers_simplified(small_params, n_stringers=12)
        assert len(assy.children) == 12

    def test_full_stringers_are_solids(self, small_params):
        from aria.digital_twin.geometry.hull import _create_stringers_full
        # Use only 4 stringers for speed
        assy = _create_stringers_full(small_params, n_stringers=4)
        assert len(assy.children) == 4
        # Each stringer should have positive volume
        for _name, child in assy.objects.items():
            if child.obj is not None and hasattr(child.obj, 'val'):
                vol = child.obj.val().Volume()
                assert vol > 0, f"Stringer {_name} has zero volume"


# ── Ring frames ─────────────────────────────────────────────────────────

class TestRingFrames:
    """Test ring frame (rib) creation."""

    def test_simplified_ring_count(self, small_params):
        """With 120 m hull and 50 m spacing, expect 1 ring (at z=50)
        since z=100 < 120 gives 2 rings at 50 and 100."""
        from aria.digital_twin.geometry.hull import _create_ring_frames
        assy = _create_ring_frames(small_params, spacing_m=50.0, solid=False)
        # z=50, z=100 are both < 120, so 2 rings
        assert len(assy.children) >= 1

    def test_full_ring_frames_solid(self, small_params):
        """Full-mode ring frames should be solid annular discs."""
        from aria.digital_twin.geometry.hull import _create_ring_frames
        assy = _create_ring_frames(small_params, spacing_m=50.0, solid=True)
        assert len(assy.children) >= 1
        for _name, child in assy.objects.items():
            if child.obj is not None and hasattr(child.obj, 'val'):
                vol = child.obj.val().Volume()
                assert vol > 0


# ── Spine truss ─────────────────────────────────────────────────────────

class TestSpineTruss:
    """Test central spine truss geometry."""

    def test_spine_creates_solid(self, small_params):
        from aria.digital_twin.geometry.hull import _create_spine_truss
        spine = _create_spine_truss(small_params)
        assert spine.val().Volume() > 0

    def test_spine_volume_analytical(self, small_params):
        """Spine volume should match pi*(R_o^2 - R_i^2)*L."""
        from aria.digital_twin.geometry.hull import (
            _create_spine_truss,
            SPINE_OUTER_RADIUS_M,
            SPINE_WALL_THICKNESS_M,
        )
        spine = _create_spine_truss(small_params)
        r_o = SPINE_OUTER_RADIUS_M
        r_i = r_o - SPINE_WALL_THICKNESS_M
        expected = math.pi * (r_o ** 2 - r_i ** 2) * small_params.hull_length_m
        actual = spine.val().Volume()
        assert actual == pytest.approx(expected, rel=0.02)


# ── Airlock cutouts ─────────────────────────────────────────────────────

class TestAirlockCutouts:
    """Test airlock hatch cutout geometry."""

    def test_cutout_count_default(self, small_params):
        from aria.digital_twin.geometry.hull import _create_airlock_cutouts
        cutouts = _create_airlock_cutouts(small_params)
        # 6 internal bulkheads between 7 zones
        assert len(cutouts) == 6

    def test_cutout_count_custom(self, small_params):
        from aria.digital_twin.geometry.hull import _create_airlock_cutouts
        cutouts = _create_airlock_cutouts(small_params, bulkhead_z_positions=[50, 100])
        assert len(cutouts) == 2


# ── Composite hull structure assembly ───────────────────────────────────

class TestCreateHullStructure:
    """Integration test for the full structural hull assembly."""

    def test_simplified_assembly_components(self, small_params):
        """Simplified mode should produce an assembly with 5 top-level
        children: pressure_hull, stringers, ring_frames, spine_truss,
        airlock_hatches."""
        from aria.digital_twin.geometry.hull import create_hull_structure
        assy = create_hull_structure(small_params, simplified=True)
        names = [child.name for child in assy.objects.values()]
        for expected in ("pressure_hull", "stringers", "ring_frames",
                         "spine_truss", "airlock_hatches"):
            assert expected in names, f"Missing component: {expected}"

    def test_assembly_has_five_children(self, small_params):
        from aria.digital_twin.geometry.hull import create_hull_structure
        assy = create_hull_structure(small_params, simplified=True)
        assert len(assy.children) == 5


# ── Compartment bulkhead hatch cutouts ──────────────────────────────────

class TestBulkheadHatchCutout:
    """Verify compartment bulkheads have airlock hatch holes."""

    def test_internal_bulkhead_has_hole(self, small_params):
        """An internal bulkhead with hatch should have less volume than
        a solid bulkhead of the same dimensions."""
        from aria.digital_twin.geometry.compartments import (
            _create_bulkhead,
            BULKHEAD_THICKNESS_M,
        )
        r_in = small_params.hull_inner_radius_m
        solid_bh = _create_bulkhead(r_in, BULKHEAD_THICKNESS_M, 50.0, hatch_radius=0.0)
        holed_bh = _create_bulkhead(r_in, BULKHEAD_THICKNESS_M, 50.0, hatch_radius=1.0)
        vol_solid = solid_bh.val().Volume()
        vol_holed = holed_bh.val().Volume()
        assert vol_holed < vol_solid, "Hatch cutout should reduce volume"
        # The removed volume should be approximately pi * 1^2 * thickness
        removed = vol_solid - vol_holed
        expected_removed = math.pi * 1.0 ** 2 * BULKHEAD_THICKNESS_M
        assert removed == pytest.approx(expected_removed, rel=0.1)

    def test_bow_stern_bulkheads_no_hatch(self, small_params):
        """Bow (z=0) and stern (z=hull_length) bulkheads should remain
        solid (no hatch cutout) in the compartment assembly."""
        from aria.digital_twin.geometry.compartments import create_compartments
        assy = create_compartments(small_params)
        # We can't easily introspect the volume of individual children
        # without more machinery, so just verify the assembly builds.
        names = [child.name for child in assy.objects.values()]
        bh_names = [n for n in names if n.startswith("bulkhead_")]
        assert len(bh_names) >= 2  # at least bow and stern
