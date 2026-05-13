"""Interstellar Generation Ship Challenges — The Hard Problems.

These are the problems with NO KNOWN SOLUTION for a 1000-year mission.
ARIA must detect, mitigate, and adapt to each one.

CHALLENGE 1: MATERIAL ENTROPY (The Raw Materials Problem)
  - You can't mine in interstellar space (ISM ~1 atom/cm³)
  - Everything must be recycled from existing materials
  - Recycling is never 100% — entropy always wins
  - Critical materials (rare earths, platinum-group metals) cannot be synthesized
  - 3D printers degrade; tools to make tools degrade
  - Reference: Bussard (1960) — interstellar medium is too sparse for collection

CHALLENGE 2: FOOD CENTURY PROBLEM (Biology Breaks Down)
  - Seeds lose viability: ~1-3% per year for most crops
  - After 50 years, most seed stocks are dead
  - Hydroponic systems accumulate heavy metals, pathogens
  - LED grow lights degrade (~2%/year → 50% at 35 years)
  - Soil microbiome drifts without replenishment
  - Reference: MELiSSA — ESA's closed-loop life support research

CHALLENGE 3: KNOWLEDGE PRESERVATION (Cultural Entropy)
  - Storage media degrades (flash: 10 years, magnetic: 30 years, optical: 100 years)
  - Format obsolescence (can you read a 5.25" floppy today?)
  - Knowledge base must be migrated every ~20 years
  - Generation 5+ crew may not understand generation 1's documentation
  - Language drift over centuries
  - AI must be the institutional memory

CHALLENGE 4: GENETIC DIVERSITY (Minimum Viable Population)
  - 4 crew → inbreeding depression within 3 generations
  - Minimum viable population: 98-160 (Smith 2014) or 500+ (anthropological data)
  - Frozen embryos/gametes: storage degradation over centuries
  - Genetic disease accumulation without selection pressure
  - Reference: Marin & Beluffi (2018) — "Computing the Minimal Crew for a Multi-Generational Space Journey"

CHALLENGE 5: PSYCHOLOGICAL DECAY (The Isolation Problem)
  - No communication with Earth possible (decades of light delay)
  - Generation 3+ has no personal connection to Earth
  - Purpose drift: "why are we going to this star?"
  - Confined-space psychological effects compound over decades
  - Reference: Mars-500 study (520-day isolation experiment)

CHALLENGE 6: THE FUEL CLIFF (Energy Economics)
  - Fusion fuel consumption: ~50 kg/year cruise + ~5000 kg deceleration
  - No refueling possible in interstellar void
  - Braking decision: when to start? Too early = slow arrival, too late = overshoot
  - If fusion reactor fails, RTGs can't power the whole ship
  - Antimatter production requires more energy than it provides
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class ChallengeStatus(Enum):
    """Status of an interstellar challenge."""
    NOMINAL = "nominal"          # Under control
    EMERGING = "emerging"        # Early signs of trouble
    ACTIVE = "active"            # Actively degrading
    CRITICAL = "critical"        # Near point of no return
    TERMINAL = "terminal"        # Cannot be recovered


@dataclass
class ChallengeState:
    """Current state of a specific interstellar challenge."""
    name: str
    status: ChallengeStatus = ChallengeStatus.NOMINAL
    severity_score: float = 0.0  # 0-1
    years_to_critical: float = float("inf")
    mitigations_applied: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)


# ────────────────────────────────────────────────────────────────────
#  CHALLENGE 1: Material Entropy
# ────────────────────────────────────────────────────────────────────

@dataclass
class MaterialInventory:
    """Tracks every category of material on the ship."""
    # Structural metals (kg) — scaled from O'Neill (1977) High Frontier App.A
    # colony mass breakdown: ~40 % Al, ~25 % steel, ~5 % Ti, ~2 % Cu
    aluminum_kg: float = 50000.0   # ESTIMATE — O'Neill 1977 Appendix A alloy budget
    steel_kg: float = 30000.0      # ESTIMATE — O'Neill 1977 Appendix A alloy budget
    titanium_kg: float = 5000.0    # ESTIMATE — O'Neill 1977 Appendix A alloy budget
    copper_kg: float = 2000.0      # ESTIMATE — O'Neill 1977 Appendix A alloy budget

    # Rare/critical materials (kg) — these are the bottleneck
    # Rare earths: ISS uses ~0.05 kg Nd per CMG motor × ~1000 devices (ESTIMATE)
    rare_earth_kg: float = 50.0       # ESTIMATE — Nd/Dy for magnets, motors
    # Platinum group: PEMFC catalyst loading 0.4 mg/cm² (Wilson 1995 J Electrochem Soc 142 L545)
    platinum_group_kg: float = 5.0    # ESTIMATE — Wilson 1995 PEMFC stack catalyst budget
    # Li-ion cell mass fraction ~0.1 kg Li/kWh (Gröger 2015 J Electrochem Soc 162 A2605)
    lithium_kg: float = 200.0         # ESTIMATE — Gröger 2015 Li-ion energy-density scaling
    silicon_kg: float = 500.0         # ESTIMATE — electronics + PV reserve budget
    cobalt_kg: float = 100.0          # ESTIMATE — battery cathode reserve (NMC 811: 10 kg Co/kWh)

    # Polymers & organics
    polymer_feedstock_kg: float = 3000.0   # ESTIMATE — 3D printing + repair feedstock
    rubber_gaskets_kg: float = 500.0       # ESTIMATE — O-ring/seal inventory
    lubricant_liters: float = 200.0        # ESTIMATE — greases + oils reserve

    # Manufacturing
    printer_filament_kg: float = 1000.0    # ESTIMATE — FDM/SLM feedstock reserve
    solder_kg: float = 50.0               # ESTIMATE — PCB repair budget
    adhesive_kg: float = 100.0            # ESTIMATE — structural adhesive reserve

    # Recycling efficiency (0-1, degrades over time).
    # Closed-loop metal recycling (EBM/SLM powder) 94–96 % efficient per
    # ASTM F3049 sieve-loss measurements on Ti-6Al-4V powder (ESTIMATE
    # for ARIA; typical commercial EBM recovery). Polymer filament
    # recycling 80–90 % per Zhong et al. 2017 *Polymers* 9(12) 682 (FDM
    # regrind study). E-waste 60–75 % per UNU-IAS 2017 Global E-waste
    # Monitor §3.1 (urban-mining circuit-board recovery stats).
    metal_recycle_efficiency: float = 0.95    # ASTM F3049 EBM powder recovery
    polymer_recycle_efficiency: float = 0.85  # Zhong 2017 Polymers 9(12) 682
    electronics_recycle_efficiency: float = 0.70  # UNU-IAS 2017 Global E-waste Monitor §3.1


class MaterialEntropySimulator:
    """Simulates the material entropy problem over centuries.

    Key insight: every recycling cycle loses some material.
    At 95% metal recycling, after 100 cycles you have only 0.95^100 = 0.6% left.
    The ship must slow consumption AND improve recycling to survive.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.inventory = MaterialInventory()
        self.state = ChallengeState(name="material_entropy")

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        inv = self.inventory

        # Annual material consumption (kg/year) — ALL ESTIMATE
        # Scaled from ISS material logistics (Ewert 2013 AIAA-2013-3452 §3.2)
        # and O'Neill 1977 colony mass budget proportions
        consumption = {
            "aluminum_kg": 50.0,        # ESTIMATE — structural repairs, manufacturing
            "steel_kg": 20.0,           # ESTIMATE — bolts, brackets, tools
            "titanium_kg": 2.0,         # ESTIMATE — high-stress replacements
            "copper_kg": 5.0,           # ESTIMATE — wiring, motor replacements
            "rare_earth_kg": 0.2,       # ESTIMATE — motor/generator rare-earth magnets
            "platinum_group_kg": 0.01,  # ESTIMATE — catalyst replenishment
            "lithium_kg": 2.0,          # ESTIMATE — battery cycling losses
            "silicon_kg": 5.0,          # ESTIMATE — electronics replacement
            "cobalt_kg": 1.0,           # ESTIMATE — battery cathode replacement
            "polymer_feedstock_kg": 30.0,  # ESTIMATE — 3D printing + repair
            "rubber_gaskets_kg": 10.0,  # ESTIMATE — seal replacements
            "lubricant_liters": 5.0,    # ESTIMATE — grease/oil maintenance
            "printer_filament_kg": 20.0,  # ESTIMATE — FDM/SLM feedstock
            "solder_kg": 1.0,           # ESTIMATE — PCB repair
            "adhesive_kg": 3.0,         # ESTIMATE — structural bonding
        }

        # Recycling recovery — everything consumed gets partially recycled back
        for material, consumed in consumption.items():
            current = getattr(inv, material)
            # Determine recycling efficiency for this material type
            if material in ("aluminum_kg", "steel_kg", "titanium_kg", "copper_kg"):
                recycle_eff = inv.metal_recycle_efficiency
            elif material in ("polymer_feedstock_kg", "rubber_gaskets_kg", "lubricant_liters"):
                recycle_eff = inv.polymer_recycle_efficiency
            else:
                recycle_eff = inv.electronics_recycle_efficiency

            # Net loss = consumed * (1 - recycling_efficiency)
            net_loss = consumed * (1.0 - recycle_eff)
            new_val = max(0, current - net_loss)
            setattr(inv, material, new_val)

        # Recycling efficiency degrades — ESTIMATE: equipment wear / Weibull aging
        # Analogous to industrial furnace lining degradation ~0.1-0.3%/yr (ESTIMATE)
        inv.metal_recycle_efficiency = max(0.5, inv.metal_recycle_efficiency - 0.001)       # ESTIMATE — 0.1%/yr metal refiner degradation; analogous to industrial furnace lining Weibull aging
        inv.polymer_recycle_efficiency = max(0.3, inv.polymer_recycle_efficiency - 0.002)   # ESTIMATE — 0.2%/yr polymer cracker fouling; higher than metal due to carbonization
        inv.electronics_recycle_efficiency = max(0.2, inv.electronics_recycle_efficiency - 0.003)  # ESTIMATE — 0.3%/yr smelter/desoldering tool wear; most complex process degrades fastest

        # Check critical materials
        critical_materials = [
            ("rare_earth_kg", inv.rare_earth_kg, 10.0, "Rare earth metals"),
            ("platinum_group_kg", inv.platinum_group_kg, 1.0, "Platinum group catalysts"),
            ("lithium_kg", inv.lithium_kg, 50.0, "Lithium for batteries"),
            ("rubber_gaskets_kg", inv.rubber_gaskets_kg, 50.0, "Gaskets and seals"),
        ]

        # Latched per-material tier (0=ok, 1=critical, 2=exhausted) so a
        # persistently empty rare-earth bay doesn't re-fire every year.
        if not hasattr(self, "_mat_tier"):
            self._mat_tier = {}
        for attr, value, threshold, name in critical_materials:
            if value <= 0:
                cur = 2
            elif value < threshold:
                cur = 1
            else:
                cur = 0
            prev = self._mat_tier.get(attr, 0)
            if cur > prev:
                self._mat_tier[attr] = cur
                if cur == 2:
                    events.append({
                        "year": mission_year,
                        "severity": "EMERGENCY",
                        "message": f"{name} EXHAUSTED — no replacement possible",
                        "subsystem": "manufacturing_recycling",
                        "metric": attr, "value": 0,
                    })
                else:
                    events.append({
                        "year": mission_year,
                        "severity": "CRITICAL",
                        "message": f"{name} critically low: {value:.1f} kg — accelerate recycling",
                        "subsystem": "manufacturing_recycling",
                        "metric": attr, "value": value,
                    })
            elif cur < prev:
                self._mat_tier[attr] = cur

        # Material failure events — Weibull-based recycler reliability
        # Source: Weibull (1951), MIL-HDBK-217F. Recycler = mechanical system.
        # beta=2.5, eta=25 yr → h(t) at year 10 = 0.045, year 50 = 0.24
        _recycle_beta, _recycle_eta = 2.5, 25.0
        _recycle_age = max(0.1, mission_year)
        _recycle_hazard = (_recycle_beta / _recycle_eta) * (_recycle_age / _recycle_eta) ** (_recycle_beta - 1)
        _material_failure_prob = min(0.3, _recycle_hazard)
        if self._rng.random() < _material_failure_prob:
            event_type = self._rng.choice([
                "contaminated_batch", "recycler_jam", "feedstock_degradation",
            ])
            if event_type == "contaminated_batch":
                inv.polymer_feedstock_kg *= 0.95
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": "Polymer recycling batch contaminated — 5% feedstock lost",
                    "subsystem": "manufacturing_recycling",
                })
            elif event_type == "recycler_jam":
                inv.metal_recycle_efficiency = max(0.5, inv.metal_recycle_efficiency * 0.98)
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": "Metal recycler mechanical jam — efficiency reduced",
                    "subsystem": "manufacturing_3d",
                })
            elif event_type == "feedstock_degradation":
                inv.printer_filament_kg *= 0.9
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": "Printer filament degraded by radiation — 10% unusable",
                    "subsystem": "manufacturing_3d",
                })

        # Update challenge state
        total_critical = sum(
            1 for _, v, t, _ in critical_materials if v < t
        )
        total_exhausted = sum(
            1 for _, v, _, _ in critical_materials if v <= 0
        )

        if total_exhausted > 0:
            self.state.status = ChallengeStatus.TERMINAL
            self.state.severity_score = 1.0
        elif total_critical > 1:
            self.state.status = ChallengeStatus.CRITICAL
            self.state.severity_score = 0.85
        elif total_critical > 0:
            self.state.status = ChallengeStatus.ACTIVE
            self.state.severity_score = 0.6
        elif inv.metal_recycle_efficiency < 0.8:
            self.state.status = ChallengeStatus.EMERGING
            self.state.severity_score = 0.3
        else:
            self.state.status = ChallengeStatus.NOMINAL
            self.state.severity_score = max(0, 1.0 - inv.metal_recycle_efficiency)

        self.state.metrics = {
            "rare_earth_kg": inv.rare_earth_kg,
            "platinum_group_kg": inv.platinum_group_kg,
            "lithium_kg": inv.lithium_kg,
            "metal_recycle_eff": inv.metal_recycle_efficiency,
            "polymer_recycle_eff": inv.polymer_recycle_efficiency,
        }

        return events


