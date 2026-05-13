from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from aria.security.supply_chain.creds_scan import (
    DEFAULT_PATTERNS,
    format_creds_report_human,
    scan_files,
)
from aria.security.supply_chain.sbom import (
    SbomBuildError,
    generate_cyclonedx_sbom,
    summarise_sbom,
)
from aria.security.supply_chain.vuln_gate import (
    PipAuditError,
    format_vuln_report_human,
    run_pip_audit,
)


def _cmd_sbom(args: argparse.Namespace) -> int:
    output_path = Path(args.output)
    pyproject = Path(args.pyproject) if args.pyproject else None
    try:
        result = generate_cyclonedx_sbom(
            output_path=output_path,
            pyproject_path=pyproject,
            timeout_s=args.timeout,
        )
    except SbomBuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = summarise_sbom(result.sbom_path)
    if args.emit_json:
        print(json.dumps({
            "sbom_path": str(result.sbom_path),
            "sha256": result.sha256_hex,
            "n_components": result.n_components,
            "spec_version": summary.get("spec_version"),
            "by_license": summary.get("by_license"),
        }, indent=2))
    else:
        print(f"SBOM written: {result.sbom_path}")
        print(f"  format:        {result.sbom_format}")
        print(f"  components:    {result.n_components}")
        print(f"  sha256:        {result.sha256_hex}")
        print(f"  by license:")
        for label, count in sorted(
            summary.get("by_license", {}).items(),
            key=lambda kv: -kv[1],
        )[:10]:
            print(f"    {label:30s} {count}")
    return 0


def _cmd_vuln(args: argparse.Namespace) -> int:
    try:
        report = run_pip_audit(
            requirements_file=args.requirements,
            local_only=not args.requirements,
            timeout_s=args.timeout,
        )
    except PipAuditError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.emit_json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(format_vuln_report_human(report))
    if args.fail_on_high_or_critical:
        if report.filter_severity({"HIGH", "CRITICAL"}):
            return 1
    if args.fail_on_any:
        if report.vulnerabilities:
            return 1
    return 0


def _cmd_creds(args: argparse.Namespace) -> int:
    paths = [Path(p) for p in args.paths] if args.paths else [Path.cwd()]
    report = scan_files(
        paths,
        patterns=DEFAULT_PATTERNS,
        detect_entropy=not args.no_entropy,
    )
    if args.emit_json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(format_creds_report_human(report))
    if args.fail_on_high_or_critical:
        critical_count = sum(
            1 for finding in report.findings
            if finding.severity in ("CRITICAL", "HIGH")
        )
        if critical_count:
            return 1
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m aria.security.supply_chain",
        description=(
            "ARIA supply-chain hardening: SBOM export, dependency-vulnerability "
            "scan, and credentials-leak detection. Default exit 0; use the "
            "--fail-on-* flags to opt into nonzero exit for CI gates."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_sbom = sub.add_parser("sbom", help="Generate a CycloneDX SBOM")
    p_sbom.add_argument(
        "--output", default="dist/sbom-cyclonedx.json",
        help="Path to write the SBOM JSON",
    )
    p_sbom.add_argument(
        "--pyproject", default=None,
        help="Path to pyproject.toml (for richer metadata)",
    )
    p_sbom.add_argument("--timeout", type=float, default=120.0)
    p_sbom.add_argument("--json", dest="emit_json", action="store_true")
    p_sbom.set_defaults(func=_cmd_sbom)

    p_vuln = sub.add_parser("vuln", help="Run pip-audit against the env")
    p_vuln.add_argument(
        "--requirements", default=None,
        help="Audit a requirements file instead of the local environment",
    )
    p_vuln.add_argument("--timeout", type=float, default=180.0)
    p_vuln.add_argument(
        "--fail-on-high-or-critical", action="store_true",
        help="Exit 1 if any HIGH/CRITICAL vulnerabilities present",
    )
    p_vuln.add_argument(
        "--fail-on-any", action="store_true",
        help="Exit 1 if any vulnerabilities present (any severity)",
    )
    p_vuln.add_argument("--json", dest="emit_json", action="store_true")
    p_vuln.set_defaults(func=_cmd_vuln)

    p_creds = sub.add_parser("creds", help="Scan for committed secrets")
    p_creds.add_argument(
        "paths", nargs="*",
        help="Files / directories to scan (default: current directory)",
    )
    p_creds.add_argument(
        "--no-entropy", action="store_true",
        help="Disable Shannon-entropy heuristic; use regex patterns only",
    )
    p_creds.add_argument(
        "--fail-on-high-or-critical", action="store_true",
        help="Exit 1 if any HIGH/CRITICAL findings present",
    )
    p_creds.add_argument("--json", dest="emit_json", action="store_true")
    p_creds.set_defaults(func=_cmd_creds)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
