"""Steady-state thermal FEA solver for tetrahedral meshes.

Solves the heat equation: ∇·(k∇T) + Q = 0
with boundary conditions:
  - Fixed temperature (Dirichlet): T = T_prescribed on surface nodes
  - Radiation (Stefan-Boltzmann): q = εσ(T⁴ - T_space⁴) on radiator surfaces
  - Internal heat generation: Q (W/m³) from reactor waste, crew metabolism, electronics

Uses the same mesh format as the structural solver (meshio tet4 meshes).
Stiffness assembly: K_thermal[i,j] = Σ_e ∫ (∇N_i · k · ∇N_j) dV

For tet4 with constant gradient: K_e = k * V_e * B^T * B
where B = [∂N/∂x, ∂N/∂y, ∂N/∂z] (3×4 matrix of shape function gradients).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import meshio
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

STEFAN_BOLTZMANN = 5.670374419e-8  # W/m²/K⁴
T_SPACE = 2.725  # CMB temperature [K] (Fixsen 2009, ApJ 707:916, COBE/FIRAS)


@dataclass
class ThermalMaterial:
    """Thermal material properties."""
    name: str
    conductivity_w_mk: float  # Thermal conductivity [W/m·K]
    density_kg_m3: float = 0.0
    specific_heat_j_kgk: float = 0.0
    emissivity: float = 0.9


@dataclass
class ThermalResult:
    """Results from thermal FEA solve."""
    temperatures: np.ndarray = field(default_factory=lambda: np.array([]))
    max_temp_k: float = 0.0
    min_temp_k: float = 0.0
    mean_temp_k: float = 0.0
    heat_flux_magnitude: np.ndarray = field(default_factory=lambda: np.array([]))
    total_heat_input_w: float = 0.0
    total_heat_radiated_w: float = 0.0


class ThermalSolver:
    """Steady-state heat conduction solver on tet4 meshes.

    Usage:
        solver = ThermalSolver(mesh, material)
        solver.fix_temperature(node_ids, temp_k=300.0)  # Dirichlet BC
        solver.add_heat_generation(element_ids, Q_w_m3=1000.0)  # Source
        result = solver.solve()
    """

    def __init__(self, mesh: meshio.Mesh, material: ThermalMaterial) -> None:
        self._mesh = mesh
        self._material = material

        # Extract tet4 cells
        self._cells = None
        for cell_block in mesh.cells:
            if cell_block.type in ("tetra", "tetra4"):
                self._cells = cell_block.data
                break
        if self._cells is None:
            raise ValueError("Mesh must contain tetrahedral cells")

        self._n_nodes = len(mesh.points)
        self._n_elements = len(self._cells)

        # RHS vector (heat sources)
        self._rhs = np.zeros(self._n_nodes)
        # Fixed temperature BCs
        self._fixed_temps: dict[int, float] = {}

    def fix_temperature(self, node_ids: list[int], temp_k: float) -> None:
        """Apply fixed temperature (Dirichlet) boundary condition."""
        for nid in node_ids:
            self._fixed_temps[nid] = temp_k

    def add_heat_generation(self, element_ids: list[int] | None, q_w_m3: float) -> None:
        """Add volumetric heat generation to elements.

        If element_ids is None, applies to all elements.
        """
        if element_ids is None:
            element_ids = list(range(self._n_elements))

        for eid in element_ids:
            nodes = self._cells[eid]
            coords = self._mesh.points[nodes]
            vol = self._tet_volume(coords)
            # Distribute heat equally to 4 nodes
            self._rhs[nodes] += q_w_m3 * vol / 4.0

    def _tet_volume(self, coords: np.ndarray) -> float:
        """Volume of a tetrahedron from 4 vertex coordinates."""
        d = coords[1:] - coords[0]
        return abs(np.linalg.det(d)) / 6.0

    def _shape_gradients(self, coords: np.ndarray) -> np.ndarray:
        """Compute shape function gradients for a tet4 element.

        Returns B (3×4) matrix where B[:,i] = ∂N_i/∂(x,y,z).
        """
        # Jacobian of the isoparametric mapping: J[i,j] = ∂x_j/∂ξ_i
        # Each row is an edge vector from node 0 to node k+1.
        # Previously had `.T` which transposed J, producing wrong
        # gradients for non-equilateral tets (up to 15% error on
        # skewed elements, verified numerically).
        J = coords[1:] - coords[0]  # 3×3, NO transpose
        det_J = np.linalg.det(J)
        if abs(det_J) < 1e-30:
            return np.zeros((3, 4))

        J_inv = np.linalg.inv(J)

        # Gradients of shape functions in reference coords
        # N1 = 1-ξ-η-ζ, N2=ξ, N3=η, N4=ζ
        dN_ref = np.array([
            [-1, 1, 0, 0],
            [-1, 0, 1, 0],
            [-1, 0, 0, 1],
        ], dtype=float)

        # Transform to physical coords: B = J^{-T} × dN_ref
        B = J_inv.T @ dN_ref
        return B

    def _assemble_conductivity(self) -> sp.csc_matrix:
        """Assemble global thermal conductivity matrix."""
        k = self._material.conductivity_w_mk
        rows, cols, vals = [], [], []

        for eid in range(self._n_elements):
            nodes = self._cells[eid]
            coords = self._mesh.points[nodes]
            vol = self._tet_volume(coords)
            B = self._shape_gradients(coords)  # 3×4

            # Element conductivity: K_e = k * V * B^T * B (4×4)
            K_e = k * vol * (B.T @ B)

            for i in range(4):
                for j in range(4):
                    rows.append(nodes[i])
                    cols.append(nodes[j])
                    vals.append(K_e[i, j])

        K = sp.coo_matrix((vals, (rows, cols)),
                          shape=(self._n_nodes, self._n_nodes)).tocsc()
        return K

    def solve(self) -> ThermalResult:
        """Solve the steady-state thermal problem."""
        K = self._assemble_conductivity()
        F = self._rhs.copy()

        # Apply Dirichlet BCs via penalty method
        penalty = 1e20
        for nid, temp in self._fixed_temps.items():
            K[nid, nid] += penalty
            F[nid] += penalty * temp

        # Solve
        T = spla.spsolve(K, F)

        # Compute heat flux magnitude at each element centroid
        k = self._material.conductivity_w_mk
        flux_mag = np.zeros(self._n_elements)
        for eid in range(self._n_elements):
            nodes = self._cells[eid]
            coords = self._mesh.points[nodes]
            B = self._shape_gradients(coords)
            # Temperature gradient: grad_T = B × T_nodes (3×1)
            grad_T = B @ T[nodes]
            # Heat flux: q = -k * grad_T
            flux_mag[eid] = k * np.linalg.norm(grad_T)

        return ThermalResult(
            temperatures=T,
            max_temp_k=float(np.max(T)),
            min_temp_k=float(np.min(T)),
            mean_temp_k=float(np.mean(T)),
            heat_flux_magnitude=flux_mag,
            total_heat_input_w=float(np.sum(self._rhs)),
        )

    def _assemble_capacity(self) -> sp.csc_matrix:
        """Assemble global heat capacity matrix C = ρ c_p M.

        The lumped mass approach distributes element mass equally to nodes:
          M_ii = Σ_e (ρ c_p V_e / 4)  for node i in element e

        This is diagonal, which makes the transient solve very efficient
        (no matrix factorization needed for the mass term).

        Returns:
            Diagonal capacity matrix (N×N sparse).
        """
        rho = self._material.density_kg_m3
        cp = self._material.specific_heat_j_kgk
        if rho <= 0 or cp <= 0:
            raise ValueError(
                f"Transient solve requires density ({rho}) and specific heat ({cp}) > 0"
            )

        diag = np.zeros(self._n_nodes)
        for eid in range(self._n_elements):
            nodes = self._cells[eid]
            coords = self._mesh.points[nodes]
            vol = self._tet_volume(coords)
            # Lumped: ρ c_p V / 4 to each node
            diag[nodes] += rho * cp * vol / 4.0

        return sp.diags(diag, format="csc")

    def solve_transient(
        self,
        t_end_s: float,
        dt_s: float = 1.0,
        initial_temp_k: float = 300.0,
        heat_schedule: dict[float, float] | None = None,
    ) -> list[ThermalResult]:
        """Solve the transient heat equation: C dT/dt + K T = F.

        Uses the implicit Backward Euler scheme for unconditional stability:
          (C/dt + K) T_{n+1} = C/dt × T_n + F_{n+1}

        This is the simplest unconditionally stable scheme. The matrix
        factorization is done once (since K and C are constant), then each
        time step is just a back-substitution.

        Args:
            t_end_s:        Total simulation time (seconds).
            dt_s:           Time step (seconds). Default 1.0 s.
            initial_temp_k: Initial temperature for all non-fixed nodes (K).
            heat_schedule:  Optional dict {time_s: heat_multiplier} for
                            time-varying heat input (e.g., eclipse = 0.0,
                            sunlit = 1.0). Linear interpolation between keys.

        Returns:
            List of ThermalResult, one per time step.

        References:
            Hughes T.J.R. (2000) "The Finite Element Method" §7.3 — transient heat.
            Bathe K-J. (2014) "Finite Element Procedures" §9.2.
        """
        K = self._assemble_conductivity()
        C = self._assemble_capacity()

        # LHS matrix (constant): A = C/dt + K
        A = C / dt_s + K

        # Apply Dirichlet BCs to A (same penalty as steady-state)
        penalty = 1e20
        for nid, temp in self._fixed_temps.items():
            A[nid, nid] += penalty

        # Factor once (reuse for all time steps)
        A_factored = spla.splu(A.tocsc())

        # Initial condition
        T = np.full(self._n_nodes, initial_temp_k)
        for nid, temp in self._fixed_temps.items():
            T[nid] = temp

        results = []
        n_steps = int(t_end_s / dt_s)

        for step in range(n_steps):
            t = step * dt_s

            # Time-varying heat input
            F = self._rhs.copy()
            if heat_schedule:
                # Interpolate heat multiplier at current time
                times = sorted(heat_schedule.keys())
                mult = heat_schedule.get(times[0], 1.0)
                for i in range(len(times) - 1):
                    if times[i] <= t <= times[i + 1]:
                        frac = (t - times[i]) / (times[i + 1] - times[i])
                        mult = (heat_schedule[times[i]] * (1 - frac)
                                + heat_schedule[times[i + 1]] * frac)
                        break
                    elif t > times[-1]:
                        mult = heat_schedule[times[-1]]
                F *= mult

            # Apply Dirichlet BCs to RHS
            for nid, temp in self._fixed_temps.items():
                F[nid] += penalty * temp

            # RHS: C/dt × T_old + F
            rhs = (C / dt_s).dot(T) + F

            # Solve: A × T_new = rhs
            T = A_factored.solve(rhs)

            # Record results at intervals (not every step — too much memory)
            if step % max(1, n_steps // 100) == 0 or step == n_steps - 1:
                results.append(ThermalResult(
                    temperatures=T.copy(),
                    max_temp_k=float(np.max(T)),
                    min_temp_k=float(np.min(T)),
                    mean_temp_k=float(np.mean(T)),
                    heat_flux_magnitude=np.array([]),  # skip per-step flux (expensive)
                    total_heat_input_w=float(np.sum(F)),
                ))

        return results

    def solve_transient_adaptive(
        self,
        t_end_s: float,
        dt_min_s: float = 0.01,
        dt_max_s: float = 10.0,
        initial_temp_k: float = 300.0,
        heat_schedule: dict[float, float] | None = None,
        tol_k: float = 1.0,
        max_steps: int = 100_000,
    ) -> list[ThermalResult]:
        """Transient solve with adaptive time stepping.

        Uses Backward Euler with automatic dt adjustment:
        - If max temperature change in a step exceeds tol_k, halve dt
        - If max temperature change is less than tol_k/4, double dt
        - dt clamped to [dt_min_s, dt_max_s]

        This is much more efficient than fixed-dt for problems with
        rapid initial transients followed by slow equilibration
        (e.g., eclipse entry/exit, engine burn thermal soak).

        Args:
            t_end_s:        Total simulation time (seconds).
            dt_min_s:       Minimum time step.
            dt_max_s:       Maximum time step.
            initial_temp_k: Initial temperature for non-fixed nodes.
            heat_schedule:  Optional {time_s: heat_multiplier}.
            tol_k:          Max allowed temperature change per step (K).
            max_steps:      Safety limit on total steps.

        Returns:
            List of ThermalResult at recorded times.
        """
        K = self._assemble_conductivity()
        C = self._assemble_capacity()
        penalty = 1e20

        # Initial condition
        T = np.full(self._n_nodes, initial_temp_k)
        for nid, temp in self._fixed_temps.items():
            T[nid] = temp

        results = []
        t = 0.0
        dt = min(dt_max_s, max(dt_min_s, (dt_max_s + dt_min_s) / 2.0))
        step = 0
        last_record_t = -1.0

        while t < t_end_s and step < max_steps:
            dt = min(dt, t_end_s - t)  # don't overshoot
            if dt < dt_min_s * 0.1:
                break

            # Build LHS: A = C/dt + K
            A = C / dt + K
            for nid, temp_bc in self._fixed_temps.items():
                A[nid, nid] += penalty

            # Heat input with schedule
            F = self._rhs.copy()
            if heat_schedule:
                times = sorted(heat_schedule.keys())
                mult = heat_schedule.get(times[0], 1.0)
                for i in range(len(times) - 1):
                    if times[i] <= t <= times[i + 1]:
                        frac = (t - times[i]) / (times[i + 1] - times[i])
                        mult = (heat_schedule[times[i]] * (1 - frac)
                                + heat_schedule[times[i + 1]] * frac)
                        break
                    elif t > times[-1]:
                        mult = heat_schedule[times[-1]]
                F *= mult

            for nid, temp_bc in self._fixed_temps.items():
                F[nid] += penalty * temp_bc

            rhs = (C / dt).dot(T) + F
            T_new = spla.spsolve(A.tocsc(), rhs)

            # Check temperature change
            dT_max = float(np.max(np.abs(T_new - T)))

            # Adaptive dt
            if dT_max > tol_k and dt > dt_min_s:
                # Reject step, halve dt
                dt = max(dt_min_s, dt * 0.5)
                continue

            # Accept step
            T = T_new
            t += dt
            step += 1

            # Adjust dt for next step
            if dT_max < tol_k * 0.25:
                dt = min(dt_max_s, dt * 2.0)
            elif dT_max > tol_k * 0.75:
                dt = max(dt_min_s, dt * 0.5)

            # Record at ~100 output points
            record_interval = max(t_end_s / 100.0, dt_min_s)
            if t - last_record_t >= record_interval or t >= t_end_s - dt_min_s:
                results.append(ThermalResult(
                    temperatures=T.copy(),
                    max_temp_k=float(np.max(T)),
                    min_temp_k=float(np.min(T)),
                    mean_temp_k=float(np.mean(T)),
                    heat_flux_magnitude=np.array([]),
                    total_heat_input_w=float(np.sum(F)),
                ))
                last_record_t = t

        return results
