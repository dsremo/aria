"""Analytical validation of the thermal FEA solver.

For a 1D bar (hollow cylinder with fixed T at each end), the steady-
state temperature profile is linear: T(z) = T_cold + (T_hot - T_cold) × z/L.

We mesh a short hollow cylinder, fix T=300 K at z=0 and T=600 K at z=L,
and check that the midpoint nodes are near 450 K (the linear interpolant).

This was added after commit a241a67 found a Jacobian-transpose bug that
was producing wrong gradients on skewed tets — the existing test suite
had NO thermal-FEA-specific test to catch it.
"""
from __future__ import annotations

import numpy as np
import pytest

from aria.digital_twin.mesher import mesh_cylinder
from aria.digital_twin.thermal_solver import ThermalSolver, ThermalMaterial


@pytest.fixture(scope="module")
def cylinder_mesh():
    """Small cylinder for thermal testing."""
    return mesh_cylinder(radius=1.0, length=5.0, thickness=0.1, element_size=0.3)


@pytest.fixture(scope="module")
def copper_thermal():
    return ThermalMaterial(name="Cu", conductivity_w_mk=400.0)


def test_linear_temperature_profile(cylinder_mesh, copper_thermal):
    """Fixed T at both ends → linear T(z). Midpoint should be ~average."""
    solver = ThermalSolver(cylinder_mesh, copper_thermal)
    pts = cylinder_mesh.points
    z = pts[:, 2]
    z_min, z_max = float(z.min()), float(z.max())

    cold_nodes = [int(i) for i in range(len(z)) if z[i] < z_min + 0.05]
    hot_nodes  = [int(i) for i in range(len(z)) if z[i] > z_max - 0.05]
    assert len(cold_nodes) > 5
    assert len(hot_nodes)  > 5

    T_COLD, T_HOT = 300.0, 600.0
    solver.fix_temperature(cold_nodes, T_COLD)
    solver.fix_temperature(hot_nodes, T_HOT)

    result = solver.solve()

    # Mid-section nodes (z ≈ L/2)
    L = z_max - z_min
    mid_mask = (z > z_min + 0.4 * L) & (z < z_min + 0.6 * L)
    T_mid = result.temperatures[mid_mask]
    assert len(T_mid) > 5, f"Not enough mid-section nodes ({len(T_mid)})"

    # Linear interpolant at midpoint: (300+600)/2 = 450 K
    expected = (T_COLD + T_HOT) / 2.0
    mean_mid = float(T_mid.mean())
    # Tolerance: 10% of the gradient (30 K) is generous for a coarse mesh.
    assert abs(mean_mid - expected) < 30.0, (
        f"Mid-section mean T = {mean_mid:.1f} K, expected ~{expected:.0f} K "
        f"(±30 K tolerance)"
    )


def test_temperature_bounds(cylinder_mesh, copper_thermal):
    """All temperatures should be between the two fixed boundaries."""
    solver = ThermalSolver(cylinder_mesh, copper_thermal)
    pts = cylinder_mesh.points
    z = pts[:, 2]
    z_min, z_max = float(z.min()), float(z.max())

    cold_nodes = [int(i) for i in range(len(z)) if z[i] < z_min + 0.05]
    hot_nodes  = [int(i) for i in range(len(z)) if z[i] > z_max - 0.05]

    solver.fix_temperature(cold_nodes, 300.0)
    solver.fix_temperature(hot_nodes, 600.0)
    result = solver.solve()

    # Max principle: no temperature should exceed the boundary values
    # (within a small FE tolerance for penalty BCs).
    assert result.min_temp_k >= 295.0, f"T_min {result.min_temp_k:.1f} < 295 K"
    assert result.max_temp_k <= 605.0, f"T_max {result.max_temp_k:.1f} > 605 K"


def test_heat_flux_positive(cylinder_mesh, copper_thermal):
    """Heat flows from hot to cold — flux magnitude should be > 0."""
    solver = ThermalSolver(cylinder_mesh, copper_thermal)
    pts = cylinder_mesh.points
    z = pts[:, 2]
    z_min, z_max = float(z.min()), float(z.max())

    cold_nodes = [int(i) for i in range(len(z)) if z[i] < z_min + 0.05]
    hot_nodes  = [int(i) for i in range(len(z)) if z[i] > z_max - 0.05]

    solver.fix_temperature(cold_nodes, 300.0)
    solver.fix_temperature(hot_nodes, 600.0)
    result = solver.solve()

    assert len(result.heat_flux_magnitude) > 0, "Should have flux data"
    assert float(result.heat_flux_magnitude.max()) > 0, "Heat flux should be positive"
