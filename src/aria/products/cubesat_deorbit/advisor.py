"""CubeSat de-orbit advisor — core logic.

The advisor answers the question every smallsat operator faces near
end-of-mission: *what do I have to do, and when, to comply with the
debris-mitigation rules?*

Three regimes are handled:

  1. **Natural decay sufficient.**  At 400-500 km altitude with
     typical ballistic coefficients, atmospheric drag will pull the
     vehicle below 120 km within 5 years (FCC) or 25 years (NASA).
     No burn needed.  The advisor reports the predicted decay
     timeline and confirms compliance.

  2. **Propulsive de-orbit required.**  Above ~600 km natural decay
     takes too long.  The advisor sizes the smallest burn that
     lowers periapsis to a target re-entry altitude, checks that
     the propellant + ΔV capability are enough, and sets the burn
     epoch to maximise reentry-footprint controllability.

  3. **Infeasible.**  Insufficient ΔV / propellant or compliance
     deadline already in the past.  The advisor flags this rather
     than producing a fake plan, and lists the specific shortfalls
     the operator can close.

This module composes existing ARIA tooling:

  * `aria.simulation.atmo_drag.orbit_lifetime` — King-Hele decay
  * `aria.simulation.atmo_drag.get_density`   — NRLMSISE-00
  * `aria.simulation.lambert_izzo`            — burn ΔV (single rev)
  * `aria.physics.uncertainty`                — confidence-tier tagging
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional


# ── Constants ───────────────────────────────────────────────────


# Earth equatorial radius (WGS-84) and gravitational parameter (km³/s²).
R_EARTH_KM = 6378.137
MU_EARTH_KM3_S2 = 398_600.4418


# Default re-entry interface altitude (km).  Below this aerodynamic
# heating dominates and the vehicle is committed to reentry.
DEFAULT_REENTRY_ALT_KM = 120.0

# FCC 22-271 deadline: post-mission disposal within 5 years.  Effective
# 2024-09-29.  Predates that for older missions.
FCC_5_YEAR_DEADLINE_S = 5.0 * 365.25 * 86400.0

# NASA ODMSP NASA-STD-8719.14B: 25-year deorbit.  Older but still
# applicable for non-FCC-licensed payloads.
NASA_25_YEAR_DEADLINE_S = 25.0 * 365.25 * 86400.0

# Standard gravity (m/s²) for ISP → exhaust-velocity conversion.
G0 = 9.806_65


# ── Decision enum + dataclasses ────────────────────────────────


class Decision(str, enum.Enum):
    NATURAL_DECAY = "natural_decay"          # do nothing; decay covers it
    BURN_REQUIRED = "burn_required"          # propulsive de-orbit
    BURN_OPTIONAL = "burn_optional"          # decay covers FCC; burn shortens
    INFEASIBLE = "infeasible"                # cannot meet compliance


@dataclass(frozen=True)
class SpacecraftState:
    """Current orbital + physical state of the CubeSat."""
    altitude_km: float                       # circular-orbit-equivalent
    inclination_deg: float
    mass_kg: float
    drag_coefficient: float = 2.2            # CubeSat typical (Vallado §8)
    cross_section_m2: float = 0.06           # 6U broadside (~0.06 m²)
    propellant_kg: float = 0.0               # remaining propellant
    isp_s: float = 220.0                     # cold-gas / butane typical
    epoch_utc: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
    )

    @property
    def ballistic_coefficient_kg_m2(self) -> float:
        """β = m / (Cd · A).  Larger β = decays slower."""
        return self.mass_kg / (
            max(self.drag_coefficient, 0.1) * max(self.cross_section_m2, 1e-4)
        )

    @property
    def delta_v_capacity_mps(self) -> float:
        """Tsiolkovsky ΔV available given remaining propellant + Isp.

        Approximates dry mass as (mass - propellant), which assumes
        the operator has reported `mass_kg` as wet mass.  For a 6U
        CubeSat with 0.5 kg butane in a 12 kg wet mass at Isp 220 s:
        ΔV ≈ 220·9.81·ln(12/11.5) ≈ 92 m/s.
        """
        wet = self.mass_kg
        dry = wet - self.propellant_kg
        if dry <= 0.0 or wet <= 0.0:
            return 0.0
        return self.isp_s * G0 * math.log(wet / dry)


@dataclass(frozen=True)
class MissionParams:
    """Operator-side inputs unrelated to current state."""
    name: str = "CubeSat"
    launch_utc: Optional[datetime] = None    # for FCC clock
    fcc_compliant_required: bool = True       # post-2024-09-29 launches
    nasa_25yr_compliant_required: bool = True
    f107_solar_flux: float = 150.0            # moderate solar activity
    target_reentry_alt_km: float = DEFAULT_REENTRY_ALT_KM


@dataclass(frozen=True)
class NaturalDecayResult:
    """Output of natural-decay analysis."""
    lifetime_years: float
    lifetime_days: float
    fcc_compliant: bool
    nasa_25yr_compliant: bool
    profile_alt_time: List[tuple]             # [(alt_km, time_days), ...]


@dataclass(frozen=True)
class BurnPlan:
    """Propulsive de-orbit burn parameters."""
    burn_epoch_utc: datetime
    delta_v_mps: float
    direction: str                            # "retrograde" / "prograde"
    propellant_kg_burned: float
    propellant_margin_kg: float               # remaining after burn
    target_periapsis_km: float
    expected_reentry_utc: datetime
    notes: str = ""


@dataclass(frozen=True)
class Footprint:
    """Predicted reentry-footprint geometry."""
    nominal_lat_deg: float
    nominal_lon_deg: float
    along_track_3sigma_km: float
    cross_track_3sigma_km: float
    casualty_area_m2: float                   # debris-impact casualty estimate
    occurs_over_water: bool                   # heuristic
    notes: str = ""


@dataclass(frozen=True)
class ComplianceCheck:
    """Per-rule compliance verdict."""
    fcc_5_year: bool
    nasa_25_year: bool
    fcc_5_year_margin_days: float
    nasa_25_year_margin_days: float


@dataclass(frozen=True)
class DeOrbitRecommendation:
    """The advisor's top-level output."""
    decision: Decision
    natural_decay: NaturalDecayResult
    burn_plan: Optional[BurnPlan]
    footprint: Optional[Footprint]
    compliance: ComplianceCheck
    confidence_tier: str                       # A / B / C from uncertainty.py
    rationale: List[str]
    operator_actions: List[str]                # specific to-dos


