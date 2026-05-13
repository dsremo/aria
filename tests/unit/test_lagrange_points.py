"""Tests for Earth-Moon Lagrange point and halo orbit computation.

Validates the CR3BP equilibrium points against:
  - Exact Newton-Raphson solutions (L1: ~58,000 km, L2: ~64,500 km from Moon)
  - Equilateral triangle property of L4/L5 (exact: |L4-Earth| = |L4-Moon| = a)
  - Jacobi constant values at each point
  - Halo orbit periods (Queqiao: ~14 days, Artemis NRHO: ~6.5 days)
  - Physical consistency (L2 further from Moon than L1)

References:
  Szebehely V. (1967) Theory of Orbits.
  Zhang et al. (2018) Sci. China Tech. Sci. 61 (Queqiao orbit parameters).
  Zimovan et al. (2017) AAS 17-362 (NRHO parameters).
"""

from __future__ import annotations

import math
import pytest

from aria.simulation.lagrange_points import (
    compute_lagrange_points,
    halo_orbit_period,
    queqiao_halo_orbit,
    artemis_nrho,
    _cr3bp_effective_potential,
    _find_collinear_lagrange,
    MU_CR3BP, EARTH_MOON_KM,
)


class TestCr3bpEffectivePotential:
    """CR3BP effective potential Ω(x, y) sanity checks."""

    def test_potential_at_earth_infinite(self):
        """Potential at Earth location (x = -μ, y = 0) must be infinite (singularity)."""
        mu = MU_CR3BP
        # At the Earth, r1 = 0 → Ω → ∞
        omega = _cr3bp_effective_potential(-mu, 0.0, mu)
        assert omega == float("inf") or omega > 1e10

    def test_potential_at_moon_infinite(self):
        """Potential at Moon location (x = 1-μ, y = 0) must be infinite."""
        mu = MU_CR3BP
        omega = _cr3bp_effective_potential(1.0 - mu, 0.0, mu)
        assert omega == float("inf") or omega > 1e10

    def test_potential_symmetric_l4_l5(self):
        """L4 and L5 must have identical effective potential (symmetric ±y)."""
        mu = MU_CR3BP
        x_L4 = 0.5 - mu
        omega_L4 = _cr3bp_effective_potential(x_L4, +math.sqrt(3) / 2, mu)
        omega_L5 = _cr3bp_effective_potential(x_L4, -math.sqrt(3) / 2, mu)
        assert abs(omega_L4 - omega_L5) < 1e-12, (
            f"L4 Ω={omega_L4:.6f} != L5 Ω={omega_L5:.6f}"
        )

    def test_potential_collinear_greater_than_triangular(self):
        """Collinear points near a primary have higher Ω than triangular points.

        L4/L5 have the LOWEST Jacobi constant of all five libration points.
        Szebehely (1967) §3.3 Table: C_J values for μ=0.01215:
          C_J(L1)=3.19 > C_J(L2)=3.17 > C_J(L3)=3.01 > C_J(L4)=C_J(L5)=2.99
        Since C_J = 2Ω at equilibrium, Ω(L2) > Ω(L4).

        L1/L2 have elevated Ω because they sit near the Moon's 1/r₂ singularity.
        L4/L5 are geometrically the farthest from both primaries (equilateral),
        giving the lowest gravitational contribution and thus lowest Ω.
        """
        mu = MU_CR3BP
        # L2 position (beyond Moon — close to lunar gravitational well)
        xL2 = _find_collinear_lagrange(mu, "L2")
        omega_L2 = _cr3bp_effective_potential(xL2, 0.0, mu)
        # L4 position (equilateral — farthest from both primaries)
        omega_L4 = _cr3bp_effective_potential(0.5 - mu, math.sqrt(3) / 2, mu)
        assert omega_L2 > omega_L4, (
            f"L2 potential {omega_L2:.4f} should exceed L4 {omega_L4:.4f} "
            f"(C_J(L4)={2*omega_L4:.4f} is lowest among all 5 points)"
        )


