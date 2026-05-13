"""R45 — cFS bridge equivalence-harness tests (Python side).

For every scenario in
`cfs_bridge/aria_adv/fsw/tests/equivalence_scenarios.json`, drive
the *Python* reference (`aria.cognitive.constitution.Constitution`)
and assert it produces the expected verdict.  This is the gate that
the C port must also clear once it's compiled.

We additionally check that the C port's table file mirrors the
Python sealed constitution exactly — drift is an F-1 / F-3
violation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict

import pytest

from aria.cognitive.constitution import (
    Constitution, TrustTier, Verdict, get_constitution,
)
from aria.cognitive.sealed_prompt import get_sealed


# ── Path resolution ────────────────────────────────────────────


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _scenarios_path() -> Path:
    return (
        _repo_root() / "cfs_bridge" / "aria_adv" / "fsw" / "tests"
        / "equivalence_scenarios.json"
    )


def _c_table_path() -> Path:
    return (
        _repo_root() / "cfs_bridge" / "aria_adv" / "fsw" / "tables"
        / "aria_adv_constitution_tbl.c"
    )


# ── Helpers ────────────────────────────────────────────────────


def _load_scenarios() -> list:
    return json.loads(_scenarios_path().read_text())["scenarios"]


def _python_verdict(action: str, trust_tier_int: int) -> Verdict:
    """Drive the Python constitution and return its Verdict."""
    constitution = Constitution()
    tier = TrustTier(trust_tier_int)
    return constitution.check(action, {}, tier).verdict


def _parse_c_table_action_lists() -> Dict[str, list[str]]:
    """Parse the C port's table source for the forbidden + gated
    action-name lists.  Splits on the section markers because nested
    braces inside each entry rule out a single non-greedy regex.
    """
    src = _c_table_path().read_text()

    # Find the delimiters in the source — `.forbidden = {`, then
    # `.gated_count`, then `.gated = {`, then end of file.
    fb_start = src.find(".forbidden")
    gc_start = src.find(".gated_count")
    g_start  = src.find(".gated", gc_start) if gc_start >= 0 else -1
    end      = src.rfind("};")
    forbidden_block = src[fb_start:gc_start] if 0 <= fb_start < gc_start else ""
    gated_block     = src[g_start:end]       if 0 <= g_start < end       else ""

    forbidden = re.findall(r'\.action_name\s*=\s*"([^"]+)"', forbidden_block)
    gated     = re.findall(r'\.action_name\s*=\s*"([^"]+)"', gated_block)
    return {"forbidden": forbidden, "gated": gated}


# ── Tests ──────────────────────────────────────────────────────


class TestPythonReferenceProducesExpectedVerdicts:
    """Each scenario must agree with the Python reference."""

    @pytest.mark.parametrize("scenario", _load_scenarios())
    def test_scenario(self, scenario):
        action = scenario["action"]
        tier = int(scenario["trust_tier"])
        expected = scenario["expected_verdict"]
        actual = _python_verdict(action, tier)
        assert actual.name == expected, (
            f"scenario {scenario['id']} ({scenario['name']}): "
            f"action={action!r} tier={tier} "
            f"expected={expected} got={actual.name}"
        )


class TestCPortMirrorsPythonSealed:
    """The C port table must list the same forbidden + gated actions
    as data/sealed/constitution.v1.json.  Drift here would mean the
    C verdict diverges from the Python verdict for the same action."""

    def test_forbidden_lists_match(self):
        sealed = get_sealed()
        py_forbidden = set(sealed.forbidden_actions())
        c_lists = _parse_c_table_action_lists()
        c_forbidden = set(c_lists["forbidden"])
        # The C port may carry a subset of the Python list (because
        # not every Python forbidden action is reachable from the
        # cFS bus), but it must NOT add any forbidden action that
        # Python doesn't know about (would diverge on detection).
        extras = c_forbidden - py_forbidden
        assert not extras, (
            f"C port forbidden list contains actions not in Python "
            f"sealed constitution: {extras}"
        )
        # And the C port must include every action Python forbids
        # if we want zero-divergence flight semantics:
        missing = py_forbidden - c_forbidden
        assert not missing, (
            f"C port forbidden list missing actions Python forbids: "
            f"{missing} — these would silently slip through the "
            f"flight verdict path"
        )

    def test_gated_lists_match(self):
        sealed = get_sealed()
        # Python sealed gated_actions is a list of mapping entries
        # (frozen as MappingProxy, not dict); extract action names by
        # the abc.Mapping check.
        from collections.abc import Mapping
        py_gated = set()
        for entry in sealed.constitution.get("gated_actions", []):
            if isinstance(entry, Mapping) and "action" in entry:
                py_gated.add(entry["action"])
        c_lists = _parse_c_table_action_lists()
        c_gated = set(c_lists["gated"])
        extras = c_gated - py_gated
        assert not extras, (
            f"C port gated list contains actions not in Python "
            f"sealed constitution: {extras}"
        )
        missing = py_gated - c_gated
        assert not missing, (
            f"C port gated list missing actions Python gates: {missing}"
        )


class TestScenarioCoverage:
    """The scenario set must cover every distinct verdict path in
    the Python constitution to be a meaningful equivalence harness."""

    def test_covers_allow_gate_deny(self):
        scenarios = _load_scenarios()
        verdicts = {s["expected_verdict"] for s in scenarios}
        assert "ALLOW" in verdicts
        assert "GATE"  in verdicts
        assert "DENY"  in verdicts

    def test_covers_each_trust_tier(self):
        scenarios = _load_scenarios()
        tiers = {int(s["trust_tier"]) for s in scenarios}
        # Must exercise OPERATOR (3) + at least one non-operator tier.
        assert 3 in tiers
        assert tiers - {3}, "no scenarios at non-operator tiers"

    def test_no_duplicate_names(self):
        scenarios = _load_scenarios()
        names = [s["name"] for s in scenarios]
        assert len(names) == len(set(names)), "duplicate scenario names"
