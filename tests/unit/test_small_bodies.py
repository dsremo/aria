"""Validation for bright asteroid + comet ephemeris.

Reference values are computed at the MPCORB element epoch
(JD 2460492.5 = 2024-Jul-01.0) where propagation drift is zero.
"""

from __future__ import annotations

import math

import pytest

from aria.simulation.small_bodies import (
    ASTEROIDS, COMETS,
    geocentric_smallbody, visible_small_bodies,
)


def _by_name(catalog, needle):
    needle = needle.lower()
    for b in catalog:
        if needle in b.name.lower():
            return b
    raise KeyError(needle)


def test_catalog_population():
    assert len(ASTEROIDS) >= 20
    assert len(COMETS) >= 10


def test_ceres_brightness_at_epoch():
    # At MPCORB epoch (2024-Jul-01), Ceres was at V ~ 8.5-9 (post-opposition).
    sb = geocentric_smallbody(_by_name(ASTEROIDS, "Ceres"), 2460492.5)
    assert sb is not None
    assert 7.5 < sb.magnitude < 10.5
    assert 1.5 < sb.distance_au < 4.5


def test_vesta_brightest_asteroid():
    sb = geocentric_smallbody(_by_name(ASTEROIDS, "Vesta"), 2460492.5)
    assert sb is not None
    assert sb.magnitude < 9.0       # Vesta is the brightest main-belt asteroid


def test_apophis_close_to_earth():
    # Apophis a ≈ 0.92 AU — semi-major axis less than Earth's.
    apophis = _by_name(ASTEROIDS, "Apophis")
    assert apophis.a_au < 1.0


def test_halley_high_inclination():
    # 1P/Halley i ≈ 162°, retrograde.
    halley = _by_name(COMETS, "Halley")
    assert halley.inc_deg > 160.0
    assert halley.is_comet


def test_visible_list_sorted_by_brightness():
    bodies = visible_small_bodies(2460492.5, mag_limit=12)
    mags = [b.magnitude for b in bodies]
    assert mags == sorted(mags)
    # Should include Vesta and Ceres at this epoch.
    names = {b.name for b in bodies}
    assert any("Vesta" in n for n in names)
    assert any("Ceres" in n for n in names)


def test_hyperbolic_comets_propagate():
    # Tsuchinshan-ATLAS has e ≈ 1.0; with hyperbolic propagation it should
    # now appear in the visible list (was bright at V≈10 in mid-2024).
    bodies = visible_small_bodies(2460492.5, mag_limit=20)
    names = {b.name for b in bodies}
    assert any("Tsuchinshan" in n for n in names)
    # And Hale-Bopp (e≈0.995, near-parabolic) should also propagate.
    assert any("Hale-Bopp" in n for n in names)


def test_phase_function_finite_for_all():
    bodies = visible_small_bodies(2460492.5, mag_limit=20)
    for b in bodies:
        assert math.isfinite(b.magnitude)
        assert math.isfinite(b.ra_deg)
        assert math.isfinite(b.dec_deg)
        assert b.distance_au > 0
