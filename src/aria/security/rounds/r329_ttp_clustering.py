"""R329 — TTP (Tactic-Technique-Procedure) clustering.

Threat: a stream of detection events with no clustering produces
alert-fatigue — analysts triage individual hits without seeing the
shared adversary playbook.

Defence: cluster events by tactic + technique overlap.  Returns
groups whose Jaccard similarity over technique sets exceeds a
threshold; each cluster represents a probable single intrusion.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Set

from aria.security.plugins import DefencePlugin, register


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def cluster_events(
    events: Iterable[Dict[str, object]],
    *,
    similarity_threshold: float = 0.4,
) -> List[List[Dict[str, object]]]:
    events_list = list(events)
    n = len(events_list)
    visited = [False] * n
    clusters: List[List[Dict[str, object]]] = []

    def techniques_of(e: Dict[str, object]) -> Set[str]:
        return set(e.get("techniques") or [])

    for i in range(n):
        if visited[i]:
            continue
        cluster = [events_list[i]]
        seed = techniques_of(events_list[i])
        visited[i] = True
        for j in range(i + 1, n):
            if visited[j]:
                continue
            if jaccard(seed, techniques_of(events_list[j])) >= similarity_threshold:
                cluster.append(events_list[j])
                visited[j] = True
                seed = seed | techniques_of(events_list[j])
        clusters.append(cluster)
    return clusters


def render_cluster_summary(clusters: List[List[Dict[str, object]]]) -> str:
    lines = []
    for i, cluster in enumerate(clusters):
        techniques: Set[str] = set()
        for ev in cluster:
            techniques |= set(ev.get("techniques") or [])
        lines.append(f"cluster {i}: events={len(cluster)} techniques={','.join(sorted(techniques))}")
    return "\n".join(lines)


register(DefencePlugin(
    round_id="R329",
    name="ttp_clustering",
    description="Jaccard-similarity clustering of detection events by ATT&CK technique set.",
))
