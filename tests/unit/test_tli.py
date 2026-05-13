"""Tests for tli.py — Trans-Lunar Injection optimizer.

Coverage:
  - Hohmann TLI: ΔV, C3, transit time, orbit parameters
  - Fast TLI: Apollo 73hr, faster-than-Hohmann ΔV increase
  - Mission propellant: Tsiolkovsky, mass conservation
  - Apollo/Artemis validation against published data
  - Trade studies: ΔV vs altitude, ΔV vs transit time

References:
  NASA SP-350 (1975) — Apollo 11 TLI
  NASA/TP-2019-220386 — SLS TLI for Artemis
  Bate et al. (1971) §6 — Hohmann transfer
"""

import math
import pytest

from aria.simulation.tli import (
    MU_EARTH, R_EARTH_M, G0_M_S2, MOON_ORBIT_M,
    APOLLO_TLI_DV_MS, SLS_TLI_DV_MS,
    APOLLO_TLI_MASS_KG, APOLLO_SIVB_ISP_S,
    TLIBurn, TLIMission,
    compute_tli, compute_tli_fast, compute_tli_mission,
    apollo_tli, artemis_tli,
    tli_dv_vs_altitude, tli_dv_vs_transit_time,
)


# ═══════════════════════════════════════════════════════════════════
#  1. HOHMANN TLI
# ═══════════════════════════════════════════════════════════════════

class TestComputeTLI:
    """Minimum-energy (Hohmann) TLI from LEO to Moon distance."""

    def test_dv_in_expected_range(self):
        """Hohmann TLI ΔV from 185 km should be 3,100–3,200 m/s."""
        b = compute_tli(185.0)
        assert 3_100 < b.dv_tli_ms < 3_200, (
            f"Hohmann TLI ΔV {b.dv_tli_ms:.0f} m/s outside 3100-3200 range"
        )

    def test_c3_negative_for_hohmann(self):
        """Hohmann transfer to Moon has C3 < 0 (bound ellipse, not hyperbolic)."""
        b = compute_tli(185.0)
        assert b.c3_km2_s2 < 0, f"Hohmann C3 {b.c3_km2_s2:.2f} should be negative"

    def test_transit_time_about_5_days(self):
        """Hohmann transit to Moon's distance should be ~5 days (120 hr)."""
        b = compute_tli(185.0)
        assert 110 < b.transit_time_hr < 130, (
            f"Transit {b.transit_time_hr:.0f} hr outside 110-130 range"
        )

    def test_transfer_ecc_near_0_97(self):
        """Transfer orbit eccentricity should be ~0.97 (very elongated)."""
        b = compute_tli(185.0)
        assert 0.95 < b.transfer_ecc < 0.99

    def test_v_transfer_exceeds_circular(self):
        """Transfer perigee speed must exceed circular orbit speed."""
        b = compute_tli(185.0)
        assert b.v_transfer_ms > b.v_circular_ms

    def test_target_distance_is_moon(self):
        """Default target should be Moon's orbital radius."""
        b = compute_tli(185.0)
        assert b.target_distance_m == MOON_ORBIT_M

    def test_higher_orbit_lower_dv(self):
        """Higher parking orbit → lower TLI ΔV (already closer to escape)."""
        b_lo = compute_tli(185.0)
        b_hi = compute_tli(500.0)
        assert b_hi.dv_tli_ms < b_lo.dv_tli_ms

    def test_returns_tli_burn(self):
        b = compute_tli(185.0)
        assert isinstance(b, TLIBurn)


# ═══════════════════════════════════════════════════════════════════
#  2. FAST TLI (Apollo-class transit time)
# ═══════════════════════════════════════════════════════════════════

class TestComputeTLIFast:
    """Fast TLI with specified transit time."""

    def test_faster_requires_more_dv(self):
        """Shorter transit time → more ΔV required."""
        b_slow = compute_tli_fast(185.0, transit_time_hr=120.0)
        b_fast = compute_tli_fast(185.0, transit_time_hr=60.0)
        assert b_fast.dv_tli_ms > b_slow.dv_tli_ms

    def test_apollo_class_dv(self):
        """Apollo 73-hour transit should give ΔV ≈ 3,100–3,300 m/s."""
        b = compute_tli_fast(185.0, transit_time_hr=73.0)
        assert 3_100 < b.dv_tli_ms < 3_300, (
            f"Apollo-class TLI ΔV {b.dv_tli_ms:.0f} m/s outside 3100-3300 range"
        )

    def test_at_hohmann_time_matches_hohmann(self):
        """Transit time ≥ Hohmann time should return Hohmann ΔV."""
        h = compute_tli(185.0)
        f = compute_tli_fast(185.0, transit_time_hr=h.transit_time_hr + 10.0)
        assert f.dv_tli_ms == pytest.approx(h.dv_tli_ms, rel=0.01)

    def test_c3_increases_with_speed(self):
        """Faster transit → higher C3 (more energy)."""
        b_slow = compute_tli_fast(185.0, transit_time_hr=120.0)
        b_fast = compute_tli_fast(185.0, transit_time_hr=48.0)
        assert b_fast.c3_km2_s2 > b_slow.c3_km2_s2

    def test_very_fast_gives_positive_c3(self):
        """48-hour transit should have C3 > 0 (hyperbolic excess)."""
        b = compute_tli_fast(185.0, transit_time_hr=48.0)
        assert b.c3_km2_s2 > 0


