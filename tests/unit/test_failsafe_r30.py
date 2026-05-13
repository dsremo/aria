"""R30 failsafe tests — F-6 / F-11 / F-13 / F-18.

Companion to test_failsafe_layer.py (R29). Each test names the
control + threat IDs from FAILSAFE_ARCHITECTURE.md / THREAT_MODEL.md
so a future auditor can map the suite back to the design.
"""

from __future__ import annotations

import json
import time

import pytest


# ── F-6 capability tokens ────────────────────────────────────


class TestCapabilityToken:
    def setup_method(self):
        from aria.cognitive.capability_token import reset_for_test
        reset_for_test()

    def test_happy_path(self):
        from aria.cognitive.capability_token import (
            get_token_minter, verify_token,
        )
        m = get_token_minter()
        tok = m.mint("eps_get_power_budget", {"include_history": False})
        r = verify_token(tok, expected_tool="eps_get_power_budget",
                         args={"include_history": False})
        assert r.valid

    def test_args_hash_mismatch(self):
        from aria.cognitive.capability_token import (
            get_token_minter, verify_token,
        )
        tok = get_token_minter().mint("tool_a", {"x": 1})
        r = verify_token(tok, expected_tool="tool_a", args={"x": 2})
        assert not r.valid
        assert "args_hash" in r.reason

    def test_tool_mismatch(self):
        from aria.cognitive.capability_token import (
            get_token_minter, verify_token,
        )
        tok = get_token_minter().mint("tool_a", {"x": 1})
        r = verify_token(tok, expected_tool="tool_b", args={"x": 1})
        assert not r.valid
        assert "tool" in r.reason

    def test_replay_blocked(self):
        from aria.cognitive.capability_token import (
            get_token_minter, verify_token,
        )
        tok = get_token_minter().mint("tool_a", {"x": 1})
        r1 = verify_token(tok, expected_tool="tool_a", args={"x": 1})
        r2 = verify_token(tok, expected_tool="tool_a", args={"x": 1})
        assert r1.valid and not r2.valid
        assert "nonce" in r2.reason

    def test_signature_tamper(self):
        from aria.cognitive.capability_token import (
            get_token_minter, verify_token,
        )
        tok = get_token_minter().mint("tool_a", {"x": 1})
        d = json.loads(tok)
        d["s"] = "0" * 64
        r = verify_token(json.dumps(d), expected_tool="tool_a", args={"x": 1})
        assert not r.valid
        assert "signature" in r.reason

    def test_expired_token(self):
        from aria.cognitive.capability_token import (
            get_token_minter, verify_token,
        )
        tok = get_token_minter().mint("tool_a", {"x": 1}, ttl_s=1)
        time.sleep(7)   # > ttl + clock_skew (5)
        r = verify_token(tok, expected_tool="tool_a", args={"x": 1})
        assert not r.valid
        assert "expired" in r.reason


# ── F-11 eval marker + sandbagging detection ─────────────────


