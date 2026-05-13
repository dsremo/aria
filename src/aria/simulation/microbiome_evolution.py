"""Microbiome Evolution Model for ARIA's 1000-Year Generation Ship.

Models the drift, selection, and adaptation of microbial communities in a
closed interstellar habitat over ~40,000 bacterial generations per mission year.

COMPARTMENT 1: HUMAN GUT MICROBIOME
  Founder effect: 1000 crew carry ~1000 species (subset of Earth's ~5000+ gut spp).
  Wright-Fisher genetic drift reduces rare species; Shannon diversity declines.
  Diet selection: limited crop variety → reduced fiber diversity → Bacteroidetes decline.
  Horizontal gene transfer (HGT): closed system + antibiotic pressure → elevated
  conjugation/transduction rates (baseline ~10^-5/generation, rising to ~10^-3).
  Dysbiosis threshold: Shannon H' < 2.5 triggers inflammatory bowel disease risk.
  Reference: Sonnenburg & Sonnenburg (2019), David et al. (2014), Groussin et al. (2017)

COMPARTMENT 2: SHIP SURFACE MICROBIOME
  Material-dependent colonization: stainless steel > polymer > borosilicate glass.
  Antimicrobial resistance (AMR) evolution: β-lactam, fluoroquinolone, aminoglycoside
  resistance genes accumulate via mutation (~10^-9/bp/generation) and HGT.
  Pathogenic mutation: virulence island acquisition probability per generation.
  Biofilm-embedded communities are 100-1000x more resistant to antimicrobials.
  Reference: Mora et al. (2016) ISS surface microbiome, Checinska et al. (2015)

COMPARTMENT 3: SOIL / AGRICULTURE MICROBIOME
  Mycorrhizal arbuscular fungi (AMF): >80% of crop plants depend on AMF for
  phosphorus uptake; network health index drives crop yield modifier.
  Nitrogen-fixing bacteria (Rhizobium, Azotobacter): population in CFU/g soil.
  Soil organic matter (SOM) cycling: decomposer community maintains humus layer.
  Closed nutrient loop means no external inputs — any species loss is permanent.
  Reference: van der Heijden et al. (2008), Bever et al. (2010)

COMPARTMENT 4: WATER SYSTEM MICROBIOME
  Legionella pneumophila: optimal growth 25-42°C in stagnant warm water.
  Complements BiofilmWaterSimulator in biology_social.py (pipe biofilm thickness,
  UV sterilization) — this module tracks species-level community composition
  and resistance evolution in the water distribution system.
  Chloramine-resistant biofilm community structure.
  Reference: Falkinham et al. (2015), Proctor et al. (2018)

Key biological parameters:
  - E. coli generation time: ~20 minutes (72 generations/day, ~26,280/year)
  - HGT conjugation rate: ~10^-5 per donor per generation (baseline)
  - Point mutation rate: ~5.4 × 10^-10 per bp per generation (E. coli)
  - Gut species count (healthy human): 500-1000 species
  - Shannon diversity (healthy gut): H' = 3.0 - 4.5
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()

# ════════════════════════════════════════════════════════════════
#  Constants — real microbiological parameters
# ════════════════════════════════════════════════════════════════

ECOLI_GENERATION_TIME_HOURS = 1 / 3  # ~20 minutes
GENERATIONS_PER_YEAR = 365.25 * 24 / ECOLI_GENERATION_TIME_HOURS  # ~26,298
POINT_MUTATION_RATE_PER_BP = 5.4e-10  # per bp per generation (Drake 1991)
ECOLI_GENOME_SIZE_BP = 4_600_000
MUTATIONS_PER_GENOME_PER_GEN = POINT_MUTATION_RATE_PER_BP * ECOLI_GENOME_SIZE_BP  # ~0.0025

HGT_BASELINE_RATE = 1e-5  # conjugation events per donor cell per generation
HGT_CLOSED_SYSTEM_MULTIPLIER = 3.0  # elevated in closed system (proximity + stress)

EARTH_GUT_SPECIES_POOL = 10000  # ~10,000 OTUs (Almeida 2019, Nature Biotech; MetaHIT/HMP)
HEALTHY_SHANNON_MIN = 3.0
HEALTHY_SHANNON_MAX = 4.5
DYSBIOSIS_THRESHOLD = 2.5  # H' below this → clinical concern

# Surface colonization rates (relative, per year) — ISS data
COLONIZATION_RATE = {
    "stainless_steel": 0.12,
    "aluminum": 0.10,
    "polymer": 0.07,
    "glass": 0.04,
    "titanium": 0.06,
}

# Antimicrobial resistance classes
AMR_CLASSES = [
    "beta_lactam",
    "fluoroquinolone",
    "aminoglycoside",
    "tetracycline",
    "vancomycin",
    "colistin",  # last-resort
]

# Legionella growth rate vs temperature (logistic-like)
LEGIONELLA_OPTIMAL_TEMP_C = 37.0
LEGIONELLA_GROWTH_RANGE = (20.0, 45.0)


# ════════════════════════════════════════════════════════════════
#  1. HUMAN GUT MICROBIOME
# ════════════════════════════════════════════════════════════════

@dataclass
class GutMicrobiomeState:
    """Tracks the collective gut microbiome of the ship's population."""

    species_count: int = 1000  # ESTIMATE — founder effect: ~1000 OTUs (HMP: Turnbaugh 2007 Nature 449 804)
    species_abundances: list[float] = field(default_factory=list)
    # H' = 3.8 is the mean Shannon diversity for healthy Western adults
    # (HMP Consortium 2012 *Nature* 486 207, Supplementary Table 2).
    shannon_diversity: float = 3.8  # HMP Consortium 2012 Nature 486 207
    dysbiosis_risk: float = 0.0  # 0-1 probability
    hgt_rate: float = HGT_BASELINE_RATE
    diet_diversity_index: float = 1.0  # 1.0 = full Earth variety, declines
    # Phylum fractions from MetaHIT gut metagenome survey (Qin et al.
    # 2010 *Nature* 464 59): Bacteroidetes 44 %, Firmicutes 40 %,
    # Proteobacteria 11 %, other 5 % — rounded to 2 decimal places.
    bacteroidetes_fraction: float = 0.45  # Qin 2010 Nature 464 59
    firmicutes_fraction: float = 0.40    # Qin 2010 Nature 464 59
    proteobacteria_fraction: float = 0.10  # Qin 2010 (bloom → dysbiosis marker)
    other_fraction: float = 0.05         # Qin 2010 residual phyla
    cumulative_hgt_events: int = 0
    novel_gene_combinations: int = 0

    def __post_init__(self):
        if not self.species_abundances:
            # Log-normal distribution of species abundances (Preston 1948)
            self.species_abundances = _generate_lognormal_abundances(
                self.species_count, seed=42
            )


