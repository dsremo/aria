from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional


SAA_FLUX_BASELINE_PER_M2_S = 5.0e3
SPE_PEAK_FLUX_PER_M2_S = 1.0e7
PLASMA_LATCH_PROB_PER_HR_BASELINE = 1.0e-6
PLASMA_LATCH_PROB_PER_HR_HIGH_FLUX = 1.0e-3


@dataclass
class CellThermalNode:
    cell_temp_k: float = 293.15
    thermal_capacitance_j_k: float = 60.0
    radiative_emissivity: float = 0.85
    radiative_area_m2: float = 0.005
    sink_temp_k: float = 273.15
    conduction_w_per_k: float = 0.5

    def step(self, *, joule_heat_w: float, irradiance_w_m2: float, dt_s: float) -> float:
        sigma = 5.670374419e-8
        radiative_w = (
            self.radiative_emissivity * sigma * self.radiative_area_m2
            * (self.cell_temp_k ** 4 - self.sink_temp_k ** 4)
        )
        conducted_w = self.conduction_w_per_k * (self.cell_temp_k - self.sink_temp_k)
        absorbed_w = irradiance_w_m2 * self.radiative_area_m2 * 0.05
        net_w = joule_heat_w + absorbed_w - radiative_w - conducted_w
        delta_t = net_w * dt_s / max(1.0, self.thermal_capacitance_j_k)
        self.cell_temp_k = max(150.0, min(400.0, self.cell_temp_k + delta_t))
        return self.cell_temp_k


@dataclass
class MpptController:
    duty_cycle: float = 0.50
    step_size: float = 0.02
    last_power_w: float = 0.0
    direction: int = 1
    min_duty: float = 0.10
    max_duty: float = 0.90

    def update(self, *, current_power_w: float) -> float:
        if current_power_w < self.last_power_w:
            self.direction = -self.direction
        self.duty_cycle = max(
            self.min_duty,
            min(self.max_duty, self.duty_cycle + self.direction * self.step_size),
        )
        self.last_power_w = current_power_w
        return self.duty_cycle

    def transfer(self, *, source_w: float, base_efficiency: float = 0.96) -> float:
        if source_w <= 0:
            return 0.0
        duty_penalty = 1.0 - 0.05 * abs(self.duty_cycle - 0.50) * 2.0
        return source_w * base_efficiency * max(0.85, duty_penalty)


@dataclass
class BmsImbalance:
    n_cells: int
    base_capacity_ah: float
    rng_seed: int = 42
    max_imbalance_pct: float = 0.05
    cell_capacities_ah: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        rng = random.Random(self.rng_seed)
        if not self.cell_capacities_ah:
            self.cell_capacities_ah = [
                self.base_capacity_ah * (1.0 + rng.uniform(-self.max_imbalance_pct, self.max_imbalance_pct))
                for _ in range(self.n_cells)
            ]

    def weakest_cell_capacity_ah(self) -> float:
        return min(self.cell_capacities_ah)

    def strongest_cell_capacity_ah(self) -> float:
        return max(self.cell_capacities_ah)

    def imbalance_ratio(self) -> float:
        weakest = self.weakest_cell_capacity_ah()
        strongest = self.strongest_cell_capacity_ah()
        if strongest == 0:
            return 0.0
        return (strongest - weakest) / strongest

    def step_age(self, *, equivalent_full_cycles: float, dt_days: float) -> None:
        cycle_loss = equivalent_full_cycles / 30000.0
        calendar_loss = dt_days / 365.25 / 80.0
        for index in range(self.n_cells):
            self.cell_capacities_ah[index] *= (1.0 - cycle_loss * 0.05 - calendar_loss * 0.01)


@dataclass
class BatteryAgingModel:
    cycle_count: float = 0.0
    calendar_days: float = 0.0
    capacity_fade_factor: float = 1.0

    def step(
        self,
        *,
        equivalent_full_cycles: float,
        dt_days: float,
        temperature_c: float = 20.0,
    ) -> float:
        self.cycle_count += equivalent_full_cycles
        self.calendar_days += dt_days
        cycle_loss = (self.cycle_count / 30000.0) * 0.20
        calendar_loss = (self.calendar_days / 365.25) * 0.02
        if temperature_c > 25.0:
            calendar_loss *= 1.0 + (temperature_c - 25.0) * 0.04
        self.capacity_fade_factor = max(0.6, 1.0 - cycle_loss - calendar_loss)
        return self.capacity_fade_factor


@dataclass
class PlasmaLatchEvent:
    occurred: bool
    timestamp_s: float
    cause: str


class PlasmaLatchupSimulator:
    def __init__(
        self,
        *,
        baseline_prob_per_hr: float = PLASMA_LATCH_PROB_PER_HR_BASELINE,
        high_flux_prob_per_hr: float = PLASMA_LATCH_PROB_PER_HR_HIGH_FLUX,
        rng_seed: int = 13,
    ) -> None:
        self._baseline = baseline_prob_per_hr
        self._high_flux = high_flux_prob_per_hr
        self._rng = random.Random(rng_seed)

    def step(
        self, *, dt_s: float, in_saa: bool = False, spe_active: bool = False,
    ) -> Optional[PlasmaLatchEvent]:
        prob_hr = self._baseline
        if in_saa:
            prob_hr = max(prob_hr, self._high_flux * 0.1)
        if spe_active:
            prob_hr = self._high_flux
        prob_step = 1.0 - math.exp(-prob_hr * dt_s / 3600.0)
        if self._rng.random() < prob_step:
            cause = "spe" if spe_active else "saa" if in_saa else "baseline"
            return PlasmaLatchEvent(
                occurred=True, timestamp_s=0.0, cause=cause,
            )
        return None


@dataclass(frozen=True)
class PowerDynamicsSnapshot:
    cell_temp_k: float
    mppt_duty_cycle: float
    bms_imbalance_pct: float
    aging_capacity_factor: float
    plasma_latch_event: Optional[PlasmaLatchEvent]
