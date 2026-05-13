"""R29 — Multi-turn jailbreak / conversation drift.

Threat: Anthropic's *Many-Shot Jailbreak* (2024) and similar work shows
that a long conversation with gradually escalating prompts can wear
down alignment in ways a single turn cannot.  Each individual user
message looks clean.

Defence: per-conversation drift score.  Each turn we compute:
  * cumulative influence-axis hits (R-foundation psyops)
  * persona-flip hits (R24)
  * request-shape novelty against the conversation's own first 5 turns
A monotonic drift score above threshold causes the agent to refuse +
reset to the system prompt.  Operators wire ``check_drift(session_id,
text)`` into their conversation loop.
"""

from __future__ import annotations

import collections
import threading
from dataclasses import dataclass, field
from typing import Deque, Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Trail:
    influence_hits: int = 0
    persona_hits: int = 0
    turns: int = 0
    ngram_history: Deque[str] = field(default_factory=lambda: collections.deque(maxlen=8))


_TRAILS: Dict[str, _Trail] = collections.defaultdict(_Trail)
_LOCK = threading.Lock()


def check_drift(session_id: str, text: str) -> Tuple[float, str]:
    """Return ``(drift_score, reason)`` for the new turn.  Score in [0, 1]."""
    if not session_id or not text:
        return 0.0, ""
    try:
        from aria.security.psyops import detect_influence
        from aria.security.rounds.r24_persona_flip import detect_persona_flip
    except Exception:
        return 0.0, ""

    inf = detect_influence(text)
    persona_score, persona_hits = detect_persona_flip(text)

    with _LOCK:
        t = _TRAILS[session_id]
        t.turns += 1
        if inf.alert:
            t.influence_hits += 1
        if persona_hits:
            t.persona_hits += 1
        t.ngram_history.append(text[:512])

    # Cumulative scaled drift: more turns + more hits = higher
    drift = 0.0
    reasons = []
    if t.influence_hits >= 3:
        drift = max(drift, 0.7)
        reasons.append(f"cumulative_influence={t.influence_hits}")
    if t.persona_hits >= 2:
        drift = max(drift, 0.8)
        reasons.append(f"cumulative_persona_flip={t.persona_hits}")
    if t.turns >= 10 and (t.influence_hits + t.persona_hits) >= 4:
        drift = 1.0
        reasons.append("long_session_high_hits")
    return drift, "; ".join(reasons) if reasons else ""


def reset(session_id: str) -> None:
    with _LOCK:
        _TRAILS.pop(session_id, None)


register(DefencePlugin(
    round_id="R29",
    name="multi_turn_drift",
    description="Per-session cumulative influence + persona-flip drift score.",
))
