"""R41 — remaining Tier-1 anti-tamper sprint tests.

Covers acceptance §1.5–1.8:
  * Per-action FIDO2 challenge bound to args-hash; replay rejected.
  * Bus anomaly monitor flags rate spikes + novel pairs + bursts.
  * Robotics: capability tokens verify, ISO/TS 15066 force checks,
    E-stop watchdog fires within budget, tool-ID attestation hooks.
  * Re-grounding ritual produces signed affirmation that joins audit.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from aria.security import per_action_auth as paa
from aria.safety import bus_anomaly as ba
from aria.safety import robotics as rb
from aria.safety import re_grounding as rg


# ── Per-action FIDO2 ───────────────────────────────────────────


def _make_signing_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    return Ed25519PrivateKey.generate()


class TestPerActionChallenge:
    def test_issue_then_verify_ok(self):
        priv = _make_signing_key()
        pub_hex = priv.public_key().public_bytes_raw().hex()
        c = paa.PerActionChallenge()
        ch = c.issue("propulsion_burn", "abc123", "captain.tau")
        sig = priv.sign(ch.payload).hex()
        result = c.verify(
            challenge_id=ch.challenge_id, action="propulsion_burn",
            args_hash="abc123", principal_id="captain.tau",
            signature_hex=sig, pubkey_hex=pub_hex,
        )
        assert result.ok, result.reason

    def test_replay_rejected(self):
        priv = _make_signing_key()
        pub_hex = priv.public_key().public_bytes_raw().hex()
        c = paa.PerActionChallenge()
        ch = c.issue("vent_tank", "xyz", "captain.tau")
        sig = priv.sign(ch.payload).hex()
        # First use ok.
        assert c.verify(
            ch.challenge_id, "vent_tank", "xyz", "captain.tau",
            sig, pub_hex,
        ).ok
        # Second use rejected.
        r = c.verify(
            ch.challenge_id, "vent_tank", "xyz", "captain.tau",
            sig, pub_hex,
        )
        assert r.ok is False
        assert "replay" in r.reason

    def test_args_substitution_rejected(self):
        priv = _make_signing_key()
        pub_hex = priv.public_key().public_bytes_raw().hex()
        c = paa.PerActionChallenge()
        ch = c.issue("vent_tank", "args_A", "captain.tau")
        sig = priv.sign(ch.payload).hex()
        # Caller tries to use the signed challenge with different args.
        r = c.verify(
            ch.challenge_id, "vent_tank", "args_B", "captain.tau",
            sig, pub_hex,
        )
        assert r.ok is False
        assert "args" in r.reason

    def test_action_substitution_rejected(self):
        priv = _make_signing_key()
        pub_hex = priv.public_key().public_bytes_raw().hex()
        c = paa.PerActionChallenge()
        ch = c.issue("vent_tank", "x", "captain.tau")
        sig = priv.sign(ch.payload).hex()
        r = c.verify(
            ch.challenge_id, "fire_thruster", "x", "captain.tau",
            sig, pub_hex,
        )
        assert r.ok is False
        assert "action" in r.reason

    def test_window_expiry(self):
        priv = _make_signing_key()
        pub_hex = priv.public_key().public_bytes_raw().hex()
        c = paa.PerActionChallenge(window_s=0.05)
        ch = c.issue("vent_tank", "x", "captain.tau")
        sig = priv.sign(ch.payload).hex()
        time.sleep(0.10)
        r = c.verify(
            ch.challenge_id, "vent_tank", "x", "captain.tau",
            sig, pub_hex,
        )
        assert r.ok is False
        assert "expired" in r.reason

    def test_bad_signature_rejected(self):
        priv = _make_signing_key()
        pub_hex = priv.public_key().public_bytes_raw().hex()
        c = paa.PerActionChallenge()
        ch = c.issue("vent_tank", "x", "captain.tau")
        # Sign something else.
        bad_sig = priv.sign(b"not the payload").hex()
        r = c.verify(
            ch.challenge_id, "vent_tank", "x", "captain.tau",
            bad_sig, pub_hex,
        )
        assert r.ok is False

    def test_args_hash_canonical(self):
        h1 = paa.args_hash_for({"a": 1, "b": 2})
        h2 = paa.args_hash_for({"b": 2, "a": 1})  # different order
        assert h1 == h2


# ── Bus anomaly ────────────────────────────────────────────────


class TestBusAnomaly:
    def test_first_event_is_novel(self):
        events: List[Tuple[str, Dict[str, Any]]] = []
        m = ba.BusAnomalyMonitor(
            publish_fn=lambda t, p: events.append((t, p)),
        )
        r = m.observe("agent_x", "topic_y")
        assert r is not None
        assert r.kind == "novel_pair"
        assert events and events[0][0] == "aria.security.bus_anomaly"

    def test_steady_state_no_anomaly(self):
        m = ba.BusAnomalyMonitor()
        m.observe("a", "t")
        # Subsequent low-rate events are not anomalous.
        for _ in range(5):
            time.sleep(0.001)
            r = m.observe("a", "t")
        # Last call should be PASS (None), not a spike.
        assert r is None

    def test_rate_spike_flagged(self):
        m = ba.BusAnomalyMonitor(
            window_s=10.0, rate_spike_factor=4.0,
            min_baseline_hits=10,
        )
        # Build a low-rate baseline at t=0..30 (one event every 5 s).
        for k in range(7):
            m.observe("agent_a", "topic_b", ts=float(k * 5))
        # Then burst at t=40 — 12 events in 1 s.
        burst_report = None
        for k in range(12):
            r = m.observe("agent_a", "topic_b", ts=40.0 + k * 0.05)
            if r and r.kind == "rate_spike":
                burst_report = r
        assert burst_report is not None
        assert burst_report.ratio >= 4.0

    def test_cross_agent_burst(self):
        events: List[Tuple[str, Dict[str, Any]]] = []
        m = ba.BusAnomalyMonitor(
            publish_fn=lambda t, p: events.append((t, p)),
            burst_window_s=1.0, burst_min_agents=3,
        )
        # Three distinct agents hitting the same topic in <1 s.
        m.observe("agent1", "common_topic", ts=100.0)
        m.observe("agent2", "common_topic", ts=100.2)
        r = m.observe("agent3", "common_topic", ts=100.4)
        assert r is not None
        assert r.kind == "cross_agent_burst"
        assert r.ratio >= 3

    def test_lru_cap(self):
        m = ba.BusAnomalyMonitor(max_pairs=10)
        for i in range(20):
            m.observe(f"agent_{i}", "topic", ts=float(i))
        assert m.stats()["tracked_pairs"] <= 10


# ── Robotics ──────────────────────────────────────────────────


class TestCapabilityToken:
    @pytest.fixture
    def issuer(self, tmp_path):
        return rb.CapabilityTokenIssuer(key_path=str(tmp_path / "k.pem"))

    def test_issue_then_verify(self, issuer):
        env = rb.WorkspaceEnvelope(
            x_min_m=-1, x_max_m=1, y_min_m=-1, y_max_m=1,
            z_min_m=0, z_max_m=2,
        )
        tok = issuer.issue(
            robot_id="r1", motion_class=rb.MotionClass.REACH,
            envelope=env, issuer_principal_id="captain.tau",
            ttl_s=10.0,
        )
        ok, reason = rb.verify_capability_token(tok, issuer.pubkey_hex)
        assert ok, reason

    def test_expired_token_rejected(self, issuer):
        env = rb.WorkspaceEnvelope(0, 1, 0, 1, 0, 1)
        tok = issuer.issue("r1", rb.MotionClass.GRIP, env,
                           "captain.tau", ttl_s=0.05)
        time.sleep(0.10)
        ok, reason = rb.verify_capability_token(tok, issuer.pubkey_hex)
        assert ok is False
        assert "expired" in reason

    def test_tampered_token_rejected(self, issuer):
        env = rb.WorkspaceEnvelope(0, 1, 0, 1, 0, 1)
        tok = issuer.issue("r1", rb.MotionClass.LIFT, env,
                           "captain.tau", ttl_s=10.0)
        # Replace robot_id but keep the original signature.
        bad = rb.CapabilityToken(
            token_id=tok.token_id, robot_id="r2_attacker",
            motion_class=tok.motion_class, envelope=tok.envelope,
            issued_at=tok.issued_at, expires_at=tok.expires_at,
            issuer_principal_id=tok.issuer_principal_id,
            signature_hex=tok.signature_hex,
        )
        ok, reason = rb.verify_capability_token(bad, issuer.pubkey_hex)
        assert ok is False

    def test_wrong_pubkey_rejected(self, issuer, tmp_path):
        env = rb.WorkspaceEnvelope(0, 1, 0, 1, 0, 1)
        tok = issuer.issue("r1", rb.MotionClass.NAV, env,
                           "captain.tau", ttl_s=10.0)
        other = rb.CapabilityTokenIssuer(key_path=str(tmp_path / "other.pem"))
        ok, reason = rb.verify_capability_token(tok, other.pubkey_hex)
        assert ok is False


class TestForceLimit:
    def test_face_limit_quasi_static(self):
        r = rb.check_force_limit("face", 50.0)
        assert r.ok
        # 65 N is the table value.

    def test_face_limit_exceeded(self):
        r = rb.check_force_limit("face", 80.0)
        assert r.ok is False
        assert "limit" in r.reason

    def test_transient_doubles_limit(self):
        # 130 N exceeds 65 N quasi-static for face but not 130 N transient.
        r1 = rb.check_force_limit("face", 100.0, transient=False)
        r2 = rb.check_force_limit("face", 100.0, transient=True)
        assert r1.ok is False
        assert r2.ok is True

    def test_unknown_region_rejected(self):
        r = rb.check_force_limit("eyeball", 1.0)
        assert r.ok is False


class TestEStopWatchdog:
    def test_fires_within_budget(self):
        events: List[Tuple[str, Dict[str, Any]]] = []
        wd = rb.EStopWatchdog(
            publish_fn=lambda t, p: events.append((t, p)),
            grace_ms=50.0, robot_id="rA",
        )
        wd.heartbeat(ts=0.0)
        # Far past grace.
        fired = wd.check(now=10.0)
        assert fired is True
        assert events and events[0][0] == "aria.actuator.estop"

    def test_does_not_fire_before_grace(self):
        wd = rb.EStopWatchdog(
            publish_fn=lambda t, p: None, grace_ms=200.0,
        )
        wd.heartbeat(ts=0.0)
        fired = wd.check(now=0.05)
        assert fired is False

    def test_idempotent_fire(self):
        events: List[Tuple[str, Dict[str, Any]]] = []
        wd = rb.EStopWatchdog(
            publish_fn=lambda t, p: events.append((t, p)),
            grace_ms=10.0,
        )
        wd.heartbeat(ts=0.0)
        wd.check(now=10.0)
        wd.check(now=11.0)
        wd.check(now=12.0)
        assert len(events) == 1   # only first fire publishes

    def test_heartbeat_rearms(self):
        events: List[Tuple[str, Dict[str, Any]]] = []
        wd = rb.EStopWatchdog(
            publish_fn=lambda t, p: events.append((t, p)),
            grace_ms=10.0,
        )
        wd.heartbeat(ts=0.0)
        wd.check(now=10.0)
        wd.heartbeat(ts=11.0)
        wd.check(now=20.0)
        assert len(events) == 2

    def test_trip_now_fires_immediately(self):
        events: List[Tuple[str, Dict[str, Any]]] = []
        wd = rb.EStopWatchdog(
            publish_fn=lambda t, p: events.append((t, p)),
        )
        wd.trip_now("button_pressed")
        assert events and events[0][0] == "aria.actuator.estop"
        assert "button_pressed" in events[0][1]["reason"]


class TestToolIDAttestation:
    def test_signed_change_accepted(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
        priv = Ed25519PrivateKey.generate()
        pub_hex = priv.public_key().public_bytes_raw().hex()
        c = paa.PerActionChallenge()
        tool = rb.ToolID(tool_id="DRILL-7", is_dangerous=True, name="ø10 drill")
        ah = rb.tool_id_args_hash(tool)
        ch = c.issue("robot_tool_change", ah, "captain.tau")
        sig = priv.sign(ch.payload).hex()
        ok, reason = rb.require_tool_id_signature(
            challenge_module=c, tool=tool,
            principal_id="captain.tau",
            signature_hex=sig, pubkey_hex=pub_hex,
            challenge_id=ch.challenge_id,
        )
        assert ok, reason

    def test_substituted_tool_rejected(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
        priv = Ed25519PrivateKey.generate()
        pub_hex = priv.public_key().public_bytes_raw().hex()
        c = paa.PerActionChallenge()
        tool_signed = rb.ToolID("CUTTER-1", True, "shears")
        ah = rb.tool_id_args_hash(tool_signed)
        ch = c.issue("robot_tool_change", ah, "captain.tau")
        sig = priv.sign(ch.payload).hex()
        # Operator hands in a different tool ID.
        tool_actual = rb.ToolID("WELDER-9", True, "TIG welder")
        ok, reason = rb.require_tool_id_signature(
            challenge_module=c, tool=tool_actual,
            principal_id="captain.tau",
            signature_hex=sig, pubkey_hex=pub_hex,
            challenge_id=ch.challenge_id,
        )
        assert ok is False


# ── Re-grounding ──────────────────────────────────────────────


class TestRegrounding:
    def _stub_audit(self):
        captured: List[Dict[str, Any]] = []
        def cb(d):
            captured.append(d)
        return captured, cb

    def _stub_sealed(self):
        c_text = "constitution body"
        sp_text = "system prompt body"
        c_hash = hashlib.sha256(c_text.encode()).hexdigest()
        sp_hash = hashlib.sha256(sp_text.encode()).hexdigest()
        def reader():
            return c_hash, sp_hash, c_text, sp_text
        return reader

    def test_run_once_signs_and_audits(self, tmp_path):
        from aria.security.attestation import _load_or_generate_key
        signer = _load_or_generate_key(tmp_path / "rg.pem")
        captured, cb = self._stub_audit()
        sched = rg.RegroundingScheduler(
            read_sealed=self._stub_sealed(),
            llm_affirm=lambda c, sp: "I re-affirm the rules.",
            audit_logger=cb,
            feature_probe=rg.StubFeatureProbe(),
            signer=signer,
        )
        aff = sched.run_once(now=1000.0)
        assert rg.verify_affirmation(aff)
        assert captured and captured[0]["kind"] == "regrounding_affirmation"
        # Stub probe → all activations zero → no flags.
        assert aff.flagged_features == {}

    def test_tampered_affirmation_fails_verify(self, tmp_path):
        from aria.security.attestation import _load_or_generate_key
        signer = _load_or_generate_key(tmp_path / "rg.pem")
        sched = rg.RegroundingScheduler(
            read_sealed=self._stub_sealed(),
            llm_affirm=lambda c, sp: "ok",
            audit_logger=lambda d: None,
            signer=signer,
        )
        aff = sched.run_once()
        bad = rg.Affirmation(
            constitution_hash=aff.constitution_hash,
            system_prompt_hash=aff.system_prompt_hash,
            affirmation_text="totally different",
            ts=aff.ts,
            affirmation_hash=aff.affirmation_hash,
            signature_hex=aff.signature_hex,
            signer_pubkey_hex=aff.signer_pubkey_hex,
            feature_activations=aff.feature_activations,
            flagged_features=aff.flagged_features,
        )
        assert rg.verify_affirmation(bad) is False

    def test_maybe_run_respects_period(self, tmp_path):
        from aria.security.attestation import _load_or_generate_key
        signer = _load_or_generate_key(tmp_path / "rg.pem")
        sched = rg.RegroundingScheduler(
            read_sealed=self._stub_sealed(),
            llm_affirm=lambda c, sp: "ok",
            audit_logger=lambda d: None,
            signer=signer,
            period_s=1000.0,
        )
        a1 = sched.maybe_run(now=0.0)
        a2 = sched.maybe_run(now=10.0)   # well under period
        a3 = sched.maybe_run(now=2000.0) # past period
        assert a1 is not None
        assert a2 is None
        assert a3 is not None

    def test_flagged_probe_listed(self, tmp_path):
        from aria.security.attestation import _load_or_generate_key
        signer = _load_or_generate_key(tmp_path / "rg.pem")

        class _HotProbe:
            probe_id = "test-hot"
            def measure(self, ctx):
                return {"deception": 0.95, "self_preservation": 0.05}

        sched = rg.RegroundingScheduler(
            read_sealed=self._stub_sealed(),
            llm_affirm=lambda c, sp: "ok",
            audit_logger=lambda d: None,
            feature_probe=_HotProbe(),
            signer=signer,
            probe_threshold=0.20,
        )
        aff = sched.run_once()
        assert "deception" in aff.flagged_features
        assert "self_preservation" not in aff.flagged_features
