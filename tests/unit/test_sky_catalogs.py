"""Validation for the sky catalogs shipped in recent rounds.

Exoplanet hosts, variable stars, double stars, NGC highlights, pulsars,
nearby stars, meteor showers, belt distribution.
"""

from __future__ import annotations

import math

import pytest

from aria.simulation.exoplanets import EXOPLANET_HOSTS, bright_hosts
from aria.simulation.variable_stars import VARIABLES, current_magnitude
from aria.simulation.double_stars import DOUBLES
from aria.simulation.ngc_highlights import NGC_HIGHLIGHTS
from aria.simulation.pulsars import PULSARS
from aria.simulation.nearby_stars import NEARBY_STARS
from aria.simulation.meteor_showers import SHOWERS, active_showers
from aria.simulation.belt_distribution import (
    synthesize_main_belt, synthesize_trojans, synthesize_kuiper_belt,
    sample_position, KIRKWOOD_GAPS,
)


# ─── Exoplanet catalog ────────────────────────────────────────────────

def test_exoplanet_catalog_size_and_bright_count():
    assert len(EXOPLANET_HOSTS) >= 30
    assert len(bright_hosts(6.5)) >= 10


def test_exoplanet_coords_in_range():
    for h in EXOPLANET_HOSTS:
        assert 0 <= h.ra_deg < 360
        assert -90 <= h.dec_deg <= 90
        assert h.n_planets >= 1


def test_exoplanet_includes_firsts():
    names = {h.name for h in EXOPLANET_HOSTS}
    assert "51 Pegasi" in names           # first hot Jupiter
    assert "TRAPPIST-1" in names          # 7-planet system
    assert "Kepler-452" in names          # Earth 2.0 candidate


# ─── Variable stars ────────────────────────────────────────────────────

def test_variables_catalog_size():
    assert len(VARIABLES) >= 20


def test_algol_light_curve_dips():
    algol = next(v for v in VARIABLES if "Algol" in v.name)
    # Maximum should be well above minimum
    mags = [current_magnitude(algol, algol.t_max_jd + d * 0.1)
            for d in range(30)]
    assert max(mags) - min(mags) > 0.8


def test_cepheid_is_periodic():
    cep = next(v for v in VARIABLES if "δ Cephei" in v.name)
    m1 = current_magnitude(cep, 2459000.0)
    m2 = current_magnitude(cep, 2459000.0 + cep.period_d)     # one full period later
    assert abs(m1 - m2) < 0.05


# ─── Double stars ────────────────────────────────────────────────────

def test_doubles_catalog_size():
    assert len(DOUBLES) >= 15


def test_mizar_and_albireo_present():
    names = {d.name for d in DOUBLES}
    assert any("Mizar" in n for n in names)
    assert any("Albireo" in n for n in names)


def test_doubles_separation_positive():
    for d in DOUBLES:
        assert d.sep_arcsec > 0
        assert 0 <= d.pa_deg < 360


# ─── NGC highlights ───────────────────────────────────────────────────

def test_ngc_highlights_catalog_size():
    assert len(NGC_HIGHLIGHTS) >= 30


def test_lmc_and_omega_cen_present():
    ids = {o.catalog_id for o in NGC_HIGHLIGHTS}
    assert "LMC" in ids
    assert "NGC 5139" in ids    # Omega Centauri


# ─── Pulsars ─────────────────────────────────────────────────────────

def test_pulsars_have_crab_and_bell_burnell():
    names = {p.common_name for p in PULSARS}
    assert any("Crab" in n for n in names)
    assert any("LGM" in n for n in names)


def test_pulsar_periods_physical():
    for p in PULSARS:
        assert 0.8 < p.period_ms < 10000     # ~1ms msp to slowest magnetars


# ─── Nearby stars ────────────────────────────────────────────────────

def test_nearby_stars_within_25ly():
    for s in NEARBY_STARS:
        assert s.distance_ly < 26


def test_proxima_is_closest():
    closest = min(NEARBY_STARS, key=lambda s: s.distance_ly)
    assert "Proxima" in closest.name


def test_nearby_contains_alpha_cen_system():
    names = {s.name for s in NEARBY_STARS}
    assert "Alpha Centauri A" in names
    assert "Alpha Centauri B" in names


# ─── Meteor showers ──────────────────────────────────────────────────

def test_meteor_showers_count():
    assert len(SHOWERS) >= 10


def test_perseids_active_in_august():
    perseids_today = [s for s in active_showers(2026, 8, 13) if s.code == "PER"]
    assert len(perseids_today) == 1


# ─── Belt distribution ───────────────────────────────────────────────

def test_belt_kirkwood_gaps_present():
    mb = synthesize_main_belt(2000, seed=42)
    bins = {}
    for s in mb:
        key = round(s.a_au, 2)
        bins[key] = bins.get(key, 0) + 1
    # Find density at the 2.50 AU gap vs. 2.60 AU adjacent peak
    at_gap = sum(v for k, v in bins.items() if abs(k - 2.50) < 0.02)
    at_peak = sum(v for k, v in bins.items() if abs(k - 2.60) < 0.02)
    # Gap density should be at most half the peak
    assert at_gap * 2 < at_peak


def test_belt_sample_positions_finite():
    for gen in (synthesize_main_belt(50), synthesize_trojans(20), synthesize_kuiper_belt(20)):
        for s in gen:
            x, y, z = sample_position(s)
            assert all(math.isfinite(v) for v in (x, y, z))


def test_kirkwood_gaps_correct_locations():
    # Jupiter's 3:1 should be at a ≈ 2.50 AU, 2:1 at 3.28 AU
    for a, hw in KIRKWOOD_GAPS:
        assert 2.4 < a < 3.4
