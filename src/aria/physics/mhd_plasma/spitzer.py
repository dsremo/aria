"""Spitzer plasma resistivity (§4.2 of D1 scope).

Spitzer & Härm 1953 *Phys Rev* 89 977 derived the parallel
resistivity of a fully ionised plasma with Coulomb collisions:

    η_Sp = (Z_eff · 5.2×10⁻⁵ · ln Λ) / T_e^(3/2)          [Ω·m]

with T_e in eV (Wesson 2011 *Tokamaks* 4th ed eq. 2.16.5, ISBN
978-0199592234). Typical values:

    T_e = 1 keV, Z_eff = 1, ln Λ = 17  → η_Sp ≈ 2.8 × 10⁻⁸ Ω·m
    T_e = 10 keV, Z_eff = 1.7, ln Λ = 18 → η_Sp ≈ 1.6 × 10⁻⁹ Ω·m

This is extremely low — a 10 keV plasma conducts better than
copper — which is why ideal MHD is a good starting approximation
for fusion reactors. The Coulomb logarithm `ln Λ ≈ 17` is
approximately constant across the T_e = 1-20 keV band (Wesson
2011 §2.16).
"""

from __future__ import annotations


def spitzer_resistivity(
    electron_temperature_ev: float,
    z_eff: float,
    coulomb_logarithm: float = 17.0,
) -> float:
    """Spitzer parallel resistivity `η_Sp` [Ω·m].

    η_Sp = (Z_eff · 5.2×10⁻⁵ · ln Λ) / T_e^(3/2)

    Args:
        electron_temperature_ev: T_e in eV (positive).
        z_eff: effective charge Σ n_i Z_i² / n_e (dimensionless,
            ≥ 1; pure hydrogen plasma has Z_eff = 1).
        coulomb_logarithm: ln Λ. Default 17 (Wesson 2011 §2.16).

    Returns:
        η_Sp in Ω·m.
    """
    if electron_temperature_ev <= 0.0:
        raise ValueError("electron_temperature_ev must be positive")
    if z_eff < 1.0:
        raise ValueError("z_eff must be >= 1 (fully ionised plasma)")
    if coulomb_logarithm <= 0.0:
        raise ValueError("coulomb_logarithm must be positive")
    return (z_eff * 5.2e-5 * coulomb_logarithm) / (electron_temperature_ev ** 1.5)
