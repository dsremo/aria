from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


GET_T0_S = 55 * 3600 + 53 * 60 + 18
GET_MASTER_ALARM_S = 55 * 3600 + 54 * 60 + 53
GET_TANK2_ZERO_S = 55 * 3600 + 55 * 60 + 35
GET_TANK1_LOSS_S = 55 * 3600 + 57 * 60 + 0
GET_FUEL_CELL_DROP_S = 55 * 3600 + 58 * 60 + 6


O2_TANK2_PRESSURE_NOMINAL_PSIA = 887.0
O2_TANK2_PRESSURE_PEAK_PSIA = 1008.0
O2_TANK1_PRESSURE_NOMINAL_PSIA = 879.0
O2_TANK_QUANTITY_NOMINAL_PCT = 81.5
HEATER_CURRENT_NOMINAL_A = 0.7
HEATER_CURRENT_SHORT_A = 18.0
TANK2_TEMP_NOMINAL_F = -190.0
TANK2_TEMP_PEAK_F = 80.0


@dataclass(frozen=True)
class TelemetrySample:
    get_seconds: float
    parameter: str
    value: float
    units: str
    quality_flag: str = "good"

    @property
    def get_string(self) -> str:
        total = int(self.get_seconds)
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _o2_tank2_pressure_psia(get_s: float) -> float:
    if get_s < GET_T0_S:
        return O2_TANK2_PRESSURE_NOMINAL_PSIA
    if get_s < GET_MASTER_ALARM_S:
        elapsed = get_s - GET_T0_S
        ramp = (O2_TANK2_PRESSURE_PEAK_PSIA - O2_TANK2_PRESSURE_NOMINAL_PSIA) * (elapsed / 95.0)
        return O2_TANK2_PRESSURE_NOMINAL_PSIA + ramp
    if get_s < GET_TANK2_ZERO_S:
        elapsed = get_s - GET_MASTER_ALARM_S
        decay = (O2_TANK2_PRESSURE_PEAK_PSIA / 42.0) * elapsed
        return max(0.0, O2_TANK2_PRESSURE_PEAK_PSIA - decay)
    return 0.0


def _o2_tank1_pressure_psia(get_s: float) -> float:
    if get_s < GET_MASTER_ALARM_S:
        return O2_TANK1_PRESSURE_NOMINAL_PSIA
    if get_s < GET_TANK1_LOSS_S:
        return O2_TANK1_PRESSURE_NOMINAL_PSIA
    elapsed_hours = (get_s - GET_TANK1_LOSS_S) / 3600.0
    decay_psia_per_hr = 250.0
    return max(0.0, O2_TANK1_PRESSURE_NOMINAL_PSIA - decay_psia_per_hr * elapsed_hours)


def _o2_tank2_quantity_pct(get_s: float) -> float:
    if get_s < GET_T0_S:
        return O2_TANK_QUANTITY_NOMINAL_PCT
    if get_s < GET_MASTER_ALARM_S:
        return O2_TANK_QUANTITY_NOMINAL_PCT
    return 0.0


def _o2_tank2_temp_f(get_s: float) -> float:
    if get_s < GET_T0_S:
        return TANK2_TEMP_NOMINAL_F
    if get_s < GET_MASTER_ALARM_S:
        elapsed = get_s - GET_T0_S
        ramp = (TANK2_TEMP_PEAK_F - TANK2_TEMP_NOMINAL_F) * (elapsed / 95.0)
        return TANK2_TEMP_NOMINAL_F + ramp
    return float("nan")


def _heater_current_a(get_s: float) -> float:
    if get_s < GET_T0_S:
        return 0.0
    if get_s < GET_MASTER_ALARM_S - 5.0:
        return HEATER_CURRENT_SHORT_A
    if get_s < GET_MASTER_ALARM_S:
        return 0.0
    return 0.0


def _fuel_cell_voltage_vdc(cell_index: int, get_s: float) -> float:
    nominal = 30.5
    if cell_index in (1, 3):
        if get_s < GET_FUEL_CELL_DROP_S:
            return nominal
        elapsed = get_s - GET_FUEL_CELL_DROP_S
        decay = min(elapsed / 300.0, 1.0) * nominal
        return max(0.0, nominal - decay)
    return nominal


