from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from aria.cognitive.doctrine import DoctrineLoader
from aria.knowledge import build_default_lesson_index
from aria.replay import (
    LlmCliAdvisor,
    ClosedLoop,
    StubAdvisor,
    StubCrossMonitor,
    WindowedZScoreDetector,
    get_scenario,
    list_scenarios,
)
from aria.replay.audit_log import AuditLogger, loop_outcome_to_event
from aria.replay.noise import overlay_noise


def _format_get(get_seconds: float) -> str:
    total = int(get_seconds)
    sign = "-" if total < 0 else ""
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def _print_outcome(index: int, outcome) -> None:
    print(f"\n[{index:02d}]  GET={outcome.anomaly.get_string()}  "
          f"{outcome.anomaly.parameter}  "
          f"score={outcome.anomaly.score:.2f}  sev={outcome.anomaly.severity}")
    if outcome.advisor:
        print(f"     advisor: {outcome.advisor.proposed_action}  "
              f"conf={outcome.advisor.confidence:.2f}  "
              f"({outcome.elapsed_advisor_s:.1f}s)")
        print(f"     rationale: {outcome.advisor.rationale[:120]}")
    if outcome.translation:
        print(f"     translation: {outcome.translation.status}  "
              f"hal={outcome.translation.hal_command.primitive if outcome.translation.hal_command else 'none'}")
        if outcome.translation.residual_reason:
            print(f"     residual: {outcome.translation.residual_reason[:120]}")
    if outcome.monitor:
        print(f"     monitor: {outcome.monitor.decision}  "
              f"({outcome.monitor.reason[:120]})")
    if outcome.hal_command:
        print(f"     APPLIED: {outcome.hal_command}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m aria.replay",
        description=(
            "ARIA replay-driver console. Run a historical scenario through "
            "the anomaly → advisor → monitor → HAL chain and print the "
            "decisions made at each step."
        ),
    )
    parser.add_argument(
        "--scenario", choices=list(list_scenarios()), default="apollo_13_cryo_stir",
    )
    parser.add_argument(
        "--advisor", choices=("stub", "claude"), default="stub",
    )
    parser.add_argument(
        "--effort", default="low",
        help="the LLM CLI effort level (low/medium/high/xhigh/max)",
    )
    parser.add_argument(
        "--with-doctrine", action="store_true",
        help="Load data/doctrine/*.json into the LLM context",
    )
    parser.add_argument(
        "--with-lessons", action="store_true",
        help="Build TF-IDF index over curated lessons and inject relevant ones into the LLM prompt",
    )
    parser.add_argument(
        "--z", type=float, default=3.5,
        help="Z-score threshold for anomaly detection",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List available scenarios and exit",
    )
    parser.add_argument(
        "--json", dest="emit_json", action="store_true",
        help="Emit machine-readable JSON instead of human text",
    )
    parser.add_argument(
        "--noise", action="store_true",
        help="Overlay sensor noise on the synthetic telemetry stream",
    )
    parser.add_argument(
        "--audit-log", default=None,
        help="Append JSON-line outcome events to this file",
    )
    args = parser.parse_args(argv)

    if args.list:
        for scenario_id in list_scenarios():
            scenario = get_scenario(scenario_id)
            print(f"{scenario_id:32s} {scenario.title}  ({scenario.date_iso})")
        return 0

    scenario = get_scenario(args.scenario)
    if args.advisor == "claude":
        advisor = LlmCliAdvisor(effort=args.effort, timeout_s=120.0)
    else:
        advisor = StubAdvisor()
    bundle = None
    if args.with_doctrine:
        bundle = DoctrineLoader(Path("data/doctrine")).load()
    lesson_index = build_default_lesson_index() if args.with_lessons else None
    applied: list[str] = []
    loop = ClosedLoop(
        detector=WindowedZScoreDetector(
            parameters=scenario.parameters,
            window_size=15, warmup_samples=5, z_threshold=args.z,
        ),
        advisor=advisor,
        monitor=StubCrossMonitor(),
        hal_apply_fn=lambda primitive, verdict: applied.append(primitive),
        doctrine_bundle=bundle,
        lesson_index=lesson_index,
    )

    if not args.emit_json:
        print(f"=== {scenario.title} ===")
        print(f"Date: {scenario.date_iso}")
        print(f"Description: {scenario.description}")
        print(f"Parameters: {', '.join(scenario.parameters)}")
        print(f"Historical alarm at GET={_format_get(scenario.historical_alarm_get_s)}")
        print(f"Historical response at GET={_format_get(scenario.historical_response_get_s)}")
        print(f"Advisor: {advisor.label}; doctrine={'yes' if bundle else 'no'}")
        print()

    samples = scenario.samples_factory()
    if args.noise:
        samples = overlay_noise(samples)
    audit_logger: Optional[AuditLogger] = None
    if args.audit_log:
        audit_logger = AuditLogger(path=Path(args.audit_log))
    for sample in samples:
        outcome = loop.step(sample)
        if outcome is not None and audit_logger is not None:
            audit_logger.write_event(loop_outcome_to_event(outcome, scenario.scenario_id))
    if audit_logger is not None:
        audit_logger.close()

    if args.emit_json:
        payload = {
            "scenario_id": scenario.scenario_id,
            "n_outcomes": len(loop.outcomes),
            "first_anomaly_get_s": loop.first_anomaly_get_s(),
            "historical_alarm_get_s": scenario.historical_alarm_get_s,
            "applied_commands": list(applied),
            "residual_log": list(loop.residual_log),
            "outcomes": [
                {
                    "get_s": outcome.anomaly.detected_at_get_s,
                    "parameter": outcome.anomaly.parameter,
                    "score": outcome.anomaly.score,
                    "severity": outcome.anomaly.severity,
                    "proposed_action": outcome.advisor.proposed_action if outcome.advisor else None,
                    "confidence": outcome.advisor.confidence if outcome.advisor else None,
                    "monitor_decision": outcome.monitor.decision if outcome.monitor else None,
                    "translation_status": outcome.translation.status if outcome.translation else None,
                    "hal_applied": outcome.hal_command,
                }
                for outcome in loop.outcomes
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        for index, outcome in enumerate(loop.outcomes, start=1):
            _print_outcome(index, outcome)
        print(f"\n=== summary ===")
        print(f"outcomes: {len(loop.outcomes)}")
        print(f"hal commands applied: {len(applied)}")
        print(f"residual entries: {len(loop.residual_log)}")
        first = loop.first_anomaly_get_s()
        if first is not None:
            lead = scenario.historical_alarm_get_s - first
            print(f"first anomaly GET={_format_get(first)}; lead vs historical alarm = {lead:.0f}s")

    return 0


if __name__ == "__main__":
    sys.exit(main())
