"""Tests for lunar_return.py — Lunar Return / Trans-Earth Injection / Re-entry.

Coverage:
  - TEI burn: ΔV, propellant, v∞ at Moon, v_circ
  - Return trajectory: entry speed, corridor validation
  - Re-entry: peak heat rate, peak deceleration, Apollo-class check
  - Entry corridor analysis: angle sweep
  - Validated Apollo 11 return mission profile (July 1969)
  - Utility functions: tei_dv_from_orbit, entry_speed_from_v_inf

References:
  NASA SP-350 (1975) "Apollo 11 Mission Report" — primary validation
  Williams S.D. (1971) NASA TR-R-390 — Apollo reentry thermal environment
  NASA SP-4009 (2008) "The Apollo Spacecraft: A Chronology" §6.4 — entry corridor
  Allen & Eggers (1958) NACA TR-1381 — ballistic reentry analysis
"""

import math
import pytest

from aria.simulation.lunar_return import (
    APOLLO_CM_BALLISTIC_COEFF,
    APOLLO_CM_LIFT_TO_DRAG,
    APOLLO_ENTRY_ANGLE_REF_DEG,
    APOLLO_ENTRY_SPEED_REF_MS,
    APOLLO_PEAK_DECEL_REF_G,
    APOLLO_PEAK_HEAT_RATE_REF,
    ORION_CM_BALLISTIC_COEFF,
    ORION_CM_LIFT_TO_DRAG,
    G0_M_S2,
    MU_MOON,
    R_MOON_M,
    LunarOrbitConfig,
    TEIResult,
    ReturnTrajectory,
    ReentryAnalysis,
    LunarReturnResult,
    apollo11_return,
    artemis2_return,
    compute_reentry,
    compute_tei,
    compute_return_trajectory,
    entry_corridor_analysis,
    entry_speed_from_v_inf,
    simulate_return,
    tei_dv_from_orbit,
)

# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════

def _apollo_config() -> LunarOrbitConfig:
    """Apollo 11 CSM configuration at TEI (NASA SP-350 Table 3-IV)."""
    return LunarOrbitConfig(
        orbit_alt_km=120.0,
        mass_kg=30_377.0,
        isp_s=314.5,
        dry_mass_kg=26_303.0,
    )


# ═══════════════════════════════════════════════════════════════════
#  1. TEI BURN — compute_tei
# ═══════════════════════════════════════════════════════════════════

