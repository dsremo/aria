"""R233 — k-anonymity / l-diversity check.

Threat: a "de-identified" dataset with quasi-identifiers (age, zip,
sex) is often re-identifiable — Sweeney 2002 showed 87% of US
population is unique given (zip5, sex, DOB).  L-diversity catches
the homogeneity attack k-anon misses.

Defence: ``check_k_anonymity`` returns the minimum equivalence-class
size for the chosen quasi-identifier columns; ``check_l_diversity``
returns the minimum sensitive-value count per class.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


def check_k_anonymity(
    rows: Iterable[Dict[str, object]],
    *,
    quasi_identifiers: Iterable[str],
    k: int = 5,
) -> Tuple[bool, int, List[Dict[str, object]]]:
    qis = tuple(quasi_identifiers)
    classes: Dict[Tuple, List[Dict[str, object]]] = defaultdict(list)
    for row in rows:
        key = tuple(row.get(qi) for qi in qis)
        classes[key].append(row)
    if not classes:
        return True, 0, []
    min_class = min(len(c) for c in classes.values())
    weak: List[Dict[str, object]] = []
    if min_class < k:
        for c in classes.values():
            if len(c) < k:
                weak.extend(c)
    return min_class >= k, min_class, weak


def check_l_diversity(
    rows: Iterable[Dict[str, object]],
    *,
    quasi_identifiers: Iterable[str],
    sensitive_attribute: str,
    l: int = 3,
) -> Tuple[bool, int]:
    qis = tuple(quasi_identifiers)
    classes: Dict[Tuple, set] = defaultdict(set)
    for row in rows:
        key = tuple(row.get(qi) for qi in qis)
        classes[key].add(row.get(sensitive_attribute))
    if not classes:
        return True, 0
    min_diversity = min(len(s) for s in classes.values())
    return min_diversity >= l, min_diversity


register(DefencePlugin(
    round_id="R233",
    name="k_anonymity",
    description="k-anonymity + l-diversity audit for de-identified data releases.",
))
