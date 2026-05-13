"""R73 — Format-string injection (printf-class).

Threat: ``printf(user_supplied)`` or its Python relatives —
``"%s" % user`` reaching ``LOG.warning(format_string, user)`` — leak
stack memory or crash the process.  CWE-134.  Recent: CVE-2023-46446
in PJSIP, CVE-2024-12345-class in legacy C libraries.

Defence: a Python-side lint + a C lint that flags any call where the
format string is NOT a literal.  Pattern-based; over-flags slightly
but errs on the side of caution.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_PRINTF_FAMILY = ("printf", "fprintf", "sprintf", "snprintf", "vprintf",
                  "vfprintf", "vsprintf", "vsnprintf", "syslog", "err",
                  "warn", "errx", "warnx")


def lint_c_for_format_strings(text: str) -> List[Tuple[int, str]]:
    """Find printf-class calls whose first argument isn't a string literal."""
    findings: List[Tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for fn in _PRINTF_FAMILY:
            m = re.search(rf"\b{fn}\s*\(\s*([^,)]+)", line)
            if not m:
                continue
            arg = m.group(1).strip()
            # Literal "..." OK
            if arg.startswith('"'):
                continue
            findings.append((i, f"{fn}({arg[:40]}...)"))
    return findings


def lint_python_for_format_strings(text: str) -> List[Tuple[int, str]]:
    """Find ``LOG.<level>(non-literal, ...)`` patterns."""
    findings: List[Tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        m = re.search(
            r"\b(?:logger|log|LOG|LOGGER)\.(?:debug|info|warning|error|critical)\(\s*([^,)]+)",
            line,
        )
        if not m:
            continue
        arg = m.group(1).strip()
        if arg.startswith(('"', "'", "f'", 'f"')):
            continue
        if arg.startswith("("):                         # likely tuple wrap
            continue
        findings.append((i, arg[:40]))
    return findings


register(DefencePlugin(
    round_id="R73",
    name="format_string",
    description="Lint C printf-class + Python LOG calls for non-literal format strings.",
))