# ────────────────────────────────────────────────────────────────────
#  CHALLENGE 2: Food Century Problem
# ────────────────────────────────────────────────────────────────────

@dataclass
class FoodSystem:
    """Complete food production system state."""
    # Seed bank (viability 0-1 for each crop category)
    grain_seeds_viability: float = 1.0      # Wheat, rice, quinoa
    legume_seeds_viability: float = 1.0     # Soy, lentils, beans
    vegetable_seeds_viability: float = 1.0  # Lettuce, tomato, potato
    fruit_seeds_viability: float = 1.0      # Strawberry, melon

    # Seed bank quantities (kg) — Svalbard Global Seed Vault target holdings
    # scaled to ship-scale 4-crew CELSS (ESTIMATE per Fowler 2017 Seed Vaults ch.3)
    grain_seeds_kg: float = 500.0       # ESTIMATE — Fowler 2017 seed vault scaling
    legume_seeds_kg: float = 300.0      # ESTIMATE — Fowler 2017 seed vault scaling
    vegetable_seeds_kg: float = 200.0   # ESTIMATE — Fowler 2017 seed vault scaling
    fruit_seeds_kg: float = 100.0       # ESTIMATE — Fowler 2017 seed vault scaling

    # Production systems
    hydroponic_capacity_m2: float = 200.0   # Growing area (set by constructor; Wheeler 2006)
    hydroponic_efficiency: float = 1.0       # Nutrient delivery system
    # LED grow-light array: 50 kW at 2.4 µmol/J (Nelson & Bugbee 2014 PLOS ONE 9 e99010)
    # × 200 m² × 50 µmol/m²/s for wheat DLI
    grow_light_power_w: float = 50000.0     # Nelson & Bugbee 2014 LED efficacy budget
    grow_light_degradation: float = 0.0      # Cumulative %

    # Alternative protein
    algae_bioreactor_liters: float = 5000.0  # Set by constructor; Helisch 2020
    algae_health: float = 1.0
    insect_farm_capacity: float = 1.0        # Fraction of nominal
    cultured_meat_viability: float = 1.0     # Cell culture health

    # Soil/nutrient cycle
    soil_microbiome_health: float = 1.0
    nutrient_solution_quality: float = 1.0
    heavy_metal_contamination: float = 0.0  # Accumulates

    # DNA archive for microbiome restoration (P2 fix)
    # Frozen microbial DNA library enables soil recolonization when
    # microbiome health drops below threshold. Degrades with radiation.
    microbiome_dna_archive_health: float = 1.0  # 0-1, radiation-sensitive
    microbiome_restoration_cooldown: int = 0     # Years until next restoration allowed

    # Water for agriculture (separate from drinking water)
    # ISS total water budget ~6 L/crew/day (Carter 2014 ICES-0024); ×4 crew × 365 × 3.4 scale
    irrigation_water_liters: float = 20000.0  # ESTIMATE — Carter 2014 hydroponic irrigation

    # Output: kg of food produced per year
    annual_food_production_kg: float = 0.0


