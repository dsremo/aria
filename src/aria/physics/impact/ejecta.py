"""Crater ejecta scaling (§4.6 of F4 scope).

At hypervelocity, a projectile impacting a thick target excavates a
crater and ejects a mass of target material that is much larger
than the projectile mass (because the projectile delivers enough
kinetic energy to eject many projectile-masses-worth of target at
lower speeds). Schonberg 2010 *International Journal of Impact
Engineering* 37, 456-468, DOI 10.1016/j.ijimpeng.2009.09.007,
gives empirical scalings for the ejecta mass, cone angle, and
velocity distribution.

Engineering approximation for the total ejecta mass:

    M_ejecta ≈ 10 · m_projectile · (v / 3 km/s)          [kg]

(Schonberg 2010 eq. 8 simplified for a = 0.5). This is an order-
of-magnitude relation valid in the 3-15 km/s regime; outside it
the scaling is untested.

The ejecta cone half-angle is typically 45°-60° (Schonberg 2010
Fig. 4); ARIA uses 50° as the default nominal value. The fraction
of the ejecta mass beyond a given half-angle follows a roughly
Gaussian distribution around the normal.

The velocity distribution is bimodal: a small high-velocity jet
(spall / front surface) and a larger low-velocity bulk. The
Schonberg 2010 paper provides the parametric fit; for our P1
subset we expose only the scalar mass and the nominal cone angle,
which is what the downstream structural pods need to close the
momentum balance.
"""

from __future__ import annotations

import math


def ejecta_mass_schonberg(
    projectile_mass_kg: float,
    impact_velocity_m_s: float,
) -> float:
    """Schonberg 2010 ejecta-mass scaling.

    M_ejecta ≈ 10 · m_p · (v / 3 km/s)                   [kg]

    Valid in the 3-15 km/s hypervelocity regime. Below 3 km/s the
    scaling over-predicts (low velocity produces less excavation);
    above 15 km/s the scaling saturates because the target starts
    to vaporize and the mass of "ejecta" (vapor) is ill-defined.
    The caller should verify the velocity regime before trusting
    the returned number.

    Args:
        projectile_mass_kg: m_p in kg (positive).
        impact_velocity_m_s: v in m/s (positive).

    Returns:
        Ejecta mass in kg.
    """
    if projectile_mass_kg <= 0.0:
        raise ValueError("projectile_mass_kg must be positive")
    if impact_velocity_m_s < 0.0:
        raise ValueError("impact_velocity_m_s must be non-negative")
    v_km_s = impact_velocity_m_s / 1000.0
    return 10.0 * projectile_mass_kg * (v_km_s / 3.0)


def ejecta_cone_half_angle_default() -> float:
    """Default nominal cone half-angle for the ejecta plume (rad).

    Returns 50° in radians per Schonberg 2010 Fig. 4 mean of the
    45°-60° observed band.
    """
    return math.radians(50.0)
