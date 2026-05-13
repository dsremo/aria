"""Production-validation aggregator — one PASS/FAIL gate.

Runs every published-record replay validator ARIA ships with and
reports a single structured summary. Designed to be the
deployability gate: if this passes, ARIA's orbital-mechanics +
propulsion stack reproduces every historical mission for which
we have a published reference, within stated tolerance.

Replays included
----------------
  * Apollo 11 (AS-506) launch-to-TLI    (saturn_v_replay)
  * Apollo 11 EDL + Δv per phase         (apollo_replay)
  * Artemis II planned profile           (artemis2_replay)
  * Iridium-Cosmos 2009 conjunction TCA  (iridium_cosmos_replay)
  * Soyuz 6-hour rendezvous DV1..DV6     (r48_extensions Soyuz)
  * Historical conjunctions (12 events)  (historical_conjunctions)

Usage
-----
  python -m tools.run_production_validation             # full run
  python -m tools.run_production_validation --json      # JSON output
  python -m tools.run_production_validation --quick     # subset

Exit codes
----------
  0 — every replay passed within tolerance
  1 — at least one replay failed
  2 — internal error (e.g. test file missing)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ReplayValidator:
    """One validator + its test path + the historical reference."""

    name: str
    test_path: str          # relative to repo root
    reference: str          # short citation for the historical record
    description: str
    quick: bool = True      # included in --quick mode?


VALIDATORS: List[ReplayValidator] = [
    ReplayValidator(
        name="saturn_v_apollo_11",
        test_path="tests/integration/test_saturn_v_replay.py",
        reference="MSC-04112; NASA SP-4029 Orloff 2000",
        description="Saturn V launch-to-TLI flight profile (AS-506)",
    ),
    ReplayValidator(
        name="apollo_11_dv_phases",
        test_path="tests/integration/test_apollo_replay.py",
        reference="NASA SP-4029 (Orloff 2000) Apollo by the Numbers",
        description="Apollo 11 propulsive Δv per phase + EDL peak g",
    ),
    ReplayValidator(
        name="artemis_2_planned",
        test_path="tests/integration/test_artemis2_replay.py",
        reference="NASA SLS Mission Booklet Artemis II",
        description="Artemis II TLI / OPF / mid-course Δv budget",
    ),
    ReplayValidator(
        name="iridium_cosmos_2009",
        test_path="tests/integration/test_iridium_cosmos_replay.py",
        reference="Wang 2010; JSpOC reconstruction",
        description="Iridium-Cosmos 2009-02-10 collision TCA + miss",
    ),
    ReplayValidator(
        name="soyuz_6h_rendezvous",
        test_path="tests/integration/test_r48_extensions.py",
        reference="Roscosmos 4-orbit profile DV1..DV6",
        description="Soyuz 6-hour rendezvous Δv reconstruction",
        quick=False,
    ),
    ReplayValidator(
        name="historical_conjunctions",
        test_path="tests/integration/test_historical_conjunctions.py",
        reference="12-event catalog (Cerise 1996 → CZ-5B 2022)",
        description="12 historical conjunction events deterministic mode",
        quick=False,
    ),
]


@dataclass
class ReplayResult:
    name: str
    passed: bool
    duration_s: float
    test_path: str
    reference: str
    description: str
    failure_summary: Optional[str] = None
    n_passed: int = 0
    n_failed: int = 0
    n_skipped: int = 0
    n_errors: int = 0


@dataclass
class AggregateResult:
    total_validators: int
    passed_validators: int
    failed_validators: int
    duration_s: float
    timestamp_iso: str
    results: List[ReplayResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return self.failed_validators == 0

    def as_dict(self) -> dict:
        return {
            "total_validators": self.total_validators,
            "passed_validators": self.passed_validators,
            "failed_validators": self.failed_validators,
            "duration_s": round(self.duration_s, 2),
            "timestamp_iso": self.timestamp_iso,
            "all_passed": self.all_passed,
            "results": [asdict(r) for r in self.results],
        }


def _run_one(validator: ReplayValidator) -> ReplayResult:
    """Run a single validator's test file and parse the result."""
    test_full = REPO_ROOT / validator.test_path
    if not test_full.is_file():
        return ReplayResult(
            name=validator.name,
            passed=False,
            duration_s=0.0,
            test_path=validator.test_path,
            reference=validator.reference,
            description=validator.description,
            failure_summary=f"test file not found: {validator.test_path}",
        )

    start = time.monotonic()
    try:
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest", str(test_full),
                "-q", "--tb=short", "--no-header",
                "-p", "no:cacheprovider",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return ReplayResult(
            name=validator.name,
            passed=False,
            duration_s=time.monotonic() - start,
            test_path=validator.test_path,
            reference=validator.reference,
            description=validator.description,
            failure_summary="timeout exceeded 10 min",
        )

    duration_s = time.monotonic() - start
    n_passed, n_failed, n_skipped, n_errors = _parse_pytest_summary(proc.stdout)
    failure_summary = None
    if proc.returncode != 0:
        # Show last few lines of pytest output for the failure message.
        lines = proc.stdout.strip().splitlines()
        failure_summary = "\n".join(lines[-15:]) if lines else proc.stderr[:500]

    return ReplayResult(
        name=validator.name,
        passed=(proc.returncode == 0),
        duration_s=duration_s,
        test_path=validator.test_path,
        reference=validator.reference,
        description=validator.description,
        failure_summary=failure_summary,
        n_passed=n_passed,
        n_failed=n_failed,
        n_skipped=n_skipped,
        n_errors=n_errors,
    )


