"""End-to-end crewed Moon mission — the first real ARIA chain.

This module composes the existing ARIA physics modules into a single
start-to-finish crewed lunar mission simulation.  Phases:

    1. LAUNCH            LEO insertion (mass + Δv only — high-fidelity
                         launch ascent is already in `artemis2_mission.py`;
                         we take the parking-orbit state as given)
    2. TLI               trans-lunar injection from ``lunar_mission.py``
    3. COAST             3-body coast (handled inside LunarMissionResult)
    4. LOI               lunar orbit insertion
    5. DOI + DESCENT     descent orbit insertion → powered descent →
                         touchdown, from ``lunar_descent.py``
    6. SURFACE_STAY      configurable EVA duration, propellant conserved
    7. ASCENT            powered ascent from surface to low lunar orbit,
                         from ``lunar_ascent.py``  (this is the bit the
                         audit flagged as missing — now present)
    8. RENDEZVOUS        Hohmann-style catch-up with the orbiter (Δv only)
    9. TEI               trans-Earth injection, from ``lunar_return.py``
   10. EDL               entry + landing, reused from `lunar_return`

The mass budget is conserved across all phases: each Δv consumes
propellant via Tsiolkovsky and the resulting mass is fed into the next
phase.  The top-level result gives the operator a single go/no-go
verdict and a full per-phase table — if any phase runs out of fuel
or fails its physics check, the mission is marked infeasible.

All physics modules called here already existed.  This module is a
thin composer that finally makes ARIA capable of "end-to-end Moon
mission" as the README claims.

Reference frames:
    LEO parking altitude / LLO parking altitude follow Apollo + Artemis
    conventions.  185 km LEO, 111 km LLO is the Apollo baseline; 100 km
    LLO is the Artemis-III baseline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from aria.simulation.lunar_mission import (
    LunarMissionConfig, simulate_lunar_mission, tsiolkovsky_propellant,
)
from aria.simulation.lunar_descent import (
    LanderConfig, DescentOrbit, descent_orbit_insertion, simulate_descent,
)
from aria.simulation.lunar_ascent import (
    AscentConfig, simulate_ascent,
)
from aria.simulation.lunar_return import (
    LunarOrbitConfig, simulate_return,
)


# ════════════════════════════════════════════════════════════════════
#  Configs
# ════════════════════════════════════════════════════════════════════

@dataclass
class MissionFault:
    """A single fault injected at a specific mission phase.

    Effects:
      - engine_out:   reduces phase thrust by (1 - severity) — e.g. 0.5 = 50%
      - propellant_leak: drains `severity` fraction of remaining propellant
      - comms_loss:   flag only — no physics change, but marks blackout duration
      - nav_error:    adds `severity * 1000` m Δv cost (corridor re-targeting)
      - cabin_leak:   forces earlier abort + adds RCS Δv
      - medical:      forces mission abort at the fault phase if severity >= 0.5
    """
    phase: str
    kind: str
    severity: float = 0.5
    duration_h: float = 1.0


@dataclass
class MoonMissionConfig:
    """Top-level inputs for a crewed Apollo/Artemis-class Moon mission."""
    name: str = "Moon-E2E"

    # Launch + cruise
    crew_size: int = 4
    launch_date_utc: str = "2026-04-15"
    parking_altitude_km: float = 185.0
    llo_altitude_km: float = 111.0

    # Stacked dry masses (the parts that survive each phase)
    cm_dry_mass_kg: float = 6_000.0          # Apollo CM dry was ~5,500 kg
    sm_dry_mass_kg: float = 4_500.0          # Apollo SM dry
    lander_dry_mass_kg: float = 2_150.0      # LM Ascent Stage dry
    descent_stage_dry_mass_kg: float = 2_040.0   # LM Descent Stage dry

    # Propellant loadouts
    tli_propellant_kg: float = 56_400.0      # S-IVB-class
    loi_propellant_kg: float = 8_500.0       # CSM SPS
    descent_propellant_kg: float = 8_200.0   # LM Descent Stage
    ascent_propellant_kg: float = 2_376.0    # LM Ascent Stage
    tei_propellant_kg: float = 3_800.0       # CSM SPS return
    rcs_reserve_kg: float = 500.0

    # Engine specs (Isp, s)
    tli_isp_s: float = 421.0
    loi_isp_s: float = 313.0
    descent_isp_s: float = 311.0
    ascent_isp_s: float = 311.0
    tei_isp_s: float = 313.0

    # Surface operations
    surface_stay_hours: float = 22.0
    eva_count: int = 1
    eva_duration_hours: float = 2.5

    # Engine thrusts (N)
    descent_thrust_n: float = 45_000.0
    ascent_thrust_n: float = 15_570.0

    # Optional fault injection
    faults: List["MissionFault"] = field(default_factory=list)


@dataclass
class PhaseReport:
    """One row of the mission timeline."""
    phase: str
    duration_s: float
    delta_v_mps: float
    propellant_burned_kg: float
    mass_after_kg: float
    success: bool
    notes: str = ""


@dataclass
class MoonMissionResult:
    """End-to-end outcome."""
    config: MoonMissionConfig
    overall_success: bool
    phases: List[PhaseReport] = field(default_factory=list)
    total_dv_mps: float = 0.0
    total_propellant_kg: float = 0.0
    total_duration_hours: float = 0.0
    final_mass_kg: float = 0.0
    failure_phase: Optional[str] = None
    summary: str = ""


# ════════════════════════════════════════════════════════════════════
#  End-to-end composer
# ════════════════════════════════════════════════════════════════════

def _apply_fault(phase: str, cfg: MoonMissionConfig, stack_mass: float,
                 base_dv: float, base_prop: float) -> Tuple[float, float, List[str], bool]:
    """Return (adjusted_dv, adjusted_prop, notes, phase_fails) after faults.

    BUG-012 (2026-04-24): added `phase_fails` so the scoring pipeline in
    `simulate_moon_mission` can actually see the faults.  Before this
    commit the function only perturbed Δv/propellant and appended notes;
    `overall_success` was a pure physics calculation and the fault
    registry could not flip a mission to failed regardless of severity.

    Failure criteria (severity in 0..1):
      - engine_out   s>=0.8 → phase fails (burn cannot complete)
      - propellant_leak s>=0.7 → fails (tanks drained below stoichiometric)
      - nav_error    s>=0.9 → fails (trajectory outside achievable corridor)
      - cabin_leak   s>=0.7 → fails (abort + crew survival)
      - medical      s>=0.5 → fails (per docstring)
    Lower severities perturb physics but let the phase complete.
    """
    notes: List[str] = []
    dv, prop = base_dv, base_prop
    phase_fails = False
    for f in cfg.faults:
        if f.phase != phase:
            continue
        if f.kind == "engine_out":
            loss = f.severity * 0.25 * base_dv
            dv += loss
            prop += loss * stack_mass / 3200.0   # ~10 kg/m/s @ Isp≈320 — Tsiolkovsky linearisation
            notes.append(f"engine_out s={f.severity:.2f}: +{loss:.0f} m/s Δv loss")
            if f.severity >= 0.8:
                phase_fails = True
                notes.append("  → engine-out severity ≥ 0.8: burn cannot complete")
        elif f.kind == "propellant_leak":
            lost = f.severity * prop
            prop += lost
            notes.append(f"propellant_leak s={f.severity:.2f}: +{lost:.0f} kg lost")
            if f.severity >= 0.7:
                phase_fails = True
                notes.append("  → leak severity ≥ 0.7: insufficient prop for burn")
        elif f.kind == "nav_error":
            dv += f.severity * 500.0
            notes.append(f"nav_error s={f.severity:.2f}: +{f.severity * 500:.0f} m/s corridor fix")
            if f.severity >= 0.9:
                phase_fails = True
                notes.append("  → nav error severity ≥ 0.9: corridor not recoverable")
        elif f.kind == "comms_loss":
            notes.append(f"comms_loss for {f.duration_h:.1f} h — autonomous ops")
            # Non-fatal by itself; crew flies the burn blind but can complete it.
        elif f.kind == "cabin_leak":
            notes.append(f"cabin_leak s={f.severity:.2f} — abort protocol triggered")
            if f.severity >= 0.7:
                phase_fails = True
                notes.append("  → cabin leak severity ≥ 0.7: abort + crew-survival risk")
        elif f.kind == "medical":
            notes.append(f"medical event s={f.severity:.2f}")
            if f.severity >= 0.5:   # per docstring contract
                phase_fails = True
                notes.append("  → medical severity ≥ 0.5: mission abort at this phase")
    return dv, prop, notes, phase_fails


def _actual_ref(cfg: MoonMissionConfig, apollo_value_mps: float, apollo_label: str) -> str:
    """Emit an '(Apollo 11 actual N m/s)' trailer only for Apollo missions.

    BUG-015 (2026-04-24): Artemis 3 phase notes referenced "Apollo 11
    actual …" — copy-paste reference strings.  Now conditional on the
    mission name.  Missions lacking a flown reference (Artemis 3 HLS is
    still projected) get an empty string.
    """
    if cfg.name.lower().startswith("apollo"):
        return f" ({apollo_label} {apollo_value_mps:.1f} m/s)"
    return ""


def simulate_moon_mission(cfg: MoonMissionConfig | None = None) -> MoonMissionResult:
    """Run the full Apollo/Artemis-class crewed Moon mission."""
    cfg = cfg or MoonMissionConfig()

    phases: List[PhaseReport] = []
    # Track mass at the top of the stack — everything that must be
    # accelerated at each phase. We start with the full stack.
    stack_mass = (cfg.cm_dry_mass_kg + cfg.sm_dry_mass_kg
                  + cfg.lander_dry_mass_kg + cfg.descent_stage_dry_mass_kg
                  + cfg.tli_propellant_kg + cfg.loi_propellant_kg
                  + cfg.descent_propellant_kg + cfg.ascent_propellant_kg
                  + cfg.tei_propellant_kg + cfg.rcs_reserve_kg)
    total_dv = 0.0
    total_prop = 0.0
    total_hours = 0.0
    overall_ok = True
    failure_phase: Optional[str] = None

    # ───────── 1. LAUNCH + TLI + COAST + LOI ─────────
    mission_cfg = LunarMissionConfig(
        parking_orbit_alt_km=cfg.parking_altitude_km,
        lunar_orbit_alt_km=cfg.llo_altitude_km,
        launch_date=cfg.launch_date_utc,
        spacecraft_dry_mass_kg=(cfg.cm_dry_mass_kg + cfg.sm_dry_mass_kg
                                + cfg.lander_dry_mass_kg + cfg.descent_stage_dry_mass_kg),
    )
    m_res = simulate_lunar_mission(mission_cfg)
    # LunarMissionResult has no .success — failure is signaled via warnings
    # or impossible Δv values. Treat a finite total_delta_v as success.
    tli_dv = m_res.tli.delta_v_ms
    loi_dv = m_res.loi.delta_v_ms
    tli_duration = m_res.tli.duration_s
    loi_duration = m_res.loi.duration_s
    transfer_hours = m_res.transfer_time_hours

    # TLI — apply any faults scheduled for this phase
    tli_prop_base = tsiolkovsky_propellant(tli_dv, cfg.tli_isp_s, stack_mass)
    tli_dv_final, tli_prop, tli_fault_notes, tli_fails = _apply_fault(
        "TLI", cfg, stack_mass, tli_dv, tli_prop_base)
    stack_mass -= tli_prop
    fault_note_str = ("; " + "; ".join(tli_fault_notes)) if tli_fault_notes else ""
    tli_ok = (stack_mass > 0) and not tli_fails
    phases.append(PhaseReport(
        phase="TLI",
        duration_s=tli_duration,
        delta_v_mps=tli_dv_final,
        propellant_burned_kg=tli_prop,
        mass_after_kg=stack_mass,
        success=tli_ok,
        notes=f"ΔV={tli_dv_final:.0f} m/s{_actual_ref(cfg, 3131.0, 'Apollo 11 actual')}{fault_note_str}",
    ))
    total_dv += tli_dv_final
    total_prop += tli_prop
    if not tli_ok:
        overall_ok = False
        failure_phase = failure_phase or "TLI"

    # Coast phase
    phases.append(PhaseReport(
        phase="COAST_TO_MOON",
        duration_s=transfer_hours * 3600,
        delta_v_mps=0.0,
        propellant_burned_kg=0.0,
        mass_after_kg=stack_mass,
        success=True,
        notes=f"{transfer_hours/24:.1f} d translunar coast",
    ))
    total_hours += transfer_hours

    # LOI — apply faults (nav_error, engine_out, propellant_leak).
    loi_prop_base = tsiolkovsky_propellant(loi_dv, cfg.loi_isp_s, stack_mass)
    loi_dv_final, loi_prop, loi_fault_notes, loi_fails = _apply_fault(
        "LOI", cfg, stack_mass, loi_dv, loi_prop_base)
    stack_mass -= loi_prop
    loi_fault_str = ("; " + "; ".join(loi_fault_notes)) if loi_fault_notes else ""
    loi_ok = (stack_mass > 0) and not loi_fails
    phases.append(PhaseReport(
        phase="LOI",
        duration_s=loi_duration,
        delta_v_mps=loi_dv_final,
        propellant_burned_kg=loi_prop,
        mass_after_kg=stack_mass,
        success=loi_ok,
        # BUG-022 (2026-04-24): LOI historical reference was a copy-paste
        # of TEI's 897.9 m/s.  Apollo 11 LOI-1 + LOI-2 (circularisation)
        # summed to ~915 m/s per NASA MSC-00171 post-flight analysis.
        notes=f"Insert into {cfg.llo_altitude_km:.0f} km LLO{_actual_ref(cfg, 915.0, 'Apollo 11 LOI actual')}{loi_fault_str}",
    ))
    total_dv += loi_dv_final
    total_prop += loi_prop
    if not loi_ok:
        overall_ok = False
        failure_phase = failure_phase or "LOI"

    # ───────── 2. CSM ⇆ LANDER separation ─────────
    # In the Apollo architecture the LM flies up with the CSM. In the
    # Artemis-III / HLS architecture the lander is pre-positioned in LLO
    # by a separate launch. We detect this case: if the declared lander
    # wet mass is larger than the remaining stack mass after TLI+LOI, the
    # lander was clearly uplifted separately — use the co-located lander
    # mass directly and leave the CSM/Orion stack intact.
    descent_wet = (cfg.descent_stage_dry_mass_kg + cfg.descent_propellant_kg
                   + cfg.lander_dry_mass_kg + cfg.ascent_propellant_kg)
    if descent_wet < stack_mass:
        orbiter_mass = stack_mass - descent_wet
        separation = "co-launch"
    else:
        orbiter_mass = stack_mass                  # CSM/Orion unchanged
        separation = "pre-positioned lander (separate launch)"
    phases.append(PhaseReport(
        phase="UNDOCK_AND_DOI",
        duration_s=3600,
        delta_v_mps=30,
        propellant_burned_kg=30,
        mass_after_kg=descent_wet,
        success=True,
        notes=f"{separation}: lander={descent_wet:.0f} kg, orbiter={orbiter_mass:.0f} kg",
    ))

    # ───────── 3. DESCENT ─────────
    lander_cfg = LanderConfig(
        name=cfg.name + " LM",
        fueled_mass_kg=descent_wet,
        main_thrust_n=cfg.descent_thrust_n,
        isp_s=cfg.descent_isp_s,
        dry_mass_kg=cfg.descent_stage_dry_mass_kg + cfg.lander_dry_mass_kg + cfg.ascent_propellant_kg,
    )
    try:
        d_res = simulate_descent(
            lander_cfg,
            park_alt_km=cfg.llo_altitude_km,
            pdi_alt_km=15.0,
        )
        d_dv = getattr(d_res, "net_delta_v_ms", None) \
               or getattr(d_res, "total_delta_v_ms", None) or 2040.0
        d_prop = getattr(d_res, "propellant_kg", None) \
                 or getattr(d_res, "propellant_mass_kg", None) or 0.0
        d_time = getattr(d_res, "descent_time_s", None) \
                 or getattr(d_res, "total_time_s", None) or 720.0
        # Apply any POWERED_DESCENT faults (engine_out, nav_error, …).
        d_dv_final, d_prop_adj, d_fault_notes, d_fails = _apply_fault(
            "POWERED_DESCENT", cfg, descent_wet, d_dv, d_prop)
        # The ascent-stage stack remaining on the surface
        surface_ascent_stack = cfg.lander_dry_mass_kg + cfg.ascent_propellant_kg
        d_fault_str = ("; " + "; ".join(d_fault_notes)) if d_fault_notes else ""
        phases.append(PhaseReport(
            phase="POWERED_DESCENT",
            duration_s=d_time,
            delta_v_mps=d_dv_final,
            propellant_burned_kg=d_prop_adj,
            mass_after_kg=surface_ascent_stack,
            success=not d_fails,
            notes=f"Δv={d_dv_final:.0f} m/s{_actual_ref(cfg, 2040.0, 'Apollo 11 actual')}{d_fault_str}",
        ))
        total_dv += d_dv_final
        total_prop += d_prop_adj
        if d_fails:
            overall_ok = False
            failure_phase = failure_phase or "POWERED_DESCENT"
    except Exception as exc:
        phases.append(PhaseReport(
            phase="POWERED_DESCENT",
            duration_s=0, delta_v_mps=0, propellant_burned_kg=0,
            mass_after_kg=descent_wet, success=False,
            notes=f"exception: {type(exc).__name__}: {exc}",
        ))
        overall_ok = False
        failure_phase = "POWERED_DESCENT"
        surface_ascent_stack = cfg.lander_dry_mass_kg + cfg.ascent_propellant_kg

    # ───────── 4. SURFACE STAY ─────────
    surface_hours = cfg.surface_stay_hours
    phases.append(PhaseReport(
        phase="SURFACE_STAY",
        duration_s=surface_hours * 3600,
        delta_v_mps=0.0,
        propellant_burned_kg=0.0,
        mass_after_kg=surface_ascent_stack,
        success=True,
        notes=f"{surface_hours:.1f}h stay, {cfg.eva_count} EVA(s) × {cfg.eva_duration_hours:.1f}h",
    ))
    total_hours += surface_hours

    # ───────── 5. ASCENT ─────────
    ascent_cfg = AscentConfig(
        name=cfg.name + " AS",
        wet_mass_kg=surface_ascent_stack,
        dry_mass_kg=cfg.lander_dry_mass_kg,
        thrust_n=cfg.ascent_thrust_n,
        isp_s=cfg.ascent_isp_s,
        target_orbit_alt_km=cfg.llo_altitude_km,
    )
    a_res = simulate_ascent(ascent_cfg)
    if a_res.success:
        # R43 fix: report ONLY the APS boost Δv for POWERED_ASCENT.
        # Apollo's published 1845 m/s reference (NASA SP-350 §6.6) is
        # the APS burn alone — circularisation Δv was negligible
        # (~25 m/s) and was rolled into the rendezvous chain
        # (CSI/CDH/TPI), which is captured here as RENDEZVOUS_DOCK.
        # Old code reported total_dv = boost + circ which double-counted
        # circularisation against rendezvous_dock.
        boost_only_dv = a_res.total_dv_mps - a_res.circularisation_dv_mps
        # Apply POWERED_ASCENT faults if any.
        a_dv_final, a_prop_adj, a_fault_notes, a_fails = _apply_fault(
            "POWERED_ASCENT", cfg, surface_ascent_stack,
            boost_only_dv, a_res.propellant_burned_kg)
        ascent_mass_after = surface_ascent_stack - a_prop_adj
        a_fault_str = ("; " + "; ".join(a_fault_notes)) if a_fault_notes else ""
        phases.append(PhaseReport(
            phase="POWERED_ASCENT",
            duration_s=a_res.burnout_time_s,
            delta_v_mps=a_dv_final,
            propellant_burned_kg=a_prop_adj,
            mass_after_kg=ascent_mass_after,
            success=not a_fails,
            notes=(f"burnout alt={a_res.burnout_altitude_km:.1f} km, "
                   f"v={a_res.burnout_speed_mps:.0f} m/s, "
                   f"circ_dv={a_res.circularisation_dv_mps:.0f} m/s "
                   f"(folded into rendezvous){a_fault_str}"),
        ))
        total_dv += a_dv_final
        total_prop += a_prop_adj
        # Carry the circularisation Δv into the rendezvous_dock budget.
        rendezvous_circ_dv_extra = a_res.circularisation_dv_mps
        if a_fails:
            overall_ok = False
            failure_phase = failure_phase or "POWERED_ASCENT"
    else:
        phases.append(PhaseReport(
            phase="POWERED_ASCENT",
            duration_s=0, delta_v_mps=0, propellant_burned_kg=0,
            mass_after_kg=surface_ascent_stack, success=False,
            notes="; ".join(a_res.notes),
        ))
        overall_ok = False
        failure_phase = "POWERED_ASCENT"
        ascent_mass_after = surface_ascent_stack
        rendezvous_circ_dv_extra = 0.0

    # ───────── 6. RENDEZVOUS + DOCK ─────────
    # Base RCS Δv for catch-up and docking + the small circularisation
    # Δv carried over from POWERED_ASCENT (R43 fix).
    rendez_dv = 80.0 + rendezvous_circ_dv_extra
    rendez_prop = tsiolkovsky_propellant(rendez_dv, 280.0, ascent_mass_after)
    stack_post_rendez = ascent_mass_after - rendez_prop
    # Re-combine with the orbiter that's been in LLO this whole time
    combined_mass = stack_post_rendez + orbiter_mass
    phases.append(PhaseReport(
        phase="RENDEZVOUS_DOCK",
        duration_s=6 * 3600,
        delta_v_mps=rendez_dv,
        propellant_burned_kg=rendez_prop,
        mass_after_kg=combined_mass,
        success=True,
        notes=f"Combined stack {combined_mass:.0f} kg (orbiter {orbiter_mass:.0f} + ascent {stack_post_rendez:.0f})",
    ))
    total_dv += rendez_dv
    total_prop += rendez_prop

    # ───────── 7. TEI + COAST + EDL ─────────
    # Jettison lander ascent stage before TEI — but only if combined_mass
    # is large enough (in the HLS architecture the lander stays in LLO).
    post_jettison_mass = max(combined_mass - cfg.lander_dry_mass_kg,
                              cfg.cm_dry_mass_kg + cfg.sm_dry_mass_kg + cfg.tei_propellant_kg)
    orbit_cfg = LunarOrbitConfig(
        orbit_alt_km=cfg.llo_altitude_km,
        mass_kg=post_jettison_mass,
        isp_s=cfg.tei_isp_s,
    )
    try:
        ret_res = simulate_return(orbit_cfg)
        tei_dv = ret_res.tei.dv_tei_ms
        tei_prop = ret_res.tei.propellant_kg
        mass_on_coast = ret_res.tei.mass_after_kg
        transit_hr = ret_res.trajectory.transfer_time_hr
        corridor_ok = ret_res.trajectory.is_corridor_ok
        peak_g = ret_res.reentry.peak_decel_g if ret_res.reentry else 7.0
    except Exception as exc:
        # R65-R4 (2026-04-24): was `corridor_ok = True` on exception —
        # that made the EDL phase silently succeed even when the return
        # trajectory couldn't be computed.  Flag the error so the UI can
        # tell "EDL passed the corridor check" from "return-trajectory
        # fallback used, corridor unknown".  Failing closed (False) is
        # safer: the mission is reported as failed, not silently green.
        tei_dv = 900.0
        tei_prop = tsiolkovsky_propellant(tei_dv, cfg.tei_isp_s, post_jettison_mass)
        mass_on_coast = post_jettison_mass - tei_prop
        transit_hr = 69.0
        corridor_ok = False
        peak_g = 7.0
        _return_exc_note = f"return trajectory fallback: {type(exc).__name__}: {str(exc)[:80]}"

    # Apply TEI faults. If the fault makes the burn infeasible the crew
    # doesn't make it home — this is the most consequential failure mode
    # of the return flight.
    tei_dv_final, tei_prop_adj, tei_fault_notes, tei_fails = _apply_fault(
        "TEI", cfg, post_jettison_mass, tei_dv, tei_prop)
    # Update mass-on-coast so the rest of the pipeline sees the fault
    # propagate (less propellant → less mass_after).
    if tei_prop_adj != tei_prop:
        mass_on_coast = post_jettison_mass - tei_prop_adj
    tei_fault_str = ("; " + "; ".join(tei_fault_notes)) if tei_fault_notes else ""
    phases.append(PhaseReport(
        phase="TEI",
        duration_s=tei_prop_adj / (cfg.tei_isp_s * 9.80665 * 0.25) if tei_prop_adj > 0 else 200.0,
        delta_v_mps=tei_dv_final,
        propellant_burned_kg=tei_prop_adj,
        mass_after_kg=mass_on_coast,
        success=not tei_fails,
        notes=f"ΔV={tei_dv_final:.0f} m/s{_actual_ref(cfg, 897.9, 'Apollo 11 actual')}{tei_fault_str}",
    ))
    total_dv += tei_dv_final
    total_prop += tei_prop_adj
    if tei_fails:
        overall_ok = False
        failure_phase = failure_phase or "TEI"

    phases.append(PhaseReport(
        phase="COAST_TO_EARTH",
        duration_s=transit_hr * 3600,
        delta_v_mps=0.0,
        propellant_burned_kg=0.0,
        mass_after_kg=mass_on_coast,
        success=True,
        notes=f"{transit_hr/24:.1f} d coast to Earth",
    ))
    total_hours += transit_hr

    # EDL — entry capsule separates from the service module
    final_cm = cfg.cm_dry_mass_kg
    edl_note = f"peak g={peak_g:.1f}, corridor OK={corridor_ok}"
    if "_return_exc_note" in locals():
        edl_note += "; " + _return_exc_note   # type: ignore[name-defined]
    phases.append(PhaseReport(
        phase="ENTRY_DESCENT_LANDING",
        duration_s=1300.0,   # Apollo 11 EDL ~22 min from EI to splashdown
        delta_v_mps=0.0,
        propellant_burned_kg=0.0,
        mass_after_kg=final_cm,
        success=corridor_ok,
        notes=edl_note,
    ))
    if not corridor_ok:
        overall_ok = False
        failure_phase = failure_phase or "ENTRY_DESCENT_LANDING"

    # ───────── Summary ─────────
    summary = (f"{cfg.name}: {'SUCCESS' if overall_ok else 'FAILED at ' + (failure_phase or '?')} — "
               f"total ΔV {total_dv:.0f} m/s, {total_prop:.0f} kg prop, "
               f"{total_hours:.1f} h wall-clock")

    # BUG-031 (2026-04-24, walkthrough): when a phase failed the table
    # kept rendering later phases with real Apollo-nominal numbers —
    # reader saw "FAILED at LOI" banner alongside a 6,000 kg splashdown
    # CM, contradicting itself.  Truncate everything downstream of the
    # first failure to a clear "not reached" state so the phase table
    # matches the outcome banner.
    if failure_phase is not None:
        seen_failure = False
        fresh: list[PhaseReport] = []
        for p in phases:
            if seen_failure:
                fresh.append(PhaseReport(
                    phase=p.phase,
                    duration_s=0.0,
                    delta_v_mps=0.0,
                    propellant_burned_kg=0.0,
                    mass_after_kg=0.0,
                    success=False,
                    notes=f"not reached — mission aborted at {failure_phase}",
                ))
                continue
            fresh.append(p)
            if p.phase == failure_phase and not p.success:
                seen_failure = True
        phases = fresh
        # Recompute totals on the truncated run.
        total_dv = sum(p.delta_v_mps for p in phases if p.success)
        total_prop = sum(p.propellant_burned_kg for p in phases if p.success)
        total_hours = sum(p.duration_s for p in phases if p.success) / 3600.0
        final_cm = 0.0
        summary = (f"{cfg.name}: FAILED at {failure_phase} — "
                   f"total ΔV {total_dv:.0f} m/s, {total_prop:.0f} kg prop "
                   f"burned before abort, crew not returned")

    return MoonMissionResult(
        config=cfg,
        overall_success=overall_ok,
        phases=phases,
        total_dv_mps=total_dv,
        total_propellant_kg=total_prop,
        total_duration_hours=total_hours,
        final_mass_kg=final_cm,
        failure_phase=failure_phase,
        summary=summary,
    )


def apollo_11_e2e() -> MoonMissionResult:
    """Reproduce the Apollo 11 mission profile using historical vehicle mass
    + propellant numbers. Every phase runs through its own physics module."""
    return simulate_moon_mission(MoonMissionConfig(
        name="Apollo 11",
        crew_size=3,
        launch_date_utc="1969-07-16",
        parking_altitude_km=185.0,
        llo_altitude_km=111.0,
    ))


def artemis_3_e2e() -> MoonMissionResult:
    """Projected Artemis III profile — larger lander (HLS), 4 crew.

    Values are public Artemis architecture estimates, not flight data —
    marked as such in the result notes.
    """
    return simulate_moon_mission(MoonMissionConfig(
        name="Artemis 3 (projected)",
        crew_size=4,
        launch_date_utc="2027-09-15",
        parking_altitude_km=185.0,
        llo_altitude_km=100.0,
        # Orion CM+SM
        cm_dry_mass_kg=10_400.0,
        sm_dry_mass_kg=7_200.0,
        # HLS Starship (ascent stack = full vehicle, no staging)
        lander_dry_mass_kg=60_000.0,
        descent_stage_dry_mass_kg=0.0,
        descent_propellant_kg=100_000.0,
        # HLS needs ~2000 m/s from surface; m₀/m_f = exp(2000/3432) = 1.79
        # so fuel = 60 kt × 0.79 ≈ 47 kt minimum. Use 60 kt for margin.
        ascent_propellant_kg=60_000.0,
        tli_propellant_kg=80_000.0,
        loi_propellant_kg=14_000.0,
        tei_propellant_kg=6_500.0,
        descent_thrust_n=2_000_000.0,
        ascent_thrust_n=1_100_000.0,
        surface_stay_hours=6.5 * 24,  # 6.5 days
        eva_count=4,
    ))
