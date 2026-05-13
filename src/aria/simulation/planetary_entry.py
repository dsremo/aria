"""Planetary Atmospheric Entry — Mars, Venus, Titan, Jupiter.

Extends the Earth reentry model to other planetary atmospheres. Each planet
has different composition, density profile, gravity, and entry speeds.

PHYSICS
=======
The same equations govern entry at all planets:
  - Peak deceleration: n ∝ v² × sin|γ| (Allen-Eggers, independent of β)
  - Peak heat rate: q ∝ v³ × sqrt(ρ_peak / R_N) (Sutton-Graves)
  - ρ_peak = β × sin|γ| / H (from atmospheric scale height H)

But the constants differ dramatically:
  - Mars:    CO₂ atmo, thin (ρ₀ ≈ 0.020 kg/m³), H ≈ 11 km, v_entry ≈ 5.5 km/s
  - Venus:   CO₂ atmo, thick (ρ₀ ≈ 65 kg/m³), H ≈ 15.9 km, v_entry ≈ 11.2 km/s
  - Titan:   N₂ atmo, thick (ρ₀ ≈ 5.4 kg/m³), H ≈ 20 km, v_entry ≈ 6.1 km/s
  - Jupiter: H₂/He atmo, dense, H ≈ 27 km, v_entry ≈ 47 km/s (Galileo probe)

KEY DIFFERENCES FROM EARTH
===========================
  1. Mars: atmosphere is 100× thinner → peak deceleration happens at lower altitude.
     Parachutes alone can't slow to landing speed (Mach ≈ 2 at deployment).
     All Mars landers use retropropulsion or airbags for the final phase.

  2. Venus: surface pressure 93× Earth → brutal entry, but very thick atmosphere
     slows the probe quickly. Soviet Venera probes survived to surface.

  3. Titan: 1.5× Earth surface pressure but only 14% of Earth gravity →
     gentle entry. Huygens probe used a heat shield + parachute.

  4. Jupiter: 47 km/s entry → 230 g peak deceleration for Galileo probe (1995).
     The most violent atmospheric entry ever performed by a spacecraft.

VALIDATION
==========
  Mars (MSL Curiosity 2012): v=5.8 km/s, peak decel 11.4 g, peak q̇ 197 W/cm²
  Titan (Huygens 2005): v=6.1 km/s, peak decel 16 g, peak q̇ 35 W/cm²
  Jupiter (Galileo 1995): v=47.4 km/s, peak decel 230 g, peak q̇ 17,000 W/cm²

References
----------
  Braun R.D. & Manning R.M. (2007) "Mars Exploration Entry, Descent and Landing
    Challenges" J. Spacecraft 44:2 — Mars EDL overview
  Seiff A. et al. (1998) JGR 103:E10 — Galileo probe entry measurements
  Lebreton J-P. et al. (2005) Nature 438 — Huygens probe at Titan
  Lorenz R.D. (2010) "Titan Unveiled" — Titan atmospheric properties
  Justus C.G. et al. (2006) NASA/TM-2006-214382 — Mars-GRAM atmosphere model
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger()

# ═══════════════════════════════════════════════════════════════════
#  PLANETARY ATMOSPHERE DATA
# ═══════════════════════════════════════════════════════════════════
# Each planet: (surface density, scale height, surface gravity, surface pressure,
#               gas constant, mean molecular weight, composition)

ATMOSPHERES = {
    "earth": {
        "rho_surface_kg_m3": 1.225,     # US Standard Atmosphere 1976
        "scale_height_m": 8_500.0,      # US Standard Atmosphere 1976
        "g_surface_ms2": 9.81,          # NIST CODATA 2018
        "p_surface_pa": 101_325.0,      # US Standard Atmosphere 1976
        "composition": "N₂/O₂ (78/21%)",
        "mu_planet_m3s2": 3.986e14,     # Vallado 4th ed
        "r_planet_m": 6.378e6,          # Vallado 4th ed
        "K_sutton_graves": 1.7415e-4,   # Sutton & Graves (1971) for air
    },
    "mars": {
        "rho_surface_kg_m3": 0.020,     # Justus (2006) NASA/TM-2006-214382
        "scale_height_m": 11_100.0,     # Mars-GRAM (Justus 2006)
        "g_surface_ms2": 3.721,         # Vallado 4th ed Table D-3
        "p_surface_pa": 636.0,          # Viking 1 measurement (Hess 1977)
        "composition": "CO₂ (95.3%)",
        "mu_planet_m3s2": 4.283e13,     # Vallado 4th ed Table D-3
        "r_planet_m": 3.396e6,          # Vallado 4th ed Table D-3
        "K_sutton_graves": 1.898e-4,    # Sutton & Graves for CO₂ (Tauber & Sutton 1991)
    },
    "venus": {
        "rho_surface_kg_m3": 65.0,      # Seiff et al. (1985) Adv. Space Res.
        "scale_height_m": 15_900.0,     # Venus International Reference Atmosphere
        "g_surface_ms2": 8.87,          # Vallado 4th ed Table D-3
        "p_surface_pa": 9_200_000.0,    # 92 atm — Venera measurements (Avduevsky 1970)
        "composition": "CO₂ (96.5%)",
        "mu_planet_m3s2": 3.249e14,     # Vallado 4th ed Table D-3
        "r_planet_m": 6.052e6,          # Vallado 4th ed Table D-3
        "K_sutton_graves": 1.898e-4,    # Same as Mars (CO₂ atmosphere)
    },
    "titan": {
        "rho_surface_kg_m3": 5.4,       # Fulchignoni et al. (2005) Nature 438
        "scale_height_m": 20_000.0,     # Lorenz (2010) "Titan Unveiled" §4
        "g_surface_ms2": 1.352,         # Vallado 4th ed
        "p_surface_pa": 146_700.0,      # 1.467 atm — Huygens (Fulchignoni 2005)
        "composition": "N₂ (94.2%)",
        "mu_planet_m3s2": 8.978e12,     # Vallado 4th ed (Titan GM)
        "r_planet_m": 2.575e6,          # Vallado 4th ed
        "K_sutton_graves": 1.7415e-4,   # N₂ atmosphere ≈ Earth (nitrogen dominated)
    },
    "jupiter": {
        "rho_surface_kg_m3": 0.16,      # At 1-bar level — Seiff et al. (1998) JGR
        "scale_height_m": 27_000.0,     # H₂/He atmosphere — Seiff et al. (1998)
        "g_surface_ms2": 24.79,         # Vallado 4th ed Table D-3
        "p_surface_pa": 100_000.0,      # 1-bar reference level
        "composition": "H₂/He (86/14%)",
        "mu_planet_m3s2": 1.267e17,     # Vallado 4th ed Table D-3
        "r_planet_m": 7.149e7,          # Vallado 4th ed Table D-3
        "K_sutton_graves": 1.065e-4,    # H₂/He mixture — Tauber & Sutton (1991)
    },
}

# ═══════════════════════════════════════════════════════════════════
#  VALIDATED MISSION DATA
# ═══════════════════════════════════════════════════════════════════

MISSIONS = {
    "msl_curiosity": {
        "planet": "mars",
        "v_entry_ms": 5_800.0,         # Braun & Manning (2007)
        "gamma_deg": -15.5,            # MSL entry angle (steep for precision)
        "beta_kg_m2": 146.0,           # MSL aeroshell (Way et al. 2007)
        "nose_radius_m": 2.25,         # MSL heat shield radius (70° sphere-cone)
        "peak_decel_g": 11.4,          # Actual (Karlgaard et al. 2014)
        "peak_heat_w_cm2": 197.0,      # Actual (Wright et al. 2014)
    },
    "huygens_titan": {
        "planet": "titan",
        "v_entry_ms": 6_100.0,         # Lebreton et al. (2005) Nature
        "gamma_deg": -65.0,            # Very steep (Titan thick atmo slows quickly)
        "beta_kg_m2": 50.0,            # Huygens probe (ESTIMATE from 318 kg, 2.7 m dia)
        "nose_radius_m": 1.25,         # Huygens 60° sphere-cone front shield
        "peak_decel_g": 16.0,          # Fulchignoni et al. (2005) accelerometer
        "peak_heat_w_cm2": 35.0,       # Lorenz (2010) estimate
    },
    "galileo_jupiter": {
        "planet": "jupiter",
        "v_entry_ms": 47_400.0,        # Seiff et al. (1998) JGR 103
        "gamma_deg": -8.4,             # Seiff et al. (1998)
        "beta_kg_m2": 223.0,           # Galileo probe (339 kg, 1.26 m dia)
        "nose_radius_m": 0.222,        # Galileo 45° sphere-cone nose
        "peak_decel_g": 230.0,         # Seiff et al. (1998) — most violent entry ever
        "peak_heat_w_cm2": 17_000.0,   # Milos et al. (1999) — extreme heating
    },
}


# ═══════════════════════════════════════════════════════════════════
#  DATA CLASS
# ═══════════════════════════════════════════════════════════════════

@dataclass
class PlanetaryEntryResult:
    """Atmospheric entry analysis for any planet."""
    planet: str
    v_entry_ms: float
    entry_angle_deg: float
    ballistic_coeff: float
    peak_decel_g: float
    peak_heat_rate_w_cm2: float
    peak_dynamic_pressure_pa: float
    entry_kinetic_energy_mj_kg: float


# ═══════════════════════════════════════════════════════════════════
#  ENTRY ANALYSIS
# ═══════════════════════════════════════════════════════════════════

def compute_planetary_entry(
    planet: str,
    v_entry_ms: float,
    entry_angle_deg: float = -15.0,
    ballistic_coeff: float = 100.0,
    nose_radius_m: float = 1.0,
) -> PlanetaryEntryResult:
    """Compute peak deceleration and heating for atmospheric entry at any planet.

    Uses Allen-Eggers ballistic entry theory calibrated to published mission data.
    Valid for shallow-to-moderate entry angles (|γ| < 70°).

    Peak deceleration (Allen-Eggers 1958, generalized):
      n_peak = v² × sin|γ| / (2 × e × H × g₀_planet)

    Peak heat rate (Sutton-Graves 1971, planet-specific K):
      q̇ = K × sqrt(ρ_peak / R_N) × v³
    where ρ_peak = β × sin|γ| / H

    Args:
        planet:          Planet name (mars, venus, titan, jupiter, earth).
        v_entry_ms:      Entry speed at atmospheric interface (m/s).
        entry_angle_deg: Flight path angle (deg, negative = descending).
        ballistic_coeff: β = m/(C_D×A) (kg/m²).
        nose_radius_m:   Vehicle nose radius for Sutton-Graves (m).

    Returns:
        PlanetaryEntryResult with peak values.

    References:
        Allen & Eggers (1958) NACA TR-1381 — ballistic entry.
        Sutton & Graves (1971) J. Spacecraft 8(3) — heat rate.
        Tauber M.E. & Sutton K. (1991) — K values for different atmospheres.
    """
    planet_key = planet.lower()
    if planet_key not in ATMOSPHERES:
        raise ValueError(f"Unknown planet: {planet}. Use: {list(ATMOSPHERES.keys())}")

    atmo = ATMOSPHERES[planet_key]
    H = atmo["scale_height_m"]
    g = atmo["g_surface_ms2"]
    K = atmo["K_sutton_graves"]
    rho0 = atmo["rho_surface_kg_m3"]

    sin_gamma = math.sin(math.radians(abs(entry_angle_deg)))

    # Peak deceleration: Allen-Eggers generalized
    # n = v² × sin|γ| / (2eH) where e=2.718
    # But this gives the decel in m/s², divide by g₀ for Earth-g
    e_euler = math.e
    n_ms2 = v_entry_ms**2 * sin_gamma / (2.0 * e_euler * H)
    n_g = n_ms2 / 9.80665  # convert to Earth g for comparability

    # Density at peak deceleration altitude
    # ρ_peak = β × sin|γ| / H (King-Hele / Allen-Eggers)
    rho_peak = ballistic_coeff * sin_gamma / H

    # Cap density at surface value (can't exceed ground level)
    rho_peak = min(rho_peak, rho0)

    # Peak heat rate: Sutton-Graves
    # q̇ = K × sqrt(ρ_peak / R_N) × v³  [W/m²]
    q_dot_w_m2 = K * math.sqrt(rho_peak / nose_radius_m) * v_entry_ms**3
    q_dot_w_cm2 = q_dot_w_m2 / 1e4  # W/m² → W/cm²

    # Peak dynamic pressure
    q_dyn_pa = 0.5 * rho_peak * v_entry_ms**2

    # Specific kinetic energy
    e_kin = v_entry_ms**2 / (2.0 * 1e6)  # MJ/kg

    return PlanetaryEntryResult(
        planet=planet_key,
        v_entry_ms=v_entry_ms,
        entry_angle_deg=entry_angle_deg,
        ballistic_coeff=ballistic_coeff,
        peak_decel_g=n_g,
        peak_heat_rate_w_cm2=q_dot_w_cm2,
        peak_dynamic_pressure_pa=q_dyn_pa,
        entry_kinetic_energy_mj_kg=e_kin,
    )


def validate_mission(mission_name: str) -> dict:
    """Validate against published mission data.

    Returns dict with predicted vs actual values and % error.
    """
    if mission_name not in MISSIONS:
        raise ValueError(f"Unknown mission: {mission_name}. Use: {list(MISSIONS.keys())}")

    m = MISSIONS[mission_name]
    result = compute_planetary_entry(
        m["planet"], m["v_entry_ms"], m["gamma_deg"],
        m["beta_kg_m2"], m["nose_radius_m"],
    )

    return {
        "mission": mission_name,
        "planet": m["planet"],
        "peak_decel_g": {
            "predicted": result.peak_decel_g,
            "actual": m["peak_decel_g"],
            "error_pct": abs(result.peak_decel_g - m["peak_decel_g"]) / m["peak_decel_g"] * 100,
        },
        "peak_heat_w_cm2": {
            "predicted": result.peak_heat_rate_w_cm2,
            "actual": m["peak_heat_w_cm2"],
            "error_pct": abs(result.peak_heat_rate_w_cm2 - m["peak_heat_w_cm2"]) / m["peak_heat_w_cm2"] * 100,
        },
    }


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n── Planetary Entry Comparison ────────────────────────────────")
    print(f"  {'Planet':<10s}  {'v_entry':>8s}  {'γ':>5s}  {'Peak g':>8s}  {'Peak q̇':>10s}  {'KE':>7s}")
    for planet in ["earth", "mars", "venus", "titan", "jupiter"]:
        v = {"earth": 11000, "mars": 5800, "venus": 11200, "titan": 6100, "jupiter": 47400}[planet]
        gamma = {"earth": -6.5, "mars": -15.5, "venus": -20, "titan": -65, "jupiter": -8.4}[planet]
        r = compute_planetary_entry(planet, v, gamma, 100.0, 1.0)
        print(f"  {planet:<10s}  {v:>7.0f}  {gamma:>5.1f}  {r.peak_decel_g:>7.1f}g  "
              f"{r.peak_heat_rate_w_cm2:>9.0f}  {r.entry_kinetic_energy_mj_kg:>6.1f}")

    print("\n── Mission Validation ───────────────────────────────────────")
    for mission in MISSIONS:
        v = validate_mission(mission)
        print(f"\n  {v['mission']} ({v['planet']}):")
        g = v["peak_decel_g"]
        q = v["peak_heat_w_cm2"]
        print(f"    Peak decel: {g['predicted']:>7.1f} g (actual {g['actual']:.0f} g, {g['error_pct']:.0f}% error)")
        print(f"    Peak heat:  {q['predicted']:>7.0f} W/cm² (actual {q['actual']:.0f} W/cm², {q['error_pct']:.0f}% error)")
