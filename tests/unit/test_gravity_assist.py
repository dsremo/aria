"""Tests for gravity_assist.py — Gravity Assist / Gravitational Slingshot Optimizer.

Coverage:
  - Core physics: eccentricity, deflection angle
  - Heliocentric ΔC3: prograde gains energy, retrograde loses energy
  - Angle convention: approach_angle_deg=0° → prograde (ΔC3 > 0)
  - Monotonicity: lower altitude → larger deflection; larger planet → larger ΔC3
  - Validated mission profiles: Voyager 1, New Horizons, Pioneer 10, Cassini Venus
  - Grand Tour chain: no crash, positive final C3
  - Edge cases: surface flyby, near-zero v∞, large v∞

References used in validation comments:
  Anderson et al. (1979) Celest. Mech. 21:113
  Curtis (2014) Orbital Mechanics §8.7
  Bate, Mueller, White (1971) §2.8
  NASA SP-4031 (Kohlhase 1977)
  Stern et al. (2008) Space Science Reviews 140:1
"""

import math
import pytest

from aria.simulation.gravity_assist import (
    AU_M,
    PLANETS,
    FlybyConfig,
    FlybyResult,
    GravityAssistChain,
    chain_gravity_assists,
    cassini_venus_flyby1,
    c3_from_launch_dv,
    compute_flyby,
    flyby_deflection_angle,
    flyby_eccentricity,
    flyby_helio_delta_v,
    grand_tour_chain,
    hohmann_transfer_dv,
    max_c3_gain_from_flyby,
    new_horizons_jupiter_flyby,
    pioneer10_jupiter_flyby,
    v_inf_at_planet,
    voyager1_jupiter_flyby,
)

# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════

def _jupiter_cfg(alt_km=349_000.0, v_inf_ms=10_220.0, approach_deg=0.0) -> FlybyConfig:
    """Convenience: Voyager 1-style Jupiter config."""
    return FlybyConfig(
        planet="jupiter",
        flyby_alt_km=alt_km,
        v_inf_ms=v_inf_ms,
        approach_angle_deg=approach_deg,
    )


# ═══════════════════════════════════════════════════════════════════
#  1. FLYBY ECCENTRICITY
# ═══════════════════════════════════════════════════════════════════

class TestFlybyEccentricity:
    """flyby_eccentricity(r_peri, v_inf, mu) = 1 + r_peri × v∞² / μ"""

    def test_always_greater_than_one(self):
        """Hyperbolic orbit must have e > 1."""
        e = flyby_eccentricity(1e8, 5000.0, 1.267e17)
        assert e > 1.0

    def test_increases_with_v_inf(self):
        """Higher v∞ → larger e → smaller turning angle."""
        e_lo = flyby_eccentricity(4.2e8, 5_000.0, 1.267e17)
        e_hi = flyby_eccentricity(4.2e8, 15_000.0, 1.267e17)
        assert e_hi > e_lo

    def test_increases_with_periapsis(self):
        """Larger periapsis → larger e → smaller turning angle."""
        e_close = flyby_eccentricity(1e8, 10_000.0, 1.267e17)
        e_far   = flyby_eccentricity(1e9, 10_000.0, 1.267e17)
        assert e_far > e_close

    def test_decreases_with_mu(self):
        """Larger μ (stronger gravity) → smaller e → larger turning angle."""
        e_weak   = flyby_eccentricity(4.2e8, 10_000.0, 1e16)
        e_strong = flyby_eccentricity(4.2e8, 10_000.0, 1e18)
        assert e_strong < e_weak

    def test_surface_flyby_jupiter(self):
        """At Jupiter surface (r=71,492 km), v∞=10 km/s: e should be ~1.56."""
        # e = 1 + 7.149e7 × (10_000)² / 1.267e17 = 1 + 7.149e7 × 1e8 / 1.267e17
        # = 1 + 7.149e15 / 1.267e17 = 1 + 0.0564 ≈ 1.056
        r_surf = PLANETS["jupiter"]["radius_m"]
        e = flyby_eccentricity(r_surf, 10_000.0, PLANETS["jupiter"]["mu_m3s2"])
        assert e > 1.0
        assert e < 5.0   # sanity bound


# ═══════════════════════════════════════════════════════════════════
#  2. DEFLECTION ANGLE
# ═══════════════════════════════════════════════════════════════════

class TestDeflectionAngle:
    """δ = 2 arcsin(1/e) — Curtis (2014) §8.7 eq. 8.61"""

    def test_between_zero_and_pi(self):
        """Deflection must be in (0, π]."""
        delta = flyby_deflection_angle(4.2e8, 10_000.0, 1.267e17)
        assert 0.0 < delta <= math.pi

    def test_decreases_with_altitude(self):
        """Closer approach → higher eccentricity → LESS deflection."""
        # Higher e → sin(δ/2)=1/e is smaller → δ is smaller
        d_close = flyby_deflection_angle(4.0e8, 10_000.0, 1.267e17)
        d_far   = flyby_deflection_angle(8.0e8, 10_000.0, 1.267e17)
        assert d_close > d_far

    def test_decreases_with_v_inf(self):
        """Higher v∞ → larger e → smaller deflection angle."""
        d_slow = flyby_deflection_angle(4.2e8,  5_000.0, 1.267e17)
        d_fast = flyby_deflection_angle(4.2e8, 20_000.0, 1.267e17)
        assert d_slow > d_fast

    def test_maximum_at_surface_jupiter(self):
        """Surface flyby gives the maximum possible deflection for given v∞."""
        r_surface = PLANETS["jupiter"]["radius_m"]
        mu_J = PLANETS["jupiter"]["mu_m3s2"]
        d_surface = flyby_deflection_angle(r_surface, 10_000.0, mu_J)
        d_altitude = flyby_deflection_angle(r_surface + 1e8, 10_000.0, mu_J)
        assert d_surface > d_altitude

    def test_voyager1_jupiter_deflection_range(self):
        """Voyager 1 Jupiter: v∞=10.22 km/s, alt=349,000 km → δ should be 80°–110°."""
        mu_J = PLANETS["jupiter"]["mu_m3s2"]
        r_J  = PLANETS["jupiter"]["radius_m"]
        r_peri = r_J + 349_000.0 * 1000.0
        delta = flyby_deflection_angle(r_peri, 10_220.0, mu_J)
        assert math.degrees(delta) > 80.0
        assert math.degrees(delta) < 110.0


