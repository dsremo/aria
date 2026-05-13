"""R35 — trace_id propagation tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from aria.security import audit
from aria.security import trace_context as tc
from aria.simulator import event_bus


# ── Basic context ────────────────────────────────────────────


class TestTraceContext:
    def test_new_trace_id_format(self):
        tid = tc.new_trace_id()
        assert tid.startswith("trc_")
        assert len(tid) == 4 + 16   # prefix + 16 hex chars

    def test_current_mints_on_first_read(self):
        # Force-clear any prior context.
        token = tc.set_trace_id("")
        try:
            a = tc.current_trace_id()
            b = tc.current_trace_id()
            # Same in same flow (after first mint).
            assert a == b
            assert a.startswith("trc_")
        finally:
            tc.reset_trace_id(token)

    def test_current_no_mint_returns_empty(self):
        token = tc.set_trace_id("")
        try:
            assert tc.current_trace_id(mint_if_absent=False) == ""
        finally:
            tc.reset_trace_id(token)

    def test_trace_scope_pushes_and_restores(self):
        token = tc.set_trace_id("")
        try:
            assert tc.current_trace_id(mint_if_absent=False) == ""
            with tc.trace_scope() as tid:
                assert tc.current_trace_id(mint_if_absent=False) == tid
                assert tid.startswith("trc_")
            # Restored after scope.
            assert tc.current_trace_id(mint_if_absent=False) == ""
        finally:
            tc.reset_trace_id(token)

    def test_trace_scope_with_explicit(self):
        with tc.trace_scope(trace_id="trc_imported_from_upstream") as tid:
            assert tid == "trc_imported_from_upstream"
            assert tc.current_trace_id(mint_if_absent=False) == "trc_imported_from_upstream"


# ── Audit log auto-fill ──────────────────────────────────────


class TestAuditAutoFill:
    def test_log_event_picks_up_active_trace_id(self):
        audit.reset_for_test()
        with tc.trace_scope() as tid:
            entry = audit.log_event("auth", "captain.tau", "login",
                                    "accepted", {"why": "test"})
        assert entry.trace_id == tid

    def test_explicit_trace_id_wins(self):
        audit.reset_for_test()
        with tc.trace_scope():
            entry = audit.log_event(
                "auth", "captain.tau", "login", "accepted",
                trace_id="trc_forced",
            )
        assert entry.trace_id == "trc_forced"

    def test_query_by_trace_id(self):
        audit.reset_for_test()
        with tc.trace_scope() as a:
            audit.log_event("auth", "u1", "login", "ok")
            audit.log_event("authz", "u1", "do_thing", "granted")
        with tc.trace_scope() as b:
            audit.log_event("auth", "u2", "login", "ok")
        log = audit.get_audit_log()
        a_entries = log.get_entries(trace_id=a)
        b_entries = log.get_entries(trace_id=b)
        assert len(a_entries) == 2
        assert len(b_entries) == 1
        assert all(e.trace_id == a for e in a_entries)


# ── Trace_id is part of the hash chain ──────────────────────


class TestChainHash:
    def test_tampering_with_trace_id_breaks_chain(self):
        log = audit.AuditLog(log_path=False)  # type: ignore[arg-type]
        with tc.trace_scope():
            log.log("auth", "u", "x", "ok")
            log.log("auth", "u", "y", "ok")
        # Tamper just the trace_id.
        log._entries[1].trace_id = "trc_evil_replacement"
        ok, seq = log.verify_chain()
        assert not ok


# ── Bus event propagation ───────────────────────────────────


class TestBusPropagation:
    def test_publish_inherits_active_trace_id(self):
        bus = event_bus.EventBus(history_size=10)
        with tc.trace_scope() as tid:
            event = bus.publish("aria.test", payload={})
        assert event.trace_id == tid

    def test_explicit_trace_id_on_publish(self):
        bus = event_bus.EventBus(history_size=10)
        event = bus.publish("aria.test", trace_id="trc_xyz")
        assert event.trace_id == "trc_xyz"

    def test_subscriber_receives_event_with_trace(self):
        bus = event_bus.EventBus(history_size=10)
        received_tids: list = []

        def handler(ev):
            received_tids.append(ev.trace_id)
            # The ContextVar should also be set INSIDE the handler.
            received_tids.append(tc.current_trace_id(mint_if_absent=False))

        bus.subscribe("aria.test", handler)
        with tc.trace_scope() as tid:
            bus.publish("aria.test", payload={})
        assert received_tids == [tid, tid]

    def test_handler_publish_inherits_trace(self):
        """Subscriber publishes a follow-on event — the new event must
        carry the same trace_id (transitive propagation through the
        whole bus fanout)."""
        bus = event_bus.EventBus(history_size=10)
        captured: list = []

        def handler(ev):
            inner = bus.publish("aria.followup", payload={})
            captured.append(inner.trace_id)

        bus.subscribe("aria.test", handler)
        with tc.trace_scope() as tid:
            bus.publish("aria.test")
        assert captured == [tid]


# ── Mirror picks up the trace_id ────────────────────────────


class TestMirrorTracePropagation:
    def test_mirror_records_trace_id(self):
        from aria.security import audit_bus_mirror as mirror
        mirror.reset_for_test()
        audit.reset_for_test()
        bus = event_bus.EventBus()
        mirror.start_audit_bus_mirror(bus=bus)
        with tc.trace_scope() as tid:
            bus.publish("aria.security.test", severity="critical")
        ents = audit.get_audit_log().get_entries(trace_id=tid)
        assert len(ents) >= 1
        assert ents[0].trace_id == tid
