"""Chandrasekhar dynamical friction.

Chandrasekhar 1943 *ApJ* 97 255 derived the gravitational drag a
massive body experiences from the trailing wake of particles it
deflects while traversing a collisionless background (stars or
dark matter). For a body of mass `M` moving at velocity `v` through
a uniform background of density `ρ` with a Maxwellian velocity
distribution of dispersion `σ_v`, the drag acceleration is

    a_df = −4π ln Λ · G² M · ρ / v² · f(X)                  [m/s²]

where `X = v / (√2 σ_v)` and

    f(X) = erf(X) − (2 X / √π) exp(−X²)

(Binney & Tremaine 2008 *Galactic Dynamics* 2nd ed eq. 8.3, ISBN
978-0691130279). `ln Λ` is the Coulomb logarithm, typically in the
range 3–30 for galactic applications. The result is valid for
body velocities comparable to or below the background dispersion;
at `v ≫ σ_v` the drag decays as `v⁻²`.
"""

from __future__ import annotations

import math

from .bondi_accretion import G_GRAV_M3_KG_S2


def coulomb_log_default() -> float:
    """Handbook galactic Coulomb logarithm `ln Λ ≈ 10`.

    Binney & Tremaine 2008 §8.1 advise `ln Λ ∈ [3, 30]` for galactic
    problems; the central value 10 is the usual order-of-magnitude
    default.
    """
    return 10.0


def _chandrasekhar_f(x: float) -> float:
    """f(X) = erf(X) − (2 X / √π) exp(−X²)."""
    return math.erf(x) - (2.0 * x / math.sqrt(math.pi)) * math.exp(-x * x)


def chandrasekhar_dynamical_friction_acceleration(
    ship_mass_kg: float,
    velocity_m_s: float,
    background_density_kg_m3: float,
    velocity_dispersion_m_s: float,
    coulomb_log: float = 10.0,
) -> float:
    """Magnitude of the Chandrasekhar 1943 drag acceleration.

    |a_df| = 4π ln Λ · G² M · ρ / v² · f(X)                 [m/s²]

    where `X = v / (√2 σ_v)`. Returns 0 for `v = 0` because the
    formula is singular there (the body at rest experiences no
    wake-induced drag; it only feels the background's dispersion).

    Args:
        ship_mass_kg: M (kg, positive).
        velocity_m_s: |v| relative to background rest frame.
        background_density_kg_m3: ρ of the collisionless background.
        velocity_dispersion_m_s: σ_v Maxwellian dispersion.
        coulomb_log: ln Λ (dimensionless, positive; default 10).

    Returns:
        |a_df| in m/s² (non-negative).
    """
    if ship_mass_kg <= 0.0:
        raise ValueError("ship_mass_kg must be positive")
    if velocity_m_s < 0.0:
        raise ValueError("velocity_m_s must be non-negative")
    if background_density_kg_m3 < 0.0:
        raise ValueError("background_density_kg_m3 must be non-negative")
    if velocity_dispersion_m_s <= 0.0:
        raise ValueError("velocity_dispersion_m_s must be positive")
    if coulomb_log <= 0.0:
        raise ValueError("coulomb_log must be positive")
    if velocity_m_s == 0.0:
        return 0.0
    x = velocity_m_s / (math.sqrt(2.0) * velocity_dispersion_m_s)
    return (
        4.0 * math.pi * coulomb_log
        * G_GRAV_M3_KG_S2 * G_GRAV_M3_KG_S2
        * ship_mass_kg * background_density_kg_m3
        / (velocity_m_s * velocity_m_s)
    ) * _chandrasekhar_f(x)
