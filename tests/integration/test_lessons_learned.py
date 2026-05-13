from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aria.cognitive.doctrine import DoctrineKind, DoctrineLoader
from aria.knowledge.lessons_learned import (
    LessonRecord,
    LessonsLearnedStore,
    NtrsSearchClient,
    load_curated_lessons,
    write_lessons_to_doctrine,
)


class TestCuratedLessons:
    def test_curated_set_present(self):
        records = load_curated_lessons()
        ids = {record.record_id for record in records}
        assert "apollo-13-cryo-stir" in ids
        assert "sts-107-columbia" in ids
        assert "mco-1999-units" in ids
        assert "challenger-sts-51l" in ids
        assert "ariane-5-501" in ids
        assert "iridium-cosmos-2009" in ids
        assert len(records) >= 25

    def test_each_record_has_citation(self):
        for record in load_curated_lessons():
            assert record.citation, f"missing citation: {record.record_id}"
            assert record.summary, f"missing summary: {record.record_id}"


class TestStorePersistence:
    def test_round_trip(self, tmp_path: Path):
        store = LessonsLearnedStore()
        store.extend(load_curated_lessons())
        out = tmp_path / "lessons.json"
        store.write(out)
        assert out.exists()
        store2 = LessonsLearnedStore()
        loaded = store2.load(out)
        assert loaded == len(store.records)

    def test_load_missing_file_returns_zero(self, tmp_path: Path):
        store = LessonsLearnedStore()
        assert store.load(tmp_path / "no_such.json") == 0

    def test_load_corrupt_returns_zero(self, tmp_path: Path):
        target = tmp_path / "lessons.json"
        target.write_text("not json at all")
        store = LessonsLearnedStore()
        assert store.load(target) == 0


class TestDoctrineExport:
    def test_lessons_become_loadable_doctrine_entries(self, tmp_path: Path):
        records = load_curated_lessons()
        target = tmp_path / "doctrine" / "lessons.json"
        n = write_lessons_to_doctrine(records, doctrine_path=target)
        assert n == len(records)
        bundle = DoctrineLoader(tmp_path / "doctrine").load()
        assert any(
            entry.kind == DoctrineKind.INCIDENT_REPORT
            for entry in bundle.entries
        )
        ids = {entry.rule_id for entry in bundle.entries}
        assert "LL-apollo-13-cryo-stir" in ids


class TestNtrsAdapter:
    def test_search_handles_url_error(self):
        opener = MagicMock()
        import urllib.error
        opener.open.side_effect = urllib.error.URLError("connection refused")
        client = NtrsSearchClient(opener=opener)
        results = client.search("apollo")
        assert results == []

    def test_search_handles_malformed_json(self):
        opener = MagicMock()
        resp = MagicMock()
        resp.read.return_value = b"<html>not json</html>"
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=None)
        opener.open.return_value = resp
        client = NtrsSearchClient(opener=opener)
        results = client.search("apollo")
        assert results == []

    def test_search_returns_results(self):
        opener = MagicMock()
        payload = {"results": [
            {"id": "12345", "title": "Apollo 13 anomaly review"},
            {"id": "67890", "title": "Mars Climate Orbiter mishap"},
        ]}
        resp = MagicMock()
        resp.read.return_value = json.dumps(payload).encode("utf-8")
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=None)
        opener.open.return_value = resp
        client = NtrsSearchClient(opener=opener)
        results = client.search("apollo 13")
        assert len(results) == 2
        assert results[0]["id"] == "12345"


class TestDoctrineLoaderPicksUpLessons:
    def test_lessons_present_in_repo_doctrine_dir(self):
        bundle = DoctrineLoader(Path("data/doctrine")).load()
        ll_ids = {
            entry.rule_id for entry in bundle.entries
            if entry.kind == DoctrineKind.INCIDENT_REPORT
            and entry.rule_id.startswith("LL-")
        }
        assert ll_ids, "expected LL- doctrine entries from curated NASA lessons"
        assert "LL-apollo-13-cryo-stir" in ll_ids
