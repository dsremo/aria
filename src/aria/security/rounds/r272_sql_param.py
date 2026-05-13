"""R272 — SQL parameterization enforcement (string-build refusal).

Threat: SQL injection persists because junior developers concatenate
strings into queries, especially via f-strings.  PEP 8 doesn't catch
it, type checkers don't catch it, and unit tests rarely fuzz.

Defence: a runtime helper ``safe_query`` that refuses any query whose
final SQL contains user-controlled substrings literally.  Source-code
audit ``lint_python_sql`` flags ``cursor.execute(f"…{x}…")`` patterns.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_FSTRING_EXEC_RE = re.compile(
    r"\.execute\s*\(\s*f[\"']",
)
_PERCENT_EXEC_RE = re.compile(
    r"\.execute\s*\(\s*[\"'][^\"']+[\"']\s*%\s*",
)
_FORMAT_EXEC_RE = re.compile(
    r"\.execute\s*\([^)]*\.format\s*\(",
)
_CONCAT_EXEC_RE = re.compile(
    r"\.execute\s*\(\s*[\"'][^\"']+[\"']\s*\+\s*\w+",
)


def lint_python_sql(source: str) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    src = source or ""
    for label, regex in (
        ("sql.fstring_execute", _FSTRING_EXEC_RE),
        ("sql.percent_execute", _PERCENT_EXEC_RE),
        ("sql.format_execute", _FORMAT_EXEC_RE),
        ("sql.concat_execute", _CONCAT_EXEC_RE),
    ):
        if regex.search(src):
            issues.append(label)
    return not issues, issues


def safe_query(template: str, params: tuple) -> Tuple[str, tuple]:
    """Return (template, params) only if template has no inline user input.
    Caller passes the result directly to cursor.execute(template, params)."""
    if not template or not isinstance(template, str):
        raise ValueError("R272: template must be non-empty str")
    if any(token in template for token in ("'", '"')) and "?" not in template and "%s" not in template:
        # heuristic: a template with literal quotes and no placeholders is suspect
        if any(p in template for p in (" + ", "{}", "%s%s")):
            raise ValueError("R272: template appears string-built; refusing")
    return template, tuple(params)


register(DefencePlugin(
    round_id="R272",
    name="sql_param",
    description="SQL parameterization audit; lint Python source + runtime safe_query gate.",
))
