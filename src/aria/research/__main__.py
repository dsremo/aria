"""CLI: `python -m aria.research` runs the daily research digest.

Hits arXiv (politely, with 3 s rate-limit between calls), filters
matches per ARIA subsystem, and writes the digest to
``data/runtime/research/`` by default. Returns exit code 0 on
success, 1 on any internal error.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from aria.research.arxiv_client import ArxivClient
from aria.research.digest import build_digest
from aria.research.filters import DEFAULT_FILTERS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the daily ARIA research digest against arXiv. "
            "Polls cs.RO + cs.LG + cs.AI + math.OC + eess.SY + "
            "q-bio.OT + physics.* categories, filters per subsystem."
        ),
    )
    parser.add_argument(
        "--max-per-category", type=int, default=50,
        help="Cap of recent papers fetched per arXiv category (default 50)",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("ARIA_RUNTIME_DIR", "data/runtime")
                + "/research",
        help="Where to drop digest_<YYYY-MM-DD>.{md,json}",
    )
    parser.add_argument(
        "--no-write", action="store_true",
        help="Print digest to stdout instead of writing files.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Use JSON output (default: markdown).",
    )
    args = parser.parse_args(argv)

    output_dir = None if args.no_write else Path(args.output_dir)
    digest = build_digest(
        max_results_per_category=args.max_per_category,
        output_dir=output_dir,
    )

    if args.no_write:
        print(digest.as_json() if args.json else digest.as_markdown())
    else:
        print(
            f"Wrote digest to {output_dir}/digest_*"
            f" — {digest.total_matches} matches across "
            f"{len(digest.sections)} sections."
        )

    return 0 if digest.total_matches >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
