"""Steady-state mass-balance solver for the MELiSSA loop.

Couples the C-I → C-II → C-III → C-IV-A/B → C-V flows and reports
loop closure for O2, CO2, water, and nitrogen, plus how much
resupply / dump each species needs at the chosen sizing.

This is a STEADY-STATE solver only — it gives the long-term average
mass balance assuming each compartment is at its design operating
point. Real MELiSSA experiments show that startup transients,
biomass-population shifts, and pH drift make achieving steady state
non-trivial. Treat the output as the *target* the operator is trying
to converge on, not a guarantee.

Closure metrics defined (each is a ratio in [0, 1]):

  O2 closure  = O2 produced by C-IV / O2 consumed by crew
  CO2 closure = CO2 absorbed by C-IV+CII / CO2 produced by crew
  H2O closure = H2O recovered (transpiration + urine) / crew demand
  N closure   = N cycled (crew → C-I → C-II → C-III → C-IV) /
                N excreted by crew

A closure of 1.0 means perfect steady-state recycling.  A closure
> 1.0 means the system over-produces and the surplus must be vented
or stored.  A closure < 1.0 means resupply is required from external
stores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from aria.physics.bioregen.compartments import (
    CompartmentI,
    CompartmentII,
    CompartmentIII,
    CompartmentIVA,
    CompartmentIVB,
)
from aria.physics.bioregen.crew import (
    Crew,
    PER_PERSON_FOOD_DRY_KG_DAY,
    PER_PERSON_RESPIRATION_H2O_KG_DAY,
)


@dataclass(frozen=True)
class LoopBalance:
    """Steady-state mass balance for the entire MELiSSA loop."""

    # Crew demand
    crew_o2_demand_kg_day: float
    crew_co2_production_kg_day: float
    crew_water_demand_kg_day: float
    crew_food_demand_kg_day: float

    # Compartment-IV production
    c4_o2_produced_kg_day: float
    c4_co2_uptake_kg_day: float
    c4_edible_biomass_kg_day: float
    c4_water_recovered_kg_day: float

    # Loop closure ratios (0 .. >1)
    o2_closure: float
    co2_closure: float
    food_closure: float
    water_closure: float
    nitrogen_closure: float

    # Resupply requirements (positive => need to ship up; negative
    # => need to vent / dump)
    o2_resupply_kg_day: float
    co2_dump_kg_day: float
    food_resupply_kg_day: float
    water_resupply_kg_day: float

    # Diagnostic warnings (e.g. C-IV undersized, plant area
    # insufficient for crew O2, etc.).
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MELiSSALoop:
    """Full MELiSSA closed-loop life-support model.

    Construct with a crew + compartments, call ``solve()`` to get a
    ``LoopBalance``. The loop is sized by the operator — we don't
    auto-size the C-IV plant area to crew demand because real
    spacecraft engineering does that as a design decision, not
    a runtime computation.
    """

    crew: Crew
    c1: CompartmentI
    c2: CompartmentII
    c3: CompartmentIII
    c4a: CompartmentIVA
    c4b: CompartmentIVB

    def solve(self) -> LoopBalance:
        warnings: list[str] = []

        # ── C-V outputs ─────────────────────────────────────────
        crew_o2_demand = self.crew.o2_consumed_kg_day
        crew_co2 = self.crew.co2_produced_kg_day
        crew_water_demand = self.crew.water_demand_kg_day
        crew_food_demand = self.crew.crew_size * PER_PERSON_FOOD_DRY_KG_DAY
        crew_n_excreted = self.crew.nitrogen_excreted_kg_day

        # Crew waste flows into C-I as organic dry matter. BVAD §4.1.5
        # gives ~0.1 kg/day dry organic waste per person; food residue
        # adds another ~0.05 kg/day per person.
        organic_input_dry_kg_day = self.crew.crew_size * 0.15

        # ── C-I → VFAs ─────────────────────────────────────────
        vfa_kg_day = self.c1.vfa_output_kg_day(organic_input_dry_kg_day)

        # ── C-II → NH4 ─────────────────────────────────────────
        nh4_from_c2 = self.c2.nh4_output_kg_day(vfa_kg_day)
        c2_co2 = self.c2.co2_output_kg_day(vfa_kg_day)
        c2_biomass = self.c2.edible_biomass_kg_day(vfa_kg_day)

        # The crew also excretes nitrogen directly via urine (urea);
        # urea is hydrolysed in C-I to NH4 with high efficiency.
        # We treat this as merging into the C-II output stream at
        # ~95 % conversion (urease is essentially universal).
        nh4_from_urea = crew_n_excreted * 0.95
        nh4_total = nh4_from_c2 + nh4_from_urea

        # ── C-III → NO3 ────────────────────────────────────────
        no3_kg_day = self.c3.nitrate_output_kg_day(nh4_total)

        # ── C-IV-A + C-IV-B uptake ─────────────────────────────
        c4_o2_produced = (
            self.c4a.o2_output_kg_day + self.c4b.o2_output_kg_day
        )
        c4_co2_uptake = (
            self.c4a.co2_uptake_kg_day + self.c4b.co2_uptake_kg_day
        )
        c4_food = (
            self.c4a.edible_biomass_kg_day
            + self.c4b.edible_biomass_kg_day
        )
        c4_no3_uptake = (
            self.c4a.no3_uptake_kg_day + self.c4b.no3_uptake_kg_day
        )

        # ── Water recovered ────────────────────────────────────
        # Plant transpiration + crew respiration condensate + urine
        # processing water (UPA + WPA equivalents). The plant
        # transpiration is the largest term in MELiSSA's design.
        h2o_plant_recovered = self.c4a.potable_water_recovered_kg_day
        h2o_crew_respiration = (
            self.crew.crew_size * PER_PERSON_RESPIRATION_H2O_KG_DAY
        )
        # Urine processing assumed 90 % water-recovery (typical UPA
        # + WPA cascade per BVAD §4.2.2).
        h2o_urine_recovery = 0.90 * (
            self.crew.crew_size * 1.5  # urine kg/day per person
        )
        h2o_recovered = (
            h2o_plant_recovered + h2o_crew_respiration + h2o_urine_recovery
        )

        # ── Closure ratios ─────────────────────────────────────
        o2_closure = (
            c4_o2_produced / crew_o2_demand if crew_o2_demand > 0 else 0.0
        )
        co2_closure = (
            c4_co2_uptake / crew_co2 if crew_co2 > 0 else 0.0
        )
        food_closure = (
            (c4_food + c2_biomass) / crew_food_demand
            if crew_food_demand > 0 else 0.0
        )
        water_closure = (
            h2o_recovered / crew_water_demand
            if crew_water_demand > 0 else 0.0
        )
        # Nitrogen cycle closure: how much of crew-excreted N gets
        # back into edible biomass via NO3 uptake.
        nitrogen_closure = (
            min(c4_no3_uptake, no3_kg_day) / crew_n_excreted
            if crew_n_excreted > 0 else 0.0
        )

        # ── Resupply quantities (positive => need to ship) ─────
        o2_resupply_kg_day = max(0.0, crew_o2_demand - c4_o2_produced)
        co2_dump_kg_day = max(0.0, crew_co2 - c4_co2_uptake)
        food_resupply_kg_day = max(
            0.0, crew_food_demand - (c4_food + c2_biomass),
        )
        water_resupply_kg_day = max(0.0, crew_water_demand - h2o_recovered)

        # ── Diagnostic warnings ────────────────────────────────
        if o2_closure < 0.5:
            warnings.append(
                f"C-IV plant area insufficient — O2 closure only "
                f"{o2_closure:.2f}; need much more A_C4A or A_C4B"
            )
        if food_closure < 0.20:
            warnings.append(
                f"food closure low ({food_closure:.2f}); resupply "
                "is the dominant supply path"
            )
        if water_closure < 0.85:
            warnings.append(
                f"water closure {water_closure:.2f}; design target is >= 0.95"
            )
        if c4_co2_uptake > crew_co2 * 1.3:
            warnings.append(
                f"C-IV is over-sized for CO2 uptake (closure {co2_closure:.2f}); "
                "C-IV will starve of CO2 unless supplemental CO2 is supplied"
            )

        return LoopBalance(
            crew_o2_demand_kg_day=crew_o2_demand,
            crew_co2_production_kg_day=crew_co2,
            crew_water_demand_kg_day=crew_water_demand,
            crew_food_demand_kg_day=crew_food_demand,
            c4_o2_produced_kg_day=c4_o2_produced,
            c4_co2_uptake_kg_day=c4_co2_uptake,
            c4_edible_biomass_kg_day=c4_food,
            c4_water_recovered_kg_day=h2o_recovered,
            o2_closure=o2_closure,
            co2_closure=co2_closure,
            food_closure=food_closure,
            water_closure=water_closure,
            nitrogen_closure=nitrogen_closure,
            o2_resupply_kg_day=o2_resupply_kg_day,
            co2_dump_kg_day=co2_dump_kg_day,
            food_resupply_kg_day=food_resupply_kg_day,
            water_resupply_kg_day=water_resupply_kg_day,
            warnings=tuple(warnings),
        )


# ── Convenience: size C-IV-A area for a target O2 closure ──────


def size_c4a_for_o2_closure(
    crew: Crew,
    target_o2_closure: float = 1.0,
    biomass_g_m2_day: float = 30.0,
    o2_g_m2_day: float = 50.0,
) -> float:
    """Return the C-IV-A area in m² required to hit the target O2
    closure for the given crew, holding plant productivity at the
    documented MELiSSA values.

    For a 1-person crew at full closure: 0.84 kg O2/day ÷ 0.050
    kg/m²·day ≈ 16.8 m². MELiSSA pilot plant has ~5 m² but only
    targets partial closure; the 16.8 m² is the analytical full-
    closure number.
    """
    if target_o2_closure < 0:
        raise ValueError(f"target_o2_closure must be >= 0, got {target_o2_closure}")
    crew_o2_kg_day = crew.o2_consumed_kg_day
    o2_per_m2_kg_day = o2_g_m2_day / 1000.0
    return target_o2_closure * crew_o2_kg_day / o2_per_m2_kg_day
