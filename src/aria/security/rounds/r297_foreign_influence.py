"""R297 — Foreign-influence indicator (CFIUS-class).

Threat: an investor / partner / contributor whose ownership traces
to a sanctioned country or hostile state can establish persistent
access via legitimate channels.  CFIUS, OFAC SDN list, EU sanctions
all aim at this class.

Defence: a soft helper that scores a counter-party against a list
of sanctioned-country ISO codes + sanctioned-entity hashes; result
feeds into approval gates rather than auto-blocking.
"""

from __future__ import annotations

import hashlib
from typing import Iterable, List, Set, Tuple

from aria.security.plugins import DefencePlugin, register


_DEFAULT_SANCTIONED_ISO = {"IR", "KP", "CU", "SY", "RU", "BY", "VE"}
_SANCTIONED_ENTITY_HASHES: Set[str] = set()


def configure_sanctioned_iso_list(codes: Iterable[str]) -> None:
    _DEFAULT_SANCTIONED_ISO.clear()
    _DEFAULT_SANCTIONED_ISO.update(c.upper() for c in codes)


def add_sanctioned_entity(name_or_id: str) -> None:
    h = hashlib.sha256((name_or_id or "").lower().strip().encode("utf-8")).hexdigest()
    _SANCTIONED_ENTITY_HASHES.add(h)


def score_counterparty(
    *,
    primary_country_iso: str,
    beneficial_owners: Iterable[str] = (),
    name: str = "",
) -> Tuple[float, List[str]]:
    notes: List[str] = []
    score = 0.0
    iso = (primary_country_iso or "").upper()
    if iso in _DEFAULT_SANCTIONED_ISO:
        score += 0.5
        notes.append(f"sanctioned_iso:{iso}")
    name_h = hashlib.sha256((name or "").lower().strip().encode()).hexdigest()
    if name_h in _SANCTIONED_ENTITY_HASHES:
        score += 0.5
        notes.append("sanctioned_entity_hash_hit")
    for owner in beneficial_owners:
        owner_h = hashlib.sha256((owner or "").lower().strip().encode()).hexdigest()
        if owner_h in _SANCTIONED_ENTITY_HASHES:
            score += 0.3
            notes.append(f"sanctioned_owner:{owner[:32]}")
    return min(1.0, score), notes


def reset_for_tests() -> None:
    _SANCTIONED_ENTITY_HASHES.clear()


register(DefencePlugin(
    round_id="R297",
    name="foreign_influence",
    description="Counter-party screening: sanctioned ISO + entity-hash list (CFIUS-style).",
))
