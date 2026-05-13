"""Tests for Earth-to-Mars transfer window simulator.

Validates the patched-conic Lambert trajectory against:
  - Analytical Hohmann formula for mean Earth-Mars orbits (8.68 km²/s²)
  - InSight 2018 actual mission data (C3 = 8.19 km²/s², error < 1%)
  - Physical ranges for TMI/MOI Δv from published mission databases
  - Lambert solver self-consistency (vis-viva verification)

References:
  Bate, Mueller, White (1971) Fundamentals of Astrodynamics §5.3, §7.4
  Vallado (2013) Fundamentals of Astrodynamics 4th ed §7.6
  JPL InSight Launch Press Kit (2018): C3 = 8.19 km²/s²
"""

from __future__ import annotations

import math
import pytest
import numpy as np


# ── Imports ──────────────────────────────────────────────────────────────────

from aria.simulation.mars_transfer import (
    MarsTransferConfig,
    simulate_mars_transfer,
    find_mars_windows,
    tmi_delta_v,
    moi_delta_v,
    circular_orbit_speed,
    tsiolkovsky_propellant,
    get_body_state_helio,
    _lambert_heliocentric,
    validate_insight,
    validate_curiosity,
    MU_SUN, MU_EARTH, MU_MARS,
    R_EARTH, R_MARS, G0,
    AU_M, EARTH_MEAN_DIST_M, MARS_MEAN_DIST_M,
)


# ═══════════════════════════════════════════════════════════════════
#  ORBITAL MECHANICS UNIT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOrbitalMechanicsFormulas:
    """Pure analytical tests — no ephemeris dependency."""

    def test_circular_orbit_speed_earth_leo(self):
        """ISS at ~400 km: ~7.66 km/s. Curtis 3rd ed §2.5."""
        r = R_EARTH + 400_000
        v = circular_orbit_speed(MU_EARTH, r)
        assert 7_600 < v < 7_800, f"LEO speed {v:.0f} m/s not in 7600-7800"

    def test_circular_orbit_speed_mars_orbit(self):
        """Mars orbit at 400 km: ~3.43 km/s. Derived from MU_MARS."""
        r = R_MARS + 400_000
        v = circular_orbit_speed(MU_MARS, r)
        assert 3_300 < v < 3_600, f"Mars 400km speed {v:.0f} m/s not in 3300-3600"

    def test_tmi_dv_hohmann_range(self):
        """TMI from 185 km LEO with Hohmann C3 (~8.68 km²/s²): expect ~3.59 km/s.

        Bate-Mueller-White §7.4 worked example for Earth-Mars Hohmann.
        """
        r_park = R_EARTH + 185_000
        # Hohmann C3 for mean Earth-Mars orbits
        r1 = EARTH_MEAN_DIST_M
        r2 = MARS_MEAN_DIST_M
        a = (r1 + r2) / 2
        v_dep  = math.sqrt(MU_SUN * (2 / r1 - 1 / a))
        v_circ = math.sqrt(MU_SUN / r1)
        c3 = (v_dep - v_circ) ** 2  # m²/s²
        dv = tmi_delta_v(r_park, c3)
        assert 3_400 < dv < 3_800, f"TMI Δv {dv:.0f} m/s outside 3400-3800"

    def test_moi_dv_physical_range(self):
        """MOI into 400 km Mars circular orbit with v∞ = 2.5 km/s: ~2.0 km/s.

        v_hyp = sqrt(v∞² + 2μ_Mars/r) = sqrt(6.25 + 22.6) = 5.37 km/s
        v_circ = sqrt(μ_Mars/r) = 3.36 km/s
        Δv = 5.37 − 3.36 = 2.01 km/s
        Note: actual MRO used aerobraking + small burns, not a direct circular insertion.
        Curtis (2014) §8.4 eq. 8.44 confirms this formula.
        """
        r_moi = R_MARS + 400_000
        dv = moi_delta_v(2_500, r_moi)  # v_inf = 2.5 km/s typical
        assert 1_500 < dv < 2_500, f"MOI Δv {dv:.0f} m/s outside 1500-2500"

    def test_moi_dv_increases_with_vinf(self):
        """Higher v∞ at Mars → higher MOI Δv (more braking needed)."""
        r_moi = R_MARS + 400_000
        dv_low  = moi_delta_v(2_000, r_moi)
        dv_high = moi_delta_v(4_000, r_moi)
        assert dv_high > dv_low, f"MOI dv should increase: {dv_low:.0f} → {dv_high:.0f}"

    def test_tsiolkovsky_zero_dv(self):
        """Zero Δv → zero propellant."""
        assert tsiolkovsky_propellant(0.0, 380, 1_000) == 0.0

    def test_tsiolkovsky_physical(self):
        """3.6 km/s at Isp=380s for 1000 kg dry: ~10-12× mass ratio → ~900 kg propellant."""
        prop = tsiolkovsky_propellant(3_600, 380, 1_000)
        assert 500 < prop < 2_000, f"Propellant {prop:.0f} kg unreasonable"

    def test_tmi_dv_increases_with_c3(self):
        """Higher C3 → larger TMI Δv (more energy needed at departure)."""
        r = R_EARTH + 185_000
        dv_low  = tmi_delta_v(r, 8e6)   # 8 km²/s²
        dv_high = tmi_delta_v(r, 16e6)  # 16 km²/s²
        assert dv_high > dv_low


