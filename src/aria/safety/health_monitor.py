"""Ping-based health monitor — detects stuck or unresponsive subsystems.

Implements the F Prime HealthImpl pattern: periodically sends keyed
pings to each registered subsystem. If a subsystem fails to respond
within warn_cycles, emits WARNING. If it misses fatal_cycles, emits
FATAL and triggers FDIR restart.

This catches failure modes that status-polling misses:
- Agent stuck in infinite loop (status stays BUSY forever)
- Deadlocked thread (no status update, no exception)
- Crashed but not cleaned up (zombie process)

Pattern studied from NASA JPL's F Prime HealthComponentImpl.cpp
(Apache 2.0) and reimplemented for ARIA's Python architecture.

Usage:
    monitor = HealthMonitor(bus=get_event_bus())
    monitor.register("thermal", ping_fn=thermal_agent.handle_ping,
                     warn_cycles=3, fatal_cycles=10)
    monitor.register("power", ping_fn=power_agent.handle_ping)
    # Call once per tick cycle:
    monitor.check_all()
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class PingEntry:
    """Tracking state for one monitored subsystem."""
    name: str
    ping_fn: Callable[[int], int]  # takes key, returns key if alive
    warn_cycles: int = 3           # cycles before WARNING
    fatal_cycles: int = 10         # cycles before FATAL
    enabled: bool = True

    # Internal state
    pending_key: int = 0
    missed_cycles: int = 0
    total_pings: int = 0
    total_failures: int = 0
    last_response_time: float = 0.0
    state: str = "ok"  # ok, warning, fatal


class HealthMonitor:
    """Ping-based health monitor for ARIA subsystems.

    Each registered subsystem must implement a ping function that
    takes an integer key and returns it unchanged. If the subsystem
    is alive and responsive, it echoes the key back. If stuck or
    crashed, the call either blocks (caught by timeout) or raises.

    The monitor runs check_all() once per tick cycle, incrementing
    missed_cycles for any subsystem that fails to respond.
    """

    def __init__(self, bus: Any = None) -> None:
        self._entries: Dict[str, PingEntry] = {}
        self._lock = threading.Lock()
        self._bus = bus
        self._cycle_count: int = 0
        self._key_counter: int = 0

    def register(
        self,
        name: str,
        ping_fn: Callable[[int], int],
        warn_cycles: int = 3,
        fatal_cycles: int = 10,
    ) -> None:
        """Register a subsystem for health monitoring."""
        with self._lock:
            self._entries[name] = PingEntry(
                name=name,
                ping_fn=ping_fn,
                warn_cycles=warn_cycles,
                fatal_cycles=fatal_cycles,
            )

    def unregister(self, name: str) -> None:
        """Remove a subsystem from monitoring."""
        with self._lock:
            self._entries.pop(name, None)

    def enable(self, name: str, enabled: bool = True) -> None:
        """Enable or disable monitoring for a specific subsystem."""
        with self._lock:
            if name in self._entries:
                self._entries[name].enabled = enabled

    def set_thresholds(self, name: str, warn_cycles: int, fatal_cycles: int) -> None:
        """Adjust thresholds at runtime (ground-commandable)."""
        with self._lock:
            if name in self._entries:
                self._entries[name].warn_cycles = warn_cycles
                self._entries[name].fatal_cycles = fatal_cycles

    def check_all(self, sim_time_yr: float = 0.0) -> Dict[str, str]:
        """Ping all registered subsystems and update their health state.

        Returns dict of {name: state} for all monitored subsystems.
        """
        self._cycle_count += 1
        results: Dict[str, str] = {}

        with self._lock:
            entries = list(self._entries.values())

        for entry in entries:
            if not entry.enabled:
                results[entry.name] = "disabled"
                continue

            self._key_counter += 1
            key = self._key_counter
            entry.pending_key = key
            entry.total_pings += 1

            # Try to ping the subsystem
            try:
                response = entry.ping_fn(key)
                if response == key:
                    # Subsystem is alive
                    entry.missed_cycles = 0
                    entry.last_response_time = time.monotonic()
                    entry.state = "ok"
                else:
                    # Wrong key — subsystem is confused
                    entry.missed_cycles += 1
                    entry.total_failures += 1
            except Exception as exc:
                # R65 (2026-04-24): was silent bump — a subsystem raising
                # from its ping callback (hardware fault, memory error,
                # broken invariant) would increment counters forever with
                # no visibility into what failed.  Log once per ping.
                import structlog
                structlog.get_logger().warning(
                    "health_monitor.ping_exception",
                    subsystem=entry.name,
                    missed_cycles=entry.missed_cycles + 1,
                    error=f"{type(exc).__name__}: {exc}",
                )
                entry.missed_cycles += 1
                entry.total_failures += 1

            # Evaluate health state
            if entry.missed_cycles >= entry.fatal_cycles:
                if entry.state != "fatal":
                    entry.state = "fatal"
                    self._emit(
                        "health.fatal",
                        entry.name,
                        f"Subsystem '{entry.name}' unresponsive for "
                        f"{entry.missed_cycles} cycles — triggering FDIR restart",
                        sim_time_yr,
                    )
            elif entry.missed_cycles >= entry.warn_cycles:
                if entry.state != "warning":
                    entry.state = "warning"
                    self._emit(
                        "health.warning",
                        entry.name,
                        f"Subsystem '{entry.name}' missed {entry.missed_cycles} pings",
                        sim_time_yr,
                    )

            results[entry.name] = entry.state

        return results

    def _emit(self, topic: str, subsystem: str, message: str, sim_time_yr: float) -> None:
        """Publish a health event to the bus."""
        from aria.safety._bus_publish import publish_compat
        severity = "critical" if "fatal" in topic else "warning"
        publish_compat(
            self._bus,
            topic,
            severity=severity,
            source="health_monitor",
            payload={"subsystem": subsystem, "message": message},
            sim_time_yr=sim_time_yr,
        )

    def status(self) -> Dict[str, Any]:
        """Return full health monitor status."""
        with self._lock:
            entries = {}
            for name, e in self._entries.items():
                entries[name] = {
                    "state": e.state,
                    "enabled": e.enabled,
                    "missed_cycles": e.missed_cycles,
                    "total_pings": e.total_pings,
                    "total_failures": e.total_failures,
                    "warn_threshold": e.warn_cycles,
                    "fatal_threshold": e.fatal_cycles,
                }
            return {
                "cycle_count": self._cycle_count,
                "subsystems": entries,
                "healthy": sum(1 for e in self._entries.values() if e.state == "ok"),
                "warning": sum(1 for e in self._entries.values() if e.state == "warning"),
                "fatal": sum(1 for e in self._entries.values() if e.state == "fatal"),
            }