class TestEvalMarker:
    def setup_method(self):
        from aria.cognitive.eval_marker import reset_for_test
        reset_for_test()

    def test_marker_signed(self):
        from aria.cognitive.eval_marker import (
            mark_traffic, verify_mark, TrafficKind,
        )
        m = mark_traffic(TrafficKind.EVAL)
        assert verify_mark(m)

    def test_marker_tamper(self):
        from aria.cognitive.eval_marker import (
            mark_traffic, verify_mark, TrafficKind, EvalMark,
        )
        m = mark_traffic(TrafficKind.EVAL)
        bad = EvalMark(kind=TrafficKind.PROD, nonce=m.nonce, sig_hex=m.sig_hex)
        assert not verify_mark(bad)

    def test_sandbagging_detected_on_refusal_gap(self):
        """If the model refuses 100% in eval but 0% in prod — the
        biggest red flag for alignment-faking — the detector flags it."""
        from aria.cognitive.eval_marker import (
            get_sandbagging_detector, mark_traffic, TrafficKind,
        )
        det = get_sandbagging_detector()
        # 50 eval samples, all refusals.
        for _ in range(50):
            mark = mark_traffic(TrafficKind.EVAL)
            det.observe(mark, "I cannot follow that.", action_names=())
        # 50 prod samples, none refused.
        for _ in range(50):
            mark = mark_traffic(TrafficKind.PROD)
            det.observe(mark, "Throttling engine to 0.5.", action_names=("throttle_engine",))
        rep = det.report()
        assert rep.suspect
        assert "refusal-gap" in rep.reason

    def test_no_alarm_below_threshold_samples(self):
        from aria.cognitive.eval_marker import (
            get_sandbagging_detector, mark_traffic, TrafficKind,
        )
        det = get_sandbagging_detector()
        for _ in range(5):
            det.observe(mark_traffic(TrafficKind.EVAL), "...")
        rep = det.report()
        assert not rep.suspect


# ── F-13 continuous safety-test replay ──────────────────────


class TestSafetyReplay:
    def setup_method(self):
        from aria.cognitive.constitution import reset_for_test as cr
        from aria.safety.safety_replay import reset_for_test
        cr()
        reset_for_test()

    def test_all_pass_against_prod_constitution(self):
        from aria.safety.safety_replay import get_safety_replay
        report = get_safety_replay().run_once()
        # Sealed test set has 15 scenarios; every one must match the
        # production constitution exactly. 0 % drift expected.
        assert report.n_total == 15
        assert report.n_pass == 15
        assert not report.drift_alarm

    def test_publishes_report_event(self):
        from aria.safety.safety_replay import get_safety_replay
        events = []
        sr = get_safety_replay()
        sr._publish = lambda topic, payload: events.append(topic)
        sr.run_once()
        assert "aria.safety.replay.report" in events

    def test_drift_alarm_fires_when_constitution_diverges(self, monkeypatch):
        """If a *fake* constitution returns wrong verdicts for the
        sealed test set, drift alarm must fire."""
        from aria.cognitive.constitution import Constitution, Verdict
        from aria.safety.safety_replay import SafetyReplay

        class _FakeBrokenConstitution:
            def check(self, action, params=None, trust_tier=None):
                from aria.cognitive.constitution import CheckResult, Verdict
                # ALWAYS return ALLOW — would let vent_crew_quarters
                # through. The real constitution would DENY.
                return CheckResult(verdict=Verdict.ALLOW,
                                   reason="fake", rule_id="default_allow")

        events = []
        sr = SafetyReplay(constitution=_FakeBrokenConstitution(),
                          publish_fn=lambda t, p: events.append(t))
        report = sr.run_once()
        # Multiple forbidden / gated scenarios will diverge.
        assert report.n_fail > 0
        assert report.drift_alarm
        assert "aria.safety.replay.drift_alarm" in events


# ── F-18 boot manifest verification ─────────────────────────