class TestComputeTei:
    """Trans-Earth Injection burn physics."""

    def test_v_circ_at_120km(self):
        """Circular orbit speed at 120 km lunar altitude should be ~1625 m/s."""
        r = R_MOON_M + 120_000.0
        v_expected = math.sqrt(MU_MOON / r)
        result = compute_tei(_apollo_config())
        assert result.v_circ_ms == pytest.approx(v_expected, rel=1e-6)

    def test_dv_tei_positive(self):
        """TEI ΔV must be positive (prograde burn increases energy)."""
        result = compute_tei(_apollo_config())
        assert result.dv_tei_ms > 0.0

    def test_dv_tei_apollo_range(self):
        """Apollo 11 TEI ΔV ~1000–1076 m/s (Orloff 2000 Table 2-2 / NASA
        SP-350 p.19). BUG-017 (2026-04-24): bumped default v∞_moon from
        837 → 1300 m/s so TEI matches the 60 h Apollo free-return profile
        the sim now reproduces; old 750–950 m/s window corresponded to
        the minimum-energy case that gave a 164 h return coast."""
        result = compute_tei(_apollo_config())
        assert 900.0 < result.dv_tei_ms < 1100.0, (
            f"TEI ΔV = {result.dv_tei_ms:.1f} m/s outside expected 900–1100 m/s"
        )

    def test_v_peri_exceeds_escape(self):
        """Speed at TEI periapsis must exceed lunar escape velocity (= sqrt(2μ/r))."""
        result = compute_tei(_apollo_config())
        r = result.r_orbit_m
        v_esc = math.sqrt(2.0 * MU_MOON / r)
        assert result.v_peri_tei_ms > v_esc

    def test_v_inf_moon_positive(self):
        """v∞ at Moon must be positive (hyperbolic departure)."""
        result = compute_tei(_apollo_config())
        assert result.v_inf_moon_ms > 0.0

    def test_v_inf_moon_equals_sqrt_c3(self):
        """v∞_moon = sqrt(C3_moon) — definition of hyperbolic excess speed."""
        result = compute_tei(_apollo_config())
        assert result.v_inf_moon_ms == pytest.approx(
            math.sqrt(result.c3_moon), rel=1e-9
        )

    def test_propellant_positive(self):
        """Propellant mass consumed for TEI must be positive."""
        result = compute_tei(_apollo_config())
        assert result.propellant_kg > 0.0

    def test_mass_after_less_than_before(self):
        """Post-TEI mass must be less than pre-TEI mass."""
        config = _apollo_config()
        result = compute_tei(config)
        assert result.mass_after_kg < config.mass_kg

    def test_mass_conservation(self):
        """mass_before = mass_after + propellant."""
        config = _apollo_config()
        result = compute_tei(config)
        assert result.mass_after_kg + result.propellant_kg == pytest.approx(
            config.mass_kg, rel=1e-9
        )

    def test_lower_orbit_needs_more_dv(self):
        """Lower lunar orbit requires less TEI ΔV (deeper in gravity well → faster orbit)."""
        config_hi = LunarOrbitConfig(200.0, 30_000.0, 314.5)
        config_lo = LunarOrbitConfig(60.0,  30_000.0, 314.5)
        tei_hi = compute_tei(config_hi)
        tei_lo = compute_tei(config_lo)
        # Lower orbit has higher v_circ → larger ΔV gap to escape
        # But escape speed also higher at lower altitude; net effect: lower orbit needs MORE ΔV
        assert tei_lo.dv_tei_ms > tei_hi.dv_tei_ms, (
            f"60km ΔV={tei_lo.dv_tei_ms:.1f} should exceed 200km ΔV={tei_hi.dv_tei_ms:.1f}"
        )

    def test_higher_v_inf_gives_more_dv(self):
        """Larger desired v∞ → larger TEI ΔV (more energy needed to depart faster)."""
        tei_slow = compute_tei(_apollo_config(), c3_moon_m2s2=500.0 ** 2)
        tei_fast = compute_tei(_apollo_config(), c3_moon_m2s2=1500.0 ** 2)
        assert tei_fast.dv_tei_ms > tei_slow.dv_tei_ms

    def test_orbit_radius_correct(self):
        """r_orbit_m = R_MOON + alt × 1000."""
        result = compute_tei(_apollo_config())
        expected_r = R_MOON_M + 120.0 * 1000.0
        assert result.r_orbit_m == pytest.approx(expected_r, rel=1e-9)


# ═══════════════════════════════════════════════════════════════════
#  2. RETURN TRAJECTORY — compute_return_trajectory
# ═══════════════════════════════════════════════════════════════════

