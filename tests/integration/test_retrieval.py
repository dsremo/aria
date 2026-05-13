from __future__ import annotations

import pytest

from aria.knowledge import (
    LessonRecord,
    TfIdfIndex,
    build_default_lesson_index,
    load_curated_lessons,
)


class TestTfIdfBasics:
    def test_empty_query_returns_empty(self):
        index = build_default_lesson_index()
        assert index.search("") == ()

    def test_index_contains_all_curated_records(self):
        index = build_default_lesson_index(include_curated=True, include_llis=False)
        assert index.n_documents == len(load_curated_lessons())


class TestRetrievalQuality:
    def test_apollo_13_query_finds_apollo_13(self):
        index = build_default_lesson_index()
        hits = index.search("Apollo 13 cryo tank rupture", top_k=3)
        assert hits
        assert hits[0].record.record_id == "apollo-13-cryo-stir"

    def test_columbia_query_finds_sts107(self):
        index = build_default_lesson_index()
        hits = index.search("foam strike RCC leading edge breakup", top_k=3)
        assert hits
        ids = {hit.record.record_id for hit in hits}
        assert "sts-107-columbia" in ids

    def test_units_query_finds_mco_and_cassini(self):
        index = build_default_lesson_index()
        hits = index.search("unit conversion lbf newton", top_k=5)
        ids = {hit.record.record_id for hit in hits}
        assert "mco-1999-units" in ids or "cassini-grand-finale-units" in ids

    def test_emu_water_query_finds_parmitano(self):
        index = build_default_lesson_index()
        hits = index.search("EMU helmet water drowning EVA", top_k=3)
        assert hits
        assert any(
            hit.record.record_id == "parmitano-eva-water"
            for hit in hits
        )

    def test_collision_query_finds_iridium_cosmos(self):
        index = build_default_lesson_index()
        hits = index.search("Iridium Cosmos collision debris", top_k=3)
        assert hits
        assert any(
            hit.record.record_id == "iridium-cosmos-2009"
            for hit in hits
        )

    def test_top_k_respected(self):
        index = build_default_lesson_index()
        hits = index.search("apollo", top_k=2)
        assert len(hits) <= 2

    def test_matched_terms_populated(self):
        index = build_default_lesson_index()
        hits = index.search("cryo tank rupture", top_k=1)
        assert hits
        assert hits[0].matched_terms


class TestKeywordBoost:
    def test_keyword_match_boosts_score(self):
        index = TfIdfIndex()
        record_a = LessonRecord(
            record_id="a", title="Generic title",
            summary="Lots of irrelevant text without the magic word here.",
            keywords=("magic-keyword",),
        )
        record_b = LessonRecord(
            record_id="b", title="The magic-keyword in the title",
            summary="Body text with no other matches at all.",
            keywords=(),
        )
        index.add(record_a)
        index.add(record_b)
        hits = index.search("magic-keyword")
        assert hits[0].record.record_id == "a"


class TestNoMatch:
    def test_unrelated_query_returns_empty_or_low_score(self):
        index = build_default_lesson_index(include_curated=True, include_llis=False)
        hits = index.search("zzzzzzzzz nonexistent fhqwhgads")
        assert hits == ()
