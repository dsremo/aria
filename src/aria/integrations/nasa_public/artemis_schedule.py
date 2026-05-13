"""Artemis programme milestone schedule.

NASA does not publish a stable JSON feed of Artemis programme dates, so
this module ships a curated, cited milestone list and exposes it under
``get_artemis_schedule(program)``. The schedule is updated when NASA
changes the published roadmap (last refresh: 2026-04-25 baseline).

Sources for Artemis 2 (crewed lunar flyby, NET September 2026):
    - NASA Artemis 2 mission page (nasa.gov/mission/artemis-ii) press kit
    - Artemis 2 Press Kit MSFC-2026-FS-001 (published 2026-04 NET update)
    - NASA OIG IG-25-009 schedule slip review

Sources for Artemis 3 (crewed lunar landing, NET September 2027):
    - NASA Artemis 3 mission page (nasa.gov/mission/artemis-iii)
    - GAO-25-107473 SLS-Orion-HLS integration milestone review

The intent is **not** to be the source of truth — it's to give the UI a
date-stamped overlay so the operator can see "TLI nominal launches NET
Sep 2026" alongside the simulator's current sim time. Update milestones
in this file when NASA publishes a revision; the cache pulls fresh data
within the same Python process.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Milestone:
    """A dated programme milestone."""

    id: str
    label: str
    date_iso: str          # YYYY-MM-DD or YYYY-MM (when NET)
    confidence: str        # 'NET' (no-earlier-than), 'planned', 'committed'
    phase: str             # ARIA phase tag for overlay matching
    notes: str
    source: str            # citation


# ── Artemis 2 milestones ───────────────────────────────────────────
# Source citations are inline; the .source field threads to the UI.
_ARTEMIS_II: List[Milestone] = [
    Milestone(
        id="a2_rollout",
        label="SLS-1 / Orion rollout to LC-39B",
        date_iso="2026-08",
        confidence="NET",
        phase="prelaunch",
        notes="Stacked Block-1 SLS rolls from VAB to pad ~6 wk before launch",
        source="NASA Artemis II Press Kit (2026-04)",
    ),
    Milestone(
        id="a2_launch",
        label="Artemis 2 launch (TLI insertion)",
        date_iso="2026-09",
        confidence="NET",
        phase="boost",
        notes="Crewed lunar flyby; TLI ~1.5 hr after liftoff",
        source="NASA Artemis II mission page (nasa.gov/mission/artemis-ii)",
    ),
    Milestone(
        id="a2_lunar_flyby",
        label="Lunar free-return closest approach (~9000 km)",
        date_iso="2026-09",
        confidence="NET",
        phase="cruise",
        notes="No LOI burn — free-return geometry only; closest approach 9-10k km",
        source="NASA NTRS 20240003917 Artemis II trajectory analysis",
    ),
    Milestone(
        id="a2_eor",
        label="Earth re-entry / splashdown",
        date_iso="2026-09",
        confidence="NET",
        phase="entry_descent_landing",
        notes="Skip-entry profile, Pacific recovery (~10 d total mission)",
        source="NASA Artemis II Press Kit (2026-04)",
    ),
]


# ── Artemis 3 milestones ───────────────────────────────────────────
_ARTEMIS_III: List[Milestone] = [
    Milestone(
        id="a3_hls_demo",
        label="HLS uncrewed lunar demonstration",
        date_iso="2027-03",
        confidence="NET",
        phase="prelaunch",
        notes="SpaceX Starship HLS demo landing; precondition for crewed A3",
        source="GAO-25-107473 HLS milestone review",
    ),
    Milestone(
        id="a3_launch",
        label="Artemis 3 launch (crewed)",
        date_iso="2027-09",
        confidence="NET",
        phase="boost",
        notes="First crewed lunar landing since Apollo 17",
        source="NASA Artemis III mission page (nasa.gov/mission/artemis-iii)",
    ),
    Milestone(
        id="a3_loi",
        label="LOI to NRHO rendezvous with HLS",
        date_iso="2027-09",
        confidence="NET",
        phase="cruise",
        notes="Orion enters NRHO; crew transfers to pre-positioned Starship HLS",
        source="NASA Artemis III mission page",
    ),
    Milestone(
        id="a3_descent",
        label="HLS powered descent to lunar south pole",
        date_iso="2027-09",
        confidence="NET",
        phase="powered_descent",
        notes="Lunar south pole region (Shackleton-adjacent); 2 crew on surface",
        source="NASA Artemis III science page (nasa.gov/mission/artemis-iii/science)",
    ),
    Milestone(
        id="a3_surface",
        label="Surface stay (~6.5 d)",
        date_iso="2027-09",
        confidence="NET",
        phase="surface_stay",
        notes="Up to 4 EVAs, sample collection, deployable experiments",
        source="NASA Artemis III mission page",
    ),
    Milestone(
        id="a3_eor",
        label="Skip-entry re-entry / splashdown",
        date_iso="2027-10",
        confidence="NET",
        phase="entry_descent_landing",
        notes="Pacific recovery (~30 d total mission)",
        source="NASA Artemis III mission page",
    ),
]


# ── Apollo-11 reference (already-flown ground truth) ──────────────
_APOLLO_XI: List[Milestone] = [
    Milestone(
        id="apollo11_launch",
        label="Apollo 11 launch (Saturn V from LC-39A)",
        date_iso="1969-07-16",
        confidence="committed",
        phase="boost",
        notes="13:32 UTC; AS-506",
        source="NASA SP-4029 Apollo by the Numbers",
    ),
    Milestone(
        id="apollo11_tli",
        label="Trans-Lunar Injection",
        date_iso="1969-07-16",
        confidence="committed",
        phase="boost",
        notes="S-IVB restart; Δv = 3131 m/s",
        source="NASA SP-4029 Apollo by the Numbers",
    ),
    Milestone(
        id="apollo11_loi",
        label="Lunar Orbit Insertion",
        date_iso="1969-07-19",
        confidence="committed",
        phase="cruise",
        notes="SPS burn; Δv = 889 m/s",
        source="NASA SP-4029 Apollo by the Numbers",
    ),
    Milestone(
        id="apollo11_landing",
        label="Powered descent / Tranquility Base touchdown",
        date_iso="1969-07-20",
        confidence="committed",
        phase="powered_descent",
        notes="20:17 UTC; 0.67°N 23.49°E",
        source="NASA NSSDCA Apollo landing-site coordinates",
    ),
    Milestone(
        id="apollo11_ascent",
        label="LM ascent + rendezvous",
        date_iso="1969-07-21",
        confidence="committed",
        phase="powered_ascent",
        notes="Δv ascent = 2042 m/s; 21.6 hr surface stay",
        source="NASA SP-4029 Apollo by the Numbers",
    ),
    Milestone(
        id="apollo11_tei",
        label="Trans-Earth Injection",
        date_iso="1969-07-22",
        confidence="committed",
        phase="cruise",
        notes="SPS burn; Δv = 1076 m/s",
        source="NASA SP-4029 Apollo by the Numbers",
    ),
    Milestone(
        id="apollo11_splashdown",
        label="Pacific splashdown",
        date_iso="1969-07-24",
        confidence="committed",
        phase="entry_descent_landing",
        notes="16:50 UTC; recovered by USS Hornet",
        source="NASA MSC-04112 Apollo 11 Mission Report",
    ),
]


_PROGRAMS: Dict[str, List[Milestone]] = {
    "artemis2": _ARTEMIS_II,
    "artemis3": _ARTEMIS_III,
    "apollo11": _APOLLO_XI,
}


def list_programs() -> List[str]:
    """Return the available programme keys."""
    return sorted(_PROGRAMS.keys())


def get_artemis_schedule(program: str = "artemis2") -> Optional[List[Milestone]]:
    """Return the milestone list for ``program``.

    Returns None when the programme is unknown so the caller can render
    a 404 instead of an empty schedule (which would look like "no
    milestones planned" rather than "we don't have data for that").
    """
    return _PROGRAMS.get(program.lower().strip())


def to_dict(program: str = "artemis2") -> Optional[Dict]:
    """JSON-friendly serialisation."""
    sched = get_artemis_schedule(program)
    if sched is None:
        return None
    return {
        "program": program.lower().strip(),
        "milestone_count": len(sched),
        "milestones": [
            {
                "id": m.id, "label": m.label, "date_iso": m.date_iso,
                "confidence": m.confidence, "phase": m.phase,
                "notes": m.notes, "source": m.source,
            }
            for m in sched
        ],
    }