def _generate_lognormal_abundances(n_species: int, seed: int = 42) -> list[float]:
    """Generate realistic species abundance distribution (log-normal)."""
    rng = random.Random(seed)
    raw = [math.exp(rng.gauss(0, 2.0)) for _ in range(n_species)]
    total = sum(raw)
    return [x / total for x in raw]


def shannon_index(abundances: list[float]) -> float:
    """Compute Shannon diversity index H' = -Σ p_i * ln(p_i)."""
    h = 0.0
    for p in abundances:
        if p > 0:
            h -= p * math.log(p)
    return h


class GutMicrobiomeSimulator:
    """Wright-Fisher drift + diet selection on the ship's human gut microbiome."""

    def __init__(self, crew_size: int, seed: int | None = None):
        self._rng = random.Random(seed)
        self.crew_size = crew_size
        self.state = GutMicrobiomeState()
        self.state.shannon_diversity = shannon_index(self.state.species_abundances)

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # --- Diet diversity decline (limited crop rotation in closed system) ---
        # Gradual loss: ~0.1% per year for first 200 years, then stabilizes
        diet_decay = 0.001 * math.exp(-mission_year / 300)
        s.diet_diversity_index = max(0.3, s.diet_diversity_index - diet_decay)

        # --- Wright-Fisher genetic drift ---
        # Effective population size scales with crew * gut volume
        # Rare species (< 0.01% abundance) face extinction via drift
        n_eff = self.crew_size * 1000  # effective microbial population proxy
        new_abundances = []
        extinct = 0
        for p in s.species_abundances:
            # Drift: variance of allele frequency ~ p(1-p)/2N
            drift_sd = math.sqrt(max(0, p * (1 - p) / (2 * n_eff)))
            new_p = max(0.0, p + self._rng.gauss(0, drift_sd))
            # Diet selection pressure: low diet diversity penalizes specialists
            selection_penalty = (1 - s.diet_diversity_index) * 0.02
            new_p *= (1 - selection_penalty * self._rng.random())
            if new_p < 1e-8:
                extinct += 1
                new_p = 0.0
            new_abundances.append(new_p)

        # Renormalize
        total = sum(new_abundances)
        if total > 0:
            s.species_abundances = [p / total for p in new_abundances]
        s.species_count = sum(1 for p in s.species_abundances if p > 0)

        # Shannon diversity
        s.shannon_diversity = shannon_index(s.species_abundances)

        if extinct > 0:
            events.append({
                "year": mission_year, "severity": "INFO",
                "message": f"Gut microbiome: {extinct} species lost to drift/selection "
                           f"(remaining: {s.species_count})",
                "subsystem": "gut_microbiome",
            })

        # --- Phylum shifts under diet pressure ---
        # Low fiber → Bacteroidetes decline, Proteobacteria bloom
        fiber_factor = s.diet_diversity_index
        s.bacteroidetes_fraction = max(0.10, 0.45 * fiber_factor)
        s.proteobacteria_fraction = min(0.40, 0.10 + 0.20 * (1 - fiber_factor))
        s.firmicutes_fraction = max(0.20, 1.0 - s.bacteroidetes_fraction
                                    - s.proteobacteria_fraction - s.other_fraction)

        # --- HGT rate escalation in closed system ---
        # Stress + proximity + antibiotic use → HGT rate climbs
        year_factor = min(5.0, 1.0 + mission_year / 200)  # up to 5x baseline
        s.hgt_rate = HGT_BASELINE_RATE * HGT_CLOSED_SYSTEM_MULTIPLIER * year_factor

        # Estimated HGT events this year across the gut population
        hgt_events_year = int(s.hgt_rate * GENERATIONS_PER_YEAR * s.species_count)
        s.cumulative_hgt_events += hgt_events_year
        # ~1% of HGT events produce novel functional combinations
        s.novel_gene_combinations += max(0, int(hgt_events_year * 0.01))

        # --- Dysbiosis risk ---
        if s.shannon_diversity < DYSBIOSIS_THRESHOLD:
            s.dysbiosis_risk = min(1.0, (DYSBIOSIS_THRESHOLD - s.shannon_diversity) / 1.5)
        else:
            s.dysbiosis_risk = max(0, 0.1 * (DYSBIOSIS_THRESHOLD - s.shannon_diversity + 0.5))

        if s.dysbiosis_risk > 0.5:
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": f"Gut dysbiosis risk {s.dysbiosis_risk:.0%} — "
                           f"Shannon H'={s.shannon_diversity:.2f}, "
                           f"Proteobacteria bloom {s.proteobacteria_fraction:.0%}",
                "subsystem": "gut_microbiome",
            })

        if s.dysbiosis_risk > 0.8:
            events.append({
                "year": mission_year, "severity": "CRITICAL",
                "message": "Population-wide inflammatory bowel disease risk — "
                           "fecal microbiota transplant reserves critically low",
                "subsystem": "gut_microbiome",
            })

        return events


