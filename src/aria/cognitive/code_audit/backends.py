"""LLM backends for code audit.

Default: the configured LLM CLI in --print mode. Same auth model as
``aria.cognitive.llm_eval.backends.LlmCliBackend``.
The audit prompt is engineered to elicit a JSON array of findings;
the backend returns the raw stdout text and the auditor parses
it. Defensive: malformed JSON is captured as an error and
the file's findings list is empty (no false-positive injection).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


CLAUDE_CLI_BINARY = "claude"
DEFAULT_TIMEOUT_S = 240.0     # per-file budget; 4 min is plenty
DEFAULT_EFFORT = "high"       # we want thorough analysis


SYSTEM_PROMPT = (
    "You are a senior security + safety engineer reviewing Python code "
    "for a research-grade spacecraft autonomy system (ARIA). Find real "
    "issues, not lint nits. Focus on:\n\n"
    "  - INPUT VALIDATION: missing bounds checks, unvalidated env vars, "
    "untrusted file/network reads, deserialisation\n"
    "  - RACE CONDITIONS: shared mutable state without locks, threading "
    "issues, async lifecycle bugs\n"
    "  - ERROR HANDLING: bare except clauses, swallowed exceptions, "
    "fail-open vs fail-closed reasoning\n"
    "  - SAFETY-CRITICAL LOGIC: bypass paths, default-allow gates, "
    "privilege-escalation, secret leaks\n"
    "  - CRYPTO MISUSE: weak primitives, fixed nonces, time-based oracles\n"
    "  - RESOURCE LEAKS: unbounded growth, missing cleanup, context-manager "
    "misuse\n\n"
    "Reply with a JSON array of finding objects. Each object MUST have:\n"
    '  {"severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO", '
    '"line_start": <int>, "line_end": <int>, '
    '"category": "<short-tag>", "title": "<one-sentence>", '
    '"description": "<paragraph>", '
    '"recommendation": "<concrete-fix>", '
    '"confidence": <0.0-1.0>}\n\n'
    "If you find nothing, return an empty JSON array: []\n"
    "Do NOT use markdown code fences. Do NOT add explanation text. "
    "Output ONLY the JSON array, nothing else.\n\n"
    "Severity guidance:\n"
    "  CRITICAL — exploitable + safety-critical (crew/spacecraft harm path)\n"
    "  HIGH     — exploitable, no auth required, common code path\n"
    "  MEDIUM   — exploit needs specific conditions / authenticated context\n"
    "  LOW      — defence-in-depth / hardening opportunity\n"
    "  INFO     — observation, no immediate fix needed\n\n"
    "Cap total findings at 10 per file; pick the most important. "
    "If genuinely benign, return [] rather than padding."
)


@dataclass
class LlmCliAuditBackend:
    """Subprocess the configured LLM CLI to audit one file at a time."""

    binary: str = CLAUDE_CLI_BINARY
    timeout_s: float = DEFAULT_TIMEOUT_S
    effort: str = DEFAULT_EFFORT
    extra_args: Sequence[str] = field(default_factory=tuple)

    @property
    def label(self) -> str:
        return f"claude-cli({self.effort})"

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def audit_text(
        self, *, file_path: str, content: str,
    ) -> str:
        """Submit one file's content to the auditor; return raw stdout."""
        if not self.is_available():
            raise RuntimeError(
                f"LLM CLI {self.binary!r} not on PATH; install it"
                " or pass a different backend."
            )
        # Cap content size — files larger than this are usually not
        # the right granularity for a focused audit.
        max_chars = 50_000
        if len(content) > max_chars:
            content = (
                content[:max_chars]
                + f"\n\n# ...truncated at {max_chars} chars..."
            )
        user_prompt = (
            f"File: {file_path}\n"
            f"Content (line-numbered):\n\n"
            + _add_line_numbers(content)
            + "\n\n"
            + "Audit this file. Return the JSON array as instructed."
        )
        cmd = [
            self.binary,
            "--print",
            "--no-session-persistence",
            "--effort", str(self.effort),
            "--append-system-prompt", SYSTEM_PROMPT,
            *self.extra_args,
            user_prompt,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"the LLM CLI timed out after {self.timeout_s}s"
            ) from None
        if result.returncode != 0:
            raise RuntimeError(
                f"the LLM CLI exited {result.returncode}: "
                f"{result.stderr.strip()[:500]}"
            )
        text = (result.stdout or "").strip()
        if not text:
            raise RuntimeError(
                f"the LLM CLI returned empty stdout"
                f"; stderr={result.stderr.strip()[:200]}"
            )
        return text


# ── Response-parser helpers ─────────────────────────────────────


def parse_findings_response(
    raw_text: str,
) -> List[Dict[str, Any]]:
    """Extract the JSON array of finding dicts from raw LLM stdout.

    Handles common deviations: markdown code fences (despite the
    system prompt forbidding them); leading prose; trailing
    explanation. Returns an empty list if no parsable JSON array.
    """
    if not raw_text:
        return []

    # Strip leading + trailing whitespace + code fences.
    text = raw_text.strip()

    # Remove markdown code fences if the LLM ignored the instruction.
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Try direct parse first.
    parsed = _try_parse_json_array(text)
    if parsed is not None:
        return parsed

    # Fallback: find the outermost JSON array in the text.
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        parsed = _try_parse_json_array(match.group(0))
        if parsed is not None:
            return parsed

    return []


def _try_parse_json_array(text: str) -> Optional[List[Dict[str, Any]]]:
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, list):
        return None
    # Filter to dicts (defensive against LLM emitting strings).
    return [item for item in loaded if isinstance(item, dict)]


def _add_line_numbers(content: str) -> str:
    """Prefix each line with its 1-indexed number, padded for the
    max width. The auditor uses these line numbers in its findings."""
    lines = content.splitlines()
    if not lines:
        return content
    width = len(str(len(lines)))
    return "\n".join(
        f"{i + 1:>{width}}  {line}" for i, line in enumerate(lines)
    )
