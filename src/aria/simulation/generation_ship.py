"""Complete Generation Ship Simulation — EVERYTHING integrated.

This is the MASTER simulation that combines all subsystems into one
coherent generation ship model for a 1000-year interstellar journey.

Systems integrated:
  FROM interstellar.py:         Core journey (fuel, radiation, hull, food, water, crew)
  FROM interstellar_challenges.py: 6 challenge simulators + cascade detection
  FROM food_synthesis.py:       Starch synthesizer + protein synthesis
  FROM food_synthesis.py:       Multi-mode propulsion (fusion + magsail + ramjet)
  FROM manufacturing.py:        4 printer types + von Neumann self-repair
  FROM defense.py:              Point defense + shields + internal security
  FROM breakthrough_tech.py:    Glass archive + nanobots + torpor + biomanufacturing
  FROM relativistic_physics.py: Exact γ, time dilation, ISM drag, radiation dose
  FROM quantum_timekeeping.py:  DSAC atomic clocks, optical lattice, QKD, quantum sensors
  FROM engineering_detail.py:   Power grid, EMC, atmospheric chemistry, structural fatigue
  FROM orbital_destination.py:  Capture orbit, Hohmann transfer at arrival

Two modes:
  1. LEGACY (no breakthrough tech) — simulates with 2024 technology only
  2. BREAKTHROUGH (with all tech) — simulates with emerging technology

This allows direct A/B comparison: does breakthrough tech save the mission?
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class GenerationShipConfig:
    """Configuration for the complete generation ship."""
    crew_size: int = 4                   # ESTIMATE — minimum viable crew for CI testing; Frankham 1995 MVP ≥50
    velocity_c: float = 0.1              # ESTIMATE — 10% c as representative interstellar cruise speed
    target_distance_ly: float = 100.0    # ESTIMATE — representative interstellar target (Alpha Cen: 4.37 ly; Proxima Cen b: 4.24 ly)
    seed: int = 42

    def __post_init__(self):
        """Validate inputs to prevent crashes from impossible configs."""
        self.velocity_c = max(0.001, min(0.999, self.velocity_c))
        self.crew_size = max(0, min(10_000, self.crew_size))
        self.target_distance_ly = max(0.001, self.target_distance_ly)

    # Toggle breakthrough technologies
    enable_starch_synthesis: bool = True
    enable_magsail: bool = True
    enable_nanobots: bool = True
    enable_torpor: bool = True
    enable_glass_archive: bool = True
    enable_biomanufacturing: bool = True
    enable_manufacturing: bool = True
    enable_defense: bool = True
    enable_advanced_systems: bool = True  # Radiation shielding, gravity, reactor, comms, recycling
    enable_crew_lifecycle: bool = True   # Individual crew members, education, ecosystem
    enable_braking_architecture: bool = True  # Forward staged-sail + magsail + fusion braking
    enable_relativistic_physics: bool = True  # Exact γ, time dilation, ISM drag, radiation dose
    enable_quantum_timekeeping: bool = True   # DSAC atomic clocks, optical lattice, QKD
    enable_engineering_detail: bool = True     # Power grid, EMC, atmo chemistry, structural fatigue
    enable_orbital_destination: bool = True    # Capture orbit, Hohmann transfer at arrival
    # Ship mass 1e8 kg = 100,000 tonnes — comparable to O'Neill Island One
    # concept (O'Neill 1977 *The High Frontier* Appendix A: Island 1 mass
    # estimate ~500,000 t unloaded structure + 100,000 t internal). 100 kt
    # is a conservative construction mass for a 1000-person vessel.
    ship_mass_kg: float = 1e8                 # O'Neill 1977 High Frontier Appendix A
    # Propellant from delta-v budget (deltav_budget.py): mid-course 51t +
    # final braking 511t + orbital insertion 445t + station-keeping 511t = 1,518t.
    # D-T fusion (Isp=100,000s) with laser-sail acceleration (Forward 1984).
    propellant_kg: float = 1_518_000          # deltav_budget.py Tsiolkovsky budget; matches interstellar.py fuel_initial_kg
    # 500 m² cross-section: hull diameter 25 m (π(12.5)²≈491 m²),
    # consistent with ISS cross-section ~73 m² truss × 7 modules
    # → scaled to 1000 crew from 6 crew gives ~500 m² (ESTIMATE).
    ship_cross_section_m2: float = 500.0      # ESTIMATE — scaled from ISS 73 m²/6 crew
    # 1 RPM habitat rotation: produces 0.56g at R=500m
    # (O'Neill 1977 *The High Frontier* §II rotation rate design).
    habitat_rpm: float = 1.0                  # O'Neill 1977 High Frontier §II
    strict_subsystems: bool = False           # Round 11: if True, re-raise init failures (for CI)

    @classmethod
    def legacy(cls, seed: int = 42) -> GenerationShipConfig:
        """2024 technology only — no breakthroughs."""
        return cls(
            seed=seed,
            enable_starch_synthesis=False,
            enable_magsail=False,
            enable_nanobots=False,
            enable_torpor=False,
            enable_glass_archive=False,
            enable_biomanufacturing=False,
            enable_braking_architecture=False,
            enable_relativistic_physics=False,
            enable_quantum_timekeeping=False,
            enable_engineering_detail=False,
            enable_orbital_destination=False,
        )

    @classmethod
    def breakthrough(cls, seed: int = 42) -> GenerationShipConfig:
        """All emerging technology enabled."""
        return cls(seed=seed)


@dataclass
class GenerationShipResults:
    """Results from a complete generation ship simulation."""
    config_mode: str = "BREAKTHROUGH"
    years_simulated: int = 0
    total_events: int = 0
    wall_time_s: float = 0.0

    # Survival
    ship_survived: bool = True
    year_of_failure: int | None = None
    failure_reason: str = ""

    # End state
    final_fuel_fraction: float = 0.0
    final_hull_integrity: float = 0.0
    final_crew_count: int = 0
    final_crew_generation: int = 0
    final_food_production_ratio: float = 0.0

    # Challenge outcomes
    challenges_terminal: int = 0
    challenge_details: dict[str, str] = field(default_factory=dict)

    # Relativistic physics
    lorentz_gamma: float = 1.0
    ship_time_years: float = 0.0
    earth_time_years: float = 0.0
    cumulative_dose_msv: float = 0.0

    # Quantum timekeeping
    clock_consensus_error_s: float = 0.0
    operational_clocks: int = 4

    # Engineering detail
    electrical_efficiency: float = 1.0
    structural_fatigue_damage: float = 0.0
    co2_ppm: float = 400.0

    # Breakthrough tech outcomes
    archive_intact: float = 1.0
    nanobot_repairs: int = 0
    torpor_food_saved_pct: float = 0.0

    # Events by severity
    severity_counts: dict[str, int] = field(default_factory=dict)
    # Per-subsystem × severity histogram: {"subsystem_name": {"CRITICAL": 12, "WARNING": 34}}
    subsystem_event_counts: dict[str, dict[str, int]] = field(default_factory=dict)

    # Navigation uncertainty budget (built at mission start from the
    # aria.physics.navigation_budget bridge module — contains one
    # row per bounded physical effect plus the quadrature total).
    navigation_budget: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"{'='*60}",
            f"  Generation Ship: {self.config_mode} mode",
            f"  {self.years_simulated} years simulated in {self.wall_time_s:.2f}s",
            f"{'='*60}",
            f"  Survived: {'YES' if self.ship_survived else 'NO (' + self.failure_reason + ')'}",
            f"  Final crew: Gen {self.final_crew_generation}, {self.final_crew_count} people",
            f"  Fuel remaining: {self.final_fuel_fraction:.1%}",
            f"  Hull integrity: {self.final_hull_integrity:.1%}",
            f"  Food ratio: {self.final_food_production_ratio:.1%}",
            f"  Challenges terminal: {self.challenges_terminal}/6",
        ]
        if self.lorentz_gamma > 1.001:
            lines.append(f"  Lorentz γ: {self.lorentz_gamma:.6f}")
            lines.append(f"  Ship time: {self.ship_time_years:.1f} yr (Earth: {self.earth_time_years:.1f} yr)")
            lines.append(f"  Radiation dose: {self.cumulative_dose_msv:.0f} mSv")
        if self.operational_clocks < 4:
            lines.append(f"  Clocks: {self.operational_clocks}/4, error {self.clock_consensus_error_s:.2e} s")
        if self.structural_fatigue_damage > 0.01:
            lines.append(f"  Fatigue damage: {self.structural_fatigue_damage:.3f}")
        if self.archive_intact < 1.0:
            lines.append(f"  Archive integrity: {self.archive_intact:.1%}")
        if self.nanobot_repairs > 0:
            lines.append(f"  Nanobot repairs: {self.nanobot_repairs:,}")
        if self.torpor_food_saved_pct > 0:
            lines.append(f"  Torpor food savings: {self.torpor_food_saved_pct:.0f}%")
        if self.severity_counts:
            lines.append(f"  Events: {dict(self.severity_counts)}")
        return "\n".join(lines)


class GenerationShipSimulation:
    """The complete generation ship simulation.

    Runs all subsystems year by year for up to 1000 years.
    """

    def __init__(self, config: GenerationShipConfig | None = None) -> None:
        self._config = config or GenerationShipConfig()
        self._results = GenerationShipResults()

    def run(self, years: int | None = None) -> GenerationShipResults:
        """Run the complete simulation."""
        cfg = self._config
        total_years = years or int(cfg.target_distance_ly / cfg.velocity_c)
        t0 = time.time()

        self._results.config_mode = "BREAKTHROUGH" if cfg.enable_starch_synthesis else "LEGACY"

        # Build and log a Phase-4 navigation uncertainty budget at
        # mission start. Pulls primitives from cruise_drag (ISM ram
        # drag, Chandrasekhar dynamical friction) and dark_sector
        # (XENONnT-bounded DM drag) and propagates each into a
        # quadrature-summed position error at arrival. This is a
        # bookkeeping pass - no simulator state is altered.
        try:
            from aria.physics.navigation_budget import (
                MissionProfile,
                build_navigation_budget,
            )

            _c_m_s = 299792458.0        # NIST CODATA 2018 exact (Tiesinga 2021 Rev Mod Phys 93 025010)
            _ly_m = 9.4607304725808e15  # IAU 2012 Resolution B2 light-year [m]
            nav_profile = MissionProfile(
                name=f"GenShip {cfg.target_distance_ly} ly @ {cfg.velocity_c:.2f}c",
                ship_mass_kg=cfg.ship_mass_kg,
                cross_section_m2=cfg.ship_cross_section_m2,
                cruise_velocity_m_s=cfg.velocity_c * _c_m_s,
                leg_distance_m=cfg.target_distance_ly * _ly_m,
                is_intergalactic=False,
            )
            nav_budget = build_navigation_budget(nav_profile)
            self._results.navigation_budget = {
                "total_position_error_m": nav_budget.total_position_error_m,
                "stopping_length_m": nav_budget.stopping_length_m,
                "is_drag_limited": nav_budget.is_drag_limited,
                "rows": [
                    {
                        "name": row.name,
                        "category": row.effect_category,
                        "value": row.perturbation_value,
                        "units": row.units,
                        "source": row.source,
                    }
                    for row in nav_budget.rows
                ],
            }
            logger.info(
                "navigation_budget.build",
                name=nav_profile.name,
                total_error_m=nav_budget.total_position_error_m,
                is_drag_limited=nav_budget.is_drag_limited,
                num_rows=len(nav_budget.rows),
            )
        except Exception as e:
            logger.warning("navigation_budget.build_failed", error=str(e))

        # Initialize subsystems
        from aria.simulation.interstellar import InterstellarSimulation
        from aria.simulation.interstellar_challenges import InterstellarChallengeOrchestrator

        base_sim = InterstellarSimulation(
            cruise_velocity_c=cfg.velocity_c, crew_size=cfg.crew_size, seed=cfg.seed
        )
        challenges = InterstellarChallengeOrchestrator(
            crew_size=cfg.crew_size,
            seed=cfg.seed,
            target_distance_ly=cfg.target_distance_ly,
            cruise_velocity_c=cfg.velocity_c,
        )

        # Optional breakthrough tech
        food_synth = None
        propulsion = None
        manufacturing = None
        defense = None
        breakthrough = None

        if cfg.enable_starch_synthesis:
            from aria.simulation.food_synthesis import FoodSynthesisSimulator
            food_synth = FoodSynthesisSimulator(crew_size=cfg.crew_size, seed=cfg.seed)

        if cfg.enable_magsail:
            from aria.simulation.food_synthesis import PropulsionSimulator
            propulsion = PropulsionSimulator(seed=cfg.seed)

        if cfg.enable_manufacturing:
            from aria.simulation.manufacturing import ManufacturingSimulator
            manufacturing = ManufacturingSimulator(seed=cfg.seed)

        if cfg.enable_defense:
            from aria.simulation.defense import DefenseSimulator
            defense = DefenseSimulator(crew_size=cfg.crew_size, seed=cfg.seed)

        if cfg.enable_glass_archive or cfg.enable_nanobots or cfg.enable_torpor:
            from aria.simulation.breakthrough_tech import BreakthroughTechOrchestrator
            breakthrough = BreakthroughTechOrchestrator(
                crew_size=cfg.crew_size, seed=cfg.seed
            )

        advanced = None
        if cfg.enable_advanced_systems:
            from aria.simulation.advanced_systems import AdvancedSystemsOrchestrator
            advanced = AdvancedSystemsOrchestrator(seed=cfg.seed)

        crew_eco = None
        if cfg.enable_crew_lifecycle:
            try:
                # Round 11 fix: orchestrator only accepts seed (crew_size not a kwarg)
                from aria.simulation.crew_ecosystem import CrewEcosystemOrchestrator
                crew_eco = CrewEcosystemOrchestrator(seed=cfg.seed)
            except Exception as e:
                logger.warning("subsystem.init_failed", subsystem="crew_ecosystem", error=str(e))

        # New systems from scientist interrogation
        thermal = None
        fire = None
        governance = None
        critical = None
        biology = None
        try:
            from aria.simulation.thermal_management import ThermalManagementSimulator
            thermal = ThermalManagementSimulator(seed=cfg.seed)
        except Exception as e:
            logger.warning("subsystem.init_failed", subsystem="thermal", error=str(e))
        try:
            from aria.simulation.fire_safety import FireSafetySimulator
            fire = FireSafetySimulator(seed=cfg.seed, crew_size=cfg.crew_size)
        except Exception as e:
            logger.warning("subsystem.init_failed", subsystem="fire_safety", error=str(e))
        try:
            from aria.simulation.governance import GovernanceSimulator
            governance = GovernanceSimulator(crew_size=cfg.crew_size, seed=cfg.seed)
        except Exception as e:
            logger.warning("subsystem.init_failed", subsystem="governance", error=str(e))
        try:
            from aria.simulation.critical_systems import (
                EpidemicSimulator, WiringDegradationSimulator,
                PowerDistributionSimulator, NeutronActivationSimulator,
            )
            critical = {
                "epidemic": EpidemicSimulator(population=cfg.crew_size, seed=cfg.seed),
                "wiring": WiringDegradationSimulator(seed=cfg.seed),
                "power": PowerDistributionSimulator(seed=cfg.seed),
                "neutron": NeutronActivationSimulator(seed=cfg.seed),
            }
        except Exception as e:
            logger.warning("subsystem.init_failed", subsystem="critical_systems", error=str(e))
        try:
            # Round 11 fix: corrected class names (was WaterQualitySimulator/
            # EcosystemBiologySimulator/LanguageDriftSimulator — none existed)
            from aria.simulation.biology_social import (
                BiofilmWaterSimulator, FungalPollinatorSimulator,
                LanguageCultureSimulator,
            )
            biology = {
                "water": BiofilmWaterSimulator(seed=cfg.seed),
                "ecosystem": FungalPollinatorSimulator(seed=cfg.seed),
                "language": LanguageCultureSimulator(seed=cfg.seed),
            }
        except Exception as e:
            logger.warning("subsystem.init_failed", subsystem="biology_social", error=str(e))

        # Remaining P1 systems from scientist interrogation
        remaining = None
        try:
            from aria.simulation.remaining_systems import (
                StellarProperMotionSimulator, OortCloudSimulator,
                ComputingRegressionSimulator, SealGasketSimulator,
                CatalystLifecycleSimulator, GravityFertilitySimulator,
            )
            remaining = {
                "stellar_motion": StellarProperMotionSimulator(seed=cfg.seed),
                "oort_cloud": OortCloudSimulator(seed=cfg.seed),
                "computing": ComputingRegressionSimulator(seed=cfg.seed),
                "seals": SealGasketSimulator(seed=cfg.seed),
                "catalysts": CatalystLifecycleSimulator(seed=cfg.seed),
                "fertility": GravityFertilitySimulator(seed=cfg.seed),
            }
        except Exception as e:
            logger.warning("subsystem.init_failed", subsystem="remaining_systems", error=str(e))

        # Medical + internal maintenance robotics
        med_robotics = None
        try:
            from aria.simulation.medical_robotics import MedicalRoboticsOrchestrator
            med_robotics = MedicalRoboticsOrchestrator(
                crew_size=cfg.crew_size, seed=cfg.seed
            )
        except Exception as e:
            logger.warning("subsystem.init_failed", subsystem="medical_robotics", error=str(e))

        # Habitat systems (HVAC, recreation, supply chain)
        habitat = None
        try:
            from aria.simulation.habitat_systems import HabitatSystemsOrchestrator
            habitat = HabitatSystemsOrchestrator(crew_size=cfg.crew_size, seed=cfg.seed)
        except Exception as e:
            logger.warning("subsystem.init_failed", subsystem="habitat", error=str(e))

        # Braking architecture (Forward staged-sail + magsail + fusion)
        braking = None
        if cfg.enable_braking_architecture:
            try:
                from aria.simulation.braking_architecture import BrakingSimulator
                braking = BrakingSimulator(
                    target_distance_ly=cfg.target_distance_ly,
                    cruise_velocity_c=cfg.velocity_c,
                    seed=cfg.seed,
                )
            except Exception as e:
                logger.warning("subsystem.init_failed", subsystem="braking", error=str(e))

        # ── Relativistic physics ──
        rel_state = None
        if cfg.enable_relativistic_physics:
            try:
                from aria.simulation.relativistic_physics import (
                    RelativisticShipState, step_physics,
                )
                rel_state = RelativisticShipState(
                    velocity_ms=cfg.velocity_c * 299_792_458.0,  # NIST CODATA 2018 c [m/s]
                    velocity_beta=cfg.velocity_c,
                    propellant_remaining_kg=base_sim.state.fusion_fuel_kg,
                )
            except Exception as e:
                logger.warning("subsystem.init_failed", subsystem="relativistic_physics", error=str(e))

        # ── Quantum timekeeping ──
        timekeeping = None
        quantum_suite = None
        if cfg.enable_quantum_timekeeping:
            try:
                from aria.simulation.quantum_timekeeping import (
                    ShipTimekeepingSystem, ShipQuantumSuite,
                )
                timekeeping = ShipTimekeepingSystem()
                quantum_suite = ShipQuantumSuite()
            except Exception as e:
                logger.warning("subsystem.init_failed", subsystem="quantum_timekeeping", error=str(e))

        # ── Engineering detail (4 simulators) ──
        engineering = None
        if cfg.enable_engineering_detail:
            try:
                from aria.simulation.engineering_detail import (
                    PowerDistributionSimulator, EMCSimulator,
                    AtmosphericChemistrySimulator, StructuralFatigueSimulator,
                )
                engineering = {
                    "power": PowerDistributionSimulator(
                        # 66 MWe thermal conversion: ITER 2018 Nucl Fusion 58 115001 D-T thermal-to-electric ~33%
                        # 200 MW_thermal × 0.33 = 66 MWe; ESTIMATE — scaled from ITER baseline
                        reactor_output_w=66_000_000, seed=cfg.seed  # ITER 2018 Nucl Fusion 58 115001 scaled
                    ),
                    "emc": EMCSimulator(seed=cfg.seed),
                    "atmosphere": AtmosphericChemistrySimulator(
                        crew_size=cfg.crew_size, seed=cfg.seed
                    ),
                    "fatigue": StructuralFatigueSimulator(
                        rpm=cfg.habitat_rpm, seed=cfg.seed,
                        fea_stress_mpa=(
                            twin_result.max_von_mises_mpa
                            if twin_result is not None else None
                        ),
                    ),
                }
            except Exception as e:
                logger.warning("subsystem.init_failed", subsystem="engineering_detail", error=str(e))

        # ── Crop rotation optimizer (GA-optimized hydroponics) ──
        crop_optimizer = None
        try:
            from aria.simulation.crop_optimizer import CropRotationOptimizer
            crop_optimizer = CropRotationOptimizer(
                crew_size=cfg.crew_size, seed=cfg.seed
            )
        except Exception as e:
            logger.warning("subsystem.init_failed", subsystem="crop_optimizer", error=str(e))

        # ── Orbital destination (event-driven at arrival) ──
        destination = None
        if cfg.enable_orbital_destination:
            try:
                from aria.simulation.orbital_destination import DestinationArrivalSimulator
                destination = DestinationArrivalSimulator(
                    ship_mass_kg=cfg.ship_mass_kg,
                    habitat_rpm=cfg.habitat_rpm,
                )
            except Exception as e:
                logger.warning("subsystem.init_failed", subsystem="orbital_destination", error=str(e))

        # ── Reactor neutronics (fusion D-T cycle, neutron damage, activation) ──
        reactor_neutronics = None
        try:
            from aria.simulation.reactor_neutronics import ReactorNeutronicsSimulator
            reactor_neutronics = ReactorNeutronicsSimulator(seed=cfg.seed)
        except Exception as e:
            logger.warning("subsystem.init_failed", subsystem="reactor_neutronics", error=str(e))

        # ── Magsail PIC interaction model ──
        magsail_pic = None
        if cfg.enable_magsail:
            try:
                from aria.simulation.magsail_pic import MagsailPICSimulator
                magsail_pic = MagsailPICSimulator(
                    ship_mass_kg=cfg.ship_mass_kg, seed=cfg.seed
                )
            except Exception as e:
                logger.warning("subsystem.init_failed", subsystem="magsail_pic", error=str(e))

        # ── Radiation transport (Monte Carlo through 7-layer shield) ──
        radiation_transport = None
        try:
            # Round 11 fix: shield_layers was missing (class requires it positionally)
            from aria.simulation.radiation_transport import (
                RadiationTransportSimulator, default_shield_layers,
            )
            radiation_transport = RadiationTransportSimulator(
                shield_layers=default_shield_layers(), seed=cfg.seed
            )
        except Exception as e:
            logger.warning("subsystem.init_failed", subsystem="radiation_transport", error=str(e))

        # ── Microbiome evolution (gut, surface, soil, water) ──
        microbiome = None
        try:
            from aria.simulation.microbiome_evolution import MicrobiomeEvolutionSimulator
            microbiome = MicrobiomeEvolutionSimulator(
                crew_size=cfg.crew_size, seed=cfg.seed
            )
        except Exception as e:
            logger.warning("subsystem.init_failed", subsystem="microbiome", error=str(e))

        # ── Anomaly detection (PCA-based, NASA C-MAPSS derived) ──
        anomaly_monitor = None
        anomaly_prev_scores: dict[str, float] = {}
        try:
            from aria.simulation.anomaly_detection import ShipAnomalyMonitor
            anomaly_monitor = ShipAnomalyMonitor(seed=cfg.seed)
        except Exception as e:
            logger.warning("subsystem.init_failed", subsystem="anomaly_monitor", error=str(e))

        # ── Crew sleep model (NASA LSDA actigraphy data) ──
        sleep_sim = None
        try:
            from aria.simulation.sleep_model import CrewSleepSimulator
            sleep_sim = CrewSleepSimulator(
                crew_size=cfg.crew_size,
                gravity_g=0.56,  # O'Neill 1977 High Frontier §II: 1 RPM at R=500m → g=ω²R=0.55g
                seed=cfg.seed,
            )
        except Exception as e:
            logger.warning("subsystem.init_failed", subsystem="sleep", error=str(e))

        # ── Mass conservation ledger (atom-level O2/CO2/H2O/N2 tracking) ──
        mass_ledger = None
        try:
            from aria.simulation.mass_conservation import MassConservationSimulator
            mass_ledger = MassConservationSimulator(
                crew_size=cfg.crew_size, seed=cfg.seed
            )
        except Exception as e:
            logger.warning("subsystem.init_failed", subsystem="mass_ledger", error=str(e))

        # Round 11: strict mode — verify critical subsystems initialized
        if cfg.strict_subsystems:
            critical_subsystems = {
                "biology": biology,
                "radiation_transport": radiation_transport,
                "crew_eco": crew_eco,
                "thermal": thermal,
                "reactor_neutronics": reactor_neutronics,
            }
            missing = [name for name, obj in critical_subsystems.items() if obj is None]
            if missing:
                raise RuntimeError(
                    f"strict_subsystems=True: the following critical subsystems "
                    f"failed to initialize: {missing}"
                )

        severity_counts: dict[str, int] = {}
        # Per-(subsystem, severity) histogram so end-of-run diagnostics show
        # exactly which subsystems emit the most alarm traffic. Logged at the
        # end of the run via structlog so we can tell at a glance which
        # subsystem is drowning the console with CRITICAL/EMERGENCY events.
        subsystem_severity: dict[tuple[str, str], int] = {}

        def _sev_and_sub(event: Any, fallback: str) -> tuple[str, str]:
            # Dataclass YearEvent has .severity / .subsystem attrs;
            # dict events carry "severity" and "subsystem" keys.
            if hasattr(event, "severity"):
                sev = str(event.severity)
                sub = getattr(event, "subsystem", fallback) or fallback
            else:
                sev = event.get("severity", "UNKNOWN")
                sub = event.get("subsystem", fallback) or fallback
            return sev, sub

        def _tally(sev: str, subsystem: str) -> None:
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            key = (subsystem or "unknown", sev)
            subsystem_severity[key] = subsystem_severity.get(key, 0) + 1

        def _tally_events(events: Any, fallback: str) -> int:
            n = 0
            if not events:
                return 0
            for ev in events:
                sev, sub = _sev_and_sub(ev, fallback)
                _tally(sev, sub)
                n += 1
            return n

        # ── Pre-simulation digital twin analysis (closed feedback loop) ──
        # Run the FEA before the sim starts so the simulation uses physically
        # consistent mass, stress limits, and thermal margins from actual geometry.
        twin_result = None
        try:
            from aria.digital_twin.bridge import SimTwinBridge
            twin_bridge = SimTwinBridge()
            twin_result = twin_bridge.analyze(cfg)
            # Feed geometry-derived mass back into config (closes the loop)
            twin_bridge.update_config(cfg, twin_result)
            logger.info(
                "digital_twin.pre_analysis",
                mass_kg=twin_result.computed_mass_kg,
                stress_mpa=twin_result.max_von_mises_mpa,
                safety_factor=twin_result.structural_safety_factor,
                temp_k=twin_result.max_temperature_k,
            )
            if twin_result.structural_safety_factor < 2.0:
                _tally("CRITICAL", "digital_twin")
                self._results.total_events += 1
        except Exception as e:
            logger.warning("digital_twin.pre_analysis_failed", error=str(e))

        # Proper time (ship time) accumulator — diverges from coordinate time at relativistic v
        # At 0.1c: γ=1.005, ship ages 0.5% slower than Earth clocks
        ship_year_accumulator = 0.0

        for year in range(1, total_years + 1):
            # Compute proper time increment (ship time < coordinate time)
            gamma = rel_state.lorentz_gamma if rel_state else 1.0
            ship_dt = 1.0 / max(gamma, 1.0)  # Proper time per coordinate year
            ship_year_accumulator += ship_dt

            # ── Early termination: ship destroyed or crew extinct ──
            if base_sim.state.hull_integrity <= 0:
                self._results.ship_survived = False
                self._results.year_of_failure = year
                self._results.failure_reason = "Hull breach — total structural failure"
                break
            if base_sim.state.crew_count <= 0:
                self._results.ship_survived = False
                self._results.year_of_failure = year
                self._results.failure_reason = "Crew extinction"
                break
            if base_sim.state.total_power_watts <= 0 and base_sim.state.fusion_fuel_kg <= 0:
                self._results.ship_survived = False
                self._results.year_of_failure = year
                self._results.failure_reason = "Total power loss — fuel exhausted, no backup"
                break
            if thermal and thermal.state.cabin_temp_c > 60:
                self._results.ship_survived = False
                self._results.year_of_failure = year
                self._results.failure_reason = f"Lethal temperature: {thermal.state.cabin_temp_c:.0f}°C"
                break

            # ── Propagate live crew count to ALL subsystems ──
            live_crew = base_sim.state.crew_count
            for obj in [food_synth, sleep_sim, mass_ledger, crop_optimizer,
                        governance, med_robotics, habitat, defense]:
                if obj is not None:
                    for attr in ('_crew_size', '_crew', '_population'):
                        if hasattr(obj, attr):
                            setattr(obj, attr, live_crew)
                            break
            if critical and "epidemic" in critical:
                epi = critical["epidemic"]
                if hasattr(epi, 'state') and hasattr(epi.state, 'population'):
                    epi.state.population = live_crew

            # Core simulation (uses coordinate time for distance tracking)
            year_events = base_sim.simulate_year()
            cr = challenges.simulate_year(float(year), base_sim.state.distance_ly)

            # Count events
            _tally_events(year_events, fallback="base_sim")
            _tally_events(cr["events"], fallback="challenges")

            # Breakthrough tech
            food_events: list = []
            if food_synth:
                food_events = food_synth.simulate_year(float(year))
                _tally_events(food_events, fallback="food_synth")

            prop_events: list = []
            if propulsion:
                prop_events = propulsion.simulate_year(
                    float(year), base_sim.state.distance_ly, cfg.target_distance_ly
                )
                _tally_events(prop_events, fallback="propulsion")

            mfg_events: list = []
            if manufacturing:
                mfg_events = manufacturing.simulate_year(float(year))
                _tally_events(mfg_events, fallback="manufacturing")

            def_events: list = []
            if defense:
                def_events = defense.simulate_year(float(year), cfg.velocity_c)
                _tally_events(def_events, fallback="defense")

            bt_result = None
            if breakthrough:
                bt_result = breakthrough.simulate_year(float(year))
                _tally_events(bt_result["events"], fallback="breakthrough")

            adv_events: list[dict[str, Any]] = []
            if advanced:
                adv_result = advanced.simulate_year(float(year))
                adv_events = adv_result.get("events", [])
                _tally_events(adv_events, fallback="advanced")

            crew_events: list[dict[str, Any]] = []
            if crew_eco:
                try:
                    crew_result = crew_eco.simulate_year(float(year))
                    crew_events = crew_result.get("events", [])
                    _tally_events(crew_events, fallback="crew_ecosystem")
                except Exception as e:
                    logger.warning("subsystem.update_failed", subsystem="crew_ecosystem", error=str(e))

            # New scientist-identified systems
            extra_events = 0
            if thermal:
                extra_events += _tally_events(thermal.simulate_year(float(year)), fallback="thermal")
            if fire:
                extra_events += _tally_events(fire.simulate_year(float(year)), fallback="fire")
            if governance:
                extra_events += _tally_events(governance.simulate_year(float(year)), fallback="governance")
            if critical:
                for name, sim in critical.items():
                    try:
                        extra_events += _tally_events(sim.simulate_year(float(year)), fallback=f"critical.{name}")
                    except Exception as e:
                        logger.warning("subsystem.update_failed", subsystem=f"critical.{name}", error=str(e))
            if biology:
                for name, sim in biology.items():
                    extra_events += _tally_events(sim.simulate_year(float(year)), fallback=f"biology.{name}")
            if remaining:
                for name, sim in remaining.items():
                    try:
                        extra_events += _tally_events(sim.simulate_year(float(year)), fallback=f"remaining.{name}")
                    except Exception as e:
                        logger.warning("subsystem.update_failed", subsystem=f"remaining.{name}", error=str(e))
            if med_robotics:
                try:
                    mr_result = med_robotics.simulate_year(float(year))
                    med_events = mr_result if isinstance(mr_result, list) else mr_result.get("events", [])
                    before = severity_counts.get("FATAL", 0)
                    extra_events += _tally_events(med_events, fallback="medical_robotics")
                    fatal_this_year = severity_counts.get("FATAL", 0) - before
                    # Medical FATAL events are tracked by med_robotics internally
                    # for reporting. The authoritative crew_count lives in
                    # base_sim (which applies hull-breach, power-loss, and
                    # radiation-casualty attrition). Feeding medical FATALs
                    # into crew_count double-counted deaths and caused
                    # unrealistic extinction for small crews. Only feed back
                    # when strict_subsystems is on AND crew is large enough
                    # for medical stochasticity to be meaningful (≥100).
                    if (
                        fatal_this_year
                        and cfg.strict_subsystems
                        and base_sim.state.crew_count >= 100
                    ):
                        base_sim.state.crew_count = max(
                            0, base_sim.state.crew_count - fatal_this_year
                        )
                except Exception as e:
                    logger.warning("subsystem.update_failed", subsystem="medical_robotics", error=str(e))
            if habitat:
                try:
                    hab_result = habitat.simulate_year(float(year))
                    habitat_events = hab_result if isinstance(hab_result, list) else hab_result.get("events", [])
                    extra_events += _tally_events(habitat_events, fallback="habitat")
                except Exception as e:
                    logger.warning("subsystem.update_failed", subsystem="habitat", error=str(e))

            # Braking architecture (Forward staged-sail deceleration)
            braking_events = 0
            if braking:
                try:
                    braking_result = braking.simulate_year(year)
                    braking_events = _tally_events(braking_result.events, fallback="braking")
                except Exception as e:
                    logger.warning("subsystem.update_failed", subsystem="braking", error=str(e))

            # ── Relativistic physics (exact γ, time dilation, ISM drag) ──
            rel_events = 0
            if rel_state is not None:
                try:
                    from aria.simulation.relativistic_physics import step_physics
                    # Sync fuel state: interstellar → relativistic physics
                    rel_state.propellant_remaining_kg = base_sim.state.fusion_fuel_kg
                    # Live ship mass = config dry mass + remaining fuel
                    live_ship_mass = cfg.ship_mass_kg - cfg.propellant_kg + base_sim.state.fusion_fuel_kg
                    # Get current thrust from propulsion if available
                    thrust = 0.0
                    if braking and hasattr(braking, 'state'):
                        thrust = getattr(braking.state, 'current_thrust_n', 0.0)
                    rel_warnings = step_physics(
                        rel_state,
                        dt_earth_years=1.0,
                        thrust_n=thrust,
                        ship_mass_kg=max(live_ship_mass, 1e6),
                        cross_section_m2=cfg.ship_cross_section_m2,
                    )
                    for msg in rel_warnings:
                        sev = "WARNING" if "WARNING" in msg.upper() else "NOMINAL"
                        _tally(sev, "relativistic_physics")
                        rel_events += 1
                except Exception as e:
                    logger.warning("subsystem.update_failed", subsystem="relativistic_physics", error=str(e))

            # ── Quantum timekeeping (atomic clocks, QKD, sensors) ──
            tk_events = 0
            if timekeeping is not None:
                try:
                    velocity_ms = rel_state.velocity_ms if rel_state else cfg.velocity_c * 299_792_458.0  # NIST CODATA 2018
                    tk_result = timekeeping.simulate_year(velocity_ms=velocity_ms)
                    # Clock failures are events
                    if tk_result.get("total_failures", 0) > 0:
                        _tally("WARNING", "timekeeping")
                        tk_events += 1
                    if tk_result.get("n_operational_dsac", 3) == 0:
                        _tally("CRITICAL", "timekeeping")
                        tk_events += 1
                except Exception as e:
                    logger.warning("subsystem.update_failed", subsystem="timekeeping", error=str(e))
            if quantum_suite is not None:
                try:
                    qs_result = quantum_suite.simulate_year()
                    if not qs_result.get("all_operational", True):
                        _tally("WARNING", "quantum_suite")
                        tk_events += 1
                except Exception as e:
                    logger.warning("subsystem.update_failed", subsystem="quantum_suite", error=str(e))

            # ── Engineering detail (power, EMC, atmosphere, fatigue) ──
            eng_events = 0
            if engineering:
                for eng_name, eng_sim in engineering.items():
                    try:
                        eng_events += _tally_events(
                            eng_sim.simulate_year(float(year)),
                            fallback=f"engineering.{eng_name}",
                        )
                    except Exception as e:
                        logger.warning("subsystem.update_failed", subsystem=f"engineering.{eng_name}", error=str(e))

            # ── Crop rotation optimizer ──
            crop_events = 0
            if crop_optimizer:
                try:
                    crop_events = _tally_events(crop_optimizer.simulate_year(float(year)), fallback="crop_optimizer")
                except Exception as e:
                    logger.warning("subsystem.update_failed", subsystem="crop_optimizer", error=str(e))

            # ── Reactor neutronics (D-T fuel cycle, neutron damage) ──
            reactor_events = 0
            if reactor_neutronics:
                try:
                    reactor_events = _tally_events(reactor_neutronics.simulate_year(float(year)), fallback="reactor_neutronics")
                except Exception as e:
                    logger.warning("subsystem.update_failed", subsystem="reactor_neutronics", error=str(e))

            # ── Magsail PIC interaction ──
            magsail_events = 0
            if magsail_pic:
                try:
                    vel_c = rel_state.velocity_beta if rel_state else cfg.velocity_c
                    magsail_events = _tally_events(magsail_pic.simulate_year(float(year), velocity_c=vel_c), fallback="magsail_pic")
                except Exception as e:
                    logger.warning("subsystem.update_failed", subsystem="magsail_pic", error=str(e))

            # ── Radiation transport (Monte Carlo shield dose) ──
            rad_transport_events = 0
            if radiation_transport:
                try:
                    rad_transport_events = _tally_events(radiation_transport.simulate_year(float(year)), fallback="radiation_transport")
                except Exception as e:
                    logger.warning("subsystem.update_failed", subsystem="radiation_transport", error=str(e))

            # ── Microbiome evolution ──
            microbiome_events = 0
            if microbiome:
                try:
                    microbiome_events = _tally_events(microbiome.simulate_year(float(year)), fallback="microbiome")
                except Exception as e:
                    logger.warning("subsystem.update_failed", subsystem="microbiome", error=str(e))

            # ── Crew sleep (NASA LSDA actigraphy) ──
            sleep_events = 0
            if sleep_sim:
                try:
                    noise = 40.0  # NASA-STD-3001 Vol.2 §4.12: quiet zone target ≤ 40 dBA during sleep
                    sleep_events = _tally_events(sleep_sim.simulate_year(float(year), noise_db=noise), fallback="sleep")
                except Exception as e:
                    logger.warning("subsystem.update_failed", subsystem="sleep", error=str(e))

            # ── Mass conservation ledger (O2/CO2/H2O/N2 atom tracking) ──
            mass_events = 0
            if mass_ledger:
                try:
                    mass_events = _tally_events(mass_ledger.simulate_year(float(year)), fallback="mass_ledger")
                    # Sync mass ledger → interstellar.py water (single source of truth)
                    base_sim.state.water_liters = mass_ledger.state.h2o_kg  # kg ≈ liters for water
                except Exception as e:
                    logger.warning("subsystem.update_failed", subsystem="mass_ledger", error=str(e))

            # ── Anomaly detection scan ──
            # Dedupe static false-positives: the PCA detectors flag constant
            # telemetry every single year, which drowns the log. Only raise
            # an anomaly when the score *grows* year-over-year (a real
            # degradation trend), not on repeated identical readings.
            anomaly_events = 0
            if anomaly_monitor:
                try:
                    # Round 13 fix: feed real telemetry instead of empty dict
                    # Detectors: reactor, pump, bearing, electronics, co2_scrubber
                    # Nominal telemetry reference values for anomaly baseline.
                    # Reactor: ITER 2018 Nucl Fusion 58 115001 D-T plasma parameters.
                    # Pump: ESTIMATE — scaled from ISS WRS coolant specs (NASA SSP 30482).
                    # Bearing: ISO 10816-1:1995 Table 1 zone A (good operation).
                    # Electronics: JEDEC JESD91A typical board/junction temps; NASA SSP 30482 28V DC bus.
                    # CO2 scrubber: NASA BVAD §4.1; NASA-STD-3001 Vol.1 §4.5.
                    telemetry = {
                        "reactor": {
                            "core_temp_K": 1500.0 + (0 if reactor_neutronics is None
                                                     else reactor_neutronics.state.tritium_inventory_kg * 0.1),
                            # 500 kPa plasma-facing component coolant pressure — ITER 2018 Nucl Fusion 58 115001
                            "plasma_pressure_kPa": 500.0,  # ITER 2018 Nucl Fusion 58 115001
                            "fuel_flow_ratio": base_sim.state.fusion_fuel_kg / max(base_sim.state.fuel_initial_kg, 1),
                            "neutron_flux_rel": 1.0 * base_sim.state.fusion_reactor_health,
                            "coolant_flow_kg_s": 100.0,  # ESTIMATE — ITER 2018 NaK coolant flow scale
                            "vibration_mm_s": 2.0,       # ESTIMATE — ISO 10816-1 zone A/B boundary
                            "magnetic_field_T": 8.0,     # ITER 2018 Nucl Fusion 58 115001: TF coil 8 T
                            "power_output_MW": base_sim.state.total_power_watts / 1e6,
                        },
                        "pump": {
                            "discharge_pressure_kPa": 300.0,  # ESTIMATE — Carter 2014 ICES-0024 WRS pump
                            "suction_pressure_kPa": 100.0,    # ESTIMATE — standard centrifugal pump inlet
                            "flow_rate_L_min": 500.0,         # ESTIMATE — scaled from ISS WRS 500 L/day
                            "motor_current_A": 25.0,          # ESTIMATE — medium-duty pump motor current
                            "vibration_mm_s": 1.5,            # ISO 10816-1:1995 Table 1 zone A nominal
                            "bearing_temp_C": 60.0,           # ESTIMATE — bearing operating 40-80°C (ISO 15242-1)
                            "seal_leakage_mL_h": 0.1,         # ESTIMATE — mechanical seal acceptable leakage
                        },
                        "bearing": {
                            "vibration_rms_mm_s": 1.2,   # ISO 10816-1:1995 Table 1 zone A: <1.8 mm/s rms
                            "vibration_peak_mm_s": 2.5,  # ISO 10816-1:1995 Table 1 zone A: <2.8 mm/s peak
                            "kurtosis": 3.0,             # Gaussian baseline kurtosis (per definition)
                            "temperature_C": 55.0,       # ESTIMATE — nominal bearing operating temperature
                            "speed_rpm": 1.0,            # O'Neill 1977 High Frontier §II: 1 RPM habitat rotation
                            "acoustic_emission_dB": 40.0,  # ESTIMATE — ISO 22096:2007 bearing AE baseline
                        },
                        "electronics": {
                            "board_temp_C": 40.0,    # JEDEC JESD91A Table 1: typical PCB surface temp
                            "junction_temp_C": 60.0, # ESTIMATE — space-grade IC junction <85°C (MIL-HDBK-217F)
                            "supply_voltage_V": 3.3, # NASA SSP 30482: standard low-voltage digital rail
                            "current_draw_A": 5.0,   # ESTIMATE — 16.5W board at 3.3V
                            "clock_drift_ppm": 1.0,  # ESTIMATE — TCXO nominal drift (JEDEC JESD218B)
                            "error_rate": base_sim.state.memory_bit_errors_total * 1e-6,
                        },
                        "co2_scrubber": {
                            "inlet_co2_ppm": 2500.0,  # NASA SWEG §4 CO2 concentration in breath return stream
                            "outlet_co2_ppm": 400.0,  # NASA-STD-3001 Vol.1 §4.5: CO2 SMAC 1000 ppm; 400 = ambient
                            "sorbent_temp_C": 80.0,   # ESTIMATE — zeolite 5A regeneration temp 80-120°C (ICES-0024)
                            "pressure_drop_kPa": 5.0, # ESTIMATE — CDRA pressure drop ~3-7 kPa (NASA ICES-0024)
                            "humidity_pct": 40.0,     # NASA-STD-3001 Vol.1 Rev.C §4.2.2: nominal RH 25-75%
                            "flow_rate_L_min": 200.0, # ESTIMATE — CDRA cabin air throughput (Carter 2014 ICES-0024)
                            "heater_power_W": 500.0,  # ESTIMATE — CDRA heater ~400-600 W (NASA ICES-0024)
                        },
                    }
                    anomaly_results = anomaly_monitor.scan_all(telemetry)
                    for ar in anomaly_results:
                        if not ar.is_anomaly:
                            continue
                        sub_name = getattr(ar, 'subsystem', 'anomaly_monitor')
                        prev = anomaly_prev_scores.get(sub_name, -1.0)
                        # Only fire when the anomaly score materially grows
                        # (0.05 delta = real trend vs PCA noise floor).
                        # Suppresses the 1-alarm-per-year static-input loop.
                        if ar.score - prev < 0.05:
                            anomaly_prev_scores[sub_name] = max(prev, ar.score)
                            continue
                        anomaly_prev_scores[sub_name] = ar.score
                        sev = "CRITICAL" if ar.score > 0.8 else "WARNING"
                        _tally(sev, f"anomaly.{sub_name}")
                        anomaly_events += 1
                except Exception as e:
                    logger.warning("subsystem.update_failed", subsystem="anomaly_monitor", error=str(e))

            self._results.total_events += (
                len(year_events) + len(cr["events"]) +
                (len(food_events) if food_synth else 0) +
                (len(prop_events) if propulsion else 0) +
                (len(mfg_events) if manufacturing else 0) +
                (len(def_events) if defense else 0) +
                (len(bt_result["events"]) if breakthrough else 0) +
                len(adv_events) +
                len(crew_events) +
                extra_events +
                braking_events +
                rel_events +
                tk_events +
                eng_events +
                crop_events +
                reactor_events +
                magsail_events +
                rad_transport_events +
                microbiome_events +
                sleep_events +
                mass_events +
                anomaly_events
            )

        # Collect results
        s = base_sim.state
        self._results.years_simulated = year if self._results.year_of_failure else total_years
        self._results.wall_time_s = time.time() - t0
        self._results.final_fuel_fraction = s.fusion_fuel_kg / max(s.fuel_initial_kg, 1.0)
        self._results.final_hull_integrity = s.hull_integrity
        self._results.final_crew_count = s.crew_count
        self._results.final_crew_generation = s.crew_generation

        # Food production ratio (use live crew count, not initial cfg)
        # Round 19: ratio aggregates ALL food sources actually used by the sim.
        # Base interstellar hydroponics (line 318 in interstellar.py) is the
        # primary supply (80% × hydroponic_capacity × grow_light_health). The
        # food_synthesis.py bioreactor is a supplemental backup, not the main
        # source, so using it alone produced misleadingly low ratios.
        # Formula: (base hydroponic production + backup synth + 1-yr reserve runway) / need
        final_crew = s.crew_count if s.crew_count > 0 else cfg.crew_size
        daily_need_kg = final_crew * 2.0
        hydroponic_per_day = (
            daily_need_kg * 0.8 * s.hydroponic_capacity * s.grow_light_health
        )
        synth_per_day = food_synth.state.total_food_kg_per_day if food_synth else 0.0
        reserves_per_day = s.food_reserves_kg / 365.0
        total_available_per_day = hydroponic_per_day + synth_per_day + reserves_per_day
        self._results.final_food_production_ratio = min(
            1.0, total_available_per_day / max(daily_need_kg, 1)
        )

        # Challenge states
        ch_summary = challenges.get_summary()
        self._results.challenge_details = {
            n: info["status"] for n, info in ch_summary.items()
        }
        self._results.challenges_terminal = sum(
            1 for st in self._results.challenge_details.values() if st == "terminal"
        )

        # Breakthrough tech outcomes
        if breakthrough:
            self._results.archive_intact = breakthrough.archive.archive.enzyme_dna_templates
            self._results.nanobot_repairs = breakthrough.nanobots.state.microfractures_repaired
            self._results.torpor_food_saved_pct = (
                breakthrough.torpor.get_resource_savings()["food_savings_pct"]
            )

        # ── Populate relativistic physics results ──
        if rel_state is not None:
            self._results.lorentz_gamma = rel_state.lorentz_gamma
            self._results.ship_time_years = rel_state.ship_elapsed_years
            self._results.earth_time_years = rel_state.earth_elapsed_years
            # Use shielded dose from advanced_systems (crew-relevant) if available,
            # otherwise fall back to unshielded ambient from relativistic_physics
            if advanced and hasattr(advanced, 'radiation') and hasattr(advanced.radiation, 'state'):
                self._results.cumulative_dose_msv = advanced.radiation.state.cumulative_crew_dose_sv * 1000
            else:
                self._results.cumulative_dose_msv = rel_state.cumulative_dose_msv

        # ── Populate quantum timekeeping results ──
        if timekeeping is not None:
            try:
                tk_final = timekeeping.simulate_year(velocity_ms=0.0)
                self._results.clock_consensus_error_s = tk_final.get("consensus_error_s", 0.0)
                optical = tk_final.get("optical_clock") or {}
                self._results.operational_clocks = tk_final.get("n_operational_dsac", 0) + (
                    1 if optical.get("operational", False) else 0
                )
            except Exception as e:
                logger.warning("subsystem.finalize_failed", subsystem="timekeeping", error=str(e))

        # ── Populate engineering results ──
        if engineering:
            try:
                self._results.electrical_efficiency = engineering["power"].state.electrical_efficiency
            except Exception as e:
                logger.warning("subsystem.finalize_failed", subsystem="engineering.power", error=str(e))
            try:
                self._results.structural_fatigue_damage = engineering["fatigue"].state.miner_damage
            except Exception as e:
                logger.warning("subsystem.finalize_failed", subsystem="engineering.fatigue", error=str(e))
            try:
                self._results.co2_ppm = engineering["atmosphere"].state.co2_ppm
            except Exception as e:
                logger.warning("subsystem.finalize_failed", subsystem="engineering.atmosphere", error=str(e))

        # Arrival velocity check: if final velocity > 0.001c, orbital insertion
        # is impossible — this is a fly-through, not a capture.
        # Priority: braking module (tracks decel) > propulsion > relativistic state > cruise
        final_velocity_c = cfg.velocity_c
        if braking and braking.state.orbital_insertion_achieved:
            final_velocity_c = braking.state.velocity_c
        elif braking:
            final_velocity_c = braking.state.velocity_c
        elif propulsion:
            final_velocity_c = propulsion.state.velocity_c
        elif rel_state is not None:
            # Only use relativistic state if no braking/propulsion module handles decel
            final_velocity_c = rel_state.velocity_beta

        # Only flag FLY_THROUGH if the ship has actually reached the target
        # distance. If the simulation ended mid-cruise (years < travel time)
        # the ship is still en-route and arrival velocity isn't meaningful yet.
        distance_covered_ly = base_sim.state.distance_ly
        arrived = distance_covered_ly >= cfg.target_distance_ly * 0.999
        if arrived and final_velocity_c > 0.001:
            self._results.ship_survived = False
            self._results.failure_reason = (
                f"FLY_THROUGH: arrival velocity {final_velocity_c:.4f}c "
                f"exceeds 0.001c — cannot achieve orbital insertion"
            )
        else:
            # ── Orbital capture at destination ──
            if destination and final_velocity_c <= 0.001:
                try:
                    capture_result = destination.execute_capture(
                        target_planet_index=0,
                        orbit_altitude_km=500.0,
                    )
                    if capture_result.get("success"):
                        logger.info(
                            "orbital_capture_achieved",
                            delta_v=capture_result.get("delta_v_m_s"),
                            orbit_radius=capture_result.get("orbit_radius_m"),
                        )
                except Exception as e:
                    logger.warning("subsystem.finalize_failed", subsystem="orbital_capture", error=str(e))

        # Survival assessment
        # Note: cumulative_dose_msv from relativistic_physics is UNSHIELDED ambient.
        # The advanced_systems radiation shielding module tracks actual crew dose.
        if not arrived or final_velocity_c <= 0.001:
            if s.hull_integrity <= 0:
                self._results.ship_survived = False
                self._results.failure_reason = "Hull breach"
            elif s.fusion_fuel_kg <= 0 and not cfg.enable_magsail:
                self._results.ship_survived = False
                self._results.failure_reason = "Fuel exhausted, no magsail"

        self._results.severity_counts = severity_counts

        # Roll up (subsystem, severity) tuples into a nested dict for results.
        per_sub: dict[str, dict[str, int]] = {}
        for (sub, sev), n in subsystem_severity.items():
            per_sub.setdefault(sub, {})[sev] = n
        self._results.subsystem_event_counts = per_sub

        # Log top alarm-generating subsystems (by CRITICAL + EMERGENCY + FATAL)
        ranked = sorted(
            per_sub.items(),
            key=lambda kv: (
                kv[1].get("FATAL", 0)
                + kv[1].get("EMERGENCY", 0)
                + kv[1].get("CRITICAL", 0)
            ),
            reverse=True,
        )
        top = ranked[:10]
        logger.info(
            "run.top_alarm_subsystems",
            top=[{"subsystem": s, "counts": c} for s, c in top],
            total_subsystems=len(per_sub),
        )

        # ── Digital twin structural/thermal analysis (post-simulation) ──
        try:
            from aria.digital_twin.bridge import SimTwinBridge
            twin_bridge = SimTwinBridge()
            twin_result = twin_bridge.analyze(cfg)
            # Store twin analysis in results for reporting
            self._results.challenge_details["digital_twin"] = (
                f"mass={twin_result.computed_mass_kg:.0f}kg, "
                f"stress={twin_result.max_von_mises_mpa:.1f}MPa, "
                f"FoS={twin_result.structural_safety_factor:.0f}x, "
                f"Tmax={twin_result.max_temperature_k:.0f}K"
            )
            if twin_result.warnings:
                for w in twin_result.warnings:
                    _tally("WARNING", "digital_twin")
                    self._results.total_events += 1
        except Exception as e:
            logger.warning("subsystem.finalize_failed", subsystem="digital_twin", error=str(e))

        return self._results


def compare_legacy_vs_breakthrough(
    years: int = 200, num_seeds: int = 10
) -> dict[str, Any]:
    """Run Monte Carlo comparison: legacy tech vs breakthrough tech.

    Returns statistics showing how much breakthrough tech improves survival.
    """
    legacy_results: list[GenerationShipResults] = []
    breakthrough_results: list[GenerationShipResults] = []

    for seed in range(num_seeds):
        # Legacy
        legacy_sim = GenerationShipSimulation(GenerationShipConfig.legacy(seed=seed))
        legacy_results.append(legacy_sim.run(years))

        # Breakthrough
        bt_sim = GenerationShipSimulation(GenerationShipConfig.breakthrough(seed=seed))
        breakthrough_results.append(bt_sim.run(years))

    # Compute statistics
    def avg(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0

    legacy_terminal = avg([r.challenges_terminal for r in legacy_results])
    bt_terminal = avg([r.challenges_terminal for r in breakthrough_results])

    legacy_food = avg([r.final_food_production_ratio for r in legacy_results])
    bt_food = avg([r.final_food_production_ratio for r in breakthrough_results])

    legacy_survival = sum(1 for r in legacy_results if r.ship_survived) / max(num_seeds, 1)
    bt_survival = sum(1 for r in breakthrough_results if r.ship_survived) / max(num_seeds, 1)

    return {
        "years": years,
        "num_seeds": num_seeds,
        "legacy": {
            "avg_terminal_challenges": legacy_terminal,
            "avg_food_ratio": legacy_food,
            "survival_rate": legacy_survival,
            "avg_events": avg([r.total_events for r in legacy_results]),
        },
        "breakthrough": {
            "avg_terminal_challenges": bt_terminal,
            "avg_food_ratio": bt_food,
            "survival_rate": bt_survival,
            "avg_events": avg([r.total_events for r in breakthrough_results]),
            "avg_nanobot_repairs": avg([r.nanobot_repairs for r in breakthrough_results]),
            "avg_torpor_savings_pct": avg([r.torpor_food_saved_pct for r in breakthrough_results]),
            "archive_intact_rate": avg([r.archive_intact for r in breakthrough_results]),
        },
        "improvement": {
            "terminal_reduction": legacy_terminal - bt_terminal,
            "food_ratio_improvement": bt_food - legacy_food,
            "survival_improvement": bt_survival - legacy_survival,
        },
    }
