"""Tests for Phase 2 digital twin subsystem geometries.

Covers reactor module, shield stack, propulsion, habitat ring,
and the updated assembly with all subsystems integrated.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aria.digital_twin.parameters import ShipParameters


# ── Shared fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def params() -> ShipParameters:
    return ShipParameters()


@pytest.fixture
def small_params() -> ShipParameters:
    """Small ship for fast CAD operations in tests."""
    return ShipParameters(
        hull_wall_thickness_m=0.5,
        hull_length_m=20.0,
        ship_mass_kg=1e6,
        ship_cross_section_m2=50.0,
        radiator_panel_width_m=5.0,
        radiator_panel_height_m=4.0,
        reactor_radius_m=1.5,
        reactor_length_m=4.0,
        habitat_ring_radius_m=30.0,
        habitat_ring_tube_radius_m=3.0,
    )


# ── Reactor module tests ────────────────────────────────────────────────

class TestReactorModule:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    def test_reactor_creates_solid(self, small_params):
        from aria.digital_twin.geometry.reactor_module import create_reactor_module
        reactor = create_reactor_module(small_params)
        assert reactor is not None
        solids = reactor.val().Solids()
        assert len(solids) >= 1

    def test_reactor_has_nested_cylinders(self, small_params):
        """The module should contain 4 concentric shells fused into one solid.

        We verify this indirectly by checking the volume is larger than
        just the innermost vessel but smaller than a solid cylinder of
        the outermost radius.
        """
        import math
        from aria.digital_twin.geometry.reactor_module import create_reactor_module
        reactor = create_reactor_module(small_params)
        volume = reactor.val().Volume()

        r_inner = small_params.reactor_radius_m
        r_outer = r_inner + 0.5 + 0.3 + 1.0  # blanket + neutron + bio
        L = small_params.reactor_length_m

        # Volume should be between inner shell only and full solid cylinder
        inner_shell_vol = math.pi * (r_inner**2 - (r_inner - 0.1)**2) * L
        full_solid_vol = math.pi * r_outer**2 * L
        assert inner_shell_vol < volume < full_solid_vol

    def test_reactor_volume_positive(self, small_params):
        from aria.digital_twin.geometry.reactor_module import create_reactor_module
        reactor = create_reactor_module(small_params)
        assert reactor.val().Volume() > 0


# ── Shield stack tests ──────────────────────────────────────────────────

class TestShieldStack:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    def test_shield_stack_has_seven_layers(self, small_params):
        from aria.digital_twin.geometry.shield_stack import create_shield_stack
        stack = create_shield_stack(small_params)
        # Assembly should have 7 children (one per layer)
        assert len(stack.children) == 7

    def test_shield_stack_layer_names(self, small_params):
        from aria.digital_twin.geometry.shield_stack import create_shield_stack
        stack = create_shield_stack(small_params)
        names = [child.name for child in stack.children]
        assert "L1_detection_sensors" in names
        assert "L5_ablation_ice" in names
        assert "L7_structural_hull" in names

    def test_shield_stack_is_assembly(self, small_params):
        import cadquery as cq
        from aria.digital_twin.geometry.shield_stack import create_shield_stack
        stack = create_shield_stack(small_params)
        assert isinstance(stack, cq.Assembly)


# ── Propulsion tests ────────────────────────────────────────────────────

class TestPropulsion:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    def test_propulsion_creates_assembly(self, small_params):
        import cadquery as cq
        from aria.digital_twin.geometry.propulsion import create_propulsion
        prop = create_propulsion(small_params)
        assert isinstance(prop, cq.Assembly)

    def test_propulsion_has_nozzle_and_magsail(self, small_params):
        from aria.digital_twin.geometry.propulsion import create_propulsion
        prop = create_propulsion(small_params)
        names = [child.name for child in prop.children]
        assert "fusion_drive_nozzle" in names
        assert "magsail_coil_50km" in names

    def test_nozzle_is_conical(self, small_params):
        """The nozzle should be a lofted solid (conical shape).

        Verify it has positive volume and the bounding box is
        roughly 10m x 10m x 10m (base diameter x height).
        """
        from aria.digital_twin.geometry.propulsion import _make_nozzle
        nozzle = _make_nozzle(base_radius=5.0, length=10.0)
        bb = nozzle.val().BoundingBox()
        # X extent ~ 10 m (diameter), Z extent ~ 10 m (length)
        x_extent = bb.xmax - bb.xmin
        z_extent = bb.zmax - bb.zmin
        assert 9.0 < x_extent < 11.0, f"X extent {x_extent}"
        assert 9.0 < z_extent < 11.0, f"Z extent {z_extent}"


# ── Habitat ring tests ──────────────────────────────────────────────────

class TestHabitatRing:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    def test_habitat_simplified_creates_assembly(self, small_params):
        import cadquery as cq
        from aria.digital_twin.geometry.habitat_ring import create_habitat_ring
        hab = create_habitat_ring(small_params, simplified=True)
        assert isinstance(hab, cq.Assembly)

    def test_habitat_has_spokes(self, small_params):
        from aria.digital_twin.geometry.habitat_ring import create_habitat_ring
        hab = create_habitat_ring(small_params, simplified=True)
        spoke_names = [c.name for c in hab.children if "spoke" in c.name]
        assert len(spoke_names) == small_params.habitat_spoke_count

    def test_habitat_full_torus(self, small_params):
        """Full torus mode with small radii should produce valid geometry."""
        from aria.digital_twin.geometry.habitat_ring import create_habitat_ring
        hab = create_habitat_ring(small_params, simplified=False)
        torus_children = [c for c in hab.children if "torus" in c.name]
        assert len(torus_children) == 1


# ── Updated assembly tests ──────────────────────────────────────────────

class TestPhase2Assembly:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    def test_assembly_includes_all_subsystems(self, small_params):
        from aria.digital_twin.geometry.assembly import assemble_ship
        ship = assemble_ship(small_params)
        names = [child.name for child in ship.children]
        assert "hull" in names
        assert "radiators" in names
        assert "reactor_module" in names
        assert "shield_stack" in names
        assert "propulsion" in names

    def test_assembly_child_count_without_habitat(self, small_params):
        from aria.digital_twin.geometry.assembly import assemble_ship
        ship = assemble_ship(small_params, include_habitat=False)
        # hull + radiators + reactor + shield_stack + propulsion + utilities
        assert len(ship.children) >= 5

    def test_assembly_with_habitat(self, small_params):
        from aria.digital_twin.geometry.assembly import assemble_ship
        ship = assemble_ship(small_params, include_habitat=True, habitat_simplified=True)
        names = [child.name for child in ship.children]
        assert "habitat_ring" in names
        assert len(ship.children) >= 6

    def test_assembly_export_step(self, small_params):
        from aria.digital_twin.geometry.assembly import assemble_ship, export_step
        ship = assemble_ship(small_params)
        with tempfile.TemporaryDirectory() as td:
            p = export_step(ship, Path(td) / "ship_phase2.step")
            assert p.exists()
            assert p.stat().st_size > 0
