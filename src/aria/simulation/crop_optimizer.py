"""Crop Rotation Optimizer — Genetic Algorithm for Generation Ship Agriculture.

Even with starch/protein synthesis, the ship maintains a ~2000 m² hydroponics
bay for fresh produce, morale, oxygen generation, and diet variety.
The crop optimizer solves: which crops, in what rotation, to maximize
nutrition while respecting constraints (light, water, space, crew preference).

NOTE ON FOOD PRODUCTION CAPACITY:
  The 2000 m² hydroponics bay covers ~5% of crew caloric need (fresh produce,
  vitamins, morale). The remaining 95% comes from:
    1. Starch synthesizer (Cai 2021): CO2 + H2O → starch, ~300 kg/day
    2. Protein synthesis (Solein): CO2 + H2 → protein, ~100 kg/day
    3. Habitat ring agriculture zone: decks 6-7 provide ~250,000 m²
       (available once ring is spun up, covers full crew need)

CONSTRAINTS (hull-based hydroponics only):
  - Limited grow area: 2000 m² (500 m² per growth chamber × 4 chambers)
  - LED power budget: 200 kW total (50 kW per chamber)
  - Water budget: 500 L/day for irrigation (recycled)
  - CO2 available: excess from crew respiration (~1060 ppm EDEN ISS measured)
  - Must provide: vitamins A/C/K/folate, fiber, variety (morale)
  - Crop cycle: 30-120 days depending on species

LED POWER VALIDATION (EDEN ISS 2020 data):
  EDEN ISS PAR sensor 2 recorded p95 = 423 umol/m2/s during active lighting,
  which converts to ~92 W/m2 via the standard 4.6 umol/W factor. Our crop
  light requirements (50-130 W/m2) are consistent with this real measurement.

CROP DATABASE (real ISS/EDEN ISS/Veggie data):
  - Lettuce: 28-day cycle, 0.2 kg/m², low light, Veggie ISS 2014
  - Tomato: 80-day cycle, 4.0 kg/m², medium light, EDEN ISS 2018
  - Wheat: 90-day cycle, 0.3 kg/m² grain, high light, USU-Apogee ISS
  - Soybean: 90-day cycle, 0.15 kg/m² bean, medium light
  - Potato: 105-day cycle, 3.0 kg/m², medium light, NASA BPS 2016
  - Radish: 25-day cycle, 0.8 kg/m², low light, ISS APH 2020
  - Pepper: 90-day cycle, 2.0 kg/m², medium-high light
  - Strawberry: 60-day cycle, 0.5 kg/m², medium light
  - Spinach: 35-day cycle, 0.3 kg/m², low light
  - Rice: 120-day cycle, 0.4 kg/m² grain, high light

GENETIC ALGORITHM:
  Chromosome = allocation of area to each crop per growth cycle
  Fitness = weighted sum of: nutrition coverage, calorie yield,
            diversity score, water efficiency, morale bonus
  Reference: Zeidler et al. "Greenhouse Module for Space System" (2017)
             Wheeler (2017) "Agriculture for Space" in NASA TM-2017-219642
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

import structlog

from aria.simulation.eden_iss_baselines import (
    EDEN_ISS_BASELINES,
    get_eden_iss_par_w_per_m2,
)

logger = structlog.get_logger()

# EDEN ISS PAR validation: real greenhouse runs at ~92 W/m2 LED equivalent
# during active lighting (p95 of PAR = 423 umol/m2/s, converted via 4.6 umol/W).
# This validates our crop light_W_per_m2 assumptions below.
_EDEN_ISS_LED_W_M2 = get_eden_iss_par_w_per_m2()  # ~92 W/m2


@dataclass
class CropSpecies:
    """A crop species with real growth parameters."""
    name: str
    cycle_days: int            # Seed to harvest
    yield_kg_per_m2: float     # Fresh weight per cycle
    water_L_per_m2_day: float  # Irrigation requirement
    light_W_per_m2: float      # LED power requirement (PAR)
    calories_per_kg: float     # kcal per kg fresh weight
    protein_g_per_kg: float    # Grams protein per kg
    vitamin_a_iu_per_kg: float # IU vitamin A per kg
    vitamin_c_mg_per_kg: float # mg vitamin C per kg
    fiber_g_per_kg: float      # Grams dietary fiber per kg
    morale_score: float        # 0-1 how much crew likes it
    source: str                # Reference


# Real crop data from ISS Veggie, EDEN ISS, NASA BPS experiments
CROP_DATABASE: list[CropSpecies] = [
    CropSpecies("Lettuce", 28, 0.20, 0.3, 60, 150, 13, 7400, 40, 13, 0.6,
                "ISS Veggie VEG-01 (2014), Massa et al."),
    CropSpecies("Tomato", 80, 4.00, 0.8, 100, 180, 9, 8300, 140, 12, 0.9,
                "EDEN ISS Antarctic (2018), Zeidler et al."),
    CropSpecies("Wheat", 90, 0.30, 0.5, 120, 3390, 133, 0, 0, 126, 0.4,
                "USU-Apogee dwarf wheat, Bugbee (2004)"),
    CropSpecies("Soybean", 90, 0.15, 0.4, 100, 1460, 360, 0, 60, 90, 0.3,
                "Wheeler et al. (1996) NASA BPC"),
    CropSpecies("Potato", 105, 3.00, 0.6, 90, 770, 20, 2, 200, 22, 0.7,
                "NASA BPS CIS-Lunar (2016)"),
    CropSpecies("Radish", 25, 0.80, 0.3, 50, 160, 7, 0, 150, 16, 0.5,
                "ISS APH (2020), Monje et al."),
    CropSpecies("Pepper", 90, 2.00, 0.7, 110, 200, 9, 3700, 1270, 17, 0.8,
                "EDEN ISS (2018), chili peppers"),
    CropSpecies("Strawberry", 60, 0.50, 0.5, 80, 320, 7, 10, 590, 20, 0.95,
                "NASA KSC growth studies"),
    CropSpecies("Spinach", 35, 0.30, 0.4, 60, 230, 29, 94700, 280, 22, 0.5,
                "ISS Veggie VEG-05 (2020)"),
    CropSpecies("Rice", 120, 0.40, 0.7, 130, 3600, 75, 0, 0, 40, 0.3,
                "Wheeler (2017) NASA TM"),
]

# Daily human requirements (NASA STD-3001, Vol. 2)
DAILY_REQUIREMENTS = {
    "calories_kcal": 2500,
    "protein_g": 56,
    "vitamin_a_iu": 3000,
    "vitamin_c_mg": 90,
    "fiber_g": 25,
}


@dataclass
class GrowthChamber:
    """A single hydroponic growth chamber."""
    area_m2: float = 500.0            # ESTIMATE — 0.5 m²/person × 1000 crew (Wheeler 2003 NASA TM-2003-212349)
    power_budget_w: float = 50_000.0  # ESTIMATE — 100 W/m² LED grow lights × 500 m² (Bugbee 1994 HortScience 29 1441)
    water_budget_L_day: float = 125.0  # ESTIMATE — 0.25 L/m²/day drip irrigation (Stoner 1994 NASA TM)


@dataclass
class CropAllocation:
    """How much area to give each crop — one chromosome in the GA."""
    # area_fractions[i] = fraction of total area for crop i (sums to 1.0)
    area_fractions: list[float] = field(default_factory=list)
    fitness: float = 0.0


@dataclass
class OptimizerState:
    """State of the crop optimizer."""
    best_allocation: CropAllocation = field(default_factory=CropAllocation)
    generation: int = 0
    best_fitness: float = 0.0
    fitness_history: list[float] = field(default_factory=list)
    daily_yield_kg: float = 0.0
    nutrition_coverage: dict[str, float] = field(default_factory=dict)


class CropRotationOptimizer:
    """Genetic algorithm optimizer for crop allocation.

    Finds the optimal allocation of grow area to maximize nutrition,
    diversity, and morale for the ship's crew.
    """

    def __init__(
        self,
        crew_size: int = 1000,            # ESTIMATE — 1000-person crew (O'Neill 1977 Island 1 baseline)
        total_area_m2: float = 2000.0,    # ESTIMATE — 2 m²/person for 1000 crew (Wheeler 2003)
        total_power_w: float = 200_000.0,  # ESTIMATE — 200 kW grow lights for 2000 m² (Bugbee 1994)
        total_water_L_day: float = 500.0,  # ESTIMATE — 0.25 L/m²/day × 2000 m² (Stoner 1994)
        population_size: int = 100,        # ESTIMATE — GA population size
        seed: int | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        self._crew = crew_size
        self._area = total_area_m2
        self._power = total_power_w
        self._water = total_water_L_day
        self._pop_size = population_size
        self._crops = CROP_DATABASE
        self._n_crops = len(self._crops)
        self.state = OptimizerState()

    def _random_allocation(self) -> CropAllocation:
        """Generate a random crop allocation (chromosome)."""
        raw = [self._rng.random() for _ in range(self._n_crops)]
        total = sum(raw)
        fracs = [r / total for r in raw]
        return CropAllocation(area_fractions=fracs)

    def _evaluate_fitness(self, alloc: CropAllocation) -> float:
        """Evaluate how good a crop allocation is.

        Fitness = nutrition_score × diversity_score × morale_score
        Penalized if constraints (power, water) are violated.
        """
        fracs = alloc.area_fractions
        total_power_used = 0.0
        total_water_used = 0.0
        total_calories_day = 0.0
        total_protein_day = 0.0
        total_vita_day = 0.0
        total_vitc_day = 0.0
        total_fiber_day = 0.0
        total_morale = 0.0
        active_crops = 0

        for i, crop in enumerate(self._crops):
            area = fracs[i] * self._area
            if area < 1.0:  # Less than 1 m² — not worth growing
                continue

            active_crops += 1
            # Power and water
            total_power_used += area * crop.light_W_per_m2
            total_water_used += area * crop.water_L_per_m2_day

            # Daily yield: area × yield_per_cycle / cycle_days
            daily_yield_kg = area * crop.yield_kg_per_m2 / crop.cycle_days
            total_calories_day += daily_yield_kg * crop.calories_per_kg
            total_protein_day += daily_yield_kg * crop.protein_g_per_kg
            total_vita_day += daily_yield_kg * crop.vitamin_a_iu_per_kg
            total_vitc_day += daily_yield_kg * crop.vitamin_c_mg_per_kg
            total_fiber_day += daily_yield_kg * crop.fiber_g_per_kg
            total_morale += fracs[i] * crop.morale_score

        # Constraint penalties
        power_penalty = 1.0
        if total_power_used > self._power:
            power_penalty = self._power / total_power_used

        water_penalty = 1.0
        if total_water_used > self._water:
            water_penalty = self._water / total_water_used

        # Nutrition coverage (fraction of crew needs met)
        crew_need = self._crew
        cal_coverage = min(1.0, total_calories_day / (DAILY_REQUIREMENTS["calories_kcal"] * crew_need))
        prot_coverage = min(1.0, total_protein_day / (DAILY_REQUIREMENTS["protein_g"] * crew_need))
        vita_coverage = min(1.0, total_vita_day / (DAILY_REQUIREMENTS["vitamin_a_iu"] * crew_need))
        vitc_coverage = min(1.0, total_vitc_day / (DAILY_REQUIREMENTS["vitamin_c_mg"] * crew_need))
        fiber_coverage = min(1.0, total_fiber_day / (DAILY_REQUIREMENTS["fiber_g"] * crew_need))

        # Note: hydroponics supplements the starch synthesizer, not sole food source.
        # Target is 10-20% of calories from fresh produce, but 100% of vitamins.
        nutrition_score = (
            0.1 * cal_coverage +    # Calories mostly from synthesizer
            0.15 * prot_coverage +
            0.25 * vita_coverage +   # Vitamins are the main goal
            0.25 * vitc_coverage +
            0.15 * fiber_coverage +
            0.1 * total_morale
        )

        # Diversity bonus: Shannon index of allocation
        diversity = 0.0
        for f in fracs:
            if f > 0.01:
                diversity -= f * math.log(f)
        max_diversity = math.log(self._n_crops)
        diversity_score = diversity / max_diversity if max_diversity > 0 else 0

        fitness = nutrition_score * (0.7 + 0.3 * diversity_score) * power_penalty * water_penalty

        alloc.fitness = fitness
        return fitness

    def _crossover(self, parent1: CropAllocation, parent2: CropAllocation) -> CropAllocation:
        """Single-point crossover."""
        point = self._rng.randint(1, self._n_crops - 1)
        child_fracs = parent1.area_fractions[:point] + parent2.area_fractions[point:]
        # Renormalize
        total = sum(child_fracs)
        child_fracs = [f / total for f in child_fracs]
        return CropAllocation(area_fractions=child_fracs)

    def _mutate(self, alloc: CropAllocation, rate: float = 0.1) -> CropAllocation:
        """Gaussian mutation on area fractions."""
        fracs = list(alloc.area_fractions)
        for i in range(len(fracs)):
            if self._rng.random() < rate:
                fracs[i] = max(0.0, fracs[i] + self._rng.gauss(0, 0.05))
        total = sum(fracs)
        if total > 0:
            fracs = [f / total for f in fracs]
        else:
            fracs = [1.0 / len(fracs)] * len(fracs)
        return CropAllocation(area_fractions=fracs)

    def _tournament_select(self, population: list[CropAllocation], k: int = 3) -> CropAllocation:
        """Tournament selection."""
        candidates = self._rng.sample(population, min(k, len(population)))
        return max(candidates, key=lambda a: a.fitness)

    def optimize(self, generations: int = 200) -> CropAllocation:
        """Run the genetic algorithm."""
        # Initialize population
        population = [self._random_allocation() for _ in range(self._pop_size)]
        for ind in population:
            self._evaluate_fitness(ind)

        for gen in range(generations):
            # Elitism: keep top 10%
            population.sort(key=lambda a: a.fitness, reverse=True)
            elite_n = max(2, self._pop_size // 10)
            new_pop = population[:elite_n]

            # Breed the rest
            while len(new_pop) < self._pop_size:
                p1 = self._tournament_select(population)
                p2 = self._tournament_select(population)
                child = self._crossover(p1, p2)
                child = self._mutate(child)
                self._evaluate_fitness(child)
                new_pop.append(child)

            population = new_pop
            best = max(population, key=lambda a: a.fitness)
            self.state.fitness_history.append(best.fitness)

        # Final best
        best = max(population, key=lambda a: a.fitness)
        self.state.best_allocation = best
        self.state.best_fitness = best.fitness
        self.state.generation = generations

        # Compute daily yield
        total_yield = 0.0
        nutrition = {}
        for i, crop in enumerate(self._crops):
            area = best.area_fractions[i] * self._area
            daily = area * crop.yield_kg_per_m2 / crop.cycle_days
            total_yield += daily

        self.state.daily_yield_kg = total_yield
        self.state.nutrition_coverage = self._compute_nutrition(best)

        return best

    def _compute_nutrition(self, alloc: CropAllocation) -> dict[str, float]:
        """Compute nutrition coverage from an allocation."""
        totals = {"calories": 0, "protein": 0, "vitamin_a": 0, "vitamin_c": 0, "fiber": 0}
        for i, crop in enumerate(self._crops):
            area = alloc.area_fractions[i] * self._area
            daily = area * crop.yield_kg_per_m2 / crop.cycle_days
            totals["calories"] += daily * crop.calories_per_kg
            totals["protein"] += daily * crop.protein_g_per_kg
            totals["vitamin_a"] += daily * crop.vitamin_a_iu_per_kg
            totals["vitamin_c"] += daily * crop.vitamin_c_mg_per_kg
            totals["fiber"] += daily * crop.fiber_g_per_kg

        crew = self._crew
        return {
            "calories_pct": min(100, totals["calories"] / (DAILY_REQUIREMENTS["calories_kcal"] * crew) * 100),
            "protein_pct": min(100, totals["protein"] / (DAILY_REQUIREMENTS["protein_g"] * crew) * 100),
            "vitamin_a_pct": min(100, totals["vitamin_a"] / (DAILY_REQUIREMENTS["vitamin_a_iu"] * crew) * 100),
            "vitamin_c_pct": min(100, totals["vitamin_c"] / (DAILY_REQUIREMENTS["vitamin_c_mg"] * crew) * 100),
            "fiber_pct": min(100, totals["fiber"] / (DAILY_REQUIREMENTS["fiber_g"] * crew) * 100),
        }

    def get_allocation_report(self) -> dict[str, Any]:
        """Human-readable report of the optimized allocation."""
        alloc = self.state.best_allocation
        crops_report = []
        for i, crop in enumerate(self._crops):
            area = alloc.area_fractions[i] * self._area
            if area < 1.0:
                continue
            daily = area * crop.yield_kg_per_m2 / crop.cycle_days
            crops_report.append({
                "crop": crop.name,
                "area_m2": round(area, 1),
                "area_pct": round(alloc.area_fractions[i] * 100, 1),
                "daily_yield_kg": round(daily, 2),
                "cycle_days": crop.cycle_days,
                "source": crop.source,
            })
        crops_report.sort(key=lambda c: c["area_m2"], reverse=True)

        return {
            "fitness": self.state.best_fitness,
            "generations": self.state.generation,
            "total_area_m2": self._area,
            "crew_size": self._crew,
            "daily_yield_kg": round(self.state.daily_yield_kg, 1),
            "nutrition_coverage": self.state.nutrition_coverage,
            "crop_allocation": crops_report,
        }

    def validate_light_against_eden_iss(self) -> dict[str, Any]:
        """Validate crop LED power assumptions against real EDEN ISS PAR data.

        Returns a report showing which crops are within, below, or above
        the measured EDEN ISS active-lighting power level (~92 W/m2).
        """
        eden_w = _EDEN_ISS_LED_W_M2
        eden_par = EDEN_ISS_BASELINES.get("par_umol")
        report: dict[str, Any] = {
            "eden_iss_par_p95_umol": eden_par.p95 if eden_par else None,
            "eden_iss_par_mean_umol": eden_par.mean if eden_par else None,
            "eden_iss_led_equivalent_w_m2": eden_w,
            "crops": [],
        }
        for crop in self._crops:
            status = "within_range"
            if crop.light_W_per_m2 > eden_w * 1.5:
                status = "above_eden_iss"
            elif crop.light_W_per_m2 < eden_w * 0.3:
                status = "below_eden_iss"
            report["crops"].append({
                "name": crop.name,
                "light_W_per_m2": crop.light_W_per_m2,
                "vs_eden_iss_pct": round(crop.light_W_per_m2 / eden_w * 100, 1),
                "status": status,
            })
        return report

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        """Simulate one year of crop production.

        Re-optimizes every 10 years to adapt to changing conditions.
        """
        events: list[dict[str, Any]] = []

        # Optimize on first call and every 10 years
        if self.state.generation == 0 or int(mission_year) % 10 == 0:
            self.optimize(generations=100)
            events.append({
                "year": mission_year,
                "severity": "NOMINAL",
                "message": f"Crop rotation optimized: {self.state.daily_yield_kg:.1f} kg/day "
                           f"from {self._area:.0f} m² (fitness {self.state.best_fitness:.3f})",
                "subsystem": "agriculture",
            })

        # Seasonal variation: yield fluctuates ±15% due to growth cycle timing
        seasonal_factor = 1.0 + 0.15 * math.sin(2 * math.pi * mission_year)

        # Equipment degradation: grow lights lose ~2% per year
        light_degradation = max(0.5, 1.0 - 0.02 * mission_year)
        effective_yield = self.state.daily_yield_kg * seasonal_factor * light_degradation

        # Check for critical vitamin deficiency
        nutrition = self.state.nutrition_coverage
        for nutrient, pct in nutrition.items():
            if pct < 20:
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": f"Critical {nutrient} coverage: only {pct:.0f}% of crew needs. "
                               "Supplement from stored vitamins.",
                    "subsystem": "agriculture",
                })

        # Light replacement needed after significant degradation
        if light_degradation < 0.7:
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": f"Grow light output at {light_degradation:.0%}. "
                           "LED replacement recommended.",
                "subsystem": "agriculture",
            })

        return events