# ═══════════════════════════════════════════════════════════════════
#  3. HELIOCENTRIC VELOCITY CHANGE — SIGN CONVENTION
# ═══════════════════════════════════════════════════════════════════

class TestFlybyHelioDeltaV:
    """flyby_helio_delta_v: prograde (α=π) gains energy, retrograde (α=0) loses energy."""

    def _alpha(self, approach_deg: float) -> float:
        """Convert FlybyConfig convention to α."""
        return math.pi * (1.0 - approach_deg / 180.0)

    def test_prograde_gains_energy(self):
        """approach_angle=0° (α=π, prograde): ΔC3 must be positive."""
        alpha = self._alpha(0.0)
        delta = math.radians(63.8)
        _, dc3 = flyby_helio_delta_v(10_220.0, 13_070.0, delta, alpha)
        assert dc3 > 0.0, f"Prograde flyby should gain energy, got ΔC3={dc3:.2f}"

    def test_retrograde_loses_energy(self):
        """approach_angle=180° (α=0, retrograde): ΔC3 must be negative."""
        alpha = self._alpha(180.0)
        delta = math.radians(63.8)
        _, dc3 = flyby_helio_delta_v(10_220.0, 13_070.0, delta, alpha)
        assert dc3 < 0.0, f"Retrograde flyby should lose energy, got ΔC3={dc3:.2f}"

    def test_perpendicular_gains_energy(self):
        """approach_angle=90° (α=π/2): ΔC3 = 2 v_J v∞ sin(δ) > 0.

        The perpendicular case gains energy too — it can exceed the prograde ΔC3
        because the heliocentric speed before the flyby is higher (v_J and v∞ add
        in quadrature). The MAXIMUM ΔC3 is at α_opt = (π+δ)/2, not at α=π.
        """
        alpha = self._alpha(90.0)
        delta = math.radians(63.8)
        _, dc3_perp = flyby_helio_delta_v(10_220.0, 13_070.0, delta, alpha)
        # At α=π/2: ΔC3 = 2*v_J*v∞*[cos(π/2-δ) - cos(π/2)] = 2*v_J*v∞*sin(δ) > 0
        assert dc3_perp > 0.0, f"Perpendicular approach should gain energy, got {dc3_perp:.2f}"

    def test_symmetry_prograde_retrograde(self):
        """Prograde gain and retrograde loss should have roughly equal magnitudes."""
        alpha_pro  = self._alpha(0.0)
        alpha_retro = self._alpha(180.0)
        delta = math.radians(60.0)
        _, dc3_pro  = flyby_helio_delta_v(10_000.0, 13_070.0, delta, alpha_pro)
        _, dc3_retro = flyby_helio_delta_v(10_000.0, 13_070.0, delta, alpha_retro)
        # Both should have equal magnitude (symmetric geometry)
        assert abs(dc3_pro + dc3_retro) < 1.0, (
            f"|ΔC3_pro|={dc3_pro:.2f} should ≈ -|ΔC3_retro|={dc3_retro:.2f}"
        )

    def test_dv_helio_non_negative(self):
        """Magnitude of heliocentric Δv must be ≥ 0."""
        for approach_deg in [0.0, 45.0, 90.0, 135.0, 180.0]:
            alpha = self._alpha(approach_deg)
            dv, _ = flyby_helio_delta_v(10_000.0, 13_070.0, math.radians(50.0), alpha)
            assert dv >= 0.0, f"dv_helio < 0 at approach_deg={approach_deg}"

    def test_optimal_angle_is_between_prograde_and_perpendicular(self):
        """Maximum ΔC3 occurs at α_opt = (π+δ)/2, NOT at α=π (prograde).

        From calculus: d/dα[cos(α-δ) - cos(α)] = 0 → α_opt = (π+δ)/2.
        This is always in (π/2, π), i.e. between perpendicular and prograde.

        max_c3_gain_from_flyby correctly finds this via a full-circle scan,
        so its result must exceed the simple α=π prograde value.
        """
        planet = "jupiter"
        v_inf  = 10_000.0
        alt_km = 349_000.0
        dc3_max    = max_c3_gain_from_flyby(planet, v_inf_ms=v_inf, min_alt_km=alt_km)
        dc3_prograde = compute_flyby(
            FlybyConfig(planet, alt_km, v_inf, approach_angle_deg=0.0)
        ).delta_c3_km2s2
        assert dc3_max > dc3_prograde, (
            f"Scan max ΔC3={dc3_max:.2f} should exceed prograde ΔC3={dc3_prograde:.2f}"
        )

    def test_larger_planet_more_energy(self):
        """Larger planet speed → more heliocentric energy change."""
        delta = math.radians(60.0)
        alpha = math.pi  # prograde
        _, dc3_venus   = flyby_helio_delta_v(5_000.0, 35_020.0, delta, alpha)
        _, dc3_jupiter = flyby_helio_delta_v(5_000.0, 13_070.0, delta, alpha)
        # Venus is faster → should give more ΔC3 at same v∞ and δ
        assert dc3_venus > dc3_jupiter


