"""4D Simulator Engine — 3D spatial position + time for ARIA generation ship.

The MAIN simulation system for ARIA. Runs every subsystem tick-by-tick
and tracks the ship's complete state through 4D spacetime.

Dimensions:
  x, y, z — galactic coordinates in light-years (Sol at origin)
  t       — mission time in years (the 4th dimension)

Every tick advances time by a configurable interval (1 year, 1 month, or 1 day)
and runs ALL subsystems in sequence:
  1. InterstellarSimulation       — core journey physics (fuel, radiation, hull, food)
  2. InterstellarChallengeOrch.   — 6 grand challenges (material entropy, food crisis, etc.)
  3. FoodSynthesisSimulator       — starch + protein synthesis
  4. PropulsionSimulator          — fusion + magsail + laser sail
  5. ManufacturingSimulator       — 3D printers + von Neumann self-repair
  6. DefenseSimulator             — point defense + shields + internal security
  7. BreakthroughTechOrchestrator — glass archive, nanobots, torpor, biomanufacturing
  8. CrewEcosystemOrchestrator    — crew lifecycle, education, closed-loop ecosystem
  9. YearlyShieldSimulator        — 7-layer shield erosion model
  10. AdvancedSystemsOrchestrator — radiation shielding, gravity, reactor, comms, recycling

After each tick, the engine:
  - Computes 3D position along the trajectory vector
  - Records velocity changes from braking / ISM drag
  - Captures a complete state snapshot
  - Logs all events into a unified timeline

The SimulatorTimeline provides time-travel: seek to any year, replay
forward/backward, export the entire history for web dashboards.
"""

from __future__ import annotations

import copy
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from aria.simulator.targets import STAR_CATALOG, StarTarget, get_target

logger = structlog.get_logger()


# ────────────────────────────────────────────────────────────────────
#  TICK RESOLUTION
# ────────────────────────────────────────────────────────────────────

class TickResolution(Enum):
    """How much mission time passes per simulation tick."""
    YEAR = "year"      # 1 tick = 1 year (default, fastest)
    MONTH = "month"    # 1 tick = 1/12 year
    DAY = "day"        # 1 tick = 1/365.25 year

    @property
    def years_per_tick(self) -> float:
        if self == TickResolution.YEAR:
            return 1.0
        elif self == TickResolution.MONTH:
            return 1.0 / 12.0
        else:
            return 1.0 / 365.25


# ────────────────────────────────────────────────────────────────────
#  SIMULATOR STATE — complete snapshot at a point in spacetime
# ────────────────────────────────────────────────────────────────────

@dataclass
class SubsystemSnapshot:
    """Captured state of one subsystem at a point in time."""
    name: str
    health: float = 1.0          # 0.0 = destroyed, 1.0 = perfect
    status: str = "NOMINAL"      # NOMINAL / WARNING / CRITICAL / OFFLINE
    metrics: dict[str, Any] = field(default_factory=dict)
    events_this_tick: int = 0


@dataclass
class SimulatorEvent:
    """A discrete event in the unified timeline."""
    mission_year: float
    category: str
    severity: str       # NOMINAL, WATCH, WARNING, CRITICAL, EMERGENCY
    description: str
    subsystem: str
    source: str = ""    # Which simulator generated this
    impact: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_year": self.mission_year,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "subsystem": self.subsystem,
            "source": self.source,
            "impact": self.impact,
        }


