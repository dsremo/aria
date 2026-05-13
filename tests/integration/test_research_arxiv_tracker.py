"""arXiv research-tracker tests.

Tests do NOT hit the live arXiv API — that would burn the polite-
poll budget + make CI flaky. Instead they patch
``urllib.request.urlopen`` with canned Atom XML responses that
mirror the actual arXiv API response shape.

A separate live probe (gated on ``ARIA_RUN_LIVE_ARXIV=1``)
exercises the real upstream when an operator wants live-mode
verification.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from aria.research import (
    ArxivClient,
    ArxivPaper,
    ResearchFilter,
    ResearchDigest,
    DEFAULT_FILTERS,
)
from aria.research import arxiv_client as arx_mod
from aria.research.digest import build_digest


# ── Canned Atom-XML payloads ────────────────────────────────────


_ATOM_TEMPLATE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <title>arXiv test feed</title>
  <id>http://arxiv.org/api/test</id>
  <opensearch:totalResults>2</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2604.17176v1</id>
    <updated>2026-04-22T12:00:00Z</updated>
    <published>2026-04-22T12:00:00Z</published>
    <title>Intent-aligned Autonomous Spacecraft Guidance via Reasoning Models</title>
    <summary>We present a hierarchical pipeline for spacecraft autonomy
    that uses a reasoning model (LLM) to produce waypoint constraints,
    fed to an SCP solver that enforces dynamics and safety. The reasoning
    model is fine-tuned via supervised fine-tuning of Qwen2.5-7B-Instruct
    with LoRA layers. We demonstrate intent-aligned trajectory generation
    on a docking benchmark.</summary>
    <author><name>A. Researcher</name></author>
    <author><name>B. Engineer</name></author>
    <link href="https://arxiv.org/abs/2604.17176v1" rel="alternate"/>
    <link href="https://arxiv.org/pdf/2604.17176v1" title="pdf"/>
    <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom"
                            term="cs.RO" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.RO" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2604.99999v1</id>
    <updated>2026-04-20T08:00:00Z</updated>
    <published>2026-04-20T08:00:00Z</published>
    <title>Coffee Brewing Kinematics for the Modern Astronaut</title>
    <summary>An exhaustive treatment of microgravity coffee bubble
    nucleation dynamics with no relevance whatsoever to spacecraft
    autonomy or guidance.</summary>
    <author><name>C. Coffeebean</name></author>
    <link href="https://arxiv.org/abs/2604.99999v1" rel="alternate"/>
    <link href="https://arxiv.org/pdf/2604.99999v1" title="pdf"/>
    <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom"
                            term="physics.flu-dyn" scheme="http://arxiv.org/schemas/atom"/>
    <category term="physics.flu-dyn" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
</feed>
"""


@pytest.fixture
def isolated_client(tmp_path: Path):
    return ArxivClient(
        cache_dir=tmp_path / "cache",
        rate_limit_delay_s=0.0,   # skip sleeps in tests
    )


def _mock_urlopen(payload: bytes, status: int = 200):
    response = io.BytesIO(payload)
    response.status = status

    class _Ctx:
        def __enter__(self):
            return response
        def __exit__(self, *_):
            return False

    return _Ctx()


# ── Atom parser correctness ─────────────────────────────────────


class TestAtomParser:
    def test_parses_two_entries(self, isolated_client):
        with patch.object(
            arx_mod.request, "urlopen",
            return_value=_mock_urlopen(_ATOM_TEMPLATE),
        ):
            papers = isolated_client.search("cs.RO", max_results=10)
        assert len(papers) == 2

    def test_first_entry_fields_correct(self, isolated_client):
        with patch.object(
            arx_mod.request, "urlopen",
            return_value=_mock_urlopen(_ATOM_TEMPLATE),
        ):
            papers = isolated_client.search("cs.RO", max_results=10)
        first = papers[0]
        assert first.arxiv_id == "2604.17176"
        assert "Intent-aligned" in first.title
        assert first.primary_category == "cs.RO"
        assert "cs.AI" in first.categories
        assert "Researcher" in first.authors[0]
        assert first.published_iso == "2026-04-22T12:00:00Z"
        assert "arxiv.org/abs/2604.17176" in first.abs_url
        assert "arxiv.org/pdf/2604.17176" in first.pdf_url

    def test_id_strips_version_suffix(self, isolated_client):
        with patch.object(
            arx_mod.request, "urlopen",
            return_value=_mock_urlopen(_ATOM_TEMPLATE),
        ):
            papers = isolated_client.search("cs.RO", max_results=10)
        # IDs must NOT carry the "v1" / "v2" tail.
        for paper in papers:
            assert not paper.arxiv_id.endswith("v1"), paper.arxiv_id

    def test_invalid_xml_raises(self, isolated_client):
        bogus = b"this is not XML at all"
        with patch.object(
            arx_mod.request, "urlopen",
            return_value=_mock_urlopen(bogus),
        ):
            with pytest.raises(RuntimeError, match="non-XML"):
                isolated_client.search("cs.RO", max_results=10)

    def test_max_results_validation(self, isolated_client):
        with pytest.raises(ValueError, match="max_results"):
            isolated_client.search("cs.RO", max_results=0)
        with pytest.raises(ValueError):
            isolated_client.search("cs.RO", max_results=10_000)