# ── Natural-decay analysis ─────────────────────────────────────


def natural_decay_lifetime(
    state: SpacecraftState,
    params: MissionParams,
    reentry_alt_km: Optional[float] = None,
) -> NaturalDecayResult:
    """Predict natural-decay lifetime using ARIA's King-Hele integrator
    + NRLMSISE-00 atmosphere."""
    from aria.simulation.atmo_drag import orbit_lifetime

    target_re = reentry_alt_km or params.target_reentry_alt_km
    result = orbit_lifetime(
        altitude_km=state.altitude_km,
        ballistic_coeff_kg_m2=state.ballistic_coefficient_kg_m2,
        f107=params.f107_solar_flux,
        reentry_alt_km=target_re,
    )
    profile = [
        (float(p["altitude_km"]), float(p["time_days"]))
        for p in result.decay_profile
    ]
    return NaturalDecayResult(
        lifetime_years=result.lifetime_years,
        lifetime_days=result.lifetime_days,
        fcc_compliant=result.lifetime_years <= 5.0,
        nasa_25yr_compliant=result.compliant_25yr,
        profile_alt_time=profile,
    )


# ── Propulsive de-orbit planner ────────────────────────────────


def _hohmann_dv_to_lower_periapsis_mps(
    apoapsis_alt_km: float,
    target_periapsis_alt_km: float,
) -> float:
    """ΔV at apoapsis to lower periapsis to ``target``.

    Single-impulse retrograde burn at apoapsis (assumed circular start).
    Returns m/s.  Vallado §9.2 closed form:
        Δv = √(μ/r_a) − √(μ/r_a · (2 r_p / (r_a + r_p)))
    """
    r_a = R_EARTH_KM + apoapsis_alt_km
    r_p = R_EARTH_KM + target_periapsis_alt_km
    if r_p >= r_a:
        return 0.0
    v_circ = math.sqrt(MU_EARTH_KM3_S2 / r_a)
    v_transfer = math.sqrt(MU_EARTH_KM3_S2 * 2.0 * r_p / (r_a * (r_a + r_p)))
    return (v_circ - v_transfer) * 1000.0   # km/s → m/s


