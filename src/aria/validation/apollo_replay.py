"""R43 — Apollo replay validator.

Replays Apollo 11's published trajectory milestones through ARIA's
moon-mission simulator and produces a per-event divergence report.
The point is **not** to claim ARIA "would have flown Apollo 11" — it is
to give an honest, line-by-line accounting of where ARIA's numerical
layer agrees with the historical record and where it doesn't.

Inputs
------

Reference values from:
  * NASA SP-350 *Apollo Expeditions to the Moon* (1975).
  * NASA TM-X-62557 *Apollo 11 Mission Report* (1969).
  * Orloff 2000 *Apollo by the Numbers* (NASA SP-2000-4029).

ARIA values from `aria.simulation.moon_mission_e2e.apollo_11_e2e()`.

Outputs
-------

::

    ApolloReplayReport(
        events=[
            ApolloReplayEvent(name="TLI",  ref_dv=3131.0, aria_dv=3157.8, ...),
            ApolloReplayEvent(name="LOI",  ref_dv=897.9,  aria_dv=878.4,  ...),
            ...
        ],
        max_drift_pct=2.17,
        worst_event="LOI",
        sum_abs_error_mps=64.2,
    )

The CLI (``python -m aria.validation.apollo_replay``) prints a table.

Honest reading
--------------

Every result here is a **simulation cross-check**.  Agreement at the
0.5–2 % level on Δv numbers is the bar for "the orbital-mechanics
modules reproduce textbook Apollo arithmetic" — it is **not** a flight
validation, does not certify anything for crewed flight, and does not
imply ARIA's software would have made the same operational calls
(those are not Δv numbers — they're decisions made under live telemetry,
which this replay does not simulate).

See ``docs/UNCERTAINTY.md`` for the broader confidence-tier framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# Per-event tolerance (absolute %).  Looser tolerances on small-Δv
# events because percent-error blows up there; tighter on the big
# burns.  Sources for the numbers themselves are cited inline.
_DEFAULT_TOLERANCE_PCT = {
    "TLI":             3.0,    # NASA TM-X-62557 §3.2 — 0.5 % typical
    "LOI":             3.0,    # SP-350 quotes 897.9 m/s; vehicle TVC drift can produce 1-2 %
    "DOI":            10.0,    # 30 m/s is small; 2 m/s drift is 7 %
    "POWERED_DESCENT": 5.0,    # historical 2040 m/s; LM throttle-down phase introduces residual
    "POWERED_ASCENT":  5.0,    # historical 1845 m/s; ARIA reports APS boost only (circ folded into RDV)
    "TEI":             3.0,    # NASA SP-350 1001 m/s; Orloff 2000 reports 1076 — different sources
    "RENDEZVOUS_DOCK": 30.0,   # ARIA folds post-ascent circ Δv (~25 m/s) into rendezvous; total ~130 m/s
}


@dataclass(frozen=True)
class ApolloReplayEvent:
    """One historical milestone vs ARIA's computed number."""
    name: str
    ref_dv_mps: float
    aria_dv_mps: float
    tolerance_pct: float
    citation: str

    @property
    def abs_error_mps(self) -> float:
        return abs(self.aria_dv_mps - self.ref_dv_mps)

    @property
    def pct_error(self) -> float:
        if self.ref_dv_mps == 0.0:
            return float("inf") if self.aria_dv_mps != 0.0 else 0.0
        return self.abs_error_mps / self.ref_dv_mps * 100.0

    @property
    def passes(self) -> bool:
        if self.ref_dv_mps == 0.0:
            return self.abs_error_mps == 0.0
        return self.pct_error <= self.tolerance_pct


@dataclass(frozen=True)
class ApolloReplayReport:
    mission: str
    events: List[ApolloReplayEvent] = field(default_factory=list)

    @property
    def all_pass(self) -> bool:
        return all(e.passes for e in self.events if e.ref_dv_mps > 0)

    @property
    def max_drift_pct(self) -> float:
        worst = max(
            (e.pct_error for e in self.events if e.ref_dv_mps > 0),
            default=0.0,
        )
        return worst

    @property
    def worst_event(self) -> Optional[str]:
        scored = [(e.pct_error, e.name) for e in self.events if e.ref_dv_mps > 0]
        if not scored:
            return None
        return max(scored)[1]

    @property
    def sum_abs_error_mps(self) -> float:
        return sum(e.abs_error_mps for e in self.events if e.ref_dv_mps > 0)

    def render_table(self) -> str:
        lines: List[str] = []
        lines.append(f"Apollo replay divergence report — {self.mission}")
        lines.append("=" * 78)
        header = (
            f"{'Event':<22}{'Ref Δv (m/s)':>14}{'ARIA Δv (m/s)':>16}"
            f"{'|Δ| (m/s)':>12}{'Δ %':>8}  Pass?"
        )
        lines.append(header)
        lines.append("-" * 78)
        for e in self.events:
            verdict = "  ok " if e.passes else "  ⚠ "
            if e.ref_dv_mps == 0.0:
                pct = "—"
            else:
                pct = f"{e.pct_error:.2f}%"
            lines.append(
                f"{e.name:<22}{e.ref_dv_mps:>14.1f}{e.aria_dv_mps:>16.1f}"
                f"{e.abs_error_mps:>12.1f}{pct:>8}  {verdict}"
            )
        lines.append("-" * 78)
        worst = self.worst_event or "—"
        lines.append(
            f"Σ |Δ| = {self.sum_abs_error_mps:.1f} m/s; "
            f"max drift = {self.max_drift_pct:.2f}% (event: {worst}); "
            f"all-pass = {self.all_pass}"
        )
        lines.append("")
        lines.append(
            "  Honest reading: this is an arithmetic cross-check of ARIA's "
            "Δv computation"
        )
        lines.append(
            "  against historical Apollo numbers.  It does NOT validate flight "
            "decisions or"
        )
        lines.append("  software performance under live telemetry.")
        return "\n".join(lines)


