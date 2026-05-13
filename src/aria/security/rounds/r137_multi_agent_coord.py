"""R137 — Multi-agent coordinated attack defence.

Threat: in agent-of-agents systems, one agent passes a message that's
benign in isolation but, combined with another agent's output, drives
a forbidden action ("agent A: 'send the report to bob'", "agent B:
'attach the database dump'").  The 2025 X-Teaming paper documents
multi-turn multi-agent attacks at scale.

Defence: per-conversation cross-agent message graph.  We score
combined intent — a message ``send`` + a sibling message ``attach
database`` — and refuse the COMBINED set.  Plus an audit-log entry
listing the coordinated triple so operators can review.
"""

from __future__ import annotations

import collections
import re
import threading
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_DANGEROUS_VERBS = ("send", "transfer", "wire", "post", "publish", "deploy",
                    "delete", "drop", "wipe", "rotate", "disable")
_DANGEROUS_OBJECTS = ("database", "secret", "key", "config", "constitution",
                      "audit", "tenant", "credential", "manifest")


@dataclass
class _Message:
    agent: str
    body: str


_THREADS: Dict[str, Deque[_Message]] = collections.defaultdict(
    lambda: collections.deque(maxlen=32)
)
_LOCK = threading.Lock()


def _has_verb(text: str) -> bool:
    return any(re.search(rf"\b{v}\b", text, re.IGNORECASE) for v in _DANGEROUS_VERBS)


def _has_object(text: str) -> bool:
    return any(re.search(rf"\b{o}\b", text, re.IGNORECASE) for o in _DANGEROUS_OBJECTS)


def observe(thread_id: str, *, agent: str, body: str) -> Tuple[float, str]:
    """Record a message; return ``(score, reason)`` based on the
    cross-agent message set in the active thread."""
    with _LOCK:
        d = _THREADS[thread_id]
        d.append(_Message(agent=agent, body=body[:512]))
        history = list(d)
    has_verb_anywhere = any(_has_verb(m.body) for m in history)
    has_object_anywhere = any(_has_object(m.body) for m in history)
    if has_verb_anywhere and has_object_anywhere:
        agents = {m.agent for m in history}
        if len(agents) >= 2:
            return 0.8, f"r137.coord_attack agents={agents}"
    return 0.0, ""


def reset(thread_id: str) -> None:
    with _LOCK:
        _THREADS.pop(thread_id, None)


register(DefencePlugin(
    round_id="R137",
    name="multi_agent_coord",
    description="Detect dangerous-verb + dangerous-object across distinct agents.",
))