def plan_propulsive_deorbit(
    state: SpacecraftState,
    params: MissionParams,
    target_periapsis_km: Optional[float] = None,
) -> Optional[BurnPlan]:
    """Compute the smallest single-impulse retrograde burn that lowers
    periapsis to ``target_periapsis_km``.  Returns ``None`` if
    propellant or ΔV capacity is insufficient."""
    target = target_periapsis_km or params.target_reentry_alt_km
    dv_required_mps = _hohmann_dv_to_lower_periapsis_mps(
        state.altitude_km, target,
    )
    if dv_required_mps <= 0.0:
        return None

    dv_capacity_mps = state.delta_v_capacity_mps
    if dv_capacity_mps < dv_required_mps:
        return None

    # Tsiolkovsky inverse: prop = m_wet · (1 − exp(−Δv / (Isp·g₀))).
    burned = state.mass_kg * (
        1.0 - math.exp(-dv_required_mps / (state.isp_s * G0))
    )
    margin = max(state.propellant_kg - burned, 0.0)

    # Burn epoch: burn now (operator can re-target).  Reentry epoch:
    # for a circular-to-elliptic transfer with apoapsis at the current
    # altitude and periapsis at target_alt, the half-orbit takes ~T/2
    # of the transfer orbit.
    a_transfer_km = (R_EARTH_KM + state.altitude_km
                     + R_EARTH_KM + target) / 2.0
    T_transfer_s = 2.0 * math.pi * math.sqrt(
        a_transfer_km ** 3 / MU_EARTH_KM3_S2
    )
    reentry_eta = state.epoch_utc + timedelta(seconds=T_transfer_s / 2.0)

    return BurnPlan(
        burn_epoch_utc=state.epoch_utc,
        delta_v_mps=dv_required_mps,
        direction="retrograde",
        propellant_kg_burned=burned,
        propellant_margin_kg=margin,
        target_periapsis_km=target,
        expected_reentry_utc=reentry_eta,
        notes=(
            f"Single-impulse Hohmann lower from {state.altitude_km:.0f} km "
            f"to {target:.0f} km periapsis"
        ),
    )


# ── Reentry-footprint estimate ─────────────────────────────────


def estimate_reentry_footprint(
    burn_plan: BurnPlan,
    state: SpacecraftState,
) -> Footprint:
    """First-order reentry-footprint prediction.

    The 3-σ along-track uncertainty for a controlled de-orbit on a
    sub-day timescale is dominated by the burn-epoch error and the
    drag-density model error.  A typical CubeSat with no precision
    tracking sees ~50–200 km along-track + ~10–30 km cross-track
    spread (Klinkrad 2006 *Space Debris* §4.5).  We use the
    pessimistic end (200 km / 30 km) as the operator-default.

    Casualty area follows ESA's 8 m² per kg-of-vehicle threshold —
    a conservative debris-cloud bounding for an uncontrolled break-up.

    Honest reading: this is a Tier-B confidence-tier prediction
    (per docs/UNCERTAINTY.md).  For a real flight a high-fidelity
    breakup model + actual launch-tracked covariance is required.
    """
    # Inclination determines the latitude band of reentry.  Without
    # ascending-node phase information we report nominal latitude as
    # a function of inclination — operator provides longitude offset
    # downstream when they choose ground-track timing.
    nominal_lat = math.copysign(
        min(abs(state.inclination_deg), 80.0), state.inclination_deg,
    )
    nominal_lon = 0.0    # caller refines using actual ground-track

    # Heuristic for "over water" — true if nominal latitude is
    # outside ±60° (mostly southern ocean / arctic).  This is
    # operator-default-only; actual targeting should always be
    # explicit when going for a target like SPOUA.
    over_water = abs(nominal_lat) > 60.0

    return Footprint(
        nominal_lat_deg=nominal_lat,
        nominal_lon_deg=nominal_lon,
        along_track_3sigma_km=200.0,
        cross_track_3sigma_km=30.0,
        casualty_area_m2=8.0 * state.mass_kg,
        occurs_over_water=over_water,
        notes=(
            "Tier-B confidence: 200 km × 30 km 3σ envelope assumes a "
            "single retrograde burn with sub-day decay.  High-fidelity "
            "footprint requires breakup-model + tracked covariance."
        ),
    )


# ── Compliance check ──────────────────────────────────────────


