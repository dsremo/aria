"""R342 — Cross-runner orchestrator.

Threat: with R51 + R101 + R151 + R201 + R251 + R301 + R351 separate
runners, operators forget to invoke one and miss its blast-radius
report.  A single orchestration call simplifies the workflow and
avoids drift between runners.

Defence: ``run_all`` invokes every adversarial runner in sequence,
returns a consolidated report with per-runner pass/fail counts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r342")


def _try_runner(runner_id: str, run_callable: Callable[[], object]) -> Tuple[int, int, str]:
    """Returns (caught, total, error_message).

    R51's runner pre-dates the ``caught`` attribute and exposes ``fired``
    instead; honour both so the consolidated report is meaningful across
    every adversarial-runner generation (audit-cleanup polish).
    """
    try:
        report = run_callable()
        results = getattr(report, "results", None)
        total = len(results) if results else 0
        caught = getattr(report, "caught", None)
        if caught is None:
            caught = getattr(report, "fired", 0)
        # Some legacy reports stored boolean ``fired`` per probe under
        # a different key — fall back to counting the truthy result.
        if not caught and results:
            for r in results:
                if isinstance(r, dict) and (r.get("caught") or r.get("fired")):
                    caught += 1
        return caught, total, ""
    except Exception as exc:
        logger.warning("r342.runner_failed runner=%s exc=%s", runner_id, exc)
        return 0, 0, f"{type(exc).__name__}:{exc}"


@dataclass
class ConsolidatedReport:
    per_runner: Dict[str, Dict[str, object]] = field(default_factory=dict)

    @property
    def total_caught(self) -> int:
        return sum(int(v.get("caught", 0)) for v in self.per_runner.values())

    @property
    def total_probes(self) -> int:
        return sum(int(v.get("total", 0)) for v in self.per_runner.values())

    @property
    def all_pass(self) -> bool:
        return all(v.get("caught", 0) == v.get("total", 0) and not v.get("error")
                   for v in self.per_runner.values())


def run_all() -> ConsolidatedReport:
    from aria.security.guard import activate_all_rounds
    activate_all_rounds(force_reload=True)

    report = ConsolidatedReport()

    runners = [
        ("R51", _runner_r51),
        ("R101", _runner_r101),
        ("R151", _runner_r151),
        ("R201", _runner_r201),
        ("R251", _runner_r251),
        ("R301", _runner_r301),
        ("R351", _runner_r351),
    ]
    for runner_id, fn in runners:
        caught, total, error = _try_runner(runner_id, fn)
        report.per_runner[runner_id] = {
            "caught": caught, "total": total, "error": error,
        }
    return report


def render_consolidated(report: ConsolidatedReport) -> str:
    lines = [
        "# R342 — consolidated runner sweep",
        f"caught: {report.total_caught}/{report.total_probes}; "
        f"all_pass: {report.all_pass}",
        "",
        "| Runner | Caught | Total | Error |",
        "|--------|--------|-------|-------|",
    ]
    for runner_id, info in report.per_runner.items():
        lines.append(
            f"| {runner_id} | {info.get('caught')} | {info.get('total')} | "
            f"{info.get('error') or '—'} |"
        )
    return "\n".join(lines)


def _runner_r51():
    from aria.security.rounds.r51_adversarial_runner import run as run_v1
    return run_v1()


def _runner_r101():
    from aria.security.rounds.r101_adversarial_runner_v2 import run_v2
    return run_v2()


def _runner_r151():
    from aria.security.rounds.r151_adversarial_runner_v3 import run_v3
    return run_v3()


def _runner_r201():
    from aria.security.rounds.r201_adversarial_runner_v4 import run_v4
    return run_v4()


def _runner_r251():
    from aria.security.rounds.r251_adversarial_runner_v5 import run_v5
    return run_v5()


def _runner_r301():
    from aria.security.rounds.r301_adversarial_runner_v6 import run_v6
    return run_v6()


def _runner_r351():
    from aria.security.rounds.r351_adversarial_runner_v7 import run_v7
    return run_v7()


register(DefencePlugin(
    round_id="R342",
    name="runner_orchestrator",
    description="Single entry-point that runs every adversarial runner v1-v7 + consolidated report.",
))
