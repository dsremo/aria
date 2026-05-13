"""Shared Scratchpad — inter-agent state sharing mechanism.

Per CENTRAL_AI_MASTER_PLAN Section 3.4:

The scratchpad is a shared key-value store where agents can post
observations and read observations from other agents. Unlike the
message bus (fire-and-forget events), scratchpad entries persist
until overwritten or expired.

Use cases:
  - PowerAgent posts current eclipse state → ThermalAgent reads to pre-heat
  - NavigationAgent posts conjunction data → PropulsionAgent reads for planning
  - EclssAgent posts fire detection → all agents read for emergency response
  - ScienceAgent posts radiation level → MedicalAgent reads for crew exposure

Entry structure:
  key: "subsystem.topic" (e.g., "power.eclipse_state", "nav.next_conjunction")
  value: arbitrary dict
  posted_by: agent name
  posted_at: timestamp
  ttl_s: time-to-live (0 = permanent until overwritten)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class ScratchpadEntry:
    """A single entry in the shared scratchpad."""
    key: str
    value: dict[str, Any]
    posted_by: str
    posted_at: float = field(default_factory=time.time)
    ttl_s: float = 0.0  # 0 = no expiry

    @property
    def expired(self) -> bool:
        if self.ttl_s <= 0:
            return False
        return time.time() - self.posted_at > self.ttl_s


class SharedScratchpad:
    """Shared key-value store for inter-agent state sharing.

    Thread-safe for async use. Agents write observations, other agents read.
    Entries can have a TTL for automatic expiry.

    Usage:
        # PowerAgent posts eclipse state
        scratchpad.write("power.eclipse_state", {"in_eclipse": True, "duration_min": 35}, "power")

        # ThermalAgent reads it
        eclipse = scratchpad.read("power.eclipse_state")
        if eclipse and eclipse["in_eclipse"]:
            await self._preheat_critical_zones()
    """

    def __init__(self) -> None:
        self._entries: dict[str, ScratchpadEntry] = {}

    def write(
        self,
        key: str,
        value: dict[str, Any],
        posted_by: str,
        ttl_s: float = 0.0,
    ) -> None:
        """Write an entry to the scratchpad."""
        self._entries[key] = ScratchpadEntry(
            key=key,
            value=value,
            posted_by=posted_by,
            ttl_s=ttl_s,
        )

    def read(self, key: str) -> dict[str, Any] | None:
        """Read an entry. Returns None if not found or expired."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expired:
            del self._entries[key]
            return None
        return entry.value

    def read_entry(self, key: str) -> ScratchpadEntry | None:
        """Read the full entry including metadata."""
        entry = self._entries.get(key)
        if entry and entry.expired:
            del self._entries[key]
            return None
        return entry

    def delete(self, key: str) -> bool:
        """Delete an entry. Returns True if it existed."""
        return self._entries.pop(key, None) is not None

    def keys_by_prefix(self, prefix: str) -> list[str]:
        """Get all keys matching a prefix (e.g., "power." returns all power entries)."""
        self._prune_expired()
        return [k for k in self._entries if k.startswith(prefix)]

    def keys_by_agent(self, agent_name: str) -> list[str]:
        """Get all keys posted by a specific agent."""
        self._prune_expired()
        return [k for k, e in self._entries.items() if e.posted_by == agent_name]

    def all_entries(self) -> dict[str, dict[str, Any]]:
        """Get all non-expired entries as {key: value}."""
        self._prune_expired()
        return {k: e.value for k, e in self._entries.items()}

    def _prune_expired(self) -> None:
        """Remove expired entries."""
        expired = [k for k, e in self._entries.items() if e.expired]
        for k in expired:
            del self._entries[k]

    @property
    def size(self) -> int:
        self._prune_expired()
        return len(self._entries)