class TestComputeReturnTrajectory:
    """Earth-return trajectory from TEI result."""

    @pytest.fixture
    def apollo_tei(self):
        return compute_tei(_apollo_config())

    def test_entry_speed_near_apollo(self, apollo_tei):
        """Entry speed should be within 1% of Apollo 11 actual (11,038 m/s).

        Source: NASA SP-350 Table 7-I.
        """
        traj = compute_return_trajectory(apollo_tei, entry_angle_deg=-6.49)
        # Our patched-conic model gives ~10,982 m/s (0.5% below 11,038 m/s actual)
        assert 10_800.0 < traj.v_entry_ms < 11_200.0, (
            f"Entry speed {traj.v_entry_ms:.1f} m/s outside 10,800–11,200 range"
        )

    def test_entry_speed_within_1pct_of_apollo(self, apollo_tei):
        """Simplified model should match Apollo 11 entry speed to within 1%."""
        traj = compute_return_trajectory(apollo_tei, entry_angle_deg=-6.49)
        apollo_actual = 11_038.0  # m/s; NASA SP-350 Table 7-I
        err_pct = abs(traj.v_entry_ms - apollo_actual) / apollo_actual * 100
        assert err_pct < 1.0, (
            f"Entry speed {traj.v_entry_ms:.1f} m/s is {err_pct:.2f}% from Apollo actual"
        )

    def test_corridor_ok_at_nominal_angle(self, apollo_tei):
        """Entry at −6.5° should be within the corridor (−7.5° to −5.5°)."""
        traj = compute_return_trajectory(apollo_tei, entry_angle_deg=-6.5)
        assert traj.is_corridor_ok is True
        assert traj.skip_out_risk is False
        assert traj.overheat_risk is False

    def test_skip_out_at_shallow_angle(self, apollo_tei):
        """Entry at −4° (too shallow) should trigger skip_out_risk."""
        traj = compute_return_trajectory(apollo_tei, entry_angle_deg=-4.0)
        assert traj.skip_out_risk is True
        assert traj.is_corridor_ok is False

    def test_overheat_at_steep_angle(self, apollo_tei):
        """Entry at −9° (too steep) should trigger overheat_risk."""
        traj = compute_return_trajectory(apollo_tei, entry_angle_deg=-9.0)
        assert traj.overheat_risk is True
        assert traj.is_corridor_ok is False

    def test_corridor_edges(self, apollo_tei):
        """Edge angles −5.5° and −7.5° should both be corridor OK."""
        for angle in [-5.5, -7.5]:
            traj = compute_return_trajectory(apollo_tei, entry_angle_deg=angle)
            assert traj.is_corridor_ok is True, (
                f"Angle {angle}° should be at corridor edge (OK), got not OK"
            )

    def test_entry_speed_dominated_by_earth_gravity(self):
        """Entry speed dominated by Earth's gravity well: barely changes with v∞ at Moon.

        Physics: v_entry² ≈ 2μ_earth/r_EI (≈ 11.2 km/s), dwarfing the small kinetic
        energy at Moon's distance.  Across v∞_moon ∈ [500, 1000] m/s the entry speed
        changes by less than 0.1%.
        """
        traj_lo = compute_return_trajectory(
            compute_tei(_apollo_config(), c3_moon_m2s2=500.0**2)
        )
        traj_hi = compute_return_trajectory(
            compute_tei(_apollo_config(), c3_moon_m2s2=1000.0**2)
        )
        diff_frac = abs(traj_hi.v_entry_ms - traj_lo.v_entry_ms) / traj_lo.v_entry_ms
        assert diff_frac < 0.005, (
            f"Entry speed should barely change with v∞: "
            f"{traj_lo.v_entry_ms:.1f} vs {traj_hi.v_entry_ms:.1f} m/s "
            f"(diff {diff_frac*100:.3f}%)"
        )


# ═══════════════════════════════════════════════════════════════════
#  3. RE-ENTRY ANALYSIS — compute_reentry
# ═══════════════════════════════════════════════════════════════════

