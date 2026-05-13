"""Research digest builder.

Polls each ResearchFilter against arXiv via ArxivClient, applies
the filter, and produces a structured digest the operator UI / CLI
can consume.

Designed to run as a daily cron. Output lands at
``data/runtime/research/digest_<YYYY-MM-DD>.md`` so the history is
walkable.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence

import structlog

from aria.research.arxiv_client import ArxivClient, ArxivPaper
from aria.research.filters import DEFAULT_FILTERS, ResearchFilter

logger = structlog.get_logger()


@dataclass(frozen=True)
class DigestSection:
    """One subsystem's relevant papers from a single digest run."""

    filter_name: str
    description: str
    n_papers_examined: int
    n_papers_matched: int
    matches: tuple[ArxivPaper, ...]


@dataclass(frozen=True)
class ResearchDigest:
    """Daily research digest across all configured filters."""

    generated_iso: str
    sections: tuple[DigestSection, ...]

    @property
    def total_matches(self) -> int:
        return sum(s.n_papers_matched for s in self.sections)

    def as_markdown(self) -> str:
        lines: list[str] = []
        lines.append(f"# ARIA research digest — {self.generated_iso}")
        lines.append("")
        lines.append(
            f"Total matches across {len(self.sections)} subsystems: "
            f"**{self.total_matches}**."
        )
        lines.append("")
        for section in self.sections:
            lines.append(f"## {section.filter_name}")
            lines.append(f"_{section.description}_")
            lines.append("")
            lines.append(
                f"Examined {section.n_papers_examined} recent papers; "
                f"{section.n_papers_matched} matched."
            )
            if not section.matches:
                lines.append("")
                lines.append("_No matches this cycle._")
                lines.append("")
                continue
            lines.append("")
            for paper in section.matches:
                lines.append(f"### [{paper.title}]({paper.abs_url})")
                lines.append(
                    f"_{', '.join(paper.authors[:5])}"
                    f"{'…' if len(paper.authors) > 5 else ''}_"
                )
                lines.append(f"`{paper.arxiv_id}` "
                             f"· {paper.primary_category} "
                             f"· {paper.published_iso[:10]}")
                summary = paper.summary.replace("\n", " ").strip()
                if len(summary) > 350:
                    summary = summary[:347] + "..."
                lines.append("")
                lines.append(summary)
                lines.append("")
        return "\n".join(lines)

    def as_json(self) -> str:
        # Convert nested tuples / dataclasses for JSON.
        data = {
            "generated_iso": self.generated_iso,
            "total_matches": self.total_matches,
            "sections": [
                {
                    "filter_name": s.filter_name,
                    "description": s.description,
                    "n_papers_examined": s.n_papers_examined,
                    "n_papers_matched": s.n_papers_matched,
                    "matches": [
                        {**asdict(paper)} for paper in s.matches
                    ],
                }
                for s in self.sections
            ],
        }
        return json.dumps(data, indent=2, sort_keys=True)


# ── Builder ─────────────────────────────────────────────────────


def build_digest(
    *,
    client: Optional[ArxivClient] = None,
    filters: Sequence[ResearchFilter] = DEFAULT_FILTERS,
    max_results_per_category: int = 50,
    output_dir: Optional[Path] = None,
) -> ResearchDigest:
    """Run every filter against the configured arXiv categories,
    aggregate matches, and (optionally) persist the digest to disk.
    """
    arxiv = client or ArxivClient()

    # Collect unique categories across all filters so we don't query
    # arXiv multiple times for the same category.
    categories_to_query: set[str] = set()
    for filt in filters:
        categories_to_query.update(filt.categories)

    paper_pool: dict[str, ArxivPaper] = {}
    for category in sorted(categories_to_query):
        try:
            papers = arxiv.search(
                category, max_results=max_results_per_category,
            )
        except Exception as exc:
            logger.warning(
                "research.arxiv_search_failed",
                category=category, error=str(exc),
            )
            continue
        for paper in papers:
            paper_pool[paper.arxiv_id] = paper

    sections: list[DigestSection] = []
    for filt in filters:
        candidates = [
            paper for paper in paper_pool.values()
            if any(cat in {paper.primary_category, *paper.categories}
                   for cat in filt.categories)
        ]
        matches = tuple(p for p in candidates if filt.matches(p))
        sections.append(DigestSection(
            filter_name=filt.name,
            description=filt.description,
            n_papers_examined=len(candidates),
            n_papers_matched=len(matches),
            matches=matches,
        ))

    digest = ResearchDigest(
        generated_iso=datetime.now(timezone.utc).isoformat(),
        sections=tuple(sections),
    )

    if output_dir is not None:
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            today = digest.generated_iso[:10]
            (output_dir / f"digest_{today}.md").write_text(
                digest.as_markdown(), encoding="utf-8",
            )
            (output_dir / f"digest_{today}.json").write_text(
                digest.as_json(), encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("research.digest_write_failed", error=str(exc))

    return digest
