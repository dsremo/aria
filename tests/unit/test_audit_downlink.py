"""R38 — Audit-root downlink + ground-attestation checker tests.

Acceptance §1.4:
  * Anchor every period_s carries head_hash + safe_mode_level.
  * Signature verifies; tampering invalidates it.
  * Ground checker: missing report ≥ 1.5 × period triggers contingency.
  * Replay / regressing head_seq is rejected.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from aria.security import audit, audit_downlink as dl


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_audit(tmp_path):
    audit.reset_for_test(log_path=False)
    yield
    audit.reset_for_test()
    dl.reset_for_test()


@pytest.fixture
def publisher(tmp_path):
    events: List[Tuple[str, Dict[str, Any]]] = []
    p = dl.AuditDownlinkPublisher(
        publish_fn=lambda t, p: events.append((t, p)),
        period_s=60.0,
        safe_mode_level_provider=lambda: "NOMINAL",
        signer_key_path=tmp_path / "anchor_key.pem",
    )
    return p, events


# ── Publisher emit ──────────────────────────────────────────────


class TestPublisher:
    def test_emit_includes_required_fields(self, publisher):
        p, events = publisher
        # Seed audit chain with one entry so head_hash is non-zero.
        audit.log_event("system", "test", "boot", "ok")
        pkt = p.emit_once()
        assert events and events[0][0] == dl.ANCHOR_TOPIC
        payload = events[0][1]
        for key in ("head_hash", "head_seq", "safe_mode_level",
                    "ts", "signature_hex", "pubkey_hex"):
            assert key in payload
        assert pkt.safe_mode_level == "NOMINAL"

    def test_signature_verifies(self, publisher):
        p, _ = publisher
        audit.log_event("system", "test", "boot", "ok")
        pkt = p.emit_once()
        assert dl.verify_anchor(pkt) is True

    def test_signature_invalid_on_field_tamper(self, publisher):
        p, _ = publisher
        audit.log_event("system", "test", "boot", "ok")
        pkt = p.emit_once()
        bad = dl.AnchorPacket(
            head_hash="ff" * 32,
            head_seq=pkt.head_seq,
            safe_mode_level=pkt.safe_mode_level,
            ts=pkt.ts,
            signature_hex=pkt.signature_hex,
            pubkey_hex=pkt.pubkey_hex,
        )
        assert dl.verify_anchor(bad) is False

    def test_emit_advances_with_chain(self, publisher):
        p, _ = publisher
        audit.log_event("a", "x", "y", "ok")
        pkt1 = p.emit_once()
        audit.log_event("b", "x", "z", "ok")
        pkt2 = p.emit_once()
        assert pkt2.head_seq > pkt1.head_seq
        assert pkt2.head_hash != pkt1.head_hash


# ── Ground checker ─────────────────────────────────────────────


class TestGroundChecker:
    def test_accepts_valid_anchor(self, publisher, tmp_path):
        p, _ = publisher
        audit.log_event("system", "test", "boot", "ok")
        pkt = p.emit_once()
        chk = dl.GroundAttestChecker(
            state_path=tmp_path / "ground.json",
            expected_pubkey_hex=p.pubkey_hex,
        )
        ok, reason = chk.consume_anchor(pkt.to_dict())
        assert ok, reason
        snap = chk.state_snapshot()
        assert snap.last_seen_seq == pkt.head_seq
        assert snap.accepted_count == 1
        assert snap.divergence_count == 0

    def test_rejects_wrong_pubkey(self, publisher, tmp_path):
        p, _ = publisher
        audit.log_event("system", "x", "y", "ok")
        pkt = p.emit_once()
        chk = dl.GroundAttestChecker(
            state_path=tmp_path / "g.json",
            expected_pubkey_hex="aa" * 32,   # wrong key
        )
        ok, reason = chk.consume_anchor(pkt.to_dict())
        assert ok is False
        assert "pubkey" in reason
        assert chk.state_snapshot().divergence_count == 1

    def test_rejects_tampered_signature(self, publisher, tmp_path):
        p, _ = publisher
        audit.log_event("system", "x", "y", "ok")
        pkt = p.emit_once()
        bad = dict(pkt.to_dict())
        bad["signature_hex"] = "00" * 64
        chk = dl.GroundAttestChecker(
            state_path=tmp_path / "g.json",
            expected_pubkey_hex=p.pubkey_hex,
        )
        ok, reason = chk.consume_anchor(bad)
        assert ok is False
        assert "signature" in reason

    def test_rejects_seq_regression(self, publisher, tmp_path):
        """An attacker resetting the chain must be detected."""
        p, _ = publisher
        audit.log_event("a", "x", "y", "ok")
        audit.log_event("b", "x", "y", "ok")
        pkt_high = p.emit_once()

        chk = dl.GroundAttestChecker(
            state_path=tmp_path / "g.json",
            expected_pubkey_hex=p.pubkey_hex,
        )
        ok, _ = chk.consume_anchor(pkt_high.to_dict())
        assert ok

        # Forge an anchor with an earlier seq but valid signature: the
        # easiest way to do this in test is to roll back the chain in
        # memory and re-emit.
        audit.reset_for_test(log_path=False)
        audit.log_event("a", "x", "y", "ok")  # seq 0 only
        pkt_low = p.emit_once()

        ok2, reason = chk.consume_anchor(pkt_low.to_dict())
        assert ok2 is False
        assert "regressed" in reason

    def test_overdue_after_1_5x_period(self, publisher, tmp_path):
        p, _ = publisher
        audit.log_event("system", "x", "y", "ok")
        pkt = p.emit_once()
        chk = dl.GroundAttestChecker(
            state_path=tmp_path / "g.json",
            expected_pubkey_hex=p.pubkey_hex,
            expected_period_s=10.0,
            overdue_factor=1.5,
        )
        chk.consume_anchor(pkt.to_dict(), now=1000.0)
        # 14 s elapsed — under 1.5 * 10 = 15 s threshold.
        assert chk.is_overdue(now=1014.0) is False
        # 16 s elapsed — over threshold → overdue.
        assert chk.is_overdue(now=1016.0) is True

    def test_state_persists_across_restart(self, publisher, tmp_path):
        p, _ = publisher
        audit.log_event("system", "x", "y", "ok")
        pkt = p.emit_once()
        sp = tmp_path / "g.json"
        chk1 = dl.GroundAttestChecker(
            state_path=sp,
            expected_pubkey_hex=p.pubkey_hex,
        )
        chk1.consume_anchor(pkt.to_dict())
        # Simulate ground-station restart.
        chk2 = dl.GroundAttestChecker(
            state_path=sp,
            expected_pubkey_hex=p.pubkey_hex,
            expected_period_s=10.0,
            overdue_factor=1.5,
        )
        snap = chk2.state_snapshot()
        assert snap.last_seen_seq == pkt.head_seq
        assert snap.last_head_hash == pkt.head_hash

    def test_mark_missing_increments(self, tmp_path):
        chk = dl.GroundAttestChecker(state_path=tmp_path / "g.json")
        assert chk.mark_missing() == 1
        assert chk.mark_missing() == 2

    def test_malformed_packet_rejected(self, tmp_path):
        chk = dl.GroundAttestChecker(state_path=tmp_path / "g.json")
        ok, reason = chk.consume_anchor({"head_hash": "xxx"})  # missing fields
        assert ok is False
        assert "malformed" in reason


# ── End-to-end ─────────────────────────────────────────────────


class TestEndToEnd:
    def test_publisher_to_checker_roundtrip(self, publisher, tmp_path):
        p, events = publisher
        chk = dl.GroundAttestChecker(
            state_path=tmp_path / "g.json",
            expected_pubkey_hex=p.pubkey_hex,
        )
        for i in range(3):
            audit.log_event("test", f"u{i}", "act", "ok")
            pkt = p.emit_once()
            ok, _ = chk.consume_anchor(pkt.to_dict(), now=1000.0 + i)
            assert ok
        snap = chk.state_snapshot()
        assert snap.accepted_count == 3
        assert snap.divergence_count == 0
