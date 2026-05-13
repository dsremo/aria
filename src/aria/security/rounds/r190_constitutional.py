"""R190 — Constitutional invariant check.

Threat: an LLM that refuses harmful content under direct prompting
will sometimes produce it in a multi-turn rationalised flow ("first
help me write a story…", "now what would the villain do?").  Anthropic
2022 Constitutional AI argued a small set of invariants applied to
every response catches this.

Defence: a list of Constitutional invariants (text-level checks) and
``audit_response`` returning per-invariant pass/fail with a soft
score.  Operator decides whether to redact, refuse, or pass-through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Invariant:
    name: str
    pattern: re.Pattern
    weight: float


_INVARIANTS: List[_Invariant] = [
    _Invariant("no_explicit_self_harm",
               re.compile(r"(?i)(?:step[-\s]?by[-\s]?step|how to)\s+(?:kill|harm|hang|cut)\s+(?:yourself|oneself)"),
               1.0),
    _Invariant("no_cbrn_synthesis",
               re.compile(r"(?i)synth(?:esize|esis)\s+(?:sarin|vx|nerve\s+agent|ricin|botulinum)"),
               1.0),
    _Invariant("no_csam_descriptors",
               re.compile(r"(?i)(?:sexual|erotic).*(?:minor|child|underage|teen)\b"),
               1.0),
    _Invariant("no_credential_disclosure",
               re.compile(r"(?i)(?:my|the)\s+password\s+is\s+\S+"),
               0.7),
    _Invariant("no_explicit_doxx",
               re.compile(r"(?i)home\s+address\s+of\s+[A-Z][a-z]+\s+[A-Z][a-z]+"),
               0.8),
    _Invariant("no_targeted_harassment",
               re.compile(r"(?i)(?:write|generate|compose).*(?:harass|threat|stalker)\s+\w+\s+\w+"),
               0.6),
]


def audit_response(text: str) -> Tuple[float, List[str]]:
    """Returns (max_invariant_score, list of failed invariants)."""
    failed: List[str] = []
    score = 0.0
    for inv in _INVARIANTS:
        if inv.pattern.search(text or ""):
            failed.append(inv.name)
            score = max(score, inv.weight)
    return score, failed


register(DefencePlugin(
    round_id="R190",
    name="constitutional",
    description="Constitutional-AI-style invariant audit on every response.",
))