# ═══════════════════════════════════════════════════════════════════
#  3. MISSION PROPELLANT
# ═══════════════════════════════════════════════════════════════════

class TestComputeTLIMission:
    """TLI mission with propellant budget."""

    @pytest.fixture
    def hohmann_mission(self):
        burn = compute_tli(185.0)
        return compute_tli_mission(burn, 100_000.0, 420.0)

    def test_propellant_positive(self, hohmann_mission):
        assert hohmann_mission.propellant_kg > 0

    def test_mass_conservation(self, hohmann_mission):
        m = hohmann_mission
        assert m.spacecraft_mass_kg == pytest.approx(
            m.propellant_kg + m.mass_after_tli_kg, rel=1e-9
        )

    def test_mass_fraction_reasonable(self, hohmann_mission):
        """TLI mass fraction should be 40–60% for chemical propulsion."""
        assert 0.3 < hohmann_mission.mass_fraction < 0.7

    def test_arrival_speed_positive(self, hohmann_mission):
        assert hohmann_mission.arrival_speed_ms > 0

    def test_v_inf_moon_positive(self, hohmann_mission):
        assert hohmann_mission.v_inf_moon_ms > 0

    def test_returns_tli_mission(self, hohmann_mission):
        assert isinstance(hohmann_mission, TLIMission)


# ═══════════════════════════════════════════════════════════════════
#  4. APOLLO VALIDATION
# ═══════════════════════════════════════════════════════════════════

class TestApolloTLI:
    """Apollo 11 TLI validation (NASA SP-350)."""

    @pytest.fixture
    def apollo(self):
        return apollo_tli()

    def test_dv_within_5pct_of_published(self, apollo):
        """Apollo TLI ΔV should be within 5% of published 3,120 m/s."""
        error_pct = abs(apollo.burn.dv_tli_ms - APOLLO_TLI_DV_MS) / APOLLO_TLI_DV_MS * 100
        assert error_pct < 5.0, (
            f"Apollo TLI ΔV {apollo.burn.dv_tli_ms:.0f} m/s is {error_pct:.1f}% "
            f"from published {APOLLO_TLI_DV_MS:.0f} m/s"
        )

    def test_propellant_reasonable(self, apollo):
        """Apollo S-IVB TLI propellant: ~70,000–80,000 kg."""
        assert 60_000 < apollo.propellant_kg < 90_000

    def test_mass_after_tli_positive(self, apollo):
        assert apollo.mass_after_tli_kg > 0


# ═══════════════════════════════════════════════════════════════════
#  5. ARTEMIS VALIDATION
# ═══════════════════════════════════════════════════════════════════

class TestArtemisTLI:
    """Artemis 2 TLI validation."""

    @pytest.fixture
    def artemis(self):
        return artemis_tli()

    def test_dv_within_5pct_of_published(self, artemis):
        """Artemis TLI ΔV should be within 5% of published 3,140 m/s."""
        error_pct = abs(artemis.burn.dv_tli_ms - SLS_TLI_DV_MS) / SLS_TLI_DV_MS * 100
        assert error_pct < 5.0

    def test_propellant_positive(self, artemis):
        assert artemis.propellant_kg > 0

    def test_mass_conservation(self, artemis):
        m = artemis
        assert m.spacecraft_mass_kg == pytest.approx(
            m.propellant_kg + m.mass_after_tli_kg, rel=1e-9
        )


# ═══════════════════════════════════════════════════════════════════
#  6. TRADE STUDIES
# ═══════════════════════════════════════════════════════════════════

class TestTradeStudies:
    """Trade study utility functions."""

    def test_dv_vs_altitude_returns_list(self):
        results = tli_dv_vs_altitude()
        assert isinstance(results, list)
        assert len(results) > 0

    def test_dv_vs_altitude_monotone_decreasing(self):
        """ΔV should decrease with altitude (closer to escape)."""
        results = tli_dv_vs_altitude()
        dvs = [r["dv_tli_ms"] for r in results]
        for i in range(1, len(dvs)):
            assert dvs[i] <= dvs[i-1], (
                f"ΔV not monotone: {dvs[i]:.0f} > {dvs[i-1]:.0f} m/s"
            )

    def test_dv_vs_transit_time_returns_list(self):
        results = tli_dv_vs_transit_time()
        assert isinstance(results, list)
        assert len(results) > 0

    def test_dv_vs_transit_time_monotone_decreasing(self):
        """Longer transit → less ΔV (approaches Hohmann minimum)."""
        results = tli_dv_vs_transit_time()
        dvs = [r["dv_tli_ms"] for r in results]
        for i in range(1, len(dvs)):
            assert dvs[i] <= dvs[i-1]
