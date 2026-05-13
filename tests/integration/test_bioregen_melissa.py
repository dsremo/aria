"""MELiSSA-fidelity bioregenerative life-support tests.

Validates the model output against published values:
  * NASA BVAD §4.1 crew metabolic loads
  * MELiSSA pilot-plant performance (Lasseur 2010, Hendrickx 2006)
  * Wheeler 2017 crop-production rates per square metre
"""

from __future__ import annotations

import pytest

from aria.physics.bioregen import (
    Crew,
    CompartmentI,
    CompartmentII,
    CompartmentIII,
    CompartmentIVA,
    CompartmentIVB,
    MELiSSALoop,
    MAX_VALIDATED_CREW,
)
from aria.physics.bioregen.flows import size_c4a_for_o2_closure
from aria.physics.bioregen.crew import (
    PER_PERSON_O2_KG_DAY,
    PER_PERSON_CO2_KG_DAY,
    PER_PERSON_FOOD_DRY_KG_DAY,
)


# ── Crew BVAD round-trip ────────────────────────────────────────


class TestCrewBvad:
    def test_one_person_o2_demand(self) -> None:
        # NASA BVAD §4.1.1: 0.84 kg/(person·day).
        crew = Crew(crew_size=1)
        assert crew.o2_consumed_kg_day == pytest.approx(0.84, rel=0.01)

    def test_three_person_demand_scales(self) -> None:
        crew = Crew(crew_size=3)
        assert crew.o2_consumed_kg_day == pytest.approx(2.52, rel=0.01)
        assert crew.co2_produced_kg_day == pytest.approx(3.0, rel=0.01)

    def test_food_demand_per_person(self) -> None:
        # BVAD §4.1.4: 0.617 kg dry / person·day.
        crew = Crew(crew_size=1)
        assert crew.food_dry_demand_kg_day == pytest.approx(0.617, rel=0.01)

    def test_water_demand_per_person(self) -> None:
        # BVAD §4.1.3: 12.4 kg/(person·day) total.
        crew = Crew(crew_size=2)
        assert crew.water_demand_kg_day == pytest.approx(24.8, rel=0.01)

    def test_zero_crew_rejected(self) -> None:
        with pytest.raises(ValueError, match="crew_size"):
            Crew(crew_size=0)

    def test_oversize_crew_rejected_with_explicit_message(self) -> None:
        # MELiSSA pilot plant validated to 1-3 person.  This is the
        # gate that prevents the old "100 crew" overclaim.
        with pytest.raises(ValueError) as exc_info:
            Crew(crew_size=100)
        msg = str(exc_info.value)
        assert "1-3" in msg or "MELiSSA" in msg or "validated" in msg

    def test_max_validated_crew_constant(self) -> None:
        assert MAX_VALIDATED_CREW == 3

    def test_negative_crew_rejected(self) -> None:
        with pytest.raises(ValueError):
            Crew(crew_size=-1)


# ── Compartment-level sanity ────────────────────────────────────


class TestCompartmentI:
    def test_liquefaction_default_72pct(self) -> None:
        c1 = CompartmentI()
        assert c1.liquefaction_fraction == pytest.approx(0.72, rel=0.01)

    def test_vfa_output_zero_input(self) -> None:
        c1 = CompartmentI()
        assert c1.vfa_output_kg_day(0.0) == 0.0

    def test_vfa_output_proportional(self) -> None:
        c1 = CompartmentI()
        # VFA = 0.5 × 0.72 × input ≈ 0.36 × input.
        assert c1.vfa_output_kg_day(1.0) == pytest.approx(0.36, rel=0.01)


class TestCompartmentII:
    def test_nh4_yield_18pct_of_vfa(self) -> None:
        c2 = CompartmentII()
        assert c2.nh4_output_kg_day(1.0) == pytest.approx(0.18, rel=0.01)

    def test_co2_yield_60pct_of_vfa(self) -> None:
        c2 = CompartmentII()
        assert c2.co2_output_kg_day(1.0) == pytest.approx(0.60, rel=0.01)

    def test_biomass_yield_22pct_of_vfa(self) -> None:
        c2 = CompartmentII()
        assert c2.edible_biomass_kg_day(1.0) == pytest.approx(0.22, rel=0.01)

    def test_yields_sum_to_one(self) -> None:
        # Mass conservation through C-II: NH4 + CO2 + biomass yields
        # should sum to ~1.0 (we ignore water).
        c2 = CompartmentII()
        total = (
            c2.nh4_output_kg_day(1.0)
            + c2.co2_output_kg_day(1.0)
            + c2.edible_biomass_kg_day(1.0)
        )
        assert total == pytest.approx(1.0, rel=0.05)


