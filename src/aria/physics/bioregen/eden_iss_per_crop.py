from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass(frozen=True)
class CropProfile:
    name: str
    yield_g_mol_par: float
    transpiration_kg_per_kg: float
    co2_uptake_kg_per_kg: float
    o2_production_kg_per_kg: float
    germination_days: int
    harvest_days: int
    growth_area_share: float
    citation: str = ""


CROP_PROFILES: tuple[CropProfile, ...] = (
    CropProfile(
        name="lettuce",
        yield_g_mol_par=4.6,
        transpiration_kg_per_kg=18.5,
        co2_uptake_kg_per_kg=2.85,
        o2_production_kg_per_kg=1.92,
        germination_days=4,
        harvest_days=28,
        growth_area_share=0.30,
        citation="Zabel et al. (2020) Open Agriculture 5; Romberg ICES-2020-258",
    ),
    CropProfile(
        name="cucumber",
        yield_g_mol_par=5.2,
        transpiration_kg_per_kg=21.0,
        co2_uptake_kg_per_kg=2.95,
        o2_production_kg_per_kg=1.98,
        germination_days=5,
        harvest_days=42,
        growth_area_share=0.20,
        citation="Bamsey ICES-2020-208",
    ),
    CropProfile(
        name="tomato_dwarf",
        yield_g_mol_par=4.1,
        transpiration_kg_per_kg=19.0,
        co2_uptake_kg_per_kg=2.70,
        o2_production_kg_per_kg=1.82,
        germination_days=7,
        harvest_days=70,
        growth_area_share=0.20,
        citation="Schubert ICES-2018-180",
    ),
    CropProfile(
        name="herbs_basil",
        yield_g_mol_par=3.8,
        transpiration_kg_per_kg=15.5,
        co2_uptake_kg_per_kg=2.55,
        o2_production_kg_per_kg=1.74,
        germination_days=5,
        harvest_days=35,
        growth_area_share=0.10,
        citation="Schubert ICES-2018-180",
    ),
    CropProfile(
        name="leafy_mixed",
        yield_g_mol_par=4.3,
        transpiration_kg_per_kg=17.0,
        co2_uptake_kg_per_kg=2.78,
        o2_production_kg_per_kg=1.89,
        germination_days=4,
        harvest_days=30,
        growth_area_share=0.10,
        citation="Romberg ICES-2020-258",
    ),
    CropProfile(
        name="microgreens",
        yield_g_mol_par=5.6,
        transpiration_kg_per_kg=14.0,
        co2_uptake_kg_per_kg=2.40,
        o2_production_kg_per_kg=1.68,
        germination_days=3,
        harvest_days=14,
        growth_area_share=0.10,
        citation="DLR EDEN ISS final report (2019)",
    ),
)


MICROGRAVITY_TRANSPIRATION_MULTIPLIER = 0.78
MICROGRAVITY_GAS_EXCHANGE_MULTIPLIER = 0.92


@dataclass
class CropTimeSeriesPoint:
    sol: int
    crop: str
    growing_area_m2: float
    produce_kg_day: float
    o2_kg_day: float
    co2_kg_day: float
    water_kg_day: float


@dataclass
class CropProductionRun:
    points: list[CropTimeSeriesPoint] = field(default_factory=list)

    def total_produce_kg(self) -> float:
        return sum(point.produce_kg_day for point in self.points)

    def total_o2_kg(self) -> float:
        return sum(point.o2_kg_day for point in self.points)

    def total_co2_kg(self) -> float:
        return sum(point.co2_kg_day for point in self.points)

    def total_water_kg(self) -> float:
        return sum(point.water_kg_day for point in self.points)


@dataclass
class PerCropGreenhouse:
    growth_area_total_m2: float = 12.5
    led_dli_mol_m2_day: float = 17.0
    crops: tuple[CropProfile, ...] = CROP_PROFILES
    microgravity: bool = False

    def step_day(self, sol: int) -> list[CropTimeSeriesPoint]:
        results: list[CropTimeSeriesPoint] = []
        for crop in self.crops:
            area_m2 = self.growth_area_total_m2 * crop.growth_area_share
            if not (crop.germination_days <= (sol % crop.harvest_days) <= crop.harvest_days):
                continue
            par_mol_day = self.led_dli_mol_m2_day * area_m2
            produce_kg_day = par_mol_day * crop.yield_g_mol_par / 1000.0
            transp = crop.transpiration_kg_per_kg
            co2 = crop.co2_uptake_kg_per_kg
            o2 = crop.o2_production_kg_per_kg
            if self.microgravity:
                transp *= MICROGRAVITY_TRANSPIRATION_MULTIPLIER
                co2 *= MICROGRAVITY_GAS_EXCHANGE_MULTIPLIER
                o2 *= MICROGRAVITY_GAS_EXCHANGE_MULTIPLIER
            results.append(CropTimeSeriesPoint(
                sol=sol,
                crop=crop.name,
                growing_area_m2=area_m2,
                produce_kg_day=produce_kg_day,
                o2_kg_day=produce_kg_day * o2,
                co2_kg_day=produce_kg_day * co2,
                water_kg_day=produce_kg_day * transp,
            ))
        return results

    def integrate(self, *, duration_days: int) -> CropProductionRun:
        run = CropProductionRun()
        for sol in range(1, duration_days + 1):
            run.points.extend(self.step_day(sol))
        return run


@dataclass(frozen=True)
class WaterClosureCheck:
    transpired_kg: float
    recovered_kg: float
    losses_kg: float
    closure_pct: float

    @property
    def closes(self) -> bool:
        return self.closure_pct >= 0.85


def water_closure_balance(
    *, transpired_kg: float, recovery_efficiency: float = 0.92,
    miscellaneous_loss_kg: float = 0.0,
) -> WaterClosureCheck:
    if transpired_kg <= 0:
        return WaterClosureCheck(0.0, 0.0, 0.0, 1.0)
    recovered = transpired_kg * recovery_efficiency
    losses = transpired_kg - recovered + miscellaneous_loss_kg
    closure = recovered / transpired_kg
    return WaterClosureCheck(
        transpired_kg=transpired_kg, recovered_kg=recovered,
        losses_kg=losses, closure_pct=closure,
    )