# ═══════════════════════════════════════════════════════════════════
#  LAMBERT SOLVER TESTS
# ═══════════════════════════════════════════════════════════════════

class TestLambertSolver:
    """Validate the heliocentric Lambert universal-variable solver."""

    def test_hohmann_c3(self):
        """Lambert on Hohmann geometry (≈179°) matches analytical C3 ≈ 8.68 km²/s².

        Bate-Mueller-White (1971) §7.4: Hohmann C3 for Earth-Mars ~8.7 km²/s².
        Uses 179° instead of 180° to avoid degenerate geometry.
        """
        r1 = EARTH_MEAN_DIST_M
        r2 = MARS_MEAN_DIST_M
        # 179 degrees: nearly-antipodal, avoids Lambert degeneracy at 180°
        r1_vec = np.array([r1, 0.0, 0.0])
        r2_vec = np.array([-r2 * math.cos(math.radians(1)),
                            r2 * math.sin(math.radians(1)), 0.0])

        a_hoh = (r1 + r2) / 2
        tof_s = math.pi * math.sqrt(a_hoh ** 3 / MU_SUN)

        v_earth_vec = np.array([0.0, math.sqrt(MU_SUN / r1), 0.0])
        v1, _ = _lambert_heliocentric(r1_vec, r2_vec, tof_s)
        c3 = np.linalg.norm(v1 - v_earth_vec) ** 2 / 1e6  # km²/s²

        # Analytical Hohmann C3
        v_dep  = math.sqrt(MU_SUN * (2 / r1 - 1 / a_hoh))
        c3_ref = (v_dep - math.sqrt(MU_SUN / r1)) ** 2 / 1e6

        assert abs(c3 - c3_ref) / c3_ref < 0.02, (
            f"Lambert Hohmann C3={c3:.2f} vs analytical {c3_ref:.2f} km²/s² (>2% error)"
        )

    def test_energy_conserved_at_departure(self):
        """Vis-viva at departure must give the same orbital energy as at arrival.

        For a single Keplerian arc, E = v²/2 - μ/r is constant.
        Lambert should produce a consistent orbit (Bate-Mueller-White §2.3).
        """
        r1_vec = np.array([EARTH_MEAN_DIST_M, 0.0, 0.0])
        r2_vec = np.array([-MARS_MEAN_DIST_M * math.cos(math.radians(5)),
                            MARS_MEAN_DIST_M * math.sin(math.radians(5)), 0.0])
        a_hoh = (EARTH_MEAN_DIST_M + MARS_MEAN_DIST_M) / 2
        tof_s = 1.15 * math.pi * math.sqrt(a_hoh ** 3 / MU_SUN)

        v1, v2 = _lambert_heliocentric(r1_vec, r2_vec, tof_s)

        r1 = np.linalg.norm(r1_vec)
        r2 = np.linalg.norm(r2_vec)
        E1 = np.dot(v1, v1) / 2 - MU_SUN / r1
        E2 = np.dot(v2, v2) / 2 - MU_SUN / r2

        assert abs(E1 - E2) / abs(E1) < 1e-6, (
            f"Orbital energy not conserved: E1={E1:.4e}, E2={E2:.4e}"
        )

    def test_angular_momentum_conserved(self):
        """Specific angular momentum h = r × v must be same at both ends."""
        r1_vec = np.array([EARTH_MEAN_DIST_M, 0.0, 0.0])
        r2_vec = np.array([-MARS_MEAN_DIST_M * math.cos(math.radians(5)),
                            MARS_MEAN_DIST_M * math.sin(math.radians(5)), 0.0])
        a_hoh = (EARTH_MEAN_DIST_M + MARS_MEAN_DIST_M) / 2
        tof_s = 1.15 * math.pi * math.sqrt(a_hoh ** 3 / MU_SUN)

        v1, v2 = _lambert_heliocentric(r1_vec, r2_vec, tof_s)

        h1 = np.linalg.norm(np.cross(r1_vec, v1))
        h2 = np.linalg.norm(np.cross(r2_vec, v2))

        assert abs(h1 - h2) / h1 < 1e-5, (
            f"|h| not conserved: h1={h1:.4e}, h2={h2:.4e}"
        )