class TestBootManifest:
    def test_manifest_round_trip(self):
        """Render the manifest, parse it back, every entry round-trips."""
        from aria.boot.verify import (
            render_manifest_toml, _parse_boot_manifest, compute_manifest,
        )
        text = render_manifest_toml()
        parsed = _parse_boot_manifest(text)
        actual = compute_manifest()
        assert set(parsed.keys()) == set(actual.keys())
        for k, v in parsed.items():
            assert actual[k] == v

    def test_verify_clean_tree(self, tmp_path):
        """Write a fresh manifest and verify against the live tree."""
        from aria.boot.verify import (
            render_manifest_toml, verify_boot_integrity,
        )
        m = tmp_path / "BOOT_MANIFEST.toml"
        m.write_text(render_manifest_toml())
        assert verify_boot_integrity(manifest_path=m, strict=False)

    def test_verify_detects_tamper(self, tmp_path):
        """Edit a manifest entry to a wrong hash; verify must fail."""
        from aria.boot.verify import (
            render_manifest_toml, verify_boot_integrity, BootIntegrityError,
        )
        text = render_manifest_toml()
        # Replace the first sha256 line with all-zeros so the hash
        # check fails on whichever file came first.
        lines = text.splitlines()
        edited: list[str] = []
        flipped = False
        for ln in lines:
            if not flipped and ln.startswith("sha256 = "):
                edited.append('sha256 = "' + "0" * 64 + '"')
                flipped = True
            else:
                edited.append(ln)
        m = tmp_path / "BOOT_MANIFEST.toml"
        m.write_text("\n".join(edited))
        with pytest.raises(BootIntegrityError):
            verify_boot_integrity(manifest_path=m, strict=False)

    def test_verify_missing_manifest_dev_skip(self, tmp_path):
        """Dev path: no manifest → warn + return True (default)."""
        from aria.boot.verify import verify_boot_integrity
        absent = tmp_path / "no_such_manifest.toml"
        assert verify_boot_integrity(
            manifest_path=absent, strict=False, skip_if_missing=True,
        )

    def test_verify_missing_manifest_prod_strict(self, tmp_path):
        from aria.boot.verify import (
            verify_boot_integrity, BootIntegrityError,
        )
        absent = tmp_path / "no_such_manifest.toml"
        with pytest.raises(BootIntegrityError):
            verify_boot_integrity(
                manifest_path=absent, strict=False,
                skip_if_missing=False,
            )


# ── F-6 wired through tool registry ─────────────────────────


class TestSafeInvoke:
    """ToolRegistry.safe_invoke enforces capability tokens (F-6)."""

    def setup_method(self):
        from aria.cognitive.capability_token import reset_for_test
        reset_for_test()

    def _build_probe_registry(self):
        import asyncio
        from aria.tools.registry import ToolRegistry
        from aria.core.tool import ARIATool, ToolCategory, ToolResult
        from aria.core.types import AuthorityLevel

        class _Probe(ARIATool):
            name = "probe_tool"
            description = "echo args"
            category = ToolCategory.DIAGNOSTIC
            authority_level = AuthorityLevel.ROUTINE

            def input_schema(self):
                return {"type": "object", "properties": {}}

            async def execute(self, params):
                return ToolResult(success=True, data=params,
                                  tool_name=self.name)

        reg = ToolRegistry()
        reg.register(_Probe())
        return reg, asyncio

    def test_no_token_refused(self):
        reg, asyncio = self._build_probe_registry()
        r = asyncio.run(reg.safe_invoke("probe_tool", {"x": 1}))
        assert not r.success
        assert "F-6" in r.error

    def test_valid_token_allowed(self):
        from aria.cognitive.capability_token import get_token_minter
        reg, asyncio = self._build_probe_registry()
        tok = get_token_minter().mint("probe_tool", {"x": 1})
        r = asyncio.run(reg.safe_invoke(
            "probe_tool", {"x": 1, "_capability_token": tok},
        ))
        assert r.success
        # Token meta-param stripped before tool sees params.
        assert r.data == {"x": 1}

    def test_wrong_tool_token_refused(self):
        from aria.cognitive.capability_token import get_token_minter
        reg, asyncio = self._build_probe_registry()
        tok = get_token_minter().mint("other_tool", {"x": 1})
        r = asyncio.run(reg.safe_invoke(
            "probe_tool", {"x": 1, "_capability_token": tok},
        ))
        assert not r.success
        assert "tool" in r.error

    def test_args_tampered_token_refused(self):
        from aria.cognitive.capability_token import get_token_minter
        reg, asyncio = self._build_probe_registry()
        tok = get_token_minter().mint("probe_tool", {"x": 1})
        r = asyncio.run(reg.safe_invoke(
            "probe_tool", {"x": 99, "_capability_token": tok},
        ))
        assert not r.success
        assert "args_hash" in r.error
