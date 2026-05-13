from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aria.knowledge.ecss_ingest import (
    EcssAuthError,
    EcssFetcher,
    EcssStandardRecord,
    _build_cookie_header,
    _classify_type,
    _slug_to_standard_id,
    load_ecss_records,
    write_ecss_records,
)


class TestSlugToStandardId:
    def test_pure_numeric_slug_uses_title(self):
        result = _slug_to_standard_id(
            "42506", "ECSS-P-00C Rev.1 – Standardization objectives",
        )
        assert "ECSS-P-00C" in result.upper()

    def test_slug_with_id_prefix(self):
        result = _slug_to_standard_id(
            "ecss-e-st-32-02c-rev-2-structural-design",
            "ECSS-E-ST-32-02C Rev.2 – Structural design",
        )
        assert "ECSS-E-ST" in result.upper()


class TestClassifyType:
    def test_engineering(self):
        assert _classify_type("ECSS-E-ST-32-02C") == "engineering"

    def test_product_assurance(self):
        assert _classify_type("ECSS-Q-ST-30C") == "product_assurance"

    def test_management(self):
        assert _classify_type("ECSS-M-ST-10C") == "management"

    def test_other(self):
        assert _classify_type("FOOBAR") == "other"


class TestCookieHeader:
    def test_empty_when_no_env(self, monkeypatch):
        for var in ("ARIA_ECSS_COOKIE_PHPSESSID", "ARIA_ECSS_COOKIE_WFWAF",
                    "ARIA_ECSS_COOKIE_LOGGED_IN", "ARIA_ECSS_COOKIE_SEC"):
            monkeypatch.delenv(var, raising=False)
        assert _build_cookie_header() == ""

    def test_combines_set_cookies(self, monkeypatch):
        monkeypatch.setenv("ARIA_ECSS_COOKIE_PHPSESSID", "abc123")
        monkeypatch.setenv("ARIA_ECSS_COOKIE_LOGGED_IN", "wp_logged=1")
        monkeypatch.delenv("ARIA_ECSS_COOKIE_WFWAF", raising=False)
        monkeypatch.delenv("ARIA_ECSS_COOKIE_SEC", raising=False)
        header = _build_cookie_header()
        assert "PHPSESSID=abc123" in header
        assert "wp_logged=1" in header


class TestFetcherAuth:
    def test_raises_when_no_cookies(self, monkeypatch):
        for var in ("ARIA_ECSS_COOKIE_PHPSESSID", "ARIA_ECSS_COOKIE_WFWAF",
                    "ARIA_ECSS_COOKIE_LOGGED_IN", "ARIA_ECSS_COOKIE_SEC"):
            monkeypatch.delenv(var, raising=False)
        fetcher = EcssFetcher()
        with pytest.raises(EcssAuthError, match="ARIA_ECSS_COOKIE"):
            fetcher._open("https://ecss.nl/")


class TestRecordRoundTrip:
    def test_persistence(self, tmp_path: Path):
        records = [
            EcssStandardRecord(
                standard_id="ECSS-E-ST-32C",
                title="Structural general requirements",
                url="https://ecss.nl/standard/ecss-e-st-32c/",
                issue_date="15 march 2017",
                standard_type="engineering",
                pdf_urls=("https://ecss.nl/wp-content/uploads/standards/ecss-e-st-32c.pdf",),
                abstract="A summary",
            ),
        ]
        out = tmp_path / "ecss.json"
        n = write_ecss_records(records, out)
        assert n == 1
        loaded = load_ecss_records(out)
        assert len(loaded) == 1
        assert loaded[0].standard_id == "ECSS-E-ST-32C"

    def test_load_missing_returns_empty(self, tmp_path: Path):
        assert load_ecss_records(tmp_path / "nope.json") == []


class TestDoctrineExport:
    def test_to_doctrine_entry_has_required_fields(self):
        record = EcssStandardRecord(
            standard_id="ECSS-E-ST-32C",
            title="ECSS-E-ST-32C – Structural design (15 March 2017)",
            url="https://ecss.nl/standard/ecss-e-st-32c/",
            issue_date="15 march 2017",
            standard_type="engineering",
            abstract="Structural margin requirements",
        )
        entry = record.to_doctrine_entry()
        assert entry["rule_id"] == "ECSS-E-ST-32C"
        assert "structural" in entry["title"].lower()
        assert "structural" in entry["body"].lower() or "structural" in entry["title"].lower()
        assert entry["citation"]
        assert entry["kind"] in ("flight_rule", "reference")


class TestLiveCorpus:
    def test_live_ecss_catalog_present(self):
        path = Path("data/ecss/active_standards.json")
        if not path.exists():
            pytest.skip("ECSS corpus not yet ingested")
        items = json.loads(path.read_text(encoding="utf-8"))
        assert len(items) >= 100

    def test_doctrine_loader_includes_ecss_catalog(self):
        from aria.cognitive.doctrine import DoctrineLoader
        bundle = DoctrineLoader(Path("data/doctrine")).load()
        ecss_entries = [
            e for e in bundle.entries
            if e.rule_id.upper().startswith("ECSS-")
        ]
        if not ecss_entries:
            pytest.skip("ECSS doctrine catalog not yet materialised")
        assert len(ecss_entries) >= 100
