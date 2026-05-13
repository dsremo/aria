"""R220 — Process-historian log tamper detection.

Threat: an attacker who silently rewrites the historian (PI, Wonder-
ware, Ignition) database hides the operational evidence of an
attack.  The TRITON attackers reportedly did this; Norsk Hydro 2019
investigators reconstructed the attack only because operators kept
paper logs.

Defence: per-row Merkle hash binding the row to its predecessor.
``verify_historian_chain`` walks the tail and detects tampering.
Pairs with R98 (immutable hash-chained logs).
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from typing import Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class HistorianRow:
    timestamp_ns: int
    tag: str
    value: float
    quality: int
    prev_hash: str
    row_hash: str = ""

    def serialise(self) -> bytes:
        return f"{self.timestamp_ns}|{self.tag}|{self.value:.10f}|{self.quality}|{self.prev_hash}".encode()


_PREV: List[str] = ["0" * 64]
_LOCK = threading.Lock()


def append_row(timestamp_ns: int, tag: str, value: float, quality: int = 192) -> HistorianRow:
    with _LOCK:
        prev = _PREV[-1]
        row = HistorianRow(timestamp_ns, tag, value, quality, prev)
        row.row_hash = hashlib.sha256(row.serialise()).hexdigest()
        _PREV.append(row.row_hash)
    return row


def verify_chain(rows: Iterable[HistorianRow]) -> Tuple[bool, int]:
    prev = "0" * 64
    for i, row in enumerate(rows):
        recomputed = hashlib.sha256(row.serialise()).hexdigest()
        if recomputed != row.row_hash or row.prev_hash != prev:
            return False, i
        prev = row.row_hash
    return True, -1


def reset_for_tests() -> None:
    with _LOCK:
        _PREV.clear()
        _PREV.append("0" * 64)


register(DefencePlugin(
    round_id="R220",
    name="historian_tamper",
    description="Process-historian Merkle hash chain; one-pass tamper detection.",
))
