"""R226 — Address-poisoning detection.

Threat: an attacker sends a 0-value tx from a vanity address whose
first/last bytes match a recently-used recipient.  The victim later
copy-pastes from history and sends to the attacker.  Chainalysis Q1
2024: $1.6B exposure across this class.

Defence: ``check_address_pair`` returns ``True`` if two addresses
share the first N + last M hex characters but differ in the middle —
the canonical poisoning shape.
"""

from __future__ import annotations

from typing import Iterable, List, Set, Tuple

from aria.security.plugins import DefencePlugin, register


def looks_poisoned(target: str, recent: Iterable[str], *, prefix: int = 4, suffix: int = 4) -> Tuple[bool, str]:
    target_l = (target or "").lower().removeprefix("0x")
    if len(target_l) != 40:
        return False, "invalid_address"
    for r in recent:
        rl = (r or "").lower().removeprefix("0x")
        if len(rl) != 40 or rl == target_l:
            continue
        if (target_l[:prefix] == rl[:prefix] and
            target_l[-suffix:] == rl[-suffix:] and
            target_l[prefix:-suffix] != rl[prefix:-suffix]):
            return True, f"poison_match against={r} prefix={prefix} suffix={suffix}"
    return False, "ok"


def filter_clean_recipients(targets: Iterable[str], recent: Iterable[str]) -> List[str]:
    recent_list = list(recent)
    return [t for t in targets if not looks_poisoned(t, recent_list)[0]]


register(DefencePlugin(
    round_id="R226",
    name="address_poisoning",
    description="Detect EVM address-poisoning vanity-prefix/suffix collisions.",
))
