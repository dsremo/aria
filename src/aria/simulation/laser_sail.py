"""Laser Sail Dynamics — photon-driven propulsion for interstellar missions.

A laser sail uses a ground-based or space-based laser array to push a
reflective sail. Unlike rockets, the propellant (photons) stays behind,
giving effectively infinite Isp. The tradeoff: thrust decreases with
distance (beam divergence) and the sail must survive extreme heating.

PHYSICS
=======
Radiation pressure force on a perfect reflector:
  F = 2P/c    (factor 2 for perfect reflection; 1 for absorption)

For a real sail with reflectivity R and absorptivity A:
  F = (1 + R) × P/c    where P = intercepted laser power

Acceleration:
  a = F/m = (1 + R) × P / (m × c)

For a sail with areal density σ (kg/m²):
  a = (1 + R) × I / (σ × c)    where I = intensity (W/m²)

BEAM DIVERGENCE
===============
The laser beam spreads over distance due to diffraction:
  θ_divergence ≈ λ / D_aperture    (radians)

At distance d, the beam spot diameter:
  d_spot = 2 × d × θ = 2 × d × λ / D

If the sail is smaller than the beam spot, not all power is intercepted:
  P_intercepted = P_laser × (A_sail / A_spot)    when A_sail < A_spot

This means acceleration drops as 1/d² beyond the "beam-riding distance"
where the spot size equals the sail size.

BREAKTHROUGH STARSHOT PARAMETERS (Lubin 2016)
=============================================
  Laser array power:  100 GW
  Laser wavelength:   1.06 μm (Nd:YAG)
  Array diameter:     10 km (phased array)
  Sail diameter:      4.1 m (circular)
  Sail mass:          1 g (gram-scale probe!)
  Target speed:       0.2c (60,000 km/s)
  Acceleration:       ~60,000 m/s² (~6,000 g) for ~10 minutes
  Beam-riding distance: ~0.01 AU (beyond this, beam > sail)

Brown University 2025: AI-optimized 200nm thin-film sail with pentagonal
hole lattice — 9000× cost reduction vs. previous designs.

References
----------
  Lubin P. (2016) JBIS 69 — "A Roadmap to Interstellar Flight"
  Forward R. (1984) JBIS 37 — "Roundtrip Interstellar Travel Using Laser-Pushed Lightsails"
  Brown/TU Delft (2025) — AI-optimized photonic lightsail
  Kulkarni N. et al. (2018) Nature Comm. 9 — lightsail stability
  arXiv:2502.17828 (2026) — photonic lightsail thermal management
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger()

# ═══════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════

C_LIGHT = 2.998e8          # Speed of light (m/s) — NIST CODATA 2018
AU_M = 1.496e11            # Astronomical unit (m) — IAU 2012
LY_M = 9.461e15            # Light-year (m) — IAU definition


# ═══════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class LaserSailConfig:
    """Laser sail mission configuration."""
    laser_power_w: float         # Total laser array power (W)
    laser_wavelength_m: float    # Laser wavelength (m)
    array_diameter_m: float      # Laser array aperture diameter (m)
    sail_diameter_m: float       # Sail diameter (m)
    sail_mass_kg: float          # Total sail + payload mass (kg)
    reflectivity: float          # Sail reflectivity (0–1). Good sail: 0.99+


@dataclass
class LaserSailResult:
    """Laser sail acceleration and mission analysis."""
    config: LaserSailConfig
    # Acceleration phase
    initial_accel_ms2: float         # Acceleration at start (m/s²)
    initial_accel_g: float           # In Earth g
    beam_riding_distance_m: float    # Distance where beam spot = sail area
    beam_riding_distance_au: float
    # At beam-riding limit
    speed_at_beam_limit_ms: float    # Speed when beam > sail (m/s)
    speed_at_beam_limit_c: float     # As fraction of c
    accel_time_s: float              # Time to reach beam limit (s)
    # Cruise
    final_speed_ms: float            # Final cruise speed (= speed at beam limit)
    final_speed_c: float             # As fraction of c
    # Travel times
    time_to_alpha_centauri_yr: float  # 4.37 ly at cruise speed
    time_to_100au_yr: float           # Kuiper belt exit


@dataclass
class SailThermalAnalysis:
    """Thermal analysis of a laser sail under illumination."""
    absorbed_power_w: float          # Power absorbed by sail (W)
    equilibrium_temp_k: float        # Radiative equilibrium temperature (K)
    max_safe_intensity_w_m2: float   # Max intensity before sail melts (W/m²)
    max_safe_power_w: float          # Max laser power for this sail


# ═══════════════════════════════════════════════════════════════════
#  CORE PHYSICS
# ═══════════════════════════════════════════════════════════════════

def compute_sail_acceleration(config: LaserSailConfig) -> LaserSailResult:
    """Compute laser sail acceleration, beam-riding limit, and cruise speed.

    The sail accelerates under laser pressure until the beam diverges
    beyond the sail area (beam-riding limit). Beyond that point, the
    intercepted power drops as 1/d², and acceleration drops as 1/d².

    Simplified model: constant acceleration up to beam-riding distance,
    then zero thrust (cruise phase). This is optimistic — a real sail
    decelerates gradually as the beam overfills the sail.

    Args:
        config: LaserSailConfig with laser and sail parameters.

    Returns:
        LaserSailResult with acceleration, speed, and travel times.

    References:
        Lubin (2016) JBIS 69 — equation set for laser-driven sail.
    """
    P = config.laser_power_w
    lam = config.laser_wavelength_m
    D_arr = config.array_diameter_m
    D_sail = config.sail_diameter_m
    m = config.sail_mass_kg
    R = config.reflectivity

    # Radiation pressure force: F = (1+R) × P/c
    F = (1.0 + R) * P / C_LIGHT

    # Initial acceleration (all power intercepted)
    a0 = F / m  # m/s²

    # Beam divergence angle (diffraction-limited)
    theta = lam / D_arr  # radians

    # Beam-riding distance: where beam spot diameter = sail diameter
    # d_spot = 2 × d × θ = D_sail → d = D_sail / (2θ)
    d_beam = D_sail / (2.0 * theta)  # meters

    # Speed at beam-riding limit (constant acceleration):
    # v = sqrt(2 × a × d)
    v_beam = math.sqrt(2.0 * a0 * d_beam)

    # Time to reach beam-riding limit:
    # t = v / a = sqrt(2d/a)
    t_beam = v_beam / a0

    # Cruise speed (no more acceleration beyond beam limit)
    v_final = v_beam

    # Travel times at cruise speed
    d_ac = 4.37 * LY_M   # Alpha Centauri distance
    d_100au = 100.0 * AU_M
    t_ac_yr = d_ac / v_final / (365.25 * 86400) if v_final > 0 else float('inf')
    t_100au_yr = d_100au / v_final / (365.25 * 86400) if v_final > 0 else float('inf')

    return LaserSailResult(
        config=config,
        initial_accel_ms2=a0,
        initial_accel_g=a0 / 9.80665,
        beam_riding_distance_m=d_beam,
        beam_riding_distance_au=d_beam / AU_M,
        speed_at_beam_limit_ms=v_beam,
        speed_at_beam_limit_c=v_beam / C_LIGHT,
        accel_time_s=t_beam,
        final_speed_ms=v_final,
        final_speed_c=v_final / C_LIGHT,
        time_to_alpha_centauri_yr=t_ac_yr,
        time_to_100au_yr=t_100au_yr,
    )


def sail_thermal_analysis(
    config: LaserSailConfig,
    emissivity: float = 0.5,
    max_temp_k: float = 1500.0,
) -> SailThermalAnalysis:
    """Compute sail thermal equilibrium under laser illumination.

    The sail absorbs a fraction (1−R) of incident power and must radiate
    it away. At thermal equilibrium:
      P_absorbed = ε × σ × A × T⁴ × 2  (both sides radiate)

    The sail temperature determines the maximum safe laser power.

    Args:
        config:     LaserSailConfig.
        emissivity: Sail thermal emissivity (0–1). Typical: 0.3–0.8.
        max_temp_k: Maximum operating temperature before degradation (K).
                    SiC: 2000 K; Al: 600 K; Si₃N₄: 1500 K.

    Returns:
        SailThermalAnalysis with temperatures and power limits.

    References:
        arXiv:2502.17828 (2026) — photonic sail thermal management.
        Lubin (2016) §4.3 — sail temperature constraints.
    """
    sigma_sb = 5.6704e-8  # Stefan-Boltzmann (W/m²/K⁴)
    A_sail = math.pi * (config.sail_diameter_m / 2.0) ** 2
    absorptivity = 1.0 - config.reflectivity

    # Absorbed power
    P_abs = absorptivity * config.laser_power_w  # assumes all power hits sail

    # Equilibrium temperature: P_abs = 2 × ε × σ × A × T⁴
    if emissivity > 0 and A_sail > 0:
        T_eq = (P_abs / (2.0 * emissivity * sigma_sb * A_sail)) ** 0.25
    else:
        T_eq = float('inf')

    # Maximum safe power: solve for P at T = max_temp_k
    P_max = 2.0 * emissivity * sigma_sb * A_sail * max_temp_k**4
    I_max = P_max / (absorptivity * A_sail) if absorptivity > 0 else float('inf')

    return SailThermalAnalysis(
        absorbed_power_w=P_abs,
        equilibrium_temp_k=T_eq,
        max_safe_intensity_w_m2=I_max,
        max_safe_power_w=P_max / absorptivity if absorptivity > 0 else float('inf'),
    )


# ═══════════════════════════════════════════════════════════════════
#  PRE-BUILT CONFIGURATIONS
# ═══════════════════════════════════════════════════════════════════

def breakthrough_starshot() -> LaserSailResult:
    """Breakthrough Starshot baseline configuration.

    Reference: Lubin (2016) JBIS 69 — "A Roadmap to Interstellar Flight".
    """
    config = LaserSailConfig(
        laser_power_w=100e9,       # 100 GW — Lubin (2016) Table 1
        laser_wavelength_m=1.06e-6,  # Nd:YAG 1.06 μm — Lubin (2016)
        array_diameter_m=10_000.0,   # 10 km phased array — Lubin (2016)
        sail_diameter_m=4.1,         # 4.1 m sail — Lubin (2016) Table 1
        sail_mass_kg=0.001,          # 1 gram total — Lubin (2016)
        reflectivity=0.999,          # Near-perfect reflector — Brown/TU Delft (2025)
    )
    return compute_sail_acceleration(config)


def solar_system_sail(sail_mass_kg: float = 100.0) -> LaserSailResult:
    """Larger sail for a solar system exploration mission.

    100 kg payload with 1 GW laser — not interstellar, but fast solar system.
    """
    config = LaserSailConfig(
        laser_power_w=1e9,            # 1 GW laser — within near-term reach
        laser_wavelength_m=1.06e-6,
        array_diameter_m=1_000.0,     # 1 km aperture
        sail_diameter_m=100.0,        # 100 m diameter sail
        sail_mass_kg=sail_mass_kg,
        reflectivity=0.99,
    )
    return compute_sail_acceleration(config)


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n── Breakthrough Starshot (1 gram, 100 GW) ───────────────────")
    bs = breakthrough_starshot()
    print(f"  Initial accel:    {bs.initial_accel_ms2:.0f} m/s² ({bs.initial_accel_g:.0f} g)")
    print(f"  Beam-riding dist: {bs.beam_riding_distance_au:.4f} AU "
          f"({bs.beam_riding_distance_m/1e9:.1f} × 10⁹ m)")
    print(f"  Accel time:       {bs.accel_time_s:.0f} s ({bs.accel_time_s/60:.1f} min)")
    print(f"  Final speed:      {bs.final_speed_ms/1000:.0f} km/s ({bs.final_speed_c:.3f}c)")
    print(f"  Alpha Centauri:   {bs.time_to_alpha_centauri_yr:.1f} years")
    print(f"  100 AU:           {bs.time_to_100au_yr:.2f} years")

    print("\n── Solar System Sail (100 kg, 1 GW) ─────────────────────────")
    ss = solar_system_sail()
    print(f"  Initial accel:    {ss.initial_accel_ms2:.3f} m/s² ({ss.initial_accel_g:.4f} g)")
    print(f"  Final speed:      {ss.final_speed_ms/1000:.1f} km/s ({ss.final_speed_c:.6f}c)")
    print(f"  100 AU:           {ss.time_to_100au_yr:.1f} years")

    print("\n── Starshot Thermal Analysis ─────────────────────────────────")
    bs_config = LaserSailConfig(100e9, 1.06e-6, 10000, 4.1, 0.001, 0.999)
    th = sail_thermal_analysis(bs_config, emissivity=0.5, max_temp_k=1500)
    print(f"  Absorbed power:   {th.absorbed_power_w/1e6:.0f} MW (0.1% of 100 GW)")
    print(f"  Equilibrium temp: {th.equilibrium_temp_k:.0f} K")
    print(f"  Max safe power:   {th.max_safe_power_w/1e9:.1f} GW (before sail melts)")
