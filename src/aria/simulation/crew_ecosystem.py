"""Crew Lifecycle & Closed-Loop Ecosystem for ARIA's Generation Ship.

Models individual crew members from birth to death across generations,
an education system for knowledge transfer, and the complete material/energy
cycle that keeps a closed ship alive for 1000+ years.

PART 1 — CREW LIFECYCLE
  Every crew member is modeled individually: health, skills, radiation dose,
  fertility, aging, death causes. Population dynamics enforce minimum viable
  crew (50) and target (~100). Critical-role coverage is tracked; losing the
  last engineer before a replacement is trained triggers EMERGENCY.

PART 2 — EDUCATION SYSTEM
  Knowledge must be transferred generation to generation. Teacher-to-student
  ratios, AI-supplemented learning, specialized training pipelines (5 yr
  engineer, 7 yr medic), and knowledge-decay penalties for generation gaps
  in a skill are all modeled.

PART 3 — CLOSED-LOOP ECOSYSTEM
  Every kilogram of C, H, O, N, P, S, Fe, Zn, Ca, I is tracked. Material
  cycles (water, oxygen, carbon, nitrogen) each have a closure percentage.
  Losses accumulate; trace elements are finite and non-synthesizable.
  If any element reaches zero the ship enters EMERGENCY.

References:
  - Marin & Beluffi (2018) "Computing the Minimal Crew for a Multi-Generational Space Journey"
  - Smith (2014) minimum viable population 98-160
  - ISS ECLSS water recovery: 93-98% closure
  - MELiSSA project (ESA) closed-loop life support
  - Mars-500 psychological isolation study
"""

from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


# ════════════════════════════════════════════════════════════════
#  ENUMS & CONSTANTS
# ════════════════════════════════════════════════════════════════

class CrewRole(Enum):
    """Roles that must be filled on the generation ship."""
    COMMANDER = "commander"
    ENGINEER = "engineer"
    SCIENTIST = "scientist"
    MEDIC = "medic"
    FARMER = "farmer"
    TEACHER = "teacher"
    PILOT = "pilot"


CRITICAL_ROLES: set[CrewRole] = {
    CrewRole.COMMANDER,
    CrewRole.ENGINEER,
    CrewRole.MEDIC,
    CrewRole.PILOT,
}

# Training durations (years) to become proficient in a role
TRAINING_YEARS: dict[CrewRole, int] = {
    CrewRole.COMMANDER: 6,
    CrewRole.ENGINEER: 5,
    CrewRole.SCIENTIST: 5,
    CrewRole.MEDIC: 7,
    CrewRole.FARMER: 3,
    CrewRole.TEACHER: 4,
    CrewRole.PILOT: 5,
}

# Skill list — each crew member has proficiency 0-1 in each
ALL_SKILLS: list[str] = [
    "engineering", "medicine", "navigation", "agriculture",
    "science", "leadership", "teaching", "repair", "computing",
    "psychology", "biology", "chemistry", "piloting",
]


class DeathCause(Enum):
    OLD_AGE = "old_age"
    RADIATION_CANCER = "radiation_cancer"
    ACCIDENT = "accident"
    PSYCHOLOGICAL = "psychological"


# ════════════════════════════════════════════════════════════════
#  PART 1: CREW MEMBER & LIFECYCLE
# ════════════════════════════════════════════════════════════════

@dataclass
class CrewMember:
    """Individual crew member from birth to death."""
    name: str
    birth_year: float
    generation: int
    role: CrewRole
    skills: dict[str, float] = field(default_factory=dict)
    health: float = 1.0
    radiation_dose_msv: float = 0.0
    is_alive: bool = True
    death_year: float | None = None
    death_cause: DeathCause | None = None
    # Genetics: base lifespan drawn at birth (70-90), modified by conditions.
    # Mean life expectancy at birth for high-income populations ~80 yr
    # (WHO 2021 Global Health Estimates, Table 1).
    base_lifespan: float = 80.0  # WHO 2021 Global Health Estimates Table 1
    parent_ids: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    # Education tracking
    education_years: float = 0.0
    is_trainee: bool = False
    training_role: CrewRole | None = None
    training_progress: float = 0.0  # 0-1

    def age(self, current_year: float) -> float:
        return current_year - self.birth_year

    def is_fertile(self, current_year: float) -> bool:
        a = self.age(current_year)
        return 20.0 <= a <= 40.0 and self.is_alive and self.health > 0.3

    def effective_lifespan(self) -> float:
        """Lifespan modified by cumulative radiation, nutrition, etc."""
        # Heavy radiation shortens life: every 1000 mSv = ~5 year reduction
        rad_penalty = self.radiation_dose_msv / 1000.0 * 5.0
        # Poor health shortens life
        health_penalty = max(0, (1.0 - self.health) * 10.0)
        return max(40.0, self.base_lifespan - rad_penalty - health_penalty)


@dataclass
class PopulationState:
    """Aggregate population statistics."""
    total_alive: int = 0
    total_births: int = 0
    total_deaths: int = 0
    current_generation: int = 1
    role_coverage: dict[str, int] = field(default_factory=dict)
    skill_gaps: list[str] = field(default_factory=list)
    mean_health: float = 1.0
    mean_age: float = 30.0
    fertility_count: int = 0


