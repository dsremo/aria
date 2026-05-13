"""R43 — provenance + ingest mapper tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aria.digital_twin import external_components as ext


# ── Provenance tagging ─────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset():
    ext.reset_for_test()
    yield
    ext.reset_for_test()


def _make_doc(tmp_path, name, default_prov, items):
    p = tmp_path / f"{name}.json"
    doc = {
        "schema_version": 1,
        "source": name, "license": "TEST",
        "default_provenance": default_prov,
        "components": items,
    }
    p.write_text(json.dumps(doc))
    return p


class TestProvenance:
    def test_default_parametric_inherited(self, tmp_path):
        _make_doc(tmp_path, "p_v1", "parametric", [{
            "part_number": "A1", "name": "x", "category": "y",
            "subcategory": "z", "material": "", "key_dimensions": {},
            "mass_g": 0.0, "max_operating_temp_k": 300.0,
            "pressure_rating_kpa": None, "source": "", "extra": {},
        }])
        comps, _ = ext.load_external_catalog(tmp_path)
        assert comps["A1"].extra.get("provenance") == "parametric"

    def test_per_component_provenance_overrides_default(self, tmp_path):
        _make_doc(tmp_path, "i_v1", "parametric", [{
            "part_number": "B1", "name": "x", "category": "y",
            "subcategory": "z", "material": "", "key_dimensions": {},
            "mass_g": 0.0, "max_operating_temp_k": 300.0,
            "pressure_rating_kpa": None, "source": "",
            "extra": {}, "provenance": "ingested",
        }])
        comps, _ = ext.load_external_catalog(tmp_path)
        assert comps["B1"].extra.get("provenance") == "ingested"

    def test_provenance_summary(self, tmp_path, monkeypatch):
        _make_doc(tmp_path, "p_v1", "parametric", [{
            "part_number": "C1", "name": "x", "category": "y",
            "subcategory": "z", "material": "", "key_dimensions": {},
            "mass_g": 0.0, "max_operating_temp_k": 300.0,
            "pressure_rating_kpa": None, "source": "", "extra": {},
        }])
        _make_doc(tmp_path, "i_v1", "ingested", [{
            "part_number": "C2", "name": "x", "category": "y",
            "subcategory": "z", "material": "", "key_dimensions": {},
            "mass_g": 0.0, "max_operating_temp_k": 300.0,
            "pressure_rating_kpa": None, "source": "", "extra": {},
        }])
        monkeypatch.setattr(ext, "_default_external_root", lambda: tmp_path)
        ext.reset_for_test()
        summary = ext.provenance_summary()
        assert summary == {"parametric": 1, "ingested": 1}

    def test_filter_by_provenance(self, tmp_path, monkeypatch):
        _make_doc(tmp_path, "mix_v1", "parametric", [
            {
                "part_number": "P1", "name": "x", "category": "y",
                "subcategory": "z", "material": "", "key_dimensions": {},
                "mass_g": 0.0, "max_operating_temp_k": 300.0,
                "pressure_rating_kpa": None, "source": "", "extra": {},
            },
            {
                "part_number": "P2", "name": "x", "category": "y",
                "subcategory": "z", "material": "", "key_dimensions": {},
                "mass_g": 0.0, "max_operating_temp_k": 300.0,
                "pressure_rating_kpa": None, "source": "",
                "extra": {}, "provenance": "ingested",
            },
        ])
        monkeypatch.setattr(ext, "_default_external_root", lambda: tmp_path)
        ext.reset_for_test()
        only_parametric = ext.filter_by_provenance("parametric")
        only_ingested = ext.filter_by_provenance("ingested")
        assert "P1" in only_parametric and "P2" not in only_parametric
        assert "P2" in only_ingested and "P1" not in only_ingested


# ── Production catalog fully tagged ────────────────────────────


class TestProductionProvenance:
    def test_all_external_parts_have_provenance(self):
        for pn, c in ext.get_external_components().items():
            assert "provenance" in c.extra, f"part {pn} missing provenance"

    def test_dominant_provenance_is_parametric(self):
        """R43 acceptance — every part the parametric generator wrote
        is tagged 'parametric' so a downstream filter can keep only
        the (currently zero) ingested parts."""
        summary = ext.provenance_summary()
        # parametric must dominate today; ingested may be 0.
        assert summary.get("parametric", 0) >= 5000


# ── Ingest mapper smoke tests ──────────────────────────────────


class TestIngestMappers:
    def test_librecube_mapper(self):
        from scripts.ingest_external_catalogs import map_librecube
        out = map_librecube([
            {
                "partNumber": "LC-RF-001",
                "name": "S-band TX",
                "category": "avionics",
                "subcategory": "rf_xcvr",
                "mass_g": 220.0, "power_w": 4.0,
            },
            {"partNumber": ""},   # empty — must be skipped
        ])
        assert len(out) == 1
        assert out[0]["part_number"] == "LIBRECUBE-LC-RF-001"
        assert out[0]["provenance"] == "ingested"
        assert out[0]["extra"]["power_w"] == 4.0

    def test_escc_mapper(self):
        from scripts.ingest_external_catalogs import map_escc_qpl
        out = map_escc_qpl([
            {"PART_NUMBER": "ABC-1", "DESCRIPTION": "Cap 10 µF",
             "CATEGORY": "electronics", "MASS_G": "0.05"},
        ])
        assert out[0]["part_number"].startswith("ESCC-")
        assert out[0]["provenance"] == "ingested"

    def test_oomi_mapper(self):
        from scripts.ingest_external_catalogs import map_oomi
        out = map_oomi([
            {"ORU_ID": "WHC-FAN-04", "nomenclature": "WHC fan",
             "subsystem": "waste", "mass_kg": 3.8, "count_on_iss": 4},
        ])
        assert out[0]["part_number"] == "OOMI-WHC-FAN-04"
        assert out[0]["mass_g"] == 3800.0
        assert out[0]["provenance"] == "ingested"

    def test_github_mapper_filters_by_prefix(self):
        from scripts.ingest_external_catalogs import map_github_repo
        out = map_github_repo([
            {"name": "cFS_apps_HK", "description": "HK app",
             "default_branch": "main", "html_url": "x", "stargazers_count": 1,
             "full_name": "nasa/cFS_apps_HK"},
            {"name": "unrelated_repo", "description": "x"},
        ])
        assert len(out) == 1
        assert out[0]["category"] == "software"
        assert out[0]["subcategory"] == "flight_app"
