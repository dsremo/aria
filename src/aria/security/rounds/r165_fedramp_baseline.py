"""R165 — FedRAMP Moderate baseline coverage check.

Threat: a CSP marketing as "FedRAMP-ready" without coverage of the
325 Moderate baseline controls fails ATO at JAB / 3PAO review.
Coverage drift between audits is the #1 failure mode.

Defence: list the Moderate baseline control families (control counts
per family), cross-reference them against R162's NIST 800-53 mapping,
and report gap families.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


# FedRAMP Moderate baseline (Rev 5) family counts — public template
# https://www.fedramp.gov/assets/resources/templates/SSP-Moderate-Template.docx
_MODERATE_FAMILY_COUNTS: Dict[str, int] = {
    "AC": 25, "AT": 5, "AU": 16, "CA": 9, "CM": 12, "CP": 13, "IA": 12,
    "IR": 10, "MA": 6, "MP": 8, "PE": 20, "PL": 8, "PS": 9, "RA": 7,
    "SA": 22, "SC": 32, "SI": 22, "SR": 12,
}


def coverage_vs_r162() -> Tuple[int, int, List[str]]:
    from aria.security.rounds.r162_nist_800_53 import _MAPPING
    covered_families: Dict[str, int] = {}
    for ctl in _MAPPING:
        fam = ctl.split("-")[0]
        covered_families[fam] = covered_families.get(fam, 0) + 1
    total_required = sum(_MODERATE_FAMILY_COUNTS.values())
    total_covered = sum(covered_families.get(f, 0) for f in _MODERATE_FAMILY_COUNTS)
    gaps = [
        f for f in _MODERATE_FAMILY_COUNTS
        if covered_families.get(f, 0) == 0
    ]
    return total_covered, total_required, gaps


def render_gap_report() -> str:
    covered, required, gaps = coverage_vs_r162()
    lines = [
        f"# FedRAMP Moderate gap (controls covered: {covered}/{required})",
        "",
        f"Family-level gaps (no ARIA round mapped): {', '.join(gaps) if gaps else 'none'}",
    ]
    return "\n".join(lines)


register(DefencePlugin(
    round_id="R165",
    name="fedramp_baseline",
    description="FedRAMP Moderate baseline coverage report against R162 mapping.",
))
