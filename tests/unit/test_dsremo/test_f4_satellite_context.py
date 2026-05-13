"""Tests for V3-F4: satellite mission context builder.

Validates:
 1. OrbitalEventTimeline.all_events returns every registered event
 2. OrbitalEventTimeline.events_in_window filters by start/end overlap
 3. build_context computes mission_elapsed_s + design_life_pct_consumed
 4. build_context returns None fields when launch_epoch / design_life unset
 5. next_eclipse / next_contact / next_maneuver pick the earliest FUTURE event
 6. Currently-active events (e.g. eclipse in progress) are returned by
    next_* when no future event of that type is queued
 7. upcoming_events includes events overlapping the horizon window
 8. upcoming_events is sorted by start_epoch
 9. horizon_s <= 0 raises ValueError
10. EventSummary.starts_in_s is negative for events already in progress
11. SatelliteMissionContext.to_dict is JSON-serialisable round-trip clean
"""

from __future__ import annotations

import json

import pytest

from aria.dsremo.detection.orbital_events import (
    OrbitalEvent,
    OrbitalEventTimeline,
    OrbitalEventType,
)
from aria.dsremo.detection.satellite_context import (
    DEFAULT_HORIZON_S,
    EventSummary,
    SatelliteMissionContext,
    build_context,
)


SAT = "SAT-LEO-01"
NOW = 1_800_000_000.0  # 2027-01-15-ish UTC


def _timeline_with(events: list[OrbitalEvent]) -> OrbitalEventTimeline:
    t = OrbitalEventTimeline()
    for e in events:
        t.register(SAT, e)
    return t


class TestTimelineAccessors:

    def test_all_events_returns_every_registered_event(self):
        events = [
            OrbitalEvent(event_type=OrbitalEventType.ECLIPSE_ENTRY.value, start_epoch=NOW + 100, duration_s=30),
            OrbitalEvent(event_type=OrbitalEventType.MANEUVER.value, start_epoch=NOW + 500, duration_s=60),
        ]
        t = _timeline_with(events)
        assert len(t.all_events(SAT)) == 2

    def test_all_events_unknown_satellite_is_empty(self):
        t = OrbitalEventTimeline()
        assert t.all_events("NOPE") == []

    def test_all_events_returns_copy_not_reference(self):
        t = _timeline_with([
            OrbitalEvent(event_type="eclipse_entry", start_epoch=NOW, duration_s=1),
        ])
        got = t.all_events(SAT)
        got.clear()
        assert len(t.all_events(SAT)) == 1

    def test_events_in_window_includes_overlaps(self):
        t = _timeline_with([
            OrbitalEvent(event_type="eclipse_entry", start_epoch=NOW - 60, duration_s=120),  # overlaps past NOW
            OrbitalEvent(event_type="maneuver", start_epoch=NOW + 500, duration_s=60),
            OrbitalEvent(event_type="gs_handover", start_epoch=NOW + 10_000, duration_s=30),
        ])
        got = t.events_in_window(SAT, NOW - 30, NOW + 1000)
        assert len(got) == 2  # eclipse (overlap) + maneuver

    def test_events_in_window_reversed_bounds_swapped(self):
        t = _timeline_with([
            OrbitalEvent(event_type="eclipse_entry", start_epoch=NOW, duration_s=30),
        ])
        got = t.events_in_window(SAT, NOW + 1000, NOW - 1000)
        assert len(got) == 1