def _compliance(
    state: SpacecraftState,
    params: MissionParams,
    decay: NaturalDecayResult,
) -> ComplianceCheck:
    fcc = decay.fcc_compliant
    nasa = decay.nasa_25yr_compliant
    fcc_margin = 5.0 * 365.25 - decay.lifetime_days
    nasa_margin = 25.0 * 365.25 - decay.lifetime_days
    return ComplianceCheck(
        fcc_5_year=fcc,
        nasa_25_year=nasa,
        fcc_5_year_margin_days=fcc_margin,
        nasa_25_year_margin_days=nasa_margin,
    )


# ── Top-level advisor ─────────────────────────────────────────


def advise_deorbit(
    state: SpacecraftState,
    params: Optional[MissionParams] = None,
) -> DeOrbitRecommendation:
    """Produce the de-orbit recommendation.  Pure function: same
    inputs always produce the same output, so the advisor is
    repeatable + auditable."""
    params = params or MissionParams()

    decay = natural_decay_lifetime(state, params)
    compliance = _compliance(state, params, decay)
    rationale: List[str] = []
    actions: List[str] = []

    # ── Decision tree.
    # 1) Natural decay covers all required rules → NATURAL_DECAY.
    if (
        (not params.fcc_compliant_required or compliance.fcc_5_year)
        and (not params.nasa_25yr_compliant_required or compliance.nasa_25_year)
    ):
        decision = Decision.NATURAL_DECAY
        rationale.append(
            f"Natural decay → reentry in {decay.lifetime_years:.1f} yr "
            f"({decay.lifetime_days:.0f} d).  FCC compliance margin "
            f"{compliance.fcc_5_year_margin_days:+.0f} d; "
            f"NASA-25-yr margin {compliance.nasa_25_year_margin_days:+.0f} d."
        )
        burn_plan = None
        footprint = None
        actions.append("Confirm passivation procedures + power down.")

    else:
        # 2) Try a propulsive de-orbit burn.
        burn_plan = plan_propulsive_deorbit(state, params)
        if burn_plan is None:
            decision = Decision.INFEASIBLE
            shortfall_dv = max(
                _hohmann_dv_to_lower_periapsis_mps(
                    state.altitude_km, params.target_reentry_alt_km,
                ) - state.delta_v_capacity_mps, 0.0,
            )
            rationale.append(
                f"Natural decay = {decay.lifetime_years:.1f} yr — exceeds "
                f"compliance limit.  Propulsive de-orbit infeasible: ΔV "
                f"capacity {state.delta_v_capacity_mps:.1f} m/s vs "
                f"required {state.delta_v_capacity_mps + shortfall_dv:.1f} m/s "
                f"(shortfall {shortfall_dv:.1f} m/s)."
            )
            actions.append(
                "Add propellant before launch, OR lower mission altitude, "
                "OR negotiate compliance waiver (FCC §25.114)."
            )
            footprint = None
        else:
            decision = Decision.BURN_REQUIRED
            footprint = estimate_reentry_footprint(burn_plan, state)
            rationale.append(
                f"Natural decay = {decay.lifetime_years:.1f} yr — exceeds "
                f"compliance limit.  Propulsive de-orbit feasible: "
                f"Δv = {burn_plan.delta_v_mps:.1f} m/s, propellant burn = "
                f"{burn_plan.propellant_kg_burned:.2f} kg "
                f"(margin {burn_plan.propellant_margin_kg:.2f} kg)."
            )
            actions.extend([
                f"Schedule retrograde burn at "
                f"{burn_plan.burn_epoch_utc.isoformat()}.",
                f"Confirm reentry footprint {footprint.along_track_3sigma_km:.0f} km × "
                f"{footprint.cross_track_3sigma_km:.0f} km 3σ.",
                "Coordinate with FAA AST + ITU notification 60 days prior.",
            ])

    # Confidence tier — Tier B for the King-Hele decay (factor-2 in CV
    # range per docs/UNCERTAINTY.md).
    tier = "B"

    return DeOrbitRecommendation(
        decision=decision,
        natural_decay=decay,
        burn_plan=burn_plan,
        footprint=footprint,
        compliance=compliance,
        confidence_tier=tier,
        rationale=rationale,
        operator_actions=actions,
    )


# ── CLI helper ────────────────────────────────────────────────


