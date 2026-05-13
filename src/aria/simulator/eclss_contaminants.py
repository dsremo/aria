"""Trace-contaminant dynamics in the habitat atmosphere.

Crew + equipment continuously outgas organic volatiles that accumulate
unless actively removed. Unremoved, they cross SMAC (Spacecraft Maximum
Allowable Concentration) limits within weeks — ethylene accelerates fruit
ripening in hydroponics, formaldehyde is carcinogenic, ammonia triggers
respiratory irritation.

This module models four representative contaminants with first-order
production + removal kinetics:

      dC/dt = Q_gen − k_removal · C

where Q_gen is from crew + agriculture + manufacturing, and k_removal is
the effective scrubber coefficient (catalytic oxidizer + activated
charcoal + zeolite 13X sieve).

References
----------
* NASA-TM-104827 "Spacecraft Maximum Allowable Concentrations for Airborne
  Contaminants", Table 2 — SMAC values
* Finn et al. 1989 NASA-TM-102829 "CO₂ and humidity removal from
  spacecraft cabin air" — scrubber kinetics
* Pilson 2013 "Introduction to the Chemistry of the Sea" Ch. 7 — source
  generation rates from biological metabolism
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller


# ── Contaminant definitions ─────────────────────────────────────────

@dataclass(frozen=True)
class ContaminantSpec:
    """Static properties of one airborne contaminant."""

    name: str
    formula: str
    smac_7day_mg_m3: float        # 7-day Spacecraft Maximum Allowable Conc.
    smac_180day_mg_m3: float      # 180-day (mission-duration)
    baseline_gen_mg_h_per_crew: float  # from crew metabolism + off-gassing (per crew member)
    agri_gen_mg_h_per_m2: float        # from hydroponics per m² growing area
    k_removal_per_hour: float     # baseline scrubber efficiency, first-order
    source: str


# Representative contaminant set (per NASA-TM-104827). Not exhaustive —
# full cabin analysis tracks 50+ VOCs — but the worst-actors for a 1 000 yr
# mission are covered.
CONTAMINANTS: Dict[str, ContaminantSpec] = {
    "ethylene": ContaminantSpec(
        name="Ethylene",
        formula="C₂H₄",
        smac_7day_mg_m3=200.0,          # NASA-TM-104827 Table 2
        smac_180day_mg_m3=25.0,
        baseline_gen_mg_h_per_crew=0.15,     # metabolic off-gassing, Pilson 2013 Ch. 7
        agri_gen_mg_h_per_m2=0.08,            # hydroponic fruit ripening hormone; plant-source dominant
        k_removal_per_hour=0.35,              # catalytic oxidizer at 200 °C, Finn 1989 §4.2
        source="NASA-TM-104827 Table 2; Pilson 2013 Ch. 7",
    ),
    "formaldehyde": ContaminantSpec(
        name="Formaldehyde",
        formula="CH₂O",
        smac_7day_mg_m3=0.1,            # NASA-TM-104827 — carcinogen, tight limit
        smac_180day_mg_m3=0.05,
        baseline_gen_mg_h_per_crew=0.02,     # off-gassing from polymer furniture + fabric
        agri_gen_mg_h_per_m2=0.01,
        k_removal_per_hour=0.55,              # activated charcoal very effective
        source="NASA-TM-104827; Finn 1989 §4.3",
    ),
    "ammonia": ContaminantSpec(
        name="Ammonia",
        formula="NH₃",
        smac_7day_mg_m3=15.0,
        smac_180day_mg_m3=7.0,
        baseline_gen_mg_h_per_crew=1.2,      # metabolic via urine → air transfer, Pilson 2013
        agri_gen_mg_h_per_m2=0.3,             # nutrient-loop volatilization in hydroponics
        k_removal_per_hour=0.40,
        source="NASA-TM-104827; NASA/TP-2015-218570 BVAD §5.4",
    ),
    "methane": ContaminantSpec(
        name="Methane",
        formula="CH₄",
        smac_7day_mg_m3=3_000.0,       # high tolerance — asphyxiant not toxic
        smac_180day_mg_m3=3_000.0,
        baseline_gen_mg_h_per_crew=4.0,      # gut microbiome, Pilson 2013 Ch. 7
        agri_gen_mg_h_per_m2=0.0,             # aerobic hydroponics, no methanogenesis
        k_removal_per_hour=0.12,              # catalytic oxidizer at 400 °C — slow
        source="NASA-TM-104827; Pilson 2013 Ch. 7",
    ),
}


# ── Runtime state ──────────────────────────────────────────────────

@dataclass
class ContaminantState:
    """Running concentration + cumulative totals for one contaminant."""

    concentration_mg_m3: float = 0.0
    cumulative_generated_mg: float = 0.0
    cumulative_removed_mg: float = 0.0
    alarm_active: bool = False


@dataclass
class EclssContaminantsState:
    """Overall trace-contaminant state for the whole habitat."""

    # Cabin volume — combined torus + modules (from parameters)
    cabin_volume_m3: float = 4.38e5   # ~438 m³/crew × 1 000, matches parameters
    crew_size: int = 1000
    agri_area_m2: float = 40_000.0     # hydroponic grow area
    scrubber_efficiency_frac: float = 1.0   # 1.0 = nominal; <1.0 = degraded scrubber

    states: Dict[str, ContaminantState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.states:
            self.states = {name: ContaminantState() for name in CONTAMINANTS}

    # ── per-tick evolution ────────────────────────────────────

    def tick(self, dt_s: float) -> None:
        """Advance concentration by dt_s seconds using forward-Euler on the
        first-order ODE  dC/dt = Q_gen/V − k·C."""
        dt_h = dt_s / 3600.0
        phase = get_phase_controller()
        crew_scale = phase.spec().crew_metabolic_frac

        bus = get_event_bus()
        for key, spec in CONTAMINANTS.items():
            st = self.states[key]
            q_gen_mg_h = (spec.baseline_gen_mg_h_per_crew * self.crew_size * crew_scale
                          + spec.agri_gen_mg_h_per_m2 * self.agri_area_m2)
            q_gen_mg_m3_h = q_gen_mg_h / self.cabin_volume_m3
            k = spec.k_removal_per_hour * self.scrubber_efficiency_frac
            # Implicit (backwards) Euler — unconditionally stable for any
            # dt_h. Explicit Euler blew up with the adaptive 30-day substep
            # used on long coasts (k·dt_h ≫ 1 → C went negative → clamped
            # → alarm flapped every tick). Solve  C_new = C_old + (Q − k·C_new)·dt:
            new_C = max(0.0, (st.concentration_mg_m3 + q_gen_mg_m3_h * dt_h)
                              / (1.0 + k * dt_h))
            # Removed mass this tick uses the new (post-step) concentration
            # to stay consistent with the implicit scheme.
            removed_mg = k * new_C * self.cabin_volume_m3 * dt_h
            st.cumulative_generated_mg += q_gen_mg_h * dt_h
            st.cumulative_removed_mg += removed_mg
            st.concentration_mg_m3 = new_C

            # Alarm if exceeds 180-day SMAC — but only re-arm once the
            # concentration drops 20 % below the limit (hysteresis) so a
            # value hovering around the threshold doesn't fire every tick.
            # Without the hysteresis band, Euler-step oscillations across
            # the SMAC line spammed the critical bus every ~60 days.
            limit = spec.smac_180day_mg_m3  # 180-day SMAC (SSP 50260)
            clear = limit * 0.8             # 20 % hysteresis band (ESTIMATE — matches propulsion_thermal)
            if new_C > limit and not st.alarm_active:
                st.alarm_active = True
                bus.publish(
                    f"eclss.contaminant.{key}.alarm",
                    severity="critical",
                    source="eclss_contaminants",
                    payload={"contaminant": spec.name,
                             "concentration_mg_m3": round(new_C, 3),
                             "smac_180day": limit,
                             "scrubber_eff_frac": self.scrubber_efficiency_frac},
                    sim_time_yr=phase.elapsed_yr,
                )
            elif new_C < clear and st.alarm_active:
                st.alarm_active = False

    # ── serialisation ────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "cabin_volume_m3": self.cabin_volume_m3,
            "crew_size": self.crew_size,
            "agri_area_m2": self.agri_area_m2,
            "scrubber_efficiency_frac": self.scrubber_efficiency_frac,
            "contaminants": {
                key: {
                    "name": spec.name,
                    "formula": spec.formula,
                    "concentration_mg_m3": round(self.states[key].concentration_mg_m3, 4),
                    "smac_7day":  spec.smac_7day_mg_m3,
                    "smac_180day": spec.smac_180day_mg_m3,
                    "alarm": self.states[key].alarm_active,
                    "cumulative_generated_mg": round(self.states[key].cumulative_generated_mg, 1),
                    "cumulative_removed_mg":  round(self.states[key].cumulative_removed_mg, 1),
                    "margin_to_smac_180d_pct": round(
                        100.0 * (1.0 - self.states[key].concentration_mg_m3 / spec.smac_180day_mg_m3),
                        1,
                    ) if spec.smac_180day_mg_m3 > 0 else None,
                    "source": spec.source,
                }
                for key, spec in CONTAMINANTS.items()
            },
        }


# ── Module singleton ──────────────────────────────────────────────

_DEFAULT: Optional[EclssContaminantsState] = None


def get_eclss_contaminants() -> EclssContaminantsState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = EclssContaminantsState()
    return _DEFAULT


def reset_eclss_contaminants() -> None:
    global _DEFAULT
    _DEFAULT = EclssContaminantsState()


def register_with_tick_engine() -> None:
    from aria.simulator.tick_engine import get_tick_engine
    get_tick_engine().register(
        "eclss_contaminants",
        get_eclss_contaminants().tick,
        order=42,   # within the consumption band
    )
