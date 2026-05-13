"""V3-F4: Satellite mission context for operator dashboard.

The V3 audit (Fischer panel §F-4) flagged that an anomaly on Day 1,847 of a
5-year mission has a completely different operational context than the same
anomaly on Day 47.  Today's dashboard shows only score and parameters; the
operator has to cross-reference STK / GMAT / ESOC Timeline Tool to get mission
age, design-life %, next eclipse, next ground-contact pass, and upcoming
maneuvers.  That adds 3-5 min per investigation.

This module builds the `SatelliteMissionContext` consumed by the /ops/
operator dashboard (served from src/aria/dsremo/web_assets/) via the
/satellites/{sat}/context HTTP endpoint.

Reference:
  * ECSS-E-ST-70C §5.4.2 — mission timeline integration requirements for
    ground-segment HMI.
  * Hoots & Roehrich 1980 Spacetrack Report No. 3 — TLE/SGP4 standard
    (auto-projection of eclipses & AOS from TLEs is a follow-up item; this
    module consumes pre-registered OrbitalEventTimeline entries).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .orbital_events import OrbitalEvent, OrbitalEventTimeline, OrbitalEventType


SECONDS_PER_DAY = 86_400.0  # SI definition
DEFAULT_HORIZON_S = 86_400.0  # ESTIMATE — 24 h rolling window matches operator shift length (ECSS-E-ST-70C §5.4.2 recommends ≥12 h)

_ECLIPSE_TYPES = frozenset({
    OrbitalEventType.ECLIPSE_ENTRY.value,
    OrbitalEventType.ECLIPSE_EXIT.value,
})
_CONTACT_TYPES = frozenset({OrbitalEventType.GROUND_STATION_HANDOVER.value})
_MANEUVER_TYPES = frozenset({OrbitalEventType.MANEUVER.value})


@dataclass(frozen=True)
class EventSummary:
    """A single orbital event projected relative to 'now'.

    starts_in_s is negative if the event has already begun and is ongoing;
    it is the positive gap until start_epoch otherwise.  Callers rendering
    the Gantt use (start_epoch, duration_s) directly — starts_in_s is for
    the sidebar text ("Next eclipse in 32 min").
    """

    event_type: str
    start_epoch: float
    duration_s: float
    description: str
    starts_in_s: float

    @classmethod
    def from_event(cls, ev: OrbitalEvent, now_epoch: float) -> "EventSummary":
        return cls(
            event_type=ev.event_type,
            start_epoch=ev.start_epoch,
            duration_s=ev.duration_s,
            description=ev.description,
            starts_in_s=ev.start_epoch - now_epoch,
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SatelliteMissionContext:
    """Context block rendered in the operator dashboard sidebar."""

    satellite_id: str
    launch_epoch: float | None
    design_life_s: float | None
    mission_elapsed_s: float
    design_life_pct_consumed: float | None
    now_epoch: float
    horizon_s: float
    next_eclipse: EventSummary | None
    next_contact: EventSummary | None
    next_maneuver: EventSummary | None
    upcoming_events: list[EventSummary] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "satellite_id": self.satellite_id,
            "launch_epoch": self.launch_epoch,
            "design_life_s": self.design_life_s,
            "mission_elapsed_s": self.mission_elapsed_s,
            "design_life_pct_consumed": self.design_life_pct_consumed,
            "now_epoch": self.now_epoch,
            "horizon_s": self.horizon_s,
            "next_eclipse": self.next_eclipse.to_dict() if self.next_eclipse else None,
            "next_contact": self.next_contact.to_dict() if self.next_contact else None,
            "next_maneuver": self.next_maneuver.to_dict() if self.next_maneuver else None,
            "upcoming_events": [e.to_dict() for e in self.upcoming_events],
        }


def _earliest_future(
    events: list[OrbitalEvent],
    type_set: frozenset,
    now_epoch: float,
) -> OrbitalEvent | None:
    """Earliest event whose start_epoch ≥ now_epoch and type ∈ type_set.

    If no future event matches, returns the currently-active event of that
    type (start ≤ now ≤ end) so the sidebar can render "Eclipse IN PROGRESS
    — exits in 7 min" rather than "next eclipse: none".
    """
    future = [e for e in events if e.event_type in type_set and e.start_epoch >= now_epoch]
    if future:
        return min(future, key=lambda e: e.start_epoch)
    active = [
        e for e in events
        if e.event_type in type_set and e.start_epoch <= now_epoch <= e.end_epoch
    ]
    if active:
        return min(active, key=lambda e: e.end_epoch)
    return None


def build_context(
    satellite_id: str,
    launch_epoch: float | None,
    design_life_s: float | None,
    timeline: OrbitalEventTimeline,
    now_epoch: float,
    horizon_s: float = DEFAULT_HORIZON_S,
) -> SatelliteMissionContext:
    """Assemble a SatelliteMissionContext for the operator dashboard.

    Pure function: reads from `timeline.all_events(satellite_id)` and
    composes the context block.  The caller supplies launch_epoch and
    design_life_s (both optional — a satellite without mission config yet
    still returns a usable context with nulls in those fields).
    """
    if horizon_s <= 0.0:
        raise ValueError(f"horizon_s must be positive, got {horizon_s!r}")

    mission_elapsed_s = 0.0
    design_life_pct_consumed: float | None = None
    if launch_epoch is not None:
        mission_elapsed_s = max(0.0, now_epoch - launch_epoch)
        if design_life_s is not None and design_life_s > 0.0:
            design_life_pct_consumed = 100.0 * mission_elapsed_s / design_life_s

    all_ev = timeline.all_events(satellite_id)

    next_eclipse_ev = _earliest_future(all_ev, _ECLIPSE_TYPES, now_epoch)
    next_contact_ev = _earliest_future(all_ev, _CONTACT_TYPES, now_epoch)
    next_maneuver_ev = _earliest_future(all_ev, _MANEUVER_TYPES, now_epoch)

    window_to = now_epoch + horizon_s
    upcoming = sorted(
        (
            e for e in all_ev
            if e.start_epoch <= window_to and e.end_epoch >= now_epoch
        ),
        key=lambda e: e.start_epoch,
    )

    return SatelliteMissionContext(
        satellite_id=satellite_id,
        launch_epoch=launch_epoch,
        design_life_s=design_life_s,
        mission_elapsed_s=mission_elapsed_s,
        design_life_pct_consumed=design_life_pct_consumed,
        now_epoch=now_epoch,
        horizon_s=horizon_s,
        next_eclipse=(
            EventSummary.from_event(next_eclipse_ev, now_epoch)
            if next_eclipse_ev else None
        ),
        next_contact=(
            EventSummary.from_event(next_contact_ev, now_epoch)
            if next_contact_ev else None
        ),
        next_maneuver=(
            EventSummary.from_event(next_maneuver_ev, now_epoch)
            if next_maneuver_ev else None
        ),
        upcoming_events=[EventSummary.from_event(e, now_epoch) for e in upcoming],
    )


__all__ = [
    "DEFAULT_HORIZON_S",
    "EventSummary",
    "SatelliteMissionContext",
    "build_context",
]