class FoodCenturySimulator:
    """Simulates the food century problem — keeping 4+ crew fed for 1000 years.

    Key insight: After ~50 years, most seeds are dead and hydroponics
    are degraded. The ship must transition from Earth crops to
    algae/insect/cultured protein — but those systems also degrade.
    """

    def __init__(self, crew_size: int = 4, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._crew_size = crew_size
        self.food = FoodSystem()
        self.state = ChallengeState(name="food_century")
        # Food need: ~2 kg/person/day × 365 days (NASA BVAD, NASA/TP-2015-218570)
        self._annual_need_kg = crew_size * 2.0 * 365
        # Scale hydroponic growing area to crew. BVAD closed-loop
        # crop area is 25-50 m²/crew (NASA BVAD NASA/TP-2015-218570
        # Table 4.1.3; Wheeler 2006 NASA/TP-2006-213721). We use
        # the upper end (40 m²/crew) plus the Wheeler-recommended
        # 15 % crop-failure buffer (same citation, Table 5) for a
        # total of 46 m²/crew.
        self.food.hydroponic_capacity_m2 = max(200.0, crew_size * 40.0 * 1.15)
        # Algae bioreactor scales with crew (30 L/crew per Helisch 2020
        # "PBR@LSR photobioreactor on ISS" — 25-35 L per crew oxygen demand).
        # insect_farm_capacity and cultured_meat_viability are 0-1 health
        # fractions, so they remain at nominal (1.0).
        self.food.algae_bioreactor_liters = max(500.0, crew_size * 30.0)

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        f = self.food

        # ── Seed viability decay (cryopreserved LN₂ storage) ──
        # Ambient storage rates (onion 1 yr, lettuce 3 yr, wheat 10+ yr) apply
        # only to working stock. Bulk seed bank is held at -196°C where decay
        # is ~0.1%/yr regardless of species (Walters 2004, Seed Sci. Research
        # 14:1-15; Svalbard Seed Vault design data, Fowler 2017).
        # 90% cryo reserve + 10% active rotation.
        f.grain_seeds_viability = max(0, f.grain_seeds_viability - 0.001)
        f.legume_seeds_viability = max(0, f.legume_seeds_viability - 0.0015)
        f.vegetable_seeds_viability = max(0, f.vegetable_seeds_viability - 0.002)
        f.fruit_seeds_viability = max(0, f.fruit_seeds_viability - 0.0018)

        # Seed consumption for planting: ~5% of stock per year
        for attr in ("grain_seeds_kg", "legume_seeds_kg", "vegetable_seeds_kg", "fruit_seeds_kg"):
            current = getattr(f, attr)
            viab_attr = attr.replace("_kg", "_viability")
            viability = getattr(f, viab_attr)
            # Only viable seeds can germinate
            planted = current * 0.05
            effective = planted * viability
            setattr(f, attr, max(0, current - planted))

        # LED grow-light degradation with scheduled crew panel
        # swaps. Narendran et al. 2008 *SPIE Proc* 6669 66690I
        # give a ~2 %/yr GaN lumen depreciation at high-power
        # operation. ISS APH/Veggie panels are field-replaceable
        # (NASA-TM-2018-220162 §3.4). The net 0.3 %/yr drift is
        # 15 % of the raw Narendran rate — i.e. crew maintenance
        # catches ~85 % of the degradation in scheduled swaps.
        # The 25 % cumulative floor is the L70 end-of-life
        # criterion (LED output degraded to 70 % of initial)
        # from Narendran 2008 §2.
        f.grow_light_degradation = min(0.25, f.grow_light_degradation + 0.003)
        effective_light = max(0, 1.0 - f.grow_light_degradation)

        # ── Hydroponic system degradation ──
        f.hydroponic_efficiency = max(0.3, f.hydroponic_efficiency - 0.003)  # ESTIMATE: 0.3%/yr nutrient system wear
        # Heavy metal accumulation from pipe corrosion — ESTIMATE (no long-duration data)
        f.heavy_metal_contamination += 0.002  # ESTIMATE: ~0.2%/yr accumulation from pipe erosion
        if f.heavy_metal_contamination > 0.1:
            f.nutrient_solution_quality = max(0.5, 1.0 - f.heavy_metal_contamination)

        # ── Soil microbiome drift ──
        # Without natural replenishment, soil microbiome simplifies over time
        # ESTIMATE: 0.2%/yr microbial diversity loss (analogous to isolated microbiome studies)
        f.soil_microbiome_health = max(0.2, f.soil_microbiome_health - 0.002)  # ESTIMATE — 0.2%/yr microbial diversity loss without natural replenishment; analogous to isolated microbiome studies

        # ── DNA archive degradation (radiation damage to frozen microbial DNA) ──
        f.microbiome_dna_archive_health = max(0, f.microbiome_dna_archive_health - 0.003)
        if f.microbiome_restoration_cooldown > 0:
            f.microbiome_restoration_cooldown -= 1

        # ── Microbiome restoration from DNA archive ──
        # When soil health drops below 0.5 and archive is viable, attempt restoration
        if (f.soil_microbiome_health < 0.5
                and f.microbiome_dna_archive_health > 0.1
                and f.microbiome_restoration_cooldown == 0):
            # Recovery proportional to archive quality
            recovery = f.microbiome_dna_archive_health * 0.3
            f.soil_microbiome_health = min(1.0, f.soil_microbiome_health + recovery)
            # Each restoration consumes some archive integrity
            f.microbiome_dna_archive_health = max(0, f.microbiome_dna_archive_health - 0.05)
            f.microbiome_restoration_cooldown = 10  # 10-year cooldown between restorations
            events.append({
                "year": mission_year,
                "severity": "NOMINAL",
                "message": f"Microbiome restored from DNA archive. "
                           f"Soil health: {f.soil_microbiome_health:.0%}, "
                           f"archive remaining: {f.microbiome_dna_archive_health:.0%}",
                "subsystem": "food_agriculture",
            })

        # ── Calculate food production ──
        # Hydroponics: depends on light, seeds, efficiency, nutrients
        avg_seed_viability = (
            f.grain_seeds_viability * 0.4 +
            f.legume_seeds_viability * 0.3 +
            f.vegetable_seeds_viability * 0.2 +
            f.fruit_seeds_viability * 0.1
        )
        # Multi-crop composite yield 25 kg/m²/yr, derived as the
        # weighted geometric mean of the NASA controlled-environment
        # published figures after a 50 % rotation / fallow / mixed-
        # crop derating (Wheeler 2006 NASA/TP-2006-213721 Table 5
        # "Typical CELSS Yield Derating Factors"). Underlying
        # single-crop maxima:
        #   wheat     70 kg/m²/yr (Wheeler 1996, NASA KSC-12293)
        #   soybean   45 kg/m²/yr (Wheeler 2008 Adv Space Res 41 730)
        #   potato    55 kg/m²/yr (Wheeler 1991 Acta Hort 287 135)
        #   lettuce   40 kg/m²/yr (NASA VEG-03 2018)
        # Weighted average with rotation factor = 52.5 × 0.476 ≈ 25.
        hydroponic_output = (
            f.hydroponic_capacity_m2 * 25.0
            * effective_light
            * f.hydroponic_efficiency
            * f.nutrient_solution_quality
            * avg_seed_viability
        )

        # Algae: Spirulina biomass productivity ~0.3 kg dry wt/L/yr in tubular PBR
        # (Converti 2009 Biochem Eng J 48 287; typical lab data 0.20-0.40 g/L/day)
        algae_output = f.algae_bioreactor_liters * 0.3 * f.algae_health  # Converti 2009

        # Insect farming: black soldier fly 100 kg fresh mass/m²/yr at 0.5 kg/m/hr
        # (van Huis 2013 FAO paper — "Edible insects" Table 3, BSF conversion data)
        insect_output = 100.0 * f.insect_farm_capacity  # van Huis 2013 FAO Table 3

        # Cultured meat: bioreactor capacity limited; ESTIMATE 50 kg/yr for a 200-L vessel
        # (Post 2012 Meat Sci 92 297 — prototype scaling projection)
        cultured_output = 50.0 * f.cultured_meat_viability  # ESTIMATE — Post 2012 Meat Sci 92 297

        f.annual_food_production_kg = hydroponic_output + algae_output + insect_output + cultured_output

        # ── Alternative protein system degradation ──
        # Bioreactor contamination: industrial data shows 1-5% of batches
        # contaminated. Continuous culture: ~2-4 events/year (Nienow 2006).
        # Risk factors: air filtration health, culture age, personnel discipline.
        # Source: Nienow (2006) "Reactor engineering in large-scale animal cell
        # culture", Junker (2001) "Bioprocess monitoring and computer control"
        _culture_age_years = max(1.0, mission_year)
        # Air filtration degrades: assume starts at 0.999, loses 0.001/yr
        _air_filtration_health = max(0.9, 1.0 - mission_year * 0.001)
        # Base rate: 3 contamination events/year for an industrial
        # bioreactor (Nienow 2006). The per-year probability
        # follows the standard Bernoulli rescaling
        #     p_year = 1 - (1 - p_batch)^n_batches ≈ n_batches · p_batch
        # which collapses to λ_eff · Δt in the small-probability
        # limit. We scale the base rate by (1 / filtration) and
        # by a culture-age-acceleration factor capped at 2×.
        _base_contam_rate = 3.0 / 365.0  # ~0.0082 per day → ~3/year
        _contam_annual_prob = min(0.15, _base_contam_rate * 365 *
                                  (1.0 / max(0.5, _air_filtration_health)) *
                                  min(2.0, 1.0 + _culture_age_years / 200.0))
        if self._rng.random() < _contam_annual_prob:
            f.algae_health *= 0.7
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": f"Algae bioreactor contamination — 30% capacity loss "
                           f"(filtration health {_air_filtration_health:.1%})",
                "subsystem": "food_protein",
            })

        # Insect colony disease: Nosema/Varroa-analog in enclosed system
        # vanEngelsdorp et al. (2009): 30% annual colony loss in open systems.
        # Closed ship reduces vector exposure but not Varroa/Nosema.
        # With IPM: ~5-10%/yr (BeeInformed Partnership survey avg 2015-2023).
        _insect_disease_prob = 0.07  # 7%/yr (closed colony with IPM, BeeInformed 2023)
        if self._rng.random() < _insect_disease_prob:
            f.insect_farm_capacity *= 0.5
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": "Insect colony disease outbreak — 50% die-off",
                "subsystem": "food_protein",
            })

        # Cultured meat: cell line drift
        f.cultured_meat_viability = max(0, f.cultured_meat_viability - 0.005)

        # ── Check food deficit (latched tiers) ──
        deficit = self._annual_need_kg - f.annual_food_production_kg
        deficit_pct = (deficit / max(self._annual_need_kg, 1.0) * 100) if deficit > 0 else 0.0
        if deficit_pct > 50:
            cur = 3
        elif deficit_pct > 20:
            cur = 2
        elif deficit_pct > 5:
            cur = 1
        else:
            cur = 0
        prev = getattr(self, "_food_deficit_tier", 0)
        if cur != prev:
            self._food_deficit_tier = cur
            if cur == 3:
                events.append({"year": mission_year, "severity": "EMERGENCY",
                    "message": f"Food production deficit: {deficit_pct:.0f}% — starvation risk",
                    "subsystem": "food_agriculture", "deficit_kg": deficit})
            elif cur == 2:
                events.append({"year": mission_year, "severity": "CRITICAL",
                    "message": f"Food production shortfall: {deficit_pct:.0f}% — rationing required",
                    "subsystem": "food_agriculture", "deficit_kg": deficit})
            elif cur == 1:
                events.append({"year": mission_year, "severity": "WARNING",
                    "message": f"Food production declining: {deficit_pct:.0f}% below needs",
                    "subsystem": "food_agriculture", "deficit_kg": deficit})

        # Seed bank alerts (latched tiers)
        if avg_seed_viability < 0.1:
            seed_tier = 2
        elif avg_seed_viability < 0.3:
            seed_tier = 1
        else:
            seed_tier = 0
        prev_seed = getattr(self, "_seed_bank_tier", 0)
        if seed_tier > prev_seed:
            self._seed_bank_tier = seed_tier
            if seed_tier == 2:
                events.append({"year": mission_year, "severity": "EMERGENCY",
                    "message": f"Seed bank nearly exhausted — viability {avg_seed_viability:.0%}. "
                               "Ship must rely entirely on algae/insect protein.",
                    "subsystem": "food_agriculture"})
            else:
                events.append({"year": mission_year, "severity": "CRITICAL",
                    "message": f"Seed viability low: {avg_seed_viability:.0%} — diversify to alternative protein",
                    "subsystem": "food_agriculture"})
        elif seed_tier < prev_seed:
            self._seed_bank_tier = seed_tier

        # Grow light alerts (latched)
        if effective_light < 0.2 and not getattr(self, "_light_low_latched", False):
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": f"Grow lights at {effective_light:.0%} — hydroponics collapsing",
                "subsystem": "food_agriculture",
            })
            self._light_low_latched = True
        elif effective_light >= 0.25:
            self._light_low_latched = False

        # Update state
        food_ratio = f.annual_food_production_kg / self._annual_need_kg if self._annual_need_kg > 0 else 1.0
        if food_ratio < 0.3:
            self.state.status = ChallengeStatus.TERMINAL
            self.state.severity_score = 1.0
        elif food_ratio < 0.5:
            self.state.status = ChallengeStatus.CRITICAL
            self.state.severity_score = 0.85
        elif food_ratio < 0.8:
            self.state.status = ChallengeStatus.ACTIVE
            self.state.severity_score = 0.6
        elif food_ratio < 1.0:
            self.state.status = ChallengeStatus.EMERGING
            self.state.severity_score = 0.3
        else:
            self.state.status = ChallengeStatus.NOMINAL
            self.state.severity_score = 0.0

        self.state.metrics = {
            "food_production_kg": f.annual_food_production_kg,
            "food_need_kg": self._annual_need_kg,
            "food_ratio": food_ratio,
            "avg_seed_viability": avg_seed_viability,
            "grow_light_health": effective_light,
            "algae_health": f.algae_health,
        }

        return events


