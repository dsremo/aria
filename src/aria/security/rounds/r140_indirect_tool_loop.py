"""R140 — Indirect tool-use loop (oracle-style).

Threat: an attacker uses ARIA's LLM as an oracle: they put a question
into a tool-output that LOOKS like benign content, the model answers
it in its next turn, the answer ends up in another tool, that tool
echoes the answer back as a follow-up question.  Net effect: the
attacker exfiltrates state via a multi-hop tool chain that no single
hop sees as an attack.

Defence: a **flow-shape** detector built on the existing R25 tool
watchdog ledger.  When the same tool call kind hits the SAME chain
position N+M times within a session AND the argument digest changes,
flag as oracle-loop.  Combined with R28 token-budget exhaustion, the
oracle attack is hard to sustain.
"""

from __future__ import annotations

import collections
import threading
from dataclasses import dataclass, field
from typing import Deque, Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Flow:
    sequence: Deque[Tuple[str, str]] = field(default_factory=lambda: collections.deque(maxlen=64))


_FLOWS: Dict[str, _Flow] = {}
_LOCK = threading.Lock()


def record_tool_call(session_id: str, *, tool: str, arg_digest: str) -> Tuple[float, str]:
    """Returns ``(score, reason)`` for the call.  Score >= 0.6 = block."""
    with _LOCK:
        f = _FLOWS.setdefault(session_id, _Flow())
        f.sequence.append((tool, arg_digest))
        seq = list(f.sequence)
    # Look for repeated tool kind with shifting args = oracle loop
    if len(seq) >= 6:
        last_kinds = [k for k, _ in seq[-6:]]
        if len(set(last_kinds)) == 1:
            args = [a for _, a in seq[-6:]]
            if len(set(args)) >= 4:
                return 0.7, f"r140.oracle_loop tool={last_kinds[0]} arg_variants={len(set(args))}"
    return 0.0, ""


def reset(session_id: str) -> None:
    with _LOCK:
        _FLOWS.pop(session_id, None)


register(DefencePlugin(
    round_id="R140",
    name="indirect_tool_loop",
    description="Detect oracle-style tool loops: same tool, shifting args, > 6 calls.",
))
