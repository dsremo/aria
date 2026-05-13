"""Turbulence closure constants (§4.6 of H1 scope, Pod H3).

Standard k-ε model coefficients from Launder & Spalding 1974
*Comput Methods Appl Mech Eng* 3 269, and the Smagorinsky LES
subgrid constant from Deardorff 1970 *J Fluid Mech* 41 453
(Smagorinsky 1963 *Mon Wea Rev* 91 99 original; Cs ≈ 0.17 for
isotropic turbulence, Cs ≈ 0.10 for channel flow).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KEpsilonConstants:
    """Launder & Spalding 1974 standard k-ε coefficients."""

    c_mu: float = 0.09  # Launder & Spalding 1974
    c_1_eps: float = 1.44  # Launder & Spalding 1974
    c_2_eps: float = 1.92  # Launder & Spalding 1974
    sigma_k: float = 1.0  # Launder & Spalding 1974
    sigma_eps: float = 1.3  # Launder & Spalding 1974


K_EPSILON_STANDARD: KEpsilonConstants = KEpsilonConstants()


@dataclass(frozen=True)
class SmagorinskyConstants:
    """Smagorinsky LES subgrid model.

    Attributes:
        c_s_isotropic: Cs ≈ 0.17 for isotropic turbulence
            (Lilly 1967 IBM Sci Compute Sympos on Environ Sci p 195).
        c_s_channel: Cs ≈ 0.10 for wall-bounded channel flow
            (Deardorff 1970 J Fluid Mech 41 453).
    """

    c_s_isotropic: float = 0.17
    c_s_channel: float = 0.10


def turbulent_viscosity_k_epsilon(
    density_kg_m3: float,
    k_m2_s2: float,
    epsilon_m2_s3: float,
    constants: KEpsilonConstants = K_EPSILON_STANDARD,
) -> float:
    """μ_t = ρ C_μ k² / ε                                      [Pa·s].

    Launder & Spalding 1974 eq. 17. Required by the momentum equation
    as the eddy-viscosity closure for the Reynolds stress tensor.
    """
    if density_kg_m3 <= 0.0:
        raise ValueError("density_kg_m3 must be positive")
    if k_m2_s2 < 0.0:
        raise ValueError("k_m2_s2 must be non-negative")
    if epsilon_m2_s3 <= 0.0:
        raise ValueError("epsilon_m2_s3 must be positive")
    return density_kg_m3 * constants.c_mu * k_m2_s2 * k_m2_s2 / epsilon_m2_s3
