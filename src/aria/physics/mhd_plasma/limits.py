"""Operational limits for tokamak plasmas (§4.4, §8 of D1 scope).

Three canonical limits that every tokamak reactor must stay below:

  1. **Kruskal-Shafranov** ideal-kink limit: the external kink mode
     grows unstable when the edge safety factor `q_a < 1`. Hence the
     engineering rule `q_a ≥ 2` to provide margin. Derived from the
     dispersion relation for a cylindrical screw pinch (Freidberg
     2014 *Ideal MHD* §6.6 eq. 6.180, ISBN 978-1107006256).

  2. **Greenwald density** limit: tokamaks disrupt at a density that
     scales linearly with plasma current and inversely with cross-
     section area:

         n_G = I_p / (π a²)    [units: 10²⁰ m⁻³, with I_p in MA, a in m]

     (Greenwald 2002 *Plasma Phys Control Fusion* 44 R27 eq. 2).

  3. **Troyon β limit**: the maximum beta before ballooning modes
     disrupt the plasma:

         β_max [%] = C_T · I_p / (a · B_T)

     with `C_T ≈ 2.8 %·T·m/MA` for conventional aspect ratio
     tokamaks (Troyon et al. 1984 *Plasma Phys Contr Fusion* 26 209).

These three limits together carve out the operating envelope for
any reactor-class fusion plasma. ARIA's baseline reactor must sit
inside all three.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def kruskal_shafranov_limit_ok(edge_safety_factor: float, margin: float = 2.0) -> bool:
    """Check the Kruskal-Shafranov edge-safety-factor limit.

    The ideal external kink is unstable when `q_a < 1`. Engineering
    practice requires `q_a ≥ margin` (default 2.0) to give growing-
    mode margin; ITER operates with `q_95 ≈ 3` (ITER Physics Basis
    1999 Table 1).

    Args:
        edge_safety_factor: q at the plasma edge (dimensionless).
        margin: required margin above the absolute onset q = 1.
            Default 2.0.

    Returns:
        True if `q_a >= margin`.
    """
    if edge_safety_factor < 0.0:
        raise ValueError("edge_safety_factor must be non-negative")
    if margin < 1.0:
        raise ValueError("margin must be at least 1.0 (Kruskal-Shafranov onset)")
    return edge_safety_factor >= margin


def greenwald_density_limit(
    plasma_current_ma: float, minor_radius_m: float
) -> float:
    """Greenwald density limit `n_G = I_p / (π a²)` [10²⁰ m⁻³].

    Args:
        plasma_current_ma: I_p in MA (positive).
        minor_radius_m: plasma minor radius a in m (positive).

    Returns:
        Greenwald density in units of 10²⁰ m⁻³. For ITER
        (I_p = 15 MA, a = 2 m) this gives `n_G ≈ 1.19 × 10²⁰ m⁻³`.
    """
    if plasma_current_ma <= 0.0:
        raise ValueError("plasma_current_ma must be positive")
    if minor_radius_m <= 0.0:
        raise ValueError("minor_radius_m must be positive")
    return plasma_current_ma / (math.pi * minor_radius_m * minor_radius_m)


def troyon_beta_limit(
    plasma_current_ma: float,
    minor_radius_m: float,
    toroidal_field_t: float,
    troyon_coefficient: float = 2.8,
) -> float:
    """Troyon beta limit `β_max [%] = C_T · I_p / (a · B_T)`.

    Args:
        plasma_current_ma: I_p (MA).
        minor_radius_m: a (m).
        toroidal_field_t: B_T (T).
        troyon_coefficient: C_T (%·T·m/MA). Default 2.8 — Troyon
            1984's empirical value for conventional aspect-ratio
            tokamaks; advanced scenarios push to ~4.

    Returns:
        β_max in **percent** (not dimensionless fraction).
    """
    if plasma_current_ma <= 0.0:
        raise ValueError("plasma_current_ma must be positive")
    if minor_radius_m <= 0.0:
        raise ValueError("minor_radius_m must be positive")
    if toroidal_field_t <= 0.0:
        raise ValueError("toroidal_field_t must be positive")
    if troyon_coefficient <= 0.0:
        raise ValueError("troyon_coefficient must be positive")
    return troyon_coefficient * plasma_current_ma / (minor_radius_m * toroidal_field_t)


# ──────────────────────────────────────────────────────────────────────
#  ITER reference baseline (ITER Physics Basis 1999 Table 1)
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ITERBaselineParameters:
    """ITER tokamak baseline design parameters.

    All values from ITER Physics Basis 1999 Nucl. Fusion 39 2137
    Chapter 1 Table 1.
    """

    major_radius_m: float = 6.2
    minor_radius_m: float = 2.0
    plasma_current_ma: float = 15.0
    toroidal_field_t: float = 5.3
    elongation: float = 1.7
    triangularity: float = 0.33
    fusion_power_mw: float = 500.0
    q_target: float = 10.0
    q_95_target: float = 3.0
    source: str = "ITER Physics Basis 1999 Nucl Fusion 39 2137 Table 1"


ITER_BASELINE: ITERBaselineParameters = ITERBaselineParameters()