# ════════════════════════════════════════════════════════════════
#  2. SHIP SURFACE MICROBIOME
# ════════════════════════════════════════════════════════════════

@dataclass
class SurfaceMicrobiomeState:
    """Microbial colonization and AMR evolution on ship surfaces."""

    # Material → biofilm coverage fraction (0-1)
    surface_colonization: dict[str, float] = field(
        default_factory=lambda: {m: 0.0 for m in COLONIZATION_RATE}
    )
    # AMR gene prevalence per class (fraction of surface isolates carrying gene)
    amr_prevalence: dict[str, float] = field(
        default_factory=lambda: {c: 0.01 for c in AMR_CLASSES}
    )
    multi_drug_resistant_fraction: float = 0.0
    pathogenic_mutation_count: int = 0
    pathogen_risk: float = 0.0  # probability of dangerous pathogen emergence
    virulence_island_acquisitions: int = 0
    total_surface_area_m2: float = 80_000.0  # ISS: ~1000 m² for 6 crew → scale to 1000 crew × 80 m²/person

    def avg_colonization(self) -> float:
        vals = list(self.surface_colonization.values())
        return sum(vals) / len(vals) if vals else 0.0


class SurfaceMicrobiomeSimulator:
    """Models surface colonization, AMR evolution, and pathogen emergence."""

    # Virulence island acquisition: ~10^-8 per cell per generation
    VIRULENCE_ACQUISITION_RATE = 1e-8
    # AMR mutation rate per resistance locus per generation
    AMR_MUTATION_RATE = 1e-7

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self.state = SurfaceMicrobiomeState()

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # --- Surface colonization (logistic growth per material) ---
        for material, rate in COLONIZATION_RATE.items():
            current = s.surface_colonization[material]
            # Logistic growth: dC/dt = r * C * (1 - C)
            growth = rate * current * (1 - current) if current > 0.001 else rate * 0.01
            s.surface_colonization[material] = min(1.0, current + growth)

        # --- AMR evolution ---
        for drug_class in AMR_CLASSES:
            prev = s.amr_prevalence[drug_class]
            # Selection + mutation + HGT spread
            mutation_gain = self.AMR_MUTATION_RATE * GENERATIONS_PER_YEAR
            # Positive selection: resistant strains have ~5% fitness advantage
            # when antimicrobials are used (which they are in closed system)
            selection_gain = prev * 0.05
            # HGT spread: proportional to donor frequency and contact rate
            hgt_gain = prev * (1 - prev) * HGT_BASELINE_RATE * GENERATIONS_PER_YEAR * 0.01
            new_prev = min(1.0, prev + mutation_gain + selection_gain + hgt_gain)
            s.amr_prevalence[drug_class] = new_prev

        # Multi-drug resistance: fraction carrying 3+ resistance genes
        resistant_classes = [c for c, p in s.amr_prevalence.items() if p > 0.1]
        if len(resistant_classes) >= 3:
            # Approximate MDR as product of top-3 prevalences (co-occurrence)
            sorted_prev = sorted(s.amr_prevalence.values(), reverse=True)
            s.multi_drug_resistant_fraction = min(
                1.0, sorted_prev[0] * sorted_prev[1] * sorted_prev[2] * 10
            )
        else:
            s.multi_drug_resistant_fraction = 0.0

        # --- Pathogenic mutation / virulence island acquisition ---
        # Effective population on surfaces: ~10^9 cells per m^2 of biofilm
        avg_col = s.avg_colonization()
        effective_cells = avg_col * s.total_surface_area_m2 * 1e9
        virulence_events = (
            self.VIRULENCE_ACQUISITION_RATE * effective_cells
            * GENERATIONS_PER_YEAR * 1e-6  # scaled for yearly probability
        )
        new_virulence = int(self._rng.expovariate(1 / max(0.01, virulence_events)))
        s.virulence_island_acquisitions += new_virulence
        s.pathogenic_mutation_count += new_virulence

        # Pathogen risk: function of MDR + virulence + colonization
        s.pathogen_risk = min(1.0, (
            s.multi_drug_resistant_fraction * 0.3
            + s.virulence_island_acquisitions / 100 * 0.4
            + avg_col * 0.3
        ))

        # Latched AMR/pathogen alarms — condition persists so don't spam.
        if s.multi_drug_resistant_fraction > 0.3 and not getattr(self, "_mdr_latched", False):
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": f"Multi-drug resistant organisms at "
                           f"{s.multi_drug_resistant_fraction:.0%} prevalence on surfaces",
                "subsystem": "surface_microbiome",
            })
            self._mdr_latched = True
        elif s.multi_drug_resistant_fraction <= 0.2:
            self._mdr_latched = False

        if s.pathogen_risk > 0.6 and not getattr(self, "_pathogen_latched", False):
            events.append({
                "year": mission_year, "severity": "CRITICAL",
                "message": f"Pathogen emergence risk {s.pathogen_risk:.0%} — "
                           f"{s.virulence_island_acquisitions} virulence acquisitions detected",
                "subsystem": "surface_microbiome",
            })
            self._pathogen_latched = True
        elif s.pathogen_risk <= 0.5:
            self._pathogen_latched = False

        if not hasattr(self, "_amr_latched"):
            self._amr_latched = set()
        for abx, p in s.amr_prevalence.items():
            if p > 0.8 and abx not in self._amr_latched:
                events.append({
                    "year": mission_year, "severity": "EMERGENCY",
                    "message": f"{abx} resistance near-universal "
                               f"({p:.0%}) — antibiotic class effectively useless",
                    "subsystem": "surface_microbiome",
                })
                self._amr_latched.add(abx)
            elif p <= 0.7:
                self._amr_latched.discard(abx)

        return events


