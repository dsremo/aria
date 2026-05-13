"""Breakthrough Technologies for Generation Ship Survival.

Every bottleneck we identified has a real solution being developed NOW.
This module implements science-backed models for each.

═══════════════════════════════════════════════════════════════
 BOTTLENECK → SOLUTION (all backed by real research)
═══════════════════════════════════════════════════════════════

DNA template degradation → SILICA GLASS STORAGE
  Microsoft Project Silica: femtosecond laser writes to glass
  4.8 TB per 120mm plate, stable 10,000+ years
  Reed-Solomon error correction, borosilicate glass
  DNA encoded in glass survives >4.4M years of radiation
  Reference: Nature (2025), doi:10.1038/s41586-025-10042-w

3D printers breaking → NANOBOT REPAIR SWARMS
  DNA-folding nanorobots that self-replicate
  Patrol surfaces 24/7, detect microfractures
  Carry self-healing compounds, seal breaches autonomously
  Can repair at molecular level — no macro tools needed
  Reference: New Atlas (2024), DNA nanorobots self-replication

Food shortage → CELL-FREE BIOMANUFACTURING
  Cell-free protein synthesis (CFPS) — no living cells needed
  PURE system: 36 enzymes + ribosomes = protein from DNA template
  Artificial photosynthetic cells: ATP from light, protein from CO2
  Self-replicating artificial cells demonstrated (Danelon group)
  Reference: PMC 10196276, ACS Synth Bio

Radiation damage → SYNTHETIC TORPOR
  Induce hibernation-like state: metabolism drops 90%
  Body temp 32°C → 15°C, heart rate drops to 5-10 bpm
  Radiation damage reduced: hypoxia + hypothermia = radioprotection
  Muscle/bone preserved despite months of inactivity
  Already demonstrated in non-hibernating animals
  Reference: MDPI Life 11(1):54 (2021), ESA torpor strategy

Knowledge loss → GLASS ARCHIVAL STORAGE
  Microsoft Project Silica: data in borosilicate glass
  10,000 year verified stability (accelerated aging tests)
  4.8 TB per plate, machine-learning read/write optimization
  Immune to: fire, flood, EMP, magnetic fields, most radiation
  Reference: Nature (2025), Microsoft Research

Hull damage → SELF-HEALING MATERIALS + NANOBOT REPAIR
  ESA HealTech: composites that self-heal at 100-140°C
  Shape-memory alloys: deform under impact, return to shape
  Nanobot-delivered sealant for micro-breaches
  Redundant hull layers (Whipple + fabric + structural + healing)

Psychological decay → AI-MEDIATED VIRTUAL ENVIRONMENTS
  VR environments for variety (forests, oceans, cities)
  AI therapist (ARIA's cognitive engine for crew support)
  Virtual windows showing space / simulated Earth scenes
  Exercise gamification, social event planning
  Education system maintaining purpose across generations
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


# ════════════════════════════════════════════════════════════════
#  1. DNA/KNOWLEDGE PRESERVATION — Silica Glass Storage
# ════════════════════════════════════════════════════════════════

@dataclass
class SilicaGlassArchive:
    """Microsoft Project Silica-inspired archival storage.

    Femtosecond laser writes voxels into borosilicate glass.
    4.8 TB per 120mm plate. Stable 10,000+ years.
    Immune to: radiation, EMP, magnetic fields, fire, water.

    This SOLVES the DNA template preservation bottleneck.
    Enzyme DNA templates encoded in glass survive the entire mission.
    """
    # 5D optical storage in fused silica: ~360 TB per disc (Kazansky 2016
    # *arXiv* 1607.06951); scaled to plate form factor ~4.8 TB/plate
    # is conservative for a 100 mm fused-silica plate (ESTIMATE — plate
    # form factor vs. disc not directly comparable).
    num_plates: int = 100  # 100 plates × 4.8 TB = 480 TB total
    capacity_tb_per_plate: float = 4.8  # ESTIMATE — Kazansky 2016 arXiv 1607.06951 scaled
    plate_health: list[float] = field(default_factory=lambda: [1.0] * 100)
    total_capacity_tb: float = 480.0

    # What's stored
    enzyme_dna_templates: float = 1.0  # Completeness (0-1)
    knowledge_base: float = 1.0        # All human knowledge
    engineering_blueprints: float = 1.0
    medical_database: float = 1.0
    cultural_archive: float = 1.0

    # Reed-Solomon error correction
    redundancy_factor: int = 5  # Each datum stored 5× across plates
    error_correction_overhead: float = 0.3  # 30% overhead for ECC

    # Reader/writer health (THIS is what degrades, not the glass)
    reader_health: float = 1.0   # Optical reader
    writer_health: float = 1.0   # Femtosecond laser writer
    reader_spares: int = 5
    writer_spares: int = 3

    # Degradation rate: glass itself is ~0.001%/century
    glass_degradation_per_year: float = 0.00001  # Effectively zero


class SilicaArchiveSimulator:
    """Simulates silica glass archival storage over millennia.

    The glass is essentially permanent. The bottleneck becomes
    the reader/writer hardware — but that can be 3D printed.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.archive = SilicaGlassArchive()

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        a = self.archive

        # Glass degradation: essentially zero (0.001% per century)
        for i in range(len(a.plate_health)):
            a.plate_health[i] = max(0, a.plate_health[i] - a.glass_degradation_per_year)

        # Reader/writer degradation: mechanical/optical components age
        a.reader_health = max(0, a.reader_health - 0.02)  # 2%/year
        a.writer_health = max(0, a.writer_health - 0.03)  # 3%/year

        # Replace reader/writer when health drops below 30%
        if a.reader_health < 0.3 and a.reader_spares > 0:
            a.reader_health = 0.9
            a.reader_spares -= 1
            events.append({
                "year": mission_year, "severity": "NOMINAL",
                "message": f"Glass archive reader replaced. {a.reader_spares} spares remaining.",
                "subsystem": "archival_storage",
            })

        if a.writer_health < 0.3 and a.writer_spares > 0:
            a.writer_health = 0.9
            a.writer_spares -= 1

        # Data integrity check (Reed-Solomon catches errors)
        intact_plates = sum(1 for h in a.plate_health if h > 0.5)
        min_plates_for_recovery = a.num_plates // a.redundancy_factor
        if intact_plates >= min_plates_for_recovery:
            # Data fully recoverable
            a.enzyme_dna_templates = 1.0
            a.knowledge_base = 1.0
        else:
            data_loss = 1.0 - (intact_plates / min_plates_for_recovery)
            a.enzyme_dna_templates = max(0, 1.0 - data_loss)
            if not getattr(self, "_archive_degraded_latched", False):
                events.append({
                    "year": mission_year, "severity": "CRITICAL",
                    "message": f"Glass archive degraded: {intact_plates}/{a.num_plates} plates intact. "
                               f"Data integrity: {a.enzyme_dna_templates:.0%}",
                    "subsystem": "archival_storage",
                })
                self._archive_degraded_latched = True

        # Alert if reader/writer both dead and no spares (latched)
        if (a.reader_health < 0.1 and a.reader_spares == 0
                and not getattr(self, "_reader_dead_latched", False)):
            events.append({
                "year": mission_year, "severity": "CRITICAL",
                "message": "Glass archive reader failing — no spares. Data readable but not updatable. "
                           "3D print replacement reader.",
                "subsystem": "archival_storage",
            })
            self._reader_dead_latched = True

        return events


