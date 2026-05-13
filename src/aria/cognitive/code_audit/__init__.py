"""Continuous AI code-audit harness — the AISLE pattern.

NASA's spacecraft software carried a vulnerability for *three years*
undetected; an AI-driven autonomous analyser (AISLE, 2026) found
and patched it in **four days**. This module is ARIA's equivalent —
an LLM-CLI-backed audit loop that scans the codebase (or a git
diff) for security / safety bugs, returns structured findings, and
tracks them over time so a regression introduces a new finding
instead of slipping past human review.

Design follows the LLM eval harness pattern in
``aria.cognitive.llm_eval``:
  * `CodeAuditBackend` protocol — pluggable LLM
  * `LlmCliAuditBackend` — the configured LLM CLI (no API key needed)
  * `AuditFinding` dataclass — severity / file / line / category
  * `Auditor` — orchestrates scans
  * Persistent baseline at ``data/runtime/code_audit/baseline.json``;
    deltas computed against it on each run

Operator usage:
  python -m aria.cognitive.code_audit --diff               # changed files only
  python -m aria.cognitive.code_audit --files src/aria/foo.py
  python -m aria.cognitive.code_audit --since-commit HEAD~5
  python -m aria.cognitive.code_audit --json > audit.json

Citations:
  * NASA AISLE 2026 — https://www.space.com/technology/nasa-spacecraft-were-vulnerable-to-hacking-for-3-years-and-nobody-knew-ai-found-and-fixed-the-flaw-in-4-days
  * OWASP Top 10 (background categories)
  * the LLM API + Code CLI auth model
"""

__all__ = (
    "Severity",
    "AuditFinding",
    "AuditFileResult",
    "AuditDigest",
    "LlmCliAuditBackend",
    "Auditor",
    "format_digest_human",
    "format_digest_markdown",
)


from aria.cognitive.code_audit.findings import (
    Severity,
    AuditFinding,
    AuditFileResult,
    AuditDigest,
)
from aria.cognitive.code_audit.backends import LlmCliAuditBackend
from aria.cognitive.code_audit.auditor import Auditor
from aria.cognitive.code_audit.format import (
    format_digest_human,
    format_digest_markdown,
)