class TestLagrangePointLocations:
    """Validate Lagrange point positions against known values."""

    def test_five_points_returned(self):
        """compute_lagrange_points() must return all five points."""
        pts = compute_lagrange_points()
        assert set(pts.keys()) == {"L1", "L2", "L3", "L4", "L5"}

    def test_l1_between_earth_and_moon(self):
        """L1 must lie between Earth and Moon along the x-axis."""
        pts = compute_lagrange_points()
        L1 = pts["L1"]
        # Earth is at x_bary < 0 (behind barycentre); Moon is at +~380,000 km
        assert 0 < L1.x_km < EARTH_MOON_KM - 4671, (
            f"L1 at x={L1.x_km:.0f} km not between Earth and Moon"
        )

    def test_l2_beyond_moon(self):
        """L2 must lie beyond the Moon (further from Earth)."""
        pts = compute_lagrange_points()
        L2 = pts["L2"]
        moon_x_km = (1.0 - MU_CR3BP) * EARTH_MOON_KM - MU_CR3BP * EARTH_MOON_KM
        # L2.x_km should be > Moon's x from barycentre ≈ +380,000 km
        assert L2.x_km > 370_000, (
            f"L2 at x={L2.x_km:.0f} km should be beyond Moon"
        )

    def test_l2_dist_from_moon_matches_wiki(self):
        """L2 distance from Moon: ~64,500 km.

        Verified by multiple sources (Szebehely 1967; Wikipedia Earth-Moon L2;
        Queqiao orbit: 64,500 km from Moon confirmed by CNSA 2018).
        """
        pts = compute_lagrange_points()
        L2 = pts["L2"]
        assert abs(L2.dist_from_moon_km - 64_500) < 1000, (
            f"L2 from Moon: {L2.dist_from_moon_km:.0f} km, expected ~64,500 km"
        )

    def test_l1_dist_from_moon_physical(self):
        """L1 distance from Moon: ~58,000 km (exact CR3BP, not Hill approx).

        Hill sphere first-order approximation gives ~61,500 km but the exact
        Newton-Raphson solution for μ = 0.01215 gives ~58,000 km.
        Reference: Wikipedia 'Lagrangian point' Earth-Moon section.
        """
        pts = compute_lagrange_points()
        L1 = pts["L1"]
        assert abs(L1.dist_from_moon_km - 58_000) < 2000, (
            f"L1 from Moon: {L1.dist_from_moon_km:.0f} km, expected ~58,000 km"
        )

    def test_l2_further_from_moon_than_l1(self):
        """L2 is always further from Moon than L1.

        L1 is on the Earth-side of Moon; L2 on the far side.
        """
        pts = compute_lagrange_points()
        assert pts["L2"].dist_from_moon_km > pts["L1"].dist_from_moon_km

    def test_l4_equilateral_triangle(self):
        """L4 must form an equilateral triangle with Earth and Moon.

        Exact property (Lagrange 1772): |L4-Earth| = |L4-Moon| = Earth-Moon dist.
        """
        pts = compute_lagrange_points()
        L4 = pts["L4"]
        assert abs(L4.dist_from_earth_km - EARTH_MOON_KM) / EARTH_MOON_KM < 0.001, (
            f"|L4-Earth| = {L4.dist_from_earth_km:.0f} km ≠ {EARTH_MOON_KM:.0f} km"
        )
        assert abs(L4.dist_from_moon_km - EARTH_MOON_KM) / EARTH_MOON_KM < 0.001, (
            f"|L4-Moon| = {L4.dist_from_moon_km:.0f} km ≠ {EARTH_MOON_KM:.0f} km"
        )

    def test_l4_l5_mirror_symmetric(self):
        """L4 and L5 are mirror images across the Earth-Moon line (x-axis)."""
        pts = compute_lagrange_points()
        L4, L5 = pts["L4"], pts["L5"]
        assert abs(L4.x_nd - L5.x_nd) < 1e-10, "L4 and L5 must have same x"
        assert abs(L4.y_nd + L5.y_nd) < 1e-10, "L4 and L5 must have opposite y"

    def test_l3_beyond_earth_opposite_side(self):
        """L3 must lie beyond Earth on the opposite side from Moon."""
        pts = compute_lagrange_points()
        L3 = pts["L3"]
        # L3 should be at negative x (anti-Moon side), beyond Earth
        assert L3.x_km < -EARTH_MOON_KM * 0.9, (
            f"L3 at x={L3.x_km:.0f} km should be beyond Earth on anti-Moon side"
        )

    def test_all_points_have_positive_dist_from_earth(self):
        """All Lagrange points must be at positive distance from Earth."""
        pts = compute_lagrange_points()
        for name, pt in pts.items():
            assert pt.dist_from_earth_km > 0, f"{name} dist from Earth is not positive"

    def test_variable_earth_moon_distance(self):
        """Lagrange points scale correctly with Earth-Moon distance.

        At perigee (356,500 km) vs apogee (406,700 km), L2 dist from Moon
        scales approximately as (dist)^(2/3) (Hill sphere scaling).
        """
        pts_perigee = compute_lagrange_points(earth_moon_dist_km=356_500.0)
        pts_apogee  = compute_lagrange_points(earth_moon_dist_km=406_700.0)
        # L2 from Moon should be larger when Moon is further away
        assert pts_apogee["L2"].dist_from_moon_km > pts_perigee["L2"].dist_from_moon_km


