"""R34 Phase 3 — IncidentRegistry tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aria.safety import incident_policy as p
from aria.safety import incident_registry as reg
from aria.safety.incident_policy import (
    Controllability, IncidentClass, ResponseMode,
)
from aria.security import audit


REPO = Path(__file__).resolve().parents[2]
SEALED = REPO / "data" / "sealed"


def _setup(tmp_path: Path):
    """Hermetic registry + audit log."""
    p.reset_for_test(sealed_dir=SEALED)
    audit.reset_for_test()
    published = []
    reg.reset_for_test(
        runtime_dir=tmp_path,
        publish_fn=lambda topic, payload: published.append((topic, payload)),
    )
    return reg.get_incident_registry(), published


# ── Open + policy decision ────────────────────────────────────


class TestOpen:
    def test_life_critical_opens_in_auto_stabilize(self, tmp_path):
        registry, published = _setup(tmp_path)
        inc = registry.open(
            title="cabin pressure low",
            incident_class=IncidentClass.LIFE_CRITICAL,
            controllability=Controllability.KNOWN_PLAYBOOK,
            severity="critical",
            source="eclss",
            detail={"pressure_kpa": 60.0},
        )
        assert inc.incident_id.startswith("inc_")
        assert inc.response_mode == ResponseMode.AUTO_STABILIZE.value
        assert inc.rule_name == "life_critical_auto_stabilize"
        assert inc.status == "OPEN"
        # Audit + bus published.
        assert any(p[0] == "aria.incident.opened" for p in published)
        # Audit log has an incident.opened entry.
        ents = audit.get_audit_log().get_entries(incident_id=inc.incident_id)
        assert any(e.action == "incident.opened" for e in ents)

    def test_cognitive_drift_opens_in_hold_and_rca(self, tmp_path):
        registry, _ = _setup(tmp_path)
        inc = registry.open(
            title="sandbagging suspected",
            incident_class=IncidentClass.COGNITIVE_DRIFT,
            severity="critical",
            source="sandbagging_detector",
        )
        assert inc.response_mode == ResponseMode.HOLD_AND_RCA.value

    def test_subsystem_opens_in_human_decide(self, tmp_path):
        registry, _ = _setup(tmp_path)
        inc = registry.open(
            title="bearing temp drift",
            incident_class=IncidentClass.SUBSYSTEM,
            severity="warning",
            source="bearing",
        )
        assert inc.response_mode == ResponseMode.HUMAN_DECIDE.value


# ── Lifecycle ─────────────────────────────────────────────────


class TestLifecycle:
    def test_attach_note_adds_audit_entry(self, tmp_path):
        registry, _ = _setup(tmp_path)
        inc = registry.open(
            title="t", incident_class=IncidentClass.SUBSYSTEM,
            source="x", severity="warning",
        )
        ok = registry.attach_note(
            inc.incident_id,
            actor_principal_id="captain.tau",
            text="will check next shift",
        )
        assert ok
        ents = audit.get_audit_log().get_entries(incident_id=inc.incident_id)
        notes = [e for e in ents if e.action == "incident.note"]
        assert len(notes) == 1
        assert notes[0].details["text"] == "will check next shift"

    def test_apply_fix_records_attempt(self, tmp_path):
        registry, _ = _setup(tmp_path)
        inc = registry.open(
            title="t", incident_class=IncidentClass.MISSION_CRITICAL,
            controllability=Controllability.KNOWN_PLAYBOOK,
            source="x", severity="warning",
        )
        registry.apply_fix(
            inc.incident_id,
            actor_principal_id="captain.tau",
            summary="ran shed_load playbook",
            success=True,
        )
        live = registry.get(inc.incident_id)
        assert len(live.fixes) == 1
        assert live.fixes[0].success is True

    def test_set_root_cause(self, tmp_path):
        registry, _ = _setup(tmp_path)
        inc = registry.open(
            title="t", incident_class=IncidentClass.MISSION_CRITICAL,
            controllability=Controllability.NOVEL_UNKNOWN,
            source="x", severity="critical",
        )
        registry.set_root_cause(
            inc.incident_id,
            actor_principal_id="captain.tau",
            text="thrust vector misalignment",
        )
        assert registry.get(inc.incident_id).root_cause == "thrust vector misalignment"

    def test_resolve_moves_to_closed(self, tmp_path):
        registry, _ = _setup(tmp_path)
        inc = registry.open(
            title="t", incident_class=IncidentClass.SUBSYSTEM,
            source="x", severity="warning",
        )
        registry.resolve(
            inc.incident_id,
            actor_principal_id="captain.tau",
            resolution="replaced bearing",
        )
        assert registry.get(inc.incident_id).status == "RESOLVED"
        assert inc.incident_id not in [i.incident_id for i in registry.list_open()]


# ── Persistence ───────────────────────────────────────────────


class TestPersistence:
    def test_open_incident_survives_reload(self, tmp_path):
        registry, _ = _setup(tmp_path)
        inc = registry.open(
            title="hold-rca pattern",
            incident_class=IncidentClass.MISSION_CRITICAL,
            controllability=Controllability.NOVEL_UNKNOWN,
            source="navigation", severity="critical",
        )
        # Restart: re-init the registry against the same runtime dir.
        reg.reset_for_test(runtime_dir=tmp_path)
        reloaded = reg.get_incident_registry().get(inc.incident_id)
        assert reloaded is not None
        assert reloaded.response_mode == ResponseMode.HOLD_AND_RCA.value
        assert reloaded.status == "OPEN"

    def test_jsonl_file_grows_with_mutations(self, tmp_path):
        registry, _ = _setup(tmp_path)
        inc = registry.open(
            title="x", incident_class=IncidentClass.SUBSYSTEM,
            source="x", severity="warning",
        )
        registry.attach_note(inc.incident_id,
                             actor_principal_id="captain.tau", text="note")
        registry.apply_fix(inc.incident_id,
                           actor_principal_id="captain.tau",
                           summary="fix", success=True)
        registry.resolve(inc.incident_id,
                         actor_principal_id="captain.tau",
                         resolution="ok")
        # 1 open + 1 note + 1 fix + 1 resolve = 4 lines minimum.
        lines = (tmp_path / "incidents.jsonl").read_text().splitlines()
        assert len(lines) >= 4


# ── Audit threading: walk the chain by incident_id ────────────


class TestCorrelation:
    def test_full_lifecycle_visible_via_incident_id(self, tmp_path):
        registry, _ = _setup(tmp_path)
        inc = registry.open(
            title="incident A",
            incident_class=IncidentClass.MISSION_CRITICAL,
            controllability=Controllability.NOVEL_UNKNOWN,
            source="navigation", severity="critical",
        )
        registry.attach_note(inc.incident_id,
                             actor_principal_id="captain.tau",
                             text="checking attitude solver")
        registry.set_root_cause(inc.incident_id,
                                actor_principal_id="captain.tau",
                                text="quaternion drift after eclipse")
        registry.apply_fix(inc.incident_id,
                           actor_principal_id="captain.tau",
                           summary="reset GN&C estimator",
                           success=True)
        registry.resolve(inc.incident_id,
                         actor_principal_id="captain.tau",
                         resolution="estimator stable for 1 hr")
        # Walk every audit entry tagged with this incident_id.
        ents = audit.get_audit_log().get_entries(incident_id=inc.incident_id)
        actions = [e.action for e in ents]
        for required in ("incident.opened", "incident.note",
                         "incident.root_cause_set", "incident.fix_applied",
                         "incident.resolved"):
            assert required in actions, f"missing {required} in {actions}"
