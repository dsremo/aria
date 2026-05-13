"""Exponential attenuation and mean-free-path primitives.

For a beam of particles passing through a homogeneous absorber of
thickness `x`, the Beer-Lambert exponential attenuation law is

    I(x) / I_0 = exp(−Σ_t · x)                           [dimensionless]

(Duderstadt & Hamilton 1976 *Nuclear Reactor Analysis* §2, ISBN
978-0471223634). Here the macroscopic total cross section is

    Σ_t = n σ = (ρ N_A / M) σ                            [1/cm]

with:
  n = nuclide number density (1/cm³)
  σ = microscopic cross section per nucleus (cm²; 1 barn = 1e-24 cm²)
  ρ = mass density (g/cm³)
  N_A = Avogadro (mol⁻¹) = 6.022 140 76e23 (CODATA 2018, exact since 2019)
  M = molar mass (g/mol)

Mean free path is `λ = 1/Σ_t` (cm).

These three primitives are the building blocks every transport code
assumes and are the closed-form checks that the test suite uses to
verify the more sophisticated solvers that will land in follow-up
commits.
"""

from __future__ import annotations

import math

# Avogadro number (CODATA 2018; exact since the 2019 SI redefinition).
AVOGADRO_MOL_INV: float = 6.02214076e23  # mol⁻¹ (exact)


def macroscopic_cross_section(
    density_g_cm3: float,
    molar_mass_g_mol: float,
    microscopic_xs_barn: float,
) -> float:
    """Macroscopic total cross section `Σ = n σ` [1/cm].

    Args:
        density_g_cm3: mass density of the absorber (g/cm³).
        molar_mass_g_mol: molar mass of the absorber nuclide (g/mol).
            For compounds, use the average atomic mass.
        microscopic_xs_barn: microscopic cross section per nucleus (barn).
            1 barn = 1e-24 cm².

    Returns:
        Σ in 1/cm.

    Example — Fe at 14 MeV, σ_t ≈ 2.5 barn:
        Σ = 7.87 · 6.022e23 / 55.85 · 2.5e-24 ≈ 0.212 1/cm
        → mean free path ≈ 4.7 cm
    """
    if density_g_cm3 <= 0.0:
        raise ValueError("density_g_cm3 must be positive")
    if molar_mass_g_mol <= 0.0:
        raise ValueError("molar_mass_g_mol must be positive")
    if microscopic_xs_barn < 0.0:
        raise ValueError("microscopic_xs_barn must be non-negative")
    n_per_cm3 = density_g_cm3 * AVOGADRO_MOL_INV / molar_mass_g_mol
    sigma_cm2 = microscopic_xs_barn * 1.0e-24
    return n_per_cm3 * sigma_cm2


def mean_free_path(
    density_g_cm3: float,
    molar_mass_g_mol: float,
    microscopic_xs_barn: float,
) -> float:
    """Mean free path `λ = 1/Σ` [cm]."""
    sigma = macroscopic_cross_section(
        density_g_cm3, molar_mass_g_mol, microscopic_xs_barn
    )
    if sigma == 0.0:
        return math.inf
    return 1.0 / sigma


def attenuation_exponential(
    macroscopic_xs_1_cm: float, thickness_cm: float
) -> float:
    """Beer-Lambert exponential attenuation `exp(−Σ x)` [dimensionless].

    Args:
        macroscopic_xs_1_cm: Σ_t in 1/cm.
        thickness_cm: slab thickness in cm.

    Returns:
        Transmitted fraction in [0, 1].
    """
    if macroscopic_xs_1_cm < 0.0:
        raise ValueError("macroscopic_xs_1_cm must be non-negative")
    if thickness_cm < 0.0:
        raise ValueError("thickness_cm must be non-negative")
    return math.exp(-macroscopic_xs_1_cm * thickness_cm)
