"""Tests for backend wave 7: crew schedule, repair queue, narrative log."""

from __future__ import annotations

import pytest

from aria.simulator.crew_schedule import (
    CrewScheduleState, get_crew_schedule, reset_crew_schedule,
)
from aria.simulator.narrative_log import (
    NarrativeLogState, _render, get_narrative_log, reset_narrative_log,
)
from aria.simulator.repair_queue import (
    RepairQueueState, TaskStatus, get_repair_queue, reset_repair_queue,
)


# ── Crew schedule ───────────────────────────────────────────────

class TestCrewSchedule:

    def test_default_three_bands(self):
        reset_crew_schedule()
        cs = get_crew_schedule()
        assert set(cs.bands.keys()) == {"A", "B", "C"}
        assert sum(b.crew_count for b in cs.bands.values()) == cs.crew_size

    def test_band_a_on_duty_at_dawn(self):
        reset_crew_schedule()
        cs = get_crew_schedule()
        # Band A starts at hour 0
        assert cs.bands["A"].is_on_duty(local_hr=2.0)
        assert not cs.bands["A"].is_on_duty(local_hr=10.0)

    def test_band_b_on_duty_morning(self):
        reset_crew_schedule()
        cs = get_crew_schedule()
        assert cs.bands["B"].is_on_duty(local_hr=10.0)

    def test_tick_advances_clock(self):
        reset_crew_schedule()
        cs = get_crew_schedule()
        cs.tick(3600.0)        # 1 hour
        assert cs.local_clock_hr == pytest.approx(1.0, abs=1e-3)

    def test_overtime_increases_sleep_debt(self):
        reset_crew_schedule()
        cs = get_crew_schedule()
        cs.force_overtime("A", 5.0)
        assert cs.bands["A"].sleep_debt_hr == pytest.approx(5.0, abs=1e-3)

    def test_consume_repair_hours_caps_at_available(self):
        reset_crew_schedule()
        cs = get_crew_schedule()
        cs.tick(3600.0)
        granted = cs.consume_repair_hours(1e6)
        assert granted <= cs.crew_hours_per_day_available
        assert granted >= 0


# ── Repair queue ────────────────────────────────────────────────

class TestRepairQueue:

    def test_initial_feedstock_present(self):
        reset_repair_queue()
        rq = get_repair_queue()
        assert rq.feedstock_kg > 0

    def test_enqueue_custom_returns_task(self):
        reset_repair_queue()
        t = get_repair_queue().enqueue_custom("test", "test patch", 5.0, 2.0, 30)
        assert t.task_id.startswith("task_")
        assert t.status == TaskStatus.PENDING

    def test_cancel_pending_succeeds(self):
        reset_repair_queue()
        rq = get_repair_queue()
        t = rq.enqueue_custom("test", "test patch", 5.0, 2.0)
        assert rq.cancel(t.task_id)
        assert t.status == TaskStatus.FAILED

    def test_refill_feedstock_caps_at_capacity(self):
        reset_repair_queue()
        rq = get_repair_queue()
        rq.feedstock_kg = rq.feedstock_capacity_kg - 100
        added = rq.refill_feedstock(1e6)
        assert added == pytest.approx(100, abs=0.1)
        assert rq.feedstock_kg == rq.feedstock_capacity_kg

    def test_auto_pull_from_hull_creates_tasks(self):
        from aria.simulator.hull_damage import (
            get_hull_damage, reset_hull_damage,
        )
        from aria.simulator.crew_schedule import (
            get_crew_schedule, reset_crew_schedule,
        )
        reset_repair_queue()
        reset_hull_damage()
        reset_crew_schedule()
        # Give crew schedule a tick so it has hours to consume
        cs = get_crew_schedule()
        cs.tick(3600.0)
        # Generate hull damage
        get_hull_damage().record_impact("hull_zone_4", 10_000.0)
        get_hull_damage().record_impact("hull_zone_4", 10_000.0)
        # Repair queue tick should auto-create matching tasks
        get_repair_queue().tick(60.0)
        rq = get_repair_queue()
        assert any(t.source == "hull_zone_4" for t in rq.queue)

    def test_to_dict_shape(self):
        reset_repair_queue()
        d = get_repair_queue().to_dict()
        for k in ("feedstock_kg", "feedstock_pct", "stats", "tasks"):
            assert k in d


# ── Narrative log ──────────────────────────────────────────────

class TestNarrativeLog:

    def test_default_subscribed_after_get(self):
        reset_narrative_log()
        nl = get_narrative_log()
        assert nl.subscribed

    def test_render_known_topic(self):
        icon, text = _render("trajectory.arrival", {"target": "Sirius A"}, "info")
        assert icon == "✓"
        assert "Sirius A" in text

    def test_render_unknown_topic_fallback(self):
        icon, text = _render("never.heard.of.this.topic",
                             {"foo": "bar"}, "info")
        assert "never.heard" in text

    def test_add_note_appears(self):
        reset_narrative_log()
        nl = get_narrative_log()
        nl.add_note("operator left bridge")
        assert any("operator left bridge" in e.text for e in nl.entries)

    def test_to_text_shape(self):
        reset_narrative_log()
        nl = get_narrative_log()
        nl.add_note("test entry")
        txt = nl.to_text(limit=10)
        assert "test entry" in txt
        assert "Year" in txt

    def test_clear_empties(self):
        reset_narrative_log()
        nl = get_narrative_log()
        nl.add_note("ephemeral")
        nl.clear()
        assert len(nl.entries) == 0

    def test_suppressed_topics_skipped(self):
        from aria.simulator.event_bus import get_event_bus
        reset_narrative_log()
        nl = get_narrative_log()
        before = len(nl.entries)
        get_event_bus().publish("tick.advanced", payload={"dt_s": 1, "wall_ms": 0.5, "registered": 0})
        # Suppressed → no narrative entry
        assert len(nl.entries) == before

    def test_unsuppressed_topic_recorded(self):
        from aria.simulator.event_bus import get_event_bus
        reset_narrative_log()
        nl = get_narrative_log()
        get_event_bus().publish("trajectory.arrival",
                                payload={"target": "Sirius A"},
                                source="test")
        assert any("Sirius A" in e.text for e in nl.entries)