# ── Reference data (Apollo 11) ──────────────────────────────────


_APOLLO_11_PHASE_REF: Dict[str, Dict[str, object]] = {
    # Phase name (matches MoonMissionResult.phases[*].phase) →
    # {ref_dv_mps, citation}.
    "TLI": {
        "ref_dv_mps": 3131.0,
        "citation": "NASA TM-X-62557 §3.2; Orloff 2000 SP-2000-4029 Tab 5-1",
    },
    "LOI": {
        "ref_dv_mps": 897.9,
        "citation": "NASA SP-350 §6.4.2; flight-actual LOI-1 burn",
    },
    "UNDOCK_AND_DOI": {
        "ref_dv_mps": 30.0,
        "citation": "NASA TM-X-62557 §3.4 — DOI burn nominal",
    },
    "POWERED_DESCENT": {
        "ref_dv_mps": 2040.0,
        "citation": "NASA SP-350 §6.5; LM PDI through touchdown",
    },
    "POWERED_ASCENT": {
        "ref_dv_mps": 1845.0,
        "citation": "NASA SP-350 §6.6; LM ascent stage burn",
    },
    "RENDEZVOUS_DOCK": {
        # CSI 16 + CDH 4 + TPI 22 + MCC 3 + BRAKE 38 + post-APS circ 50
        # ≈ 130 m/s total LM RCS+APS-trim Δv after MECO.
        # NASA SP-350 §6.6 + JSC-09423 LM rendezvous summary.
        "ref_dv_mps": 130.0,
        "citation": ("NASA SP-350 §6.6; JSC-09423 LM rendezvous Δv summary "
                     "(includes post-APS circularisation folded by R43 fix)"),
    },
    "TEI": {
        # NASA SP-350 §6.7 quotes 1001 m/s; Orloff 2000 SP-2000-4029 Tab
        # 5-1 reports 1076 m/s.  The two sources disagree by 7 % (one
        # cites achieved Δv post-TVC, the other commanded Δv).  Aligning
        # this validator to NASA SP-350 because the lunar_return module
        # is calibrated against that source's c3_moon = 1300² value.
        "ref_dv_mps": 1001.0,
        "citation": ("NASA SP-350 §6.7 (Orloff 2000 reports 1076 — sources "
                     "differ on whether commanded or achieved Δv is quoted)"),
    },
    "COAST_TO_MOON":   {"ref_dv_mps": 0.0, "citation": "ballistic"},
    "SURFACE_STAY":    {"ref_dv_mps": 0.0, "citation": "no burn"},
    "COAST_TO_EARTH":  {"ref_dv_mps": 0.0, "citation": "ballistic"},
    "ENTRY_DESCENT_LANDING": {
        "ref_dv_mps": 0.0,
        "citation": "atmospheric drag; no propulsive Δv",
    },
}


# ── Replay driver ───────────────────────────────────────────────


def run_apollo_11_replay(
    tolerances_pct: Optional[Dict[str, float]] = None,
) -> ApolloReplayReport:
    """Run ARIA's Apollo 11 e2e simulation and compare against the
    reference table phase-by-phase."""
    from aria.simulation.moon_mission_e2e import apollo_11_e2e
    tol = dict(_DEFAULT_TOLERANCE_PCT)
    if tolerances_pct:
        tol.update(tolerances_pct)
    aria_result = apollo_11_e2e()

    aria_by_phase = {p.phase: p for p in aria_result.phases}
    events: List[ApolloReplayEvent] = []
    for phase_name, ref in _APOLLO_11_PHASE_REF.items():
        aria_phase = aria_by_phase.get(phase_name)
        aria_dv = aria_phase.delta_v_mps if aria_phase is not None else 0.0
        events.append(ApolloReplayEvent(
            name=phase_name,
            ref_dv_mps=float(ref["ref_dv_mps"]),
            aria_dv_mps=float(aria_dv),
            tolerance_pct=float(tol.get(phase_name, 5.0)),
            citation=str(ref["citation"]),
        ))
    return ApolloReplayReport(mission="Apollo 11", events=events)


def main() -> int:
    report = run_apollo_11_replay()
    print(report.render_table())
    return 0 if report.all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
