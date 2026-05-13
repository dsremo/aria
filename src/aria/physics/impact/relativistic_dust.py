"""Relativistic interstellar dust impact (§4.7 of F4 scope).

At ARIA's cruise velocity (β ≈ 0.1), an interstellar dust grain
with a rest-frame mass of ~10⁻¹⁵ kg carries a kinetic energy that
classical and Hertzian analyses completely misrepresent. The
relativistic kinetic energy is

    KE = (γ − 1) m_0 c²                                   [J]

with the Lorentz factor

    γ = 1 / √(1 − β²)                                    [dimensionless]

For β = 0.1, γ = 1.00504, so KE ≈ 0.005 m_0 c². A 10⁻¹⁵ kg grain
then carries ~4.5 × 10⁻⁴ J — a small number in absolute terms but
*much* larger than the classical (1/2) m v² = 4.5 × 10⁻⁴ J (they
agree at this γ because β is small). The divergence from the
classical formula grows rapidly above β ≈ 0.3:

    β     γ         KE / ((1/2) m v²)
    0.10  1.005     ≈ 1.005
    0.30  1.048     ≈ 1.048
    0.50  1.155     ≈ 1.155
    0.90  2.294     ≈ 3.1
    0.99  7.089     ≈ 12.4

Relativistic momentum:

    p = γ m_0 v                                           [kg·m/s]

The *energy* carried by a single grain is deposited in a volume
comparable to the projectile's Lorentz-contracted size; at the
threshold of the ultra-relativistic regime we can no longer trust
the Christiansen / NNO scaling because the impact physics is
dominated by plasma formation and ablation rather than mechanical
cratering.

This module provides the kinematic closed forms (exact) and a
regime-gate helper that flags when we are past the 0.01 c threshold
at which the empirical BLE equations should not be trusted. ARIA's
`whipple.py` consumes the flag and issues an ESTIMATE warning with
a widened uncertainty band.

References:
  - Einstein 1905 Ann. Phys. 17 891 (relativistic KE and momentum)
  - Rindler 2006 *Relativity: Special, General, and Cosmological*
    2nd ed (ISBN 978-0198567325)
  - Hoang 2017 ApJ 847 77 DOI 10.3847/1538-4357/aa88a7
    (interstellar dust impact on relativistic probes)
"""

from __future__ import annotations

import math

# Speed of light (SI 2019 base-unit redefinition: exact).
SPEED_OF_LIGHT_M_S: float = 2.99792458e8

# Threshold beyond which the Christiansen / NNO empirical ballistic
# limit equations are not trusted. 0.01 c = 3×10⁶ m/s is ~200× the
# highest NASA JSC HVI test-range velocity (~15 km/s).
ULTRA_RELATIVISTIC_THRESHOLD_FRACTION_C: float = 0.01


def is_ultra_relativistic_regime(velocity_m_s: float) -> bool:
    """True if ``velocity_m_s`` exceeds the 0.01 c gate for the
    empirical Whipple BLE.
    """
    if velocity_m_s < 0.0:
        raise ValueError("velocity_m_s must be non-negative")
    return velocity_m_s > ULTRA_RELATIVISTIC_THRESHOLD_FRACTION_C * SPEED_OF_LIGHT_M_S


def _lorentz_gamma(velocity_m_s: float) -> float:
    if velocity_m_s < 0.0:
        raise ValueError("velocity_m_s must be non-negative")
    beta = velocity_m_s / SPEED_OF_LIGHT_M_S
    if beta >= 1.0:
        raise ValueError("velocity cannot reach or exceed c")
    return 1.0 / math.sqrt(1.0 - beta * beta)


def relativistic_impact_kinetic_energy(
    rest_mass_kg: float, velocity_m_s: float
) -> float:
    """Exact relativistic kinetic energy `(γ − 1) m_0 c²` [J].

    For ``v ≪ c`` this reduces to the classical `(1/2) m v²`
    formula to O(β²); at β = 0.1 the difference is ~0.5 %.

    Args:
        rest_mass_kg: rest mass of the projectile (kg, positive).
        velocity_m_s: lab-frame speed (m/s). Must be < c.

    Returns:
        Kinetic energy in joules. Non-negative.
    """
    if rest_mass_kg <= 0.0:
        raise ValueError("rest_mass_kg must be positive")
    gamma = _lorentz_gamma(velocity_m_s)
    return (gamma - 1.0) * rest_mass_kg * SPEED_OF_LIGHT_M_S * SPEED_OF_LIGHT_M_S


def relativistic_impact_momentum(
    rest_mass_kg: float, velocity_m_s: float
) -> float:
    """Exact relativistic momentum `γ m_0 v` [kg·m/s].

    Args:
        rest_mass_kg: rest mass (kg).
        velocity_m_s: lab-frame speed (m/s).

    Returns:
        Momentum magnitude in kg·m/s.
    """
    if rest_mass_kg <= 0.0:
        raise ValueError("rest_mass_kg must be positive")
    gamma = _lorentz_gamma(velocity_m_s)
    return gamma * rest_mass_kg * velocity_m_s
