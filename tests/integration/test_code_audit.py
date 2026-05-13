"""Continuous AI code-audit harness tests.

Uses a stub backend so CI doesn't hit the live the LLM CLI.
A live probe (gated on ``ARIA_RUN_LIVE_CODE_AUDIT=1``) exercises the
real CLI against a small ARIA file."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest

from aria.cognitive.code_audit import (
    AuditDigest,
    AuditFinding,
    AuditFileResult,
    Auditor,
    LlmCliAuditBackend,
    Severity,
    format_digest_human,
    format_digest_markdown,
)
from aria.cognitive.code_audit.backends import (
    parse_findings_response,
)


# ── Stub backend ────────────────────────────────────────────────


@dataclass
class _StubBackend:
    response_text: str = "[]"
    raise_on_audit: bool = False
    label: str = "stub-test"
    submitted: List[tuple] = field(default_factory=list)

    def is_available(self) -> bool:
        return True

    def audit_text(self, *, file_path: str, content: str) -> str:
        self.submitted.append((file_path, len(content)))
        if self.raise_on_audit:
            raise RuntimeError("stub backend forced failure")
        return self.response_text


# ── Severity primitives ─────────────────────────────────────────


class TestSeverity:
    def test_rank_order(self):
        assert Severity.CRITICAL.rank > Severity.HIGH.rank
        assert Severity.HIGH.rank > Severity.MEDIUM.rank
        assert Severity.MEDIUM.rank > Severity.LOW.rank
        assert Severity.LOW.rank > Severity.INFO.rank


class TestAuditFinding:
    def test_stable_id_is_deterministic(self):
        finding_a = AuditFinding(
            severity=Severity.HIGH, file_path="x.py",
            line_start=5, line_end=5,
            category="input-validation",
            title="Missing bounds check",
            description="...", recommendation="...",
        )
        finding_b = AuditFinding(
            severity=Severity.HIGH, file_path="x.py",
            line_start=42, line_end=42,         # different line
            category="input-validation",
            title="Missing bounds check",
            description="...", recommendation="...",
        )
        # Same file + category + title → same stable_id even with
        # different line numbers (the regression-tracking property).
        assert finding_a.stable_id == finding_b.stable_id

    def test_stable_id_differs_for_different_categories(self):
        finding_a = AuditFinding(
            severity=Severity.HIGH, file_path="x.py", line_start=5,
            line_end=5, category="input-validation",
            title="Missing bounds check",
            description="", recommendation="",
        )
        finding_b = AuditFinding(
            severity=Severity.HIGH, file_path="x.py", line_start=5,
            line_end=5, category="race",
            title="Missing bounds check",
            description="", recommendation="",
        )
        assert finding_a.stable_id != finding_b.stable_id

    def test_negative_line_rejected(self):
        with pytest.raises(ValueError, match="line_start"):
            AuditFinding(
                severity=Severity.HIGH, file_path="x.py",
                line_start=-1, line_end=0,
                category="x", title="x", description="", recommendation="",
            )

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(ValueError, match="confidence"):
            AuditFinding(
                severity=Severity.HIGH, file_path="x.py",
                line_start=1, line_end=1, category="x",
                title="x", description="", recommendation="",
                confidence=2.0,
            )

    def test_line_end_before_start_rejected(self):
        with pytest.raises(ValueError, match="line_end"):
            AuditFinding(
                severity=Severity.HIGH, file_path="x.py",
                line_start=10, line_end=5,
                category="x", title="x", description="", recommendation="",
            )

    def test_round_trip_through_dict(self):
        f = AuditFinding(
            severity=Severity.MEDIUM, file_path="a/b.py",
            line_start=12, line_end=12, category="error-handling",
            title="bare except", description="...", recommendation="narrow",
            confidence=0.9,
        )
        round_trip = AuditFinding.from_dict(f.as_dict())
        assert round_trip == f


# ── JSON parser ─────────────────────────────────────────────────


class TestParseFindingsResponse:
    def test_empty_array_string(self):
        assert parse_findings_response("[]") == []

    def test_one_finding(self):
        text = json.dumps([
            {"severity": "HIGH", "file_path": "x.py",
             "line_start": 3, "line_end": 3,
             "category": "input-validation",
             "title": "Missing bounds check",
             "description": "...", "recommendation": "...",
             "confidence": 0.9},
        ])
        parsed = parse_findings_response(text)
        assert len(parsed) == 1
        assert parsed[0]["severity"] == "HIGH"

    def test_strips_markdown_fences(self):
        text = "```json\n[{\"severity\": \"LOW\", \"line_start\": 1, " \
               "\"line_end\": 1, \"category\": \"x\", " \
               "\"title\": \"x\", \"description\": \"x\", " \
               "\"recommendation\": \"x\", \"file_path\": \"y.py\", " \
               "\"confidence\": 0.5}]\n```"
        parsed = parse_findings_response(text)
        assert len(parsed) == 1
        assert parsed[0]["severity"] == "LOW"

    def test_pulls_array_from_prose(self):
        prose = (
            "Here are my findings:\n\n"
            '[{"severity":"INFO","line_start":1,"line_end":1,'
            '"category":"x","title":"x","description":"x",'
            '"recommendation":"x","file_path":"y.py","confidence":1.0}]\n'
            "Done."
        )
        parsed = parse_findings_response(prose)
        assert len(parsed) == 1

    def test_garbage_returns_empty_list(self):
        assert parse_findings_response("hello world") == []
        assert parse_findings_response("") == []
        assert parse_findings_response("not json at all") == []

    def test_non_array_top_level_returns_empty(self):
        assert parse_findings_response('{"severity": "HIGH"}') == []

    def test_non_dict_items_filtered_out(self):
        # Defensive against an LLM that emits ["bad", {...valid...}]
        text = json.dumps([
            "this is a string not a dict",
            {"severity": "LOW", "file_path": "x.py",
             "line_start": 1, "line_end": 1,
             "category": "x", "title": "x",
             "description": "x", "recommendation": "x",
             "confidence": 1.0},
        ])
        parsed = parse_findings_response(text)
        assert len(parsed) == 1


# ── Auditor: file scan + diff scan ──────────────────────────────


class TestAuditFile:
    def test_empty_findings_returns_clean_result(self, tmp_path: Path):
        target = tmp_path / "clean.py"
        target.write_text("def f():\n    return 1\n")
        backend = _StubBackend(response_text="[]")
        auditor = Auditor(backend=backend)
        result = auditor.audit_file(target)
        assert result.error is None
        assert result.findings == ()
        assert backend.submitted, "stub didn't see the file content"

    def test_single_finding_parsed(self, tmp_path: Path):
        target = tmp_path / "buggy.py"
        target.write_text("def f(x):\n    return eval(x)\n")
        canned = json.dumps([
            {"severity": "CRITICAL", "line_start": 2, "line_end": 2,
             "category": "code-injection",
             "title": "Use of eval() on untrusted input",
             "description": "eval() executes arbitrary code.",
             "recommendation": "Replace with ast.literal_eval or a parser.",
             "confidence": 0.95},
        ])
        backend = _StubBackend(response_text=canned)
        auditor = Auditor(backend=backend)
        result = auditor.audit_file(target)
        assert result.error is None
        assert len(result.findings) == 1
        assert result.findings[0].severity is Severity.CRITICAL
        assert result.findings[0].category == "code-injection"
        assert "eval" in result.findings[0].title.lower()
        # file_path injected by the auditor.
        assert result.findings[0].file_path == str(target)

    def test_missing_file_captures_error(self, tmp_path: Path):
        backend = _StubBackend()
        auditor = Auditor(backend=backend)
        result = auditor.audit_file(tmp_path / "no-such.py")
        assert result.error is not None
        assert "not found" in result.error
        assert result.findings == ()

    def test_backend_exception_captured(self, tmp_path: Path):
        target = tmp_path / "x.py"
        target.write_text("x = 1\n")
        backend = _StubBackend(raise_on_audit=True)
        auditor = Auditor(backend=backend)
        result = auditor.audit_file(target)
        assert result.error is not None
        assert "stub backend" in result.error
        assert result.findings == ()


# ── Aggregation + delta ─────────────────────────────────────────


class TestAuditFiles:
    def test_aggregates_severity_counts(self, tmp_path: Path):
        f1 = tmp_path / "a.py"; f1.write_text("a = 1\n")
        f2 = tmp_path / "b.py"; f2.write_text("b = 2\n")
        canned = json.dumps([
            {"severity": "HIGH", "line_start": 1, "line_end": 1,
             "category": "x", "title": "T", "description": "",
             "recommendation": "", "confidence": 0.8},
            {"severity": "LOW", "line_start": 1, "line_end": 1,
             "category": "y", "title": "U", "description": "",
             "recommendation": "", "confidence": 0.9},
        ])
        backend = _StubBackend(response_text=canned)
        auditor = Auditor(
            backend=backend,
            baseline_path=tmp_path / "baseline.json",
        )
        digest = auditor.audit_files([f1, f2])
        # 2 files × 2 findings = 4 total (1 HIGH, 1 LOW per file).
        assert digest.total_findings == 4
        assert digest.n_high == 2
        assert digest.n_low == 2
        assert digest.n_critical == 0


class TestBaselineDelta:
    def test_first_run_compares_against_empty_baseline(self, tmp_path: Path):
        target = tmp_path / "x.py"; target.write_text("x = 1\n")
        canned = json.dumps([
            {"severity": "HIGH", "line_start": 1, "line_end": 1,
             "category": "race", "title": "Shared mutable state",
             "description": "", "recommendation": "", "confidence": 0.7},
        ])
        backend = _StubBackend(response_text=canned)
        auditor = Auditor(
            backend=backend,
            baseline_path=tmp_path / "baseline.json",
        )
        digest = auditor.audit_files([target])
        assert digest.baseline_compared is True
        # First run: no baseline → all findings are NEW.
        assert len(digest.new_findings) == 1
        assert len(digest.resolved_findings) == 0
        assert len(digest.persisting_findings) == 0

    def test_persisting_finding_recognised(self, tmp_path: Path):
        target = tmp_path / "x.py"; target.write_text("x = 1\n")
        canned = json.dumps([
            {"severity": "HIGH", "line_start": 1, "line_end": 1,
             "category": "race", "title": "Shared mutable state",
             "description": "", "recommendation": "", "confidence": 0.7},
        ])
        backend = _StubBackend(response_text=canned)
        baseline_path = tmp_path / "baseline.json"
        auditor = Auditor(backend=backend, baseline_path=baseline_path)
        # First run lands a finding; we treat it as the baseline.
        first = auditor.audit_files([target])
        auditor.write_baseline(first)
        # Second run with the SAME finding (same stable_id).
        second = auditor.audit_files([target])
        # Same logical finding → persisting, not new.
        assert len(second.new_findings) == 0
        assert len(second.persisting_findings) == 1
        assert len(second.resolved_findings) == 0

    def test_resolved_finding_recognised(self, tmp_path: Path):
        target = tmp_path / "x.py"; target.write_text("x = 1\n")
        # Run 1 finds an issue.
        canned_run_1 = json.dumps([
            {"severity": "HIGH", "line_start": 1, "line_end": 1,
             "category": "race", "title": "Shared mutable state",
             "description": "", "recommendation": "", "confidence": 0.7},
        ])
        backend = _StubBackend(response_text=canned_run_1)
        baseline_path = tmp_path / "baseline.json"
        auditor = Auditor(backend=backend, baseline_path=baseline_path)
        first = auditor.audit_files([target])
        auditor.write_baseline(first)
        # Run 2 returns no findings (presumed fixed).
        backend.response_text = "[]"
        second = auditor.audit_files([target])
        assert len(second.resolved_findings) == 1
        assert len(second.new_findings) == 0
        assert len(second.persisting_findings) == 0

    def test_new_finding_recognised(self, tmp_path: Path):
        target = tmp_path / "x.py"; target.write_text("x = 1\n")
        baseline_path = tmp_path / "baseline.json"
        # Run 1: clean.
        backend = _StubBackend(response_text="[]")
        auditor = Auditor(backend=backend, baseline_path=baseline_path)
        first = auditor.audit_files([target])
        auditor.write_baseline(first)
        # Run 2: NEW finding appears.
        backend.response_text = json.dumps([
            {"severity": "CRITICAL", "line_start": 5, "line_end": 5,
             "category": "code-injection",
             "title": "Use of eval()", "description": "",
             "recommendation": "", "confidence": 0.95},
        ])
        second = auditor.audit_files([target])
        assert len(second.new_findings) == 1
        assert second.new_findings[0].severity is Severity.CRITICAL


# ── Format helpers ──────────────────────────────────────────────


class TestFormatters:
    def _digest(self) -> AuditDigest:
        finding = AuditFinding(
            severity=Severity.HIGH, file_path="x.py",
            line_start=42, line_end=42,
            category="input-validation",
            title="Missing bounds check on user input",
            description="...", recommendation="...",
            confidence=0.85,
        )
        file_result = AuditFileResult(
            file_path="x.py", elapsed_s=2.0, response_chars=200,
            findings=(finding,),
        )
        return AuditDigest(
            timestamp_iso="2026-04-29T12:00:00+00:00",
            backend_label="stub-test",
            files=(file_result,),
            total_findings=1, n_high=1,
            elapsed_s=2.0,
            baseline_compared=True,
            new_findings=(finding,),
        )

    def test_human_includes_severity_histogram(self):
        text = format_digest_human(self._digest())
        assert "Severity histogram" in text
        assert "HIGH" in text
        assert "x.py" in text
        assert "Missing bounds check" in text

    def test_markdown_renders_table(self):
        md = format_digest_markdown(self._digest())
        assert "| Severity | Count |" in md
        assert "## Severity histogram" in md
        assert "## New findings" in md
        assert "Missing bounds check" in md

    def test_human_omits_persisting_section_when_empty(self):
        # No persisting → that section absent.
        digest = self._digest()
        text = format_digest_human(digest)
        assert "PERSISTING HIGH/CRITICAL" not in text

    def test_json_round_trip(self):
        digest = self._digest()
        as_dict = digest.as_dict()
        # Must be JSON-serialisable cleanly.
        encoded = json.dumps(as_dict)
        assert "x.py" in encoded
        assert "Missing bounds check" in encoded


# ── Live probe (opt-in only) ────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("ARIA_RUN_LIVE_CODE_AUDIT") != "1",
    reason="live the LLM CLI code audit; gated on ARIA_RUN_LIVE_CODE_AUDIT=1",
)
def test_live_audit_against_real_claude_cli(tmp_path: Path):
    """Smoke: real the LLM CLI auditing a tiny intentionally-buggy file."""
    target = tmp_path / "tiny.py"
    target.write_text(
        "import pickle\n"
        "def load(blob):\n"
        "    return pickle.loads(blob)\n"   # CRITICAL — pickle of untrusted bytes
    )
    backend = LlmCliAuditBackend(effort="low", timeout_s=180.0)
    if not backend.is_available():
        pytest.skip("claude CLI not installed")
    auditor = Auditor(
        backend=backend, baseline_path=tmp_path / "baseline.json",
    )
    digest = auditor.audit_files([target], compare_to_baseline=False)
    # The auditor MUST flag pickle.loads on untrusted input.
    assert digest.total_findings >= 1
    assert digest.n_critical + digest.n_high >= 1, (
        "pickle deserialisation should be flagged HIGH+ at minimum; "
        f"got {digest.total_findings} findings, severities: "
        f"C={digest.n_critical} H={digest.n_high} M={digest.n_medium} "
        f"L={digest.n_low} I={digest.n_info}"
    )
