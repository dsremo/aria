"""Lightweight 3D linear-elastic FEA solver for tetrahedral meshes.

Built on scipy.sparse so there is no dependency on external FE packages.
Supports:
  - Isotropic linear elasticity (Young's modulus E, Poisson's ratio nu)
  - 4-node tetrahedra (tet4) with constant-strain formulation
  - 10-node tetrahedra (tet10) with quadratic shape functions + 4-pt Gauss
  - Pressure loads on surface faces, gravity body forces
  - Fixed (Dirichlet) boundary conditions via penalty method
  - Von Mises stress post-processing at element centroids/Gauss points
  - ICCG iterative solver for large meshes (>50K DOFs)

Analytical validation target:
    Thin-walled pressurised cylinder:
        sigma_hoop  = p * R / t
        sigma_axial = p * R / (2 * t)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

import meshio
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from aria.physics.solid_mechanics.plasticity import (
    consistent_tangent_modulus,
    radial_return_j2,
)


# ---------------------------------------------------------------------------
# Voigt ↔ 3×3 tensor conversion (solver's own convention)
# ---------------------------------------------------------------------------
# Voigt stress order: [σxx, σyy, σzz, τyz, τxz, τxy]
# Voigt strain order: [εxx, εyy, εzz, γyz, γxz, γxy]  (γ = engineering shear = 2·ε_shear)
# These match _isotropic_D and _tet4_B_and_V above.

def _voigt_stress_to_tensor(s: np.ndarray) -> np.ndarray:
    """Voigt (6,) stress → 3×3 symmetric Cauchy tensor."""
    return np.array([
        [s[0], s[5], s[4]],
        [s[5], s[1], s[3]],
        [s[4], s[3], s[2]],
    ], dtype=np.float64)


def _tensor_to_voigt_stress(t: np.ndarray) -> np.ndarray:
    """3×3 symmetric stress tensor → Voigt (6,)."""
    return np.array([t[0, 0], t[1, 1], t[2, 2], t[1, 2], t[0, 2], t[0, 1]], dtype=np.float64)


def _voigt_strain_to_tensor(e: np.ndarray) -> np.ndarray:
    """Voigt (6,) engineering strain → 3×3 tensorial strain (shears halved)."""
    return np.array([
        [e[0],        e[5] * 0.5, e[4] * 0.5],
        [e[5] * 0.5,  e[1],       e[3] * 0.5],
        [e[4] * 0.5,  e[3] * 0.5, e[2]],
    ], dtype=np.float64)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MaterialProperty:
    """Isotropic material properties."""
    name: str
    E: float          # Young's modulus (Pa)
    nu: float         # Poisson's ratio (dimensionless)
    density: float    # kg/m^3

    def __post_init__(self) -> None:
        if not (0.0 < self.nu < 0.5):
            raise ValueError(f"Poisson's ratio must be in (0, 0.5), got {self.nu}")
        if self.E <= 0:
            raise ValueError(f"Young's modulus must be positive, got {self.E}")


@dataclass
class FEAResult:
    """Container for FEA solution."""
    displacements: np.ndarray        # (n_nodes, 3) displacement vector
    von_mises_stress: np.ndarray     # (n_elements,) von Mises at centroid
    max_stress: float
    min_stress: float
    strain_energy: float             # 0.5 * u^T K u


@dataclass
class NonlinearResult:
    """Container for nonlinear (elastoplastic) FEA solution."""
    displacements: np.ndarray        # (n_nodes, 3)
    von_mises_stress: np.ndarray     # (n_elements,)
    plastic_strain: np.ndarray       # (n_elements,) equivalent plastic strain
    max_stress: float
    yield_reached: bool              # True if any element exceeded yield
    converged: bool                  # True if Newton-Raphson converged
    iterations: int                  # number of NR iterations
    load_steps: int                  # number of load increments


@dataclass
class ModalResult:
    """Container for modal / vibration analysis results.

    Attributes
    ----------
    frequencies_hz : list[float]
        Natural frequencies in Hz, sorted ascending.
    mode_shapes : list[np.ndarray]
        Corresponding eigenvectors (each shape ``(n_dof,)``), normalised
        w.r.t. the mass matrix so that φ^T M φ = 1.
    """
    frequencies_hz: list[float] = field(default_factory=list)
    mode_shapes: list[np.ndarray] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Material stiffness matrix
# ---------------------------------------------------------------------------

def _isotropic_D(E: float, nu: float) -> np.ndarray:
    """6x6 material (constitutive) matrix for 3D isotropic elasticity.

    Voigt ordering: [sig_xx, sig_yy, sig_zz, tau_yz, tau_xz, tau_xy].
    """
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    mu = E / (2.0 * (1.0 + nu))

    D = np.array([
        [lam + 2*mu, lam,        lam,        0,  0,  0],
        [lam,        lam + 2*mu, lam,        0,  0,  0],
        [lam,        lam,        lam + 2*mu, 0,  0,  0],
        [0,          0,          0,          mu, 0,  0],
        [0,          0,          0,          0,  mu, 0],
        [0,          0,          0,          0,  0,  mu],
    ], dtype=np.float64)
    return D


# ---------------------------------------------------------------------------
# Tet4 element routines
# ---------------------------------------------------------------------------

def _tet4_B_and_V(coords: np.ndarray) -> Tuple[np.ndarray, float]:
    """Strain-displacement matrix B (6x12) and volume for a tet4 element.

    Parameters
    ----------
    coords : (4, 3) array
        Nodal coordinates of the tetrahedron.

    Returns
    -------
    B : (6, 12) array
    V : float  (positive volume)
    """
    # Jacobian:  J[i,j] = coords[i+1,j] - coords[0,j]  for i=0..2
    x = coords[:, 0]
    y = coords[:, 1]
    z = coords[:, 2]

    # Vectors from node 0 to nodes 1, 2, 3
    J = np.array([
        [x[1] - x[0], y[1] - y[0], z[1] - z[0]],
        [x[2] - x[0], y[2] - y[0], z[2] - z[0]],
        [x[3] - x[0], y[3] - y[0], z[3] - z[0]],
    ], dtype=np.float64)

    detJ = np.linalg.det(J)
    V = abs(detJ) / 6.0

    if V < 1e-30:
        raise ValueError("Degenerate tetrahedron with near-zero volume.")

    # Inverse of J^T gives the shape-function gradients (dN/dx, dN/dy, dN/dz)
    # For tet4, N_i are linear: N0 = 1-xi-eta-zeta, N1=xi, N2=eta, N3=zeta
    # dN/d(physical) = inv(J^T) @ dN/d(parent)
    # dN/d(parent) for nodes 1,2,3 is I(3x3); for node 0 it is -[1,1,1]
    invJT = np.linalg.inv(J.T)  # (3, 3)

    # Gradients of shape functions w.r.t. physical coords
    # dN1 = invJT @ [1,0,0], dN2 = invJT @ [0,1,0], dN3 = invJT @ [0,0,1]
    dN = np.zeros((4, 3), dtype=np.float64)
    dN[1] = invJT[:, 0]
    dN[2] = invJT[:, 1]
    dN[3] = invJT[:, 2]
    dN[0] = -(dN[1] + dN[2] + dN[3])

    # Assemble B matrix (6 x 12)
    # Voigt: [eps_xx, eps_yy, eps_zz, gam_yz, gam_xz, gam_xy]
    B = np.zeros((6, 12), dtype=np.float64)
    for i in range(4):
        c = 3 * i
        dNi_x, dNi_y, dNi_z = dN[i]
        B[0, c]     = dNi_x
        B[1, c + 1] = dNi_y
        B[2, c + 2] = dNi_z
        B[3, c + 1] = dNi_z
        B[3, c + 2] = dNi_y
        B[4, c]     = dNi_z
        B[4, c + 2] = dNi_x
        B[5, c]     = dNi_y
        B[5, c + 1] = dNi_x

    return B, V


# ---------------------------------------------------------------------------
# Tet10 element routines (quadratic tetrahedral, 4-point Gauss)
# ---------------------------------------------------------------------------

# 4-point Gauss quadrature for tetrahedra (Keast 1986)
_TET10_ALPHA = 0.5854101966249685  # (5 + 3*sqrt(5)) / 20
_TET10_BETA = 0.1381966011250105   # (5 - sqrt(5)) / 20
_TET10_GAUSS = [
    # (xi, eta, zeta, weight)   — reference tet volume = 1/6
    (_TET10_BETA, _TET10_BETA, _TET10_BETA, 1.0 / 24.0),
    (_TET10_ALPHA, _TET10_BETA, _TET10_BETA, 1.0 / 24.0),
    (_TET10_BETA, _TET10_ALPHA, _TET10_BETA, 1.0 / 24.0),
    (_TET10_BETA, _TET10_BETA, _TET10_ALPHA, 1.0 / 24.0),
]


def _tet10_shape_grad(xi: float, eta: float, zeta: float) -> np.ndarray:
    """Shape function gradients dN/d(xi,eta,zeta) for tet10 at a point.

    Returns (10, 3) array of gradients in natural coordinates.

    Node numbering (meshio convention):
      0-3: corner nodes
      4: midside 0-1, 5: midside 1-2, 6: midside 0-2,
      7: midside 0-3, 8: midside 1-3, 9: midside 2-3
    """
    lam = 1.0 - xi - eta - zeta
    dN = np.zeros((10, 3), dtype=np.float64)

    # d/d(xi), d/d(eta), d/d(zeta)
    # N0 = lam*(2*lam - 1);  d(lam)/d(xi) = -1, etc.
    dN[0] = [-(4*lam - 1), -(4*lam - 1), -(4*lam - 1)]
    dN[1] = [4*xi - 1, 0, 0]
    dN[2] = [0, 4*eta - 1, 0]
    dN[3] = [0, 0, 4*zeta - 1]
    # N4 = 4*lam*xi
    dN[4] = [4*(lam - xi), -4*xi, -4*xi]
    # N5 = 4*xi*eta
    dN[5] = [4*eta, 4*xi, 0]
    # N6 = 4*lam*eta
    dN[6] = [-4*eta, 4*(lam - eta), -4*eta]
    # N7 = 4*lam*zeta
    dN[7] = [-4*zeta, -4*zeta, 4*(lam - zeta)]
    # N8 = 4*xi*zeta
    dN[8] = [4*zeta, 0, 4*xi]
    # N9 = 4*eta*zeta
    dN[9] = [0, 4*zeta, 4*eta]
    return dN


def _tet10_B_matrix(dN_phys: np.ndarray) -> np.ndarray:
    """Strain-displacement matrix B (6x30) from physical shape gradients.

    Parameters
    ----------
    dN_phys : (10, 3) — shape function gradients in physical coords.
    """
    B = np.zeros((6, 30), dtype=np.float64)
    for i in range(10):
        c = 3 * i
        dx, dy, dz = dN_phys[i]
        B[0, c]     = dx
        B[1, c + 1] = dy
        B[2, c + 2] = dz
        B[3, c + 1] = dz
        B[3, c + 2] = dy
        B[4, c]     = dz
        B[4, c + 2] = dx
        B[5, c]     = dy
        B[5, c + 1] = dx
    return B


def _tet10_ke_and_V(coords: np.ndarray, D: np.ndarray) -> Tuple[np.ndarray, float]:
    """Element stiffness (30x30) and volume for a tet10 element.

    Uses 4-point Gauss quadrature for exact integration of quadratic
    shape functions.

    Parameters
    ----------
    coords : (10, 3) — nodal coordinates.
    D : (6, 6) — material stiffness matrix.

    Returns
    -------
    ke : (30, 30) element stiffness matrix
    V : float positive volume
    """
    ke = np.zeros((30, 30), dtype=np.float64)
    V_total = 0.0

    for xi, eta, zeta, w in _TET10_GAUSS:
        dN_nat = _tet10_shape_grad(xi, eta, zeta)  # (10, 3)

        # Jacobian: J = dN_nat^T @ coords → (3, 3)
        J = dN_nat.T @ coords  # (3, 3)
        detJ = np.linalg.det(J)
        if abs(detJ) < 1e-30:
            continue

        # Physical shape function gradients: dN_phys = dN_nat @ inv(J)
        invJ = np.linalg.inv(J)
        dN_phys = dN_nat @ invJ  # (10, 3)

        B = _tet10_B_matrix(dN_phys)  # (6, 30)

        # Accumulate: ke += B^T D B * detJ * w
        ke += (B.T @ D @ B) * abs(detJ) * w
        V_total += abs(detJ) * w

    return ke, V_total


def _triangle_area_and_normal(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray):
    """Area and outward unit normal of a triangle."""
    e1 = p1 - p0
    e2 = p2 - p0
    cross = np.cross(e1, e2)
    area = 0.5 * np.linalg.norm(cross)
    if area < 1e-30:
        return area, np.zeros(3)
    normal = cross / (2.0 * area)
    return area, normal


# ---------------------------------------------------------------------------
# FEA Solver
# ---------------------------------------------------------------------------

class FEASolver:
    """Linear-elastic FEA solver for tet4 meshes.

    Usage::

        mat = MaterialProperty("Al7075", E=71.7e9, nu=0.33, density=2810)
        solver = FEASolver(mesh, mat)
        solver.fix_nodes(bottom_nodes)
        # Prefer _apply_pressure_lumped(node_ids, pa) over apply_pressure
        # when passing a bag of surface-node IDs — apply_pressure auto-
        # detects "list length divisible by 3" as consecutive triangle
        # triplets, which misinterprets an unsorted ID set.
        solver._apply_pressure_lumped(inner_surface_nodes, 1e6)
        result = solver.solve()
    """

    def __init__(self, mesh: meshio.Mesh, material: MaterialProperty) -> None:
        self.points = np.asarray(mesh.points, dtype=np.float64)
        self.n_nodes = len(self.points)
        self.n_dof = 3 * self.n_nodes
        self.material = material

        # Auto-detect element type: prefer tet10 over tet4
        self.element_type = "tetra"  # "tetra" or "tetra10"
        self.elements: np.ndarray | None = None
        self._nodes_per_element = 4

        for cell_block in mesh.cells:
            if cell_block.type == "tetra10":
                self.elements = np.asarray(cell_block.data, dtype=np.int64)
                self.element_type = "tetra10"
                self._nodes_per_element = 10
                break
        if self.elements is None:
            for cell_block in mesh.cells:
                if cell_block.type == "tetra":
                    self.elements = np.asarray(cell_block.data, dtype=np.int64)
                    break

        if self.elements is None:
            raise ValueError("Mesh contains no tetrahedral (tetra or tetra10) cells.")

        self.n_elements = len(self.elements)

        # Force vector and BC bookkeeping
        self._F = np.zeros(self.n_dof, dtype=np.float64)
        self._fixed_dofs: set[int] = set()

        # Pre-compute element matrices
        self._Bs: list[np.ndarray] = []  # B matrices (tet4 only)
        self._Vs: list[float] = []       # element volumes
        self._kes: list[np.ndarray | None] = []  # element stiffness (tet10 only)

        D = _isotropic_D(material.E, material.nu)
        for el_nodes in self.elements:
            if self.element_type == "tetra10":
                ke, V = _tet10_ke_and_V(self.points[el_nodes], D)
                self._Bs.append(np.empty(0))  # placeholder
                self._kes.append(ke)
                self._Vs.append(V)
            else:
                B, V = _tet4_B_and_V(self.points[el_nodes])
                self._Bs.append(B)
                self._kes.append(None)
                self._Vs.append(V)

    # ----- Boundary conditions -----

    def fix_nodes(self, node_ids: list[int]) -> None:
        """Apply fixed (zero-displacement) Dirichlet BCs at given nodes."""
        for nid in node_ids:
            for d in range(3):
                self._fixed_dofs.add(3 * nid + d)

    # ----- Loads -----

    def apply_pressure(self, surface_nodes: list[int], pressure_pa: float) -> None:
        """Apply uniform pressure to faces whose nodes belong to ``surface_nodes``.

        Delegates to :meth:`_apply_pressure_lumped`, which discovers exterior
        triangular faces from the tet connectivity where ALL three face-nodes
        are in the given set, then applies pressure with correct face normals.

        Previously this method auto-detected "len(nodes) divisible by 3"
        as "caller passed consecutive triangle triplets" and split the
        list into 3-tuples — which silently mis-applied pressure when
        the caller actually passed an unordered bag of surface-node IDs
        (the common case). That footgun caused a 10× stress overread in
        bridge.py. Removed: always use the lumped-face discovery path.

        If you genuinely have explicit triangle connectivity, call
        :meth:`apply_pressure_faces` (not yet implemented) or build the
        force vector manually.
        """
        self._apply_pressure_lumped(list(surface_nodes), pressure_pa)

    def _apply_pressure_lumped(self, node_ids: list[int], pressure_pa: float) -> None:
        """Simplified lumped pressure: find all exterior triangular faces
        that consist entirely of the given node set, then apply pressure
        to those faces with correct normals and areas.
        """
        node_set = set(node_ids)
        # Build exterior faces from tet connectivity (each tet has 4 faces)
        face_count: dict[tuple[int, ...], list[int]] = {}
        face_defs = [(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)]
        for eidx, el_nodes in enumerate(self.elements):
            for fd in face_defs:
                face = tuple(sorted(el_nodes[list(fd)]))
                face_count.setdefault(face, []).append(eidx)

        pts = self.points
        for face, elems in face_count.items():
            # Exterior faces belong to exactly one element
            if len(elems) != 1:
                continue
            # All face nodes must be in the requested set
            if not all(n in node_set for n in face):
                continue
            n0, n1, n2 = face
            area, normal = _triangle_area_and_normal(pts[n0], pts[n1], pts[n2])

            # Orient normal inward (toward element centroid)
            el_nodes = self.elements[elems[0]]
            centroid = pts[el_nodes].mean(axis=0)
            face_center = pts[list(face)].mean(axis=0)
            if np.dot(normal, centroid - face_center) < 0:
                normal = -normal

            # Pressure inward → force along inward normal
            force_per_node = pressure_pa * area * normal / 3.0
            for nid in face:
                self._F[3 * nid: 3 * nid + 3] += force_per_node

    def apply_gravity(
        self,
        accel_ms2: float = 9.81,
        direction: tuple = (0.0, 0.0, -1.0),
    ) -> None:
        """Apply gravitational body force to all elements."""
        d = np.asarray(direction, dtype=np.float64)
        d = d / np.linalg.norm(d)
        rho = self.material.density
        npe = self._nodes_per_element

        for el_idx, el_nodes in enumerate(self.elements):
            V = self._Vs[el_idx]
            # Lumped: total force = rho * V * g * dir, split equally to all nodes
            f_node = rho * V * accel_ms2 * d / npe
            for nid in el_nodes:
                self._F[3 * nid: 3 * nid + 3] += f_node

    # ----- Assembly & solve -----

    def _assemble_mass(self) -> sp.csc_matrix:
        """Assemble the lumped mass matrix M.

        For tet4: consistent mass (rho*V/20)*[[2I,I,I,I],...]
        For tet10: diagonal lumped mass (rho*V/npe per node) for stability.
        """
        rho = self.material.density
        npe = self._nodes_per_element
        ndof_el = 3 * npe

        n_entries = self.n_elements * ndof_el * ndof_el
        rows = np.empty(n_entries, dtype=np.int64)
        cols = np.empty(n_entries, dtype=np.int64)
        vals = np.empty(n_entries, dtype=np.float64)

        idx = 0
        for el_idx, el_nodes in enumerate(self.elements):
            V = self._Vs[el_idx]

            if self.element_type == "tetra10":
                # Diagonal lumped mass for tet10
                me = np.zeros((ndof_el, ndof_el), dtype=np.float64)
                mass_per_node = rho * V / npe
                for i in range(npe):
                    for d in range(3):
                        me[3 * i + d, 3 * i + d] = mass_per_node
            else:
                coeff = rho * V / 20.0
                me = np.zeros((ndof_el, ndof_el), dtype=np.float64)
                for i in range(4):
                    for j in range(4):
                        scale = 2.0 if i == j else 1.0
                        for d in range(3):
                            me[3 * i + d, 3 * j + d] = coeff * scale

            dofs = np.empty(ndof_el, dtype=np.int64)
            for i, nid in enumerate(el_nodes):
                dofs[3 * i: 3 * i + 3] = [3 * nid, 3 * nid + 1, 3 * nid + 2]

            for i in range(ndof_el):
                for j in range(ndof_el):
                    rows[idx] = dofs[i]
                    cols[idx] = dofs[j]
                    vals[idx] = me[i, j]
                    idx += 1

        M_coo = sp.coo_matrix((vals, (rows, cols)), shape=(self.n_dof, self.n_dof))
        return M_coo.tocsc()

    def _assemble_stiffness(self) -> sp.csc_matrix:
        """Assemble the global stiffness matrix K using COO format.

        Handles both tet4 (12x12 per element) and tet10 (30x30 per element).
        """
        npe = self._nodes_per_element
        ndof_el = 3 * npe  # 12 for tet4, 30 for tet10
        D = _isotropic_D(self.material.E, self.material.nu)

        n_entries = self.n_elements * ndof_el * ndof_el
        rows = np.empty(n_entries, dtype=np.int64)
        cols = np.empty(n_entries, dtype=np.int64)
        vals = np.empty(n_entries, dtype=np.float64)

        idx = 0
        for el_idx, el_nodes in enumerate(self.elements):
            if self.element_type == "tetra10":
                ke = self._kes[el_idx]
            else:
                B = self._Bs[el_idx]
                V = self._Vs[el_idx]
                ke = (B.T @ D @ B) * V

            # DOF indices for this element
            dofs = np.empty(ndof_el, dtype=np.int64)
            for i, nid in enumerate(el_nodes):
                dofs[3 * i: 3 * i + 3] = [3 * nid, 3 * nid + 1, 3 * nid + 2]

            # Scatter into COO
            for i in range(ndof_el):
                for j in range(ndof_el):
                    rows[idx] = dofs[i]
                    cols[idx] = dofs[j]
                    vals[idx] = ke[i, j]
                    idx += 1

        K_coo = sp.coo_matrix((vals, (rows, cols)), shape=(self.n_dof, self.n_dof))
        return K_coo.tocsc()

    def _assemble_tangent_stiffness_from_qps(
        self,
        qps: list[dict],
        C_ep: np.ndarray,
    ) -> sp.csc_matrix:
        """Assemble K_t = Σ_qp B^T C^ep_qp B · weight using the consistent
        algorithmic tangent per quadrature point.

        This replaces the elastic-tangent assembly in ``_assemble_stiffness``
        inside the Newton-Raphson loop.  When all QPs are in the elastic
        regime (Δγ=0), C^ep = C_e so the result equals ``_assemble_stiffness``.

        References
        ----------
        Simo & Hughes (1998) *Computational Inelasticity* §3.5 (consistent
        algorithmic tangent achieves quadratic NR convergence vs. sub-quadratic
        with the elastic tangent).

        Args:
            qps:  list of QP dicts from ``_build_quadrature_points``.
            C_ep: (n_qp, 6, 6) consistent tangent per QP.
        """
        n_qp = len(qps)
        n_nodes = self.n_nodes

        # Pre-allocate COO storage.  Each QP contributes ndof_qp × ndof_qp entries.
        ndof_max = max(len(qp["dofs"]) for qp in qps)
        n_entries = n_qp * ndof_max * ndof_max
        rows = np.empty(n_entries, dtype=np.int64)
        cols = np.empty(n_entries, dtype=np.int64)
        vals = np.zeros(n_entries, dtype=np.float64)

        idx = 0
        for qi, qp in enumerate(qps):
            B = qp["B"]           # (6, n_dof_el)
            w = qp["weight"]      # scalar
            dofs = qp["dofs"]     # (n_dof_el,)
            n_dof_el = len(dofs)
            ke_qp = (B.T @ C_ep[qi] @ B) * w  # (n_dof_el, n_dof_el)
            end = idx + n_dof_el * n_dof_el
            r_idx = np.repeat(dofs, n_dof_el)
            c_idx = np.tile(dofs, n_dof_el)
            rows[idx:end] = r_idx
            cols[idx:end] = c_idx
            vals[idx:end] = ke_qp.ravel()
            idx = end

        K_coo = sp.coo_matrix((vals[:idx], (rows[:idx], cols[:idx])),
                              shape=(self.n_dof, self.n_dof))
        return K_coo.tocsc()

    def solve(self) -> FEAResult:
        """Assemble and solve the FE system, returning stresses.

        Uses direct solver (spsolve) for small systems (<50K DOFs)
        and preconditioned conjugate gradient (ICCG) for larger ones.
        """
        K = self._assemble_stiffness()
        F = self._F.copy()

        # Apply Dirichlet BCs via penalty method
        diag_vals = K.diagonal()
        penalty = max(abs(diag_vals.max()), abs(diag_vals.min()), 1.0) * 1e8

        for dof in self._fixed_dofs:
            K[dof, dof] += penalty
            F[dof] = 0.0

        # Choose solver based on problem size
        if self.n_dof > 50000:
            # ICCG: incomplete LU preconditioner + conjugate gradient
            # Better memory scaling for large meshes
            K_csc = K.tocsc()
            try:
                ilu = spla.spilu(K_csc, drop_tol=1e-4)
                M_precond = spla.LinearOperator(K_csc.shape, ilu.solve)
                u, info = spla.cg(K_csc, F, M=M_precond, tol=1e-10, maxiter=5000)
                if info != 0:
                    # Fall back to direct solver
                    u = spla.spsolve(K, F)
            except Exception:
                u = spla.spsolve(K, F)
        else:
            u = spla.spsolve(K, F)

        # Post-processing: stresses and von Mises
        D = _isotropic_D(self.material.E, self.material.nu)
        von_mises = np.empty(self.n_elements, dtype=np.float64)
        npe = self._nodes_per_element

        for el_idx in range(self.n_elements):
            el_nodes = self.elements[el_idx]

            # Element displacement vector
            ndof_el = 3 * npe
            ue = np.empty(ndof_el, dtype=np.float64)
            for i, nid in enumerate(el_nodes):
                ue[3 * i: 3 * i + 3] = u[3 * nid: 3 * nid + 3]

            if self.element_type == "tetra10":
                # Average von Mises over 4 Gauss points
                vm_sum = 0.0
                for xi, eta, zeta, w in _TET10_GAUSS:
                    dN_nat = _tet10_shape_grad(xi, eta, zeta)
                    J = dN_nat.T @ self.points[el_nodes]
                    detJ = np.linalg.det(J)
                    if abs(detJ) < 1e-30:
                        continue
                    invJ = np.linalg.inv(J)
                    dN_phys = dN_nat @ invJ
                    B = _tet10_B_matrix(dN_phys)
                    sigma = D @ (B @ ue)
                    sxx, syy, szz = sigma[0], sigma[1], sigma[2]
                    tyz, txz, txy = sigma[3], sigma[4], sigma[5]
                    vm = np.sqrt(
                        0.5 * ((sxx - syy)**2 + (syy - szz)**2 + (szz - sxx)**2)
                        + 3.0 * (txy**2 + txz**2 + tyz**2)
                    )
                    vm_sum += vm
                von_mises[el_idx] = vm_sum / 4.0
            else:
                B = self._Bs[el_idx]
                sigma = D @ (B @ ue)
                sxx, syy, szz = sigma[0], sigma[1], sigma[2]
                tyz, txz, txy = sigma[3], sigma[4], sigma[5]
                vm = np.sqrt(
                    0.5 * ((sxx - syy)**2 + (syy - szz)**2 + (szz - sxx)**2)
                    + 3.0 * (txy**2 + txz**2 + tyz**2)
                )
                von_mises[el_idx] = vm

        displacements = u.reshape(-1, 3)
        strain_energy = 0.5 * u @ self._F

        return FEAResult(
            displacements=displacements,
            von_mises_stress=von_mises,
            max_stress=float(von_mises.max()),
            min_stress=float(von_mises.min()),
            strain_energy=float(strain_energy),
        )

    def _build_quadrature_points(self) -> list[dict]:
        """Return a flat list of quadrature points over all elements.

        Each entry has:
            element_idx : int
            dofs        : (12,) or (30,) int array — global DOF indices
            B           : (6, 12) or (6, 30) strain-displacement matrix
            weight      : float — integration weight (w·|det J|), in m³
            n_nodes     : 4 (tet4) or 10 (tet10)

        Unifies the tet4 and tet10 paths so the nonlinear NR loop is
        element-order agnostic. For tet4 there is one QP per element
        (constant strain); for tet10 there are four (Keast 1986 4-pt rule).
        """
        qps: list[dict] = []
        for el_idx, el_nodes in enumerate(self.elements):
            coords = self.points[el_nodes]
            n_nodes = self._nodes_per_element
            dofs = np.empty(3 * n_nodes, dtype=np.int64)
            for i, nid in enumerate(el_nodes):
                dofs[3*i:3*i+3] = [3*nid, 3*nid+1, 3*nid+2]

            if self.element_type == "tetra10":
                for xi, eta, zeta, w in _TET10_GAUSS:
                    dN_nat = _tet10_shape_grad(xi, eta, zeta)
                    J = dN_nat.T @ coords
                    detJ = np.linalg.det(J)
                    if abs(detJ) < 1e-30:
                        continue
                    dN_phys = dN_nat @ np.linalg.inv(J)
                    B = _tet10_B_matrix(dN_phys)
                    qps.append({
                        "element_idx": el_idx,
                        "dofs": dofs,
                        "B": B,
                        "weight": abs(detJ) * w,
                        "n_nodes": 10,
                    })
            else:
                qps.append({
                    "element_idx": el_idx,
                    "dofs": dofs,
                    "B": self._Bs[el_idx],
                    "weight": self._Vs[el_idx],
                    "n_nodes": 4,
                })
        return qps

    def solve_nonlinear(
        self,
        yield_stress: float,
        hardening_modulus: float = 0.0,
        n_load_steps: int = 10,
        max_iter: int = 50,
        tol: float = 1e-6,
    ) -> NonlinearResult:
        """Incremental Newton-Raphson solver with von Mises plasticity.

        Implements radial return mapping for J2 (von Mises) plasticity
        with isotropic linear hardening. Load is applied in equal
        increments; at each increment, Newton-Raphson iterates until
        the residual force norm drops below tolerance. Stress and
        plastic strain are tracked per quadrature point (one for tet4,
        four for tet10 via Keast 1986 4-point Gauss), and the reported
        per-element result is the max von Mises / plastic strain across
        that element's quadrature points.

        Radial return is performed by
        :func:`aria.physics.solid_mechanics.plasticity.radial_return_j2`
        (Simo & Hughes 1998 Box 3.1) — the solver is the FE orchestrator
        only; the constitutive law lives in the shared physics module.

        Parameters
        ----------
        yield_stress : float
            Initial yield stress (Pa). E.g., Ti-6Al-4V: 880e6 Pa.
        hardening_modulus : float
            Linear isotropic hardening slope H = dσ_y/dp̄ (Pa). H=0 →
            perfect plasticity.
        n_load_steps : int
            Number of equal load increments.
        max_iter : int
            Max Newton-Raphson iterations per load step.
        tol : float
            Convergence tolerance on relative residual force norm.

        Returns
        -------
        NonlinearResult
            Displacements (n_nodes, 3), per-element von Mises stress
            (Pa, peak over the element's QPs), per-element equivalent
            plastic strain p̄ (peak over QPs), and convergence flags.

        Notes
        -----
        Supports both tet4 (one QP) and tet10 (four QPs via Keast 1986
        4-point Gauss). The tangent stiffness K_t uses the consistent
        algorithmic tangent C^ep (Simo & Hughes §3.5 eq. 3.45) at yielded
        QPs and the elastic tangent D_e at elastic QPs — gives quadratic NR
        convergence near the solution. Built via
        ``_assemble_tangent_stiffness_from_qps``.
        """
        if self.element_type not in ("tetra", "tetra10"):
            raise NotImplementedError(
                f"Nonlinear solve supports tet4 and tet10, got {self.element_type!r}"
            )

        E = self.material.E
        nu = self.material.nu

        n_dof = self.n_dof
        n_el = self.n_elements

        qps = self._build_quadrature_points()
        n_qp = len(qps)
        # Per-QP state
        sigma = np.zeros((n_qp, 6), dtype=np.float64)
        eps_p = np.zeros(n_qp, dtype=np.float64)
        # Consistent-tangent state: trial stress and plastic multiplier per QP,
        # used to build C^ep (Simo & Hughes 1998 §3.5 eq. 3.45) for K_t.
        sigma_trial = np.zeros((n_qp, 6), dtype=np.float64)
        delta_gamma = np.zeros(n_qp, dtype=np.float64)

        # Pre-compute elastic 6×6 modulus for QPs in elastic regime
        D_el = _isotropic_D(E, nu)
        # Per-QP tangent C^ep; initialise to elastic
        C_ep = np.tile(D_el, (n_qp, 1, 1))  # (n_qp, 6, 6)

        # Total applied force
        F_total = self._F.copy()
        dF = F_total / n_load_steps

        u = np.zeros(n_dof)
        converged = True

        for load_step in range(1, n_load_steps + 1):
            F_target = dF * load_step

            for nr_iter in range(max_iter):
                # Internal force: F_int = Σ_qp B^T σ · w·|detJ|
                F_int = np.zeros(n_dof)
                for qi, qp in enumerate(qps):
                    F_int[qp["dofs"]] += (qp["B"].T @ sigma[qi]) * qp["weight"]

                # Residual with BC zeroing
                R = F_target - F_int
                for dof in self._fixed_dofs:
                    R[dof] = 0.0

                r_norm = np.linalg.norm(R)
                f_norm = max(np.linalg.norm(F_target), 1e-30)
                if r_norm / f_norm < tol:
                    break

                # Consistent algorithmic tangent stiffness (Simo & Hughes §3.5).
                # At yielded QPs C^ep != C_e → quadratic NR convergence.
                K_t = self._assemble_tangent_stiffness_from_qps(qps, C_ep)
                for dof in self._fixed_dofs:
                    K_t[dof, dof] += max(abs(K_t.diagonal().max()), 1.0) * 1e8

                du = spla.spsolve(K_t, R)
                u += du

                # Per-QP radial return + update consistent tangent
                for qi, qp in enumerate(qps):
                    ue_inc = du[qp["dofs"]]
                    d_eps_voigt = qp["B"] @ ue_inc  # (6,) engineering shear

                    stress_n_tensor = _voigt_stress_to_tensor(sigma[qi])
                    d_eps_tensor = _voigt_strain_to_tensor(d_eps_voigt)
                    stress_new_tensor, p_new, dg, _ = radial_return_j2(
                        stress_n=stress_n_tensor,
                        strain_increment=d_eps_tensor,
                        plastic_strain_n=eps_p[qi],
                        youngs_modulus_pa=E,
                        poisson_ratio=nu,
                        yield_strength_pa=yield_stress,
                        hardening_modulus_pa=hardening_modulus,
                    )
                    sigma[qi] = _tensor_to_voigt_stress(stress_new_tensor)
                    eps_p[qi] = p_new
                    delta_gamma[qi] = dg

                    # Record trial stress for consistent tangent computation:
                    # σ_trial = σ_n + C_e : Δε (elastic predictor before return)
                    mu = E / (2.0 * (1.0 + nu))
                    K_bulk = E / (3.0 * (1.0 - 2.0 * nu))
                    d_eps_t = _voigt_strain_to_tensor(d_eps_voigt)
                    tr_deps = d_eps_t[0, 0] + d_eps_t[1, 1] + d_eps_t[2, 2]
                    s_elastic_inc = 2.0 * mu * d_eps_t + (K_bulk - 2.0 * mu / 3.0) * tr_deps * np.eye(3)
                    sigma_trial[qi] = _tensor_to_voigt_stress(stress_n_tensor + s_elastic_inc)

                    # Update C^ep: use consistent tangent when yielded, else elastic
                    if dg > 0.0:
                        C_ep[qi] = consistent_tangent_modulus(
                            stress_trial=_voigt_stress_to_tensor(sigma_trial[qi]),
                            delta_gamma=dg,
                            youngs_modulus_pa=E,
                            poisson_ratio=nu,
                            hardening_modulus_pa=hardening_modulus,
                        )
                    else:
                        C_ep[qi] = D_el
            else:
                converged = False

        # Per-QP von Mises, then reduce to per-element peak across its QPs.
        vm_per_qp = np.zeros(n_qp)
        for qi in range(n_qp):
            s = sigma[qi]
            sxx, syy, szz = s[0], s[1], s[2]
            tyz, txz, txy = s[3], s[4], s[5]
            vm_per_qp[qi] = np.sqrt(
                0.5 * ((sxx-syy)**2 + (syy-szz)**2 + (szz-sxx)**2)
                + 3.0 * (txy**2 + txz**2 + tyz**2)
            )

        vm_final = np.zeros(n_el)
        eps_p_final = np.zeros(n_el)
        for qi, qp in enumerate(qps):
            el = qp["element_idx"]
            if vm_per_qp[qi] > vm_final[el]:
                vm_final[el] = vm_per_qp[qi]
            if eps_p[qi] > eps_p_final[el]:
                eps_p_final[el] = eps_p[qi]

        return NonlinearResult(
            displacements=u.reshape(-1, 3),
            von_mises_stress=vm_final,
            plastic_strain=eps_p_final,
            max_stress=float(vm_final.max()),
            yield_reached=bool(np.any(eps_p_final > 0)),
            converged=converged,
            iterations=nr_iter + 1 if converged else max_iter,
            load_steps=n_load_steps,
        )

    def solve_modal(self, n_modes: int = 10) -> ModalResult:
        """Solve the generalised eigenvalue problem K phi = omega^2 M phi.

        Finds the *n_modes* lowest natural frequencies and corresponding
        mode shapes.  Uses :func:`scipy.sparse.linalg.eigsh` (Lanczos
        iteration for real symmetric matrices) in shift-invert mode for
        robust extraction of the smallest eigenvalues.

        Fixed DOFs are enforced by zeroing the corresponding rows/columns
        in both K and M and placing a large value on the diagonal of K so
        that those DOFs produce eigenvalues well above the physical range.

        Parameters
        ----------
        n_modes : int
            Number of lowest modes to compute (default 10).

        Returns
        -------
        ModalResult
            Natural frequencies (Hz, ascending) and mode-shape vectors.

        Raises
        ------
        ValueError
            If the mesh has fewer free DOFs than requested modes.

        Notes
        -----
        If any returned frequency matches equipment vibration sources
        (e.g. pumps ~0.5 Hz, fans ~1 Hz), a resonance risk exists and
        the structure should be stiffened or damped.
        """
        K = self._assemble_stiffness()
        M = self._assemble_mass()

        # Enforce Dirichlet BCs: zero rows/cols in K and M, put large
        # diagonal in K so constrained DOFs have huge eigenvalues.
        diag_k = K.diagonal()
        penalty = max(abs(diag_k.max()), abs(diag_k.min()), 1.0) * 1e8

        # Convert to lil for efficient row/col zeroing
        K_lil = K.tolil()
        M_lil = M.tolil()
        for dof in self._fixed_dofs:
            K_lil[dof, :] = 0.0
            K_lil[:, dof] = 0.0
            K_lil[dof, dof] = penalty
            M_lil[dof, :] = 0.0
            M_lil[:, dof] = 0.0
            M_lil[dof, dof] = 1.0  # unit mass so eigenvalue = penalty

        K_csc = K_lil.tocsc()
        M_csc = M_lil.tocsc()

        n_free = self.n_dof - len(self._fixed_dofs)
        if n_modes >= n_free:
            raise ValueError(
                f"Requested {n_modes} modes but only {n_free} free DOFs."
            )

        # Shift-invert mode (sigma=0) targets the smallest eigenvalues
        eigenvalues, eigenvectors = spla.eigsh(
            K_csc, k=n_modes, M=M_csc, sigma=0.0, which="LM",
        )

        # eigenvalues are omega^2; convert to Hz
        # Guard against small negative values from numerical noise
        omega_sq = np.real(eigenvalues)
        omega_sq = np.clip(omega_sq, 0.0, None)
        freqs_hz = np.sqrt(omega_sq) / (2.0 * np.pi)

        # Sort ascending
        order = np.argsort(freqs_hz)
        freqs_hz = freqs_hz[order]
        eigenvectors = eigenvectors[:, order]

        mode_shapes = [eigenvectors[:, i] for i in range(n_modes)]

        return ModalResult(
            frequencies_hz=freqs_hz.tolist(),
            mode_shapes=mode_shapes,
        )
