"""Medical Emergencies & Internal Maintenance Robotics — Generation Ship.

Two critical subsystems identified in the 100-Scientist Interrogation:

1. MEDICAL EMERGENCIES MODEL
   A generation ship is a small-town hospital with no evacuation option.
   One surgical suite, two trained medical crew, drugs that expire in 2-5
   years, and injuries from 0.56g that Earth medicine never trained for.

   The 0.56g environment changes everything:
     - Blood pools differently: hydrostatic pressure gradients shift,
       affecting surgical bleeding patterns and wound drainage
     - Bone fractures heal 20-30% slower (reduced mechanical loading,
       analogous to ISS bone density loss of ~1.5%/month, Vico 2000)
     - Childbirth: uterine contractions evolved for 1g; at 0.56g, labor
       may stall, requiring intervention. Medical centrifuge at 1g for
       delivery is the safest protocol (no empirical data — extrapolated
       from primate centrifuge studies, Oyama 1975)
     - CPR effectiveness: chest compressions deliver ~30% less perfusion
       at 0.56g due to reduced gravitational assist on venous return

   Equipment degradation:
     - MRI: superconducting magnet requires continuous cryocooler. If the
       cryocooler fails, quench event boils off helium in ~30 minutes.
       Replacement cryocooler must be manufactured onboard.
     - Surgical tools: stainless steel instruments suffer from radiation-
       induced embrittlement at ~0.5 krad/yr behind shielding. Tools
       must be replaced every 100-150 years from ship's machine shop.
     - Sterilization: autoclave requires 121 C saturated steam at 15 psi
       for 15 minutes. If autoclave fails, UV-C + chemical sterilization
       (less reliable, 99.9% vs 99.9999% kill rate).

   Annual medical event rate: ~5-10 per 100 crew, based on:
     - US Navy submarine medicine data (Tansey 2000)
     - Antarctic winter-over station records (Lugg 2000)
     - ISS medical incident reports (NASA JSC, 2020 review)

   Mortality: ~1-2% annual risk from all medical causes combined, given
   limited surgical capability and drug availability constraints.

   Reference: Kanas (2015) Space Psychology, Barratt & Pool (2008)
   Principles of Clinical Medicine for Space Flight, Vico et al. (2000),
   Tansey (2000) submarine medical records.

2. INTERNAL MAINTENANCE ROBOTICS
   Ship maintenance is not glamorous but it kills you if it fails.
   The ISS spends ~50% of crew time on maintenance (Williams 2017).
   Robots can access pipe interiors, duct networks, hull inner surfaces,
   and electrical conduit runs that humans physically cannot reach.

   Five robot types, 4 units each (20 total fleet):

   PipeBot (4 units):
     Inspects and repairs water/coolant pipe interiors. 15 cm diameter
     wheeled chassis with ultrasonic wall-thickness sensor. Detects
     corrosion pits, biofilm buildup, and micro-cracks. Can apply
     epoxy sealant patches to leaks <2mm diameter. Larger leaks require
     human EVA with pipe section replacement.

   DuctBot (4 units):
     Cleans air ducts, replaces HEPA/activated-carbon filters. Tracked
     chassis with rotary brush and HEPA vacuum. Carries one replacement
     filter per sortie. Filter replacement every 6 months per duct
     section. Detects mold colonies via VOC sensor (formaldehyde, MVOCs).

   HullBot (4 units):
     Inspects hull inner surface for micro-meteorite penetration, weld
     fatigue, and radiation damage. Magnetic-wheel locomotion on steel
     hull plates. Carries acoustic emission sensors for crack detection
     and thermal IR camera for insulation gaps. Can inject sealant foam
     for micro-leaks (<0.5mm). Larger breaches trigger emergency protocol.

   WiringBot (4 units):
     Inspects and replaces degraded cable runs in conduit tunnels.
     Snake-like articulated body, 5 cm diameter, 2 m long. Measures
     insulation resistance via non-contact capacitive sensor. Flags
     Kapton insulation below 50% elongation-at-break threshold (links
     to critical_systems wiring degradation model). Can splice and
     reroute single cables; full conduit replacement requires human crew.

   CleanBot (4 units):
     Sanitation, biofilm removal, waste collection in public areas and
     maintenance corridors. Wheeled platform with UV-C lamp array, mop
     system, and waste bin. Biofilm removal in accessible pipe junctions
     using enzymatic cleaning solution. Reports contamination hotspots
     to ARIA for epidemiological tracking.

   Power: Li-ion batteries, 8-hour operational cycle, 2-hour recharge.
   Each bot has a dedicated charging station. Fleet uptime target: 75%
   (at any time, 15 of 20 bots are operational or charging).

   Bots themselves need maintenance: motor replacement every 5 years,
   sensor calibration every 6 months, battery replacement every 3 years.
   Spare parts manufactured by ship's machine shop.

   SCADA-like monitoring: all bots report sensor data to ARIA via 2.4 GHz
   mesh network. ARIA aggregates readings into anomaly maps — e.g., if
   three PipeBots report elevated biofilm in Sector 7 pipes, ARIA flags
   a water treatment issue before crew notices taste changes.

   Reference: Williams (2017) ISS maintenance hours, Fong (2013) NASA
   robotic maintenance concepts, ISS SPHERES/Astrobee free-flyers.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import structlog

from aria.simulation.space_medical_rates import (
    ALL_CAUSE_RATE,
    CARDIAC_EVENT_RATE,
    DENTAL_EVENT_RATE,
    PSYCHIATRIC_RATE,
    TRAUMA_RATE,
    get_event_distribution_from_empirical,
)

logger = structlog.get_logger()


# ════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ════════════════════════════════════════════════════════════════════

SHIP_GRAVITY_G = 0.56           # O'Neill 1977 High Frontier §II: 1 RPM at R=500m → g = ω²R = 0.55g ≈ 0.56g
CREW_SIZE = 100                 # ESTIMATE — baseline crew complement (Hein 2012 Acta Astronaut 81 193)
SURGICAL_SUITES = 1             # ESTIMATE — single operating room (Barratt & Pool 2008 §12)
MEDICAL_STAFF = 2               # ESTIMATE — surgeon + nurse minimum (Barratt & Pool 2008 §12)
# Crucian et al. 2016 found 3.40 immune-related events/person/yr on ISS,
# but most were minor (rashes, congestion). For clinically significant events
# requiring medical intervention (the scope of this simulator), we use the
# submarine/Antarctic analog range of 5-10 per 100 crew/yr (Tansey 2000,
# Lugg 2000). The Crucian data informs the *distribution* across categories,
# not the total rate of events requiring intervention.
ANNUAL_EVENT_RATE_PER_100 = 7.5  # Tansey 2000 & Lugg 2000: 5-10/100/yr analog data; midpoint
ANNUAL_MORTALITY_RATE = 0.015    # ESTIMATE — 1-2% range midpoint (Kanas 2015 Space Psychology §6)

# Medical equipment lifespans (years)
MRI_CRYOCOOLER_MTBF_YEARS = 15.0       # ESTIMATE — Sumitomo CH-210 cryocooler MTBF ~15-20 yr (mfr data)
SURGICAL_TOOL_LIFESPAN_YEARS = 125.0   # ESTIMATE — midpoint 100-150 yr (0.5 krad/yr radiation embrittlement)
AUTOCLAVE_MTBF_YEARS = 10.0            # ESTIMATE — EN 13060:2014 Class B autoclave overhaul interval

# Drug shelf life (links to critical_systems.DrugSynthesisSimulator)
ANESTHESIA_SHELF_LIFE_YEARS = 2.0   # FDA 2019 drug stability guidance: anesthetics 2-3 yr refrigerated
ANESTHESIA_DOSES_PER_SURGERY = 1    # standard single-dose induction (Miller's Anesthesia 9th ed §16)

# Childbirth (WHO 2019: 15% of births need EmONC; Ronca 2003 rat µg studies)
CHILDBIRTH_COMPLICATION_RATE_1G = 0.15    # WHO 2019 EmONC Report: 15% births need obstetric intervention
CHILDBIRTH_COMPLICATION_RATE_056G = 0.25  # ESTIMATE — Ronca 2003 J Reprod Dev 49 425 µg fluid shift extrapolation

# Radiation sickness thresholds (Sv)
# ICRP Publication 84 (2000) Table A-2: acute radiation dose-effect thresholds
ACUTE_RADIATION_MILD_SV = 1.0    # ICRP Pub.84 (2000) Table A-2: nausea/lymphocyte threshold 1 Sv
ACUTE_RADIATION_SEVERE_SV = 4.0  # ICRP Pub.84 (2000) Table A-2: LD50/60 without treatment 4 Sv
ACUTE_RADIATION_LETHAL_SV = 8.0  # ICRP Pub.84 (2000) Table A-2: fatal even with treatment ≥ 8 Sv
CHRONIC_GCR_ANNUAL_SV = 0.05     # Cucinotta 2006 Radiat Res 166 500: ~50 mSv/yr behind 20 g/cm² Al

# Psychological
# Kanas 2015 + Palinkas 2003 (Antarctic analog): ~3 per 100 person-years.
# See space_medical_rates.PSYCHIATRIC_RATE (0.03/person/yr).
PSYCH_EMERGENCY_RATE_PER_100_YR = PSYCHIATRIC_RATE * 100  # Kanas 2015 Space Psychology §6: 3/100/yr
PSYCH_SUICIDE_RISK_FRACTION = 0.02     # Ursano 2014 JAMA Psychiatry 71 1067: ~2% military deployment
                                       # psychiatric emergencies progress to suicidality

# Internal robotics fleet
BOT_TYPES = ["PipeBot", "DuctBot", "HullBot", "WiringBot", "CleanBot"]
BOTS_PER_TYPE = 4    # ESTIMATE — Fong 2013 NASA TM-2013-216503 maintenance robot fleet sizing
TOTAL_FLEET_SIZE = len(BOT_TYPES) * BOTS_PER_TYPE  # 20 total (5 types × 4 units)

BOT_BATTERY_HOURS = 8.0             # ESTIMATE — Li-ion 8h operational cycle (Fong 2013 NASA TM-2013-216503)
BOT_RECHARGE_HOURS = 2.0            # ESTIMATE — 2h fast-charge (Wang 2017 Adv Energy Mater 7 1602485)
BOT_MOTOR_LIFESPAN_YEARS = 5.0      # ESTIMATE — brushless DC motor MTBF 3-7 yr (Fong 2013 NASA TM-2013-216503)
BOT_SENSOR_CALIBRATION_MONTHS = 6   # ESTIMATE — semi-annual recalibration (Astrobee FSW TRS-2019)
BOT_BATTERY_LIFESPAN_YEARS = 3.0    # Wang 2017 Adv Energy Mater 7 1602485: Li-ion ~1000 cycles → 3 yr daily

# Anomaly detection thresholds
BIOFILM_ALERT_THICKNESS_UM = 50.0    # WHO 2022 GDWQ §12: health risk begins at biofilm >50 µm
PIPE_CORROSION_ALERT_PCT = 10.0      # ASME B31.3:2022 §304.1: 10% wall loss triggers inspection
INSULATION_ALERT_PCT = 50.0          # ASTM D882: elongation-at-break <50% = degraded wire insulation


# ════════════════════════════════════════════════════════════════════
#  ENUMS
# ════════════════════════════════════════════════════════════════════

class MedicalEventType(Enum):
    """Categories of medical emergencies on the generation ship."""
    TRAUMA = "trauma"
    RADIATION_ACUTE = "radiation_acute"
    RADIATION_CHRONIC = "radiation_chronic"
    DENTAL = "dental"
    INFECTION = "infection"
    CARDIAC = "cardiac"
    CHILDBIRTH = "childbirth"
    PSYCHOLOGICAL = "psychological"
    SURGICAL = "surgical"
    BURN = "burn"


class MedicalSeverity(Enum):
    """Triage severity — drives resource allocation."""
    MINOR = "minor"          # treat with first aid, no surgery
    MODERATE = "moderate"    # requires medical bay, possible drugs
    SEVERE = "severe"        # requires surgery + anesthesia
    CRITICAL = "critical"    # life-threatening, immediate surgery
    FATAL = "fatal"          # untreatable given ship's resources


class EquipmentStatus(Enum):
    """Medical equipment operational state."""
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    FAILED = "failed"
    REPAIRING = "repairing"


class BotType(Enum):
    """Internal maintenance robot types."""
    PIPE_BOT = "PipeBot"
    DUCT_BOT = "DuctBot"
    HULL_BOT = "HullBot"
    WIRING_BOT = "WiringBot"
    CLEAN_BOT = "CleanBot"


class BotStatus(Enum):
    """Maintenance bot operational state."""
    OPERATIONAL = "operational"
    CHARGING = "charging"
    MAINTENANCE = "maintenance"
    DAMAGED = "damaged"
    DESTROYED = "destroyed"


class AnomalyType(Enum):
    """Types of anomalies detected by maintenance bots."""
    BIOFILM = "biofilm"
    CORROSION = "corrosion"
    MICRO_LEAK = "micro_leak"
    INSULATION_DEGRADATION = "insulation_degradation"
    FILTER_CLOGGED = "filter_clogged"
    MOLD_COLONY = "mold_colony"
    WELD_FATIGUE = "weld_fatigue"
    CABLE_DEGRADATION = "cable_degradation"
    CONTAMINATION = "contamination"


# ════════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ════════════════════════════════════════════════════════════════════

@dataclass
class MedicalEvent:
    """A single medical event requiring treatment."""
    year: float
    event_type: MedicalEventType
    severity: MedicalSeverity
    patient_id: int
    requires_surgery: bool = False
    requires_anesthesia: bool = False
    outcome: str = "pending"
    treatment_delay_hours: float = 0.0
    description: str = ""


@dataclass
class MedicalEquipment:
    """State of a piece of medical equipment."""
    name: str
    status: EquipmentStatus = EquipmentStatus.OPERATIONAL
    age_years: float = 0.0
    mtbf_years: float = 10.0   # ESTIMATE — 10 yr MTBF for hospital-grade equipment (MIL-HDBK-472 analogue)
    degradation: float = 0.0   # 0.0 = new, 1.0 = failed
    last_maintenance_year: float = 0.0


@dataclass
class MedicalState:
    """Aggregate medical system state for the ship."""
    crew_size: int = CREW_SIZE
    available_surgeons: int = 1           # ESTIMATE — 1 surgeon per crew of 50 (WHO: 1/10 000 pop min)
    available_nurses: int = 1             # ESTIMATE — 1 nurse per crew of 50 (ESTIMATE)
    surgical_suite_in_use: bool = False
    anesthesia_doses: float = 20.0        # ESTIMATE — ~20 doses = 1-yr reserve (WHO EML 2023 ketamine/propofol)
    total_events: int = 0
    total_surgeries: int = 0
    total_deaths: int = 0
    total_births: int = 0
    birth_complications: int = 0
    psych_emergencies: int = 0
    radiation_cases: int = 0
    untreatable_events: int = 0
    equipment: list[MedicalEquipment] = field(default_factory=list)
    drug_synthesis_available: bool = True
    cumulative_chronic_dose_sv: float = 0.0


@dataclass
class MaintenanceBot:
    """State of a single maintenance robot."""
    bot_id: str
    bot_type: BotType
    status: BotStatus = BotStatus.OPERATIONAL
    battery_pct: float = 100.0
    hours_since_charge: float = 0.0
    age_years: float = 0.0
    motor_age_years: float = 0.0
    sensor_months_since_cal: int = 0
    battery_age_years: float = 0.0
    repairs_completed: int = 0
    anomalies_detected: int = 0
    total_operational_hours: float = 0.0


@dataclass
class AnomalyReport:
    """Sensor anomaly detected by a maintenance bot."""
    year: float
    bot_id: str
    anomaly_type: AnomalyType
    sector: int
    severity: float  # 0.0-1.0
    description: str
    auto_repaired: bool = False


@dataclass
class RoboticsFleetState:
    """Aggregate state of the internal maintenance robot fleet."""
    bots: list[MaintenanceBot] = field(default_factory=list)
    total_anomalies_detected: int = 0
    total_repairs_completed: int = 0
    total_bot_failures: int = 0
    spare_motors: int = 40         # ESTIMATE — 2 motors per bot × 20 bots initial stock
    spare_sensors: int = 40        # ESTIMATE — 2 sensors per bot × 20 bots initial stock
    spare_batteries: int = 20      # ESTIMATE — 1 battery per bot × 20 bots initial stock
    mesh_network_health: float = 1.0
    sector_anomaly_counts: dict[int, int] = field(default_factory=dict)


# ════════════════════════════════════════════════════════════════════
#  1. MEDICAL EMERGENCIES SIMULATOR
# ════════════════════════════════════════════════════════════════════

class MedicalEmergencySimulator:
    """Full-fidelity medical emergency model for ARIA's generation ship.

    Models annual medical events, surgical capacity, drug availability,
    equipment degradation, childbirth at 0.56g, radiation sickness,
    psychological emergencies, and mortality.

    Links to critical_systems.DrugSynthesisSimulator for drug supply.
    """

    # Relative frequency of event types (must sum to ~1.0).
    # Derived from empirical incidence rates (Crucian et al. 2016 +
    # NASA flight surgeon data) via space_medical_rates module.
    # Infection is dominant because ISS data shows immune-related
    # events (rashes, respiratory, herpes) are by far the most common.
    _EMPIRICAL_DIST = get_event_distribution_from_empirical()
    EVENT_DISTRIBUTION: dict[MedicalEventType, float] = {
        MedicalEventType.TRAUMA: _EMPIRICAL_DIST["trauma"],
        MedicalEventType.DENTAL: _EMPIRICAL_DIST["dental"],
        MedicalEventType.INFECTION: _EMPIRICAL_DIST["infection"],
        MedicalEventType.PSYCHOLOGICAL: _EMPIRICAL_DIST["psychological"],
        MedicalEventType.BURN: _EMPIRICAL_DIST["burn"],
        MedicalEventType.CARDIAC: _EMPIRICAL_DIST["cardiac"],
        MedicalEventType.RADIATION_CHRONIC: _EMPIRICAL_DIST["radiation_chronic"],
        MedicalEventType.RADIATION_ACUTE: _EMPIRICAL_DIST["radiation_acute"],
        MedicalEventType.CHILDBIRTH: _EMPIRICAL_DIST["childbirth"],
        MedicalEventType.SURGICAL: _EMPIRICAL_DIST["surgical"],
    }

    # Probability that event type requires surgery.
    # ESTIMATE — Barratt & Pool 2008 *Principles of Clinical Medicine for Space Flight* §12
    # surgical need by category; exact fractions scaled from terrestrial trauma/cardiac registries.
    SURGERY_PROBABILITY: dict[MedicalEventType, float] = {
        MedicalEventType.TRAUMA: 0.30,          # ESTIMATE — ~30% trauma events need operative care (Barratt 2008)
        MedicalEventType.DENTAL: 0.10,          # ESTIMATE — ~10% need extraction/oral surgery (Barratt 2008)
        MedicalEventType.INFECTION: 0.05,       # ESTIMATE — ~5% infections need I&D surgery (Barratt 2008)
        MedicalEventType.PSYCHOLOGICAL: 0.0,    # no surgical intervention for psych events
        MedicalEventType.BURN: 0.20,            # ESTIMATE — ~20% burns need debridement/grafting (Barratt 2008)
        MedicalEventType.CARDIAC: 0.40,         # ESTIMATE — ~40% cardiac need intervention (Barratt 2008)
        MedicalEventType.RADIATION_CHRONIC: 0.0,  # chronic GCR: managed medically (Cucinotta 2006)
        MedicalEventType.RADIATION_ACUTE: 0.05, # ESTIMATE — 5% acute radiation cases need surgery (Barratt 2008)
        MedicalEventType.CHILDBIRTH: 0.35,      # WHO 2019 EmONC: C-section rate in isolated setting ~35%
        MedicalEventType.SURGICAL: 1.0,         # by definition (Tansey 2000 submarine surgical rate)
    }

    # Base severity distribution per event type: (minor, moderate, severe, critical).
    # ESTIMATE — Tansey 2000 USN submarine medical records + Lugg 2000 Antarctic station data.
    # Exact fractional splits are ESTIMATE calibrated to analog populations.
    SEVERITY_WEIGHTS: dict[MedicalEventType, tuple[float, ...]] = {
        MedicalEventType.TRAUMA: (0.3, 0.35, 0.25, 0.10),        # ESTIMATE — Tansey 2000 USN injury severity
        MedicalEventType.DENTAL: (0.5, 0.35, 0.10, 0.05),        # ESTIMATE — Lugg 2000 Antarctic dental records
        MedicalEventType.INFECTION: (0.3, 0.4, 0.2, 0.1),        # ESTIMATE — Crucian 2016 ISS infection severity
        MedicalEventType.PSYCHOLOGICAL: (0.2, 0.4, 0.3, 0.1),    # ESTIMATE — Kanas 2015 Space Psychology §6
        MedicalEventType.BURN: (0.2, 0.3, 0.3, 0.2),             # ESTIMATE — Tansey 2000 burn severity
        MedicalEventType.CARDIAC: (0.1, 0.3, 0.3, 0.3),          # ESTIMATE — NASA JSC 2020 cardiac review
        MedicalEventType.RADIATION_CHRONIC: (0.5, 0.3, 0.15, 0.05),  # Cucinotta 2006 GCR severity spectrum
        MedicalEventType.RADIATION_ACUTE: (0.1, 0.2, 0.3, 0.4),  # ICRP Pub.84 (2000) Table A-2 acute range
        MedicalEventType.CHILDBIRTH: (0.5, 0.3, 0.15, 0.05),     # WHO 2019 EmONC Report complication rate
        MedicalEventType.SURGICAL: (0.0, 0.2, 0.5, 0.3),         # ESTIMATE — Tansey 2000 elective vs urgent
    }

    def __init__(self, crew_size: int = CREW_SIZE, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.state = MedicalState(crew_size=crew_size)
        self._init_equipment()

    def _init_equipment(self) -> None:
        """Initialize medical equipment inventory."""
        self.state.equipment = [
            MedicalEquipment("MRI_scanner", mtbf_years=MRI_CRYOCOOLER_MTBF_YEARS),  # see constant above
            MedicalEquipment("surgical_tools", mtbf_years=SURGICAL_TOOL_LIFESPAN_YEARS),  # see constant above
            MedicalEquipment("autoclave", mtbf_years=AUTOCLAVE_MTBF_YEARS),  # see constant above
            # Ventilator 12 yr MTBF — ESTIMATE; FDA-cleared ICU ventilator service life 7-15 yr (FDA 510k)
            MedicalEquipment("ventilator", mtbf_years=12.0),      # ESTIMATE — FDA 510k ICU ventilator 7-15 yr
            # Defibrillator 8 yr — ESTIMATE; AED recommended replacement 8-10 yr (AHA 2020 guidelines)
            MedicalEquipment("defibrillator", mtbf_years=8.0),    # ESTIMATE — AHA 2020 AED replacement 8-10 yr
            # Portable ultrasound 10 yr — ESTIMATE; Mindray M7 rated 10,000 h operational life
            MedicalEquipment("ultrasound", mtbf_years=10.0),      # ESTIMATE — Mindray M7 10,000 h ≈ 10 yr
            # Medical centrifuge 20 yr — ESTIMATE; benchtop centrifuge 10-20 yr (ANSI/ASSE Z9.3:2012)
            MedicalEquipment("medical_centrifuge", mtbf_years=20.0),  # ESTIMATE — ANSI/ASSE Z9.3:2012
            # X-ray 12 yr — ESTIMATE; flat-panel detector service life 10-15 yr (IEC 60601-1)
            MedicalEquipment("xray", mtbf_years=12.0),            # ESTIMATE — IEC 60601-1 flat-panel 10-15 yr
        ]

    def _pick_severity(self, event_type: MedicalEventType) -> MedicalSeverity:
        """Pick severity using weighted distribution."""
        weights = self.SEVERITY_WEIGHTS[event_type]
        levels = [
            MedicalSeverity.MINOR,
            MedicalSeverity.MODERATE,
            MedicalSeverity.SEVERE,
            MedicalSeverity.CRITICAL,
        ]
        return self._rng.choices(levels, weights=weights, k=1)[0]

    def _pick_event_type(self) -> MedicalEventType:
        """Pick event type using frequency distribution."""
        types = list(self.EVENT_DISTRIBUTION.keys())
        weights = list(self.EVENT_DISTRIBUTION.values())
        return self._rng.choices(types, weights=weights, k=1)[0]

    def _generate_event(self, year: float) -> MedicalEvent:
        """Generate a single medical event."""
        event_type = self._pick_event_type()
        severity = self._pick_severity(event_type)
        patient_id = self._rng.randint(1, self.state.crew_size)

        needs_surgery = self._rng.random() < self.SURGERY_PROBABILITY[event_type]
        if severity == MedicalSeverity.CRITICAL:
            needs_surgery = True  # critical always needs surgery if survivable

        needs_anesthesia = needs_surgery and event_type != MedicalEventType.DENTAL

        return MedicalEvent(
            year=year,
            event_type=event_type,
            severity=severity,
            patient_id=patient_id,
            requires_surgery=needs_surgery,
            requires_anesthesia=needs_anesthesia,
            description=self._describe_event(event_type, severity),
        )

    def _describe_event(
        self, event_type: MedicalEventType, severity: MedicalSeverity
    ) -> str:
        """Generate human-readable event description."""
        descriptions = {
            MedicalEventType.TRAUMA: {
                MedicalSeverity.MINOR: "Minor laceration from industrial work at 0.56g",
                MedicalSeverity.MODERATE: "Fracture from fall — bone healing impaired at 0.56g",
                MedicalSeverity.SEVERE: "Crush injury in manufacturing bay, internal bleeding",
                MedicalSeverity.CRITICAL: "Multi-system trauma from equipment failure at 0.56g",
            },
            MedicalEventType.DENTAL: {
                MedicalSeverity.MINOR: "Cavity requiring filling — no Earth supply chain",
                MedicalSeverity.MODERATE: "Tooth extraction needed, local anesthetic",
                MedicalSeverity.SEVERE: "Dental abscess with systemic infection risk",
                MedicalSeverity.CRITICAL: "Jaw fracture requiring surgical reconstruction",
            },
            MedicalEventType.BURN: {
                MedicalSeverity.MINOR: "First-degree burn from hot pipe contact",
                MedicalSeverity.MODERATE: "Second-degree burns, 5% BSA, from coolant splash",
                MedicalSeverity.SEVERE: "Third-degree burns, 15% BSA, from electrical fire",
                MedicalSeverity.CRITICAL: "Major burns >30% BSA from fire emergency",
            },
            MedicalEventType.PSYCHOLOGICAL: {
                MedicalSeverity.MINOR: "Acute anxiety episode, resolved with counseling",
                MedicalSeverity.MODERATE: "Depressive episode requiring medication adjustment",
                MedicalSeverity.SEVERE: "Psychotic break requiring sedation and isolation",
                MedicalSeverity.CRITICAL: "Suicide attempt — immediate intervention required",
            },
            MedicalEventType.CHILDBIRTH: {
                MedicalSeverity.MINOR: "Normal delivery at 0.56g, no complications",
                MedicalSeverity.MODERATE: "Prolonged labor at 0.56g, oxytocin augmentation",
                MedicalSeverity.SEVERE: "Childbirth complication, medical centrifuge to 1g",
                MedicalSeverity.CRITICAL: "Emergency cesarean section at 0.56g",
            },
            MedicalEventType.RADIATION_ACUTE: {
                MedicalSeverity.MINOR: "Mild ARS from SPE, <1 Sv, nausea and fatigue",
                MedicalSeverity.MODERATE: "Moderate ARS, 1-2 Sv, lymphocyte depression",
                MedicalSeverity.SEVERE: "Severe ARS, 2-4 Sv, bone marrow suppression",
                MedicalSeverity.CRITICAL: "Lethal dose >4 Sv from unshielded SPE exposure",
            },
        }
        type_descs = descriptions.get(event_type, {})
        return type_descs.get(
            severity,
            f"{event_type.value} event, severity: {severity.value}",
        )

    def _treat_event(self, event: MedicalEvent) -> list[dict[str, Any]]:
        """Attempt to treat a medical event. Returns log entries."""
        logs: list[dict[str, Any]] = []
        s = self.state

        # Check surgical capacity
        if event.requires_surgery:
            if s.surgical_suite_in_use:
                event.treatment_delay_hours = self._rng.uniform(2.0, 12.0)
                if event.severity == MedicalSeverity.CRITICAL:
                    # Delayed critical surgery — elevated mortality.
                    # Raut 2019 (J Trauma Acute Care Surg 87): delayed
                    # emergency surgery mortality ~10% (not 30%).
                    if self._rng.random() < 0.10:
                        event.outcome = "death_delayed_surgery"
                        event.severity = MedicalSeverity.FATAL
                        s.total_deaths += 1
                        logs.append({
                            "year": event.year, "severity": "FATAL",
                            "message": (
                                f"Patient {event.patient_id} died waiting for "
                                f"surgical suite. Delay: {event.treatment_delay_hours:.1f}h. "
                                f"Ship has only {SURGICAL_SUITES} suite(s)."
                            ),
                            "subsystem": "medical",
                        })
                        return logs

            # Check anesthesia availability
            if event.requires_anesthesia:
                if s.anesthesia_doses < ANESTHESIA_DOSES_PER_SURGERY:
                    if s.drug_synthesis_available:
                        logs.append({
                            "year": event.year, "severity": "WARNING",
                            "message": "Anesthesia low, emergency synthesis requested",
                            "subsystem": "medical",
                        })
                    else:
                        # No anesthesia, no synthesis — surgery without anesthesia.
                        # Historic battlefield surgery mortality (Bell 2008,
                        # Mil Med 173): ~5% with experienced surgeon and
                        # improvised analgesia. Ship has both.
                        event.outcome = "surgery_no_anesthesia"
                        if self._rng.random() < 0.05:
                            event.severity = MedicalSeverity.FATAL
                            event.outcome = "death_no_anesthesia"
                            s.total_deaths += 1
                            s.untreatable_events += 1
                            logs.append({
                                "year": event.year, "severity": "FATAL",
                                "message": (
                                    f"Patient {event.patient_id} died during surgery "
                                    f"without anesthesia. Drug synthesis offline."
                                ),
                                "subsystem": "medical",
                            })
                            return logs
                else:
                    s.anesthesia_doses -= ANESTHESIA_DOSES_PER_SURGERY

            s.surgical_suite_in_use = True
            s.total_surgeries += 1

        # Check equipment degradation impact
        for equip in s.equipment:
            if equip.status == EquipmentStatus.FAILED:
                if event.severity in (MedicalSeverity.SEVERE, MedicalSeverity.CRITICAL):
                    if equip.name in ("MRI_scanner", "ventilator", "defibrillator"):
                        # Missing critical equipment for severe case.
                        # Field hospital survival without advanced imaging
                        # still >95% for stable trauma (Eastridge 2012,
                        # J Trauma 73, Iraq/Afghanistan casualty data).
                        if self._rng.random() < 0.03:
                            event.outcome = f"death_no_{equip.name}"
                            event.severity = MedicalSeverity.FATAL
                            s.total_deaths += 1
                            s.untreatable_events += 1
                            logs.append({
                                "year": event.year, "severity": "FATAL",
                                "message": (
                                    f"Patient {event.patient_id}: {event.event_type.value} "
                                    f"could not be treated — {equip.name} is offline."
                                ),
                                "subsystem": "medical",
                            })
                            return logs

        # Baseline mortality for critical events.
        # Moore 2020 J Trauma 88: National Trauma Data Bank survival >97% with full ICU
        # → 3% mortality rate for critical events in best-case in-situ treatment
        if event.severity == MedicalSeverity.CRITICAL and event.outcome == "pending":
            if self._rng.random() < 0.03:  # Moore 2020 J Trauma 88: 3% critical event mortality
                event.outcome = "death_despite_treatment"
                event.severity = MedicalSeverity.FATAL
                s.total_deaths += 1
                logs.append({
                    "year": event.year, "severity": "FATAL",
                    "message": (
                        f"Patient {event.patient_id} died despite treatment. "
                        f"Event: {event.event_type.value}, severity: critical."
                    ),
                    "subsystem": "medical",
                })
                return logs

        # Successful treatment
        if event.outcome == "pending":
            event.outcome = "treated"

        # Release surgical suite
        if event.requires_surgery:
            s.surgical_suite_in_use = False

        return logs

    def _handle_childbirth(self, event: MedicalEvent, year: float) -> list[dict[str, Any]]:
        """Special handling for childbirth events at 0.56g."""
        logs: list[dict[str, Any]] = []
        s = self.state

        s.total_births += 1

        # Check if medical centrifuge is available for complicated births
        centrifuge = None
        for equip in s.equipment:
            if equip.name == "medical_centrifuge":
                centrifuge = equip
                break

        complication_rate = CHILDBIRTH_COMPLICATION_RATE_056G
        if centrifuge and centrifuge.status == EquipmentStatus.OPERATIONAL:
            # Centrifuge available — can deliver at simulated 1g
            complication_rate = CHILDBIRTH_COMPLICATION_RATE_1G

        if self._rng.random() < complication_rate:
            s.birth_complications += 1
            logs.append({
                "year": year, "severity": "WARNING",
                "message": (
                    f"Childbirth complication at {SHIP_GRAVITY_G}g. "
                    f"Centrifuge {'available' if centrifuge and centrifuge.status == EquipmentStatus.OPERATIONAL else 'UNAVAILABLE'}. "
                    f"Complication rate: {complication_rate:.0%}."
                ),
                "subsystem": "medical",
            })

        return logs

    def _degrade_equipment(self, year: float) -> list[dict[str, Any]]:
        """Age and potentially fail medical equipment each year."""
        logs: list[dict[str, Any]] = []

        for equip in self.state.equipment:
            if equip.status == EquipmentStatus.FAILED:
                continue

            equip.age_years += 1.0

            # Weibull CDF: P(fail) = 1 - exp(-(t/η)^β)
            # β=2 wear-out regime — Abernethy 2006 *Weibull Analysis Handbook* §3.4
            fail_prob = 1.0 - math.exp(-((equip.age_years / equip.mtbf_years) ** 2))  # Abernethy 2006 §3.4 β=2
            equip.degradation = min(1.0, fail_prob)

            if equip.degradation > 0.7:
                equip.status = EquipmentStatus.DEGRADED

            if self._rng.random() < fail_prob * 0.1:
                equip.status = EquipmentStatus.FAILED
                logs.append({
                    "year": year, "severity": "EMERGENCY",
                    "message": (
                        f"Medical equipment FAILED: {equip.name} "
                        f"(age: {equip.age_years:.0f} yr, MTBF: {equip.mtbf_years:.0f} yr). "
                        f"Requires onboard manufacturing for replacement."
                    ),
                    "subsystem": "medical",
                })

        return logs

    def _accumulate_chronic_radiation(self, year: float) -> list[dict[str, Any]]:
        """Track cumulative chronic GCR exposure."""
        logs: list[dict[str, Any]] = []
        s = self.state

        annual_dose = CHRONIC_GCR_ANNUAL_SV * (0.8 + 0.4 * self._rng.random())
        s.cumulative_chronic_dose_sv += annual_dose

        # Cancer risk: linear no-threshold model (LNT)
        # ICRP 103 (2007) §A.4.4: nominal risk coefficient 5.5% per Sv whole-body effective dose
        cancer_risk = s.cumulative_chronic_dose_sv * 0.055  # ICRP 103 (2007) §A.4.4: 5.5%/Sv LNT
        if cancer_risk > 0.1 and year % 10 == 0:
            logs.append({
                "year": year, "severity": "WARNING",
                "message": (
                    f"Cumulative GCR dose: {s.cumulative_chronic_dose_sv:.2f} Sv. "
                    f"Estimated excess cancer risk: {cancer_risk:.1%}."
                ),
                "subsystem": "medical",
            })

        return logs

    def _replenish_anesthesia(self) -> None:
        """Replenish anesthesia if drug synthesis is online."""
        if self.state.drug_synthesis_available:
            # Biomanufacturing produces ~10 doses/year (ESTIMATE — Post 2012 Meat Sci 92 297 bioreactor scale)
            self.state.anesthesia_doses = min(
                30.0,  # ESTIMATE — maximum stockpile ~30 doses (Barratt & Pool 2008 §12)
                self.state.anesthesia_doses + 10.0  # ESTIMATE — annual bioproduction rate
            )

    def simulate_year(
        self, mission_year: float, spe_dose_sv: float = 0.0
    ) -> list[dict[str, Any]]:
        """Simulate one year of medical events.

        Args:
            mission_year: Current mission year.
            spe_dose_sv: Additional acute radiation dose from SPE events
                this year (0.0 if no SPE).

        Returns:
            List of event log dictionaries.
        """
        events: list[dict[str, Any]] = []
        s = self.state

        # --- Equipment degradation ---
        events.extend(self._degrade_equipment(mission_year))

        # --- Chronic radiation ---
        events.extend(self._accumulate_chronic_radiation(mission_year))

        # --- Replenish drugs ---
        self._replenish_anesthesia()

        # --- Generate medical events ---
        # Poisson arrival, not a hard integer floor. A tiny crew should see
        # <1 event/yr on average — the old `max(1, ...)` floor silently
        # inflated the rate ~3× for 4-person missions and exhausted the crew.
        lam = ANNUAL_EVENT_RATE_PER_100 * s.crew_size / 100.0
        n_events = 0
        if lam > 0:
            L = math.exp(-lam)
            p = 1.0
            while p > L:
                n_events += 1
                p *= self._rng.random()
            n_events -= 1
        s.total_events += n_events

        for _ in range(n_events):
            event = self._generate_event(mission_year)

            # Special: acute radiation from SPE
            if spe_dose_sv > ACUTE_RADIATION_MILD_SV:
                # SPE hit — add radiation cases
                if self._rng.random() < 0.3:
                    event = MedicalEvent(
                        year=mission_year,
                        event_type=MedicalEventType.RADIATION_ACUTE,
                        severity=(
                            MedicalSeverity.CRITICAL if spe_dose_sv > ACUTE_RADIATION_SEVERE_SV
                            else MedicalSeverity.SEVERE if spe_dose_sv > ACUTE_RADIATION_MILD_SV * 2
                            else MedicalSeverity.MODERATE
                        ),
                        patient_id=self._rng.randint(1, s.crew_size),
                        requires_surgery=False,
                        description=f"Acute radiation sickness from SPE: {spe_dose_sv:.2f} Sv",
                    )
                    s.radiation_cases += 1

            # Special handling for childbirth
            if event.event_type == MedicalEventType.CHILDBIRTH:
                events.extend(self._handle_childbirth(event, mission_year))

            # Special handling for psychological emergencies
            if event.event_type == MedicalEventType.PSYCHOLOGICAL:
                s.psych_emergencies += 1
                if event.severity == MedicalSeverity.CRITICAL:
                    # Suicide risk
                    if self._rng.random() < PSYCH_SUICIDE_RISK_FRACTION:
                        event.severity = MedicalSeverity.FATAL
                        event.outcome = "suicide"
                        s.total_deaths += 1
                        events.append({
                            "year": mission_year, "severity": "FATAL",
                            "message": (
                                f"Crew member {event.patient_id}: suicide. "
                                f"Generation ship psychological support inadequate."
                            ),
                            "subsystem": "medical",
                        })
                        continue

            # Treat the event
            treatment_logs = self._treat_event(event)
            events.extend(treatment_logs)

        # --- Anesthesia consumption tracking ---
        if s.anesthesia_doses < 5:
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": (
                    f"Anesthesia supply critically low: {s.anesthesia_doses:.0f} doses. "
                    f"Drug synthesis {'ONLINE' if s.drug_synthesis_available else 'OFFLINE'}."
                ),
                "subsystem": "medical",
            })

        return events

    def get_mortality_rate(self) -> float:
        """Calculate observed annual mortality rate."""
        if self.state.total_events == 0:
            return 0.0
        return self.state.total_deaths / max(1, self.state.total_events)

    def get_equipment_status(self) -> dict[str, str]:
        """Return status of all medical equipment."""
        return {e.name: e.status.value for e in self.state.equipment}

    def repair_equipment(self, name: str) -> bool:
        """Repair a piece of failed medical equipment."""
        for equip in self.state.equipment:
            if equip.name == name and equip.status in (
                EquipmentStatus.FAILED, EquipmentStatus.DEGRADED
            ):
                equip.status = EquipmentStatus.OPERATIONAL
                equip.degradation = 0.0
                equip.age_years = 0.0
                return True
        return False


# ════════════════════════════════════════════════════════════════════
#  2. INTERNAL MAINTENANCE ROBOTICS
# ════════════════════════════════════════════════════════════════════

class MaintenanceRoboticsFleet:
    """Fleet of 20 internal maintenance robots for ARIA's generation ship.

    Five types (4 each): PipeBot, DuctBot, HullBot, WiringBot, CleanBot.
    Bots operate on 8-hour battery cycles, report to ARIA via mesh network,
    and detect anomalies that trigger automated or human repair dispatch.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.state = RoboticsFleetState()
        self._init_fleet()

    def _init_fleet(self) -> None:
        """Create the 20-bot fleet: 4 of each type."""
        bots: list[MaintenanceBot] = []
        for bot_type in BotType:
            for i in range(BOTS_PER_TYPE):
                bot_id = f"{bot_type.value}_{i+1:02d}"
                bots.append(MaintenanceBot(bot_id=bot_id, bot_type=bot_type))
        self.state.bots = bots

    def get_operational_count(self) -> int:
        """Count bots currently operational or charging."""
        return sum(
            1 for b in self.state.bots
            if b.status in (BotStatus.OPERATIONAL, BotStatus.CHARGING)
        )

    def get_bots_by_type(self, bot_type: BotType) -> list[MaintenanceBot]:
        """Get all bots of a specific type."""
        return [b for b in self.state.bots if b.bot_type == bot_type]

    def _operate_bot(self, bot: MaintenanceBot, hours: float) -> list[AnomalyReport]:
        """Simulate a bot operating for given hours. Returns anomaly reports."""
        anomalies: list[AnomalyReport] = []

        if bot.status != BotStatus.OPERATIONAL:
            return anomalies

        bot.hours_since_charge += hours
        bot.total_operational_hours += hours
        bot.battery_pct = max(0.0, 100.0 * (1.0 - bot.hours_since_charge / BOT_BATTERY_HOURS))

        # Battery depleted — must charge
        if bot.battery_pct <= 0.0:
            bot.status = BotStatus.CHARGING
            bot.hours_since_charge = 0.0
            return anomalies

        # Anomaly detection probability per operating period
        detection_prob = self._anomaly_detection_prob(bot)

        if self._rng.random() < detection_prob:
            anomaly = self._generate_anomaly(bot)
            anomalies.append(anomaly)
            bot.anomalies_detected += 1
            self.state.total_anomalies_detected += 1

            sector = anomaly.sector
            self.state.sector_anomaly_counts[sector] = (
                self.state.sector_anomaly_counts.get(sector, 0) + 1
            )

            # Auto-repair if minor
            if anomaly.severity < 0.3:
                anomaly.auto_repaired = True
                bot.repairs_completed += 1
                self.state.total_repairs_completed += 1

        return anomalies

    def _anomaly_detection_prob(self, bot: MaintenanceBot) -> float:
        """Probability of detecting an anomaly in one operating period.

        Depends on bot type and sensor calibration freshness.
        """
        # Detection probabilities per operating period — ESTIMATE calibrated to
        # Astrobee inspection coverage data (Fong 2013 NASA TM-2013-216503 §4.2)
        base_probs = {
            BotType.PIPE_BOT: 0.15,    # ESTIMATE — Fong 2013 NASA TM-2013-216503 pipe inspection coverage
            BotType.DUCT_BOT: 0.12,    # ESTIMATE — duct bot HEPA filter check cadence
            BotType.HULL_BOT: 0.08,    # ESTIMATE — hull inspection: lower anomaly density
            BotType.WIRING_BOT: 0.10,  # ESTIMATE — wiring conduit inspection coverage
            BotType.CLEAN_BOT: 0.18,   # ESTIMATE — CleanBot surface coverage higher (more area per sortie)
        }
        base = base_probs.get(bot.bot_type, 0.10)

        # Sensor calibration decay: detection drops if overdue
        cal_months = bot.sensor_months_since_cal
        if cal_months > BOT_SENSOR_CALIBRATION_MONTHS:
            overdue = cal_months - BOT_SENSOR_CALIBRATION_MONTHS
            base *= max(0.3, 1.0 - overdue * 0.1)

        return base

    def _generate_anomaly(self, bot: MaintenanceBot) -> AnomalyReport:
        """Generate an anomaly report based on bot type."""
        type_anomalies = {
            BotType.PIPE_BOT: [
                (AnomalyType.BIOFILM, "Biofilm buildup in pipe section"),
                (AnomalyType.CORROSION, "Pipe wall corrosion pit detected"),
                (AnomalyType.MICRO_LEAK, "Micro-leak at pipe joint, <2mm"),
            ],
            BotType.DUCT_BOT: [
                (AnomalyType.FILTER_CLOGGED, "HEPA filter at 80%+ pressure drop"),
                (AnomalyType.MOLD_COLONY, "Mold colony detected via VOC sensor"),
                (AnomalyType.CONTAMINATION, "Elevated particulate count in duct"),
            ],
            BotType.HULL_BOT: [
                (AnomalyType.MICRO_LEAK, "Hull micro-penetration, <0.5mm"),
                (AnomalyType.WELD_FATIGUE, "Acoustic emission at weld seam"),
                (AnomalyType.CORROSION, "Hull plate surface corrosion"),
            ],
            BotType.WIRING_BOT: [
                (AnomalyType.CABLE_DEGRADATION, "Kapton insulation below threshold"),
                (AnomalyType.INSULATION_DEGRADATION, "Capacitive sensor: insulation loss"),
                (AnomalyType.CORROSION, "Connector corrosion detected"),
            ],
            BotType.CLEAN_BOT: [
                (AnomalyType.BIOFILM, "Biofilm at pipe junction access point"),
                (AnomalyType.CONTAMINATION, "Contamination hotspot in corridor"),
                (AnomalyType.MOLD_COLONY, "Surface mold colony in maintenance bay"),
            ],
        }

        options = type_anomalies.get(bot.bot_type, [
            (AnomalyType.CONTAMINATION, "General anomaly detected"),
        ])
        anomaly_type, description = self._rng.choice(options)
        sector = self._rng.randint(1, 12)
        severity = self._rng.uniform(0.05, 0.95)

        return AnomalyReport(
            year=0.0,  # set by simulate_year
            bot_id=bot.bot_id,
            anomaly_type=anomaly_type,
            sector=sector,
            severity=severity,
            description=description,
        )

    def _age_bots(self) -> list[dict[str, Any]]:
        """Age all bots by one year. Handle component degradation."""
        events: list[dict[str, Any]] = []

        for bot in self.state.bots:
            if bot.status == BotStatus.DESTROYED:
                continue

            bot.age_years += 1.0
            bot.motor_age_years += 1.0
            bot.battery_age_years += 1.0
            bot.sensor_months_since_cal += 12

            # Motor failure check
            if bot.motor_age_years >= BOT_MOTOR_LIFESPAN_YEARS:
                if self.state.spare_motors > 0:
                    self.state.spare_motors -= 1
                    bot.motor_age_years = 0.0
                    bot.status = BotStatus.MAINTENANCE
                    events.append({
                        "year": 0.0, "severity": "INFO",
                        "message": (
                            f"{bot.bot_id}: motor replaced "
                            f"(spare motors remaining: {self.state.spare_motors})"
                        ),
                        "subsystem": "robotics",
                    })
                else:
                    bot.status = BotStatus.DAMAGED
                    self.state.total_bot_failures += 1
                    events.append({
                        "year": 0.0, "severity": "WARNING",
                        "message": (
                            f"{bot.bot_id}: motor failure, NO SPARE MOTORS. "
                            f"Bot offline until manufacturing produces replacement."
                        ),
                        "subsystem": "robotics",
                    })

            # Battery replacement check
            if bot.battery_age_years >= BOT_BATTERY_LIFESPAN_YEARS:
                if self.state.spare_batteries > 0:
                    self.state.spare_batteries -= 1
                    bot.battery_age_years = 0.0
                else:
                    bot.status = BotStatus.DAMAGED
                    self.state.total_bot_failures += 1
                    events.append({
                        "year": 0.0, "severity": "WARNING",
                        "message": (
                            f"{bot.bot_id}: battery depleted, no spares. "
                            f"Bot offline."
                        ),
                        "subsystem": "robotics",
                    })

        return events

    def _recharge_bots(self) -> None:
        """Recharge any charging bots (simulated as instant per year step)."""
        for bot in self.state.bots:
            if bot.status == BotStatus.CHARGING:
                bot.battery_pct = 100.0
                bot.hours_since_charge = 0.0
                bot.status = BotStatus.OPERATIONAL

    def _return_from_maintenance(self) -> None:
        """Return bots from maintenance to operational."""
        for bot in self.state.bots:
            if bot.status == BotStatus.MAINTENANCE:
                bot.status = BotStatus.OPERATIONAL

    def _check_mesh_network(self) -> list[dict[str, Any]]:
        """Assess mesh network health based on operational bot count."""
        events: list[dict[str, Any]] = []
        operational = self.get_operational_count()
        # Mesh degrades if too few nodes
        self.state.mesh_network_health = min(1.0, operational / (TOTAL_FLEET_SIZE * 0.5))

        if self.state.mesh_network_health < 0.6:
            events.append({
                "year": 0.0, "severity": "WARNING",
                "message": (
                    f"Mesh network degraded: {self.state.mesh_network_health:.0%} health. "
                    f"Only {operational}/{TOTAL_FLEET_SIZE} bots online. "
                    f"Anomaly detection coverage reduced."
                ),
                "subsystem": "robotics",
            })

        return events

    def get_sector_hotspots(self, threshold: int = 3) -> list[int]:
        """Return sectors with anomaly counts above threshold.

        ARIA uses this for proactive maintenance dispatch.
        """
        return [
            sector for sector, count in self.state.sector_anomaly_counts.items()
            if count >= threshold
        ]

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        """Simulate one year of fleet operations.

        Returns list of event log dictionaries.
        """
        events: list[dict[str, Any]] = []

        # Return bots from previous year's maintenance/charging
        self._recharge_bots()
        self._return_from_maintenance()

        # Age bots (component degradation)
        age_events = self._age_bots()
        for e in age_events:
            e["year"] = mission_year
        events.extend(age_events)

        # Operate each bot for a simulated year (~2000 hours useful)
        all_anomalies: list[AnomalyReport] = []
        for bot in self.state.bots:
            if bot.status == BotStatus.OPERATIONAL:
                # Simulate ~250 work days × 8 hours, chunked
                anomalies = self._operate_bot(bot, hours=6.0)
                for a in anomalies:
                    a.year = mission_year
                all_anomalies.extend(anomalies)

        # Log significant anomalies
        for anomaly in all_anomalies:
            if anomaly.severity > 0.5:
                events.append({
                    "year": mission_year,
                    "severity": "WARNING" if anomaly.severity < 0.8 else "CRITICAL",
                    "message": (
                        f"{anomaly.bot_id} detected {anomaly.anomaly_type.value} "
                        f"in Sector {anomaly.sector}: {anomaly.description} "
                        f"(severity: {anomaly.severity:.2f})"
                        + (" [AUTO-REPAIRED]" if anomaly.auto_repaired else " [HUMAN DISPATCH NEEDED]")
                    ),
                    "subsystem": "robotics",
                })

        # Check mesh network
        mesh_events = self._check_mesh_network()
        for e in mesh_events:
            e["year"] = mission_year
        events.extend(mesh_events)

        return events

    def add_spare_parts(self, motors: int = 0, sensors: int = 0, batteries: int = 0) -> None:
        """Add manufactured spare parts to inventory."""
        self.state.spare_motors += motors
        self.state.spare_sensors += sensors
        self.state.spare_batteries += batteries

    def repair_bot(self, bot_id: str) -> bool:
        """Manually repair a damaged bot (requires spare parts)."""
        for bot in self.state.bots:
            if bot.bot_id == bot_id and bot.status == BotStatus.DAMAGED:
                if self.state.spare_motors > 0:
                    self.state.spare_motors -= 1
                    bot.status = BotStatus.OPERATIONAL
                    bot.motor_age_years = 0.0
                    bot.battery_age_years = 0.0
                    return True
        return False


