"""Thermal strain evaluation (§4.1 of F5 scope).

For isotropic materials in the small-strain regime, the thermal strain
is (Boley & Weiner 1960 eq. 1.2.1, ISBN 978-0486695792):

    ε^θ_ij(x, t) = α (T(x,t) − T_ref) δ_ij                [-]

For orthotropic / anisotropic materials the scalar CTE becomes a
symmetric second-rank tensor:

    ε^θ_ij = α_ij (T − T_ref)                             [-]

Both forms are provided. The output strain tensor is in the material
principal axes; it is the caller's job to rotate into the global
frame if needed (Jones 1999 *Mechanics of Composite Materials*,
ISBN 978-1560327127, §2.4).
"""

from __future__ import annotations

import numpy as np


def linear_thermal_strain(
    cte_k_inv: float,
    temperature_k: float,
    reference_temperature_k: float = 293.15,
) -> float:
    """Scalar thermal strain `ε^θ = α (T − T_ref)` [dimensionless].

    Args:
        cte_k_inv: linear coefficient of thermal expansion (1/K).
            Positive for most materials; carbon-fiber composites may
            have small negative values in the fiber direction.
        temperature_k: current temperature (K).
        reference_temperature_k: stress-free reference temperature (K).
            Default 293.15 K (ASTM E228 reference).

    Returns:
        Scalar strain (dimensionless). Positive for T > T_ref.
    """
    return cte_k_inv * (temperature_k - reference_temperature_k)


def thermal_strain_tensor(
    cte_k_inv: float,
    temperature_k: float,
    reference_temperature_k: float = 293.15,
) -> np.ndarray:
    """Isotropic thermal strain tensor `ε^θ_ij = α ΔT δ_ij` (3×3).

    Returns a diagonal strain tensor since an isotropic material
    expands equally in all directions.
    """
    eps = linear_thermal_strain(cte_k_inv, temperature_k, reference_temperature_k)
    return eps * np.eye(3, dtype=float)


def thermal_strain_anisotropic(
    cte_tensor_k_inv: np.ndarray,
    temperature_k: float,
    reference_temperature_k: float = 293.15,
) -> np.ndarray:
    """Anisotropic thermal strain tensor for an orthotropic material.

    ε^θ_ij = α_ij (T − T_ref)                             [-]

    Args:
        cte_tensor_k_inv: (3, 3) symmetric CTE tensor in the material
            principal axes (1/K).
        temperature_k: current T (K).
        reference_temperature_k: stress-free T_ref (K).

    Returns:
        (3, 3) strain tensor.

    Raises:
        ValueError: if the CTE tensor is not symmetric to 1e-12.
    """
    alpha = np.asarray(cte_tensor_k_inv, dtype=float).reshape(3, 3)
    if not np.allclose(alpha, alpha.T, atol=1e-12):
        raise ValueError("CTE tensor must be symmetric")
    delta_t = temperature_k - reference_temperature_k
    return alpha * delta_t