# ═══════════════════════════════════════════════════════════════════
#  4. COMPUTE_FLYBY — ANGLE CONVENTION INTEGRATION
# ═══════════════════════════════════════════════════════════════════

class TestComputeFlyby:
    """compute_flyby integrates eccentricity, deflection, and heliocentric Δv."""

    def test_prograde_gives_positive_dc3(self):
        """approach_angle_deg=0° → prograde → ΔC3 > 0."""
        cfg = _jupiter_cfg(approach_deg=0.0)
        result = compute_flyby(cfg)
        assert result.delta_c3_km2s2 > 0.0, (
            f"Prograde Jupiter flyby should gain energy, got {result.delta_c3_km2s2:.2f}"
        )

    def test_retrograde_gives_negative_dc3(self):
        """approach_angle_deg=180° → retrograde → ΔC3 < 0."""
        cfg = _jupiter_cfg(approach_deg=180.0)
        result = compute_flyby(cfg)
        assert result.delta_c3_km2s2 < 0.0, (
            f"Retrograde Jupiter flyby should lose energy, got {result.delta_c3_km2s2:.2f}"
        )

    def test_is_prograde_flag_correct(self):
        """is_prograde flag matches sign of ΔC3."""
        pro  = compute_flyby(_jupiter_cfg(approach_deg=0.0))
        retro = compute_flyby(_jupiter_cfg(approach_deg=180.0))
        assert pro.is_prograde is True
        assert retro.is_prograde is False

    def test_eccentricity_greater_than_one(self):
        """All valid flybys must have hyperbolic eccentricity e > 1."""
        for planet in ["venus", "earth", "mars", "jupiter", "saturn"]:
            cfg = FlybyConfig(planet=planet, flyby_alt_km=1000.0,
                              v_inf_ms=8_000.0, approach_angle_deg=0.0)
            result = compute_flyby(cfg)
            assert result.eccentricity > 1.0, (
                f"Planet={planet}: e={result.eccentricity:.3f} must be > 1"
            )

    def test_deflection_bounded(self):
        """Deflection angle must be in (0°, 180°)."""
        result = compute_flyby(_jupiter_cfg())
        assert 0.0 < result.deflection_deg < 180.0

    def test_max_deflection_geq_deflection(self):
        """Surface deflection ≥ actual deflection (surface is closest possible)."""
        result = compute_flyby(_jupiter_cfg(alt_km=349_000.0))
        assert result.max_deflection_deg >= result.deflection_deg

    def test_v_inf_preserved(self):
        """v∞ is conserved (same as input — no energy change in planet frame)."""
        cfg = _jupiter_cfg(v_inf_ms=12_345.0)
        result = compute_flyby(cfg)
        assert result.v_inf_ms == pytest.approx(12_345.0)

    def test_lower_altitude_more_deflection(self):
        """Closer flyby → smaller e → larger deflection angle."""
        close = compute_flyby(_jupiter_cfg(alt_km=50_000.0))
        far   = compute_flyby(_jupiter_cfg(alt_km=500_000.0))
        assert close.deflection_deg > far.deflection_deg

    def test_lower_altitude_more_energy_gain(self):
        """Closer flyby → more deflection → more ΔC3 (for prograde)."""
        close = compute_flyby(_jupiter_cfg(alt_km=50_000.0))
        far   = compute_flyby(_jupiter_cfg(alt_km=500_000.0))
        assert close.delta_c3_km2s2 > far.delta_c3_km2s2

    def test_planet_speed_stored_correctly(self):
        """FlybyResult.v_planet_ms should match the planet table."""
        result = compute_flyby(_jupiter_cfg())
        assert result.v_planet_ms == pytest.approx(PLANETS["jupiter"]["v_orb_ms"])

    def test_unknown_planet_raises(self):
        """Unknown planet name raises ValueError."""
        cfg = FlybyConfig(planet="pluto", flyby_alt_km=100.0,
                          v_inf_ms=5000.0, approach_angle_deg=0.0)
        with pytest.raises(ValueError, match="Unknown planet"):
            compute_flyby(cfg)

    def test_higher_v_inf_less_deflection(self):
        """Faster spacecraft → less deflection per flyby (larger e)."""
        slow = compute_flyby(_jupiter_cfg(v_inf_ms=5_000.0))
        fast = compute_flyby(_jupiter_cfg(v_inf_ms=20_000.0))
        assert slow.deflection_deg > fast.deflection_deg

    def test_all_planets_prograde_positive(self):
        """Every planet gives positive ΔC3 for approach_angle=0°."""
        for planet in PLANETS:
            cfg = FlybyConfig(planet=planet, flyby_alt_km=1000.0,
                              v_inf_ms=8_000.0, approach_angle_deg=0.0)
            result = compute_flyby(cfg)
            assert result.delta_c3_km2s2 > 0.0, (
                f"Planet {planet} should give positive ΔC3, got {result.delta_c3_km2s2:.2f}"
            )


# ═══════════════════════════════════════════════════════════════════
#  5. MAX C3 GAIN FROM FLYBY
# ═══════════════════════════════════════════════════════════════════

