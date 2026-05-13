"""R327 — TLP (Traffic Light Protocol) tagging.

Threat: shared threat-intel without TLP tags gets disclosed too
broadly — RED items end up in public Slack, AMBER ends up on
Twitter.  FIRST.org TLP 2.0 is the standard.

Defence: a ``TLPLevel`` enum + ``can_share`` policy gate.  Sharing
to a recipient classification *broader* than the item's TLP raises;
emitter helpers ensure every outbound communication carries the tag.
"""

from __future__ import annotations

from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_TLP_LEVELS = ("CLEAR", "GREEN", "AMBER+STRICT", "AMBER", "RED")
# Higher rank = more restrictive (CLEAR=0 broadest, RED=4 most restrictive).
_RANK = {level: i for i, level in enumerate(_TLP_LEVELS)}


def is_valid(tlp: str) -> bool:
    return tlp.upper() in _TLP_LEVELS


def can_share(item_tlp: str, recipient_scope: str) -> Tuple[bool, str]:
    """``item_tlp`` is the originator's TLP; ``recipient_scope`` is the
    minimum-restriction scope (CLEAR is the broadest)."""
    if not is_valid(item_tlp):
        return False, f"tlp.invalid_item:{item_tlp}"
    if not is_valid(recipient_scope):
        return False, f"tlp.invalid_scope:{recipient_scope}"
    item_rank = _RANK[item_tlp.upper()]
    scope_rank = _RANK[recipient_scope.upper()]
    if scope_rank < item_rank:
        return False, f"tlp.over_share item={item_tlp} scope={recipient_scope}"
    return True, "ok"


def tag_outgoing(message: str, tlp: str) -> str:
    if not is_valid(tlp):
        raise ValueError(f"R327: invalid TLP {tlp}")
    return f"TLP:{tlp.upper()}\n\n{message}"


register(DefencePlugin(
    round_id="R327",
    name="tlp_tagging",
    description="Traffic Light Protocol 2.0 enforcement: refuse over-sharing.",
))
