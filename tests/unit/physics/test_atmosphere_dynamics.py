"""Tests for ECLSS habitat atmosphere mass-balance dynamics.

Validates:
1.  AtmosphereState.nominal() initialises O₂ fraction ≈ 20.9%.
2.  AtmosphereState.nominal() initialises CO₂ ≈ 400 ppm.
3.  CDRA efficiency decreases with age (Knox 2016).
4.  CDRA efficiency at age=0 equals nominal (0.98).
5.  Sabatier efficiency decreases with catalyst age (Abney 2011).
6.  Sabatier efficiency at age=0 equals nominal (0.95).
7.  OGA rate decreases with cell age (Takahashi 2019).
8.  OGA rate at age=0 equals nominal × crew_size.
9.  cabin_co2_ppm() returns correct ppm for known state.
10. cabin_o2_fraction() returns correct fraction for known state.
11. step_atmosphere: CO₂ rises when CDRA is offline.
12. step_atmosphere: CO₂ stays stable when CDRA is at full efficiency.
13. step_atmosphere: O₂ depletes when OGA is offline.
14. step_atmosphere: O₂ stays stable when OGA is at full efficiency.
15. step_atmosphere: trace CO accumulates when TCCS offline.
16. step_atmosphere: trace CO stays near zero when TCCS online.
17. co2_incapacitation_risk(): 0 at nominal, >0 at elevated, 1.0 at IDLH.
18. o2_hypoxia_risk(): 0 at nominal, >0 below 15.5%, 1.0 below 15.5%.
19. step_atmosphere: age counters increment by dt_days/365.25.
20. step_atmosphere: dt_days=0 is a no-op.
21. Hull leak slowly depletes total atmosphere mass.
22. 30-day simulation: CO₂ stays below OSHA PEL with all ECLSS online.
"""

from __future__ import annotations

import pytest

from aria.physics.life_support.atmosphere_dynamics import (
    CABIN_O2_FRACTION_NOMINAL,
    CDRA_NOMINAL_EFFICIENCY,
    CO2_PPM_NIOSH_IDLH,
    CO2_PPM_OSHA_PEL,
    O2_FRACTION_HYPOXIA_LOW,
    OGA_NOMINAL_RATE_KG_DAY_PER_CREW,
    SABATIER_NOMINAL_EFFICIENCY,
    AtmosphereState,
    EclssConfig,
    cabin_co2_ppm,
    cabin_o2_fraction,
    cdra_scrubbing_efficiency,
    co2_incapacitation_risk,
    o2_hypoxia_risk,
    oga_o2_rate_kg_day,
    sabatier_co2_removal_fraction,
    step_atmosphere,
)


def _nominal_state(crew: int = 8) -> AtmosphereState:
    return AtmosphereState.nominal(cabin_volume_m3=2400.0, crew=crew)


def _nominal_config(crew: int = 8) -> EclssConfig:
    return EclssConfig(crew_size=crew)


# ── Initialisation ────────────────────────────────────────────────────────────

class TestAtmosphereStateInit:

    def test_o2_fraction_near_nominal(self):
        s = _nominal_state()
        assert abs(cabin_o2_fraction(s) - CABIN_O2_FRACTION_NOMINAL) < 0.005

    def test_co2_ppm_near_400(self):
        s = _nominal_state()
        ppm = cabin_co2_ppm(s)
        assert 300 < ppm < 500, f"CO₂ ppm = {ppm:.0f}, expected ~400"


# ── Component efficiency ──────────────────────────────────────────────────────

class TestCdraEfficiency:

    def test_nominal_efficiency_at_zero_age(self):
        assert abs(cdra_scrubbing_efficiency(0.0) - CDRA_NOMINAL_EFFICIENCY) < 1e-9

    def test_efficiency_decreases_with_age(self):
        e0 = cdra_scrubbing_efficiency(0.0)
        e5 = cdra_scrubbing_efficiency(5.0)
        e10 = cdra_scrubbing_efficiency(10.0)
        assert e5 < e0
        assert e10 < e5

    def test_efficiency_nonnegative(self):
        assert cdra_scrubbing_efficiency(100.0) >= 0.0

    def test_efficiency_at_one_tau(self):
        from aria.physics.life_support.atmosphere_dynamics import CDRA_DEGRADATION_TAU_YEARS
        eta = cdra_scrubbing_efficiency(CDRA_DEGRADATION_TAU_YEARS)
        # At one e-folding time, efficiency should be η₀ / e
        expected = CDRA_NOMINAL_EFFICIENCY / 2.71828
        assert abs(eta - expected) < 0.002