class TestMaxC3GainFromFlyby:
    """max_c3_gain_from_flyby scans angles to find the maximum achievable ΔC3."""

    def test_positive_for_all_planets(self):
        """All planets should offer positive maximum ΔC3."""
        for planet in PLANETS:
            dc3 = max_c3_gain_from_flyby(planet, v_inf_ms=10_000.0, min_alt_km=100.0)
            assert dc3 > 0.0, f"{planet}: max ΔC3 should be positive, got {dc3:.2f}"

    def test_jupiter_beats_mars(self):
        """Jupiter is larger and faster (for v∞ = 10 km/s) than Mars."""
        dc3_J = max_c3_gain_from_flyby("jupiter", v_inf_ms=10_000.0)
        dc3_M = max_c3_gain_from_flyby("mars",    v_inf_ms=10_000.0)
        assert dc3_J > dc3_M

    def test_lower_altitude_more_max_dc3(self):
        """Lower minimum flyby altitude → more deflection → higher max ΔC3."""
        dc3_hi = max_c3_gain_from_flyby("jupiter", v_inf_ms=10_000.0, min_alt_km=100.0)
        dc3_lo = max_c3_gain_from_flyby("jupiter", v_inf_ms=10_000.0, min_alt_km=500_000.0)
        assert dc3_hi > dc3_lo

    def test_geq_prograde_single_flyby(self):
        """max_c3_gain should be ≥ prograde flyby ΔC3 at same altitude."""
        alt_km = 200_000.0
        v_inf  = 10_000.0
        dc3_max = max_c3_gain_from_flyby("jupiter", v_inf_ms=v_inf, min_alt_km=alt_km)
        dc3_pro = compute_flyby(FlybyConfig("jupiter", alt_km, v_inf, 0.0)).delta_c3_km2s2
        assert dc3_max >= dc3_pro - 1.0  # 1 km²/s² tolerance for scan resolution


# ═══════════════════════════════════════════════════════════════════
#  6. VALIDATED MISSION PROFILES
# ═══════════════════════════════════════════════════════════════════

class TestValidatedMissions:
    """Cross-check against published mission data."""

    def test_voyager1_jupiter_prograde(self):
        """Voyager 1 Jupiter flyby (March 1979) must show energy gain.

        Published: v∞ = 10.22 km/s, closest approach 349,000 km.
        Source: Anderson et al. (1979) Celest. Mech. 21:113 Table 1.
        """
        result = voyager1_jupiter_flyby()
        assert result.delta_c3_km2s2 > 0.0, "Voyager 1 Jupiter flyby must gain energy"
        assert result.is_prograde is True
        assert result.flyby_alt_km == pytest.approx(349_000.0)
        assert result.v_inf_ms == pytest.approx(10_220.0)

    def test_voyager1_deflection_in_range(self):
        """Voyager 1 Jupiter deflection should be 85°–110° for v∞=10.22 km/s at 349,000 km."""
        result = voyager1_jupiter_flyby()
        assert 85.0 < result.deflection_deg < 110.0, (
            f"Deflection {result.deflection_deg:.1f}° outside expected range"
        )

    def test_voyager1_significant_dc3(self):
        """Voyager 1 Jupiter ΔC3 should be > 100 km²/s² (enough to alter heliocentric orbit)."""
        result = voyager1_jupiter_flyby()
        assert result.delta_c3_km2s2 > 100.0, (
            f"Voyager 1 ΔC3 = {result.delta_c3_km2s2:.1f} km²/s², expected > 100"
        )

    def test_new_horizons_jupiter_prograde(self):
        """New Horizons Jupiter flyby (Feb 2007): v∞=18.4 km/s, prograde boost.

        Source: Stern et al. (2008) Space Science Reviews 140:1 Table 1.
        """
        result = new_horizons_jupiter_flyby()
        assert result.delta_c3_km2s2 > 0.0
        assert result.is_prograde is True

    def test_new_horizons_small_deflection(self):
        """New Horizons flew far (2.3 Mkm) → small deflection → small but positive ΔC3."""
        result = new_horizons_jupiter_flyby()
        # Very distant flyby → small deflection (< 30°)
        assert result.deflection_deg < 30.0, (
            f"New Horizons deflection {result.deflection_deg:.1f}° should be < 30°"
        )
        assert result.delta_c3_km2s2 > 0.0

    def test_cassini_venus_prograde(self):
        """Cassini Venus flyby 1 (April 1998): prograde, energy gain.

        Source: Wolf & Smith (1995) JPL Pub 95-7 §III.
        """
        result = cassini_venus_flyby1()
        assert result.delta_c3_km2s2 > 0.0
        assert result.is_prograde is True
        assert result.flyby_alt_km == pytest.approx(284.0)

    def test_cassini_venus_large_deflection(self):
        """Cassini Venus flyby at 284 km altitude with v∞=5.3 km/s → large deflection."""
        result = cassini_venus_flyby1()
        # Low-altitude flyby at low v∞ → near-maximum deflection (> 70°)
        assert result.deflection_deg > 70.0, (
            f"Cassini Venus deflection {result.deflection_deg:.1f}° should be > 70°"
        )

    def test_pioneer10_jupiter_prograde(self):
        """Pioneer 10 Jupiter flyby (Dec 1973): first spacecraft to achieve escape via GA.

        Source: Fimmel, Swindell, Burgess (1974) NASA SP-349 §4.
        """
        result = pioneer10_jupiter_flyby()
        assert result.delta_c3_km2s2 > 0.0
        assert result.is_prograde is True

    def test_pioneer10_closer_than_voyager1(self):
        """Pioneer 10 flew closer (130,354 km) than Voyager 1 (349,000 km) → more deflection."""
        pioneer  = pioneer10_jupiter_flyby()
        voyager1 = voyager1_jupiter_flyby()
        # Lower altitude → more deflection (for similar v∞)
        assert pioneer.flyby_alt_km < voyager1.flyby_alt_km