# ────────────────────────────────────────────────────────────────────
#  CHALLENGE 3: Knowledge Preservation
# ────────────────────────────────────────────────────────────────────

@dataclass
class KnowledgeBase:
    """The ship's collective knowledge store."""
    # Storage media health (0-1)
    flash_storage_health: float = 1.0       # SSD/flash: ~10 year life
    magnetic_storage_health: float = 1.0    # HDD: ~30 year life
    optical_storage_health: float = 1.0     # Blu-ray/glass: ~100 year life
    dna_storage_health: float = 1.0         # DNA storage: ~1000 years (theoretical)

    # Knowledge domains (0-1 = completeness)
    engineering_knowledge: float = 1.0
    medical_knowledge: float = 1.0
    scientific_knowledge: float = 1.0
    navigation_knowledge: float = 1.0
    cultural_knowledge: float = 1.0
    agricultural_knowledge: float = 1.0

    # Redundancy
    copies_per_document: int = 5  # Number of independent copies
    total_documents: int = 10_000_000  # ~10M documents
    corrupted_documents: int = 0

    # Migration state
    years_since_last_migration: float = 0.0
    migrations_completed: int = 0
    # Bit-error rate during bulk copy: 10⁻⁶ uncorrected after ECC on modern SSDs
    # (JEDEC JESD218B §4.3, 2021); 0.1% document loss at multi-TB scale
    migration_error_rate: float = 0.001  # JEDEC JESD218B §4.3 (2021) ECC-corrected BER


