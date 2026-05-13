"""R45 — CubeSat de-orbit advisor integration tests.

The advisor is the first ARIA *product* — a closed-loop deliverable
that takes operator inputs and produces a single high-stakes
recommendation.  Tests verify each regime (natural decay,
propulsive burn, infeasible) plus the underlying physics agreements
against published references.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from aria.products.cubesat_deorbit import (
    BurnPlan,
    Decision,
    Footprint,
    MissionParams,
    NaturalDecayResult,
    SpacecraftState,
    advise_deorbit,
    estimate_reentry_footprint,
    natural_decay_lifetime,
    plan_propulsive_deorbit,
)
from aria.products.cubesat_deorbit.advisor import (
    G0,
    _hohmann_dv_to_lower_periapsis_mps,
)


# ── State arithmetic ──────────────────────────────────────────


class TestSpacecraftState:
    def test_ballistic_coefficient(self):
        state = SpacecraftState(
            altitude_km=550, inclination_deg=51.6,
            mass_kg=12.0, drag_coefficient=2.2, cross_section_m2=0.06,
        )
        # β = 12 / (2.2 × 0.06) ≈ 90.9 kg/m²
        assert state.ballistic_coefficient_kg_m2 == pytest.approx(90.9, abs=0.5)

    def test_delta_v_capacity_zero_propellant(self):
        state = SpacecraftState(
            altitude_km=500, inclination_deg=51.6,
            mass_kg=12.0, propellant_kg=0.0, isp_s=220.0,
        )
        assert state.delta_v_capacity_mps == 0.0

    def test_delta_v_capacity_tsiolkovsky(self):
        """0.5 kg butane in 12 kg wet, Isp 220 s → ΔV ≈ 91.7 m/s."""
        state = SpacecraftState(
            altitude_km=500, inclination_deg=51.6,
            mass_kg=12.0, propellant_kg=0.5, isp_s=220.0,
        )
        expected = 220.0 * G0 * math.log(12.0 / 11.5)
        assert state.delta_v_capacity_mps == pytest.approx(expected, rel=1e-6)


# ── Hohmann ΔV ────────────────────────────────────────────────


class TestHohmann:
    def test_lower_periapsis_400_to_120(self):
        """Vallado §9.2 worked example region.  ΔV at 400 km circular
        to lower periapsis to 120 km is ≈ 79 m/s."""
        dv = _hohmann_dv_to_lower_periapsis_mps(400.0, 120.0)
        assert dv == pytest.approx(79.0, abs=5.0)

    def test_zero_when_target_above_current(self):
        dv = _hohmann_dv_to_lower_periapsis_mps(400.0, 500.0)
        assert dv == 0.0

    def test_higher_alt_needs_more_dv(self):
        low = _hohmann_dv_to_lower_periapsis_mps(400.0, 120.0)
        high = _hohmann_dv_to_lower_periapsis_mps(700.0, 120.0)
        assert high > low


# ── Natural decay regime ──────────────────────────────────────


class TestNaturalDecay:
    def test_400km_decays_under_5_years(self):
        """A 400 km, 12 kg, 0.06 m² CubeSat decays in ~1-2 yr at
        moderate solar activity."""
        state = SpacecraftState(
            altitude_km=400.0, inclination_deg=51.6,
            mass_kg=12.0, cross_section_m2=0.06,
        )
        params = MissionParams(f107_solar_flux=150.0)
        result = natural_decay_lifetime(state, params)
        assert result.lifetime_years < 5.0
        assert result.fcc_compliant
        assert result.nasa_25yr_compliant

    def test_low_altitude_returns_short_profile(self):
        state = SpacecraftState(altitude_km=300.0, inclination_deg=51.6,
                                mass_kg=12.0)
        params = MissionParams()
        result = natural_decay_lifetime(state, params)
        assert len(result.profile_alt_time) >= 2
        assert result.profile_alt_time[0][0] >= result.profile_alt_time[-1][0]


# ── Burn planner ─────────────────────────────────────────────


class TestBurnPlanner:
    def test_no_propellant_returns_none(self):
        state = SpacecraftState(
            altitude_km=700.0, inclination_deg=51.6,
            mass_kg=12.0, propellant_kg=0.0, isp_s=220.0,
        )
        params = MissionParams()
        assert plan_propulsive_deorbit(state, params) is None

    def test_insufficient_propellant_returns_none(self):
        # 0.5 kg propellant in 12 kg → 91 m/s ΔV, but 700 km decay
        # needs ~165 m/s.
        state = SpacecraftState(
            altitude_km=700.0, inclination_deg=51.6,
            mass_kg=12.0, propellant_kg=0.5, isp_s=220.0,
        )
        params = MissionParams()
        assert plan_propulsive_deorbit(state, params) is None

    def test_sufficient_propellant_yields_plan(self):
        state = SpacecraftState(
            altitude_km=700.0, inclination_deg=51.6,
            mass_kg=12.0, propellant_kg=1.5, isp_s=220.0,
        )
        params = MissionParams()
        plan = plan_propulsive_deorbit(state, params)
        assert plan is not None
        assert plan.delta_v_mps > 0.0
        assert plan.direction == "retrograde"
        assert plan.propellant_kg_burned < state.propellant_kg
        assert plan.expected_reentry_utc > plan.burn_epoch_utc

    def test_propellant_burned_consistent_with_tsiolkovsky(self):
        state = SpacecraftState(
            altitude_km=700.0, inclination_deg=51.6,
            mass_kg=12.0, propellant_kg=1.5, isp_s=220.0,
        )
        params = MissionParams()
        plan = plan_propulsive_deorbit(state, params)
        expected_burn = state.mass_kg * (
            1.0 - math.exp(-plan.delta_v_mps / (state.isp_s * G0))
        )
        assert plan.propellant_kg_burned == pytest.approx(expected_burn, rel=1e-6)


# ── Footprint ────────────────────────────────────────────────


class TestFootprint:
    def test_inclination_drives_nominal_latitude(self):
        state = SpacecraftState(
            altitude_km=500, inclination_deg=51.6, mass_kg=12.0,
            propellant_kg=2.0, isp_s=220.0,
        )
        params = MissionParams()
        plan = plan_propulsive_deorbit(state, params)
        fp = estimate_reentry_footprint(plan, state)
        assert fp.nominal_lat_deg == pytest.approx(51.6, abs=0.1)

    def test_high_inclination_clamped_to_80(self):
        state = SpacecraftState(
            altitude_km=500, inclination_deg=98.0, mass_kg=12.0,
            propellant_kg=2.0, isp_s=220.0,
        )
        params = MissionParams()
        plan = plan_propulsive_deorbit(state, params)
        fp = estimate_reentry_footprint(plan, state)
        # Sun-synchronous orbits clamp at 80° because the reentry
        # latitude isn't necessarily at the orbital extreme.
        assert abs(fp.nominal_lat_deg) <= 80.0

    def test_casualty_area_scales_with_mass(self):
        state12 = SpacecraftState(
            altitude_km=500, inclination_deg=51.6, mass_kg=12.0,
            propellant_kg=2.0, isp_s=220.0,
        )
        state100 = SpacecraftState(
            altitude_km=500, inclination_deg=51.6, mass_kg=100.0,
            propellant_kg=2.0, isp_s=220.0,
        )
        params = MissionParams()
        fp12 = estimate_reentry_footprint(
            plan_propulsive_deorbit(state12, params), state12,
        )
        fp100 = estimate_reentry_footprint(
            plan_propulsive_deorbit(state100, params), state100,
        )
        assert fp100.casualty_area_m2 > fp12.casualty_area_m2


# ── End-to-end advisor decisions ─────────────────────────────


class TestAdvisor:
    def test_400km_natural_decay(self):
        state = SpacecraftState(
            altitude_km=400.0, inclination_deg=51.6,
            mass_kg=12.0, cross_section_m2=0.06,
        )
        rec = advise_deorbit(state, MissionParams())
        assert rec.decision is Decision.NATURAL_DECAY
        assert rec.burn_plan is None
        assert rec.compliance.fcc_5_year
        assert rec.compliance.nasa_25_year

    def test_700km_no_propellant_infeasible(self):
        state = SpacecraftState(
            altitude_km=700.0, inclination_deg=51.6,
            mass_kg=12.0, propellant_kg=0.0,
        )
        rec = advise_deorbit(state, MissionParams())
        assert rec.decision is Decision.INFEASIBLE
        assert rec.burn_plan is None
        # Must list the specific shortfall.
        assert any("shortfall" in r.lower() for r in rec.rationale)

    def test_700km_with_propellant_burn_required(self):
        state = SpacecraftState(
            altitude_km=700.0, inclination_deg=51.6,
            mass_kg=12.0, propellant_kg=1.5, isp_s=220.0,
        )
        rec = advise_deorbit(state, MissionParams())
        assert rec.decision is Decision.BURN_REQUIRED
        assert rec.burn_plan is not None
        assert rec.footprint is not None
        assert rec.compliance.fcc_5_year is False
        # Operator actions must be specific + actionable.
        assert any("retrograde burn" in a for a in rec.operator_actions)

    def test_compliance_disabled_skips_burn(self):
        """If the operator declares compliance is not required (e.g.
        non-FCC-licensed deep-space cubesat), the advisor must not
        force a burn even with long decay."""
        state = SpacecraftState(
            altitude_km=700.0, inclination_deg=51.6,
            mass_kg=12.0, propellant_kg=0.0,
        )
        params = MissionParams(
            fcc_compliant_required=False,
            nasa_25yr_compliant_required=False,
        )
        rec = advise_deorbit(state, params)
        assert rec.decision is Decision.NATURAL_DECAY
        assert rec.burn_plan is None

    def test_recommendation_is_pure(self):
        """Same inputs must produce identical outputs (auditability
        requirement for an advisor product)."""
        state = SpacecraftState(
            altitude_km=550.0, inclination_deg=51.6,
            mass_kg=12.0, propellant_kg=1.0, isp_s=220.0,
        )
        params = MissionParams(f107_solar_flux=150.0)
        r1 = advise_deorbit(state, params)
        r2 = advise_deorbit(state, params)
        assert r1.decision == r2.decision
        assert r1.natural_decay.lifetime_days == \
               r2.natural_decay.lifetime_days

    def test_confidence_tier_b(self):
        """King-Hele decay is Tier-B per docs/UNCERTAINTY.md."""
        state = SpacecraftState(
            altitude_km=400.0, inclination_deg=51.6, mass_kg=12.0,
        )
        rec = advise_deorbit(state, MissionParams())
        assert rec.confidence_tier == "B"