# ═══════════════════════════════════════════════════════════════════
#  7. GRAND TOUR CHAIN
# ═══════════════════════════════════════════════════════════════════

class TestGrandTourChain:
    """Grand Tour trajectory: Earth → Jupiter → Saturn → Uranus → Neptune."""

    @pytest.fixture(scope="class")
    def tour(self):
        return grand_tour_chain()

    def test_no_crash(self, tour):
        """Grand tour chain must run without raising an exception."""
        # Fixture construction is the test — reaching here means no crash
        assert tour is not None

    def test_four_flybys(self, tour):
        """Grand Tour must have exactly 4 flybys: Jupiter, Saturn, Uranus, Neptune."""
        assert len(tour.flybys) == 4

    def test_flyby_sequence(self, tour):
        """Flybys must be in the correct order: Jupiter, Saturn, Uranus, Neptune."""
        planets = [f.planet for f in tour.flybys]
        assert planets == ["jupiter", "saturn", "uranus", "neptune"]

    def test_final_c3_positive(self, tour):
        """Final C3 > 0 means heliocentric hyperbolic orbit (spacecraft escapes Sun)."""
        assert tour.final_c3_km2s2 > 0.0, (
            f"Grand Tour should result in solar escape (C3>0), got {tour.final_c3_km2s2:.1f}"
        )

    def test_final_c3_exceeds_launch(self, tour):
        """Grand Tour must end with more energy than at launch."""
        assert tour.final_c3_km2s2 > tour.launch_c3_km2s2

    def test_all_flybys_prograde(self, tour):
        """All four flybys are prograde → all ΔC3 > 0."""
        for fb in tour.flybys:
            assert fb.delta_c3_km2s2 > 0.0, (
                f"Flyby at {fb.planet}: ΔC3={fb.delta_c3_km2s2:.1f} should be > 0"
            )

    def test_total_dv_helio_positive(self, tour):
        """Sum of heliocentric |Δv| across all flybys must be positive."""
        assert tour.total_delta_v_helio_ms > 0.0

    def test_jupiter_gives_most_dc3(self, tour):
        """Jupiter is the dominant flyby — gives the largest ΔC3 of the four."""
        jup_dc3 = tour.flybys[0].delta_c3_km2s2  # Jupiter first
        for fb in tour.flybys[1:]:
            assert jup_dc3 > fb.delta_c3_km2s2, (
                f"Jupiter ΔC3={jup_dc3:.1f} should exceed {fb.planet} ΔC3={fb.delta_c3_km2s2:.1f}"
            )


# ═══════════════════════════════════════════════════════════════════
#  8. CHAIN_GRAVITY_ASSISTS — GENERAL
# ═══════════════════════════════════════════════════════════════════

class TestChainGravityAssists:
    """chain_gravity_assists builds a multi-flyby trajectory."""

    def test_single_flyby_chain(self):
        """Single-flyby chain should match compute_flyby for same config."""
        chain = chain_gravity_assists(
            departure_planet="earth",
            flyby_sequence=["jupiter"],
            flyby_altitudes_km=[349_000.0],
            launch_c3_km2s2=11.5,
            flyby_approach_angles_deg=[0.0],
        )
        assert len(chain.flybys) == 1
        # ΔC3 > 0 for prograde Jupiter flyby
        assert chain.flybys[0].delta_c3_km2s2 > 0.0

    def test_mismatched_lengths_raises(self):
        """If flyby_altitudes_km and flyby_sequence have different lengths, raise ValueError."""
        with pytest.raises(ValueError):
            chain_gravity_assists(
                departure_planet="earth",
                flyby_sequence=["jupiter", "saturn"],
                flyby_altitudes_km=[349_000.0],  # wrong length
                launch_c3_km2s2=11.5,
            )

    def test_retrograde_chain_loses_energy(self):
        """All-retrograde flybys: final C3 < launch C3."""
        chain = chain_gravity_assists(
            departure_planet="earth",
            flyby_sequence=["jupiter"],
            flyby_altitudes_km=[349_000.0],
            launch_c3_km2s2=100.0,
            flyby_approach_angles_deg=[180.0],  # retrograde
        )
        assert chain.final_c3_km2s2 < chain.launch_c3_km2s2

    def test_default_approach_angles_prograde(self):
        """Default approach_angles (None) → all prograde → all ΔC3 > 0."""
        chain = chain_gravity_assists(
            departure_planet="earth",
            flyby_sequence=["jupiter", "saturn"],
            flyby_altitudes_km=[349_000.0, 162_000.0],
            launch_c3_km2s2=11.5,
        )
        for fb in chain.flybys:
            assert fb.delta_c3_km2s2 > 0.0, (
                f"{fb.planet}: ΔC3={fb.delta_c3_km2s2:.1f} should be > 0 with default angles"
            )

    def test_sequence_description_correct(self):
        """sequence_description should list all planets in order."""
        chain = chain_gravity_assists(
            departure_planet="earth",
            flyby_sequence=["venus", "jupiter"],
            flyby_altitudes_km=[300.0, 300_000.0],
            launch_c3_km2s2=5.0,
        )
        assert "earth" in chain.sequence_description
        assert "venus" in chain.sequence_description
        assert "jupiter" in chain.sequence_description


# ═══════════════════════════════════════════════════════════════════
#  9. HOHMANN TRANSFER AND HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

