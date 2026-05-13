"""Context Window Manager — manages what goes into the LLM's context budget.

Per CENTRAL_AI_MASTER_PLAN Part 10:
  - Not all information can fit in the LLM's context window
  - Critical: prioritize safety-relevant data over routine telemetry
  - Budget: allocate tokens across system state, anomalies, procedures, memory

  - If a tool result exceeds budget, store full result and provide summary
  - Always include active alerts and anomalies (safety first)
  - Include relevant procedures for the current situation
  - Include recent memory if relevant

Token Budget Allocation (8K context):
  System prompt:        1500 tokens (fixed)
  System state:         1000 tokens
  Active anomalies:     2000 tokens (highest priority)
  Relevant procedures:   800 tokens
  Memory/history:        500 tokens
  Tool results:         2000 tokens
  Slack:                 200 tokens
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from aria.core.types import MissionPhase, Severity
from aria.memory.store import MemoryStore

logger = structlog.get_logger()

# Token estimation: ~4 chars per token (rough)
CHARS_PER_TOKEN = 4

# Budget allocation
TOKEN_BUDGETS = {
    "system_state": 1000,
    "active_anomalies": 2000,
    "procedures": 800,
    "memory": 500,
    "tool_results": 2000,
}
TOTAL_BUDGET = 8000


def estimate_tokens(text: str) -> int:
    """Rough token estimate — 1 token ≈ 4 chars."""
    return len(text) // CHARS_PER_TOKEN + 1


@dataclass
class ContextBudget:
    """Tracks token usage across context sections."""
    system_state_used: int = 0
    anomalies_used: int = 0
    procedures_used: int = 0
    memory_used: int = 0
    tool_results_used: int = 0

    @property
    def total_used(self) -> int:
        return (
            self.system_state_used + self.anomalies_used +
            self.procedures_used + self.memory_used + self.tool_results_used
        )

    @property
    def remaining(self) -> int:
        return max(0, TOTAL_BUDGET - self.total_used)


@dataclass
class ContextWindow:
    """Assembled context for a reasoning session."""
    system_state: str = ""
    anomalies: str = ""
    procedures: str = ""
    memory: str = ""
    budget: ContextBudget = field(default_factory=ContextBudget)
    overflow_refs: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        """Assemble into a single context block for the system prompt."""
        parts = []
        if self.system_state:
            parts.append(f"## Current System State\n{self.system_state}")
        if self.anomalies:
            parts.append(f"## Active Anomalies\n{self.anomalies}")
        if self.procedures:
            parts.append(f"## Relevant Procedures\n{self.procedures}")
        if self.memory:
            parts.append(f"## Recent Events\n{self.memory}")
        if self.overflow_refs:
            parts.append(f"[Note: {len(self.overflow_refs)} full results stored to disk — "
                         "summaries provided above]")
        return "\n\n".join(parts)


class ContextWindowManager:
    """Builds a context window within token budget.

    Priority order (safety first):
      1. Active anomalies and alerts (CRITICAL > WARNING > WATCH)
      2. System state relevant to current situation
      3. Relevant procedures (matched by keywords)
      4. Recent episodic memory
      5. Tool results (truncated to budget)
    """

    def __init__(self, memory: MemoryStore | None = None) -> None:
        self._memory = memory

    def build_context(
        self,
        system_status: dict[str, Any],
        recent_anomalies: list[dict[str, Any]] | None = None,
        active_alerts: list[dict[str, Any]] | None = None,
        query_text: str = "",
        mission_phase: str = "NOMINAL_LEO",
    ) -> ContextWindow:
        """Build a context window within budget.

        Args:
            system_status: coordinator.system_status() output
            recent_anomalies: recent anomaly events
            active_alerts: current captain alerts
            query_text: captain's query (for procedure matching)
            mission_phase: current mission phase

        Returns:
            ContextWindow with assembled text sections
        """
        ctx = ContextWindow()

        # 1. Active anomalies (highest priority — safety)
        anomalies = recent_anomalies or []
        alerts = active_alerts or []
        ctx.anomalies = self._build_anomalies_section(anomalies, alerts)
        ctx.budget.anomalies_used = estimate_tokens(ctx.anomalies)

        # 2. System state (condensed to fit budget)
        ctx.system_state = self._build_state_section(system_status, mission_phase)
        ctx.budget.system_state_used = estimate_tokens(ctx.system_state)

        # 3. Relevant procedures (matched by query + anomaly keywords)
        keywords = self._extract_keywords(query_text, anomalies, alerts)
        ctx.procedures = self._build_procedures_section(keywords)
        ctx.budget.procedures_used = estimate_tokens(ctx.procedures)

        # 4. Memory (if available and budget permits)
        if self._memory and ctx.budget.remaining > 200:
            ctx.memory = self._build_memory_section(query_text)
            ctx.budget.memory_used = estimate_tokens(ctx.memory)

        return ctx

    def fit_tool_result(self, result_text: str, ctx: ContextWindow) -> str:
        """Fit a tool result into remaining context budget.

        If result exceeds budget, truncate and note overflow.
        """
        budget = TOKEN_BUDGETS["tool_results"]
        tokens = estimate_tokens(result_text)

        if tokens <= budget:
            ctx.budget.tool_results_used += tokens
            return result_text

        # Truncate to budget
        max_chars = budget * CHARS_PER_TOKEN
        truncated = result_text[:max_chars]
        ctx.overflow_refs.append(f"tool_result_{len(ctx.overflow_refs)}")
        ctx.budget.tool_results_used += budget

        return truncated + f"\n[TRUNCATED: full result ({tokens} tokens) stored as reference]"

    def _build_anomalies_section(
        self,
        anomalies: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
    ) -> str:
        """Build anomalies section — sorted by severity (CRITICAL first)."""
        severity_order = {"EMERGENCY": 0, "CRITICAL": 1, "WARNING": 2, "WATCH": 3}

        # Combine and sort by severity
        all_items = []
        for a in anomalies:
            all_items.append({
                "severity": a.get("severity", "WATCH"),
                "text": a.get("message", str(a)),
                "source": a.get("subsystem", a.get("source", "")),
            })
        for a in alerts:
            all_items.append({
                "severity": a.get("severity", "WARNING"),
                "text": a.get("message", a.get("description", str(a))),
                "source": "captain_alert",
            })

        all_items.sort(key=lambda x: severity_order.get(x["severity"], 9))

        # Truncate to budget
        budget = TOKEN_BUDGETS["active_anomalies"]
        lines = []
        used = 0
        for item in all_items:
            line = f"[{item['severity']}] ({item['source']}) {item['text']}"
            line_tokens = estimate_tokens(line)
            if used + line_tokens > budget:
                lines.append(f"... and {len(all_items) - len(lines)} more (truncated)")
                break
            lines.append(line)
            used += line_tokens

        if not lines:
            return "No active anomalies."
        return "\n".join(lines)

    def _build_state_section(self, status: dict[str, Any], phase: str) -> str:
        """Build condensed system state."""
        lines = [f"Phase: {phase}"]

        health = status.get("health_score", 100.0)
        safe_mode = status.get("safe_mode", "NOMINAL")
        lines.append(f"Health: {health:.0f}% | Safe Mode: {safe_mode}")

        # Agent statuses
        agents = status.get("agents", {})
        if agents:
            agent_summary = ", ".join(
                f"{name}:{info.get('status', '?')}" if isinstance(info, dict) else f"{name}:{info}"
                for name, info in agents.items()
            )
            lines.append(f"Agents: {agent_summary}")

        # Last anomaly
        last = status.get("last_anomaly")
        if last and isinstance(last, dict):
            lines.append(f"Last anomaly: [{last.get('severity', '?')}] {last.get('source', '')}")

        return "\n".join(lines)

    def _build_procedures_section(self, keywords: list[str]) -> str:
        """Find relevant procedures by keyword matching."""
        if not self._memory or not keywords:
            return ""

        budget = TOKEN_BUDGETS["procedures"]
        lines = []
        used = 0

        for keyword in keywords:
            procs = self._memory.search_procedures(keyword)
            for proc in procs[:2]:  # Max 2 per keyword
                title = proc.get("title", "")
                content = proc.get("content", "")
                line = f"**{title}**: {content}"
                tokens = estimate_tokens(line)
                if used + tokens > budget:
                    break
                lines.append(line)
                used += tokens

        return "\n".join(lines) if lines else ""

    def _build_memory_section(self, query: str) -> str:
        """Recall relevant episodic memory."""
        if not self._memory or not query:
            return ""

        episodes = self._memory.recall_episodes(query=query, limit=3)
        if not episodes:
            return ""

        budget = TOKEN_BUDGETS["memory"]
        lines = []
        used = 0
        for ep in episodes:
            summary = getattr(ep, "summary", "") if not isinstance(ep, dict) else ep.get("summary", "")
            line = f"- {summary}"
            tokens = estimate_tokens(line)
            if used + tokens > budget:
                break
            lines.append(line)
            used += tokens

        return "\n".join(lines)

    @staticmethod
    def _extract_keywords(
        query: str,
        anomalies: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
    ) -> list[str]:
        """Extract keywords from query + anomaly context for procedure matching."""
        keywords = []

        # From query
        key_terms = [
            "fire", "depressurization", "leak", "collision", "maneuver",
            "radiation", "battery", "power", "co2", "o2", "eclipse",
            "thermal", "fuel", "propellant", "comms", "signal",
        ]
        query_lower = query.lower()
        keywords.extend(t for t in key_terms if t in query_lower)

        # From anomalies
        for a in anomalies:
            msg = a.get("message", "").lower()
            keywords.extend(t for t in key_terms if t in msg)

        # From alerts
        for a in alerts:
            msg = (a.get("message", "") + a.get("description", "")).lower()
            keywords.extend(t for t in key_terms if t in msg)

        return list(set(keywords))[:5]  # Max 5 keywords
