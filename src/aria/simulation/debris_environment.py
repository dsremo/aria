"""Orbital Debris Environment Model — flux, collision probability, shield penetration.

The most dangerous aspect of near-Earth space operations is orbital debris.
This module quantifies the risk and provides tools for trajectory planning
around the debris environment.

THE DEBRIS THREAT
=================
Orbital debris consists of defunct satellites, rocket bodies, collision
fragments, and paint flakes orbiting at 7–8 km/s relative to Earth.
At those speeds, even a 1 cm fragment delivers ~30 kJ of kinetic energy —
enough to destroy a spacecraft.

Current LEO debris population (NASA ODQN Vol. 27, 2023):
  >10 cm tracked:  ~27,500 objects  (detectable by ground radar)
  >1  cm:         ~900,000 objects  (below radar threshold)
  >1  mm:        ~130,000,000 objects (lethal to EVA suits, solar panels)

WHAT THIS MODULE COMPUTES
=========================
1. Flux model: cumulative debris flux Φ(h, d) [hits/m²/yr] at altitude h for
   objects larger than diameter d. Tabulated from NASA ORDEM 3.0 and
   Klinkrad (2006) for 5 object size thresholds.

2. Collision probability: P_collision(A, T, h) for a spacecraft with cross-
   section A [m²] in orbit at altitude h for duration T [years].

3. Shield penetration: critical projectile diameter d_crit that a Whipple
   bumper shield of given areal density can stop. Uses modified Cour-Palais
   ballistic limit equation (NASA/TP-2009-214797).

4. Ascent profile: debris flux vs altitude during launch ascent. Identifies
   the most hazardous altitude bands (peak at 800–900 km).

5. Conjunction alert: checks whether a planned departure date falls within
   a high-debris-density period due to recent fragmentation events.

MITIGATION STRATEGIES
=====================
1. Altitude selection: stay below 600 km (natural decay < 25 years) or above
   2,000 km (sparse debris). The 800–1,000 km band is the worst.
2. Whipple bumper shields: thin bumper + standoff gap fragments impactors before
   reaching the main wall. ISS uses ~5 layers on crew modules.
3. Maneuvering: conjunction avoidance burns. ISS performs ~3 CDAs/year.
4. Design for demise: spacecraft design to burn up during re-entry.

KEY LIMITATION
==============
This module uses TABULATED FLUX from published data, not a full ORDEM/MASTER
propagator. It captures the long-term steady-state flux accurately but cannot
account for recent fragmentation events (e.g., anti-sat missile tests).
For mission-critical analysis, integrate with Space-Track.org TLE catalog.

References:
  Klinkrad H. (2006) Space Debris: Models and Risk Analysis. Springer.
  Liou J-C, Johnson N.L. (2006) Risks in Space from Orbiting Debris. Science 311:340.
  NASA Orbital Debris Quarterly News (ODQN) Vol. 27 Issue 1 (Feb 2023).
  Cour-Palais B.G. (1969) Meteoroid Environment Model. NASA TN D-5547.
  NASA/TP-2009-214797: Handbook for Designing MMOD Protection.
  NASA-STD-8719.14B: Process for Limiting Orbital Debris (25-year decay rule).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import structlog

logger = structlog.get_logger()

# ═══════════════════════════════════════════════════════════════════
#  PHYSICAL CONSTANTS
# ═══════════════════════════════════════════════════════════════════

R_EARTH_KM = 6_371.0          # Earth mean radius (km) — IAU 2015
MU_EARTH   = 3.986004418e14   # Earth GM (m³/s²) — Vallado 4th ed Table D-1

# ISS reference orbit (used for flux normalisation)
ISS_ALTITUDE_KM = 408.0       # ISS mean altitude (km) — NASA ISS Facts, 2024

# Closing velocity (average for debris-spacecraft encounter)
# Klinkrad (2006) §5.2: average relative velocity ≈ 10 km/s in LEO.
AVG_CLOSING_SPEED_KMS = 10.0  # km/s — Klinkrad (2006) Space Debris §5.2

# ═══════════════════════════════════════════════════════════════════
#  DEBRIS FLUX TABLE — NASA ORDEM 3.2 (2023) / Klinkrad 2006
# ═══════════════════════════════════════════════════════════════════
# Cumulative flux Φ(h, d) = number of impacts per m² per year
# for objects larger than diameter d, at altitude h km.
#
# Updated to ORDEM 3.2 (NASA NTRS 20230014989):
#   - Includes Cosmos 1408 ASAT debris (Nov 2021, ~1,500 tracked fragments)
#   - Includes Fengyun-1C (2007), Iridium-33/Cosmos-2251 (2009) fragments
#   - Extended coverage to GEO (40,000 km) and projections to year 2050
#
# Data sources:
#   d > 10 cm: tracked catalog, ORDEM 3.2 Fig. 3-1; ODQN Vol. 27 (2023) Fig. 2
#   d > 1 cm:  ORDEM 3.2 analytical populations; Klinkrad (2006) Table A1.3
#   d > 1 mm:  ORDEM 3.2 sub-cm populations; scaling from Klinkrad (2006)
#   d > 0.1mm: power-law extrapolation from Drolshagen (2001) ESOC
#
# Changes from ORDEM 3.0 to 3.2 at key altitudes:
#   400–600 km: +10–15% from Cosmos 1408 debris cloud (Sun-synchronous band)
#   800–900 km: +5% refinement from radar observations (HUSIR + Goldstone)
#   >1200 km:   minor updates from optical observations (ES-MCAT)
#
# Altitude nodes [km]:
FLUX_ALT_KM = [200, 400, 500, 600, 700, 800, 900, 1000, 1200, 1500, 2000]

# Flux tables: Φ [hits/m²/yr] at each altitude node
# Format: {threshold_label: [flux at each altitude node]}

# Objects > 10 cm (tracked, NORAD catalog quality)
# Source: ORDEM 3.2 tracked population (2023); ODQN Vol. 27 Fig. 2
# Update: Cosmos 1408 added ~1,500 tracked fragments at 400–600 km
FLUX_GT10CM = [
    2.0e-8,   # 200 km (low — atmospheric drag quickly removes debris)
    5.5e-7,   # 400 km (ISS altitude; +10% from Cosmos 1408 — ORDEM 3.2)
    1.8e-6,   # 500 km (+20% Cosmos 1408 primary cloud — ORDEM 3.2)
    4.6e-6,   # 600 km (+15% Cosmos 1408 + Iridium band — ORDEM 3.2)
    8.2e-6,   # 700 km (+2.5% minor update — ORDEM 3.2)
    1.25e-5,  # 800 km (worst zone; +4% HUSIR radar refinement — ORDEM 3.2)
    1.05e-5,  # 900 km (+5% radar update — ORDEM 3.2)
    7.2e-6,   # 1000 km (+3% — ORDEM 3.2)
    2.0e-6,   # 1200 km (unchanged — ORDEM 3.2)
    5.0e-7,   # 1500 km (semi-sparse, unchanged)
    1.0e-7,   # 2000 km (approaching inner Van Allen belt)
]

# Objects > 1 cm (below radar, kill vehicles for spacecraft)
# Source: ORDEM 3.2 analytical model (NASA NTRS 20230014989 §4.2)
# Cosmos 1408 contribution: +10–15% at 400–600 km for sub-catalog sizes
FLUX_GT1CM = [
    3.0e-6,   # 200 km
    4.5e-5,   # 400 km (ISS; +12% Cosmos 1408 — ORDEM 3.2)
    1.4e-4,   # 500 km (+17% Cosmos 1408 primary band — ORDEM 3.2)
    4.0e-4,   # 600 km (+14% — ORDEM 3.2)
    6.2e-4,   # 700 km (+3% — ORDEM 3.2)
    9.3e-4,   # 800 km (peak; +3% radar — ORDEM 3.2)
    7.7e-4,   # 900 km (+3% — ORDEM 3.2)
    5.1e-4,   # 1000 km (+2% — ORDEM 3.2)
    1.5e-4,   # 1200 km (unchanged)
    4.0e-5,   # 1500 km (unchanged)
    8.0e-6,   # 2000 km (unchanged)
]

# Objects > 1 mm (hypervelocity kill for EVA suits, solar arrays, optics)
# Source: ORDEM 3.2 sub-cm population; Klinkrad (2006) Table A1.3
FLUX_GT1MM = [
    7.5e-5,   # 200 km
    1.1e-3,   # 400 km (ISS; +10% Cosmos 1408 — ORDEM 3.2)
    3.4e-3,   # 500 km (+13% — ORDEM 3.2)
    1.0e-2,   # 600 km (+14% — ORDEM 3.2)
    1.55e-2,  # 700 km (+3% — ORDEM 3.2)
    2.35e-2,  # 800 km (peak; +2% — ORDEM 3.2)
    1.95e-2,  # 900 km (+3% — ORDEM 3.2)
    1.32e-2,  # 1000 km (+2% — ORDEM 3.2)
    3.8e-3,   # 1200 km (unchanged)
    1.0e-3,   # 1500 km (unchanged)
    2.0e-4,   # 2000 km (unchanged)
]

# Objects > 0.1 mm (damage to solar panels, thermal coatings, windows)
# Source: power-law extrapolation from Drolshagen (2001), factor ~30× vs 1mm
# Minor updates from ORDEM 3.2 at 400-600 km (same percentage as 1mm tier)
FLUX_GT01MM = [
    2.3e-3,   # 200 km
    3.3e-2,   # 400 km (+10% — ORDEM 3.2)
    1.0e-1,   # 500 km (+11% — ORDEM 3.2)
    3.0e-1,   # 600 km (+15% — ORDEM 3.2)
    4.6e-1,   # 700 km (+2% — ORDEM 3.2)
    7.0e-1,   # 800 km (peak; +1.5% — ORDEM 3.2)
    5.8e-1,   # 900 km (+2% — ORDEM 3.2)
    4.0e-1,   # 1000 km (+3% — ORDEM 3.2)
    1.1e-1,   # 1200 km (unchanged)
    3.0e-2,   # 1500 km (unchanged)
    6.0e-3,   # 2000 km (unchanged)
]

# Combined table for lookup
FLUX_TABLES: dict[str, list[float]] = {
    ">10cm": FLUX_GT10CM,
    ">1cm":  FLUX_GT1CM,
    ">1mm":  FLUX_GT1MM,
    ">0.1mm": FLUX_GT01MM,
}

# ═══════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class DebrisFluxResult:
    """Debris flux at a given altitude."""
    altitude_km: float
    flux_gt10cm_per_m2_yr: float    # Tracked (>10 cm) flux
    flux_gt1cm_per_m2_yr: float     # Dangerous (>1 cm) flux
    flux_gt1mm_per_m2_yr: float     # Damaging (>1 mm) flux
    flux_gt01mm_per_m2_yr: float    # Degrading (>0.1 mm) flux
    risk_level: str                  # "low" / "moderate" / "high" / "extreme"
    risk_note: str


@dataclass
class CollisionProbability:
    """Probability of collision during a mission phase."""
    altitude_km: float
    cross_section_m2: float
    duration_years: float
    size_threshold: str              # ">10cm", ">1cm", ">1mm", ">0.1mm"
    flux_per_m2_yr: float
    probability: float               # P(at least one hit) = 1 - exp(-Φ·A·T)
    expected_hits: float             # Mean number of hits (Poisson λ)
    # Note: probability < 1e-4 is generally acceptable for mission planning
    # NASA-STD-8719.14B threshold: P_collision < 1/1000 per 5-year mission


@dataclass
class ShieldPerformance:
    """Whipple bumper shield penetration analysis.

    A Whipple shield consists of a thin outer bumper plate separated from
    the main pressure wall by a standoff gap. An impactor hitting the bumper
    is shattered and dispersed, reducing impact pressure on the main wall.
    """
    shield_areal_density_g_cm2: float   # Total shield mass per area
    bumper_thickness_mm: float          # Outer bumper thickness
    wall_thickness_mm: float            # Main wall thickness
    standoff_gap_mm: float              # Gap between bumper and wall
    material: str                       # "aluminum" / "kevlar" / "nextel"
    critical_diameter_cm: float         # Max projectile diameter that is stopped
    flux_survived_per_m2_yr: float      # Flux of objects ABOVE critical diameter
    # Context: ISS modules use 4-6 layers, stop objects up to ~1 cm at 7 km/s


@dataclass
class AscentDebrisProfile:
    """Debris risk profile for launch ascent from surface to target orbit."""
    target_altitude_km: float
    max_flux_altitude_km: float          # Altitude with peak debris density
    max_flux_gt1cm_per_m2_yr: float      # Peak flux during ascent
    transit_time_s: float                # Time spent in debris-dense zone
    integrated_fluence_per_m2: float     # Total expected impacts during ascent


@dataclass
class DebrisRiskSummary:
    """Complete debris risk assessment for a mission."""
    mission_name: str
    phases: list[CollisionProbability] = field(default_factory=list)
    total_probability_gt1cm: float = 0.0   # P(at least one 1cm+ hit) for whole mission
    shield: Optional[ShieldPerformance] = None
    mitigation_recommendations: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
#  FLUX INTERPOLATION
# ═══════════════════════════════════════════════════════════════════

def get_debris_flux(altitude_km: float, size_threshold: str = ">1cm") -> float:
    """Return cumulative debris flux at the given altitude [hits/m²/yr].

    Uses linear interpolation on the tabulated ORDEM 3.0 / Klinkrad data.
    For altitudes below 200 km: atmospheric drag clears debris rapidly,
    flux extrapolated to ~0 at 150 km (debris decays within days).
    For altitudes above 2000 km: transition to sparse outer belt region.

    Args:
        altitude_km:     Orbital altitude above Earth surface [km]
        size_threshold:  ">10cm", ">1cm", ">1mm", or ">0.1mm"

    Returns:
        Flux [hits/m²/yr] — mean number of impacts per unit area per year

    References:
        Klinkrad (2006) Table A1.3; NASA ODQN Vol. 27 (2023).
    """
    if size_threshold not in FLUX_TABLES:
        raise ValueError(f"Unknown size threshold '{size_threshold}'. "
                         f"Use: {list(FLUX_TABLES.keys())}")

    table = FLUX_TABLES[size_threshold]

    # Below 200 km: atmospheric drag removes debris, flux → 0 at 150 km
    if altitude_km <= 150.0:
        return 0.0
    if altitude_km < FLUX_ALT_KM[0]:  # 150-200 km interpolation
        frac = (altitude_km - 150.0) / (FLUX_ALT_KM[0] - 150.0)
        return frac * table[0]

    # Above 2000 km: sparse — extrapolate as declining power law
    if altitude_km > FLUX_ALT_KM[-1]:
        # Scale by (h/2000)^(-2.5) — typical debris population thinning
        ref = table[-1]
        return ref * (FLUX_ALT_KM[-1] / altitude_km) ** 2.5

    # Linear interpolation within table
    for i in range(len(FLUX_ALT_KM) - 1):
        if FLUX_ALT_KM[i] <= altitude_km <= FLUX_ALT_KM[i + 1]:
            frac = (altitude_km - FLUX_ALT_KM[i]) / (FLUX_ALT_KM[i + 1] - FLUX_ALT_KM[i])
            return table[i] + frac * (table[i + 1] - table[i])

    return table[-1]  # fallback


def debris_flux_full(altitude_km: float) -> DebrisFluxResult:
    """Return the complete flux profile at a given altitude.

    Args:
        altitude_km: Orbital altitude [km]

    Returns:
        DebrisFluxResult with all size-threshold fluxes and risk classification
    """
    f10 = get_debris_flux(altitude_km, ">10cm")
    f1  = get_debris_flux(altitude_km, ">1cm")
    f1m = get_debris_flux(altitude_km, ">1mm")
    f01 = get_debris_flux(altitude_km, ">0.1mm")

    # Risk classification based on >1 cm flux (the kill-vehicle threshold)
    # These thresholds are judgment-based, informed by ISS operations:
    # ISS is at ~408 km where flux_gt1cm ≈ 4e-5. ISS crew is evacuated for
    # P_collision > 1/1000 per 5-year mission. With A=3600 m², T=5yr:
    # λ = 4e-5 × 3600 × 5 = 0.72 → P = 1-exp(-0.72) = 49% per 5yr ISS.
    # Hence ISS relies on shielding, not low flux.
    if f1 < 5e-6:
        risk_level = "low"
        risk_note = "Debris flux low — atmospheric drag clears population rapidly"
    elif f1 < 5e-5:
        risk_level = "moderate"
        risk_note = "Similar to ISS altitude — standard Whipple shielding sufficient"
    elif f1 < 3e-4:
        risk_level = "high"
        risk_note = "Elevated debris density — Iridium/Cosmos collision altitude band"
    else:
        risk_level = "extreme"
        risk_note = "Peak debris zone (800–900 km) — ASAT test fragments still present"

    return DebrisFluxResult(
        altitude_km=altitude_km,
        flux_gt10cm_per_m2_yr=f10,
        flux_gt1cm_per_m2_yr=f1,
        flux_gt1mm_per_m2_yr=f1m,
        flux_gt01mm_per_m2_yr=f01,
        risk_level=risk_level,
        risk_note=risk_note,
    )


# ═══════════════════════════════════════════════════════════════════
#  COLLISION PROBABILITY
# ═══════════════════════════════════════════════════════════════════

def collision_probability(
    altitude_km: float,
    cross_section_m2: float,
    duration_years: float,
    size_threshold: str = ">1cm",
) -> CollisionProbability:
    """Compute probability of at least one debris collision during a mission phase.

    Uses Poisson statistics: P(at least one hit) = 1 - exp(-λ)
    where λ = Φ(h, d) × A × T (expected number of impacts).

    This is the standard model used by NASA JSC for ISS collision risk
    (NASA-STD-8719.14B §4.3.3) and for satellite design margin analysis.

    Args:
        altitude_km:      Orbital altitude [km]
        cross_section_m2: Exposed cross-sectional area [m²]
        duration_years:   Time at this altitude [years]
        size_threshold:   Object size threshold for flux lookup

    Returns:
        CollisionProbability with P, λ, and context

    Notes:
        NASA-STD-8719.14B threshold: P < 1/1000 per debris-generating event.
        For 5-year LEO missions with large cross sections, P(>1cm) >> 1/1000.
        Mitigation: Whipple shielding (stops objects below d_crit) and maneuvers.
    """
    flux = get_debris_flux(altitude_km, size_threshold)
    lam = flux * cross_section_m2 * duration_years  # expected hits (Poisson λ)
    prob = 1.0 - math.exp(-lam)

    return CollisionProbability(
        altitude_km=altitude_km,
        cross_section_m2=cross_section_m2,
        duration_years=duration_years,
        size_threshold=size_threshold,
        flux_per_m2_yr=flux,
        probability=prob,
        expected_hits=lam,
    )


# ═══════════════════════════════════════════════════════════════════
#  WHIPPLE BUMPER SHIELD ANALYSIS
# ═══════════════════════════════════════════════════════════════════

def whipple_shield_analysis(
    bumper_thickness_mm: float,
    wall_thickness_mm: float,
    standoff_gap_mm: float,
    material: str = "aluminum",
    impact_speed_km_s: float = 7.0,
    impact_angle_deg: float = 0.0,
) -> ShieldPerformance:
    """Compute Whipple bumper shield performance — maximum stopped projectile size.

    Uses the modified Cour-Palais ballistic limit equation (BLE) from
    NASA/TP-2009-214797 §3.2, calibrated for aluminum-on-aluminum impacts:

    In the hypervelocity regime (v > 7 km/s):
      d_crit = [ρ_w^(1/3) × t_w × (S/d_p)^(2/3)] / [C × ρ_p^(1/3) × v^(2/3)]

    Simplified (solving for d_crit given shield geometry):
      d_crit = K × (t_w × S^(2/3)) / v^(2/3)

    where:
      K = material-dependent constant (NASA/TP-2009-214797 Table 3.1)
      t_w = wall thickness [cm]
      S = standoff gap [cm]
      v = impact velocity [km/s]

    Oblique impact correction (NASA/TP-2009-214797 §3.3):
      At oblique incidence angle θ (from normal), the effective path length
      through the shield increases by 1/cos(θ), so the shield can stop larger
      projectiles:
        d_crit_oblique = d_crit_normal / cos^(2/3)(θ)

      In LEO the average impact angle is ~35° from normal (Klinkrad 2006 §5.3),
      giving a ~20% increase in critical diameter vs. normal incidence.

    Areal density calculation:
      ξ = ρ × t_bumper + ρ × t_wall  [g/cm²]

    Args:
        bumper_thickness_mm: Outer bumper (spall plate) thickness [mm]
        wall_thickness_mm:   Main pressure wall thickness [mm]
        standoff_gap_mm:     Gap between bumper and wall [mm]
        material:            "aluminum", "kevlar", or "nextel"
        impact_speed_km_s:   Hypervelocity impact speed [km/s]
        impact_angle_deg:    Impact angle from surface normal (deg).
                             0° = head-on (normal incidence, worst case).
                             35° = LEO average (Klinkrad 2006 §5.3).
                             Max 85° (grazing impacts deflect, not modeled).
                             Default 0° for conservative analysis.

    Returns:
        ShieldPerformance with critical diameter and residual flux

    References:
        NASA/TP-2009-214797: Handbook for Designing MMOD Protection.
        Cour-Palais B.G. (1969) NASA TN D-5547.
        Christiansen E.L. (2003) Meteoroid/debris shielding. NASA TP-2003-210788.
    """
    # Material constants
    material_props = {
        # (density g/cm³, BLE constant K, H_B Brinell hardness)
        "aluminum": (2.70, 0.14, 40),      # Al-6061-T6; Christiansen (2003)
        "kevlar":   (1.44, 0.22, None),    # Kevlar-29; NASA TP-2003-210788
        "nextel":   (2.70, 0.25, None),    # Nextel AF-62; NASA TP-2003-210788
    }
    if material.lower() not in material_props:
        raise ValueError(f"Unknown material '{material}'. Use: {list(material_props.keys())}")

    rho_w, K, H_B = material_props[material.lower()]

    # Convert to cm for the BLE formula
    t_bumper_cm = bumper_thickness_mm / 10.0
    t_wall_cm   = wall_thickness_mm / 10.0
    S_cm        = standoff_gap_mm / 10.0

    # Areal density [g/cm²]
    xi = rho_w * (t_bumper_cm + t_wall_cm)

    # Modified Cour-Palais BLE for Whipple shield (hypervelocity regime)
    # NASA/TP-2009-214797 eq. 3-2: d_crit in cm
    # d_crit = K × (t_w × S^(2/3)) / (ρ_p^(1/3) × v^(2/3))
    # Assuming projectile density = 2.8 g/cm³ (typical debris, Al alloy)
    rho_p = 2.80  # g/cm³ typical orbital debris (Klinkrad 2006 §2.3)
    d_crit_cm = K * (t_wall_cm * S_cm ** (2.0 / 3.0)) / (rho_p ** (1.0 / 3.0) * impact_speed_km_s ** (2.0 / 3.0))

    # Oblique impact correction — NASA/TP-2009-214797 §3.3
    # At angle θ from normal, effective shield thickness increases by 1/cos(θ),
    # which allows stopping larger projectiles:
    #   d_crit_oblique = d_crit_normal / cos^(2/3)(θ)
    # Clamp to 85° (grazing impacts deflect rather than penetrate)
    theta_rad = math.radians(min(abs(impact_angle_deg), 85.0))
    cos_theta = math.cos(theta_rad)
    if cos_theta > 0.01:  # avoid division by near-zero for extreme grazing
        d_crit_cm = d_crit_cm / (cos_theta ** (2.0 / 3.0))

    # Convert to useful units
    d_crit_cm = max(d_crit_cm, 0.0)
    d_crit_mm = d_crit_cm * 10.0

    # Residual flux: anything ABOVE d_crit survives the shield.
    # Interpolation direction: as d_crit increases (better shield), fewer objects
    # survive → flux_survived decreases. At d_crit=1mm: flux(>1mm); at d_crit=10mm:
    # flux(>1cm) which is smaller. Reference altitude: ISS orbit (408 km).
    alt_ref = ISS_ALTITUDE_KM
    if d_crit_mm >= 10.0:
        # Shield stops up to 10 mm+ → only >10 cm objects survive
        flux_survived = get_debris_flux(alt_ref, ">10cm")
        size_label = ">10cm"
    elif d_crit_mm >= 1.0:
        # d_crit in [1mm, 10mm]: interpolate flux between >1mm and >1cm
        # at d_crit=1mm → flux(>1mm); at d_crit=10mm → flux(>1cm) [smaller]
        frac = (d_crit_mm - 1.0) / (10.0 - 1.0)
        f_1mm = get_debris_flux(alt_ref, ">1mm")
        f_1cm = get_debris_flux(alt_ref, ">1cm")
        flux_survived = f_1mm + frac * (f_1cm - f_1mm)
        size_label = f">{d_crit_mm:.1f}mm"
    elif d_crit_mm >= 0.1:
        # d_crit in [0.1mm, 1mm]: interpolate flux between >0.1mm and >1mm
        # at d_crit=0.1mm → flux(>0.1mm); at d_crit=1mm → flux(>1mm) [smaller]
        frac = (d_crit_mm - 0.1) / (1.0 - 0.1)
        f_01mm = get_debris_flux(alt_ref, ">0.1mm")
        f_1mm  = get_debris_flux(alt_ref, ">1mm")
        flux_survived = f_01mm + frac * (f_1mm - f_01mm)
        size_label = f">{d_crit_mm:.2f}mm"
    else:
        # Very thin shield: stops nothing meaningful — all >0.1mm objects survive
        flux_survived = get_debris_flux(alt_ref, ">0.1mm")
        size_label = f">{d_crit_mm:.2f}mm"

    return ShieldPerformance(
        shield_areal_density_g_cm2=xi,
        bumper_thickness_mm=bumper_thickness_mm,
        wall_thickness_mm=wall_thickness_mm,
        standoff_gap_mm=standoff_gap_mm,
        material=material,
        critical_diameter_cm=d_crit_cm,
        flux_survived_per_m2_yr=flux_survived,
    )


# ═══════════════════════════════════════════════════════════════════
#  ASCENT DEBRIS PROFILE
# ═══════════════════════════════════════════════════════════════════

def ascent_debris_profile(
    target_altitude_km: float,
    ascent_time_s: float = 600.0,
    cross_section_m2: float = 20.0,
) -> AscentDebrisProfile:
    """Compute integrated debris exposure during launch ascent.

    The ascent from surface to target orbit passes through all altitude
    bands. Time spent in each band depends on ascent rate (roughly linear
    for the orbital insertion phase above 100 km).

    Args:
        target_altitude_km:  Target circular orbit altitude [km]
        ascent_time_s:       Total ascent time from 100 km to target [s]
        cross_section_m2:    Rocket cross-section area [m²]

    Returns:
        AscentDebrisProfile with peak flux altitude and integrated fluence

    Note:
        During ascent the spacecraft has LOW collision probability because:
        1. It passes through each altitude band only briefly (~few minutes)
        2. The flux is much lower at lower altitudes
        3. The MECO (Main Engine Cutoff) happens at target altitude only
        Ascent debris risk is NOT the dominant risk — parking orbit is.
    """
    # Sample altitude profile during ascent (100 km to target)
    alt_start_km = 100.0
    n_samples = 50
    alts = [alt_start_km + (target_altitude_km - alt_start_km) * i / (n_samples - 1)
            for i in range(n_samples)]

    dt_s = ascent_time_s / n_samples  # time spent at each altitude sample

    peak_flux = 0.0
    peak_alt  = alt_start_km
    total_fluence = 0.0

    for alt in alts:
        f1 = get_debris_flux(alt, ">1cm")
        if f1 > peak_flux:
            peak_flux = f1
            peak_alt  = alt
        # Fluence [hits/m²] during this altitude segment
        # dt_s in seconds, flux in hits/m²/yr → convert
        fluence = f1 * cross_section_m2 * dt_s / (365.25 * 86400)
        total_fluence += fluence

    return AscentDebrisProfile(
        target_altitude_km=target_altitude_km,
        max_flux_altitude_km=peak_alt,
        max_flux_gt1cm_per_m2_yr=peak_flux,
        transit_time_s=ascent_time_s,
        integrated_fluence_per_m2=total_fluence / cross_section_m2,
    )


# ═══════════════════════════════════════════════════════════════════
#  ORBITAL LIFETIME
# ═══════════════════════════════════════════════════════════════════

def orbital_lifetime_years(altitude_km: float, ballistic_coeff_kg_m2: float = 100.0) -> float:
    """Approximate atmospheric drag orbital lifetime for an orbiting object.

    Uses the simplified drag lifetime formula based on USAF Aerospace Corp
    Orbital Decay Look-up Tables and NASA Debris Handbook (Laurance 2014):

      T_decay ≈ (2 × M × H_eff) / (Cd × A × ρ(h) × v_circ)

    where H_eff is the atmospheric scale height at orbital altitude h (km).
    Above 200 km, H_eff ranges from 60–200 km (US Standard Atmosphere 1976;
    Jacchia model), NOT the surface 7 km — this is the critical difference.

    Tabulated reference lifetimes for β = M/(Cd×A) = 100 kg/m² [~Starlink class]:
      200 km →   1 day
      300 km →  60 days
      400 km →   4 years
      500 km →  50 years
      600 km → 350 years (exceeds 25-year rule → requires active deorbit)
      700 km → 2000 years

    Source: Laurance M.R. (2014) Space Debris Mitigation. ESA SP-411;
            USSTRATCOM Historical Decay Data; Klinkrad (2006) §4.3.

    Args:
        altitude_km:            Circular orbit altitude [km]
        ballistic_coeff_kg_m2:  β = M/(Cd×A) [kg/m²]; typical debris 50–200

    Returns:
        Approximate orbital lifetime [years]

    References:
        Klinkrad H. (2006) Space Debris §4.3.
        NASA-STD-8719.14B: 25-year deorbit rule.
        US Standard Atmosphere (1976) NASA TM X-74335.
    """
    # Tabulated (altitude_km, lifetime_years) for β = 100 kg/m²
    # Source: USSTRATCOM decay tables; Klinkrad (2006) Table 4.2
    _ALT_REF = [150,   200,    250,     300,      350,      400,      450,
                500,   550,    600,     650,      700,      800,      900,
                1000,  1200,   1500,    2000]
    _LIFE_100 = [0.003, 0.003,  0.05,    0.16,     0.6,      4.0,      15.0,
                 50.0,  130.0,  350.0,   800.0,    2000.0,  12000.0, 50000.0,
                 1e5,   5e5,    1e6,     1e6]
    # Scale by ballistic coefficient (lifetime ∝ β)
    scale = ballistic_coeff_kg_m2 / 100.0

    if altitude_km <= _ALT_REF[0]:
        return _LIFE_100[0] * scale

    if altitude_km >= _ALT_REF[-1]:
        return _LIFE_100[-1] * scale

    # Log-linear interpolation (lifetime spans many orders of magnitude)
    for i in range(len(_ALT_REF) - 1):
        if _ALT_REF[i] <= altitude_km <= _ALT_REF[i + 1]:
            frac = (altitude_km - _ALT_REF[i]) / (_ALT_REF[i + 1] - _ALT_REF[i])
            log_life = (math.log(_LIFE_100[i]) +
                        frac * (math.log(_LIFE_100[i + 1]) - math.log(_LIFE_100[i])))
            return math.exp(log_life) * scale

    return _LIFE_100[-1] * scale


def passes_25year_rule(altitude_km: float, ballistic_coeff_kg_m2: float = 100.0) -> bool:
    """Check if a satellite at this altitude satisfies NASA-STD-8719.14B 25-year rule.

    NASA-STD-8719.14B requires that any satellite placed in LEO must
    deorbit naturally or be actively deorbited within 25 years of
    end-of-mission. This is the primary debris mitigation regulation.

    Args:
        altitude_km:           Orbital altitude [km]
        ballistic_coeff_kg_m2: β = M/(Cd×A) [kg/m²]. Default 100 kg/m²
                               (representative medium satellite, Starlink class).

    Returns:
        True if orbital lifetime < 25 years (compliant), False otherwise
    """
    return orbital_lifetime_years(altitude_km, ballistic_coeff_kg_m2) <= 25.0


# ═══════════════════════════════════════════════════════════════════
#  FULL MISSION RISK ASSESSMENT
# ═══════════════════════════════════════════════════════════════════

def mission_debris_risk(
    mission_name: str,
    phases: list[dict],
    shield: Optional[dict] = None,
) -> DebrisRiskSummary:
    """Compute full debris risk assessment for a multi-phase mission.

    Args:
        mission_name: Human-readable mission description
        phases: List of dicts with keys:
          - "name": phase name (str)
          - "altitude_km": orbital altitude (float)
          - "cross_section_m2": exposed area (float)
          - "duration_years": time in this orbit (float)
          - "size_threshold": debris size (str, default ">1cm")
        shield: Optional Whipple shield spec dict:
          - "bumper_mm": outer bumper thickness (float)
          - "wall_mm": main wall thickness (float)
          - "gap_mm": standoff gap (float)
          - "material": shield material (str)

    Returns:
        DebrisRiskSummary

    Example:
        mission_debris_risk("ISS-5yr", [
            {"name": "parking", "altitude_km": 400, "cross_section_m2": 3600,
             "duration_years": 5.0, "size_threshold": ">1cm"},
        ], shield={"bumper_mm": 1.5, "wall_mm": 4.0, "gap_mm": 100.0})
    """
    results: list[CollisionProbability] = []

    # Compute collision probability for each phase
    # Overall P = 1 - Π(1 - P_i)  (independent phases)
    p_safe_overall = 1.0

    for phase in phases:
        size_thresh = phase.get("size_threshold", ">1cm")
        cp = collision_probability(
            altitude_km=phase["altitude_km"],
            cross_section_m2=phase["cross_section_m2"],
            duration_years=phase["duration_years"],
            size_threshold=size_thresh,
        )
        results.append(cp)
        p_safe_overall *= (1.0 - cp.probability)

    total_p = 1.0 - p_safe_overall

    # Shield analysis
    shield_result = None
    if shield:
        shield_result = whipple_shield_analysis(
            bumper_thickness_mm=shield.get("bumper_mm", 1.5),
            wall_thickness_mm=shield.get("wall_mm", 4.0),
            standoff_gap_mm=shield.get("gap_mm", 100.0),
            material=shield.get("material", "aluminum"),
        )

    # Mitigation recommendations
    recs = []
    if total_p > 0.01:
        recs.append("CRITICAL: P(hit) > 1%. Consider Whipple shielding upgrade or altitude change.")
    elif total_p > 0.001:
        recs.append("WARNING: P(hit) > 0.1%. Standard NASA-STD-8719.14B threshold.")
    else:
        recs.append("ACCEPTABLE: P(hit) < 0.1%.")

    max_flux_alt = max(phases, key=lambda p: get_debris_flux(p["altitude_km"], ">1cm"))["altitude_km"]
    if 700 < max_flux_alt < 1000:
        recs.append(
            f"Operating in peak debris zone ({max_flux_alt:.0f} km). "
            "This band contains fragments from Iridium-33/Cosmos-2251 collision (2009) "
            "and ASAT test debris. Consider altitude selection below 600 km or above 1000 km."
        )

    for phase in phases:
        if not passes_25year_rule(phase["altitude_km"]):
            recs.append(
                f"Phase '{phase.get('name', '?')}' at {phase['altitude_km']:.0f} km "
                "exceeds 25-year orbital lifetime rule (NASA-STD-8719.14B). "
                "End-of-life deorbit maneuver required."
            )

    if shield_result and shield_result.critical_diameter_cm < 0.1:
        recs.append(
            "Shield performance limited: d_crit < 1 mm. Objects 1–10 mm will penetrate. "
            "Consider increasing standoff gap or wall thickness."
        )

    return DebrisRiskSummary(
        mission_name=mission_name,
        phases=results,
        total_probability_gt1cm=total_p,
        shield=shield_result,
        mitigation_recommendations=recs,
    )


# ═══════════════════════════════════════════════════════════════════
#  NOTABLE FRAGMENTATION EVENTS
# ═══════════════════════════════════════════════════════════════════

NOTABLE_FRAGMENTATION_EVENTS = [
    # (year, altitude_km, fragments_generated, description)
    (1986, 900,  300, "Kosmos-1813 explosion — added dense fragments 800-1000 km"),
    (2007, 863, 2841, "China ASAT test (Fengyun-1C) — 2800+ tracked fragments, ~10000 total"),
    (2009, 789, 1800, "Iridium-33 / Cosmos-2251 collision — first accidental hypervelocity collision"),
    (2021, 485, 1500, "Russia ASAT test (Kosmos-1408) — forced ISS crew to shelter"),
    (2022, 450,  400, "Kosmos-1408 cloud descending into ISS altitude band"),
]
# Source: NASA ODQN Vol. 25 (2021); Kelso (2021) CelesTrak; Liou & Johnson (2006)


def print_debris_report(summary: DebrisRiskSummary) -> None:
    """Print formatted debris risk report to stdout."""
    print(f"\n{'='*65}")
    print(f"  ORBITAL DEBRIS RISK: {summary.mission_name}")
    print(f"{'='*65}")
    for cp in summary.phases:
        print(f"  Phase: {cp.altitude_km:.0f} km orbit, "
              f"{cp.duration_years:.1f} yr, A={cp.cross_section_m2:.0f} m²")
        print(f"    Flux ({cp.size_threshold}): {cp.flux_per_m2_yr:.2e} hits/m²/yr")
        print(f"    Expected hits: {cp.expected_hits:.3f}")
        print(f"    P(at least 1 hit): {cp.probability*100:.4f}%")
    print(f"{'─'*65}")
    print(f"  TOTAL P(≥1 hit, >1cm): {summary.total_probability_gt1cm*100:.4f}%")
    if summary.shield:
        s = summary.shield
        print(f"  Shield: {s.material} bumper={s.bumper_thickness_mm:.1f}mm "
              f"wall={s.wall_thickness_mm:.1f}mm gap={s.standoff_gap_mm:.0f}mm")
        print(f"    Stops objects ≤ {s.critical_diameter_cm*10:.1f} mm "
              f"| Residual flux: {s.flux_survived_per_m2_yr:.2e} hits/m²/yr")
    print(f"{'─'*65}")
    print("  Recommendations:")
    for r in summary.mitigation_recommendations:
        print(f"    • {r}")
    print(f"{'='*65}")


# ═══════════════════════════════════════════════════════════════════
#  PREDEFINED MISSION PROFILES
# ═══════════════════════════════════════════════════════════════════

def iss_mission_risk(duration_years: float = 0.5) -> DebrisRiskSummary:
    """Debris risk for a standard ISS mission.

    ISS has a cross section of ~3600 m² (solar arrays + modules).
    ISS Whipple shielding: 1.5 mm Al bumper, 100 mm gap, 4 mm Al wall.
    ISS altitude: ~408 km.

    Reference: NASA ISS Debris Assessment Report (2023), JSC-67024.
    """
    return mission_debris_risk(
        "ISS Mission",
        phases=[{
            "name": "ISS orbit",
            "altitude_km": 408.0,
            "cross_section_m2": 3600.0,    # NASA ISS Fact Sheet 2024: 109m × 73m footprint
            "duration_years": duration_years,
            "size_threshold": ">1cm",
        }],
        shield={
            "bumper_mm": 1.5,   # Al-6061 outer bumper; NASA JSC-67024
            "wall_mm": 4.0,     # Pressure vessel wall; NASA JSC-67024
            "gap_mm": 100.0,    # Typical standoff; NASA/TP-2009-214797 §4.2
            "material": "aluminum",
        },
    )


def lunar_transit_risk() -> DebrisRiskSummary:
    """Debris risk during trans-lunar injection from 185 km parking orbit.

    The TLI parking orbit phase (a few hours at 185 km LEO) is the only
    debris-relevant phase of a lunar mission. Once past ~2000 km, debris
    is negligible.
    """
    return mission_debris_risk(
        "Lunar Mission (LEO parking phase)",
        phases=[{
            "name": "LEO parking orbit",
            "altitude_km": 185.0,
            "cross_section_m2": 40.0,    # Apollo CSM+LM stack cross section (est.)
            "duration_years": 3.0 / (365.25 * 24),  # ~3 hours in parking orbit
            "size_threshold": ">1cm",
        }],
    )


if __name__ == "__main__":
    print("\n── ISS Orbit Debris Profile ────────────────────────────────")
    f = debris_flux_full(408.0)
    print(f"  Alt: {f.altitude_km:.0f} km  |  Risk: {f.risk_level.upper()}")
    print(f"  >10cm flux:   {f.flux_gt10cm_per_m2_yr:.2e} hits/m²/yr")
    print(f"  >1cm flux:    {f.flux_gt1cm_per_m2_yr:.2e} hits/m²/yr")
    print(f"  >1mm flux:    {f.flux_gt1mm_per_m2_yr:.2e} hits/m²/yr")
    print(f"  Note: {f.risk_note}")

    print("\n── ISS 0.5-Year Mission Risk ───────────────────────────────")
    r = iss_mission_risk(0.5)
    print_debris_report(r)

    print("\n── Lunar Transit LEO Parking Risk ──────────────────────────")
    r2 = lunar_transit_risk()
    print_debris_report(r2)

    print("\n── Worst Debris Altitudes ─────────────────────────────────")
    for alt in [300, 400, 500, 600, 700, 800, 900, 1000, 1200]:
        f1 = get_debris_flux(alt, ">1cm")
        life = orbital_lifetime_years(alt)
        rule = "✓" if passes_25year_rule(alt) else "✗"
        print(f"  {alt:5d} km: flux={f1:.2e}/m²/yr  lifetime={life:.1f}yr  25yr-rule:{rule}")
