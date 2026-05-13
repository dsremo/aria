from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional


PIP_AUDIT_BIN = "pip-audit"
DEFAULT_TIMEOUT_S = 180.0


@dataclass(frozen=True)
class Vulnerability:
    package: str
    installed_version: str
    vuln_id: str
    aliases: tuple[str, ...] = ()
    fix_versions: tuple[str, ...] = ()
    description: str = ""
    severity: str = "UNKNOWN"


@dataclass(frozen=True)
class VulnReport:
    vulnerabilities: tuple[Vulnerability, ...] = ()
    n_dependencies_scanned: int = 0
    skipped: tuple[dict[str, Any], ...] = ()
    raw_json: Optional[dict[str, Any]] = None

    @property
    def n_total(self) -> int:
        return len(self.vulnerabilities)

    def by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for vuln in self.vulnerabilities:
            counts[vuln.severity] = counts.get(vuln.severity, 0) + 1
        return counts

    def filter_severity(self, severities: Iterable[str]) -> tuple[Vulnerability, ...]:
        wanted = {s.upper() for s in severities}
        return tuple(
            vuln for vuln in self.vulnerabilities
            if vuln.severity.upper() in wanted
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_dependencies_scanned": self.n_dependencies_scanned,
            "n_vulnerabilities": self.n_total,
            "by_severity": self.by_severity(),
            "skipped": list(self.skipped),
            "vulnerabilities": [
                {
                    "package": vuln.package,
                    "installed_version": vuln.installed_version,
                    "vuln_id": vuln.vuln_id,
                    "aliases": list(vuln.aliases),
                    "fix_versions": list(vuln.fix_versions),
                    "severity": vuln.severity,
                    "description": vuln.description,
                }
                for vuln in self.vulnerabilities
            ],
        }


def _classify_severity(description: str, aliases: Iterable[str]) -> str:
    blob = description.upper()
    for alias in aliases:
        blob = blob + " " + alias.upper()
    if any(token in blob for token in ("CRITICAL", "RCE", "REMOTE CODE EXECUTION")):
        return "CRITICAL"
    if any(token in blob for token in ("HIGH", "PRIVILEGE ESCALATION", "ARBITRARY CODE")):
        return "HIGH"
    if any(token in blob for token in ("MEDIUM", "DOS", "DENIAL OF SERVICE")):
        return "MEDIUM"
    if any(token in blob for token in ("LOW", "INFO")):
        return "LOW"
    return "UNKNOWN"


def parse_pip_audit_output(raw_json: dict[str, Any]) -> VulnReport:
    dependencies = raw_json.get("dependencies") or []
    vulnerabilities: list[Vulnerability] = []
    skipped: list[dict[str, Any]] = []

    for dep in dependencies:
        if not isinstance(dep, dict):
            continue
        if dep.get("skip_reason"):
            skipped.append({
                "name": dep.get("name", ""),
                "reason": dep.get("skip_reason", ""),
            })
            continue
        package = dep.get("name", "")
        version = dep.get("version", "")
        for vuln in dep.get("vulns") or []:
            if not isinstance(vuln, dict):
                continue
            aliases = tuple(vuln.get("aliases") or ())
            description = vuln.get("description") or ""
            fix_versions = tuple(vuln.get("fix_versions") or ())
            severity = _classify_severity(description, aliases)
            vulnerabilities.append(
                Vulnerability(
                    package=package,
                    installed_version=version,
                    vuln_id=vuln.get("id") or "UNKNOWN",
                    aliases=aliases,
                    fix_versions=fix_versions,
                    description=description,
                    severity=severity,
                )
            )

    return VulnReport(
        vulnerabilities=tuple(vulnerabilities),
        n_dependencies_scanned=len(dependencies),
        skipped=tuple(skipped),
        raw_json=raw_json,
    )


class PipAuditError(RuntimeError):
    pass


def run_pip_audit(
    *,
    requirements_file: Optional[str] = None,
    local_only: bool = True,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    extra_args: Optional[list[str]] = None,
) -> VulnReport:
    binary = shutil.which(PIP_AUDIT_BIN)
    if binary is None:
        raise PipAuditError("pip-audit not on PATH; install with `pip install pip-audit`")

    cmd: list[str] = [binary, "--format", "json", "--progress-spinner", "off"]
    if local_only and requirements_file is None:
        cmd.append("--local")
    if requirements_file is not None:
        cmd.extend(["--requirement", requirements_file])
    if extra_args:
        cmd.extend(extra_args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PipAuditError(f"pip-audit timed out after {timeout_s}s") from exc

    if result.returncode not in (0, 1):
        raise PipAuditError(
            f"pip-audit exit {result.returncode}: {result.stderr.strip()[:400]}"
        )

    if not result.stdout.strip():
        return VulnReport()

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PipAuditError(
            f"pip-audit emitted non-JSON: {result.stdout[:200]}"
        ) from exc
    return parse_pip_audit_output(payload)


def format_vuln_report_human(report: VulnReport) -> str:
    lines: list[str] = []
    lines.append("Vulnerability scan (pip-audit)")
    lines.append("─" * 50)
    lines.append(f"Dependencies scanned:  {report.n_dependencies_scanned}")
    lines.append(f"Vulnerabilities found: {report.n_total}")
    sev_counts = report.by_severity()
    if sev_counts:
        for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"):
            count = sev_counts.get(severity, 0)
            if count:
                lines.append(f"  {severity:8s} {count}")
    if report.skipped:
        lines.append(f"Skipped: {len(report.skipped)}")
    lines.append("")
    if not report.vulnerabilities:
        lines.append("(clean)")
        return "\n".join(lines)
    for vuln in report.vulnerabilities[:50]:
        lines.append(
            f"  {vuln.severity:8s} {vuln.package}=={vuln.installed_version} "
            f"{vuln.vuln_id}"
        )
        if vuln.fix_versions:
            lines.append(f"           fix: {', '.join(vuln.fix_versions)}")
        if vuln.description:
            snippet = vuln.description.replace("\n", " ")[:140]
            lines.append(f"           {snippet}")
    if len(report.vulnerabilities) > 50:
        lines.append(f"  ... and {len(report.vulnerabilities) - 50} more")
    return "\n".join(lines)
