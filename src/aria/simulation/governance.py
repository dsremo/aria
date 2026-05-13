"""Governance & Justice System for a Generation Ship.

THE ETHICIST'S QUESTIONS:
  - Children born on ship never consented to this mission
  - Who decides who can have children? (population control)
  - What's the legal framework? Ship's constitution?
  - Crime and punishment in a closed society
  - Leadership succession across 40+ generations

THE CRIMINOLOGIST'S QUESTIONS:
  - Theft of resources (water, food rations)
  - Violence (assault, murder — in a society you can never leave)
  - Sabotage (disgruntled crew damaging systems)
  - You can't imprison people — the ship needs every hand

GOVERNANCE MODEL:
  Constitutional democracy with:
  - Ship's Constitution (written by founders, amendable by supermajority)
  - Council of 7 (elected every 5 years, 2 term limit)
  - Captain (elected by council, emergency powers time-limited)
  - ARIA as impartial referee (enforces constitution, not faction politics)
  - Judiciary: 3-person tribunal for disputes
  - No death penalty (population too small)
  - Rehabilitation over punishment (community service, education)
  - Population targets: council votes on birth permits based on resources
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class GovernanceState:
    """Government and justice system state."""
    # Constitution
    constitution_version: int = 1
    amendments_passed: int = 0
    constitutional_crises: int = 0

    # Leadership
    council_members: int = 7
    council_election_year: float = 0.0
    captain_name: str = "Founder-Captain"
    captain_tenure_years: float = 0.0
    leadership_transitions: int = 0

    # Democracy health
    voter_participation: float = 0.85  # 85% turnout
    political_parties: int = 1  # 1 = consensus, 2+ = factions
    trust_in_government: float = 0.8
    freedom_index: float = 0.9  # 0 = authoritarian, 1 = free

    # Justice
    crimes_total: int = 0
    crimes_this_year: int = 0
    active_sentences: int = 0  # People on community service
    tribunals_held: int = 0
    appeals_granted: int = 0

    # Population control
    birth_permits_issued: int = 0
    birth_permit_queue: int = 0  # Couples waiting
    population_target: int = 100

    # Consent and rights
    generation_consent_score: float = 1.0  # Gen 1 = 1.0, decays
    child_rights_index: float = 0.9  # Education, play, health
    elder_care_index: float = 0.8


class GovernanceSimulator:
    """Simulates governance, justice, and social contract across generations."""

    def __init__(self, crew_size: int = 4, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._crew_size = crew_size
        self.state = GovernanceState(population_target=max(50, crew_size * 2))

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state
        generation = 1 + int(mission_year / 25)

        # ── Elections every 5 years ──
        if mission_year > 0 and mission_year % 5 == 0:
            s.council_election_year = mission_year
            # Voter participation declines with apathy
            s.voter_participation = max(0.3, s.voter_participation - 0.005)
            # Random chance of contested election
            if self._rng.random() < 0.1:
                s.political_parties = min(4, s.political_parties + 1)
                events.append({
                    "year": mission_year, "severity": "WATCH",
                    "message": f"New political faction formed. {s.political_parties} parties.",
                    "subsystem": "governance",
                })

        # ── Captain succession every 10-15 years ──
        s.captain_tenure_years += 1
        if s.captain_tenure_years > 10 and self._rng.random() < 0.1:
            s.captain_name = f"Captain-Gen{generation}"
            s.captain_tenure_years = 0
            s.leadership_transitions += 1
            events.append({
                "year": mission_year, "severity": "NOMINAL",
                "message": f"Leadership transition: {s.captain_name} elected.",
                "subsystem": "governance",
            })

        # ── Consent decay across generations ──
        if generation > 1:
            s.generation_consent_score = max(0.2, 1.0 - (generation - 1) * 0.03)

        # ── Crime ──
        # Crime rate: ~2% base, increases with low trust/resources
        crime_rate = 0.02 * (2.0 - s.trust_in_government)
        crimes = max(0, int(self._crew_size * crime_rate))
        s.crimes_this_year = crimes
        s.crimes_total += crimes

        if crimes > 0:
            # Type distribution
            for _ in range(crimes):
                crime_type = self._rng.choice([
                    "resource_theft", "assault", "vandalism",
                    "unauthorized_access", "insubordination",
                ])
                s.tribunals_held += 1
                s.active_sentences += 1

            if crimes > 3:
                events.append({
                    "year": mission_year, "severity": "WARNING",
                    "message": f"Crime spike: {crimes} incidents. "
                               f"Trust in government: {s.trust_in_government:.0%}",
                    "subsystem": "governance",
                })

        # Sentences expire (community service ~1 year)
        s.active_sentences = max(0, s.active_sentences - max(1, s.active_sentences // 2))

        # ── Trust dynamics ──
        if s.freedom_index < 0.5:
            s.trust_in_government = max(0.1, s.trust_in_government - 0.02)
        if s.voter_participation > 0.6:
            s.trust_in_government = min(0.95, s.trust_in_government + 0.005)

        # ── Constitutional crisis (rare) ──
        if s.trust_in_government < 0.3 and self._rng.random() < 0.05:
            s.constitutional_crises += 1
            events.append({
                "year": mission_year, "severity": "CRITICAL",
                "message": f"Constitutional crisis #{s.constitutional_crises}: "
                           f"government legitimacy questioned. Emergency council session.",
                "subsystem": "governance",
            })

        # ── Population control ──
        # Birth permits based on resource availability
        s.birth_permits_issued = max(0, (s.population_target - self._crew_size) // 5)

        return events

    def get_governance_report(self) -> dict[str, Any]:
        s = self.state
        return {
            "constitution_version": s.constitution_version,
            "council_members": s.council_members,
            "captain": s.captain_name,
            "voter_participation": f"{s.voter_participation:.0%}",
            "political_parties": s.political_parties,
            "trust": f"{s.trust_in_government:.0%}",
            "freedom_index": f"{s.freedom_index:.0%}",
            "total_crimes": s.crimes_total,
            "active_sentences": s.active_sentences,
            "constitutional_crises": s.constitutional_crises,
            "generation_consent": f"{s.generation_consent_score:.0%}",
        }