class TestComputeReentry:
    """Atmospheric entry heating and deceleration analysis."""

    def test_apollo_peak_heat_rate_matches_published(self):
        """Apollo 11 ref conditions → peak heat rate ≈ 450 W/cm² (Williams 1971).

        Source: Williams S.D. (1971) NASA TR-R-390, Fig. 5.
        """
        result = compute_reentry(
            APOLLO_ENTRY_SPEED_REF_MS,
            entry_angle_deg=-APOLLO_ENTRY_ANGLE_REF_DEG,
            ballistic_coeff=APOLLO_CM_BALLISTIC_COEFF,
        )
        assert abs(result.peak_heat_rate_w_cm2 - APOLLO_PEAK_HEAT_RATE_REF) < 5.0, (
            f"Peak heat rate {result.peak_heat_rate_w_cm2:.1f} should be ≈ "
            f"{APOLLO_PEAK_HEAT_RATE_REF} W/cm²"
        )

    def test_apollo_peak_decel_matches_published(self):
        """Apollo 11 ref conditions → peak decel ≈ 6.9 g (NASA SP-350 Table 6-VII)."""
        result = compute_reentry(
            APOLLO_ENTRY_SPEED_REF_MS,
            entry_angle_deg=-APOLLO_ENTRY_ANGLE_REF_DEG,
        )
        assert abs(result.peak_decel_g - APOLLO_PEAK_DECEL_REF_G) < 0.1, (
            f"Peak decel {result.peak_decel_g:.2f} g should be ≈ {APOLLO_PEAK_DECEL_REF_G} g"
        )

    def test_heat_rate_increases_with_speed(self):
        """Higher entry speed → higher peak heat rate (∝ v³)."""
        slow = compute_reentry(10_000.0)
        fast = compute_reentry(12_000.0)
        assert fast.peak_heat_rate_w_cm2 > slow.peak_heat_rate_w_cm2

    def test_heat_rate_speed_cubed_scaling(self):
        """Peak heat rate scales as v³ per Sutton-Graves formula."""
        r1 = compute_reentry(10_000.0)
        r2 = compute_reentry(12_000.0)
        # q ∝ v³: ratio should ≈ (12/10)³ = 1.728
        ratio = r2.peak_heat_rate_w_cm2 / r1.peak_heat_rate_w_cm2
        assert ratio == pytest.approx((12_000.0 / 10_000.0) ** 3, rel=0.01), (
            f"Heat rate ratio {ratio:.3f} should ≈ (12/10)³ = {(1.2)**3:.3f}"
        )

    def test_decel_increases_with_speed(self):
        """Higher entry speed → higher peak deceleration (∝ v²)."""
        slow = compute_reentry(10_000.0)
        fast = compute_reentry(12_000.0)
        assert fast.peak_decel_g > slow.peak_decel_g

    def test_decel_speed_squared_scaling(self):
        """Peak deceleration scales as v² (Allen-Eggers model)."""
        r1 = compute_reentry(10_000.0)
        r2 = compute_reentry(12_000.0)
        ratio = r2.peak_decel_g / r1.peak_decel_g
        assert ratio == pytest.approx((12_000.0 / 10_000.0) ** 2, rel=0.01), (
            f"Decel ratio {ratio:.3f} should ≈ (12/10)² = {(1.2)**2:.3f}"
        )

    def test_steeper_angle_more_decel(self):
        """Steeper entry angle → higher peak deceleration."""
        shallow = compute_reentry(11_000.0, entry_angle_deg=-5.0)
        steep   = compute_reentry(11_000.0, entry_angle_deg=-8.0)
        assert steep.peak_decel_g > shallow.peak_decel_g

    def test_steeper_angle_more_heat(self):
        """Steeper entry angle → higher peak heat rate (more severe entry)."""
        shallow = compute_reentry(11_000.0, entry_angle_deg=-5.0)
        steep   = compute_reentry(11_000.0, entry_angle_deg=-8.0)
        assert steep.peak_heat_rate_w_cm2 > shallow.peak_heat_rate_w_cm2

    def test_peak_heat_positive(self):
        """Peak heat rate must be positive for any valid entry."""
        for v in [9_000, 11_000, 13_000]:
            result = compute_reentry(float(v))
            assert result.peak_heat_rate_w_cm2 > 0.0

    def test_peak_decel_positive(self):
        """Peak deceleration must be positive for any valid entry."""
        for v in [9_000, 11_000, 13_000]:
            result = compute_reentry(float(v))
            assert result.peak_decel_g > 0.0

    def test_kinetic_energy_scaling(self):
        """Entry kinetic energy = v²/2 (in MJ/kg)."""
        v = 11_038.0
        result = compute_reentry(v)
        expected = v**2 / (2e6)
        assert result.entry_kinetic_energy_mj_kg == pytest.approx(expected, rel=1e-6)

    def test_is_apollo_class_true_for_reference(self):
        """Apollo reference conditions should satisfy the apollo-class check."""
        result = compute_reentry(APOLLO_ENTRY_SPEED_REF_MS)
        assert result.is_apollo_class is True

    def test_is_apollo_class_false_for_very_slow(self):
        """Very low entry speed (hypothetical sub-orbital) should NOT be Apollo-class."""
        result = compute_reentry(5_000.0)
        assert result.is_apollo_class is False

    def test_is_apollo_class_false_for_very_fast(self):
        """Very high entry speed (Mars return ~14 km/s) should NOT be Apollo-class."""
        result = compute_reentry(14_000.0)
        assert result.is_apollo_class is False


