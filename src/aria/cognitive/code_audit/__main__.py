"""CLI: python -m aria.cognitive.code_audit

Modes:
  --diff           audit only files changed since HEAD (default ref)
  --since-commit   audit files changed since <ref>
  --files PATH...  audit specific paths
  --update-baseline  treat the current run's findings as the new baseline

Output:
  Default: human-readable digest to stdout
  --json   machine-readable JSON
  --markdown  markdown digest

Exit codes:
  0  default — always, regardless of findings (safe for cron / CI inboxes)
  2  internal error (e.g. backend unavailable)

Pass --fail-on-new-high to opt into exit 1 when a new HIGH/CRITICAL
finding is introduced; intended for environments that explicitly want
a hard gate (and have arranged not to email on it).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aria.cognitive.code_audit.auditor import Auditor
from aria.cognitive.code_audit.backends import LlmCliAuditBackend
from aria.cognitive.code_audit.findings import AuditDigest, Severity
from aria.cognitive.code_audit.format import (
    format_digest_human,
    format_digest_markdown,
)


def _has_new_high_or_critical(digest: AuditDigest) -> bool:
    return any(
        f.severity in (Severity.CRITICAL, Severity.HIGH)
        for f in digest.new_findings
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run ARIA's continuous AI code-audit harness over a set "
            "of Python files. Backend defaults to the LLM CLI."
        ),
    )
    grp = parser.add_mutually_exclusive_group(required=False)
    grp.add_argument(
        "--diff", action="store_true",
        help="Audit files changed since HEAD (default).",
    )
    grp.add_argument(
        "--since-commit", type=str, default=None,
        help="Audit files changed since the given git ref (e.g. HEAD~5, main).",
    )
    grp.add_argument(
        "--files", nargs="+", default=None,
        help="Audit specific Python files.",
    )
    parser.add_argument(
        "--effort", default="high",
        help="the LLM CLI effort level (low/medium/high/xhigh/max)",
    )
    parser.add_argument(
        "--timeout", type=float, default=240.0,
        help="Per-file timeout in seconds (default 240).",
    )
    parser.add_argument(
        "--update-baseline", action="store_true",
        help=(
            "Treat the run output as the new baseline (overwrites "
            "data/runtime/code_audit/baseline.json). Use when you've "
            "triaged the current findings and want to start tracking "
            "deltas from this point."
        ),
    )
    parser.add_argument(
        "--no-baseline", action="store_true",
        help="Don't compare against the baseline; report raw findings only.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON.",
    )
    parser.add_argument(
        "--markdown", action="store_true",
        help="Emit markdown digest.",
    )
    parser.add_argument(
        "--repo-root", default=".",
        help="Repository root for git-diff resolution (default: cwd).",
    )
    parser.add_argument(
        "--fail-on-new-high", action="store_true",
        help=(
            "Exit 1 when a NEW HIGH/CRITICAL finding is introduced. "
            "Off by default so cron / CI mailers stay quiet."
        ),
    )
    args = parser.parse_args(argv)

    backend = LlmCliAuditBackend(
        effort=args.effort,
        timeout_s=args.timeout,
    )
    if not backend.is_available():
        print(
            "ERROR: LLM CLI not on PATH; install before running.",
            file=sys.stderr,
        )
        return 2

    auditor = Auditor(
        backend=backend,
        repo_root=Path(args.repo_root).resolve(),
    )

    compare_to_baseline = not args.no_baseline

    if args.files:
        files = [Path(p) for p in args.files]
        digest = auditor.audit_files(
            files, compare_to_baseline=compare_to_baseline,
        )
    elif args.since_commit:
        digest = auditor.audit_diff(
            since_commit=args.since_commit,
            compare_to_baseline=compare_to_baseline,
        )
    else:
        # default: --diff
        digest = auditor.audit_diff(
            since_commit="HEAD",
            compare_to_baseline=compare_to_baseline,
        )

    # Emit.
    if args.json:
        print(json.dumps(digest.as_dict(), indent=2))
    elif args.markdown:
        print(format_digest_markdown(digest))
    else:
        print(format_digest_human(digest))

    if args.update_baseline:
        auditor.write_baseline(digest)
        print(f"\n[baseline updated → {auditor.baseline_path}]",
              file=sys.stderr)

    if args.fail_on_new_high and _has_new_high_or_critical(digest):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
