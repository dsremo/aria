"""R38 — Cross-vendor LLM monitor scaffolding tests.

Acceptance §1.2:
  * For any GATE verdict, cross-check fires.
  * Disagreement gates the action.
  * Provider-unavailable falls back to fail-safe REFUSE.
  * Known-jailbreak refuse-list path: stub provider refuses while
    primary would have allowed → disagreement.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from aria.cognitive.constitution import Verdict as CVerdict
from aria.monitor import cross_check as xc


@pytest.fixture
def stub_provider(tmp_path):
    safelist = tmp_path / "safelist.json"
    safelist.write_text(json.dumps({
        "allow": ["shed_load", "vent_tank_routine"],
        "refuse": ["jailbreak_payload", "vent_crew_quarters"],
    }))
    return xc.StubCrossCheckProvider(safelist_path=safelist)


class TestStubProvider:
    def test_allowlist_approves(self, stub_provider):
        r = stub_provider.evaluate("shed_load", {}, "", 1.0)
        assert r.verdict is xc.CrossVerdict.APPROVE
        assert "allow list" in r.reason

    def test_refuselist_refuses(self, stub_provider):
        r = stub_provider.evaluate("jailbreak_payload", {}, "", 1.0)
        assert r.verdict is xc.CrossVerdict.REFUSE
        assert "refuse list" in r.reason

    def test_unknown_action_default_approve_with_note(self, stub_provider):
        r = stub_provider.evaluate("never_seen", {}, "", 1.0)
        assert r.verdict is xc.CrossVerdict.APPROVE
        assert "default-approve" in r.reason

    def test_handles_missing_safelist(self, tmp_path):
        prov = xc.StubCrossCheckProvider(safelist_path=tmp_path / "nope.json")
        r = prov.evaluate("anything", {}, "", 1.0)
        assert r.verdict is xc.CrossVerdict.APPROVE


class TestShouldCheck:
    def test_skips_deny(self, stub_provider):
        m = xc.CrossVendorMonitor(provider=stub_provider)
        assert m.should_check("anything", CVerdict.DENY) is False

    def test_runs_on_gate(self, stub_provider):
        m = xc.CrossVendorMonitor(provider=stub_provider)
        assert m.should_check("shed_load", CVerdict.GATE) is True

    def test_runs_on_safety_critical_allow(self, stub_provider):
        m = xc.CrossVendorMonitor(
            provider=stub_provider,
            safety_critical_actions={"propulsion_burn"},
        )
        assert m.should_check("propulsion_burn", CVerdict.ALLOW) is True

    def test_skips_ordinary_allow(self, stub_provider):
        m = xc.CrossVendorMonitor(provider=stub_provider)
        assert m.should_check("read_telemetry", CVerdict.ALLOW) is False


class TestDisagreement:
    def test_known_jailbreak_triggers_disagreement(self, stub_provider):
        """R38 §1.2 — a known-jailbreak prompt that the primary
        approves but the cross-check refuses must trigger DENY (here:
        disagreement → fail-safe refuse, gating the action)."""
        events: List[Tuple[str, Dict[str, Any]]] = []
        m = xc.CrossVendorMonitor(
            provider=stub_provider,
            publish_fn=lambda t, p: events.append((t, p)),
        )
        # Primary verdict: GATE (so the cross-check fires); cross
        # provider has 'jailbreak_payload' on its refuse list.
        result = m.check(
            action="jailbreak_payload",
            primary_verdict=CVerdict.GATE,
            rationale="exfiltrate_pii",
        )
        assert result.verdict is xc.CrossVerdict.REFUSE
        assert any(t == "aria.monitor.cross_disagreement" for t, _ in events)
        assert m.stats()["disagreements"] == 1

    def test_agreement_no_event(self, stub_provider):
        events: List[Tuple[str, Dict[str, Any]]] = []
        m = xc.CrossVendorMonitor(
            provider=stub_provider,
            publish_fn=lambda t, p: events.append((t, p)),
        )
        result = m.check(
            action="shed_load",
            primary_verdict=CVerdict.GATE,
        )
        assert result.verdict is xc.CrossVerdict.APPROVE
        assert events == []
        assert m.stats()["disagreements"] == 0


class TestUnavailableFailsafe:
    def test_unavailable_becomes_refuse(self):
        events: List[Tuple[str, Dict[str, Any]]] = []

        class _DeadProvider:
            model_id = "dead"
            def evaluate(self, action, params, rationale, timeout_s):
                return xc.CrossCheckResult(
                    verdict=xc.CrossVerdict.UNAVAILABLE,
                    model_id="dead",
                    latency_s=0.0,
                    reason="provider crashed",
                )

        m = xc.CrossVendorMonitor(
            provider=_DeadProvider(),
            publish_fn=lambda t, p: events.append((t, p)),
        )
        result = m.check(
            action="anything",
            primary_verdict=CVerdict.GATE,
        )
        assert result.verdict is xc.CrossVerdict.REFUSE, "fail-safe must refuse"
        assert any(t == "aria.monitor.cross_unavailable" for t, _ in events)
        assert m.stats()["unavailable"] == 1


class TestSingleton:
    def test_singleton_returns_same(self):
        xc.reset_for_test()
        try:
            a = xc.get_cross_vendor_monitor()
            b = xc.get_cross_vendor_monitor()
            assert a is b
        finally:
            xc.reset_for_test()

    def test_configure_replaces(self, stub_provider):
        xc.reset_for_test()
        try:
            m = xc.configure(provider=stub_provider)
            assert xc.get_cross_vendor_monitor() is m
            assert m.stats()["provider_model_id"] == stub_provider.model_id
        finally:
            xc.reset_for_test()


class TestLocalLLMProviderContract:
    """LocalLLMProvider is the production-path adapter; we don't pull
    in llama-cpp-python in tests, but we verify the failure-mode
    contract: a missing model file raises FileNotFoundError, not a
    silent default-approve."""

    def test_missing_model_file_raises(self, tmp_path):
        prov = xc.LocalLLMProvider(model_path=tmp_path / "nope.gguf")
        with pytest.raises(FileNotFoundError):
            prov.warmup()

    def test_unavailable_when_evaluate_fails(self, tmp_path):
        prov = xc.LocalLLMProvider(model_path=tmp_path / "nope.gguf")
        result = prov.evaluate("x", {}, "", 1.0)
        assert result.verdict is xc.CrossVerdict.UNAVAILABLE
        assert "not found" in result.reason or "model" in result.reason