class TestCompartmentIII:
    def test_default_efficiency_95pct(self) -> None:
        c3 = CompartmentIII()
        assert c3.conversion_efficiency == pytest.approx(0.95, rel=0.01)

    def test_residual_5pct(self) -> None:
        c3 = CompartmentIII()
        assert c3.nh4_residual_kg_day(1.0) == pytest.approx(0.05, rel=0.01)

    def test_nitrate_output(self) -> None:
        c3 = CompartmentIII()
        assert c3.nitrate_output_kg_day(1.0) == pytest.approx(0.95, rel=0.01)


class TestCompartmentIVA:
    def test_zero_area_zero_output(self) -> None:
        c4a = CompartmentIVA(area_m2=0.0)
        assert c4a.o2_output_kg_day == 0.0
        assert c4a.edible_biomass_kg_day == 0.0

    def test_one_m2_o2_50g_per_day(self) -> None:
        # Wheeler 2017: O2 ≈ 50 g/m²·day at canopy steady state.
        c4a = CompartmentIVA(area_m2=1.0)
        assert c4a.o2_output_kg_day == pytest.approx(0.050, rel=0.01)

    def test_negative_area_rejected(self) -> None:
        with pytest.raises(ValueError):
            CompartmentIVA(area_m2=-1.0)

    def test_water_recovery_includes_capture_loss(self) -> None:
        # Transpiration 3.5 kg/m²·day at 95 % capture → 3.325 kg/m²·day.
        c4a = CompartmentIVA(area_m2=1.0)
        assert c4a.potable_water_recovered_kg_day == pytest.approx(
            3.325, rel=0.01,
        )


class TestCompartmentIVB:
    def test_one_m2_spirulina_o2(self) -> None:
        # Cogne 2003 / MELiSSA C-IV-B: ~25 g O2/m²·day at design point.
        c4b = CompartmentIVB(area_m2=1.0)
        assert c4b.o2_output_kg_day == pytest.approx(0.025, rel=0.01)


# ── Sizing helper ───────────────────────────────────────────────


class TestSizingForO2Closure:
    def test_one_person_full_closure_about_17m2(self) -> None:
        # 0.84 / 0.050 = 16.8 m²
        crew = Crew(crew_size=1)
        area = size_c4a_for_o2_closure(crew, target_o2_closure=1.0)
        assert area == pytest.approx(16.8, rel=0.01)

    def test_three_person_full_closure_about_50m2(self) -> None:
        # 3 × 16.8 = 50.4 m²
        crew = Crew(crew_size=3)
        area = size_c4a_for_o2_closure(crew, target_o2_closure=1.0)
        assert area == pytest.approx(50.4, rel=0.01)

    def test_partial_closure_proportional(self) -> None:
        crew = Crew(crew_size=1)
        a_full = size_c4a_for_o2_closure(crew, target_o2_closure=1.0)
        a_half = size_c4a_for_o2_closure(crew, target_o2_closure=0.5)
        assert a_half == pytest.approx(a_full / 2.0, rel=0.001)


# ── Full-loop steady-state behaviour ────────────────────────────


def _melissa_pilot_plant_loop(area_c4a_m2: float = 16.8) -> MELiSSALoop:
    """A 1-person MELiSSA loop sized for full O2 closure on C-IV-A.

    With area_c4a = 16.8 m² and a 1-person crew, the steady-state
    O2 production should match crew demand (~0.84 kg/day) within
    a few percent.
    """
    return MELiSSALoop(
        crew=Crew(crew_size=1),
        c1=CompartmentI(),
        c2=CompartmentII(),
        c3=CompartmentIII(),
        c4a=CompartmentIVA(area_m2=area_c4a_m2),
        c4b=CompartmentIVB(area_m2=2.0),    # small Spirulina supplement
    )


