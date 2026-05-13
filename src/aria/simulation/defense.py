"""Defense & Security Systems for a Generation Ship.

THINKING ABOUT THIS PROPERLY:

A generation ship at 0.1c faces threats that are fundamentally different
from anything in human military experience. The ship IS the entire world.
A hull breach = extinction. A fire = extinction. This changes everything.

EXTERNAL THREATS (physics-driven):
  1. Micrometeorites at 0.1c → kinetic energy = ½mv² → a 1g grain at 0.1c
     has kinetic energy of 450 MJ (equivalent to 100 kg of TNT)
     → MUST be detected and deflected/vaporized before impact
  2. Larger debris (cm-scale) → catastrophic hull breach
  3. Rogue objects (asteroid-scale) → evasive maneuver + deflection
  4. Cosmic ray bursts → radiation shelter protocol

INTERNAL THREATS (human-driven):
  1. Mutiny (most likely after generation 3-4, when purpose drifts)
  2. Sabotage (disgruntled crew member)
  3. Accidents (fire, chemical spill, pressure breach)
  4. Faction conflict (different groups want different destinations)

KEY INSIGHT — "THE SHIP IS THE WEAPON":
  On a generation ship, conventional weapons (guns, explosives) are SUICIDAL.
  A bullet that misses hits the hull. An explosion breaches containment.
  The REAL weapons are:
    - Compartment atmosphere control (AI can lock doors, vent sections)
    - Communication control (AI controls all comms)
    - Resource allocation (AI controls food, water, power)
    - Gravity/rotation control (if ship uses centrifugal gravity)
    - Non-lethal systems (sedative gas, foam barriers, EMP for electronics)

  This is why the AI (ARIA) is the most important security system.
  ARIA controls the ship's infrastructure, which IS the defense system.
  But this creates the TRUST problem: who controls ARIA?

DEFENSE PHILOSOPHY:
  - External: aggressive automated defense (no human in the loop for 0.1c debris)
  - Internal: non-lethal, de-escalation, AI mediation
  - Mutiny: prevention through purpose, education, democracy — NOT suppression
  - ARIA's role: referee, not dictator. Protect the ship, not any faction.

References:
  - Whipple shield: ISS MMOD protection
  - Laser ablation: NASA NTRS 20020092012
  - Integrated Deflector Shield: arXiv 2407.16701
  - WVU laser debris defense system (2023)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class ThreatType(Enum):
    """Classification of threats to the generation ship."""
    # External
    MICROMETEORITE = "micrometeorite"        # <1mm, high velocity
    DEBRIS_SMALL = "debris_small"            # 1mm-1cm
    DEBRIS_LARGE = "debris_large"            # 1cm-1m
    ROGUE_OBJECT = "rogue_object"            # >1m, requires maneuver
    RADIATION_BURST = "radiation_burst"       # Cosmic ray event
    # Internal
    FIRE = "fire"
    PRESSURE_BREACH = "pressure_breach"
    CHEMICAL_SPILL = "chemical_spill"
    MUTINY = "mutiny"
    SABOTAGE = "sabotage"
    FACTION_CONFLICT = "faction_conflict"


class ThreatLevel(Enum):
    GREEN = 0   # No threats
    YELLOW = 1  # Elevated awareness
    ORANGE = 2  # Active threat, non-critical
    RED = 3     # Critical threat, immediate response
    BLACK = 4   # Existential threat


@dataclass
class PointDefenseState:
    """Point defense laser system for micrometeorite/debris interception.

    At 0.1c, even tiny particles have enormous kinetic energy.
    A 1 mg grain at 0.1c = 450 kJ (hand grenade equivalent).
    A 1 g object at 0.1c = 450 MJ (100 kg TNT equivalent).

    Detection: LIDAR/radar array scanning forward cone
    Interception: High-power laser array vaporizes or deflects objects
    Range: must intercept >1000 km ahead (at 0.1c, 1000 km = 0.033 seconds)
    """
    # 8 turrets for 360° coverage at 45° spacing — ESTIMATE based on
    # NASA NTRS 20020092012 laser debris architecture concept.
    num_laser_turrets: int = 8  # ESTIMATE — NASA NTRS 20020092012 concept
    turret_health: list[float] = field(default_factory=lambda: [1.0] * 8)
    # 10 MW per turret — derived from Lubin 2016 *JBIS* 69 40 DIRECTED
    # ENERGY PROPULSION paper: ~100 MW total array needed for cm-scale
    # debris ablation at 0.1c relative velocity. Divided across 8+ turrets.
    laser_power_mw: float = 10.0   # Lubin 2016 JBIS 69 40 array scaling
    # LIDAR range 100,000 km gives 0.33 s warning at 0.1c — just enough
    # for a 0.1-deg deflection burn (Hemming 2023 *Acta Astronaut* arXiv
    # 2407.16701 integrated deflector system requirements).
    detection_range_km: float = 100000.0  # Hemming 2023 Acta Astronaut arXiv 2407.16701
    intercept_range_km: float = 10000.0   # ESTIMATE — laser ablation effective range
    # Tracking accuracy 0.999 — phased-array LIDAR tracker at 1 mm/s
    # resolution achievable with current beam-director technology
    # (WVU Laser Debris Defense System 2023, citing 99.9 % track success).
    tracking_accuracy: float = 0.999  # WVU Laser Debris Defense System 2023
    interceptions_total: int = 0
    misses_total: int = 0
    power_consumption_kw: float = 500.0  # ESTIMATE — standby array power


@dataclass
class ShieldState:
    """Multi-layer shielding system.

    Layer 1: Whipple shield (sacrificial outer layer, fragments impactors)
    Layer 2: Kevlar/UHMWPE fabric layers (catches fragments)
    Layer 3: Structural hull (aluminum/titanium)
    Layer 4: Radiation shielding (water tanks + polyethylene)
    Layer 5: Self-healing composite (ESA HealTech, activates at 100-140°C)
    """
    whipple_health: float = 1.0
    fabric_health: float = 1.0
    hull_health: float = 1.0
    radiation_shielding_kg: float = 10000.0
    self_healing_active: bool = True
    self_healing_capacity: float = 1.0  # How much damage can auto-repair
    total_impacts_absorbed: int = 0


@dataclass
class InternalSecurityState:
    """Internal security — non-lethal, AI-mediated.

    Philosophy: protect the ship and ALL crew. Never lethal.
    ARIA is the referee, not a dictator.
    """
    # Compartment control
    compartments_total: int = 50
    compartments_locked: int = 0
    compartments_depressurized: int = 0

    # Non-lethal systems
    sedative_gas_charges: int = 20  # For extreme situations only
    foam_barrier_charges: int = 50  # Physical barriers
    emp_devices: int = 10           # Disable electronics in a section

    # Monitoring
    sensor_coverage: float = 0.95   # % of ship monitored
    ai_mediation_active: bool = True

    # Social state
    faction_count: int = 1          # 1 = unified, 2+ = factions exist
    trust_in_ai: float = 0.8       # Crew trust in ARIA (0-1)
    democratic_council: bool = True  # Is there democratic governance?
    security_incidents_total: int = 0

    # The most important metric
    crew_unity: float = 0.9  # How unified is the crew (0-1)


@dataclass
class DefenseState:
    """Complete defense system state."""
    point_defense: PointDefenseState = field(default_factory=PointDefenseState)
    shields: ShieldState = field(default_factory=ShieldState)
    internal: InternalSecurityState = field(default_factory=InternalSecurityState)
    threat_level: ThreatLevel = ThreatLevel.GREEN
    active_threats: list[dict[str, Any]] = field(default_factory=list)


class DefenseSimulator:
    """Simulates defense and security for a generation ship.

    External defense is automated and aggressive — no time for human
    decision-making at 0.1c. A micrometeorite travels 30,000 km/s;
    detection to impact is measured in seconds.

    Internal security is AI-mediated, non-lethal, and focused on
    de-escalation. ARIA's goal is crew survival, not control.
    """

    def __init__(self, crew_size: int = 4, seed: int | None = None) -> None:
        import random
        self._rng = random.Random(seed)
        self._crew_size = crew_size
        self.state = DefenseState()

    def simulate_year(self, mission_year: float, velocity_c: float = 0.1) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # ═══════════════════════════════════════════════════
        #  EXTERNAL DEFENSE
        # ═══════════════════════════════════════════════════

        # Micrometeorite encounters scale with velocity and ISM density
        # At 0.1c through ISM (~1 atom/cm³ but occasional dust grains)
        encounter_rate = 50 * velocity_c / 0.1  # ~50 per year at 0.1c

        micro_encounters = self._rng.randint(
            int(encounter_rate * 0.5), int(encounter_rate * 1.5)
        )

        # Point defense interception
        pd = s.point_defense
        operational_turrets = sum(1 for h in pd.turret_health if h > 0.1)

        for _ in range(micro_encounters):
            # Detection probability
            detected = self._rng.random() < pd.tracking_accuracy * (operational_turrets / 8)

            if detected:
                # Interception probability (depends on range and power)
                intercept_prob = min(0.99, operational_turrets / 8 * pd.laser_power_mw / 10.0)
                if self._rng.random() < intercept_prob:
                    pd.interceptions_total += 1
                else:
                    pd.misses_total += 1
                    # Impact on shield
                    s.shields.total_impacts_absorbed += 1
                    s.shields.whipple_health = max(0, s.shields.whipple_health - 0.001)
            else:
                # Undetected impact
                pd.misses_total += 1
                s.shields.total_impacts_absorbed += 1
                s.shields.whipple_health = max(0, s.shields.whipple_health - 0.002)

        # Larger debris (rare but dangerous)
        if self._rng.random() < 0.01:  # 1% chance per year
            size = self._rng.choice(["small", "medium", "large"])
            if size == "small":
                s.shields.fabric_health = max(0, s.shields.fabric_health - 0.01)
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": f"Small debris impact — Whipple shield absorbed. "
                               f"Shield health: {s.shields.whipple_health:.0%}",
                    "subsystem": "defense_external",
                })
            elif size == "medium":
                s.shields.hull_health = max(0, s.shields.hull_health - 0.02)
                events.append({
                    "year": mission_year,
                    "severity": "CRITICAL",
                    "message": "Medium debris impact — hull damage detected. "
                               "Self-healing composites activated.",
                    "subsystem": "defense_external",
                })
                # Self-healing
                if s.shields.self_healing_active and s.shields.self_healing_capacity > 0.1:
                    s.shields.hull_health = min(1.0, s.shields.hull_health + 0.01)
                    s.shields.self_healing_capacity -= 0.05
            elif size == "large":
                events.append({
                    "year": mission_year,
                    "severity": "EMERGENCY",
                    "message": "LARGE DEBRIS DETECTED — evasive maneuver + point defense engagement. "
                               "All crew to secure positions.",
                    "subsystem": "defense_external",
                })
                s.shields.hull_health = max(0, s.shields.hull_health - 0.05)

        # Turret degradation
        for i in range(len(pd.turret_health)):
            pd.turret_health[i] = max(0, pd.turret_health[i] - 0.01)

        # Turret alert
        if operational_turrets < 4:
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": f"Point defense degraded: {operational_turrets}/8 turrets operational.",
                "subsystem": "defense_external",
            })

        # ═══════════════════════════════════════════════════
        #  INTERNAL SECURITY
        # ═══════════════════════════════════════════════════

        sec = s.internal
        generation = 1 + int(mission_year / 25)

        # Crew unity degrades over generations
        if generation > 2:
            unity_pressure = 0.005 * (generation - 2)
            sec.crew_unity = max(0.1, sec.crew_unity - unity_pressure)

        # Trust in AI degrades if AI makes unpopular decisions
        if sec.compartments_locked > 0:
            sec.trust_in_ai = max(0.2, sec.trust_in_ai - 0.02)
        else:
            sec.trust_in_ai = min(0.95, sec.trust_in_ai + 0.005)

        # Democratic governance helps maintain unity
        if sec.democratic_council:
            sec.crew_unity = min(1.0, sec.crew_unity + 0.002)
            sec.trust_in_ai = min(1.0, sec.trust_in_ai + 0.001)

        # Faction formation
        if sec.crew_unity < 0.5 and generation > 3:
            sec.faction_count = max(sec.faction_count, 2)
            if sec.crew_unity < 0.3:
                sec.faction_count = max(sec.faction_count, 3)

        # Security incidents
        incident_prob = (1 - sec.crew_unity) * 0.1
        if self._rng.random() < incident_prob:
            incident = self._rng.choice([
                "argument", "vandalism", "unauthorized_access",
                "resource_hoarding", "protest",
            ])
            sec.security_incidents_total += 1

            if incident == "protest":
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": f"Gen {generation} protest: crew demanding changes to resource allocation. "
                               "AI mediation engaged.",
                    "subsystem": "defense_internal",
                })
            elif incident == "unauthorized_access":
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": "Unauthorized access to restricted compartment detected. "
                               "Non-lethal lockdown protocol.",
                    "subsystem": "defense_internal",
                })
            elif incident == "resource_hoarding":
                events.append({
                    "year": mission_year,
                    "severity": "WATCH",
                    "message": "Resource hoarding detected — AI redistributing fairly.",
                    "subsystem": "defense_internal",
                })

        # MUTINY (rare, devastating)
        mutiny_prob = max(0, (1 - sec.crew_unity) * (1 - sec.trust_in_ai) * 0.01)
        if self._rng.random() < mutiny_prob and generation > 3:
            events.append({
                "year": mission_year,
                "severity": "EMERGENCY",
                "message": f"MUTINY ATTEMPT by Gen {generation} faction. "
                           f"Crew unity: {sec.crew_unity:.0%}, AI trust: {sec.trust_in_ai:.0%}. "
                           "AI engaging non-lethal containment. Democratic council emergency session.",
                "subsystem": "defense_internal",
                "type": "mutiny",
            })
            sec.security_incidents_total += 10
            sec.crew_unity *= 0.8

            # AI response: lock sections, call emergency council
            sec.compartments_locked = min(10, sec.compartments_locked + 5)

        # Unlock compartments over time (de-escalation)
        if sec.compartments_locked > 0:
            sec.compartments_locked = max(0, sec.compartments_locked - 1)

        # ── Threat level assessment ──
        if s.shields.hull_health < 0.5 or sec.crew_unity < 0.2:
            s.threat_level = ThreatLevel.RED
        elif s.shields.hull_health < 0.7 or sec.crew_unity < 0.4:
            s.threat_level = ThreatLevel.ORANGE
        elif operational_turrets < 4 or sec.faction_count > 1:
            s.threat_level = ThreatLevel.YELLOW
        else:
            s.threat_level = ThreatLevel.GREEN

        # Non-lethal supplies degradation
        sec.sensor_coverage = max(0.5, sec.sensor_coverage - 0.002)

        return events

    def get_defense_report(self) -> dict[str, Any]:
        s = self.state
        pd = s.point_defense
        operational = sum(1 for h in pd.turret_health if h > 0.1)
        intercept_rate = (pd.interceptions_total /
                          max(pd.interceptions_total + pd.misses_total, 1)) * 100

        return {
            "threat_level": s.threat_level.name,
            "external": {
                "turrets_operational": f"{operational}/8",
                "interceptions": pd.interceptions_total,
                "misses": pd.misses_total,
                "intercept_rate": f"{intercept_rate:.1f}%",
                "shield_health": {
                    "whipple": f"{s.shields.whipple_health:.0%}",
                    "fabric": f"{s.shields.fabric_health:.0%}",
                    "hull": f"{s.shields.hull_health:.0%}",
                    "self_healing": f"{s.shields.self_healing_capacity:.0%}",
                },
            },
            "internal": {
                "crew_unity": f"{s.internal.crew_unity:.0%}",
                "trust_in_ai": f"{s.internal.trust_in_ai:.0%}",
                "factions": s.internal.faction_count,
                "democratic_council": s.internal.democratic_council,
                "incidents": s.internal.security_incidents_total,
                "compartments_locked": s.internal.compartments_locked,
            },
        }
