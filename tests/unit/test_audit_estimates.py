"""Tests for scripts/audit_estimates.py — the ESTIMATE-tag auditor."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "audit_estimates.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("audit_estimates", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit():
    return _load_module()


class TestClassification:
    """The classify() function must put each line in the right bucket."""

    def test_placeholder_is_placeholder(self, audit):
        assert audit.classify("x = 5  # ESTIMATE — no published data, assumed") == "placeholder"
        assert audit.classify("x = 5  # ESTIMATE — placeholder") == "placeholder"

    def test_author_year_citation_is_has_citation(self, audit):
        line = "x = 0.42  # ESTIMATE — Cucinotta 2014 solar min"
        assert audit.classify(line) == "has_citation"

    def test_standard_is_has_standard(self, audit):
        line = "x = 15.0  # ESTIMATE — ISO 17771:2007 scaled"
        # "scaled" keyword wins; we check a pure-standard line below.
        line2 = "x = 15.0  # ESTIMATE — NASA-STD-3001 Vol 1 §4.2"
        assert audit.classify(line2) == "has_standard"

    def test_scaled_wins_over_citation(self, audit):
        # When both a citation AND "scaled" appear, scaled_from_citation wins.
        line = "x = 15.0  # ESTIMATE — Carrasquillo 2017 scaled conservative"
        assert audit.classify(line) == "scaled_from_citation"

    def test_bare_reason(self, audit):
        line = "x = 5  # ESTIMATE — chosen by eye on the 50m hull"
        assert audit.classify(line) == "bare_reason"

    def test_unlabeled(self, audit):
        assert audit.classify("x = 5  # ESTIMATE") == "unlabeled"

    def test_bare_reason_separators(self, audit):
        """All of em-dash, hyphen, colon, paren, and English connectors
        must be recognised as real-reason separators (bare_reason)."""
        assert audit.classify("x = 5  # ESTIMATE - chosen by eye") == "bare_reason"
        assert audit.classify("x = 5  # ESTIMATE: chosen by eye") == "bare_reason"
        assert audit.classify("x = 5  # ESTIMATE (chosen by eye)") == "bare_reason"
        assert audit.classify("x = 5  # ESTIMATE based on hull geometry") == "bare_reason"
        # "derived" is a scaling qualifier — takes precedence over standards
        assert audit.classify("x = 5  # ESTIMATE derived from ISS specs") == "scaled_from_citation"
        # Bare ESTIMATE alone still classifies as unlabeled
        assert audit.classify("x = 5  # ESTIMATE") == "unlabeled"
        assert audit.classify("x = 5  # ESTIMATE   ") == "unlabeled"


class TestScanFile:
    def test_finds_only_comment_estimates(self, tmp_path, audit):
        f = tmp_path / "sample.py"
        f.write_text(
            'x = 1  # ESTIMATE — Smith 2020\n'
            'y = 2  # not an estimate\n'
            'z = """ESTIMATE in a docstring"""\n'
            'w = 3  # ESTIMATE\n'
        )
        hits = audit.scan_file(f)
        # Docstring line is skipped; expect 2 hits.
        assert len(hits) == 2
        linenos = {h[0] for h in hits}
        assert linenos == {1, 4}

    def test_classifies_within_file(self, tmp_path, audit):
        f = tmp_path / "sample.py"
        f.write_text(
            'a = 1  # ESTIMATE — Menvielle 1991\n'
            'b = 2  # ESTIMATE — no data\n'
            'c = 3  # ESTIMATE — ISO 17771\n'
        )
        hits = audit.scan_file(f)
        categories = {lineno: cat for lineno, cat, _ in hits}
        assert categories[1] == "has_citation"
        assert categories[2] == "placeholder"
        assert categories[3] == "has_standard"


class TestCLI:
    def test_script_runs_and_reports_total(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(REPO_ROOT / "src")],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr
        assert "ESTIMATE tag audit" in result.stdout
        assert "Total tags:" in result.stdout

    def test_script_json_output_is_parseable(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(REPO_ROOT / "src"), "--json"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert "total" in data
        assert "by_category" in data
        assert "by_package" in data
        assert data["total"] > 0  # codebase currently has many ESTIMATE tags

    def test_script_category_filter(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--root", str(REPO_ROOT / "src"),
             "--category", "has_citation"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr
        # Output should list filepaths ending in .py and "has_citation" summary line
        assert "has_citation" in result.stdout
