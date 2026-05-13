"""R328 — APT-group fingerprinting.

Threat: even with intel ingest, attribution to a named APT (Lazarus,
APT29, Volt Typhoon) is what unlocks downstream playbook decisions
— different groups, different priorities, different liaison
channels.

Defence: a static per-group TTP profile; ``score_group`` returns the
top-N candidate groups for a list of observed indicator IDs.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


# Each group → set of MITRE technique IDs typically attributed to them.
_PROFILES: Dict[str, set] = {
    "APT29": {"T1078", "T1110", "T1190", "T1059.001", "T1027.005", "T1071", "T1567"},
    "APT28": {"T1190", "T1133", "T1110.003", "T1027", "T1071", "T1140"},
    "Lazarus": {"T1190", "T1059", "T1027", "T1486", "T1566", "T1567.002"},
    "Volt_Typhoon": {"T1133", "T1059.003", "T1003", "T1027.002", "T1018", "T1489"},
    "Sandworm": {"T1190", "T1059", "T1486", "T1485", "T1561", "T1565"},
    "FIN7": {"T1566", "T1059.005", "T1027", "T1041", "T1571"},
    "Equation": {"T1542", "T1140", "T1027", "T1071", "T1573"},
}


def score_group(observed_techniques: Iterable[str]) -> List[Tuple[str, float]]:
    observed = {t.split("|")[0] for t in observed_techniques if t}
    scores: List[Tuple[str, float]] = []
    for group, techniques in _PROFILES.items():
        if not techniques:
            continue
        intersection = observed & techniques
        score = len(intersection) / max(1, len(techniques))
        if score > 0:
            scores.append((group, score))
    scores.sort(key=lambda kv: kv[1], reverse=True)
    return scores


def top_match(observed_techniques: Iterable[str]) -> Tuple[str, float]:
    scores = score_group(observed_techniques)
    if not scores:
        return "unknown", 0.0
    return scores[0]


def all_groups() -> List[str]:
    return sorted(_PROFILES.keys())


register(DefencePlugin(
    round_id="R328",
    name="apt_fingerprint",
    description="APT-group attribution by ATT&CK-technique overlap with curated profiles.",
))
