"""Through-thickness thermal gradient stress (§4.4 of F5 scope).

For a thin free plate with a temperature distribution `T(z)` that
varies only across the thickness (no in-plane gradient, no external
in-plane loads), the closed-form stress distribution is (Boley &
Weiner 1960 §10.4 eq. 10.4.5, ISBN 978-0486695792):

    σ_x(z) = σ_y(z) = −(E α / (1 − ν)) · (T(z) − T_avg)   [Pa]

where `T_avg = (1/h) ∫_{−h/2}^{+h/2} T(z) dz` is the thickness-
averaged temperature. The constant `−E α T_avg / (1−ν)` is the
**membrane** contribution (equilibrium with zero external force), and
the `+E α T(z) / (1−ν)` is the local "would-be" thermal expansion.

For a **linear** gradient `T(z) = T_avg + (ΔT / h) z`, the peak
surface stress is

    σ_max = (E α ΔT) / (2 (1 − ν))                        [Pa]

located at z = ±h/2 (the two faces) with opposite signs — one face
in compression, the other in tension, a pure bending moment across
the thickness. Here ΔT is the **full** outer-to-inner temperature
difference, not the half-difference.

Worked example: EUROFER97 10 mm plate with linear T from 293 K
(inner) to 373 K (outer), E = 217 GPa, α = 10.6e-6 /K, ν = 0.30:

    σ_max = 217e9 · 10.6e-6 · 80 / (2 · 0.70)
          ≈ 131.4 MPa (one face +, the other −)

This is the Boley-Weiner §10.4 closed form; the F5 verification test
reproduces this exact calculation.
"""

from __future__ import annotations

import numpy as np


def linear_gradient_peak_stress(
    youngs_modulus_pa: float,
    cte_k_inv: float,
    delta_t_outer_inner_k: float,
    poissons_ratio: float,
) -> float:
    """Peak surface stress in a free plate with a linear through-
    thickness temperature gradient.

    σ_max = ± (E α ΔT) / (2 (1 − ν))                       [Pa]

    Args:
        youngs_modulus_pa: Young's modulus (Pa).
        cte_k_inv: CTE (1/K).
        delta_t_outer_inner_k: full outer-face minus inner-face
            temperature difference (K). Positive means the outer
            face is hotter.
        poissons_ratio: ν (dimensionless), 0 ≤ ν < 0.5.

    Returns:
        Peak stress magnitude (Pa, always positive). The outer face
        is in compression, the inner face in tension (or vice versa
        for ΔT < 0); the caller is expected to apply the sign based
        on geometry.
    """
    if youngs_modulus_pa <= 0.0:
        raise ValueError("youngs_modulus_pa must be positive")
    if not (-1.0 < poissons_ratio < 0.5):
        raise ValueError("poissons_ratio must satisfy -1 < ν < 0.5")
    return abs(
        youngs_modulus_pa
        * cte_k_inv
        * delta_t_outer_inner_k
        / (2.0 * (1.0 - poissons_ratio))
    )


def linear_gradient_stress_profile(
    youngs_modulus_pa: float,
    cte_k_inv: float,
    inner_temperature_k: float,
    outer_temperature_k: float,
    poissons_ratio: float,
    n_samples: int = 11,
) -> tuple[np.ndarray, np.ndarray]:
    """Through-thickness stress profile `σ(z)` for a free plate with
    linear T(z).

    Returns:
        Tuple ``(z_normalised, sigma_pa)`` with ``z_normalised`` in
        ``[-0.5, +0.5]`` (fraction of thickness; z=-0.5 is the inner
        face, z=+0.5 the outer face) and ``sigma_pa`` the Boley-Weiner
        in-plane stress at each sample (Pa).

    The profile is linear in z and passes through zero at the mid-
    plane. Use this for plotting or for verification tests that check
    the full-field form rather than only the peak magnitude.
    """
    if n_samples < 2:
        raise ValueError("n_samples must be at least 2")
    if not (-1.0 < poissons_ratio < 0.5):
        raise ValueError("poissons_ratio must satisfy -1 < ν < 0.5")
    z = np.linspace(-0.5, 0.5, n_samples, dtype=float)
    t_avg = 0.5 * (inner_temperature_k + outer_temperature_k)
    delta_t = outer_temperature_k - inner_temperature_k
    # T(z) = T_avg + ΔT · z for z in [-0.5, +0.5]
    t_z = t_avg + delta_t * z
    sigma = -(
        youngs_modulus_pa * cte_k_inv / (1.0 - poissons_ratio)
    ) * (t_z - t_avg)
    return z, sigma
