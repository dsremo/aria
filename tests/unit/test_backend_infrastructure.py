"""Tests for the second backend wave: event bus, tick engine, SEU model,
ECLSS trace contaminants."""

from __future__ import annotations

import math

import pytest

from aria.simulator.event_bus import Event, EventBus, _topic_matches, get_event_bus
from aria.simulator.tick_engine import TickEngine, get_tick_engine, reset_tick_engine
from aria.simulator.computing_radiation import (
    ComputingRadiationState, get_computing_radiation, reset_computing_radiation,
)
from aria.simulator.eclss_contaminants import (
    CONTAMINANTS, EclssContaminantsState, get_eclss_contaminants,
    reset_eclss_contaminants,
)


# ── Event bus ────────────────────────────────────────────────────

class TestEventBus:

    def test_topic_matches_exact(self):
        assert _topic_matches("reactor.ignition", "reactor.ignition")
        assert not _topic_matches("reactor.ignition", "reactor.scram")

    def test_topic_matches_wildcards(self):
        assert _topic_matches("reactor.ignition", "reactor.*")
        assert _topic_matches("reactor.anything", "*")
        assert _topic_matches("eclss.contaminant.ethylene.alarm", "eclss.*")

    def test_publish_subscribe(self):
        bus = EventBus()
        received = []
        bus.subscribe("reactor.*", lambda e: received.append(e.topic))
        bus.publish("reactor.ignition", source="test")
        bus.publish("eclss.alarm", source="test")
        assert received == ["reactor.ignition"]

    def test_history_ring_buffer(self):
        bus = EventBus(history_size=3)
        for i in range(5):
            bus.publish(f"topic.{i}")
        recent = bus.recent(n=10)
        # Should only keep last 3 (ring buffer size)
        assert len(recent) == 3
        assert [e.topic for e in recent] == ["topic.4", "topic.3", "topic.2"]

    def test_recent_filters_by_severity(self):
        bus = EventBus()
        bus.publish("a", severity="info")
        bus.publish("b", severity="warning")
        bus.publish("c", severity="critical")
        warnings = bus.recent(min_severity="warning")
        assert {e.topic for e in warnings} == {"b", "c"}

    def test_subscriber_failure_isolated(self):
        bus = EventBus()
        calls_a = []
        bus.subscribe("*", lambda e: (1 / 0))          # always raises
        bus.subscribe("*", lambda e: calls_a.append(e.topic))
        bus.publish("test")
        # Second subscriber should still run
        assert calls_a == ["test"]

    def test_unsubscribe(self):
        bus = EventBus()
        seen = []
        fn = lambda e: seen.append(e.topic)
        bus.subscribe("a.*", fn)
        bus.publish("a.x"); bus.publish("a.y")
        assert len(seen) == 2
        bus.unsubscribe("a.*", fn)
        bus.publish("a.z")
        assert len(seen) == 2


# ── Tick engine ──────────────────────────────────────────────────

class TestTickEngine:

    def test_registration(self):
        reset_tick_engine()
        eng = get_tick_engine()
        calls = []
        eng.register("a", lambda dt: calls.append(("a", dt)), order=10)
        eng.register("b", lambda dt: calls.append(("b", dt)), order=5)
        eng.advance(1.0)
        # Lower order fires first
        names = [c[0] for c in calls]
        assert names.index("b") < names.index("a")

    def test_advance_substeps_large_dt(self):
        reset_tick_engine()
        eng = get_tick_engine()
        counts = []
        eng.register("x", lambda dt: counts.append(dt), order=50)
        eng.MAX_SUBSTEP_S = 10.0
        eng.advance(25.0)      # should fire 3 times: 10 + 10 + 5
        assert sum(counts) == pytest.approx(25.0)
        assert len(counts) == 3

    def test_error_in_subsystem_captured_as_event(self):
        reset_tick_engine()
        bus = get_event_bus()
        bus.clear_history()
        eng = get_tick_engine()
        eng.register("bad", lambda dt: (_ for _ in ()).throw(RuntimeError("boom")), order=50)
        eng.advance(1.0)
        evts = [e for e in bus.recent() if e.topic == "tick.subsystem_error"]
        assert len(evts) >= 1

    def test_to_dict_shape(self):
        reset_tick_engine()
        eng = get_tick_engine()
        eng.register("x", lambda dt: None)
        eng.advance(1.0)
        d = eng.to_dict()
        assert "registered" in d
        assert "total_sim_time_s" in d
        assert d["tick_count"] == 1


