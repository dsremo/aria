"""Audit orchestrator — file scan + diff scan + baseline tracking.

The Auditor walks a list of files (or a git diff), submits each to
the configured backend, parses findings, aggregates, and computes
NEW / RESOLVED / PERSISTING deltas against the persistent baseline
at ``data/runtime/code_audit/baseline.json``.

Design choices:
  * One file at a time to the LLM — keeps prompts focused and lets
    findings include precise line numbers without the LLM losing
    track across file boundaries.
  * Errors per-file captured into ``AuditFileResult.error`` instead
    of raised — one bad file should not abort the whole batch.
  * Baseline file is human-readable JSON. An operator can hand-edit
    it to mark findings as accepted-risk; future runs will track
    deltas against the edited baseline.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Tuple

import structlog

from aria.cognitive.code_audit.backends import (
    LlmCliAuditBackend,
    parse_findings_response,
)
from aria.cognitive.code_audit.findings import (
    AuditDigest,
    AuditFileResult,
    AuditFinding,
    Severity,
    aggregate_severity_counts,
)

logger = structlog.get_logger()


DEFAULT_BASELINE_PATH = Path(
    os.environ.get("ARIA_RUNTIME_DIR", "data/runtime")
) / "code_audit" / "baseline.json"


@dataclass
class Auditor:
    """Orchestrate code-audit runs against a configurable backend."""

    backend: Any = field(default_factory=LlmCliAuditBackend)
    repo_root: Path = field(default_factory=Path.cwd)
    baseline_path: Path = field(default_factory=lambda: DEFAULT_BASELINE_PATH)

    # ── Audit-one-file ─────────────────────────────────────────

    def audit_file(self, file_path: Path) -> AuditFileResult:
        path = Path(file_path)
        if not path.is_file():
            return AuditFileResult(
                file_path=str(path),
                elapsed_s=0.0,
                response_chars=0,
                findings=tuple(),
                error=f"file not found: {path}",
            )

        start = time.monotonic()
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return AuditFileResult(
                file_path=str(path),
                elapsed_s=time.monotonic() - start,
                response_chars=0,
                findings=tuple(),
                error=f"read failed: {exc}",
            )

        try:
            raw = self.backend.audit_text(
                file_path=str(path), content=content,
            )
        except Exception as exc:  # noqa: BLE001
            return AuditFileResult(
                file_path=str(path),
                elapsed_s=time.monotonic() - start,
                response_chars=0,
                findings=tuple(),
                error=f"{type(exc).__name__}: {exc}",
            )

        finding_dicts = parse_findings_response(raw)
        findings: List[AuditFinding] = []
        for d in finding_dicts:
            d = {**d, "file_path": str(path)}
            try:
                findings.append(AuditFinding.from_dict(d))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "code_audit.parse_finding_failed",
                    file=str(path),
                    error=str(exc),
                )
        return AuditFileResult(
            file_path=str(path),
            elapsed_s=time.monotonic() - start,
            response_chars=len(raw),
            findings=tuple(findings),
            error=None,
        )

    # ── Audit-many ─────────────────────────────────────────────

    def audit_files(
        self,
        files: Sequence[Path],
        *,
        compare_to_baseline: bool = True,
    ) -> AuditDigest:
        run_start = time.monotonic()
        results: List[AuditFileResult] = []
        for path in files:
            result = self.audit_file(path)
            results.append(result)

        all_findings = [
            f for r in results for f in r.findings
        ]
        counts = aggregate_severity_counts(all_findings)
        n_errors = sum(1 for r in results if r.error)

        # Baseline delta.
        baseline_compared = False
        new_findings: Tuple[AuditFinding, ...] = tuple()
        resolved: Tuple[AuditFinding, ...] = tuple()
        persisting: Tuple[AuditFinding, ...] = tuple()
        if compare_to_baseline:
            try:
                baseline = self._load_baseline()
                baseline_compared = True
                new_findings, resolved, persisting = _diff_against_baseline(
                    current=all_findings, baseline=baseline,
                )
            except Exception as exc:    # noqa: BLE001
                logger.warning(
                    "code_audit.baseline_load_failed", error=str(exc),
                )

        digest = AuditDigest(
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            backend_label=self.backend.label,
            files=tuple(results),
            total_findings=len(all_findings),
            n_critical=counts[Severity.CRITICAL],
            n_high=counts[Severity.HIGH],
            n_medium=counts[Severity.MEDIUM],
            n_low=counts[Severity.LOW],
            n_info=counts[Severity.INFO],
            n_errors=n_errors,
            elapsed_s=time.monotonic() - run_start,
            baseline_compared=baseline_compared,
            new_findings=new_findings,
            resolved_findings=resolved,
            persisting_findings=persisting,
        )
        return digest

    # ── Diff mode ──────────────────────────────────────────────

    def audit_diff(
        self,
        *,
        since_commit: str = "HEAD",
        compare_to_baseline: bool = True,
    ) -> AuditDigest:
        """Audit only the Python files changed since ``since_commit``."""
        files = self._files_changed_since(since_commit)
        return self.audit_files(
            files, compare_to_baseline=compare_to_baseline,
        )

    def _files_changed_since(self, ref: str) -> List[Path]:
        try:
            out = subprocess.check_output(
                ["git", "-C", str(self.repo_root),
                 "diff", "--name-only", ref],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            return []
        out_files: List[Path] = []
        for line in out.splitlines():
            line = line.strip()
            if not line.endswith(".py"):
                continue
            full = self.repo_root / line
            if full.is_file():
                out_files.append(full)
        return out_files

    # ── Baseline I/O ───────────────────────────────────────────

    def _load_baseline(self) -> List[AuditFinding]:
        if not self.baseline_path.is_file():
            return []
        try:
            payload = json.loads(
                self.baseline_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "code_audit.baseline_parse_failed", error=str(exc),
            )
            return []
        items = payload.get("findings", [])
        out: List[AuditFinding] = []
        for d in items:
            try:
                out.append(AuditFinding.from_dict(d))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def write_baseline(self, digest: AuditDigest) -> None:
        """Persist the current digest as the new baseline."""
        try:
            self.baseline_path.parent.mkdir(parents=True, exist_ok=True)
            findings = [f.as_dict() for f in digest.all_findings()]
            payload = {
                "timestamp_iso": digest.timestamp_iso,
                "backend_label": digest.backend_label,
                "n_findings": len(findings),
                "findings": findings,
            }
            tmp = self.baseline_path.with_suffix(
                self.baseline_path.suffix + ".tmp",
            )
            tmp.write_text(
                json.dumps(payload, indent=2), encoding="utf-8",
            )
            os.replace(tmp, self.baseline_path)
        except OSError as exc:
            logger.warning(
                "code_audit.baseline_write_failed", error=str(exc),
            )


# ── Delta logic ─────────────────────────────────────────────────


def _diff_against_baseline(
    *, current: List[AuditFinding], baseline: List[AuditFinding],
) -> Tuple[
    Tuple[AuditFinding, ...],
    Tuple[AuditFinding, ...],
    Tuple[AuditFinding, ...],
]:
    """Compute (new, resolved, persisting)."""
    cur_by_id = {f.stable_id: f for f in current}
    base_by_id = {f.stable_id: f for f in baseline}

    new_ids = set(cur_by_id) - set(base_by_id)
    resolved_ids = set(base_by_id) - set(cur_by_id)
    persisting_ids = set(cur_by_id) & set(base_by_id)

    return (
        tuple(cur_by_id[i] for i in sorted(new_ids)),
        tuple(base_by_id[i] for i in sorted(resolved_ids)),
        tuple(cur_by_id[i] for i in sorted(persisting_ids)),
    )
