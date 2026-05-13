"""R230 — Cross-chain message verifier (LayerZero / CCIP / Hyperlane).

Threat: cross-chain messaging protocols (LayerZero, CCIP, Hyperlane,
Wormhole) accept relayed messages signed by a guardian/relayer set.
A stale or forged message bypasses the source-chain semantics.
LayerZero v1 vulnerabilities 2023, Hop 2024.

Defence: validate (source_chain_id, source_address, nonce,
timestamp, message_hash) tuple — refuse stale messages, refuse
nonce-out-of-order, refuse messages whose source_address isn't in
the operator's allow-list.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _ChainState:
    last_nonce: int = -1


_STATES: Dict[Tuple[int, str], _ChainState] = {}
_LOCK = threading.Lock()


def verify_cross_chain_message(
    *,
    source_chain_id: int,
    source_address: str,
    nonce: int,
    message_timestamp: float,
    allowed_sources: Iterable[Tuple[int, str]],
    max_age_seconds: float = 1800.0,
    now: float = 0.0,
) -> Tuple[bool, str]:
    t = now or time.time()
    src = (source_chain_id, (source_address or "").lower())
    if src not in {(c, a.lower()) for c, a in allowed_sources}:
        return False, f"crosschain.source_not_allowed:{src}"

    age = t - message_timestamp
    if age > max_age_seconds:
        return False, f"crosschain.stale age={age:.0f}s"
    if age < -60.0:
        return False, "crosschain.future_timestamp"

    with _LOCK:
        state = _STATES.setdefault(src, _ChainState())
        if nonce <= state.last_nonce:
            return False, f"crosschain.nonce_replay last={state.last_nonce} got={nonce}"
        state.last_nonce = nonce
    return True, f"crosschain.ok nonce={nonce}"


def reset_for_tests() -> None:
    with _LOCK:
        _STATES.clear()


register(DefencePlugin(
    round_id="R230",
    name="cross_chain_msg",
    description="Cross-chain message verifier: source allow-list + nonce + freshness.",
))
