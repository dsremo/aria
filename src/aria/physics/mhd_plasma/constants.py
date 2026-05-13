"""Plasma physics constants (§5 of D1 scope).

Every value below carries an inline citation per CLAUDE.md.

Sources:
  - SI 2019 base-unit redefinition (exact values for c, e, k_B, h)
  - CODATA 2018 (Tiesinga et al. 2021 Rev. Mod. Phys. 93 025010)
  - NIST Reference on Constants, Units, and Uncertainty
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PlasmaConstants:
    """Fundamental constants needed by every plasma-physics formula.

    All values are CODATA 2018 / SI 2019 (exact where applicable).
    """

    # Speed of light (SI 2019: exact by definition).
    c_m_s: float = 2.99792458e8

    # Elementary charge (SI 2019: exact by definition).
    e_c: float = 1.602176634e-19

    # Boltzmann constant (SI 2019: exact by definition).
    k_b_j_k: float = 1.380649e-23

    # Proton mass (CODATA 2018; Tiesinga 2021).
    m_p_kg: float = 1.67262192369e-27

    # Electron mass (CODATA 2018).
    m_e_kg: float = 9.1093837015e-31

    # Vacuum permeability (CODATA 2018; no longer exactly 4π×10⁻⁷
    # after the 2019 SI redefinition — this is the best measured value).
    mu_0_n_a2: float = 1.25663706212e-6

    # Vacuum permittivity (CODATA 2018).
    epsilon_0_f_m: float = 8.8541878128e-12

    # Deuterium mass in atomic mass units → kg.
    # m_d ≈ 2.01410177812 u × 1.66053906660e-27 kg/u
    #     ≈ 3.34358377e-27 kg
    # NIST atomic mass evaluation 2016 (Huang 2017 Chin Phys C 41 030002).
    m_d_kg: float = 3.34358377e-27

    # Tritium mass. m_t ≈ 3.01604928 u (NIST AME 2016).
    m_t_kg: float = 5.00735666e-27

    @property
    def m_dt_avg_kg(self) -> float:
        """Mean D-T fuel ion mass — equal-mixture average."""
        return 0.5 * (self.m_d_kg + self.m_t_kg)


PLASMA_CONSTANTS: PlasmaConstants = PlasmaConstants()


def temperature_ev_to_kelvin(t_ev: float) -> float:
    """Convert temperature from eV to K via `k_B T = E` identity.

    T [K] = T [eV] × e / k_B
          = T [eV] × 1.160451812e4        (since e/k_B = 11604.518...)
    """
    if t_ev < 0.0:
        raise ValueError("temperature must be non-negative")
    return t_ev * PLASMA_CONSTANTS.e_c / PLASMA_CONSTANTS.k_b_j_k


def kelvin_to_temperature_ev(t_k: float) -> float:
    """Inverse of ``temperature_ev_to_kelvin``."""
    if t_k < 0.0:
        raise ValueError("temperature must be non-negative")
    return t_k * PLASMA_CONSTANTS.k_b_j_k / PLASMA_CONSTANTS.e_c
