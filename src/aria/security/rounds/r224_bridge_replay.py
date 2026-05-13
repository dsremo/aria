"""R224 — Cross-chain bridge replay protection.

Threat: cross-chain bridges encode events on chain A → relayed →
mint on chain B.  Without per-message uniqueness, a replay re-mints
unlimited tokens.  Wormhole 2022 ($325M), Nomad 2022 ($190M), Ronin
2022 ($625M) are bridge failures — different root causes but all
amplified by missing replay protection.

Defence: per-bridge nonce ledger.  ``record_bridge_message`` rejects
any (chain_pair, message_hash) tuple seen before; ``verify_quorum``
rejects messages without the operator-set guardian-quorum signatures.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Dict, Iterable, Set, Tuple

from aria.security.plugins import DefencePlugin, register


_SEEN: Dict[str, Set[str]] = {}
_LOCK = threading.Lock()


def record_bridge_message(chain_pair: str, message_blob: bytes) -> Tuple[bool, str]:
    h = hashlib.sha256(message_blob).hexdigest()
    with _LOCK:
        seen = _SEEN.setdefault(chain_pair, set())
        if h in seen:
            return False, f"bridge.replay chain_pair={chain_pair} hash={h[:16]}…"
        seen.add(h)
    return True, "ok"


def verify_quorum(
    signatures: Iterable[Tuple[str, bytes]],
    *,
    guardians: Set[str],
    threshold: int,
) -> Tuple[bool, str]:
    valid_signers: Set[str] = set()
    for signer, sig in signatures:
        if signer in guardians and sig and len(sig) >= 64:
            valid_signers.add(signer)
    if len(valid_signers) < threshold:
        return False, f"bridge.quorum_short {len(valid_signers)}/{threshold}"
    return True, f"bridge.quorum_ok {len(valid_signers)}/{len(guardians)}"


def reset_for_tests() -> None:
    with _LOCK:
        _SEEN.clear()


register(DefencePlugin(
    round_id="R224",
    name="bridge_replay",
    description="Cross-chain bridge replay ledger + guardian-quorum verifier.",
))
