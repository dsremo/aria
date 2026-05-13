from __future__ import annotations

from pathlib import Path

import pytest

from aria.integrations.kaitai_schema_registry import (
    DEFAULT_KAITAI_DIR,
    KaitaiSchemaRegistry,
    parse_kaitai_file,
    render_schema_for_advisor_prompt,
)


class TestRegistry:
    def test_loads_from_repo(self):
        registry = KaitaiSchemaRegistry.from_directory(DEFAULT_KAITAI_DIR)
        assert registry.n_schemas >= 100, (
            f"expected >=100 schemas; got {registry.n_schemas}"
        )

    def test_well_known_satellites_present(self):
        registry = KaitaiSchemaRegistry.from_directory(DEFAULT_KAITAI_DIR)
        ids = set(registry.schemas_by_id.keys())
        for required in ("aausat4", "aisat", "armadillo", "beesat"):
            assert required in ids, f"missing schema: {required}"

    def test_schema_has_endian_and_title(self):
        registry = KaitaiSchemaRegistry.from_directory(DEFAULT_KAITAI_DIR)
        record = registry.lookup("aausat4")
        assert record is not None
        assert record.title
        assert record.endian in ("be", "le")
        assert record.field_count > 0


class TestSearch:
    def test_keyword_search_finds_matches(self):
        registry = KaitaiSchemaRegistry.from_directory(DEFAULT_KAITAI_DIR)
        results = registry.search_by_keyword("aausat")
        assert results
        assert all("aausat" in record.schema_id.lower() for record in results)

    def test_keyword_search_empty_when_no_match(self):
        registry = KaitaiSchemaRegistry.from_directory(DEFAULT_KAITAI_DIR)
        results = registry.search_by_keyword("nonexistent_xyzzy_keyword")
        assert results == []


class TestRendering:
    def test_render_for_advisor_prompt(self):
        registry = KaitaiSchemaRegistry.from_directory(DEFAULT_KAITAI_DIR)
        record = registry.lookup("aausat4")
        text = render_schema_for_advisor_prompt(record)
        assert "aausat4" in text
        assert "endian" in text
        assert "fields:" in text


class TestParser:
    def test_returns_none_for_missing_file(self, tmp_path: Path):
        result = parse_kaitai_file(tmp_path / "nope.ksy")
        assert result is None

    def test_returns_none_for_wrong_suffix(self, tmp_path: Path):
        wrong = tmp_path / "x.txt"
        wrong.write_text("meta:\n  id: x\n")
        assert parse_kaitai_file(wrong) is None

    def test_parses_minimal_ksy(self, tmp_path: Path):
        path = tmp_path / "test.ksy"
        path.write_text(
            "meta:\n"
            "  id: testsat\n"
            "  title: Test satellite\n"
            "  endian: be\n"
            "doc-ref: 'https://example.com/test'\n"
            "doc: |\n"
            "  :field battery_voltage: packet.eps.battery\n"
            "  :field temp: packet.eps.temp\n"
            "seq:\n"
            "  - id: packet\n"
            "    type: u4\n"
        )
        record = parse_kaitai_file(path)
        assert record is not None
        assert record.schema_id == "testsat"
        assert record.title == "Test satellite"
        assert record.endian == "be"
        assert record.doc_ref == "https://example.com/test"
        assert record.field_count == 2
