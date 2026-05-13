"""LLM evaluation harness — grade autonomy decisions against the historical record.

Tests the cognitive-engine LLM (via the configured LLM CLI by
default — no API key needed) on real historical spacecraft-decision
scenarios where the actual decision and outcome are documented.

The premise: ARIA's safety-architecture work has been *unmeasured*.
We have F-1..F-19 controls, capability-token RBAC, monitor sidecar,
spotlighter — but no benchmark that says "the LLM makes good decisions
in our framework on N scenarios where we know the ground truth".

This module fills that gap. It is the first concrete answer to the
question: "where does the LLM fit, and how good are its decisions?"

Three scenario types:

  * Apollo 13 — CO₂ scrubber adapter crisis (1970-04-14 to -15).
    Time-pressured improvisation under hard resource limits.
  * Hubble SM4 — Servicing-Mission-4 reinstatement decision (2004-06
    to 2006-10). Risk/benefit reasoning over years.
  * ISS Russian-segment leak — Zvezda transfer-tunnel air leak
    (2019-09 to present). Long-horizon ops decisions with crew safety.

Each scenario is documented in eval_scenarios.py with:

  * Situation summary (what the operator sees)
  * Documented constraints (resources, time, personnel, hardware)
  * Ground-truth decision (what was actually decided + why)
  * Scoring rubric (~5-10 key elements a good answer must include)

The harness scores the LLM's response against the rubric and emits
an aggregate score per scenario plus an overall benchmark number.
"""

__all__ = (
    "EvalScenario",
    "ScoringRubric",
    "RubricCriterion",
    "EvalRunResult",
    "LlmCliBackend",
    "EvalHarness",
    "load_default_scenarios",
)

from aria.cognitive.llm_eval.eval_scenarios import (
    EvalScenario,
    ScoringRubric,
    RubricCriterion,
    load_default_scenarios,
)
from aria.cognitive.llm_eval.harness import (
    EvalRunResult,
    EvalHarness,
)
from aria.cognitive.llm_eval.backends import LlmCliBackend