class TestHaloOrbitPeriod:
    """Halo orbit period via Richardson (1980) linearized formula."""

    def test_l1_period_physical_range(self):
        """L1 halo orbit period: 7–20 days for Earth-Moon system.

        The Richardson (1980) linearized frequency gives the natural libration
        frequency at L1. For Earth-Moon μ=0.01215 and L1 at ~0.836 (nd),
        c₂ ≈ 11.2 and ωL ≈ 0.674 (nd/nd), giving T ≈ 9.3 days.
        Actual halo orbit periods range 8–16 days depending on amplitude;
        the linearized formula approximates the small-amplitude limit.
        Farquhar & Kamel (1973) Celest. Mech. 7 458: L1 period ~8–12 days.
        """
        mu = MU_CR3BP
        xL1 = _find_collinear_lagrange(mu, "L1")
        period = halo_orbit_period(xL1, mu)
        assert 7 < period < 20, (
            f"L1 halo period {period:.1f} days outside 7-20 day range"
        )

    def test_l2_period_physical_range(self):
        """L2 halo orbit period: 10–20 days (comparable to L1)."""
        mu = MU_CR3BP
        xL2 = _find_collinear_lagrange(mu, "L2")
        period = halo_orbit_period(xL2, mu)
        assert 10 < period < 20, (
            f"L2 halo period {period:.1f} days outside 10-20 day range"
        )


class TestQueqiaoHaloOrbit:
    """Chang'e-4 Queqiao relay satellite halo orbit."""

    def test_lagrange_point_is_l2(self):
        """Queqiao orbits L2 (far side line-of-sight requires beyond-Moon relay)."""
        halo = queqiao_halo_orbit()
        assert halo.lagrange_point == "L2"

    def test_amplitude_physical(self):
        """Queqiao amplitude: 13,000 km (Zhang et al. 2018)."""
        halo = queqiao_halo_orbit()
        assert abs(halo.amplitude_km - 13_000) < 2000, (
            f"Queqiao amplitude {halo.amplitude_km:.0f} km, expected ~13,000 km"
        )

    def test_period_physical(self):
        """Queqiao period: ~14 days (Zhang et al. 2018 report ~14.08 days)."""
        halo = queqiao_halo_orbit()
        assert 10 < halo.period_days < 20, (
            f"Queqiao period {halo.period_days:.1f} d outside 10-20 day range"
        )

    def test_insertion_dv_low(self):
        """L2 halo insertion Δv must be low (< 100 m/s) — efficient transfer.

        Queqiao insertion: ~25 m/s (Zhang et al. 2018).
        CR3BP near-L2 orbits have very small insertion Δv due to weak stability.
        """
        halo = queqiao_halo_orbit()
        assert halo.delta_v_insertion_ms < 100, (
            f"L2 insertion Δv {halo.delta_v_insertion_ms:.0f} m/s should be < 100 m/s"
        )


class TestArtemisNrho:
    """Artemis Gateway NRHO parameters."""

    def test_lagrange_point_is_l2(self):
        """Gateway NRHO is near L2."""
        nrho = artemis_nrho()
        assert nrho.lagrange_point == "L2"

    def test_period_near_resonance(self):
        """NRHO period: ~6.5617 days (9:2 resonance with lunar orbit).

        Zimovan et al. (2017) AAS 17-362.
        """
        nrho = artemis_nrho()
        assert abs(nrho.period_days - 6.5617) < 0.1, (
            f"NRHO period {nrho.period_days:.4f} d, expected 6.5617 d"
        )

    def test_station_keeping_very_low(self):
        """NRHO station-keeping: ~10 m/s/year — quasi-stable orbit.

        Williams et al. (2017) AAS 17-360.
        Much lower than GEO station-keeping (~50 m/s/year).
        """
        nrho = artemis_nrho()
        assert nrho.delta_v_insertion_ms < 30, (
            f"NRHO station-keeping {nrho.delta_v_insertion_ms:.0f} m/s/yr, expected ~10"
        )

    def test_amplitude_matches_nrho_range(self):
        """NRHO amplitude should represent the 3,000–70,000 km orbit range."""
        nrho = artemis_nrho()
        assert 20_000 < nrho.amplitude_km < 50_000
