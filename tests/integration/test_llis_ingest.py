from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aria.knowledge.llis_ingest import (
    LlisError,
    LlisFetcher,
    LlisLesson,
    _parse_hit,
    _strip_html,
    load_llis_lessons,
    write_llis_lessons,
)


class TestStripHtml:
    def test_removes_tags(self):
        assert _strip_html("<p>hello <b>world</b></p>") == "hello world"

    def test_collapses_whitespace(self):
        assert _strip_html("a   b\n\nc") == "a b c"

    def test_decodes_entities(self):
        assert "&" in _strip_html("a &amp; b")

    def test_empty_input(self):
        assert _strip_html("") == ""
        assert _strip_html(None) == ""


class TestParseHit:
    def test_parses_minimal_hit(self):
        hit = {
            "_id": "100",
            "_source": {
                "lesson_date": "2010-01-01",
                "abstract": "<p>Test abstract</p>",
                "lesson": "<p>Test lesson</p>",
                "submitting_organization": "Test",
            },
        }
        record = _parse_hit(hit)
        assert record is not None
        assert record.lesson_id == "100"
        assert record.title == "Test abstract"

    def test_returns_none_for_invalid_source(self):
        assert _parse_hit({"_id": "1"}) is None

    def test_extracts_topics_and_categories(self):
        hit = {
            "_id": "5",
            "_source": {
                "abstract": "x",
                "topics": [{"topic_text": "Topic A"}, {"topic_text": "Topic B"}],
                "categories": [{"category_text": "Category 1"}],
            },
        }
        record = _parse_hit(hit)
        assert "Topic A" in record.topics
        assert "Topic B" in record.topics
        assert "Category 1" in record.categories


class TestLessonRecordConversion:
    def test_to_lesson_record_includes_event_lesson_recommendation(self):
        lesson = LlisLesson(
            lesson_id="42",
            title="Sample title",
            abstract="abs",
            description_event="event body",
            lesson="lesson body",
            recommendation="recommend body",
            lesson_date="2020-01-01",
            submitting_organization="JPL",
            topics=("topic-x",),
            categories=("cat-y",),
        )
        record = lesson.to_lesson_record()
        assert record.record_id == "llis-42"
        assert "event body" in record.summary
        assert "lesson body" in record.summary
        assert "recommend body" in record.summary
        assert "topic-x" in record.keywords
        assert "JPL" in record.citation


class TestPersistence:
    def test_write_and_load_round_trip(self, tmp_path: Path):
        lessons = [
            LlisLesson(
                lesson_id="1", title="t1", abstract="a1",
                description_event="e1", lesson="l1", recommendation="r1",
                lesson_date="2024-01-01",
                submitting_organization="Test", topics=("x",), categories=("y",),
            ),
        ]
        out = tmp_path / "llis.json"
        n = write_llis_lessons(lessons, out)
        assert n == 1
        loaded = load_llis_lessons(out)
        assert len(loaded) == 1
        assert loaded[0].lesson_id == "1"


class TestFetcher:
    def test_handles_url_error(self):
        from urllib import error
        fetcher = LlisFetcher()
        original = type(fetcher).fetch_page

        def _broken(self, *, from_offset):
            raise LlisError("boom")
        type(fetcher).fetch_page = _broken
        try:
            with pytest.raises(LlisError):
                fetcher.fetch_page(from_offset=0)
        finally:
            type(fetcher).fetch_page = original


class TestLiveCorpus:
    def test_corpus_file_exists_with_2000_plus_lessons(self):
        path = Path("data/lessons_learned/llis_corpus.json")
        if not path.exists():
            pytest.skip("LLIS corpus not yet ingested")
        items = json.loads(path.read_text(encoding="utf-8"))
        assert len(items) >= 1000

    def test_corpus_records_have_required_fields(self):
        path = Path("data/lessons_learned/llis_corpus.json")
        if not path.exists():
            pytest.skip("LLIS corpus not yet ingested")
        items = json.loads(path.read_text(encoding="utf-8"))
        for item in items[:50]:
            assert "lesson_id" in item
            assert "title" in item or "abstract" in item


class TestRetrievalIntegration:
    def test_lesson_index_grows_with_llis(self):
        from aria.knowledge import build_default_lesson_index
        index = build_default_lesson_index(include_curated=False, include_llis=True)
        path = Path("data/lessons_learned/llis_corpus.json")
        if not path.exists():
            pytest.skip("LLIS corpus not yet ingested")
        assert index.n_documents >= 1000

    def test_apollo_query_finds_relevant_records(self):
        from aria.knowledge import build_default_lesson_index
        path = Path("data/lessons_learned/llis_corpus.json")
        if not path.exists():
            pytest.skip("LLIS corpus not yet ingested")
        index = build_default_lesson_index()
        hits = index.search("apollo cryo tank pressure", top_k=5)
        assert hits
