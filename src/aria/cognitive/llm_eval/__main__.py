"""CLI entry: `python -m aria.cognitive.llm_eval`.

Runs the default scenario set through the configured LLM CLI backend
and prints the aggregate to stdout. Returns exit code 0 if all
scenarios pass, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys

from aria.cognitive.llm_eval.backends import LlmCliBackend
from aria.cognitive.llm_eval.eval_scenarios import load_default_scenarios
from aria.cognitive.llm_eval.harness import (
    EvalHarness,
    format_aggregate_human,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Grade ARIA's LLM (via the configured LLM CLI) against historical "
            "spacecraft-decision scenarios."
        ),
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit a JSON aggregate (still uses exit code for CI)",
    )
    parser.add_argument(
        "--scenario", default=None,
        help="Run only the scenario with this id (default: all).",
    )
    parser.add_argument(
        "--effort", default="high",
        help="LLM CLI effort level (low/medium/high/xhigh/max)",
    )
    parser.add_argument(
        "--timeout", type=float, default=240.0,
        help="Per-scenario timeout in seconds (default: 240)",
    )
    args = parser.parse_args(argv)

    backend = LlmCliBackend(
        effort=args.effort,
        timeout_s=args.timeout,
    )
    if not backend.is_available():
        print(
            "ERROR: LLM CLI not found on PATH; install before running.",
            file=sys.stderr,
        )
        return 2

    harness = EvalHarness(backend=backend)

    scenarios = load_default_scenarios()
    if args.scenario is not None:
        scenarios = tuple(
            scenario for scenario in scenarios
            if scenario.id == args.scenario
        )
        if not scenarios:
            print(f"ERROR: no scenario with id {args.scenario!r}",
                  file=sys.stderr)
            return 2

    aggregate = harness.run_all(scenarios)

    if args.json:
        print(json.dumps(aggregate.as_dict(), indent=2))
    else:
        print(format_aggregate_human(aggregate))

    return 0 if aggregate.failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
