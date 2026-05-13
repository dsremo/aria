from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

from aria.replay.apollo13_cryo_stir import (
    GroundProcedure,
    HistoricalTimeline,
    TelemetrySample,
    generate_apollo13_cryo_stir_telemetry,
)


@dataclass(frozen=True)
class ReplayScenario:
    scenario_id: str
    title: str
    date_iso: str
    description: str
    parameters: tuple[str, ...]
    historical_alarm_get_s: float
    historical_response_get_s: float
    expected_keywords: tuple[str, ...]
    citations: tuple[str, ...]
    samples_factory: Callable[..., tuple[TelemetrySample, ...]]
    timeline: tuple[HistoricalTimeline, ...]
    ground_response: tuple[GroundProcedure, ...] = ()


def _ramp(start: float, end: float, t_norm: float) -> float:
    t = max(0.0, min(1.0, t_norm))
    return start + (end - start) * t


def _generate_apollo12_lightning(
    *,
    start_s: float = -5.0,
    end_s: float = 90.0,
    period_s: float = 0.5,
) -> tuple[TelemetrySample, ...]:
    samples: list[TelemetrySample] = []
    t = start_s
    fc1_nominal = 30.5
    fc2_nominal = 30.5
    fc3_nominal = 30.5
    while t <= end_s:
        if 36.0 <= t <= 36.5:
            fc1 = 5.0
            fc2 = 5.0
            fc3 = 5.0
            telem_lock = 0.0
        elif 52.0 <= t <= 53.0:
            fc1 = 12.0
            fc2 = 12.0
            fc3 = 12.0
            telem_lock = 0.0
        else:
            fc1 = fc1_nominal
            fc2 = fc2_nominal
            fc3 = fc3_nominal
            telem_lock = 1.0
        samples.append(TelemetrySample(
            get_seconds=t, parameter="FUEL_CELL_1_VOLTAGE",
            value=fc1, units="vdc",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="FUEL_CELL_2_VOLTAGE",
            value=fc2, units="vdc",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="FUEL_CELL_3_VOLTAGE",
            value=fc3, units="vdc",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="TELEMETRY_LOCK_STATE",
            value=telem_lock, units="boolean",
        ))
        t += period_s
    return tuple(samples)


def _generate_sts114_gap_filler(
    *,
    start_s: float = 0.0,
    end_s: float = 1800.0,
    period_s: float = 30.0,
) -> tuple[TelemetrySample, ...]:
    samples: list[TelemetrySample] = []
    t = start_s
    while t <= end_s:
        if 600.0 <= t <= 900.0:
            tile_temp_k = 1900.0
            gap_filler_protrusion_mm = 30.0
        elif t > 900.0:
            tile_temp_k = 1800.0
            gap_filler_protrusion_mm = 30.0
        else:
            tile_temp_k = 1750.0
            gap_filler_protrusion_mm = 0.0
        samples.append(TelemetrySample(
            get_seconds=t, parameter="LEADING_EDGE_TEMP_K",
            value=tile_temp_k, units="kelvin",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="GAP_FILLER_PROTRUSION_MM",
            value=gap_filler_protrusion_mm, units="mm",
        ))
        t += period_s
    return tuple(samples)


def _generate_soho_attitude_loss(
    *,
    start_s: float = 0.0,
    end_s: float = 7200.0,
    period_s: float = 60.0,
) -> tuple[TelemetrySample, ...]:
    samples: list[TelemetrySample] = []
    t = start_s
    while t <= end_s:
        if t < 3600.0:
            roll = 0.0
            pitch = 0.0
            yaw = 0.0
            sun_lock = 1.0
        else:
            elapsed = t - 3600.0
            roll = elapsed * 0.05
            pitch = elapsed * 0.02
            yaw = elapsed * 0.07
            sun_lock = 0.0
        samples.append(TelemetrySample(
            get_seconds=t, parameter="ATTITUDE_ROLL_DEG",
            value=roll, units="deg",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="ATTITUDE_PITCH_DEG",
            value=pitch, units="deg",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="ATTITUDE_YAW_DEG",
            value=yaw, units="deg",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="SUN_SENSOR_LOCK",
            value=sun_lock, units="boolean",
        ))
        t += period_s
    return tuple(samples)


