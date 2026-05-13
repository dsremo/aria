"""Validation for Messier deep-sky catalog."""

from __future__ import annotations

import pytest

from aria.simulation.messier import MESSIER, messier_by_class, visible_messier


def test_catalog_has_all_110():
    nums = [m.m for m in MESSIER]
    assert len(MESSIER) == 110
    assert min(nums) == 1
    assert max(nums) == 110
    # No duplicates
    assert len(set(nums)) == 110


def test_class_distribution_sane():
    # Classic breakdown: ~40 galaxies, ~29 globular clusters, ~27 open clusters
    by = {c: len(messier_by_class(c)) for c in ("G", "GC", "OC", "N", "PN", "SR", "AS", "D")}
    assert by["G"] >= 35
    assert by["GC"] >= 25
    assert by["OC"] >= 25
    assert by["N"] >= 5
    assert by["PN"] >= 3
    assert by["SR"] == 1     # M1 Crab Nebula
    assert sum(by.values()) == 110


def test_famous_objects_populated():
    by_m = {m.m: m for m in MESSIER}
    assert "Crab" in by_m[1].name
    assert "Andromeda" in by_m[31].name
    assert by_m[31].obj_class == "G"
    assert "Pleiades" in by_m[45].name
    assert by_m[45].obj_class == "OC"
    assert "Orion" in by_m[42].name
    assert "Sombrero" in by_m[104].name


def test_coordinates_in_range():
    for m in MESSIER:
        assert 0 <= m.ra_deg < 360, f"M{m.m} RA out of range: {m.ra_deg}"
        assert -90 <= m.dec_deg <= 90, f"M{m.m} Dec out of range: {m.dec_deg}"
        assert m.vmag < 12, f"M{m.m} mag implausibly faint: {m.vmag}"
        assert m.size_amaj >= m.size_amin > 0


def test_visible_messier_filter():
    bright = visible_messier(5.0)
    # Pleiades, Andromeda, Beehive, Orion all V<5
    names = {m.name for m in bright}
    assert "Pleiades" in names
    assert "Andromeda Galaxy" in names
    assert "Beehive Cluster" in names
    assert "Orion Nebula" in names
    # Sorted brightest → faintest
    mags = [m.vmag for m in bright]
    assert mags == sorted(mags)
