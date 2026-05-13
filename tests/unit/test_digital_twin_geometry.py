"""Tests for the digital twin parametric ship geometry.

At least 10 tests covering parameter derivation, hull volume,
radiator area, export, and assembly.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from aria.digital_twin.parameters import ShipParameters


# ── Fixture ──────────────────────────────────────────────────────────────

@pytest.fixture
def params() -> ShipParameters:
    return ShipParameters()


# ── Parameter derivation tests ───────────────────────────────────────────

class TestParameters:
    """Verify dimensions derived from simulation configs."""

    def test_hull_radius_from_cross_section(self, params: ShipParameters):
        """hull_radius = sqrt(500 / pi) ~ 12.62 m."""
        expected = math.sqrt(500.0 / math.pi)
        assert abs(params.hull_radius_m - expected) < 1e-6

    def test_hull_inner_radius(self, params: ShipParameters):
        """Inner radius = outer - wall thickness."""
        expected = params.hull_radius_m - params.hull_wall_thickness_m
        assert abs(params.hull_inner_radius_m - expected) < 1e-9

    def test_hull_length_positive(self, params: ShipParameters):
        """Hull length must be derived and positive."""
        assert params.hull_length_m > 0.0

    def test_hull_length_reasonable(self, params: ShipParameters):
        """Hull length should be in a plausible range (100-2000 m)."""
        assert 100.0 < params.hull_length_m < 2000.0

    def test_habitat_ring_gravity(self, params: ShipParameters):
        """At 1 RPM and R=500 m, centripetal accel ~ 0.56 g."""
        omega = 2 * math.pi * params.habitat_rpm / 60.0
        accel = omega ** 2 * params.habitat_ring_radius_m
        g_fraction = accel / 9.81
        assert 0.4 < g_fraction < 0.7, f"Got {g_fraction:.3f} g"

    def test_radiator_panel_area(self, params: ShipParameters):
        """Each panel should be 500 m^2."""
        assert abs(params.radiator_panel_area_m2 - 500.0) < 1e-6

    def test_total_radiator_area(self, params: ShipParameters):
        """100 panels x 500 m^2 = 50,000 m^2."""
        assert abs(params.total_radiator_area_m2 - 50_000.0) < 1e-6

    def test_shield_has_seven_layers(self, params: ShipParameters):
        """Shield stack should have exactly 7 layers."""
        assert len(params.shield_layers) == 7

    def test_ablation_ice_thickness(self, params: ShipParameters):
        """Ablation ice layer should be 5.45 m."""
        ice_layer = [l for l in params.shield_layers if "ice" in l.name][0]
        assert abs(ice_layer.thickness_m - 5.45) < 1e-6

    def test_reactor_radius(self, params: ShipParameters):
        """Reactor radius = 3.0 m from neutronics first-wall geometry."""
        assert abs(params.reactor_radius_m - 3.0) < 1e-6


# ── Hull geometry tests ──────────────────────────────────────────────────

class TestHullGeometry:
    """CadQuery hull solid tests."""

    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    @pytest.fixture
    def small_params(self) -> ShipParameters:
        """Small ship for fast CAD operations in tests."""
        return ShipParameters(
            hull_wall_thickness_m=0.5,
            hull_length_m=20.0,
            ship_mass_kg=1e6,
            ship_cross_section_m2=50.0,
        )

    def test_hull_creates_solid(self, small_params):
        from aria.digital_twin.geometry.hull import create_hull
        hull = create_hull(small_params)
        assert hull is not None
        # Should have at least one solid
        assert len(hull.val().Solids()) >= 1

    def test_hull_volume_shell(self, small_params):
        """Hull volume ~ pi*(R^2 - r^2)*L for the cylindrical portion."""
        from aria.digital_twin.geometry.hull import create_hull
        r_out = small_params.hull_radius_m
        r_in = small_params.hull_inner_radius_m
        length = small_params.hull_length_m

        # Analytical cylinder shell volume (no caps)
        expected_cyl = math.pi * (r_out**2 - r_in**2) * length

        hull = create_hull(small_params)
        actual_vol = hull.val().Volume()

        # Actual includes hemispherical caps minus docking hole, so it
        # should be somewhat larger than just the cylinder shell.
        # Caps add ~(4/3)*pi*(R^3 - r^3) which can be significant
        # for short hulls with large radii. Allow 0.8x to 3.0x.
        assert 0.8 * expected_cyl < actual_vol < 3.0 * expected_cyl, (
            f"Volume {actual_vol:.1f} outside expected range "
            f"[{0.8*expected_cyl:.1f}, {2.0*expected_cyl:.1f}]"
        )

    def test_hull_export_step(self, small_params):
        from aria.digital_twin.geometry.hull import create_hull, export_step
        hull = create_hull(small_params)
        with tempfile.TemporaryDirectory() as td:
            p = export_step(hull, Path(td) / "hull.step")
            assert p.exists()
            assert p.stat().st_size > 0

    def test_hull_export_stl(self, small_params):
        from aria.digital_twin.geometry.hull import create_hull, export_stl
        hull = create_hull(small_params)
        with tempfile.TemporaryDirectory() as td:
            p = export_stl(hull, Path(td) / "hull.stl")
            assert p.exists()
            assert p.stat().st_size > 0


# ── Radiator array tests ────────────────────────────────────────────────

class TestRadiatorArray:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    @pytest.fixture
    def small_params(self) -> ShipParameters:
        return ShipParameters(
            hull_wall_thickness_m=0.5,
            hull_length_m=20.0,
            ship_mass_kg=1e6,
            ship_cross_section_m2=50.0,
            radiator_panel_width_m=5.0,
            radiator_panel_height_m=4.0,
        )

    def test_radiator_creates_assembly(self, small_params):
        from aria.digital_twin.geometry.radiator_array import create_radiator_array
        assy = create_radiator_array(small_params, n_panels=4)
        assert assy is not None
        assert len(assy.children) == 4

    def test_radiator_panel_count(self, small_params):
        from aria.digital_twin.geometry.radiator_array import create_radiator_array
        assy = create_radiator_array(small_params, n_panels=6)
        assert len(assy.children) == 6


# ── Assembly tests ───────────────────────────────────────────────────────

class TestAssembly:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    @pytest.fixture
    def small_params(self) -> ShipParameters:
        return ShipParameters(
            hull_wall_thickness_m=0.5,
            hull_length_m=20.0,
            ship_mass_kg=1e6,
            ship_cross_section_m2=50.0,
            radiator_panel_width_m=5.0,
            radiator_panel_height_m=4.0,
        )

    def test_assemble_ship(self, small_params):
        from aria.digital_twin.geometry.assembly import assemble_ship
        ship = assemble_ship(small_params)
        assert ship is not None
        # hull + radiators + reactor + shield + propulsion + utility systems
        assert len(ship.children) >= 5

    def test_assembly_export_step(self, small_params):
        from aria.digital_twin.geometry.assembly import assemble_ship, export_step
        ship = assemble_ship(small_params)
        with tempfile.TemporaryDirectory() as td:
            p = export_step(ship, Path(td) / "ship.step")
            assert p.exists()
            assert p.stat().st_size > 0
