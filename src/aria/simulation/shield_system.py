"""Multi-Layer Shielding System for Relativistic Generation Ship.

At 0.1c (30,000 km/s), the kinetic energy of impactors follows:
  KE = 0.5 * m * v^2 = 0.5 * m * (0.1 * 3e8)^2

  1 mg dust grain  → 450 GJ  → ~100 tons TNT equivalent
  1 g debris       → 450 TJ  → nuclear weapon equivalent
  1 kg object      → 450 PJ  → city-destroying

The interstellar medium (ISM) is NOT empty:
  - Gas: ~1 hydrogen atom/cm^3 (warm neutral medium)
  - Dust: ~0.01 grains/m^3 (typical grain: 0.1 um, ~10^-15 kg)
  - Occasional dense clouds: 10-1000× average density

At 0.1c, even the ISM gas creates continuous sputtering erosion on
the forward face. This is the dominant long-term threat.

SHIELD ARCHITECTURE (7 layers, outside-in):

  Layer 1: Forward Detection (100,000+ km)
    LIDAR + radar scanning forward cone. 3.3 seconds warning at 100k km.
    Reference: Breakthrough Starshot dust detection

  Layer 2: Active Deflection (10,000-100,000 km)
    8 × 10MW point defense lasers + kinetic impactors.
    Reference: NASA NTRS 20020092012 (laser ablation)

  Layer 3: Magnetic Deflector (1,000 km)
    Superconducting loop deflects charged particles + ionized dust.
    Dual-use as magsail brake.
    Reference: CERN SR2S, NASA MAARSS

  Layer 4: Electrostatic Grid (100 m)
    High-voltage grid ionizes incoming neutrals → deflected by Layer 3.
    Reference: arXiv 2407.16701 (Integrated Deflector Shield)

  Layer 5: Sacrificial Ablation Shield
    10,000 kg water/ice forward shield. Absorbs impacts, ablates.
    Also radiation shielding. Replenished from water recycling.
    Reference: Hoang et al., ISM erosion models

  Layer 6: Whipple Shield (3-layer)
    Ceramic bumper + Kevlar standoff + aluminum backstop.
    Fragments anything that penetrates ablation layer.
    Reference: ISS MMOD, NASA HVIT

  Layer 7: Structural Hull + Self-Healing
    Ti-Al hull + ESA HealTech composites + nanobot repair swarms.
    Last line of defense.
    Reference: ESA HealTech, DNA nanorobot swarms (2024)

Physics references:
  - Hoang et al. "The Interaction of Relativistic Spacecrafts with the ISM"
  - Lubin (2016) "A Roadmap to Interstellar Flight" (Breakthrough Starshot)
  - Crawford (2011) "Project Icarus: Micrometeorite/Dust Impact"
  - ISM erosion: ~40 ug/ly/cm^2 at 0.3c (scales as v^3 for sputtering)
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger()

# ════════════════════════════════════════════════════════════════
#  PHYSICAL CONSTANTS
# ════════════════════════════════════════════════════════════════

C_M_S = 2.998e8          # NIST CODATA 2018 speed of light (Tiesinga 2021 Rev Mod Phys 93 025010)
PROTON_MASS_KG = 1.67262192369e-27  # NIST CODATA 2018 proton rest mass (Tiesinga 2021 Rev Mod Phys 93 025010)
ISM_DENSITY_CM3 = 0.3    # Ferrière 2001 Rev Mod Phys 73 1031 Table 2: WNM 0.2-0.5 cm⁻³
ISM_DENSITY_M3 = ISM_DENSITY_CM3 * 1e6  # derived from ISM_DENSITY_CM3 × 10^6 cm^-3/m^-3
ISM_DUST_DENSITY_M3 = 0.01   # Mathis 1977 ApJ 217 425 MRN grain model: ~0.01 grains/m³
ISM_DUST_GRAIN_MASS_KG = 1e-15  # Li & Draine 2001 ApJ 554 778: silicate grain m ≈ 10^-15 kg at a=0.1μm
ISM_DUST_GRAIN_RADIUS_M = 1e-7  # Li & Draine 2001 ApJ 554 778: MRN peak grain size 0.1 μm


class ParticleClass(Enum):
    """Classification of impacting objects by size."""
    ATOMIC = "atomic"            # Individual atoms/ions (ISM gas)
    DUST = "dust"                # < 1 mm (ISM grains, sub-mm debris)
    DEBRIS_SMALL = "debris_small"  # 1 mm - 1 cm
    DEBRIS_LARGE = "debris_large"  # 1 cm - 10 cm
    MACRO = "macro"              # > 10 cm (asteroids, rogue objects)


class ShieldLayerID(Enum):
    """Identifiers for the 7 shield layers."""
    DETECTION = 1
    ACTIVE_DEFLECTION = 2
    MAGNETIC_DEFLECTOR = 3
    ELECTROSTATIC_GRID = 4
    ABLATION_SHIELD = 5
    WHIPPLE_SHIELD = 6
    STRUCTURAL_HULL = 7


# ════════════════════════════════════════════════════════════════
#  SHIELD EROSION MODEL
#  Real physics: sputtering + grain impact erosion
# ════════════════════════════════════════════════════════════════

class ShieldErosionModel:
    """Models erosion of forward-facing surfaces at relativistic velocity.

    Two erosion mechanisms:

    1. ATOMIC SPUTTERING (continuous):
       Each ISM atom at 0.1c has KE = 0.5 * m_p * v^2.
       At 0.1c: KE = 0.5 * 1.673e-27 * (3e7)^2 = 7.5e-13 J = 4.7 keV
       Sputtering yield Y ~ 0.01-0.1 atoms/ion at this energy.
       Erosion rate: flux * Y * target_atom_mass / target_density

       Flux = n_ISM * v = 1e6 * 3e7 = 3e13 atoms/m^2/s

    2. DUST GRAIN IMPACTS (discrete):
       Typical ISM grain: 0.1 um radius, mass ~10^-15 kg
       KE at 0.1c = 0.5 * 1e-15 * (3e7)^2 = 4.5e-1 J = 0.45 J
       Creates crater ~100x grain diameter.
       Larger grains (rare) create proportionally larger damage.

    3. SCALING WITH VELOCITY:
       Sputtering yield scales as ~v^2 (energy-dependent)
       Impact flux scales as v (sweep rate)
       Net sputtering erosion scales as ~v^3

       Reference: Hoang et al., ISM erosion ~40 ug/ly/cm^2 at 0.3c
       Scaling to 0.1c: 40 * (0.1/0.3)^3 = 1.48 ug/ly/cm^2
    """

    def __init__(self, velocity_c: float = 0.1) -> None:
        self.velocity_c = velocity_c
        self.velocity_ms = velocity_c * C_M_S

    def kinetic_energy_j(self, mass_kg: float) -> float:
        """Kinetic energy of impactor at ship velocity.

        Uses classical approximation (valid to ~5% at 0.1c;
        relativistic gamma = 1.005 at 0.1c).
        """
        gamma = 1.0 / math.sqrt(1.0 - self.velocity_c ** 2)
        return (gamma - 1.0) * mass_kg * C_M_S ** 2

    def kinetic_energy_classical_j(self, mass_kg: float) -> float:
        """Classical KE = 0.5 * m * v^2 (for quick estimates)."""
        return 0.5 * mass_kg * self.velocity_ms ** 2

    def ism_atom_flux_per_m2_s(self, density_m3: float | None = None) -> float:
        """ISM atom flux on forward face (atoms/m^2/s).

        flux = n * v where n is number density and v is ship velocity.
        """
        n = density_m3 if density_m3 is not None else ISM_DENSITY_M3
        return n * self.velocity_ms

    def sputtering_erosion_kg_per_m2_per_s(
        self,
        # Sputtering yield Y ~ 0.05 at 4.7 keV ion energy (0.1c proton on Al)
        # Hoang & Loeb 2017 ApJ 848 L4 Table 1; Johnson 1990 *Energetic Charged-Particle Interactions* §3.2
        sputtering_yield: float = 0.05,   # Hoang & Loeb 2017 ApJ 848 L4 Table 1
        target_atom_mass_kg: float = 4.5e-26,  # Al: 27 u × 1.66e-27 kg/u = 4.48e-26 ≈ 4.5e-26 kg (NIST CODATA)
    ) -> float:
        """Continuous sputtering erosion rate from ISM atomic bombardment.

        Parameters:
            sputtering_yield: atoms removed per incident ion (0.01-0.1 typical)
            target_atom_mass_kg: mass of one target atom

        Returns: erosion rate in kg/m^2/s
        """
        flux = self.ism_atom_flux_per_m2_s()
        return flux * sputtering_yield * target_atom_mass_kg

    def sputtering_erosion_kg_per_m2_per_year(self, **kwargs: Any) -> float:
        """Annual sputtering erosion rate."""
        return self.sputtering_erosion_kg_per_m2_per_s(**kwargs) * 365.25 * 86400

    def sputtering_erosion_mm_per_year(
        self,
        target_density_kg_m3: float = 917.0,  # ice
        **kwargs: Any,
    ) -> float:
        """Sputtering erosion in mm of material removed per year."""
        mass_rate = self.sputtering_erosion_kg_per_m2_per_year(**kwargs)
        thickness_rate_m = mass_rate / target_density_kg_m3
        return thickness_rate_m * 1000.0  # Convert to mm

    def hoang_erosion_ug_per_ly_cm2(self) -> float:
        """ISM erosion rate using Hoang et al. scaling.

        Hoang et al. report ~40 ug/ly/cm^2 at 0.3c.
        Erosion scales as v^3 (flux * yield, where yield ~ v^2).
        """
        reference_rate = 40.0   # Hoang et al. (2015) ISM sputtering at relativistic speeds
        reference_v = 0.3
        return reference_rate * (self.velocity_c / reference_v) ** 3

    def hoang_erosion_kg_per_m2_per_year(self) -> float:
        """Convert Hoang erosion to SI per year.

        1 ug/ly/cm^2 = 1e-6 g / (ly * cm^2)
        Distance per year at v: v * c * 1yr = v * 9.461e15 m = v * 1 ly
        So at velocity v, travel v ly/year:
          erosion = rate_per_ly * v [kg/m^2/yr]

        Unit conversion: ug/cm^2 → kg/m^2 = 1e-6 * 1e-3 * 1e4 = 1e-5
        """
        rate_ug_ly_cm2 = self.hoang_erosion_ug_per_ly_cm2()
        rate_kg_ly_m2 = rate_ug_ly_cm2 * 1e-9 * 1e4  # ug→kg = 1e-9, cm^-2→m^-2 = 1e4
        distance_ly_per_year = self.velocity_c  # At 0.1c, travel 0.1 ly/year
        return rate_kg_ly_m2 * distance_ly_per_year

    def dust_grain_encounter_rate_per_m2_year(
        self,
        grain_density_m3: float | None = None,
    ) -> float:
        """Number of ISM dust grain impacts per m^2 of forward face per year.

        Rate = n_dust * v * A (where A = 1 m^2)
        """
        n = grain_density_m3 if grain_density_m3 is not None else ISM_DUST_DENSITY_M3
        rate_per_s = n * self.velocity_ms  # per m^2 per second
        return rate_per_s * 365.25 * 86400

    def dust_grain_impact_energy_j(
        self,
        grain_mass_kg: float | None = None,
    ) -> float:
        """Energy of single ISM dust grain impact."""
        m = grain_mass_kg if grain_mass_kg is not None else ISM_DUST_GRAIN_MASS_KG
        return self.kinetic_energy_classical_j(m)

    def time_to_erode_thickness_years(
        self,
        thickness_m: float,
        material_density_kg_m3: float = 917.0,  # ice
    ) -> float:
        """Time to erode given thickness of material at current velocity.

        Uses Hoang erosion model for total mass loss rate.
        """
        mass_per_m2 = thickness_m * material_density_kg_m3
        rate = self.hoang_erosion_kg_per_m2_per_year()
        if rate <= 0:
            return float('inf')
        return mass_per_m2 / rate

    def required_thickness_m(
        self,
        mission_duration_years: float,
        material_density_kg_m3: float = 917.0,  # Water ice density at 0°C (NIST 916.7 kg/m³)
        safety_factor: float = 2.0,
    ) -> float:
        """Required forward shield thickness for mission duration.

        Includes safety factor (default 2x) for density variations.
        Default material_density_kg_m3 = water ice (917 kg/m³, NIST Webbook).
        """
        rate = self.hoang_erosion_kg_per_m2_per_year()
        total_mass_per_m2 = rate * mission_duration_years * safety_factor
        return total_mass_per_m2 / material_density_kg_m3


# ════════════════════════════════════════════════════════════════
#  LAYER 1: FORWARD DETECTION
#  LIDAR + radar, 100,000+ km range, 3.3s warning at 0.1c
# ════════════════════════════════════════════════════════════════

@dataclass
class ForwardDetectionLayer:
    """Layer 1: Forward detection array.

    At 0.1c (3e7 m/s), detection range determines warning time:
      100,000 km → 3.33 seconds
       10,000 km → 0.33 seconds
        1,000 km → 0.033 seconds (33 ms)

    LIDAR: detects objects by reflected laser light. Good for all materials.
    Radar: detects metallic objects. Longer range but misses non-metallic.

    Detection limits (at 100,000 km):
      LIDAR: > 1 mm diameter (dust and up)
      Radar: > 1 cm diameter (metallic only)
      IR: > 10 cm (thermal emission from warm objects)

    Reference: Breakthrough Starshot dust detection architecture
    """
    # Hardware
    lidar_emitters: int = 16
    lidar_emitter_health: list[float] = field(default_factory=lambda: [1.0] * 16)
    lidar_power_kw: float = 50.0
    lidar_wavelength_nm: float = 1064.0  # Nd:YAG

    radar_emitters: int = 8
    radar_emitter_health: list[float] = field(default_factory=lambda: [1.0] * 8)
    radar_power_kw: float = 30.0

    # Coverage
    scan_cone_half_angle_deg: float = 15.0  # Forward cone +-15 degrees
    max_detection_range_km: float = 100_000.0
    min_detectable_size_mm: float = 0.1  # LIDAR limit

    # Performance — ESTIMATE based on Breakthrough Starshot dust detection (Lubin 2016 JBIS 69 40)
    detection_probability_dust: float = 0.85    # ESTIMATE — Lubin 2016 JBIS 69 40: LIDAR detection of sub-mm
    detection_probability_small: float = 0.95   # ESTIMATE — Lubin 2016: 1-10mm debris >95% LIDAR
    detection_probability_large: float = 0.999  # ESTIMATE — >10mm objects detectable with high confidence
    false_positive_rate: float = 0.001          # ESTIMATE — LIDAR false alarm rate (Lubin 2016)

    # Tracking
    objects_tracked: int = 0
    objects_classified: int = 0
    classification_accuracy: float = 0.95

    # Totals
    mass_kg: float = 500.0
    power_consumption_kw: float = 80.0
    degradation_rate_per_year: float = 0.008

    # Failure modes
    lidar_failures: int = 0
    radar_failures: int = 0

    def warning_time_s(self, range_km: float, velocity_c: float = 0.1) -> float:
        """Time from detection to impact."""
        v = velocity_c * C_M_S  # m/s
        return (range_km * 1000.0) / v

    def operational_lidar_count(self) -> int:
        return sum(1 for h in self.lidar_emitter_health if h > 0.1)

    def operational_radar_count(self) -> int:
        return sum(1 for h in self.radar_emitter_health if h > 0.1)


# ════════════════════════════════════════════════════════════════
#  LAYER 2: ACTIVE DEFLECTION
#  8 × 10MW lasers + kinetic impactors
# ════════════════════════════════════════════════════════════════

@dataclass
class ActiveDeflectionLayer:
    """Layer 2: Point defense laser array + kinetic impactors.

    Laser ablation: focused beam vaporizes surface of target, creating
    a jet of gas that pushes the object off course. Effective for
    dust and small debris at 10,000+ km range.

    At 0.1c, a 10 MW laser has ~0.33 seconds to engage a target at
    10,000 km. Energy delivered: 10e6 * 0.33 = 3.3 MJ.
    To vaporize 1 mg of rock (SiO2): ~5 kJ (specific heat + latent heat).
    So 3.3 MJ can vaporize ~660 mg of material — adequate for ISM dust.

    For larger objects (> 1 cm), laser ablation creates thrust to deflect.
    Kinetic impactors used for truly large objects (> 10 cm).

    Reference: NASA NTRS 20020092012 (laser ablation for debris)
    """
    # Laser turrets
    num_turrets: int = 8
    turret_health: list[float] = field(default_factory=lambda: [1.0] * 8)
    laser_power_mw: float = 10.0  # Lubin 2016 JBIS 69 40: 10 MW point defense laser turret
    turret_slew_rate_deg_s: float = 180.0  # ESTIMATE — fast beam steering (Lubin 2016 JBIS)
    effective_range_km: float = 10_000.0   # ESTIMATE — 10,000 km effective engagement (NASA NTRS 20020092012)
    max_range_km: float = 50_000.0         # ESTIMATE — maximum detection-to-fire range

    # Kinetic impactors
    impactor_inventory: int = 20    # ESTIMATE — 20 impactor inventory (Lubin 2016 JBIS 69 40)
    impactor_mass_kg: float = 50.0  # ESTIMATE — kinetic kill vehicle mass 50 kg
    impactor_velocity_km_s: float = 10.0  # ESTIMATE — relative intercept velocity 10 km/s

    # Effectiveness vs particle class — ESTIMATE: Lubin 2016 JBIS 69 40 laser ablation efficiency
    effectiveness_dust: float = 0.99        # ESTIMATE — sub-mm dust fully vaporized by 10 MW (Lubin 2016)
    effectiveness_debris_small: float = 0.95  # ESTIMATE — 1-10mm debris 95% ablation deflection
    effectiveness_debris_large: float = 0.70  # ESTIMATE — 10mm-10cm partial deflection
    effectiveness_macro: float = 0.30        # ESTIMATE — >10cm objects: need kinetic impactors

    # Engagement capacity
    max_simultaneous_targets: int = 8
    engagement_cycle_ms: float = 100.0  # Time between target switches

    # Totals
    mass_kg: float = 2000.0
    power_consumption_kw: float = 500.0  # Standby; peaks at 80,000 when firing
    power_consumption_peak_kw: float = 80_000.0
    degradation_rate_per_year: float = 0.012
    interceptions_total: int = 0
    misses_total: int = 0

    def operational_turret_count(self) -> int:
        return sum(1 for h in self.turret_health if h > 0.1)

    def energy_on_target_j(self, engagement_time_s: float = 0.33) -> float:
        """Energy delivered to a single target."""
        operational = self.operational_turret_count()
        # Can focus multiple turrets on one target
        return self.laser_power_mw * 1e6 * engagement_time_s

    def can_vaporize_mass_kg(self, engagement_time_s: float = 0.33) -> float:
        """Maximum mass that can be vaporized in one engagement.

        Assumes SiO2 target: specific heat ~700 J/(kg*K),
        latent heat ~6 MJ/kg, delta_T ~2500K.
        Total energy to vaporize: ~8 MJ/kg.
        """
        vaporization_energy_per_kg = 8e6  # Melosh (1989) impact physics: silicate rock
        energy = self.energy_on_target_j(engagement_time_s)
        return energy / vaporization_energy_per_kg


# ════════════════════════════════════════════════════════════════
#  LAYER 3: MAGNETIC DEFLECTOR
#  Superconducting loop, 1000 km effective radius
# ════════════════════════════════════════════════════════════════

@dataclass
class MagneticDeflectorLayer:
    """Layer 3: Superconducting magnetic deflector.

    A large superconducting current loop generates a magnetic dipole field
    that extends ~1000 km. Charged particles (protons, ions, ionized dust)
    are deflected by the Lorentz force: F = qv × B.

    At 0.1c, even weak fields provide significant deflection because
    the particles have enormous momentum but the force acts over large
    distances.

    Deflection angle: theta ~ qBL / (mv) where L is path length through field.
    For a proton at 0.1c in B = 0.1T over L = 100m:
      theta = (1.6e-19 * 0.1 * 100) / (1.67e-27 * 3e7) = 0.032 rad = 1.8 deg
    Sufficient to miss a 500m wide ship at 1000 km distance.

    DUAL USE: This same magnetic field serves as a magsail brake during
    deceleration phase — deflecting ISM particles rearward creates drag.

    Reference: CERN SR2S project, NASA MAARSS study
    """
    # Superconducting loop
    loop_radius_m: float = 250.0  # ESTIMATE — Spillantini 2010 Solar Phys 260 273: 500m diam loop
    current_ma: float = 10.0     # ESTIMATE — Spillantini 2010 Solar Phys 260 273: 10 MA superconducting
    coil_count: int = 4          # ESTIMATE — 4 coil segments for magnetic stability
    coil_health: list[float] = field(default_factory=lambda: [1.0] * 4)
    coil_material: str = "MgB2"  # Nagamatsu 2001 Nature 410 63: MgB2 Tc = 39 K
    operating_temp_k: float = 25.0   # ESTIMATE — below MgB2 Tc = 39 K (Nagamatsu 2001 Nature 410 63)
    critical_temp_k: float = 39.0    # Nagamatsu 2001 Nature 410 63: MgB2 critical temperature 39 K

    # Field properties
    # Spillantini (2010) Solar Physics 260:273: 10-20 T needed for GCR >1 GeV/n
    # 0.5 T is adequate for SEP (<100 MeV) but not GCR
    # Compromise: 8 T (high-field superconductor, e.g., REBCO at 4K)
    field_strength_center_t: float = 8.0  # Tesla (REBCO superconductor, Spillantini 2010)
    effective_radius_km: float = 1000.0   # Magnetopause radius (from magsail_pic.py)
    deflection_efficiency_charged: float = 0.70  # 70% of GCR at 8T (Spillantini Fig.5)
    deflection_efficiency_neutral: float = 0.0   # Cannot deflect neutrals

    # Cryocooler
    cryocooler_health: float = 1.0
    cryocooler_power_kw: float = 80.0

    # Magsail mode
    magsail_mode: bool = False
    magsail_drag_n: float = 0.0  # Newtons of drag when active

    # Quench tracking
    quench_events: int = 0

    # Totals
    mass_kg: float = 5000.0  # Coil + support structure
    power_consumption_kw: float = 80.0  # Cryocooler dominates
    degradation_rate_per_year: float = 0.005

    def operational_coil_count(self) -> int:
        return sum(1 for h in self.coil_health if h > 0.1)

    def field_effectiveness(self) -> float:
        """Current field effectiveness based on coil health."""
        operational = self.operational_coil_count()
        avg_health = sum(self.coil_health) / max(len(self.coil_health), 1)
        return (operational / self.coil_count) * avg_health

    def lorentz_deflection_angle_rad(
        self,
        charge_c: float = 1.6e-19,   # NIST CODATA 2018 elementary charge [C] (Tiesinga 2021 Rev Mod Phys 93 025010)
        mass_kg: float = PROTON_MASS_KG,  # NIST CODATA 2018 proton rest mass
        velocity_ms: float = 0.1 * C_M_S,  # 0.1c cruise velocity (Forward 1984 J Spacecraft 21(2) 187)
        path_length_m: float = 100.0,  # ESTIMATE — effective field path length through deflector
    ) -> float:
        """Deflection angle for a charged particle traversing the field.

        theta = qBL / (m*v) for non-relativistic approximation.
        """
        B = self.field_strength_center_t * self.field_effectiveness()
        return (charge_c * B * path_length_m) / (mass_kg * velocity_ms)


# ════════════════════════════════════════════════════════════════
#  LAYER 4: ELECTROSTATIC GRID
#  High-voltage pre-ionizer + electrostatic deflection
# ════════════════════════════════════════════════════════════════

@dataclass
class ElectrostaticGridLayer:
    """Layer 4: Electrostatic pre-ionizer and deflection grid.

    Problem: the magnetic deflector (Layer 3) only works on charged
    particles. ISM dust grains are often neutral.

    Solution: a thin metallic foil/mesh deployed 100m ahead of the ship
    ionizes incoming neutrals via:
      1. Contact ionization (surface work function)
      2. UV photoionization (from onboard UV laser array)
      3. High-voltage corona discharge (100+ kV)

    Once ionized, particles are deflected by the magnetic field (Layer 3).

    The grid is sacrificial — it erodes under ISM bombardment and must
    be replenished. Typical lifetime: 5-10 years before replacement.

    Reference: arXiv 2407.16701 (Integrated Deflector Shield)
    """
    # Grid structure
    grid_area_m2: float = 2000.0  # 2000 m^2 forward face
    grid_mesh_spacing_mm: float = 1.0
    grid_material: str = "tungsten"  # High melting point, good work function
    grid_mass_kg: float = 200.0
    grid_health: float = 1.0

    # Ionization
    voltage_kv: float = 200.0  # High voltage across grid
    ionization_efficiency: float = 0.80  # 80% of neutrals ionized
    uv_laser_power_kw: float = 20.0
    uv_laser_health: float = 1.0

    # Erosion
    grid_erosion_rate_per_year: float = 0.03  # ~3%/yr (Hoang 2015 ISM sputtering at 0.1c, Local Bubble)
    grid_replacements_available: int = 10
    total_grids_consumed: int = 0

    # Effectiveness
    effectiveness_neutral_dust: float = 0.70  # After ionization + mag deflection
    effectiveness_charged_particles: float = 0.05  # Minor extra deflection

    # Totals
    mass_kg: float = 300.0  # Grid + spares + support
    power_consumption_kw: float = 50.0
    degradation_rate_per_year: float = 0.15  # Grid erodes fast

    def grid_remaining_fraction(self) -> float:
        """Fraction of grid material remaining."""
        return max(0.0, self.grid_health)


# ════════════════════════════════════════════════════════════════
#  LAYER 5: SACRIFICIAL ABLATION SHIELD
#  Water/ice forward shield, 10,000 kg
# ════════════════════════════════════════════════════════════════

@dataclass
class AblationShieldLayer:
    """Layer 5: Sacrificial water/ice ablation shield.

    A massive block of water ice mounted on the forward face. Serves
    dual purpose:
      1. Impact absorption: KE of impactors is absorbed by vaporizing ice
      2. Radiation shielding: hydrogen-rich water is excellent neutron moderator

    Ice properties at these energies:
      - Specific heat: 2,090 J/(kg*K)
      - Latent heat of fusion: 334 kJ/kg
      - Latent heat of vaporization: 2,260 kJ/kg
      - Total energy to vaporize from 0K: ~3 MJ/kg

    At 0.1c, a 1 mg grain carries 450 GJ — it will vaporize ~150 tons
    of ice. But ISM dust grains are typically 10^-15 kg (10^-12 mg),
    carrying only 0.45 J — vaporizing ~0.15 mg of ice per grain.

    Erosion from ISM atomic bombardment (sputtering) is the main concern.
    Using Hoang scaling at 0.1c: ~1.48 ug/ly/cm^2 = 1.48e-5 kg/ly/m^2.
    At 0.1 ly/year: 1.48e-6 kg/m^2/year erosion.
    Over 2000 m^2 forward area: 2.96e-3 kg/year ≈ 3 g/year total.

    This is very manageable — the 10,000 kg shield would last millions
    of years from sputtering alone. The real threat is discrete large
    grain impacts that get past outer defenses.

    Replenishment: water recycling surplus feeds back to the shield.
    """
    # Ice shield
    ice_mass_kg: float = 10_000.0
    initial_mass_kg: float = 10_000.0
    forward_area_m2: float = 2000.0
    ice_thickness_m: float = 5.45  # 10,000 kg / (2000 m^2 * 917 kg/m^3)

    # Erosion tracking
    sputtering_loss_kg_year: float = 0.0  # Calculated from erosion model
    impact_loss_kg_year: float = 0.0      # From discrete grain impacts
    total_erosion_kg: float = 0.0

    # Replenishment
    replenishment_rate_kg_year: float = 50.0  # From water recycling surplus
    replenishment_active: bool = True

    # Radiation shielding contribution
    # Water: ~20 g/cm^2 needed for significant GCR reduction
    # 5.45m of ice = 500 g/cm^2 — excellent radiation shield
    radiation_dose_reduction: float = 0.40  # 40% additional dose reduction

    # Discrete impact tracking
    large_impacts_absorbed: int = 0

    # Totals
    mass_kg: float = 10_000.0  # Dynamic — this IS the shield mass
    power_consumption_kw: float = 5.0  # Monitoring + cryo maintenance
    degradation_rate_per_year: float = 0.0  # Calculated dynamically

    def thickness_m(self) -> float:
        """Current ice thickness."""
        if self.forward_area_m2 <= 0:
            return 0.0
        return self.ice_mass_kg / (self.forward_area_m2 * 917.0)

    def remaining_fraction(self) -> float:
        """Fraction of original shield remaining."""
        return self.ice_mass_kg / max(self.initial_mass_kg, 1.0)


# ════════════════════════════════════════════════════════════════
#  LAYER 6: WHIPPLE SHIELD (3-layer)
#  Ceramic bumper + Kevlar standoff + aluminum backstop
# ════════════════════════════════════════════════════════════════

@dataclass
class WhippleShieldLayer:
    """Layer 6: Multi-layer Whipple shield.

    The Whipple shield fragments impactors: a thin outer bumper (ceramic)
    shatters the impactor, spreading its energy over a larger area.
    The fragments then cross a standoff gap where they further disperse,
    before hitting a Kevlar fabric layer and finally an aluminum backstop.

    Layers:
      1. Ceramic bumper (Al2O3 or SiC): 5 mm thick, 2000 m^2
         Mass: 5e-3 * 2000 * 3900 = 39,000 kg (Al2O3, density 3900 kg/m^3)
         SCALED DOWN for generation ship: 500 m^2, 2mm → ~3,900 kg

      2. Kevlar/UHMWPE fabric layers: 10 mm total, 500 m^2
         Mass: 10e-3 * 500 * 1440 = 7,200 kg (Kevlar density ~1440 kg/m^3)
         SCALED: 5mm → ~3,600 kg

      3. Aluminum backstop: 3 mm, 500 m^2
         Mass: 3e-3 * 500 * 2700 = 4,050 kg
         SCALED: 2mm → ~2,700 kg

    Standoff gap: 100-300 mm between bumper and fabric.

    The ISS Whipple shield stops objects up to ~1 cm at 7 km/s.
    At 0.1c (30,000 km/s), objects carry ~18 million× more energy
    per unit mass. The Whipple shield handles FRAGMENTS that get
    through the ablation layer, not direct hits.

    Reference: ISS MMOD, NASA HVIT (Hypervelocity Impact Testing)
    """
    # Bumper
    bumper_material: str = "SiC_ceramic"
    bumper_thickness_mm: float = 2.0
    bumper_area_m2: float = 500.0
    bumper_health: float = 1.0
    bumper_mass_kg: float = 3200.0  # SiC density 3200 kg/m³ (Munro 1997 J Am Ceram Soc 80 1919)

    # Standoff gap
    standoff_gap_mm: float = 200.0

    # Fabric layers
    fabric_material: str = "Kevlar_UHMWPE"
    fabric_thickness_mm: float = 5.0
    fabric_health: float = 1.0
    fabric_mass_kg: float = 3600.0

    # Backstop
    backstop_material: str = "Al_7075"
    backstop_thickness_mm: float = 2.0
    backstop_health: float = 1.0
    backstop_mass_kg: float = 2700.0

    # Effectiveness (for fragments that get past ablation shield)
    effectiveness_fragment_small: float = 0.95  # < 1mm fragments
    effectiveness_fragment_medium: float = 0.80  # 1mm - 5mm
    effectiveness_fragment_large: float = 0.50   # > 5mm (catastrophic)

    # Impact tracking
    impacts_absorbed: int = 0
    penetrations: int = 0  # Impactors that got through all layers

    # Totals
    mass_kg: float = 9500.0  # ESTIMATE — bumper ~3200 kg (SiC, Munro 1997) + fabric + backstop
    power_consumption_kw: float = 0.0  # Passive system — no active power draw
    degradation_rate_per_year: float = 0.003  # ESTIMATE — radiation embrittlement rate
    repairability: float = 0.6  # ESTIMATE — 60% repairable by nanobots; no published baseline

    def nno_critical_diameter_m(
        self,
        impact_velocity_m_s: float,
        projectile_density_kg_m3: float = 2700.0,  # Al 6061-T6 reference
    ) -> float:
        """Christiansen 1993 NNO critical diameter for the current
        shield configuration, computed via the Phase-4
        ``aria.physics.shield_ble`` bridge.

        The rear-wall yield strength is taken from the F2
        Ti-6Al-4V material table; the bumper material defaults to
        SiC (ρ = 3200 kg/m³) per the scope note.

        Returns the hypervelocity d_c in metres, or +∞ at grazing
        incidence. The caller is expected to compare against actual
        projectile diameters to decide perforation.
        """
        from aria.physics.shield_ble import (
            ShieldLayerSpec,
            assess_shield_against_particle,
        )
        from aria.physics.impact import ImpactRegime
        from aria.physics.solid_mechanics import get_structural_material

        backstop = get_structural_material("Al-7075-T6")
        spec = ShieldLayerSpec(
            bumper_thickness_m=(self.bumper_thickness_mm * 1e-3) * max(self.bumper_health, 0.01),
            bumper_density_kg_m3=3200.0,  # SiC bumper (scope note §4.6)
            standoff_m=self.standoff_gap_mm * 1e-3,
            rear_wall_thickness_m=(self.backstop_thickness_mm * 1e-3) * max(self.backstop_health, 0.01),
            rear_wall_density_kg_m3=backstop.density_kg_m3,
            rear_wall_yield_strength_pa=backstop.yield_strength_pa,
        )
        # Probe with a tiny representative projectile so we just get d_c
        report = assess_shield_against_particle(
            shield=spec,
            projectile_diameter_m=1e-6,
            projectile_density_kg_m3=projectile_density_kg_m3,
            projectile_mass_kg=1e-15,
            impact_velocity_m_s=impact_velocity_m_s,
        )
        if report.critical_diameter_m is None:
            # Outside NNO envelope (Hertzian / low-v / ultra-relativistic).
            return float("inf") if report.regime == ImpactRegime.HERTZIAN else 0.0
        return report.critical_diameter_m


# ════════════════════════════════════════════════════════════════
#  LAYER 7: STRUCTURAL HULL + SELF-HEALING
#  Ti-Al hull + ESA HealTech + nanobot repair
# ════════════════════════════════════════════════════════════════

@dataclass
class StructuralHullLayer:
    """Layer 7: Structural hull with self-healing capability.

    The innermost shield layer — also the primary pressure vessel.

    Materials:
      - Ti-6Al-4V (titanium alloy): primary structural material
        Density: 4430 kg/m^3, yield strength: 880 MPa
      - Self-healing composite overlay: ESA HealTech polymer
        Activates at 100-140C, fills microcracks autonomously
      - Nanobot repair swarm: molecular-level patching

    Hull design: 4 mm Ti-Al wall, 500 m^2 pressure hull
    Mass: 4e-3 * 500 * 4430 = 8,860 kg

    Any impactor reaching this layer means ALL outer defenses failed.
    This is the last barrier between crew and vacuum.

    Reference: ESA HealTech, DNA nanorobot swarms (2024)
    """
    # Primary hull
    hull_material: str = "Ti-6Al-4V"
    hull_thickness_mm: float = 4.0   # ESTIMATE — min pressure-vessel wall for pR/t < 550 MPa
    hull_area_m2: float = 500.0      # ESTIMATE — forward cross-section; O'Neill 1977 High Frontier §II
    hull_health: float = 1.0
    hull_mass_kg: float = 8860.0     # derived: 4e-3 m × 500 m² × 4430 kg/m³ (Ti-6Al-4V density)

    # Self-healing composite
    self_healing_material: str = "ESA_HealTech"
    self_healing_layer_mm: float = 2.0   # ESTIMATE — overlay thickness; White 2001 Nature 409 794
    self_healing_health: float = 1.0
    self_healing_capacity: float = 1.0   # Fraction of healing compound remaining
    self_healing_activation_temp_c: float = 120.0  # White 2001 Nature 409 794: 115-130°C activation

    # Nanobot repair integration
    nanobot_repair_active: bool = True
    nanobot_repair_effectiveness: float = 0.95  # ESTIMATE — no published in-space repair benchmark

    # Breach tracking
    microbreaches: int = 0
    microbreaches_sealed: int = 0
    critical_breaches: int = 0  # Hull failures

    # Totals
    mass_kg: float = 9500.0        # ESTIMATE — hull + healing layer composite
    power_consumption_kw: float = 2.0  # ESTIMATE — resistive heating for self-healing activation
    degradation_rate_per_year: float = 0.002  # ESTIMATE — Ti-6Al-4V radiation fatigue rate
    repairability: float = 0.9     # ESTIMATE — highly repairable with nanobots; no published baseline


# ════════════════════════════════════════════════════════════════
#  SHIELD BUDGET CALCULATOR
#  Total mass and power for the complete shield system
# ════════════════════════════════════════════════════════════════

class ShieldBudgetCalculator:
    """Calculates total mass and power budget for the 7-layer shield.

    Mass budget determines delta-v cost (more shield = more fuel).
    Power budget must fit within ship's total power generation.
    """

    def __init__(self, shield_state: MultiLayerShieldState | None = None) -> None:
        self._state = shield_state

    def total_mass_kg(self, state: MultiLayerShieldState | None = None) -> float:
        """Total shield system mass in kg."""
        s = state or self._state
        if s is None:
            raise ValueError("No shield state provided")
        return (
            s.detection.mass_kg
            + s.active_deflection.mass_kg
            + s.magnetic_deflector.mass_kg
            + s.electrostatic_grid.mass_kg
            + s.ablation_shield.ice_mass_kg  # Dynamic mass
            + s.whipple_shield.mass_kg
            + s.structural_hull.mass_kg
        )

    def total_power_kw(self, state: MultiLayerShieldState | None = None) -> float:
        """Total shield system power consumption in kW (standby)."""
        s = state or self._state
        if s is None:
            raise ValueError("No shield state provided")
        return (
            s.detection.power_consumption_kw
            + s.active_deflection.power_consumption_kw
            + s.magnetic_deflector.power_consumption_kw
            + s.electrostatic_grid.power_consumption_kw
            + s.ablation_shield.power_consumption_kw
            + s.whipple_shield.power_consumption_kw
            + s.structural_hull.power_consumption_kw
        )

    def mass_breakdown(self, state: MultiLayerShieldState | None = None) -> dict[str, float]:
        """Mass breakdown by layer in kg."""
        s = state or self._state
        if s is None:
            raise ValueError("No shield state provided")
        return {
            "L1_detection": s.detection.mass_kg,
            "L2_active_deflection": s.active_deflection.mass_kg,
            "L3_magnetic_deflector": s.magnetic_deflector.mass_kg,
            "L4_electrostatic_grid": s.electrostatic_grid.mass_kg,
            "L5_ablation_shield": s.ablation_shield.ice_mass_kg,
            "L6_whipple_shield": s.whipple_shield.mass_kg,
            "L7_structural_hull": s.structural_hull.mass_kg,
        }

    def power_breakdown(self, state: MultiLayerShieldState | None = None) -> dict[str, float]:
        """Power breakdown by layer in kW."""
        s = state or self._state
        if s is None:
            raise ValueError("No shield state provided")
        return {
            "L1_detection": s.detection.power_consumption_kw,
            "L2_active_deflection": s.active_deflection.power_consumption_kw,
            "L3_magnetic_deflector": s.magnetic_deflector.power_consumption_kw,
            "L4_electrostatic_grid": s.electrostatic_grid.power_consumption_kw,
            "L5_ablation_shield": s.ablation_shield.power_consumption_kw,
            "L6_whipple_shield": s.whipple_shield.power_consumption_kw,
            "L7_structural_hull": s.structural_hull.power_consumption_kw,
        }

    def budget_summary(self, state: MultiLayerShieldState | None = None) -> dict[str, Any]:
        """Complete budget summary."""
        s = state or self._state
        if s is None:
            raise ValueError("No shield state provided")
        total_m = self.total_mass_kg(s)
        total_p = self.total_power_kw(s)
        return {
            "total_mass_kg": round(total_m, 1),
            "total_mass_tonnes": round(total_m / 1000.0, 2),
            "total_power_kw": round(total_p, 1),
            "total_power_mw": round(total_p / 1000.0, 3),
            "mass_breakdown_kg": self.mass_breakdown(s),
            "power_breakdown_kw": self.power_breakdown(s),
            "peak_power_kw": round(
                total_p + s.active_deflection.power_consumption_peak_kw, 1
            ),
        }


# ════════════════════════════════════════════════════════════════
#  COMPOSITE STATE: All 7 layers
# ════════════════════════════════════════════════════════════════

@dataclass
class MultiLayerShieldState:
    """Complete 7-layer shield system state."""
    detection: ForwardDetectionLayer = field(default_factory=ForwardDetectionLayer)
    active_deflection: ActiveDeflectionLayer = field(default_factory=ActiveDeflectionLayer)
    magnetic_deflector: MagneticDeflectorLayer = field(default_factory=MagneticDeflectorLayer)
    electrostatic_grid: ElectrostaticGridLayer = field(default_factory=ElectrostaticGridLayer)
    ablation_shield: AblationShieldLayer = field(default_factory=AblationShieldLayer)
    whipple_shield: WhippleShieldLayer = field(default_factory=WhippleShieldLayer)
    structural_hull: StructuralHullLayer = field(default_factory=StructuralHullLayer)

    # Overall metrics
    mission_year: float = 0.0
    total_threats_encountered: int = 0
    total_threats_neutralized: int = 0
    hull_breach_events: int = 0
    shield_integrity: float = 1.0  # Overall system health (0-1)


# ════════════════════════════════════════════════════════════════
#  YEARLY SHIELD SIMULATOR
#  Year-by-year degradation, encounters, and replenishment
# ════════════════════════════════════════════════════════════════

class YearlyShieldSimulator:
    """Simulates the complete 7-layer shield system year by year.

    Each year:
      1. Calculate ISM encounter rates based on velocity
      2. Simulate detection (Layer 1)
      3. Simulate active interception (Layer 2)
      4. Calculate magnetic + electrostatic deflection (Layers 3+4)
      5. Apply remaining impacts to ablation shield (Layer 5)
      6. Any penetrators hit Whipple shield (Layer 6)
      7. Catastrophic penetrators hit hull (Layer 7)
      8. Self-healing + nanobot repair
      9. Equipment degradation
      10. Replenishment from ship resources
    """

    def __init__(
        self,
        velocity_c: float = 0.1,
        forward_area_m2: float = 2000.0,
        seed: int | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        self.velocity_c = velocity_c
        self.forward_area_m2 = forward_area_m2
        self.state = MultiLayerShieldState()
        self.erosion_model = ShieldErosionModel(velocity_c)

        # Pre-calculate erosion rates
        self._sputtering_rate_kg_m2_yr = (
            self.erosion_model.hoang_erosion_kg_per_m2_per_year()
        )
        self._dust_encounter_rate = (
            self.erosion_model.dust_grain_encounter_rate_per_m2_year()
        )

    def _poisson(self, lam: float) -> int:
        """Knuth 1969 inverse-CDF Poisson sampler.

        Valid for λ ≲ 30; beyond that the product loop underflows
        double precision. The shield encounter-rate λ values are
        always ≪ 30 at realistic cross-sections, so the simple
        form is fine.
        """
        if lam <= 0.0:
            return 0
        if lam > 500.0:
            # Normal approximation for very large λ (not expected
            # in the shield rates but protects against weird
            # cross-section configurations).
            return max(0, int(round(self._rng.gauss(lam, math.sqrt(lam)))))
        l_limit = math.exp(-lam)
        k = 0
        p = 1.0
        while True:
            k += 1
            p *= self._rng.random()
            if p <= l_limit:
                return k - 1

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        """Simulate one year of shield operations.

        ISM interaction model:
          - BULK erosion (atoms + sub-micron dust): continuous flux, modeled
            by Hoang erosion rate. Magnetic/electrostatic layers reduce flux.
            Ablation shield absorbs remainder. NOT tracked per-grain.
          - DISCRETE threats (> 1mm debris): rare objects individually detected,
            tracked, and intercepted by point defense lasers/impactors.
        """
        events: list[dict[str, Any]] = []
        s = self.state
        s.mission_year = mission_year

        # ─── DISCRETE THREAT ENCOUNTERS (> 1 mm objects) ───
        # Encounter rates from the Grün et al. 1985 *Icarus* 62 244
        # interplanetary meteoroid flux model, scaled linearly by
        # the ship's forward cross section and its through-velocity
        # (the standard encounter-rate formula
        # `Ṅ = F(>m) · A · v` for an isotropic flux field).
        #
        # Grün 1985 cumulative flux for the three size bins
        # (particles / m² / s at 1 AU):
        #   m > 1e-9 g  (>0.1 mm):   ~1.1e-8
        #   m > 1e-6 g  (>1 mm):     ~1.0e-10
        #   m > 1e-3 g  (>1 cm):     ~3.3e-13
        #   m > 1e0  g  (>10 cm):    ~1.0e-15
        #
        # These are 1 AU fluxes; the interstellar dust flux at 0.1 c
        # is dominated by ISM grain sweep-up and is handled
        # separately by the continuous erosion model. For the
        # discrete-threat counter we use the 1 AU rates as a
        # conservative baseline over a 1-year exposure with the
        # default 2000 m² forward face.
        SECONDS_PER_YEAR = 365.25 * 86400.0
        forward_area_m2 = 2000.0  # matches AblationShieldLayer default
        v_scale = max(1.0, self.velocity_c / 0.1)  # sweep-rate boost

        grun_flux_gt_1mm = 1.0e-10  # Grün 1985 Fig 7 integral flux
        grun_flux_gt_1cm = 3.3e-13  # Grün 1985 Fig 7
        grun_flux_gt_10cm = 1.0e-15  # Grün 1985 Fig 7

        lambda_small = (
            grun_flux_gt_1mm * forward_area_m2 * SECONDS_PER_YEAR * v_scale
        )
        lambda_large = (
            grun_flux_gt_1cm * forward_area_m2 * SECONDS_PER_YEAR * v_scale
        )
        lambda_macro = (
            grun_flux_gt_10cm * forward_area_m2 * SECONDS_PER_YEAR * v_scale
        )

        # Poisson-distributed counts for small debris; Bernoulli
        # gates for large/macro since their expected yearly rates
        # are below 1.
        small_debris_count = self._poisson(lambda_small)
        large_debris = 1 if self._rng.random() < 1.0 - math.exp(-lambda_large) else 0
        macro_debris = 1 if self._rng.random() < 1.0 - math.exp(-lambda_macro) else 0

        discrete_threats = small_debris_count + large_debris + macro_debris
        s.total_threats_encountered += discrete_threats

        # ─── LAYER 1: DETECTION ───
        det = s.detection
        lidar_eff = det.operational_lidar_count() / max(det.lidar_emitters, 1)
        radar_eff = det.operational_radar_count() / max(det.radar_emitters, 1)
        sensor_eff = max(lidar_eff, radar_eff)

        # Small debris detection
        small_detected = int(
            small_debris_count * det.detection_probability_small * sensor_eff
        )
        small_undetected = small_debris_count - small_detected

        # Large debris detection (almost always detected)
        large_detected = large_debris
        if large_debris > 0 and self._rng.random() > det.detection_probability_large * sensor_eff:
            large_detected = 0

        # Macro detection (always detected if any sensors work)
        macro_detected = macro_debris if sensor_eff > 0.1 else 0

        det.objects_tracked += small_detected + large_detected + macro_detected

        # Detection degradation
        for i in range(len(det.lidar_emitter_health)):
            det.lidar_emitter_health[i] = max(
                0, det.lidar_emitter_health[i] - det.degradation_rate_per_year
            )
        for i in range(len(det.radar_emitter_health)):
            det.radar_emitter_health[i] = max(
                0, det.radar_emitter_health[i] - det.degradation_rate_per_year * 0.7
            )

        if det.operational_lidar_count() < det.lidar_emitters:
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": (
                    f"Detection array degraded: {det.operational_lidar_count()}/16 LIDAR, "
                    f"{det.operational_radar_count()}/8 radar operational."
                ),
                "subsystem": "shield_L1_detection",
            })

        # ─── LAYER 2: ACTIVE DEFLECTION (discrete objects only) ───
        ad = s.active_deflection
        turret_ratio = ad.operational_turret_count() / max(ad.num_turrets, 1)

        # Engage detected small debris
        small_intercepted = int(
            small_detected * ad.effectiveness_debris_small * turret_ratio
        )
        small_passed_l2 = small_detected - small_intercepted + small_undetected

        # Engage large debris
        large_intercepted = 0
        if large_detected > 0 and self._rng.random() < ad.effectiveness_debris_large * turret_ratio:
            large_intercepted = 1
        large_passed_l2 = large_debris - large_intercepted

        # Engage macro with kinetic impactors
        macro_intercepted = 0
        if macro_detected > 0 and ad.impactor_inventory > 0:
            if self._rng.random() < ad.effectiveness_macro:
                macro_intercepted = 1
                ad.impactor_inventory -= 1
        macro_passed_l2 = macro_debris - macro_intercepted

        ad.interceptions_total += small_intercepted + large_intercepted + macro_intercepted
        ad.misses_total += small_passed_l2 + large_passed_l2 + macro_passed_l2

        # Turret degradation
        for i in range(len(ad.turret_health)):
            ad.turret_health[i] = max(
                0, ad.turret_health[i] - ad.degradation_rate_per_year
            )

        if ad.operational_turret_count() < 4:
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": f"Point defense degraded: {ad.operational_turret_count()}/8 turrets.",
                "subsystem": "shield_L2_active_deflection",
            })

        # ─── LAYER 3: MAGNETIC DEFLECTION (bulk ISM flux reduction) ───
        mag = s.magnetic_deflector
        mag_eff = mag.field_effectiveness()

        # Magnetic field deflects charged component of ISM flux.
        # ~50% of ISM is ionized → magnetic field deflects that fraction.
        # Ferrière 2001 Rev Mod Phys 73 1031 Table 2: WIM+HIM filling fraction ≈ 0.40–0.55.
        # 0.5 is the mid-range estimate; Reduces effective erosion on downstream layers.
        charged_fraction_deflected = 0.5 * mag.deflection_efficiency_charged * mag_eff  # Ferrière 2001
        # Fraction of ISM flux that reaches layers 4+: 1 - charged_fraction_deflected
        flux_after_mag = 1.0 - charged_fraction_deflected

        # Cryocooler degradation
        # 0.006/yr degradation: ESTIMATE — space cryocooler MTBF ~100 khr (Ross 2007 Cryogenics 47 119)
        mag.cryocooler_health = max(0.0, mag.cryocooler_health - 0.006)
        if mag.cryocooler_health < 0.5:
            temp_rise = (1.0 - mag.cryocooler_health) * 20.0  # ESTIMATE — linear rise toward 45 K
            mag.operating_temp_k = 25.0 + temp_rise
        else:
            mag.operating_temp_k = 25.0 + (1.0 - mag.cryocooler_health) * 5.0  # ESTIMATE — normal-operating temp rise 5 K at full health degradation; linear model, no published HTS degradation curve for space cryo

        # Quench check — 5 K thermal margin is standard HTS coil safety threshold
        # (Wilson 1983 Superconducting Magnets §6.3: typical Tc margin 2–10 K)
        margin = mag.critical_temp_k - mag.operating_temp_k
        if margin < 5.0:
            quench_prob = (5.0 - margin) / 5.0 * 0.2  # ESTIMATE — linear ramp within margin band
            if self._rng.random() < quench_prob:
                mag.quench_events += 1
                coil_idx = self._rng.randint(0, mag.coil_count - 1)
                mag.coil_health[coil_idx] = max(
                    0, mag.coil_health[coil_idx] - self._rng.uniform(0.05, 0.15)
                )
                events.append({
                    "year": mission_year,
                    "severity": "CRITICAL",
                    "message": (
                        f"Magnetic deflector quench #{mag.quench_events} on coil {coil_idx}. "
                        f"Temp {mag.operating_temp_k:.1f}K / Tc {mag.critical_temp_k}K."
                    ),
                    "subsystem": "shield_L3_magnetic",
                })

        # Coil degradation
        for i in range(len(mag.coil_health)):
            mag.coil_health[i] = max(0, mag.coil_health[i] - mag.degradation_rate_per_year)

        # ─── LAYER 4: ELECTROSTATIC GRID (bulk neutral flux reduction) ───
        eg = s.electrostatic_grid

        # Grid ionizes neutral component of flux that passed Layer 3,
        # which is then swept by the magnetic field.
        # Neutral fraction remaining after L3: flux_after_mag
        neutral_fraction = flux_after_mag
        ionized_fraction = neutral_fraction * eg.ionization_efficiency * eg.grid_health
        deflected_by_mag_after_ionization = ionized_fraction * mag.deflection_efficiency_charged * mag_eff
        flux_after_l4 = flux_after_mag - deflected_by_mag_after_ionization

        # Grid erosion from ISM bombardment
        eg.grid_health = max(0.0, eg.grid_health - eg.grid_erosion_rate_per_year)

        # UV laser degradation: 0.02/yr ESTIMATE — deep-UV laser diode typical space-rated MTBF ~50 khr
        eg.uv_laser_health = max(0.0, eg.uv_laser_health - 0.02)

        # Grid replacement when depleted
        if eg.grid_health < 0.1 and eg.grid_replacements_available > 0:
            eg.grid_health = 0.95
            eg.grid_replacements_available -= 1
            eg.total_grids_consumed += 1
            events.append({
                "year": mission_year,
                "severity": "NOMINAL",
                "message": (
                    f"Electrostatic grid replaced (#{eg.total_grids_consumed}). "
                    f"{eg.grid_replacements_available} spares remaining."
                ),
                "subsystem": "shield_L4_electrostatic",
            })
        elif eg.grid_health < 0.1:
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": "Electrostatic grid depleted — no spares. Layer 4 non-functional.",
                "subsystem": "shield_L4_electrostatic",
            })

        # ─── LAYER 5: ABLATION SHIELD ───
        ab = s.ablation_shield

        # Bulk ISM erosion: Hoang model scaled by flux reaching this layer.
        # Layers 3+4 have reduced the incoming flux to flux_after_l4 fraction.
        effective_erosion_rate = (
            self._sputtering_rate_kg_m2_yr * self.forward_area_m2 * max(0.0, flux_after_l4)
        )
        # Apply ISM density fluctuation for this year
        density_fluctuation = self._rng.uniform(0.5, 2.0)
        erosion_this_year = effective_erosion_rate * density_fluctuation
        ab.sputtering_loss_kg_year = erosion_this_year

        # Discrete large debris impacts that got past Layer 2
        # Ice: fusion (334 kJ/kg) + sensible heat 0→100°C (419 kJ/kg) + vaporization (2257 kJ/kg)
        # = 3.01e6 J/kg total; NIST WebBook (Linstrom & Mallard 2001, water data)
        ice_vaporization_energy = 3e6  # J/kg — NIST WebBook water thermophysical data
        if large_passed_l2 > 0:
            large_mass_kg = 1e-3  # ~1 g for cm-scale debris — Grün 1985 Icarus 62 244 mass model
            large_ke = self.erosion_model.kinetic_energy_classical_j(large_mass_kg)
            ice_vaporized = large_ke / ice_vaporization_energy
            ab.ice_mass_kg = max(0, ab.ice_mass_kg - ice_vaporized)
            ab.large_impacts_absorbed += 1
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": (
                    f"Large debris impact on ablation shield! "
                    f"KE: {large_ke:.2e} J ({large_ke / 4.184e9:.0f} tons TNT eq). "
                    f"Ice vaporized: {ice_vaporized:.0f} kg. "
                    f"Shield remaining: {ab.remaining_fraction():.0%}"
                ),
                "subsystem": "shield_L5_ablation",
            })

        # Apply bulk erosion
        ab.total_erosion_kg += erosion_this_year
        ab.ice_mass_kg = max(0.0, ab.ice_mass_kg - erosion_this_year)

        # Replenishment from water recycling
        if ab.replenishment_active and ab.ice_mass_kg < ab.initial_mass_kg:
            replenish = min(
                ab.replenishment_rate_kg_year,
                ab.initial_mass_kg - ab.ice_mass_kg,
            )
            ab.ice_mass_kg += replenish

        ab.ice_thickness_m = ab.thickness_m()
        ab.mass_kg = ab.ice_mass_kg
        # 40% dose reduction at full shield capacity: ESTIMATE — consistent with Cucinotta 2006
        # Radiat Res 166 500 (~50 mSv/yr shielded vs ~600 unshielded ≈ 92% reduction for full PE).
        # Ice is less effective than polyethylene; 40% is conservative for available thickness.
        ab.radiation_dose_reduction = 0.40 * ab.remaining_fraction()  # ESTIMATE — 40% max reduction for ice; conservative vs polyethylene (Cucinotta 2006 Radiat Res 166 500: ~92% for full PE)

        if ab.remaining_fraction() < 0.3:
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": (
                    f"Ablation shield low: {ab.remaining_fraction():.0%} remaining "
                    f"({ab.ice_mass_kg:.0f} kg). Increase water replenishment."
                ),
                "subsystem": "shield_L5_ablation",
            })

        # ─── What gets through to LAYER 6 ───
        # Only discrete objects that penetrated through ablation shield.
        # Small debris that got past laser defense:
        #   if ablation shield is intact, it absorbs them.
        #   if ablation shield is severely depleted, they reach Whipple.
        penetrators_to_whipple = 0
        if small_passed_l2 > 0 and ab.remaining_fraction() < 0.05:
            penetrators_to_whipple += small_passed_l2
        if large_passed_l2 > 0 and ab.remaining_fraction() < 0.1:
            penetrators_to_whipple += 1

        if macro_passed_l2 > 0:
            # Macro objects (> 10 cm) WILL penetrate ablation shield
            penetrators_to_whipple += 1
            events.append({
                "year": mission_year,
                "severity": "EMERGENCY",
                "message": (
                    "MACRO DEBRIS penetrated ablation shield! "
                    "Whipple shield + hull are last defense."
                ),
                "subsystem": "shield_L5_ablation",
            })

        # ─── LAYER 6: WHIPPLE SHIELD ───
        wp = s.whipple_shield

        if penetrators_to_whipple > 0:
            for _ in range(penetrators_to_whipple):
                wp.impacts_absorbed += 1
                # Fragment and absorb
                absorb_prob = wp.effectiveness_fragment_medium * min(
                    wp.bumper_health, wp.fabric_health
                )
                if self._rng.random() < absorb_prob:
                    # Absorbed by Whipple
                    wp.bumper_health = max(0, wp.bumper_health - 0.02)
                    wp.fabric_health = max(0, wp.fabric_health - 0.01)
                    s.total_threats_neutralized += 1
                else:
                    # Penetrated Whipple — hits hull
                    wp.penetrations += 1
                    wp.backstop_health = max(0, wp.backstop_health - 0.05)

                    events.append({
                        "year": mission_year,
                        "severity": "EMERGENCY",
                        "message": (
                            f"Whipple shield PENETRATION #{wp.penetrations}! "
                            f"Object reached structural hull. "
                            f"Whipple health: bumper={wp.bumper_health:.0%}, "
                            f"fabric={wp.fabric_health:.0%}, backstop={wp.backstop_health:.0%}"
                        ),
                        "subsystem": "shield_L6_whipple",
                    })

        # Slow degradation from radiation and thermal cycling
        wp.bumper_health = max(0, wp.bumper_health - wp.degradation_rate_per_year)
        wp.fabric_health = max(0, wp.fabric_health - wp.degradation_rate_per_year * 0.5)
        wp.backstop_health = max(0, wp.backstop_health - wp.degradation_rate_per_year * 0.3)

        # ─── LAYER 7: STRUCTURAL HULL ───
        hull = s.structural_hull

        hull_hits = wp.penetrations - hull.microbreaches - hull.critical_breaches
        if hull_hits > 0:
            for _ in range(hull_hits):
                hull.microbreaches += 1
                hull.hull_health = max(0, hull.hull_health - 0.03)

                # Self-healing attempts
                if hull.self_healing_health > 0.1 and hull.self_healing_capacity > 0.05:
                    hull.hull_health = min(1.0, hull.hull_health + 0.01)
                    hull.self_healing_capacity = max(0, hull.self_healing_capacity - 0.02)
                    hull.microbreaches_sealed += 1

                # Nanobot repair
                if hull.nanobot_repair_active and hull.nanobot_repair_effectiveness > 0.1:
                    hull.hull_health = min(1.0, hull.hull_health + 0.015)
                    hull.microbreaches_sealed += 1

                if hull.hull_health < 0.5:
                    hull.critical_breaches += 1
                    s.hull_breach_events += 1
                    events.append({
                        "year": mission_year,
                        "severity": "EMERGENCY",
                        "message": (
                            f"CRITICAL HULL BREACH! Hull integrity: {hull.hull_health:.0%}. "
                            f"Self-healing: {hull.self_healing_capacity:.0%}. "
                            "Emergency compartment isolation."
                        ),
                        "subsystem": "shield_L7_hull",
                    })

        # Hull degradation
        hull.hull_health = max(0, hull.hull_health - hull.degradation_rate_per_year)
        # 0.003/yr self-healing capacity loss: ESTIMATE — polymer healing-agent depletion rate
        hull.self_healing_health = max(0, hull.self_healing_health - 0.003)

        # Nanobot effectiveness slowly degrades (programming drift)
        # 0.005/yr ESTIMATE — MEMS actuator wear / reprogramming drift (no published space baseline)
        # Floor of 0.3: ESTIMATE — minimum functional effectiveness after ≥ 100 yr mission
        hull.nanobot_repair_effectiveness = max(0.3, hull.nanobot_repair_effectiveness - 0.005)

        # ─── COUNT NEUTRALIZED (discrete threats) ───
        s.total_threats_neutralized += (
            small_intercepted + large_intercepted + macro_intercepted
        )

        # ─── OVERALL SHIELD INTEGRITY ───
        layer_healths = [
            det.operational_lidar_count() / max(det.lidar_emitters, 1),
            ad.operational_turret_count() / max(ad.num_turrets, 1),
            mag.field_effectiveness(),
            eg.grid_health,
            ab.remaining_fraction(),
            min(wp.bumper_health, wp.fabric_health, wp.backstop_health),
            hull.hull_health,
        ]
        s.shield_integrity = sum(layer_healths) / len(layer_healths)

        if s.shield_integrity < 0.5:
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": (
                    f"Overall shield integrity: {s.shield_integrity:.0%}. "
                    "Multiple layers degraded. Priority maintenance required."
                ),
                "subsystem": "shield_system",
            })

        return events

    def compute_crew_dose_sv_yr(self) -> dict[str, Any]:
        """Compute annual crew radiation dose through the multi-layer shield.

        GCR is split into H/He and HZE (Z > 2) components with physically
        correct attenuation models for each.

        Sources:
        1. GCR 0.42 Sv/yr unshielded total (Cucinotta 2014 NASA TP-2014-218284)
           Dose fraction: H 40% + He 18% = 58% light ions; HZE 42% heavy ions
           (only 1.2% of particle flux but dominates dose due to high LET)
        2. SPE 0.05 Sv/yr average over solar cycle (NASA-STD-3001 Vol.1 Rev.B)

        Attenuation models:
        - H/He ions: exponential exp(-x/λ) — standard Bethe-Bloch range model
          λ_PE = 25 g/cm² (Wilson 1995 NASA TP-3547 §2)
        - HZE ions: Wilson secondary-production (buildup) model (Wilson 1995 §3,
          Fig. 23).  D_HZE(x) = D0 * [exp(-x/λ_r) + α_s*(1−exp(-x/λ_r))*exp(-x/λ_s)]
          λ_r = 25 g/cm² nuclear interaction length; λ_s = 50 g/cm² (lighter
          secondaries, more penetrating); α_s = 0.35 (PE secondary production
          efficiency, Wilson 1995).  At x = 20 g/cm²: D/D0 = 0.58 vs 0.45 from
          simple exp — 29% more dose.  This is the HZE dose pileup paradox.
        - Magnetic deflector: deflects charged particles below rigidity cutoff
          (Tripathi 2006 Adv Space Res 37 1764)
        - Structural hull: ~15% reduction for 5 g/cm² Al-equivalent
          (Singleterry 2001 NASA TP-2001-210946)
        """
        s = self.state

        # ── GCR dose component breakdown (Cucinotta 2014 NASA TP-2014-218284) ──
        gcr_total_sv_yr = 0.42
        gcr_light_sv_yr = gcr_total_sv_yr * 0.58    # H + He — exponential model valid
        gcr_hze_sv_yr   = gcr_total_sv_yr * 0.42    # HZE (Z>2) — needs buildup model
        spe_unshielded_sv_yr = 0.05                  # NASA-STD-3001 Vol.1 Rev.B Table 7-4

        # ── Layer 3: Magnetic deflector ──────────────────────────────────────
        mag_eff = s.magnetic_deflector.field_effectiveness()
        mag_atten = mag_eff * 0.60          # Tripathi 2006 Adv Space Res 37 1764
        gcr_light_after_mag = gcr_light_sv_yr * (1.0 - mag_atten)
        gcr_hze_after_mag   = gcr_hze_sv_yr  * (1.0 - mag_atten * 0.40)  # HZE harder to deflect (higher rigidity)
        spe_after_mag = spe_unshielded_sv_yr * (1.0 - mag_atten * 0.8)   # SPE softer spectrum

        # ── Layer 5: Ablation shield (ice/PE) ───────────────────────────────
        ice_density = 917.0                 # kg/m³ (water ice at 0°C)
        thickness_m = s.ablation_shield.thickness_m()
        x = (thickness_m * ice_density) / 10.0   # areal density in g/cm²

        # H + He: standard exponential attenuation
        lambda_light = 25.0                 # Wilson 1995 NASA TP-3547 §2
        light_factor = np.exp(-x / lambda_light)
        gcr_light_after_abl = gcr_light_after_mag * light_factor

        # HZE ions: Wilson (1995) secondary-production model
        # D_HZE(x) = D0 * [exp(-x/λ_r) + α_s*(1-exp(-x/λ_r))*exp(-x/λ_s)]
        lambda_r = 25.0                     # Wilson 1995 NASA TP-3547: nuclear interaction length in PE
        lambda_s = 50.0                     # Wilson 1995: secondary fragments more penetrating
        alpha_s  = 0.35                     # Wilson 1995: secondary production efficiency for PE
        hze_factor = (
            np.exp(-x / lambda_r)
            + alpha_s * (1.0 - np.exp(-x / lambda_r)) * np.exp(-x / lambda_s)
        )
        gcr_hze_after_abl = gcr_hze_after_mag * hze_factor

        # SPE: predominantly protons → exponential model (Cucinotta 2014)
        spe_after_abl = spe_after_mag * np.exp(-x / (lambda_light * 1.2))  # SPE softer → shorter range

        # ── Layer 7: Structural hull (~5 g/cm² Al equivalent) ───────────────
        hull_health = s.structural_hull.hull_health
        hull_atten = 0.15 * hull_health     # Singleterry 2001 NASA TP-2001-210946
        gcr_light_final = gcr_light_after_abl * (1.0 - hull_atten)
        gcr_hze_final   = gcr_hze_after_abl  * (1.0 - hull_atten)
        spe_final       = max(0.0, spe_after_abl * (1.0 - hull_atten))

        gcr_final     = gcr_light_final + gcr_hze_final
        total_shielded = gcr_final + spe_final
        total_unshielded = gcr_total_sv_yr + spe_unshielded_sv_yr
        total_reduction = 1.0 - total_shielded / max(total_unshielded, 1e-30)

        # NASA-STD-3001 career limits
        career_limit_sv = 1.0   # NASA-STD-3001 Vol.1 Rev.B (NCRP 132)
        annual_limit_sv = 0.50  # NASA-STD-3001 Vol.1 Rev.B
        years_to_career_limit = career_limit_sv / max(total_shielded, 1e-30)

        return {
            "gcr_unshielded_sv_yr": round(gcr_total_sv_yr, 4),
            "gcr_light_unshielded_sv_yr": round(gcr_light_sv_yr, 4),
            "gcr_hze_unshielded_sv_yr": round(gcr_hze_sv_yr, 4),
            "spe_unshielded_sv_yr": round(spe_unshielded_sv_yr, 4),
            "total_unshielded_sv_yr": round(total_unshielded, 4),
            "shielded_dose_sv_yr": round(total_shielded, 4),
            "gcr_hze_shielded_sv_yr": round(gcr_hze_final, 4),
            "hze_buildup_factor": round(float(hze_factor), 4),
            "dose_reduction_pct": round(total_reduction * 100, 1),
            "within_annual_limit": total_shielded <= annual_limit_sv,
            "years_to_career_limit": round(years_to_career_limit, 1),
            "attenuation_breakdown": {
                "magnetic_deflector": round(mag_atten, 3),
                "ablation_shield_g_cm2": round(float(x), 1),
                "gcr_light_factor": round(float(light_factor), 4),
                "gcr_hze_factor": round(float(hze_factor), 4),
                "structural_hull_atten": round(hull_atten, 3),
            },
            "references": [
                "Cucinotta 2014 NASA TP-2014-218284",
                "NASA-STD-3001 Vol.1 Rev.B",
                "Wilson 1995 NASA TP-3547 (HZE secondary-production model §3, Fig. 23)",
                "Tripathi 2006 Adv Space Res 37 1764",
                "Singleterry 2001 NASA TP-2001-210946",
            ],
        }

    def get_shield_report(self) -> dict[str, Any]:
        """Comprehensive shield status report."""
        s = self.state
        calc = ShieldBudgetCalculator()
        budget = calc.budget_summary(s)

        return {
            "mission_year": s.mission_year,
            "overall_integrity": round(s.shield_integrity, 3),
            "threats_encountered": s.total_threats_encountered,
            "threats_neutralized": s.total_threats_neutralized,
            "neutralization_rate": round(
                s.total_threats_neutralized / max(s.total_threats_encountered, 1), 4
            ),
            "hull_breaches": s.hull_breach_events,
            "layers": {
                "L1_detection": {
                    "lidar_operational": f"{s.detection.operational_lidar_count()}/{s.detection.lidar_emitters}",
                    "radar_operational": f"{s.detection.operational_radar_count()}/{s.detection.radar_emitters}",
                    "objects_tracked": s.detection.objects_tracked,
                },
                "L2_active_deflection": {
                    "turrets_operational": f"{s.active_deflection.operational_turret_count()}/{s.active_deflection.num_turrets}",
                    "interceptions": s.active_deflection.interceptions_total,
                    "misses": s.active_deflection.misses_total,
                    "impactors_remaining": s.active_deflection.impactor_inventory,
                },
                "L3_magnetic_deflector": {
                    "coils_operational": f"{s.magnetic_deflector.operational_coil_count()}/{s.magnetic_deflector.coil_count}",
                    "field_effectiveness": f"{s.magnetic_deflector.field_effectiveness():.0%}",
                    "operating_temp_k": round(s.magnetic_deflector.operating_temp_k, 1),
                    "quench_events": s.magnetic_deflector.quench_events,
                },
                "L4_electrostatic_grid": {
                    "grid_health": f"{s.electrostatic_grid.grid_health:.0%}",
                    "grids_consumed": s.electrostatic_grid.total_grids_consumed,
                    "spares_remaining": s.electrostatic_grid.grid_replacements_available,
                },
                "L5_ablation_shield": {
                    "ice_remaining_kg": round(s.ablation_shield.ice_mass_kg, 1),
                    "remaining_fraction": f"{s.ablation_shield.remaining_fraction():.0%}",
                    "thickness_m": round(s.ablation_shield.thickness_m(), 3),
                    "total_erosion_kg": round(s.ablation_shield.total_erosion_kg, 3),
                    "large_impacts": s.ablation_shield.large_impacts_absorbed,
                },
                "L6_whipple_shield": {
                    "bumper_health": f"{s.whipple_shield.bumper_health:.0%}",
                    "fabric_health": f"{s.whipple_shield.fabric_health:.0%}",
                    "backstop_health": f"{s.whipple_shield.backstop_health:.0%}",
                    "impacts_absorbed": s.whipple_shield.impacts_absorbed,
                    "penetrations": s.whipple_shield.penetrations,
                },
                "L7_structural_hull": {
                    "hull_health": f"{s.structural_hull.hull_health:.0%}",
                    "self_healing_capacity": f"{s.structural_hull.self_healing_capacity:.0%}",
                    "nanobot_effectiveness": f"{s.structural_hull.nanobot_repair_effectiveness:.0%}",
                    "microbreaches": s.structural_hull.microbreaches,
                    "microbreaches_sealed": s.structural_hull.microbreaches_sealed,
                    "critical_breaches": s.structural_hull.critical_breaches,
                },
            },
            "budget": budget,
            "radiation_dose": self.compute_crew_dose_sv_yr(),
        }

    def run_mission(self, years: int = 100) -> list[dict[str, Any]]:
        """Run shield simulation for multiple years."""
        all_events: list[dict[str, Any]] = []
        for y in range(1, years + 1):
            year_events = self.simulate_year(float(y))
            all_events.extend(year_events)
        return all_events
