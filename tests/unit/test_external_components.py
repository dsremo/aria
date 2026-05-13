"""R40 — external component catalog tests.

Acceptance §3 (Tier-3):
  1. Catalog count goes from 1 098 → ≥ 5 000 line items.
  2. Every imported part has source citation + license tag.
  3. ARIA part lookup API returns the same shape as today.
  4. Mass / power / thermal queries against the new catalog stay < 50 ms.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from aria.digital_twin import components_db, external_components as ext
from aria.digital_twin.components_db import Component


# ── Fixture: tiny synthetic external catalog ────────────────────


@pytest.fixture
def synthetic_external(tmp_path):
    doc = {
        "schema_version": 1,
        "source": "TestSource",
        "license": "TEST-PUBLIC",
        "url": "",
        "ingested_at": "2026-04-26",
        "components": [
            {
                "part_number": "TEST-001",
                "name": "Test resistor",
                "category": "electronics",
                "subcategory": "resistor",
                "material": "thick film",
                "key_dimensions": {"case": "0805"},
                "mass_g": 0.005,
                "max_operating_temp_k": 428.0,
                "pressure_rating_kpa": None,
                "source": "TestSource cite",
                "extra": {"ohms": 1000.0},
            },
            {
                "part_number": "TEST-002",
                "name": "Test capacitor",
                "category": "electronics",
                "subcategory": "capacitor",
                "material": "X7R",
                "key_dimensions": {"case": "0805"},
                "mass_g": 0.008,
                "max_operating_temp_k": 398.0,
                "pressure_rating_kpa": None,
                "source": "TestSource cite",
                "extra": {"capacitance_f": 1e-6},
            },
        ],
    }
    p = tmp_path / "test_v1.json"
    p.write_text(json.dumps(doc))
    return tmp_path


# ── Loader behaviour ────────────────────────────────────────────


class TestLoader:
    def test_loads_components(self, synthetic_external):
        comps, tags = ext.load_external_catalog(synthetic_external)
        assert len(comps) == 2
        assert "TEST-001" in comps
        assert "TEST-002" in comps

    def test_records_license_tag(self, synthetic_external):
        _, tags = ext.load_external_catalog(synthetic_external)
        assert tags["TEST-001"].license == "TEST-PUBLIC"
        assert tags["TEST-001"].source == "TestSource"

    def test_returns_real_components(self, synthetic_external):
        comps, _ = ext.load_external_catalog(synthetic_external)
        c = comps["TEST-001"]
        assert isinstance(c, Component)
        assert c.category == "electronics"
        assert c.subcategory == "resistor"

    def test_missing_root_returns_empty(self, tmp_path):
        comps, tags = ext.load_external_catalog(tmp_path / "nope")
        assert comps == {}
        assert tags == {}

    def test_strict_mode_raises_on_duplicate(self, tmp_path):
        # Two files claiming the same part_number.
        d = {
            "schema_version": 1, "source": "A", "license": "X",
            "components": [{
                "part_number": "DUP", "name": "x", "category": "y",
                "subcategory": "z", "material": "", "key_dimensions": {},
                "mass_g": 1.0, "max_operating_temp_k": 300.0,
                "pressure_rating_kpa": None, "source": "", "extra": {},
            }],
        }
        (tmp_path / "a.json").write_text(json.dumps(d))
        d2 = dict(d); d2["source"] = "B"
        (tmp_path / "b.json").write_text(json.dumps(d2))
        with pytest.raises(RuntimeError):
            ext.load_external_catalog(tmp_path, strict=True)

    def test_lenient_mode_drops_duplicate(self, tmp_path):
        d = {
            "schema_version": 1, "source": "A", "license": "X",
            "components": [{
                "part_number": "DUP", "name": "x", "category": "y",
                "subcategory": "z", "material": "", "key_dimensions": {},
                "mass_g": 1.0, "max_operating_temp_k": 300.0,
                "pressure_rating_kpa": None, "source": "", "extra": {},
            }],
        }
        (tmp_path / "a.json").write_text(json.dumps(d))
        d2 = dict(d); d2["source"] = "B"
        (tmp_path / "b.json").write_text(json.dumps(d2))
        comps, _ = ext.load_external_catalog(tmp_path, strict=False)
        assert len(comps) == 1   # second file's duplicate dropped


# ── Production catalog ─────────────────────────────────────────


class TestProductionCatalog:
    def setup_method(self) -> None:
        ext.reset_for_test()

    def teardown_method(self) -> None:
        ext.reset_for_test()

    def test_meets_acceptance_5000_parts(self):
        """R40 §3 Tier-3 acceptance: ≥ 5 000 line items."""
        total = ext.merged_total()
        assert total >= 5000, f"only {total} parts; acceptance is ≥ 5000"

    def test_every_part_has_source_citation(self):
        """Every imported part must have a non-empty source string."""
        for pn, comp in ext.get_external_components().items():
            assert comp.source, f"part {pn} missing source citation"

    def test_every_part_has_license_tag(self):
        tags = ext.get_external_license_tags()
        for pn in ext.get_external_components():
            assert pn in tags, f"no license tag for {pn}"
            assert tags[pn].license, f"empty license for {pn}"

    def test_lookup_api_returns_component_shape(self):
        merged = ext.merged_catalog()
        # Pick a known external part.
        sample_pn = next(iter(ext.get_external_components()))
        c = merged[sample_pn]
        assert isinstance(c, Component)
        assert hasattr(c, "part_number")
        assert hasattr(c, "category")
        assert hasattr(c, "subcategory")
        assert hasattr(c, "mass_g")

    def test_mass_query_under_50ms(self):
        """Mass aggregation across the merged catalog must be < 50 ms."""
        merged = ext.merged_catalog()
        t0 = time.monotonic()
        total_mass_g = sum(c.mass_g for c in merged.values())
        elapsed = time.monotonic() - t0
        assert elapsed < 0.050, f"mass query took {elapsed*1000:.1f} ms"
        assert total_mass_g > 0.0

    def test_thermal_query_under_50ms(self):
        merged = ext.merged_catalog()
        t0 = time.monotonic()
        max_t = max(c.max_operating_temp_k for c in merged.values()
                    if c.max_operating_temp_k > 0)
        elapsed = time.monotonic() - t0
        assert elapsed < 0.050, f"thermal query took {elapsed*1000:.1f} ms"
        assert max_t > 300.0   # something is rated above room T

    def test_categories_cover_all_tier3_groups(self):
        """All ten categories named in PRODUCTION_READINESS_RESEARCH.md
        §3 Tier-3 must be present (or labelled close enough)."""
        merged = ext.merged_catalog()
        cats = {c.category for c in merged.values()}
        # The ten Tier-3 buckets, normalised to ARIA's category labels.
        required = {
            "avionics", "power", "propulsion", "thermal",
            "eclss", "fasteners",
            "science", "robotics", "software",
            # Structures + EEE roll up into 'electronics' / 'electrical'
            # for now; left for R43 to refactor.
            "electronics",
        }
        missing = required - cats
        assert not missing, f"missing categories: {missing}"

    def test_no_in_tree_external_collision(self):
        """External adds must not mask in-tree hand-curated parts."""
        in_tree = set(components_db.COMPONENT_DATABASE)
        external = set(ext.get_external_components())
        overlap = in_tree & external
        # If there's overlap, in-tree wins via merged_catalog — verify.
        merged = ext.merged_catalog()
        for pn in overlap:
            assert merged[pn] is components_db.COMPONENT_DATABASE[pn]


# ── License enforcement contract ───────────────────────────────


class TestLicenseTagging:
    def setup_method(self) -> None:
        ext.reset_for_test()

    def teardown_method(self) -> None:
        ext.reset_for_test()

    def test_license_summary_nonempty(self):
        summary = ext.license_summary()
        assert summary, "no license tags at all"
        # CC-BY-SA viral subset must be tagged so a downstream filter can
        # exclude it from a non-CC-BY-SA distribution.
        assert any("CC-BY-SA" in k for k in summary), (
            "libreCube CC-BY-SA tag missing"
        )

    def test_source_summary_includes_iss_oomi(self):
        summary = ext.source_summary()
        assert any("OOMI" in k for k in summary), (
            "ISS OOMI source tag missing"
        )
