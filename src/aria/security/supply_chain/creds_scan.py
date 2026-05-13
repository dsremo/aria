from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional, Pattern as RePattern


_PRINTABLE = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=_-."
)
ENTROPY_MIN_BITS = 4.5
ENTROPY_MIN_LEN = 32


@dataclass(frozen=True)
class Pattern:
    name: str
    regex: RePattern
    severity: str = "HIGH"
    description: str = ""


@dataclass(frozen=True)
class CredsFinding:
    file_path: str
    line_no: int
    pattern_name: str
    severity: str
    matched_text: str
    excerpt: str

    def redacted_excerpt(self) -> str:
        if not self.matched_text:
            return self.excerpt
        return self.excerpt.replace(self.matched_text, _redact(self.matched_text))


@dataclass(frozen=True)
class CredsScanReport:
    findings: tuple[CredsFinding, ...] = ()
    files_scanned: int = 0
    bytes_scanned: int = 0
    skipped: tuple[str, ...] = ()

    @property
    def n_findings(self) -> int:
        return len(self.findings)

    def by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return counts

    def as_dict(self) -> dict[str, Any]:
        return {
            "files_scanned": self.files_scanned,
            "bytes_scanned": self.bytes_scanned,
            "n_findings": self.n_findings,
            "by_severity": self.by_severity(),
            "skipped": list(self.skipped),
            "findings": [
                {
                    "file_path": finding.file_path,
                    "line_no": finding.line_no,
                    "pattern_name": finding.pattern_name,
                    "severity": finding.severity,
                    "matched_redacted": _redact(finding.matched_text),
                    "excerpt": finding.redacted_excerpt(),
                }
                for finding in self.findings
            ],
        }


def _redact(text: str) -> str:
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}***{text[-3:]}"


DEFAULT_PATTERNS: tuple[Pattern, ...] = (
    Pattern(
        name="aws-access-key-id",
        regex=re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        severity="CRITICAL",
        description="AWS access key ID",
    ),
    Pattern(
        name="aws-temp-access-key",
        regex=re.compile(r"\bASIA[0-9A-Z]{16}\b"),
        severity="CRITICAL",
        description="AWS STS temporary access key",
    ),
    Pattern(
        name="github-pat",
        regex=re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
        severity="CRITICAL",
        description="GitHub personal access token (classic)",
    ),
    Pattern(
        name="github-fine-grained-pat",
        regex=re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b"),
        severity="CRITICAL",
        description="GitHub fine-grained personal access token",
    ),
    Pattern(
        name="github-oauth",
        regex=re.compile(r"\bgho_[A-Za-z0-9]{36}\b"),
        severity="CRITICAL",
        description="GitHub OAuth token",
    ),
    Pattern(
        name="slack-bot-token",
        regex=re.compile(r"\bxox[bapr]-[A-Za-z0-9-]{10,}\b"),
        severity="HIGH",
        description="Slack bot/user token",
    ),
    Pattern(
        name="google-api-key",
        regex=re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
        severity="HIGH",
        description="Google API key (Maps, Gemini, etc.)",
    ),
    Pattern(
        name="stripe-live-key",
        regex=re.compile(r"\bsk_live_[A-Za-z0-9]{24,}\b"),
        severity="CRITICAL",
        description="Stripe live secret key",
    ),
    Pattern(
        name="anthropic-api-key",
        regex=re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}\b"),
        severity="CRITICAL",
        description="Anthropic API key",
    ),
    Pattern(
        name="openai-api-key",
        regex=re.compile(r"\bsk-[A-Za-z0-9]{40,}\b"),
        severity="CRITICAL",
        description="OpenAI API key",
    ),
    Pattern(
        name="ssh-private-key-block",
        regex=re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        severity="CRITICAL",
        description="SSH/PGP private key header",
    ),
    Pattern(
        name="jwt-token",
        regex=re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        severity="MEDIUM",
        description="JWT (may be sample / test)",
    ),
    Pattern(
        name="generic-bearer-header",
        regex=re.compile(
            r"(?i)\b(authorization|x-auth-token|x-api-key|api[_-]?key)"
            r"\s*[:=]\s*[\"']?[A-Za-z0-9_\-\.]{20,}[\"']?"
        ),
        severity="MEDIUM",
        description="Generic API/auth header with high-length value",
    ),
)


def _shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    total = len(text)
    entropy = 0.0
    for count in counts.values():
        probability = count / total
        entropy -= probability * math.log2(probability)
    return entropy


