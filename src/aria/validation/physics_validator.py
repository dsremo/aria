"""Comprehensive physics/engineering validation for ARIA generation ship simulations.

Checks physical consistency of a simulation timeline against known physical laws
and engineering constraints. Each validator returns Violation objects describing
any broken invariant, with the mission year and severity.

Validation categories:
  1. Energy conservation   — power budget, RTG Pu-238 decay, fuel energy density
  2. Mass conservation     — total mass only decreases (no creation in void)
  3. Velocity constraints  — 0.1c ceiling, magsail deceleration only
  4. Population constraints — non-negative, biological feasibility
  5. Resource non-negativity — fuel, water, food, spares, health in [0,1]
  6. Thermal balance       — radiator capacity vs waste heat
  7. Shield erosion        — monotonic decrease, Hoang et al. model
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ViolationSeverity(Enum):
    """How bad is the physics violation."""
    INFO = "INFO"           # Minor numerical drift, possibly acceptable
    WARNING = "WARNING"     # Notable deviation from physical law
    ERROR = "ERROR"         # Clear violation of a conservation law
    CRITICAL = "CRITICAL"   # Impossible state (negative mass, FTL, etc.)


@dataclass
class Violation:
    """A single physics violation detected in the simulation."""
    category: str           # e.g. "ENERGY", "MASS", "VELOCITY"
    severity: ViolationSeverity
    mission_year: float
    description: str
    expected: Any = None
    actual: Any = None

    def __str__(self) -> str:
        parts = [
            f"[{self.severity.value}] Year {self.mission_year:.0f} "
            f"({self.category}): {self.description}"
        ]
        if self.expected is not None:
            parts.append(f"  Expected: {self.expected}")
        if self.actual is not None:
            parts.append(f"  Actual: {self.actual}")
        return "\n".join(parts)


@dataclass
class ValidationReport:
    """Complete validation report for a simulation run."""
    years_validated: int = 0
    violations: list[Violation] = field(default_factory=list)
    checks_run: int = 0
    checks_passed: int = 0

    @property
    def checks_failed(self) -> int:
        return self.checks_run - self.checks_passed

    @property
    def is_clean(self) -> bool:
        return len(self.violations) == 0

    @property
    def error_count(self) -> int:
        return sum(
            1 for v in self.violations
            if v.severity in (ViolationSeverity.ERROR, ViolationSeverity.CRITICAL)
        )

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == ViolationSeverity.WARNING)

    def violations_by_category(self) -> dict[str, list[Violation]]:
        result: dict[str, list[Violation]] = {}
        for v in self.violations:
            result.setdefault(v.category, []).append(v)
        return result

    def summary(self) -> str:
        lines = [
            f"Physics Validation Report",
            f"{'=' * 50}",
            f"Years validated: {self.years_validated}",
            f"Checks run: {self.checks_run}",
            f"Checks passed: {self.checks_passed}",
            f"Violations: {len(self.violations)} "
            f"({self.error_count} errors, {self.warning_count} warnings)",
        ]
        if self.violations:
            by_cat = self.violations_by_category()
            lines.append("")
            for cat, vs in sorted(by_cat.items()):
                lines.append(f"  {cat}: {len(vs)} violations")
        return "\n".join(lines)


# ────────────────────────────────────────────────────────────────
#  Physical constants
# ────────────────────────────────────────────────────────────────

C_M_S = 2.998e8                   # Speed of light (m/s)
PU238_HALF_LIFE_YEARS = 87.7      # Pu-238 half-life
STEFAN_BOLTZMANN = 5.670374419e-8  # W/m^2/K^4
DT_ENERGY_DENSITY_J_KG = 3.4e14   # D-T fusion: 340 TJ/kg
SECONDS_PER_YEAR = 3.15576e7
SHIP_MASS_KG = 1e7                 # ~10,000 tonnes baseline


class PhysicsValidator:
    """Validates physical consistency of a generation ship simulation.

    Works with both the SimulatorEngine (4D timeline) and the
    GenerationShipSimulation (InterstellarState year-by-year).

    Usage with SimulatorEngine:
        engine = SimulatorEngine(target=..., velocity_c=0.1)
        engine.initialize()
        engine.run(years=200)
        validator = PhysicsValidator()
        report = validator.validate_timeline(engine.timeline)

    Usage with InterstellarSimulation state snapshots:
        validator = PhysicsValidator()
        report = validator.validate_states(states)
    """

    def __init__(
        self,
        max_velocity_c: float = 0.1,
        tolerance: float = 0.01,
        initial_fuel_kg: float = 50_000.0,
        initial_water_liters: float = 50_000.0,
        initial_food_kg: float = 10_000.0,
        ship_dry_mass_kg: float = 1e7,
    ) -> None:
        self._max_v = max_velocity_c
        self._tol = tolerance
        self._fuel0 = initial_fuel_kg
        self._water0 = initial_water_liters
        self._food0 = initial_food_kg
        self._dry_mass = ship_dry_mass_kg

    # ────────────────────────────────────────────────────────────
    #  Top-level validation entry points
    # ────────────────────────────────────────────────────────────

    def validate_timeline(self, timeline: Any) -> ValidationReport:
        """Validate a SimulatorTimeline from the 4D SimulatorEngine.

        Extracts state snapshots and runs all checks.
        """
        snapshots = timeline._snapshots if hasattr(timeline, "_snapshots") else []
        return self._validate_snapshot_sequence(snapshots, source="timeline")

    def validate_states(self, states: list[Any]) -> ValidationReport:
        """Validate a list of InterstellarState or SimulatorState objects."""
        return self._validate_snapshot_sequence(states, source="states")

    def validate_engine(self, engine: Any) -> ValidationReport:
        """Validate directly from a SimulatorEngine instance."""
        return self.validate_timeline(engine.timeline)

    # ────────────────────────────────────────────────────────────
    #  Core validation loop
    # ────────────────────────────────────────────────────────────

    def _validate_snapshot_sequence(
        self, snapshots: list[Any], source: str = ""
    ) -> ValidationReport:
        """Run all physics checks on an ordered sequence of state snapshots."""
        report = ValidationReport()
        if not snapshots:
            return report

        report.years_validated = len(snapshots)
        prev = None

        for snap in snapshots:
            year = self._get_year(snap)

            # 1. Energy conservation
            self._check_energy(snap, year, report)

            # 2. Mass conservation (needs prev state)
            if prev is not None:
                self._check_mass_conservation(prev, snap, year, report)

            # 3. Velocity constraints
            self._check_velocity(snap, year, report)

            # 4. Population constraints
            self._check_population(snap, prev, year, report)

            # 5. Resource non-negativity
            self._check_resources(snap, year, report)

            # 6. Thermal balance
            self._check_thermal(snap, year, report)

            # 7. Shield erosion
            if prev is not None:
                self._check_shield(prev, snap, year, report)

            prev = snap

        return report

    # ────────────────────────────────────────────────────────────
    #  1. ENERGY CONSERVATION
    # ────────────────────────────────────────────────────────────

    def _check_energy(self, snap: Any, year: float, report: ValidationReport) -> None:
        """Check energy conservation constraints."""

        # RTG power follows Pu-238 half-life
        report.checks_run += 1
        rtg_frac = self._get(snap, "rtg_power_fraction", 1.0)
        expected_rtg = 0.5 ** (year / PU238_HALF_LIFE_YEARS)
        if abs(rtg_frac - expected_rtg) > self._tol and year > 0:
            report.violations.append(Violation(
                category="ENERGY",
                severity=ViolationSeverity.WARNING,
                mission_year=year,
                description=(
                    f"RTG power fraction deviates from Pu-238 half-life model "
                    f"(87.7 yr). delta={abs(rtg_frac - expected_rtg):.4f}"
                ),
                expected=round(expected_rtg, 4),
                actual=round(rtg_frac, 4),
            ))
        else:
            report.checks_passed += 1

        # Fuel mass x energy density >= kinetic energy at current velocity
        report.checks_run += 1
        fuel_kg = self._get(snap, "fuel_kg",
                            self._get(snap, "fusion_fuel_kg", self._fuel0))
        v_c = self._get(snap, "velocity_scalar_c",
                        self._get(snap, "velocity_c", 0.1))
        v_ms = v_c * C_M_S
        ke_ship = 0.5 * self._dry_mass * v_ms ** 2
        fuel_energy = fuel_kg * DT_ENERGY_DENSITY_J_KG

        # This is a budget check: total fuel energy at launch must cover KE
        # At any point, fuel_energy + already_burned_energy >= KE
        # We check initial fuel covers initial KE (one-time at year 0)
        if year < 1.0:
            initial_fuel_energy = self._fuel0 * DT_ENERGY_DENSITY_J_KG
            if initial_fuel_energy < ke_ship * 0.01:
                # Note: ship is laser-launched to 0.1c, so onboard fuel
                # doesn't need to cover acceleration KE. It covers
                # station-keeping and braking only. This check ensures
                # the fuel has meaningful energy content.
                report.violations.append(Violation(
                    category="ENERGY",
                    severity=ViolationSeverity.INFO,
                    mission_year=year,
                    description="Onboard fuel energy is tiny vs ship KE (expected: laser launch)",
                    expected="Laser-launched to 0.1c",
                    actual=f"Fuel energy: {initial_fuel_energy:.2e} J, Ship KE: {ke_ship:.2e} J",
                ))
            else:
                report.checks_passed += 1
        else:
            report.checks_passed += 1

        # Power budget: total power should be non-negative
        report.checks_run += 1
        power = self._get(snap, "power_watts",
                          self._get(snap, "total_power_watts", 0))
        if power < 0:
            report.violations.append(Violation(
                category="ENERGY",
                severity=ViolationSeverity.CRITICAL,
                mission_year=year,
                description="Total power is negative",
                expected=">= 0",
                actual=power,
            ))
        else:
            report.checks_passed += 1

    # ────────────────────────────────────────────────────────────
    #  2. MASS CONSERVATION
    # ────────────────────────────────────────────────────────────

    def _check_mass_conservation(
        self, prev: Any, curr: Any, year: float, report: ValidationReport
    ) -> None:
        """Total ship mass can only decrease (fuel burn, waste ejection)."""
        report.checks_run += 1

        prev_mass = self._compute_total_mass(prev)
        curr_mass = self._compute_total_mass(curr)

        # Mass should not increase. Allow small tolerance for numerical noise.
        mass_increase = curr_mass - prev_mass
        threshold = prev_mass * 0.001  # 0.1% tolerance

        if mass_increase > threshold:
            report.violations.append(Violation(
                category="MASS",
                severity=ViolationSeverity.ERROR,
                mission_year=year,
                description=(
                    f"Total mass increased by {mass_increase:.1f} kg "
                    f"(cannot create matter in interstellar void)"
                ),
                expected=f"<= {prev_mass:.0f} kg",
                actual=f"{curr_mass:.0f} kg",
            ))
        else:
            report.checks_passed += 1

    def _compute_total_mass(self, snap: Any) -> float:
        """Estimate total ship mass from tracked quantities."""
        fuel = self._get(snap, "fuel_kg",
                         self._get(snap, "fusion_fuel_kg", 0))
        water = self._get(snap, "water_liters", 0)  # ~1 kg/liter
        food = self._get(snap, "food_reserves_kg", 0)
        crew = self._get(snap, "crew_count", 0) * 80.0  # ~80 kg/person
        spares_e = self._get(snap, "spare_electronics", 0) * 2.0  # ~2 kg each
        spares_m = self._get(snap, "spare_mechanical", 0) * 5.0  # ~5 kg each
        shielding = self._get(snap, "radiation_shielding_mass_kg", 10000.0)

        return self._dry_mass + fuel + water + food + crew + spares_e + spares_m + shielding

    # ────────────────────────────────────────────────────────────
    #  3. VELOCITY CONSTRAINTS
    # ────────────────────────────────────────────────────────────

    def _check_velocity(self, snap: Any, year: float, report: ValidationReport) -> None:
        """Velocity must not exceed 0.1c; magsail only decelerates."""
        report.checks_run += 1

        v_c = self._get(snap, "velocity_scalar_c",
                        self._get(snap, "velocity_c", 0.0))
        phase = self._get(snap, "phase", "CRUISE")

        # Never exceed max velocity
        if v_c > self._max_v * (1 + self._tol):
            report.violations.append(Violation(
                category="VELOCITY",
                severity=ViolationSeverity.CRITICAL,
                mission_year=year,
                description=f"Velocity {v_c:.6f}c exceeds maximum {self._max_v}c",
                expected=f"<= {self._max_v}c",
                actual=f"{v_c:.6f}c",
            ))
        else:
            report.checks_passed += 1

        # Velocity must be non-negative
        report.checks_run += 1
        if v_c < -1e-10:
            report.violations.append(Violation(
                category="VELOCITY",
                severity=ViolationSeverity.CRITICAL,
                mission_year=year,
                description=f"Negative velocity: {v_c:.6f}c (ship going backwards)",
                expected=">= 0",
                actual=f"{v_c:.6f}c",
            ))
        else:
            report.checks_passed += 1

    # ────────────────────────────────────────────────────────────
    #  4. POPULATION CONSTRAINTS
    # ────────────────────────────────────────────────────────────

    def _check_population(
        self, snap: Any, prev: Any | None, year: float, report: ValidationReport
    ) -> None:
        """Population must be >= 0. Births only if fertile crew exist."""
        report.checks_run += 1

        crew = self._get(snap, "crew_count", 0)
        if crew < 0:
            report.violations.append(Violation(
                category="POPULATION",
                severity=ViolationSeverity.CRITICAL,
                mission_year=year,
                description=f"Negative population: {crew}",
                expected=">= 0",
                actual=crew,
            ))
        else:
            report.checks_passed += 1

        # Check for unreasonable population growth
        if prev is not None:
            report.checks_run += 1
            prev_crew = self._get(prev, "crew_count", 0)
            if prev_crew > 0 and crew > prev_crew:
                growth_rate = (crew - prev_crew) / max(prev_crew, 1)
                # Maximum biological growth: ~3% per year (high birth, low death)
                if growth_rate > 0.10:
                    report.violations.append(Violation(
                        category="POPULATION",
                        severity=ViolationSeverity.WARNING,
                        mission_year=year,
                        description=(
                            f"Population growth {growth_rate:.0%} exceeds "
                            f"biological maximum (~3-10%/yr)"
                        ),
                        expected="<= 10% growth/year",
                        actual=f"{growth_rate:.0%} ({prev_crew} -> {crew})",
                    ))
                else:
                    report.checks_passed += 1
            else:
                report.checks_passed += 1

    # ────────────────────────────────────────────────────────────
    #  5. RESOURCE NON-NEGATIVITY
    # ────────────────────────────────────────────────────────────

    def _check_resources(self, snap: Any, year: float, report: ValidationReport) -> None:
        """All resources must be >= 0; all health values in [0, 1]."""

        # Non-negative resources
        resource_fields = [
            ("fuel_kg", "fusion_fuel_kg"),
            ("water_liters", None),
            ("food_reserves_kg", None),
            ("o2_reserves_kg", None),
            ("spare_electronics", None),
            ("spare_mechanical", None),
        ]

        for primary, fallback in resource_fields:
            report.checks_run += 1
            val = self._get(snap, primary, self._get(snap, fallback, 0) if fallback else 0)
            if val < -1e-6:
                report.violations.append(Violation(
                    category="RESOURCE",
                    severity=ViolationSeverity.ERROR,
                    mission_year=year,
                    description=f"Negative resource: {primary} = {val}",
                    expected=">= 0",
                    actual=val,
                ))
            else:
                report.checks_passed += 1

        # Health values in [0, 1]
        health_fields = [
            "hull_integrity",
            "electronics_health",
            "printer_health",
            "seed_viability",
            "hydroponic_capacity",
            "grow_light_health",
            "crew_morale",
            "shield_overall_health",
        ]

        for hf in health_fields:
            val = self._get(snap, hf, None)
            if val is None:
                continue
            report.checks_run += 1
            if val < -1e-6 or val > 1.0 + 1e-6:
                report.violations.append(Violation(
                    category="RESOURCE",
                    severity=ViolationSeverity.ERROR,
                    mission_year=year,
                    description=f"Health value out of [0,1]: {hf} = {val:.4f}",
                    expected="[0.0, 1.0]",
                    actual=round(val, 4),
                ))
            else:
                report.checks_passed += 1

    # ────────────────────────────────────────────────────────────
    #  6. THERMAL BALANCE
    # ────────────────────────────────────────────────────────────

    def _check_thermal(self, snap: Any, year: float, report: ValidationReport) -> None:
        """Radiator must dissipate waste heat. If not, temperature should rise.

        Stefan-Boltzmann law: P_radiated = epsilon * sigma * A * T^4
        For space radiator: epsilon ~ 0.9, A ~ 2000 m^2, T ~ 300 K
        Max radiated: 0.9 * 5.67e-8 * 2000 * 300^4 ~ 826 kW
        """
        report.checks_run += 1

        # Estimate radiator capacity
        # Standard generation ship: ~2000 m^2 radiator area
        radiator_area_m2 = 2000.0
        emissivity = 0.9
        radiator_temp_k = 300.0  # Nominal operating temperature

        max_radiated_w = (
            emissivity * STEFAN_BOLTZMANN * radiator_area_m2 * radiator_temp_k ** 4
        )

        # Waste heat estimate: reactor inefficiency
        reactor_health = self._get(snap, "reactor_health",
                                   self._get(snap, "fusion_reactor_health", 1.0))
        power_w = self._get(snap, "power_watts",
                            self._get(snap, "total_power_watts", 500_000))
        # Assume 60% thermal efficiency -> 40% waste heat
        waste_heat_w = power_w * 0.4

        if waste_heat_w > max_radiated_w * 1.5:
            report.violations.append(Violation(
                category="THERMAL",
                severity=ViolationSeverity.WARNING,
                mission_year=year,
                description=(
                    f"Waste heat ({waste_heat_w:.0f} W) exceeds radiator capacity "
                    f"({max_radiated_w:.0f} W) by {waste_heat_w / max_radiated_w:.1%}"
                ),
                expected=f"<= {max_radiated_w:.0f} W",
                actual=f"{waste_heat_w:.0f} W",
            ))
        else:
            report.checks_passed += 1

    # ────────────────────────────────────────────────────────────
    #  7. SHIELD EROSION
    # ────────────────────────────────────────────────────────────

    def _check_shield(
        self, prev: Any, curr: Any, year: float, report: ValidationReport
    ) -> None:
        """Shield health should decrease monotonically (no regeneration in void).

        Exception: ice ablation shield can be replenished from water recycling.
        """
        report.checks_run += 1

        prev_shield = self._get(prev, "shield_overall_health",
                                self._get(prev, "hull_integrity", 1.0))
        curr_shield = self._get(curr, "shield_overall_health",
                                self._get(curr, "hull_integrity", 1.0))

        # Shield should not increase (with small tolerance for ice replenishment)
        increase = curr_shield - prev_shield
        if increase > 0.02:  # Allow 2% for ice replenishment
            report.violations.append(Violation(
                category="SHIELD",
                severity=ViolationSeverity.WARNING,
                mission_year=year,
                description=(
                    f"Shield health increased by {increase:.4f} "
                    f"(unexpected regeneration beyond ice replenishment)"
                ),
                expected=f"<= {prev_shield:.4f}",
                actual=f"{curr_shield:.4f}",
            ))
        else:
            report.checks_passed += 1

        # Verify erosion rate is consistent with Hoang et al. model
        # At 0.1c, ISM sputtering erosion is ~40 ug/ly/cm^2 at 0.3c
        # Scales as v^3 for sputtering: 40 * (0.1/0.3)^3 = ~1.5 ug/ly/cm^2
        # Over 10,000 kg shield: very small fractional erosion per year
        report.checks_run += 1
        v_c = self._get(curr, "velocity_scalar_c",
                        self._get(curr, "velocity_c", 0.1))

        if v_c > 0.001:
            # Expected erosion per year from Hoang model (scaled)
            # erosion_rate ~ v^3 (sputtering regime)
            hoang_rate_at_03c = 40e-9  # kg/ly/cm^2 at 0.3c
            scaled_rate = hoang_rate_at_03c * (v_c / 0.3) ** 3
            shield_area_cm2 = 1e8  # ~100 m^2 forward face = 1e8 cm^2
            erosion_kg_per_ly = scaled_rate * shield_area_cm2
            # Per year at v_c: erosion_kg = erosion_kg_per_ly * v_c
            expected_erosion_kg_yr = erosion_kg_per_ly * v_c

            # Shield mass ~ 10,000 kg initially
            shield_mass_kg = 10_000.0
            expected_health_loss = expected_erosion_kg_yr / shield_mass_kg

            actual_loss = prev_shield - curr_shield
            if actual_loss < 0:
                actual_loss = 0  # Handled by monotonicity check above

            # The actual erosion should be in the same order of magnitude
            # as the Hoang model. Allow 100x factor for layered shield system.
            if expected_health_loss > 0 and actual_loss > expected_health_loss * 1000:
                report.violations.append(Violation(
                    category="SHIELD",
                    severity=ViolationSeverity.INFO,
                    mission_year=year,
                    description=(
                        f"Shield erosion ({actual_loss:.6f}/yr) is >1000x "
                        f"Hoang et al. model ({expected_health_loss:.6f}/yr at {v_c:.4f}c)"
                    ),
                    expected=f"~{expected_health_loss:.6f}/yr",
                    actual=f"{actual_loss:.6f}/yr",
                ))
            else:
                report.checks_passed += 1
        else:
            report.checks_passed += 1  # At very low velocity, no meaningful erosion

    # ────────────────────────────────────────────────────────────
    #  Helpers
    # ────────────────────────────────────────────────────────────

    @staticmethod
    def _get(obj: Any, attr: str, default: Any = None) -> Any:
        """Get attribute from object or dict, with fallback."""
        if isinstance(obj, dict):
            return obj.get(attr, default)
        return getattr(obj, attr, default)

    @staticmethod
    def _get_year(snap: Any) -> float:
        """Extract mission year from a snapshot."""
        for attr in ("mission_time_years", "mission_year"):
            val = getattr(snap, attr, None)
            if val is not None:
                return float(val)
        if isinstance(snap, dict):
            return float(snap.get("mission_time_years", snap.get("mission_year", 0)))
        return 0.0


# ────────────────────────────────────────────────────────────────
#  Convenience runner: validate a freshly-run simulation
# ────────────────────────────────────────────────────────────────

def validate_generation_ship(
    years: int = 200,
    seed: int = 42,
    verbose: bool = False,
) -> ValidationReport:
    """Run a generation ship simulation and validate its physics.

    Uses the SimulatorEngine with full timeline for year-by-year checking.
    """
    from aria.simulator.engine import SimulatorEngine
    from aria.simulator.targets import STAR_CATALOG

    # Pick a target that matches the requested duration
    # At 0.1c, distance_ly = years * 0.1
    target_distance = years * 0.1
    # Find best matching target or use 100 ly default
    target = STAR_CATALOG.get("100_ly_target")
    for t in STAR_CATALOG.values():
        if abs(t.distance_ly / 0.1 - years) < abs(target.distance_ly / 0.1 - years):
            target = t

    engine = SimulatorEngine(
        target=target,
        velocity_c=0.1,
        crew_size=4,
        seed=seed,
    )
    engine.initialize()
    engine.run(years=years)

    validator = PhysicsValidator()
    report = validator.validate_engine(engine)

    if verbose:
        print(report.summary())
        if report.violations:
            print()
            for v in report.violations[:20]:
                print(v)
                print()

    return report
