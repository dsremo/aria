"""Runaway electron physics — Dreicer field + Rosenbluth-Putvinski
avalanche (§4.8 of D1 scope).

During a tokamak disruption, the thermal quench flashes the plasma
temperature down below 100 eV in milliseconds. The plasma becomes
high-resistivity, the inductive loop voltage spikes, and a fraction
of electrons accelerate out of the thermal distribution into a
runaway beam. The final runaway current is set by two mechanisms:

  1. **Primary (Dreicer) generation**: electrons at the tail of the
     thermal distribution are continuously scattered into the
     runaway regime when the parallel electric field exceeds the
     Dreicer threshold
         E_D = n_e e³ ln Λ / (4π ε₀² m_e v_th²)
     (Dreicer 1960 *Phys Rev* 117 329). For reactor-relevant
     densities and T_e ≈ 10 keV, E_D ≈ 30 V/m.

  2. **Secondary (Rosenbluth-Putvinski avalanche)**: a pre-existing
     runaway electron can knock a thermal electron into the runaway
     regime via a close collision. Since *both* electrons are now
     runaways, they can each do it again — the population grows
     exponentially. The final amplification factor is
         N_final / N_seed ≈ exp((I_p / I_A) · 2.5)
     with `I_A ≈ 1 MA` (Rosenbluth & Putvinski 1997 *Nucl Fusion*
     37 1355 eq. 18). For ITER (`I_p = 15 MA`) the amplification
     is `exp(37.5) ≈ 1.8×10¹⁶`, meaning even a *single* seed
     electron becomes a multi-MA runaway beam.

This is why disruption mitigation — massive gas injection,
shattered pellet injection, killer pellets — is a first-order
reactor design problem: the avalanche amplification is so large
that seed suppression alone cannot work.
"""

from __future__ import annotations

import math

from .constants import PLASMA_CONSTANTS, PlasmaConstants

# Rosenbluth & Putvinski 1997 critical current scale (Nucl Fusion 37
# 1355 eq. 18). Empirically ~1 MA for all conventional tokamaks.
ROSENBLUTH_PUTVINSKI_I_A_MA: float = 1.0  # MA
ROSENBLUTH_PUTVINSKI_GAIN_EXPONENT: float = 2.5  # dimensionless


def dreicer_field(
    electron_density_m3: float,
    electron_temperature_ev: float,
    coulomb_logarithm: float = 17.0,
    constants: PlasmaConstants = PLASMA_CONSTANTS,
) -> float:
    """Dreicer critical electric field for runaway onset.

    E_D = n_e · e³ · ln Λ / (4π ε₀² · T_e)                 [V/m]

    with T_e in **joules**. This is the canonical Dreicer field
    given in Helander & Sigmar 2002 *Collisional Transport in
    Magnetized Plasmas* eq. 11.27 (ISBN 978-0521020985) and
    Wesson 2011 *Tokamaks* 4th ed §2.16. The physical picture is
    that `E_D` is the electric field at which the electron-ion
    Coulomb friction force on a thermal electron equals the
    applied electric force; above this field, a thermal electron
    can accelerate indefinitely (runaway).

    Reference: Dreicer 1960 *Phys Rev* 117 329; Wesson 2011
    *Tokamaks* §2.16 Table 2.16.1 gives ~44 V/m at n_e = 10²⁰ m⁻³,
    T_e = 1 keV.

    Args:
        electron_density_m3: n_e in particles per m³ (positive).
        electron_temperature_ev: T_e in eV (positive).
        coulomb_logarithm: ln Λ. Default 17 (Wesson 2011 §2.16).
        constants: override for testing.

    Returns:
        E_D in V/m.

    Canonical checks:
      n_e = 10²⁰ m⁻³, T_e =  1 keV, ln Λ = 17 → E_D ≈ 44 V/m
      n_e = 10²⁰ m⁻³, T_e = 10 keV, ln Λ = 17 → E_D ≈ 4.4 V/m
    """
    if electron_density_m3 <= 0.0:
        raise ValueError("electron_density_m3 must be positive")
    if electron_temperature_ev <= 0.0:
        raise ValueError("electron_temperature_ev must be positive")
    if coulomb_logarithm <= 0.0:
        raise ValueError("coulomb_logarithm must be positive")

    e = constants.e_c
    eps0 = constants.epsilon_0_f_m
    # T_e [J] = T_e [eV] · e
    t_e_joules = electron_temperature_ev * e
    return (
        electron_density_m3
        * e * e * e
        * coulomb_logarithm
        / (4.0 * math.pi * eps0 * eps0 * t_e_joules)
    )


def rosenbluth_putvinski_avalanche(
    plasma_current_ma: float,
    seed_electrons: float = 1.0,
    i_a_ma: float = ROSENBLUTH_PUTVINSKI_I_A_MA,
    gain_exponent: float = ROSENBLUTH_PUTVINSKI_GAIN_EXPONENT,
) -> float:
    """Rosenbluth-Putvinski avalanche amplification of a runaway seed.

    N_final / N_seed ≈ exp((I_p / I_A) · γ)               [dimensionless]

    with `γ ≈ 2.5` (Rosenbluth & Putvinski 1997 Nucl Fusion 37 1355
    eq. 18) and `I_A ≈ 1 MA` the critical avalanche current scale.

    Args:
        plasma_current_ma: pre-disruption plasma current I_p (MA).
        seed_electrons: number of seed runaway electrons (before the
            avalanche kicks in). Default 1 — one electron is enough
            for a big machine. The result is `seed × exp(I_p/I_A·γ)`.
        i_a_ma: critical current scale (MA). Default 1.0.
        gain_exponent: γ (dimensionless). Default 2.5.

    Returns:
        Final runaway electron count (dimensionless, ≥ seed_electrons).

    Canonical ITER check: I_p = 15 MA, seed = 1 →
        N = exp(15 · 2.5) = exp(37.5) ≈ 1.94 × 10¹⁶
    confirming that ITER's disruption runaway population is set
    entirely by the avalanche — the seed is effectively irrelevant.
    """
    if plasma_current_ma <= 0.0:
        raise ValueError("plasma_current_ma must be positive")
    if seed_electrons < 0.0:
        raise ValueError("seed_electrons must be non-negative")
    if i_a_ma <= 0.0:
        raise ValueError("i_a_ma must be positive")
    if gain_exponent <= 0.0:
        raise ValueError("gain_exponent must be positive")
    return seed_electrons * math.exp(plasma_current_ma / i_a_ma * gain_exponent)
