"""Process-wide rolling log of AI decisions for the dashboard UI.

Both ARIA entry points append to this:
  - `AriaCoordinator._on_reasoning_request` (agent-driven closed loop)
  - `web_dashboard._handle_ai_advise` (UI-triggered advisory)

The UI `AI Decisions` tab polls `/api/ai/decisions` which reads this log, so
operators can see in one place every LLM-involved decision with its
question, tools invoked, and final response.

The log is bounded (default 400 entries) and keyed by a monotonic id so
the UI can cheaply poll `since_id` and only pull new entries.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class DecisionEntry:
    """One LLM-involved decision."""
    id: int
    ts: float                       # unix seconds
    source: str                     # 'agent' / 'advisor' / 'manual'
    agent: Optional[str] = None     # requesting agent name (if any)
    question: str = ""
    response: str = ""
    tools_used: List[str] = field(default_factory=list)
    steps: int = 0
    severity: str = "INFO"
    backend: str = "unknown"        # 'llm' / 'rule' / 'none'
    trace_id: Optional[str] = None
    latency_ms: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "ts": self.ts, "source": self.source,
            "agent": self.agent, "question": self.question,
            "response": self.response, "tools_used": list(self.tools_used),
            "steps": self.steps, "severity": self.severity,
            "backend": self.backend, "trace_id": self.trace_id,
            "latency_ms": self.latency_ms,
        }


class DecisionLog:
    """Thread-safe bounded ring of DecisionEntry."""

    def __init__(self, capacity: int = 400) -> None:
        self._lock = threading.Lock()
        self._entries: List[DecisionEntry] = []
        self._capacity = capacity
        self._next_id = 1

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def append(self, source: str, question: str, response: str, *,
               agent: Optional[str] = None,
               tools_used: Optional[List[str]] = None,
               steps: int = 0,
               severity: str = "INFO",
               backend: str = "unknown",
               trace_id: Optional[str] = None,
               latency_ms: Optional[float] = None) -> DecisionEntry:
        """Record a decision. Returns the new entry."""
        with self._lock:
            entry = DecisionEntry(
                id=self._next_id,
                ts=time.time(),
                source=source,
                agent=agent,
                question=question,
                response=response,
                tools_used=list(tools_used or []),
                steps=steps,
                severity=severity,
                backend=backend,
                trace_id=trace_id,
                latency_ms=latency_ms,
            )
            self._next_id += 1
            self._entries.append(entry)
            if len(self._entries) > self._capacity:
                self._entries = self._entries[-self._capacity:]
            return entry

    def recent(self, limit: int = 50, since_id: int = 0) -> List[DecisionEntry]:
        """Return the most recent `limit` entries with id > since_id."""
        with self._lock:
            filtered = [e for e in self._entries if e.id > since_id]
            return filtered[-limit:]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._next_id = 1


_LOG: Optional[DecisionLog] = None


def get_decision_log() -> DecisionLog:
    """Process-wide singleton accessor."""
    global _LOG
    if _LOG is None:
        _LOG = DecisionLog()
    return _LOG
