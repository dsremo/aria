"""Operator-driven failure / scenario injector.

Lets the React UI (or a test) say "trip the maglev bearing" or "knock
out radiator wing +Y" or "set scrubber efficiency to 5 %" so the cascade
through dependency_graph.failure_cascade can be observed live in the
inspector + alarms.

Each scenario is a named callable that mutates one or more subsystem
states and publishes a corresponding event.

Handy for:
  * Testing the React panels with realistic alarm cascades
  * Crew training simulators
  * Engineering-review demos ("watch what happens if shield L4 fails")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller


# ── Scenario registry ──────────────────────────────────────────────

@dataclass(frozen=True)
class Scenario:
    """A named failure scenario."""

    id: str
    label: str
    description: str
    impact: str            # one-line cascade hint for the UI
    severity: str          # 'warning' or 'critical'
    apply: Callable[[], dict]   # returns dict of changed-state info


def _scenario_maglev_trip() -> dict:
    from aria.simulator.bearing_dynamics import get_bearing_state
    bs = get_bearing_state()
    bs.force_trip("Failure injector: maglev controller fault")
    return {"target": "ring_bearing", "new_mode": bs.mode.value}


def _scenario_radiator_loss() -> dict:
    from aria.simulator.propulsion_thermal import get_propulsion_thermal
    pt = get_propulsion_thermal()
    pt.radiator_capacity_w *= 0.5     # halve radiator capacity = simulate 1 of 2 wings lost
    return {"target": "radiator_array_0", "new_capacity_w": pt.radiator_capacity_w}


def _scenario_eclss_scrubber_fault() -> dict:
    from aria.simulator.eclss_contaminants import get_eclss_contaminants
    ec = get_eclss_contaminants()
    ec.scrubber_efficiency_frac = 0.10   # 90 % degradation
    return {"target": "eclss", "scrubber_eff_frac": ec.scrubber_efficiency_frac}


def _scenario_main_fuel_leak() -> dict:
    from aria.simulator.fuel_tracker import get_fuel_inventory
    fi = get_fuel_inventory()
    t = fi.tanks["main_tank_a"]
    # Skip if tank is effectively empty — old drill reported "30 %
    # vented" with leaked_kg=0 because it was draining already-empty
    # tanks, giving operators a false "drill succeeded" signal.
    if t.contents_kg < 1.0:
        return {"target": "fuel_tank_0", "leaked_kg": 0.0,
                "status": "skipped", "reason": "tank_a already empty"}
    leaked = t.contents_kg * 0.30        # 30 % loss from tank A
    t.contents_kg -= leaked
    # Update cumulative_leaked so the conservation invariant
    # (contents + cumulative_drawn + cumulative_leaked = capacity) holds.
    t.cumulative_leaked_kg = getattr(t, "cumulative_leaked_kg", 0.0) + leaked
    return {"target": "fuel_tank_0", "leaked_kg": round(leaked, 1)}


def _scenario_shield_ice_micrometeoroid() -> dict:
    """Simulates ablation-ice loss to a micrometeoroid impact — small
    fraction of mass + extra contaminants released."""
    return {"target": "shield_layer_4", "ice_loss_kg": 5e3}


def _scenario_seu_storm() -> dict:
    """Simulates a galactic-cosmic-ray flare. Bumps SEU rate dramatically."""
    from aria.simulator.computing_radiation import get_computing_radiation
    cr = get_computing_radiation()
    cr.current_shielding_factor *= 100   # 100x worse temporarily
    return {"target": "avionics_compute", "shielding_factor": cr.current_shielding_factor}


def _scenario_apu_fault() -> dict:
    """Simulates loss of one of the two APUs — affects bringup but not cruise."""
    return {"target": "apu_bootstrap", "units_lost": 1}


def _scenario_tmr_disagreement_burst() -> dict:
    """Forces a TMR voter disagreement + recovery."""
    from aria.simulator.computing_radiation import get_computing_radiation
    cr = get_computing_radiation()
    cr.tmr_disagreements += 5
    cr.tmr_minority_vote_outs += 5
    return {"target": "flight_computer_tmr", "disagreements_added": 5}


def _scenario_avionics_ecc_cascade() -> dict:
    """Flight-computer ECC cascade: burst of uncorrectable bit flips.

    Simulates a radiation-induced double-bit error storm where ECC SECDED
    can detect but not correct — some escape silently. Publishes both
    halt (ecc_detect_only_halt) and escape (ecc_escape) events so the
    alarms panel shows the cascade, and bumps the counters so the
    AvionicsPanel reflects the elevated rate. Severity: critical — silent
    corruption is the worst-case failure mode for a triple-redundant flight
    computer.

    BUG-030 (2026-04-24): the walkthrough referenced this ID but no
    scenario was registered; any test following the docs got HTTP 400.
    """
    from aria.simulator.computing_radiation import get_computing_radiation
    from aria.simulator.event_bus import get_event_bus
    from aria.simulator.mission_phases import get_phase_controller
    cr = get_computing_radiation()
    bus = get_event_bus()
    phase = get_phase_controller()
    halts   = 8   # 8 ECC-halt bit flips (detect-only)
    escapes = 2   # 2 silent escapes (worst case)
    cr.ecc_detect_only_halts += halts
    cr.ecc_escapes           += escapes
    cr.total_seu_events      += halts + escapes
    for _ in range(halts):
        bus.publish("avionics.ecc_detect_only_halt",
                    severity="warning", source="failure_injector",
                    payload={"total": cr.ecc_detect_only_halts,
                             "cause": "avionics_ecc_cascade"},
                    sim_time_yr=phase.elapsed_yr)
    for _ in range(escapes):
        bus.publish("avionics.ecc_escape",
                    severity="critical", source="failure_injector",
                    payload={"total": cr.ecc_escapes,
                             "cause": "avionics_ecc_cascade"},
                    sim_time_yr=phase.elapsed_yr)
    return {"target": "flight_computer_ecc",
            "halts_added": halts, "escapes_added": escapes}


# ── Track-3 P2 densification: 31 additional scenarios ──────────────
# Each scenario has a citation tag pointing to the failure-mode source.
# State mutations target real subsystem singletons where possible; for
# subsystems that don't expose a knob, the scenario emits a structured
# event that the corresponding agent's handle_message picks up.

def _scenario_solar_string_failure() -> dict:
    """Single string of a deployed solar wing fails open. Cuts solar
    output by ~12 % (1 of 8 strings on a typical ISS-class wing).

    Source: NASA TM-2003-212427 ISS solar array degradation study;
    ISS 2BA wing has 8 SARJs / 24 strings → ~12 % loss per string.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    delta_pct = -12.0  # NASA TM-2003-212427: ~1/8 wing strings ≈ 12 %
    bus.publish(
        "power.solar_string_failure",
        severity="warning", source="failure_injector",
        payload={"delta_power_pct": delta_pct, "string": "wing+Y_str3"},
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "solar_array_wing_+Y", "string_lost": "str3",
            "delta_power_pct": delta_pct}


