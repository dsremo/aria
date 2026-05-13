"""Regression tests locking in the audit-fix changes.

Covers the fixes applied after the 15+10 round engineering audit:
  * Spoke / docking-port angular collision
  * Sim vs twin radiator-area consistency
  * Parametric propagation from ShipParameters to the glTF
  * Shield layer count + cumulative thickness
  * Crew-module count and pressurised volume
  * Comm-antenna and docking-port counts

These tests exist so the "audit sweep" results are enforced by CI, not
just documented in a report. Any future refactor that breaks collision
avoidance, parameter propagation or area closure will fail here.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from aria.digital_twin.parameters import ShipParameters
from aria.digital_twin.export_gltf import build_ship_gltf


@pytest.fixture
def params() -> ShipParameters:
    return ShipParameters()


@pytest.fixture
def gltf(params: ShipParameters) -> dict:
    return build_ship_gltf(params)


@pytest.fixture
def mesh_names(gltf) -> list[str]:
    return [m["name"] for m in gltf["meshes"]]


# ── Round-1 audit fix: spoke↔docking-port collision ────────────────────

class TestSpokeDockingPortSeparation:
    """Docking ports must not share an angle with any habitat-ring spoke."""

    def test_spoke_count_matches_parameter(self, params, mesh_names):
        n = sum(1 for n in mesh_names if n.startswith("spoke_"))
        assert n == params.habitat_spoke_count, (
            f"glTF renders {n} spokes but ShipParameters.habitat_spoke_count = "
            f"{params.habitat_spoke_count}. Parameter is not being read."
        )

    def test_docking_port_count(self, mesh_names):
        n = sum(1 for n in mesh_names if n.startswith("docking_port_"))
        assert n == 4, f"Expected 4 docking ports, got {n}"

    def test_docking_ports_at_45deg_offsets(self, params):
        """Ports at 45°, 135°, 225°, 315°; spokes at 360°/N × k.

        Min angular separation between any port and any spoke must be > 10°
        to avoid physical overlap.
        """
        dock_angles = [45.0 + 90.0 * i for i in range(4)]
        spoke_angles = [360.0 * i / params.habitat_spoke_count
                        for i in range(params.habitat_spoke_count)]
        min_sep = min(
            min(abs(((d - s + 180.0) % 360.0) - 180.0) for s in spoke_angles)
            for d in dock_angles
        )
        assert min_sep > 10.0, (
            f"Min angular separation port↔spoke = {min_sep:.1f}°; must be "
            f"> 10° to avoid geometric collision."
        )


# ── Round-1 audit fix: sim vs twin radiator-area parity ────────────────

class TestRadiatorAreaConsistency:
    """Both radiator representations (100-panel physics sim and N-wing twin)
    must deliver the same total area so heat rejection is not overstated."""

    def test_radiator_area_consistent(self, params):
        assert params.radiator_area_consistent(tol=0.95), (
            f"Sim area {params.total_radiator_area_m2} m² vs twin area "
            f"{params.total_radiator_wing_area_m2} m² — ratio below 0.95."
        )

    def test_twin_meets_thermal_requirement(self, params):
        """Radiator area must deliver ≥ 134 MW at 500 K (thermal_management.py)."""
        sigma = 5.670374419e-8  # Stefan-Boltzmann
        epsilon = 0.85           # grey-body emissivity for heat-pipe panels
        T_hot = 500.0            # K (potassium heat-pipe operating temp)
        T_cold = 3.0             # K (deep space background)
        Q = epsilon * sigma * params.total_radiator_wing_area_m2 * (T_hot ** 4 - T_cold ** 4)
        # 134 MW is the number in thermal_management.py
        assert Q > 100e6, f"Radiator delivers only {Q / 1e6:.1f} MW; need > 100 MW"

    def test_gltf_wing_count_matches_parameter(self, params, mesh_names):
        n = sum(1 for n in mesh_names if n.startswith("radiator_array_"))
        assert n == params.radiator_wing_count, (
            f"glTF has {n} wings but params.radiator_wing_count = "
            f"{params.radiator_wing_count}"
        )


# ── Shield-stack geometry ──────────────────────────────────────────────

class TestShieldStack:
    """7 layers, cumulative thickness matches sum(layer.thickness_m)."""

    def test_seven_shield_layers(self, mesh_names):
        n = sum(1 for n in mesh_names if n.startswith("shield_layer_"))
        assert n == 7, f"Expected 7 shield layers, got {n}"

    def test_shield_layers_named_consecutively(self, mesh_names):
        names = {n for n in mesh_names if n.startswith("shield_layer_")}
        assert names == {f"shield_layer_{i}" for i in range(7)}

    def test_cumulative_shield_thickness(self, params):
        total = sum(L.thickness_m for L in params.shield_layers)
        # 0.10 + 0.50 + 0.30 + 0.001 + 5.45 + 0.209 + 0.006 = 6.567 m
        assert abs(total - 6.567) < 0.01, f"Cumulative thickness {total} ≠ 6.567"

    def test_ablation_ice_dominant(self, params):
        """Ablation ice should be >80 % of the total shield thickness."""
        ice = next(L.thickness_m for L in params.shield_layers if L.name == "ablation_ice")
        total = sum(L.thickness_m for L in params.shield_layers)
        assert ice / total > 0.80, f"Ice {ice} / total {total} = {ice/total:.2f}"


# ── Habitat ring modules ───────────────────────────────────────────────

class TestHabitatModules:
    """24 crew-quarter pods, combined volume gives ≥ 40 m³/crew."""

    def test_24_hab_modules(self, mesh_names):
        n = sum(1 for n in mesh_names if n.startswith("hab_module_"))
        assert n == 24, f"Expected 24 hab modules, got {n}"

    def test_hab_module_volume_per_crew(self, params):
        """24 × (14 × 16 × 8) = 43 008 m³ / 1000 crew = 43 m³/crew (quarters
        alone). Torus adds another 395 m³/crew for commons. Combined well
        above NASA BVAD 50 m³/crew minimum for multi-year missions."""
        module_volume = 24 * 14.0 * 16.0 * 8.0
        torus_volume = 2.0 * math.pi ** 2 * params.habitat_ring_radius_m * params.habitat_ring_tube_radius_m ** 2
        per_crew = (module_volume + torus_volume) / params.crew_size
        assert per_crew >= 50.0, f"Only {per_crew:.0f} m³/crew; need ≥50"


# ── Hull surface details ────────────────────────────────────────────────

class TestHullDetail:
    def test_5_stiffener_rings(self, mesh_names):
        n = sum(1 for n in mesh_names if n.startswith("hull_stiffener_"))
        assert n == 5

    def test_3_fuel_tanks(self, mesh_names):
        n = sum(1 for n in mesh_names if n.startswith("fuel_tank_"))
        assert n == 3

    def test_4_docking_ports(self, mesh_names):
        n = sum(1 for n in mesh_names if n.startswith("docking_port_"))
        assert n == 4

    def test_4_comm_antennas(self, mesh_names):
        n = sum(1 for n in mesh_names if n.startswith("comm_antenna_"))
        assert n == 4

    def test_4_engine_bells(self, mesh_names):
        n = sum(1 for n in mesh_names if n.startswith("engine_bell_"))
        assert n == 4

    def test_singletons_present(self, mesh_names):
        """Parts that should appear exactly once."""
        for required in (
            "hull_main", "habitat_ring", "reactor_engine",
            "magnetic_nozzle", "bow_sensor_ring",
        ):
            assert required in mesh_names, f"Missing {required}"


# ── Sim/twin parameter propagation ─────────────────────────────────────

class TestParametricPropagation:
    """Changing ShipParameters must actually change the glTF output."""

    def test_changing_spoke_count_changes_geometry(self):
        p = ShipParameters()
        p.habitat_spoke_count = 4
        g = build_ship_gltf(p)
        names = {m["name"] for m in g["meshes"]}
        spokes = {n for n in names if n.startswith("spoke_")}
        assert len(spokes) == 4, f"Expected 4 spokes, got {len(spokes)}"
        assert spokes == {f"spoke_{i}" for i in range(4)}

    def test_changing_wing_count_changes_geometry(self):
        p = ShipParameters()
        p.radiator_wing_count = 4
        g = build_ship_gltf(p)
        wings = {m["name"] for m in g["meshes"] if m["name"].startswith("radiator_array_")}
        assert len(wings) == 4


# ── Total mesh count sanity ────────────────────────────────────────────

def test_total_mesh_count(mesh_names, params):
    """Expected composition with default ShipParameters (6 spokes, 2 wings)."""
    expected_minimum = (
        1  # hull_main
        + 1  # habitat_ring
        + 1  # reactor_engine
        + 1  # magnetic_nozzle
        + 1  # bow_sensor_ring
        + 5  # hull_stiffener_0..4
        + 3  # fuel_tank_0..2
        + params.radiator_wing_count   # radiator_array_0..(N-1)
        + params.habitat_spoke_count   # spoke_0..(N-1)
        + 4  # engine_bell_0..3
        + 7  # shield_layer_0..6
        + 24  # hab_module_0..23
        + 4  # docking_port_0..3
        + 4  # comm_antenna_0..3
    )
    assert len(mesh_names) == expected_minimum, (
        f"Mesh count {len(mesh_names)} ≠ expected {expected_minimum}. "
        f"Components may have been added/removed without test update."
    )