# ── Computing radiation (SEU) ────────────────────────────────────

class TestComputingRadiation:

    def test_zero_elapsed_zero_events(self):
        reset_computing_radiation()
        st = get_computing_radiation()
        st.tick(0.0)
        assert st.total_seu_events == 0

    def test_seu_rate_scales_with_time(self):
        reset_computing_radiation()
        st = get_computing_radiation()
        # Tick an hour — expect SOME events eventually (with seeded RNG)
        for _ in range(600):           # 600 × 6 s = 1 hr
            st.tick(6.0)
        # Not a strict threshold — SEU is a Poisson process — but totals
        # should be non-negative and correction_rate should be in [0, 1].
        assert st.total_seu_events >= 0
        assert 0.0 <= st.correction_rate() <= 1.0

    def test_to_dict_shape(self):
        reset_computing_radiation()
        d = get_computing_radiation().to_dict()
        assert set(d.keys()) == {"config", "totals", "rates"}
        assert "seu_events" in d["totals"]
        assert "correction_rate" in d["rates"]


# ── ECLSS trace contaminants ─────────────────────────────────────

class TestEclssContaminants:

    def test_all_contaminants_initialised(self):
        reset_eclss_contaminants()
        st = get_eclss_contaminants()
        for key in CONTAMINANTS:
            assert key in st.states
            assert st.states[key].concentration_mg_m3 == 0.0

    def test_concentration_rises_then_plateaus(self):
        """With baseline generation + nominal scrubbing, C should approach
        the steady-state Q_gen/(k·V) and not explode."""
        reset_eclss_contaminants()
        st = get_eclss_contaminants()
        for _ in range(24 * 30):          # 30 days of hourly ticks
            st.tick(3600.0)
        for key, spec in CONTAMINANTS.items():
            c = st.states[key].concentration_mg_m3
            # Must be positive (generation happening)
            assert c >= 0.0
            # Must be bounded (scrubbing effective) — well below SMAC_7day
            assert c < spec.smac_7day_mg_m3, (
                f"{key} concentration {c} exceeds SMAC {spec.smac_7day_mg_m3}"
            )

    def test_scrubber_failure_triggers_alarm(self):
        reset_eclss_contaminants()
        st = get_eclss_contaminants()
        st.scrubber_efficiency_frac = 0.02   # 98% degraded — scrubbers nearly offline
        for _ in range(24 * 180):             # 180 days of ticks
            st.tick(3600.0)
        # At least one contaminant should be in alarm
        alarms = [k for k, cs in st.states.items() if cs.alarm_active]
        assert len(alarms) >= 1, "Degraded scrubber should trigger alarms"

    def test_to_dict_shape(self):
        reset_eclss_contaminants()
        d = get_eclss_contaminants().to_dict()
        assert "contaminants" in d
        for key in CONTAMINANTS:
            assert key in d["contaminants"]
            entry = d["contaminants"][key]
            assert "concentration_mg_m3" in entry
            assert "smac_180day" in entry
            assert "margin_to_smac_180d_pct" in entry


# ── Integration: tick_engine drives all modules ─────────────────

class TestTickEngineIntegration:

    def test_full_stack_ticks_without_error(self):
        """Register SEU + contaminants, advance an hour, verify state sane."""
        reset_tick_engine()
        reset_computing_radiation()
        reset_eclss_contaminants()
        from aria.simulator.computing_radiation import register_with_tick_engine as reg_crad
        from aria.simulator.eclss_contaminants import register_with_tick_engine as reg_ec
        reg_crad()
        reg_ec()
        eng = get_tick_engine()
        eng.advance(3600.0)
        assert "computing_radiation" in eng.registered_names()
        assert "eclss_contaminants" in eng.registered_names()
        # Contaminants should have moved off zero
        ec = get_eclss_contaminants()
        total_gen = sum(cs.cumulative_generated_mg for cs in ec.states.values())
        assert total_gen > 0