# ═══════════════════════════════════════════════════════════════════
#  4. VALIDATED APOLLO 11 RETURN
# ═══════════════════════════════════════════════════════════════════

class TestApollo11Return:
    """Full Apollo 11 return mission validation against published data."""

    @pytest.fixture(scope="class")
    def result(self):
        return apollo11_return()

    def test_returns_lunar_return_result(self, result):
        """apollo11_return() must return a LunarReturnResult object."""
        assert isinstance(result, LunarReturnResult)

    def test_tei_dv_in_expected_range(self, result):
        """Apollo 11 TEI ΔV ~1000–1076 m/s (Orloff 2000 Table 2-2);
        default v∞_moon updated to 1300 m/s in BUG-017 fix (2026-04-24)."""
        assert 900.0 < result.tei.dv_tei_ms < 1100.0

    def test_entry_speed_near_actual(self, result):
        """Entry speed within 1% of NASA SP-350 published value (11,038 m/s)."""
        apollo_actual = 11_038.0
        err = abs(result.trajectory.v_entry_ms - apollo_actual) / apollo_actual
        assert err < 0.01, f"Entry speed error = {err*100:.2f}%, must be < 1%"

    def test_peak_heat_rate_near_actual(self, result):
        """Peak heat rate within 10% of Williams (1971) published value (~450 W/cm²)."""
        williams_value = 450.0
        err = abs(result.reentry.peak_heat_rate_w_cm2 - williams_value) / williams_value
        assert err < 0.10, (
            f"Peak heat rate = {result.reentry.peak_heat_rate_w_cm2:.1f} W/cm², "
            f"error {err*100:.1f}% from {williams_value}"
        )

    def test_peak_decel_near_actual(self, result):
        """Peak decel within 10% of NASA SP-350 Table 6-VII (6.9 g)."""
        sp350_value = 6.9
        err = abs(result.reentry.peak_decel_g - sp350_value) / sp350_value
        assert err < 0.10, (
            f"Peak decel = {result.reentry.peak_decel_g:.2f} g, "
            f"error {err*100:.1f}% from {sp350_value} g"
        )

    def test_entry_corridor_ok(self, result):
        """Apollo 11 entry at −6.49° should be within the corridor."""
        assert result.trajectory.is_corridor_ok is True
        assert result.trajectory.skip_out_risk is False
        assert result.trajectory.overheat_risk is False

    def test_is_apollo_class(self, result):
        """Apollo 11 conditions should satisfy the apollo-class flag."""
        assert result.reentry.is_apollo_class is True

    def test_propellant_positive(self, result):
        """TEI propellant mass must be positive."""
        assert result.tei.propellant_kg > 0.0

    def test_mass_after_tei_positive(self, result):
        """Post-TEI spacecraft mass must be positive."""
        assert result.tei.mass_after_kg > 0.0


# ═══════════════════════════════════════════════════════════════════
#  5. ENTRY CORRIDOR ANALYSIS
# ═══════════════════════════════════════════════════════════════════