# ════════════════════════════════════════════════════════════════
#  2. NANOBOT REPAIR SWARMS
# ════════════════════════════════════════════════════════════════

@dataclass
class NanobotSwarmState:
    """Self-replicating nanobot repair system.

    DNA-folding nanobots that:
    - Patrol ship surfaces and interior 24/7
    - Detect microfractures at molecular level
    - Carry self-healing compounds
    - Seal breaches autonomously
    - Self-replicate from raw materials

    NOT science fiction — DNA nanorobots that self-replicate
    have been demonstrated. (New Atlas, 2024)
    """
    # Swarm populations (billions of nanobots) — ESTIMATE design target;
    # 10 B hull-patrol bots covering 50,000 m² hull at 5 µm/bot = 200/m²
    # (Freitas & Merkle 2004 *Kinematic Self-Replicating Machines* Ch. 5
    # coverage density analysis).
    hull_patrol_swarm_billions: float = 10.0   # ESTIMATE — Freitas & Merkle 2004 Ch. 5
    interior_patrol_swarm_billions: float = 5.0   # ESTIMATE — proportional scaling
    repair_swarm_billions: float = 2.0            # ESTIMATE — repair sub-swarm fraction

    # Swarm health
    swarm_health: float = 1.0  # Overall effectiveness
    replication_rate: float = 1.0  # Self-replication capability

    # Materials consumed for replication (kg/year)
    raw_material_consumption_kg_year: float = 5.0
    sealant_reserves_kg: float = 500.0

    # Performance metrics
    microfractures_detected: int = 0
    microfractures_repaired: int = 0
    breaches_sealed: int = 0
    false_positives: int = 0

    # Power consumption
    power_consumption_kw: float = 10.0  # Entire swarm

    # Programming
    programming_version: int = 1
    programming_health: float = 1.0  # Instruction set integrity


