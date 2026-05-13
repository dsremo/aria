"""R34 Phase 1 — audit persistence + boot verify + bus mirror tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from aria.security import audit
from aria.security import audit_bus_mirror as mirror


# ── Persistence ────────────────────────────────────────────────


class TestPersistence:
    def test_writes_to_disk(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        log = audit.AuditLog(log_path)
        log.log("auth", "captain.tau", "login", "accepted",
                {"ip": "127.0.0.1"})
        log.log("authz", "captain.tau", "kill_switch.reset", "granted",
                {"role": "captain"})
        # File contains both entries.
        lines = log_path.read_text().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["event_type"] == "auth"
        assert first["seq"] == 0
        assert first["hash_value"]

    def test_load_resumes_seq_and_chain(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        log = audit.AuditLog(path)
        log.log("auth", "alice", "login", "accepted")
        log.log("auth", "bob", "login", "accepted")
        head_before = log.head_hash()
        # New process: re-instantiate, file is read.
        log2 = audit.AuditLog(path)
        assert len(log2) == 2
        assert log2.head_hash() == head_before
        # Next entry continues the chain.
        log2.log("auth", "charlie", "login", "accepted")
        assert log2.head_seq() == 2
        # The chain still verifies after the resume.
        ok, seq = log2.verify_chain()
        assert ok and seq is None


# ── Tamper detection ───────────────────────────────────────────


class TestTamper:
    def test_modified_entry_detected(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        log = audit.AuditLog(path)
        for who in ("a", "b", "c"):
            log.log("auth", who, "login", "accepted")
        # Tamper: rewrite the second line's identity but keep its hash.
        lines = path.read_text().splitlines()
        d = json.loads(lines[1])
        d["identity"] = "evil"
        lines[1] = json.dumps(d)
        path.write_text("\n".join(lines) + "\n")
        # Reload — verify_chain detects it.
        log2 = audit.AuditLog(path)
        ok, seq = log2.verify_chain()
        assert not ok
        assert seq == 1   # the tampered entry's seq

    def test_deleted_entry_detected(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        log = audit.AuditLog(path)
        for who in ("a", "b", "c"):
            log.log("auth", who, "login", "accepted")
        lines = path.read_text().splitlines()
        # Drop the middle entry — chain should break at "c".
        lines.pop(1)
        path.write_text("\n".join(lines) + "\n")
        log2 = audit.AuditLog(path)
        ok, seq = log2.verify_chain()
        assert not ok


# ── Boot verify + alarm publish ────────────────────────────────


class TestVerifyAtBoot:
    def test_clean_chain_returns_true(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        log = audit.AuditLog(path)
        log.log("auth", "alice", "login", "accepted")
        # New process: verify_at_boot.
        published = []
        ok = audit.verify_at_boot(
            log_path=path,
            publish_fn=lambda topic, payload: published.append((topic, payload)),
        )
        assert ok
        assert published == []

    def test_break_publishes_alarm(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        log = audit.AuditLog(path)
        for who in ("a", "b", "c"):
            log.log("auth", who, "login", "accepted")
        # Tamper.
        lines = path.read_text().splitlines()
        d = json.loads(lines[1])
        d["identity"] = "evil"
        lines[1] = json.dumps(d)
        path.write_text("\n".join(lines) + "\n")

        published = []
        ok = audit.verify_at_boot(
            log_path=path,
            publish_fn=lambda topic, payload: published.append((topic, payload)),
        )
        assert not ok
        assert published, "expected an alarm to be published"
        topic, payload = published[0]
        assert topic == "aria.security.audit_chain_break"
        assert payload["first_break_seq"] == 1


# ── Anchor publishing ──────────────────────────────────────────


class TestAnchor:
    def test_publishes_every_n(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        topics = []
        log = audit.AuditLog(
            path, anchor_every_n=3,
            anchor_publisher=lambda topic, payload: topics.append((topic, payload)),
        )
        for i in range(7):
            log.log("auth", f"u{i}", "login", "accepted")
        # 7 entries with anchor every 3 → fired at 3 and 6 → 2 anchors.
        anchors = [(t, p) for t, p in topics
                   if t == "aria.security.audit.anchor"]
        assert len(anchors) == 2
        assert anchors[0][1]["head_seq"] == 2     # 0,1,2 → 3rd entry seq=2
        assert anchors[1][1]["head_seq"] == 5


# ── Correlation / incident threading ───────────────────────────


class TestIncidentThreading:
    def test_filter_by_incident_id(self, tmp_path):
        log = audit.AuditLog(tmp_path / "audit.jsonl")
        log.log("auth", "captain.tau", "login", "accepted",
                incident_id="inc_a")
        log.log("authz", "captain.tau", "kill_switch.assert", "granted",
                incident_id="inc_a")
        log.log("authz", "crew.alpha", "approval.sign", "granted",
                incident_id="inc_b")
        a = log.get_entries(incident_id="inc_a")
        b = log.get_entries(incident_id="inc_b")
        assert len(a) == 2
        assert len(b) == 1
        assert all(e.incident_id == "inc_a" for e in a)

    def test_min_severity_filter(self, tmp_path):
        log = audit.AuditLog(tmp_path / "audit.jsonl")
        log.log("auth", "x", "y", "ok", severity="info")
        log.log("auth", "x", "y", "ok", severity="warning")
        log.log("auth", "x", "y", "ok", severity="critical")
        warn_plus = log.get_entries(min_severity="warning")
        assert len(warn_plus) == 2
        crit_plus = log.get_entries(min_severity="critical")
        assert len(crit_plus) == 1


# ── Bus mirror ──────────────────────────────────────────────────


class _FakeEvent:
    def __init__(self, topic, severity="info", payload=None, source="test"):
        self.topic = topic
        self.severity = severity
        self.payload = payload or {}
        self.source = source


class _FakeBus:
    def __init__(self):
        self._subs = []

    def subscribe(self, pattern, fn):
        self._subs.append((pattern, fn))

    def publish(self, event):
        for pat, fn in self._subs:
            if pat == "*" or event.topic.startswith(pat.rstrip("*")):
                fn(event)


class TestBusMirror:
    def setup_method(self):
        mirror.reset_for_test()
        # New audit log per-test so we can read fresh entries.
        audit.reset_for_test()

    def test_warning_event_is_logged(self):
        bus = _FakeBus()
        m = mirror.start_audit_bus_mirror(bus=bus)
        bus.publish(_FakeEvent("aria.power.shed_load", severity="warning",
                               payload={"why": "test"}))
        log = audit.get_audit_log()
        entries = log.get_entries()
        assert len(entries) == 1
        assert entries[0].action == "aria.power.shed_load"
        assert entries[0].severity == "warning"
        assert entries[0].source == "test"

    def test_info_event_is_skipped(self):
        bus = _FakeBus()
        mirror.start_audit_bus_mirror(bus=bus)
        bus.publish(_FakeEvent("aria.power.tick", severity="info",
                               payload={}))
        assert len(audit.get_audit_log().get_entries()) == 0

    def test_security_topic_always_logged_even_at_info(self):
        bus = _FakeBus()
        mirror.start_audit_bus_mirror(bus=bus)
        bus.publish(_FakeEvent("aria.security.session_created",
                               severity="info", payload={"who": "x"}))
        # Security prefix → always audit.
        assert len(audit.get_audit_log().get_entries()) == 1

    def test_tamper_substring_always_logged(self):
        bus = _FakeBus()
        mirror.start_audit_bus_mirror(bus=bus)
        bus.publish(_FakeEvent("aria.eclss.scrubber.tamper_detected",
                               severity="info"))
        assert len(audit.get_audit_log().get_entries()) == 1

    def test_incident_id_propagates(self):
        bus = _FakeBus()
        mirror.start_audit_bus_mirror(bus=bus)
        bus.publish(_FakeEvent("aria.safety.alarm",
                               severity="critical",
                               payload={"incident_id": "inc_xyz",
                                        "detail": "ok"}))
        ents = audit.get_audit_log().get_entries(incident_id="inc_xyz")
        assert len(ents) == 1
        # The incident_id is consumed from payload (not duplicated in details).
        assert "incident_id" not in ents[0].details
        assert ents[0].details["detail"] == "ok"

    def test_idempotent_start(self):
        bus = _FakeBus()
        mirror.start_audit_bus_mirror(bus=bus)
        mirror.start_audit_bus_mirror(bus=bus)   # second call is a no-op
        bus.publish(_FakeEvent("aria.security.x", severity="critical"))
        # Each event should produce exactly ONE audit entry (not two).
        assert len(audit.get_audit_log().get_entries()) == 1