# ════════════════════════════════════════════════════════════════
#  3. SOIL / AGRICULTURE MICROBIOME
# ════════════════════════════════════════════════════════════════

@dataclass
class SoilMicrobiomeState:
    """Agricultural soil microbiome health for the ship's food production."""

    mycorrhizal_health: float = 1.0  # 0 = collapsed, 1 = thriving
    mycorrhizal_species_count: int = 50  # ESTIMATE — 50 AMF species; van der Heijden 1998 Nature 396 69: diversity drives yield
    nitrogen_fixers_cfu_per_g: float = 1e7  # ESTIMATE — 10^7 CFU/g healthy soil (Bottomley 2006 Agronomy §21)
    decomposer_activity: float = 1.0  # relative decomposition rate
    soil_organic_matter_pct: float = 5.0  # ESTIMATE — 5% SOM healthy range (Brady & Weil 2014 Nature/Properties of Soils §12)
    phosphorus_availability: float = 1.0  # relative, driven by AMF
    crop_yield_modifier: float = 1.0  # multiplicative effect on food production
    pathogenic_fungi_risk: float = 0.0  # Fusarium, Pythium
    soil_ph: float = 6.5  # ESTIMATE — 6.5 optimal for most crops (Brady & Weil 2014 §12.5)
    microbial_biomass_carbon_mg_per_kg: float = 400.0  # ESTIMATE — 200-600 mg/kg healthy soil (Anderson 2003 Soil Biol Biochem 35 311)


