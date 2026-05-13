"""Resource Mining Mission Simulation — interstellar mining from real exoplanet data.

Loads NASA Exoplanet Archive data and simulates resource extraction missions
to carbon-rich worlds (diamond mining), icy bodies, metal-rich planets, and
rare-earth super-Earths.

Key scenario: 55 Cancri e — a carbon-rich super-Earth 12.6 ly away whose
mantle may contain a substantial diamond layer. At 0.1c the one-way trip
takes ~126 years, requiring generation-ship technology.

Subsystems:
  1. ResourceScanner  — parse exoplanet CSV, classify by resource type, score
  2. MiningOpsModel   — orbital insertion, surface ops, extraction, processing
  3. MissionPlanner   — multi-stop route optimization with fuel/cargo trade-offs
  4. MiningMission    — full simulation combining travel + mining + return
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# ────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ────────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
EXOPLANET_CSV = DATA_DIR / "raw" / "exoplanets" / "nearby_confirmed_planets.csv"

# NIST CODATA 2018: c = 299 792.458 km/s (exact definition)
SPEED_OF_LIGHT_KM_S = 299_792.458  # NIST CODATA 2018 (exact definition)
# IAU 2012 Resolution B2: 1 light-year = 9.4607304725808 × 10¹² km
LY_IN_KM = 9.461e12  # IAU 2012 Resolution B2

# Ship defaults
DEFAULT_VELOCITY_C = 0.10       # cruise at 10% light speed
# Ship cargo/fuel: O'Neill (1977) High Frontier mass budget scaled to interstellar ship
DEFAULT_CARGO_CAPACITY_T = 5000  # ESTIMATE — O'Neill 1977 scaled cargo budget
DEFAULT_FUEL_CAPACITY_T = 20000  # ESTIMATE — Zubrin 1991 interstellar fuel budget
DEFAULT_CREW_SIZE = 12           # ESTIMATE — minimum functional crew for mining mission
REACTOR_POWER_MW = 500          # ESTIMATE — 5× ISS power (NASA SSP 30482 scaling)

# Mining yields (metric tons per Earth-year of operation)
# 55 Cancri e diamond mantle: Madhusudhan 2012 ApJ 756 L15 (up to 1/3 carbon by mass)
DIAMOND_YIELD_T_PER_YEAR = 450      # ESTIMATE — Madhusudhan 2012 ApJ 756 L15 carbon fraction
WATER_ICE_YIELD_T_PER_YEAR = 2000   # ESTIMATE — icy world surface mining rate
METAL_YIELD_T_PER_YEAR = 800        # ESTIMATE — asteroid-class iron/nickel extraction
RARE_EARTH_YIELD_T_PER_YEAR = 120   # ESTIMATE — rare-earth concentration at 0.015% crust

# Value per metric ton (arbitrary economic units, 1 AU = ~$1B USD equivalent)
VALUE_PER_TON = {
    "DIAMOND": 50.0,
    "WATER_ICE": 0.5,
    "METALS": 5.0,
    "RARE_EARTH": 200.0,
}


# ────────────────────────────────────────────────────────────────────
#  RESOURCE TYPES
# ────────────────────────────────────────────────────────────────────

class ResourceType(Enum):
    """Classification of extractable resources."""
    DIAMOND = "DIAMOND"          # Carbon-rich → diamond extraction
    WATER_ICE = "WATER_ICE"      # Low-temp, low-density icy worlds
    METALS = "METALS"            # High-density iron/nickel/platinum
    RARE_EARTH = "RARE_EARTH"    # Rocky super-Earths, tectonic activity
    UNKNOWN = "UNKNOWN"          # Insufficient data


# ────────────────────────────────────────────────────────────────────
#  EXOPLANET TARGET
# ────────────────────────────────────────────────────────────────────

@dataclass
class MiningTarget:
    """A confirmed exoplanet evaluated as a mining target."""
    name: str
    host_star: str
    distance_pc: float           # parsecs from Sol
    radius_earth: float          # planet radius in Earth radii
    mass_earth: float            # planet mass in Earth masses
    orbital_period_days: float
    eq_temp_k: float | None      # equilibrium temperature (K), may be None
    spectral_type: str
    stellar_teff: float          # host star effective temperature (K)
    stellar_mass: float          # host star mass in solar masses
    disc_year: int

    # Derived
    resource_type: ResourceType = ResourceType.UNKNOWN
    mining_score: float = 0.0     # composite value * accessibility
    density_earth: float = 0.0    # bulk density relative to Earth
    delta_v_km_s: float = 0.0     # orbital insertion Δv (vis-viva, km/s)
    travel_time_years: float = 0.0  # one-way at default velocity

    @property
    def distance_ly(self) -> float:
        return self.distance_pc * 3.26156

    def __post_init__(self) -> None:
        if self.radius_earth > 0 and self.mass_earth > 0:
            # density ~ mass / radius^3 (relative to Earth)
            self.density_earth = self.mass_earth / (self.radius_earth ** 3)
        self.travel_time_years = self.distance_ly / DEFAULT_VELOCITY_C
        # Rough delta-v: escape velocity of target planet (km/s)
        # v_esc = 11.2 * sqrt(M/R) for Earth-relative units
        if self.radius_earth > 0 and self.mass_earth > 0:
            self.delta_v_km_s = 11.2 * math.sqrt(self.mass_earth / self.radius_earth)


# ────────────────────────────────────────────────────────────────────
#  RESOURCE SCANNER
# ────────────────────────────────────────────────────────────────────

class ResourceScanner:
    """Parse real NASA exoplanet data and classify mining targets.

    Classification heuristics (applied to confirmed planets):
      DIAMOND/CARBON:  high density (>1.5 Earth), high temp (>1000 K),
                       OR host star carbon-enriched (spectral G/K + known
                       carbon-rich like 55 Cnc system)
      WATER_ICE:       low temp (<300 K) and low density (<0.8 Earth)
      METALS:          very high density (>2.0 Earth) and small radius (<4 Re)
      RARE_EARTH:      rocky super-Earth (1-2 Re, 1-10 Me) with moderate temp
    """

    # Known carbon-rich systems (from literature)
    CARBON_RICH_HOSTS = {"55 Cnc", "WASP-12", "HD 108874", "HD 196050"}

    def __init__(self, csv_path: Path | str | None = None) -> None:
        self._csv_path = Path(csv_path) if csv_path else EXOPLANET_CSV
        self._targets: list[MiningTarget] = []

    @property
    def targets(self) -> list[MiningTarget]:
        return list(self._targets)

    def load(self) -> int:
        """Load and parse the exoplanet CSV. Returns number of targets loaded."""
        self._targets.clear()

        if not self._csv_path.exists():
            logger.warning("mining.csv_not_found", path=str(self._csv_path))
            return 0

        with open(self._csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    target = self._parse_row(row)
                    if target is not None:
                        self._targets.append(target)
                except Exception as exc:
                    logger.debug("mining.parse_skip", name=row.get("pl_name"), err=str(exc))

        # Classify and score all targets
        for t in self._targets:
            t.resource_type = self._classify(t)
            t.mining_score = self._score(t)

        logger.info("mining.scanner.loaded", total=len(self._targets))
        return len(self._targets)

    def _parse_row(self, row: dict[str, str]) -> MiningTarget | None:
        """Parse one CSV row into a MiningTarget. Returns None if essential data missing."""
        name = row.get("pl_name", "").strip().strip('"')
        host = row.get("hostname", "").strip().strip('"')
        if not name:
            return None

        def safe_float(key: str) -> float:
            val = row.get(key, "").strip()
            if not val:
                return 0.0
            return float(val)

        dist_pc = safe_float("sy_dist")
        radius = safe_float("pl_rade")
        mass = safe_float("pl_bmasse")

        # Skip entries with no distance or no radius+mass
        if dist_pc <= 0 or (radius <= 0 and mass <= 0):
            return None

        eq_temp_raw = row.get("pl_eqt", "").strip()
        eq_temp = float(eq_temp_raw) if eq_temp_raw else None

        return MiningTarget(
            name=name,
            host_star=host,
            distance_pc=dist_pc,
            radius_earth=radius if radius > 0 else 1.0,
            mass_earth=mass if mass > 0 else 1.0,
            orbital_period_days=safe_float("pl_orbper"),
            eq_temp_k=eq_temp,
            spectral_type=row.get("st_spectype", "").strip().strip('"'),
            stellar_teff=safe_float("st_teff"),
            stellar_mass=safe_float("st_mass"),
            disc_year=int(safe_float("disc_year")) if safe_float("disc_year") else 0,
        )

    def _classify(self, t: MiningTarget) -> ResourceType:
        """Classify a planet by likely extractable resource."""
        # Carbon-rich / diamond worlds
        if t.host_star in self.CARBON_RICH_HOSTS:
            if t.mass_earth > 2.0 and t.radius_earth < 5.0:
                return ResourceType.DIAMOND

        if (t.density_earth > 1.5 and t.eq_temp_k is not None
                and t.eq_temp_k > 1000 and t.radius_earth < 5.0):
            return ResourceType.DIAMOND

        # Water ice worlds
        if t.eq_temp_k is not None and t.eq_temp_k < 300 and t.density_earth < 0.8:
            return ResourceType.WATER_ICE

        # Metal-rich worlds
        if t.density_earth > 2.0 and t.radius_earth < 4.0:
            return ResourceType.METALS

        # Rare-earth super-Earths
        if 1.0 <= t.radius_earth <= 2.5 and 1.0 <= t.mass_earth <= 10.0:
            if t.eq_temp_k is None or 200 < t.eq_temp_k < 800:
                return ResourceType.RARE_EARTH

        return ResourceType.UNKNOWN

    def _score(self, t: MiningTarget) -> float:
        """Score = resource_value * accessibility.

        accessibility decreases with distance and delta-v.
        """
        if t.resource_type == ResourceType.UNKNOWN:
            return 0.0

        base_value = VALUE_PER_TON.get(t.resource_type.value, 1.0)

        # Mass-based value multiplier — ESTIMATE: larger planet = more resource mass
        mass_factor = min(t.mass_earth / 5.0, 3.0)  # ESTIMATE: capped at 3× for 15+ Me

        # Distance penalty — ESTIMATE: sqrt decay for accessibility cost
        dist_ly = t.distance_ly
        if dist_ly <= 0:
            return 0.0
        distance_penalty = 1.0 / (1.0 + math.sqrt(dist_ly))  # ESTIMATE: √dist decay

        # Delta-v penalty — ESTIMATE: 20 km/s normalizer (comparable to Earth escape velocity)
        dv_penalty = 1.0 / (1.0 + t.delta_v_km_s / 20.0)  # ESTIMATE: 20 km/s = Earth escape ref

        return base_value * mass_factor * distance_penalty * dv_penalty

    def get_by_type(self, resource_type: ResourceType) -> list[MiningTarget]:
        """Return targets of a specific resource type, sorted by score descending."""
        return sorted(
            [t for t in self._targets if t.resource_type == resource_type],
            key=lambda t: t.mining_score,
            reverse=True,
        )

    def get_top_targets(self, n: int = 20) -> list[MiningTarget]:
        """Return top N targets across all types by mining score."""
        scored = [t for t in self._targets if t.mining_score > 0]
        return sorted(scored, key=lambda t: t.mining_score, reverse=True)[:n]

    def get_nearby(self, max_distance_ly: float = 20.0) -> list[MiningTarget]:
        """Return all classified targets within max_distance_ly."""
        return sorted(
            [t for t in self._targets
             if t.distance_ly <= max_distance_ly and t.resource_type != ResourceType.UNKNOWN],
            key=lambda t: t.distance_ly,
        )

    def find_target(self, name: str) -> MiningTarget | None:
        """Find a target by name (case-insensitive partial match)."""
        name_lower = name.lower().replace("_", " ")
        for t in self._targets:
            if name_lower in t.name.lower().replace("_", " "):
                return t
        return None


# ────────────────────────────────────────────────────────────────────
#  MINING OPERATIONS MODEL
# ────────────────────────────────────────────────────────────────────

class MiningMethod(Enum):
    ORBITAL_CAPTURE = "orbital_capture"       # Scoop atmosphere from orbit
    ROBOTIC_SURFACE = "robotic_surface"       # Heat-resistant robots on surface
    SUBSURFACE_DRILL = "subsurface_drill"     # Drill to diamond layer
    ICE_HARVESTING = "ice_harvesting"         # Surface/subsurface ice extraction
    STRIP_MINING = "strip_mining"             # Open-pit for metals/rare earth


@dataclass
class MiningOperation:
    """State of a single mining operation at one target."""
    target: MiningTarget
    method: MiningMethod
    year_started: float = 0.0
    duration_years: float = 0.0
    tons_extracted: float = 0.0
    tons_processed: float = 0.0    # refined product
    fuel_consumed_t: float = 0.0
    power_required_mw: float = 0.0
    crew_assigned: int = 0
    robots_deployed: int = 0
    status: str = "PLANNED"        # PLANNED, IN_PROGRESS, COMPLETE, ABORTED

    @property
    def value(self) -> float:
        return self.tons_processed * VALUE_PER_TON.get(
            self.target.resource_type.value, 1.0
        )


@dataclass
class MiningOpsConfig:
    """Configuration for mining operations."""
    reactor_power_mw: float = REACTOR_POWER_MW
    crew_size: int = DEFAULT_CREW_SIZE
    cargo_capacity_t: float = DEFAULT_CARGO_CAPACITY_T
    processing_efficiency: float = 0.65   # ESTIMATE — fraction raw → refined (analogous to ISS WRS 90%, Sung & Tai 1997 HPHT 35%)
    robot_count: int = 24                 # heat-resistant mining robots


class MiningOpsModel:
    """Simulates resource extraction at a planetary target.

    Models:
      - Orbital insertion fuel cost
      - Mining method selection based on planet conditions
      - Extraction rates adjusted for temperature, gravity, composition
      - Processing pipeline: raw ore → refined material → cargo
      - Power and crew/robot requirements
    """

    def __init__(self, config: MiningOpsConfig | None = None, seed: int = 42) -> None:
        self._config = config or MiningOpsConfig()
        self._rng = random.Random(seed)
        self._operations: list[MiningOperation] = []

    @property
    def operations(self) -> list[MiningOperation]:
        return list(self._operations)

    def select_method(self, target: MiningTarget) -> MiningMethod:
        """Choose the optimal mining method for a target."""
        rt = target.resource_type

        if rt == ResourceType.DIAMOND:
            # Extreme heat worlds → orbital capture or robotic surface mining
            if target.eq_temp_k is not None and target.eq_temp_k > 1500:
                return MiningMethod.ORBITAL_CAPTURE
            return MiningMethod.SUBSURFACE_DRILL

        if rt == ResourceType.WATER_ICE:
            return MiningMethod.ICE_HARVESTING

        if rt == ResourceType.METALS:
            return MiningMethod.STRIP_MINING

        if rt == ResourceType.RARE_EARTH:
            return MiningMethod.SUBSURFACE_DRILL

        return MiningMethod.ROBOTIC_SURFACE

    def orbital_insertion_fuel(self, target: MiningTarget, ship_mass_t: float) -> float:
        """Estimate fuel needed to enter orbit around the target planet (metric tons).

        Uses Tsiolkovsky rocket equation: delta_m = m * (1 - exp(-dv / ve))
        Exhaust velocity ~ 30 km/s for fusion drive.
        """
        # Fusion drive Isp ~3000 s → ve = Isp * g0 = 3000 * 9.81e-3 km/s ≈ 30 km/s
        # Reference: Frisbee 2003 AIAA-2003-4676 (inertial confinement fusion drive)
        ve_km_s = 30.0  # Frisbee 2003 AIAA-2003-4676: ICF fusion drive exhaust velocity
        dv = target.delta_v_km_s * 1.5  # ESTIMATE: 1.5× escape velocity for insertion + circularization
        fuel = ship_mass_t * (1.0 - math.exp(-dv / ve_km_s))
        return max(fuel, 0.0)

    def estimate_yield(
        self, target: MiningTarget, method: MiningMethod, duration_years: float
    ) -> tuple[float, float]:
        """Estimate raw extraction and processed yield (tons).

        Returns (raw_tons, processed_tons).
        """
        base_rates = {
            ResourceType.DIAMOND: DIAMOND_YIELD_T_PER_YEAR,
            ResourceType.WATER_ICE: WATER_ICE_YIELD_T_PER_YEAR,
            ResourceType.METALS: METAL_YIELD_T_PER_YEAR,
            ResourceType.RARE_EARTH: RARE_EARTH_YIELD_T_PER_YEAR,
        }
        base = base_rates.get(target.resource_type, 100.0)

        # Gravity modifier: higher gravity = harder extraction
        gravity_factor = 1.0
        if target.mass_earth > 0 and target.radius_earth > 0:
            surface_g = target.mass_earth / (target.radius_earth ** 2)
            gravity_factor = 1.0 / max(surface_g, 0.1)
            gravity_factor = max(0.2, min(gravity_factor, 2.0))

        # Temperature modifier: extreme heat reduces efficiency
        temp_factor = 1.0
        if target.eq_temp_k is not None and target.eq_temp_k > 1000:
            temp_factor = max(0.3, 1.0 - (target.eq_temp_k - 1000) / 5000)

        # Method modifier — ESTIMATE: relative efficiency of each method
        method_factor = {
            MiningMethod.ORBITAL_CAPTURE: 0.6,    # ESTIMATE: lower yield (atmospheric diffusion loss)
            MiningMethod.ROBOTIC_SURFACE: 0.8,    # ESTIMATE: robot downtime in extreme heat
            MiningMethod.SUBSURFACE_DRILL: 1.0,   # ESTIMATE: baseline (direct ore access)
            MiningMethod.ICE_HARVESTING: 1.2,     # ESTIMATE: ice is easily extracted by melting
            MiningMethod.STRIP_MINING: 1.1,       # ESTIMATE: high volume, lower grade ore
        }.get(method, 1.0)

        # Random variance — ESTIMATE: ±15% geological variability
        variance = self._rng.uniform(0.85, 1.15)

        raw_tons = base * gravity_factor * temp_factor * method_factor * variance * duration_years
        processed_tons = raw_tons * self._config.processing_efficiency

        return raw_tons, processed_tons

    def power_requirement(self, method: MiningMethod) -> float:
        """Power required in MW for the mining method.

        All values are ESTIMATE — no operational data; scaled from
        terrestrial analogues (e.g., open-pit mining ~50 MW per Mt/yr,
        Williams 2001 *Energy Conversion and Management* 42 1669).
        """
        return {
            MiningMethod.ORBITAL_CAPTURE: 120.0,   # ESTIMATE: magnetic scoop + processing
            MiningMethod.ROBOTIC_SURFACE: 200.0,   # ESTIMATE: robot fleet + comms + processing
            MiningMethod.SUBSURFACE_DRILL: 350.0,  # ESTIMATE: high-power drill + processing
            MiningMethod.ICE_HARVESTING: 80.0,     # ESTIMATE: lower energy (phase-change extraction)
            MiningMethod.STRIP_MINING: 250.0,      # ESTIMATE: large-scale ore movement
        }.get(method, 150.0)

    def crew_requirement(self, method: MiningMethod) -> int:
        """Minimum crew needed to oversee the mining operation."""
        return {
            MiningMethod.ORBITAL_CAPTURE: 3,
            MiningMethod.ROBOTIC_SURFACE: 2,
            MiningMethod.SUBSURFACE_DRILL: 6,
            MiningMethod.ICE_HARVESTING: 4,
            MiningMethod.STRIP_MINING: 8,
        }.get(method, 4)

    def robots_required(self, method: MiningMethod) -> int:
        """Number of robots needed."""
        return {
            MiningMethod.ORBITAL_CAPTURE: 4,
            MiningMethod.ROBOTIC_SURFACE: 16,
            MiningMethod.SUBSURFACE_DRILL: 12,
            MiningMethod.ICE_HARVESTING: 8,
            MiningMethod.STRIP_MINING: 20,
        }.get(method, 8)

    def run_operation(
        self,
        target: MiningTarget,
        mission_year: float,
        duration_years: float,
    ) -> MiningOperation:
        """Run a complete mining operation at the target.

        Selects method, computes fuel/yield/power, returns operation record.
        """
        method = self.select_method(target)
        raw, processed = self.estimate_yield(target, method, duration_years)
        power = self.power_requirement(method)
        crew = self.crew_requirement(method)
        robots = self.robots_required(method)

        # Cap processed output to cargo capacity
        processed = min(processed, self._config.cargo_capacity_t)

        # Fuel for orbital insertion (assume ship mass ~ 50000 t)
        fuel = self.orbital_insertion_fuel(target, ship_mass_t=50000)

        op = MiningOperation(
            target=target,
            method=method,
            year_started=mission_year,
            duration_years=duration_years,
            tons_extracted=raw,
            tons_processed=processed,
            fuel_consumed_t=fuel,
            power_required_mw=power,
            crew_assigned=crew,
            robots_deployed=robots,
            status="COMPLETE",
        )
        self._operations.append(op)

        logger.info(
            "mining.operation.complete",
            target=target.name,
            method=method.value,
            raw_tons=f"{raw:.1f}",
            processed_tons=f"{processed:.1f}",
            value=f"{op.value:.1f}",
        )
        return op


# ────────────────────────────────────────────────────────────────────
#  MISSION PLANNER
# ────────────────────────────────────────────────────────────────────

@dataclass
class MissionStop:
    """One stop on a multi-target mining route."""
    target: MiningTarget
    arrival_year: float
    mining_duration_years: float
    departure_year: float = 0.0
    fuel_for_transit: float = 0.0
    fuel_for_insertion: float = 0.0

    def __post_init__(self) -> None:
        self.departure_year = self.arrival_year + self.mining_duration_years


@dataclass
class MissionRoute:
    """Complete multi-stop mining mission route."""
    stops: list[MissionStop] = field(default_factory=list)
    total_distance_ly: float = 0.0
    total_fuel_t: float = 0.0
    total_duration_years: float = 0.0
    total_mining_years: float = 0.0
    estimated_cargo_t: float = 0.0
    estimated_value: float = 0.0


class MissionPlanner:
    """Plans optimal mining routes given ship state and target list.

    Greedy approach: pick highest score/distance target first, then
    chain to next-best reachable target until fuel or cargo is full.
    """

    def __init__(
        self,
        velocity_c: float = DEFAULT_VELOCITY_C,
        fuel_capacity_t: float = DEFAULT_FUEL_CAPACITY_T,
        cargo_capacity_t: float = DEFAULT_CARGO_CAPACITY_T,
        seed: int = 42,
    ) -> None:
        self._velocity_c = velocity_c
        self._fuel_capacity = fuel_capacity_t
        self._cargo_capacity = cargo_capacity_t
        self._rng = random.Random(seed)

    def fuel_for_transit(self, distance_ly: float, ship_mass_t: float = 50000) -> float:
        """Fuel to traverse a given distance at cruise velocity.

        Simplified: fuel ~ distance * ship_mass * constant
        (real calculation would use relativistic rocket equation).
        """
        # ESTIMATE: 100 t fuel per ly per 10 kt ship mass — rough ICF fuel budget
        # (Zubrin 1991 AIAA-91-3547: fuel fraction for staged interstellar mission)
        return distance_ly * (ship_mass_t / 10000) * 100.0

    def plan_single(
        self,
        target: MiningTarget,
        mining_duration_years: float = 10.0,
    ) -> MissionRoute:
        """Plan a single-target mission: Sol → target → Sol."""
        dist = target.distance_ly
        travel_one_way = dist / self._velocity_c
        fuel_transit = self.fuel_for_transit(dist) * 2  # round trip
        fuel_insertion = MiningOpsModel().orbital_insertion_fuel(target, 50000)

        stop = MissionStop(
            target=target,
            arrival_year=travel_one_way,
            mining_duration_years=mining_duration_years,
            fuel_for_transit=fuel_transit / 2,
            fuel_for_insertion=fuel_insertion,
        )

        route = MissionRoute(
            stops=[stop],
            total_distance_ly=dist * 2,
            total_fuel_t=fuel_transit + fuel_insertion,
            total_duration_years=travel_one_way * 2 + mining_duration_years,
            total_mining_years=mining_duration_years,
        )
        return route

    def plan_multi_stop(
        self,
        targets: list[MiningTarget],
        mining_years_per_stop: float = 5.0,
        max_stops: int = 5,
    ) -> MissionRoute:
        """Plan a multi-stop mining route using greedy nearest-best heuristic.

        Starts from Sol (0,0,0), visits targets in score-weighted order,
        returns to Sol.
        """
        if not targets:
            return MissionRoute()

        # Sort by score descending
        candidates = sorted(targets, key=lambda t: t.mining_score, reverse=True)
        candidates = candidates[:max_stops * 3]  # pre-filter

        route = MissionRoute()
        visited: set[str] = set()
        current_pos_ly = 0.0  # simplified: distance from Sol along path
        current_year = 0.0
        remaining_fuel = self._fuel_capacity
        remaining_cargo = self._cargo_capacity

        ops_model = MiningOpsModel(seed=self._rng.randint(0, 2**31))

        for _ in range(max_stops):
            best = None
            best_score = -1.0

            for c in candidates:
                if c.name in visited:
                    continue
                leg_dist = c.distance_ly  # simplification: distance from Sol
                fuel_needed = self.fuel_for_transit(leg_dist)
                if fuel_needed > remaining_fuel * 0.4:  # keep 60% for return
                    continue
                # Score adjusted for distance from current position
                adj_score = c.mining_score / (1.0 + abs(c.distance_ly - current_pos_ly) * 0.1)
                if adj_score > best_score:
                    best_score = adj_score
                    best = c

            if best is None:
                break

            visited.add(best.name)
            leg_dist = best.distance_ly
            travel = abs(leg_dist - current_pos_ly) / self._velocity_c
            fuel_transit = self.fuel_for_transit(abs(leg_dist - current_pos_ly))
            fuel_insert = ops_model.orbital_insertion_fuel(best, 50000)

            current_year += travel
            stop = MissionStop(
                target=best,
                arrival_year=current_year,
                mining_duration_years=mining_years_per_stop,
                fuel_for_transit=fuel_transit,
                fuel_for_insertion=fuel_insert,
            )

            # Estimate yield
            _, processed = ops_model.estimate_yield(
                best, ops_model.select_method(best), mining_years_per_stop
            )
            cargo_loaded = min(processed, remaining_cargo)

            current_year += mining_years_per_stop
            current_pos_ly = leg_dist
            remaining_fuel -= (fuel_transit + fuel_insert)
            remaining_cargo -= cargo_loaded

            route.stops.append(stop)
            route.total_mining_years += mining_years_per_stop
            route.estimated_cargo_t += cargo_loaded
            route.estimated_value += cargo_loaded * VALUE_PER_TON.get(
                best.resource_type.value, 1.0
            )

            if remaining_cargo <= 0:
                break

        # Return leg
        return_travel = current_pos_ly / self._velocity_c
        return_fuel = self.fuel_for_transit(current_pos_ly)
        current_year += return_travel

        # Total path length: sum of each stop's Earth-frame
        # distance plus the return leg back to origin. This is
        # a straight-line upper bound — real curved trajectories
        # through multi-star routes are computed by a3_oberth
        # when the ship state requires them.
        route.total_distance_ly = sum(
            s.target.distance_ly for s in route.stops
        ) + current_pos_ly
        route.total_fuel_t = (self._fuel_capacity - remaining_fuel) + return_fuel
        route.total_duration_years = current_year

        return route


# ────────────────────────────────────────────────────────────────────
#  55 CANCRI e DIAMOND MISSION (specific scenario)
# ────────────────────────────────────────────────────────────────────

def build_55_cnc_e_target() -> MiningTarget:
    """Construct the 55 Cancri e diamond-planet target from known parameters.

    55 Cnc e (Janssen):
      - Distance: 12.6 ly (3.86 pc)
      - Radius: 1.875 Earth radii
      - Mass: 7.99 Earth masses
      - Orbital period: 0.737 days (ultra-short)
      - Equilibrium temperature: ~1958 K (dayside up to 2700 K)
      - Composition: estimated 1/3 carbon by mass, significant diamond layer
    """
    return MiningTarget(
        name="55 Cnc e",
        host_star="55 Cnc",
        distance_pc=3.856,
        radius_earth=1.875,
        mass_earth=7.99,
        orbital_period_days=0.7365474,
        eq_temp_k=1958.0,
        spectral_type="G8 V",
        stellar_teff=5172.0,
        stellar_mass=0.905,
        disc_year=2004,
        resource_type=ResourceType.DIAMOND,
    )


@dataclass
class DiamondMissionScenario:
    """Complete 55 Cnc e diamond extraction scenario."""
    # Planet parameters — 55 Cnc e
    # Demory 2016 Nature 532 207: mass = 7.99 ± 0.32 Earth masses
    planet_mass_earth: float = 7.99           # Demory 2016 Nature 532 207
    # Bourrier 2018 A&A 619 A1: radius = 1.875 ± 0.029 Earth radii
    planet_radius_earth: float = 1.875        # Bourrier 2018 A&A 619 A1
    surface_temp_k: float = 2150.0            # ESTIMATE — mean of Demory 2016 (1643 K) + day-side max
    # Madhusudhan 2012 ApJ 756 L15: up to 1/3 of 55 Cnc e mass may be carbon
    carbon_fraction: float = 0.33             # Madhusudhan 2012 ApJ 756 L15: 1/3 carbon by mass
    diamond_fraction_of_carbon: float = 0.3   # ESTIMATE: ~30% of carbon at depth converts to diamond

    # Mission parameters
    # van Leeuwen 2007 A&A 474 653: parallax = 79.80±0.84 mas → distance = 12.53 pc = 12.6 ly
    distance_ly: float = 12.6                 # van Leeuwen 2007 A&A 474 653 Hipparcos parallax
    velocity_c: float = 0.1                   # ESTIMATE — design cruise speed
    mining_duration_years: float = 20.0       # ESTIMATE — mission planning horizon

    # Extraction approach
    orbital_processing: bool = True           # scoop atmosphere
    robotic_surface: bool = True              # heat-resistant robots
    max_robot_surface_temp_k: float = 2500.0  # ESTIMATE — UHTC robot thermal limit

    @property
    def travel_time_one_way_years(self) -> float:
        return self.distance_ly / self.velocity_c

    @property
    def total_mission_years(self) -> float:
        return self.travel_time_one_way_years * 2 + self.mining_duration_years

    @property
    def planet_carbon_mass_kg(self) -> float:
        earth_mass_kg = 5.972e24
        return self.planet_mass_earth * earth_mass_kg * self.carbon_fraction

    @property
    def diamond_reserve_kg(self) -> float:
        return self.planet_carbon_mass_kg * self.diamond_fraction_of_carbon

    @property
    def diamond_reserve_carats(self) -> float:
        # 1 carat = 0.0002 kg
        return self.diamond_reserve_kg / 0.0002

    def estimate_annual_yield_carats(self) -> float:
        """Estimated diamond yield per year of operation.

        Orbital capture: ~200 tons/yr of carbon from atmosphere
        Surface mining: ~250 tons/yr from graphite/diamond layers
        Total: ~450 tons/yr raw carbon → ~135 tons diamond
        At 5e6 carats/ton → 675 million carats/yr
        """
        raw_carbon_t = DIAMOND_YIELD_T_PER_YEAR  # 450 t/yr
        diamond_fraction = 0.30  # ESTIMATE: 30% of extracted carbon yields gem-quality diamond
        diamond_tons = raw_carbon_t * diamond_fraction
        # 1 carat = 0.2 g → 1 metric ton = 5 × 10⁶ carats (exact conversion)
        carats_per_ton = 5_000_000  # exact: 1 t = 5e6 carats (IGC standard)
        return diamond_tons * carats_per_ton

    def describe(self) -> str:
        lines = [
            "=" * 60,
            "  55 CANCRI e — DIAMOND MINING MISSION",
            "=" * 60,
            f"  Target: 55 Cnc e (Janssen)",
            f"  Distance: {self.distance_ly} ly from Sol",
            f"  Travel time (one-way): {self.travel_time_one_way_years:.0f} years at {self.velocity_c}c",
            f"  Total mission: {self.total_mission_years:.0f} years",
            "",
            "  PLANET:",
            f"    Mass: {self.planet_mass_earth}x Earth ({self.planet_mass_earth * 5.972e24:.2e} kg)",
            f"    Radius: {self.planet_radius_earth}x Earth",
            f"    Surface temp: {self.surface_temp_k:.0f} K",
            f"    Carbon fraction: {self.carbon_fraction:.0%}",
            f"    Estimated diamond reserve: {self.diamond_reserve_carats:.2e} carats",
            "",
            "  EXTRACTION:",
            f"    Orbital CO2 capture: {'YES' if self.orbital_processing else 'NO'}",
            f"    Robotic surface mining: {'YES' if self.robotic_surface else 'NO'}",
            f"    Robot heat tolerance: {self.max_robot_surface_temp_k:.0f} K",
            f"    Annual yield: {self.estimate_annual_yield_carats():,.0f} carats/year",
            f"    {self.mining_duration_years:.0f}-year yield: "
            f"{self.estimate_annual_yield_carats() * self.mining_duration_years:,.0f} carats",
            "",
            "  CHALLENGES:",
            "    - Extreme surface heat (no EVA possible)",
            "    - No breathable atmosphere (CO2/CO/SiO dominant)",
            "    - High gravity (2.3g surface)",
            "    - Tidal locking → permanent dayside/nightside",
            "    - Solution: orbital processing + robotic surface ops",
            "",
            "  RETURN:",
            f"    Option A: Ship returns ({self.travel_time_one_way_years:.0f} yr)",
            f"    Option B: Autonomous cargo pods at 0.05c ({self.distance_ly/0.05:.0f} yr)",
        ]
        return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────
#  COMPLETE MINING MISSION SIMULATION
# ────────────────────────────────────────────────────────────────────

@dataclass
class MiningMissionConfig:
    """Configuration for a full mining mission."""
    target_name: str = "55 Cnc e"
    velocity_c: float = DEFAULT_VELOCITY_C
    crew_size: int = DEFAULT_CREW_SIZE
    cargo_capacity_t: float = DEFAULT_CARGO_CAPACITY_T
    fuel_capacity_t: float = DEFAULT_FUEL_CAPACITY_T
    mining_duration_years: float = 20.0
    seed: int = 42
    use_cargo_pods: bool = True   # send cargo back via autonomous pods


@dataclass
class MiningMissionResults:
    """Results from a complete mining mission."""
    target_name: str = ""
    resource_type: str = ""
    distance_ly: float = 0.0

    # Travel
    travel_time_one_way_years: float = 0.0
    total_mission_years: float = 0.0

    # Mining
    mining_method: str = ""
    mining_duration_years: float = 0.0
    raw_extracted_t: float = 0.0
    processed_t: float = 0.0
    value_au: float = 0.0          # in abstract economic units

    # Fuel
    fuel_for_transit_t: float = 0.0
    fuel_for_insertion_t: float = 0.0
    total_fuel_t: float = 0.0

    # Operations
    power_required_mw: float = 0.0
    crew_assigned: int = 0
    robots_deployed: int = 0

    # Ship state
    ship_survived: bool = True
    cargo_pods_sent: int = 0

    # Events
    events: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=" * 60,
            f"  MINING MISSION: {self.target_name}",
            f"  Resource: {self.resource_type}",
            "=" * 60,
            f"  Distance: {self.distance_ly:.1f} ly",
            f"  Travel (one-way): {self.travel_time_one_way_years:.1f} years",
            f"  Total mission: {self.total_mission_years:.1f} years",
            "",
            f"  Mining method: {self.mining_method}",
            f"  Mining duration: {self.mining_duration_years:.1f} years",
            f"  Raw extracted: {self.raw_extracted_t:,.1f} tons",
            f"  Processed: {self.processed_t:,.1f} tons",
            f"  Value: {self.value_au:,.1f} AU",
            "",
            f"  Fuel (transit): {self.fuel_for_transit_t:,.0f} tons",
            f"  Fuel (insertion): {self.fuel_for_insertion_t:,.0f} tons",
            f"  Fuel (total): {self.total_fuel_t:,.0f} tons",
            "",
            f"  Power: {self.power_required_mw:.0f} MW",
            f"  Crew: {self.crew_assigned}",
            f"  Robots: {self.robots_deployed}",
            f"  Cargo pods sent: {self.cargo_pods_sent}",
            f"  Ship survived: {'YES' if self.ship_survived else 'NO'}",
            f"  Events logged: {len(self.events)}",
        ]
        return "\n".join(lines)


class MiningMission:
    """Full mining mission simulation: travel to target, mine, return.

    Integrates:
      - ResourceScanner to find/validate target
      - MiningOpsModel for extraction simulation
      - MissionPlanner for route/fuel planning
      - Optional GenerationShipSimulation for travel phase
    """

    def __init__(self, config: MiningMissionConfig | None = None) -> None:
        self._config = config or MiningMissionConfig()
        self._scanner = ResourceScanner()
        self._ops = MiningOpsModel(
            config=MiningOpsConfig(
                crew_size=self._config.crew_size,
                cargo_capacity_t=self._config.cargo_capacity_t,
            ),
            seed=self._config.seed,
        )
        self._planner = MissionPlanner(
            velocity_c=self._config.velocity_c,
            fuel_capacity_t=self._config.fuel_capacity_t,
            cargo_capacity_t=self._config.cargo_capacity_t,
            seed=self._config.seed,
        )
        self._results = MiningMissionResults()

    @property
    def results(self) -> MiningMissionResults:
        return self._results

    def run(self) -> MiningMissionResults:
        """Execute the complete mining mission."""
        cfg = self._config
        r = self._results
        events: list[dict[str, Any]] = []

        # Phase 0: Load exoplanet data and find target
        loaded = self._scanner.load()
        events.append({"year": 0, "phase": "SCAN", "msg": f"Loaded {loaded} exoplanets"})

        # Prefer known high-fidelity parameters for notable targets
        target: MiningTarget | None = None
        if "55" in cfg.target_name and "cnc" in cfg.target_name.lower():
            target = build_55_cnc_e_target()
            events.append({"year": 0, "phase": "SCAN",
                           "msg": "Using known 55 Cnc e parameters (12.6 ly)"})
        else:
            target = self._scanner.find_target(cfg.target_name)

        if target is None:
            r.ship_survived = False
            events.append({"year": 0, "phase": "ABORT",
                           "msg": f"Target '{cfg.target_name}' not found"})
            r.events = events
            return r

        # Ensure classification
        if target.resource_type == ResourceType.UNKNOWN:
            target.resource_type = self._scanner._classify(target)
        if target.mining_score == 0:
            target.mining_score = self._scanner._score(target)

        r.target_name = target.name
        r.resource_type = target.resource_type.value
        r.distance_ly = target.distance_ly

        # Phase 1: Outbound travel
        travel_one_way = target.distance_ly / cfg.velocity_c
        r.travel_time_one_way_years = travel_one_way

        events.append({
            "year": 0, "phase": "LAUNCH",
            "msg": f"Departing Sol for {target.name} ({target.distance_ly:.1f} ly)",
        })

        # Simulate travel with generation ship if available (supplemental detail)
        ship_travel_note = ""
        try:
            from aria.simulation.generation_ship import (
                GenerationShipConfig, GenerationShipSimulation,
            )
            ship_config = GenerationShipConfig(
                crew_size=cfg.crew_size,
                velocity_c=cfg.velocity_c,
                target_distance_ly=target.distance_ly,
                seed=cfg.seed,
            )
            ship_sim = GenerationShipSimulation(ship_config)
            ship_results = ship_sim.run(years=max(1, int(travel_one_way)))
            if ship_results.ship_survived:
                ship_travel_note = "crew intact"
            else:
                ship_travel_note = (
                    f"crew attrition during transit "
                    f"(gen-ship sim: {ship_results.failure_reason or 'challenge failure'})"
                )
        except Exception as exc:
            ship_travel_note = f"travel sim skipped: {exc}"

        events.append({
            "year": travel_one_way, "phase": "ARRIVAL",
            "msg": f"Arrived at {target.name}. {ship_travel_note}",
        })

        # Phase 2: Mining operations
        method = self._ops.select_method(target)
        r.mining_method = method.value
        r.mining_duration_years = cfg.mining_duration_years

        events.append({
            "year": travel_one_way, "phase": "MINING_START",
            "msg": f"Beginning {method.value} at {target.name}",
        })

        operation = self._ops.run_operation(
            target, mission_year=travel_one_way,
            duration_years=cfg.mining_duration_years,
        )

        r.raw_extracted_t = operation.tons_extracted
        r.processed_t = operation.tons_processed
        r.value_au = operation.value
        r.power_required_mw = operation.power_required_mw
        r.crew_assigned = operation.crew_assigned
        r.robots_deployed = operation.robots_deployed

        events.append({
            "year": travel_one_way + cfg.mining_duration_years,
            "phase": "MINING_COMPLETE",
            "msg": f"Extracted {operation.tons_extracted:,.0f}t raw, "
                   f"{operation.tons_processed:,.0f}t processed",
        })

        # Phase 3: Cargo pods (optional)
        if cfg.use_cargo_pods and operation.tons_processed > 0:
            pod_capacity = 500.0  # ESTIMATE: 500 t per pod (5× CargoPod capacity for bulk missions)
            num_pods = max(1, int(math.ceil(operation.tons_processed / pod_capacity)))
            r.cargo_pods_sent = num_pods
            events.append({
                "year": travel_one_way + cfg.mining_duration_years,
                "phase": "CARGO_LAUNCH",
                "msg": f"Launched {num_pods} cargo pods toward Sol "
                       f"({operation.tons_processed:,.0f}t total)",
            })

        # Phase 4: Return transit
        fuel_transit = self._planner.fuel_for_transit(target.distance_ly) * 2
        fuel_insert = self._ops.orbital_insertion_fuel(target, 50000)
        r.fuel_for_transit_t = fuel_transit
        r.fuel_for_insertion_t = fuel_insert
        r.total_fuel_t = fuel_transit + fuel_insert

        r.total_mission_years = travel_one_way * 2 + cfg.mining_duration_years
        r.ship_survived = True

        events.append({
            "year": r.total_mission_years, "phase": "RETURN",
            "msg": f"Ship returns to Sol. Mission duration: "
                   f"{r.total_mission_years:.0f} years",
        })

        r.events = events
        return r


# ────────────────────────────────────────────────────────────────────
#  NEARBY TARGETS (convenience)
# ────────────────────────────────────────────────────────────────────

NOTABLE_TARGETS = {
    "55_cnc_e": {
        "name": "55 Cnc e",
        "distance_ly": 12.6,
        "type": "DIAMOND",
        "description": "Carbon-rich super-Earth, ~1/3 carbon, possible diamond mantle",
    },
    "gj_876_d": {
        "name": "GJ 876 d",
        "distance_ly": 15.2,
        "type": "RARE_EARTH",
        "description": "Super-Earth (6.8 Me) in GJ 876 system",
    },
    "tau_ceti": {
        "name": "Tau Ceti system",
        "distance_ly": 11.9,
        "type": "METALS",
        "description": "Sun-like star with multiple planets, heavy debris disk",
    },
    "proxima_b": {
        "name": "Proxima Centauri b",
        "distance_ly": 4.24,
        "type": "RARE_EARTH",
        "description": "Nearest known exoplanet, Earth-mass in habitable zone",
    },
    "gj_832_b": {
        "name": "GJ 832 b",
        "distance_ly": 16.2,
        "type": "WATER_ICE",
        "description": "Jupiter-mass planet, potential icy moons",
    },
}


def list_mining_targets() -> list[dict[str, Any]]:
    """List all notable mining targets with descriptions."""
    scanner = ResourceScanner()
    loaded = scanner.load()

    results = []
    for key, info in sorted(NOTABLE_TARGETS.items()):
        found = scanner.find_target(info["name"].split()[0])
        entry = {
            "key": key,
            "name": info["name"],
            "distance_ly": info["distance_ly"],
            "type": info["type"],
            "description": info["description"],
            "in_catalog": found is not None,
        }
        if found:
            entry["mining_score"] = round(found.mining_score, 3)
        results.append(entry)

    # Add top scored targets from real data
    top = scanner.get_top_targets(10)
    for t in top:
        if not any(t.name in r["name"] for r in results):
            results.append({
                "key": t.name.lower().replace(" ", "_"),
                "name": t.name,
                "distance_ly": round(t.distance_ly, 1),
                "type": t.resource_type.value,
                "description": f"{t.resource_type.value} target, "
                               f"{t.mass_earth:.1f} Me, score={t.mining_score:.3f}",
                "in_catalog": True,
                "mining_score": round(t.mining_score, 3),
            })

    return results


# ────────────────────────────────────────────────────────────────────
#  CLI ENTRY POINTS
# ────────────────────────────────────────────────────────────────────

def cli_list_targets() -> None:
    """Print all mining targets in a formatted table."""
    targets = list_mining_targets()

    print(f"\n{'='*72}")
    print(f"  ARIA Mining Targets — Interstellar Resource Survey")
    print(f"{'='*72}")
    print(f"  {'Name':<25} {'Dist (ly)':>10} {'Type':<12} {'Score':>8}")
    print(f"  {'-'*25} {'-'*10} {'-'*12} {'-'*8}")

    for t in sorted(targets, key=lambda x: x.get("mining_score", 0), reverse=True):
        score = t.get("mining_score", "N/A")
        score_str = f"{score:.3f}" if isinstance(score, float) else str(score)
        print(f"  {t['name']:<25} {t['distance_ly']:>10.1f} {t['type']:<12} {score_str:>8}")

    print(f"\n  Total targets: {len(targets)}")
    print(f"  Data source: NASA Exoplanet Archive (nearby confirmed planets)")
    print()


def cli_run_mining_mission(target_name: str, duration_years: int = 250) -> None:
    """Run a mining mission from the CLI."""
    # Map shorthand target names
    target_map = {
        "55_cnc_e": "55 Cnc e",
        "gj_876_d": "GJ 876 d",
        "tau_ceti": "tau ceti",
        "proxima_b": "Proxima Cen",
        "gj_832_b": "GJ 832 b",
    }
    resolved_name = target_map.get(target_name, target_name)

    # Determine mining duration from total duration
    # Total = 2 * travel + mining
    # For 55 Cnc e: travel = 126 yr each way, so mining = duration - 252
    target: MiningTarget | None = None
    if "55" in target_name and "cnc" in target_name.lower():
        target = build_55_cnc_e_target()
    else:
        scanner = ResourceScanner()
        scanner.load()
        target = scanner.find_target(resolved_name)

    if target is None:
        print(f"\n  Target '{target_name}' not found.")
        print(f"  Use 'aria sim mining --list-targets' to see available targets.\n")
        return

    travel = target.distance_ly / DEFAULT_VELOCITY_C
    mining_years = max(5, duration_years - 2 * travel)

    config = MiningMissionConfig(
        target_name=resolved_name,
        mining_duration_years=mining_years,
    )

    print(f"\n  Initializing mining mission to {target.name}...")
    print(f"  Travel time: {travel:.0f} years each way")
    print(f"  Mining duration: {mining_years:.0f} years")
    print(f"  Total mission: {2*travel + mining_years:.0f} years\n")

    mission = MiningMission(config)
    results = mission.run()

    print(results.summary())

    # Show 55 Cnc e specific info if applicable
    if "55 Cnc" in (target.name or ""):
        scenario = DiamondMissionScenario(mining_duration_years=mining_years)
        print(f"\n{scenario.describe()}")

    # Event log
    print(f"\n  {'MISSION LOG':^58}")
    print(f"  {'-'*58}")
    for ev in results.events:
        print(f"  Year {ev['year']:>7.0f} | {ev['phase']:<16} | {ev['msg']}")
    print()