class TestSabatierEfficiency:

    def test_nominal_efficiency_at_zero_age(self):
        assert abs(sabatier_co2_removal_fraction(0.0) - SABATIER_NOMINAL_EFFICIENCY) < 1e-9

    def test_efficiency_decreases_with_age(self):
        e0 = sabatier_co2_removal_fraction(0.0)
        e5 = sabatier_co2_removal_fraction(5.0)
        assert e5 < e0

    def test_efficiency_nonnegative(self):
        assert sabatier_co2_removal_fraction(100.0) >= 0.0

    def test_converges_to_min(self):
        # Long-aged catalyst converges to η₀ × (1 − A)
        from aria.physics.life_support.atmosphere_dynamics import SABATIER_DEGRADE_FRACTION
        e_inf = sabatier_co2_removal_fraction(200.0)
        expected = SABATIER_NOMINAL_EFFICIENCY * (1.0 - SABATIER_DEGRADE_FRACTION)
        assert abs(e_inf - expected) < 0.01


class TestOgaRate:

    def test_nominal_rate_at_zero_age(self):
        rate = oga_o2_rate_kg_day(0.0, crew_size=8)
        expected = OGA_NOMINAL_RATE_KG_DAY_PER_CREW * 8
        assert abs(rate - expected) < 1e-9

    def test_rate_decreases_with_age(self):
        r0 = oga_o2_rate_kg_day(0.0, 8)
        r10 = oga_o2_rate_kg_day(10.0, 8)
        assert r10 < r0

    def test_rate_scales_with_crew(self):
        r8 = oga_o2_rate_kg_day(0.0, 8)
        r4 = oga_o2_rate_kg_day(0.0, 4)
        assert abs(r8 / r4 - 2.0) < 1e-9

    def test_rate_nonnegative_at_very_old_age(self):
        assert oga_o2_rate_kg_day(1000.0, 8) >= 0.0


# ── Derived quantities ────────────────────────────────────────────────────────

class TestCabinMetrics:

    def test_co2_ppm_empty_state(self):
        s = AtmosphereState(co2_kg=0.0, o2_kg=0.0, n2_kg=0.0)
        assert cabin_co2_ppm(s) == 0.0
        assert cabin_o2_fraction(s) == 0.0

    def test_co2_ppm_pure_co2(self):
        # 1 kg CO₂, no other gas → 1e6 ppm
        s = AtmosphereState(co2_kg=1.0, o2_kg=0.0, n2_kg=0.0)
        assert abs(cabin_co2_ppm(s) - 1e6) < 1.0

    def test_o2_fraction_pure_o2(self):
        s = AtmosphereState(co2_kg=0.0, o2_kg=1.0, n2_kg=0.0)
        assert abs(cabin_o2_fraction(s) - 1.0) < 1e-6


# ── step_atmosphere ───────────────────────────────────────────────────────────

class TestStepAtmosphere:

    def test_noop_at_zero_dt(self):
        s = _nominal_state()
        co2_before = s.co2_kg
        step_atmosphere(s, _nominal_config(), dt_days=0.0)
        assert s.co2_kg == co2_before

    def test_co2_rises_cdra_offline(self):
        s = _nominal_state()
        cfg = _nominal_config()
        cfg.cdra_online = False
        cfg.sabatier_online = False
        co2_before = s.co2_kg
        step_atmosphere(s, cfg, dt_days=1.0)
        assert s.co2_kg > co2_before

    def test_co2_stable_cdra_fully_on(self):
        """With CDRA at full efficiency, CO₂ should not accumulate."""
        s = _nominal_state()
        cfg = _nominal_config()
        cfg.cdra_online = True
        cfg.sabatier_online = True
        # Run 10 days
        for _ in range(10):
            step_atmosphere(s, cfg, dt_days=1.0)
        ppm = cabin_co2_ppm(s)
        assert ppm < CO2_PPM_OSHA_PEL, f"CO₂ = {ppm:.0f} ppm exceeds PEL"

    def test_o2_depletes_oga_offline(self):
        s = _nominal_state()
        cfg = _nominal_config()
        cfg.oga_online = False
        o2_before = s.o2_kg
        for _ in range(7):
            step_atmosphere(s, cfg, dt_days=1.0)
        assert s.o2_kg < o2_before

    def test_o2_stable_oga_online(self):
        s = _nominal_state()
        cfg = _nominal_config()
        o2_initial = s.o2_kg
        for _ in range(30):
            step_atmosphere(s, cfg, dt_days=1.0)
        o2_frac = cabin_o2_fraction(s)
        assert o2_frac > O2_FRACTION_HYPOXIA_LOW

    def test_trace_co_accumulates_tccs_offline(self):
        s = _nominal_state()
        cfg = _nominal_config()
        cfg.tccs_online = False
        step_atmosphere(s, cfg, dt_days=30.0)
        assert s.co_kg > 0.0

    def test_trace_co_near_zero_tccs_online(self):
        s = _nominal_state()
        cfg = _nominal_config()
        s.co_kg = 0.0
        for _ in range(30):
            step_atmosphere(s, cfg, dt_days=1.0)
        # TCCS removes 90%, residual = 10% of 30 days production
        from aria.physics.life_support.atmosphere_dynamics import CREW_CO_KG_DAY, TCCS_CO_REMOVAL_EFFICIENCY
        total_prod = CREW_CO_KG_DAY * cfg.crew_size * 30.0
        max_residual = total_prod * (1.0 - TCCS_CO_REMOVAL_EFFICIENCY) * 2
        assert s.co_kg < max_residual

    def test_age_counters_increment(self):
        s = _nominal_state()
        cfg = _nominal_config()
        step_atmosphere(s, cfg, dt_days=365.25)
        assert abs(s.cdra_age_years - 1.0) < 0.01
        assert abs(s.sabatier_age_years - 1.0) < 0.01
        assert abs(s.oga_age_years - 1.0) < 0.01

    def test_hull_leak_depletes_total_mass(self):
        s = _nominal_state()
        cfg = _nominal_config()
        cfg.hull_leak_kg_day = 0.5  # elevated leak
        total_before = s.o2_kg + s.n2_kg
        for _ in range(30):
            step_atmosphere(s, cfg, dt_days=1.0)
        total_after = s.o2_kg + s.n2_kg
        assert total_after < total_before

    def test_returns_same_state_object(self):
        s = _nominal_state()
        returned = step_atmosphere(s, _nominal_config(), dt_days=1.0)
        assert returned is s


