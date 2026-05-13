"""R72 — Buffer-overflow class detection in the cFS C bridge.

Threat: ARIA's ``cfs_bridge/`` ships a small slice of C code that runs
inside the NASA cFS executive.  Any unchecked ``memcpy`` / ``strcpy`` /
``sprintf`` is a remote-code-execution vector.  The "Software Faults
in C Code" CVE class (Heartbleed CVE-2014-0160 was a textbook case)
remains active — every year fresh examples ship in cFS-adjacent code.

Defence: a static linter that walks ``.c`` files and reports any
unsafe primitive call, with a recommended bounded replacement
(``memcpy_s`` / ``strncpy`` / ``snprintf``).  Designed to plug into
``make security`` so any new C code has to either pass the lint or
declare an explicit ``// allow_unsafe(reason="...")`` comment.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_UNSAFE = {
    "strcpy": "strncpy / snprintf",
    "strcat": "strncat / snprintf",
    "sprintf": "snprintf",
    "vsprintf": "vsnprintf",
    "gets": "fgets",
    "memcpy": "memcpy_s (where available) + size assert",
    "memmove": "memmove_s",
}

# Allow operator-acked usages via a per-line comment.
_ACK_RE = re.compile(r"//\s*allow_unsafe\s*\(reason\s*=\s*\"[^\"]+\"\)")


def lint_c_source(text: str) -> List[Tuple[int, str, str]]:
    """Return a list of ``(line_number, function_called, recommendation)``."""
    findings: List[Tuple[int, str, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if _ACK_RE.search(line):
            continue
        for fn, rec in _UNSAFE.items():
            # Match `fn(` — call site, not the symbol in a comment block
            # (we're conservative; comments containing fn names generate noise).
            if re.search(rf"\b{fn}\s*\(", line):
                # Skip comment-only lines
                stripped = line.lstrip()
                if stripped.startswith("//") or stripped.startswith("*"):
                    continue
                findings.append((i, fn, rec))
                break
    return findings


def lint_directory(root: Path) -> List[Tuple[Path, List[Tuple[int, str, str]]]]:
    """Walk ``root`` for ``*.c`` and ``*.h`` and return findings list."""
    out: List[Tuple[Path, List[Tuple[int, str, str]]]] = []
    if not root.is_dir():
        return out
    for p in root.rglob("*.[ch]"):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        findings = lint_c_source(text)
        if findings:
            out.append((p, findings))
    return out


register(DefencePlugin(
    round_id="R72",
    name="buffer_overflow_lint",
    description="Walk C source for strcpy/sprintf/gets/memcpy without an ack.",
))