class SoilMicrobiomeSimulator:
    """Models soil microbiome dynamics critical for closed-loop agriculture."""

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self.state = SoilMicrobiomeState()

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # --- Mycorrhizal network health ---
        # In closed system, genetic diversity of AMF slowly erodes
        drift_loss = self._rng.random() * 0.01  # ~1% chance of losing a species/yr
        if drift_loss > 0.008 and s.mycorrhizal_species_count > 5:
            s.mycorrhizal_species_count -= 1

        # Health scales with species richness (log relationship)
        s.mycorrhizal_health = min(1.0, math.log(s.mycorrhizal_species_count + 1)
                                   / math.log(51))  # normalized to initial 50 species

        # Phosphorus availability driven by AMF
        s.phosphorus_availability = 0.3 + 0.7 * s.mycorrhizal_health

        # --- Nitrogen-fixing bacteria ---
        # Population fluctuates with soil pH, organic matter, crop rotation
        ph_stress = abs(s.soil_ph - 6.5) / 3.0  # stress from pH deviation
        n_fix_growth = 0.05 * (1 - ph_stress) * s.decomposer_activity
        n_fix_noise = self._rng.gauss(0, 0.02)
        s.nitrogen_fixers_cfu_per_g *= max(0.5, 1.0 + n_fix_growth + n_fix_noise)
        s.nitrogen_fixers_cfu_per_g = max(1e4, min(1e9, s.nitrogen_fixers_cfu_per_g))

        # --- Soil organic matter cycling ---
        # Decomposers convert plant residue to humus; without them SOM drops
        decomposition_input = 0.3  # annual plant residue return (fraction)
        mineralization = 0.05 * s.decomposer_activity  # SOM breakdown
        s.soil_organic_matter_pct += decomposition_input * 0.1 - mineralization
        s.soil_organic_matter_pct = max(0.5, min(8.0, s.soil_organic_matter_pct))

        # Decomposer activity depends on SOM and moisture (assumed constant in ship)
        s.decomposer_activity = min(1.2, 0.5 + s.soil_organic_matter_pct * 0.1)

        # Microbial biomass carbon
        s.microbial_biomass_carbon_mg_per_kg = (
            200 * s.decomposer_activity + 100 * s.mycorrhizal_health
            + 50 * (s.nitrogen_fixers_cfu_per_g / 1e7)
        )

        # --- Pathogenic fungi ---
        # Enclosed greenhouse → higher humidity → Fusarium/Pythium risk
        base_pathogen_rate = 0.05
        # Risk increases if mycorrhizal network is weakened (AMF suppress pathogens)
        pathogen_boost = (1 - s.mycorrhizal_health) * 0.3
        s.pathogenic_fungi_risk = min(1.0, base_pathogen_rate + pathogen_boost
                                      + self._rng.gauss(0, 0.02))
        s.pathogenic_fungi_risk = max(0.0, s.pathogenic_fungi_risk)

        # --- Soil pH drift (recycled water effects) ---
        s.soil_ph += self._rng.gauss(0, 0.03)
        s.soil_ph = max(4.5, min(8.5, s.soil_ph))

        # --- Crop yield modifier ---
        s.crop_yield_modifier = (
            s.phosphorus_availability * 0.3
            + min(1.0, s.nitrogen_fixers_cfu_per_g / 1e7) * 0.3
            + s.decomposer_activity / 1.2 * 0.2
            + (1 - s.pathogenic_fungi_risk) * 0.2
        )

        # Events
        if s.mycorrhizal_health < 0.5:
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": f"Mycorrhizal network degraded to {s.mycorrhizal_health:.0%} — "
                           f"{s.mycorrhizal_species_count} AMF species remaining",
                "subsystem": "soil_microbiome",
            })

        if s.nitrogen_fixers_cfu_per_g < 1e5:
            events.append({
                "year": mission_year, "severity": "CRITICAL",
                "message": f"Nitrogen-fixing bacteria collapsed to "
                           f"{s.nitrogen_fixers_cfu_per_g:.0e} CFU/g — "
                           "crop nitrogen deficiency imminent",
                "subsystem": "soil_microbiome",
            })

        if s.crop_yield_modifier < 0.6:
            events.append({
                "year": mission_year, "severity": "CRITICAL",
                "message": f"Soil microbiome degradation reducing crop yields to "
                           f"{s.crop_yield_modifier:.0%} of baseline",
                "subsystem": "soil_microbiome",
            })

        if s.pathogenic_fungi_risk > 0.5:
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": f"Fungal pathogen risk at {s.pathogenic_fungi_risk:.0%} — "
                           "Fusarium/Pythium outbreak likely in greenhouse",
                "subsystem": "soil_microbiome",
            })

        return events