def _scenario_charge_controller_oscillation() -> dict:
    """MPPT controller oscillation: power flickers ±15 % at 0.3 Hz.

    Source: NASA NTRS 20060020470 — solar array regulator instability
    when array I-V curve is near MPP knee; observed on early ISS PVCUs.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "power.mppt_oscillation",
        severity="warning", source="failure_injector",
        payload={"amplitude_pct": 15.0, "freq_hz": 0.3,  # NTRS 20060020470
                 "duration_s": 600.0},
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "mppt_controller_a", "amplitude_pct": 15.0,
            "freq_hz": 0.3}


def _scenario_battery_cell_short() -> dict:
    """Internal short on one cell of the main battery pack.

    Source: NASA-STD-5017 battery safety; one-cell short reduces pack
    capacity by 1/N and raises pack temperature ~5 °C immediately.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "power.battery_cell_short",
        severity="critical", source="failure_injector",
        payload={"cell_id": "pack_a_cell_07",
                 "capacity_loss_pct": 8.3,   # 1/12 cells in pack
                 "temperature_rise_c": 5.0},  # NASA-STD-5017
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "battery_pack_a", "cell": "07",
            "capacity_loss_pct": 8.3}


def _scenario_eclipse_overrun() -> dict:
    """Eclipse longer than predicted (e.g., partial-conjunction geometry).

    Source: ECSS-E-ST-20C eclipse-period budgeting; treat as +20 %
    over nominal LEO eclipse (typical 35 min × 1.20 = 42 min).
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "power.eclipse_overrun",
        severity="warning", source="failure_injector",
        payload={"extra_minutes": 7.0, "nominal_min": 35.0},  # ECSS-E-ST-20C
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "orbit_geometry", "extra_minutes": 7.0}


def _scenario_radiator_blockage() -> dict:
    """Radiator panel surface contamination (e.g., ammonia leak crystals)
    cuts effective emissivity. Source: NASA TM-2009-215586 — ISS ammonia
    leak crystallisation observed Dec 2012; ε drops 0.85 → 0.55 (-35 %).
    """
    from aria.simulator.propulsion_thermal import get_propulsion_thermal
    pt = get_propulsion_thermal()
    pt.radiator_capacity_w *= 0.65   # 35 % loss — NASA TM-2009-215586
    return {"target": "radiator_panel_4",
            "new_capacity_w": pt.radiator_capacity_w,
            "note": "emissivity dropped 0.85→0.55 (NH3 crystals)"}


def _scenario_coolant_loop_air() -> dict:
    """Air ingress in the internal thermal control loop. Source: NASA
    TM-2010-216758 — ISS ITCS air-bubble events reduce flow rate ~20 %.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "thermal.coolant_air_ingress",
        severity="warning", source="failure_injector",
        payload={"flow_loss_pct": 20.0,  # NASA TM-2010-216758
                 "loop": "ITCS_loop_b"},
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "itcs_loop_b", "flow_loss_pct": 20.0}


