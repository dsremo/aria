"""R34 Phase 2 — incident response policy tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from aria.safety import incident_policy as p
from aria.safety.incident_policy import (
    Controllability,
    IncidentClass,
    ResponseMode,
)


REPO = Path(__file__).resolve().parents[2]
SEALED = REPO / "data" / "sealed"


def _setup():
    p.reset_for_test(sealed_dir=SEALED)


# ── Sealed file load ───────────────────────────────────────────


class TestLoad:
    def test_loads_rules(self):
        _setup()
        store = p.get_policy_store()
        rules = store.all_rules()
        assert len(rules) >= 8
        names = {r.name for r in rules}
        assert "life_critical_auto_stabilize" in names


# ── Each documented mode ───────────────────────────────────────


class TestDecisionMatrix:
    def test_life_critical_always_auto_stabilize(self):
        _setup()
        for ctl in list(Controllability) + [None]:
            d = p.decide_response_mode(IncidentClass.LIFE_CRITICAL, ctl)
            assert d.mode is ResponseMode.AUTO_STABILIZE
            assert d.rule_name == "life_critical_auto_stabilize"

    def test_security_always_auto_stabilize(self):
        _setup()
        d = p.decide_response_mode(IncidentClass.SECURITY,
                                   Controllability.NOVEL_UNKNOWN)
        assert d.mode is ResponseMode.AUTO_STABILIZE
        assert "security" in d.rule_name

    def test_cognitive_drift_holds(self):
        """The whole point of the policy: blind action on suspected
        sandbagging or constitution drift could be the AI gaming the
        very metric we use to detect it. Pause first."""
        _setup()
        d = p.decide_response_mode(IncidentClass.COGNITIVE_DRIFT,
                                   Controllability.NOVEL_UNKNOWN)
        assert d.mode is ResponseMode.HOLD_AND_RCA

    def test_mission_critical_known_executes(self):
        _setup()
        d = p.decide_response_mode(IncidentClass.MISSION_CRITICAL,
                                   Controllability.KNOWN_PLAYBOOK)
        assert d.mode is ResponseMode.AUTO_STABILIZE

    def test_mission_critical_novel_holds(self):
        _setup()
        d = p.decide_response_mode(IncidentClass.MISSION_CRITICAL,
                                   Controllability.NOVEL_UNKNOWN)
        assert d.mode is ResponseMode.HOLD_AND_RCA

    def test_mission_critical_recurring_human(self):
        _setup()
        d = p.decide_response_mode(IncidentClass.MISSION_CRITICAL,
                                   Controllability.RECURRING_TUNING)
        assert d.mode is ResponseMode.HUMAN_DECIDE

    def test_mission_critical_degraded_known_stabilizes(self):
        _setup()
        d = p.decide_response_mode(IncidentClass.MISSION_CRITICAL,
                                   Controllability.DEGRADED_KNOWN)
        assert d.mode is ResponseMode.AUTO_STABILIZE

    def test_subsystem_human_decides(self):
        _setup()
        d = p.decide_response_mode(IncidentClass.SUBSYSTEM,
                                   Controllability.KNOWN_PLAYBOOK)
        assert d.mode is ResponseMode.HUMAN_DECIDE

    def test_comfort_observe(self):
        _setup()
        d = p.decide_response_mode(IncidentClass.COMFORT, None)
        assert d.mode is ResponseMode.OBSERVE_ONLY

    def test_informational_observe(self):
        _setup()
        d = p.decide_response_mode(IncidentClass.INFORMATIONAL, None)
        assert d.mode is ResponseMode.OBSERVE_ONLY


# ── Decision audit trail ───────────────────────────────────────


class TestAudit:
    def test_decision_carries_rule_name_and_description(self):
        _setup()
        d = p.decide_response_mode(IncidentClass.LIFE_CRITICAL,
                                   Controllability.NOVEL_UNKNOWN)
        assert d.rule_name
        assert d.description