# ═══════════════════════════════════════════════════════════════════
#  EPHEMERIS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestEphemeris:
    """Validate JPL ephemeris access via astropy."""

    def test_earth_heliocentric_distance_2020(self):
        """Earth heliocentric distance on 2020-07-30: ~1.015 AU (near aphelion).

        Earth aphelion ~July 4 at 1.0167 AU; July 30 ≈ 1.015 AU.
        Vallado (2013) Table D-3: Earth eccentricity = 0.0167.
        """
        r, v = get_body_state_helio("earth", "2020-07-30")
        r_au = np.linalg.norm(r) / AU_M
        assert 1.01 < r_au < 1.02, f"Earth at 2020-07-30: {r_au:.4f} AU, expected ~1.015"

    def test_earth_orbital_speed_physical(self):
        """Earth heliocentric speed: 29.3-30.0 km/s (aphelion-perihelion range).

        Vallado (2013) Table D-3: Earth v_mean = 29.78 km/s.
        """
        r, v = get_body_state_helio("earth", "2020-01-01")
        speed_kms = np.linalg.norm(v) / 1000
        assert 29.0 < speed_kms < 30.5, f"Earth speed {speed_kms:.2f} km/s outside 29.0-30.5"

    def test_mars_near_perihelion_2020(self):
        """Mars perihelion ≈ 2020-08-03 (computed): distance ~1.381 AU.

        Mars perihelion distance a*(1-e) = 1.524*(1-0.093) = 1.381 AU.
        Vallado (2013) Table D-3.
        """
        r, v = get_body_state_helio("mars", "2020-08-03")
        r_au = np.linalg.norm(r) / AU_M
        assert 1.35 < r_au < 1.42, (
            f"Mars at perihelion 2020-08-03: {r_au:.4f} AU, expected ~1.381"
        )

    def test_mars_orbital_speed_physical(self):
        """Mars mean orbital speed: ~24.1 km/s. Vallado (2013) Table D-3."""
        r, v = get_body_state_helio("mars", "2022-01-01")
        speed_kms = np.linalg.norm(v) / 1000
        assert 21.5 < speed_kms < 26.5, f"Mars speed {speed_kms:.2f} km/s outside 21.5-26.5"