def _scenario_peltier_runaway() -> dict:
    """Thermo-electric cooler thermal runaway in equipment rack.
    Source: ESA ECSS-E-ST-31C thermal control margin; a 40 W TEC stuck
    on can raise rack air temp ~6 °C in 10 min.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "thermal.peltier_runaway",
        severity="warning", source="failure_injector",
        payload={"rack": "rack_3", "power_w": 40.0,        # ECSS-E-ST-31C
                 "predicted_rise_c_per_10min": 6.0},
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "rack_3_tec", "power_w": 40.0}


def _scenario_sun_facing_panel_overheat() -> dict:
    """Avionics panel facing the Sun loses its sun-shield deployment.
    Source: ECSS-E-ST-31C — direct-solar absorptivity at 1 AU brings a
    bare aluminium panel to ~120 °C steady-state vs the 60 °C qual limit.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "thermal.sun_panel_overheat",
        severity="critical", source="failure_injector",
        payload={"panel": "avionics_+Z",
                 "predicted_temp_c": 120.0,   # ECSS-E-ST-31C bare-Al at 1 AU
                 "qual_limit_c": 60.0},
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "avionics_+Z_panel", "predicted_temp_c": 120.0}


def _scenario_hab_ring_temp_gradient() -> dict:
    """Habitat-ring temperature gradient: shaded side 15 °C cooler than
    sun side. Source: NASA SP-2010-3407 NTRS — habitat thermal stratification
    threshold for crew comfort is ±5 °C; this scenario triples it.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "thermal.habitat_gradient",
        severity="warning", source="failure_injector",
        payload={"gradient_c": 15.0,        # 3× NASA SP-2010-3407 limit
                 "sun_side_c": 24.0, "shaded_side_c": 9.0},
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "habitat_ring", "gradient_c": 15.0}


def _scenario_co2_scrubber_breakthrough() -> dict:
    """4BMS-style CO2 scrubber bed saturation. Source: NASA/TP-2015-218570
    BVAD — CDRA bed breakthrough sends ppCO2 over the 1000 Pa SMAC.
    """
    from aria.simulator.eclss_contaminants import get_eclss_contaminants
    ec = get_eclss_contaminants()
    ec.scrubber_efficiency_frac = min(ec.scrubber_efficiency_frac, 0.20)
    return {"target": "cdra_bed_a", "scrubber_eff_frac": ec.scrubber_efficiency_frac,
            "spec_smac_pa": 1000.0}  # NASA/TP-2015-218570 24-hr SMAC


def _scenario_water_recycler_jam() -> dict:
    """Urine processor distillation assembly jam. Source: NASA TM-2012-217354
    UPA failures led to 4-day water margin events on ISS.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "eclss.water_recycler_jam",
        severity="critical", source="failure_injector",
        payload={"unit": "UPA_distillation",
                 "estimated_repair_days": 4.0,   # NASA TM-2012-217354
                 "water_margin_days": 4.0},
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "upa_distillation", "repair_days": 4.0}


def _scenario_o2_partial_pressure_drop() -> dict:
    """OGS Sabatier reactor stalls; ppO2 drifts down 21 → 18 kPa over hours.
    Source: NASA SSP 50260 Atmospheric Composition spec — alarm threshold
    19.5 kPa.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "eclss.o2_partial_pressure_drop",
        severity="critical", source="failure_injector",
        payload={"current_kpa": 18.0, "alarm_kpa": 19.5,  # SSP 50260
                 "drift_kpa_per_hr": -0.5},
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "ogs_sabatier", "current_kpa": 18.0}


def _scenario_voc_excursion() -> dict:
    """Volatile organic compound (formaldehyde) excursion above 24-hr SMAC.
    Source: NASA JSC-20584 SMAC list — formaldehyde 24-hr SMAC = 0.04 mg/m³.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "eclss.voc_excursion",
        severity="warning", source="failure_injector",
        payload={"contaminant": "formaldehyde",
                 "current_mg_m3": 0.12, "smac_24h_mg_m3": 0.04},   # JSC-20584
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "cabin_air", "contaminant": "formaldehyde",
            "ratio_to_smac": 3.0}