# ── Risk functions ────────────────────────────────────────────────────────────

class TestCo2IncapacitationRisk:

    def test_zero_at_nominal(self):
        assert co2_incapacitation_risk(400.0) == 0.0

    def test_zero_below_cognitive_threshold(self):
        assert co2_incapacitation_risk(999.0) == 0.0

    def test_nonzero_above_cognitive_threshold(self):
        assert co2_incapacitation_risk(2000.0) > 0.0

    def test_increases_with_ppm(self):
        r1 = co2_incapacitation_risk(2000.0)
        r2 = co2_incapacitation_risk(10000.0)
        r3 = co2_incapacitation_risk(30000.0)
        assert r2 > r1
        assert r3 > r2

    def test_one_at_idlh(self):
        assert co2_incapacitation_risk(CO2_PPM_NIOSH_IDLH + 1000) == 1.0

    def test_bounded_to_one(self):
        assert co2_incapacitation_risk(1e9) == 1.0


class TestO2HypoxiaRisk:

    def test_zero_at_nominal(self):
        assert o2_hypoxia_risk(CABIN_O2_FRACTION_NOMINAL) == 0.0

    def test_zero_above_nominal(self):
        assert o2_hypoxia_risk(0.25) == 0.0

    def test_nonzero_below_nominal(self):
        assert o2_hypoxia_risk(0.18) > 0.0

    def test_one_below_hypoxia_threshold(self):
        assert o2_hypoxia_risk(O2_FRACTION_HYPOXIA_LOW - 0.01) == 1.0

    def test_increases_as_o2_decreases(self):
        r1 = o2_hypoxia_risk(0.19)
        r2 = o2_hypoxia_risk(0.17)
        assert r2 > r1


# ── 30-day integration scenario ───────────────────────────────────────────────

class TestScenarios:

    def test_nominal_30day_co2_below_osha_pel(self):
        """All ECLSS online, 8 crew, 30 days — CO₂ must stay below OSHA PEL."""
        s = _nominal_state(crew=8)
        cfg = _nominal_config(crew=8)
        for _ in range(30):
            step_atmosphere(s, cfg, dt_days=1.0)
        ppm = cabin_co2_ppm(s)
        assert ppm < CO2_PPM_OSHA_PEL, f"CO₂ = {ppm:.0f} ppm exceeds OSHA PEL after 30 days"

    def test_cdra_failure_co2_spikes(self):
        """CDRA failure: CO₂ should exceed 1000 ppm within 7 days."""
        s = _nominal_state(crew=8)
        cfg = _nominal_config(crew=8)
        cfg.cdra_online = False
        cfg.sabatier_online = False
        for _ in range(7):
            step_atmosphere(s, cfg, dt_days=1.0)
        ppm = cabin_co2_ppm(s)
        assert ppm > 1000.0, f"Expected CO₂ > 1000 ppm after CDRA failure, got {ppm:.0f}"

    def test_oga_failure_o2_depletes(self):
        """OGA failure: O₂ fraction drops detectably in 7 days."""
        s = _nominal_state(crew=8)
        cfg = _nominal_config(crew=8)
        cfg.oga_online = False
        o2_init = cabin_o2_fraction(s)
        for _ in range(7):
            step_atmosphere(s, cfg, dt_days=1.0)
        assert cabin_o2_fraction(s) < o2_init
