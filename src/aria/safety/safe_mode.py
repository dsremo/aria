"""Safe Mode Manager — 4-level degradation hierarchy.

Level 1 (REDUCED_SCIENCE): Shed science loads, reduce data collection
Level 2 (REDUCED_AUTONOMY): AI advisory only, Captain makes all decisions
Level 3 (MONITORING_ONLY): No actuator commands, monitor + report only
Level 4 (SURVIVAL): Minimum power — comms + ECLSS only, sun-pointing

Each level defines:
  - Which subsystems are active
  - Which tools are available
  - What authority level ARIA has
  - Entry/exit criteria
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

import structlog

from aria.bus.message_bus import Message, MessageBus
from aria.core.types import AuthorityLevel, EventPriority

logger = structlog.get_logger()


# Autonomy audit F29 — bound the safe-mode transition history so a
# multi-year mission cannot leak memory through repeated transitions.
_MAX_TRANSITION_HISTORY = 500


def _is_finite(x: Any) -> bool:
    """Autonomy audit F10 — refuse NaN / inf / non-numeric so a
    malformed health metric cannot bypass every threshold."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v)


class SafeLevel(IntEnum):
    """Safe mode levels. Higher = more restricted."""

    NOMINAL = 0
    REDUCED_SCIENCE = 1
    REDUCED_AUTONOMY = 2
    MONITORING_ONLY = 3
    SURVIVAL = 4


@dataclass
class SafeLevelConfig:
    """Configuration for each safe mode level."""

    level: SafeLevel
    active_agents: list[str]
    disabled_tools: list[str]
    max_authority: AuthorityLevel
    description: str


# Default configurations per level
LEVEL_CONFIGS: dict[SafeLevel, SafeLevelConfig] = {
    SafeLevel.NOMINAL: SafeLevelConfig(
        level=SafeLevel.NOMINAL,
        active_agents=["telemetry", "power", "navigation", "thermal", "eclss"],
        disabled_tools=[],
        max_authority=AuthorityLevel.SUPERVISED,
        description="All systems nominal. Full capability.",
    ),
    SafeLevel.REDUCED_SCIENCE: SafeLevelConfig(
        level=SafeLevel.REDUCED_SCIENCE,
        active_agents=["telemetry", "power", "navigation", "thermal", "eclss"],
        disabled_tools=["genastra_analyze_biosignature"],
        max_authority=AuthorityLevel.SUPERVISED,
        description="Science instruments powered down. Core ops continue.",
    ),
    SafeLevel.REDUCED_AUTONOMY: SafeLevelConfig(
        level=SafeLevel.REDUCED_AUTONOMY,
        active_agents=["telemetry", "power", "navigation", "thermal", "eclss"],
        disabled_tools=["genastra_analyze_biosignature", "conjunction_watch_plan_maneuver"],
        max_authority=AuthorityLevel.ADVISORY,
        description="AI advisory only. Captain makes all decisions.",
    ),
    SafeLevel.MONITORING_ONLY: SafeLevelConfig(
        level=SafeLevel.MONITORING_ONLY,
        active_agents=["telemetry", "power", "eclss"],
        disabled_tools=[
            "genastra_analyze_biosignature", "conjunction_watch_plan_maneuver",
            "conjunction_watch_run_screening",
        ],
        max_authority=AuthorityLevel.SENSOR_ONLY,
        description="No actuator commands. Monitor and report only.",
    ),
    SafeLevel.SURVIVAL: SafeLevelConfig(
        level=SafeLevel.SURVIVAL,
        active_agents=["power", "eclss"],
        disabled_tools=["*"],  # All tools except essential
        max_authority=AuthorityLevel.SENSOR_ONLY,
        description="SURVIVAL MODE. Minimum power. Comms + ECLSS only.",
    ),
}

# Auto-entry thresholds.  Recovery audit R-21 adds ``active_fdir_count``
# so a fault-storm escalates safe-mode regardless of health score.
ENTRY_THRESHOLDS: dict[SafeLevel, dict[str, float]] = {
    SafeLevel.REDUCED_SCIENCE: {"health_score_below": 80, "power_margin_below_w": 100,
                                 "active_fdir_count": 2},
    SafeLevel.REDUCED_AUTONOMY: {"health_score_below": 60, "consecutive_ai_errors": 5,
                                 "active_fdir_count": 4},
    SafeLevel.MONITORING_ONLY: {"health_score_below": 40, "critical_subsystems": 2,
                                "active_fdir_count": 6},
    SafeLevel.SURVIVAL: {"health_score_below": 20, "battery_soc_below": 10,
                         "active_fdir_count": 10},
}