class TestMELiSSALoop:
    def test_solve_returns_balance(self) -> None:
        loop = _melissa_pilot_plant_loop()
        balance = loop.solve()
        assert balance.crew_o2_demand_kg_day == pytest.approx(0.84, rel=0.01)
        assert balance.crew_co2_production_kg_day == pytest.approx(1.0, rel=0.01)

    def test_o2_closure_near_one_at_target_sizing(self) -> None:
        loop = _melissa_pilot_plant_loop(area_c4a_m2=16.8)
        balance = loop.solve()
        # 0.84 kg from C4A + 0.05 from C4B = 0.89 → closure ~1.06.
        assert 1.0 <= balance.o2_closure <= 1.2

    def test_undersized_c4_warns_o2_closure_low(self) -> None:
        # Tiny C-IV: should fail O2 closure and emit a warning.
        loop = MELiSSALoop(
            crew=Crew(crew_size=1),
            c1=CompartmentI(),
            c2=CompartmentII(),
            c3=CompartmentIII(),
            c4a=CompartmentIVA(area_m2=1.0),
            c4b=CompartmentIVB(area_m2=0.5),
        )
        balance = loop.solve()
        assert balance.o2_closure < 0.2
        assert any("O2 closure" in w for w in balance.warnings)
        # Resupply required:
        assert balance.o2_resupply_kg_day > 0.5

    def test_water_closure_at_design_high(self) -> None:
        loop = _melissa_pilot_plant_loop()
        balance = loop.solve()
        # Plant transpiration alone provides much more H2O than the
        # crew drinks; combined with respiration condensate + urine
        # processing, water closure is high.
        assert balance.water_closure >= 0.95

    def test_food_closure_under_one(self) -> None:
        # Even at full O2 closure, a 16.8 m² + 2 m² C-IV produces:
        #   C-IV-A: 16.8 × 0.030 = 0.504 kg dry food/day
        #   C-IV-B: 2.0  × 0.010 = 0.020 kg dry food/day
        #   C-II:  ~ 0.024 kg single-cell protein/day
        # Crew demand: 0.617 kg/day → food closure ~0.89.
        loop = _melissa_pilot_plant_loop()
        balance = loop.solve()
        assert 0.5 <= balance.food_closure < 1.0

    def test_co2_dump_zero_when_oversized(self) -> None:
        # 30 m² C-IV-A absorbs much more CO2 than 1-person produces.
        loop = MELiSSALoop(
            crew=Crew(crew_size=1),
            c1=CompartmentI(),
            c2=CompartmentII(),
            c3=CompartmentIII(),
            c4a=CompartmentIVA(area_m2=30.0),
            c4b=CompartmentIVB(area_m2=2.0),
        )
        balance = loop.solve()
        # CO2 closure > 1 means the system over-absorbs, CO2 dump ~0.
        assert balance.co2_closure > 1.5
        assert balance.co2_dump_kg_day == 0.0
        # Should warn about CO2 starvation in C-IV.
        assert any("over-sized" in w.lower() or "co2 closure" in w.lower()
                   for w in balance.warnings)

    def test_3_person_loop_scales_demand(self) -> None:
        loop = MELiSSALoop(
            crew=Crew(crew_size=3),
            c1=CompartmentI(),
            c2=CompartmentII(),
            c3=CompartmentIII(),
            c4a=CompartmentIVA(area_m2=50.0),
            c4b=CompartmentIVB(area_m2=5.0),
        )
        balance = loop.solve()
        assert balance.crew_o2_demand_kg_day == pytest.approx(2.52, rel=0.01)
        assert 0.95 <= balance.o2_closure <= 1.3

    def test_nitrogen_closure_within_range(self) -> None:
        loop = _melissa_pilot_plant_loop()
        balance = loop.solve()
        # N closure depends on whether plant N uptake matches the
        # NO3 produced by C-III. Should be a reasonable fraction.
        assert 0.0 <= balance.nitrogen_closure <= 2.0

    def test_warnings_emitted_as_tuple(self) -> None:
        loop = _melissa_pilot_plant_loop()
        balance = loop.solve()
        assert isinstance(balance.warnings, tuple)


# ── Honest-bound enforcement ────────────────────────────────────


class TestHonestBoundEnforcement:
    """The 100-crew overclaim was retired in HONEST_ASSESSMENT.md.
    These tests pin that the new model **structurally rejects** any
    attempt to revive it."""

    def test_construction_with_4_person_rejected(self) -> None:
        with pytest.raises(ValueError, match="MELiSSA|validated|1-3"):
            Crew(crew_size=4)

    def test_construction_with_10_person_rejected(self) -> None:
        with pytest.raises(ValueError):
            Crew(crew_size=10)

    def test_construction_with_100_person_rejected(self) -> None:
        # The exact value from the historical overclaim.
        with pytest.raises(ValueError):
            Crew(crew_size=100)

    def test_max_validated_crew_immutable_constant(self) -> None:
        # If someone changes this in the future they break the test
        # AND have to update the citation chain.
        from aria.physics.bioregen.crew import MAX_VALIDATED_CREW
        assert MAX_VALIDATED_CREW == 3
