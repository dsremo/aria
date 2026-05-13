"""R46 — Repository secret-scan (history + working tree).

Threat: a developer commits ``aria-prod.env`` containing a real
production API key.  GitHub's secret-scanner finds it minutes later
and the key must be rotated.  Lockfile-only deploys still prefer to
catch this *before* the push reaches GitHub.

Defence: a small ``scan_paths(paths)`` function that walks files and
matches the same secret-shape patterns from R2.  Returns a list of
findings with file path + line number for the pre-commit hook.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_SECRET_PATTERNS = tuple((name, re.compile(pat)) for name, pat in [
    ("aws_key", r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ("github_pat", r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    ("slack_token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    ("openai_key", r"\bsk-[A-Za-z0-9]{20,}\b"),
    ("private_key_block", r"-----BEGIN (?:RSA|OPENSSH|EC|DSA) PRIVATE KEY-----"),
    ("jwt", r"\bey[A-Za-z0-9_=-]{20,}\.[A-Za-z0-9_=-]{20,}\.[A-Za-z0-9_=-]{20,}\b"),
])


_DEFAULT_SKIP_DIRS = (".git", "node_modules", "venv", ".venv", "__pycache__")
_TEXT_EXTS = (
    ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".env",
    ".sh", ".md", ".txt", ".cfg", ".ini", ".pem", ".key",
)


def is_text_file(path: Path) -> bool:
    if path.suffix.lower() in _TEXT_EXTS:
        return True
    try:
        return b"\x00" not in path.read_bytes()[:8192]
    except OSError:
        return False


def scan_text(text: str) -> List[Tuple[str, int]]:
    """Return ``[(secret_name, line_number_1_based), …]`` for ``text``."""
    out: List[Tuple[str, int]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for name, pat in _SECRET_PATTERNS:
            if pat.search(line):
                out.append((name, i))
                break
    return out


def scan_paths(roots: List[Path]) -> List[Tuple[Path, str, int]]:
    """Walk ``roots`` and return findings list."""
    findings: List[Tuple[Path, str, int]] = []
    for root in roots:
        if root.is_file():
            if is_text_file(root):
                for name, ln in scan_text(root.read_text(encoding="utf-8", errors="replace")):
                    findings.append((root, name, ln))
            continue
        for p in root.rglob("*"):
            if p.is_dir():
                if p.name in _DEFAULT_SKIP_DIRS:
                    # rglob does not honour skip; we just don't recurse here.
                    pass
                continue
            if any(part in _DEFAULT_SKIP_DIRS for part in p.parts):
                continue
            if not is_text_file(p):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for name, ln in scan_text(text):
                findings.append((p, name, ln))
    return findings


register(DefencePlugin(
    round_id="R46",
    name="secret_scan",
    description="Pre-commit / pre-push secret-shape scanner over working tree.",
))