def _scenario_food_supply_short() -> dict:
    """Food-supply audit shows a 7 % shortfall vs metabolic budget.
    Source: NASA/TP-2015-218570 BVAD — 1.83 kg food per crew per day.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "eclss.food_supply_short",
        severity="warning", source="failure_injector",
        payload={"shortfall_pct": 7.0,
                 "kg_per_crew_day": 1.83},   # NASA/TP-2015-218570 BVAD
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "food_inventory", "shortfall_pct": 7.0}


def _scenario_star_tracker_blinded() -> dict:
    """Stray light from the Moon limb saturates the primary star tracker
    for ~12 minutes around lunar terminator crossings.
    Source: ESA ECSS-E-ST-60-20C star-tracker exclusion-angle 30°.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "navigation.startracker_blinded",
        severity="warning", source="failure_injector",
        payload={"unit": "ST_primary", "duration_min": 12.0,
                 "exclusion_deg": 30.0},   # ECSS-E-ST-60-20C
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "star_tracker_primary", "duration_min": 12.0}


def _scenario_imu_drift_burst() -> dict:
    """IMU bias drift burst: 0.3°/h gyro drift on one of three units.
    Source: SAE AS8013 navigation-grade IMU spec — 0.01°/h nominal,
    0.3°/h is qualification-failure level.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "navigation.imu_drift_burst",
        severity="warning", source="failure_injector",
        payload={"unit": "IMU_b", "drift_deg_per_hr": 0.3,   # SAE AS8013
                 "spec_deg_per_hr": 0.01},
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "imu_b", "drift_deg_per_hr": 0.3}


def _scenario_gnc_attitude_runaway() -> dict:
    """ADCS commanded slew exceeds rate-limit and triggers reaction-wheel
    saturation. Source: ECSS-E-ST-60-30C attitude rate limits — 0.5°/s
    for crewed vehicles in cruise.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "navigation.attitude_runaway",
        severity="critical", source="failure_injector",
        payload={"commanded_rate_deg_s": 1.4,
                 "limit_deg_s": 0.5},   # ECSS-E-ST-60-30C
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "adcs_loop", "commanded_rate_deg_s": 1.4}


def _scenario_gps_loss() -> dict:
    """LEO/cis-lunar GPS signal loss for 8 minutes (multi-jamming event).
    Source: GPS-PS-200 SPS performance standard — outage tolerance < 1 hr.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "navigation.gps_loss",
        severity="warning", source="failure_injector",
        payload={"duration_min": 8.0,
                 "spec_max_outage_hr": 1.0},   # GPS-PS-200
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "gps_receiver", "duration_min": 8.0}


def _scenario_hga_pointing_loss() -> dict:
    """High-gain antenna pointing drift exceeds half-power beamwidth.
    Source: NASA DSN 810-005 telecom design — Ka-band HPBW ≈ 0.05° for
    typical 4 m HGA → losing pointing drops link budget ~3 dB.
    """
    from aria.simulator.comms_budget import get_comms_budget
    cb = get_comms_budget()
    cb.snr_db = max(cb.snr_db - 3.0, -20.0)   # DSN 810-005 link-budget hit
    return {"target": "hga", "snr_loss_db": 3.0,
            "new_snr_db": round(cb.snr_db, 1)}


def _scenario_lga_failover() -> dict:
    """Forced fall-back to low-gain antenna; bandwidth collapses to 1 kbps.
    Source: NASA Apollo-era LGA = ~1 kbps emergency telemetry.
    """
    from aria.simulator.comms_budget import get_comms_budget
    cb = get_comms_budget()
    cb.achievable_bps = min(cb.achievable_bps, 1_000.0)   # 1 kbps Apollo LGA
    cb.link_modulation = "LGA_FSK"
    return {"target": "antenna_chain", "new_bps": cb.achievable_bps}


def _scenario_downlink_collapse() -> dict:
    """DSN aperture array contention: link drops to 100 bps for 6 hours.
    Source: NASA DSN scheduling — high-priority spacecraft can pre-empt
    sub-priority links during planetary encounters.
    """
    from aria.simulator.comms_budget import get_comms_budget
    cb = get_comms_budget()
    cb.achievable_bps = 100.0   # DSN pre-emption telemetry-only
    return {"target": "downlink", "new_bps": 100.0, "duration_hr": 6.0}


def _scenario_encryption_handshake_fail() -> dict:
    """End-to-end key rotation fails; ground rejects every packet for
    a key window. Source: CCSDS 350.0-G-2 key management — typical key
    epoch is 24 hours; mid-epoch rotation failure is a known fault mode.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "comms.encryption_handshake_fail",
        severity="warning", source="failure_injector",
        payload={"key_epoch_hr": 24.0,   # CCSDS 350.0-G-2
                 "rejected_packets": 1_240},
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "uplink_keymgr", "rejected_packets": 1_240}