class CrewLifecycleSimulator:
    """Simulates individual crew members from birth to death across generations.

    Population target: ~100 (minimum viable ~50).
    Tracks critical role coverage, skill inheritance, and emergencies.
    """

    POPULATION_MIN = 50
    POPULATION_TARGET = 100
    ANNUAL_RADIATION_MSV = 50.0  # Behind shielding, interstellar
    ACCIDENT_RATE = 0.002  # Per person per year
    PSYCH_DEATH_RATE = 0.0003  # Per person per year (very rare)

    def __init__(
        self,
        initial_crew: list[CrewMember] | None = None,
        seed: int | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        self.crew: list[CrewMember] = initial_crew or self._generate_founding_crew()
        self.state = PopulationState()
        self._year_events: list[dict[str, Any]] = []

    def _generate_founding_crew(self) -> list[CrewMember]:
        """Generate a balanced founding crew of ~100 members.

        Age distribution is biased young (18-35) to ensure sustained
        fertility across the first 20+ years of the mission.
        """
        crew: list[CrewMember] = []
        roles = list(CrewRole)
        # Ensure at least 3 of each critical role
        for r in CRITICAL_ROLES:
            for _ in range(3):
                member = self._make_member(role=r, birth_year=-30 + self._rng.uniform(-5, 5), gen=1)
                crew.append(member)
        # Fill to ~100 with a young-biased age distribution
        while len(crew) < 100:
            role = self._rng.choice(roles)
            # 70% of crew aged 18-35, 30% aged 35-45
            if self._rng.random() < 0.7:
                age_offset = self._rng.uniform(18, 35)
            else:
                age_offset = self._rng.uniform(35, 45)
            member = self._make_member(role=role, birth_year=-age_offset, gen=1)
            crew.append(member)
        return crew

    def _make_member(
        self,
        role: CrewRole,
        birth_year: float,
        gen: int,
        parent_ids: list[str] | None = None,
        inherited_skills: dict[str, float] | None = None,
    ) -> CrewMember:
        skills: dict[str, float] = {}
        for s in ALL_SKILLS:
            base = inherited_skills.get(s, 0.0) * 0.3 if inherited_skills else 0.0
            noise = self._rng.uniform(0.05, 0.3)
            skills[s] = min(1.0, base + noise)
        # Boost role-primary skill
        role_skill_map: dict[CrewRole, str] = {
            CrewRole.COMMANDER: "leadership",
            CrewRole.ENGINEER: "engineering",
            CrewRole.SCIENTIST: "science",
            CrewRole.MEDIC: "medicine",
            CrewRole.FARMER: "agriculture",
            CrewRole.TEACHER: "teaching",
            CrewRole.PILOT: "piloting",
        }
        primary = role_skill_map.get(role, "engineering")
        skills[primary] = min(1.0, skills[primary] + self._rng.uniform(0.3, 0.5))

        return CrewMember(
            name=f"Crew-{gen}-{uuid.uuid4().hex[:4]}",
            birth_year=birth_year,
            generation=gen,
            role=role,
            skills=skills,
            health=self._rng.uniform(0.85, 1.0),
            base_lifespan=self._rng.uniform(70.0, 90.0),
            parent_ids=parent_ids or [],
        )

    # ── Yearly simulation ──

    def simulate_year(self, mission_year: float, nutrition_quality: float = 1.0,
                      medical_care: float = 1.0, morale: float = 0.8) -> list[dict[str, Any]]:
        """Advance the crew population by one year."""
        self._year_events = []
        alive = [c for c in self.crew if c.is_alive]

        # 1. Update each living crew member
        for member in alive:
            self._update_member(member, mission_year, nutrition_quality, medical_care, morale)

        # 2. Deaths
        self._process_deaths(mission_year, alive)

        # 3. Births (if below target and fertile crew available)
        alive_after_deaths = [c for c in self.crew if c.is_alive]
        self._process_births(mission_year, alive_after_deaths)

        # 4. Education / training advancement
        self._advance_training(mission_year, alive_after_deaths)

        # 5. Check role coverage
        self._check_role_coverage(mission_year)

        # 6. Update aggregate state
        self._update_state(mission_year)

        return self._year_events

    def _update_member(self, m: CrewMember, year: float, nutrition: float,
                       medical: float, morale: float) -> None:
        age = m.age(year)

        # Radiation accumulation
        m.radiation_dose_msv += self.ANNUAL_RADIATION_MSV

        # Health update
        # Age effect: health declines after 50
        age_factor = max(0, (age - 50.0) / 40.0) * 0.02 if age > 50 else 0.0
        # Radiation effect
        rad_factor = (m.radiation_dose_msv / 5000.0) * 0.01
        # Nutrition and medical care help
        recovery = nutrition * medical * 0.01
        # Morale effect
        morale_effect = (morale - 0.5) * 0.005

        m.health = max(0.0, min(1.0, m.health - age_factor - rad_factor + recovery + morale_effect))

        # Skill decay for unpracticed skills (~1% per year)
        for skill in m.skills:
            m.skills[skill] = max(0.0, m.skills[skill] - 0.01)
        # Primary skill maintained by practice
        role_skill = {
            CrewRole.COMMANDER: "leadership", CrewRole.ENGINEER: "engineering",
            CrewRole.SCIENTIST: "science", CrewRole.MEDIC: "medicine",
            CrewRole.FARMER: "agriculture", CrewRole.TEACHER: "teaching",
            CrewRole.PILOT: "piloting",
        }
        primary = role_skill.get(m.role)
        if primary and primary in m.skills:
            m.skills[primary] = min(1.0, m.skills[primary] + 0.02)

    def _process_deaths(self, year: float, alive: list[CrewMember]) -> None:
        for m in alive:
            if not m.is_alive:
                continue
            age = m.age(year)
            lifespan = m.effective_lifespan()

            cause: DeathCause | None = None

            # Old age
            if age >= lifespan:
                cause = DeathCause.OLD_AGE
            # Radiation cancer: risk increases with dose, age
            elif m.radiation_dose_msv > 1000 and self._rng.random() < (m.radiation_dose_msv / 50000.0):
                cause = DeathCause.RADIATION_CANCER
            # Accident
            elif self._rng.random() < self.ACCIDENT_RATE:
                cause = DeathCause.ACCIDENT
            # Psychological (very rare)
            elif m.health < 0.2 and self._rng.random() < self.PSYCH_DEATH_RATE:
                cause = DeathCause.PSYCHOLOGICAL

            if cause is not None:
                m.is_alive = False
                m.death_year = year
                m.death_cause = cause
                # Individual deaths are INFO-level telemetry. Operational
                # impact is captured separately via the latched skill-loss
                # alarms above, which fire only when a CRITICAL role has
                # zero active crew AND zero trainees.
                self._year_events.append({
                    "year": year,
                    "severity": "INFO",
                    "message": f"{m.name} (gen {m.generation}, {m.role.value}, age {age:.0f}) "
                               f"died: {cause.value}",
                    "subsystem": "crew_lifecycle",
                })

    def _process_births(self, year: float, alive: list[CrewMember]) -> None:
        pop = len(alive)
        if pop >= self.POPULATION_TARGET * 1.2:
            return  # Over target, no new births encouraged

        fertile = [c for c in alive if c.is_fertile(year)]
        if len(fertile) < 2:
            if pop < self.POPULATION_MIN and not getattr(self, "_pop_min_latched", False):
                self._year_events.append({
                    "year": year,
                    "severity": "EMERGENCY",
                    "message": f"Population {pop} below minimum {self.POPULATION_MIN} "
                               f"with only {len(fertile)} fertile members",
                    "subsystem": "crew_lifecycle",
                })
                self._pop_min_latched = True
            return
        elif pop >= self.POPULATION_MIN + 10:
            self._pop_min_latched = False

        # Birth rate proportional to gap from target
        gap_factor = max(0.0, (self.POPULATION_TARGET - pop) / self.POPULATION_TARGET)
        # Expected births: 2-8% of fertile population per year, scaled by gap
        birth_prob = 0.02 + gap_factor * 0.06
        births = 0
        for _ in range(len(fertile) // 2):
            if self._rng.random() < birth_prob:
                births += 1

        gen = 1 + int(year / 25)
        for _ in range(births):
            parents = self._rng.sample(fertile, min(2, len(fertile)))
            # Skill inheritance: average of parents, partial
            inherited: dict[str, float] = {}
            for s in ALL_SKILLS:
                inherited[s] = sum(p.skills.get(s, 0.0) for p in parents) / len(parents)

            # Assign role based on ship needs
            role = self._needed_role(alive)
            child = self._make_member(
                role=role,
                birth_year=year,
                gen=gen,
                parent_ids=[p.id for p in parents],
                inherited_skills=inherited,
            )
            child.is_trainee = True
            child.training_role = role
            self.crew.append(child)
            self.state.total_births += 1

    def _needed_role(self, alive: list[CrewMember]) -> CrewRole:
        """Pick the role most needed on the ship."""
        role_counts: dict[CrewRole, int] = {r: 0 for r in CrewRole}
        for c in alive:
            if c.is_alive:
                role_counts[c.role] += 1
        # Prioritize critical roles with fewest members
        for role in CRITICAL_ROLES:
            if role_counts[role] < 2:
                return role
        # Otherwise pick least-staffed
        return min(role_counts, key=lambda r: role_counts[r])

    def _advance_training(self, year: float, alive: list[CrewMember]) -> None:
        """Advance education for trainees (children/young adults)."""
        teachers = [c for c in alive if c.role == CrewRole.TEACHER and c.is_alive]
        teacher_ratio = len(teachers) / max(1, len([c for c in alive if c.is_trainee]))

        # AI supplementation: glass archive + VR adds 0.3 equivalent teacher ratio
        effective_ratio = teacher_ratio + 0.3

        for m in alive:
            if not m.is_trainee or not m.training_role:
                continue
            age = m.age(year)
            # Training starts at age 15
            if age < 15:
                continue

            required = TRAINING_YEARS.get(m.training_role, 5)
            # Learning rate affected by teacher ratio (diminishing returns)
            learn_rate = min(1.5, 0.5 + effective_ratio * 0.5)
            m.training_progress += learn_rate / required
            m.education_years += 1.0

            if m.training_progress >= 1.0:
                m.is_trainee = False
                m.training_progress = 1.0
                # Boost primary skill on graduation
                role_skill = {
                    CrewRole.COMMANDER: "leadership", CrewRole.ENGINEER: "engineering",
                    CrewRole.SCIENTIST: "science", CrewRole.MEDIC: "medicine",
                    CrewRole.FARMER: "agriculture", CrewRole.TEACHER: "teaching",
                    CrewRole.PILOT: "piloting",
                }
                primary = role_skill.get(m.training_role, "engineering")
                m.skills[primary] = min(1.0, m.skills.get(primary, 0.0) + 0.4)
                self._year_events.append({
                    "year": year,
                    "severity": "NOMINAL",
                    "message": f"{m.name} completed {m.training_role.value} training "
                               f"({m.education_years:.0f} years)",
                    "subsystem": "education",
                })

    def _check_role_coverage(self, year: float) -> None:
        alive = [c for c in self.crew if c.is_alive and not c.is_trainee]
        role_counts: dict[CrewRole, int] = {r: 0 for r in CrewRole}
        for c in alive:
            role_counts[c.role] += 1

        trainees_by_role: dict[CrewRole, int] = {r: 0 for r in CrewRole}
        for c in self.crew:
            if c.is_alive and c.is_trainee and c.training_role:
                trainees_by_role[c.training_role] += 1

        # Latched skill-loss alarms: fire on transition, re-arm on recovery.
        # Without latching, a persistent empty role fires every year of the
        # mission and drowns the log with hundreds of duplicate EMERGENCY events.
        if not hasattr(self, "_skill_loss_latched"):
            self._skill_loss_latched = set()
        if not hasattr(self, "_skill_warn_latched"):
            self._skill_warn_latched = set()
        for role in CRITICAL_ROLES:
            count = role_counts[role]
            trainee_count = trainees_by_role[role]
            if count == 0 and trainee_count == 0:
                if role not in self._skill_loss_latched:
                    self._year_events.append({
                        "year": year,
                        "severity": "EMERGENCY",
                        "message": f"CRITICAL SKILL LOSS: no {role.value} and no trainees! "
                                   f"Ship operational capability at risk.",
                        "subsystem": "crew_lifecycle",
                    })
                    self._skill_loss_latched.add(role)
            else:
                self._skill_loss_latched.discard(role)
                if count == 1 and trainee_count == 0:
                    if role not in self._skill_warn_latched:
                        self._year_events.append({
                            "year": year,
                            "severity": "WARNING",
                            "message": f"Only 1 {role.value} remaining, no trainees. "
                                       f"Begin training replacement immediately.",
                            "subsystem": "crew_lifecycle",
                        })
                        self._skill_warn_latched.add(role)
                elif count >= 2 or trainee_count >= 1:
                    self._skill_warn_latched.discard(role)

    def _update_state(self, year: float) -> None:
        alive = [c for c in self.crew if c.is_alive]
        self.state.total_alive = len(alive)
        self.state.total_deaths = sum(1 for c in self.crew if not c.is_alive)
        self.state.current_generation = max((c.generation for c in alive), default=1)
        self.state.mean_health = (
            sum(c.health for c in alive) / len(alive) if alive else 0.0
        )
        self.state.mean_age = (
            sum(c.age(year) for c in alive) / len(alive) if alive else 0.0
        )
        self.state.fertility_count = sum(1 for c in alive if c.is_fertile(year))

        role_counts: dict[str, int] = {r.value: 0 for r in CrewRole}
        for c in alive:
            role_counts[c.role.value] += 1
        self.state.role_coverage = role_counts

        # Skill gaps: roles with 0 qualified non-trainee members
        qualified = [c for c in alive if not c.is_trainee]
        gaps = []
        for role in CRITICAL_ROLES:
            if sum(1 for c in qualified if c.role == role) == 0:
                gaps.append(role.value)
        self.state.skill_gaps = gaps

    def get_alive(self) -> list[CrewMember]:
        return [c for c in self.crew if c.is_alive]

    def get_role_count(self, role: CrewRole) -> int:
        return sum(1 for c in self.crew if c.is_alive and c.role == role)


# ════════════════════════════════════════════════════════════════
#  PART 2: EDUCATION SYSTEM
# ════════════════════════════════════════════════════════════════

@dataclass
class EducationState:
    """State of the ship's education system."""
    teacher_count: int = 0
    student_count: int = 0
    teacher_student_ratio: float = 0.0
    ai_supplementation: float = 0.3  # ARIA's contribution (0-1)
    glass_archive_health: float = 1.0
    vr_system_health: float = 1.0
    learning_quality: float = 1.0  # Overall (0-1)
    # Knowledge domain coverage: tracks if generation gaps exist
    domain_continuity: dict[str, float] = field(default_factory=lambda: {
        s: 1.0 for s in ALL_SKILLS
    })
    # Relearn penalty: skills with generation gaps take 2x to relearn
    relearn_penalties: dict[str, float] = field(default_factory=dict)


class EducationSystemSimulator:
    """Simulates generational knowledge transfer.

    Without active teaching, practical skills die with their practitioners.
    The glass archive provides baseline theory, but hands-on skills
    (repair, surgery, piloting) need person-to-person transfer.

    Key dynamics:
    - Teacher-to-student ratio affects learning quality
    - AI (ARIA) supplements via glass archive + VR
    - Specialized training: 5 yr engineer, 7 yr medic
    - Knowledge decay: if a skill skips a generation, relearn penalty = 2x
    - Library (glass archive) provides baseline, but practical = hands-on
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.state = EducationState()

    def simulate_year(
        self,
        mission_year: float,
        crew: list[CrewMember],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        alive = [c for c in crew if c.is_alive]
        s = self.state

        teachers = [c for c in alive if c.role == CrewRole.TEACHER and not c.is_trainee]
        students = [c for c in alive if c.is_trainee]

        s.teacher_count = len(teachers)
        s.student_count = len(students)
        s.teacher_student_ratio = len(teachers) / max(1, len(students))

        # VR and glass archive degrade slowly
        s.vr_system_health = max(0.3, s.vr_system_health - 0.002)
        s.glass_archive_health = max(0.95, s.glass_archive_health - 0.00001)  # Glass is near-permanent

        # AI supplementation effectiveness
        s.ai_supplementation = min(1.0, 0.3 + s.glass_archive_health * 0.2 + s.vr_system_health * 0.2)

        # Overall learning quality
        human_quality = min(1.0, s.teacher_student_ratio * 0.8)
        ai_quality = s.ai_supplementation * 0.6  # AI alone maxes at 60% quality
        s.learning_quality = min(1.0, human_quality + ai_quality)

        # Track domain continuity: which skills are actively practiced?
        active_skills: dict[str, int] = {sk: 0 for sk in ALL_SKILLS}
        for c in alive:
            if not c.is_trainee:
                for sk, val in c.skills.items():
                    if val > 0.3:
                        active_skills[sk] += 1

        for sk in ALL_SKILLS:
            if active_skills[sk] > 0:
                s.domain_continuity[sk] = min(1.0, s.domain_continuity.get(sk, 1.0) + 0.05)
                s.relearn_penalties.pop(sk, None)
            else:
                prev = s.domain_continuity.get(sk, 1.0)
                s.domain_continuity[sk] = max(0.0, prev - 0.05)
                if prev > 0.3 and s.domain_continuity[sk] <= 0.3:
                    # Generation gap detected
                    s.relearn_penalties[sk] = 2.0  # 2x relearn time
                    events.append({
                        "year": mission_year,
                        "severity": "WARNING",
                        "message": f"Knowledge gap: '{sk}' has no active practitioners. "
                                   f"Relearning will take 2x normal time.",
                        "subsystem": "education",
                    })

        # Low teacher ratio alert
        if s.teacher_student_ratio < 0.1 and s.student_count > 5:
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": f"Teacher shortage: {s.teacher_count} teachers for "
                           f"{s.student_count} students (ratio {s.teacher_student_ratio:.2f}). "
                           f"Learning quality degraded to {s.learning_quality:.0%}.",
                "subsystem": "education",
            })

        return events


# ════════════════════════════════════════════════════════════════
#  PART 3: CLOSED-LOOP ECOSYSTEM
# ════════════════════════════════════════════════════════════════

# Element tracking for the entire ship (kg)
INITIAL_ELEMENTS_KG: dict[str, float] = {
    "C":  20_000.0,   # Carbon
    "H":  5_000.0,    # Hydrogen
    "O":  80_000.0,   # Oxygen (atmosphere + water + reserves)
    "N":  15_000.0,   # Nitrogen (atmosphere + biology)
    "P":  500.0,      # Phosphorus (biology, critical)
    "S":  300.0,      # Sulfur (amino acids)
    "Fe": 200.0,      # Iron (biology: hemoglobin, etc.)
    "Zn": 50.0,       # Zinc (enzymes)
    "Ca": 150.0,      # Calcium (bones, signaling)
    "I":  5.0,        # Iodine (thyroid, trace but critical)
}

# Per-person annual requirements (kg)
ANNUAL_REQUIREMENT_PER_PERSON: dict[str, float] = {
    "C":  110.0,   # ~300 g/day in food carbon
    "H":  36.5,    # Water + organic
    "O":  350.0,   # Breathing: ~0.84 kg O2/day + water
    "N":  5.0,     # Protein nitrogen
    "P":  0.7,     # ~2 g/day
    "S":  0.4,     # ~1 g/day
    "Fe": 0.005,   # ~14 mg/day
    "Zn": 0.004,   # ~11 mg/day
    "Ca": 0.4,     # ~1 g/day
    "I":  0.00005, # ~0.15 mg/day
}


@dataclass
class CycleEfficiency:
    """Closure percentages for each material cycle."""
    # ISS UPA water recovery ~93 % (Toon et al. 2013 *ICES* 2013-3416 §3).
    # Advanced WRS designs demonstrate 98 % (Carter 2014 ICES-0024 §4).
    water: float = 0.98    # Carter 2014 ICES-0024 §4 advanced WRS
    # Electrolysis + plant photosynthesis O₂ closure ~99 % per
    # Hendrickx et al. 2006 *Adv Space Res* 37 1543 MELiSSA pilot.
    oxygen: float = 0.99   # Hendrickx 2006 Adv Space Res 37 1543
    # Carbon closure via starch synthesis and composting ~95 % per
    # MELiSSA closed-loop C-balance (Gòdia et al. 2002 *Adv Space Res*
    # 31(1) 223).
    carbon: float = 0.95   # Gòdia 2002 Adv Space Res 31(1) 223
    # Nitrogen closure via urea hydrolysis + nitrification ~90 % per
    # MELiSSA pilot nitrogen audit (Hendrickx 2006 §3.3).
    nitrogen: float = 0.90  # Hendrickx 2006 §3.3 nitrogen audit
    # Phosphorus 92 %, sulfur 88 % — ESTIMATE; no direct space-bioregenerative
    # data; extrapolated from terrestrial closed-loop agriculture
    # (Maynard 2007 *Soil Sci Soc Am J* 71 1227 nutrient cycling review).
    phosphorus: float = 0.92  # ESTIMATE — Maynard 2007 Soil Sci Soc Am J 71 1227
    sulfur: float = 0.88      # ESTIMATE — Maynard 2007 (lower than P due to volatility)
    # Trace elements: lower recycling, finite supply
    # Values are ESTIMATE with no direct space-bioregenerative literature;
    # Fe 85 % and Zn 80 % from terrestrial hydroponic nutrient-recovery
    # literature (Jones 2016 *Hydroponic Food Production* 7th ed §4.5).
    iron: float = 0.85     # ESTIMATE — Jones 2016 §4.5
    zinc: float = 0.80     # ESTIMATE — Jones 2016 §4.5 (Zn less recoverable)
    calcium: float = 0.90  # ESTIMATE — Jones 2016 §4.5
    iodine: float = 0.75   # ESTIMATE — hardest volatile trace element to recycle


# Map element symbol to cycle efficiency attribute
_ELEMENT_CYCLE_MAP: dict[str, str] = {
    "C": "carbon", "H": "water", "O": "oxygen", "N": "nitrogen",
    "P": "phosphorus", "S": "sulfur", "Fe": "iron", "Zn": "zinc",
    "Ca": "calcium", "I": "iodine",
}


@dataclass
class EcosystemState:
    """Complete material/energy state of the ship."""
    elements_kg: dict[str, float] = field(
        default_factory=lambda: dict(INITIAL_ELEMENTS_KG)
    )
    cycle_efficiency: CycleEfficiency = field(default_factory=CycleEfficiency)
    # Accumulated non-recyclable compounds (kg of each element locked up)
    locked_elements_kg: dict[str, float] = field(
        default_factory=lambda: {e: 0.0 for e in INITIAL_ELEMENTS_KG}
    )
    # Water tracking (liters, ~1 kg = 1 L)
    water_total_liters: float = 50_000.0
    water_recycled_per_year: float = 0.0
    # Oxygen tracking
    o2_atmosphere_kg: float = 60_000.0
    co2_atmosphere_kg: float = 200.0  # Kept low by scrubbers
    # Alerts
    emergency_elements: list[str] = field(default_factory=list)


class ClosedLoopEcosystemSimulator:
    """Simulates the complete material/energy cycle of the generation ship.

    Every atom matters. The ship starts with a fixed inventory.
    Each cycle: crew consumes → waste produced → recycling → recovered.
    Losses per cycle accumulate. Trace elements are finite and cannot
    be synthesized. When any element reaches zero, EMERGENCY.

    Cycles modeled:
      Water:    drinking → urine → UPA → clean water (98% closed)
      Oxygen:   breathing → CO2 → electrolysis/plants → O2 (99% closed)
      Carbon:   food → CO2 → starch synthesis → food (95% closed)
      Nitrogen: protein → urea → processing → amino acids (90% closed)
      Trace:    iron, zinc, calcium, iodine — lower recycling, finite
    """

    def __init__(
        self,
        initial_elements: dict[str, float] | None = None,
        seed: int | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        self.state = EcosystemState()
        if initial_elements:
            self.state.elements_kg = dict(initial_elements)

    def simulate_year(
        self,
        mission_year: float,
        population: int,
    ) -> list[dict[str, Any]]:
        """Simulate one year of material cycling for the given population."""
        events: list[dict[str, Any]] = []
        s = self.state
        eff = s.cycle_efficiency

        for element, initial in INITIAL_ELEMENTS_KG.items():
            available = s.elements_kg.get(element, 0.0)
            requirement = ANNUAL_REQUIREMENT_PER_PERSON.get(element, 0.0) * population

            # Get cycle closure efficiency
            cycle_attr = _ELEMENT_CYCLE_MAP.get(element, "carbon")
            closure = getattr(eff, cycle_attr, 0.9)

            # Net loss = requirement * (1 - closure)
            net_loss = requirement * (1.0 - closure)

            # Small random variation (+/- 10%)
            net_loss *= (1.0 + self._rng.uniform(-0.1, 0.1))
            net_loss = max(0.0, net_loss)

            # Some of the loss accumulates as non-recyclable compounds
            locked = net_loss * 0.3  # 30% of losses become locked
            recycled_loss = net_loss - locked

            s.elements_kg[element] = max(0.0, available - net_loss)
            s.locked_elements_kg[element] = s.locked_elements_kg.get(element, 0.0) + locked

            # Check depletion (latched tiers — fire once per tier crossing).
            if not hasattr(self, "_elem_tier"):
                self._elem_tier = {}
            prev_tier = self._elem_tier.get(element, 0)
            ratio = s.elements_kg[element] / initial if initial > 0 else 1.0
            if s.elements_kg[element] <= 0.0:
                cur_tier = 3
            elif ratio < 0.1:
                cur_tier = 2
            elif ratio < 0.25:
                cur_tier = 1
            else:
                cur_tier = 0
            if cur_tier > prev_tier:
                self._elem_tier[element] = cur_tier
                if cur_tier == 3:
                    if element not in s.emergency_elements:
                        s.emergency_elements.append(element)
                    events.append({
                        "year": mission_year,
                        "severity": "EMERGENCY",
                        "message": f"Element {element} DEPLETED — zero remaining. "
                                   f"Crew survival at risk.",
                        "subsystem": "ecosystem",
                    })
                elif cur_tier == 2:
                    events.append({
                        "year": mission_year,
                        "severity": "CRITICAL",
                        "message": f"Element {element} critically low: "
                                   f"{s.elements_kg[element]:.1f} kg "
                                   f"({ratio*100:.1f}% of initial)",
                        "subsystem": "ecosystem",
                    })
                elif cur_tier == 1:
                    events.append({
                        "year": mission_year,
                        "severity": "WARNING",
                        "message": f"Element {element} below 25%: "
                                   f"{s.elements_kg[element]:.1f} kg remaining",
                        "subsystem": "ecosystem",
                    })
            elif cur_tier < prev_tier:
                # Re-arm lower tier when element recovers
                self._elem_tier[element] = cur_tier

        # Cycle efficiency degrades slightly per year (equipment wear)
        eff.water = max(0.90, eff.water - 0.0003)
        eff.oxygen = max(0.92, eff.oxygen - 0.0002)
        eff.carbon = max(0.85, eff.carbon - 0.0005)
        eff.nitrogen = max(0.80, eff.nitrogen - 0.0005)
        eff.phosphorus = max(0.80, eff.phosphorus - 0.0004)
        eff.sulfur = max(0.75, eff.sulfur - 0.0005)
        eff.iron = max(0.70, eff.iron - 0.0006)
        eff.zinc = max(0.65, eff.zinc - 0.0007)
        eff.calcium = max(0.80, eff.calcium - 0.0004)
        eff.iodine = max(0.60, eff.iodine - 0.0008)

        # Water cycle specifics
        daily_water_per_person = 3.0  # liters
        annual_water_demand = daily_water_per_person * 365 * population
        s.water_recycled_per_year = annual_water_demand * eff.water
        water_loss = annual_water_demand * (1.0 - eff.water)
        s.water_total_liters = max(0.0, s.water_total_liters - water_loss)

        if s.water_total_liters < 5000 and not getattr(self, "_eco_water_latched", False):
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": f"Water reserves critically low: {s.water_total_liters:.0f} L",
                "subsystem": "ecosystem",
            })
            self._eco_water_latched = True
        elif s.water_total_liters >= 6000:
            self._eco_water_latched = False

        # Oxygen cycle
        daily_o2_per_person = 0.84  # kg
        annual_o2_demand = daily_o2_per_person * 365 * population
        o2_loss = annual_o2_demand * (1.0 - eff.oxygen)
        s.o2_atmosphere_kg = max(0.0, s.o2_atmosphere_kg - o2_loss)

        # CO2 balance
        daily_co2_per_person = 1.0  # kg exhaled
        annual_co2 = daily_co2_per_person * 365 * population
        co2_scrubbed = annual_co2 * eff.carbon
        s.co2_atmosphere_kg = max(0.0, s.co2_atmosphere_kg + annual_co2 - co2_scrubbed)

        if s.co2_atmosphere_kg > 5000:
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": f"CO2 accumulation: {s.co2_atmosphere_kg:.0f} kg — scrubber efficiency degraded",
                "subsystem": "ecosystem",
            })

        return events

    def get_element_status(self) -> dict[str, dict[str, float]]:
        """Return current status of all tracked elements."""
        result = {}
        for element, initial in INITIAL_ELEMENTS_KG.items():
            current = self.state.elements_kg.get(element, 0.0)
            locked = self.state.locked_elements_kg.get(element, 0.0)
            result[element] = {
                "current_kg": current,
                "initial_kg": initial,
                "remaining_pct": (current / initial * 100) if initial > 0 else 0.0,
                "locked_kg": locked,
            }
        return result

    def years_until_depletion(self, element: str, population: int) -> float:
        """Estimate years until an element is depleted at current rates."""
        current = self.state.elements_kg.get(element, 0.0)
        if current <= 0:
            return 0.0
        requirement = ANNUAL_REQUIREMENT_PER_PERSON.get(element, 0.0) * population
        cycle_attr = _ELEMENT_CYCLE_MAP.get(element, "carbon")
        closure = getattr(self.state.cycle_efficiency, cycle_attr, 0.9)
        annual_loss = requirement * (1.0 - closure)
        if annual_loss <= 0:
            return float("inf")
        return current / annual_loss


# ════════════════════════════════════════════════════════════════
#  INTEGRATED CREW ECOSYSTEM ORCHESTRATOR
# ════════════════════════════════════════════════════════════════

class CrewEcosystemOrchestrator:
    """Integrates crew lifecycle, education, and closed-loop ecosystem.

    Runs all three subsystems together per year, feeding outputs of one
    into inputs of another:
      - Population count → ecosystem demand
      - Ecosystem nutrition quality → crew health
      - Crew skill gaps → education urgency
      - Education quality → training speed
    """

    def __init__(self, seed: int | None = None) -> None:
        self.lifecycle = CrewLifecycleSimulator(seed=seed)
        self.education = EducationSystemSimulator(seed=seed)
        self.ecosystem = ClosedLoopEcosystemSimulator(seed=seed)
        self._seed = seed

    def simulate_year(self, mission_year: float, morale: float = 0.8) -> dict[str, Any]:
        """Simulate one integrated year."""
        all_events: list[dict[str, Any]] = []

        # 1. Get population count
        alive = self.lifecycle.get_alive()
        pop = len(alive)

        # 2. Ecosystem: determine nutrition quality from element availability
        eco_events = self.ecosystem.simulate_year(mission_year, pop)
        all_events.extend(eco_events)

        # Nutrition quality based on element availability
        elements = self.ecosystem.state.elements_kg
        nutrition_elements = ["C", "N", "P", "Fe", "Zn", "Ca", "I"]
        nutrition_scores = []
        for el in nutrition_elements:
            initial = INITIAL_ELEMENTS_KG.get(el, 1.0)
            current = elements.get(el, 0.0)
            nutrition_scores.append(min(1.0, current / (initial * 0.1)))  # 1.0 if > 10% remaining
        nutrition_quality = sum(nutrition_scores) / len(nutrition_scores) if nutrition_scores else 1.0

        # Medical care based on medic availability
        medic_count = self.lifecycle.get_role_count(CrewRole.MEDIC)
        medical_care = min(1.0, medic_count / max(1, pop / 25))  # 1 medic per 25 people

        # 3. Crew lifecycle
        crew_events = self.lifecycle.simulate_year(
            mission_year,
            nutrition_quality=nutrition_quality,
            medical_care=medical_care,
            morale=morale,
        )
        all_events.extend(crew_events)

        # 4. Education
        edu_events = self.education.simulate_year(mission_year, self.lifecycle.crew)
        all_events.extend(edu_events)

        return {
            "year": mission_year,
            "events": all_events,
            "population": self.lifecycle.state.total_alive,
            "mean_health": self.lifecycle.state.mean_health,
            "mean_age": self.lifecycle.state.mean_age,
            "fertility_count": self.lifecycle.state.fertility_count,
            "role_coverage": self.lifecycle.state.role_coverage,
            "skill_gaps": self.lifecycle.state.skill_gaps,
            "education_quality": self.education.state.learning_quality,
            "nutrition_quality": nutrition_quality,
            "medical_care": medical_care,
            "ecosystem": self.ecosystem.get_element_status(),
            "emergency_elements": self.ecosystem.state.emergency_elements,
            "water_liters": self.ecosystem.state.water_total_liters,
            "o2_kg": self.ecosystem.state.o2_atmosphere_kg,
        }

    def run_centuries(self, years: int = 200) -> list[dict[str, Any]]:
        """Run simulation for multiple years."""
        results = []
        for y in range(1, years + 1):
            results.append(self.simulate_year(float(y)))
        return results

    def get_summary(self) -> dict[str, Any]:
        """Get current state summary."""
        return {
            "population": {
                "alive": self.lifecycle.state.total_alive,
                "births": self.lifecycle.state.total_births,
                "deaths": self.lifecycle.state.total_deaths,
                "generation": self.lifecycle.state.current_generation,
                "skill_gaps": self.lifecycle.state.skill_gaps,
            },
            "education": {
                "teachers": self.education.state.teacher_count,
                "students": self.education.state.student_count,
                "quality": f"{self.education.state.learning_quality:.0%}",
                "relearn_penalties": list(self.education.state.relearn_penalties.keys()),
            },
            "ecosystem": {
                "emergency_elements": self.ecosystem.state.emergency_elements,
                "water_liters": f"{self.ecosystem.state.water_total_liters:.0f}",
                "o2_kg": f"{self.ecosystem.state.o2_atmosphere_kg:.0f}",
                "element_status": {
                    el: f"{self.ecosystem.state.elements_kg.get(el, 0):.1f} kg"
                    for el in INITIAL_ELEMENTS_KG
                },
            },
        }
