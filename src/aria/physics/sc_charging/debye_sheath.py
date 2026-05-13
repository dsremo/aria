"""Debye length and Child-Langmuir sheath (§4.3 of D2 scope).

The Debye length is the characteristic scale over which a plasma
screens an imposed electric field — below `λ_D` quasi-neutrality
breaks down and the sheath forms. A charged spacecraft surface sits
at the far wall of a Child-Langmuir sheath that is several Debye
lengths thick for strongly negative potentials.

References: Chen 2016 *Introduction to Plasma Physics* 3rd ed eq. 1.11
and eq. 8.24 (ISBN 978-3319223087).
"""

from __future__ import annotations

import math

from ..mhd_plasma.constants import PLASMA_CONSTANTS, PlasmaConstants


def debye_length(
    electron_density_m3: float,
    electron_temperature_ev: float,
    constants: PlasmaConstants = PLASMA_CONSTANTS,
) -> float:
    """Electron Debye length λ_D in meters.

    λ_D = (ε₀ k_B T_e / (n_e e²))^½
        = (ε₀ T_e[J] / (n_e e²))^½           [m]

    with T_e expressed in joules via T_e[J] = T_e[eV]·e.

    Canonical checks:
      GEO substorm T_e = 10 keV, n_e = 1 cm⁻³ → λ_D ≈ 743 m
          (Chen 2016 Table 1; Lai 2012 §4.1)
      LIC       T_e = 8000 K, n_e = 0.1 cm⁻³ → λ_D ≈ 19.6 m
          (Redfield & Linsky 2008 ApJ 673 283)

    Args:
        electron_density_m3: n_e (m⁻³, positive).
        electron_temperature_ev: T_e (eV, positive).
        constants: override for testing.

    Returns:
        λ_D in meters.
    """
    if electron_density_m3 <= 0.0:
        raise ValueError("electron_density_m3 must be positive")
    if electron_temperature_ev <= 0.0:
        raise ValueError("electron_temperature_ev must be positive")
    e = constants.e_c
    eps0 = constants.epsilon_0_f_m
    t_e_joules = electron_temperature_ev * e
    return math.sqrt(eps0 * t_e_joules / (electron_density_m3 * e * e))


def child_langmuir_sheath_thickness(
    debye_length_m: float,
    surface_potential_v: float,
    electron_temperature_ev: float,
) -> float:
    """Child-Langmuir sheath thickness for a strongly charged surface.

    s = λ_D · (e|φ_s| / k_B T_e)^{3/4}                   [m]

    which in the eV convention for T_e is simply
    s = λ_D · (|φ_s|[V] / T_e[eV])^{3/4}.

    Chen 2016 eq. 8.24. Valid for e|φ_s| ≫ k_B T_e (strongly negative
    wall, ion-matrix regime); returns λ_D for weak potentials because
    the Child-Langmuir law reduces to the Debye shielding limit there.

    Args:
        debye_length_m: λ_D in meters (positive).
        surface_potential_v: φ_s in volts (any sign; only magnitude
            matters).
        electron_temperature_ev: T_e in eV (positive).

    Returns:
        Sheath thickness s in meters.
    """
    if debye_length_m <= 0.0:
        raise ValueError("debye_length_m must be positive")
    if electron_temperature_ev <= 0.0:
        raise ValueError("electron_temperature_ev must be positive")
    phi_over_t = abs(surface_potential_v) / electron_temperature_ev
    if phi_over_t <= 1.0:
        return debye_length_m
    return debye_length_m * phi_over_t**0.75
