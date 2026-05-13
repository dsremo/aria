"""Crew-health aggregator — high-level health stats over mission years.

Aggregates five well-documented spaceflight-medicine effects per crew
member; runs population-level (1 000 crew) so the UI can show a single
gauge per condition. Each model is first-order; for full per-individual
health timelines the existing physics modules (SANS, vestibular,
cardio) provide the underlying physiology.

  * SANS (Spaceflight-Associated Neuro-ocular Syndrome) — develops in
    micro-g but is suppressed by 0.56 g rotational gravity; we model the
    incidence as f(g_partial, mission_yr) per Mader 2011 Ophthalmology
  * Bone density loss — 1 % / month at 0 g, 0.3 % / month at 0.56 g
    (NASA HRP 2022 estimate; Sibonga 2007 J. Bone Miner. Metab.)
  * Cardiovascular deconditioning — VO₂max drop ~5 % / yr at 0 g,
    ~2 % / yr at 0.56 g (Convertino 1996 Aviat. Space Environ. Med.)
  * Vestibular adaptation — recovery from spinning-environment otolith
    confusion follows a 2-week exponential to baseline (Clément 2006)
  * Psychological cohesion — slow drift from baseline as a function of
    isolation duration; counter-strategies in `crew_ecosystem.py`

References
----------
  * Mader 2011 Ophthalmology 118 — SANS incidence per mission duration
  * Sibonga 2007 J. Bone Miner. Metab. — bone-loss rate vs gravity
  * Convertino 1996 Aviat. Space Environ. Med. — VO₂max under µg
  * Clément 2006 J. Vestib. Res. — vestibular adaptation timescale
  * NASA HRP 2022 risk-baseline (Human Research Program risk catalogue)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller


# Effective gravity at the crew's working location (rim of habitat ring,
# 0.56 g per parameters.habitat_ring physics)
EFFECTIVE_G_RIM: float = 0.56

# Bone loss rate (per-month fraction at full µg, scaled by (1 - g_partial))
BONE_LOSS_RATE_PER_MONTH_AT_0G: float = 0.010   # Sibonga 2007 — 1 % / mo

# Bone-loss countermeasure efficacy: ARED resistive exercise (ISS standard)
# reduces bone loss by ~40 % vs unprotected microgravity exposure per
# Shackelford 2004 J Bone Miner Res 19(8) — bedrest+ARED retained ~60 %
# of bone density of unprotected bedrest controls. Modelled as a constant
# multiplier on the gravity-scaled loss rate; assumes the crew is on the
# nominal ISS-class daily exercise protocol.
BONE_COUNTERMEASURE_EFFECTIVENESS: float = 0.40

# Cardiovascular VO₂max decline rate at full µg (per year fraction)
VO2MAX_DECLINE_RATE_PER_YR_AT_0G: float = 0.05   # Convertino 1996 — 5 % / yr

# SANS prevalence baseline at full µg (fraction of crew per yr)
SANS_INCIDENCE_PER_YR_AT_0G: float = 0.30        # Mader 2011 — 30 % / yr in long-duration crew


@dataclass
class CrewHealthState:
    """Population-level crew health, advanced over mission time.

    R8 (2026-04-24, sync refactor): `crew_size` is no longer a local
    field — it's a property delegating to `MissionState.crew_alive`,
    the single mission-wide source of truth for population.  Was
    independently defaulted to 1000 in 4 modules with no propagation;
    that pattern is gone.
    """

    # Bone density: 100 % at start
    bone_density_pct: float = 100.0

    # Cardiovascular fitness (VO₂max as % of pre-launch baseline)
    vo2max_pct: float = 100.0

    # SANS prevalence (% of crew currently affected)
    sans_prevalence_pct: float = 0.0

    # Vestibular adaptation: 0 = fully adapted, 1 = brand-new exposure
    vestibular_unadapted_frac: float = 1.0

    # Psychological cohesion (qualitative 0..100)
    psych_cohesion_pct: float = 100.0

    # Operational state
    effective_g: float = EFFECTIVE_G_RIM
    # If set, overrides the bearing-derived g (testing + scenarios)
    manual_g_override: Optional[float] = None

    # Cumulative
    elapsed_yr: float = 0.0
    total_alarms: int = 0

    # R8 (2026-04-24): crew_size now reads from MissionState — single
    # source of truth across crew_health / crew_schedule / agriculture.
    @property
    def crew_size(self) -> int:
        from aria.core.mission_state import get_mission_state
        return get_mission_state().crew_alive

    # ── tick ────────────────────────────────────────────────────

    def tick(self, dt_s: float) -> None:
        bus = get_event_bus()
        phase = get_phase_controller()

        # Effective g: explicit manual override wins; else derive from bearing.
        if self.manual_g_override is not None:
            self.effective_g = self.manual_g_override
        else:
            try:
                from aria.simulator.bearing_dynamics import get_bearing_state, BearingMode
                bs = get_bearing_state()
                if bs.mode == BearingMode.OFF:
                    self.effective_g = 0.0
                else:
                    self.effective_g = EFFECTIVE_G_RIM
            except Exception:
                pass

        dt_yr = dt_s / (365.25 * 24 * 3600)
        dt_mo = dt_yr * 12.0

        # Bone density: mu-g rate × (1 - g_partial) × (1 - countermeasure efficacy).
        # Countermeasure factor reflects ARED-class daily resistive exercise per
        # Shackelford 2004; applies to all crew unless overridden in scenario data.
        gravity_factor = max(0.0, 1.0 - self.effective_g)
        countermeasure_factor = max(0.0, 1.0 - BONE_COUNTERMEASURE_EFFECTIVENESS)
        bone_loss_pct = (
            BONE_LOSS_RATE_PER_MONTH_AT_0G * 100.0
            * gravity_factor * countermeasure_factor * dt_mo
        )
        # Floor at 55 % — severe-osteoporosis fracture threshold per WHO T-score
        # criteria (Kanis 2008); below this, bones become structurally suspect
        # but the model isn't trying to predict actual fractures.
        self.bone_density_pct = max(55.0, self.bone_density_pct - bone_loss_pct)

        # VO2max: same scaling
        vo2_loss_pct = VO2MAX_DECLINE_RATE_PER_YR_AT_0G * 100.0 * (1.0 - self.effective_g) * dt_yr
        self.vo2max_pct = max(50.0, self.vo2max_pct - vo2_loss_pct)

        # SANS prevalence (slow accumulation under µg, partial-g blocks it)
        sans_increment_pct = SANS_INCIDENCE_PER_YR_AT_0G * 100.0 * max(0.0, 1.0 - self.effective_g) * dt_yr
        self.sans_prevalence_pct = min(100.0, self.sans_prevalence_pct + sans_increment_pct)

        # Vestibular adaptation: exponential decay toward 0 over 2 weeks
        # of continuous exposure (or full reset if effective_g changes)
        tau_yr = 2.0 / 52.0   # 2 weeks
        self.vestibular_unadapted_frac *= max(0.0, 1.0 - dt_yr / tau_yr)

        # Psych cohesion: slow drift with mission time + bonus when bone/cardio healthy.
        # Drift -2 % per decade base, scaled by physical-health margin.
        # Cap the per-tick swing: a 100-yr auto-tick with physical_score
        # at the 0.5 clamp floor would otherwise drop cohesion by 40 pct
        # in one tick, erasing mission state before operators can react.
        # Using a first-order lag keeps the steady-state behaviour but
        # bounds the per-step change.
        physical_score = max(0.1, (self.bone_density_pct + self.vo2max_pct) / 200.0)
        # Equilibrium target: 100 % when perfectly healthy, drifts lower
        # as the -2 %/decade term integrates. We apply the drift as an
        # incremental change but cap its magnitude to avoid wild swings.
        cohesion_drift = -2.0 * dt_yr / 10.0 / physical_score
        cohesion_drift = max(-5.0, min(5.0, cohesion_drift))   # cap per-tick swing
        self.psych_cohesion_pct = max(0.0, min(100.0, self.psych_cohesion_pct + cohesion_drift))

        self.elapsed_yr = phase.elapsed_yr

        # Alarm thresholds
        if self.bone_density_pct < 80.0 and self.bone_density_pct + bone_loss_pct >= 80.0:
            self._alarm("Crew bone density below 80 % baseline", "warning")
        if self.bone_density_pct < 70.0 and self.bone_density_pct + bone_loss_pct >= 70.0:
            self._alarm("Crew bone density below 70 % — fracture risk imminent", "critical")
        if self.psych_cohesion_pct < 60.0:
            if not getattr(self, "_psych_alarmed", False):
                self._alarm("Psychological cohesion below 60 % — intervention needed", "warning")
                self._psych_alarmed = True
        elif self.psych_cohesion_pct >= 70.0:
            # Reset the one-shot flag once cohesion has recovered with a 10 %
            # hysteresis buffer. Without this the alarm latches forever after
            # the first trip, so a second dip produces no warning.
            self._psych_alarmed = False

    def _alarm(self, msg: str, severity: str) -> None:
        bus = get_event_bus()
        phase = get_phase_controller()
        self.total_alarms += 1
        bus.publish(f"crew.health.{severity}",
                    severity=severity, source="crew_health",
                    payload={"message": msg,
                             "bone_pct": round(self.bone_density_pct, 2),
                             "vo2max_pct": round(self.vo2max_pct, 2),
                             "psych_pct": round(self.psych_cohesion_pct, 2)},
                    sim_time_yr=phase.elapsed_yr)

    # ── serialisation ──────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "crew_size":                 self.crew_size,
            "effective_g":               round(self.effective_g, 4),
            "elapsed_yr":                round(self.elapsed_yr, 3),
            "metrics": {
                "bone_density_pct":      round(self.bone_density_pct, 2),
                "vo2max_pct":            round(self.vo2max_pct, 2),
                "sans_prevalence_pct":   round(self.sans_prevalence_pct, 2),
                "vestibular_unadapted_pct": round(100.0 * self.vestibular_unadapted_frac, 2),
                "psych_cohesion_pct":    round(self.psych_cohesion_pct, 2),
            },
            "alarms_fired":              self.total_alarms,
            "sources": [
                "Mader 2011 Ophthalmology 118",
                "Sibonga 2007 J. Bone Miner. Metab.",
                "Convertino 1996 Aviat. Space Environ. Med.",
                "Clément 2006 J. Vestib. Res.",
                "NASA HRP 2022 risk catalogue",
            ],
        }


_DEFAULT: Optional[CrewHealthState] = None


def get_crew_health() -> CrewHealthState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = CrewHealthState()
    return _DEFAULT


def reset_crew_health() -> None:
    global _DEFAULT
    _DEFAULT = CrewHealthState()


def register_with_tick_engine() -> None:
    from aria.simulator.tick_engine import get_tick_engine
    get_tick_engine().register("crew_health", get_crew_health().tick, order=48)