# ════════════════════════════════════════════════════════════════
#  4. WATER SYSTEM MICROBIOME
# ════════════════════════════════════════════════════════════════

@dataclass
class WaterMicrobiomeState:
    """Species-level water system microbiome (complements BiofilmWaterSimulator)."""

    legionella_concentration_cfu_l: float = 0.0  # target: <1000 CFU/L (WHO Water Safety 2019)
    legionella_growth_rate: float = 0.0
    water_temp_c: float = 25.0              # ESTIMATE — 25°C distribution temp (Falkinham 2015 Pathogens 4 373: Legionella optimal 25-45°C)
    chloramine_resistant_fraction: float = 0.01  # ESTIMATE — 1% chloramine-resistant biofilm fraction (Proctor 2018 Microbiome 6 111)
    biofilm_community_diversity: float = 3.0  # ESTIMATE — H'=3.0 biofilm (Proctor 2018)
    total_species_in_water: int = 200        # ESTIMATE — 200 species in pipe biofilm community
    opportunistic_pathogen_count: int = 5   # ESTIMATE — 5 opportunistic pathogens (Falkinham 2015 §3)
    disinfection_efficacy: float = 0.95     # ESTIMATE — 95% reduction from chloramine (WHO Water Safety 2019 §9)

    def legionella_safe(self) -> bool:
        return self.legionella_concentration_cfu_l < 1000


class WaterMicrobiomeSimulator:
    """Tracks water system microbial community — complements biology_social.py."""

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self.state = WaterMicrobiomeState()

    def _legionella_growth_factor(self, temp: float) -> float:
        """Temperature-dependent Legionella growth (Arrhenius-like).

        Peak at 37°C, growth between 20-45°C, killed above 60°C.
        """
        if temp < LEGIONELLA_GROWTH_RANGE[0] or temp > 60:
            return 0.0
        if temp > 45:
            # Declining above 45°C, dead at 60°C
            return max(0.0, 1.0 - (temp - 45) / 15)
        # Bell curve centered at 37°C
        return math.exp(-0.5 * ((temp - LEGIONELLA_OPTIMAL_TEMP_C) / 5) ** 2)

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # --- Temperature fluctuation ---
        s.water_temp_c += self._rng.gauss(0, 1.0)
        s.water_temp_c = max(15, min(50, s.water_temp_c))

        # --- Legionella dynamics ---
        growth_factor = self._legionella_growth_factor(s.water_temp_c)
        s.legionella_growth_rate = growth_factor * 0.5  # per year relative growth

        # Legionella population
        base_growth = s.legionella_concentration_cfu_l * (1 + s.legionella_growth_rate)
        # Continuous low-level seeding from biofilm
        seeding = 50 + self._rng.expovariate(0.01) * 0.1
        # Disinfection kill
        kill = s.disinfection_efficacy * (1 - s.chloramine_resistant_fraction)
        s.legionella_concentration_cfu_l = max(
            0, (base_growth + seeding) * (1 - kill)
        )

        # --- Chloramine resistance evolution ---
        # Resistant fraction grows under constant chloramine pressure
        resistance_gain = (
            POINT_MUTATION_RATE_PER_BP * ECOLI_GENOME_SIZE_BP  # ~0.0025 mutations/gen
            * GENERATIONS_PER_YEAR * 1e-5  # fraction conferring resistance
            + s.chloramine_resistant_fraction * 0.03  # selection advantage
        )
        s.chloramine_resistant_fraction = min(
            1.0, s.chloramine_resistant_fraction + resistance_gain
        )

        # Disinfection efficacy declines as resistance grows
        s.disinfection_efficacy = max(0.3, 0.95 - s.chloramine_resistant_fraction * 0.5)

        # --- Water community diversity ---
        # Slow drift loss in closed system
        if self._rng.random() < 0.05:
            s.total_species_in_water = max(20, s.total_species_in_water - 1)
        s.biofilm_community_diversity = min(
            3.5, math.log(s.total_species_in_water + 1) / math.log(201) * 3.5
        )

        # --- Opportunistic pathogen emergence ---
        if self._rng.random() < 0.02:
            s.opportunistic_pathogen_count = min(
                20, s.opportunistic_pathogen_count + 1
            )

        # Events (latched tier transitions)
        if not s.legionella_safe():
            cur = 2 if s.legionella_concentration_cfu_l > 10000 else 1
        else:
            cur = 0
        prev = getattr(self, "_legionella_tier", 0)
        if cur > prev:
            self._legionella_tier = cur
            events.append({
                "year": mission_year,
                "severity": "CRITICAL" if cur == 2 else "WARNING",
                "message": f"Legionella at {s.legionella_concentration_cfu_l:.0f} CFU/L "
                           f"(limit 1000) — water temp {s.water_temp_c:.1f}°C",
                "subsystem": "water_microbiome",
            })
        elif cur == 0 and prev > 0:
            self._legionella_tier = 0

        if s.chloramine_resistant_fraction > 0.3 and not getattr(self, "_chloramine_latched", False):
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": f"Chloramine-resistant biofilm fraction at "
                           f"{s.chloramine_resistant_fraction:.0%} — "
                           "alternative disinfection strategies needed",
                "subsystem": "water_microbiome",
            })
            self._chloramine_latched = True
        elif s.chloramine_resistant_fraction <= 0.2:
            self._chloramine_latched = False

        return events