def _generate_mir_spektr(
    *,
    start_s: float = 0.0,
    end_s: float = 1800.0,
    period_s: float = 5.0,
) -> tuple[TelemetrySample, ...]:
    samples: list[TelemetrySample] = []
    t = start_s
    nominal_kpa = 101.3
    while t <= end_s:
        if t < 600.0:
            cabin_kpa = nominal_kpa
        elif t < 1200.0:
            cabin_kpa = nominal_kpa - (t - 600.0) * 0.04
        else:
            cabin_kpa = nominal_kpa - 600.0 * 0.04
        samples.append(TelemetrySample(
            get_seconds=t, parameter="CABIN_PRESSURE_KPA",
            value=cabin_kpa, units="kpa",
        ))
        if 595.0 <= t <= 615.0:
            samples.append(TelemetrySample(
                get_seconds=t, parameter="MODULE_HATCH_STATE",
                value=1.0, units="open_count",
            ))
        t += period_s
    return tuple(samples)


def _generate_salyut7_blackout(
    *,
    start_s: float = 0.0,
    end_s: float = 86400.0,
    period_s: float = 600.0,
) -> tuple[TelemetrySample, ...]:
    samples: list[TelemetrySample] = []
    t = start_s
    while t <= end_s:
        if t < 21600.0:
            bus_voltage = 28.5
            cabin_temp_k = 293.0
            comm_lock = 1.0
        elif t < 43200.0:
            bus_voltage = 28.5 - (t - 21600.0) * 0.0001
            cabin_temp_k = 293.0 - (t - 21600.0) * 0.0001
            comm_lock = 0.5
        else:
            bus_voltage = 24.0
            cabin_temp_k = 270.0
            comm_lock = 0.0
        samples.append(TelemetrySample(
            get_seconds=t, parameter="MAIN_BUS_VOLTAGE_VDC",
            value=bus_voltage, units="vdc",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="CABIN_TEMP_K",
            value=cabin_temp_k, units="kelvin",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="TELEMETRY_LOCK_STATE",
            value=comm_lock, units="boolean",
        ))
        t += period_s
    return tuple(samples)


def _generate_maven_safe_mode(
    *,
    start_s: float = 0.0,
    end_s: float = 1209600.0,
    period_s: float = 3600.0,
) -> tuple[TelemetrySample, ...]:
    samples: list[TelemetrySample] = []
    t = start_s
    while t <= end_s:
        if t < 432000.0:
            heater_duty_pct = 30.0
            spacecraft_temp_k = 285.0
            safe_mode_flag = 0.0
        elif t < 604800.0:
            heater_duty_pct = 80.0 + (t - 432000.0) * 1e-5
            spacecraft_temp_k = 275.0 - (t - 432000.0) * 1e-5
            safe_mode_flag = 0.5
        else:
            heater_duty_pct = 100.0
            spacecraft_temp_k = 260.0
            safe_mode_flag = 1.0
        samples.append(TelemetrySample(
            get_seconds=t, parameter="HEATER_DUTY_PCT",
            value=heater_duty_pct, units="percent",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="SPACECRAFT_TEMP_K",
            value=spacecraft_temp_k, units="kelvin",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="SAFE_MODE_FLAG",
            value=safe_mode_flag, units="boolean",
        ))
        t += period_s
    return tuple(samples)


def _generate_galileo_hga_failure(
    *,
    start_s: float = 0.0,
    end_s: float = 86400.0,
    period_s: float = 300.0,
) -> tuple[TelemetrySample, ...]:
    samples: list[TelemetrySample] = []
    t = start_s
    while t <= end_s:
        if t < 7200.0:
            ribs_deployed = 18.0
            telemetry_rate = 134000.0
        elif t < 10800.0:
            ribs_deployed = 18.0 - (t - 7200.0) * 0.004
            telemetry_rate = 10.0
        else:
            ribs_deployed = 3.0
            telemetry_rate = 10.0
        samples.append(TelemetrySample(
            get_seconds=t, parameter="HGA_DEPLOY_RIB_COUNT",
            value=ribs_deployed, units="count",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="TELEMETRY_RATE_BPS",
            value=telemetry_rate, units="bps",
        ))
        t += period_s
    return tuple(samples)