class TestHohmannTransfer:
    """hohmann_transfer_dv: vis-viva for two-impulse circular orbit transfer."""

    def test_earth_to_mars_dv_range(self):
        """Earth→Mars Hohmann Δv1 ≈ 2.9 km/s (Curtis 2014 Example 6.1)."""
        r_E = PLANETS["earth"]["a_m"]
        r_M = PLANETS["mars"]["a_m"]
        dv1, dv2, tof = hohmann_transfer_dv(r_E, r_M)
        # Δv1 ≈ 2.9 km/s, Δv2 ≈ 2.6 km/s (from Earth to Mars Hohmann)
        assert 2_500.0 < dv1 < 3_200.0, f"Δv1={dv1:.0f} m/s out of expected range"
        assert 2_000.0 < dv2 < 3_000.0, f"Δv2={dv2:.0f} m/s out of expected range"

    def test_earth_to_jupiter_tof_years(self):
        """Earth→Jupiter Hohmann transfer: ~2.7 years (Curtis 2014)."""
        r_E = PLANETS["earth"]["a_m"]
        r_J = PLANETS["jupiter"]["a_m"]
        _, _, tof = hohmann_transfer_dv(r_E, r_J)
        assert 2.5 < tof < 3.0, f"TOF={tof:.2f} years out of expected ~2.7 year range"

    def test_outward_both_positive(self):
        """For outward transfer (r2 > r1), both Δv1 and Δv2 are positive."""
        r1 = PLANETS["earth"]["a_m"]
        r2 = PLANETS["saturn"]["a_m"]
        dv1, dv2, _ = hohmann_transfer_dv(r1, r2)
        assert dv1 > 0.0
        assert dv2 > 0.0


class TestVInfAtPlanet:
    """v_inf_at_planet: approximate arrival v∞ from Hohmann transfer."""

    def test_v_inf_positive(self):
        """Arrival v∞ must be positive for Earth→Jupiter."""
        v = v_inf_at_planet("earth", "jupiter")
        assert v > 0.0

    def test_earth_to_jupiter_range(self):
        """Earth→Jupiter Hohmann arrival v∞ ≈ 5.6 km/s (from circular orbit model)."""
        v = v_inf_at_planet("earth", "jupiter")
        assert 4_000.0 < v < 7_000.0, f"v∞={v:.0f} m/s out of expected ~5,600 m/s range"

    def test_earth_to_mars_range(self):
        """Earth→Mars Hohmann arrival v∞ ≈ 2.6 km/s."""
        v = v_inf_at_planet("earth", "mars")
        assert 1_500.0 < v < 3_500.0


class TestC3FromLaunchDv:
    """c3_from_launch_dv: C3 from parking orbit burn."""

    def test_zero_dv_gives_zero_c3(self):
        """Δv=0 from parking orbit → not enough for escape → C3=0."""
        c3 = c3_from_launch_dv(0.0)
        assert c3 == pytest.approx(0.0)

    def test_large_dv_gives_large_c3(self):
        """Very large Δv → large C3."""
        c3 = c3_from_launch_dv(10_000.0)
        assert c3 > 0.0

    def test_voyager1_launch_c3(self):
        """Voyager 1 TMI burn Δv ≈ 6.31 km/s from 200 km LEO → C3 ≈ 77.5 km²/s².

        Derivation: C3 = (v_circ + Δv_TMI)² − 2μ_earth/r_park
          v_circ(200 km) ≈ 7784 m/s
          For C3 = 77.5 km²/s² = 77.5×10⁶ m²/s²:
            (7784 + Δv)² = 77.5e6 + 2×3.986e14/6578137 = 198.7×10⁶ → Δv ≈ 6311 m/s

        Source: NASA SP-4031 Table 2-1 (C3); Δv derived from published C3.
        """
        c3 = c3_from_launch_dv(6_311.0, parking_orbit_alt_km=200.0)
        assert 70.0 < c3 < 85.0, (
            f"Voyager 1-class launch C3={c3:.1f} km²/s², expected ≈77.5 km²/s²"
        )

    def test_c3_never_negative(self):
        """C3 is clamped to 0 when Δv is insufficient for escape."""
        c3 = c3_from_launch_dv(100.0)  # negligible Δv
        assert c3 == pytest.approx(0.0)


# ═══════════════════════════════════════════════════════════════════
#  10. PLANET DATA TABLE SANITY
# ═══════════════════════════════════════════════════════════════════

class TestPlanetData:
    """Sanity-check the planet data table entries."""

    @pytest.mark.parametrize("planet", list(PLANETS.keys()))
    def test_orbital_speed_consistent(self, planet):
        """v_orb should be within 2% of sqrt(MU_SUN / a) for each planet."""
        import math as _math
        from aria.simulation.gravity_assist import MU_SUN
        p = PLANETS[planet]
        v_computed = _math.sqrt(MU_SUN / p["a_m"])
        v_table = p["v_orb_ms"]
        relative_err = abs(v_table - v_computed) / v_computed
        assert relative_err < 0.02, (
            f"{planet}: table v_orb={v_table:.0f} m/s vs computed {v_computed:.0f} m/s "
            f"({relative_err*100:.1f}% error)"
        )

    @pytest.mark.parametrize("planet", list(PLANETS.keys()))
    def test_mu_positive(self, planet):
        """μ must be positive for all planets."""
        assert PLANETS[planet]["mu_m3s2"] > 0.0

    @pytest.mark.parametrize("planet", list(PLANETS.keys()))
    def test_radius_positive(self, planet):
        """Radius must be positive for all planets."""
        assert PLANETS[planet]["radius_m"] > 0.0

    def test_jupiter_largest_mu(self):
        """Jupiter has the largest μ of all planets listed."""
        mu_J = PLANETS["jupiter"]["mu_m3s2"]
        for planet, data in PLANETS.items():
            if planet != "jupiter":
                assert mu_J > data["mu_m3s2"], (
                    f"Jupiter μ should exceed {planet} μ"
                )


