"""R164 — ISO/IEC 27001:2022 Annex A control checklist.

Threat: ISO 27001 certification requires a Statement of Applicability
covering 93 Annex A controls.  Building this from scratch every audit
cycle wastes weeks; rounds get re-implemented under different names.

Defence: static map of ISO 27001:2022 Annex A control IDs → ARIA
rounds, with ``check_soa`` returning the applicability status string
auditors expect ("Implemented", "Not Applicable", "Planned").
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_ANNEX_A: Dict[str, Tuple[str, List[str]]] = {
    "A.5.1":  ("information security policies", ["R162"]),
    "A.5.7":  ("threat intelligence", ["R93", "R90"]),
    "A.5.15": ("access control", ["R39", "R161"]),
    "A.5.17": ("authentication information", ["R65", "R64", "R63"]),
    "A.5.23": ("information security for cloud services", ["R122", "R123", "R124", "R125"]),
    "A.5.30": ("ICT readiness for business continuity", ["R99"]),
    "A.5.31": ("legal, statutory, regulatory requirements", ["R166"]),
    "A.5.33": ("protection of records", ["R98"]),
    "A.6.7":  ("remote working", ["R153", "R160"]),
    "A.7.4":  ("physical security monitoring", ["R102", "R104"]),
    "A.8.2":  ("privileged access rights", ["R124", "R161"]),
    "A.8.3":  ("information access restriction", ["R97", "R161"]),
    "A.8.5":  ("secure authentication", ["R64", "R63"]),
    "A.8.7":  ("protection against malware", ["R80", "R194"]),
    "A.8.8":  ("management of technical vulnerabilities", ["R93", "R94"]),
    "A.8.9":  ("configuration management", ["R115", "R169"]),
    "A.8.12": ("data leakage prevention", ["R97", "R167"]),
    "A.8.13": ("information backup", ["R98"]),
    "A.8.15": ("logging", ["R34", "R98", "R150"]),
    "A.8.16": ("monitoring activities", ["R23", "R26"]),
    "A.8.20": ("network security", ["R113", "R157"]),
    "A.8.21": ("security of network services", ["R116", "R156"]),
    "A.8.23": ("web filtering", ["R88", "R91"]),
    "A.8.24": ("use of cryptography", ["R47", "R67", "R108"]),
    "A.8.26": ("application security requirements", ["R6", "R72", "R74"]),
    "A.8.28": ("secure coding", ["R75", "R76"]),
    "A.8.29": ("security testing in development and acceptance", ["R94", "R51", "R101", "R151"]),
    "A.8.32": ("change management", ["R114", "R121"]),
}


def check_soa(control_id: str) -> Tuple[str, List[str]]:
    """Returns ('Implemented' | 'Not Applicable', round_list)."""
    entry = _ANNEX_A.get(control_id)
    if entry is None:
        return "Not Applicable", []
    _, rounds = entry
    return ("Implemented" if rounds else "Planned"), list(rounds)


def render_soa_table() -> str:
    lines = ["| ISO 27001:2022 | Description | ARIA Rounds | Status |", "|---|---|---|---|"]
    for ctl in sorted(_ANNEX_A):
        desc, rounds = _ANNEX_A[ctl]
        status = "Implemented" if rounds else "Planned"
        lines.append(f"| {ctl} | {desc} | {', '.join(rounds)} | {status} |")
    return "\n".join(lines)


register(DefencePlugin(
    round_id="R164",
    name="iso_27001",
    description="ISO/IEC 27001:2022 Annex A control → ARIA round Statement of Applicability.",
))
