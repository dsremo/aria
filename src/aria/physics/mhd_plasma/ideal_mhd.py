"""Ideal MHD kinematic primitives — Alfvén speed, gyroradius, β
(§4.1 of D1 scope).

The Alfvén wave propagates along magnetic field lines at

    v_A = B / √(μ₀ ρ)                                     [m/s]

(Freidberg 2014 *Ideal MHD* §2.4 eq. 2.37, ISBN 978-1107006256).
This is the fundamental MHD characteristic speed and sets the
timescale on which kink, sausage, and tearing modes grow.

Ion gyroradius (Larmor radius):

    ρ_i = m_i v_⊥ / (|q_i| B)                             [m]

with v_⊥ the perpendicular ion velocity. For a thermal distribution
we use v_⊥ ≈ √(2 k_B T_i / m_i).

Plasma β — the ratio of thermal to magnetic pressure:

    β = 2 μ₀ p / B² = 2 μ₀ (n k_B T) / B²                 [dimensionless]

(Freidberg 2014 §2.7 eq. 2.94). Engineering tokamaks run at
β ≈ 0.01-0.1; stellarators and spherical tokamaks push higher.
The Troyon limit (see `limits.py`) caps the β a toroidal plasma
can reach before kink instabilities disrupt it.
"""

from __future__ import annotations

import math

from .constants import PLASMA_CONSTANTS, PlasmaConstants


def alfven_speed(
    magnetic_field_t: float,
    mass_density_kg_m3: float,
    constants: PlasmaConstants = PLASMA_CONSTANTS,
) -> float:
    """Alfvén wave phase speed `v_A = B / √(μ₀ ρ)` [m/s].

    Args:
        magnetic_field_t: |B| in Tesla.
        mass_density_kg_m3: plasma ion mass density in kg/m³.
        constants: override for testing.

    Returns:
        Alfvén speed in m/s. Positive.
    """
    if magnetic_field_t < 0.0:
        raise ValueError("magnetic_field_t must be non-negative")
    if mass_density_kg_m3 <= 0.0:
        raise ValueError("mass_density_kg_m3 must be positive")
    return magnetic_field_t / math.sqrt(constants.mu_0_n_a2 * mass_density_kg_m3)


def ion_gyroradius(
    ion_mass_kg: float,
    perpendicular_velocity_m_s: float,
    charge_number: int,
    magnetic_field_t: float,
    constants: PlasmaConstants = PLASMA_CONSTANTS,
) -> float:
    """Ion Larmor radius `ρ_i = m v_⊥ / (|q| B)` [m].

    Args:
        ion_mass_kg: ion mass (kg).
        perpendicular_velocity_m_s: component of velocity perpendicular
            to B (m/s).
        charge_number: integer ion charge Z (elementary charges).
        magnetic_field_t: |B| in Tesla.
        constants: override for testing.

    Returns:
        Gyroradius in metres.
    """
    if ion_mass_kg <= 0.0:
        raise ValueError("ion_mass_kg must be positive")
    if perpendicular_velocity_m_s < 0.0:
        raise ValueError("perpendicular_velocity_m_s must be non-negative")
    if charge_number == 0:
        raise ValueError("charge_number must be nonzero (neutrals do not gyrate)")
    if magnetic_field_t <= 0.0:
        raise ValueError("magnetic_field_t must be positive")
    q = abs(charge_number) * constants.e_c
    return ion_mass_kg * perpendicular_velocity_m_s / (q * magnetic_field_t)


def plasma_beta(
    pressure_pa: float,
    magnetic_field_t: float,
    constants: PlasmaConstants = PLASMA_CONSTANTS,
) -> float:
    """Plasma beta `β = 2 μ₀ p / B²` [dimensionless].

    Args:
        pressure_pa: total plasma pressure (Pa). Includes ion +
            electron thermal contributions.
        magnetic_field_t: |B| at the flux surface (T). Positive.

    Returns:
        β (dimensionless, non-negative).
    """
    if pressure_pa < 0.0:
        raise ValueError("pressure_pa must be non-negative")
    if magnetic_field_t <= 0.0:
        raise ValueError("magnetic_field_t must be positive")
    return 2.0 * constants.mu_0_n_a2 * pressure_pa / (magnetic_field_t * magnetic_field_t)