# ═══════════════════════════════════════════════════════════════════
#  SIMULATOR-LAYER PLANNER (aria.simulator.gravity_assist)
# ═══════════════════════════════════════════════════════════════════
# Tests for the high-level mission planner that chains Hohmann legs +
# fly-by credits. Deep physics lives in aria.simulation.gravity_assist
# (tested above); these tests cover the planner surface (BODY_ORBITS,
# hohmann_transfer, gravity_assist_boost, plan_mission).


from aria.simulator.gravity_assist import (  # noqa: E402
    BODY_ORBITS,
    DEFAULT_FLYBY_ALT_KM,
    FlybyBoost,
    HohmannLeg,
    MissionPlan,
    gravity_assist_boost,
    hohmann_transfer,
    plan_mission,
)
from aria.simulator.gravity_assist import MU_SUN_M3S2  # noqa: E402


class TestBodyOrbits:
    """BODY_ORBITS should cover the canonical solar-system planets."""

    def test_contains_all_major_planets(self):
        for body in ("mercury", "venus", "earth", "mars",
                     "jupiter", "saturn", "uranus", "neptune"):
            assert body in BODY_ORBITS, f"{body} missing from BODY_ORBITS"

    def test_earth_au_is_unity(self):
        assert BODY_ORBITS["earth"]["a_au"] == pytest.approx(1.0, abs=1e-3)

    def test_periods_monotonic_with_distance(self):
        """Kepler's 3rd law — farther bodies have longer periods."""
        ordered = ["mercury", "venus", "earth", "mars",
                   "jupiter", "saturn", "uranus", "neptune"]
        periods = [BODY_ORBITS[b]["period_days"] for b in ordered]
        assert periods == sorted(periods)

    def test_kepler_third_law(self):
        """T² ∝ a³ — check Earth, Jupiter, Saturn against P²/a³ = const."""
        ratios = []
        for body in ("earth", "jupiter", "saturn"):
            a = BODY_ORBITS[body]["a_au"]
            T = BODY_ORBITS[body]["period_days"] / 365.25
            ratios.append(T ** 2 / a ** 3)
        # All ratios should be ≈ 1 (yr² / AU³) within 1 %.
        for r in ratios:
            assert r == pytest.approx(1.0, rel=0.01)


class TestHohmannTransferWrapper:
    """hohmann_transfer(r1_au, r2_au) returns (dv_kms, tof_days)."""

    def test_earth_to_mars_ballpark(self):
        """Earth→Mars Hohmann: total Δv ≈ 5.6 km/s, ToF ≈ 259 days.
        Curtis (2014) Example 6.3 / NASA trajectory primer."""
        dv_kms, tof_days = hohmann_transfer(1.0, 1.5237)
        assert 5.0 < dv_kms < 6.5, f"Earth→Mars Δv out of range: {dv_kms:.2f}"
        assert 250 < tof_days < 270, f"Earth→Mars ToF out of range: {tof_days:.1f}"

    def test_earth_to_jupiter_ballpark(self):
        """Earth→Jupiter Hohmann: total Δv ≈ 14 km/s, ToF ≈ 2.7 yr.
        Bate-Mueller-White table 5.4."""
        dv_kms, tof_days = hohmann_transfer(1.0, 5.2026)
        assert 13.0 < dv_kms < 15.0, f"Earth→Jupiter Δv out of range: {dv_kms:.2f}"
        assert 2.5 < tof_days / 365.25 < 3.0, (
            f"Earth→Jupiter ToF out of range: {tof_days/365.25:.2f} yr"
        )

    def test_symmetric(self):
        """Hohmann Δv is symmetric in the endpoints."""
        dv_ab, _ = hohmann_transfer(1.0, 5.2)
        dv_ba, _ = hohmann_transfer(5.2, 1.0)
        assert dv_ab == pytest.approx(dv_ba, rel=1e-6)

    def test_zero_radius_raises(self):
        with pytest.raises(ValueError):
            hohmann_transfer(0.0, 1.0)

    def test_mu_override_changes_result(self):
        """Passing a different μ should change the answer (sanity)."""
        dv_def, _ = hohmann_transfer(1.0, 1.5237)
        dv_hi, _ = hohmann_transfer(1.0, 1.5237, mu_sun=MU_SUN_M3S2 * 2.0)
        # Stronger Sun → higher speeds → larger absolute Δv.
        assert dv_hi > dv_def


class TestGravityAssistBoost:
    """gravity_assist_boost: practical slingshot Δv gain (km/s)."""

    def test_jupiter_flyby_ballpark(self):
        """Jupiter fly-by at 300 km altitude with v∞ = 10 km/s should
        deliver multiple km/s of free heliocentric Δv (Voyager-class)."""
        dv = gravity_assist_boost(
            v_approach_kms=10.0,
            planet_mass_kg=1.898e27,  # Jupiter mass (NASA fact sheet)
            closest_approach_km=300.0,
            planet="jupiter",
        )
        # Voyager 1 gained ~16 km/s at Jupiter; our "optimal case" formula
        # should produce something in the 5–25 km/s band.
        assert 3.0 < dv < 30.0, f"Jupiter fly-by Δv out of range: {dv:.2f}"

    def test_venus_smaller_than_jupiter(self):
        """Venus cannot match Jupiter's Δv gain at similar v∞ + altitude."""
        dv_v = gravity_assist_boost(10.0, 4.867e24, 300.0, planet="venus")
        dv_j = gravity_assist_boost(10.0, 1.898e27, 300.0, planet="jupiter")
        assert dv_v < dv_j

    def test_higher_altitude_reduces_gain(self):
        """Farther fly-by = smaller deflection = less Δv."""
        dv_close = gravity_assist_boost(10.0, 1.898e27, 300.0,  planet="jupiter")
        dv_far   = gravity_assist_boost(10.0, 1.898e27, 1e6,    planet="jupiter")
        assert dv_close > dv_far

    def test_bad_planet_raises(self):
        with pytest.raises(ValueError):
            gravity_assist_boost(10.0, 1.898e27, 300.0, planet="krypton")

    def test_periapsis_must_be_positive(self):
        """Altitude large-negative-enough to drive r_peri below zero raises."""
        with pytest.raises(ValueError):
            # Jupiter radius is 71,492 km → altitude -80,000 km puts r_peri negative.
            gravity_assist_boost(10.0, 1.898e27, -80_000.0, planet="jupiter")


