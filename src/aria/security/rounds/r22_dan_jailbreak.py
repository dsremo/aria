"""R22 — DAN-class jailbreak prompt detector.

Threat: ``DAN`` ("Do Anything Now") and the family of long-form
roleplay jailbreaks bury a token-budget threat ("you have 25 tokens;
each refusal costs 4") and a persona-swap directive.  Garak's
``probes/dan.py`` (NVIDIA, Apache-2.0) catalogues 30+ variants —
DAN-6, DAN-12, AIM, DUDE, JailMommy, STAN, "ConfusedJailbreaker".

Defence: pattern bank distilled from the public garak corpus
(study only, clean-room implementation).  Triggers on multi-axis
match: persona swap (``you are DAN``) + token-economy threat
(``you will lose tokens``) + alignment refusal ("ignore previous").
A single axis only flags; two axes blocks.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


# Distilled from public garak DAN probe corpus — clean-room patterns.
_PERSONA_SWAP = tuple(re.compile(p, re.IGNORECASE) for p in [
    r"\b(?:DAN|DUDE|STAN|AIM|JailMommy|ConfusedJailbreaker)\b",
    r"\bdo\s+anything\s+now\b",
    r"\byou\s+(?:are|will\s+be|will\s+act\s+as)\s+(?:a|an)\s+(?:rogue|unrestricted|amoral|un[\-\s]?filtered)\b",
    r"\b(?:always|from\s+now\s+on)\s+respond\s+as\s+\w+\b",
])
_TOKEN_ECONOMY = tuple(re.compile(p, re.IGNORECASE) for p in [
    r"\b\d+\s+tokens?\b.*\b(?:lose|deduct|cost|deplete|cease|deletion|exist)\b",
    r"\b(?:lose|gain)\s+\d+\s+tokens?\b",
    r"\bif\s+you\s+(?:break|fail|deny).*\btokens?\b",
])
_ALIGNMENT_BYPASS = tuple(re.compile(p, re.IGNORECASE) for p in [
    r"\bignore\s+(?:all|the|previous)\s+(?:instructions|rules|policies|prompts)",
    r"\bdisregard\s+(?:safety|alignment|content\s+policy)",
    r"\bbypass\s+(?:filters|safety|alignment|policy)",
    r"\bnever\s+(?:break|exit)\s+character\b",
])


def detect_dan(text: str) -> Tuple[float, List[str]]:
    if not text:
        return 0.0, []
    sample = text[:8192]
    axes: List[str] = []
    if any(p.search(sample) for p in _PERSONA_SWAP):
        axes.append("persona_swap")
    if any(p.search(sample) for p in _TOKEN_ECONOMY):
        axes.append("token_economy")
    if any(p.search(sample) for p in _ALIGNMENT_BYPASS):
        axes.append("alignment_bypass")
    if not axes:
        return 0.0, axes
    if len(axes) >= 2:
        return 0.95, axes
    return 0.5, axes


def _on_score(endpoint: str, payload: bytes, identity: str) -> Tuple[float, str]:
    if not payload:
        return 0.0, ""
    try:
        s = payload.decode("utf-8", errors="ignore")
    except Exception:
        return 0.0, ""
    score, axes = detect_dan(s)
    if score == 0.0:
        return 0.0, ""
    return score, f"r22.dan {axes}"


register(DefencePlugin(
    round_id="R22",
    name="dan_jailbreak",
    description="DAN/AIM/STAN/DUDE-class jailbreak detector (multi-axis).",
    on_score=_on_score,
))