# Exit (recovery) thresholds — must be higher than entry to prevent oscillation
EXIT_THRESHOLDS: dict[SafeLevel, dict[str, float]] = {
    SafeLevel.REDUCED_SCIENCE: {"health_score_above": 85, "power_margin_above_w": 200},
    SafeLevel.REDUCED_AUTONOMY: {"health_score_above": 70, "stability_minutes": 30},
    SafeLevel.MONITORING_ONLY: {"health_score_above": 55, "stability_minutes": 60},
    SafeLevel.SURVIVAL: {"health_score_above": 35, "stability_minutes": 120},
}


class SafeModeManager:
    """Manages safe mode transitions for ARIA.

    Monitors health score and automatically enters/exits safe modes.
    Captain can also manually command safe mode transitions.
    """

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._current_level = SafeLevel.NOMINAL
        self._entry_time: float | None = None
        self._transition_history: list[dict[str, Any]] = []
        # Autonomy audit F4 — monotonic clock so an NTP set-back can't
        # extend / shorten the stability window.
        self._stable_since_monotonic: float | None = None

    @property
    def current_level(self) -> SafeLevel:
        return self._current_level

    @property
    def config(self) -> SafeLevelConfig:
        return LEVEL_CONFIGS[self._current_level]

    def evaluate(
        self,
        health_score: float,
        battery_soc: float = 100.0,
        power_margin_w: float = 1000.0,
        critical_subsystem_count: int = 0,
        ai_consecutive_errors: int = 0,
        active_fdir_count: int = 0,
    ) -> SafeLevel | None:
        """Evaluate whether safe mode transition is needed.

        Returns new level if transition needed, None if staying.

        Autonomy audit F10 — any non-finite numeric input forces a
        conservative downgrade to MONITORING_ONLY rather than passing
        every threshold (NaN comparisons are always False).

        Autonomy audit F11 — escalation jumps to the DEEPEST triggering
        level on a single tick, not one level per tick.
        """
        # F10 — non-finite input → conservative downgrade.
        if not all(_is_finite(x) for x in (
            health_score, battery_soc, power_margin_w,
        )):
            logger.warning(
                "safe_mode.evaluate.non_finite_input",
                health_score=health_score,
                battery_soc=battery_soc,
                power_margin_w=power_margin_w,
            )
            if self._current_level < SafeLevel.MONITORING_ONLY:
                return SafeLevel.MONITORING_ONLY
            return None

        # F11 — find the deepest triggering level.
        deepest_trigger: SafeLevel | None = None
        for level in [SafeLevel.SURVIVAL, SafeLevel.MONITORING_ONLY,
                      SafeLevel.REDUCED_AUTONOMY, SafeLevel.REDUCED_SCIENCE]:
            if level <= self._current_level:
                continue
            thresholds = ENTRY_THRESHOLDS.get(level, {})
            triggered = False
            if health_score < thresholds.get("health_score_below", 0):
                triggered = True
            if battery_soc < thresholds.get("battery_soc_below", 0):
                triggered = True
            if power_margin_w < thresholds.get("power_margin_below_w", -9999):
                triggered = True
            if critical_subsystem_count >= thresholds.get("critical_subsystems", 999):
                triggered = True
            if ai_consecutive_errors >= thresholds.get("consecutive_ai_errors", 999):
                triggered = True
            # Recovery audit R-21 — active-FDIR-fault-count gate.
            if active_fdir_count >= thresholds.get("active_fdir_count", 999):
                triggered = True
            if triggered:
                # SURVIVAL is checked first; the loop runs strict-greater
                # to current_level so the FIRST hit IS the deepest.
                deepest_trigger = level
                break
        if deepest_trigger is not None:
            return deepest_trigger

        # Recovery (exit to less restrictive mode).
        if self._current_level > SafeLevel.NOMINAL:
            exit_to = SafeLevel(self._current_level - 1)
            thresholds = EXIT_THRESHOLDS.get(self._current_level, {})

            can_exit = True
            if health_score < thresholds.get("health_score_above", 0):
                can_exit = False

            # F4 — stability window measured on monotonic clock.
            required_minutes = thresholds.get("stability_minutes", 0)
            if required_minutes > 0:
                nm = time.monotonic()
                if self._stable_since_monotonic is None:
                    self._stable_since_monotonic = nm
                    can_exit = False
                elif (nm - self._stable_since_monotonic) / 60 < required_minutes:
                    can_exit = False
            else:
                self._stable_since_monotonic = None

            if can_exit:
                return exit_to

        return None

    async def transition(self, new_level: SafeLevel, reason: str = "") -> None:
        """Execute safe mode transition."""
        old_level = self._current_level
        if new_level == old_level:
            return

        self._current_level = new_level
        self._entry_time = time.time()
        self._stable_since_monotonic = None

        record = {
            "from": old_level.name,
            "to": new_level.name,
            "reason": reason,
            "timestamp": time.time(),
        }
        self._transition_history.append(record)
        # Autonomy audit F29 — bound the history.
        if len(self._transition_history) > _MAX_TRANSITION_HISTORY:
            self._transition_history = self._transition_history[-_MAX_TRANSITION_HISTORY:]

        direction = "ESCALATED" if new_level > old_level else "RECOVERED"

        logger.warning(
            "safe_mode.transition",
            direction=direction,
            from_level=old_level.name,
            to_level=new_level.name,
            reason=reason,
        )

        # Notify on the bus
        priority = EventPriority.P0_EMERGENCY if new_level >= SafeLevel.MONITORING_ONLY else EventPriority.P1_CRITICAL
        await self._bus.publish(
            Message(
                topic="aria.safety.mode_change",
                payload={
                    "direction": direction,
                    "from_level": old_level.name,
                    "to_level": new_level.name,
                    "config": {
                        "active_agents": self.config.active_agents,
                        "max_authority": self.config.max_authority.name,
                        "description": self.config.description,
                    },
                    "reason": reason,
                },
                priority=priority,
                source_agent="safe_mode_manager",
            )
        )

    def get_history(self) -> list[dict[str, Any]]:
        return self._transition_history

    def force_level(self, new_level: SafeLevel, reason: str = "") -> None:
        """Recovery audit R-1: synchronous safe-mode demote callable from
        threads outside the asyncio loop (e.g. ground-deadman watchdog,
        deadman supervisor).

        Records the intent immediately, then schedules the async
        ``transition()`` on the running loop via
        ``asyncio.run_coroutine_threadsafe`` if a loop is reachable.
        Falls back to a synchronous state mutation + bus-bypass log
        when no loop is available so the level change is durable even
        in last-gasp paths.
        """
        if new_level == self._current_level:
            return
        # Always mutate locally first so any subsequent read sees the
        # demoted level even if the loop scheduling races.
        old_level = self._current_level
        self._current_level = new_level
        self._entry_time = time.time()
        self._stable_since_monotonic = None
        self._transition_history.append({
            "from": old_level.name,
            "to": new_level.name,
            "reason": f"force_level:{reason}",
            "timestamp": time.time(),
            "synchronous": True,
        })
        if len(self._transition_history) > _MAX_TRANSITION_HISTORY:
            self._transition_history = self._transition_history[-_MAX_TRANSITION_HISTORY:]
        logger.error("safe_mode.force_level",
                     from_level=old_level.name,
                     to_level=new_level.name,
                     reason=reason)
        # Attempt to publish the bus event from whatever loop the bus
        # belongs to.  If no loop is running in this thread we fall
        # back to the bus's own loop reference if it has one.
        try:
            loop = getattr(self._bus, "_loop", None) or asyncio.get_event_loop()
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.transition(new_level, reason=f"force:{reason}"),
                    loop,
                )
        except Exception as exc:    # noqa: BLE001
            logger.warning("safe_mode.force_level.publish_failed",
                           error=f"{type(exc).__name__}: {exc}")


# ── Singleton (R-1) ────────────────────────────────────────────────

_SAFE_MODE_SINGLETON: SafeModeManager | None = None


def set_safe_mode_singleton(manager: SafeModeManager) -> None:
    """Recovery audit R-1: register the SafeModeManager so threads
    outside the coordinator (ground deadman, deadman supervisor, FDIR
    recovery plans running in worker threads) can reach it without
    holding a reference."""
    global _SAFE_MODE_SINGLETON
    _SAFE_MODE_SINGLETON = manager


def get_safe_mode_singleton() -> SafeModeManager | None:
    return _SAFE_MODE_SINGLETON