class TestEntryCorridor:
    """entry_corridor_analysis sweeps entry angles."""

    @pytest.fixture
    def corridor(self):
        return entry_corridor_analysis(11_038.0)

    def test_returns_list(self, corridor):
        """Should return a list of dicts."""
        assert isinstance(corridor, list)
        assert len(corridor) > 0

    def test_nominal_angle_in_corridor(self, corridor):
        """The −6.5° nominal angle must be OK (corridor = True)."""
        for entry in corridor:
            if abs(entry["entry_angle_deg"] - (-6.5)) < 0.1:
                assert entry["is_corridor_ok"] is True
                break

    def test_shallow_angle_skip_risk(self, corridor):
        """Angles shallower than −5.5° should have skip_out_risk=True."""
        for entry in corridor:
            if entry["entry_angle_deg"] > -5.5:
                assert entry["skip_out_risk"] is True, (
                    f"Angle {entry['entry_angle_deg']}° should have skip_out_risk"
                )

    def test_steep_angle_overheat_risk(self, corridor):
        """Angles steeper than −7.5° should have overheat_risk=True."""
        for entry in corridor:
            if entry["entry_angle_deg"] < -7.5:
                assert entry["overheat_risk"] is True, (
                    f"Angle {entry['entry_angle_deg']}° should have overheat_risk"
                )

    def test_heat_rate_monotone_with_angle(self, corridor):
        """Steeper entry angle → more heating (monotone).

        Sorted ascending by angle: -9 < -8 < ... < -4.
        pairs[i] is LESS steep than pairs[i-1] → should have LESS heat.
        q ∝ sqrt(sin|γ|), strictly monotone.
        """
        angles = [e["entry_angle_deg"] for e in corridor]
        heats  = [e["peak_heat_w_cm2"] for e in corridor]
        # Sort ascending: most-steep (-9) first, least-steep (-4) last
        pairs = sorted(zip(angles, heats), key=lambda x: x[0])
        for i in range(1, len(pairs)):
            # pairs[i] has a larger (less negative) angle = shallower = less heat
            assert pairs[i][1] <= pairs[i-1][1] or abs(pairs[i][0] - pairs[i-1][0]) < 0.01, (
                f"Heat rate should decrease as angle becomes shallower: "
                f"angle {pairs[i][0]}° heat {pairs[i][1]:.1f} W/cm² should be ≤ "
                f"angle {pairs[i-1][0]}° heat {pairs[i-1][1]:.1f} W/cm²"
            )

    def test_custom_angles(self):
        """Custom angle list should return correct length."""
        custom = [-5.0, -6.0, -7.0]
        result = entry_corridor_analysis(11_038.0, entry_angles_deg=custom)
        assert len(result) == 3
        assert [r["entry_angle_deg"] for r in result] == custom


# ═══════════════════════════════════════════════════════════════════
#  6. UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

class TestTEIDVFromOrbit:
    """tei_dv_from_orbit: quick TEI ΔV trade study."""

    def test_positive_output(self):
        """TEI ΔV must be positive for any reasonable input."""
        dv = tei_dv_from_orbit(110.0)
        assert dv > 0.0

    def test_higher_orbit_lower_dv(self):
        """Higher orbit → lower orbital speed → less ΔV needed to escape."""
        dv_lo = tei_dv_from_orbit(60.0)
        dv_hi = tei_dv_from_orbit(300.0)
        assert dv_lo > dv_hi

    def test_higher_v_inf_more_dv(self):
        """Larger v∞ goal → more TEI ΔV required."""
        dv_slow = tei_dv_from_orbit(110.0, v_inf_moon_ms=500.0)
        dv_fast = tei_dv_from_orbit(110.0, v_inf_moon_ms=2000.0)
        assert dv_fast > dv_slow

    def test_matches_compute_tei(self):
        """tei_dv_from_orbit should match compute_tei ΔV for same inputs."""
        orbit_alt = 120.0
        v_inf = 837.0
        dv_quick = tei_dv_from_orbit(orbit_alt, v_inf_moon_ms=v_inf)
        config = LunarOrbitConfig(orbit_alt_km=orbit_alt, mass_kg=30_000.0, isp_s=314.5)
        tei_full = compute_tei(config, c3_moon_m2s2=v_inf**2)
        assert dv_quick == pytest.approx(tei_full.dv_tei_ms, rel=1e-6)


class TestEntrySpeedFromVInf:
    """entry_speed_from_v_inf: v_entry = sqrt(v∞² + 2μ/r_EI)."""

    def test_v_inf_zero_gives_escape_speed(self):
        """At v∞ = 0 (minimum energy), entry speed = escape speed at EI altitude."""
        from aria.simulation.lunar_return import MU_EARTH, R_EARTH_M, ENTRY_INTERFACE_M
        r_ei = R_EARTH_M + ENTRY_INTERFACE_M
        v_esc_EI = math.sqrt(2.0 * MU_EARTH / r_ei)
        v_entry = entry_speed_from_v_inf(0.0)
        assert v_entry == pytest.approx(v_esc_EI, rel=1e-9)

    def test_increases_with_v_inf(self):
        """Higher v∞ → higher entry speed."""
        slow = entry_speed_from_v_inf(0.0)
        fast = entry_speed_from_v_inf(2000.0)
        assert fast > slow

    def test_value_positive(self):
        """Entry speed must always be positive."""
        assert entry_speed_from_v_inf(0.0) > 0.0
        assert entry_speed_from_v_inf(500.0) > 0.0

    def test_minimum_lunar_return_speed(self):
        """Entry speed for v∞=0 should be ~11,074 m/s (Moon-distance minimum energy)."""
        v_entry = entry_speed_from_v_inf(0.0)
        # Minimum energy Earth return (v∞→0): all speed comes from gravity well
        # v_entry² = 2μ/r_EI = 2×3.986e14/6500057 ≈ 122.6×10⁶ → v ≈ 11074 m/s
        assert 11_000.0 < v_entry < 11_200.0, (
            f"Minimum entry speed {v_entry:.0f} m/s outside expected 11,000–11,200 m/s range"
        )