class NanobotSwarmSimulator:
    """Simulates nanobot repair swarms.

    Nanobots solve the "inspection problem": you can't manually
    inspect every square meter of a generation ship. Nanobots do
    it continuously, at molecular resolution.

    Key advantage: self-replication means the swarm is self-sustaining.
    Key risk: programming corruption → rogue behavior (grey goo scenario).
    Mitigation: hardware kill switches, swarm population limits, isolated
    replication zones with AI oversight.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.state = NanobotSwarmState()

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # ── Hull patrol: detect microfractures ──
        patrol_coverage = min(1.0, s.hull_patrol_swarm_billions / 10.0) * s.swarm_health
        # At full coverage, detect ~100 microfractures/year
        detected = int(100 * patrol_coverage * (1 + self._rng.random() * 0.5))
        s.microfractures_detected += detected

        # ── Repair: seal microfractures ──
        repair_capacity = min(1.0, s.repair_swarm_billions / 2.0) * s.swarm_health
        repaired = int(detected * repair_capacity * 0.95)  # 95% repair rate
        s.microfractures_repaired += repaired

        if detected > repaired + 10:
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": f"Nanobot repair backlog: {detected - repaired} unrepaired microfractures",
                "subsystem": "nanobot_swarm",
            })

        # ── Self-replication to maintain population ──
        # Natural attrition: ~5% per year
        attrition = 0.05
        s.hull_patrol_swarm_billions *= (1 - attrition)
        s.interior_patrol_swarm_billions *= (1 - attrition)
        s.repair_swarm_billions *= (1 - attrition)

        # Self-replication (if materials available)
        if s.sealant_reserves_kg > 10 and s.replication_rate > 0.1:
            growth = attrition * s.replication_rate  # Replace losses
            s.hull_patrol_swarm_billions *= (1 + growth)
            s.interior_patrol_swarm_billions *= (1 + growth)
            s.repair_swarm_billions *= (1 + growth)
            s.sealant_reserves_kg -= s.raw_material_consumption_kg_year

        # Cap populations (safety limit against grey goo)
        s.hull_patrol_swarm_billions = min(20.0, s.hull_patrol_swarm_billions)
        s.interior_patrol_swarm_billions = min(10.0, s.interior_patrol_swarm_billions)
        s.repair_swarm_billions = min(5.0, s.repair_swarm_billions)

        # ── Programming degradation ──
        # Cosmic radiation can corrupt nanobot instructions
        s.programming_health = max(0.5, s.programming_health - 0.002)
        if s.programming_health < 0.7:
            # Need to re-flash from glass archive
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": f"Nanobot programming degraded: {s.programming_health:.0%}. "
                           "Re-flashing from silica glass archive.",
                "subsystem": "nanobot_swarm",
            })
            s.programming_health = 0.95  # Re-flash from glass archive

        # ── Swarm health ──
        s.swarm_health = min(
            s.hull_patrol_swarm_billions / 10.0,
            s.programming_health,
            1.0 if s.sealant_reserves_kg > 0 else 0.3,
        )

        return events


# ════════════════════════════════════════════════════════════════
#  3. SYNTHETIC TORPOR (Hibernation)
# ════════════════════════════════════════════════════════════════

@dataclass
class TorporState:
    """Synthetic torpor/hibernation system.

    Induces controlled hypothermia + hypoxia:
    - Body temp: 37°C → 15-20°C
    - Heart rate: 70 bpm → 5-10 bpm
    - Metabolism: reduced 90%
    - Radiation resistance: significantly increased
    - Muscle/bone: preserved (unlike normal bed rest)

    Reference: MDPI Life 11(1):54 (2021), ESA torpor strategy
    """
    torpor_pods: int = 8  # 2 per crew member (redundant)
    pod_health: list[float] = field(default_factory=lambda: [1.0] * 8)
    cooling_system_health: float = 1.0
    drug_delivery_health: float = 1.0

    # Torpor drug reserves (doses)
    torpor_induction_doses: int = 500
    revival_doses: int = 500

    # Crew torpor state
    crew_in_torpor: int = 0
    crew_awake: int = 4
    torpor_cycles_total: int = 0

    # Benefits during torpor
    food_reduction_factor: float = 0.1   # 90% less food needed
    water_reduction_factor: float = 0.15  # 85% less water
    o2_reduction_factor: float = 0.1     # 90% less O2
    radiation_protection_factor: float = 0.75  # 25% less radiation damage (Rithidech 2013, hypothermia radioprotection)

    # Rotation schedule
    rotation_months: int = 6  # 6 months torpor, 6 months awake


class TorporSimulator:
    """Simulates synthetic torpor for resource conservation and radiation protection.

    For a generation ship, torpor is a GAME CHANGER:
    - 90% food reduction when in torpor
    - 40% less radiation damage
    - Extends effective crew lifetime
    - Allows skeleton crew operations
    - Muscle/bone preserved (unlike zero-G atrophy)
    """

    def __init__(self, crew_size: int = 4, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._crew_size = crew_size
        self.state = TorporState(crew_awake=crew_size)

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # ── Rotation: half crew in torpor, half awake ──
        s.crew_in_torpor = self._crew_size // 2
        s.crew_awake = self._crew_size - s.crew_in_torpor
        s.torpor_cycles_total += s.crew_in_torpor * 2  # 2 rotations/year

        # ── Resource savings (per year) ──
        # Normal: 4 crew × 2 kg food/day × 365 = 2920 kg
        # With torpor: 2 awake × 2kg + 2 torpor × 0.2kg = 1606 kg (45% savings)
        awake_food = s.crew_awake * 2.0 * 365
        torpor_food = s.crew_in_torpor * 2.0 * 365 * s.food_reduction_factor
        total_food_needed = awake_food + torpor_food
        savings_pct = (1 - total_food_needed / (self._crew_size * 2.0 * 365)) * 100

        # ── Pod degradation ──
        for i in range(len(s.pod_health)):
            s.pod_health[i] = max(0, s.pod_health[i] - 0.01)

        s.cooling_system_health = max(0.3, s.cooling_system_health - 0.005)
        s.drug_delivery_health = max(0.3, s.drug_delivery_health - 0.003)

        # Drug consumption
        s.torpor_induction_doses -= s.crew_in_torpor * 2
        s.revival_doses -= s.crew_in_torpor * 2

        # ── Complications ──
        # 0.5% risk per torpor cycle of minor complication
        for _ in range(s.crew_in_torpor * 2):
            if self._rng.random() < 0.005:
                events.append({
                    "year": mission_year, "severity": "WARNING",
                    "message": "Minor torpor complication — crew member revival delayed. "
                               "Medical monitoring engaged.",
                    "subsystem": "torpor",
                })

        # Drug supply alert (latched)
        if s.torpor_induction_doses < 50 and not getattr(self, "_torpor_drug_latched", False):
            events.append({
                "year": mission_year, "severity": "CRITICAL",
                "message": f"Torpor drug supply low: {s.torpor_induction_doses} doses remaining. "
                           "Synthesize more from cell-free biomanufacturing.",
                "subsystem": "torpor",
            })
            self._torpor_drug_latched = True
        elif s.torpor_induction_doses >= 100:
            self._torpor_drug_latched = False

        return events

    def get_resource_savings(self) -> dict[str, float]:
        """Calculate resource savings from torpor rotation."""
        s = self.state
        normal_food = self._crew_size * 2.0 * 365
        torpor_food = (s.crew_awake * 2.0 + s.crew_in_torpor * 2.0 * s.food_reduction_factor) * 365
        normal_water = self._crew_size * 3.0 * 365
        torpor_water = (s.crew_awake * 3.0 + s.crew_in_torpor * 3.0 * s.water_reduction_factor) * 365

        # Guard against division by zero when crew_size is 0
        if self._crew_size == 0 or normal_food == 0:
            return {
                "food_savings_pct": 0.0,
                "water_savings_pct": 0.0,
                "radiation_reduction_pct": 0.0,
                "food_needed_kg_year": 0.0,
                "food_normal_kg_year": 0.0,
            }

        return {
            "food_savings_pct": (1 - torpor_food / normal_food) * 100,
            "water_savings_pct": (1 - torpor_water / normal_water) * 100,
            "radiation_reduction_pct": s.radiation_protection_factor * 100 * s.crew_in_torpor / self._crew_size,
            "food_needed_kg_year": torpor_food,
            "food_normal_kg_year": normal_food,
        }


# ════════════════════════════════════════════════════════════════
#  4. CELL-FREE BIOMANUFACTURING
# ════════════════════════════════════════════════════════════════

@dataclass
class BiomanufacturingState:
    """Cell-free biomanufacturing system.

    Uses PURE system (Protein synthesis Using Recombinant Elements):
    36 purified enzymes + ribosomes + energy source = protein from DNA.

    CRITICAL DEPENDENCY: The PURE system is "cell-free" for protein synthesis,
    but ribosomes themselves must be harvested from living E. coli cultures.
    Ribosomes are complex macromolecular machines (2.5 MDa, 3 rRNAs + 54 proteins)
    that cannot yet be synthesized in vitro. The ship MUST maintain E. coli
    bioreactors as a ribosome source.

    Can produce:
    - Food enzymes (for starch synthesizer)
    - Medical drugs (antibiotics, hormones, vaccines)
    - Torpor drugs (for hibernation system)
    - Industrial enzymes (for recycling, waste processing)
    - Nanobot programming molecules (DNA templates for nanobots)
    """
    pure_system_health: float = 1.0
    ribosome_stock: float = 1.0  # Ribosome availability (0-1)
    atp_generation_health: float = 1.0  # Energy supply for synthesis

    # E. coli bioreactor for ribosome production
    # Ribosomes cannot be synthesized cell-free — they require living cells
    ecoli_culture_health: float = 1.0  # E. coli bioreactor viability (0-1)
    ecoli_backup_frozen_stocks: int = 50  # Frozen glycerol stocks for recovery
    ribosome_production_rate: float = 1.0  # Fraction of nominal

    # Production capabilities
    can_produce_food_enzymes: bool = True
    can_produce_drugs: bool = True
    can_produce_industrial_enzymes: bool = True

    # Output (grams per day)
    protein_output_g_day: float = 100.0  # 100g/day at full capacity
    drug_output_g_day: float = 10.0

    # Self-replication
    # The PURE system can produce its OWN enzymes from DNA templates
    # → self-sustaining if DNA templates preserved (in glass archive)
    # BUT ribosomes must come from E. coli cultures
    self_replication_capability: float = 1.0


class BiomanufacturingSimulator:
    """Simulates cell-free biomanufacturing.

    The key insight: CFPS doesn't need living cells.
    No contamination risk from cell culture.
    DNA templates in silica glass → enzymes → proteins → everything.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.state = BiomanufacturingState()

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # Gradual degradation
        s.pure_system_health = max(0.3, s.pure_system_health - 0.005)
        s.atp_generation_health = max(0.3, s.atp_generation_health - 0.003)

        # ── E. coli bioreactor management (ribosome source) ──
        # E. coli cultures degrade from: contamination, phage attack, genetic drift
        s.ecoli_culture_health = max(0.0, s.ecoli_culture_health - 0.01)

        # Random contamination event (~3% per year)
        if self._rng.random() < 0.03:
            s.ecoli_culture_health *= 0.5
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": "E. coli bioreactor contamination — ribosome production halved. "
                           "Attempting recovery from frozen stocks.",
                "subsystem": "biomanufacturing",
            })

        # Recovery from frozen stocks if culture crashes
        if s.ecoli_culture_health < 0.2 and s.ecoli_backup_frozen_stocks > 0:
            s.ecoli_backup_frozen_stocks -= 1
            s.ecoli_culture_health = 0.85
            events.append({
                "year": mission_year, "severity": "NOMINAL",
                "message": f"E. coli culture restarted from frozen stock. "
                           f"{s.ecoli_backup_frozen_stocks} stocks remaining.",
                "subsystem": "biomanufacturing",
            })

        if s.ecoli_culture_health < 0.1 and s.ecoli_backup_frozen_stocks == 0:
            events.append({
                "year": mission_year, "severity": "EMERGENCY",
                "message": "E. coli cultures dead, no frozen stocks — "
                           "cannot produce ribosomes. PURE system will fail.",
                "subsystem": "biomanufacturing",
            })

        # Ribosome stock depends on E. coli culture health
        s.ribosome_production_rate = s.ecoli_culture_health
        ribosome_degradation = 0.008
        ribosome_supply = s.ribosome_production_rate * 0.012
        s.ribosome_stock = max(0.0, min(1.0,
            s.ribosome_stock - ribosome_degradation + ribosome_supply
        ))

        # Self-replication: PURE system produces its own replacement enzymes
        # (but NOT ribosomes — those come from E. coli)
        if s.self_replication_capability > 0.3:
            recovery = s.self_replication_capability * 0.01
            s.pure_system_health = min(1.0, s.pure_system_health + recovery)

        # Production capacity — now includes E. coli dependency
        capacity = (
            s.pure_system_health * s.ribosome_stock * s.atp_generation_health
        )
        s.protein_output_g_day = 100.0 * capacity
        s.drug_output_g_day = 10.0 * capacity

        # Self-replication degrades slowly (instruction copying errors)
        s.self_replication_capability = max(0, s.self_replication_capability - 0.002)

        # Can refresh from glass archive
        if s.self_replication_capability < 0.5 and mission_year % 50 == 0:
            s.self_replication_capability = 0.9
            events.append({
                "year": mission_year, "severity": "NOMINAL",
                "message": "Biomanufacturing DNA templates refreshed from silica glass archive.",
                "subsystem": "biomanufacturing",
            })

        if capacity < 0.3:
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": f"Biomanufacturing capacity at {capacity:.0%}. "
                           "Protein and drug production degraded.",
                "subsystem": "biomanufacturing",
            })

        return events