def _scenario_propulsion_valve_stuck() -> dict:
    """Pyro-actuated isolation valve stuck closed; engine cluster A
    inoperable. Source: NASA-STD-5017 propulsion-valve qualification —
    one-failure tolerance required.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "propulsion.valve_stuck_closed",
        severity="critical", source="failure_injector",
        payload={"valve": "main_iso_a",
                 "thrust_loss_pct": 50.0,   # 1/2 cluster ≈ 50 %
                 "qual_spec": "NASA-STD-5017"},
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "main_iso_valve_a", "thrust_loss_pct": 50.0}


def _scenario_mixture_ratio_excursion() -> dict:
    """O/F ratio drifts 5.5 → 6.4 (high-O/F) for 30 s; engine runs hot.
    Source: NASA SP-125 (Sutton) liquid-rocket O/F dispersion ≤ 3 %; this
    is 16 % off-nominal.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "propulsion.mixture_ratio_excursion",
        severity="critical", source="failure_injector",
        payload={"of_ratio": 6.4, "nominal": 5.5,
                 "spec_dispersion_pct": 3.0,  # NASA SP-125
                 "duration_s": 30.0},
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "main_engine", "of_ratio": 6.4, "duration_s": 30.0}


def _scenario_igniter_failure() -> dict:
    """Spark igniter on Engine 2 fails; auto-relight system kicks in.
    Source: NASA-STD-6016 ignition-system redundancy requirement.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "propulsion.igniter_failure",
        severity="warning", source="failure_injector",
        payload={"engine": "engine_2",
                 "redundant_unit": "engine_2_alt",
                 "spec": "NASA-STD-6016"},
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "engine_2_igniter", "auto_relight": True}


def _scenario_throttle_oscillation() -> dict:
    """Closed-loop throttle servo oscillation ±8 % at 4 Hz.
    Source: NASA SP-194 LM descent-engine pogo studies — 1-2 Hz coupling
    threshold; 4 Hz mechanical-only.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "propulsion.throttle_oscillation",
        severity="warning", source="failure_injector",
        payload={"amplitude_pct": 8.0, "freq_hz": 4.0},   # NASA SP-194
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "throttle_servo", "amplitude_pct": 8.0}


def _scenario_radiation_dose_spike() -> dict:
    """Solar particle event delivers an extra 15 mSv hourly dose to crew.
    Source: NCRP 132 / NASA SP-2009-3405 — 30-day BFO limit 250 mSv; SPE
    can deliver 25-50 mSv to skin behind 5 g/cm² in a few hours.
    """
    from aria.simulator.crew_health import get_crew_health
    ch = get_crew_health()
    bus = get_event_bus()
    phase = get_phase_controller()
    spike_msv = 15.0   # SPE skin-dose hourly fragment, NCRP 132
    bus.publish(
        "crew.radiation_spike",
        severity="critical", source="failure_injector",
        payload={"hourly_msv": spike_msv,
                 "30day_bfo_limit_msv": 250.0},
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "crew", "spike_msv": spike_msv}


def _scenario_medical_cardiac() -> dict:
    """One crew member presents acute coronary syndrome.
    Source: NASA STD-3001 medical contingency planning — 0.1 events / yr / 1000-crew baseline.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "crew.medical_emergency",
        severity="critical", source="failure_injector",
        payload={"presentation": "acute_coronary_syndrome",
                 "rate_per_1000crew_yr": 0.1},   # NASA STD-3001
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "crew", "presentation": "acute_coronary_syndrome"}


def _scenario_sleep_deprivation_cascade() -> dict:
    """Crew schedule slip → 3 nights of <5 h sleep across 60 % of crew.
    Source: NASA TM-2014-217376 sleep & performance — < 6 h chronically
    degrades cognitive performance equivalently to 0.05 % BAC.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "crew.sleep_deprivation",
        severity="warning", source="failure_injector",
        payload={"affected_frac": 0.60, "nights": 3,
                 "avg_hr": 4.5, "spec_min_hr": 6.0},   # NASA TM-2014-217376
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "crew_schedule", "affected_frac": 0.60}