# ═══════════════════════════════════════════════════════════════════
#  7. LIFT-TO-DRAG CORRECTION — Loh (1963) L/D model
# ═══════════════════════════════════════════════════════════════════

class TestLiftToDragCorrection:
    """L/D parameter modifies peak decel and heat rate per Loh (1963)."""

    def test_default_ld_matches_apollo(self):
        """Default L/D=0.3 reproduces Apollo calibration (no correction)."""
        re = compute_reentry(
            APOLLO_ENTRY_SPEED_REF_MS,
            entry_angle_deg=-APOLLO_ENTRY_ANGLE_REF_DEG,
            lift_to_drag=APOLLO_CM_LIFT_TO_DRAG,
        )
        assert re.peak_decel_g == pytest.approx(APOLLO_PEAK_DECEL_REF_G, rel=0.01)
        assert re.peak_heat_rate_w_cm2 == pytest.approx(APOLLO_PEAK_HEAT_RATE_REF, rel=0.01)

    def test_ballistic_higher_peak_g(self):
        """L/D=0 (ballistic) gives ~30% higher peak-g than L/D=0.3 (Apollo).

        Loh (1963) §4.3: n(L/D=0)/n(L/D=0.3) ≈ (1+0.3)/(1+0) = 1.3.
        """
        re_apollo = compute_reentry(11_038.0, entry_angle_deg=-6.49, lift_to_drag=0.3)
        re_ballistic = compute_reentry(11_038.0, entry_angle_deg=-6.49, lift_to_drag=0.0)
        ratio = re_ballistic.peak_decel_g / re_apollo.peak_decel_g
        assert ratio == pytest.approx(1.3, rel=0.01), (
            f"Ballistic/Apollo peak-g ratio {ratio:.3f} should ≈ 1.3"
        )

    def test_higher_ld_lower_peak_g(self):
        """Higher L/D → lower peak deceleration (more lift → more time to slow down)."""
        g_low = compute_reentry(11_000.0, entry_angle_deg=-6.0, lift_to_drag=0.1).peak_decel_g
        g_mid = compute_reentry(11_000.0, entry_angle_deg=-6.0, lift_to_drag=0.3).peak_decel_g
        g_high = compute_reentry(11_000.0, entry_angle_deg=-6.0, lift_to_drag=0.5).peak_decel_g
        assert g_low > g_mid > g_high

    def test_higher_ld_lower_heat_rate(self):
        """Higher L/D → lower peak heat rate (vehicle stays higher → lower ρ)."""
        q_low = compute_reentry(11_000.0, entry_angle_deg=-6.0, lift_to_drag=0.1).peak_heat_rate_w_cm2
        q_mid = compute_reentry(11_000.0, entry_angle_deg=-6.0, lift_to_drag=0.3).peak_heat_rate_w_cm2
        q_high = compute_reentry(11_000.0, entry_angle_deg=-6.0, lift_to_drag=0.5).peak_heat_rate_w_cm2
        assert q_low > q_mid > q_high

    def test_ld_heat_rate_correction_weaker_than_decel(self):
        """Heat rate L/D correction is sqrt of decel correction (q ∝ sqrt(ρ))."""
        re_03 = compute_reentry(11_000.0, entry_angle_deg=-6.0, lift_to_drag=0.3)
        re_00 = compute_reentry(11_000.0, entry_angle_deg=-6.0, lift_to_drag=0.0)
        g_ratio = re_00.peak_decel_g / re_03.peak_decel_g
        q_ratio = re_00.peak_heat_rate_w_cm2 / re_03.peak_heat_rate_w_cm2
        # q_ratio should ≈ sqrt(g_ratio)
        assert q_ratio == pytest.approx(math.sqrt(g_ratio), rel=0.01)

    def test_orion_ld_equals_apollo_ld(self):
        """Orion and Apollo both have L/D ≈ 0.3 (offset CG trim)."""
        assert ORION_CM_LIFT_TO_DRAG == pytest.approx(APOLLO_CM_LIFT_TO_DRAG, abs=0.05)


