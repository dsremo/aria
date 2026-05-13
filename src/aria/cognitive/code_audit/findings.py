"""Audit-finding data model.

Structured output the LLM emits, ARIA stores, the operator reviews.
Severity scale matches the OWASP / CVSS coarse bucketing the user
already knows from the existing `aria.security` audits — an operator
who has triaged the R1-R351 findings will read these the same way.
"""

from __future__ import annotations

import enum
import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


class Severity(str, enum.Enum):
    """OWASP/CVSS-style coarse severity bucketing."""

    CRITICAL = "CRITICAL"     # remote exploit, data loss, safety bypass
    HIGH = "HIGH"             # exploitable on common path, no auth required
    MEDIUM = "MEDIUM"         # exploit needs specific conditions / auth
    LOW = "LOW"               # hardening opportunity, defence-in-depth
    INFO = "INFO"             # observation; no immediate fix needed

    @property
    def rank(self) -> int:
        """Numeric rank for sorting most-severe-first."""
        return {
            Severity.CRITICAL: 4,
            Severity.HIGH: 3,
            Severity.MEDIUM: 2,
            Severity.LOW: 1,
            Severity.INFO: 0,
        }[self]


@dataclass(frozen=True)
class AuditFinding:
    """One auditor-reported issue.

    The ``stable_id`` field is a SHA-256 of (file, category, brief
    description hash) — the same logical issue produces the same
    ``stable_id`` across runs even if the line number drifts. This
    is what the baseline-delta logic uses to recognise persisting
    vs new vs resolved findings.
    """

    severity: Severity
    file_path: str
    line_start: int                  # 1-indexed; 0 if unknown
    line_end: int                    # 1-indexed; line_start if single line
    category: str                    # e.g. "input-validation", "race"
    title: str                       # one-sentence summary
    description: str                 # 1-3 paragraph explanation
    recommendation: str              # concrete suggested fix
    confidence: float = 1.0          # 0..1 — auditor's certainty
    stable_id: str = ""              # auto-derived if empty

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be in [0, 1]; got {self.confidence}"
            )
        if self.line_start < 0:
            raise ValueError(f"line_start must be >= 0; got {self.line_start}")
        if self.line_end < self.line_start:
            raise ValueError(
                f"line_end ({self.line_end}) must be >= line_start "
                f"({self.line_start})"
            )
        if not self.stable_id:
            object.__setattr__(self, "stable_id", _compute_stable_id(
                file_path=self.file_path,
                category=self.category,
                title=self.title,
            ))

    def as_dict(self) -> Dict[str, Any]:
        """JSON-friendly serialisation."""
        return {
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
            "stable_id": self.stable_id,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "AuditFinding":
        sev_value = payload.get("severity", "INFO")
        if isinstance(sev_value, Severity):
            sev = sev_value
        else:
            try:
                sev = Severity(str(sev_value).upper())
            except ValueError:
                sev = Severity.INFO
        return cls(
            severity=sev,
            file_path=str(payload.get("file_path", "")),
            line_start=int(payload.get("line_start", 0)),
            line_end=int(payload.get("line_end", payload.get("line_start", 0))),
            category=str(payload.get("category", "")),
            title=str(payload.get("title", "")),
            description=str(payload.get("description", "")),
            recommendation=str(payload.get("recommendation", "")),
            confidence=float(payload.get("confidence", 1.0)),
            stable_id=str(payload.get("stable_id", "")),
        )


def _compute_stable_id(
    *, file_path: str, category: str, title: str,
) -> str:
    """Hash that's stable across line-number drift."""
    blob = f"{file_path}|{category}|{title}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


@dataclass(frozen=True)
class AuditFileResult:
    """Outcome of auditing one file."""

    file_path: str
    elapsed_s: float
    response_chars: int
    findings: Tuple[AuditFinding, ...]
    error: Optional[str] = None


@dataclass(frozen=True)
class AuditDigest:
    """Aggregate of one full audit run."""

    timestamp_iso: str
    backend_label: str
    files: Tuple[AuditFileResult, ...]
    total_findings: int = 0
    n_critical: int = 0
    n_high: int = 0
    n_medium: int = 0
    n_low: int = 0
    n_info: int = 0
    n_errors: int = 0
    elapsed_s: float = 0.0
    baseline_compared: bool = False
    new_findings: Tuple[AuditFinding, ...] = field(default_factory=tuple)
    resolved_findings: Tuple[AuditFinding, ...] = field(default_factory=tuple)
    persisting_findings: Tuple[AuditFinding, ...] = field(default_factory=tuple)

    def all_findings(self) -> List[AuditFinding]:
        out: List[AuditFinding] = []
        for file_result in self.files:
            out.extend(file_result.findings)
        return out

    def as_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_iso": self.timestamp_iso,
            "backend_label": self.backend_label,
            "elapsed_s": round(self.elapsed_s, 1),
            "total_findings": self.total_findings,
            "n_critical": self.n_critical,
            "n_high": self.n_high,
            "n_medium": self.n_medium,
            "n_low": self.n_low,
            "n_info": self.n_info,
            "n_errors": self.n_errors,
            "baseline_compared": self.baseline_compared,
            "new_findings": [f.as_dict() for f in self.new_findings],
            "resolved_findings": [f.as_dict() for f in self.resolved_findings],
            "persisting_findings": [f.as_dict() for f in self.persisting_findings],
            "files": [
                {
                    "file_path": fr.file_path,
                    "elapsed_s": round(fr.elapsed_s, 2),
                    "response_chars": fr.response_chars,
                    "error": fr.error,
                    "findings": [f.as_dict() for f in fr.findings],
                }
                for fr in self.files
            ],
        }


def aggregate_severity_counts(
    findings: List[AuditFinding],
) -> Dict[Severity, int]:
    counts: Dict[Severity, int] = {sev: 0 for sev in Severity}
    for f in findings:
        counts[f.severity] += 1
    return counts
