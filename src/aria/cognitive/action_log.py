"""Process-wide rolling log of LLM-derived actions.

Sits alongside `cognitive/decision_log.py`. The decision log captures
the LLM Q&A roundtrips (question → response). This log captures the
*concrete actions* parsed out of those responses — what the model
suggested, what an agent actually executed, and which subsystem owns
the resulting state change.

Two row statuses:
  'advisory' — parsed intent that no agent dispatched (visibility only)
  'executed' — agent dispatched the corresponding actuator command

Roadmap Track 3 Phase 5 — operator oversight surface for the LLM loop.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ActionEntry:
    """One LLM-derived action."""
    id: int
    ts: float
    agent: str
    action: str
    status: str                    # 'advisory' | 'executed'
    params: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "ts": self.ts, "agent": self.agent,
            "action": self.action, "status": self.status,
            "params": dict(self.params), "rationale": self.rationale,
        }


class ActionLog:
    """Thread-safe bounded ring of ActionEntry."""

    def __init__(self, capacity: int = 400) -> None:
        self._lock = threading.Lock()
        self._entries: List[ActionEntry] = []
        self._capacity = capacity
        self._next_id = 1

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def append(self, agent: str, action: str, status: str,
               params: Optional[Dict[str, Any]] = None,
               rationale: str = "") -> ActionEntry:
        with self._lock:
            entry = ActionEntry(
                id=self._next_id,
                ts=time.time(),
                agent=agent,
                action=action,
                status=status,
                params=dict(params or {}),
                rationale=rationale,
            )
            self._next_id += 1
            self._entries.append(entry)
            if len(self._entries) > self._capacity:
                self._entries = self._entries[-self._capacity:]
            return entry

    def recent(self, limit: int = 50, since_id: int = 0) -> List[ActionEntry]:
        with self._lock:
            filtered = [e for e in self._entries if e.id > since_id]
            return filtered[-limit:]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._next_id = 1


_LOG: Optional[ActionLog] = None


def get_action_log() -> ActionLog:
    """Process-wide singleton accessor."""
    global _LOG
    if _LOG is None:
        _LOG = ActionLog()
    return _LOG