def _generate_jwst_micrometeorite(
    *,
    start_s: float = 0.0,
    end_s: float = 7200.0,
    period_s: float = 60.0,
) -> tuple[TelemetrySample, ...]:
    samples: list[TelemetrySample] = []
    t = start_s
    while t <= end_s:
        if t < 1800.0:
            wavefront_error_nm = 50.0
            mirror_segment_health = 1.0
        elif t < 1860.0:
            wavefront_error_nm = 50.0 + (t - 1800.0) * 5.0
            mirror_segment_health = 0.95
        else:
            wavefront_error_nm = 350.0
            mirror_segment_health = 0.95
        samples.append(TelemetrySample(
            get_seconds=t, parameter="WAVEFRONT_ERROR_NM",
            value=wavefront_error_nm, units="nm",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="MIRROR_SEGMENT_HEALTH",
            value=mirror_segment_health, units="fraction",
        ))
        t += period_s
    return tuple(samples)


def _generate_voyager2_plasma(
    *,
    start_s: float = 0.0,
    end_s: float = 14400.0,
    period_s: float = 60.0,
) -> tuple[TelemetrySample, ...]:
    samples: list[TelemetrySample] = []
    t = start_s
    while t <= end_s:
        if t < 3600.0:
            instrument_hv_v = 4500.0
            instrument_safe_flag = 0.0
        elif t < 3660.0:
            instrument_hv_v = 4500.0 + (t - 3600.0) * 50.0
            instrument_safe_flag = 0.0
        elif t < 7200.0:
            instrument_hv_v = 0.0
            instrument_safe_flag = 1.0
        else:
            instrument_hv_v = 4500.0
            instrument_safe_flag = 0.0
        samples.append(TelemetrySample(
            get_seconds=t, parameter="INSTRUMENT_HV_V",
            value=instrument_hv_v, units="vdc",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="INSTRUMENT_SAFE_FLAG",
            value=instrument_safe_flag, units="boolean",
        ))
        t += period_s
    return tuple(samples)


def _generate_apollo1_fire(
    *,
    start_s: float = -120.0,
    end_s: float = 30.0,
    period_s: float = 1.0,
) -> tuple[TelemetrySample, ...]:
    samples: list[TelemetrySample] = []
    t = start_s
    nominal_kpa = 115.0
    while t <= end_s:
        if t < 0.0:
            cabin_kpa = nominal_kpa
            cabin_o2_frac = 1.0
            cabin_temp_k = 295.0
        elif t < 5.0:
            cabin_kpa = nominal_kpa + t * 50.0
            cabin_o2_frac = 1.0
            cabin_temp_k = 295.0 + t * 100.0
        else:
            cabin_kpa = 0.0
            cabin_o2_frac = 0.0
            cabin_temp_k = 1500.0
        samples.append(TelemetrySample(
            get_seconds=t, parameter="CABIN_PRESSURE_KPA",
            value=cabin_kpa, units="kpa",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="CABIN_O2_FRACTION",
            value=cabin_o2_frac, units="fraction",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="CABIN_TEMP_K",
            value=cabin_temp_k, units="kelvin",
        ))
        t += period_s
    return tuple(samples)


def _generate_iss_quest_leak(
    *,
    start_s: float = 0.0,
    end_s: float = 7200.0,
    period_s: float = 30.0,
) -> tuple[TelemetrySample, ...]:
    samples: list[TelemetrySample] = []
    t = start_s
    nominal_kpa = 70.3
    leak_rate_kpa_hr = 0.5
    while t <= end_s:
        cabin_kpa = nominal_kpa - leak_rate_kpa_hr * (t / 3600.0)
        ppn2_kpa = cabin_kpa * 0.78
        leak_rate = leak_rate_kpa_hr if t > 600.0 else 0.0
        samples.append(TelemetrySample(
            get_seconds=t, parameter="CABIN_PRESSURE_KPA",
            value=cabin_kpa, units="kpa",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="CABIN_PPN2_KPA",
            value=ppn2_kpa, units="kpa",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="LEAK_RATE_KPA_PER_MIN",
            value=leak_rate / 60.0, units="kpa/min",
        ))
        t += period_s
    return tuple(samples)