# ════════════════════════════════════════════════════════════════
#  5. INTEGRATED BREAKTHROUGH TECH ORCHESTRATOR
# ════════════════════════════════════════════════════════════════

class BreakthroughTechOrchestrator:
    """Runs all breakthrough technologies together, showing synergies.

    Synergy map:
      Glass Archive → stores DNA templates → Biomanufacturing produces enzymes
      Biomanufacturing → produces torpor drugs → Torpor saves resources
      Nanobots → repair hull → extend ship lifetime
      Nanobots program stored in → Glass Archive (re-flash when corrupted)
      Torpor → reduces food need → Starch Synthesizer can keep up
      All tech → maintained by → Manufacturing (3D printers)
    """

    def __init__(self, crew_size: int = 4, seed: int | None = None) -> None:
        self.archive = SilicaArchiveSimulator(seed=seed)
        self.nanobots = NanobotSwarmSimulator(seed=seed)
        self.torpor = TorporSimulator(crew_size=crew_size, seed=seed)
        self.biomanufacturing = BiomanufacturingSimulator(seed=seed)
        self._crew_size = crew_size

    def simulate_year(self, mission_year: float) -> dict[str, Any]:
        all_events: list[dict[str, Any]] = []

        all_events.extend(self.archive.simulate_year(mission_year))
        all_events.extend(self.nanobots.simulate_year(mission_year))
        all_events.extend(self.torpor.simulate_year(mission_year))
        all_events.extend(self.biomanufacturing.simulate_year(mission_year))

        # ── Synergies ──
        # Glass archive feeds biomanufacturing DNA templates
        if self.archive.archive.enzyme_dna_templates > 0.9:
            self.biomanufacturing.state.self_replication_capability = max(
                self.biomanufacturing.state.self_replication_capability, 0.5
            )

        # Biomanufacturing produces torpor drugs
        if self.biomanufacturing.state.drug_output_g_day > 5:
            self.torpor.state.torpor_induction_doses = max(
                self.torpor.state.torpor_induction_doses, 100
            )

        return {
            "year": mission_year,
            "events": all_events,
            "archive_intact": self.archive.archive.enzyme_dna_templates,
            "nanobot_health": self.nanobots.state.swarm_health,
            "torpor_savings": self.torpor.get_resource_savings(),
            "biomanufacturing_capacity": (
                self.biomanufacturing.state.pure_system_health *
                self.biomanufacturing.state.ribosome_stock
            ),
        }

    def run_centuries(self, years: int = 1000) -> list[dict[str, Any]]:
        results = []
        for y in range(1, years + 1):
            results.append(self.simulate_year(float(y)))
        return results

    def get_summary(self) -> dict[str, Any]:
        return {
            "archive": {
                "plates_intact": sum(1 for h in self.archive.archive.plate_health if h > 0.5),
                "dna_templates": f"{self.archive.archive.enzyme_dna_templates:.0%}",
                "reader_health": f"{self.archive.archive.reader_health:.0%}",
            },
            "nanobots": {
                "hull_swarm_billions": f"{self.nanobots.state.hull_patrol_swarm_billions:.1f}B",
                "fractures_repaired": self.nanobots.state.microfractures_repaired,
                "swarm_health": f"{self.nanobots.state.swarm_health:.0%}",
            },
            "torpor": self.torpor.get_resource_savings(),
            "biomanufacturing": {
                "capacity": f"{self.biomanufacturing.state.pure_system_health:.0%}",
                "protein_g_day": f"{self.biomanufacturing.state.protein_output_g_day:.0f}",
                "self_replication": f"{self.biomanufacturing.state.self_replication_capability:.0%}",
            },
        }
