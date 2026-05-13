"""Subsystem-specific filters that decide which arXiv papers are relevant.

Each filter is a (name, arXiv categories, keyword set, must-have-terms)
tuple. A paper matches if any keyword appears in title or abstract,
AND any must-have term (if present) also appears.

Keyword lists are intentionally narrow — broad words like "AI" or
"system" would flood the digest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from aria.research.arxiv_client import ArxivPaper


@dataclass(frozen=True)
class ResearchFilter:
    name: str
    description: str
    categories: Tuple[str, ...]
    keywords: Tuple[str, ...]
    must_have_any: Tuple[str, ...] = ()

    def matches(self, paper: ArxivPaper) -> bool:
        haystack = f"{paper.title} {paper.summary}".lower()
        if not any(kw.lower() in haystack for kw in self.keywords):
            return False
        if self.must_have_any and not any(
            mh.lower() in haystack for mh in self.must_have_any
        ):
            return False
        # Category gate: at least one of the paper's categories must
        # be in our list (primary_category or secondary).
        paper_cats = {paper.primary_category, *paper.categories}
        return any(cat in paper_cats for cat in self.categories)


# ── Default filter set ──────────────────────────────────────────


DEFAULT_FILTERS: Tuple[ResearchFilter, ...] = (
    ResearchFilter(
        name="autonomy",
        description=(
            "Spacecraft autonomy + onboard decision making — the LLM-in-loop"
            " research area where ARIA's cognitive engine sits."
        ),
        categories=("cs.RO", "cs.AI"),
        keywords=(
            "spacecraft autonomy",
            "satellite autonomy",
            "onboard decision",
            "autonomous spacecraft",
            "autonomous satellite",
            "in-orbit autonomy",
            "AEGIS",
            "MEXEC",
            "ASPEN",
        ),
    ),
    ResearchFilter(
        name="ml_safety",
        description=(
            "ML safety + alignment work directly relevant to ARIA's"
            " F-1..F-19 safety architecture and sandbagging detector."
        ),
        categories=("cs.LG", "cs.AI"),
        keywords=(
            "alignment",
            "RLHF",
            "constitutional",
            "deceptive alignment",
            "sandbagging",
            "robustness verification",
            "specification gaming",
            "reward hacking",
            "interpretability",
        ),
        must_have_any=(
            "safety",
            "safe",
            "alignment",
            "verification",
            "robust",
        ),
    ),
    ResearchFilter(
        name="guidance_navigation",
        description=(
            "GNC research — MPC, SCP, Kalman filtering — the deterministic"
            " safety gate that sits underneath ARIA's LLM advisor."
        ),
        categories=("cs.RO", "math.OC", "eess.SY"),
        keywords=(
            "model predictive control",
            "sequential convex programming",
            "trajectory optimization",
            "Kalman filter",
            "attitude control",
            "rendezvous",
            "docking",
            "orbit determination",
        ),
        must_have_any=(
            "spacecraft",
            "satellite",
            "trajectory",
            "orbit",
            "rendezvous",
        ),
    ),
    ResearchFilter(
        name="life_support",
        description=(
            "Bioregenerative life support, ECLSS — the literature ARIA's"
            " physics/bioregen module tracks against."
        ),
        categories=("q-bio.OT", "physics.bio-ph"),
        keywords=(
            "MELiSSA",
            "bioregenerative",
            "ECLSS",
            "life support",
            "Spirulina",
            "closed loop ecology",
            "Arthrospira",
            "controlled ecological life support",
        ),
    ),
    ResearchFilter(
        name="propulsion",
        description=(
            "Spacecraft propulsion — Hall thrusters, ion engines,"
            " chemical propulsion, propellant management."
        ),
        categories=("physics.flu-dyn", "physics.space-ph"),
        keywords=(
            "Hall thruster",
            "ion thruster",
            "ion engine",
            "Hall-effect thruster",
            "electric propulsion",
            "specific impulse",
            "plasma thruster",
            "VASIMR",
        ),
    ),
    ResearchFilter(
        name="radiation",
        description=(
            "Radiation environment + transport — galactic cosmic rays,"
            " solar particle events, shielding design."
        ),
        categories=("physics.med-ph", "physics.space-ph"),
        keywords=(
            "galactic cosmic ray",
            "GCR",
            "solar particle event",
            "SPE",
            "cosmic radiation",
            "radiation shielding",
            "single event upset",
            "SEU",
            "total ionizing dose",
        ),
        must_have_any=(
            "spacecraft",
            "satellite",
            "astronaut",
            "shielding",
            "spaceflight",
        ),
    ),
    ResearchFilter(
        name="conjunction",
        description=(
            "Orbital debris + conjunction analysis — feeds ARIA's"
            " aria.conjunction screening module."
        ),
        categories=("astro-ph.EP", "astro-ph.IM"),
        keywords=(
            "conjunction analysis",
            "collision probability",
            "orbital debris",
            "TLE catalog",
            "space debris",
            "close approach",
            "conjunction screening",
            "satellite collision",
        ),
    ),
)
