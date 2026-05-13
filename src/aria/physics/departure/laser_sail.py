"""Forward 1984 laser-pushed lightsail propulsion (§4.5 of A3 scope).

Forward 1984 J. Spacecraft 21(2) 187 (DOI 10.2514/3.8632) derived the
force on a perfectly-reflecting flat sail normal to an incident
collimated laser beam of power `P`:

    F = 2 P / c                                     [N]

(factor 2 for specular reflection: the photon's momentum flips, so the
momentum transfer is 2·p_photon instead of p_photon). The corresponding
sail acceleration for a total mass `m` is:

    a = 2 P / (m c)                                 [m/s²]

Units check: [P/(m·c)] = W / (kg · m/s) = (J/s)/(kg·m/s)
           = (N·m/s)/(kg·m/s) = N/kg = m/s²         ✓

Modern follow-ons: Lubin 2016 "A Roadmap to Interstellar Flight" JBIS
69 40 (directed-energy propulsion architecture), Parkin 2018 Acta
Astronautica 144 1 (Breakthrough Starshot physics).
"""

from __future__ import annotations

import math

# Speed of light in vacuum (SI 2019 base-unit redefinition: exact).
SPEED_OF_LIGHT_M_S: float = 2.99792458e8  # SI base units (exact by definition)


def laser_sail_acceleration(
    laser_power_w: float,
    sail_mass_kg: float,
    reflectivity: float = 1.0,
) -> float:
    """Acceleration of a perfectly reflecting flat sail under a
    collimated laser beam.

    a = (1 + R) P / (m c)                           [m/s²]

    where R is the reflectivity (R = 1 for a perfect mirror, giving
    the Forward 1984 factor of 2; R = 0 for a black absorber, giving
    half as much thrust and heating the sail).

    Args:
        laser_power_w: incident power delivered to the sail (W). The
            caller is responsible for beam-divergence and pointing
            losses.
        sail_mass_kg: total decelerating/accelerating mass (sail +
            tethers + payload) in kg.
        reflectivity: `R ∈ [0, 1]`. Default 1 (perfect mirror).

    Returns:
        Acceleration magnitude in m/s².

    Raises:
        ValueError: for non-physical inputs.
    """
    if laser_power_w < 0.0:
        raise ValueError("laser_power_w must be non-negative")
    if sail_mass_kg <= 0.0:
        raise ValueError("sail_mass_kg must be positive")
    if not (0.0 <= reflectivity <= 1.0):
        raise ValueError("reflectivity must be in [0, 1]")
    return (1.0 + reflectivity) * laser_power_w / (sail_mass_kg * SPEED_OF_LIGHT_M_S)


def laser_sail_cruise_time(
    target_delta_v_m_s: float,
    laser_power_w: float,
    sail_mass_kg: float,
    reflectivity: float = 1.0,
) -> float:
    """Time to accelerate a laser sail to a target Δv under constant
    illumination.

    Assumes constant sail mass (no ablation), constant laser power at
    the sail, and neglects relativistic mass increase (valid for
    `Δv ≲ 0.1 c`; the B2 pod handles the relativistic regime).

    t = Δv / a                                      [s]
    """
    if target_delta_v_m_s < 0.0:
        raise ValueError("target_delta_v_m_s must be non-negative")
    a = laser_sail_acceleration(laser_power_w, sail_mass_kg, reflectivity)
    if a <= 0.0:
        return math.inf
    return target_delta_v_m_s / a
