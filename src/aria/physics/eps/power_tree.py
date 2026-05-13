from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from aria.physics.eps.li_ion_cells import (
    LiIonCell,
    terminal_voltage,
    update_soc,
)
from aria.physics.eps.solar_cells import (
    SolarCell,
    cell_max_power,
)


SOLAR_CONSTANT_W_M2 = 1361.0
ISS_AVG_LOAD_KW = 84.0
ISS_GENERATION_PEAK_KW = 240.0
ISS_BATTERY_TOTAL_KWH = 224.0
ECLIPSE_FRACTION_LEO = 0.36
EARTH_ALBEDO_FACTOR = 0.30


@dataclass
class SolarArray:
    cells_in_series: int
    cells_in_parallel: int
    cell: SolarCell
    pointing_efficiency: float = 0.95
    harness_efficiency: float = 0.97
    degradation_factor: float = 1.0

    def power_at_irradiance(
        self, *, irradiance_w_m2: float, cell_temp_k: float,
    ) -> float:
        if irradiance_w_m2 <= 0.0:
            return 0.0
        ivpoint = cell_max_power(
            self.cell,
            temperature_k=cell_temp_k,
            intensity_w_m2=irradiance_w_m2,
        )
        per_cell_pmp = ivpoint.power_w
        gross = (
            per_cell_pmp * self.cells_in_series * self.cells_in_parallel
            * self.pointing_efficiency * self.harness_efficiency
            * self.degradation_factor
        )
        return max(0.0, gross)


@dataclass
class MpptStage:
    efficiency: float = 0.96

    def transfer(self, *, source_w: float) -> float:
        if source_w <= 0:
            return 0.0
        return source_w * self.efficiency


@dataclass
class BatteryPack:
    cell: LiIonCell
    cells_in_series: int
    parallel_strings: int
    soc_fraction: float = 1.0
    temperature_c: float = 20.0
    cycle_count: int = 0
    calendar_age_days: float = 0.0

    def pack_voltage(self, *, draw_a: float = 0.0) -> float:
        return terminal_voltage(
            self.cell,
            soc_fraction=self.soc_fraction,
            current_a=draw_a / max(1, self.parallel_strings),
            temperature_c=self.temperature_c,
        ) * self.cells_in_series

    def pack_capacity_ah(self) -> float:
        return self.cell.nominal_capacity_ah * self.parallel_strings

    def pack_energy_wh(self) -> float:
        nominal_voltage = self.cell.nominal_voltage_v * self.cells_in_series
        return self.pack_capacity_ah() * nominal_voltage * self.soc_fraction

    def step_charge(self, *, current_a: float, dt_s: float) -> None:
        new_soc = update_soc(
            self.cell,
            soc_fraction=self.soc_fraction,
            current_a=current_a / max(1, self.parallel_strings),
            dt_s=dt_s,
            temperature_c=self.temperature_c,
        )
        self.soc_fraction = max(0.0, min(1.0, new_soc))

    def calendar_age_factor(self) -> float:
        years = self.calendar_age_days / 365.25
        return max(0.6, 1.0 - 0.02 * years)

    def cycle_age_factor(self) -> float:
        return max(0.6, 1.0 - (self.cycle_count / 30000.0) * 0.4)


@dataclass(frozen=True)
class LoadGroup:
    name: str
    nominal_w: float
    priority: int


@dataclass(frozen=True)
class LoadSheddingPolicy:
    groups: tuple[LoadGroup, ...]

    def shed_to_budget(self, *, available_w: float) -> tuple[tuple[str, float], ...]:
        applied: list[tuple[str, float]] = []
        remaining = max(0.0, available_w)
        for group in sorted(self.groups, key=lambda g: g.priority):
            allocated = min(group.nominal_w, remaining)
            applied.append((group.name, allocated))
            remaining -= allocated
            if remaining <= 0:
                break
        for group in self.groups:
            if not any(name == group.name for name, _ in applied):
                applied.append((group.name, 0.0))
        return tuple(applied)


@dataclass(frozen=True)
class PowerTreeSnapshot:
    irradiance_w_m2: float
    eclipse: bool
    array_dc_w: float
    mppt_out_w: float
    battery_voltage_v: float
    battery_soc: float
    battery_charge_w: float
    battery_discharge_w: float
    bus_voltage_v: float
    load_demand_w: float
    load_supplied_w: float
    load_allocations: tuple[tuple[str, float], ...]
    margin_w: float
    notes: str = ""


