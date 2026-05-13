"""R349 — CVSS v3.1 base-score helper.

Threat: vulnerability triage without a numeric severity drifts on
analyst gut.  CVSS v3.1 is the de-facto standard; any production
ARIA tracker that emits findings should attach a base score and the
canonical vector string.

Defence: a small calculator over the CVSS v3.1 base metrics.  Returns
both the base score (0.0–10.0) and the canonical vector for ticketing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class CVSSv31Base:
    av: str = "N"   # Attack Vector: N|A|L|P
    ac: str = "L"   # Attack Complexity: L|H
    pr: str = "N"   # Privileges Required: N|L|H
    ui: str = "N"   # User Interaction: N|R
    s: str = "U"    # Scope: U|C
    c: str = "N"    # Confidentiality Impact: N|L|H
    i: str = "N"    # Integrity Impact: N|L|H
    a: str = "N"    # Availability Impact: N|L|H


_AV = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}
_AC = {"L": 0.77, "H": 0.44}
_UI = {"N": 0.85, "R": 0.62}
_PR_NORMAL = {"N": 0.85, "L": 0.62, "H": 0.27}
_PR_CHANGED = {"N": 0.85, "L": 0.68, "H": 0.5}
_CIA = {"N": 0.0, "L": 0.22, "H": 0.56}


def base_score(b: CVSSv31Base) -> Tuple[float, str]:
    av = _AV.get(b.av.upper(), 0.85)
    ac = _AC.get(b.ac.upper(), 0.77)
    ui = _UI.get(b.ui.upper(), 0.85)
    pr_table = _PR_CHANGED if b.s.upper() == "C" else _PR_NORMAL
    pr = pr_table.get(b.pr.upper(), 0.85)
    c = _CIA.get(b.c.upper(), 0.0)
    i = _CIA.get(b.i.upper(), 0.0)
    a = _CIA.get(b.a.upper(), 0.0)

    iss_base = 1 - ((1 - c) * (1 - i) * (1 - a))
    if b.s.upper() == "U":
        impact = 6.42 * iss_base
    else:
        impact = 7.52 * (iss_base - 0.029) - 3.25 * ((iss_base - 0.02) ** 15)
    exploitability = 8.22 * av * ac * pr * ui
    if impact <= 0:
        score = 0.0
    elif b.s.upper() == "U":
        score = round_up_one(min(impact + exploitability, 10.0))
    else:
        score = round_up_one(min(1.08 * (impact + exploitability), 10.0))

    vector = (
        f"CVSS:3.1/AV:{b.av.upper()}/AC:{b.ac.upper()}/PR:{b.pr.upper()}/"
        f"UI:{b.ui.upper()}/S:{b.s.upper()}/C:{b.c.upper()}/I:{b.i.upper()}/A:{b.a.upper()}"
    )
    return score, vector


def round_up_one(x: float) -> float:
    """CVSS v3.1 spec rounding: round to one decimal up."""
    import math
    return math.ceil(x * 10) / 10.0


def severity_band(score: float) -> str:
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    if score > 0.0:
        return "low"
    return "none"


register(DefencePlugin(
    round_id="R349",
    name="cvss",
    description="CVSS v3.1 base-score calculator + canonical vector emitter.",
))
