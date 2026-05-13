#!/usr/bin/env python3
"""Audit ``# ESTIMATE`` tags across the ARIA codebase.

Per `CLAUDE.md`, every numerical constant must carry a citation on the
same line or the line above. When no published source exists, the value
must be tagged ``# ESTIMATE — <why>`` so reviewers know which numbers
are derived, scaled, or placeholder.

This script walks ``src/aria/`` and reports how many ESTIMATE tags exist,
broken down by **category** (pure-placeholder vs. scaled-from-citation vs.
derived-calculation) and by **package** (simulation, digital_twin,
physics, ...). It exists so every commit can measure whether the citation
debt is going up or down; run it before major releases.

Usage::

    python scripts/audit_estimates.py                 # summary table
    python scripts/audit_estimates.py --per-file      # file-level breakdown
    python scripts/audit_estimates.py --json          # machine-readable

Exit code 0 — always, this is a reporter, not a gate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


# Categories we sort ESTIMATE tags into. Matches are checked in order —
# the first pattern that matches the trailing rationale wins.
#
# Reason-separator patterns we recognise (these terminate ESTIMATE and
# start the free-text justification):
#   "ESTIMATE — ..."   em-dash, canonical per CLAUDE.md
#   "ESTIMATE - ..."   hyphen
#   "ESTIMATE: ..."    colon
#   "ESTIMATE (...)"   parenthetical
#   "ESTIMATE based ..." / "ESTIMATE derived ..." / "ESTIMATE per ..."
#   "ESTIMATE from ..." / "ESTIMATE approx ..." / "ESTIMATE scaled ..."
#
# "has_reason" below is anything with such a separator; the more specific
# categories take precedence. Bare `# ESTIMATE` with no further text is
# `unlabeled` — the worst bucket, requires immediate annotation.
_CATEGORY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # "ESTIMATE — no published data", "no data available", "placeholder"
    ("placeholder", re.compile(
        r"ESTIMATE\b[^\n]*\b(no\s+(published|known|available)?\s*data"
        r"|placeholder|assumed|heuristic|guess)\b",
        re.IGNORECASE,
    )),
    # "ESTIMATE — Author YYYY scaled", "... approximation", "... scaled from"
    ("scaled_from_citation", re.compile(
        r"ESTIMATE\b[^\n]*\b(scaled|approx|conservative|derived|interpolat|"
        r"extrapolat|lower\s+bound|upper\s+bound|bound|per\s+\w+|ratio)\b",
        re.IGNORECASE,
    )),
    # "ESTIMATE — AuthorSurname YYYY" (no scaling qualifier before/after)
    ("has_citation", re.compile(
        r"ESTIMATE\b[^\n]*\b[A-Z][a-z]{2,}(?:\s*&\s*[A-Z][a-z]+)?\s+[12][0-9]{3}\b"
    )),
    # "ESTIMATE — ISO 17771", "ESTIMATE — NFPA 12A", "ESTIMATE — NASA-STD-..."
    ("has_standard", re.compile(
        r"ESTIMATE\b[^\n]*\b(ISO|ASTM|ASME|IEEE|NFPA|NASA-STD|MIL-STD|MIL-HDBK|"
        r"ECSS|CCSDS|SAE|IEC|ASHRAE|DOE|EPA|OSHA|WHO|FAR)\b"
    )),
    # "ESTIMATE" followed by any recognised reason separator — em-dash,
    # hyphen, colon, paren, or a known English connector verb.
    ("bare_reason", re.compile(
        r"ESTIMATE(\s*[—\-:]|\s*\(|\s+(based|derived|from|per|using|via|"
        r"approx|scaled|due\s+to|because|consistent\s+with))",
        re.IGNORECASE,
    )),
]

_FALLBACK_CATEGORY = "unlabeled"


def classify(line: str) -> str:
    """Return one of the defined categories for this ESTIMATE line."""
    for name, pat in _CATEGORY_PATTERNS:
        if pat.search(line):
            return name
    return _FALLBACK_CATEGORY


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return list of ``(lineno, category, stripped_line)`` for this file."""
    out: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for i, raw in enumerate(text.splitlines(), start=1):
        # Match only when ESTIMATE is inside a Python comment.
        if "# ESTIMATE" not in raw and "#ESTIMATE" not in raw:
            continue
        # Skip markdown / docstrings masquerading (rare but possible).
        if '"""' in raw or "'''" in raw:
            continue
        category = classify(raw)
        out.append((i, category, raw.strip()))
    return out


def package_of(path: Path, root: Path) -> str:
    """Return the top-level package name under src/aria/."""
    try:
        rel = path.relative_to(root)
        parts = rel.parts
        if parts and parts[0] == "aria" and len(parts) > 1:
            return parts[1]
        if parts:
            return parts[0]
    except ValueError:
        pass
    return "<other>"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default="src",
                    help="Root dir to scan (default: src)")
    ap.add_argument("--per-file", action="store_true",
                    help="Print per-file counts in addition to the summary")
    ap.add_argument("--json", action="store_true",
                    help="Print machine-readable JSON only")
    ap.add_argument("--category", default=None,
                    help="If set, list every line in this category only")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"scan root {root} not found", file=sys.stderr)
        return 2

    by_category: Counter[str] = Counter()
    by_package: defaultdict[str, Counter[str]] = defaultdict(Counter)
    per_file: dict[str, int] = {}
    detail_lines: list[tuple[Path, int, str, str]] = []

    for py in root.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        hits = scan_file(py)
        if not hits:
            continue
        per_file[str(py.relative_to(root))] = len(hits)
        pkg = package_of(py, root)
        for lineno, cat, line in hits:
            by_category[cat] += 1
            by_package[pkg][cat] += 1
            if args.category and cat == args.category:
                detail_lines.append((py.relative_to(root), lineno, cat, line))

    total = sum(by_category.values())

    if args.json:
        print(json.dumps({
            "total": total,
            "by_category": dict(by_category),
            "by_package": {p: dict(c) for p, c in by_package.items()},
            "per_file": per_file,
        }, indent=2))
        return 0

    if args.category:
        for rel, lineno, cat, line in detail_lines:
            print(f"{rel}:{lineno}  {line}")
        print(f"\n{len(detail_lines)} lines in category {args.category!r}")
        return 0

    print(f"ESTIMATE tag audit — root: {root}")
    print(f"Total tags: {total}")
    print()
    print("By category:")
    for cat in ("placeholder", "bare_reason", "has_citation", "has_standard",
                "scaled_from_citation", "unlabeled"):
        n = by_category.get(cat, 0)
        pct = 100.0 * n / total if total else 0.0
        print(f"  {cat:22s}  {n:5d}  ({pct:4.1f}%)")
    print()
    print("By package (top 15):")
    rows = sorted(by_package.items(), key=lambda kv: -sum(kv[1].values()))
    for pkg, cats in rows[:15]:
        n = sum(cats.values())
        pct = 100.0 * n / total if total else 0.0
        print(f"  {pkg:22s}  {n:5d}  ({pct:4.1f}%)")

    if args.per_file:
        print()
        print("Top 20 files by ESTIMATE count:")
        for rel, n in sorted(per_file.items(), key=lambda kv: -kv[1])[:20]:
            print(f"  {n:4d}  {rel}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