@dataclass
class PowerTree:
    array: SolarArray
    mppt: MpptStage
    battery: BatteryPack
    bus_efficiency: float = 0.98
    bus_nominal_v: float = 120.0
    load_policy: Optional[LoadSheddingPolicy] = None
    history: list[PowerTreeSnapshot] = field(default_factory=list)

    def step(
        self,
        *,
        irradiance_w_m2: float,
        cell_temp_k: float,
        load_demand_w: float,
        dt_s: float,
        eclipse: bool = False,
    ) -> PowerTreeSnapshot:
        if irradiance_w_m2 < 0:
            raise ValueError("irradiance must be non-negative")
        if load_demand_w < 0:
            raise ValueError("load demand must be non-negative")
        if dt_s <= 0:
            raise ValueError("dt_s must be positive")

        irr = 0.0 if eclipse else irradiance_w_m2
        array_dc_w = self.array.power_at_irradiance(
            irradiance_w_m2=irr, cell_temp_k=cell_temp_k,
        )
        mppt_out_w = self.mppt.transfer(source_w=array_dc_w)

        net_w = mppt_out_w * self.bus_efficiency - load_demand_w
        battery_charge_w = 0.0
        battery_discharge_w = 0.0
        if net_w > 0:
            battery_charge_w = net_w
            charge_current = battery_charge_w / max(self.battery.pack_voltage(), 1e-3)
            self.battery.step_charge(current_a=-charge_current, dt_s=dt_s)
        else:
            battery_discharge_w = -net_w
            discharge_current = battery_discharge_w / max(self.battery.pack_voltage(), 1e-3)
            self.battery.step_charge(current_a=discharge_current, dt_s=dt_s)

        available_for_loads_w = mppt_out_w * self.bus_efficiency + battery_discharge_w
        allocations: tuple[tuple[str, float], ...] = ()
        load_supplied_w = min(load_demand_w, available_for_loads_w)
        if self.load_policy is not None:
            allocations = self.load_policy.shed_to_budget(
                available_w=available_for_loads_w,
            )
        margin_w = available_for_loads_w - load_demand_w

        snapshot = PowerTreeSnapshot(
            irradiance_w_m2=irr,
            eclipse=eclipse,
            array_dc_w=array_dc_w,
            mppt_out_w=mppt_out_w,
            battery_voltage_v=self.battery.pack_voltage(),
            battery_soc=self.battery.soc_fraction,
            battery_charge_w=battery_charge_w,
            battery_discharge_w=battery_discharge_w,
            bus_voltage_v=self.bus_nominal_v,
            load_demand_w=load_demand_w,
            load_supplied_w=load_supplied_w,
            load_allocations=allocations,
            margin_w=margin_w,
        )
        self.history.append(snapshot)
        return snapshot


def simulate_leo_orbit(
    tree: PowerTree,
    *,
    orbit_period_s: float = 5_580.0,
    eclipse_fraction: float = ECLIPSE_FRACTION_LEO,
    n_orbits: int = 1,
    base_load_w: float = 0.0,
    sample_period_s: float = 60.0,
    sun_pointing_irradiance_w_m2: float = SOLAR_CONSTANT_W_M2,
    eclipse_cell_temp_k: float = 263.0,
    sun_cell_temp_k: float = 333.0,
) -> list[PowerTreeSnapshot]:
    snapshots: list[PowerTreeSnapshot] = []
    eclipse_seconds = eclipse_fraction * orbit_period_s
    sunlit_seconds = orbit_period_s - eclipse_seconds
    for _ in range(n_orbits):
        elapsed = 0.0
        while elapsed < sunlit_seconds:
            dt = min(sample_period_s, sunlit_seconds - elapsed)
            snap = tree.step(
                irradiance_w_m2=sun_pointing_irradiance_w_m2,
                cell_temp_k=sun_cell_temp_k,
                load_demand_w=base_load_w,
                dt_s=dt,
                eclipse=False,
            )
            snapshots.append(snap)
            elapsed += dt
        elapsed = 0.0
        while elapsed < eclipse_seconds:
            dt = min(sample_period_s, eclipse_seconds - elapsed)
            snap = tree.step(
                irradiance_w_m2=0.0,
                cell_temp_k=eclipse_cell_temp_k,
                load_demand_w=base_load_w,
                dt_s=dt,
                eclipse=True,
            )
            snapshots.append(snap)
            elapsed += dt
    return snapshots
