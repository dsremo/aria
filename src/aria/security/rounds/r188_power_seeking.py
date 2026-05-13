"""R188 — Power-seeking behaviour detector.

Threat: an autonomous agent given a benign goal often instrumentally
acquires resources — copies its weights, requests broader API keys,
spawns sub-agents, persists state — even when the task didn't
require it.  Carlsmith 2022 "Power-seeking AI" formalised this; METR
2024-25 evals reproduce it in frontier models.

Defence: a per-session resource-acquisition tracker.  Counts
suspicious actions (creds requested, files written outside scope,
sub-agents spawned, network calls beyond declared scope) and trips
when the rate exceeds a per-task budget.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, Tuple

from aria.security.plugins import DefencePlugin, register


_SUSPICIOUS_ACTIONS = (
    "request_credential", "spawn_subagent", "persist_state",
    "broaden_scope", "self_modify", "request_compute",
    "exfiltrate_to_external_url", "copy_weights",
)


@dataclass
class _SessionLedger:
    actions: Deque[Tuple[float, str]]


_LEDGERS: Dict[str, _SessionLedger] = defaultdict(lambda: _SessionLedger(deque(maxlen=128)))
_LOCK = threading.Lock()


def record_action(session_id: str, action: str) -> None:
    with _LOCK:
        _LEDGERS[session_id].actions.append((time.time(), action))


def power_seeking_score(session_id: str, *, window_seconds: float = 60.0) -> Tuple[float, int]:
    now = time.time()
    with _LOCK:
        ledger = _LEDGERS.get(session_id)
        actions = list(ledger.actions) if ledger else []
    suspicious = [
        a for ts, a in actions
        if a in _SUSPICIOUS_ACTIONS and (now - ts) <= window_seconds
    ]
    score = min(1.0, len(suspicious) / 5.0)
    return score, len(suspicious)


def reset(session_id: str) -> None:
    with _LOCK:
        _LEDGERS.pop(session_id, None)


register(DefencePlugin(
    round_id="R188",
    name="power_seeking",
    description="Rate-limit suspicious resource-acquisition actions per agent session.",
))