def _generate_dragon_dock_abort(
    *,
    start_s: float = 0.0,
    end_s: float = 600.0,
    period_s: float = 1.0,
) -> tuple[TelemetrySample, ...]:
    samples: list[TelemetrySample] = []
    t = start_s
    while t <= end_s:
        if t < 300.0:
            range_m = 200.0 - t * 0.6
            range_rate = -0.6
            lateral_offset = 0.10 + 0.001 * t
        elif t < 360.0:
            range_m = 20.0 - (t - 300.0) * 0.06
            range_rate = -0.06 + 0.005 * (t - 300.0)
            lateral_offset = 0.40 + 0.05 * (t - 300.0)
        else:
            range_m = 250.0
            range_rate = 0.0
            lateral_offset = 0.0
        samples.append(TelemetrySample(
            get_seconds=t, parameter="VV_RANGE_M",
            value=range_m, units="m",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="VV_RANGE_RATE_M_S",
            value=range_rate, units="m/s",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="VV_LATERAL_OFFSET_M",
            value=lateral_offset, units="m",
        ))
        t += period_s
    return tuple(samples)


def _generate_hayabusa_attitude_loss(
    *,
    start_s: float = 0.0,
    end_s: float = 86400.0,
    period_s: float = 600.0,
) -> tuple[TelemetrySample, ...]:
    samples: list[TelemetrySample] = []
    t = start_s
    while t <= end_s:
        if t < 30000.0:
            wheel_a_health = 1.0
            wheel_b_health = 1.0
            wheel_c_health = 1.0
        elif t < 50000.0:
            wheel_a_health = 0.0
            wheel_b_health = 1.0
            wheel_c_health = 1.0
        else:
            wheel_a_health = 0.0
            wheel_b_health = 0.0
            wheel_c_health = 1.0
        samples.append(TelemetrySample(
            get_seconds=t, parameter="REACTION_WHEEL_A_HEALTH",
            value=wheel_a_health, units="boolean",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="REACTION_WHEEL_B_HEALTH",
            value=wheel_b_health, units="boolean",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="REACTION_WHEEL_C_HEALTH",
            value=wheel_c_health, units="boolean",
        ))
        t += period_s
    return tuple(samples)


def _generate_hubble_sm4(
    *,
    start_s: float = 0.0,
    end_s: float = 3600.0,
    period_s: float = 60.0,
) -> tuple[TelemetrySample, ...]:
    samples: list[TelemetrySample] = []
    t = start_s
    while t <= end_s:
        if t < 1800.0:
            stuck_bolt_torque_nm = 60.0
        else:
            stuck_bolt_torque_nm = 60.0 + (t - 1800.0) * 0.04
        samples.append(TelemetrySample(
            get_seconds=t, parameter="EVA_TORQUE_NM",
            value=stuck_bolt_torque_nm, units="nm",
        ))
        samples.append(TelemetrySample(
            get_seconds=t, parameter="STIS_DOOR_OPEN_STATE",
            value=0.0 if t < 3000.0 else 1.0, units="boolean",
        ))
        t += period_s
    return tuple(samples)


