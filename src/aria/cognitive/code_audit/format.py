"""Markdown + human-text formatters for AuditDigest output."""

from __future__ import annotations

from typing import List

from aria.cognitive.code_audit.findings import (
    AuditDigest,
    AuditFinding,
    Severity,
)


def format_digest_human(digest: AuditDigest) -> str:
    lines: List[str] = []
    lines.append("=" * 78)
    lines.append(f"ARIA — Code Audit Digest  ({digest.backend_label})")
    lines.append(f"Run at: {digest.timestamp_iso}")
    lines.append(f"Elapsed: {digest.elapsed_s:.1f}s; "
                 f"files: {len(digest.files)}; "
                 f"errors: {digest.n_errors}")
    lines.append("=" * 78)
    lines.append("")
    lines.append("Severity histogram:")
    lines.append(f"  CRITICAL: {digest.n_critical:3d}")
    lines.append(f"  HIGH:     {digest.n_high:3d}")
    lines.append(f"  MEDIUM:   {digest.n_medium:3d}")
    lines.append(f"  LOW:      {digest.n_low:3d}")
    lines.append(f"  INFO:     {digest.n_info:3d}")
    lines.append(f"  total:    {digest.total_findings:3d}")
    lines.append("")

    if digest.baseline_compared:
        lines.append(f"Baseline delta:")
        lines.append(f"  NEW:        {len(digest.new_findings):3d}  "
                     "(introduced since last run — review!)")
        lines.append(f"  RESOLVED:   {len(digest.resolved_findings):3d}  "
                     "(fixed since last run)")
        lines.append(f"  PERSISTING: {len(digest.persisting_findings):3d}  "
                     "(still open from last run)")
        lines.append("")

    if digest.new_findings:
        lines.append("─── NEW FINDINGS (introduced this run) ───")
        for f in sorted(
            digest.new_findings, key=lambda x: -x.severity.rank,
        ):
            lines.append(_format_finding_line(f))
        lines.append("")

    if digest.persisting_findings:
        critical_persist = [
            f for f in digest.persisting_findings
            if f.severity in (Severity.CRITICAL, Severity.HIGH)
        ]
        if critical_persist:
            lines.append("─── PERSISTING HIGH/CRITICAL ───")
            for f in sorted(
                critical_persist, key=lambda x: -x.severity.rank,
            ):
                lines.append(_format_finding_line(f))
            lines.append("")

    if digest.n_errors:
        lines.append("─── FILE-LEVEL ERRORS ───")
        for fr in digest.files:
            if fr.error:
                lines.append(f"  [ERR] {fr.file_path}: {fr.error}")
        lines.append("")

    lines.append("=" * 78)
    return "\n".join(lines)


def _format_finding_line(f: AuditFinding) -> str:
    loc = (
        f"{f.file_path}:{f.line_start}"
        if f.line_start > 0 else f.file_path
    )
    return (
        f"  [{f.severity.value:8s}] {loc}\n"
        f"             {f.title}\n"
        f"             category={f.category}  "
        f"confidence={f.confidence:.2f}  "
        f"id={f.stable_id}"
    )


def format_digest_markdown(digest: AuditDigest) -> str:
    lines: List[str] = []
    lines.append(f"# ARIA Code Audit — {digest.timestamp_iso[:10]}")
    lines.append("")
    lines.append(f"_Backend: `{digest.backend_label}`; "
                 f"elapsed {digest.elapsed_s:.1f}s; "
                 f"{len(digest.files)} files; "
                 f"{digest.n_errors} errors._")
    lines.append("")
    lines.append("## Severity histogram")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|------:|")
    lines.append(f"| CRITICAL | {digest.n_critical} |")
    lines.append(f"| HIGH     | {digest.n_high} |")
    lines.append(f"| MEDIUM   | {digest.n_medium} |")
    lines.append(f"| LOW      | {digest.n_low} |")
    lines.append(f"| INFO     | {digest.n_info} |")
    lines.append(f"| **Total** | **{digest.total_findings}** |")
    lines.append("")
    if digest.baseline_compared:
        lines.append("## Baseline delta")
        lines.append("")
        lines.append(f"- **NEW:** {len(digest.new_findings)}  "
                     "(introduced since last run)")
        lines.append(f"- **RESOLVED:** {len(digest.resolved_findings)}  "
                     "(fixed since last run)")
        lines.append(f"- **PERSISTING:** {len(digest.persisting_findings)}  "
                     "(still open from last run)")
        lines.append("")
    if digest.new_findings:
        lines.append("## New findings")
        lines.append("")
        for f in sorted(
            digest.new_findings, key=lambda x: -x.severity.rank,
        ):
            lines.extend(_finding_md_block(f))
            lines.append("")
    if digest.persisting_findings:
        lines.append("## Persisting findings")
        lines.append("")
        for f in sorted(
            digest.persisting_findings, key=lambda x: -x.severity.rank,
        ):
            lines.extend(_finding_md_block(f))
            lines.append("")
    return "\n".join(lines)


def _finding_md_block(f: AuditFinding) -> List[str]:
    lines: List[str] = []
    loc = (
        f"`{f.file_path}:{f.line_start}`"
        if f.line_start > 0
        else f"`{f.file_path}`"
    )
    lines.append(
        f"### [{f.severity.value}] {f.title}"
    )
    lines.append(f"_{loc} · category `{f.category}` · "
                 f"confidence {f.confidence:.2f} · id `{f.stable_id}`_")
    lines.append("")
    lines.append(f"**Description.** {f.description}")
    lines.append("")
    lines.append(f"**Recommendation.** {f.recommendation}")
    return lines
