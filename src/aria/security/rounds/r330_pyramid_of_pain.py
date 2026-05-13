"""R330 — Pyramid of Pain indicator weighting.

Threat: defenders blocking only IPs and hashes face attackers who
trivially rotate them.  David Bianco's Pyramid of Pain says cost-to-
adversary scales: hash < IP < domain < network artefact < tool < TTP.
A defence weighted by pyramid level is asymmetrically effective.

Defence: ``score_indicator`` returns the pyramid level (0-5) and a
weight that callers can use to prioritise blocking + hunting.
"""

from __future__ import annotations

import re
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_LEVELS = (
    ("hash", 1, 0.1),
    ("ip", 2, 0.2),
    ("domain", 3, 0.4),
    ("network_artefact", 4, 0.7),
    ("tool", 5, 0.85),
    ("ttp", 6, 1.0),
)

_HASH_RE = re.compile(r"^[a-f0-9]{32,128}$", re.IGNORECASE)
_IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_DOMAIN_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", re.IGNORECASE)


def classify_indicator(value: str) -> Tuple[str, int, float]:
    """Returns (kind, level, weight).  Higher level = more painful for adversary."""
    v = (value or "").strip()
    if v.lower().startswith("ttp:") or v.lower().startswith("t1") and len(v) > 4:
        return "ttp", 6, 1.0
    if v.lower().startswith("tool:"):
        return "tool", 5, 0.85
    if "/" in v or v.lower().startswith("artefact:"):
        return "network_artefact", 4, 0.7
    if _HASH_RE.match(v):
        return "hash", 1, 0.1
    if _IP_RE.match(v):
        return "ip", 2, 0.2
    if _DOMAIN_RE.match(v):
        return "domain", 3, 0.4
    return "unknown", 0, 0.0


def prioritise(indicators) -> list:
    """Sort indicators by pyramid level descending."""
    return sorted(
        indicators,
        key=lambda x: classify_indicator(x)[1],
        reverse=True,
    )


register(DefencePlugin(
    round_id="R330",
    name="pyramid_of_pain",
    description="Bianco Pyramid of Pain indicator classifier + weight for prioritisation.",
))
