from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from aria.replay.apollo13_cryo_stir import TelemetrySample


@dataclass(frozen=True)
class SensorNoiseProfile:
    parameter: str
    one_sigma: float
    bias: float = 0.0
    quantization_step: float = 0.0
    citation: str = ""


DEFAULT_SENSOR_NOISE_PROFILES: tuple[SensorNoiseProfile, ...] = (
    SensorNoiseProfile(
        parameter="O2_TANK_2_PRESSURE",
        one_sigma=2.0,
        bias=0.0,
        quantization_step=0.5,
        citation="Apollo SC09 Operations: cryo pressure transducer ±0.5 % FS, FS=1500 psia",
    ),
    SensorNoiseProfile(
        parameter="O2_TANK_2_TEMP",
        one_sigma=0.3,
        bias=0.1,
        quantization_step=0.1,
        citation="Apollo cryo temp sensor: ±2 deg per AOH §11",
    ),
    SensorNoiseProfile(
        parameter="O2_TANK_2_HEATER_CURRENT",
        one_sigma=0.05,
        quantization_step=0.05,
        citation="CSM heater current sensor full-scale ±2 % per AOH §11",
    ),
    SensorNoiseProfile(
        parameter="FUEL_CELL_1_VOLTAGE",
        one_sigma=0.05,
        quantization_step=0.01,
        citation="Apollo FC voltage telemetry: 8-bit ADC ±0.5 V FS",
    ),
    SensorNoiseProfile(
        parameter="FUEL_CELL_2_VOLTAGE",
        one_sigma=0.05,
        quantization_step=0.01,
    ),
    SensorNoiseProfile(
        parameter="FUEL_CELL_3_VOLTAGE",
        one_sigma=0.05,
        quantization_step=0.01,
    ),
    SensorNoiseProfile(
        parameter="CABIN_PRESSURE_KPA",
        one_sigma=0.02,
        quantization_step=0.01,
        citation="ISS PCS pressure sensor: ±0.05 kPa per SSP-50261",
    ),
    SensorNoiseProfile(
        parameter="CABIN_PPCO2_KPA",
        one_sigma=0.005,
        quantization_step=0.001,
    ),
    SensorNoiseProfile(
        parameter="MAIN_BUS_VOLTAGE_VDC",
        one_sigma=0.5,
        quantization_step=0.1,
        citation="ISS bus voltage telemetry: ±0.5 V resolution",
    ),
    SensorNoiseProfile(
        parameter="LEADING_EDGE_TEMP_K",
        one_sigma=8.0,
        quantization_step=2.0,
        citation="STS WLE thermocouple ±15 K per CAIB Vol II",
    ),
    SensorNoiseProfile(
        parameter="ATTITUDE_ROLL_DEG",
        one_sigma=0.05,
        quantization_step=0.01,
    ),
    SensorNoiseProfile(
        parameter="ATTITUDE_PITCH_DEG",
        one_sigma=0.05,
        quantization_step=0.01,
    ),
    SensorNoiseProfile(
        parameter="ATTITUDE_YAW_DEG",
        one_sigma=0.05,
        quantization_step=0.01,
    ),
)


def _profile_lookup(parameter: str, profiles: tuple[SensorNoiseProfile, ...]) -> Optional[SensorNoiseProfile]:
    for profile in profiles:
        if profile.parameter == parameter:
            return profile
    return None


def overlay_noise(
    samples: tuple[TelemetrySample, ...],
    *,
    profiles: tuple[SensorNoiseProfile, ...] = DEFAULT_SENSOR_NOISE_PROFILES,
    rng_seed: int = 7,
) -> tuple[TelemetrySample, ...]:
    import math
    rng = random.Random(rng_seed)
    out: list[TelemetrySample] = []
    for sample in samples:
        profile = _profile_lookup(sample.parameter, profiles)
        if profile is None or math.isnan(sample.value):
            out.append(sample)
            continue
        noisy = sample.value + rng.gauss(profile.bias, profile.one_sigma)
        if profile.quantization_step > 0 and not math.isnan(noisy):
            noisy = round(noisy / profile.quantization_step) * profile.quantization_step
        out.append(TelemetrySample(
            get_seconds=sample.get_seconds, parameter=sample.parameter,
            value=noisy, units=sample.units, quality_flag=sample.quality_flag,
        ))
    return tuple(out)