def _looks_high_entropy(token: str) -> bool:
    if len(token) < ENTROPY_MIN_LEN:
        return False
    if not all(ch in _PRINTABLE for ch in token):
        return False
    return _shannon_entropy(token) >= ENTROPY_MIN_BITS


def scan_text(
    *,
    file_path: str,
    text: str,
    patterns: Iterable[Pattern] = DEFAULT_PATTERNS,
    detect_entropy: bool = True,
) -> tuple[CredsFinding, ...]:
    findings: list[CredsFinding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        seen_spans: list[tuple[int, int]] = []
        for pattern in patterns:
            for match in pattern.regex.finditer(line):
                seen_spans.append(match.span())
                findings.append(
                    CredsFinding(
                        file_path=file_path,
                        line_no=line_no,
                        pattern_name=pattern.name,
                        severity=pattern.severity,
                        matched_text=match.group(0),
                        excerpt=line.strip()[:200],
                    )
                )
        if detect_entropy:
            for token in re.findall(r"[A-Za-z0-9_\-\./+=]{32,}", line):
                if any(start <= line.find(token) < end for start, end in seen_spans):
                    continue
                if _looks_high_entropy(token):
                    findings.append(
                        CredsFinding(
                            file_path=file_path,
                            line_no=line_no,
                            pattern_name="high-entropy-string",
                            severity="LOW",
                            matched_text=token,
                            excerpt=line.strip()[:200],
                        )
                    )
                    break
    return tuple(findings)


_SKIP_DIR_NAMES = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "dist", "build", ".idea", ".vscode",
    "graphify-out", "leann_indexes", ".leann",
}
_SKIP_SUFFIXES = {
    ".pyc", ".so", ".o", ".a", ".whl", ".tar", ".gz", ".zip", ".7z",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".pdf", ".ico",
    ".woff", ".woff2", ".ttf", ".otf",
    ".mp3", ".mp4", ".webm", ".mov",
    ".onnx", ".pt", ".pth", ".bin", ".gguf", ".npz", ".npy",
    ".db", ".sqlite", ".sqlite3",
}
MAX_FILE_BYTES = 1_500_000


def _iter_paths(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_file():
            yield root
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in _SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.suffix.lower() in _SKIP_SUFFIXES:
                continue
            yield path


def scan_files(
    paths: Iterable[Path],
    *,
    patterns: Iterable[Pattern] = DEFAULT_PATTERNS,
    detect_entropy: bool = True,
    max_bytes: int = MAX_FILE_BYTES,
) -> CredsScanReport:
    findings: list[CredsFinding] = []
    files_scanned = 0
    bytes_scanned = 0
    skipped: list[str] = []
    for path in _iter_paths(paths):
        try:
            size = path.stat().st_size
        except OSError as exc:
            skipped.append(f"{path}: {exc}")
            continue
        if size > max_bytes:
            skipped.append(f"{path}: too large ({size} bytes)")
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            skipped.append(f"{path}: {exc}")
            continue
        files_scanned += 1
        bytes_scanned += size
        findings.extend(
            scan_text(
                file_path=str(path),
                text=content,
                patterns=patterns,
                detect_entropy=detect_entropy,
            )
        )
    return CredsScanReport(
        findings=tuple(findings),
        files_scanned=files_scanned,
        bytes_scanned=bytes_scanned,
        skipped=tuple(skipped),
    )


def format_creds_report_human(report: CredsScanReport) -> str:
    lines: list[str] = []
    lines.append("Credentials-leak scan")
    lines.append("─" * 50)
    lines.append(f"Files scanned: {report.files_scanned}  ({report.bytes_scanned} bytes)")
    lines.append(f"Findings:      {report.n_findings}")
    sev_counts = report.by_severity()
    for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        count = sev_counts.get(severity, 0)
        if count:
            lines.append(f"  {severity:8s} {count}")
    if report.skipped:
        lines.append(f"Skipped: {len(report.skipped)}")
    lines.append("")
    if not report.findings:
        lines.append("(no leaks detected)")
        return "\n".join(lines)
    for finding in report.findings[:50]:
        lines.append(
            f"  {finding.severity:8s} {finding.file_path}:{finding.line_no} "
            f"[{finding.pattern_name}]"
        )
        lines.append(f"           {finding.redacted_excerpt()}")
    if len(report.findings) > 50:
        lines.append(f"  ... and {len(report.findings) - 50} more")
    return "\n".join(lines)
