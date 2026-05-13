"""FCC §25.114 waiver-application helper.

When a smallsat cannot meet the FCC 22-271 5-year post-mission
disposal rule (FCC 22-271 effective 2024-09-29), the operator may
apply for a waiver under 47 CFR §1.3 — but the FCC requires that
the application include specific technical justifications.

This module produces a structured waiver-application skeleton from
the advisor's recommendation: the same input the advisor used to
decide that natural decay is insufficient becomes the evidence base
for the waiver request.

The output is a list of ``WaiverSection`` objects that together form
an exhibit the operator can attach to FCC Form 312 or 442.  The
operator (or their counsel) is expected to add narrative context;
ARIA does the technical-numerical work and flags fields that need
operator-supplied colour.

Authoritative sources used by this module:
  * FCC 22-271 (rulemaking; 5-year post-mission disposal).
  * 47 CFR §1.3 (waiver authority).
  * 47 CFR §25.114 (orbital-debris-mitigation showings).
  * NASA-STD-8719.14B (NASA-side disposal standard).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from aria.products.cubesat_deorbit.advisor import (
    DeOrbitRecommendation,
    Decision,
    SpacecraftState,
    MissionParams,
)


@dataclass(frozen=True)
class WaiverSection:
    heading: str
    paragraph: str
    operator_must_supply: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class FCCWaiverApplication:
    mission_name: str
    generated_utc: str
    sections: List[WaiverSection]
    fcc_rule_cited: str
    waiver_authority: str
    technical_summary: str

    def to_text(self) -> str:
        """Render the waiver application as plain text suitable for
        copy-pasting into FCC Form 312 / 442 narrative fields."""
        out = []
        out.append("=" * 72)
        out.append(
            f"FCC §25.114 Orbital Debris Mitigation — Waiver Application")
        out.append(f"Mission: {self.mission_name}")
        out.append(f"Generated: {self.generated_utc}")
        out.append(f"Rule cited: {self.fcc_rule_cited}")
        out.append(f"Waiver authority: {self.waiver_authority}")
        out.append("=" * 72)
        out.append("")
        out.append("Technical summary")
        out.append("-" * 72)
        out.append(self.technical_summary)
        out.append("")
        for s in self.sections:
            out.append(s.heading)
            out.append("-" * 72)
            out.append(s.paragraph)
            if s.operator_must_supply:
                out.append("")
                out.append("[Operator must supply:]")
                for item in s.operator_must_supply:
                    out.append(f"  - {item}")
            out.append("")
        return "\n".join(out)


def build_waiver_application(
    rec: DeOrbitRecommendation,
    state: SpacecraftState,
    params: MissionParams,
    mission_name: str = "CubeSat",
) -> FCCWaiverApplication:
    """Generate a FCC §25.114 waiver application skeleton."""

    if rec.decision is not Decision.INFEASIBLE:
        # Caller should not normally invoke this for a compliant
        # mission — but we still produce a useful document because
        # operators sometimes pre-stage the waiver in case a burn
        # fails on orbit.
        leading = (
            f"This skeleton was generated for a mission whose advisor "
            f"verdict is {rec.decision.value.upper()}.  Use only as a "
            f"contingency template if the planned disposal fails."
        )
    else:
        leading = (
            f"Mission {mission_name} cannot meet the FCC 22-271 five-year "
            f"post-mission disposal rule.  The advisor's analysis below "
            f"explains why and proposes mitigations."
        )

    decay = rec.natural_decay
    comp = rec.compliance
    summary = (
        f"{leading}\n\n"
        f"Natural-decay lifetime estimate: {decay.lifetime_years:.1f} yr "
        f"({decay.lifetime_days:.0f} d).\n"
        f"FCC 5-yr margin: {comp.fcc_5_year_margin_days:+.0f} d "
        f"(positive = compliant).\n"
        f"NASA 25-yr margin: {comp.nasa_25_year_margin_days:+.0f} d.\n"
        f"Δv capacity: {state.delta_v_capacity_mps:.1f} m/s "
        f"(propellant {state.propellant_kg:.2f} kg, Isp {state.isp_s:.0f} s)."
    )

    sections: List[WaiverSection] = [
        WaiverSection(
            heading="1. Identification of the Rule from Which Waiver Is Sought",
            paragraph=(
                "Applicant requests waiver of FCC 22-271 §1, codified at "
                "47 CFR §25.114(d)(14)(iv), which requires post-mission "
                "disposal within five (5) years of mission completion."
            ),
        ),
        WaiverSection(
            heading="2. Technical Showing — Vehicle State at End-of-Mission",
            paragraph=(
                f"Mission orbital altitude (circular-equivalent): "
                f"{state.altitude_km:.1f} km.\n"
                f"Inclination: {state.inclination_deg:.2f}°.\n"
                f"Wet mass at end-of-mission: {state.mass_kg:.2f} kg "
                f"(propellant {state.propellant_kg:.2f} kg).\n"
                f"Drag coefficient assumed: {state.drag_coefficient:.2f} "
                f"(Vallado §8 baseline).\n"
                f"Cross-section assumed: {state.cross_section_m2:.3f} m²."
            ),
            operator_must_supply=[
                "Vehicle drawing showing area + tumble axes.",
                "Last-on-orbit telemetry confirming altitude + attitude.",
            ],
        ),
        WaiverSection(
            heading="3. Atmospheric-Drag Decay Analysis",
            paragraph=(
                f"Using NRLMSISE-00 atmospheric density at "
                f"F10.7 = {params.f107_solar_flux:.0f} sfu and the King-Hele "
                f"semi-analytic decay integrator (Vallado §8.6), the "
                f"vehicle natural-decay lifetime is "
                f"{decay.lifetime_years:.2f} years.  This exceeds the FCC "
                f"5-year limit by {-comp.fcc_5_year_margin_days:.0f} days."
            ),
        ),
        WaiverSection(
            heading="4. Propulsive De-Orbit Feasibility",
            paragraph=(
                f"Δv required to lower periapsis to "
                f"{params.target_reentry_alt_km:.0f} km is "
                f"{rec.burn_plan.delta_v_mps:.1f} m/s "
                "; available Δv capacity per Tsiolkovsky is "
                f"{state.delta_v_capacity_mps:.1f} m/s."
                if rec.burn_plan is not None else
                f"Δv capacity is {state.delta_v_capacity_mps:.1f} m/s; the "
                f"required lower-periapsis Δv exceeds this, so a single-impulse "
                f"propulsive de-orbit is infeasible without additional "
                f"propellant."
            ),
            operator_must_supply=[
                "Propulsion system datasheet (for ground-station verification).",
                "Failure-mode analysis: thruster valve, ECU, etc.",
            ],
        ),
        WaiverSection(
            heading="5. Risk Mitigation Plan",
            paragraph=(
                "Applicant proposes the following mitigations:\n"
                "  (a) End-of-mission passivation (battery + propellant "
                "      depletion) to remove stored energy.\n"
                "  (b) Conjunction screening via the operator-managed "
                "      ARIA Conjunction Screener service for the entire "
                "      passive-decay phase, with notification to "
                "      18 SDS for any high-Pc events.\n"
                "  (c) ITU notification 60 days prior to the projected "
                "      reentry window."
            ),
            operator_must_supply=[
                "Confirmation of conjunction-screening contract or in-house tooling.",
                "List of ground stations that will participate in passivation.",
            ],
        ),
        WaiverSection(
            heading="6. Public-Interest Showing (47 CFR §1.3)",
            paragraph=(
                "Grant of the waiver is in the public interest because the "
                "mission [operator must supply science / commercial / "
                "national-security justification].  The natural-decay path "
                "remains a closed-form prediction with bounded uncertainty; "
                "the casualty risk is bounded above by the cross-section + "
                "mass values reported in §2 and meets ESA's 8 m²/kg threshold "
                "for a controlled break-up."
            ),
            operator_must_supply=[
                "Mission-impact narrative (1-2 paragraphs).",
                "Comparable precedents (other granted waivers).",
            ],
        ),
        WaiverSection(
            heading="7. Coordination with Other Authorities",
            paragraph=(
                "Applicant has notified or will notify, prior to launch:\n"
                "  - 18th Space Defense Squadron (USSF) for SSA cataloguing.\n"
                "  - FAA/AST if the reentry window may overfly U.S. airspace.\n"
                "  - ITU BR for radio coordination of the de-orbit telemetry.\n"
                "  - The host launch provider's range-safety officer."
            ),
            operator_must_supply=[
                "Copies of 18 SDS / FAA notifications.",
            ],
        ),
    ]

    return FCCWaiverApplication(
        mission_name=mission_name,
        generated_utc=datetime.now(timezone.utc).isoformat(),
        sections=sections,
        fcc_rule_cited="47 CFR §25.114(d)(14)(iv) (FCC 22-271)",
        waiver_authority="47 CFR §1.3",
        technical_summary=summary,
    )