def generate_apollo13_cryo_stir_telemetry(
    *,
    get_start_s: float = GET_T0_S - 60.0,
    get_end_s: float = GET_FUEL_CELL_DROP_S + 120.0,
    sample_period_s: float = 1.0,
) -> tuple[TelemetrySample, ...]:
    if sample_period_s <= 0:
        raise ValueError("sample_period_s must be positive")
    samples: list[TelemetrySample] = []
    current_get = get_start_s
    while current_get <= get_end_s:
        samples.append(TelemetrySample(
            get_seconds=current_get, parameter="O2_TANK_2_PRESSURE",
            value=_o2_tank2_pressure_psia(current_get), units="psia",
        ))
        samples.append(TelemetrySample(
            get_seconds=current_get, parameter="O2_TANK_1_PRESSURE",
            value=_o2_tank1_pressure_psia(current_get), units="psia",
        ))
        samples.append(TelemetrySample(
            get_seconds=current_get, parameter="O2_TANK_2_QUANTITY",
            value=_o2_tank2_quantity_pct(current_get), units="percent",
        ))
        samples.append(TelemetrySample(
            get_seconds=current_get, parameter="O2_TANK_2_TEMP",
            value=_o2_tank2_temp_f(current_get), units="degF",
            quality_flag="good" if current_get < GET_MASTER_ALARM_S else "lost",
        ))
        samples.append(TelemetrySample(
            get_seconds=current_get, parameter="O2_TANK_2_HEATER_CURRENT",
            value=_heater_current_a(current_get), units="amps",
        ))
        for cell_index in (1, 2, 3):
            samples.append(TelemetrySample(
                get_seconds=current_get,
                parameter=f"FUEL_CELL_{cell_index}_VOLTAGE",
                value=_fuel_cell_voltage_vdc(cell_index, current_get),
                units="vdc",
            ))
        current_get += sample_period_s
    return tuple(samples)


@dataclass(frozen=True)
class HistoricalTimeline:
    label: str
    get_seconds: float
    description: str

    @property
    def get_string(self) -> str:
        total = int(self.get_seconds)
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


HISTORICAL_TIMELINE: tuple[HistoricalTimeline, ...] = (
    HistoricalTimeline(
        label="stir_command",
        get_seconds=GET_T0_S,
        description="Houston commands O2 tank 2 cryo-stir; heater "
                    "current spikes to ~18 A (Cortright Report fig 5-3)",
    ),
    HistoricalTimeline(
        label="master_alarm",
        get_seconds=GET_MASTER_ALARM_S,
        description="Master alarm; O2 tank 2 pressure peak 1008 psia "
                    "then loss (Mission Report §5.1.4 + Cortright fig 5-2)",
    ),
    HistoricalTimeline(
        label="tank2_pressure_zero",
        get_seconds=GET_TANK2_ZERO_S,
        description="O2 tank 2 pressure reads zero (Mission Report §5.1.4)",
    ),
    HistoricalTimeline(
        label="tank1_decay_visible",
        get_seconds=GET_TANK1_LOSS_S,
        description="O2 tank 1 pressure begins steady decline "
                    "(secondary leak; Mission Report §5.1.4)",
    ),
    HistoricalTimeline(
        label="fuel_cells_1_3_lost",
        get_seconds=GET_FUEL_CELL_DROP_S,
        description="Fuel cells 1 and 3 lose reactant pressure; voltage "
                    "begins dropping (Cortright Report fig 5-4)",
    ),
)


@dataclass(frozen=True)
class GroundProcedure:
    get_seconds_acted: float
    description: str
    citation: str


HISTORICAL_GROUND_RESPONSE: tuple[GroundProcedure, ...] = (
    GroundProcedure(
        get_seconds_acted=GET_MASTER_ALARM_S + 60.0,
        description="EECOM Sy Liebergot directs Lovell to switch fuel-cell "
                    "to backup; not yet aware of tank rupture.",
        citation="Apollo 13 Mission Report §5.1.5",
    ),
    GroundProcedure(
        get_seconds_acted=GET_FUEL_CELL_DROP_S + 720.0,
        description="Flight director Kranz declares 'we just lost the moon' "
                    "and orders LM lifeboat checklist.",
        citation="Apollo 13 Mission Report §5.2 + crew transcript",
    ),
    GroundProcedure(
        get_seconds_acted=GET_FUEL_CELL_DROP_S + 4800.0,
        description="Crew enters LM Aquarius; CSM powered down.",
        citation="Apollo 13 Mission Report §5.2.3",
    ),
)


CITATIONS = (
    "Cortright Commission Report on the Apollo 13 Accident, NASA SP-1969 (1970)",
    "Apollo 13 Mission Report, MSC-02680, NASA Manned Spacecraft Center (Sep 1970), §5",
    "Apollo Spacecraft Flight History, NASA TM-X-65495",
    "Liebergot, S. EECOM: Last Man Through the Door (oral history)",
)