def _parse_pytest_summary(output: str) -> tuple[int, int, int, int]:
    """Extract pass/fail/skip/error counts from a pytest -q summary line."""
    n_passed = n_failed = n_skipped = n_errors = 0
    for line in output.strip().splitlines():
        line = line.strip()
        if " passed" in line or " failed" in line or " error" in line:
            # Lines like: "11 passed, 2 skipped in 0.29s"
            parts = line.replace(",", "").split()
            for i, token in enumerate(parts):
                if not token.isdigit():
                    continue
                value = int(token)
                next_word = parts[i + 1] if i + 1 < len(parts) else ""
                if next_word.startswith("passed"):
                    n_passed = max(n_passed, value)
                elif next_word.startswith("failed"):
                    n_failed = max(n_failed, value)
                elif next_word.startswith("skipped"):
                    n_skipped = max(n_skipped, value)
                elif next_word.startswith("error"):
                    n_errors = max(n_errors, value)
    return n_passed, n_failed, n_skipped, n_errors


def run_all(quick: bool = False) -> AggregateResult:
    chosen = [validator for validator in VALIDATORS if (not quick or validator.quick)]
    aggregate_start = time.monotonic()
    results: List[ReplayResult] = []
    for validator in chosen:
        results.append(_run_one(validator))

    return AggregateResult(
        total_validators=len(chosen),
        passed_validators=sum(1 for r in results if r.passed),
        failed_validators=sum(1 for r in results if not r.passed),
        duration_s=time.monotonic() - aggregate_start,
        timestamp_iso=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        results=results,
    )


def _print_human(aggregate: AggregateResult) -> None:
    print()
    print("=" * 78)
    print("ARIA — Production Validation (replay against published records)")
    print("=" * 78)
    for result in aggregate.results:
        status = "PASS" if result.passed else "FAIL"
        marker = "✓" if result.passed else "✗"
        print(
            f"  [{status}] {marker} {result.name:35s} "
            f"{result.n_passed:3d} pass / "
            f"{result.n_failed:3d} fail / "
            f"{result.n_skipped:3d} skip   "
            f"{result.duration_s:6.2f}s"
        )
        print(f"           ref: {result.reference}")
        print(f"           {result.description}")
        if result.failure_summary and not result.passed:
            print(f"     >> last lines of pytest output:")
            for tail_line in result.failure_summary.splitlines()[-10:]:
                print(f"         {tail_line}")
        print()
    print("-" * 78)
    overall = "PASS" if aggregate.all_passed else "FAIL"
    print(
        f"  Overall: {overall}  "
        f"({aggregate.passed_validators}/{aggregate.total_validators} validators, "
        f"{aggregate.duration_s:.1f}s total)"
    )
    print("=" * 78)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run all ARIA replay validators against historical records.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit a JSON summary (still uses exit codes for CI)",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Quick subset only (skips long-running historical-conjunctions + Soyuz)",
    )
    args = parser.parse_args()

    aggregate = run_all(quick=args.quick)
    if args.json:
        print(json.dumps(aggregate.as_dict(), indent=2))
    else:
        _print_human(aggregate)

    return 0 if aggregate.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