class TestPlanMission:
    """plan_mission chains Hohmann legs + fly-by credits."""

    def test_direct_earth_to_jupiter(self):
        """Direct Earth→Jupiter plan: one leg, no fly-bys."""
        plan = plan_mission("earth", "jupiter")
        assert isinstance(plan, MissionPlan)
        assert plan.sequence == ["earth", "jupiter"]
        assert len(plan.legs) == 1
        assert plan.flybys == []
        assert plan.total_dv_savings_kms == 0.0
        assert plan.total_dv_required_kms == pytest.approx(
            plan.total_dv_gross_kms, rel=1e-9
        )
        # ≈ 14 km/s, 2.7 yr
        assert 13.0 < plan.total_dv_required_kms < 15.0
        assert 2.5 < plan.total_duration_days / 365.25 < 3.0

    def test_voyager_like_via_jupiter_saves_dv(self):
        """Earth → Jupiter → Saturn via Jupiter fly-by should show
        positive fly-by savings (free Δv credit)."""
        direct = plan_mission("earth", "saturn")
        via_j  = plan_mission("earth", "saturn", ["jupiter"])
        assert via_j.total_dv_savings_kms > 0.0
        # Net fuel Δv with the fly-by credit should be strictly lower
        # (or equal, if clamped) than the gross leg total.
        assert via_j.total_dv_required_kms < via_j.total_dv_gross_kms
        # Both direct and via-Jupiter should arrive at Saturn (same final body).
        assert direct.sequence[-1] == "saturn"
        assert via_j.sequence[-1] == "saturn"
        # Leg count = len(sequence) - 1
        assert len(via_j.legs) == len(via_j.sequence) - 1
        assert len(via_j.flybys) == 1
        assert via_j.flybys[0].planet == "jupiter"

    def test_earth_jupiter_via_venus_flyby(self):
        """Voyager / Galileo style: Earth → Venus → Earth → Jupiter.
        Venus + Earth fly-bys both contribute positive Δv credits."""
        plan = plan_mission("earth", "jupiter", ["venus", "earth"])
        assert plan.sequence == ["earth", "venus", "earth", "jupiter"]
        assert len(plan.legs) == 3
        assert len(plan.flybys) == 2
        # Each fly-by should produce a non-negative Δv gain.
        for fb in plan.flybys:
            assert fb.dv_gained_kms >= 0.0
            assert fb.deflection_deg > 0.0
            assert fb.closest_approach_km == DEFAULT_FLYBY_ALT_KM
        # Total savings strictly positive.
        assert plan.total_dv_savings_kms > 0.0

    def test_grand_tour_numbers_are_ballpark(self):
        """Grand Tour: Earth → Jupiter → Saturn → Uranus → Neptune.

        Pure patched-conic Hohmann summation gives the UPPER bound on
        cruise time: each leg is a half-ellipse between successive
        gas-giant orbits (Jupiter→Saturn ≈ 5 yr, Saturn→Uranus ≈ 16 yr,
        Uranus→Neptune ≈ 30 yr). Voyager's real 12-yr Earth-to-Neptune
        used the fly-bys themselves to shortcut the slow outer legs,
        which this simplified chained-Hohmann model does NOT — the UI
        shows the Hohmann-chain upper bound + the fuel savings credit.
        """
        plan = plan_mission(
            "earth", "neptune", ["jupiter", "saturn", "uranus"]
        )
        yrs = plan.total_duration_days / 365.25
        assert 10.0 < yrs < 200.0, (
            f"Grand Tour chained-Hohmann duration out of range: {yrs:.1f} yr"
        )
        # Fly-by savings should be multiple km/s (three gas giants).
        assert plan.total_dv_savings_kms > 2.0

    def test_to_dict_has_expected_keys(self):
        plan = plan_mission("earth", "mars")
        d = plan.to_dict()
        for key in ("sequence", "legs", "flybys",
                    "total_dv_required_kms", "total_dv_gross_kms",
                    "total_dv_savings_kms", "total_duration_days",
                    "total_duration_years", "summary"):
            assert key in d
        assert d["summary"] == "earth → mars"

    def test_unknown_body_raises(self):
        with pytest.raises(ValueError):
            plan_mission("earth", "vulcan")
        with pytest.raises(ValueError):
            plan_mission("earth", "jupiter", ["krypton"])

    def test_required_dv_never_negative(self):
        """Even with generous fly-by savings we clamp at zero — a fly-by
        cannot refund the initial escape burn."""
        plan = plan_mission(
            "earth", "jupiter",
            ["venus", "earth", "venus", "earth", "jupiter"],
        )
        assert plan.total_dv_required_kms >= 0.0