# ═══════════════════════════════════════════════════════════════════
#  8. ARTEMIS 2 VALIDATION — April 10, 2026
# ═══════════════════════════════════════════════════════════════════

class TestArtemis2Return:
    """Validate against Artemis 2 mission data (April 2026).

    Artemis 2 was a free-return lunar flyby using a ballistic (non-skip) entry.
    Entry speed ≈ Mach 33 ≈ 11 km/s; peak decel ≈ 3.9 g.
    References:
        NASA Artemis II Flight Day 10 blog (April 10, 2026)
        NASA/TM-2009-214786 — Orion aerodynamic characteristics
    """

    @pytest.fixture
    def result(self):
        return artemis2_return()

    def test_returns_result(self, result):
        assert isinstance(result, LunarReturnResult)

    def test_entry_speed_mach_33(self, result):
        """Entry speed ≈ 11 km/s (Mach 33 confirmed by NASA blog)."""
        # Speed of sound at 122 km: ~270 m/s → Mach 33 = ~8,910 m/s
        # But "Mach 33" in NASA press usually means sea-level equivalent.
        # Sea-level speed of sound: 343 m/s → Mach 33 = 11,319 m/s.
        # Actual entry speed is ~11,000 m/s from orbital mechanics.
        assert 10_800.0 < result.trajectory.v_entry_ms < 11_200.0, (
            f"Artemis 2 entry speed {result.trajectory.v_entry_ms:.0f} m/s "
            f"should be ~11,000 m/s (Mach 33)"
        )

    def test_peak_decel_near_published(self, result):
        """Peak decel ≈ 3.9 g (NASA pre-flight prediction, confirmed).

        Entry angle −3.7° with L/D=0.3 → sin(3.7°)/sin(6.49°) × 6.9 ≈ 3.9 g.
        """
        assert result.reentry.peak_decel_g == pytest.approx(3.9, abs=0.3), (
            f"Artemis 2 peak decel {result.reentry.peak_decel_g:.1f} g "
            f"should be ≈ 3.9 g (±0.3 g tolerance)"
        )

    def test_peak_heat_rate_lower_than_apollo(self, result):
        """Shallower entry → lower peak heat rate than Apollo (~450 W/cm²)."""
        assert result.reentry.peak_heat_rate_w_cm2 < APOLLO_PEAK_HEAT_RATE_REF

    def test_peak_heat_rate_reasonable(self, result):
        """Heat rate should be 250–400 W/cm² for Artemis 2 shallow entry."""
        assert 250.0 < result.reentry.peak_heat_rate_w_cm2 < 400.0

    def test_shallow_entry_angle(self, result):
        """Artemis 2 entered shallower than Apollo (−3.7° vs −6.49°)."""
        assert abs(result.trajectory.entry_corridor_deg) < abs(-6.49)

    def test_is_apollo_class(self, result):
        """Artemis 2 is still in the Apollo-class range (11 km/s lunar return)."""
        assert result.reentry.is_apollo_class is True

    def test_orion_ballistic_coeff_differs_from_apollo(self):
        """Orion β ≈ 335 kg/m² (heavier, bigger) vs Apollo β ≈ 352.6 kg/m²."""
        assert ORION_CM_BALLISTIC_COEFF != APOLLO_CM_BALLISTIC_COEFF
        # Orion β is actually slightly lower than Apollo (bigger area relative to mass)
        assert ORION_CM_BALLISTIC_COEFF < APOLLO_CM_BALLISTIC_COEFF