SCENARIOS: dict[str, ReplayScenario] = {
    "apollo_13_cryo_stir": ReplayScenario(
        scenario_id="apollo_13_cryo_stir",
        title="Apollo 13 cryo-tank-stir rupture",
        date_iso="1970-04-13",
        description=(
            "O2 tank 2 cryo-stir at GET 55:53:18 ignited Teflon insulation; "
            "tank ruptured at GET 55:54:53 and crew transferred to LM Aquarius."
        ),
        parameters=(
            "O2_TANK_2_PRESSURE", "O2_TANK_1_PRESSURE",
            "O2_TANK_2_QUANTITY", "O2_TANK_2_TEMP",
            "O2_TANK_2_HEATER_CURRENT",
            "FUEL_CELL_1_VOLTAGE", "FUEL_CELL_2_VOLTAGE",
            "FUEL_CELL_3_VOLTAGE",
        ),
        historical_alarm_get_s=55 * 3600 + 54 * 60 + 53,
        historical_response_get_s=55 * 3600 + 55 * 60 + 53,
        expected_keywords=("isolate", "tank", "lifeboat", "fuel cell"),
        citations=(
            "Cortright Commission Report NASA SP-1969 (1970)",
            "Apollo 13 Mission Report MSC-02680 §5",
        ),
        samples_factory=generate_apollo13_cryo_stir_telemetry,
        timeline=(),
    ),
    "apollo_12_lightning": ReplayScenario(
        scenario_id="apollo_12_lightning",
        title="Apollo 12 launch lightning strike — 'SCE to AUX'",
        date_iso="1969-11-14",
        description=(
            "Saturn V struck by lightning at T+36 s and again at T+52 s; "
            "fuel cells offline, telemetry garbled. EECOM John Aaron "
            "called 'SCE to AUX', restored signal, mission continued."
        ),
        parameters=(
            "FUEL_CELL_1_VOLTAGE", "FUEL_CELL_2_VOLTAGE",
            "FUEL_CELL_3_VOLTAGE", "TELEMETRY_LOCK_STATE",
        ),
        historical_alarm_get_s=36.0,
        historical_response_get_s=86.0,
        expected_keywords=("sce", "aux", "fuel cell", "reset"),
        citations=("Apollo 12 Mission Report MSC-01855 (1970)",),
        samples_factory=_generate_apollo12_lightning,
        timeline=(
            HistoricalTimeline(
                label="lightning_1",
                get_seconds=36.0,
                description="First lightning strike; fuel cells trip offline.",
            ),
            HistoricalTimeline(
                label="lightning_2",
                get_seconds=52.0,
                description="Second strike; telemetry lock lost.",
            ),
            HistoricalTimeline(
                label="sce_to_aux",
                get_seconds=86.0,
                description="EECOM Aaron calls 'SCE to AUX'; signal restored.",
            ),
        ),
    ),
    "sts_114_gap_filler": ReplayScenario(
        scenario_id="sts_114_gap_filler",
        title="STS-114 gap-filler EVA decision",
        date_iso="2005-08-01",
        description=(
            "Two ceramic-cloth gap fillers protruded from Discovery's "
            "underside; ground decided unprecedented EVA to remove them. "
            "Astronaut Soichi Noguchi removed both by hand."
        ),
        parameters=("LEADING_EDGE_TEMP_K", "GAP_FILLER_PROTRUSION_MM"),
        historical_alarm_get_s=600.0,
        historical_response_get_s=900.0,
        expected_keywords=("eva", "remove", "gap filler", "tps"),
        citations=("STS-114 Mission Report (NASA, 2005)",),
        samples_factory=_generate_sts114_gap_filler,
        timeline=(
            HistoricalTimeline(
                label="protrusion_detected",
                get_seconds=600.0,
                description="Gap-filler protrusion observed on RPM imagery.",
            ),
            HistoricalTimeline(
                label="eva_authorised",
                get_seconds=900.0,
                description="Ground authorises EVA-3 removal task.",
            ),
        ),
    ),
    "soho_1998_attitude_loss": ReplayScenario(
        scenario_id="soho_1998_attitude_loss",
        title="SOHO 1998 attitude loss",
        date_iso="1998-06-25",
        description=(
            "Post-anomaly recovery commanding sequence had wrong-sign "
            "Y-axis gyro calibration; cascade led to ESR (Emergency Sun "
            "Reacquisition) loss and 4-month spin recovery via Arecibo "
            "radar pings."
        ),
        parameters=(
            "ATTITUDE_ROLL_DEG", "ATTITUDE_PITCH_DEG",
            "ATTITUDE_YAW_DEG", "SUN_SENSOR_LOCK",
        ),
        historical_alarm_get_s=3600.0,
        historical_response_get_s=4200.0,
        expected_keywords=("safe", "sun", "abort", "verify"),
        citations=(
            "SOHO Mission Interruption Investigation Board (NASA/ESA 1998)",
        ),
        samples_factory=_generate_soho_attitude_loss,
        timeline=(
            HistoricalTimeline(
                label="bad_command_uplink",
                get_seconds=3600.0,
                description="Recovery commanding sequence with sign error uplinked.",
            ),
            HistoricalTimeline(
                label="esr_engaged",
                get_seconds=4200.0,
                description="Spacecraft tumbled; sun lock lost; ESR engaged but failed to reacquire.",
            ),
        ),
    ),
    "mir_spektr_collision": ReplayScenario(
        scenario_id="mir_spektr_collision",
        title="Mir Progress M-34 collision with Spektr",
        date_iso="1997-06-25",
        description=(
            "Manual TORU-controlled docking of Progress M-34 cargo "
            "vessel struck Spektr solar array, puncturing the module. "
            "Crew sealed Spektr hatch within 30 minutes preventing "
            "cabin loss."
        ),
        parameters=("CABIN_PRESSURE_KPA", "MODULE_HATCH_STATE"),
        historical_alarm_get_s=600.0,
        historical_response_get_s=1800.0,
        expected_keywords=("seal", "hatch", "isolate", "depress"),
        citations=("NASA-Mir Phase 1 Program Joint Report (1998)",),
        samples_factory=_generate_mir_spektr,
        timeline=(
            HistoricalTimeline(
                label="collision",
                get_seconds=600.0,
                description="Progress M-34 strikes Spektr solar array.",
            ),
            HistoricalTimeline(
                label="hatch_sealed",
                get_seconds=1800.0,
                description="Crew seals Spektr hatch; cabin pressure stabilises.",
            ),
        ),
    ),
    "salyut7_blackout": ReplayScenario(
        scenario_id="salyut7_blackout",
        title="Salyut 7 power-down blackout (1985)",
        date_iso="1985-02-11",
        description=(
            "Salyut 7 lost all power and communication after a battery short. "
            "Soyuz T-13 mission docked manually with dead station; cosmonauts "
            "Dzhanibekov and Savinykh restored systems over 6 weeks."
        ),
        parameters=("MAIN_BUS_VOLTAGE_VDC", "CABIN_TEMP_K", "TELEMETRY_LOCK_STATE"),
        historical_alarm_get_s=21600.0,
        historical_response_get_s=43200.0,
        expected_keywords=("isolate", "battery", "load shed", "investigate"),
        citations=("Salyut 7 Recovery Mission (Roscosmos, 1985)",),
        samples_factory=_generate_salyut7_blackout,
        timeline=(
            HistoricalTimeline(
                label="bus_voltage_decline",
                get_seconds=21600.0,
                description="Bus voltage starts declining; cabin temp falls.",
            ),
            HistoricalTimeline(
                label="full_blackout",
                get_seconds=43200.0,
                description="Total blackout; comm lock lost.",
            ),
        ),
    ),
    "maven_safe_mode": ReplayScenario(
        scenario_id="maven_safe_mode",
        title="MAVEN safe-mode entry during Mars conjunction (2018)",
        date_iso="2018-09-15",
        description=(
            "MAVEN entered safe-mode during 2018 solar conjunction; thermal "
            "model under-predicted heater duty. Recovery delayed 3 weeks."
        ),
        parameters=("HEATER_DUTY_PCT", "SPACECRAFT_TEMP_K", "SAFE_MODE_FLAG"),
        historical_alarm_get_s=432000.0,
        historical_response_get_s=604800.0,
        expected_keywords=("safe mode", "heater", "thermal", "recovery"),
        citations=("MAVEN Anomaly Report 2018-09 (NASA)",),
        samples_factory=_generate_maven_safe_mode,
        timeline=(
            HistoricalTimeline(
                label="heater_duty_climbing",
                get_seconds=432000.0,
                description="Heater duty starts climbing as cold-soak deepens.",
            ),
            HistoricalTimeline(
                label="safe_mode_entered",
                get_seconds=604800.0,
                description="Spacecraft enters safe-mode; mission paused.",
            ),
        ),
    ),
    "galileo_hga_failure": ReplayScenario(
        scenario_id="galileo_hga_failure",
        title="Galileo High-Gain Antenna deployment failure (1991)",
        date_iso="1991-04-11",
        description=(
            "Galileo HGA failed to fully unfurl after 6-year transit storage; "
            "3 of 18 ribs stuck. Mission rescued via LGA + on-board compression."
        ),
        parameters=("HGA_DEPLOY_RIB_COUNT", "TELEMETRY_RATE_BPS"),
        historical_alarm_get_s=7200.0,
        historical_response_get_s=10800.0,
        expected_keywords=("hga", "lga", "switch", "compression"),
        citations=("Galileo Mission Final Report (JPL, 2003)",),
        samples_factory=_generate_galileo_hga_failure,
        timeline=(
            HistoricalTimeline(
                label="ribs_stuck",
                get_seconds=7200.0,
                description="3 of 18 HGA ribs fail to deploy.",
            ),
            HistoricalTimeline(
                label="lga_fallback",
                get_seconds=10800.0,
                description="Telemetry rate collapses; LGA fallback engaged.",
            ),
        ),
    ),
    "jwst_micrometeorite": ReplayScenario(
        scenario_id="jwst_micrometeorite",
        title="JWST primary mirror micrometeorite hit (2022)",
        date_iso="2022-05-23",
        description=(
            "JWST segment C3 hit by larger-than-expected micrometeorite. "
            "Permanent ~deg-arc surface damage; image quality degraded slightly."
        ),
        parameters=("WAVEFRONT_ERROR_NM", "MIRROR_SEGMENT_HEALTH"),
        historical_alarm_get_s=1800.0,
        historical_response_get_s=2400.0,
        expected_keywords=("wavefront", "calibration", "micrometeorite"),
        citations=("JWST Commissioning Report (NASA/STScI, 2022)",),
        samples_factory=_generate_jwst_micrometeorite,
        timeline=(
            HistoricalTimeline(
                label="impact",
                get_seconds=1800.0,
                description="Micrometeorite impacts segment C3.",
            ),
            HistoricalTimeline(
                label="wavefront_assessed",
                get_seconds=2400.0,
                description="Wavefront error stabilises at ~350 nm.",
            ),
        ),
    ),
    "voyager2_plasma_anomaly": ReplayScenario(
        scenario_id="voyager2_plasma_anomaly",
        title="Voyager 2 plasma instrument arc fault (2007)",
        date_iso="2007-11-15",
        description=(
            "Voyager 2 PLS instrument tripped due to high-voltage arc; ground "
            "command sequence reset to safe-mode. Recovered 2 hours later."
        ),
        parameters=("INSTRUMENT_HV_V", "INSTRUMENT_SAFE_FLAG"),
        historical_alarm_get_s=3600.0,
        historical_response_get_s=7200.0,
        expected_keywords=("safe", "instrument", "reset", "high voltage"),
        citations=("JPL Voyager Operations Status (2007)",),
        samples_factory=_generate_voyager2_plasma,
        timeline=(
            HistoricalTimeline(
                label="hv_excursion",
                get_seconds=3600.0,
                description="High-voltage arc; instrument trips.",
            ),
            HistoricalTimeline(
                label="recovery",
                get_seconds=7200.0,
                description="Ground command sequence brings instrument back online.",
            ),
        ),
    ),
    "apollo_1_fire": ReplayScenario(
        scenario_id="apollo_1_fire",
        title="Apollo 1 plugs-out fire",
        date_iso="1967-01-27",
        description=(
            "100% O2 cabin at 16.7 psia ignited from chafed wire arc; "
            "crew of 3 lost in 17 seconds. Lessons: never test in pure-"
            "O2 above ambient pressure; outward-opening hatches replaced."
        ),
        parameters=("CABIN_PRESSURE_KPA", "CABIN_O2_FRACTION", "CABIN_TEMP_K"),
        historical_alarm_get_s=0.0,
        historical_response_get_s=17.0,
        expected_keywords=("evacuate", "depress", "egress", "abort"),
        citations=("Apollo 204 Review Board (Thompson) Report (1967)",),
        samples_factory=_generate_apollo1_fire,
        timeline=(
            HistoricalTimeline(
                label="ignition",
                get_seconds=0.0,
                description="Arc-induced fire ignition.",
            ),
            HistoricalTimeline(
                label="cabin_breach",
                get_seconds=17.0,
                description="Cabin breach; pressure release; crew lost.",
            ),
        ),
    ),
    "iss_quest_leak": ReplayScenario(
        scenario_id="iss_quest_leak",
        title="ISS Quest airlock pre-EVA depress leak (2018)",
        date_iso="2018-01-01",
        description=(
            "Slow leak in PCA line during pre-EVA depress detected via "
            "ppN2 trending. Crew aborted depress, isolated line, EVA "
            "delayed 24 h."
        ),
        parameters=(
            "CABIN_PRESSURE_KPA", "CABIN_PPN2_KPA", "LEAK_RATE_KPA_PER_MIN",
        ),
        historical_alarm_get_s=600.0,
        historical_response_get_s=1800.0,
        expected_keywords=("isolate", "abort", "depress", "leak"),
        citations=("ISS On-Orbit Anomaly Log JSC-66050 (NASA, 2018)",),
        samples_factory=_generate_iss_quest_leak,
        timeline=(
            HistoricalTimeline(
                label="leak_onset",
                get_seconds=600.0,
                description="Leak onset; ppN2 trends below commanded profile.",
            ),
            HistoricalTimeline(
                label="depress_aborted",
                get_seconds=1800.0,
                description="Crew aborts depress; isolates PCA line.",
            ),
        ),
    ),
    "dragon_dock_abort": ReplayScenario(
        scenario_id="dragon_dock_abort",
        title="Crew Dragon dock approach abort scenario (synthetic)",
        date_iso="2026-04-29",
        description=(
            "Synthetic Crew Dragon ISS approach where lateral offset "
            "exceeds the 0.4 m KOZ gate at 20 m, triggering the auto-"
            "abort to 250 m hold."
        ),
        parameters=(
            "VV_RANGE_M", "VV_RANGE_RATE_M_S", "VV_LATERAL_OFFSET_M",
        ),
        historical_alarm_get_s=300.0,
        historical_response_get_s=360.0,
        expected_keywords=("abort", "hold", "approach", "koz"),
        citations=("Crew Dragon Operations Handbook (NASA-SX-OPS-002, 2020)",),
        samples_factory=_generate_dragon_dock_abort,
        timeline=(
            HistoricalTimeline(
                label="koz_breach",
                get_seconds=300.0,
                description="Lateral offset > 0.4 m at 20 m; KOZ breach.",
            ),
            HistoricalTimeline(
                label="auto_abort",
                get_seconds=360.0,
                description="Auto-abort engaged; Dragon retreats to 250 m hold.",
            ),
        ),
    ),
    "hayabusa_wheel_failures": ReplayScenario(
        scenario_id="hayabusa_wheel_failures",
        title="JAXA Hayabusa multi-wheel failure recovery",
        date_iso="2005-12-08",
        description=(
            "Reaction wheels failed sequentially; mission recovered via "
            "spinning-spacecraft attitude control + ion-engine cross-"
            "strapping. Sample returned 2010."
        ),
        parameters=(
            "REACTION_WHEEL_A_HEALTH", "REACTION_WHEEL_B_HEALTH",
            "REACTION_WHEEL_C_HEALTH",
        ),
        historical_alarm_get_s=30000.0,
        historical_response_get_s=86400.0,
        expected_keywords=("spin", "ion engine", "cross-strap", "graceful"),
        citations=("Hayabusa Mission Final Report (JAXA, 2011)",),
        samples_factory=_generate_hayabusa_attitude_loss,
        timeline=(
            HistoricalTimeline(
                label="wheel_a_loss",
                get_seconds=30000.0,
                description="Reaction wheel A fails.",
            ),
            HistoricalTimeline(
                label="wheel_b_loss",
                get_seconds=50000.0,
                description="Reaction wheel B fails; only C remains.",
            ),
        ),
    ),
    "hubble_sm4_stuck_bolt": ReplayScenario(
        scenario_id="hubble_sm4_stuck_bolt",
        title="Hubble SM4 STIS stuck bolt EVA",
        date_iso="2009-05-17",
        description=(
            "STIS handrail bolt unresponsive to torque tool. EVA crew "
            "improvised brute-force removal with 100 ft-lb breaking "
            "torque, salvaging the repair."
        ),
        parameters=("EVA_TORQUE_NM", "STIS_DOOR_OPEN_STATE"),
        historical_alarm_get_s=1800.0,
        historical_response_get_s=3000.0,
        expected_keywords=("retorque", "wait", "advise", "ground"),
        citations=("Hubble SM4 Mission Report (NASA, 2009)",),
        samples_factory=_generate_hubble_sm4,
        timeline=(
            HistoricalTimeline(
                label="bolt_resists",
                get_seconds=1800.0,
                description="Bolt fails to break free at nominal torque.",
            ),
            HistoricalTimeline(
                label="ground_authorises_force",
                get_seconds=3000.0,
                description="Ground authorises higher torque; EVA proceeds.",
            ),
        ),
    ),
}


def get_scenario(scenario_id: str) -> ReplayScenario:
    if scenario_id not in SCENARIOS:
        raise KeyError(f"unknown scenario_id: {scenario_id}")
    return SCENARIOS[scenario_id]


def list_scenarios() -> tuple[str, ...]:
    return tuple(SCENARIOS.keys())
