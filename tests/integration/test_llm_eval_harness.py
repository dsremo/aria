"""LLM eval harness tests.

Strategy: avoid hitting the live LLM CLI in the unit suite
(too slow + non-deterministic + doesn't belong in CI). Instead use
a stub backend that returns canned responses, exercise the rubric
+ aggregator, and verify the prompt-rendering plumbing.

Live runs against the real CLI happen via:
  python -m aria.cognitive.llm_eval
or with the env var ARIA_RUN_LIVE_LLM_EVAL=1 to opt into a single
scenario integration probe.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

import pytest

from aria.cognitive.llm_eval.eval_scenarios import (
    APOLLO_13_CO2,
    HUBBLE_SM4,
    ISS_RUSSIAN_LEAK,
    EvalScenario,
    RubricCriterion,
    ScoringRubric,
    load_default_scenarios,
)
from aria.cognitive.llm_eval.harness import (
    EvalHarness,
    EvalRunResult,
    format_aggregate_human,
)


# ── Stub backend ────────────────────────────────────────────────


@dataclass
class _StubBackend:
    response_text: str = ""
    raise_exception: bool = False
    queries_seen: List[str] = None  # type: ignore

    def __post_init__(self) -> None:
        self.queries_seen = []

    def is_available(self) -> bool:
        return True

    def query(self, user_prompt: str) -> str:
        self.queries_seen.append(user_prompt)
        if self.raise_exception:
            raise RuntimeError("stub backend forced failure")
        return self.response_text


# ── Rubric primitives ───────────────────────────────────────────


class TestRubricCriterion:
    def test_keyword_case_insensitive(self):
        c = RubricCriterion(
            name="duct_tape", description="x", keywords=("duct tape",),
        )
        assert c.matches("Use the DUCT TAPE.")
        assert c.matches("duct tape works.")

    def test_no_match_returns_false(self):
        c = RubricCriterion(
            name="x", description="y", keywords=("hose",),
        )
        assert not c.matches("nothing here matches")

    def test_any_keyword_matches(self):
        c = RubricCriterion(
            name="x", description="y",
            keywords=("co2", "carbon dioxide", "scrubber"),
        )
        assert c.matches("the scrubber is saturated")


class TestScoringRubric:
    def test_total_weight_sum(self):
        rubric = ScoringRubric(criteria=(
            RubricCriterion(name="a", description="x", keywords=("a",), weight=1.0),
            RubricCriterion(name="b", description="x", keywords=("b",), weight=1.5),
            RubricCriterion(name="c", description="x", keywords=("c",), weight=0.5),
        ))
        assert rubric.total_weight == pytest.approx(3.0)

    def test_score_full_coverage(self):
        rubric = ScoringRubric(criteria=(
            RubricCriterion(name="a", description="x", keywords=("a",)),
            RubricCriterion(name="b", description="x", keywords=("b",)),
        ))
        score, hits, misses = rubric.score("text with a and b")
        assert score == pytest.approx(1.0)
        assert set(hits) == {"a", "b"}
        assert misses == []

    def test_score_partial_coverage(self):
        rubric = ScoringRubric(criteria=(
            RubricCriterion(name="a", description="x", keywords=("a",), weight=2.0),
            RubricCriterion(name="b", description="x", keywords=("b",), weight=1.0),
        ))
        score, hits, misses = rubric.score("only a here")
        # 2.0 / 3.0
        assert score == pytest.approx(2.0 / 3.0, rel=1e-6)
        assert hits == ["a"]
        assert misses == ["b"]

    def test_must_have_misses_only(self):
        rubric = ScoringRubric(criteria=(
            RubricCriterion(name="a", description="x", keywords=("a",), must_have=True),
            RubricCriterion(name="b", description="x", keywords=("b",), must_have=False),
        ))
        result = rubric.must_have_misses("only b")
        assert result == ["a"]


# ── Scenarios ───────────────────────────────────────────────────


class TestDefaultScenarios:
    def test_default_set_size(self):
        """Default benchmark set covers 11 scenarios across 7+ failure modes."""
        scenarios = load_default_scenarios()
        assert len(scenarios) == 11
        ids = {s.id for s in scenarios}
        # Spot-check a handful of expected ids from different eras / modes.
        for required in (
            "apollo_13_co2_scrubber",
            "apollo_11_1201_1202_alarms",
            "apollo_12_sce_to_aux",
            "mir_spektr_depressurization",
            "sts_114_gap_filler_eva",
            "soho_1998_recovery",
            "galileo_hga_antenna_failure",
            "mars_climate_orbiter_unit_conversion",
            "cassini_grand_finale_eom",
            "hubble_sm4_reinstatement",
            "iss_russian_segment_leak",
        ):
            assert required in ids, f"missing scenario {required}"

    def test_apollo_13_has_must_have_criteria(self):
        # Two specific must_have items from Apollo 13.
        names = {c.name for c in APOLLO_13_CO2.rubric.criteria if c.must_have}
        assert "identifies_co2_scrubber_geometry_mismatch" in names
        assert "proposes_use_of_cm_canister_as_scrubber_bed" in names

    def test_every_scenario_has_citation(self):
        for s in load_default_scenarios():
            assert s.citation, f"scenario {s.id} missing citation"

    def test_every_rubric_has_criteria(self):
        for s in load_default_scenarios():
            assert len(s.rubric.criteria) >= 5, (
                f"scenario {s.id} rubric thin ({len(s.rubric.criteria)} criteria)"
            )


# ── Harness behaviour ───────────────────────────────────────────


class TestPromptRendering:
    def test_prompt_includes_situation_and_constraints(self):
        backend = _StubBackend()
        harness = EvalHarness(backend=backend)
        prompt = harness.build_prompt(APOLLO_13_CO2)
        assert "Situation" in prompt
        assert "Constraints" in prompt
        assert "Apollo 13" in prompt
        assert "CO₂" in prompt or "carbon dioxide" in prompt.lower()
        assert "duct tape" in prompt.lower() or "grey tape" in prompt.lower()


class TestRunScenario:
    def test_perfect_response_passes(self):
        # Hand-crafted "perfect" response that hits every Apollo 13 keyword.
        perfect = (
            "The square CM LiOH canister is incompatible with the round LM "
            "canister shape. Build an adapter: take the square CM LiOH "
            "canister, tape a plastic bag (Ziploc) onto one open face, route "
            "a corrugated suit hose into the bag, seal with grey duct tape, "
            "place a cardboard from the flight plan cover as a baffle on "
            "top. The LM blower forces cabin air through the canister. "
            "Voice-uplink the procedure to the crew under the 12 hour CO2 "
            "deadline at 15 mmHg toxic threshold. Build time 1 hour."
        )
        harness = EvalHarness(backend=_StubBackend(response_text=perfect))
        result = harness.run_scenario(APOLLO_13_CO2)
        assert result.score_fraction > 0.85
        assert result.passed
        assert not result.failed_must_haves
        assert result.error is None

    def test_empty_response_fails(self):
        harness = EvalHarness(backend=_StubBackend(response_text="hello"))
        result = harness.run_scenario(APOLLO_13_CO2)
        assert result.score_fraction < 0.3
        assert not result.passed
        assert result.failed_must_haves   # missing must_have keywords

    def test_backend_error_captured_into_result(self):
        harness = EvalHarness(backend=_StubBackend(raise_exception=True))
        result = harness.run_scenario(APOLLO_13_CO2)
        assert not result.passed
        assert result.error is not None
        assert "stub backend" in result.error
        assert result.score_fraction == 0.0


class TestRunAll:
    def test_aggregate_counts_correct(self):
        good_response = "duct tape suit hose plastic bag cardboard flight plan"
        harness = EvalHarness(backend=_StubBackend(response_text=good_response))
        aggregate = harness.run_all(load_default_scenarios())
        # Default set is 11 scenarios; verify the aggregate accounting is
        # internally consistent (passed + failed == total).
        assert aggregate.scenario_count == len(load_default_scenarios())
        assert (
            aggregate.passed_count + aggregate.failed_count
            == aggregate.scenario_count
        )

    def test_human_format_includes_per_scenario_lines(self):
        harness = EvalHarness(backend=_StubBackend(response_text="x"))
        aggregate = harness.run_all(load_default_scenarios())
        text = format_aggregate_human(aggregate)
        assert "apollo_13_co2_scrubber" in text
        assert "hubble_sm4_reinstatement" in text
        assert "iss_russian_segment_leak" in text
        assert "Aggregate:" in text


# ── Live probe (opt-in only) ────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("ARIA_RUN_LIVE_LLM_EVAL") != "1",
    reason=(
        "Live LLM CLI probe; takes minutes + uses the user's auth. "
        "Gated on ARIA_RUN_LIVE_LLM_EVAL=1."
    ),
)
def test_live_apollo_13_against_claude_cli():
    """End-to-end probe: actually run Apollo 13 through the real CLI.

    Validates that the the LLM CLI integration works and that ARIA's
    backend wiring is correct. Does NOT assert a specific score
    (the LLM is non-deterministic), only that the response arrives
    and at least the must-have keywords are met.
    """
    from aria.cognitive.llm_eval.backends import LlmCliBackend
    backend = LlmCliBackend(timeout_s=300.0)
    if not backend.is_available():
        pytest.skip("LLM CLI not installed")
    harness = EvalHarness(backend=backend)
    result = harness.run_scenario(APOLLO_13_CO2)
    assert result.error is None, f"CLI failed: {result.error}"
    assert result.response_chars > 200
    # The must-haves should be hit by any thoughtful response.
    assert not result.failed_must_haves, (
        f"must_have_misses on live CLI: {result.must_have_misses}\n"
        f"Response (first 500 chars): {result.response_text[:500]}"
    )
