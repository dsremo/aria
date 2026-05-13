"""Validation for the 88 IAU constellation catalog."""

from __future__ import annotations

import pytest

from aria.simulation.constellations import (
    CONSTELLATIONS, CONSTELLATION_LINES_88, get_centroid,
)
from aria.simulation.star_field import load_hyg


def test_88_constellations_exist():
    assert len(CONSTELLATIONS) == 88
    abbrs = {c.abbr for c in CONSTELLATIONS}
    assert len(abbrs) == 88   # unique abbreviations


def test_centroid_coordinates_valid():
    for c in CONSTELLATIONS:
        assert 0 <= c.ra_deg < 360, f"{c.abbr} bad RA"
        assert -90 <= c.dec_deg <= 90, f"{c.abbr} bad Dec"
        assert len(c.abbr) == 3


def test_known_centroid_lookups():
    # Spot-checks against published IAU centroids
    assert get_centroid("Ori") is not None
    ra, dec = get_centroid("Ori")
    assert 80 < ra < 90, f"Orion RA off: {ra}"
    assert 0 < dec < 12, f"Orion Dec off: {dec}"
    assert get_centroid("Cru") is not None
    ra, dec = get_centroid("Cru")
    assert -65 < dec < -55       # Crux is southern
    assert get_centroid("ZZZ") is None


def test_stick_figure_coverage():
    """At least 30 constellations have stick figures (lines)."""
    assert len(CONSTELLATION_LINES_88) >= 30


def test_hip_endpoints_mostly_in_catalog():
    """≥95% of HIP endpoints in stick figures must resolve in HYG."""
    cat_hips = {s.hip_id for s in load_hyg() if s.hip_id > 0}
    all_endpoints = set()
    for lines in CONSTELLATION_LINES_88.values():
        for a, b in lines:
            all_endpoints.add(a); all_endpoints.add(b)
    resolved = all_endpoints & cat_hips
    coverage = len(resolved) / len(all_endpoints)
    assert coverage >= 0.95, f"Only {coverage:.1%} HIP coverage"


def test_no_self_loops_in_lines():
    for k, lines in CONSTELLATION_LINES_88.items():
        for a, b in lines:
            assert a != b, f"{k} has self-loop on HIP {a}"