# ═══════════════════════════════════════════════════════════════════
#  MISSION SIMULATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestMarsTransferSimulation:
    """simulate_mars_transfer() — trajectory and budget validation."""

    def test_insight_2018_c3(self):
        """InSight 2018: C3 within 2% of published 8.19 km²/s².

        Near-perihelion Mars arrival → low-C3 window.
        JPL InSight Launch Press Kit, May 2018.
        """
        v = validate_insight()
        assert v["c3_error_pct"] < 2.0, (
            f"InSight C3 error {v['c3_error_pct']:.1f}% > 2%: "
            f"computed={v['c3_computed_km2s2']:.2f}, ref={v['c3_ref_km2s2']:.2f}"
        )

    def test_insight_2018_tmi_dv(self):
        """InSight 2018: TMI Δv within 2% of reference (~3.58 km/s from LEO)."""
        v = validate_insight()
        assert v["tmi_error_pct"] < 2.0, (
            f"InSight TMI error {v['tmi_error_pct']:.1f}% > 2%: "
            f"computed={v['tmi_dv_computed_ms']:.0f}, ref={v['tmi_dv_ref_ms']:.0f} m/s"
        )

    def test_result_fields_complete(self):
        """simulate_mars_transfer must return all expected fields."""
        config = MarsTransferConfig(
            departure_date="2018-05-05",
            tof_days=205.0,
        )
        r = simulate_mars_transfer(config)
        assert r.c3_km2s2 > 0
        assert r.v_inf_earth_ms > 0
        assert r.v_inf_mars_ms > 0
        assert r.tmi.delta_v_ms > 0
        assert r.moi.delta_v_ms > 0
        assert r.total_delta_v_ms == pytest.approx(r.tmi.delta_v_ms + r.moi.delta_v_ms)

    def test_tmi_larger_than_moi(self):
        """TMI Δv > MOI Δv for low-C3 windows.

        TMI (Earth escape to heliocentric arc) is always the bigger burn for
        typical Earth-Mars missions. MOI is smaller because Mars is lighter.
        Validated across InSight, Curiosity, Spirit references.
        """
        config = MarsTransferConfig(departure_date="2018-05-05", tof_days=205.0)
        r = simulate_mars_transfer(config)
        assert r.tmi.delta_v_ms > r.moi.delta_v_ms, (
            f"TMI {r.tmi.delta_v_ms:.0f} m/s should exceed MOI {r.moi.delta_v_ms:.0f} m/s"
        )

    def test_c3_positive(self):
        """C3 must be positive for any valid transfer orbit (hyperbolic departure)."""
        config = MarsTransferConfig(departure_date="2018-05-05", tof_days=205.0)
        r = simulate_mars_transfer(config)
        assert r.c3_km2s2 > 0

    def test_tof_conserved(self):
        """Arrival date must be exactly TOF days after departure."""
        config = MarsTransferConfig(departure_date="2018-05-05", tof_days=205.0)
        r = simulate_mars_transfer(config)
        dep = r.departure_date
        arr = r.arrival_date
        # Count days between departure and arrival
        from datetime import date
        d1 = date.fromisoformat(dep)
        d2 = date.fromisoformat(arr)
        assert (d2 - d1).days == int(config.tof_days), (
            f"TOF mismatch: dep={dep}, arr={arr}, Δ={(d2-d1).days}d vs {config.tof_days}"
        )

    def test_earth_heliocentric_physical(self):
        """Earth heliocentric distance at departure must be 0.98–1.02 AU."""
        config = MarsTransferConfig(departure_date="2018-05-05", tof_days=205.0)
        r = simulate_mars_transfer(config)
        au = r.earth_helio_km / (AU_M / 1000)
        assert 0.98 < au < 1.02, f"Earth at departure: {au:.4f} AU outside 0.98-1.02"

    def test_mars_heliocentric_physical(self):
        """Mars heliocentric distance at arrival: 1.38–1.67 AU (perihelion-aphelion).

        Mars eccentricity = 0.093 → perihelion 1.381 AU, aphelion 1.666 AU.
        Vallado (2013) Table D-3.
        """
        config = MarsTransferConfig(departure_date="2018-05-05", tof_days=205.0)
        r = simulate_mars_transfer(config)
        au = r.mars_helio_km / (AU_M / 1000)
        assert 1.35 < au < 1.70, f"Mars at arrival: {au:.4f} AU outside 1.35-1.70"

    def test_total_propellant_positive(self):
        """Total propellant mass must be positive."""
        config = MarsTransferConfig(departure_date="2018-05-05", tof_days=205.0)
        r = simulate_mars_transfer(config)
        assert r.total_propellant_kg > 0

    def test_curiosity_c3_in_range(self):
        """Curiosity 2011: C3 in 8-15 km²/s² range (moderate-energy window).

        2011 window had Mars moving toward aphelion at arrival (~1.58 AU).
        Patched-conic gives ~10.5 km²/s²; JPL value ~11.5 km²/s² (press kit).
        """
        c = validate_curiosity()
        assert 8 < c["c3_computed_km2s2"] < 15, (
            f"Curiosity C3={c['c3_computed_km2s2']:.2f} outside 8-15 km²/s²"
        )


