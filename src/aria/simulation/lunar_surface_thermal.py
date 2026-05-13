"""Lunar surface thermal cycling — day/night extremes on the Moon.

Apollo 17 on-surface measurements: equatorial midday ~+106 °C, midnight
~-173 °C, a 279 K swing over a 29.5-Earth-day cycle. Thermal fatigue
from this cycling is the primary life-limiter for surface hardware.

This module gives ARIA a real thermal-network model for surface
equipment:

  1. **Lunar day/night temperature** — sun elevation × albedo + regolith
     thermal inertia (Langseth 1976 HFE data)
  2. **Equipment thermal response** — lumped-capacitance radiator sized
     for the lander / rover / ISRU plant + multi-layer insulation (MLI)
     effectiveness at extreme temperatures
  3. **Thermal fatigue** — cycle counting for structural joints exposed
     to ΔT > 200 K (combined with Miner's rule from solid_mechanics)

References:
    Heiken, Vaniman & French (1991) "Lunar Sourcebook" §4.1
    Langseth, M. G. et al. (1976) "Revised Lunar Heat-Flow Values,"
        Lunar Sci. Conf. 7, 3143-3171.
    Vasavada et al. (2012) J. Geophys. Res. 117, E00H18 (Diviner data)
    NASA/TM-20220011598 "Lunar Surface Thermal Environments"
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional


# Lunar orbital / physical constants
SIDEREAL_MONTH_D = 27.3217   # days
SYNODIC_MONTH_D = 29.5306    # sun-to-sun; this is what drives lighting
R_MOON_M = 1737400.0
SOLAR_FLUX_AT_MOON = 1361.0  # W/m² (same as Earth; neglect eccentricity)
STEFAN_BOLTZMANN = 5.670374419e-8


@dataclass
class LunarThermalSite:
    """Surface location for thermal modeling."""
    name: str = "Apollo 17 Taurus-Littrow"
    latitude_deg: float = 20.19
    longitude_deg: float = 30.77
    albedo: float = 0.12               # regolith mean (Vasavada 2012)
    thermal_inertia_j_m2_k_s05: float = 50.0   # TI in MKS (Langseth range 30-70)
    # Regolith emissivity in the LWIR
    emissivity: float = 0.97


@dataclass
class LunarThermalState:
    """One snapshot in a surface diurnal cycle."""
    t_hours: float
    sun_elevation_deg: float
    surface_temp_k: float
    incident_flux_w_m2: float


def _sun_elevation(t_h: float, latitude_deg: float,
                   longitude_deg: float = 0.0) -> float:
    """Approximate sun elevation at lunar equator-relative latitude / longitude.

    t_h is mission-clock hours from local noon. The synodic-month period
    (29.5306 d) governs local solar time; we approximate it as a simple
    cosine in mission-clock time.
    """
    # Synodic hour-angle: ω = 2π / T_synodic, T = 29.5 d
    omega_per_hour = 2 * math.pi / (SYNODIC_MONTH_D * 24)
    h_angle = omega_per_hour * t_h + math.radians(longitude_deg)
    lat = math.radians(latitude_deg)
    # solar declination ignored (near 0 on lunar equator)
    sin_elev = math.sin(lat) * 0 + math.cos(lat) * math.cos(h_angle)
    sin_elev = max(-1.0, min(1.0, sin_elev))
    return math.degrees(math.asin(sin_elev))


def surface_temperature(t_h: float, site: LunarThermalSite) -> LunarThermalState:
    """Estimate surface temperature given time since local noon.

    Heat balance at steady state (simplified):
        (1 − α) S cos(θ) + F_geo  =  ε σ T⁴ + C_reg dT/dt

    We approximate the diurnal response with a complex of:
      - direct solar heating when sun above horizon
      - radiative emission continuously
      - soil thermal inertia lag (phase shift ~3-5 h)
    """
    sun_elev = _sun_elevation(t_h, site.latitude_deg, site.longitude_deg)
    if sun_elev > 0:
        cos_z = math.sin(math.radians(sun_elev))
        incident = SOLAR_FLUX_AT_MOON * cos_z * (1 - site.albedo)
    else:
        incident = 0.0
    # Geothermal flux ~ 21 mW/m² (Langseth)
    geo = 0.021
    total_heating = incident + geo
    # Equilibrium temperature from ε σ T⁴ = total_heating
    if total_heating > 1e-3:
        t_eq = (total_heating / (site.emissivity * STEFAN_BOLTZMANN)) ** 0.25
    else:
        t_eq = 120.0   # Deep-night floor ~100-130 K (Vasavada 2012)

    # Damp with thermal inertia: true surface temperature lags equilibrium
    # by a phase ~3 h (scaling with TI). Implemented as a simple weighted
    # blend between current equilibrium and a mean-temperature baseline.
    mean_t = 215.0   # Langseth annual mean at equator
    damping = min(1.0, site.thermal_inertia_j_m2_k_s05 / 100.0)
    # More damping = closer to mean; extreme swings only for low-TI regolith
    surface = mean_t + (t_eq - mean_t) * (1.0 - damping * 0.25)
    # Cap at physical bounds observed by Diviner: lunar equatorial night
    # doesn't go below ~100 K (regolith heat capacity buffers), day peaks
    # near 390 K at subsolar.
    surface = max(95.0, min(surface, 395.0))
    return LunarThermalState(
        t_hours=t_h, sun_elevation_deg=sun_elev,
        surface_temp_k=surface, incident_flux_w_m2=incident,
    )


def diurnal_cycle(site: LunarThermalSite, n_samples: int = 120) -> List[LunarThermalState]:
    """Full synodic-month temperature curve (lunar-day surface cycling)."""
    total_hours = SYNODIC_MONTH_D * 24
    return [surface_temperature(t_h=total_hours * k / (n_samples - 1), site=site)
            for k in range(n_samples)]


# ════════════════════════════════════════════════════════════════════
#  Equipment thermal response (lumped node)
# ════════════════════════════════════════════════════════════════════

@dataclass
class EquipmentThermalConfig:
    """Surface equipment thermal properties."""
    name: str = "HLS-class lander"
    mass_kg: float = 30_000.0
    specific_heat_j_kg_k: float = 900.0       # Al/CFRP average
    radiator_area_m2: float = 30.0            # deployable
    mli_layers: int = 30                       # gold/Mylar multi-layer
    coating_emissivity: float = 0.85          # white thermal control paint
    coating_absorptivity: float = 0.25        # keeps solar absorption low
    internal_heat_w: float = 500.0            # electronics + avionics


@dataclass
class EquipmentThermalState:
    t_hours: float
    equipment_temp_k: float
    heat_in_w: float
    heat_out_w: float
    surface_temp_k: float


def simulate_equipment(cfg: EquipmentThermalConfig,
                       site: LunarThermalSite,
                       n_cycles: int = 1,
                       dt_s: float = 600.0) -> List[EquipmentThermalState]:
    """Integrate equipment temperature across n_cycles synodic months.

    Lumped capacitance node with:
      - Direct solar absorption: α × S × cos(z)    [W]
      - Regolith IR reflection:   ε × σ T_reg⁴ × A_view   [W]
      - Radiator IR emission:     ε × σ T⁴ × A_rad          [W out]
      - Internal dissipation:     P_int                    [W in]
      - MLI thermal resistance at extremes
    """
    total_h = SYNODIC_MONTH_D * 24 * n_cycles
    n_steps = int(total_h * 3600 / dt_s)
    # Thermal capacity of equipment
    C_eq = cfg.mass_kg * cfg.specific_heat_j_kg_k   # J/K
    temp = 290.0   # K, start at ambient cabin temp
    history: List[EquipmentThermalState] = []
    mli_factor = max(0.01, 1.0 / (cfg.mli_layers + 1))   # ~N-layer reduction

    for step in range(n_steps):
        t_h = step * dt_s / 3600
        surface = surface_temperature(t_h % (SYNODIC_MONTH_D * 24), site)
        sun_elev = max(0.0, surface.sun_elevation_deg)
        cos_z = math.sin(math.radians(sun_elev))

        # Solar absorption on a flat top plate (small area fraction)
        top_area = cfg.radiator_area_m2 * 0.5
        solar_abs_w = cfg.coating_absorptivity * SOLAR_FLUX_AT_MOON * cos_z * top_area

        # IR from regolith (hot during day, cold at night): assumed 50% view factor
        T_reg = surface.surface_temp_k
        view_factor = 0.5
        reg_flux_w = (STEFAN_BOLTZMANN * cfg.coating_emissivity * T_reg ** 4
                      * view_factor * top_area * mli_factor)

        # Radiation to 3 K sky
        rad_out_w = STEFAN_BOLTZMANN * cfg.coating_emissivity * temp ** 4 \
                    * cfg.radiator_area_m2

        heat_in = solar_abs_w + reg_flux_w + cfg.internal_heat_w
        heat_out = rad_out_w
        dT = (heat_in - heat_out) / C_eq * dt_s
        temp = max(20.0, min(temp + dT, 600.0))

        if step % max(1, n_steps // 240) == 0:
            history.append(EquipmentThermalState(
                t_hours=t_h, equipment_temp_k=temp,
                heat_in_w=heat_in, heat_out_w=heat_out,
                surface_temp_k=surface.surface_temp_k,
            ))
    return history


def thermal_cycle_fatigue_cycles(delta_t_k: float, n_cycles: int,
                                  s_n_slope: float = -0.12,
                                  reference_cycles: float = 1e6) -> float:
    """Estimate cumulative fatigue from thermal cycling using a simple S–N
    relation.

    For structural joints subjected to a thermal range ΔT, the equivalent
    strain range is Δε ≈ α × ΔT (α ≈ 10⁻⁵ /K for aluminium-class alloys).
    Coffin-Manson fatigue life is N_f = (Δε/ε_ref)^(1/s). For aerospace
    joints we use s=-0.12 and ε_ref = 0.01 (reference low-cycle fatigue
    strain).

    Returns accumulated damage fraction (Miner's rule). Damage ≥ 1 means
    failure predicted.
    """
    alpha = 1.0e-5   # thermal expansion coefficient (typical aluminium)
    eps_range = alpha * delta_t_k
    eps_ref = 0.01
    if eps_range <= 0:
        return 0.0
    nf = reference_cycles * (eps_range / eps_ref) ** (1 / s_n_slope)
    return n_cycles / max(nf, 1.0)
