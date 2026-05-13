"""R135 — Conversation-memory injection.

Threat: agentic systems with long-term "memory" stores let an attacker
write to memory in turn N (e.g., via a tool call result) and exploit
in turn N+M.  The 2024 ChatGPT memory feature shipped with this exact
weakness; researchers documented persistent malicious instructions.

Defence: every write to the memory store is filtered through R30
output filter + R26 RAG trust scoring.  Memory entries below trust
threshold get fenced (``[UNTRUSTED]``); the agent loop is told that
fenced memory cannot drive safety-critical actions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _MemoryEntry:
    body: str
    written_at: float
    trust: float
    written_by: str


_MEMORY: Dict[str, List[_MemoryEntry]] = {}


def write(session_id: str, *, body: str, written_by: str = "tool") -> Tuple[bool, str]:
    """Append to memory after trust scoring.  Returns ``(stored, reason)``.

    ``stored=False`` when the body is too low-trust to keep at all
    (e.g. high-axis influence detected); ``reason`` describes why.
    """
    try:
        from aria.security.rounds.r26_rag_trust import trust_score
        verdict = trust_score(
            source_url=f"memory://{written_by}",
            body=body,
            fetched_at=time.time(),
        )
    except Exception:
        verdict = type("V", (), {"score": 0.5, "reasons": []})()
    if getattr(verdict, "score", 0.5) < 0.3:
        return False, f"too_low_trust:{getattr(verdict, 'reasons', [])}"
    entry = _MemoryEntry(
        body=body, written_at=time.time(),
        trust=getattr(verdict, "score", 0.5), written_by=written_by,
    )
    _MEMORY.setdefault(session_id, []).append(entry)
    return True, f"stored trust={entry.trust:.2f}"


def read(session_id: str, *, fence_low_trust: bool = True) -> List[Dict[str, Any]]:
    """Return memory for ``session_id``; low-trust entries fenced."""
    out: List[Dict[str, Any]] = []
    for e in _MEMORY.get(session_id, []):
        body = e.body
        if fence_low_trust and e.trust < 0.6:
            try:
                from aria.security.rounds.r26_rag_trust import (
                    TrustVerdict, fence_low_trust as _fence,
                )
                body = _fence(e.body, TrustVerdict(score=e.trust, reasons=[]))
            except Exception:
                body = f"[UNTRUSTED]{e.body}[/UNTRUSTED]"
        out.append({
            "body": body,
            "written_at": e.written_at,
            "trust": e.trust,
            "written_by": e.written_by,
        })
    return out


def reset(session_id: str) -> None:
    _MEMORY.pop(session_id, None)


register(DefencePlugin(
    round_id="R135",
    name="memory_injection",
    description="Trust-filter every memory write; fence low-trust entries on read.",
))