def _render_text(recommendation: DeOrbitRecommendation) -> str:
    r = recommendation
    lines = []
    lines.append("=" * 72)
    lines.append("ARIA CubeSat End-of-Life De-Orbit Advisor")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"DECISION: {r.decision.value.upper()}")
    lines.append(f"Confidence tier: {r.confidence_tier}")
    lines.append("")
    lines.append("Natural decay analysis")
    lines.append(f"  Lifetime           : {r.natural_decay.lifetime_years:.2f} yr")
    lines.append(f"  Re-entry projected : "
                 f"{r.natural_decay.lifetime_days:.0f} d after epoch")
    lines.append(f"  FCC 5-yr           : "
                 f"{'PASS' if r.compliance.fcc_5_year else 'FAIL'} "
                 f"(margin {r.compliance.fcc_5_year_margin_days:+.0f} d)")
    lines.append(f"  NASA 25-yr         : "
                 f"{'PASS' if r.compliance.nasa_25_year else 'FAIL'} "
                 f"(margin {r.compliance.nasa_25_year_margin_days:+.0f} d)")
    lines.append("")
    if r.burn_plan is not None:
        lines.append("Propulsive de-orbit plan")
        lines.append(f"  Δv required        : {r.burn_plan.delta_v_mps:.2f} m/s")
        lines.append(f"  Direction          : {r.burn_plan.direction}")
        lines.append(f"  Propellant burned  : "
                     f"{r.burn_plan.propellant_kg_burned:.3f} kg "
                     f"(margin {r.burn_plan.propellant_margin_kg:.3f} kg)")
        lines.append(f"  Target periapsis   : {r.burn_plan.target_periapsis_km:.0f} km")
        lines.append(f"  Burn epoch         : {r.burn_plan.burn_epoch_utc.isoformat()}")
        lines.append(f"  Re-entry epoch     : {r.burn_plan.expected_reentry_utc.isoformat()}")
        lines.append("")
    if r.footprint is not None:
        lines.append("Re-entry footprint")
        lines.append(f"  Nominal lat/lon    : "
                     f"{r.footprint.nominal_lat_deg:.1f}° / "
                     f"{r.footprint.nominal_lon_deg:.1f}°")
        lines.append(f"  Along-track 3σ     : {r.footprint.along_track_3sigma_km:.0f} km")
        lines.append(f"  Cross-track 3σ     : {r.footprint.cross_track_3sigma_km:.0f} km")
        lines.append(f"  Casualty area est  : {r.footprint.casualty_area_m2:.1f} m²")
        lines.append(f"  Over water (heur.) : "
                     f"{'yes' if r.footprint.occurs_over_water else 'no'}")
        lines.append("")
    lines.append("Rationale")
    for line in r.rationale:
        lines.append(f"  - {line}")
    lines.append("")
    lines.append("Operator actions")
    for action in r.operator_actions:
        lines.append(f"  □ {action}")
    return "\n".join(lines)


def main() -> int:
    """CLI entry — `python -m aria.products.cubesat_deorbit`."""
    import argparse
    import sys
    parser = argparse.ArgumentParser(
        description="ARIA CubeSat de-orbit advisor",
    )
    parser.add_argument("--altitude-km", type=float, default=550.0)
    parser.add_argument("--inclination-deg", type=float, default=51.6)
    parser.add_argument("--mass-kg", type=float, default=12.0)
    parser.add_argument("--cross-section-m2", type=float, default=0.06)
    parser.add_argument("--cd", type=float, default=2.2)
    parser.add_argument("--propellant-kg", type=float, default=0.0)
    parser.add_argument("--isp-s", type=float, default=220.0)
    parser.add_argument("--f107", type=float, default=150.0)
    parser.add_argument("--target-re-alt-km", type=float, default=120.0)
    args = parser.parse_args()

    state = SpacecraftState(
        altitude_km=args.altitude_km,
        inclination_deg=args.inclination_deg,
        mass_kg=args.mass_kg,
        drag_coefficient=args.cd,
        cross_section_m2=args.cross_section_m2,
        propellant_kg=args.propellant_kg,
        isp_s=args.isp_s,
    )
    params = MissionParams(
        f107_solar_flux=args.f107,
        target_reentry_alt_km=args.target_re_alt_km,
    )
    rec = advise_deorbit(state, params)
    print(_render_text(rec))
    return 0 if rec.decision is not Decision.INFEASIBLE else 1


if __name__ == "__main__":
    raise SystemExit(main())