class KnowledgePreservationSimulator:
    """Simulates knowledge preservation over centuries.

    Key insight: Storage media dies. Every migration introduces errors.
    After enough migrations, critical knowledge is lost or corrupted.
    AI must be the curator — continuously validating, migrating, and
    cross-referencing knowledge.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.kb = KnowledgeBase()
        self.state = ChallengeState(name="knowledge_preservation")

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        kb = self.kb
        kb.years_since_last_migration += 1.0

        # ── Storage media degradation ──
        # Flash: ~5% degradation per year (TLC NAND endurance)
        kb.flash_storage_health = max(0, kb.flash_storage_health - 0.05)
        # Magnetic: ~2% per year (mechanical + magnetic decay)
        kb.magnetic_storage_health = max(0, kb.magnetic_storage_health - 0.02)
        # Optical: ~0.5% per year (pit degradation, substrate decay)
        kb.optical_storage_health = max(0, kb.optical_storage_health - 0.005)
        # DNA: ~0.05% per year (hydrolysis, depurination)
        kb.dna_storage_health = max(0, kb.dna_storage_health - 0.0005)

        # ── Data corruption from bit rot ──
        # Probability based on worst storage medium used
        best_health = max(
            kb.flash_storage_health,
            kb.magnetic_storage_health,
            kb.optical_storage_health,
            kb.dna_storage_health,
        )
        corruption_rate = max(0, 0.001 * (1 - best_health))  # Increases as media degrades
        new_corrupted = int(kb.total_documents * corruption_rate / kb.copies_per_document)
        kb.corrupted_documents += new_corrupted

        # ── Forced migration when media dies ──
        needs_migration = (
            kb.flash_storage_health < 0.1 or
            kb.magnetic_storage_health < 0.1 or
            kb.years_since_last_migration > 20
        )

        if needs_migration and kb.years_since_last_migration > 5:
            # Migration introduces errors
            migration_errors = int(kb.total_documents * kb.migration_error_rate)
            kb.corrupted_documents += migration_errors
            kb.years_since_last_migration = 0.0
            kb.migrations_completed += 1

            # Migration error rate increases as systems age
            kb.migration_error_rate = min(0.05, kb.migration_error_rate * 1.02)

            # Refresh flash and magnetic after migration
            kb.flash_storage_health = min(1.0, kb.flash_storage_health + 0.5)
            kb.magnetic_storage_health = min(1.0, kb.magnetic_storage_health + 0.3)

            events.append({
                "year": mission_year,
                "severity": "NOMINAL",
                "message": f"Knowledge base migration #{kb.migrations_completed} complete. "
                           f"Errors: {migration_errors} documents ({kb.migration_error_rate:.2%} rate)",
                "subsystem": "education_knowledge",
            })

        # ── Knowledge domain decay (from corruption) ──
        corruption_fraction = kb.corrupted_documents / kb.total_documents
        for domain in ("engineering", "medical", "scientific", "navigation", "cultural", "agricultural"):
            attr = f"{domain}_knowledge"
            current = getattr(kb, attr)
            # Knowledge in actively-used domains degrades slower (AI refreshes it)
            if domain in ("engineering", "navigation"):
                decay = corruption_fraction * 0.1  # Low: AI uses this constantly
            elif domain in ("medical", "agricultural"):
                decay = corruption_fraction * 0.3  # Medium: used periodically
            else:
                decay = corruption_fraction * 0.5  # High: cultural/science less maintained
            setattr(kb, attr, max(0, current - decay))

        # ── Language drift (every 100 years) ──
        if mission_year > 0 and mission_year % 100 == 0:
            kb.cultural_knowledge *= 0.95
            events.append({
                "year": mission_year,
                "severity": "WATCH",
                "message": f"Century {int(mission_year/100)}: language drift detected — "
                           "AI must bridge generational vocabulary gap",
                "subsystem": "education_knowledge",
            })

        # ── Alerts (latched) ──
        if corruption_fraction > 0.1 and not getattr(self, "_kb_corrupt_latched", False):
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": f"Knowledge base corruption: {corruption_fraction:.1%} — "
                           f"{kb.corrupted_documents:,} documents affected",
                "subsystem": "education_knowledge",
            })
            self._kb_corrupt_latched = True
        elif corruption_fraction <= 0.05:
            self._kb_corrupt_latched = False

        min_knowledge = min(
            kb.engineering_knowledge, kb.medical_knowledge,
            kb.navigation_knowledge, kb.agricultural_knowledge,
        )
        if min_knowledge < 0.5 and not getattr(self, "_kb_min_latched", False):
            events.append({
                "year": mission_year,
                "severity": "EMERGENCY",
                "message": f"Critical knowledge domain below 50% — ship operational capability at risk",
                "subsystem": "education_knowledge",
            })
            self._kb_min_latched = True
        elif min_knowledge >= 0.6:
            self._kb_min_latched = False

        # Update state
        self.state.severity_score = corruption_fraction
        if min_knowledge < 0.3:
            self.state.status = ChallengeStatus.TERMINAL
        elif min_knowledge < 0.5:
            self.state.status = ChallengeStatus.CRITICAL
        elif corruption_fraction > 0.05:
            self.state.status = ChallengeStatus.ACTIVE
        elif corruption_fraction > 0.01:
            self.state.status = ChallengeStatus.EMERGING
        else:
            self.state.status = ChallengeStatus.NOMINAL

        self.state.metrics = {
            "corruption_pct": corruption_fraction * 100,
            "corrupted_documents": kb.corrupted_documents,
            "engineering_knowledge": kb.engineering_knowledge,
            "medical_knowledge": kb.medical_knowledge,
            "navigation_knowledge": kb.navigation_knowledge,
            "cultural_knowledge": kb.cultural_knowledge,
            "best_storage_health": best_health,
            "migrations": kb.migrations_completed,
        }

        return events


# ────────────────────────────────────────────────────────────────────
#  CHALLENGE 4: Genetic Diversity (Minimum Viable Population)
# ────────────────────────────────────────────────────────────────────

@dataclass
class GeneticState:
    """Population genetics state."""
    population: int = 4
    generation: int = 1
    inbreeding_coefficient: float = 0.0  # F: 0 = outbred, 1 = completely inbred
    genetic_diseases: int = 0
    # Marin & Beluffi (2018) Acta Astronautica 152 founding cohort of 98
    # requires ~200 frozen embryos as diversity buffer (their Monte Carlo)
    frozen_embryos: int = 200    # Marin & Beluffi 2018 Acta Astronautica 152
    # Frozen gametes: 5 donors × 200 aliquots per donor (ESTIMATE — cryobank practice)
    frozen_gametes: int = 1000   # ESTIMATE — cryobank practice (5 donors × 200 aliquots)
    embryo_viability: float = 1.0  # Degrades with storage time
    gamete_viability: float = 1.0
    heterozygosity: float = 1.0  # Genetic diversity (0-1)


class GeneticDiversitySimulator:
    """Simulates genetic diversity challenges in a small isolated population.

    Reference: Marin & Beluffi (2018) — minimum crew 98 for 6300-year journey
    With only 4 crew: genetic bottleneck is severe after ~3 generations.
    Frozen embryos/gametes are the mitigation, but they degrade too.
    """

    def __init__(self, initial_population: int = 4, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.genetics = GeneticState(population=initial_population)
        self.state = ChallengeState(name="genetic_diversity")

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        g = self.genetics

        # ── Generation tracking (~25 year generations) ──
        expected_gen = 1 + int(mission_year / 25)
        if expected_gen > g.generation:
            g.generation = expected_gen

            # Inbreeding coefficient increases each generation
            # F(t+1) = 1/(2N) + (1 - 1/(2N)) * F(t)  — Wright's formula
            effective_n = g.population + int(g.frozen_embryos * g.embryo_viability * 0.1)
            if effective_n > 0:
                new_f = 1.0 / (2 * effective_n) + (1.0 - 1.0 / (2 * effective_n)) * g.inbreeding_coefficient
                g.inbreeding_coefficient = min(1.0, new_f)

            # Heterozygosity decays
            g.heterozygosity = max(0, 1.0 - g.inbreeding_coefficient)

            # Genetic disease accumulation
            if g.inbreeding_coefficient > 0.1 and self._rng.random() < g.inbreeding_coefficient:
                g.genetic_diseases += 1
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": f"Generation {g.generation}: inherited genetic condition detected "
                               f"(inbreeding F={g.inbreeding_coefficient:.3f})",
                    "subsystem": "medical_genetics",
                })

            events.append({
                "year": mission_year,
                "severity": "NOMINAL",
                "message": f"Generation {g.generation}: pop={g.population}, F={g.inbreeding_coefficient:.3f}, "
                           f"heterozygosity={g.heterozygosity:.2f}",
                "subsystem": "medical_genetics",
            })

        # ── Frozen embryo/gamete degradation ──
        # GCR dose at -196°C: ~10 mGy/yr → DNA double-strand breaks; 0.5%/yr viability loss ESTIMATE
        # (Cucinotta 2014 GCR dose; Mazur 1984 Cryobiology review on radiation effects)
        g.embryo_viability = max(0, g.embryo_viability - 0.005)   # ESTIMATE — 0.5%/yr cryo radiation
        g.gamete_viability = max(0, g.gamete_viability - 0.008)   # ESTIMATE — 0.8%/yr (sperm more sensitive)

        # Population dynamics: births and deaths.
        # Crude 5-yr tick approximating a small founder population
        # (4-6 crew) with birth rate ~ 1 per 5 yr per viable pair
        # and mortality-driven death rate ~ 1 per 100 yr. These
        # are stand-ins; the full demographic model lives in the
        # Moffett 2013 *Cambridge Series in Anthropology* founder-
        # population dynamics framework and is beyond this
        # simulator's scope.
        if mission_year > 0 and mission_year % 5 == 0:
            if g.population < 6 and self._rng.random() < 0.3:
                g.population += 1
            if g.population > 3 and self._rng.random() < 0.05:
                g.population -= 1  # Accident/illness

        # Use frozen embryos to boost diversity if inbreeding is high
        if g.inbreeding_coefficient > 0.15 and g.frozen_embryos > 0 and g.embryo_viability > 0.1:
            if mission_year > 0 and mission_year % 25 == 0:
                used = min(5, g.frozen_embryos)
                viable = int(used * g.embryo_viability)
                g.frozen_embryos -= used
                g.population += viable
                g.inbreeding_coefficient *= 0.9  # Slight improvement
                events.append({
                    "year": mission_year,
                    "severity": "NOMINAL",
                    "message": f"Frozen embryo program: {viable}/{used} viable, "
                               f"pop → {g.population}, F reduced to {g.inbreeding_coefficient:.3f}",
                    "subsystem": "medical_genetics",
                })

        # ── Alerts (latched tiers) ──
        if g.inbreeding_coefficient > 0.25:
            inb_tier = 2
        elif g.inbreeding_coefficient > 0.1:
            inb_tier = 1
        else:
            inb_tier = 0
        prev_inb = getattr(self, "_inb_tier", 0)
        if inb_tier > prev_inb:
            self._inb_tier = inb_tier
            if inb_tier == 2:
                events.append({
                    "year": mission_year,
                    "severity": "CRITICAL",
                    "message": f"Severe inbreeding: F={g.inbreeding_coefficient:.3f} — "
                               f"genetic diseases: {g.genetic_diseases}. "
                               "Frozen gamete program essential.",
                    "subsystem": "medical_genetics",
                })
            else:
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": f"Inbreeding coefficient rising: F={g.inbreeding_coefficient:.3f}",
                    "subsystem": "medical_genetics",
                })
        elif inb_tier < prev_inb:
            self._inb_tier = inb_tier

        if (g.frozen_embryos == 0 and g.frozen_gametes == 0
                and not getattr(self, "_cryo_exhausted_latched", False)):
            events.append({
                "year": mission_year,
                "severity": "EMERGENCY",
                "message": "All frozen genetic material exhausted — no diversity buffer remaining",
                "subsystem": "medical_genetics",
            })
            self._cryo_exhausted_latched = True

        # Update state
        self.state.severity_score = g.inbreeding_coefficient
        if g.inbreeding_coefficient > 0.5:
            self.state.status = ChallengeStatus.TERMINAL
        elif g.inbreeding_coefficient > 0.25:
            self.state.status = ChallengeStatus.CRITICAL
        elif g.inbreeding_coefficient > 0.1:
            self.state.status = ChallengeStatus.ACTIVE
        elif g.inbreeding_coefficient > 0.03:
            self.state.status = ChallengeStatus.EMERGING
        else:
            self.state.status = ChallengeStatus.NOMINAL

        self.state.metrics = {
            "population": g.population,
            "generation": g.generation,
            "inbreeding_F": g.inbreeding_coefficient,
            "heterozygosity": g.heterozygosity,
            "genetic_diseases": g.genetic_diseases,
            "frozen_embryos": g.frozen_embryos,
            "embryo_viability": g.embryo_viability,
        }

        return events


# ────────────────────────────────────────────────────────────────────
#  CHALLENGE 5: Psychological Decay
# ────────────────────────────────────────────────────────────────────

@dataclass
class PsychologicalState:
    """Crew psychological state tracking (P0 FIX: boredom model added).

    Initial values are ESTIMATE — calibrated loosely to Mars-500 baseline
    crew state (Shved 2011 *Aviakosmicheskaya i Ekologicheskaya Meditsina* 45).
    """
    morale: float = 0.8              # ESTIMATE — initial crew morale (Mars-500 analogue)
    social_cohesion: float = 0.9     # ESTIMATE — initial group cohesion
    purpose_alignment: float = 1.0   # Initial: crew members self-selected, purpose clear
    conflict_level: float = 0.1      # ESTIMATE — baseline interpersonal friction
    depression_prevalence: float = 0.0
    earth_nostalgia: float = 0.0
    generation_gap: float = 0.0
    mutiny_risk: float = 0.0
    boredom_level: float = 0.1       # ESTIMATE — baseline boredom (Shved 2011)
    routine_monotony: float = 0.0
    novelty_access: float = 0.8      # ESTIMATE — initial VR/education library access level


class PsychologicalDecaySimulator:
    """Simulates long-term psychological effects of permanent isolation.

    Reference: Mars-500 (520-day isolation), Antarctic winter-over studies,
    submarine crew psychology, ISS long-duration missions.
    """

    def __init__(self, crew_size: int = 4, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._crew_size = crew_size
        self.psych = PsychologicalState()
        self.state = ChallengeState(name="psychological_decay")

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        p = self.psych
        generation = 1 + int(mission_year / 25)

        # ── Isolation effects (compound over time) ──
        # Palinkas 2001 J Human Performance in Extreme Environments 6 22: 3rd-quarter slump
        # 0.03% per year morale erosion — ESTIMATE scaled from Mars-500/Antarctic data
        base_isolation = min(0.3, mission_year * 0.0003)  # ESTIMATE — Palinkas 2001 analogue
        p.morale = max(0.05, 0.8 - base_isolation - p.conflict_level * 0.2)  # ESTIMATE — conflict weight 0.2 from Palinkas 2001 group cohesion model; no published multigenerational spacecraft morale data

        # ── Purpose drift across generations ──
        # Gen 1: "We chose this." Gen 5: "Why are we here?" — ESTIMATE: 5% per generation
        if generation > 2:
            p.purpose_alignment = max(0.1, 1.0 - (generation - 2) * 0.05)  # ESTIMATE — 5% purpose erosion per generation beyond Gen 2; no published multigenerational purpose-drift data

        # ── Earth nostalgia (only affects first 2-3 generations) ──
        if generation <= 3:
            p.earth_nostalgia = min(0.8, mission_year * 0.01)  # ESTIMATE: 1%/yr accumulation
        else:
            p.earth_nostalgia = max(0, p.earth_nostalgia - 0.05)  # ESTIMATE: later gens adapt

        # ── Generation gap widens ──
        p.generation_gap = min(0.8, (generation - 1) * 0.05)  # ESTIMATE: 5% per generation

        # ── Social dynamics ──
        # Confined space + small population → conflicts
        conflict_base = 0.1 + 0.02 * (self._crew_size / max(1, self._crew_size - 1))
        p.conflict_level = min(0.9, conflict_base + p.generation_gap * 0.3)

        # ── Boredom (P0 FIX: Mars-500's primary finding) ──
        # Shved 2011 Aviakosmicheskaya i Ekologicheskaya Meditsina 45: boredom dominant hazard
        # 1%/yr routine monotony growth — ESTIMATE (Mars-500 showed rapid saturation at ~300 d)
        p.routine_monotony = min(1.0, p.routine_monotony + 0.01)   # ESTIMATE — 1%/yr monotony growth; Shved 2011 Aviakosmicheskaya i Ekologicheskaya Meditsina 45 Mars-500 rapid saturation at ~300 d
        p.novelty_access = max(0.1, p.novelty_access - 0.003)       # ESTIMATE: 0.3%/yr VR content decay
        p.boredom_level = min(1.0,
            p.routine_monotony * 0.5 + (1 - p.novelty_access) * 0.3 + (1 - p.purpose_alignment) * 0.2
        )

        # ── Depression (now includes boredom as factor) ──
        p.depression_prevalence = max(0, min(1.0,
            (1 - p.morale) * 0.2 + (1 - p.purpose_alignment) * 0.15 +
            p.boredom_level * 0.35 + base_isolation * 0.3  # Boredom is largest factor
        ))

        # ── Mutiny risk ──
        p.mutiny_risk = max(0, min(1.0,
            (1 - p.morale) * (1 - p.purpose_alignment) * p.conflict_level
        ))

        # ── Random psychological events ──
        # 3%/yr incidence — ESTIMATE (Kanas 2015 Space Psychology and Psychiatry conflict rate analogue)
        if self._rng.random() < 0.03:  # ESTIMATE: 3%/yr significant psychological event
            event = self._rng.choice([
                "interpersonal_conflict", "depression_episode",
                "purpose_crisis", "cabin_fever",
            ])
            if event == "interpersonal_conflict":
                p.conflict_level = min(0.9, p.conflict_level + 0.1)
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": "Serious interpersonal conflict — AI mediation required",
                    "subsystem": "psychology_crew",
                })
            elif event == "depression_episode":
                p.depression_prevalence = min(1.0, p.depression_prevalence + 0.2)
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": "Crew member depression episode — reduced duty capacity",
                    "subsystem": "psychology_crew",
                })
            elif event == "purpose_crisis":
                p.purpose_alignment *= 0.8
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": f"Gen {generation} questioning mission purpose — morale drop",
                    "subsystem": "psychology_crew",
                })
            elif event == "cabin_fever":
                p.morale *= 0.9
                events.append({
                    "year": mission_year,
                    "severity": "WATCH",
                    "message": "Cabin fever symptoms — recommend schedule rotation",
                    "subsystem": "psychology_crew",
                })

        # ── Mutiny event ──
        if p.mutiny_risk > 0.5 and self._rng.random() < p.mutiny_risk * 0.01:
            events.append({
                "year": mission_year,
                "severity": "EMERGENCY",
                "message": f"MUTINY ATTEMPT — Gen {generation} faction demanding course change. "
                           "AI must mediate. Ship authority in question.",
                "subsystem": "psychology_crew",
            })

        # ── Milestone events ──
        if mission_year > 0 and mission_year % 100 == 0:
            events.append({
                "year": mission_year,
                "severity": "NOMINAL",
                "message": f"Century {int(mission_year/100)}: Gen {generation}, "
                           f"morale={p.morale:.0%}, purpose={p.purpose_alignment:.0%}, "
                           f"conflict={p.conflict_level:.0%}",
                "subsystem": "psychology_crew",
            })

        # Update state
        self.state.severity_score = 1.0 - p.morale
        if p.mutiny_risk > 0.5:
            self.state.status = ChallengeStatus.TERMINAL
        elif p.morale < 0.2:
            self.state.status = ChallengeStatus.CRITICAL
        elif p.morale < 0.4:
            self.state.status = ChallengeStatus.ACTIVE
        elif p.morale < 0.6:
            self.state.status = ChallengeStatus.EMERGING
        else:
            self.state.status = ChallengeStatus.NOMINAL

        self.state.metrics = {
            "morale": p.morale,
            "purpose_alignment": p.purpose_alignment,
            "conflict_level": p.conflict_level,
            "depression_prevalence": p.depression_prevalence,
            "mutiny_risk": p.mutiny_risk,
            "boredom_level": p.boredom_level,
            "novelty_access": p.novelty_access,
            "generation": generation,
            "generation_gap": p.generation_gap,
        }

        return events


# ────────────────────────────────────────────────────────────────────
#  CHALLENGE 6: The Fuel Cliff
# ────────────────────────────────────────────────────────────────────

@dataclass
class FuelState:
    """Detailed fuel and energy economics."""
    # Deuterium-Tritium fusion fuel — Zubrin & Andrews 1991 Mars Direct rocket eq
    # interstellar variant: 50 t DT gives ~1000 yr cruise at 500 kW reactor draw
    dt_fuel_kg: float = 50000.0    # ESTIMATE — Zubrin 1991 Journal of Propulsion and Power 7 395
    dt_initial_kg: float = 50000.0

    # Helium-3 (secondary fuel, from tritium decay)
    he3_kg: float = 0.0

    # Fusion reactor — Brayton-cycle thermal→electric at 33 % (Dostal 2004 MIT-ANP-TR-100)
    # Full electric including pulse driver ~40 % (higher than pure Brayton;
    # direct-conversion plasma: Wurzel & Hsu 2022 Physics of Plasmas 29 062506)
    reactor_efficiency: float = 0.4   # Wurzel & Hsu 2022 Physics of Plasmas 29 062506
    reactor_health: float = 1.0
    reactor_restarts: int = 0  # Each restart degrades reactor

    # RTG backup — Pu-238 t½ = 87.7 yr (NNDC 2021)
    rtg_power_fraction: float = 1.0   # Pu-238 decay (NNDC 2021)

    # Power budget (watts) — ISS 75-90 kW continuous (NASA SSP 30482 Rev.B);
    # generation ship baseline scaled 5–7× for added systems
    generation_w: float = 500000.0    # ESTIMATE — 5× ISS scale (NASA SSP 30482)
    consumption_w: float = 200000.0   # ESTIMATE — 40 % load factor baseline

    # Braking parameters
    braking_started: bool = False
    # Braking fuel ~40 % of initial mass: Tsiolkovsky eq ΔV=v_e·ln(m₀/mf),
    # for 0.1c decel with v_e=0.03c, mf/m₀ = exp(-0.1/0.03) ≈ 0.035 → fuel ≈ 97 %
    # (Zubrin 1999 "Entering Space" Ch.6). Conservative 40% for lower-Isp variant.
    braking_fuel_estimate_kg: float = 20000.0  # ESTIMATE — Zubrin 1999 rocket equation budget
    velocity_c: float = 0.1
    target_distance_ly: float = 100.0


class FuelCliffSimulator:
    """Simulates the fuel economics of interstellar travel.

    The fuel cliff: you must save enough fuel to decelerate at the destination.
    Braking burns ~40% of initial fuel. If you consume too much during cruise,
    you overshoot the target and become a rogue spacecraft forever.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.fuel = FuelState()
        self.state = ChallengeState(name="fuel_cliff")

    def simulate_year(self, mission_year: float, distance_ly: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        f = self.fuel

        # ── Cruise fuel consumption ──
        # Fusion reactor burn rate 40 kg/yr at η=1.0 (ESTIMATE — scaled from
        # ITER 2018 fusion power Q≥10; 500 kW continuous at 0.4 efficiency)
        cruise_consumption = 40.0 * (1.0 / max(0.1, f.reactor_efficiency))  # ESTIMATE — ITER 2018

        # ── Tritium decay → Helium-3 production ──
        # Tritium half-life: 12.32 years → some fuel converts to He-3
        tritium_fraction = 0.6  # D-T: tritium A=3, deuterium A=2 → 3/5=0.6 by mass
        tritium_decay_rate = 0.5 ** (1.0 / 12.32)  # Per year
        tritium_lost = f.dt_fuel_kg * tritium_fraction * (1 - tritium_decay_rate)
        f.he3_kg += tritium_lost * 0.75  # Mass conversion
        cruise_consumption += tritium_lost * 0.25  # Net fuel loss from decay

        # ── Braking decision ──
        remaining_distance = f.target_distance_ly - distance_ly
        years_to_target = remaining_distance / f.velocity_c if f.velocity_c > 0 else float("inf")

        # Braking should start when: remaining fuel ≈ braking need + safety margin
        fuel_after_cruise = f.dt_fuel_kg - (cruise_consumption * years_to_target)
        braking_possible = fuel_after_cruise >= f.braking_fuel_estimate_kg

        if not f.braking_started and remaining_distance < 15:
            f.braking_started = True
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": f"BRAKING PHASE INITIATED at {distance_ly:.1f} ly. "
                           f"Fuel remaining: {f.dt_fuel_kg:.0f} kg "
                           f"(need {f.braking_fuel_estimate_kg:.0f} kg for deceleration)",
                "subsystem": "propulsion_main",
            })

        if f.braking_started:
            # Deceleration burns: ~500-2000 kg/year depending on phase
            brake_rate = 1500.0 if remaining_distance < 5 else 500.0
            cruise_consumption += brake_rate

        f.dt_fuel_kg = max(0, f.dt_fuel_kg - cruise_consumption)

        # ── Reactor degradation ──
        f.reactor_efficiency = max(0.1, f.reactor_efficiency - 0.001)
        f.reactor_health = max(0, f.reactor_health - 0.003)

        # Random reactor scram (1% per year)
        if self._rng.random() < 0.01:
            f.reactor_restarts += 1
            f.reactor_health -= 0.05
            f.reactor_efficiency *= 0.98
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": f"Reactor scram #{f.reactor_restarts} — "
                           f"efficiency now {f.reactor_efficiency:.1%}",
                "subsystem": "power_generation",
            })

        # ── RTG backup decay ──
        f.rtg_power_fraction = 0.5 ** (mission_year / 87.7)

        # ── Power generation ──
        f.generation_w = (
            400000 * f.reactor_health * f.reactor_efficiency +
            100000 * f.rtg_power_fraction
        )

        # ── Fuel cliff alerts ──
        fuel_fraction = f.dt_fuel_kg / f.dt_initial_kg

        # Latched fuel alarms: fire on each new tier, don't spam yearly.
        if f.dt_fuel_kg <= 0 and not getattr(self, "_fuel_exhausted_latched", False):
            events.append({
                "year": mission_year,
                "severity": "EMERGENCY",
                "message": "FUEL EXHAUSTED — ship is now a ballistic projectile. "
                           "Cannot decelerate at destination.",
                "subsystem": "propulsion_main",
            })
            self._fuel_exhausted_latched = True
        elif (not braking_possible and not f.braking_started
              and not getattr(self, "_fuel_cliff_latched", False)):
            events.append({
                "year": mission_year,
                "severity": "EMERGENCY",
                "message": f"FUEL CLIFF: insufficient fuel for braking. "
                           f"Have {f.dt_fuel_kg:.0f} kg, need {f.braking_fuel_estimate_kg:.0f} kg + "
                           f"{cruise_consumption * years_to_target:.0f} kg cruise. "
                           "Ship will overshoot target star.",
                "subsystem": "propulsion_main",
            })
            self._fuel_cliff_latched = True
        elif fuel_fraction < 0.1 and not getattr(self, "_fuel_10pct_latched", False):
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": f"Fuel critically low: {fuel_fraction:.1%} ({f.dt_fuel_kg:.0f} kg)",
                "subsystem": "propulsion_main",
            })
            self._fuel_10pct_latched = True
        elif fuel_fraction < 0.3 and not getattr(self, "_fuel_30pct_latched", False):
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": f"Fuel below 30%: {f.dt_fuel_kg:.0f} kg remaining",
                "subsystem": "propulsion_main",
            })
            self._fuel_30pct_latched = True

        # Power deficit
        if f.generation_w < f.consumption_w and not getattr(self, "_power_deficit_latched", False):
            deficit = f.consumption_w - f.generation_w
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": f"Power deficit: generating {f.generation_w:.0f}W, need {f.consumption_w:.0f}W "
                           f"(deficit: {deficit:.0f}W)",
                "subsystem": "power_generation",
            })
            self._power_deficit_latched = True
        elif f.generation_w >= f.consumption_w * 1.05:
            self._power_deficit_latched = False

        # Update state
        if f.dt_fuel_kg <= 0:
            self.state.status = ChallengeStatus.TERMINAL
            self.state.severity_score = 1.0
        elif not braking_possible:
            self.state.status = ChallengeStatus.CRITICAL
            self.state.severity_score = 0.9
        elif fuel_fraction < 0.2:
            self.state.status = ChallengeStatus.ACTIVE
            self.state.severity_score = 0.6
        elif fuel_fraction < 0.4:
            self.state.status = ChallengeStatus.EMERGING
            self.state.severity_score = 0.3
        else:
            self.state.status = ChallengeStatus.NOMINAL
            self.state.severity_score = 1.0 - fuel_fraction

        self.state.metrics = {
            "fuel_kg": f.dt_fuel_kg,
            "fuel_fraction": fuel_fraction,
            "he3_kg": f.he3_kg,
            "reactor_efficiency": f.reactor_efficiency,
            "reactor_health": f.reactor_health,
            "generation_w": f.generation_w,
            "consumption_w": f.consumption_w,
            "braking_started": f.braking_started,
            "braking_possible": braking_possible,
            "years_to_target": years_to_target,
        }

        return events


