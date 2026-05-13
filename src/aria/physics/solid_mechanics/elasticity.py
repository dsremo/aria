"""Elastic-constant conversions (§4.3 of F1 scope).

Three independent elastic moduli describe any isotropic Hookean
material; the remaining ones follow from algebraic identities
(Timoshenko & Goodier 1970 *Theory of Elasticity* 3rd ed Ch. 1,
ISBN 978-0070858053):

    λ = E ν / ((1 + ν)(1 − 2ν))                           Lamé first
    μ = G = E / (2(1 + ν))                                shear modulus
    K = E / (3(1 − 2ν))                                   bulk modulus

These are the identities used by the stress-tensor and plasticity
modules in the rest of the package.
"""

from __future__ import annotations


def lame_constants(
    youngs_modulus_pa: float, poissons_ratio: float
) -> tuple[float, float]:
    """Return ``(λ, μ)`` in Pa from (E, ν).

    λ = E ν / ((1 + ν)(1 − 2ν))                           [Pa]
    μ = E / (2(1 + ν))                                    [Pa]
    """
    _check_youngs(youngs_modulus_pa)
    _check_poisson(poissons_ratio)
    denom = (1.0 + poissons_ratio) * (1.0 - 2.0 * poissons_ratio)
    lam = youngs_modulus_pa * poissons_ratio / denom
    mu = youngs_modulus_pa / (2.0 * (1.0 + poissons_ratio))
    return lam, mu


def shear_modulus(youngs_modulus_pa: float, poissons_ratio: float) -> float:
    """Shear modulus `G = μ = E / (2(1 + ν))` [Pa]."""
    _check_youngs(youngs_modulus_pa)
    _check_poisson(poissons_ratio)
    return youngs_modulus_pa / (2.0 * (1.0 + poissons_ratio))


def bulk_modulus(youngs_modulus_pa: float, poissons_ratio: float) -> float:
    """Bulk modulus `K = E / (3(1 − 2ν))` [Pa].

    Diverges as ν → 0.5 (incompressible limit), which is physically
    correct: an incompressible material cannot absorb volume change.
    """
    _check_youngs(youngs_modulus_pa)
    _check_poisson(poissons_ratio)
    return youngs_modulus_pa / (3.0 * (1.0 - 2.0 * poissons_ratio))


def _check_youngs(e: float) -> None:
    if e <= 0.0:
        raise ValueError("youngs_modulus_pa must be positive")


def _check_poisson(nu: float) -> None:
    if not (-1.0 < nu < 0.5):
        raise ValueError("poissons_ratio must lie in (-1, 0.5)")