@dataclass
class SimulatorState:
    """Complete state of the generation ship at a single point in 4D spacetime.

    This is the atomic unit of the simulator — everything about the ship
    at one moment in time.
    """
    # ─── 4D coordinates ─────────────────────────────────────────
    position_3d: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    velocity_3d: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    mission_time_years: float = 0.0

    # ─── Trajectory ─────────────────────────────────────────────
    origin: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    target: list[float] = field(default_factory=lambda: [100.0, 0.0, 0.0])
    target_name: str = ""
    distance_traveled_ly: float = 0.0
    distance_remaining_ly: float = 0.0
    velocity_scalar_c: float = 0.0     # Fraction of c
    phase: str = "PRE_LAUNCH"

    # ─── Core subsystem states ──────────────────────────────────
    hull_integrity: float = 1.0
    fuel_fraction: float = 1.0
    fuel_kg: float = 50000.0
    power_watts: float = 500000.0
    rtg_power_fraction: float = 1.0
    reactor_health: float = 1.0

    # ─── Life support ───────────────────────────────────────────
    crew_count: int = 4
    crew_generation: int = 1
    crew_morale: float = 0.8
    food_reserves_kg: float = 10000.0
    water_liters: float = 50000.0
    seed_viability: float = 1.0
    o2_reserves_kg: float = 500.0

    # ─── Subsystem health map ───────────────────────────────────
    electronics_health: float = 1.0
    radiation_dose_krad: float = 0.0
    printer_health: float = 1.0
    hydroponic_capacity: float = 1.0
    grow_light_health: float = 1.0
    bioreactor_health: float = 1.0
    knowledge_integrity: float = 1.0
    ai_model_version: int = 1

    # ─── Shield state ───────────────────────────────────────────
    shield_overall_health: float = 1.0
    micrometeorite_impacts: int = 0

    # ─── Manufacturing ──────────────────────────────────────────
    spare_electronics: int = 200
    spare_mechanical: int = 100

    # ─── Survival flag ──────────────────────────────────────────
    ship_survived: bool = True
    failure_reason: str = ""

    # ─── Subsystem snapshots ────────────────────────────────────
    subsystems: dict[str, SubsystemSnapshot] = field(default_factory=dict)

    # ─── Event log for this tick ────────────────────────────────
    events_this_tick: list[dict[str, Any]] = field(default_factory=list)

    # ─── Tick metadata ──────────────────────────────────────────
    tick_number: int = 0
    wall_clock_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON export."""
        d = {
            "position_3d": list(self.position_3d),
            "velocity_3d": list(self.velocity_3d),
            "mission_time_years": self.mission_time_years,
            "target_name": self.target_name,
            "distance_traveled_ly": round(self.distance_traveled_ly, 4),
            "distance_remaining_ly": round(self.distance_remaining_ly, 4),
            "velocity_scalar_c": round(self.velocity_scalar_c, 6),
            "phase": self.phase,
            "hull_integrity": round(self.hull_integrity, 4),
            "fuel_fraction": round(self.fuel_fraction, 4),
            "fuel_kg": round(self.fuel_kg, 1),
            "power_watts": round(self.power_watts, 1),
            "crew_count": self.crew_count,
            "crew_generation": self.crew_generation,
            "crew_morale": round(self.crew_morale, 4),
            "food_reserves_kg": round(self.food_reserves_kg, 1),
            "water_liters": round(self.water_liters, 1),
            "seed_viability": round(self.seed_viability, 4),
            "electronics_health": round(self.electronics_health, 4),
            "radiation_dose_krad": round(self.radiation_dose_krad, 2),
            "printer_health": round(self.printer_health, 4),
            "shield_overall_health": round(self.shield_overall_health, 4),
            "ship_survived": self.ship_survived,
            "failure_reason": self.failure_reason,
            "tick_number": self.tick_number,
            "subsystems": {
                name: {
                    "health": round(ss.health, 4),
                    "status": ss.status,
                    "events_this_tick": ss.events_this_tick,
                }
                for name, ss in self.subsystems.items()
            },
            "events_this_tick": self.events_this_tick,
        }
        return d


# ────────────────────────────────────────────────────────────────────
#  SIMULATOR TIMELINE — the 4th dimension
# ────────────────────────────────────────────────────────────────────

class SimulatorTimeline:
    """Time dimension of the 4D simulator.

    Stores a snapshot of SimulatorState at every recorded point in time.
    Supports seeking to any year, forward/backward replay, and export.
    """

    def __init__(self) -> None:
        self._snapshots: list[SimulatorState] = []
        self._year_index: dict[float, int] = {}  # year → snapshot index
        self._cursor: int = -1

    @property
    def length(self) -> int:
        """Total number of snapshots in the timeline."""
        return len(self._snapshots)

    @property
    def years(self) -> list[float]:
        """All recorded mission years, in order."""
        return [s.mission_time_years for s in self._snapshots]

    @property
    def first_year(self) -> float:
        if not self._snapshots:
            return 0.0
        return self._snapshots[0].mission_time_years

    @property
    def last_year(self) -> float:
        if not self._snapshots:
            return 0.0
        return self._snapshots[-1].mission_time_years

    @property
    def cursor(self) -> int:
        return self._cursor

    @property
    def current(self) -> SimulatorState | None:
        """State at the current cursor position."""
        if 0 <= self._cursor < len(self._snapshots):
            return self._snapshots[self._cursor]
        return None

    def append(self, state: SimulatorState) -> None:
        """Append a new state snapshot to the timeline."""
        idx = len(self._snapshots)
        # Deep copy to prevent mutation from affecting recorded state
        frozen = copy.deepcopy(state)
        self._snapshots.append(frozen)
        self._year_index[frozen.mission_time_years] = idx
        self._cursor = idx

    def seek(self, year: float) -> SimulatorState | None:
        """Seek to the closest snapshot at or before the given year.

        Returns the state at that year, or None if timeline is empty.
        Sets the cursor to that position.
        """
        if not self._snapshots:
            return None

        # Exact match
        if year in self._year_index:
            self._cursor = self._year_index[year]
            return self._snapshots[self._cursor]

        # Binary search for closest year <= target
        lo, hi = 0, len(self._snapshots) - 1
        best = 0
        while lo <= hi:
            mid = (lo + hi) // 2
            if self._snapshots[mid].mission_time_years <= year:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1

        self._cursor = best
        return self._snapshots[self._cursor]

    def seek_exact(self, year: float) -> SimulatorState | None:
        """Seek to an exact year. Returns None if not found."""
        if year in self._year_index:
            self._cursor = self._year_index[year]
            return self._snapshots[self._cursor]
        return None

    def step_forward(self) -> SimulatorState | None:
        """Advance cursor by one snapshot. Returns new state or None at end."""
        if self._cursor < len(self._snapshots) - 1:
            self._cursor += 1
            return self._snapshots[self._cursor]
        return None

    def step_backward(self) -> SimulatorState | None:
        """Move cursor back one snapshot. Returns new state or None at start."""
        if self._cursor > 0:
            self._cursor -= 1
            return self._snapshots[self._cursor]
        return None

    def range(self, start_year: float, end_year: float) -> list[SimulatorState]:
        """Get all snapshots within a year range (inclusive)."""
        return [
            s for s in self._snapshots
            if start_year <= s.mission_time_years <= end_year
        ]

    def get_trajectory(self) -> list[list[float]]:
        """Extract the 3D trajectory as a list of [x, y, z] points."""
        return [list(s.position_3d) for s in self._snapshots]

    def get_metric_series(self, metric: str) -> list[tuple[float, Any]]:
        """Extract a time series of any metric from the snapshots.

        Returns list of (year, value) tuples.
        """
        series = []
        for s in self._snapshots:
            val = getattr(s, metric, None)
            if val is not None:
                series.append((s.mission_time_years, val))
        return series

    def export_json(self) -> list[dict[str, Any]]:
        """Export full timeline as JSON-serializable list."""
        return [s.to_dict() for s in self._snapshots]

    def clear(self) -> None:
        """Reset the timeline."""
        self._snapshots.clear()
        self._year_index.clear()
        self._cursor = -1


# ────────────────────────────────────────────────────────────────────
#  SIMULATOR ENGINE — runs the full simulation
# ────────────────────────────────────────────────────────────────────

class SimulatorEngine:
    """4D Simulator Engine — drives every subsystem tick by tick.

    This is the central simulation loop. Each tick:
      1. Advances mission time by tick_resolution
      2. Runs all subsystems for that time step
      3. Computes 3D position along the trajectory
      4. Captures complete state into the timeline
      5. Logs all events

    Usage:
        engine = SimulatorEngine(
            target=STAR_CATALOG["alpha_centauri"],
            velocity_c=0.1,
            crew_size=50,
        )
        engine.initialize()
        engine.run(years=43)
        state_at_year_20 = engine.timeline.seek(20)
    """

    def __init__(
        self,
        target: StarTarget | None = None,
        velocity_c: float = 0.1,
        crew_size: int = 4,
        seed: int = 42,
        tick_resolution: TickResolution = TickResolution.YEAR,
        enable_all_subsystems: bool = True,
    ) -> None:
        self._target = target or STAR_CATALOG["100_ly_target"]
        self._velocity_c = velocity_c
        self._crew_size = crew_size
        self._seed = seed
        self._tick_resolution = tick_resolution
        self._enable_all = enable_all_subsystems

        # 3D trajectory vector
        self._direction = self._compute_direction()
        self._total_distance = self._target.distance_ly

        # State
        self._state = SimulatorState(
            origin=[0.0, 0.0, 0.0],
            target=list(self._target.position_ly),
            target_name=self._target.name,
            velocity_scalar_c=velocity_c,
            distance_remaining_ly=self._total_distance,
            crew_count=crew_size,
        )
        self._state.velocity_3d = [
            velocity_c * d for d in self._direction
        ]

        # Timeline
        self._timeline = SimulatorTimeline()

        # Event log
        self._all_events: list[SimulatorEvent] = []

        # Control
        self._initialized = False
        self._paused = False
        self._tick_count = 0
        self._wall_start: float = 0.0

        # Subsystem instances (initialized on .initialize())
        self._base_sim: Any = None
        self._challenges: Any = None
        self._food_synth: Any = None
        self._propulsion: Any = None
        self._manufacturing: Any = None
        self._defense: Any = None
        self._breakthrough: Any = None
        self._crew_eco: Any = None
        self._shield: Any = None
        self._advanced: Any = None

    @property
    def state(self) -> SimulatorState:
        """Current simulation state."""
        return self._state

    @property
    def timeline(self) -> SimulatorTimeline:
        """The 4th dimension — full timeline of all recorded states."""
        return self._timeline

    @property
    def events(self) -> list[SimulatorEvent]:
        """All events across the entire simulation."""
        return list(self._all_events)

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def mission_year(self) -> float:
        return self._state.mission_time_years

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def target(self) -> StarTarget:
        return self._target

    def initialize(self) -> None:
        """Initialize all subsystems. Must be called before run/step."""
        from aria.simulation.interstellar import InterstellarSimulation
        from aria.simulation.interstellar_challenges import InterstellarChallengeOrchestrator

        self._base_sim = InterstellarSimulation(
            cruise_velocity_c=self._velocity_c,
            crew_size=self._crew_size,
            seed=self._seed,
        )
        self._challenges = InterstellarChallengeOrchestrator(
            crew_size=self._crew_size, seed=self._seed,
        )

        if self._enable_all:
            self._init_optional_subsystems()

        self._wall_start = time.time()
        self._initialized = True

        # Record initial state (year 0)
        self._update_state_from_subsystems()
        self._timeline.append(self._state)

        logger.info(
            "simulator.initialized",
            target=self._target.display_name,
            distance_ly=self._total_distance,
            velocity_c=self._velocity_c,
            crew=self._crew_size,
            tick_resolution=self._tick_resolution.value,
        )

    def _init_optional_subsystems(self) -> None:
        """Initialize all optional subsystems with graceful fallbacks."""
        try:
            from aria.simulation.food_synthesis import FoodSynthesisSimulator
            self._food_synth = FoodSynthesisSimulator(
                crew_size=self._crew_size, seed=self._seed,
            )
        except Exception:
            logger.debug("simulator.subsystem_skip", name="food_synthesis")

        try:
            from aria.simulation.food_synthesis import PropulsionSimulator
            self._propulsion = PropulsionSimulator(seed=self._seed)
        except Exception:
            logger.debug("simulator.subsystem_skip", name="propulsion")

        try:
            from aria.simulation.manufacturing import ManufacturingSimulator
            self._manufacturing = ManufacturingSimulator(seed=self._seed)
        except Exception:
            logger.debug("simulator.subsystem_skip", name="manufacturing")

        try:
            from aria.simulation.defense import DefenseSimulator
            self._defense = DefenseSimulator(
                crew_size=self._crew_size, seed=self._seed,
            )
        except Exception:
            logger.debug("simulator.subsystem_skip", name="defense")

        try:
            from aria.simulation.breakthrough_tech import BreakthroughTechOrchestrator
            self._breakthrough = BreakthroughTechOrchestrator(
                crew_size=self._crew_size, seed=self._seed,
            )
        except Exception:
            logger.debug("simulator.subsystem_skip", name="breakthrough_tech")

        try:
            from aria.simulation.crew_ecosystem import CrewEcosystemOrchestrator
            self._crew_eco = CrewEcosystemOrchestrator(seed=self._seed)
        except Exception:
            logger.debug("simulator.subsystem_skip", name="crew_ecosystem")

        try:
            from aria.simulation.shield_system import YearlyShieldSimulator
            self._shield = YearlyShieldSimulator()
        except Exception:
            logger.debug("simulator.subsystem_skip", name="shield_system")

        try:
            from aria.simulation.advanced_systems import AdvancedSystemsOrchestrator
            self._advanced = AdvancedSystemsOrchestrator(seed=self._seed)
        except Exception:
            logger.debug("simulator.subsystem_skip", name="advanced_systems")

    # ─── Execution ──────────────────────────────────────────────

    def run(self, years: float | None = None) -> SimulatorState:
        """Run the simulation for the given number of years (or full mission).

        Returns the final state.
        """
        if not self._initialized:
            self.initialize()

        total_years = years or (self._total_distance / self._velocity_c)
        dt = self._tick_resolution.years_per_tick
        ticks_needed = int(math.ceil(total_years / dt))

        logger.info(
            "simulator.run_start",
            total_years=total_years,
            ticks=ticks_needed,
            resolution=self._tick_resolution.value,
        )

        for _ in range(ticks_needed):
            if self._paused:
                break
            if not self._state.ship_survived:
                break
            self.step()

        self._state.wall_clock_s = time.time() - self._wall_start
        logger.info(
            "simulator.run_complete",
            mission_years=self._state.mission_time_years,
            ticks=self._tick_count,
            events=len(self._all_events),
            survived=self._state.ship_survived,
            wall_time_s=round(self._state.wall_clock_s, 2),
        )
        return self._state

    def step(self) -> SimulatorState:
        """Execute a single simulation tick. Returns the new state."""
        if not self._initialized:
            raise RuntimeError("Call initialize() before step()")
        if self._paused:
            return self._state

        dt = self._tick_resolution.years_per_tick
        self._tick_count += 1
        tick_events: list[SimulatorEvent] = []

        # Only run subsystem simulate_year on integer year boundaries
        # For sub-year resolutions, we interpolate position but run
        # subsystems at yearly cadence (they all operate per-year)
        new_year = self._state.mission_time_years + dt
        crossed_year = int(new_year) > int(self._state.mission_time_years)

        self._state.mission_time_years = new_year

        if crossed_year or self._tick_resolution == TickResolution.YEAR:
            tick_events = self._run_subsystem_tick()

        # Update 3D position
        self._update_3d_position()

        # Record events
        for ev in tick_events:
            self._all_events.append(ev)

        self._state.events_this_tick = [e.to_dict() for e in tick_events]
        self._state.tick_number = self._tick_count

        # Survival check
        self._check_survival()

        # Record snapshot in timeline
        self._timeline.append(self._state)

        return self._state

    def pause(self) -> None:
        """Pause the simulation."""
        self._paused = True

    def resume(self) -> None:
        """Resume a paused simulation."""
        self._paused = False

    def seek(self, year: float) -> SimulatorState | None:
        """Seek the timeline to a specific year. Does not re-simulate."""
        return self._timeline.seek(year)

    # ─── Internal tick logic ─────────────────────────────────────

    def _run_subsystem_tick(self) -> list[SimulatorEvent]:
        """Run all subsystems for one year and collect events."""
        year = self._state.mission_time_years
        events: list[SimulatorEvent] = []

        # 1. Core interstellar simulation
        if self._base_sim:
            year_events = self._base_sim.simulate_year()
            for e in year_events:
                events.append(SimulatorEvent(
                    mission_year=e.year,
                    category=e.category,
                    severity=e.severity,
                    description=e.description,
                    subsystem=e.subsystem,
                    source="interstellar",
                    impact=e.impact,
                ))

        # 2. Challenge orchestrator
        if self._challenges:
            cr = self._challenges.simulate_year(
                year, self._base_sim.state.distance_ly if self._base_sim else 0,
            )
            for e in cr.get("events", []):
                events.append(SimulatorEvent(
                    mission_year=year,
                    category=e.get("category", "CHALLENGE"),
                    severity=e.get("severity", "UNKNOWN"),
                    description=e.get("description", ""),
                    subsystem=e.get("subsystem", "challenges"),
                    source="challenges",
                ))

        # 3. Food synthesis
        if self._food_synth:
            try:
                food_events = self._food_synth.simulate_year(year)
                for e in food_events:
                    events.append(SimulatorEvent(
                        mission_year=year,
                        category=e.get("category", "FOOD"),
                        severity=e.get("severity", "UNKNOWN"),
                        description=e.get("description", ""),
                        subsystem=e.get("subsystem", "food_synthesis"),
                        source="food_synthesis",
                    ))
            except Exception as e:
                logger.warning("subsystem.update_failed", subsystem="food_synthesis", error=str(e))

        # 4. Propulsion
        if self._propulsion:
            try:
                distance = self._base_sim.state.distance_ly if self._base_sim else 0
                prop_events = self._propulsion.simulate_year(
                    year, distance, self._total_distance,
                )
                for e in prop_events:
                    events.append(SimulatorEvent(
                        mission_year=year,
                        category=e.get("category", "PROPULSION"),
                        severity=e.get("severity", "UNKNOWN"),
                        description=e.get("description", ""),
                        subsystem=e.get("subsystem", "propulsion"),
                        source="propulsion",
                    ))
            except Exception as e:
                logger.warning("subsystem.update_failed", subsystem="propulsion", error=str(e))

        # 5. Manufacturing
        if self._manufacturing:
            try:
                mfg_events = self._manufacturing.simulate_year(year)
                for e in mfg_events:
                    events.append(SimulatorEvent(
                        mission_year=year,
                        category=e.get("category", "MANUFACTURING"),
                        severity=e.get("severity", "UNKNOWN"),
                        description=e.get("description", ""),
                        subsystem=e.get("subsystem", "manufacturing"),
                        source="manufacturing",
                    ))
            except Exception as e:
                logger.warning("subsystem.update_failed", subsystem="manufacturing", error=str(e))

        # 6. Defense
        if self._defense:
            try:
                def_events = self._defense.simulate_year(year, self._velocity_c)
                for e in def_events:
                    events.append(SimulatorEvent(
                        mission_year=year,
                        category=e.get("category", "DEFENSE"),
                        severity=e.get("severity", "UNKNOWN"),
                        description=e.get("description", ""),
                        subsystem=e.get("subsystem", "defense"),
                        source="defense",
                    ))
            except Exception as e:
                logger.warning("subsystem.update_failed", subsystem="defense", error=str(e))

        # 7. Breakthrough tech
        if self._breakthrough:
            try:
                bt_result = self._breakthrough.simulate_year(year)
                for e in bt_result.get("events", []):
                    events.append(SimulatorEvent(
                        mission_year=year,
                        category=e.get("category", "BREAKTHROUGH"),
                        severity=e.get("severity", "UNKNOWN"),
                        description=e.get("description", ""),
                        subsystem=e.get("subsystem", "breakthrough"),
                        source="breakthrough_tech",
                    ))
            except Exception as e:
                logger.warning("subsystem.update_failed", subsystem="breakthrough_tech", error=str(e))

        # 8. Crew ecosystem
        if self._crew_eco:
            try:
                crew_result = self._crew_eco.simulate_year(year)
                for e in crew_result.get("events", []):
                    events.append(SimulatorEvent(
                        mission_year=year,
                        category=e.get("category", "CREW"),
                        severity=e.get("severity", "UNKNOWN"),
                        description=e.get("description", ""),
                        subsystem=e.get("subsystem", "crew"),
                        source="crew_ecosystem",
                    ))
            except Exception as e:
                logger.warning("subsystem.update_failed", subsystem="crew_ecosystem", error=str(e))

        # 9. Shield system
        if self._shield:
            try:
                shield_events = self._shield.simulate_year(year)
                for e in shield_events:
                    events.append(SimulatorEvent(
                        mission_year=year,
                        category=e.get("category", "SHIELD"),
                        severity=e.get("severity", "UNKNOWN"),
                        description=e.get("description", ""),
                        subsystem=e.get("subsystem", "shield"),
                        source="shield_system",
                    ))
            except Exception as e:
                logger.warning("subsystem.update_failed", subsystem="shield", error=str(e))

        # 10. Advanced systems
        if self._advanced:
            try:
                adv_result = self._advanced.simulate_year(year)
                for e in adv_result.get("events", []):
                    events.append(SimulatorEvent(
                        mission_year=year,
                        category=e.get("category", "ADVANCED"),
                        severity=e.get("severity", "UNKNOWN"),
                        description=e.get("description", ""),
                        subsystem=e.get("subsystem", "advanced"),
                        source="advanced_systems",
                    ))
            except Exception as e:
                logger.warning("subsystem.update_failed", subsystem="advanced_systems", error=str(e))

        # Sync state from subsystems
        self._update_state_from_subsystems()

        return events

    def _update_3d_position(self) -> None:
        """Compute 3D position along the trajectory vector."""
        s = self._state
        t = s.mission_time_years

        # Distance traveled = integral of velocity over time
        # For simplicity with year-by-year velocity changes from base_sim:
        if self._base_sim:
            s.distance_traveled_ly = self._base_sim.state.distance_ly
            s.velocity_scalar_c = self._base_sim.state.velocity_c
        else:
            s.distance_traveled_ly = t * self._velocity_c
            s.velocity_scalar_c = self._velocity_c

        s.distance_remaining_ly = max(
            0.0, self._total_distance - s.distance_traveled_ly,
        )

        # Clamp: don't overshoot
        fraction = min(1.0, s.distance_traveled_ly / self._total_distance)

        # Linear interpolation along the direction vector
        s.position_3d = [
            s.origin[i] + fraction * (s.target[i] - s.origin[i])
            for i in range(3)
        ]

        # Velocity vector: current speed * direction
        v_c = s.velocity_scalar_c
        s.velocity_3d = [v_c * d for d in self._direction]

    def _update_state_from_subsystems(self) -> None:
        """Sync SimulatorState fields from underlying subsystem states."""
        s = self._state

        if self._base_sim:
            bs = self._base_sim.state
            s.hull_integrity = bs.hull_integrity
            s.fuel_kg = bs.fusion_fuel_kg
            s.fuel_fraction = bs.fusion_fuel_kg / bs.fuel_initial_kg
            s.power_watts = bs.total_power_watts
            s.rtg_power_fraction = bs.rtg_power_fraction
            s.reactor_health = bs.fusion_reactor_health
            # R8 (2026-04-24, sync refactor): when the base simulator
            # reports a crew change, push it into MissionState so the
            # rest of the system (crew_health, crew_schedule, agri,
            # advisor, telemetry) sees the new population on the same
            # tick.  Without this, a death event reaches the snapshot
            # but crew_size in those modules stayed pinned at 1000.
            try:
                from aria.core.mission_state import get_mission_state
                if int(bs.crew_count) != get_mission_state().crew_alive:
                    get_mission_state().set_crew_alive(int(bs.crew_count))
            except Exception:
                pass
            s.crew_count = bs.crew_count
            s.crew_generation = bs.crew_generation
            s.crew_morale = bs.crew_morale
            s.food_reserves_kg = bs.food_reserves_kg
            s.water_liters = bs.water_liters
            s.seed_viability = bs.seed_viability
            s.o2_reserves_kg = bs.o2_reserves_kg
            s.electronics_health = bs.electronics_health
            s.radiation_dose_krad = bs.total_radiation_dose_krad
            s.printer_health = bs.printer_health
            s.hydroponic_capacity = bs.hydroponic_capacity
            s.grow_light_health = bs.grow_light_health
            s.bioreactor_health = bs.algae_bioreactor_health
            s.knowledge_integrity = bs.knowledge_base_integrity
            s.ai_model_version = bs.ai_model_version
            s.micrometeorite_impacts = bs.micrometeorite_impacts
            s.spare_electronics = bs.spare_electronics
            s.spare_mechanical = bs.spare_mechanical
            s.phase = bs.phase

        # Subsystem health snapshots
        s.subsystems = {}

        s.subsystems["core_journey"] = SubsystemSnapshot(
            name="core_journey",
            health=s.hull_integrity,
            status=self._health_to_status(s.hull_integrity),
        )
        s.subsystems["power"] = SubsystemSnapshot(
            name="power",
            health=s.reactor_health,
            status=self._health_to_status(s.reactor_health),
            metrics={"watts": s.power_watts, "rtg_fraction": s.rtg_power_fraction},
        )
        s.subsystems["life_support"] = SubsystemSnapshot(
            name="life_support",
            health=min(
                s.food_reserves_kg / 10000.0,
                s.water_liters / 50000.0,
                1.0,
            ),
            status=self._food_status(s),
        )
        s.subsystems["electronics"] = SubsystemSnapshot(
            name="electronics",
            health=s.electronics_health,
            status=self._health_to_status(s.electronics_health),
            metrics={"radiation_krad": s.radiation_dose_krad},
        )
        s.subsystems["manufacturing"] = SubsystemSnapshot(
            name="manufacturing",
            health=s.printer_health,
            status=self._health_to_status(s.printer_health),
            metrics={"spare_elec": s.spare_electronics, "spare_mech": s.spare_mechanical},
        )
        s.subsystems["shield"] = SubsystemSnapshot(
            name="shield",
            health=s.shield_overall_health,
            status=self._health_to_status(s.shield_overall_health),
            metrics={"impacts": s.micrometeorite_impacts},
        )
        s.subsystems["crew"] = SubsystemSnapshot(
            name="crew",
            health=s.crew_morale,
            status="NOMINAL" if s.crew_morale > 0.4 else "WARNING" if s.crew_morale > 0.2 else "CRITICAL",
            metrics={"count": s.crew_count, "generation": s.crew_generation},
        )

    def _check_survival(self) -> None:
        """Check for mission-ending conditions."""
        s = self._state
        if not s.ship_survived:
            return  # Already failed

        # R8 (2026-04-24, sync refactor): read hull from the LIVE
        # hull_damage aggregator (worst-region health) and crew from
        # MissionState — the snapshot scalars `s.hull_integrity` and
        # `s.crew_count` are 1 tick stale, which let a ship "survive"
        # after a hull breach for a full tick.
        try:
            from aria.core.mission_state import get_mission_state
            ms = get_mission_state()
            live_hull_pct = ms.hull_integrity_pct
            live_crew     = ms.crew_alive
        except Exception:
            live_hull_pct = s.hull_integrity * 100.0  # back-compat fallback
            live_crew     = s.crew_count

        if live_hull_pct <= 0 or s.hull_integrity <= 0:
            s.ship_survived = False
            s.failure_reason = "HULL_BREACH: hull integrity reached zero"
        elif live_crew <= 0 or s.crew_count <= 0:
            s.ship_survived = False
            s.failure_reason = "CREW_EXTINCTION: no surviving crew"
        elif s.food_reserves_kg <= 0 and s.seed_viability <= 0:
            s.ship_survived = False
            s.failure_reason = "STARVATION: no food reserves and no viable seeds"

    def _compute_direction(self) -> list[float]:
        """Compute unit direction vector from origin to target."""
        pos = self._target.position_ly
        dist = self._target.distance_ly
        if dist < 1e-12:
            return [1.0, 0.0, 0.0]
        return [p / dist for p in pos]

    @staticmethod
    def _health_to_status(health: float) -> str:
        if health > 0.7:
            return "NOMINAL"
        elif health > 0.4:
            return "WARNING"
        elif health > 0.1:
            return "CRITICAL"
        else:
            return "OFFLINE"

    @staticmethod
    def _food_status(s: SimulatorState) -> str:
        if s.food_reserves_kg > 5000 and s.water_liters > 25000:
            return "NOMINAL"
        elif s.food_reserves_kg > 1000 and s.water_liters > 5000:
            return "WARNING"
        else:
            return "CRITICAL"

    def get_summary(self) -> dict[str, Any]:
        """Get a human-readable summary of the current simulation state."""
        s = self._state
        return {
            "target": self._target.display_name,
            "mission_year": round(s.mission_time_years, 2),
            "position_ly": [round(p, 4) for p in s.position_3d],
            "velocity_c": round(s.velocity_scalar_c, 6),
            "distance_traveled_ly": round(s.distance_traveled_ly, 2),
            "distance_remaining_ly": round(s.distance_remaining_ly, 2),
            "phase": s.phase,
            "hull_integrity": f"{s.hull_integrity:.1%}",
            "fuel_fraction": f"{s.fuel_fraction:.1%}",
            "crew": f"Gen {s.crew_generation}, {s.crew_count} people",
            "food_kg": round(s.food_reserves_kg),
            "water_l": round(s.water_liters),
            "ship_survived": s.ship_survived,
            "total_events": len(self._all_events),
            "ticks": self._tick_count,
            "timeline_snapshots": self._timeline.length,
        }


# ────────────────────────────────────────────────────────────────────
#  FACTORY — create missions with presets
# ────────────────────────────────────────────────────────────────────

class Simulator4D:
    """Factory for creating 4D generation ship simulations.

    Usage:
        sim = Simulator4D.create_mission("alpha_centauri")
        sim.run(years=43)

        # Or with custom parameters:
        sim = Simulator4D.create_mission(
            "tau_ceti", velocity_c=0.05, crew_size=100,
        )

        # Or fully custom target:
        sim = Simulator4D.create_custom(
            target_ly=[50.0, 10.0, -5.0],
            velocity_c=0.1,
        )
    """

    # Default cruise velocities per target (optimized for mission duration)
    _PRESET_VELOCITIES: dict[str, float] = {
        "alpha_centauri": 0.1,
        "proxima_centauri": 0.1,
        "barnards_star": 0.1,
        "wolf_359": 0.1,
        "lalande_21185": 0.1,
        "sirius": 0.1,
        "tau_ceti": 0.1,
        "epsilon_eridani": 0.1,
        "ross_128": 0.1,
        "trappist_1": 0.05,
        "100_ly_target": 0.1,
    }

    @classmethod
    def create_mission(
        cls,
        target_star: str,
        velocity_c: float | None = None,
        crew_size: int = 4,
        seed: int = 42,
        tick_resolution: TickResolution = TickResolution.YEAR,
        enable_all_subsystems: bool = True,
    ) -> SimulatorEngine:
        """Create a simulator for a preset mission.

        Args:
            target_star: Key from STAR_CATALOG (e.g., "alpha_centauri")
            velocity_c: Cruise velocity as fraction of c (default: preset per target)
            crew_size: Initial crew count
            seed: RNG seed for reproducibility
            tick_resolution: Time granularity per tick
            enable_all_subsystems: Whether to run all optional subsystems

        Returns:
            Initialized SimulatorEngine ready to run.
        """
        target = get_target(target_star)
        v = velocity_c or cls._PRESET_VELOCITIES.get(target_star, 0.1)

        engine = SimulatorEngine(
            target=target,
            velocity_c=v,
            crew_size=crew_size,
            seed=seed,
            tick_resolution=tick_resolution,
            enable_all_subsystems=enable_all_subsystems,
        )
        engine.initialize()

        logger.info(
            "simulator4d.mission_created",
            target=target.display_name,
            distance_ly=target.distance_ly,
            velocity_c=v,
            duration_years=round(target.distance_ly / v, 1),
            crew=crew_size,
        )
        return engine

    @classmethod
    def create_custom(
        cls,
        target_ly: list[float],
        target_name: str = "custom",
        velocity_c: float = 0.1,
        crew_size: int = 4,
        seed: int = 42,
        tick_resolution: TickResolution = TickResolution.YEAR,
    ) -> SimulatorEngine:
        """Create a simulator with a custom target position.

        Args:
            target_ly: [x, y, z] target position in light-years
            target_name: Display name for the target
            velocity_c: Cruise velocity
            crew_size: Initial crew count
            seed: RNG seed
            tick_resolution: Time granularity

        Returns:
            Initialized SimulatorEngine ready to run.
        """
        dist = math.sqrt(sum(c * c for c in target_ly))
        if dist < 1e-6:
            raise ValueError("Target must be at a nonzero distance from Sol")

        target = StarTarget(
            name=target_name,
            display_name=target_name,
            position_ly=list(target_ly),
            distance_ly=dist,
            spectral_type="unknown",
            mass_solar=1.0,
            habitable_zone_au=(0.9, 1.7),
            known_planets=0,
            notes="Custom target",
        )

        engine = SimulatorEngine(
            target=target,
            velocity_c=velocity_c,
            crew_size=crew_size,
            seed=seed,
            tick_resolution=tick_resolution,
        )
        engine.initialize()
        return engine

    @classmethod
    def list_presets(cls) -> list[dict[str, Any]]:
        """List all available mission presets with details."""
        presets = []
        for key in sorted(cls._PRESET_VELOCITIES.keys()):
            target = STAR_CATALOG[key]
            v = cls._PRESET_VELOCITIES[key]
            presets.append({
                "key": key,
                "name": target.display_name,
                "distance_ly": target.distance_ly,
                "velocity_c": v,
                "duration_years": round(target.distance_ly / v, 1),
                "known_planets": target.known_planets,
                "spectral_type": target.spectral_type,
            })
        return presets
