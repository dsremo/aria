"""Christiansen 1990 crater depth scaling (§4.4 of F4 scope).

For a hypervelocity sphere impacting a thick ductile metal target,
the crater depth is empirically correlated by Christiansen 1990
*NASA TM-105002* eq. 2:

    p = 5.24 · d^(19/18) · H^(−1/4) · (ρ_p / ρ_t)^(1/2) ·
        (v cos θ)^(2/3)                                   [cm]

with:
    d = projectile diameter (cm)
    H = target Brinell hardness (dimensionless scale)
    ρ_p, ρ_t = projectile and target densities (g/cm³)
    v = relative impact speed (km/s)
    θ = angle from the target normal (rad)

The scaling is an order-of-magnitude engineering model, calibrated
against the NASA JSC hypervelocity impact test data up to ~7 km/s
Al-on-Al. Above ~15 km/s the crater depth scaling starts to
under-predict because of vaporization effects; Christiansen 1990
§4 discusses the extrapolation caveat.

Worked example from Christiansen 1990 Fig. 4:
  d = 0.8 cm, H = 120 (Al 2024-T3), ρ_p = 2.7, ρ_t = 2.7,
  v = 6.8 km/s, θ = 0.

  p = 5.24 · 0.8^1.056 · 120^-0.25 · 1.0 · 6.8^0.667
    = 5.24 · 0.789 · 0.302 · 3.584
    ≈ 4.47 cm

matches the NASA JSC test-fit to within the scatter band.

This routine returns the depth in **SI meters** (the Christiansen
original is cm for historical reasons).
"""

from __future__ import annotations


def crater_depth_christiansen(
    projectile_diameter_m: float,
    target_brinell_hardness: float,
    projectile_density_kg_m3: float,
    target_density_kg_m3: float,
    impact_velocity_m_s: float,
    angle_from_normal_rad: float = 0.0,
) -> float:
    """Christiansen 1990 NASA TM-105002 eq. 2 crater depth.

    p [m] = 0.0524 · d^(19/18) · H^(−1/4) · (ρ_p/ρ_t)^(1/2) ·
            (v cos θ)^(2/3)

    Note: the Christiansen scaling prefactor is 5.24 in his cgs
    units (d [cm], v [km/s], p [cm]). Converting to SI by retaining
    the same dimensionless powers gives the same 5.24 but requires
    the caller to feed centimetres and kilometres. We do the
    conversion internally so the user supplies SI everywhere.

    Args:
        projectile_diameter_m: d (m).
        target_brinell_hardness: H (dimensionless). For Al 2024-T3
            H ≈ 120, for Ti-6Al-4V ≈ 334, for soft steel ≈ 200.
        projectile_density_kg_m3: ρ_p (kg/m³).
        target_density_kg_m3: ρ_t (kg/m³).
        impact_velocity_m_s: v (m/s).
        angle_from_normal_rad: θ (rad). Default 0 (normal incidence).

    Returns:
        Crater depth p in metres.
    """
    import math

    if projectile_diameter_m <= 0.0:
        raise ValueError("projectile_diameter_m must be positive")
    if target_brinell_hardness <= 0.0:
        raise ValueError("target_brinell_hardness must be positive")
    if projectile_density_kg_m3 <= 0.0 or target_density_kg_m3 <= 0.0:
        raise ValueError("densities must be positive")
    if impact_velocity_m_s < 0.0:
        raise ValueError("impact_velocity_m_s must be non-negative")
    if not (-math.pi / 2 < angle_from_normal_rad < math.pi / 2):
        raise ValueError("angle_from_normal_rad must lie in (-π/2, π/2)")

    # Convert SI inputs to the Christiansen cgs scaling units:
    d_cm = projectile_diameter_m * 100.0  # m → cm
    v_km_s = impact_velocity_m_s / 1000.0  # m/s → km/s
    # Densities enter only as a ratio, so kg/m³ vs g/cm³ cancels.
    density_ratio = projectile_density_kg_m3 / target_density_kg_m3

    cos_theta = math.cos(angle_from_normal_rad)
    v_cos_theta = v_km_s * cos_theta
    if v_cos_theta <= 0.0:
        return 0.0

    p_cm = (
        5.24
        * (d_cm ** (19.0 / 18.0))
        * (target_brinell_hardness ** -0.25)
        * (density_ratio ** 0.5)
        * (v_cos_theta ** (2.0 / 3.0))
    )
    # Back to SI metres.
    return p_cm / 100.0
