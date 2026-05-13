"""Bondi-Hoyle spherical accretion onto a moving body.

Bondi & Hoyle 1944 *MNRAS* 104 273 and Bondi 1952 *MNRAS* 112 195
derived the steady-state accretion rate of a stationary body of
mass `M` in a gas of density `ρ_∞` and sound speed `c_s`:

    Ṁ_B = 4π λ G² M² ρ_∞ / c_s³                             [kg/s]

with `λ ≈ 1/4` for an adiabatic γ = 5/3 gas (Bondi 1952 Table 1).
For a body moving through the gas at velocity `v` relative to the
rest frame, the rate generalises to the Bondi-Hoyle form

    Ṁ_BH = 4π G² M² ρ_∞ / (v² + c_s²)^{3/2}                 [kg/s]

(Hoyle & Lyttleton 1939; Edgar 2004 *New Astron Rev* 48 843),
which reduces to the stationary Bondi rate when `v ≪ c_s` and to
the ballistic `Ṁ ∝ v⁻³` high-Mach limit when `v ≫ c_s`. For
ARIA-scale ships (M ~ 10⁶ kg) this is many orders of magnitude
below the ship's own mass flux, but it enters the thermal budget
via the accreted mass's kinetic energy.
"""

from __future__ import annotations

import math

# CODATA 2018 Newton constant.
G_GRAV_M3_KG_S2: float = 6.67430e-11


def bondi_accretion_rate_kg_s(
    ship_mass_kg: float,
    ambient_density_kg_m3: float,
    ambient_sound_speed_m_s: float,
    bondi_lambda: float = 0.25,
) -> float:
    """Stationary Bondi 1952 accretion rate.

    Ṁ = 4π λ G² M² ρ / c_s³                                 [kg/s]

    The default `λ = 1/4` is the γ = 5/3 value from Bondi 1952
    Table 1 (isentropic adiabatic gas).
    """
    if ship_mass_kg <= 0.0:
        raise ValueError("ship_mass_kg must be positive")
    if ambient_density_kg_m3 <= 0.0:
        raise ValueError("ambient_density_kg_m3 must be positive")
    if ambient_sound_speed_m_s <= 0.0:
        raise ValueError("ambient_sound_speed_m_s must be positive")
    if bondi_lambda <= 0.0:
        raise ValueError("bondi_lambda must be positive")
    return (
        4.0 * math.pi * bondi_lambda
        * G_GRAV_M3_KG_S2 * G_GRAV_M3_KG_S2
        * ship_mass_kg * ship_mass_kg
        * ambient_density_kg_m3
        / (ambient_sound_speed_m_s ** 3)
    )


def bondi_hoyle_rate_kg_s(
    ship_mass_kg: float,
    ambient_density_kg_m3: float,
    ambient_sound_speed_m_s: float,
    relative_velocity_m_s: float,
) -> float:
    """Bondi-Hoyle moving-body accretion rate.

    Ṁ = 4π G² M² ρ / (v² + c_s²)^{3/2}                      [kg/s]

    Reduces to the stationary Bondi rate (with λ = 1) when v → 0.
    In the large-Mach limit v ≫ c_s the rate scales as v⁻³ — drag
    and accretion both shut off because the ship sees a strongly
    beam-like flow and the gravitational focusing radius shrinks.
    """
    if ship_mass_kg <= 0.0:
        raise ValueError("ship_mass_kg must be positive")
    if ambient_density_kg_m3 <= 0.0:
        raise ValueError("ambient_density_kg_m3 must be positive")
    if ambient_sound_speed_m_s <= 0.0:
        raise ValueError("ambient_sound_speed_m_s must be positive")
    if relative_velocity_m_s < 0.0:
        raise ValueError("relative_velocity_m_s must be non-negative")
    v_eff_sq = (
        relative_velocity_m_s * relative_velocity_m_s
        + ambient_sound_speed_m_s * ambient_sound_speed_m_s
    )
    return (
        4.0 * math.pi
        * G_GRAV_M3_KG_S2 * G_GRAV_M3_KG_S2
        * ship_mass_kg * ship_mass_kg
        * ambient_density_kg_m3
        / (v_eff_sq ** 1.5)
    )
