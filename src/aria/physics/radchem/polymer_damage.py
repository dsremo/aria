"""Polymer radiation damage (§4.4, §4.5 of J2 scope).

Charlesby–Pinner sol-fraction after dose D (Charlesby & Pinner 1959
*Proc Roy Soc A* 249 367; Dole 1972 *Radiation Chemistry of
Macromolecules* vol 1 eq. 5.1):

    s + √s = p₀/q₀ + 10 / (q₀ · M_{w,0} · D_Mrad)            [–]

with `p₀ = G_s · 0.48e-4` the fraction of mainchain bonds broken per
Mrad per repeat unit and `q₀ = G_x · 0.96e-4` the crosslinks per
repeat unit per Mrad. The ratio `p₀/q₀ = G_s / (2 G_x)` determines
whether the polymer net-scissions (>1) or net-crosslinks (<1).

Clough 1988 *IEEE Trans Nucl Sci* NS-35 1302 gives empirical Weibull-
style decays for tensile strength σ and elongation at break ε_b:

    σ(D)/σ₀   = exp[ −(D / D_{1/2,σ})^β_σ ]                  [–]
    ε_b(D)/ε_0 = exp[ −(D / D_{1/2,ε})^β_ε ]

with β ≈ 1 for most polymers; we store β in the material table.
Elongation usually fails first (D_{1/2,ε} ≪ D_{1/2,σ}).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PolymerJ2:
    """Radiation-chemistry parameters for a polymer.

    Attributes:
        name: identifier.
        g_s_molec_per_100_ev: chain-scission G-value.
        g_x_molec_per_100_ev: crosslinking G-value.
        d_half_tensile_mgy: dose at which σ/σ₀ = 1/e (MGy).
        d_half_elongation_mgy: dose at which ε_b/ε₀ = 1/e (MGy).
        weibull_beta_tensile: β_σ (dimensionless).
        weibull_beta_elongation: β_ε (dimensionless).
        source: citation.
    """

    name: str
    g_s_molec_per_100_ev: float
    g_x_molec_per_100_ev: float
    d_half_tensile_mgy: float
    d_half_elongation_mgy: float
    weibull_beta_tensile: float
    weibull_beta_elongation: float
    source: str


# LDPE — crosslinking-dominant, long Weibull lifetime.
LDPE = PolymerJ2(
    name="LDPE",
    g_s_molec_per_100_ev=0.8,  # Dole 1972 Table 3.1
    g_x_molec_per_100_ev=1.0,  # Dole 1972 Table 3.1
    d_half_tensile_mgy=10.0,  # IEC 60544-2 reference
    d_half_elongation_mgy=3.0,  # IEC 60544-2 (elongation fails first)
    weibull_beta_tensile=1.0,  # Clough 1988 fit
    weibull_beta_elongation=1.0,  # Clough 1988 fit
    source="Dole 1972 Table 3.1; IEC 60544-2; Clough 1988 IEEE NS-35 1302",
)

# UHMWPE — balanced scission/crosslink; important for tether materials.
UHMWPE = PolymerJ2(
    name="UHMWPE",
    g_s_molec_per_100_ev=0.3,  # Dole 1972 Table 3.1
    g_x_molec_per_100_ev=0.3,  # Dole 1972 Table 3.1
    d_half_tensile_mgy=8.0,  # Clough 1988
    d_half_elongation_mgy=2.5,  # Clough 1988
    weibull_beta_tensile=1.0,  # Clough 1988
    weibull_beta_elongation=1.0,  # Clough 1988
    source="Dole 1972 Table 3.1; Clough 1988 IEEE NS-35 1302",
)

# Kevlar (PPTA) — scission-dominant, relatively rad-hard.
KEVLAR = PolymerJ2(
    name="Kevlar-49",
    g_s_molec_per_100_ev=0.6,  # Dole 1972 Table 5.1
    g_x_molec_per_100_ev=0.05,  # Dole 1972 Table 5.1 (Kevlar: < 0.1)
    d_half_tensile_mgy=2.0,  # Clough 1988 IEEE NS-35 1302 Fig 6
    d_half_elongation_mgy=0.7,  # Clough 1988 IEEE NS-35 1302 Fig 6
    weibull_beta_tensile=1.0,  # Clough 1988
    weibull_beta_elongation=1.0,  # Clough 1988
    source="Dole 1972 Table 5.1; Clough 1988 IEEE NS-35 1302 Fig 6",
)


POLYMER_J2_TABLE: dict[str, PolymerJ2] = {
    "LDPE": LDPE,
    "UHMWPE": UHMWPE,
    "Kevlar-49": KEVLAR,
}


def get_polymer_j2(name: str) -> PolymerJ2:
    """Look up a polymer by name."""
    try:
        return POLYMER_J2_TABLE[name]
    except KeyError as e:
        raise KeyError(
            f"Unknown polymer {name!r}. Known: {sorted(POLYMER_J2_TABLE.keys())}"
        ) from e


def charlesby_pinner_sol_fraction(
    dose_mrad: float,
    initial_mw_g_mol: float,
    polymer: PolymerJ2,
) -> float:
    """Solve `s + √s = p₀/q₀ + 10/(q₀ M₀ D)` for the sol fraction s.

    The equation is quadratic in √s: let u = √s, then
        u² + u − rhs = 0  →  u = (−1 + √(1 + 4 rhs)) / 2
    so s = u². Returns 0 when the RHS is non-positive (fully
    crosslinked / gel limit).

    Args:
        dose_mrad: accumulated γ-equivalent dose (Mrad, positive).
        initial_mw_g_mol: M_{w,0} (g/mol, positive).
        polymer: PolymerJ2 descriptor.

    Returns:
        Sol fraction s (dimensionless, in [0, 1]).
    """
    if dose_mrad <= 0.0:
        raise ValueError("dose_mrad must be positive")
    if initial_mw_g_mol <= 0.0:
        raise ValueError("initial_mw_g_mol must be positive")
    if polymer.g_x_molec_per_100_ev <= 0.0:
        raise ValueError("polymer has zero G_x — Charlesby-Pinner undefined")
    p0 = polymer.g_s_molec_per_100_ev * 0.48e-4
    q0 = polymer.g_x_molec_per_100_ev * 0.96e-4
    rhs = p0 / q0 + 10.0 / (q0 * initial_mw_g_mol * dose_mrad)
    if rhs <= 0.0:
        return 0.0
    u = (-1.0 + math.sqrt(1.0 + 4.0 * rhs)) / 2.0
    return min(u * u, 1.0)


def _weibull_retention(
    dose_mgy: float, d_half_mgy: float, beta: float
) -> float:
    """Clough 1988 Weibull mechanical-property retention."""
    if dose_mgy < 0.0:
        raise ValueError("dose_mgy must be non-negative")
    if d_half_mgy <= 0.0:
        raise ValueError("d_half_mgy must be positive")
    if beta <= 0.0:
        raise ValueError("beta must be positive")
    return math.exp(-((dose_mgy / d_half_mgy) ** beta))


def clough_weibull_tensile_retention(
    dose_mgy: float, polymer: PolymerJ2
) -> float:
    """σ(D)/σ₀ = exp[−(D/D_{1/2,σ})^β_σ]                       [–]."""
    return _weibull_retention(
        dose_mgy, polymer.d_half_tensile_mgy, polymer.weibull_beta_tensile
    )


def clough_weibull_elongation_retention(
    dose_mgy: float, polymer: PolymerJ2
) -> float:
    """ε_b(D)/ε₀ = exp[−(D/D_{1/2,ε})^β_ε]                     [–]."""
    return _weibull_retention(
        dose_mgy, polymer.d_half_elongation_mgy, polymer.weibull_beta_elongation
    )