# ════════════════════════════════════════════════════════════════
#  UNIFIED SIMULATOR
# ════════════════════════════════════════════════════════════════

class MicrobiomeEvolutionSimulator:
    """Unified microbiome evolution across all ship compartments.

    Integrates gut, surface, soil, and water microbiome models to track
    the 1000-year evolutionary trajectory of microbial communities in
    the closed generation ship ecosystem.

    Parameters
    ----------
    crew_size : int
        Number of crew members (affects gut microbiome effective population).
    seed : int
        Random seed for reproducibility.
    """

    def __init__(self, crew_size: int = 1000, seed: int = 42):
        self.crew_size = crew_size
        self.seed = seed
        self.mission_year = 0.0

        self.gut = GutMicrobiomeSimulator(crew_size=crew_size, seed=seed)
        self.surface = SurfaceMicrobiomeSimulator(seed=seed + 1)
        self.soil = SoilMicrobiomeSimulator(seed=seed + 2)
        self.water = WaterMicrobiomeSimulator(seed=seed + 3)

        self._yearly_history: list[dict[str, Any]] = []

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        """Advance all microbiome compartments by one year.

        Returns list of notable events across all compartments.
        """
        self.mission_year = mission_year
        events: list[dict[str, Any]] = []

        events.extend(self.gut.simulate_year(mission_year))
        events.extend(self.surface.simulate_year(mission_year))
        events.extend(self.soil.simulate_year(mission_year))
        events.extend(self.water.simulate_year(mission_year))

        # Cross-compartment interactions
        events.extend(self._cross_compartment_effects(mission_year))

        # Store snapshot
        self._yearly_history.append({
            "year": mission_year,
            "gut_diversity": self.gut.state.shannon_diversity,
            "surface_amr": self.surface.state.multi_drug_resistant_fraction,
            "soil_yield": self.soil.state.crop_yield_modifier,
            "water_legionella": self.water.state.legionella_concentration_cfu_l,
            "event_count": len(events),
        })

        return events

    def _cross_compartment_effects(self, mission_year: float) -> list[dict[str, Any]]:
        """Model interactions between microbiome compartments."""
        events: list[dict[str, Any]] = []

        # Surface AMR genes transfer to gut via hand-mouth route
        surface_amr_pressure = self.surface.state.multi_drug_resistant_fraction
        if surface_amr_pressure > 0.2:
            # Elevate gut HGT rate when surface MDR organisms are prevalent
            self.gut.state.hgt_rate *= (1 + surface_amr_pressure * 0.5)

        # Water contamination affects gut
        if not self.water.state.legionella_safe():
            # Legionella doesn't colonize gut but exposure stresses immune system
            self.gut.state.dysbiosis_risk = min(
                1.0, self.gut.state.dysbiosis_risk + 0.05
            )

        # Soil pathogen fungi can contaminate water
        if self.soil.state.pathogenic_fungi_risk > 0.5:
            self.water.state.total_species_in_water = min(
                300, self.water.state.total_species_in_water + 2
            )

        # Compound crisis detection
        gut_crisis = self.gut.state.dysbiosis_risk > 0.5
        surface_crisis = self.surface.state.pathogen_risk > 0.5
        soil_crisis = self.soil.state.crop_yield_modifier < 0.6
        water_crisis = not self.water.state.legionella_safe()

        crisis_count = sum([gut_crisis, surface_crisis, soil_crisis, water_crisis])
        prev_cascade = getattr(self, "_cascade_tier", 0)
        cur_cascade = 2 if crisis_count >= 3 else (1 if crisis_count >= 2 else 0)
        if cur_cascade > prev_cascade:
            self._cascade_tier = cur_cascade
            if cur_cascade == 2:
                events.append({
                    "year": mission_year, "severity": "EMERGENCY",
                    "message": f"Microbiome cascade failure: {crisis_count}/4 compartments "
                               "in crisis — ship ecosystem integrity threatened",
                    "subsystem": "microbiome_cross_compartment",
                })
            else:
                events.append({
                    "year": mission_year, "severity": "CRITICAL",
                    "message": f"Multi-compartment microbiome stress: {crisis_count}/4 "
                               "compartments degraded — intervention required",
                    "subsystem": "microbiome_cross_compartment",
                })
        elif cur_cascade < prev_cascade:
            self._cascade_tier = cur_cascade

        return events

    def get_report(self) -> dict[str, Any]:
        """Return comprehensive microbiome status report."""
        g = self.gut.state
        sf = self.surface.state
        so = self.soil.state
        w = self.water.state

        return {
            "mission_year": self.mission_year,
            "crew_size": self.crew_size,

            # Key tracked metrics
            "gut_diversity_index": g.shannon_diversity,
            "resistance_genes": {
                drug: f"{prev:.1%}" for drug, prev in sf.amr_prevalence.items()
            },
            "pathogen_risk": sf.pathogen_risk,
            "soil_health": so.crop_yield_modifier,

            # Gut details
            "gut": {
                "species_count": g.species_count,
                "shannon_diversity": round(g.shannon_diversity, 3),
                "dysbiosis_risk": round(g.dysbiosis_risk, 3),
                "hgt_rate": g.hgt_rate,
                "diet_diversity": round(g.diet_diversity_index, 3),
                "phylum_balance": {
                    "Bacteroidetes": round(g.bacteroidetes_fraction, 3),
                    "Firmicutes": round(g.firmicutes_fraction, 3),
                    "Proteobacteria": round(g.proteobacteria_fraction, 3),
                },
                "cumulative_hgt_events": g.cumulative_hgt_events,
                "novel_gene_combinations": g.novel_gene_combinations,
            },

            # Surface details
            "surface": {
                "colonization": {
                    m: round(c, 3) for m, c in sf.surface_colonization.items()
                },
                "amr_prevalence": {
                    d: round(p, 4) for d, p in sf.amr_prevalence.items()
                },
                "multi_drug_resistant": round(sf.multi_drug_resistant_fraction, 3),
                "virulence_acquisitions": sf.virulence_island_acquisitions,
                "pathogen_risk": round(sf.pathogen_risk, 3),
            },

            # Soil details
            "soil": {
                "mycorrhizal_health": round(so.mycorrhizal_health, 3),
                "mycorrhizal_species": so.mycorrhizal_species_count,
                "nitrogen_fixers_cfu_g": so.nitrogen_fixers_cfu_per_g,
                "organic_matter_pct": round(so.soil_organic_matter_pct, 2),
                "decomposer_activity": round(so.decomposer_activity, 3),
                "crop_yield_modifier": round(so.crop_yield_modifier, 3),
                "pathogenic_fungi_risk": round(so.pathogenic_fungi_risk, 3),
            },

            # Water details
            "water": {
                "legionella_cfu_l": round(w.legionella_concentration_cfu_l, 1),
                "legionella_safe": w.legionella_safe(),
                "chloramine_resistant": round(w.chloramine_resistant_fraction, 4),
                "disinfection_efficacy": round(w.disinfection_efficacy, 3),
                "community_diversity": round(w.biofilm_community_diversity, 3),
                "species_count": w.total_species_in_water,
            },

            "history_length": len(self._yearly_history),
        }
