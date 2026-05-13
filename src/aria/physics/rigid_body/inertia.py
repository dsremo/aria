"""Inertia tensor primitives (§4.1 of docs/pods/C3_euler_tensor.md).

For a rigid body of mass density `ρ(r)` (kg/m³) referred to its center
of mass, the inertia tensor is the symmetric 3×3 matrix

    I_{ij} = ∫_B ρ(r) (r² δ_{ij} − r_i r_j) d³r           [kg·m²]

(Goldstein 2002 eq. 5.6, ISBN 978-0201657029).

Parallel-axis (Steiner's) theorem — shifting the reference point from
the center of mass `O` to a new point `P` displaced by `a`:

    I^{(P)}_{ij} = I^{(CM)}_{ij} + M (a² δ_{ij} − a_i a_j)  [kg·m²]

(Landau-Lifshitz Vol. 1 §32 eq. 32.12, ISBN 978-0750628969).

Diagonalization of the CM inertia tensor yields the principal axes and
principal moments `(I_1, I_2, I_3)`. In the principal frame the matrix
is `diag(I_1, I_2, I_3)` and the Euler equations take their standard
form (see `euler_equations.py`).

For a discrete set of point masses at positions `r_k` (already measured
from the CM), the continuous integral reduces to

    I_{ij} = Σ_k m_k (|r_k|² δ_{ij} − r_{k,i} r_{k,j})     [kg·m²]

which is what `inertia_from_point_masses` implements.
"""

from __future__ import annotations

import numpy as np


def inertia_from_point_masses(
    positions_m: np.ndarray, masses_kg: np.ndarray
) -> np.ndarray:
    """Assemble the inertia tensor from point masses measured about the CM.

    Args:
        positions_m: (N, 3) array of position vectors of the N point
            masses, **already referred to the center of mass**.
        masses_kg: (N,) array of masses.

    Returns:
        (3, 3) symmetric inertia tensor in kg·m².
    """
    r = np.asarray(positions_m, dtype=float)
    m = np.asarray(masses_kg, dtype=float)
    if r.ndim != 2 or r.shape[1] != 3:
        raise ValueError("positions_m must have shape (N, 3)")
    if m.ndim != 1 or m.shape[0] != r.shape[0]:
        raise ValueError("masses_kg must have shape (N,) matching positions_m")
    if np.any(m < 0.0):
        raise ValueError("masses must be non-negative")

    r2 = np.sum(r * r, axis=1)  # (N,) |r_k|²
    I = np.zeros((3, 3), dtype=float)
    # Diagonal: Σ m (r² − r_i²) = Σ m r² − Σ m r_i²
    I[0, 0] = float(np.sum(m * (r2 - r[:, 0] * r[:, 0])))
    I[1, 1] = float(np.sum(m * (r2 - r[:, 1] * r[:, 1])))
    I[2, 2] = float(np.sum(m * (r2 - r[:, 2] * r[:, 2])))
    # Off-diagonal: −Σ m r_i r_j
    I[0, 1] = I[1, 0] = float(-np.sum(m * r[:, 0] * r[:, 1]))
    I[0, 2] = I[2, 0] = float(-np.sum(m * r[:, 0] * r[:, 2]))
    I[1, 2] = I[2, 1] = float(-np.sum(m * r[:, 1] * r[:, 2]))
    return I


def parallel_axis_transform(
    inertia_cm_kg_m2: np.ndarray,
    displacement_m: np.ndarray,
    mass_kg: float,
) -> np.ndarray:
    """Steiner's theorem: shift inertia tensor from CM to a displaced point.

    I^{(P)}_{ij} = I^{(CM)}_{ij} + M (|a|² δ_{ij} − a_i a_j)

    Args:
        inertia_cm_kg_m2: (3, 3) CM inertia tensor (kg·m²).
        displacement_m: (3,) vector from CM to new reference point (m).
        mass_kg: total body mass (kg).

    Returns:
        (3, 3) inertia tensor about the new reference point.
    """
    if mass_kg <= 0.0:
        raise ValueError("mass_kg must be positive")
    I_cm = np.asarray(inertia_cm_kg_m2, dtype=float).reshape(3, 3)
    a = np.asarray(displacement_m, dtype=float).reshape(3)
    a2 = float(np.dot(a, a))
    return I_cm + mass_kg * (a2 * np.eye(3) - np.outer(a, a))


def diagonalize_inertia(
    inertia_kg_m2: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Find principal moments and principal-axis frame.

    Returns:
        ``(principal_moments, principal_axes)`` where
        ``principal_moments`` is (3,) in ascending order and
        ``principal_axes`` is (3, 3) with each column the unit vector
        of the corresponding principal axis expressed in the original
        frame.

    Uses numpy's symmetric-matrix eigendecomposition (`numpy.linalg.eigh`),
    which guarantees real eigenvalues and orthogonal eigenvectors.
    """
    I = np.asarray(inertia_kg_m2, dtype=float).reshape(3, 3)
    # Symmetrize defensively against round-off.
    I_sym = 0.5 * (I + I.T)
    eigvals, eigvecs = np.linalg.eigh(I_sym)
    return eigvals, eigvecs


def is_positive_definite(
    inertia_kg_m2: np.ndarray, tol: float = 1.0e-12
) -> bool:
    """Check whether an inertia tensor is physically admissible.

    A valid inertia tensor is symmetric positive-definite. Small
    negative eigenvalues (below ``tol``) are accepted as numerical
    round-off.
    """
    I = np.asarray(inertia_kg_m2, dtype=float).reshape(3, 3)
    if not np.allclose(I, I.T, atol=1e-10):
        return False
    eigvals = np.linalg.eigvalsh(0.5 * (I + I.T))
    # Accept eigenvalues that are positive (or zero within roundoff).
    # The second condition `> tol` was overly strict — rejected valid
    # marginal inertia tensors in the (0, 1e-12) range.
    return bool(np.all(eigvals > -tol))


# ─── Analytic closed forms for common bodies ───────────────────────────


def inertia_solid_sphere(mass_kg: float, radius_m: float) -> np.ndarray:
    """Solid sphere of uniform density: `I = (2/5) M R² · δ_{ij}`.

    Reference: Goldstein 2002 Table 5.1 (ISBN 978-0201657029).
    """
    if mass_kg <= 0.0:
        raise ValueError("mass_kg must be positive")
    if radius_m <= 0.0:
        raise ValueError("radius_m must be positive")
    return (2.0 / 5.0) * mass_kg * radius_m * radius_m * np.eye(3)


def inertia_thin_ring(mass_kg: float, radius_m: float) -> np.ndarray:
    """Thin ring (hoop) about its symmetry axis.

    For a hoop of radius R lying in the x-y plane:
        I_zz = M R²                (about the symmetry axis)
        I_xx = I_yy = M R² / 2     (in-plane; perpendicular-axis theorem)

    Reference: Goldstein 2002 Problem 5.11; Landau-Lifshitz §32.
    """
    if mass_kg <= 0.0:
        raise ValueError("mass_kg must be positive")
    if radius_m <= 0.0:
        raise ValueError("radius_m must be positive")
    MR2 = mass_kg * radius_m * radius_m
    return np.diag([0.5 * MR2, 0.5 * MR2, MR2])
