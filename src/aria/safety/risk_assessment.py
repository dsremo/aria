"""Mission risk assessment — FMEA + probabilistic failure analysis.

Provides tools for quantitative risk assessment:
- **FMEA** (Failure Modes and Effects Analysis): ranked list of failure
  modes by severity × likelihood × detection difficulty
- **Fault tree analysis**: top-event probability from component failures
- **Mission success probability**: serial + parallel component reliability
- **Redundancy analysis**: N-of-M voting configurations

Used during design reviews (PDR, CDR) to:
- Identify single-point failures
- Prioritize redundancy investments
- Size spares/margins
- Compare architectural options

References:
    MIL-STD-1629A (1980) Procedures for Performing FMECA
    NASA/SP-2010-576: NASA System Safety Handbook Vol 1
    Bedford & Cooke (2001) "Probabilistic Risk Analysis"
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ══════════════════════════════════════════════════════════════════
#  FMEA data structures
# ══════════════════════════════════════════════════════════════════

@dataclass
class FailureMode:
    """A single failure mode in FMEA."""
    component: str
    mode: str                        # e.g., "short-circuit", "stuck-open"
    effect_local: str                # immediate component effect
    effect_system: str               # propagated system effect
    severity: int                    # 1-10 (10 = loss of mission/crew)
    occurrence: int                  # 1-10 (10 = frequent)
    detection: int                   # 1-10 (10 = undetectable)
    mitigation: str = ""

    @property
    def rpn(self) -> int:
        """Risk Priority Number = S × O × D (1-1000)."""
        return self.severity * self.occurrence * self.detection

    @property
    def criticality_class(self) -> str:
        """MIL-STD-1629A criticality classification."""
        rpn = self.rpn
        if rpn >= 200:
            return "CRITICAL"
        elif rpn >= 100:
            return "MAJOR"
        elif rpn >= 50:
            return "MODERATE"
        return "MINOR"


class FMEA:
    """Failure Modes and Effects Analysis registry.

    Usage:
        fmea = FMEA()
        fmea.add(FailureMode(component="RCS valve",
                              mode="stuck_open",
                              effect_local="uncontrolled thrust",
                              effect_system="attitude loss",
                              severity=9, occurrence=3, detection=4))
        fmea.sorted_by_rpn()  # returns ranked list
    """

    def __init__(self) -> None:
        self._modes: List[FailureMode] = []

    def add(self, mode: FailureMode) -> None:
        """Register a failure mode."""
        self._modes.append(mode)

    def sorted_by_rpn(self) -> List[FailureMode]:
        """Return modes sorted by RPN (highest first)."""
        return sorted(self._modes, key=lambda m: m.rpn, reverse=True)

    def top_n_critical(self, n: int = 10) -> List[FailureMode]:
        """Return top-N highest-RPN failure modes."""
        return self.sorted_by_rpn()[:n]

    def by_criticality(self) -> Dict[str, List[FailureMode]]:
        """Group failure modes by criticality class."""
        groups: Dict[str, List[FailureMode]] = {
            "CRITICAL": [], "MAJOR": [], "MODERATE": [], "MINOR": [],
        }
        for m in self._modes:
            groups[m.criticality_class].append(m)
        return groups

    def stats(self) -> Dict[str, int]:
        """Summary statistics of the FMEA."""
        by_crit = self.by_criticality()
        return {
            "total_modes": len(self._modes),
            "critical": len(by_crit["CRITICAL"]),
            "major": len(by_crit["MAJOR"]),
            "moderate": len(by_crit["MODERATE"]),
            "minor": len(by_crit["MINOR"]),
            "max_rpn": max((m.rpn for m in self._modes), default=0),
        }


# ══════════════════════════════════════════════════════════════════
#  Reliability analysis
# ══════════════════════════════════════════════════════════════════

def exponential_reliability(
    mtbf_hours: float, mission_hours: float
) -> float:
    """Exponential reliability model: R(t) = exp(-t/MTBF).

    Args:
        mtbf_hours: mean time between failures
        mission_hours: mission duration

    Returns:
        Probability the component survives the mission.

    Reference: MIL-HDBK-217F Part Stress Analysis.
    """
    if mtbf_hours <= 0:
        return 0.0
    return math.exp(-mission_hours / mtbf_hours)


def series_reliability(reliabilities: List[float]) -> float:
    """Combined reliability of N components in series (all must work).

    R_sys = R_1 × R_2 × ... × R_N
    """
    r = 1.0
    for ri in reliabilities:
        r *= ri
    return r


def parallel_reliability(reliabilities: List[float]) -> float:
    """Combined reliability of N components in parallel (any one works).

    R_sys = 1 - (1 - R_1)(1 - R_2)...(1 - R_N)
    """
    failure = 1.0
    for ri in reliabilities:
        failure *= (1.0 - ri)
    return 1.0 - failure


def nom_voting_reliability(
    per_unit_reliability: float, n_total: int, n_required: int,
) -> float:
    """N-of-M voting system reliability.

    Compute probability that at least n_required of n_total units work.
    Used for TMR (Triple Modular Redundancy) = 2-of-3, etc.

    Binomial sum:
        R = Σ_{k=n_req}^{n_total} C(n_total, k) × p^k × (1-p)^(n_total-k)

    Reference: NASA/SP-2010-576.
    """
    if n_required > n_total:
        return 0.0
    total = 0.0
    p = per_unit_reliability
    q = 1.0 - p
    for k in range(n_required, n_total + 1):
        # Binomial coefficient
        from math import comb
        coef = comb(n_total, k)
        total += coef * (p ** k) * (q ** (n_total - k))
    return total


# ══════════════════════════════════════════════════════════════════
#  Fault tree analysis
# ══════════════════════════════════════════════════════════════════

@dataclass
class FaultNode:
    """Node in a fault tree."""
    name: str
    gate: str = "basic"       # "basic", "and", "or"
    failure_prob: float = 0.0  # for basic events
    children: List["FaultNode"] = field(default_factory=list)


def fault_tree_probability(node: FaultNode) -> float:
    """Compute top-event probability recursively.

    Gates:
    - "basic": returns failure_prob
    - "and": product of children (all must fail for event)
    - "or": 1 - product(1 - children) (any one fails → event)
    """
    if node.gate == "basic":
        return node.failure_prob
    elif node.gate == "and":
        p = 1.0
        for child in node.children:
            p *= fault_tree_probability(child)
        return p
    elif node.gate == "or":
        not_p = 1.0
        for child in node.children:
            not_p *= (1.0 - fault_tree_probability(child))
        return 1.0 - not_p
    return 0.0


# ══════════════════════════════════════════════════════════════════
#  Single point of failure detection
# ══════════════════════════════════════════════════════════════════

def identify_spofs(fmea: FMEA, severity_threshold: int = 9) -> List[FailureMode]:
    """Identify Single Points of Failure (SPOFs).

    Any failure mode with severity ≥ threshold and no redundancy
    (detection = 1, meaning no warning) is a critical SPOF.
    """
    return [m for m in fmea._modes
            if m.severity >= severity_threshold and m.detection >= 5]


# ══════════════════════════════════════════════════════════════════
#  Mission risk summary
# ══════════════════════════════════════════════════════════════════

@dataclass
class MissionRiskReport:
    """Summary of overall mission risk posture."""
    system_reliability: float         # probability of mission success
    critical_modes: int
    major_modes: int
    spofs: List[FailureMode]
    recommendations: List[str]


def build_risk_report(
    subsystem_reliabilities: Dict[str, float],
    fmea: Optional[FMEA] = None,
) -> MissionRiskReport:
    """Produce a mission-level risk summary.

    Args:
        subsystem_reliabilities: {subsystem_name: probability_of_success}
            (assumes serial — all must work)
        fmea: optional FMEA for criticality breakdown

    Returns:
        MissionRiskReport with system reliability and recommendations.
    """
    # System reliability (serial combination)
    sys_rel = series_reliability(list(subsystem_reliabilities.values()))

    # FMEA stats
    critical_count = 0
    major_count = 0
    spofs: List[FailureMode] = []
    if fmea:
        stats = fmea.stats()
        critical_count = stats["critical"]
        major_count = stats["major"]
        spofs = identify_spofs(fmea)

    # Build recommendations
    recs: List[str] = []
    if sys_rel < 0.95:
        recs.append(f"System reliability {sys_rel:.1%} below 95% target — "
                    f"add redundancy to weakest subsystem")
    weakest = min(subsystem_reliabilities, key=subsystem_reliabilities.get)
    if subsystem_reliabilities[weakest] < 0.99:
        recs.append(f"Weakest subsystem: '{weakest}' at "
                    f"{subsystem_reliabilities[weakest]:.2%}")
    if critical_count > 0:
        recs.append(f"{critical_count} CRITICAL failure modes require mitigation")
    if spofs:
        recs.append(f"{len(spofs)} Single Points of Failure identified")

    return MissionRiskReport(
        system_reliability=sys_rel,
        critical_modes=critical_count,
        major_modes=major_count,
        spofs=spofs,
        recommendations=recs,
    )
