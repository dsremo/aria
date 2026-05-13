"""Orbital event timeline — correlate anomalies with orbital context.

Experienced telemetry observers correlate anomalies with orbital events:
    - Eclipse entry/exit (thermal discontinuity)
    - South Atlantic Anomaly (SAA) passage (radiation noise)
    - Ground station handover (brief comms gap)
    - Perigee/apogee crossing (gravitational stress)
    - Solar array pointing errors

This module provides a simple event registration and lookup API.
Operators register expected orbital events; the detection pipeline checks
if a detected anomaly coincides with an orbital event and annotates it.

Usage:
    register_orbital_event("SAT-1", OrbitalEvent(
        event_type="saa_passage",
        start_epoch=1711900000.0,
        duration_s=600.0,
        description="SAA transit — expect radiation spikes",
    ))

    ctx = get_orbital_context("SAT-1", timestamp_epoch)
    if ctx:
        # anomaly during SAA → likely radiation, not real fault
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, unique

import structlog

logger = structlog.get_logger()


@unique
class OrbitalEventType(str, Enum):
    ECLIPSE_ENTRY = "eclipse_entry"
    ECLIPSE_EXIT = "eclipse_exit"
    SAA_PASSAGE = "saa_passage"
    GROUND_STATION_HANDOVER = "gs_handover"
    PERIGEE = "perigee"
    APOGEE = "apogee"
    MANEUVER = "maneuver"
    CUSTOM = "custom"


@dataclass
class OrbitalEvent:
    """A single orbital event with start time and duration."""
    event_type: str  # OrbitalEventType value or custom string
    start_epoch: float  # UTC epoch seconds
    duration_s: float = 300.0  # default 5 min
    description: str = ""
    suppress_detectors: list[str] = field(default_factory=list)

    @property
    def end_epoch(self) -> float:
        return self.start_epoch + self.duration_s

    def is_active(self, t: float) -> bool:
        return self.start_epoch <= t <= self.end_epoch


class OrbitalEventTimeline:
    """Per-satellite timeline of orbital events."""

    def __init__(self, max_events: int = 10000) -> None:
        self._events: dict[str, list[OrbitalEvent]] = {}  # sat_id → events
        self._max = max_events

    def register(self, satellite_id: str, event: OrbitalEvent) -> None:
        """Add an orbital event to the timeline."""
        events = self._events.setdefault(satellite_id, [])
        events.append(event)
        # GC: remove expired events
        now = time.time()
        events[:] = [e for e in events if e.end_epoch > now - 3600]
        if len(events) > self._max:
            events[:] = events[-self._max:]

    def register_periodic_eclipse(
        self,
        satellite_id: str,
        period_s: float = 5400.0,        # ESTIMATE — 90-min LEO orbital period (Wertz & Larson 1999 SMAD §6.2)
        eclipse_fraction: float = 0.35,  # ESTIMATE — 35% eclipse fraction typical LEO (Wertz & Larson 1999 §11.4)
        first_eclipse_epoch: float = 0.0,
        n_orbits: int = 100,
    ) -> int:
        """Register a repeating eclipse pattern for N future orbits.

        Args:
            period_s: Orbital period in seconds (5400 for LEO).
            eclipse_fraction: Fraction of orbit in eclipse (0.35 typical for LEO).
            first_eclipse_epoch: UTC epoch of first eclipse entry.
            n_orbits: How many future orbits to pre-register.

        Returns:
            Number of events registered.
        """
        eclipse_duration = period_s * eclipse_fraction
        count = 0
        for i in range(n_orbits):
            entry_epoch = first_eclipse_epoch + i * period_s
            self.register(satellite_id, OrbitalEvent(
                event_type=OrbitalEventType.ECLIPSE_ENTRY.value,
                start_epoch=entry_epoch,
                duration_s=30.0,  # transition window
                description=f"Eclipse entry (orbit {i+1})",
            ))
            exit_epoch = entry_epoch + eclipse_duration
            self.register(satellite_id, OrbitalEvent(
                event_type=OrbitalEventType.ECLIPSE_EXIT.value,
                start_epoch=exit_epoch,
                duration_s=30.0,
                description=f"Eclipse exit (orbit {i+1})",
            ))
            count += 2
        return count

    def get_context(self, satellite_id: str, t: float) -> list[OrbitalEvent]:
        """Return all active orbital events at time t for a satellite."""
        events = self._events.get(satellite_id, [])
        return [e for e in events if e.is_active(t)]

    def all_events(self, satellite_id: str) -> list[OrbitalEvent]:
        """Return a copy of every registered event for the satellite.

        Used by satellite_context.build_context() and the /orbital_events
        API endpoint (V3-F4).  Returned list is ordered by insertion; callers
        that need chronological order should sort by start_epoch.
        """
        return list(self._events.get(satellite_id, []))

    def events_in_window(
        self,
        satellite_id: str,
        from_epoch: float,
        to_epoch: float,
    ) -> list[OrbitalEvent]:
        """Return events overlapping the window [from_epoch, to_epoch]."""
        if to_epoch < from_epoch:
            from_epoch, to_epoch = to_epoch, from_epoch
        return [
            e for e in self._events.get(satellite_id, [])
            if e.start_epoch <= to_epoch and e.end_epoch >= from_epoch
        ]

    def is_during_event(self, satellite_id: str, t: float, event_type: str | None = None) -> bool:
        """Check if timestamp falls during an orbital event."""
        for e in self.get_context(satellite_id, t):
            if event_type is None or e.event_type == event_type:
                return True
        return False

    def get_suppressed_detectors(self, satellite_id: str, t: float) -> set[str]:
        """Return detectors that should be suppressed due to active orbital events."""
        suppressed: set[str] = set()
        for e in self.get_context(satellite_id, t):
            suppressed.update(e.suppress_detectors)
        return suppressed

    def clear(self, satellite_id: str | None = None) -> None:
        if satellite_id:
            self._events.pop(satellite_id, None)
        else:
            self._events.clear()


# Singleton
_timeline = OrbitalEventTimeline()


def get_orbital_timeline() -> OrbitalEventTimeline:
    return _timeline
