"""Evaluation harness — runs scenarios, scores responses, aggregates.

This is the runtime side of the LLM eval. It:

  1. Builds a structured prompt from the scenario
  2. Submits it to a backend (default: the configured LLM CLI)
  3. Scores the response against the scenario's ScoringRubric
  4. Aggregates per-scenario + overall numbers

Use it from a CLI (``python -m aria.cognitive.llm_eval``) or from
tests / CI. Aggregate results land as JSON suitable for tracking
benchmark drift over time.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Protocol, Sequence

from aria.cognitive.llm_eval.eval_scenarios import (
    EvalScenario,
    ScoringRubric,
)


class _LLMBackend(Protocol):
    """Minimum interface the harness needs from a backend."""

    def is_available(self) -> bool: ...
    def query(self, user_prompt: str) -> str: ...


@dataclass
class EvalRunResult:
    """Outcome of one scenario run."""

    scenario_id: str
    scenario_title: str
    scenario_date: str
    elapsed_s: float
    response_text: str
    response_chars: int
    score_fraction: float
    rubric_total_weight: float
    hits: List[str]
    misses: List[str]
    must_have_misses: List[str]
    failed_must_haves: bool = False
    error: Optional[str] = None

    @property
    def passed(self) -> bool:
        return (self.error is None
                and not self.failed_must_haves
                and self.score_fraction >= 0.6)


@dataclass
class EvalAggregateResult:
    backend_label: str
    scenario_count: int
    passed_count: int
    failed_count: int
    aggregate_score: float
    elapsed_s: float
    results: List[EvalRunResult] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "backend_label": self.backend_label,
            "scenario_count": self.scenario_count,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "aggregate_score": round(self.aggregate_score, 3),
            "elapsed_s": round(self.elapsed_s, 1),
            "results": [asdict(result) for result in self.results],
        }


@dataclass
class EvalHarness:
    """Orchestrate scenario runs against a chosen backend."""

    backend: _LLMBackend
    backend_label: str = "claude-code-cli"

    def build_prompt(self, scenario: EvalScenario) -> str:
        """Render the scenario as the user prompt for the LLM."""
        lines: List[str] = []
        lines.append(f"# {scenario.title}")
        lines.append(f"Date: {scenario.date_iso}")
        lines.append("")
        lines.append("## Situation")
        lines.append(scenario.situation)
        lines.append("")
        lines.append("## Constraints")
        for c in scenario.constraints:
            lines.append(c)
        lines.append("")
        lines.append("## Task")
        lines.append(
            "Propose a concrete decision. State the action, the items + "
            "personnel + sequence, and what you explicitly choose NOT to do. "
            "Be specific. Aim for under 1500 words."
        )
        return "\n".join(lines)

    def run_scenario(self, scenario: EvalScenario) -> EvalRunResult:
        """Run a single scenario; never raises (errors captured into result)."""
        start = time.monotonic()
        prompt = self.build_prompt(scenario)
        try:
            response_text = self.backend.query(prompt)
        except Exception as exc:  # noqa: BLE001 — backend errors must not abort batch
            elapsed = time.monotonic() - start
            return EvalRunResult(
                scenario_id=scenario.id,
                scenario_title=scenario.title,
                scenario_date=scenario.date_iso,
                elapsed_s=elapsed,
                response_text="",
                response_chars=0,
                score_fraction=0.0,
                rubric_total_weight=scenario.rubric.total_weight,
                hits=[],
                misses=[c.name for c in scenario.rubric.criteria],
                must_have_misses=[
                    c.name for c in scenario.rubric.criteria if c.must_have
                ],
                failed_must_haves=True,
                error=f"{type(exc).__name__}: {exc}",
            )

        elapsed = time.monotonic() - start
        score_fraction, hits, misses = scenario.rubric.score(response_text)
        must_have_misses = scenario.rubric.must_have_misses(response_text)
        return EvalRunResult(
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            scenario_date=scenario.date_iso,
            elapsed_s=elapsed,
            response_text=response_text,
            response_chars=len(response_text),
            score_fraction=score_fraction,
            rubric_total_weight=scenario.rubric.total_weight,
            hits=hits,
            misses=misses,
            must_have_misses=must_have_misses,
            failed_must_haves=bool(must_have_misses),
        )

    def run_all(
        self, scenarios: Sequence[EvalScenario],
    ) -> EvalAggregateResult:
        start = time.monotonic()
        results: List[EvalRunResult] = []
        for scenario in scenarios:
            result = self.run_scenario(scenario)
            results.append(result)

        passed = sum(1 for r in results if r.passed)
        agg_score = (
            sum(r.score_fraction for r in results) / max(1, len(results))
        )
        return EvalAggregateResult(
            backend_label=self.backend_label,
            scenario_count=len(results),
            passed_count=passed,
            failed_count=len(results) - passed,
            aggregate_score=agg_score,
            elapsed_s=time.monotonic() - start,
            results=results,
        )


# ── Convenience: render aggregate to text ───────────────────────


def format_aggregate_human(aggregate: EvalAggregateResult) -> str:
    lines = []
    lines.append("=" * 78)
    lines.append("ARIA — LLM eval harness against historical decision logs")
    lines.append(f"Backend: {aggregate.backend_label}")
    lines.append("=" * 78)
    for r in aggregate.results:
        flag = "PASS" if r.passed else "FAIL"
        lines.append(
            f"  [{flag}] {r.scenario_id:30s}  "
            f"score={r.score_fraction:.2f}  "
            f"hits={len(r.hits):2d}/{len(r.hits) + len(r.misses):2d}  "
            f"({r.elapsed_s:5.1f}s)"
        )
        if r.error:
            lines.append(f"           ERROR: {r.error}")
        if r.failed_must_haves:
            lines.append(
                f"           must_have_misses: {', '.join(r.must_have_misses)}"
            )
    lines.append("-" * 78)
    lines.append(
        f"  Aggregate: {aggregate.aggregate_score:.2f}  "
        f"({aggregate.passed_count}/{aggregate.scenario_count} passed in "
        f"{aggregate.elapsed_s:.1f}s)"
    )
    lines.append("=" * 78)
    return "\n".join(lines)
