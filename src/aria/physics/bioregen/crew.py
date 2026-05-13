"""Crew metabolic loads — NASA BVAD (Baseline Values and Assumptions Document).

The C-V (crew) compartment of the MELiSSA loop. Drives the demand
side of the closed loop: O2 consumption, CO2 production, water
turnover, food intake, waste output.

All numbers cited per NASA TP-2015-218570 'Baseline Values and
Assumptions Document for Mission and Vehicle Architectures' §4.1
(crew metabolic loads).
"""

from __future__ import annotations

from dataclasses import dataclass


# ── Hard validity bound ────────────────────────────────────────


# MELiSSA pilot plant in Barcelona has been run for ~1 person at
# steady state since 2009, with experiments at higher loadings.
# The largest fully-closed experiment to date is ~3 person-equivalent
# for limited duration. Beyond ~3 persons, the published model
# extrapolates and we mark it explicitly out-of-validation.
MAX_VALIDATED_CREW: int = 3


# ── Per-person metabolic constants ─────────────────────────────


# All mass flows in kg/(person·day). Source: BVAD §4.1 Table 4.1-1.
PER_PERSON_O2_KG_DAY: float = 0.84       # NASA TP-2015-218570 §4.1.1
PER_PERSON_CO2_KG_DAY: float = 1.00      # NASA TP-2015-218570 §4.1.2
PER_PERSON_H2O_DRINK_KG_DAY: float = 2.0   # potable + food prep (BVAD §4.1.3)
PER_PERSON_H2O_HYGIENE_KG_DAY: float = 6.4  # hygiene + laundry + flush (BVAD §4.1.3)
PER_PERSON_H2O_TOTAL_KG_DAY: float = 12.4  # full crew water budget (BVAD §4.1.3)
PER_PERSON_FOOD_DRY_KG_DAY: float = 0.617   # dry food intake (BVAD §4.1.4)
PER_PERSON_URINE_KG_DAY: float = 1.5      # BVAD §4.1.5
PER_PERSON_FECES_KG_DAY: float = 0.123    # BVAD §4.1.5 (wet)
PER_PERSON_RESPIRATION_H2O_KG_DAY: float = 2.28  # exhaled + perspiration

# Nitrogen flux through the crew compartment.
# A 'standard human' eats ~12-14 g N / day in dietary protein;
# excretes ~12-14 g N / day in urea + uric acid (Westerterp-
# Plantenga 2009). MELiSSA uses N = 13 g/day per person.
PER_PERSON_N_KG_DAY: float = 0.013    # MELiSSA Lasseur 2010 Fig 2

# Heat dissipation (relevant for thermal loop).
PER_PERSON_HEAT_W: float = 117.0        # at moderate workload (BVAD §4.1.6)


# ── Crew compartment dataclass ─────────────────────────────────


@dataclass(frozen=True)
class Crew:
    """A bounded crew complement (1 to MAX_VALIDATED_CREW persons).

    Constructing with ``crew_size > MAX_VALIDATED_CREW`` raises
    ``ValueError`` — extrapolating MELiSSA fidelity beyond the
    pilot plant's validated range silently is exactly the kind of
    overclaim HONEST_ASSESSMENT.md demands we stop making.
    """

    crew_size: int

    def __post_init__(self) -> None:
        if not 1 <= self.crew_size <= MAX_VALIDATED_CREW:
            raise ValueError(
                f"crew_size must be 1..{MAX_VALIDATED_CREW} (MELiSSA pilot-plant "
                f"validated range); got {self.crew_size}. Larger systems "
                "exist on paper but are NOT validated against the BLSS "
                "experimental record."
            )

    @property
    def o2_consumed_kg_day(self) -> float:
        return self.crew_size * PER_PERSON_O2_KG_DAY

    @property
    def co2_produced_kg_day(self) -> float:
        return self.crew_size * PER_PERSON_CO2_KG_DAY

    @property
    def water_demand_kg_day(self) -> float:
        return self.crew_size * PER_PERSON_H2O_TOTAL_KG_DAY

    @property
    def drinking_water_demand_kg_day(self) -> float:
        return self.crew_size * PER_PERSON_H2O_DRINK_KG_DAY

    @property
    def food_dry_demand_kg_day(self) -> float:
        return self.crew_size * PER_PERSON_FOOD_DRY_KG_DAY

    @property
    def waste_kg_day(self) -> float:
        """Combined urine + feces (mass terms)."""
        return self.crew_size * (
            PER_PERSON_URINE_KG_DAY + PER_PERSON_FECES_KG_DAY
        )

    @property
    def nitrogen_excreted_kg_day(self) -> float:
        return self.crew_size * PER_PERSON_N_KG_DAY

    @property
    def heat_load_w(self) -> float:
        return self.crew_size * PER_PERSON_HEAT_W