class TestBuildContext:

    def test_mission_elapsed_and_percent(self):
        launch = NOW - 60 * 86_400.0  # 60 days ago
        design = 1825 * 86_400.0      # 5-year mission
        ctx = build_context(SAT, launch, design, OrbitalEventTimeline(), NOW)
        assert ctx.mission_elapsed_s == pytest.approx(60 * 86_400.0)
        assert ctx.design_life_pct_consumed == pytest.approx(100 * 60 / 1825, rel=1e-6)

    def test_no_launch_epoch_leaves_nulls(self):
        ctx = build_context(SAT, None, None, OrbitalEventTimeline(), NOW)
        assert ctx.launch_epoch is None
        assert ctx.design_life_s is None
        assert ctx.mission_elapsed_s == 0.0
        assert ctx.design_life_pct_consumed is None

    def test_design_life_none_yields_null_pct(self):
        ctx = build_context(SAT, NOW - 100.0, None, OrbitalEventTimeline(), NOW)
        assert ctx.design_life_pct_consumed is None

    def test_design_life_zero_yields_null_pct(self):
        ctx = build_context(SAT, NOW - 100.0, 0.0, OrbitalEventTimeline(), NOW)
        assert ctx.design_life_pct_consumed is None

    def test_future_launch_clamps_elapsed_to_zero(self):
        ctx = build_context(SAT, NOW + 1000.0, 1000.0, OrbitalEventTimeline(), NOW)
        assert ctx.mission_elapsed_s == 0.0
        assert ctx.design_life_pct_consumed == 0.0

    def test_picks_earliest_future_eclipse(self):
        t = _timeline_with([
            OrbitalEvent(event_type="eclipse_entry", start_epoch=NOW + 500, duration_s=30, description="later"),
            OrbitalEvent(event_type="eclipse_entry", start_epoch=NOW + 100, duration_s=30, description="sooner"),
            OrbitalEvent(event_type="maneuver", start_epoch=NOW + 50, duration_s=60),  # not an eclipse
        ])
        ctx = build_context(SAT, None, None, t, NOW)
        assert ctx.next_eclipse is not None
        assert ctx.next_eclipse.description == "sooner"
        assert ctx.next_eclipse.starts_in_s == pytest.approx(100.0)

    def test_in_progress_eclipse_surfaces_when_no_future_queued(self):
        t = _timeline_with([
            OrbitalEvent(event_type="eclipse_entry", start_epoch=NOW - 50, duration_s=200),
        ])
        ctx = build_context(SAT, None, None, t, NOW)
        assert ctx.next_eclipse is not None
        assert ctx.next_eclipse.starts_in_s == pytest.approx(-50.0)

    def test_no_eclipse_returns_none(self):
        t = _timeline_with([
            OrbitalEvent(event_type="maneuver", start_epoch=NOW + 500, duration_s=60),
        ])
        ctx = build_context(SAT, None, None, t, NOW)
        assert ctx.next_eclipse is None

    def test_next_contact_picks_gs_handover(self):
        t = _timeline_with([
            OrbitalEvent(event_type=OrbitalEventType.GROUND_STATION_HANDOVER.value, start_epoch=NOW + 900, duration_s=600),
        ])
        ctx = build_context(SAT, None, None, t, NOW)
        assert ctx.next_contact is not None
        assert ctx.next_contact.event_type == "gs_handover"

    def test_next_maneuver(self):
        t = _timeline_with([
            OrbitalEvent(event_type="maneuver", start_epoch=NOW + 3600, duration_s=300, description="orbit raise"),
        ])
        ctx = build_context(SAT, None, None, t, NOW)
        assert ctx.next_maneuver is not None
        assert ctx.next_maneuver.description == "orbit raise"

    def test_upcoming_events_within_horizon_only(self):
        inside = OrbitalEvent(event_type="eclipse_entry", start_epoch=NOW + 1000, duration_s=30)
        outside = OrbitalEvent(event_type="eclipse_entry", start_epoch=NOW + 2 * DEFAULT_HORIZON_S, duration_s=30)
        t = _timeline_with([inside, outside])
        ctx = build_context(SAT, None, None, t, NOW, horizon_s=DEFAULT_HORIZON_S)
        assert len(ctx.upcoming_events) == 1
        assert ctx.upcoming_events[0].start_epoch == pytest.approx(inside.start_epoch)

    def test_upcoming_events_sorted_by_start(self):
        evs = [
            OrbitalEvent(event_type="eclipse_entry", start_epoch=NOW + 500, duration_s=30),
            OrbitalEvent(event_type="maneuver", start_epoch=NOW + 100, duration_s=30),
            OrbitalEvent(event_type="gs_handover", start_epoch=NOW + 300, duration_s=30),
        ]
        t = _timeline_with(evs)
        ctx = build_context(SAT, None, None, t, NOW)
        starts = [e.start_epoch for e in ctx.upcoming_events]
        assert starts == sorted(starts)

    def test_horizon_must_be_positive(self):
        with pytest.raises(ValueError):
            build_context(SAT, None, None, OrbitalEventTimeline(), NOW, horizon_s=0)
        with pytest.raises(ValueError):
            build_context(SAT, None, None, OrbitalEventTimeline(), NOW, horizon_s=-1.0)


class TestEventSummary:

    def test_starts_in_s_negative_when_event_in_progress(self):
        ev = OrbitalEvent(event_type="eclipse_entry", start_epoch=NOW - 30, duration_s=120)
        s = EventSummary.from_event(ev, NOW)
        assert s.starts_in_s == pytest.approx(-30.0)

    def test_starts_in_s_positive_when_event_future(self):
        ev = OrbitalEvent(event_type="eclipse_entry", start_epoch=NOW + 600, duration_s=30)
        s = EventSummary.from_event(ev, NOW)
        assert s.starts_in_s == pytest.approx(600.0)


class TestJSONSerialization:

    def test_to_dict_roundtrip_json_clean(self):
        launch = NOW - 100.0
        design = 1000.0
        t = _timeline_with([
            OrbitalEvent(event_type="eclipse_entry", start_epoch=NOW + 50, duration_s=30, description="e1"),
            OrbitalEvent(event_type=OrbitalEventType.GROUND_STATION_HANDOVER.value, start_epoch=NOW + 200, duration_s=600),
        ])
        ctx = build_context(SAT, launch, design, t, NOW)
        j = json.dumps(ctx.to_dict())
        back = json.loads(j)
        assert back["satellite_id"] == SAT
        assert back["next_eclipse"]["event_type"] == "eclipse_entry"
        assert back["next_contact"]["event_type"] == "gs_handover"
        assert back["next_maneuver"] is None
        assert len(back["upcoming_events"]) == 2

    def test_to_dict_shape_matches_dataclass_fields(self):
        ctx = build_context(SAT, None, None, OrbitalEventTimeline(), NOW)
        d = ctx.to_dict()
        expected_keys = {
            "satellite_id", "launch_epoch", "design_life_s",
            "mission_elapsed_s", "design_life_pct_consumed",
            "now_epoch", "horizon_s",
            "next_eclipse", "next_contact", "next_maneuver",
            "upcoming_events",
        }
        assert set(d.keys()) == expected_keys
        assert isinstance(ctx, SatelliteMissionContext)