# ════════════════════════════════════════════════════════════════════
#  3. COMBINED ORCHESTRATOR
# ════════════════════════════════════════════════════════════════════

class MedicalRoboticsOrchestrator:
    """Runs medical emergencies and internal robotics together.

    Cross-system interactions:
      - CleanBot biofilm detections feed into infection risk
      - DuctBot mold detections affect respiratory illness rates
      - Bot fleet health affects ship maintenance → accident rates
    """

    def __init__(
        self,
        crew_size: int = CREW_SIZE,
        seed: int | None = None,
    ) -> None:
        self.medical = MedicalEmergencySimulator(crew_size=crew_size, seed=seed)
        self.robotics = MaintenanceRoboticsFleet(
            seed=(seed + 1000) if seed is not None else None
        )
        self._rng = random.Random(seed)

    def simulate_year(
        self, mission_year: float, spe_dose_sv: float = 0.0
    ) -> list[dict[str, Any]]:
        """Simulate one year of both subsystems with cross-system effects."""
        events: list[dict[str, Any]] = []

        # Run robotics first — their findings affect medical risks
        robotics_events = self.robotics.simulate_year(mission_year)
        events.extend(robotics_events)

        # Cross-system: poor maintenance → higher trauma rate
        fleet_health = self.robotics.get_operational_count() / TOTAL_FLEET_SIZE
        if fleet_health < 0.5:
            # Degraded ship maintenance increases accident risk
            # Temporarily boost crew size to increase event count
            original_crew = self.medical.state.crew_size
            self.medical.state.crew_size = int(original_crew * 1.3)
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": (
                    f"Maintenance fleet at {fleet_health:.0%} capacity. "
                    f"Accident risk elevated due to deferred ship maintenance."
                ),
                "subsystem": "medical_robotics_interaction",
            })

        medical_events = self.medical.simulate_year(mission_year, spe_dose_sv)
        events.extend(medical_events)

        # Restore crew size if modified
        self.medical.state.crew_size = CREW_SIZE if fleet_health < 0.5 else self.medical.state.crew_size

        return events

    def simulate_decade(
        self, start_year: float, spe_years: dict[float, float] | None = None
    ) -> list[dict[str, Any]]:
        """Simulate 10 years, optionally with SPE events in specific years."""
        all_events: list[dict[str, Any]] = []
        spe_years = spe_years or {}

        for yr in range(int(start_year), int(start_year) + 10):
            year_f = float(yr)
            spe_dose = spe_years.get(year_f, 0.0)
            year_events = self.simulate_year(year_f, spe_dose_sv=spe_dose)
            all_events.extend(year_events)

        return all_events

    def get_summary(self) -> dict[str, Any]:
        """Return combined summary of both subsystems."""
        med = self.medical.state
        rob = self.robotics.state
        return {
            "medical": {
                "total_events": med.total_events,
                "total_surgeries": med.total_surgeries,
                "total_deaths": med.total_deaths,
                "total_births": med.total_births,
                "birth_complications": med.birth_complications,
                "psych_emergencies": med.psych_emergencies,
                "radiation_cases": med.radiation_cases,
                "untreatable_events": med.untreatable_events,
                "anesthesia_doses": med.anesthesia_doses,
                "cumulative_radiation_sv": med.cumulative_chronic_dose_sv,
                "equipment_status": self.medical.get_equipment_status(),
            },
            "robotics": {
                "fleet_size": TOTAL_FLEET_SIZE,
                "operational": self.robotics.get_operational_count(),
                "total_anomalies": rob.total_anomalies_detected,
                "total_repairs": rob.total_repairs_completed,
                "bot_failures": rob.total_bot_failures,
                "spare_motors": rob.spare_motors,
                "spare_batteries": rob.spare_batteries,
                "mesh_health": rob.mesh_network_health,
                "sector_hotspots": self.robotics.get_sector_hotspots(),
            },
        }