# ── Cache behaviour ─────────────────────────────────────────────


class TestArxivCache:
    def test_second_call_within_ttl_skips_network(self, isolated_client):
        call_count = {"n": 0}

        def _counting_urlopen(*args, **kwargs):
            call_count["n"] += 1
            return _mock_urlopen(_ATOM_TEMPLATE)

        with patch.object(
            arx_mod.request, "urlopen", side_effect=_counting_urlopen,
        ):
            isolated_client.search("cs.RO", max_results=10)
            isolated_client.search("cs.RO", max_results=10)
        assert call_count["n"] == 1

    def test_cache_expires_after_ttl(self, tmp_path):
        client = ArxivClient(
            cache_dir=tmp_path / "cache",
            cache_ttl_s=0.0,   # immediately stale
            rate_limit_delay_s=0.0,
        )
        call_count = {"n": 0}

        def _counting_urlopen(*args, **kwargs):
            call_count["n"] += 1
            return _mock_urlopen(_ATOM_TEMPLATE)

        with patch.object(
            arx_mod.request, "urlopen", side_effect=_counting_urlopen,
        ):
            client.search("cs.RO", max_results=10)
            client.search("cs.RO", max_results=10)
        assert call_count["n"] == 2


# ── Filter logic ────────────────────────────────────────────────


class TestResearchFilter:
    def _intent_aligned_paper(self) -> ArxivPaper:
        return ArxivPaper(
            arxiv_id="2604.17176",
            title="Intent-aligned Autonomous Spacecraft Guidance",
            authors=("A. Researcher",),
            summary=(
                "We use a reasoning model to produce waypoint constraints"
                " for spacecraft autonomy, with SCP enforcing safety."
            ),
            primary_category="cs.RO",
            categories=("cs.RO", "cs.AI"),
            published_iso="2026-04-22T12:00:00Z",
            updated_iso="2026-04-22T12:00:00Z",
            pdf_url="x", abs_url="y",
        )

    def _coffee_paper(self) -> ArxivPaper:
        return ArxivPaper(
            arxiv_id="2604.99999",
            title="Coffee Brewing Kinematics",
            authors=("C. Coffeebean",),
            summary="microgravity coffee bubble nucleation",
            primary_category="physics.flu-dyn",
            categories=("physics.flu-dyn",),
            published_iso="2026-04-20T08:00:00Z",
            updated_iso="2026-04-20T08:00:00Z",
            pdf_url="x", abs_url="y",
        )

    def test_autonomy_filter_matches_relevant_paper(self):
        autonomy = next(f for f in DEFAULT_FILTERS if f.name == "autonomy")
        assert autonomy.matches(self._intent_aligned_paper())

    def test_autonomy_filter_rejects_irrelevant_paper(self):
        autonomy = next(f for f in DEFAULT_FILTERS if f.name == "autonomy")
        assert not autonomy.matches(self._coffee_paper())

    def test_propulsion_filter_rejects_autonomy_paper(self):
        propulsion = next(f for f in DEFAULT_FILTERS if f.name == "propulsion")
        # "Hall thruster" is not in the autonomy paper's text.
        assert not propulsion.matches(self._intent_aligned_paper())

    def test_filter_keyword_case_insensitive(self):
        autonomy = next(f for f in DEFAULT_FILTERS if f.name == "autonomy")
        loud_paper = ArxivPaper(
            arxiv_id="x", title="SPACECRAFT AUTONOMY in the deep solar system",
            authors=(), summary="", primary_category="cs.RO",
            categories=("cs.RO",), published_iso="", updated_iso="",
            pdf_url="", abs_url="",
        )
        assert autonomy.matches(loud_paper)

    def test_must_have_any_gate(self):
        ml_safety = next(f for f in DEFAULT_FILTERS if f.name == "ml_safety")
        # Has a keyword (sandbagging) but no must_have_any term.
        no_safety = ArxivPaper(
            arxiv_id="x", title="Sandbagging in language models",
            authors=(), summary="we discuss sandbagging extensively but"
            " never mention any safety alignment robustness verification term"
            " from the must-have list at all not even once.",
            primary_category="cs.LG", categories=("cs.LG",),
            published_iso="", updated_iso="", pdf_url="", abs_url="",
        )
        # The summary above does include "safety" and "alignment" and "robust"
        # explicitly so it WILL match — verify positive case first.
        assert ml_safety.matches(no_safety)

        # Now a paper that has the keyword but no must-have term.
        keyword_only = ArxivPaper(
            arxiv_id="x", title="Sandbagging in toddlers",
            authors=(), summary="just keyword nothing else relevant",
            primary_category="cs.LG", categories=("cs.LG",),
            published_iso="", updated_iso="", pdf_url="", abs_url="",
        )
        assert not ml_safety.matches(keyword_only)


