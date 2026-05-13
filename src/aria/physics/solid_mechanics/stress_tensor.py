"""Stress tensor operations — deviatoric decomposition, invariants,
von Mises equivalent, principal stresses (§4.5 of F1 scope).

A symmetric Cauchy stress tensor σ_ij decomposes into a hydrostatic
part and a deviatoric part:

    p      = (1/3) σ_kk                                  hydrostatic (Pa)
    s_ij   = σ_ij − p δ_ij                               deviatoric (Pa)

The three principal invariants are:

    I_1 = σ_kk
    I_2 = (1/2)(σ_kk σ_ll − σ_ij σ_ij)
    I_3 = det(σ_ij)

The J₂ second deviatoric invariant is

    J_2 = (1/2) s_ij s_ij                                [Pa²]

and the von Mises equivalent stress (Hill 1950 eq. 2.32, ISBN
978-0198503675) is

    σ̄_VM = √(3 J_2)
        = √( (1/2) [(σ_11−σ_22)² + (σ_22−σ_33)² + (σ_33−σ_11)²
                    + 6 (σ_12² + σ_23² + σ_31²)] )       [Pa]

Principal stresses are the eigenvalues of the symmetric matrix;
since σ is symmetric they are real and the eigenvectors are
orthogonal (numpy's `eigvalsh` / `eigh`).
"""

from __future__ import annotations

import math

import numpy as np


def _as_3x3(sigma: np.ndarray) -> np.ndarray:
    s = np.asarray(sigma, dtype=float).reshape(3, 3)
    # Symmetrize defensively against floating-point noise.
    return 0.5 * (s + s.T)


def stress_invariants(sigma: np.ndarray) -> tuple[float, float, float]:
    """Return ``(I_1, I_2, I_3)`` in (Pa, Pa², Pa³)."""
    s = _as_3x3(sigma)
    I1 = float(np.trace(s))
    I2 = 0.5 * (I1 * I1 - float(np.sum(s * s)))
    I3 = float(np.linalg.det(s))
    return I1, I2, I3


def deviatoric_stress(sigma: np.ndarray) -> np.ndarray:
    """Deviatoric part `s_ij = σ_ij − p δ_ij` [Pa]."""
    s = _as_3x3(sigma)
    p = float(np.trace(s)) / 3.0
    return s - p * np.eye(3)


def j2_invariant(sigma: np.ndarray) -> float:
    """J₂ deviatoric invariant `= (1/2) s_ij s_ij` [Pa²]."""
    s_dev = deviatoric_stress(sigma)
    return 0.5 * float(np.sum(s_dev * s_dev))


def von_mises_equivalent_stress(sigma: np.ndarray) -> float:
    """Von Mises equivalent stress `σ̄_VM = √(3 J_2)` [Pa].

    The explicit scalar form from Hill 1950 eq. 2.32 is equivalent
    (and more convenient for unit tests):

        σ̄² = (1/2) [ (σ_xx−σ_yy)² + (σ_yy−σ_zz)² + (σ_zz−σ_xx)²
                     + 6 (σ_xy² + σ_yz² + σ_zx²) ]
    """
    return math.sqrt(3.0 * j2_invariant(sigma))


def principal_stresses(sigma: np.ndarray) -> tuple[float, float, float]:
    """Return the three principal stresses in descending order [Pa].

    Uses ``numpy.linalg.eigvalsh`` (symmetric-matrix solver) which
    guarantees real eigenvalues.
    """
    s = _as_3x3(sigma)
    eigs = np.linalg.eigvalsh(s)  # ascending
    # Reverse to descending: σ_1 ≥ σ_2 ≥ σ_3
    eigs_desc = eigs[::-1]
    return float(eigs_desc[0]), float(eigs_desc[1]), float(eigs_desc[2])
