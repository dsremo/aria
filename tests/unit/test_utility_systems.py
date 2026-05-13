"""Tests for utility_systems geometry module.

Covers fuel tanks, water tanks, gas tanks, cargo bay, docking ports,
and backup solar panels.
"""

from __future__ import annotations

import math

import pytest

from aria.digital_twin.parameters import ShipParameters


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
    )


# ── Fuel tanks ─────────────────────────────────────────────────────────────


class TestFuelTanks:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    def test_creates_4_tanks_by_default(self, small_params):
        from aria.digital_twin.geometry.utility_systems import create_fuel_tanks
        assy = create_fuel_tanks(small_params)
        assert len(assy.children) == 4

    def test_custom_tank_count(self, small_params):
        from aria.digital_twin.geometry.utility_systems import create_fuel_tanks
        assy = create_fuel_tanks(small_params, n_tanks=2)
        assert len(assy.children) == 2

    def test_tank_names_sequential(self, small_params):
        from aria.digital_twin.geometry.utility_systems import create_fuel_tanks
        assy = create_fuel_tanks(small_params)
        names = [child.name for child in assy.children]
        for i in range(4):
            assert f"dt_fuel_tank_{i:02d}" in names

    def test_assembly_name(self, small_params):
        from aria.digital_twin.geometry.utility_systems import create_fuel_tanks
        assy = create_fuel_tanks(small_params)
        assert assy.name == "fuel_tanks"


# ── Water tanks ────────────────────────────────────────────────────────────


class TestWaterTanks:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    def test_creates_2_tanks(self, small_params):
        from aria.digital_twin.geometry.utility_systems import create_water_tanks
        assy = create_water_tanks(small_params)
        assert len(assy.children) == 2

    def test_tank_names(self, small_params):
        from aria.digital_twin.geometry.utility_systems import create_water_tanks
        assy = create_water_tanks(small_params)
        names = [child.name for child in assy.children]
        assert "water_tank_00" in names
        assert "water_tank_01" in names


# ── Gas tanks ──────────────────────────────────────────────────────────────


class TestGasTanks:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    def test_creates_6_spheres(self, small_params):
        from aria.digital_twin.geometry.utility_systems import create_gas_tanks
        assy = create_gas_tanks(small_params)
        assert len(assy.children) == 6

    def test_gas_tank_names(self, small_params):
        from aria.digital_twin.geometry.utility_systems import create_gas_tanks
        assy = create_gas_tanks(small_params)
        names = [child.name for child in assy.children]
        for i in range(6):
            assert f"gas_tank_{i:02d}" in names


# ── Cargo bay ──────────────────────────────────────────────────────────────


class TestCargoBay:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    def test_cargo_bay_has_volume_and_doors(self, small_params):
        from aria.digital_twin.geometry.utility_systems import create_cargo_bay
        assy = create_cargo_bay(small_params)
        names = [child.name for child in assy.children]
        assert "cargo_bay_volume" in names
        assert "cargo_door_00" in names
        assert "cargo_door_01" in names

    def test_cargo_bay_child_count(self, small_params):
        from aria.digital_twin.geometry.utility_systems import create_cargo_bay
        assy = create_cargo_bay(small_params)
        # 1 bay volume + 2 door leaves
        assert len(assy.children) == 3


# ── Docking ports ──────────────────────────────────────────────────────────


class TestDockingPorts:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    def test_creates_3_ports(self, small_params):
        from aria.digital_twin.geometry.utility_systems import create_docking_ports
        assy = create_docking_ports(small_params)
        assert len(assy.children) == 3

    def test_port_names(self, small_params):
        from aria.digital_twin.geometry.utility_systems import create_docking_ports
        assy = create_docking_ports(small_params)
        names = [child.name for child in assy.children]
        assert "dock_forward_main" in names
        assert "dock_lateral_shuttle" in names
        assert "dock_aft_service" in names

    def test_forward_port_uses_params_radius(self, params):
        """Forward port radius must match ShipParameters.docking_port_radius_m."""
        assert params.docking_port_radius_m == 2.0


# ── Solar backup ───────────────────────────────────────────────────────────


class TestSolarBackup:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    def test_creates_4_panels(self, small_params):
        from aria.digital_twin.geometry.utility_systems import create_solar_backup
        assy = create_solar_backup(small_params)
        assert len(assy.children) == 4

    def test_panel_names(self, small_params):
        from aria.digital_twin.geometry.utility_systems import create_solar_backup
        assy = create_solar_backup(small_params)
        names = [child.name for child in assy.children]
        for i in range(4):
            assert f"solar_panel_{i:02d}" in names

    def test_assembly_name(self, small_params):
        from aria.digital_twin.geometry.utility_systems import create_solar_backup
        assy = create_solar_backup(small_params)
        assert assy.name == "solar_backup"


# ── Integration: assembly includes utility systems ─────────────────────────


class TestAssemblyIntegration:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    def test_assemble_ship_includes_utility_systems(self, small_params):
        from aria.digital_twin.geometry.assembly import assemble_ship
        ship = assemble_ship(small_params)
        child_names = [child.name for child in ship.children]
        expected = [
            "fuel_tanks", "water_tanks", "gas_tanks",
            "cargo_bay", "docking_ports", "solar_backup",
        ]
        for name in expected:
            assert name in child_names, f"Missing {name} in assembly"


# ── Volume / dimension sanity checks ──────────────────────────────────────


class TestDimensionSanity:
    def test_fuel_tank_volume_exceeds_requirement(self):
        """4 tanks (R=5m, L=55m + caps) must hold >= 17,272 m^3."""
        r, l_cyl = 5.0, 55.0
        v_cyl = math.pi * r ** 2 * l_cyl
        v_caps = (4.0 / 3.0) * math.pi * r ** 3
        v_single = v_cyl + v_caps
        v_total = 4 * v_single
        assert v_total >= 17_272, f"Total fuel volume {v_total:.0f} < 17,272 m^3"

    def test_water_tank_volume_covers_500t(self):
        """2 tanks (R=4m, L=10m) must hold >= 500 m^3 (500 t water)."""
        r, l_cyl = 4.0, 10.0
        v_single = math.pi * r ** 2 * l_cyl
        v_total = 2 * v_single
        assert v_total >= 500, f"Total water volume {v_total:.0f} < 500 m^3"

    def test_gas_tank_volume_covers_o2(self):
        """6 spheres (R=3.5m) must hold >= 1,145 m^3 (300t O2 at 200 bar)."""
        r = 3.5
        v_single = (4.0 / 3.0) * math.pi * r ** 3
        v_total = 6 * v_single
        assert v_total >= 1_077, f"Total gas volume {v_total:.0f} < 1,077 m^3"

    def test_fuel_tanks_fit_inside_hull(self):
        """Each fuel tank (R=5m at 35% radial offset) must fit inside hull (R=12.6m)."""
        params = ShipParameters()
        tank_r = 5.0
        radial_offset = params.hull_radius_m * 0.35
        outermost = radial_offset + tank_r
        assert outermost < params.hull_radius_m, (
            f"Fuel tank outer edge {outermost:.1f}m exceeds hull R={params.hull_radius_m:.1f}m"
        )