class TestDefaultFilters:
    def test_seven_filters_loaded(self):
        names = {f.name for f in DEFAULT_FILTERS}
        assert names == {
            "autonomy", "ml_safety", "guidance_navigation",
            "life_support", "propulsion", "radiation", "conjunction",
        }

    def test_each_filter_has_categories_and_keywords(self):
        for f in DEFAULT_FILTERS:
            assert f.categories, f"{f.name} has no categories"
            assert f.keywords, f"{f.name} has no keywords"
            assert f.description, f"{f.name} has no description"


# ── Digest builder ──────────────────────────────────────────────


class TestDigestBuilder:
    def test_digest_aggregates_by_filter(self, tmp_path):
        client = ArxivClient(
            cache_dir=tmp_path / "cache",
            rate_limit_delay_s=0.0,
        )
        # Mock urlopen to return the same Atom payload every call —
        # this simulates a "two papers per category" feed.
        with patch.object(
            arx_mod.request, "urlopen",
            side_effect=lambda *args, **kwargs: _mock_urlopen(_ATOM_TEMPLATE),
        ):
            digest = build_digest(client=client, max_results_per_category=10)

        assert isinstance(digest, ResearchDigest)
        assert len(digest.sections) == len(DEFAULT_FILTERS)
        # The intent-aligned paper should hit the autonomy filter.
        autonomy_section = next(
            s for s in digest.sections if s.filter_name == "autonomy"
        )
        assert autonomy_section.n_papers_matched >= 1
        # The coffee paper should be filtered out everywhere.
        for section in digest.sections:
            for paper in section.matches:
                assert paper.arxiv_id != "2604.99999", (
                    f"coffee paper leaked into {section.filter_name}"
                )

    def test_digest_writes_files_when_output_dir(self, tmp_path):
        client = ArxivClient(
            cache_dir=tmp_path / "cache",
            rate_limit_delay_s=0.0,
        )
        out = tmp_path / "out"
        with patch.object(
            arx_mod.request, "urlopen",
            side_effect=lambda *args, **kwargs: _mock_urlopen(_ATOM_TEMPLATE),
        ):
            digest = build_digest(
                client=client, max_results_per_category=10,
                output_dir=out,
            )
        today = digest.generated_iso[:10]
        assert (out / f"digest_{today}.md").is_file()
        assert (out / f"digest_{today}.json").is_file()

    def test_markdown_renders_no_exception(self, tmp_path):
        client = ArxivClient(
            cache_dir=tmp_path / "cache",
            rate_limit_delay_s=0.0,
        )
        with patch.object(
            arx_mod.request, "urlopen",
            side_effect=lambda *args, **kwargs: _mock_urlopen(_ATOM_TEMPLATE),
        ):
            digest = build_digest(client=client, max_results_per_category=10)
        markdown = digest.as_markdown()
        assert "ARIA research digest" in markdown
        assert "autonomy" in markdown.lower()


# ── Live probe (opt-in only) ────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("ARIA_RUN_LIVE_ARXIV") != "1",
    reason="live arXiv probe; gated on ARIA_RUN_LIVE_ARXIV=1",
)
def test_live_arxiv_returns_recent_cs_ro_papers(tmp_path):
    """Opt-in: actually hit arXiv with a real query for cs.RO."""
    client = ArxivClient(
        cache_dir=tmp_path / "live_cache",
        rate_limit_delay_s=3.0,
    )
    papers = client.search("cs.RO", max_results=5)
    assert len(papers) >= 1
    # IDs should follow YYMM.NNNNN pattern.
    for paper in papers:
        assert "." in paper.arxiv_id
        assert paper.title
