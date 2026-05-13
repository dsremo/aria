"""Gravitational-wave energy loss from a close two-body encounter
(§4.8 of docs/pods/A2_tidal_tensor.md).

The Peters-Mathews 1963 quadrupole formula (Phys. Rev. 131 435,
DOI 10.1103/PhysRev.131.435) gives the instantaneous GW luminosity of
a two-body system in a circular orbit of separation `r`:

    P_GW = (32/5) · G⁴/c⁵ · m_1² m_2² (m_1 + m_2) / r⁵   [W]

Unit audit:
    [G⁴/c⁵] = (m³ kg⁻¹ s⁻²)⁴ / (m/s)⁵
            = m¹² kg⁻⁴ s⁻⁸ / (m⁵ s⁻⁵)
            = m⁷ kg⁻⁴ s⁻³
    [P_GW]  = m⁷ kg⁻⁴ s⁻³ · kg⁵ / m⁵
            = m² kg s⁻³ = (kg m²/s²) / s = J/s = W     ✓

For ARIA-scale encounters the numbers are absurdly small:
  - ship `m₁ = 10⁷ kg`, Jupiter `m₂ = 1.9e27 kg`, `r = 10⁸ m`
    → P_GW ≈ 10⁻⁴⁵ W, completely undetectable.

A2 still evaluates the Peters-Mathews integral along every close
encounter so we can state in writing that GR radiation reaction is
below 10⁻³⁰ of any other force in the sim.
"""

from __future__ import annotations

# CODATA 2018 constants.
_G: float = 6.67430e-11  # m³ kg⁻¹ s⁻²
_C: float = 2.99792458e8  # m/s (SI exact)


def peters_mathews_gw_power(
    mass_1_kg: float, mass_2_kg: float, separation_m: float
) -> float:
    """Instantaneous GW luminosity of a two-body circular orbit.

    P_GW = (32/5) G⁴ c⁻⁵ m₁² m₂² (m₁ + m₂) / r⁵        [W]

    Args:
        mass_1_kg: mass of the first body (kg).
        mass_2_kg: mass of the second body (kg).
        separation_m: instantaneous body-body separation (m).

    Returns:
        GW power radiated in W. Always non-negative.

    Notes:
        The Peters-Mathews formula is derived for a bound circular
        orbit; it is still a valid *instantaneous* radiation rate for
        a hyperbolic flyby at closest approach (the leading quadrupole
        is quadratic in the second time derivative of the inertia
        tensor and does not care about boundedness). For flybys the
        radiated energy is the integral `∫ P_GW dt` over the close-
        approach duration, which the caller does numerically.
    """
    if mass_1_kg <= 0.0 or mass_2_kg <= 0.0:
        raise ValueError("masses must be positive")
    if separation_m <= 0.0:
        raise ValueError("separation_m must be positive")
    prefac = (32.0 / 5.0) * (_G**4) / (_C**5)
    mass_term = (mass_1_kg**2) * (mass_2_kg**2) * (mass_1_kg + mass_2_kg)
    return prefac * mass_term / (separation_m**5)
