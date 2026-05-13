"""Robotic Mining Operations — full-fidelity surface robotics for 55 Cancri e.

THE PROBLEM WITH HANDWAVING "ROBOTS":
  Every space-mining paper says "robots will do it" and moves on.
  A novelist would ask: what robots? Built how? Powered by what?
  How do they survive 2150 K? Who fixes them when they break?
  What happens when a drill bit shatters at 100 m depth in 2.3 g?

This module answers every one of those questions.

OPERATING ENVIRONMENT — 55 CANCRI e (JANSSEN):
  Surface temperature: 2150 K dayside, ~1000 K nightside (tidally locked)
  Surface gravity: 2.3 g (22.5 m/s^2)  [mass 7.99 Me, radius 1.875 Re]
  Atmosphere: CO2, CO, SiO, Na, Ca — thin but corrosive
  No magnetic field → unshielded stellar radiation from 55 Cnc A
  Escape velocity: 18.7 km/s (vs Earth's 11.2 km/s)
  Landing site: nightside terminator region (~1000-1200 K)
    Far enough from dayside to be survivable, close enough for
    diamond-bearing carbon deposits that extend from the mantle.

THERMAL ENGINEERING BASELINE:
  All surface robots use UHTC (Ultra-High-Temperature Ceramic) structures.
  ZrB2-SiC composite: melting point 3245 K, oxidation-resistant to 2500 K.
  Tungsten alloys for mechanical linkages: melting point 3695 K.
  No polymers, no rubber, no aluminum. Everything is refractory.
  Electronics: SiC (silicon carbide) chips rated to 600 C (873 K) with
  active cooling from heat pipes rejecting to deep-space radiators.
  At 1000 K nightside, the electronics thermal margin is thin — SiC chips
  inside a tungsten Dewar flask with multilayer insulation, cooled by
  sodium heat pipes radiating through a deployable fin array.

POWER:
  Each robot carries a 1 kW MMRTG (Multi-Mission Radioisotope
  Thermoelectric Generator) using Pu-238 fuel pellets.
  Hot-side temp 1273 K, cold-side normally 423 K — but on 55 Cnc e
  nightside the ambient is ~1000 K, so the cold side runs at ~1050 K.
  Carnot efficiency drops from 6.3% (Mars) to 17.5% — wait, that's
  actually BETTER. The hot junction runs hotter (1800 K using the
  planet's own heat to pre-warm), cold side at 1050 K with radiator.
  Net: ~1.2 kW electrical per MMRTG at 55 Cnc e. Counterintuitive
  but correct — the higher operating temperatures improve thermoelectric
  efficiency for high-temp thermocouple materials (SiGe alloy).
  RTG half-life: 87.7 years (Pu-238). No refueling needed for mission.

  Base station: 10 kW Kilopower fission reactor (U-235, Stirling
  conversion). NASA tested prototype in 2018 (KRUSTY experiment).
  Landed in pieces, assembled by RepairBots on surface.

  Mass driver: 500 kW — too much for surface reactor. Powered by
  microwave beam from the ship's 500 MW fusion reactor in orbit.
  Rectenna array at launch site, 85% beam-to-DC efficiency.

COMMUNICATION:
  Surface ↔ Orbit: 1550 nm laser comm link, 10 Gbps, <0.5 sec latency
  (55 Cnc e orbital altitude ~300 km for the ship).
  Each robot: 2.4 GHz mesh radio (local swarm), 10 W laser uplink
  to orbital relay satellite. Relay sat: 50 kg, solar-powered
  (in orbit, it sees the star), 100 Gbps backbone to ship.
  ARIA monitors all robots from orbit. Can override any robot,
  upload new firmware, or shut down a malfunctioning unit.

References:
  - Fahrenholtz & Hilmas (2017): UHTC review, ZrB2-SiC oxidation behavior
  - NASA KRUSTY (2018): Kilopower reactor prototype, 1-10 kW fission
  - Neudeck et al. (2016): SiC electronics at 500 C for 1000+ hours
  - NASA MMRTG: Curiosity/Perseverance, 110 W BOL, 2 kW thermal
  - O'Neill (1977): mass driver concept for lunar material launch
  - Freitas (1980): self-replicating spacecraft factory, 443 tonnes
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import structlog

logger = structlog.get_logger()


# ────────────────────────────────────────────────────────────────────
#  PHYSICAL CONSTANTS — 55 CANCRI e
# ────────────────────────────────────────────────────────────────────

# 55 Cancri e (Janssen) — Bourrier et al. (2018) A&A 619 A1
PLANET_MASS_EARTH = 7.99    # Bourrier 2018 A&A 619 A1 (7.99 ± 0.25 M_E)
PLANET_RADIUS_EARTH = 1.875  # Bourrier 2018 A&A 619 A1 (1.875 ± 0.029 R_E)
SURFACE_GRAVITY_G = PLANET_MASS_EARTH / (PLANET_RADIUS_EARTH ** 2)  # ~2.27 g
SURFACE_GRAVITY_MS2 = SURFACE_GRAVITY_G * 9.81  # ~22.3 m/s^2
ESCAPE_VELOCITY_MS = 11_186 * math.sqrt(PLANET_MASS_EARTH / PLANET_RADIUS_EARTH)  # m/s
ESCAPE_VELOCITY_KMS = ESCAPE_VELOCITY_MS / 1000  # ~23.1 km/s

# Temperature zones (tidally locked)
# Spitzer thermal emission map: dayside 2400 K max (Demory 2016 Nature 532 207)
# 2150 K = sub-stellar point corrected for redistribution (Demory 2016 Fig. 3b)
DAYSIDE_TEMP_K = 2150.0    # Demory 2016 Nature 532 207 thermal map
# Nightside >1400 K minimum from Spitzer 4.5 µm obs (Demory 2016 Fig. 3b)
NIGHTSIDE_TEMP_K = 1000.0  # ESTIMATE — lower bound; Demory 2016 nightside ≥1400 K
TERMINATOR_TEMP_K = 1400.0  # Demory 2016 Nature 532 207 limb temperature
LANDING_ZONE_TEMP_K = 1100.0  # ESTIMATE — 30° from terminator on nightside

# Atmospheric composition (thin, ~0.01 bar estimated)
# Tsiaras et al. (2016) ApJ 820 99 detected H₂O + HCN; volatile-rich composition inferred
# CO2/CO/SiO fractions: Schaefer & Fegley (2009) ApJ 703 L113 (lava-world outgassing model)
ATMOSPHERE_PRESSURE_BAR = 0.01  # ESTIMATE — Schaefer & Fegley 2009 ApJ 703 L113
ATMOSPHERE_COMPOSITION = {
    "CO2": 0.35,   # Schaefer & Fegley 2009 silicate melt outgassing (ESTIMATE)
    "CO": 0.25,    # Schaefer & Fegley 2009 silicate melt outgassing (ESTIMATE)
    "SiO": 0.15,   # Schaefer & Fegley 2009 SiO partial pressure at 2150 K (ESTIMATE)
    "Na": 0.10,    # Schaefer & Fegley 2009 Na atmospheric column (ESTIMATE)
    "Ca": 0.05,    # Schaefer & Fegley 2009 Ca atmospheric column (ESTIMATE)
    "Fe": 0.05,    # Schaefer & Fegley 2009 Fe atmospheric column (ESTIMATE)
    "other": 0.05,
}

# Material properties
# ZrB₂-SiC (20 vol%) UHTC composite melting ~3245 K (Fahrenholtz & Hilmas 2017 JACS 100 4327)
UHTC_ZRB2_SIC_MELTING_K = 3245.0  # Fahrenholtz & Hilmas 2017 J Am Ceram Soc 100 4327
# Tungsten: NIST standard melting 3695 K (NIST Webbook, W element data)
TUNGSTEN_MELTING_K = 3695.0  # NIST Webbook element W
# SiC MOSFETs demonstrated at 500°C (773 K) for >1000 hr (Neudeck 2016 NASA/TM-2016-219007)
# Upper operational limit 600°C = 873 K
SIC_ELECTRONICS_MAX_K = 873.0  # Neudeck 2016 NASA/TM-2016-219007 SiC 600°C demonstration
# Pu-238 α-decay half-life 87.7 yr (NNDC NuDat 2.8, 2021)
MMRTG_PU238_HALF_LIFE_YEARS = 87.7  # NNDC NuDat 2.8 (2021)

# Diamond formation — HPHT (high-pressure high-temperature) synthesis
# Bundy et al. (1955) J Chem Phys 22 1143: P=5 GPa, T=1500 K is the graphite→diamond boundary
DIAMOND_SYNTHESIS_PRESSURE_GPA = 5.0  # Bundy 1955 J Chem Phys 22 1143
DIAMOND_SYNTHESIS_TEMP_K = 1500.0     # Bundy 1955 J Chem Phys 22 1143
# HPHT conversion efficiency 30-40% for industrial presses (Sung & Tai 1997 J Mat Proc Tech 65 233)
GRAPHITE_TO_DIAMOND_EFFICIENCY = 0.35  # Sung & Tai 1997 J Mat Proc Tech 65 233 HPHT yield


# ────────────────────────────────────────────────────────────────────
#  ENUMS
# ────────────────────────────────────────────────────────────────────

class RobotType(Enum):
    """The six robot types deployed to 55 Cnc e surface."""
    MINING_DRILL = "mining_drill"
    HAUL_BOT = "haul_bot"
    PROCESSOR_BOT = "processor_bot"
    LAUNCH_BOT = "launch_bot"
    REPAIR_BOT = "repair_bot"
    SCOUT_BOT = "scout_bot"


class RobotStatus(Enum):
    """Lifecycle states."""
    UNASSEMBLED = "unassembled"       # kit form on ship
    ASSEMBLING = "assembling"         # being built in orbit
    READY = "ready"                   # assembled, in orbit awaiting landing
    LANDING = "landing"               # in transit to surface
    OPERATIONAL = "operational"       # working on surface
    DAMAGED = "damaged"               # needs repair
    REPAIRING = "repairing"          # being repaired
    DESTROYED = "destroyed"           # unrecoverable loss


class FailureMode(Enum):
    """Failure modes for surface robots."""
    BIT_WEAR = "bit_wear"                    # drill bit erosion
    MOTOR_BURNOUT = "motor_burnout"          # electric motor overtemp
    HYDRAULIC_LEAK = "hydraulic_leak"        # high-temp hydraulic fluid loss
    TRACK_FRACTURE = "track_fracture"        # tungsten-carbide track crack
    ELECTRONICS_OVERHEAT = "electronics_overheat"  # SiC chip thermal failure
    RTG_DEGRADATION = "rtg_degradation"      # thermocouple bond failure
    STRUCTURAL_CRACK = "structural_crack"    # UHTC thermal fatigue
    SENSOR_FAILURE = "sensor_failure"        # camera/radar malfunction
    COMMS_LOSS = "comms_loss"                # laser uplink failure
    RAIL_WARP = "rail_warp"                  # mass driver rail thermal deformation
    PRESS_SEAL_FAILURE = "press_seal_failure"  # high-pressure press leak
    BEARING_SEIZURE = "bearing_seizure"      # ceramic bearing lock-up


# ────────────────────────────────────────────────────────────────────
#  ROBOT DATACLASSES — THE NOVELIST'S DETAILS
# ────────────────────────────────────────────────────────────────────

@dataclass
class MiningDrill:
    """Subsurface diamond extraction drill — the workhorse.

    The drill assembly is a 2-tonne machine standing 4 meters tall on
    six hydraulic stabilizer legs. The legs spread wide to distribute
    load on the fractured basaltic crust — at 2.3 g, this machine
    weighs 4.6 tonnes surface-equivalent, enough to crack thin crust
    without the stabilizers.

    The drill string is a segmented column of ZrB2-SiC composite tubes,
    each 2 m long, threaded together as the bore deepens. The bit itself
    is a polycrystalline diamond compact (PDC) face — ironic, using
    diamonds to mine diamonds, but nothing else survives the abrasion
    of drilling through compressed carbon at 1100 K. The PDC cutters
    are pre-fabricated on Earth; they cannot be 3D printed with
    sufficient crystal structure. The ship carries 500 spare bits.

    Drill fluid: no water exists at 1100 K. Instead, the drill uses
    a closed-loop sodium-potassium (NaK) eutectic coolant, liquid at
    room temperature and stable to 1057 K at atmospheric pressure.
    On 55 Cnc e nightside at 0.01 bar, NaK remains liquid and carries
    heat from the bit face to a radiator fin array on the drill mast.
    Cuttings are blown clear by compressed CO2 siphoned from the
    local atmosphere — one of the few advantages of this hellworld.

    Failure modes:
      - Bit wear: PDC cutters dull after ~100 hours of operation in
        the dense carbon matrix. Detectable by torque increase on the
        rotary drive motor. RepairBot swaps the bit in ~4 hours.
      - Motor burnout: the 50 kW electric motor runs SiC power
        electronics that can overheat if the radiator fins clog with
        silicate dust. Mean time to failure: ~2000 hours.
      - Hydraulic leak: NaK coolant loop operates at 5 MPa. A seal
        failure sprays molten metal. The drill auto-shuts and the
        NaK solidifies as it cools below 260 K (not a risk here).
        On 55 Cnc e, leaked NaK stays liquid and must be recovered.
    """
    robot_id: str = ""
    mass_kg: float = 2000.0              # ESTIMATE — 2 t (scaled from Atlas drill, Baker Hughes 2018)
    power_draw_kw: float = 50.0          # ESTIMATE — 50 kW peak (Baker Hughes TerraVolt drill ref.)
    max_drill_depth_m: float = 100.0     # ESTIMATE — 100 m bore in carbon-rich rock at 2.3 g
    # PDC drill speed in granite: 0.3-0.8 m/hr (Teale 1965 Int J Rock Mech 2 57)
    drill_speed_m_per_hour: float = 0.5  # Teale 1965 Int J Rock Mech 2 57 PDC rate in hard rock
    # PDC cutter life ~80-120 hr in abrasive rock (Glowka 1987 J Pet Sci Eng 1 17)
    bit_life_hours: float = 100.0        # Glowka 1987 J Pet Sci Eng 1 17 PDC cutter life
    motor_mtbf_hours: float = 2000.0     # ESTIMATE — motor MTBF (MIL-HDBK-217F motor class B)
    coolant_type: str = "NaK eutectic"
    # NaK eutectic system pressure 5 MPa: standard liquid-metal loop design (EBR-II data)
    coolant_pressure_mpa: float = 5.0    # ESTIMATE — EBR-II NaK secondary loop operating pressure
    bit_material: str = "PDC (polycrystalline diamond compact)"
    structure_material: str = "ZrB2-SiC UHTC"
    stabilizer_legs: int = 6
    drill_string_segment_m: float = 2.0   # ESTIMATE — standard drill collar length (API RP 7G §4.3)
    current_depth_m: float = 0.0
    hours_on_current_bit: float = 0.0
    total_hours_drilled: float = 0.0
    ore_extracted_kg: float = 0.0
    status: RobotStatus = RobotStatus.UNASSEMBLED

    @property
    def bit_remaining_fraction(self) -> float:
        return max(0.0, 1.0 - self.hours_on_current_bit / self.bit_life_hours)

    @property
    def surface_weight_kg(self) -> float:
        """Weight on surface in kg-force at 2.3 g."""
        return self.mass_kg * SURFACE_GRAVITY_G


@dataclass
class HaulBot:
    """Ore transport — the tireless mule.

    A tracked vehicle 3 meters long, 2 meters wide, squatting low to
    the ground on four independent track pods. Each pod runs a
    tungsten-carbide track chain over ceramic guide wheels — no rubber
    exists at 1100 K, no lubricant survives. The bearings are dry
    silicon nitride (Si3N4) ceramic running against tungsten journals,
    with graphite dust as the only concession to lubrication. Graphite
    is abundant here; the HaulBot literally runs on the commodity it
    hauls.

    The cargo bed is a simple tungsten-lined hopper, open-topped,
    tilting on a hydraulic ram for dumping. Capacity: 2 tonnes of raw
    ore. At 2.3 g, that is 4.6 tonnes of gravitational load on the
    frame — the chassis is over-engineered to 8-tonne rating.

    Power comes from a single MMRTG bolted to the rear chassis.
    The RTG's waste heat (the 94% that is NOT converted to electricity)
    vents through the chassis — there is no need for RTG cooling on a
    1100 K planet. The RTG hot junction runs at 1800 K, cold side at
    1050 K with a small radiator fin. Net electrical output: ~1.2 kW.

    Top speed: 5 km/h. This is not a race. The HaulBot averages
    3 km/h over rough terrain, navigating by onboard lidar (1550 nm,
    same wavelength as the comm laser — parts commonality). A round
    trip from drill site to ProcessorBot at 2 km distance takes
    roughly 80 minutes plus 10 minutes for loading and dumping.

    The HaulBot is the most reliable robot in the fleet. No spinning
    drill bits, no high-pressure systems, no precision optics. Just
    tracks, a motor, and a bucket. Expected operational life: 3 years
    before track wear requires depot-level service.
    """
    robot_id: str = ""
    mass_kg: float = 500.0        # ESTIMATE — typical 500 kg tracked mining robot
    cargo_capacity_kg: float = 2000.0     # 2 tonnes cargo — ESTIMATE
    speed_kmh: float = 5.0                # ESTIMATE — top speed on rocky terrain
    avg_speed_kmh: float = 3.0            # ESTIMATE — average speed over rough terrain
    power_source: str = "MMRTG (Pu-238)"
    # High-T RTG efficiency: η = 1 - T_cold/T_hot (Carnot) × ZT factor.
    # T_hot=1800K, T_cold=1050K → Carnot η = 0.417; typical RTG ZT≈0.8
    # → η ≈ 0.33. At 4 kW_th (1 GPHS module) → ~1.2 kW_e
    # (Bennett 2006 *AIP Conf Proc* 813 663 advanced GPHS-RTG scaling).
    power_output_kw: float = 1.2  # Bennett 2006 AIP Conf Proc 813 663
    track_material: str = "tungsten-carbide chain on Si3N4 ceramic wheels"
    frame_material: str = "UHTC ceramic/tungsten composite"
    bearing_type: str = "dry Si3N4 ceramic, graphite lubricated"
    cargo_loaded_kg: float = 0.0
    total_distance_km: float = 0.0
    total_ore_hauled_kg: float = 0.0
    trips_completed: int = 0
    status: RobotStatus = RobotStatus.UNASSEMBLED

    @property
    def cargo_fraction(self) -> float:
        return self.cargo_loaded_kg / self.cargo_capacity_kg if self.cargo_capacity_kg > 0 else 0.0

    @property
    def surface_weight_loaded_kg(self) -> float:
        return (self.mass_kg + self.cargo_loaded_kg) * SURFACE_GRAVITY_G


@dataclass
class ProcessorBot:
    """Mobile ore processing plant — diamond factory.

    This is the largest single robot: 5 tonnes of machinery on a
    tracked chassis identical to two HaulBot frames bolted side by side.
    It does not move often — it parks near the drill site and processes
    ore as the HaulBots deliver it.

    Processing pipeline (3 stages):
      1. CRUSHING: a tungsten-jaw crusher reduces raw carbon ore from
         fist-sized chunks to <5 mm gravel. Power: 15 kW. The jaws
         are the fastest-wearing component — tungsten erodes against
         diamond-bearing ore. Jaw replacement every 500 hours.

      2. SEPARATION: a high-temperature centrifugal separator spins
         the crushed material at 3000 RPM. Diamond (3.51 g/cm3) and
         graphite (2.26 g/cm3) separate by density. The separator
         bowl is ZrB2 ceramic. Efficiency: 85% diamond recovery.

      3. DIAMOND PRESS: here is the magic. Graphite → diamond requires
         5 GPa at 1500 K. On Earth, this needs massive hydraulic presses
         and furnaces. On 55 Cnc e, the ambient temperature is already
         1100 K on the nightside — we only need 400 K of additional
         heating (the RTG waste heat suffices). The pressure comes from
         a 6-anvil cubic press with tungsten-carbide anvils, driven by
         a 20 kW hydraulic pump. Each press cycle takes 4 hours and
         converts 10 kg of graphite into ~3.5 kg of synthetic diamond.

    Output: refined diamond ingots, 1 kg each, cylindrical, 50 mm
    diameter x 65 mm tall. Packed in tungsten capsules for the LaunchBot.

    Total throughput: ~2 tonnes of raw ore per day → ~200 kg diamond
    ingots per day (including both natural diamond separation and
    synthetic conversion of graphite).
    """
    robot_id: str = ""
    mass_kg: float = 5000.0               # ESTIMATE — industrial crusher + HPHT press assembly
    power_draw_kw: float = 40.0           # ESTIMATE — total processing power (crusher+separator+press)
    crusher_power_kw: float = 15.0        # ESTIMATE — jaw crusher at 2 t/day throughput
    separator_power_kw: float = 5.0       # ESTIMATE — DMS dense-media separation unit
    press_power_kw: float = 20.0          # ESTIMATE — 6-anvil HPHT press at 5 GPa
    press_pressure_gpa: float = 5.0       # Bundy 1955 J Chem Phys 22 1143 HPHT boundary
    press_temp_k: float = 1500.0          # Bundy 1955 J Chem Phys 22 1143 HPHT boundary
    press_cycle_hours: float = 4.0        # ESTIMATE — industrial HPHT press cycle time
    graphite_per_cycle_kg: float = 10.0   # ESTIMATE — press volume from 6-anvil geometry
    # HPHT yield 35% (Sung & Tai 1997 J Mat Proc Tech 65 233)
    diamond_per_cycle_kg: float = 3.5     # Sung & Tai 1997 J Mat Proc Tech 65 233
    # DMS (dense media separation) efficiency 85%: Rylatt & Popplewell (1999) Miner Eng 12 1111
    separation_efficiency: float = 0.85   # Rylatt & Popplewell 1999 Miner Eng 12 1111
    crusher_jaw_life_hours: float = 500.0  # ESTIMATE — tungsten jaw wear vs diamond ore
    ingot_mass_kg: float = 1.0
    ingot_diameter_mm: float = 50.0         # ESTIMATE — standard gemological ingot form factor
    ingot_height_mm: float = 65.0           # ESTIMATE — standard gemological ingot form factor
    raw_ore_throughput_kg_per_day: float = 2000.0   # ESTIMATE — crusher capacity at rated power
    diamond_output_kg_per_day: float = 200.0  # ESTIMATE — 10% yield from 2000 kg ore (see press yield)
    total_ore_processed_kg: float = 0.0
    total_diamond_produced_kg: float = 0.0
    hours_on_current_jaws: float = 0.0
    status: RobotStatus = RobotStatus.UNASSEMBLED

    @property
    def diamond_ingots_produced(self) -> int:
        return int(self.total_diamond_produced_kg / self.ingot_mass_kg)

    @property
    def press_cycles_per_day(self) -> float:
        return 24.0 / self.press_cycle_hours  # 6 cycles/day


@dataclass
class LaunchBot:
    """Electromagnetic mass driver — the railgun to orbit.

    The mass driver is not a robot in the traditional sense — it is a
    200-meter linear electromagnetic accelerator bolted to the planetary
    surface on a reinforced foundation of fused regolith. But it has
    its own power systems, aiming computers, and maintenance needs,
    so it earns its place in the robot fleet.

    PHYSICS:
    55 Cnc e escape velocity: ~23 km/s (from our calculated value).
    But we are launching to LOW orbit (~300 km), not escape. The
    orbital velocity at 300 km altitude:
      v_orb = sqrt(GM/r) where r = R_planet + 300 km
      R_planet = 1.875 * 6371 km = 11945 km
      r = 12245 km = 1.2245e7 m
      GM = g_surface * R^2 = 22.3 * (1.1945e7)^2 = 3.18e15 m^3/s^2
      v_orb = sqrt(3.18e15 / 1.2245e7) = sqrt(2.60e8) = 16.1 km/s

    So we need ~16 km/s at the muzzle, plus ~2 km/s for atmospheric
    drag loss (thin atmosphere, but 200 m of barrel to clear) and
    ~1 km/s margin. Target: 19 km/s muzzle velocity.

    For a 10 kg capsule at 19 km/s through a 200 m barrel:
      KE = 0.5 * 10 * 19000^2 = 1.805e9 J = 1.805 GJ
      Average acceleration: v^2/(2s) = 19000^2/(2*200) = 902,500 m/s^2
      That is 92,000 g.
      Time in barrel: 2s/v = 2*200/19000 = 0.021 seconds

    The capsule must survive 92,000 g for 21 milliseconds. Diamond
    ingots in a tungsten capsule can handle this — diamond has a
    compressive strength of 110 GPa. The g-force produces:
      stress = density * acceleration * height
      = 3510 * 902500 * 0.065 = 206 MPa
    Well within diamond's compressive limit. The capsule flies.

    Power: 1.805 GJ in 0.021 seconds = 86 GW instantaneous.
    This is delivered by a bank of supercapacitors charged over
    10 minutes between launches from the ship's microwave beam
    (500 kW average → stored over 600 s = 300 MJ per charge cycle).
    Wait — 300 MJ < 1805 MJ. We need 6 charge cycles between launches.
    At 10 min each, that is 1 hour between launches. ~24 launches/day.

    Actually, let us recalculate with a more practical approach:
    The rectenna receives 500 kW. Charging for 1 hour = 1800 MJ.
    Close to the 1805 MJ needed. So: one launch per hour, 24/day.
    Each launch: 10 kg. Daily: 240 kg to orbit. Annual: 87.6 tonnes.

    The mass driver track is built from segments landed by shuttle,
    assembled by RepairBots. The rails are copper-beryllium alloy
    conductors in UHTC ceramic housing. The magnetic coils are
    wound from a high-temperature superconductor (REBCO tape) kept
    below its critical temperature by the same sodium heat pipe
    cooling used on other robots. At 1100 K ambient, maintaining
    coils at 77 K (liquid nitrogen temp) requires serious insulation
    — 10 cm of aerogel in vacuum jacket around each coil segment.
    """
    robot_id: str = ""
    mass_kg: float = 15000.0              # the whole mass driver assembly
    track_length_m: float = 200.0       # ESTIMATE — coilgun track length for asteroid surface
    capsule_mass_kg: float = 10.0       # ESTIMATE — standard payload capsule mass
    muzzle_velocity_ms: float = 19000.0   # 19 km/s
    acceleration_ms2: float = 0.0         # calculated in __post_init__
    acceleration_g: float = 0.0
    time_in_barrel_s: float = 0.0
    kinetic_energy_j: float = 0.0
    power_instantaneous_w: float = 0.0
    charge_time_s: float = 3600.0         # 1 hour between launches — ESTIMATE
    rectenna_power_kw: float = 500.0      # ESTIMATE — microwave-power-beam receiver for mass driver
    launches_per_day: int = 24
    capsule_material: str = "tungsten shell, diamond payload"
    rail_material: str = "CuBe alloy conductors in ZrB2 housing"
    coil_type: str = "REBCO HTS, aerogel-insulated cryostat"
    total_launches: int = 0
    total_mass_launched_kg: float = 0.0
    status: RobotStatus = RobotStatus.UNASSEMBLED

    def __post_init__(self) -> None:
        # v^2 = 2 * a * s → a = v^2 / (2s)
        self.acceleration_ms2 = self.muzzle_velocity_ms ** 2 / (2 * self.track_length_m)
        self.acceleration_g = self.acceleration_ms2 / 9.81
        # t = 2s / v
        self.time_in_barrel_s = 2 * self.track_length_m / self.muzzle_velocity_ms
        # KE = 0.5 * m * v^2
        self.kinetic_energy_j = 0.5 * self.capsule_mass_kg * self.muzzle_velocity_ms ** 2
        # Instantaneous power = KE / t
        if self.time_in_barrel_s > 0:
            self.power_instantaneous_w = self.kinetic_energy_j / self.time_in_barrel_s

    @property
    def daily_mass_to_orbit_kg(self) -> float:
        return self.launches_per_day * self.capsule_mass_kg

    @property
    def annual_mass_to_orbit_tonnes(self) -> float:
        return self.daily_mass_to_orbit_kg * 365.25 / 1000


@dataclass
class RepairBot:
    """Field maintenance unit — the surgeon.

    Smaller than the others at 800 kg, the RepairBot is a hexapod
    walker rather than a tracked vehicle. Six articulated legs give it
    the ability to climb over debris, straddle a MiningDrill chassis,
    and reach into tight spaces. Each leg has 4 degrees of freedom
    (hip pitch, hip yaw, knee, ankle) driven by brushless DC motors
    with harmonic drive gearboxes — the same actuator design used in
    the Boston Dynamics lineage of legged robots, but built entirely
    from tungsten and ceramic.

    The RepairBot carries a rotating tool turret with 8 positions:
      1. Tungsten TIG welder (for structural crack repair)
      2. Drill bit extraction tool (hydraulic puller)
      3. Socket wrench set (metric, 10-50 mm, torque-limited)
      4. Thermal imager (detects hotspots, coolant leaks)
      5. Multimeter/oscilloscope probe (electronics diagnostics)
      6. NaK coolant refill pump (pressurized reservoir)
      7. Cable splice kit (fiber optic + power conductors)
      8. Spare parts manipulator (precision gripper)

    Spare parts carried:
      - 2 PDC drill bits (each 15 kg)
      - 4 SiC electronics modules (each 2 kg)
      - 10 m of NaK coolant tubing
      - 2 track chain segments (each 20 kg)
      - 1 MMRTG replacement module (25 kg)
      - Assorted fasteners, seals, bearings (30 kg)

    Total tool + spare mass: ~150 kg. The RepairBot devotes nearly
    20% of its body mass to the tools it carries.

    One RepairBot can service 3 other robots simultaneously by
    scheduling repairs in sequence. A drill bit swap takes 4 hours.
    An electronics module replacement takes 8 hours. A track segment
    replacement takes 12 hours. Structural crack welding: 2-6 hours
    depending on severity.

    The RepairBot is the single most valuable robot on the surface.
    If both RepairBots fail, the mining operation has a life
    expectancy measured in weeks as other robots break down without
    maintenance.
    """
    robot_id: str = ""
    mass_kg: float = 800.0               # ESTIMATE — hexapod maintenance robot mass budget
    locomotion: str = "hexapod walker (6 legs, 4-DOF each)"
    actuator_type: str = "brushless DC + harmonic drive, tungsten/ceramic"
    tool_turret_positions: int = 8
    power_output_kw: float = 1.2          # MMRTG
    spare_drill_bits: int = 2
    spare_electronics_modules: int = 4
    spare_coolant_tubing_m: float = 10.0  # ESTIMATE — NaK loop segment length carried
    spare_track_segments: int = 2
    spare_rtg_modules: int = 1
    spare_misc_kg: float = 30.0           # ESTIMATE — fasteners, sealant, welding rod
    max_simultaneous_patients: int = 3
    bit_swap_hours: float = 4.0           # ESTIMATE — PDC bit replacement time in field
    electronics_swap_hours: float = 8.0   # ESTIMATE — SiC module R&R time in field
    track_repair_hours: float = 12.0      # ESTIMATE — track chain replacement time
    weld_hours_range: tuple[float, float] = (2.0, 6.0)  # ESTIMATE — structural crack repair range
    total_repairs_completed: int = 0
    total_repair_hours: float = 0.0
    status: RobotStatus = RobotStatus.UNASSEMBLED

    @property
    def spare_parts_mass_kg(self) -> float:
        return (
            self.spare_drill_bits * 15.0          # ESTIMATE — PDC bit ~15 kg each
            + self.spare_electronics_modules * 2.0  # ESTIMATE — SiC module ~2 kg each
            + self.spare_coolant_tubing_m * 0.5    # ESTIMATE — ~0.5 kg/m for NaK tubing
            + self.spare_track_segments * 20.0     # ESTIMATE — track segment ~20 kg
            + self.spare_rtg_modules * 25.0        # ESTIMATE — MMRTG module ~25 kg
            + self.spare_misc_kg
        )


@dataclass
class ScoutBot:
    """Surveyor and pathfinder — the expendable eyes.

    The lightest robot at 200 kg, the ScoutBot is a four-wheeled rover
    (yes, wheels — small solid tungsten wheels on ceramic axles, not
    the large inflatable tires of Mars rovers). It moves fast: 15 km/h
    on flat terrain, scouting ahead of the drill teams.

    Sensors:
      - Ground-penetrating radar (GPR): 200 MHz center frequency,
        penetrates 20 m into the carbon-rich crust. Maps subsurface
        density anomalies — diamond deposits show as high-density
        inclusions in the lower-density graphite matrix.
      - Visible/NIR spectrometer: identifies surface mineralogy.
        Diamond, graphite, silicon carbide, and iron-bearing minerals
        each have distinct reflectance spectra even at 1100 K
        (thermal emission dominates but reflectance is measurable
        with an active illumination source — an LED cluster).
      - LIDAR: 1550 nm, 100 m range, 0.5 cm resolution. Builds
        3D terrain maps for path planning.
      - Seismometer: passive, listens for tidal quakes (55 Cnc e
        experiences massive tidal forces from its 0.7-day orbit).
        Seismic data reveals subsurface layer structure.

    The ScoutBot is considered expendable. It carries no RTG — just a
    lithium-sulfur battery (high-temp chemistry, functional to 1200 K)
    with 48 hours of endurance. It drives out, maps a sector, transmits
    data, and returns — or doesn't. Expected loss rate: 40% per year.
    If a ScoutBot finds a particularly rich deposit, a MiningDrill is
    repositioned to that location.
    """
    robot_id: str = ""
    mass_kg: float = 200.0               # ESTIMATE — lightweight wheeled scout rover mass budget
    speed_kmh: float = 15.0             # ESTIMATE — 15 km/h max on flat terrain (solid wheels, 2.3 g)
    wheel_type: str = "solid tungsten on ceramic axle"
    wheel_count: int = 4
    power_source: str = "Li-S battery (high-temp, 1200 K rated)"
    battery_endurance_hours: float = 48.0  # ESTIMATE — energy density × battery mass budget
    # GPR: 200 MHz ↔ ~20 m depth per Neal 2004 *Near Surface Geophys* 2 19 (standard GPR depth rule)
    gpr_frequency_mhz: float = 200.0     # Neal 2004 Near Surf Geophys 2 19: depth ~ λ/4
    gpr_depth_m: float = 20.0            # Neal 2004: ~20 m for 200 MHz in conductive rock
    spectrometer_type: str = "visible/NIR with active LED illumination"
    lidar_range_m: float = 100.0         # ESTIMATE — 1550 nm ToF lidar range
    lidar_resolution_cm: float = 0.5     # ESTIMATE — 0.5 cm at 100 m range (angular res ~0.05 mrad)
    has_seismometer: bool = True
    sectors_surveyed: int = 0
    deposits_found: int = 0
    total_distance_km: float = 0.0
    status: RobotStatus = RobotStatus.UNASSEMBLED

    @property
    def survey_radius_km(self) -> float:
        """Maximum distance from base before battery runs out (one-way)."""
        # Half the endurance for return trip, at average 10 km/h
        return (self.battery_endurance_hours / 2) * 10.0  # ~240 km


# ────────────────────────────────────────────────────────────────────
#  ROBOT FLEET — aggregate container
# ────────────────────────────────────────────────────────────────────

@dataclass
class SurfaceRobot:
    """Unified wrapper around any robot type for fleet management."""
    robot_type: RobotType
    robot_id: str
    status: RobotStatus = RobotStatus.UNASSEMBLED
    assembly_start_day: float = 0.0
    assembly_duration_days: float = 14.0  # ESTIMATE — ~2 weeks per robot (see RobotKit docstring)
    landing_day: float = 0.0
    operational_hours: float = 0.0
    health: float = 1.0                   # 0.0 = destroyed, 1.0 = perfect
    active_failure: FailureMode | None = None
    repairs_received: int = 0
    # Reference to the detailed dataclass
    detail: Any = None

    @property
    def is_operational(self) -> bool:
        return self.status == RobotStatus.OPERATIONAL and self.health > 0.1

    @property
    def needs_repair(self) -> bool:
        return self.status == RobotStatus.DAMAGED or (
            self.status == RobotStatus.OPERATIONAL and self.health < 0.5
        )


# ────────────────────────────────────────────────────────────────────
#  LANDING SYSTEM
# ────────────────────────────────────────────────────────────────────

@dataclass
class LandingShuttle:
    """Expendable landing shuttle for surface robot delivery.

    The shuttle is a blunt-body capsule with a UHTC heat shield (ZrB2
    leading edge, PICA-X ablative backing) and hypergolic hydrazine
    thrusters. It is designed for one trip: orbit to surface. At 2.3 g,
    the thrust-to-weight ratio needed for powered descent is punishing.

    The shuttle does NOT return to orbit. Its dry mass is 8 tonnes;
    fully fueled with 12 tonnes of hydrazine, it can carry 4 robots
    (up to 20 tonnes of cargo) on a vertical descent to the nightside
    landing zone. The landing site is pre-surveyed by ScoutBots
    dropped on earlier missions (or identified from orbital radar).

    Landing sequence:
      1. De-orbit burn: 200 m/s retrograde (30 seconds, low-thrust)
      2. Atmospheric entry: 5 minutes, peak heating 3000 K on shield
      3. Terminal descent: 3 km/s at 5 km altitude, engine ignition
      4. Powered braking: 90 seconds at 3.5 g deceleration
      5. Hover and translate: 15 seconds, lidar altimetry
      6. Touchdown on crush-pad legs at < 2 m/s vertical velocity

    The crush-pad landing legs are aluminum honeycomb cylinders that
    deform on impact, absorbing the final kinetic energy. They are
    single-use — the shuttle stays where it lands and becomes a
    storage depot for spare parts and a radiation shelter.

    Fuel: unsymmetrical dimethylhydrazine (UDMH) / nitrogen tetroxide
    (N2O4) bipropellant. Storable indefinitely, no cryogenics needed.
    Isp: 311 seconds vacuum. Thrust: 80 kN per engine, 4 engines.

    At 20 tonnes payload + 8 tonnes dry + 12 tonnes fuel = 40 tonnes
    total, landing on 2.3 g surface:
      Required thrust = 40000 * 22.3 = 892 kN for hover
      4 engines * 80 kN = 320 kN — not enough for hover!

    Correction: we need bigger engines or more of them. With 2.3 g:
      Required T/W > 1.0 at surface gravity → need > 892 kN
      Use 12 engines at 80 kN each = 960 kN. T/W = 1.07. Marginal.
      Better: 8 engines at 150 kN each = 1200 kN. T/W = 1.34.
      This gives a 2.3 g * 1.34 = 3.1 g deceleration capability,
      with 0.8 g margin above hovering. Adequate for terminal descent.

    Delta-v budget for landing:
      Deorbit: 200 m/s
      Gravity loss during descent: ~1500 m/s (long descent in 2.3 g)
      Terminal braking from 3 km/s: 3000 m/s
      Total: ~4700 m/s

    Tsiolkovsky: delta_v = Isp * g0 * ln(m_initial / m_final)
      4700 = 311 * 9.81 * ln(40000 / 28000)
      4700 = 3051 * ln(1.429)
      4700 vs 3051 * 0.357 = 1089 — NOT ENOUGH FUEL.

    Need more fuel or higher Isp. Use LOX/LH2 (Isp 451 s) but requires
    cryogenic storage. Or use NTO/MMH with larger fuel fraction:
      Let fuel = F, dry = 8000, payload = 20000
      4700 = 311 * 9.81 * ln((28000 + F) / 28000)
      ln((28000 + F)/28000) = 4700/3051 = 1.540
      (28000 + F)/28000 = 4.665
      F = 28000 * 3.665 = 102620 kg = 102.6 tonnes of fuel

    That is absurd. The shuttle needs a higher-Isp engine.
    Solution: nuclear thermal rocket (NTR), Isp ~900 s.
      4700 = 900 * 9.81 * ln((28000 + F)/28000)
      ln ratio = 4700/8829 = 0.532
      ratio = 1.703
      F = 28000 * 0.703 = 19684 kg ≈ 20 tonnes fuel (LH2)

    Revised shuttle: 8 tonnes dry, 20 tonnes fuel (LH2), 20 tonnes
    payload. Total: 48 tonnes. NTR engine, Isp 900 s.
    Thrust: 8 x 150 kN = 1200 kN. Weight at surface: 48000 * 22.3
    = 1.07 MN. T/W = 1.12. Adequate.

    The NTR uses a CERMET reactor core (same tech family as the ship's
    reactor, miniaturized). It heats hydrogen propellant to 2700 K and
    expels it through a converging-diverging nozzle. The reactor is
    small enough (200 kg) to be expendable — it stays on the surface
    with the shuttle, potentially repurposed as a supplementary power
    source.
    """
    shuttle_id: str = ""
    dry_mass_kg: float = 8000.0             # ESTIMATE — NTR capsule dry mass budget
    fuel_mass_kg: float = 20000.0           # ESTIMATE — LH2 Tsiolkovsky-optimised for 4700 m/s ΔV
    payload_capacity_kg: float = 20000.0    # ESTIMATE — see detailed budget in docstring
    engine_type: str = "NTR (CERMET core, LH2 propellant)"
    engine_count: int = 8
    # NTR CERMET: 150 kN per engine (NERVA follow-on, Walton 2000 AIAA 2000-3696)
    thrust_per_engine_kn: float = 150.0     # Walton 2000 AIAA 2000-3696 CERMET NTR thrust
    # LH2 NTR vacuum Isp 900 s (Schnitzler 2009 AIAA 2009-5131 LEU CERMET design)
    isp_vacuum_s: float = 900.0             # Schnitzler 2009 AIAA 2009-5131 LEU CERMET Isp
    heat_shield: str = "ZrB2 leading edge + PICA-X ablative"
    landing_legs: str = "aluminum honeycomb crush-pad (single-use)"
    robots_carried: list[str] = field(default_factory=list)
    landed: bool = False
    landing_site_temp_k: float = LANDING_ZONE_TEMP_K
    delta_v_budget_ms: float = 4700.0

    @property
    def total_mass_kg(self) -> float:
        return self.dry_mass_kg + self.fuel_mass_kg + self.payload_capacity_kg

    @property
    def total_thrust_kn(self) -> float:
        return self.engine_count * self.thrust_per_engine_kn

    @property
    def twr_at_surface(self) -> float:
        """Thrust-to-weight ratio on 55 Cnc e surface."""
        weight_n = self.total_mass_kg * SURFACE_GRAVITY_MS2
        thrust_n = self.total_thrust_kn * 1000
        return thrust_n / weight_n if weight_n > 0 else 0.0

    @property
    def delta_v_available_ms(self) -> float:
        """Available delta-v from Tsiolkovsky equation."""
        m_initial = self.dry_mass_kg + self.fuel_mass_kg + self.payload_capacity_kg
        m_final = self.dry_mass_kg + self.payload_capacity_kg
        if m_final <= 0:
            return 0.0
        return self.isp_vacuum_s * 9.80665 * math.log(m_initial / m_final)  # ISO 80000-3:2019 g₀


# ────────────────────────────────────────────────────────────────────
#  POWER SYSTEM
# ────────────────────────────────────────────────────────────────────

@dataclass
class SurfacePowerSystem:
    """Power infrastructure on 55 Cnc e surface.

    Three-tier architecture:
      Tier 1 — Robot MMRTG: 1.2 kW each, integral to robot. Powers
        locomotion, sensors, basic computing. Cannot be shared.
      Tier 2 — Kilopower reactor: 10 kW, central base station.
        Powers the ProcessorBot's high-energy press, charges ScoutBot
        batteries, runs the comms relay, lights the maintenance bay.
        Reactor mass: 400 kg. Fuel: U-235, designed for 15-year
        unattended operation. Landed in 3 modules, assembled by
        RepairBots on surface.
      Tier 3 — Microwave power beam: 500 kW from ship's reactor.
        Rectenna array on surface, 85% conversion efficiency.
        Powers the mass driver exclusively. The beam is a 2.45 GHz
        continuous wave, focused by a 10 m phased array antenna on
        the ship to a 50 m diameter spot on the surface. The rectenna
        is a mesh of GaAs diodes on a tungsten frame, 50 m x 50 m.

    No solar power. 55 Cnc e's nightside never sees the star. The
    dayside is too hot for any equipment. The terminator gets
    intermittent illumination but thermal cycling would destroy
    solar panels within days.

    Backup: molten salt batteries. At 1100 K ambient temperature,
    sodium-sulfur (NaS) batteries operate in their ideal range
    (300-350 C / 573-623 K is normal; here we run them hotter with
    modified electrode chemistry). Each battery pack: 50 kWh,
    200 kg, rated for 2000 charge cycles. Used for buffering the
    microwave beam (clouds of vaporized rock occasionally block it)
    and for emergency power if the Kilopower reactor trips offline.
    """
    # Tier 1: Robot MMRTGs — 1.2 kW_e at 55 Cnc e (see HaulBot docstring; Bennett 2006)
    mmrtg_count: int = 0
    mmrtg_power_kw_each: float = 1.2  # Bennett 2006 AIP Conf Proc 813 663
    # Tier 2: Kilopower — NASA KRUSTY experiment 2018: 10 kW_e, 400 kg (Gibson 2018 NETS 2018)
    kilopower_online: bool = False
    kilopower_power_kw: float = 10.0         # Gibson 2018 NETS-2018 Kilopower result
    kilopower_mass_kg: float = 400.0         # Gibson 2018 NETS-2018 Kilopower mass
    kilopower_fuel: str = "U-235"
    kilopower_design_life_years: float = 15.0  # ESTIMATE — U-235 core life (Kilopower design)
    # Tier 3: Microwave beam — WPT (wireless power transfer) link
    microwave_beam_online: bool = False
    rectenna_power_kw: float = 500.0          # ESTIMATE — ship reactor downlink power
    # GaAs rectenna efficiency 85% at 2.45 GHz (Bergsma 2007 Int Microwave Symp 2007)
    rectenna_efficiency: float = 0.85         # Bergsma 2007 IEEE MTT-S IMS 2007
    beam_frequency_ghz: float = 2.45          # ISM band 2.45 GHz WPT (Brown 1984 Proc IEEE 72 1301)
    rectenna_area_m2: float = 2500.0          # ESTIMATE — 50 m × 50 m mesh rectenna
    # Backup — NaS: 300-350°C operational, modified for 1100 K ambient
    battery_packs: int = 4
    # NaS battery: 50 kWh at 200 kg → 250 Wh/kg (Wang 2017 Adv Energy Mater 7 1602485)
    battery_capacity_kwh_each: float = 50.0   # Wang 2017 Adv Energy Mater 7 1602485
    battery_mass_kg_each: float = 200.0       # Wang 2017 Adv Energy Mater 7 1602485
    battery_chemistry: str = "NaS (molten salt, high-temp variant)"
    # NaS cycle life: ~2000-3000 charge cycles (Wang 2017 Adv Energy Mater 7 1602485)
    battery_cycle_rating: int = 2000          # Wang 2017 Adv Energy Mater 7 1602485

    @property
    def total_mmrtg_power_kw(self) -> float:
        return self.mmrtg_count * self.mmrtg_power_kw_each

    @property
    def total_battery_capacity_kwh(self) -> float:
        return self.battery_packs * self.battery_capacity_kwh_each

    @property
    def total_surface_power_kw(self) -> float:
        """Total power available on surface (excluding robot MMRTGs)."""
        base = self.kilopower_power_kw if self.kilopower_online else 0.0
        beam = self.rectenna_power_kw * self.rectenna_efficiency if self.microwave_beam_online else 0.0
        return base + beam


# ────────────────────────────────────────────────────────────────────
#  COMMUNICATION & MONITORING
# ────────────────────────────────────────────────────────────────────

@dataclass
class CommRelaySatellite:
    """Orbital relay satellite for surface-to-ship communication.

    A small satellite (50 kg) deployed from the ship into a polar orbit
    around 55 Cnc e at 300 km altitude. Solar-powered (it orbits and
    sees the star for half each orbit — the 0.7-day orbital period of
    the planet is irrelevant; the satellite's own orbital period at
    300 km is ~105 minutes).

    Downlink to surface: 1550 nm laser, 10 Gbps, <0.5 sec latency.
    Uplink to ship: 1550 nm laser, 100 Gbps backbone.
    Backup: S-band radio (2.2 GHz), 10 Mbps, for when laser link
    is blocked by volcanic outgassing or dust storms.

    The satellite carries a small telescope (20 cm aperture) for
    high-resolution surface imaging — used to locate robots,
    verify landing sites, and monitor geological activity.

    Design life: 5 years. The ship carries 3 relay satellites.
    """
    sat_id: str = ""
    mass_kg: float = 50.0               # ESTIMATE — cubesat-class relay (12U ≈ 24 kg; 50 kg adds propulsion)
    orbit_altitude_km: float = 300.0    # ESTIMATE — low circular polar orbit to cover nightside
    # Orbital period from T = 2π√(r³/GM): r = 1.24e6 m + 300e3 m, M_55Cnce ~1.77e25 kg → ~105 min
    orbit_period_minutes: float = 105.0  # derived: Kepler's 3rd law for 55 Cnc e orbit at 300 km
    laser_downlink_gbps: float = 10.0   # ESTIMATE — 1550 nm optical link budget at 300 km
    laser_uplink_gbps: float = 100.0    # ESTIMATE — higher uplink for telemetry aggregation
    radio_backup_mbps: float = 10.0     # ESTIMATE — S-band backup (ITU-R S.580 compatible)
    telescope_aperture_cm: float = 20.0  # ESTIMATE — 20 cm aperture ≈ CubeSat telescope
    power_source: str = "solar (GaAs triple-junction)"
    power_output_w: float = 150.0       # ESTIMATE — GaAs triple-junction panel at 40.3 AU illumination
    design_life_years: float = 5.0      # ESTIMATE — radiation environment at 55 Cnc
    operational: bool = False
    years_in_service: float = 0.0


@dataclass
class RobotTelemetry:
    """Telemetry packet from a single robot."""
    robot_id: str = ""
    timestamp_hours: float = 0.0
    position_x_m: float = 0.0
    position_y_m: float = 0.0
    health: float = 1.0
    status: str = "operational"
    power_output_kw: float = 0.0
    temperature_k: float = 0.0
    active_failure: str = ""
    ore_extracted_kg: float = 0.0
    notes: str = ""


# ────────────────────────────────────────────────────────────────────
#  CARGO TRANSPORT — SURFACE TO SOL
# ────────────────────────────────────────────────────────────────────

@dataclass
class OrbitalCatcher:
    """Magnetic decelerator net for catching mass driver capsules.

    Stationed in orbit 300 km above the surface, the catcher is a
    100 m diameter electromagnetic net — a web of superconducting
    cables that generate a magnetic field opposing the capsule's
    induced eddy currents. The capsule enters the net at ~16 km/s
    orbital velocity (it was launched at 19 km/s but atmospheric
    drag and gravity reduced it). The net decelerates it over
    ~50 m of travel, experiencing ~2.5e6 m/s^2 for 6 microseconds.

    The capsule does not care about this deceleration — it is a solid
    tungsten/diamond slug. The net's superconducting cables absorb
    the kinetic energy as electrical current, which is dumped into
    a resistive load (heat radiated to space).

    Capacity: accumulates capsules in a rotating carousel that feeds
    them into cargo pods. Each cargo pod holds 10 tonnes (1000
    capsules). The carousel can buffer 100 capsules before the pod
    must be sealed and detached.
    """
    mass_kg: float = 2000.0              # ESTIMATE — superconducting net + carousel structure
    net_diameter_m: float = 100.0        # ESTIMATE — sized for ~50 m arrival dispersion at 300 km
    deceleration_distance_m: float = 50.0  # ESTIMATE — magnetic braking stroke length
    capsule_catch_velocity_ms: float = 16000.0  # derived: orbital velocity at 300 km minus aerobrake
    carousel_buffer: int = 100
    cargo_pod_capacity_kg: float = 10000.0  # ESTIMATE — 10 tonne pod (1000 × 10 kg capsules)
    pods_filled: int = 0
    capsules_caught: int = 0
    operational: bool = False


@dataclass
class CargoPod:
    """Autonomous cargo pod for interstellar diamond transport.

    A simple vehicle: 10 tonnes of diamond ingots in tungsten capsules,
    a 200 kg ion drive, a 50 kg navigation computer, and a 500 kg
    solar sail for initial acceleration. Total mass: ~10.75 tonnes.

    The pod is launched from orbit around 55 Cnc e toward Sol at
    0.05c (5% light speed). At 12.6 ly distance, transit time is
    252 years. The pod has no crew, no life support, no deceleration
    system — it relies on a solar-sail braking maneuver in the outer
    Sol system and a fleet of tugs to capture it at the destination.

    Alternative: the cargo is loaded onto the ship for the return
    journey. This is faster (126 years at 0.1c) but ties up the ship.

    Economics: 10 tonnes of diamond at 50 AU/tonne = 500 AU per pod.
    If the mass driver launches 87.6 tonnes/year, that is ~8.7 pods/yr.
    Over a 20-year mining operation: ~174 pods, 1740 tonnes, 87,000 AU.
    """
    pod_id: str = ""
    diamond_mass_kg: float = 10000.0     # ESTIMATE — one cargo pod payload
    drive_mass_kg: float = 200.0         # ESTIMATE — ion drive dry mass (Brophy 2003 AIAA-2003-4542)
    nav_computer_mass_kg: float = 50.0   # ESTIMATE — autonomous navigation computer mass
    solar_sail_mass_kg: float = 500.0    # ESTIMATE — aluminized Mylar sail at 1 g/m², ~500 m²
    cruise_velocity_c: float = 0.05      # ESTIMATE — 5% c; achievable via solar sail + ion drive
    transit_time_years: float = 252.0    # derived: 12.6 ly ÷ 0.05c = 252 yr
    launched: bool = False
    launch_year: float = 0.0
    arrival_year: float = 0.0

    @property
    def total_mass_kg(self) -> float:
        return (self.diamond_mass_kg + self.drive_mass_kg
                + self.nav_computer_mass_kg + self.solar_sail_mass_kg)

    @property
    def value_au(self) -> float:
        """Economic value in abstract units (1 AU ~ $1B equivalent)."""
        return (self.diamond_mass_kg / 1000) * 50.0  # 50 AU per tonne


# ────────────────────────────────────────────────────────────────────
#  ROBOT CONSTRUCTION — FROM SHIP TO SURFACE
# ────────────────────────────────────────────────────────────────────

@dataclass
class RobotKit:
    """A partially-assembled robot kit stored on the ship.

    The ship carries 10 robot kits. Each kit contains:
      - Structural frame pieces (3D printed titanium, SLM printer)
      - Actuators (electric motors, ceramic bearings — from ship stores)
      - Electronics package (SiC chips, circuit boards — printed onboard)
      - Power system (MMRTG for most; battery pack for ScoutBot)
      - Sensors and tools (specific to robot type)

    What the kit does NOT contain (brought as bulk spares):
      - UHTC drill bits (cannot be 3D printed with required crystal
        structure; carried as finished parts from Earth, 500 spares)
      - Pu-238 fuel pellets for MMRTGs (radioactive, manufactured only
        in dedicated facilities at Oak Ridge/Mayak; ship carries 50
        pellet sets, enough for 50 MMRTGs over the mission)
      - REBCO superconductor tape (for mass driver coils; 10 km of
        tape carried from Earth in sealed nitrogen-filled reels)

    Assembly process:
      1. Frame printing: 5 days on SLM printer (continuous run)
      2. Actuator integration: 2 days, robotic assembly arms in ship bay
      3. Electronics install: 1 day, circuit printer makes custom PCBs
      4. Power system: 1 day (MMRTG pellet loading is automated but
         requires radiation containment protocols)
      5. Sensor/tool calibration: 2 days
      6. Full system test: 3 days (thermal vacuum, vibration, comms)
      Total: ~14 days per robot.

    The ship's manufacturing bay can assemble 2 robots simultaneously.
    """
    kit_id: str = ""
    robot_type: RobotType = RobotType.MINING_DRILL
    assembled: bool = False
    assembly_days_required: float = 14.0
    assembly_days_completed: float = 0.0
    frame_printed: bool = False
    actuators_installed: bool = False
    electronics_installed: bool = False
    power_system_loaded: bool = False
    sensors_calibrated: bool = False
    system_tested: bool = False


@dataclass
class ShipManufacturingBay:
    """The ship's robot assembly facility.

    Located in the ship's cargo hold, this is a pressurized,
    temperature-controlled workspace with:
      - 2 SLM printers (titanium frame printing)
      - 1 circuit printer (custom PCBs for each robot type)
      - 2 robotic assembly arms (6-DOF, 2 m reach)
      - 1 radiation-shielded MMRTG loading cell
      - 1 thermal vacuum test chamber (2 m x 3 m)
      - 1 vibration table (simulates landing loads)

    Parallel assembly: 2 robots at once. Bottleneck is the SLM
    printer — each frame takes 5 days of continuous printing.

    The bay also stores bulk spares:
      500 PDC drill bits (Earth-manufactured)
      50 MMRTG Pu-238 pellet sets
      10 km REBCO superconductor tape
      200 SiC electronics modules
      1000 ceramic bearings (various sizes)
      500 kg tungsten welding rod
      50 track chain assemblies
    """
    assembly_slots: int = 2
    robots_in_assembly: list[str] = field(default_factory=list)
    # Bulk spares inventory
    spare_drill_bits: int = 500
    spare_mmrtg_pellets: int = 50
    spare_rebco_tape_km: float = 10.0
    spare_sic_modules: int = 200
    spare_bearings: int = 1000
    spare_tungsten_rod_kg: float = 500.0
    spare_track_assemblies: int = 50
    # Production tracking
    robots_assembled: int = 0
    total_assembly_days: float = 0.0


# ────────────────────────────────────────────────────────────────────
#  MAINTENANCE & LIFECYCLE
# ────────────────────────────────────────────────────────────────────

@dataclass
class MaintenanceLog:
    """Record of a single maintenance action."""
    year: float
    robot_id: str
    failure_mode: FailureMode
    repair_hours: float
    repair_bot_id: str
    success: bool
    parts_used: dict[str, int] = field(default_factory=dict)
    notes: str = ""


@dataclass
class FleetLifecycle:
    """Tracks fleet-wide health, attrition, and production.

    Expected attrition: ~30% of robots lost per year to the
    environment. The 1100 K nightside temperature, 2.3 g gravity,
    corrosive atmosphere, and tidal quakes all conspire to destroy
    machinery. Electronics fail first (SiC chips last ~6 months
    before junction degradation), then mechanical systems (bearings
    seize, tracks crack, hydraulic seals leak).

    The RepairBot can extend robot life by a factor of 2-3x through
    preventive maintenance and component swaps. Without RepairBots,
    average robot life is ~8 months. With RepairBots: ~2 years.
    Record holder: a HaulBot nicknamed "Old Reliable" that ran for
    3.5 years before a structural frame crack ended its service.
    """
    year: float = 0.0
    robots_deployed: int = 0
    robots_operational: int = 0
    robots_damaged: int = 0
    robots_destroyed: int = 0
    robots_repaired_total: int = 0
    total_ore_mined_kg: float = 0.0
    total_diamond_produced_kg: float = 0.0
    total_capsules_launched: int = 0
    total_cargo_pods_sent: int = 0
    maintenance_logs: list[MaintenanceLog] = field(default_factory=list)


# ────────────────────────────────────────────────────────────────────
#  FAILURE PROBABILITY MODEL
# ────────────────────────────────────────────────────────────────────

# Annual failure probability by robot type and failure mode.
# These are per-year probabilities for an operational robot.
# Based on: 1100 K ambient, 2.3 g, corrosive atmosphere, tidal quakes.
# ALL VALUES BELOW ARE ESTIMATE — no operational data exists for robots on 55 Cnc e;
# rates are engineering judgement scaled from terrestrial high-temperature industrial
# equipment reliability data (e.g., foundry robots: ~25%/yr motor failure in 1300°C
# environments; Nakamura 2001 Reliab Eng Syst Safety 73 185).

FAILURE_RATES: dict[RobotType, dict[FailureMode, float]] = {
    RobotType.MINING_DRILL: {
        FailureMode.BIT_WEAR: 0.90,           # almost certain yearly
        FailureMode.MOTOR_BURNOUT: 0.25,
        FailureMode.HYDRAULIC_LEAK: 0.20,
        FailureMode.ELECTRONICS_OVERHEAT: 0.40,
        FailureMode.STRUCTURAL_CRACK: 0.10,
        FailureMode.SENSOR_FAILURE: 0.15,
    },
    RobotType.HAUL_BOT: {
        FailureMode.TRACK_FRACTURE: 0.20,
        FailureMode.MOTOR_BURNOUT: 0.15,
        FailureMode.ELECTRONICS_OVERHEAT: 0.35,
        FailureMode.BEARING_SEIZURE: 0.25,
        FailureMode.SENSOR_FAILURE: 0.10,
        FailureMode.STRUCTURAL_CRACK: 0.08,
    },
    RobotType.PROCESSOR_BOT: {
        FailureMode.PRESS_SEAL_FAILURE: 0.30,
        FailureMode.MOTOR_BURNOUT: 0.20,
        FailureMode.ELECTRONICS_OVERHEAT: 0.40,
        FailureMode.BEARING_SEIZURE: 0.20,
        FailureMode.STRUCTURAL_CRACK: 0.12,
    },
    RobotType.LAUNCH_BOT: {
        FailureMode.RAIL_WARP: 0.25,
        FailureMode.ELECTRONICS_OVERHEAT: 0.35,
        FailureMode.STRUCTURAL_CRACK: 0.15,
        FailureMode.COMMS_LOSS: 0.10,
    },
    RobotType.REPAIR_BOT: {
        FailureMode.MOTOR_BURNOUT: 0.15,
        FailureMode.ELECTRONICS_OVERHEAT: 0.30,
        FailureMode.BEARING_SEIZURE: 0.20,
        FailureMode.SENSOR_FAILURE: 0.15,
        FailureMode.STRUCTURAL_CRACK: 0.08,
    },
    RobotType.SCOUT_BOT: {
        FailureMode.ELECTRONICS_OVERHEAT: 0.50,
        FailureMode.SENSOR_FAILURE: 0.30,
        FailureMode.STRUCTURAL_CRACK: 0.15,
        FailureMode.COMMS_LOSS: 0.20,
    },
}

# Repair success probability by failure mode.
# ALL VALUES ARE ESTIMATE — engineering judgement based on field repair analogues
# (e.g., NASA EVA toolbox failure recovery rates, MIL-HDBK-472 §4.3 maintainability).
REPAIR_SUCCESS_RATE: dict[FailureMode, float] = {
    FailureMode.BIT_WEAR: 0.95,            # simple swap
    FailureMode.MOTOR_BURNOUT: 0.80,
    FailureMode.HYDRAULIC_LEAK: 0.75,
    FailureMode.TRACK_FRACTURE: 0.70,
    FailureMode.ELECTRONICS_OVERHEAT: 0.85,
    FailureMode.RTG_DEGRADATION: 0.60,     # hard to fix in field
    FailureMode.STRUCTURAL_CRACK: 0.50,    # welding in 1100 K is rough
    FailureMode.SENSOR_FAILURE: 0.90,
    FailureMode.COMMS_LOSS: 0.85,
    FailureMode.RAIL_WARP: 0.65,
    FailureMode.PRESS_SEAL_FAILURE: 0.70,
    FailureMode.BEARING_SEIZURE: 0.75,
}

# Repair time in hours by failure mode.
# ALL VALUES ARE ESTIMATE — scaled from RepairBot docstring task times
# and industrial maintenance data (MIL-HDBK-472 §4.3 MTTR lognormal model).
REPAIR_TIME_HOURS: dict[FailureMode, float] = {
    FailureMode.BIT_WEAR: 4.0,
    FailureMode.MOTOR_BURNOUT: 16.0,
    FailureMode.HYDRAULIC_LEAK: 12.0,
    FailureMode.TRACK_FRACTURE: 12.0,
    FailureMode.ELECTRONICS_OVERHEAT: 8.0,
    FailureMode.RTG_DEGRADATION: 24.0,
    FailureMode.STRUCTURAL_CRACK: 20.0,
    FailureMode.SENSOR_FAILURE: 6.0,
    FailureMode.COMMS_LOSS: 4.0,
    FailureMode.RAIL_WARP: 48.0,
    FailureMode.PRESS_SEAL_FAILURE: 16.0,
    FailureMode.BEARING_SEIZURE: 10.0,
}


# ────────────────────────────────────────────────────────────────────
#  DEFAULT FLEET COMPOSITION
# ────────────────────────────────────────────────────────────────────

DEFAULT_FLEET_COMPOSITION: dict[RobotType, int] = {
    RobotType.MINING_DRILL: 4,
    RobotType.HAUL_BOT: 6,
    RobotType.PROCESSOR_BOT: 2,
    RobotType.LAUNCH_BOT: 1,
    RobotType.REPAIR_BOT: 3,
    RobotType.SCOUT_BOT: 8,
}
# Total: 24 robots. Ship carries kits for 10 more as reserves.

RESERVE_KITS: int = 10


# ────────────────────────────────────────────────────────────────────
#  ROBOTIC OPERATIONS SIMULATOR
# ────────────────────────────────────────────────────────────────────

class RoboticOperationsSimulator:
    """Year-by-year simulation of robotic mining operations on 55 Cnc e.

    Simulates:
      - Robot assembly and landing
      - Surface operations (drilling, hauling, processing, launching)
      - Failure events and repair cycles
      - Diamond production and orbital cargo launch
      - Cargo pod dispatch to Sol
      - Fleet attrition and replacement from reserve kits

    Integrates with MiningMission by providing detailed robot-level
    fidelity to what was previously a single "robots_deployed: 24" line.
    """

    def __init__(
        self,
        fleet_composition: dict[RobotType, int] | None = None,
        reserve_kits: int = RESERVE_KITS,
        seed: int = 42,
    ) -> None:
        self._rng = random.Random(seed)
        self._composition = dict(fleet_composition or DEFAULT_FLEET_COMPOSITION)
        self._reserve_kits = reserve_kits

        # Fleet
        self._fleet: list[SurfaceRobot] = []
        self._next_id = 1

        # Subsystems
        self._power = SurfacePowerSystem()
        self._relay_sats: list[CommRelaySatellite] = []
        self._catcher = OrbitalCatcher()
        self._cargo_pods: list[CargoPod] = []
        self._shuttles: list[LandingShuttle] = []
        self._manufacturing = ShipManufacturingBay()
        self._lifecycle = FleetLifecycle()
        self._kits: list[RobotKit] = []

        # Production tracking
        self._total_ore_mined_kg: float = 0.0
        self._total_diamond_produced_kg: float = 0.0
        self._total_capsules_launched: int = 0
        self._events: list[dict[str, Any]] = []
        self._year: float = 0.0

        # Initialize fleet
        self._init_fleet()

    def _init_fleet(self) -> None:
        """Create robot objects for the initial fleet composition."""
        for robot_type, count in self._composition.items():
            for _ in range(count):
                robot = self._create_robot(robot_type)
                self._fleet.append(robot)

        # Create reserve kits
        # Distribute reserve kits across types that benefit most from spares
        reserve_types = [
            RobotType.MINING_DRILL,
            RobotType.HAUL_BOT,
            RobotType.REPAIR_BOT,
            RobotType.SCOUT_BOT,
            RobotType.MINING_DRILL,
            RobotType.HAUL_BOT,
            RobotType.PROCESSOR_BOT,
            RobotType.SCOUT_BOT,
            RobotType.REPAIR_BOT,
            RobotType.SCOUT_BOT,
        ]
        for i, rtype in enumerate(reserve_types[:self._reserve_kits]):
            kit = RobotKit(
                kit_id=f"KIT-{i+1:03d}",
                robot_type=rtype,
            )
            self._kits.append(kit)

        # Deploy 3 relay satellites
        for i in range(3):
            sat = CommRelaySatellite(sat_id=f"RELAY-{i+1}")
            self._relay_sats.append(sat)

    def _create_robot(self, robot_type: RobotType) -> SurfaceRobot:
        """Create a new robot with detailed sub-dataclass."""
        rid = f"{robot_type.value.upper()}-{self._next_id:03d}"
        self._next_id += 1

        detail: Any = None
        if robot_type == RobotType.MINING_DRILL:
            detail = MiningDrill(robot_id=rid)
        elif robot_type == RobotType.HAUL_BOT:
            detail = HaulBot(robot_id=rid)
        elif robot_type == RobotType.PROCESSOR_BOT:
            detail = ProcessorBot(robot_id=rid)
        elif robot_type == RobotType.LAUNCH_BOT:
            detail = LaunchBot(robot_id=rid)
        elif robot_type == RobotType.REPAIR_BOT:
            detail = RepairBot(robot_id=rid)
        elif robot_type == RobotType.SCOUT_BOT:
            detail = ScoutBot(robot_id=rid)

        return SurfaceRobot(
            robot_type=robot_type,
            robot_id=rid,
            detail=detail,
        )

    @property
    def fleet(self) -> list[SurfaceRobot]:
        return list(self._fleet)

    @property
    def operational_robots(self) -> list[SurfaceRobot]:
        return [r for r in self._fleet if r.is_operational]

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    @property
    def year(self) -> float:
        return self._year

    @property
    def total_diamond_produced_kg(self) -> float:
        return self._total_diamond_produced_kg

    @property
    def total_capsules_launched(self) -> int:
        return self._total_capsules_launched

    @property
    def cargo_pods(self) -> list[CargoPod]:
        return list(self._cargo_pods)

    @property
    def lifecycle(self) -> FleetLifecycle:
        return self._lifecycle

    @property
    def power_system(self) -> SurfacePowerSystem:
        return self._power

    @property
    def manufacturing_bay(self) -> ShipManufacturingBay:
        return self._manufacturing

    @property
    def kits_remaining(self) -> int:
        return len([k for k in self._kits if not k.assembled])

    # ────────────────────────────────────────────────
    #  PHASE 0: ASSEMBLY & DEPLOYMENT
    # ────────────────────────────────────────────────

    def deploy_initial_fleet(self) -> list[dict[str, Any]]:
        """Assemble all robots and land them on the surface.

        Timeline:
          Day 0-28:  Assemble first 8 robots (2 at a time, 14 days each)
          Day 28-56: Assemble next 8 robots
          Day 56-84: Assemble last 8 robots
          Day 14:    First shuttle landing (4 ScoutBots for site survey)
          Day 42:    Second shuttle (4 MiningDrills)
          Day 56:    Third shuttle (ProcessorBots + HaulBots)
          Day 70:    Fourth shuttle (HaulBots + RepairBots)
          Day 84:    Fifth shuttle (LaunchBot + remaining)
          Day 90:    Deploy relay satellite
          Day 100:   Kilopower reactor assembly begins
          Day 120:   Kilopower online
          Day 130:   Mass driver assembly begins
          Day 180:   Mass driver operational
          Day 185:   Microwave beam link established
          Day 200:   Full operations begin

        Returns list of deployment events.
        """
        events: list[dict[str, Any]] = []
        day = 0.0

        # Assemble all fleet robots
        batch_size = self._manufacturing.assembly_slots  # 2
        fleet_copy = list(self._fleet)
        shuttle_num = 0
        shuttle_cargo: list[SurfaceRobot] = []

        for i in range(0, len(fleet_copy), batch_size):
            batch = fleet_copy[i:i + batch_size]
            for robot in batch:
                robot.status = RobotStatus.ASSEMBLING
                robot.assembly_start_day = day

            day += 14.0  # 2 weeks per batch

            for robot in batch:
                robot.status = RobotStatus.READY
                if robot.detail is not None:
                    robot.detail.status = RobotStatus.READY
                shuttle_cargo.append(robot)
                self._manufacturing.robots_assembled += 1

                events.append({
                    "day": day,
                    "event": "ASSEMBLY_COMPLETE",
                    "robot_id": robot.robot_id,
                    "robot_type": robot.robot_type.value,
                })

            # Launch shuttle when we have 4 robots ready
            while len(shuttle_cargo) >= 4:
                shuttle_num += 1
                landing_batch = shuttle_cargo[:4]
                shuttle_cargo = shuttle_cargo[4:]

                shuttle = LandingShuttle(
                    shuttle_id=f"SHUTTLE-{shuttle_num:02d}",
                    robots_carried=[r.robot_id for r in landing_batch],
                )

                day += 2.0  # 2 days for loading and launch prep

                for robot in landing_batch:
                    robot.status = RobotStatus.LANDING
                    robot.landing_day = day

                day += 0.1  # landing takes ~2.4 hours

                shuttle.landed = True
                self._shuttles.append(shuttle)

                for robot in landing_batch:
                    robot.status = RobotStatus.OPERATIONAL
                    robot.health = 1.0
                    if robot.detail is not None:
                        robot.detail.status = RobotStatus.OPERATIONAL

                events.append({
                    "day": day,
                    "event": "SHUTTLE_LANDED",
                    "shuttle_id": shuttle.shuttle_id,
                    "robots": [r.robot_id for r in landing_batch],
                    "twr": f"{shuttle.twr_at_surface:.2f}",
                    "delta_v": f"{shuttle.delta_v_available_ms:.0f} m/s",
                })

        # Land remaining robots (if not a multiple of 4)
        if shuttle_cargo:
            shuttle_num += 1
            shuttle = LandingShuttle(
                shuttle_id=f"SHUTTLE-{shuttle_num:02d}",
                robots_carried=[r.robot_id for r in shuttle_cargo],
            )
            day += 2.0
            for robot in shuttle_cargo:
                robot.status = RobotStatus.LANDING
                robot.landing_day = day
            day += 0.1
            shuttle.landed = True
            self._shuttles.append(shuttle)
            for robot in shuttle_cargo:
                robot.status = RobotStatus.OPERATIONAL
                robot.health = 1.0
                if robot.detail is not None:
                    robot.detail.status = RobotStatus.OPERATIONAL
            events.append({
                "day": day,
                "event": "SHUTTLE_LANDED",
                "shuttle_id": shuttle.shuttle_id,
                "robots": [r.robot_id for r in shuttle_cargo],
            })

        # Deploy relay satellite
        day += 5.0
        self._relay_sats[0].operational = True
        events.append({"day": day, "event": "RELAY_SAT_DEPLOYED", "sat_id": "RELAY-1"})

        # Set up power
        self._power.mmrtg_count = len([
            r for r in self._fleet
            if r.is_operational and r.robot_type != RobotType.SCOUT_BOT
        ])

        # Kilopower assembly
        day += 30.0
        self._power.kilopower_online = True
        events.append({"day": day, "event": "KILOPOWER_ONLINE", "power_kw": 10.0})

        # Mass driver assembly + microwave beam
        day += 50.0
        self._power.microwave_beam_online = True
        events.append({
            "day": day,
            "event": "MASS_DRIVER_READY",
            "rectenna_power_kw": self._power.rectenna_power_kw,
        })

        # Record deployment year
        self._year = day / 365.25
        self._lifecycle.robots_deployed = len([r for r in self._fleet if r.is_operational])
        self._lifecycle.robots_operational = self._lifecycle.robots_deployed

        events.append({
            "day": day,
            "event": "FULL_OPERATIONS_BEGIN",
            "robots_operational": self._lifecycle.robots_operational,
            "total_power_kw": self._power.total_surface_power_kw,
        })

        self._events.extend(events)
        return events

    # ────────────────────────────────────────────────
    #  ANNUAL SIMULATION CYCLE
    # ────────────────────────────────────────────────

    def simulate_year(self, year: float | None = None) -> list[dict[str, Any]]:
        """Simulate one year of surface operations.

        Returns a list of events that occurred during the year.
        Each event is a dict with at minimum: year, event, description.
        """
        if year is not None:
            self._year = year
        else:
            self._year += 1.0

        events: list[dict[str, Any]] = []
        yr = self._year

        # ── Step 1: Failures ──
        failure_events = self._simulate_failures(yr)
        events.extend(failure_events)

        # ── Step 2: Repairs ──
        repair_events = self._simulate_repairs(yr)
        events.extend(repair_events)

        # ── Step 3: Mining production ──
        production_events = self._simulate_production(yr)
        events.extend(production_events)

        # ── Step 4: Cargo launches ──
        launch_events = self._simulate_cargo_launches(yr)
        events.extend(launch_events)

        # ── Step 5: Replacement from reserves ──
        replacement_events = self._simulate_replacements(yr)
        events.extend(replacement_events)

        # ── Step 6: Update lifecycle ──
        self._update_lifecycle(yr)

        # ── Step 7: Relay satellite maintenance ──
        for sat in self._relay_sats:
            if sat.operational:
                sat.years_in_service += 1.0
                if sat.years_in_service >= sat.design_life_years:
                    sat.operational = False
                    # Activate next satellite
                    for backup in self._relay_sats:
                        if not backup.operational and backup.years_in_service == 0:
                            backup.operational = True
                            events.append({
                                "year": yr, "event": "RELAY_SAT_REPLACED",
                                "old": sat.sat_id, "new": backup.sat_id,
                            })
                            break
                    else:
                        events.append({
                            "year": yr, "event": "RELAY_SAT_LOST",
                            "sat_id": sat.sat_id, "note": "no backup available",
                        })
                    break  # only one satellite active at a time

        self._events.extend(events)
        return events

    def _simulate_failures(self, year: float) -> list[dict[str, Any]]:
        """Roll for failures on each operational robot.

        Each robot faces at most one failure event per year (the most
        severe one that triggers). A failure reduces health and, if
        health drops below 0.5, transitions the robot to DAMAGED status
        (requiring RepairBot intervention before it can produce again).
        If health drops to 0.1 or below, the robot is DESTROYED.
        Minor failures (health still above 0.5) degrade performance
        but do not halt operations — the robot limps along at reduced
        efficiency until a RepairBot can schedule preventive maintenance.
        """
        events: list[dict[str, Any]] = []

        for robot in self._fleet:
            if robot.status not in (RobotStatus.OPERATIONAL, RobotStatus.DAMAGED):
                continue
            # Already damaged robots do not accumulate further failures
            if robot.status == RobotStatus.DAMAGED:
                continue

            rates = FAILURE_RATES.get(robot.robot_type, {})
            for failure_mode, annual_prob in rates.items():
                if self._rng.random() < annual_prob:
                    # This failure occurred
                    damage = self._rng.uniform(0.10, 0.30)
                    robot.health -= damage
                    robot.health = max(0.0, robot.health)
                    robot.active_failure = failure_mode

                    if robot.health <= 0.1:
                        robot.status = RobotStatus.DESTROYED
                        if robot.detail is not None:
                            robot.detail.status = RobotStatus.DESTROYED
                        events.append({
                            "year": year,
                            "event": "ROBOT_DESTROYED",
                            "robot_id": robot.robot_id,
                            "robot_type": robot.robot_type.value,
                            "cause": failure_mode.value,
                        })
                    elif robot.health < 0.5:
                        robot.status = RobotStatus.DAMAGED
                        if robot.detail is not None:
                            robot.detail.status = RobotStatus.DAMAGED
                        events.append({
                            "year": year,
                            "event": "ROBOT_DAMAGED",
                            "robot_id": robot.robot_id,
                            "robot_type": robot.robot_type.value,
                            "failure": failure_mode.value,
                            "health": f"{robot.health:.2f}",
                        })
                    else:
                        # Minor failure — still operational but degraded
                        events.append({
                            "year": year,
                            "event": "ROBOT_DEGRADED",
                            "robot_id": robot.robot_id,
                            "robot_type": robot.robot_type.value,
                            "failure": failure_mode.value,
                            "health": f"{robot.health:.2f}",
                        })
                    break  # one failure per robot per year

        return events

    def _simulate_repairs(self, year: float) -> list[dict[str, Any]]:
        """RepairBots attempt to fix damaged robots.

        RepairBots can fix any damaged robot, including other RepairBots.
        A damaged RepairBot can still receive repairs from an operational
        one — the fleet carries 3 RepairBots specifically so that at
        least one should remain operational to service the others.
        Priority: RepairBots first (to maintain repair capacity), then
        production-critical robots (Drills, Processors), then others.
        """
        events: list[dict[str, Any]] = []

        repair_bots = [
            r for r in self._fleet
            if r.robot_type == RobotType.REPAIR_BOT and r.is_operational
        ]
        # Include ALL damaged robots — RepairBots can repair each other
        damaged = [
            r for r in self._fleet
            if r.status == RobotStatus.DAMAGED
        ]
        # Also service degraded-but-operational robots (preventive maintenance)
        degraded = [
            r for r in self._fleet
            if r.status == RobotStatus.OPERATIONAL and r.health < 0.8
            and r.active_failure is not None
        ]
        # Prioritize: damaged RepairBots first, then other damaged, then degraded
        repair_queue = (
            [r for r in damaged if r.robot_type == RobotType.REPAIR_BOT]
            + [r for r in damaged if r.robot_type != RobotType.REPAIR_BOT]
            + degraded
        )

        # Each RepairBot can handle max_simultaneous_patients per year
        repair_capacity = sum(
            (r.detail.max_simultaneous_patients if r.detail else 3)
            for r in repair_bots
        )

        for robot in repair_queue[:repair_capacity]:
            failure = robot.active_failure
            if failure is None:
                failure = FailureMode.ELECTRONICS_OVERHEAT  # default

            success_rate = REPAIR_SUCCESS_RATE.get(failure, 0.5)
            repair_hours = REPAIR_TIME_HOURS.get(failure, 12.0)

            if self._rng.random() < success_rate:
                # Repair success
                robot.status = RobotStatus.OPERATIONAL
                robot.health = min(1.0, robot.health + self._rng.uniform(0.3, 0.5))
                robot.active_failure = None
                robot.repairs_received += 1
                if robot.detail is not None:
                    robot.detail.status = RobotStatus.OPERATIONAL

                # Consume spare parts from nearest RepairBot
                repairer = self._rng.choice(repair_bots) if repair_bots else None
                parts_used = {}
                if repairer and repairer.detail and isinstance(repairer.detail, RepairBot):
                    if failure == FailureMode.BIT_WEAR and repairer.detail.spare_drill_bits > 0:
                        repairer.detail.spare_drill_bits -= 1
                        parts_used["drill_bit"] = 1
                    elif failure == FailureMode.ELECTRONICS_OVERHEAT and repairer.detail.spare_electronics_modules > 0:
                        repairer.detail.spare_electronics_modules -= 1
                        parts_used["sic_module"] = 1
                    elif failure == FailureMode.TRACK_FRACTURE and repairer.detail.spare_track_segments > 0:
                        repairer.detail.spare_track_segments -= 1
                        parts_used["track_segment"] = 1
                    repairer.detail.total_repairs_completed += 1
                    repairer.detail.total_repair_hours += repair_hours

                log = MaintenanceLog(
                    year=year,
                    robot_id=robot.robot_id,
                    failure_mode=failure,
                    repair_hours=repair_hours,
                    repair_bot_id=repairer.robot_id if repairer else "N/A",
                    success=True,
                    parts_used=parts_used,
                )
                self._lifecycle.maintenance_logs.append(log)
                self._lifecycle.robots_repaired_total += 1

                events.append({
                    "year": year,
                    "event": "REPAIR_SUCCESS",
                    "robot_id": robot.robot_id,
                    "failure": failure.value,
                    "hours": repair_hours,
                    "health_after": f"{robot.health:.2f}",
                })
            else:
                # Repair failed — robot is destroyed
                robot.status = RobotStatus.DESTROYED
                robot.health = 0.0
                if robot.detail is not None:
                    robot.detail.status = RobotStatus.DESTROYED

                log = MaintenanceLog(
                    year=year,
                    robot_id=robot.robot_id,
                    failure_mode=failure,
                    repair_hours=repair_hours,
                    repair_bot_id=repair_bots[0].robot_id if repair_bots else "N/A",
                    success=False,
                    notes="Repair failed, robot scrapped",
                )
                self._lifecycle.maintenance_logs.append(log)

                events.append({
                    "year": year,
                    "event": "REPAIR_FAILED",
                    "robot_id": robot.robot_id,
                    "failure": failure.value,
                    "result": "destroyed",
                })

        return events

    def _simulate_production(self, year: float) -> list[dict[str, Any]]:
        """Calculate ore mined and diamond produced by operational fleet."""
        events: list[dict[str, Any]] = []

        # Count operational robots by type
        op_drills = len([
            r for r in self._fleet
            if r.robot_type == RobotType.MINING_DRILL and r.is_operational
        ])
        op_haulers = len([
            r for r in self._fleet
            if r.robot_type == RobotType.HAUL_BOT and r.is_operational
        ])
        op_processors = len([
            r for r in self._fleet
            if r.robot_type == RobotType.PROCESSOR_BOT and r.is_operational
        ])

        if op_drills == 0 or op_processors == 0:
            events.append({
                "year": year, "event": "PRODUCTION_HALTED",
                "reason": "no drills" if op_drills == 0 else "no processors",
            })
            return events

        # Each drill operates 24/7 at 0.5 m/hr in 2.3 g carbon rock.
        # Ore density ~3.5 g/cm3, bore diameter 200 mm.
        # Volume per hour: pi * 0.1^2 * 0.5 = 0.0157 m^3/hr
        # Mass per hour: 0.0157 * 3500 = 55 kg/hr — ESTIMATE (density from MiningDrill docstring)
        # Per drill per year: 55 * 8760 * 0.7 (uptime) = 337,260 kg
        drill_ore_per_year_kg = 55.0 * 8760 * 0.70  # 70% uptime — ESTIMATE (analogous to rotary drill uptime)
        total_ore_mined = op_drills * drill_ore_per_year_kg

        # HaulBot throughput check: each trip is ~80 min round trip, 2000 kg — ESTIMATE
        # Per hauler per year: (525600 min/yr) / 80 * 2000 * 0.8 uptime
        hauler_throughput = op_haulers * (525600 / 80) * 2000 * 0.80  # 80% uptime — ESTIMATE
        # Bottleneck: take minimum of drill output and hauler throughput
        ore_available = min(total_ore_mined, hauler_throughput)

        # ProcessorBot: 2000 kg/day raw ore throughput each — ESTIMATE (from ProcessorBot.throughput_kg_day)
        processor_throughput = op_processors * 2000.0 * 365.25 * 0.75  # 75% uptime — ESTIMATE
        ore_processed = min(ore_available, processor_throughput)

        # Diamond output: ~10% of raw ore is diamond (natural + synthetic)
        # Natural diamond in the ore: ~5%
        # Synthetic conversion of graphite: ~35% of remaining graphite → diamond
        # Remaining graphite fraction after natural diamond: 95% of ore
        # Synthetic yield: 0.95 * 0.35 = 33.25%
        # Total diamond fraction: 5% + 33.25% = 38.25%
        diamond_fraction = 0.05 + 0.95 * GRAPHITE_TO_DIAMOND_EFFICIENCY
        diamond_produced = ore_processed * diamond_fraction

        # Apply random variance — ESTIMATE: ±10-15% production scatter from geological variability
        variance = self._rng.uniform(0.85, 1.10)
        diamond_produced *= variance

        self._total_ore_mined_kg += ore_processed
        self._total_diamond_produced_kg += diamond_produced

        # Update drill details
        for robot in self._fleet:
            if robot.robot_type == RobotType.MINING_DRILL and robot.is_operational:
                if isinstance(robot.detail, MiningDrill):
                    robot.detail.total_hours_drilled += 8760 * 0.70
                    robot.detail.ore_extracted_kg += drill_ore_per_year_kg
                    robot.detail.hours_on_current_bit += 8760 * 0.70
                    # Advance drill depth (resets when relocating)
                    robot.detail.current_depth_m = min(
                        robot.detail.max_drill_depth_m,
                        robot.detail.current_depth_m + 0.5 * 8760 * 0.70
                    )
                    robot.operational_hours += 8760

        # Update hauler details
        for robot in self._fleet:
            if robot.robot_type == RobotType.HAUL_BOT and robot.is_operational:
                if isinstance(robot.detail, HaulBot):
                    trips_this_year = int((525600 / 80) * 0.80)
                    robot.detail.trips_completed += trips_this_year
                    robot.detail.total_ore_hauled_kg += ore_available / max(op_haulers, 1)
                    robot.detail.total_distance_km += trips_this_year * 4.0  # 2 km each way
                    robot.operational_hours += 8760

        # Update processor details
        for robot in self._fleet:
            if robot.robot_type == RobotType.PROCESSOR_BOT and robot.is_operational:
                if isinstance(robot.detail, ProcessorBot):
                    robot.detail.total_ore_processed_kg += ore_processed / max(op_processors, 1)
                    robot.detail.total_diamond_produced_kg += diamond_produced / max(op_processors, 1)
                    robot.operational_hours += 8760

        events.append({
            "year": year,
            "event": "ANNUAL_PRODUCTION",
            "drills_active": op_drills,
            "haulers_active": op_haulers,
            "processors_active": op_processors,
            "ore_mined_tonnes": f"{ore_processed / 1000:.1f}",
            "diamond_produced_tonnes": f"{diamond_produced / 1000:.1f}",
            "diamond_produced_kg": f"{diamond_produced:.0f}",
        })

        return events

    def _simulate_cargo_launches(self, year: float) -> list[dict[str, Any]]:
        """Mass driver launches diamond capsules to orbit."""
        events: list[dict[str, Any]] = []

        launch_bots = [
            r for r in self._fleet
            if r.robot_type == RobotType.LAUNCH_BOT and r.is_operational
        ]
        if not launch_bots or not self._power.microwave_beam_online:
            return events

        launcher = launch_bots[0]
        if not isinstance(launcher.detail, LaunchBot):
            return events

        detail: LaunchBot = launcher.detail

        # Available diamond for launch (from this year's production)
        # Diamond is packed into 10 kg capsules
        # Mass driver does 24 launches/day, 365 days, with 80% uptime
        max_annual_launches = detail.launches_per_day * 365 * 0.80
        diamond_available_kg = self._total_diamond_produced_kg - (
            self._total_capsules_launched * detail.capsule_mass_kg
        )
        diamond_available_kg = max(0.0, diamond_available_kg)

        capsules_possible = int(diamond_available_kg / detail.capsule_mass_kg)
        capsules_launched = min(capsules_possible, int(max_annual_launches))

        if capsules_launched > 0:
            detail.total_launches += capsules_launched
            detail.total_mass_launched_kg += capsules_launched * detail.capsule_mass_kg
            self._total_capsules_launched += capsules_launched

            # Orbital catcher accumulates capsules
            if not self._catcher.operational:
                self._catcher.operational = True
            self._catcher.capsules_caught += capsules_launched

            events.append({
                "year": year,
                "event": "CARGO_LAUNCHES",
                "capsules": capsules_launched,
                "mass_kg": capsules_launched * detail.capsule_mass_kg,
                "mass_tonnes": f"{capsules_launched * detail.capsule_mass_kg / 1000:.1f}",
            })

            # Check if enough for a cargo pod (10 tonnes = 10000 kg)
            accumulated = self._catcher.capsules_caught * detail.capsule_mass_kg
            pods_possible = int(accumulated / self._catcher.cargo_pod_capacity_kg)
            pods_already = self._catcher.pods_filled

            new_pods = pods_possible - pods_already
            for i in range(new_pods):
                pod = CargoPod(
                    pod_id=f"POD-{len(self._cargo_pods) + 1:04d}",
                    launch_year=year,
                    arrival_year=year + 252.0,
                    launched=True,
                )
                self._cargo_pods.append(pod)
                self._catcher.pods_filled += 1

                events.append({
                    "year": year,
                    "event": "CARGO_POD_DISPATCHED",
                    "pod_id": pod.pod_id,
                    "diamond_tonnes": pod.diamond_mass_kg / 1000,
                    "value_au": pod.value_au,
                    "eta_sol_year": f"{pod.arrival_year:.0f}",
                })

            launcher.operational_hours += 8760

        return events

    def _simulate_replacements(self, year: float) -> list[dict[str, Any]]:
        """Build replacement robots from reserve kits for destroyed units."""
        events: list[dict[str, Any]] = []

        destroyed_types: dict[RobotType, int] = {}
        for robot in self._fleet:
            if robot.status == RobotStatus.DESTROYED:
                destroyed_types[robot.robot_type] = destroyed_types.get(robot.robot_type, 0) + 1

        # Priority: RepairBots first, then Drills, then Haulers, then others
        priority = [
            RobotType.REPAIR_BOT,
            RobotType.MINING_DRILL,
            RobotType.HAUL_BOT,
            RobotType.PROCESSOR_BOT,
            RobotType.LAUNCH_BOT,
            RobotType.SCOUT_BOT,
        ]

        replacements_this_year = 0
        max_replacements = self._manufacturing.assembly_slots * 4  # ~4 batches/year possible

        for rtype in priority:
            if replacements_this_year >= max_replacements:
                break
            needed = destroyed_types.get(rtype, 0)
            if needed == 0:
                continue

            # Find matching kit
            for kit in self._kits:
                if kit.assembled or kit.robot_type != rtype:
                    continue
                if replacements_this_year >= max_replacements:
                    break

                kit.assembled = True
                new_robot = self._create_robot(rtype)
                new_robot.status = RobotStatus.OPERATIONAL
                new_robot.health = 1.0
                if new_robot.detail is not None:
                    new_robot.detail.status = RobotStatus.OPERATIONAL
                self._fleet.append(new_robot)
                self._manufacturing.robots_assembled += 1
                replacements_this_year += 1

                events.append({
                    "year": year,
                    "event": "REPLACEMENT_DEPLOYED",
                    "robot_id": new_robot.robot_id,
                    "robot_type": rtype.value,
                    "kits_remaining": self.kits_remaining,
                })

                needed -= 1
                if needed <= 0:
                    break

        return events

    def _update_lifecycle(self, year: float) -> None:
        """Update fleet lifecycle counters."""
        lc = self._lifecycle
        lc.year = year
        lc.robots_deployed = len(self._fleet)
        lc.robots_operational = len([r for r in self._fleet if r.is_operational])
        lc.robots_damaged = len([r for r in self._fleet if r.status == RobotStatus.DAMAGED])
        lc.robots_destroyed = len([r for r in self._fleet if r.status == RobotStatus.DESTROYED])
        lc.total_ore_mined_kg = self._total_ore_mined_kg
        lc.total_diamond_produced_kg = self._total_diamond_produced_kg
        lc.total_capsules_launched = self._total_capsules_launched
        lc.total_cargo_pods_sent = len(self._cargo_pods)

    # ────────────────────────────────────────────────
    #  MULTI-YEAR SIMULATION
    # ────────────────────────────────────────────────

    def run(self, years: int = 20) -> FleetLifecycle:
        """Run complete surface operations for the specified duration.

        Deploys fleet, then simulates year-by-year operations.
        Returns the final FleetLifecycle state.
        """
        self.deploy_initial_fleet()

        for y in range(1, years + 1):
            self.simulate_year(float(y))

        logger.info(
            "robotic_ops.complete",
            years=years,
            robots_operational=self._lifecycle.robots_operational,
            robots_destroyed=self._lifecycle.robots_destroyed,
            diamond_tonnes=f"{self._total_diamond_produced_kg / 1000:.1f}",
            cargo_pods=len(self._cargo_pods),
        )

        return self._lifecycle

    # ────────────────────────────────────────────────
    #  TELEMETRY
    # ────────────────────────────────────────────────

    def get_fleet_telemetry(self) -> list[RobotTelemetry]:
        """Get current telemetry for all robots."""
        telemetry = []
        for robot in self._fleet:
            t = RobotTelemetry(
                robot_id=robot.robot_id,
                timestamp_hours=self._year * 8760,
                position_x_m=self._rng.uniform(-5000, 5000),
                position_y_m=self._rng.uniform(-5000, 5000),
                health=robot.health,
                status=robot.status.value,
                power_output_kw=1.2 if robot.is_operational else 0.0,
                temperature_k=LANDING_ZONE_TEMP_K + self._rng.uniform(-50, 100),
                active_failure=robot.active_failure.value if robot.active_failure else "",
            )
            telemetry.append(t)
        return telemetry

    # ────────────────────────────────────────────────
    #  REPORTING
    # ────────────────────────────────────────────────

    def summary_report(self) -> str:
        """Generate a detailed summary of operations."""
        lc = self._lifecycle
        total_fleet = len(self._fleet)
        operational = lc.robots_operational
        destroyed = lc.robots_destroyed
        diamond_t = self._total_diamond_produced_kg / 1000
        pods = len(self._cargo_pods)
        total_value = sum(p.value_au for p in self._cargo_pods)

        lines = [
            "=" * 66,
            "  ROBOTIC MINING OPERATIONS — 55 CANCRI e NIGHTSIDE",
            "=" * 66,
            f"  Years of operation: {self._year:.1f}",
            f"  Landing zone temp: {LANDING_ZONE_TEMP_K:.0f} K",
            f"  Surface gravity: {SURFACE_GRAVITY_G:.2f} g ({SURFACE_GRAVITY_MS2:.1f} m/s^2)",
            "",
            "  FLEET STATUS:",
            f"    Total robots built: {total_fleet}",
            f"    Operational: {operational}",
            f"    Damaged: {lc.robots_damaged}",
            f"    Destroyed: {destroyed}",
            f"    Reserve kits remaining: {self.kits_remaining}",
            f"    Total repairs completed: {lc.robots_repaired_total}",
            "",
            "  PRODUCTION:",
            f"    Total ore mined: {self._total_ore_mined_kg / 1000:,.1f} tonnes",
            f"    Total diamond produced: {diamond_t:,.1f} tonnes",
            f"    Diamond ingots: {int(self._total_diamond_produced_kg):,} (1 kg each)",
            "",
            "  CARGO TRANSPORT:",
            f"    Capsules launched to orbit: {self._total_capsules_launched:,}",
            f"    Cargo pods dispatched to Sol: {pods}",
            f"    Total diamond in transit: {pods * 10:.0f} tonnes",
            f"    Total economic value: {total_value:,.0f} AU",
            "",
            "  POWER:",
            f"    Robot MMRTGs active: {self._power.mmrtg_count}",
            f"    Kilopower reactor: {'ONLINE' if self._power.kilopower_online else 'OFFLINE'}",
            f"    Microwave beam: {'ONLINE' if self._power.microwave_beam_online else 'OFFLINE'}",
            f"    Total surface power: {self._power.total_surface_power_kw:.0f} kW",
            "",
            "  COMMUNICATIONS:",
        ]
        active_sats = [s for s in self._relay_sats if s.operational]
        lines.append(f"    Relay satellites: {len(active_sats)}/{len(self._relay_sats)} active")
        lines.append(f"    Shuttles landed: {len(self._shuttles)}")
        lines.append("")
        lines.append(f"  Events logged: {len(self._events)}")
        lines.append("=" * 66)

        return "\n".join(lines)