def _scenario_decompression_micro() -> dict:
    """Slow micro-leak in Hatch-3 seal: cabin pressure drops 0.5 kPa/hr.
    Source: NASA SSP 41172 cabin pressure spec — alarm at -1.4 kPa/hr.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "eclss.micro_leak",
        severity="warning", source="failure_injector",
        payload={"location": "hatch_3_seal",
                 "rate_kpa_per_hr": -0.5,
                 "alarm_kpa_per_hr": -1.4},   # NASA SSP 41172
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "hatch_3_seal", "rate_kpa_per_hr": -0.5}


def _scenario_infectious_outbreak() -> dict:
    """Norovirus-like cluster: 4 crew symptomatic in 24 hr.
    Source: NASA TM-2009-214779 immune dysregulation in flight; reactivation
    of latent viruses observed in 47 % of long-duration crew.
    """
    bus = get_event_bus()
    phase = get_phase_controller()
    bus.publish(
        "crew.infectious_cluster",
        severity="warning", source="failure_injector",
        payload={"cases_24h": 4, "agent": "norovirus_like",
                 "latent_reactivation_rate_pct": 47.0},   # NASA TM-2009-214779
        sim_time_yr=phase.elapsed_yr,
    )
    return {"target": "crew_health", "cases_24h": 4}


SCENARIOS: Dict[str, Scenario] = {s.id: s for s in [
    Scenario(
        id="maglev_trip",
        label="Maglev Controller Trip",
        description="Force the habitat-ring magnetic bearing to fall back to roller",
        impact="Loading transfers to mechanical rollers; L₁₀ life starts ticking",
        severity="warning",
        apply=_scenario_maglev_trip,
    ),
    Scenario(
        id="radiator_loss",
        label="Radiator Wing -Y loss",
        description="Halves total radiator capacity (one wing destroyed by MMOD)",
        impact="Thermal margin drops; auto-throttle may kick in during BOOST",
        severity="critical",
        apply=_scenario_radiator_loss,
    ),
    Scenario(
        id="eclss_scrubber_fault",
        label="ECLSS Scrubber 90% Degraded",
        description="Drops scrubber efficiency to 10 % (catalytic oxidiser failure)",
        impact="Trace contaminants will breach SMAC over days; alarms fire",
        severity="critical",
        apply=_scenario_eclss_scrubber_fault,
    ),
    Scenario(
        id="fuel_leak_a",
        label="Fuel Tank A Leak",
        description="30 % of D/He-3 in tank A vented to space",
        impact="Total propellant down ~10 %; ΔV margin reduced",
        severity="warning",
        apply=_scenario_main_fuel_leak,
    ),
    Scenario(
        id="shield_ice_mmod",
        label="Shield L4 MMOD Strike",
        description="Micrometeoroid impact on ablation ice (5 t lost)",
        impact="GCR dose attenuation slightly reduced; expect minor health uptick",
        severity="warning",
        apply=_scenario_shield_ice_micrometeoroid,
    ),
    Scenario(
        id="seu_storm",
        label="GCR Flare (×100 SEU rate)",
        description="100× boost to SEU rate — simulates a galactic flare",
        impact="ECC corrects most; watch for halts and escapes",
        severity="warning",
        apply=_scenario_seu_storm,
    ),
    Scenario(
        id="apu_fault",
        label="APU 1 Fault",
        description="Loses one of the two bootstrap APUs",
        impact="No effect during cruise; risk during next cold-start",
        severity="warning",
        apply=_scenario_apu_fault,
    ),
    Scenario(
        id="tmr_burst",
        label="TMR Disagreement Burst",
        description="Forces 5 voter disagreements (radiation-induced)",
        impact="Voter recovers; logged for review",
        severity="warning",
        apply=_scenario_tmr_disagreement_burst,
    ),
    Scenario(
        id="avionics_ecc_cascade",
        label="Avionics ECC Cascade",
        description="8 ECC-halt bit flips + 2 silent escapes in flight computer memory",
        impact="Escapes are silent corruption; compute TMR may paper over but watch for drift",
        severity="critical",
        apply=_scenario_avionics_ecc_cascade,
    ),
    # Power (4)
    Scenario(id="solar_string_failure",
             label="Solar wing string open",
             description="One string of 24 on +Y wing fails open (NASA TM-2003-212427)",
             impact="Solar output -12 %; battery margin tightens during eclipse",
             severity="warning", apply=_scenario_solar_string_failure),
    Scenario(id="charge_controller_oscillation",
             label="MPPT controller oscillation",
             description="Regulator unstable near MPP knee, ±15 % at 0.3 Hz",
             impact="Bus-voltage hunting; PowerAgent should request reasoning",
             severity="warning", apply=_scenario_charge_controller_oscillation),
    Scenario(id="battery_cell_short",
             label="Battery cell internal short",
             description="One pack-A cell shorts (8.3 % capacity loss + 5 °C rise)",
             impact="Pack must be isolated before runaway; DSCC degraded",
             severity="critical", apply=_scenario_battery_cell_short),
    Scenario(id="eclipse_overrun",
             label="Eclipse overrun (+20 %)",
             description="Geometry pushes eclipse 35→42 min (ECSS-E-ST-20C)",
             impact="Battery DoD deeper than budgeted; expect SoC alarm",
             severity="warning", apply=_scenario_eclipse_overrun),
    # Thermal (4)
    Scenario(id="radiator_blockage",
             label="Radiator NH₃ crystallisation",
             description="Emissivity 0.85→0.55 from leaked-ammonia crystals (NASA TM-2009-215586)",
             impact="Capacity -35 %; radiator wing remains structurally fine",
             severity="warning", apply=_scenario_radiator_blockage),
    Scenario(id="coolant_loop_air",
             label="ITCS air ingress",
             description="Bubble forms in loop B; flow -20 % (NASA TM-2010-216758)",
             impact="Equipment temps drift up 5 °C; vent procedure may be needed",
             severity="warning", apply=_scenario_coolant_loop_air),
    Scenario(id="peltier_runaway",
             label="Rack TEC stuck on",
             description="40 W Peltier stuck powered; rack heating 6 °C / 10 min",
             impact="Rack air temp rises; affected rack should be load-shed",
             severity="warning", apply=_scenario_peltier_runaway),
    Scenario(id="sun_panel_overheat",
             label="Sun-shield retracted",
             description="+Z avionics panel sees direct Sun; 120 °C steady-state predicted",
             impact="Above 60 °C qual limit; reorient or shut down +Z avionics",
             severity="critical", apply=_scenario_sun_facing_panel_overheat),
    Scenario(id="hab_ring_gradient",
             label="Habitat-ring temp gradient",
             description="Sun-side 24 °C / shade-side 9 °C — 3× crew-comfort spec",
             impact="Crew thermal stress; spin-attitude bias may help",
             severity="warning", apply=_scenario_hab_ring_temp_gradient),
    # ECLSS (5)
    Scenario(id="co2_breakthrough",
             label="CO₂ scrubber breakthrough",
             description="CDRA bed saturates; ppCO₂ above 1000 Pa SMAC (NASA/TP-2015-218570)",
             impact="Headache risk in 4-6 h; switch to bed B + bake-out cycle",
             severity="critical", apply=_scenario_co2_scrubber_breakthrough),
    Scenario(id="water_recycler_jam",
             label="UPA distillation jam",
             description="Urine processor down ~4 days (NASA TM-2012-217354)",
             impact="Water margin shrinks to 4 days; ration on potable supply",
             severity="critical", apply=_scenario_water_recycler_jam),
    Scenario(id="o2_pressure_drop",
             label="OGS partial-pressure drift",
             description="ppO₂ drifting 21→18 kPa; Sabatier reactor stalled",
             impact="Below 19.5 kPa alarm (SSP 50260); crew O₂ supplemented",
             severity="critical", apply=_scenario_o2_partial_pressure_drop),
    Scenario(id="voc_excursion",
             label="Formaldehyde 3× SMAC",
             description="Cabin VOC 0.12 mg/m³ vs 0.04 24-hr SMAC (JSC-20584)",
             impact="Long-exposure irritation; bake-out + filter change",
             severity="warning", apply=_scenario_voc_excursion),
    Scenario(id="food_supply_short",
             label="Food audit -7 % shortfall",
             description="Inventory below metabolic budget (NASA/TP-2015-218570 BVAD)",
             impact="Mission-extension risk; ration or accelerate resupply",
             severity="warning", apply=_scenario_food_supply_short),
    # Navigation (4)
    Scenario(id="startracker_blinded",
             label="Star tracker blinded by Moon",
             description="Stray light from lunar limb saturates ST-primary 12 min (ECSS-E-ST-60-20C)",
             impact="Attitude solution falls back to IMU-only; expect drift",
             severity="warning", apply=_scenario_star_tracker_blinded),
    Scenario(id="imu_drift_burst",
             label="IMU bias drift burst",
             description="IMU-B drift 0.3°/h vs 0.01°/h spec (SAE AS8013)",
             impact="Vote out IMU-B; relying on A/C until recalibration",
             severity="warning", apply=_scenario_imu_drift_burst),
    Scenario(id="attitude_runaway",
             label="ADCS attitude runaway",
             description="Commanded slew 1.4°/s vs 0.5°/s limit (ECSS-E-ST-60-30C)",
             impact="Reaction wheels saturate; safe-mode likely",
             severity="critical", apply=_scenario_gnc_attitude_runaway),
    Scenario(id="gps_loss",
             label="GPS outage 8 min",
             description="Multi-jamming event; GPS dropout 8 min (GPS-PS-200)",
             impact="Position fix degrades to IMU dead-reckoning",
             severity="warning", apply=_scenario_gps_loss),
    # Comms (4)
    Scenario(id="hga_pointing_loss",
             label="HGA pointing drift",
             description="HGA off half-power beamwidth; -3 dB link (DSN 810-005)",
             impact="Downlink margin shrinks; bit error rate climbs",
             severity="warning", apply=_scenario_hga_pointing_loss),
    Scenario(id="lga_failover",
             label="HGA → LGA failover",
             description="High-gain failure forces low-gain at 1 kbps",
             impact="Bandwidth collapse; telemetry only, no high-rate science",
             severity="critical", apply=_scenario_lga_failover),
    Scenario(id="downlink_collapse",
             label="DSN pre-emption (100 bps)",
             description="DSN scheduler pre-empts our slot; 100 bps for 6 hr",
             impact="Drain telemetry queue locally; resume after window",
             severity="warning", apply=_scenario_downlink_collapse),
    Scenario(id="encryption_handshake_fail",
             label="Key rotation failure",
             description="CCSDS 350.0-G-2 mid-epoch key exchange fails; ground rejects packets",
             impact="No commands accepted until handshake recovers (~30 min)",
             severity="warning", apply=_scenario_encryption_handshake_fail),
    # Propulsion (4)
    Scenario(id="propulsion_valve_stuck",
             label="Main iso valve stuck closed",
             description="Pyro valve A stuck; thrust -50 % (NASA-STD-5017)",
             impact="Cluster A inoperable; rebalance ΔV via cluster B",
             severity="critical", apply=_scenario_propulsion_valve_stuck),
    Scenario(id="mixture_ratio_excursion",
             label="O/F excursion 5.5→6.4",
             description="O/F 16 % off spec for 30 s (NASA SP-125 dispersion ≤3 %)",
             impact="Engine runs hot; chamber temp spike, possible erosion",
             severity="critical", apply=_scenario_mixture_ratio_excursion),
    Scenario(id="igniter_failure",
             label="Engine 2 igniter failure",
             description="Spark igniter off; redundant unit auto-relights (NASA-STD-6016)",
             impact="Brief pressure dip; cluster nominal after relight",
             severity="warning", apply=_scenario_igniter_failure),
    Scenario(id="throttle_oscillation",
             label="Throttle servo oscillation",
             description="±8 % at 4 Hz on closed-loop throttle (NASA SP-194)",
             impact="Vibration coupling risk; reduce throttle or hold attitude",
             severity="warning", apply=_scenario_throttle_oscillation),
    # Crew & medical (5)
    Scenario(id="radiation_dose_spike",
             label="SPE +15 mSv/hr",
             description="Solar particle event hourly skin dose (NCRP 132)",
             impact="Crew shelter in shielded vault; mission Δv may be deferred",
             severity="critical", apply=_scenario_radiation_dose_spike),
    Scenario(id="medical_cardiac",
             label="Crew acute coronary",
             description="One crew presents ACS (NASA STD-3001)",
             impact="Medical bay activated; mission tempo reduces to crew‑safe",
             severity="critical", apply=_scenario_medical_cardiac),
    Scenario(id="sleep_deprivation",
             label="Crew sleep deprivation",
             description="3 nights <5 h for 60 % of crew (NASA TM-2014-217376)",
             impact="Cognitive ≈ 0.05 % BAC; restrict critical ops; reschedule",
             severity="warning", apply=_scenario_sleep_deprivation_cascade),
    Scenario(id="decompression_micro",
             label="Hatch-3 micro-leak",
             description="0.5 kPa/hr loss; below alarm but persistent (NASA SSP 41172)",
             impact="Locate via tape-test; budget repair window",
             severity="warning", apply=_scenario_decompression_micro),
    Scenario(id="infectious_cluster",
             label="Norovirus-like outbreak",
             description="4 crew symptomatic in 24 hr (NASA TM-2009-214779 immune)",
             impact="Quarantine + cleaning protocol; mission ops paced down",
             severity="warning", apply=_scenario_infectious_outbreak),
]}


def list_scenarios() -> List[Scenario]:
    return list(SCENARIOS.values())


def trigger(scenario_id: str) -> dict:
    sc = SCENARIOS.get(scenario_id)
    if sc is None:
        return {"error": f"Unknown scenario '{scenario_id}'",
                "available": [s.id for s in list_scenarios()]}
    bus = get_event_bus()
    phase = get_phase_controller()
    # Apply the mutation
    result = sc.apply()
    # Publish a single 'failure_injector' event so it shows up in the alarms tab
    bus.publish(
        f"failure_injector.{scenario_id}",
        severity=sc.severity,
        source="failure_injector",
        payload={"label": sc.label, "impact": sc.impact, **result},
        sim_time_yr=phase.elapsed_yr,
    )
    return {
        "id": sc.id,
        "label": sc.label,
        "applied": True,
        "result": result,
        "severity": sc.severity,
        "impact": sc.impact,
    }


def to_dict() -> dict:
    return {
        "scenarios": [
            {"id": s.id, "label": s.label, "description": s.description,
             "impact": s.impact, "severity": s.severity}
            for s in list_scenarios()
        ],
        "count": len(SCENARIOS),
    }
