from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


EDEN_ISS_MISSION_DURATION_DAYS = 281
EDEN_ISS_FRESH_PRODUCE_TOTAL_KG = 268.0
EDEN_ISS_AVG_PRODUCE_KG_PER_DAY = 0.95
EDEN_ISS_O2_PRODUCTION_AVG_KG_PER_DAY = 1.83
EDEN_ISS_CO2_UPTAKE_AVG_KG_PER_DAY = 2.68
EDEN_ISS_WATER_TRANSPIRATION_AVG_KG_PER_DAY = 17.0
EDEN_ISS_GROWTH_AREA_M2 = 12.5
EDEN_ISS_LED_DLI_MOL_M2_DAY = 17.0


EDEN_ISS_CITATIONS = (
    "Zabel et al. (2020) Open Agriculture 5: 1-15 — EDEN ISS Antarctica greenhouse mission summary",
    "Schubert et al. (2018) ICES-2018-180 — EDEN ISS first-year operations",
    "Bamsey et al. (2020) ICES-2020-208 — EDEN ISS gas exchange + water balance",
    "Romberg et al. (2020) ICES-2020-258 — EDEN ISS LED + nutrient solution data",
    "DLR EDEN ISS final report (2019), public release",
)


@dataclass(frozen=True)
class EdenIssBaseline:
    duration_days: float = EDEN_ISS_MISSION_DURATION_DAYS
    produce_total_kg: float = EDEN_ISS_FRESH_PRODUCE_TOTAL_KG
    produce_avg_kg_day: float = EDEN_ISS_AVG_PRODUCE_KG_PER_DAY
    o2_avg_kg_day: float = EDEN_ISS_O2_PRODUCTION_AVG_KG_PER_DAY
    co2_avg_kg_day: float = EDEN_ISS_CO2_UPTAKE_AVG_KG_PER_DAY
    water_transp_avg_kg_day: float = EDEN_ISS_WATER_TRANSPIRATION_AVG_KG_PER_DAY
    growth_area_m2: float = EDEN_ISS_GROWTH_AREA_M2
    led_dli_mol_m2_day: float = EDEN_ISS_LED_DLI_MOL_M2_DAY


@dataclass(frozen=True)
class EdenIssDelta:
    parameter: str
    measured_value: float
    published_value: float
    relative_error: float
    within_tolerance: bool
    units: str = ""

    @property
    def relative_error_pct(self) -> float:
        return self.relative_error * 100.0


@dataclass(frozen=True)
class EdenIssReport:
    deltas: tuple[EdenIssDelta, ...]
    overall_within_tolerance: bool
    notes: str

    def as_dict(self) -> dict:
        return {
            "overall_within_tolerance": self.overall_within_tolerance,
            "notes": self.notes,
            "deltas": [
                {
                    "parameter": delta.parameter,
                    "measured": delta.measured_value,
                    "published": delta.published_value,
                    "relative_error_pct": round(delta.relative_error_pct, 2),
                    "within_tolerance": delta.within_tolerance,
                    "units": delta.units,
                }
                for delta in self.deltas
            ],
        }


def _delta(
    parameter: str, measured: float, published: float,
    tolerance: float, units: str,
) -> EdenIssDelta:
    if published == 0:
        relative_error = float("inf") if measured != 0 else 0.0
    else:
        relative_error = abs(measured - published) / abs(published)
    return EdenIssDelta(
        parameter=parameter,
        measured_value=measured,
        published_value=published,
        relative_error=relative_error,
        within_tolerance=relative_error <= tolerance,
        units=units,
    )


@dataclass
class GreenhouseProduceModel:
    growth_area_m2: float = 12.5
    led_dli_mol_m2_day: float = 17.0
    produce_yield_g_mol_par: float = 4.47
    transpiration_kg_per_kg_produce: float = 17.9
    co2_uptake_kg_per_kg_produce: float = 2.82
    o2_production_kg_per_kg_produce: float = 1.93

    def step_day(self) -> dict[str, float]:
        photons_mol_day = self.led_dli_mol_m2_day * self.growth_area_m2
        produce_kg_day = (photons_mol_day * self.produce_yield_g_mol_par) / 1000.0
        return {
            "produce_kg_day": produce_kg_day,
            "co2_uptake_kg_day": produce_kg_day * self.co2_uptake_kg_per_kg_produce,
            "o2_production_kg_day": produce_kg_day * self.o2_production_kg_per_kg_produce,
            "water_transp_kg_day": produce_kg_day * self.transpiration_kg_per_kg_produce,
        }

    def integrate(self, *, duration_days: int) -> dict[str, float]:
        per_day = self.step_day()
        return {
            "duration_days": float(duration_days),
            "produce_total_kg": per_day["produce_kg_day"] * duration_days,
            "co2_uptake_total_kg": per_day["co2_uptake_kg_day"] * duration_days,
            "o2_production_total_kg": per_day["o2_production_kg_day"] * duration_days,
            "water_transp_total_kg": per_day["water_transp_kg_day"] * duration_days,
            "produce_avg_kg_day": per_day["produce_kg_day"],
            "co2_avg_kg_day": per_day["co2_uptake_kg_day"],
            "o2_avg_kg_day": per_day["o2_production_kg_day"],
            "water_avg_kg_day": per_day["water_transp_kg_day"],
        }


def validate_against_eden_iss(
    integrated: dict[str, float],
    *,
    baseline: Optional[EdenIssBaseline] = None,
    tolerance_pct: float = 25.0,
) -> EdenIssReport:
    base = baseline or EdenIssBaseline()
    tol = tolerance_pct / 100.0
    deltas = (
        _delta("produce_avg", integrated["produce_avg_kg_day"], base.produce_avg_kg_day, tol, "kg/day"),
        _delta("co2_uptake_avg", integrated["co2_avg_kg_day"], base.co2_avg_kg_day, tol, "kg/day"),
        _delta("o2_production_avg", integrated["o2_avg_kg_day"], base.o2_avg_kg_day, tol, "kg/day"),
        _delta("water_transpiration_avg", integrated["water_avg_kg_day"], base.water_transp_avg_kg_day, tol, "kg/day"),
        _delta("produce_total_280d", integrated["produce_total_kg"], base.produce_total_kg, tol, "kg"),
    )
    overall = all(delta.within_tolerance for delta in deltas)
    notes = (
        "EDEN ISS Antarctica greenhouse 281-day mission baseline (2018, "
        "DLR + 14 partners). Tolerance ±25 % is a sanity-check band — "
        "EDEN ISS produce yields varied 0.5–1.5 kg/day across crops "
        "(cucumber, lettuce, tomato, herbs) and growth area was "
        "reconfigured mid-mission. Citations: " + "; ".join(EDEN_ISS_CITATIONS)
    )
    return EdenIssReport(
        deltas=deltas, overall_within_tolerance=overall, notes=notes,
    )