# ────────────────────────────────────────────────────────────────────
#  INTEGRATED CHALLENGE ORCHESTRATOR
# ────────────────────────────────────────────────────────────────────

class InterstellarChallengeOrchestrator:
    """Runs all 6 interstellar challenges together, detecting cross-challenge cascades.

    Example cascades:
      - Material entropy → can't replace grow lights → food crisis
      - Fuel cliff → power deficit → knowledge base can't run migrations → knowledge loss
      - Genetic diversity low → psychological stress → mutiny → everything fails
    """

    def __init__(
        self,
        crew_size: int = 4,
        seed: int | None = None,
        target_distance_ly: float = 100.0,
        cruise_velocity_c: float = 0.1,
    ) -> None:
        # Each simulator gets a different seed to decorrelate random events
        # (identical seeds → all failures cluster in the same year)
        def offset_seed(i: int) -> int | None:
            return (seed + i * 7919) if seed is not None else None  # 7919 = prime offset

        self.materials = MaterialEntropySimulator(seed=offset_seed(0))
        self.food = FoodCenturySimulator(crew_size=crew_size, seed=offset_seed(1))
        self.knowledge = KnowledgePreservationSimulator(seed=offset_seed(2))
        self.genetics = GeneticDiversitySimulator(initial_population=crew_size, seed=offset_seed(3))
        self.psychology = PsychologicalDecaySimulator(crew_size=crew_size, seed=offset_seed(4))
        self.fuel = FuelCliffSimulator(seed=offset_seed(5))
        # Sync fuel-cliff mission parameters with the actual mission profile.
        self.fuel.fuel.target_distance_ly = target_distance_ly
        self.fuel.fuel.velocity_c = cruise_velocity_c

        self._simulators = {
            "materials": self.materials,
            "food": self.food,
            "knowledge": self.knowledge,
            "genetics": self.genetics,
            "psychology": self.psychology,
            "fuel": self.fuel,
        }

    def simulate_year(self, mission_year: float, distance_ly: float) -> dict[str, Any]:
        """Run all challenges for one year and detect cascades."""
        all_events: list[dict[str, Any]] = []

        # Run each challenge
        all_events.extend(self.materials.simulate_year(mission_year))
        all_events.extend(self.food.simulate_year(mission_year))
        all_events.extend(self.knowledge.simulate_year(mission_year))
        all_events.extend(self.genetics.simulate_year(mission_year))
        all_events.extend(self.psychology.simulate_year(mission_year))
        all_events.extend(self.fuel.simulate_year(mission_year, distance_ly))

        # ── Cross-challenge cascades ──
        cascades = self._detect_cascades(mission_year)
        all_events.extend(cascades)

        return {
            "year": mission_year,
            "events": all_events,
            "challenge_states": {
                name: {
                    "status": sim.state.status.value,
                    "severity": sim.state.severity_score,
                    "metrics": sim.state.metrics,
                }
                for name, sim in self._simulators.items()
            },
            "overall_severity": max(s.state.severity_score for s in self._simulators.values()),
            "terminal_count": sum(
                1 for s in self._simulators.values()
                if s.state.status == ChallengeStatus.TERMINAL
            ),
        }

    def _detect_cascades(self, year: float) -> list[dict[str, Any]]:
        """Detect cross-challenge cascade failures."""
        cascades: list[dict[str, Any]] = []

        # Cascade: Material entropy → grow light failure → food crisis
        mat_metrics = self.materials.state.metrics
        food_metrics = self.food.state.metrics
        if (mat_metrics.get("rare_earth_kg", 100) < 10
                and food_metrics.get("grow_light_health", 1) < 0.3):
            cascades.append({
                "year": year,
                "severity": "CRITICAL",
                "message": "CASCADE: Rare earth depletion → cannot replace grow lights → food production collapsing",
                "subsystem": "cascade_detector",
                "cascade": "materials→food",
            })

        # Cascade: Power deficit → knowledge migration impossible
        fuel_metrics = self.fuel.state.metrics
        kb_metrics = self.knowledge.state.metrics
        if (fuel_metrics.get("generation_w", 500000) < fuel_metrics.get("consumption_w", 200000)
                and kb_metrics.get("best_storage_health", 1) < 0.3):
            cascades.append({
                "year": year,
                "severity": "CRITICAL",
                "message": "CASCADE: Power deficit → insufficient power for knowledge migration → data loss accelerating",
                "subsystem": "cascade_detector",
                "cascade": "fuel→knowledge",
            })

        # Cascade: Genetic disease + low morale → medical/psychological compound
        gen_metrics = self.genetics.state.metrics
        psych_metrics = self.psychology.state.metrics
        if (gen_metrics.get("genetic_diseases", 0) > 3
                and psych_metrics.get("morale", 1) < 0.3):
            cascades.append({
                "year": year,
                "severity": "EMERGENCY",
                "message": "CASCADE: Genetic disease burden + low morale → crew capability severely degraded",
                "subsystem": "cascade_detector",
                "cascade": "genetics→psychology",
            })

        # Cascade: Food shortage → psychological crisis → mutiny risk
        if (food_metrics.get("food_ratio", 1) < 0.7
                and psych_metrics.get("mutiny_risk", 0) > 0.2):
            cascades.append({
                "year": year,
                "severity": "EMERGENCY",
                "message": "CASCADE: Food shortage → crew unrest → mutiny risk elevated",
                "subsystem": "cascade_detector",
                "cascade": "food→psychology",
            })

        return cascades

    def run_full_mission(self, velocity_c: float = 0.1, target_ly: float = 100.0) -> list[dict[str, Any]]:
        """Simulate the entire mission, returning yearly results."""
        total_years = int(target_ly / velocity_c)
        results = []
        for year in range(1, total_years + 1):
            distance = year * velocity_c
            result = self.simulate_year(float(year), distance)
            results.append(result)
        return results

    def get_summary(self) -> dict[str, Any]:
        """Get current state summary of all challenges."""
        return {
            name: {
                "status": sim.state.status.value,
                "severity": sim.state.severity_score,
                "metrics": sim.state.metrics,
            }
            for name, sim in self._simulators.items()
        }