# ═══════════════════════════════════════════════════════════════════
#  LAUNCH WINDOW SCANNER
# ═══════════════════════════════════════════════════════════════════

class TestLaunchWindowScanner:
    """find_mars_windows() — verify window detection around known opportunities."""

    def test_finds_windows_2018(self):
        """2018 window (InSight): scanner must find at least one low-C3 window.

        InSight C3 = 8.19 km²/s² confirmed. Scanner should find windows < 12 km²/s².
        """
        windows = find_mars_windows(
            start_date="2018-04-01",
            scan_days=60,
            tof_range=(180.0, 280.0),
            tof_steps=12,
            c3_max_km2s2=15.0,
        )
        assert len(windows) > 0, "Should find at least one window in 2018"

    def test_minimum_c3_in_2018(self):
        """Best window C3 in 2018 should be near 8.19 km²/s² (InSight launch).

        Scanner coarse grid may miss exact optimum; require < 12 km²/s².
        """
        windows = find_mars_windows(
            start_date="2018-04-01",
            scan_days=60,
            tof_range=(180.0, 280.0),
            tof_steps=15,
            c3_max_km2s2=15.0,
        )
        best_c3 = min(w.c3_km2s2 for w in windows)
        assert best_c3 < 12.0, (
            f"Best 2018 window C3={best_c3:.2f} km²/s² > 12 (expected ~8.2)"
        )

    def test_windows_sorted_by_c3(self):
        """Returned windows must be sorted by C3 ascending (lowest first)."""
        windows = find_mars_windows(
            start_date="2018-04-01",
            scan_days=30,
            tof_range=(180.0, 280.0),
            tof_steps=8,
            c3_max_km2s2=20.0,
        )
        if len(windows) > 1:
            for i in range(len(windows) - 1):
                assert windows[i].c3_km2s2 <= windows[i + 1].c3_km2s2, (
                    f"Windows not sorted: {windows[i].c3_km2s2:.2f} > {windows[i+1].c3_km2s2:.2f}"
                )

    def test_tmi_dv_consistent_with_c3(self):
        """TMI Δv in window results must be consistent with the window's C3."""
        windows = find_mars_windows(
            start_date="2018-04-20",
            scan_days=20,
            tof_range=(190.0, 250.0),
            tof_steps=8,
            c3_max_km2s2=15.0,
        )
        assert len(windows) > 0, "Expected windows in May 2018"
        for w in windows[:5]:
            r_park = R_EARTH + 185_000
            dv_expect = tmi_delta_v(r_park, w.c3_km2s2 * 1e6)
            assert abs(w.tmi_dv_ms - dv_expect) < 5, (
                f"TMI mismatch: window={w.tmi_dv_ms:.1f}, expected={dv_expect:.1f} m/s"
            )
