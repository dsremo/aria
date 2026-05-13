"""Memory Store — multi-tier memory for ARIA.

Four memory tiers, modelled on common cognitive-agent memory layers:

1. Working Memory: Current situation, last N minutes of events.
   Working set for the active reasoning turn.
   Fast, small, volatile.

2. Episodic Memory: Past incidents indexed by type and severity.
   Long-term project facts loaded at session start.
   "What happened before when battery SoC dropped below 20%?"

3. Semantic Memory: Domain knowledge, procedures, manuals.
   Vector-indexed long-term knowledge.
   "What is the procedure for CO2 scrubber replacement?"

4. Procedural Memory: Learned patterns, calibration data.
   Operator-specific preferences and feedback.
   "Last time we adjusted the CUSUM threshold it improved detection."
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class Episode:
    """A single episodic memory — something that happened."""

    episode_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    event_type: str = ""  # "anomaly", "maneuver", "alert", "reasoning", "decision"
    severity: str = "NOMINAL"
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: list[str] = field(default_factory=list)
    related_episodes: list[str] = field(default_factory=list)

    def matches(self, query: str) -> float:
        """Simple relevance scoring (keyword matching). Production: use embeddings."""
        query_lower = query.lower()
        score = 0.0
        if query_lower in self.summary.lower():
            score += 1.0
        if query_lower in self.event_type.lower():
            score += 0.5
        for tag in self.tags:
            if query_lower in tag.lower():
                score += 0.3
        return score


@dataclass
class Procedure:
    """A semantic memory — a procedure or piece of domain knowledge."""

    procedure_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    content: str = ""
    category: str = ""  # "emergency", "maintenance", "science", "operations"
    subsystem: str = ""  # "eclss", "power", "navigation", etc.
    tags: list[str] = field(default_factory=list)

    def matches(self, query: str) -> float:
        query_lower = query.lower()
        score = 0.0
        if query_lower in self.title.lower():
            score += 2.0
        if query_lower in self.content.lower():
            score += 0.5
        if query_lower in self.category.lower():
            score += 0.3
        if query_lower in self.subsystem.lower():
            score += 0.3
        return score


@dataclass
class LearnedPattern:
    """A procedural memory — something ARIA learned from experience."""

    pattern_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    description: str = ""
    context: str = ""  # When does this pattern apply?
    action: str = ""  # What should ARIA do?
    confidence: float = 0.5
    times_applied: int = 0
    last_applied: str = ""
    success_rate: float = 0.0


class MemoryStore:
    """Multi-tier memory store for ARIA.

    Usage:
        memory = MemoryStore(persist_dir="data/memory")
        await memory.store_episode(event_type="anomaly", summary="Battery SoC dropped to 15%")
        episodes = memory.recall_episodes("battery low", limit=5)
    """

    def __init__(self, persist_dir: str | Path | None = None) -> None:
        self._working: list[dict[str, Any]] = []  # Ring buffer, last N minutes
        self._working_max = 200
        self._episodes: list[Episode] = []
        self._episodes_max = 5000
        self._procedures: list[Procedure] = []
        self._patterns: list[LearnedPattern] = []
        self._persist_dir = Path(persist_dir) if persist_dir else None

        if self._persist_dir:
            self._load()

    # --- Working Memory (volatile, recent events) ---

    def push_working(self, event: dict[str, Any]) -> None:
        """Add to working memory (ring buffer)."""
        event["_timestamp"] = time.time()
        self._working.append(event)
        if len(self._working) > self._working_max:
            self._working = self._working[-self._working_max:]

    def get_working(self, minutes_back: float = 5.0) -> list[dict[str, Any]]:
        """Get recent working memory within time window."""
        cutoff = time.time() - (minutes_back * 60)
        return [e for e in self._working if e.get("_timestamp", 0) > cutoff]

    def clear_working(self) -> None:
        self._working.clear()

    # --- Episodic Memory (past incidents) ---

    async def store_episode(
        self,
        event_type: str,
        summary: str,
        details: dict[str, Any] | None = None,
        severity: str = "NOMINAL",
        tags: list[str] | None = None,
    ) -> Episode:
        """Store a new episodic memory."""
        episode = Episode(
            event_type=event_type,
            severity=severity,
            summary=summary,
            details=details or {},
            tags=tags or [],
        )
        self._episodes.append(episode)
        if len(self._episodes) > self._episodes_max:
            self._episodes = self._episodes[-self._episodes_max:]

        if self._persist_dir:
            self._save_episodes()

        return episode

    def recall_episodes(
        self,
        query: str = "",
        event_type: str = "",
        severity: str = "",
        limit: int = 10,
    ) -> list[Episode]:
        """Recall relevant episodes. Production: use vector embeddings."""
        episodes = self._episodes

        if event_type:
            episodes = [e for e in episodes if e.event_type == event_type]
        if severity:
            episodes = [e for e in episodes if e.severity == severity]

        if query:
            scored = [(e, e.matches(query)) for e in episodes]
            scored.sort(key=lambda x: x[1], reverse=True)
            return [e for e, s in scored[:limit] if s > 0]

        return episodes[-limit:]

    def get_episode_count(self) -> int:
        return len(self._episodes)

    # --- Semantic Memory (procedures, knowledge) ---

    def add_procedure(
        self,
        title: str,
        content: str,
        category: str = "",
        subsystem: str = "",
        tags: list[str] | None = None,
    ) -> Procedure:
        """Add a procedure to semantic memory."""
        proc = Procedure(
            title=title,
            content=content,
            category=category,
            subsystem=subsystem,
            tags=tags or [],
        )
        self._procedures.append(proc)
        # Prune to prevent unbounded growth over multi-year missions
        _MAX_PROCEDURES = 1000
        if len(self._procedures) > _MAX_PROCEDURES:
            self._procedures = self._procedures[-_MAX_PROCEDURES:]

        if self._persist_dir:
            self._save_procedures()

        return proc

    def search_procedures(self, query: str, limit: int = 5) -> list[Procedure]:
        """Search procedures by relevance."""
        scored = [(p, p.matches(query)) for p in self._procedures]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [p for p, s in scored[:limit] if s > 0]

    def get_procedures_by_subsystem(self, subsystem: str) -> list[Procedure]:
        return [p for p in self._procedures if p.subsystem == subsystem]

    # --- Procedural Memory (learned patterns) ---

    def learn_pattern(
        self,
        description: str,
        context: str,
        action: str,
        confidence: float = 0.5,
    ) -> LearnedPattern:
        """Store a learned pattern."""
        pattern = LearnedPattern(
            description=description,
            context=context,
            action=action,
            confidence=confidence,
        )
        self._patterns.append(pattern)
        return pattern

    def get_applicable_patterns(self, context: str) -> list[LearnedPattern]:
        """Find patterns that match the current context."""
        context_lower = context.lower()
        return [
            p for p in self._patterns
            if context_lower in p.context.lower() or p.context.lower() in context_lower
        ]

    def record_pattern_outcome(self, pattern_id: str, success: bool) -> None:
        """Update a pattern's success rate based on outcome."""
        for p in self._patterns:
            if p.pattern_id == pattern_id:
                p.times_applied += 1
                p.last_applied = datetime.now(timezone.utc).isoformat()
                # Running average
                p.success_rate = (
                    (p.success_rate * (p.times_applied - 1) + (1.0 if success else 0.0))
                    / p.times_applied
                )
                break

    # --- Summary ---

    def summary(self) -> dict[str, Any]:
        return {
            "working_memory_items": len(self._working),
            "episodes": len(self._episodes),
            "procedures": len(self._procedures),
            "learned_patterns": len(self._patterns),
        }

    # --- Persistence ---

    def _save_episodes(self) -> None:
        if not self._persist_dir:
            return
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        path = self._persist_dir / "episodes.json"
        data = [
            {
                "episode_id": e.episode_id,
                "event_type": e.event_type,
                "severity": e.severity,
                "summary": e.summary,
                "details": e.details,
                "timestamp": e.timestamp,
                "tags": e.tags,
            }
            for e in self._episodes[-1000:]  # Save last 1000
        ]
        path.write_text(json.dumps(data, indent=2, default=str))

    def _save_procedures(self) -> None:
        if not self._persist_dir:
            return
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        path = self._persist_dir / "procedures.json"
        data = [
            {
                "procedure_id": p.procedure_id,
                "title": p.title,
                "content": p.content,
                "category": p.category,
                "subsystem": p.subsystem,
                "tags": p.tags,
            }
            for p in self._procedures
        ]
        path.write_text(json.dumps(data, indent=2, default=str))

    def _load(self) -> None:
        if not self._persist_dir:
            return
        ep_path = self._persist_dir / "episodes.json"
        if ep_path.exists():
            try:
                data = json.loads(ep_path.read_text())
                for item in data:
                    self._episodes.append(Episode(**item))
                logger.info("memory.episodes_loaded", count=len(self._episodes))
            except Exception as exc:
                logger.error("memory.load_error", file="episodes.json", error=str(exc))

        proc_path = self._persist_dir / "procedures.json"
        if proc_path.exists():
            try:
                data = json.loads(proc_path.read_text())
                for item in data:
                    self._procedures.append(Procedure(**item))
                logger.info("memory.procedures_loaded", count=len(self._procedures))
            except Exception as exc:
                logger.error("memory.load_error", file="procedures.json", error=str(exc))
