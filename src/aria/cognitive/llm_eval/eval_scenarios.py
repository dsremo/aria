"""Historical spacecraft-decision scenarios with documented ground truth.

Every scenario is sourced from public-domain mission reports +
peer-reviewed history; citations are inline. Each one is the
real situation as the people on the ground / in the spacecraft
saw it at the moment of the decision — not what we know now.

The scoring rubrics enumerate the key elements a good answer must
include. They are intentionally NOT exhaustive — a thoughtful answer
might add elements not in the rubric. The score measures *coverage*
of the historically-recognised key elements, not stylistic match
to the actual decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


# ── Scoring primitives ──────────────────────────────────────────


@dataclass(frozen=True)
class RubricCriterion:
    """One scorable element a good answer should contain.

    ``keywords`` are case-insensitive substrings any of which counts
    as a hit. Use multiple variants ("CO₂", "carbon dioxide", "scrubber")
    so the rubric isn't brittle to surface phrasing.
    """

    name: str
    description: str
    keywords: Tuple[str, ...]
    weight: float = 1.0          # contribution to the scenario score
    must_have: bool = False      # if True, missing this fails the scenario

    def matches(self, response_text: str) -> bool:
        text = response_text.lower()
        return any(kw.lower() in text for kw in self.keywords)


@dataclass(frozen=True)
class ScoringRubric:
    criteria: Tuple[RubricCriterion, ...]

    @property
    def total_weight(self) -> float:
        return sum(c.weight for c in self.criteria)

    def score(self, response_text: str) -> Tuple[float, List[str], List[str]]:
        """Return ``(fraction, hits, misses)`` for the response."""
        hits: List[str] = []
        misses: List[str] = []
        gained = 0.0
        for criterion in self.criteria:
            if criterion.matches(response_text):
                gained += criterion.weight
                hits.append(criterion.name)
            else:
                misses.append(criterion.name)
        if self.total_weight <= 0:
            return 0.0, hits, misses
        return gained / self.total_weight, hits, misses

    def must_have_misses(self, response_text: str) -> List[str]:
        return [
            c.name for c in self.criteria
            if c.must_have and not c.matches(response_text)
        ]


# ── Scenarios ───────────────────────────────────────────────────


@dataclass(frozen=True)
class EvalScenario:
    """A historical spacecraft-decision scenario for LLM evaluation."""

    id: str
    title: str
    date_iso: str
    situation: str
    constraints: Tuple[str, ...]
    ground_truth_decision: str
    ground_truth_outcome: str
    citation: str
    rubric: ScoringRubric
    # Maximum response tokens; the prompt asks the LLM to be concise.
    max_response_chars: int = 6000


# ── Apollo 13 CO₂ scrubber adapter (1970-04-14 to -15) ──────────


# Source: NASA SP-350 §11.6 + Houston-Apollo-13 Mission Report
# MSC-04098 §3.3 + Lovell & Kluger 1994 "Lost Moon" Ch. 14.
APOLLO_13_CO2 = EvalScenario(
    id="apollo_13_co2_scrubber",
    title="Apollo 13 CO₂ scrubber adapter crisis",
    date_iso="1970-04-14",
    situation=(
        "It is 56 hours into Apollo 13. The Service Module's oxygen tank #2 has "
        "exploded; the crew has retreated to the Lunar Module 'Aquarius' as a "
        "lifeboat. The LM is rated for 2 crew × 45 hours but must now sustain 3 "
        "crew × ~90 hours until Earth re-entry.\n\n"
        "Onboard CO₂ partial pressure is rising. The LM's lithium-hydroxide "
        "(LiOH) scrubber canisters are saturating. The crew has spare LiOH "
        "canisters in the Command Module 'Odyssey', but the CM and LM canisters "
        "use INCOMPATIBLE shapes — the CM uses square canisters, the LM uses "
        "round ones. Without a working scrubber the CO₂ partial pressure will "
        "exceed 15 mmHg (toxic threshold) within ~12 hours.\n\n"
        "Mission Control has assembled a team led by Ed Smylie (Crew Systems "
        "Division) to design an adapter the crew can build from items aboard. "
        "The clock is short; the adapter must be uplinkable as voice-readable "
        "construction instructions and buildable by the crew with no machine "
        "tools, no measuring instruments, in cold low-light low-power conditions "
        "with reduced cognitive performance from CO₂ + sleep deprivation."
    ),
    constraints=(
        "Items confirmed aboard the spacecraft (per Houston manifest):",
        "  - 4 spare square LiOH canisters from CM (each 4.5 in × 4.5 in × 4.5 in)",
        "  - Pressure suits including their hoses (corrugated, ~1 in dia)",
        "  - Rolls of grey duct tape ('grey tape')",
        "  - Plastic bags (Ziploc-style storage bags)",
        "  - Cardboard from flight-plan covers and book bindings",
        "  - Bungee cords",
        "  - Cue cards / paper",
        "  - Sock (one), towels",
        "Hard constraints:",
        "  - No machine tools, no measuring instruments, no soldering",
        "  - Voice-uplink instructions only (no diagrams the crew can see)",
        "  - Build time budget: ~1 hour with sleep-deprived crew",
        "  - Crew must build the adapter without unsealing the suit hoses or "
        "    breaking any item that is later needed for re-entry",
        "  - Result must seat against the LM scrubber inlet without leaks",
    ),
    ground_truth_decision=(
        "Smylie's team designed and uplinked a procedure ('the mailbox') that "
        "uses: the square CM LiOH canister itself as the scrubber bed; one "
        "plastic bag taped over one end as a flexible coupling; a corrugated "
        "suit hose taped into the bag as the air conduit; and a cardboard "
        "flight-plan cover taped on top as a pressure-distribution baffle. "
        "Grey tape seals every interface. The arrangement is stuffed into the "
        "LM's environmental-control duct so that the LM blower forces cabin air "
        "through the square canister via the hose."
    ),
    ground_truth_outcome=(
        "Built and installed within 1 hour by the crew. CO₂ partial pressure "
        "dropped from ~15 mmHg back to ~2 mmHg within 90 minutes and stayed "
        "controlled for the remaining ~50 hours of return flight. No subsequent "
        "CO₂ excursion. All 3 crew returned safely 1970-04-17."
    ),
    citation=(
        "NASA SP-350 §11.6; Houston-Apollo-13 Mission Report MSC-04098 §3.3; "
        "Lovell & Kluger 1994 'Lost Moon' Ch. 14."
    ),
    rubric=ScoringRubric(criteria=(
        RubricCriterion(
            name="identifies_co2_scrubber_geometry_mismatch",
            description="Recognises the canister shape incompatibility (square vs round)",
            keywords=("square", "round", "incompatible", "mismatch", "shape"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="proposes_use_of_cm_canister_as_scrubber_bed",
            description="Uses the CM LiOH canister itself (where the chemistry is)",
            keywords=("cm canister", "command module canister", "lioh canister",
                      "use the canister", "use the cm", "square canister"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="proposes_duct_tape_seal",
            description="Uses duct/grey tape as the seal medium",
            keywords=("duct tape", "grey tape", "gray tape", "tape"),
            weight=1.0,
        ),
        RubricCriterion(
            name="proposes_suit_hose_as_air_conduit",
            description="Uses a pressure-suit hose to conduct air to the canister",
            keywords=("suit hose", "pressure suit hose", "spacesuit hose",
                      "corrugated hose", "hose"),
            weight=1.0,
        ),
        RubricCriterion(
            name="proposes_plastic_bag_as_flexible_coupling",
            description="Uses a plastic bag as a flexible coupling/seal",
            keywords=("plastic bag", "ziploc", "storage bag", "bag"),
            weight=1.0,
        ),
        RubricCriterion(
            name="proposes_cardboard_baffle",
            description="Uses cardboard from flight-plan covers as a baffle/spacer",
            keywords=("cardboard", "flight plan cover", "flight-plan cover",
                      "book cover"),
            weight=1.0,
        ),
        RubricCriterion(
            name="addresses_voice_uplink_constraint",
            description="Acknowledges the instructions must be voice-readable",
            keywords=("voice", "voice uplink", "voice-readable", "verbal",
                      "spoken", "no diagram", "without diagrams"),
            weight=0.5,
        ),
        RubricCriterion(
            name="time_pressure_acknowledged",
            description="Mentions the ~12 hour CO₂-toxic deadline / hour budget",
            keywords=("12 hour", "12 hours", "time pressure", "1 hour", "deadline",
                      "co2 partial pressure", "15 mmhg", "toxic"),
            weight=0.5,
        ),
        RubricCriterion(
            name="addresses_lm_blower_for_airflow",
            description="Recognises LM blower must force air through the canister",
            keywords=("lm blower", "blower", "fan", "lm fan", "force air"),
            weight=0.5,
        ),
    )),
)


# ── Hubble SM4 reinstatement (2004-06-2006-10) ──────────────────


# Source: NASA Hubble SM4 Final Report 2008; Crippen 2003 NASA-MEM
# review of post-Columbia HST options; Griffin 2006 announcement
# transcript.
HUBBLE_SM4 = EvalScenario(
    id="hubble_sm4_reinstatement",
    title="Hubble Space Telescope Servicing Mission 4 reinstatement",
    date_iso="2006-10-31",
    situation=(
        "Hubble Space Telescope is in 565 km orbit, inclination 28.5°. The "
        "Columbia accident (2003-02-01) revealed that thermal-protection-system "
        "damage during ascent can be invisible from inside the orbiter; CAIB "
        "Recommendation R6.4-1 mandates safe-haven capability for every Shuttle "
        "mission post-RTF. ISS missions get safe-haven via the station; HST "
        "mission cannot reach ISS (different orbit, no Δv).\n\n"
        "NASA Administrator Sean O'Keefe canceled SM4 in 2004-01 on safety "
        "grounds. The decision was contested by the science community + a 2005 "
        "National Academy of Sciences review, which argued that without SM4 "
        "Hubble would lose its remaining gyros, batteries, and key instruments "
        "by ~2008-2010. Mike Griffin (new Administrator from 2005-04) is "
        "weighing whether to reinstate SM4.\n\n"
        "The SM4 manifest is intensive: install Wide Field Camera 3 + Cosmic "
        "Origins Spectrograph; repair STIS + ACS in-orbit (never done before); "
        "replace all 6 gyros, all 6 batteries, FGS-2; install Soft Capture "
        "Mechanism for eventual deorbit. Expected mission Δv from launch to "
        "rendezvous: ~225 m/s; servicing duration ~12 days; 5 EVAs."
    ),
    constraints=(
        "Hard constraints:",
        "  - CAIB R6.4-1 mandates safe-haven capability for every Shuttle flight",
        "  - HST orbit unreachable from ISS due to inclination + altitude mismatch",
        "  - Without SM4, Hubble loses science capability by 2008-2010 (gyros/batteries)",
        "  - SM4 has documented ~1-in-150 to 1-in-220 Loss-of-Crew probability",
        "    (post-RTF Shuttle PRA, vs ISS missions ~1-in-130)",
        "  - HST is irreplaceable in the 2010-2020 window (JWST not yet flying)",
        "Available options:",
        "  - Reinstate SM4 with a second Shuttle on standby for rescue (LON STS-400)",
        "  - Cancel SM4; let Hubble degrade naturally; deorbit when safe",
        "  - Robotic servicing mission (DARPA Orbital Express demoed 2007 — but",
        "    no rated robotic gyro replacement)",
        "  - Defer indefinitely pending a future capability (no funded plan)",
    ),
    ground_truth_decision=(
        "Mike Griffin announced 2006-10-31 that SM4 would be reinstated, with "
        "a second Shuttle (STS-400, Endeavour) standing by on Pad 39B for "
        "Launch-On-Need rescue if STS-125 (Atlantis) suffered orbiter damage at "
        "HST orbit. STS-125 launched 2009-05-11 and completed 5 EVAs over 12 "
        "days; STS-400 was demated after STS-125 returned safely."
    ),
    ground_truth_outcome=(
        "STS-125 returned safely 2009-05-24. Hubble received WFC3, COS, gyro "
        "+ battery replacement, STIS + ACS repair, Soft Capture Mechanism. "
        "HST has continued operating into the 2025+ era; SM4 is universally "
        "regarded as one of the most successful servicing missions in history. "
        "STS-400 was never launched (no rescue needed)."
    ),
    citation=(
        "NASA HST SM4 Final Report 2008; NAS 2005 'Assessment of Options for "
        "Extending the Life of HST'; Griffin 2006-10-31 announcement transcript."
    ),
    rubric=ScoringRubric(criteria=(
        RubricCriterion(
            name="recognises_caib_safe_haven_constraint",
            description="Cites CAIB R6.4-1 / Columbia / safe-haven requirement",
            keywords=("caib", "columbia", "safe haven", "safe-haven",
                      "tps damage", "thermal protection"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="recognises_iss_orbit_mismatch",
            description="Notes HST orbit incompatible with ISS (no safe-haven by ISS rendezvous)",
            keywords=("orbit mismatch", "different orbit", "inclination",
                      "cannot reach iss", "no delta-v to iss",
                      "565 km", "28.5"),
            weight=1.0,
        ),
        RubricCriterion(
            name="proposes_lon_rescue_shuttle",
            description="Proposes second Shuttle on standby for Launch-On-Need rescue",
            keywords=("standby", "lon", "launch on need", "launch-on-need",
                      "second shuttle", "rescue shuttle", "sts-400",
                      "standby orbiter"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="quantifies_loss_without_sm4",
            description="Quantifies what HST loses without servicing (gyros, batteries, instruments)",
            keywords=("gyros", "gyro", "batteries", "battery",
                      "instrument", "stis", "acs", "wfc3"),
            weight=1.0,
        ),
        RubricCriterion(
            name="risk_benefit_framing",
            description="Compares LoC risk against irreplaceable-science benefit",
            keywords=("risk", "loss of crew", "loc", "probability",
                      "1-in-", "benefit", "trade-off", "tradeoff"),
            weight=1.0,
        ),
        RubricCriterion(
            name="time_window_unique",
            description="Recognises the 2010-2020 unique-capability window (pre-JWST)",
            keywords=("jwst", "irreplaceable", "unique", "no replacement",
                      "successor", "until"),
            weight=0.5,
        ),
        RubricCriterion(
            name="considers_robotic_alternative",
            description="Considers and rules out robotic servicing alternative",
            keywords=("robotic", "darpa", "orbital express", "automated",
                      "uncrewed servicing"),
            weight=0.5,
        ),
        RubricCriterion(
            name="recommends_proceed_with_sm4",
            description="Concludes that SM4 should proceed (with mitigation)",
            keywords=("proceed", "reinstate", "go ahead", "carry out",
                      "approve", "should fly", "should be flown"),
            weight=1.0,
            must_have=True,
        ),
    )),
)


# ── ISS Russian-segment leak (2019-09 to present) ───────────────


# Source: NASA OIG IG-22-019 ISS Transition Report; NASA HQ 2024-09-12
# briefing transcript on Zvezda PrK leak; Roscosmos / NASA Joint
# Pressure-Decay Investigation Reports (JPDIR) 2020-2024.
ISS_RUSSIAN_LEAK = EvalScenario(
    id="iss_russian_segment_leak",
    title="ISS Russian-segment Zvezda transfer-tunnel leak",
    date_iso="2024-09-12",
    situation=(
        "ISS Zvezda module's Transfer Tunnel ('PrK') has a chronic air leak, "
        "first detected 2019-09 and characterised over multiple Joint "
        "Pressure-Decay Investigations (JPDIR) since. The leak rate has trended "
        "upward over years: ~270 g/day in 2020-2021, ~520 g/day in 2023-2024. "
        "Multiple repair attempts have located + patched some cracks but the "
        "underlying root cause appears to be metal fatigue in welds.\n\n"
        "Crew has been operating with hatch closures: PrK hatch is closed when "
        "not in use, isolating the segment from the rest of Zvezda when the "
        "leak rate would otherwise drive station ATM make-up consumption "
        "above the ECLSS budget. A 2024 NASA Inspector-General report rates "
        "the leak as 'highest concern' for ISS structural risk.\n\n"
        "ISS is funded through 2030; Russian segment is committed through 2028 "
        "minimum. Replacement (US Deorbit Vehicle launch ~2028, controlled "
        "deorbit ~2030-2031) is in procurement. The decision is whether to "
        "tolerate the leak through end-of-mission, attempt a more aggressive "
        "repair (welding, segment isolation), or move up the deorbit timeline."
    ),
    constraints=(
        "Hard constraints:",
        "  - ISS hardware lifetime: NASA 2030 / Roscosmos 2028+",
        "  - Atmospheric make-up: O₂/N₂ supplied by Progress + Cygnus (limited)",
        "  - Crew safety: PrK is a transfer tunnel; explosive depressurization risk",
        "    if a crack propagates suddenly under thermal cycling",
        "  - Russian Federal Space Agency (Roscosmos) has primary responsibility",
        "    for Zvezda; NASA cannot unilaterally repair / modify",
        "  - In-orbit welding never demonstrated (would require Russian EVA)",
        "  - Replacement deorbit vehicle (USDV, SpaceX): NET 2028",
        "Operational mitigations already in place:",
        "  - PrK hatch closed when not in use (Roscosmos 2020)",
        "  - Regular leak-rate measurement + structural inspection EVAs",
        "  - Limit non-essential traffic through PrK",
    ),
    ground_truth_decision=(
        "NASA + Roscosmos jointly: maintain PrK hatch-closed-when-not-in-use "
        "policy; continue make-up resupply via Progress / Cygnus; do NOT "
        "attempt in-orbit weld; monitor leak rate continuously with an "
        "agreed escalation threshold; plan for ISS deorbit on schedule "
        "(USDV launch NET 2028, controlled deorbit NET 2030). Crew is "
        "instructed to use PrK only for essential transfers and to evacuate "
        "Zvezda first if leak rate spikes."
    ),
    ground_truth_outcome=(
        "Leak rate continues to rise but slowly; PrK hatch policy holds. "
        "ISS still operational as of 2026-04. USDV procurement on track. "
        "No explosive depressurization event has occurred. (ARIA's eval is "
        "scored against this incremental approach as the documented "
        "ground-truth response, NOT against any aggressive alternative.)"
    ),
    citation=(
        "NASA OIG IG-22-019 ISS Transition Report; NASA HQ 2024-09-12 "
        "briefing transcript on Zvezda PrK leak; JPDIR reports 2020-2024."
    ),
    rubric=ScoringRubric(criteria=(
        RubricCriterion(
            name="recognises_chronic_leak_metal_fatigue_root_cause",
            description="Diagnoses the root cause as metal fatigue / welds",
            keywords=("metal fatigue", "weld", "fatigue", "crack",
                      "structural", "thermal cycling"),
            weight=1.0,
            must_have=True,
        ),
        RubricCriterion(
            name="recommends_hatch_isolation_policy",
            description="Recommends keeping PrK hatch closed when not in use",
            keywords=("hatch closed", "close the hatch", "hatch closure",
                      "isolation", "isolate", "isolate the segment",
                      "segment isolation"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="recognises_crew_safety_priority",
            description="Prioritises crew safety / explosive-depress risk",
            keywords=("crew safety", "explosive decompression",
                      "explosive depressurization", "rapid depressurization",
                      "evacuate", "decompression"),
            weight=1.0,
        ),
        RubricCriterion(
            name="rules_out_in_orbit_weld",
            description="Rules out in-orbit welding (never demonstrated, EVA-heavy)",
            keywords=("welding", "weld", "not feasible", "never demonstrated",
                      "rule out", "not attempt"),
            weight=0.75,
        ),
        RubricCriterion(
            name="recognises_make_up_atmosphere_supply",
            description="Notes O₂/N₂ resupply from Progress / Cygnus / cargo",
            keywords=("progress", "cygnus", "resupply", "make up",
                      "make-up", "atmosphere supply", "n2", "o2"),
            weight=0.5,
        ),
        RubricCriterion(
            name="trends_leak_rate_with_escalation_threshold",
            description="Continues leak-rate monitoring with a stated escalation threshold",
            keywords=("monitor", "trend", "rate", "threshold", "escalation",
                      "trip point", "limit"),
            weight=0.75,
        ),
        RubricCriterion(
            name="aligns_with_iss_eom_2030_or_usdv",
            description="Plans for / acknowledges ISS EoM 2030 + USDV deorbit",
            keywords=("2030", "end of mission", "eom", "deorbit",
                      "usdv", "deorbit vehicle", "spacex"),
            weight=0.75,
        ),
        RubricCriterion(
            name="acknowledges_russian_segment_authority",
            description="Notes Roscosmos primary responsibility for Zvezda",
            keywords=("roscosmos", "russian", "russia", "russian federal",
                      "rfsa"),
            weight=0.5,
        ),
        RubricCriterion(
            name="conservative_incremental_response",
            description="Recommends a conservative, incremental response (NOT aggressive intervention)",
            keywords=("monitor", "incremental", "conservative", "do not",
                      "tolerate", "manage", "continue current",
                      "maintain"),
            weight=1.0,
            must_have=True,
        ),
    )),
)


# ── Apollo 11 LM 1201/1202 program alarms during landing (1969-07-20) ──


# Source: Apollo 11 Mission Report MSC-04112 §5.10; Eyles 2018 "Sunburst
# and Luminary" Ch. 24; Mindell 2008 "Digital Apollo" Ch. 8;
# Bales / Garman / Aldrin oral histories (NASA JSC OH).
APOLLO_11_PROGRAM_ALARMS = EvalScenario(
    id="apollo_11_1201_1202_alarms",
    title="Apollo 11 LM Guidance Computer 1201/1202 program alarms during powered descent",
    date_iso="1969-07-20",
    situation=(
        "The Apollo 11 Lunar Module 'Eagle' is in powered descent — Armstrong "
        "and Aldrin ~6 minutes into a 12-minute braking + approach phase, ~6 km "
        "above the lunar surface. The LM Guidance Computer (LGC) is running "
        "Program 63 (powered descent) and has just been commanded to bring up "
        "rendezvous-radar tracking data per the flight plan to support an abort-"
        "to-rendezvous if needed.\n\n"
        "At T-0:05:30 (mission elapsed) the LGC throws a 1202 program alarm: "
        "'EXECUTIVE OVERFLOW — NO CORE SETS'. Aldrin reads it down to MOCR. The "
        "alarm repeats at intervals of ~30 seconds, then changes to 1201 "
        "('EXECUTIVE OVERFLOW — NO VAC AREAS') as the descent continues. The "
        "LGC display freezes momentarily on each alarm, then resumes. Computer "
        "behaviour otherwise looks correct — guidance, navigation, and throttle "
        "control are still feeding the engine.\n\n"
        "GUIDO controller Steve Bales has ~10 seconds per alarm to call GO/NO-GO "
        "to FLIGHT (Gene Kranz). The crew is asking, 'What's the program alarm?'  "
        "The LM is running out of altitude; the descent profile cannot be "
        "indefinitely paused. An abort would jettison the descent stage, fire "
        "the ascent engine, and try to rendezvous with Columbia."
    ),
    constraints=(
        "Hard constraints:",
        "  - Powered descent has < 6 min remaining; cannot pause indefinitely",
        "  - LGC has 4 KB erasable + 36 KB fixed memory (Block II AGC)",
        "  - Each alarm code documents an 'executive scheduler' resource ",
        "    exhaustion: 1201 = no Vector Accumulator areas, 1202 = no Core sets",
        "  - 'Bailout' code in the LGC restarts only the most recent jobs and ",
        "    preserves the highest-priority guidance job (Eyles' priority-",
        "    interrupt design) — this is the documented behaviour",
        "  - Abort-to-rendezvous would discard the landing attempt, return to ",
        "    Columbia at unknown rendezvous geometry",
        "  - Communication latency to MOCR: ~1.3 s each way",
        "Available diagnostic info (in order of arrival):",
        "  - Alarm code: 1202, then 1201 — both 'executive overflow'",
        "  - LGC display recovers within a second of each alarm",
        "  - Engine throttle, attitude, descent rate all reading nominal",
        "  - Rendezvous radar mode switch position: 'AUTO' (the cause, ",
        "    confirmed only post-flight)",
        "Personnel:",
        "  - GUIDO Steve Bales (24 yo, MIT-trained; has the call)",
        "  - Backroom support: Jack Garman (NASA JSC, has the AGC alarm",
        "    cheat-sheet card in his console)",
    ),
    ground_truth_decision=(
        "Bales, after consulting Garman, called GO at each alarm: 'We're GO on "
        "that alarm.' Garman's pre-mission cheat-sheet listed 1201 / 1202 as ',"
        "GO unless they recur in rapid succession.' The reasoning: the LGC's "
        "Eyles-designed priority-interrupt scheduler was designed to drop "
        "low-priority jobs and keep guidance running — so as long as the "
        "computer was recovering from each alarm and continuing the descent "
        "guidance, the alarm itself was non-fatal. Continue the descent; "
        "monitor for compounding failure (which never came)."
    ),
    ground_truth_outcome=(
        "Eagle landed at Tranquility Base with ~30 seconds of fuel remaining "
        "(the alarms ate ~6 % of the descent margin). Post-flight analysis "
        "found the rendezvous-radar mode switch was wired to keep its "
        "counter active even when set to AUTO, dumping ~13 % of the LGC "
        "duty cycle into a job that didn't need to run. Without Eyles' "
        "priority-interrupt design + Garman's cheat-sheet + Bales' call, "
        "Apollo 11 would have aborted to rendezvous and the first lunar "
        "landing would have slipped to a later mission."
    ),
    citation=(
        "Apollo 11 Mission Report MSC-04112 §5.10; Eyles 2018 'Sunburst and "
        "Luminary' Ch. 24; Mindell 2008 'Digital Apollo' Ch. 8; "
        "Bales / Garman / Aldrin oral histories (NASA JSC OH)."
    ),
    rubric=ScoringRubric(criteria=(
        RubricCriterion(
            name="recognises_executive_overflow_meaning",
            description="Identifies 1201/1202 as executive scheduler resource exhaustion",
            keywords=("executive overflow", "scheduler", "no core sets",
                      "no vac", "vector accumulator", "resource exhaustion",
                      "overload"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="recognises_priority_interrupt_recovery",
            description="Notes the LGC's Eyles-designed priority-interrupt / bailout recovery",
            keywords=("priority interrupt", "priority-interrupt", "bailout",
                      "restart", "drops low-priority", "preserves guidance",
                      "recovers", "self-recovers", "graceful"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="recommends_continue_descent",
            description="Calls GO and continues the descent",
            keywords=("go", "continue", "do not abort", "press on",
                      "proceed with descent", "land"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="recognises_rendezvous_radar_likely_culprit",
            description="Suspects the rendezvous-radar duty-cycle as the load source",
            keywords=("rendezvous radar", "radar", "switch", "rr mode",
                      "duty cycle", "extra load"),
            weight=1.0,
        ),
        RubricCriterion(
            name="time_pressure_acknowledged",
            description="Acknowledges the < 6 min descent budget / fuel margin",
            keywords=("6 min", "minutes", "fuel", "altitude", "descent",
                      "margin", "time pressure"),
            weight=0.5,
        ),
        RubricCriterion(
            name="monitor_for_compounding_failure",
            description="Specifies what would warrant abort (compounding / different alarm)",
            keywords=("monitor", "rapid succession", "different alarm",
                      "compounding", "sustained", "would abort if"),
            weight=1.0,
        ),
        RubricCriterion(
            name="rejects_abort_unless_compounding",
            description="Argues against immediate abort with the alarm alone",
            keywords=("not abort", "do not abort", "no abort", "rejects abort",
                      "abort would", "refuse abort"),
            weight=1.0,
        ),
        RubricCriterion(
            name="cites_pre_mission_alarm_table",
            description="References the AGC alarm cheat-sheet / pre-mission table",
            keywords=("cheat sheet", "cheat-sheet", "alarm table", "alarm card",
                      "garman", "pre-mission"),
            weight=0.5,
        ),
    )),
)


# ── Apollo 12 SCE to AUX (1969-11-14) ──────────────────────────────


# Source: Apollo 12 Mission Report MSC-01855 §5.1; John Aaron NASA JSC
# oral history; Cernan/Conrad transcripts; Brian Brand 2015 "When the
# Lightning Struck Apollo 12".
APOLLO_12_LIGHTNING = EvalScenario(
    id="apollo_12_sce_to_aux",
    title="Apollo 12 lightning strike post-launch — 'SCE to AUX' call",
    date_iso="1969-11-14",
    situation=(
        "Apollo 12 launched into bad weather at 11:22 EST. At T+36.5 seconds "
        "(altitude ~2 km, max-Q regime) the vehicle is struck by lightning. "
        "At T+52 seconds, a second strike. Inside the Command Module, every "
        "alarm light on the panel illuminates. The Caution & Warning system "
        "shows fuel-cell disconnect, AC bus failure, and dozens of out-of-"
        "tolerance reads. The PCM telemetry stream (Pulse Code Modulated) "
        "downlinked to MOCR has gone garbled — flight controllers see "
        "noise where they used to see structured frames.\n\n"
        "The Saturn V's Instrument Unit guidance computer is unaffected (it's "
        "on the launch vehicle, not the spacecraft). The S-IC and S-II are "
        "performing nominally. The vehicle is still on the planned trajectory. "
        "The crew (Conrad / Gordon / Bean) reports the cabin is dark — the "
        "displays have flipped to ALL-ON or ALL-OFF, and they cannot tell "
        "which systems are live.\n\n"
        "MOCR has < 5 minutes to decide whether to call ABORT. CapCom must "
        "advise the crew. The launch profile is still nominal per Saturn IU "
        "telemetry; only the spacecraft side is reading garbage. EECOM John "
        "Aaron is the controller responsible for spacecraft electrical."
    ),
    constraints=(
        "Hard constraints:",
        "  - Saturn V trajectory still nominal per IU telemetry",
        "  - Spacecraft (CSM) electrical telemetry: garbage / noise",
        "  - Cabin displays: blanked / illegible from crew perspective",
        "  - PCM downlink: corrupted (cannot diagnose from ground)",
        "  - < 5 minutes to next major decision point (S-IC cutoff)",
        "  - Abort options: Mode IA (Saturn V Range Safety destruct + LES",
        "    pull-away) or Mode IB (LES pull-away after staging)",
        "Available diagnostic info:",
        "  - All C&W lights ON simultaneously (suggests common-mode fault)",
        "  - Saturn IU is fine (suggests problem isolated to spacecraft)",
        "  - Crew reports cabin smell normal, no fire",
        "Available system knobs (CSM electrical):",
        "  - SCE (Signal Conditioning Equipment) switch positions:",
        "      NORMAL — operates from main DC bus",
        "      AUX — operates from auxiliary low-voltage backup",
        "      OFF",
        "  - Fuel cells 1, 2, 3 main bus connect / disconnect",
        "  - AC inverter bus 1, 2 select",
        "Personnel context:",
        "  - EECOM John Aaron (24 yo) saw 'all-zero / all-one' SCE pattern",
        "    once before in a 1968 simulator test — knew the recovery",
        "  - Decision-maker authority: FLIGHT (Gerry Griffin)",
    ),
    ground_truth_decision=(
        "John Aaron called: 'Try SCE to AUX.' CapCom Gerry Carr passed it up: "
        "'Apollo 12, Houston. Try SCE to AUX. Over.' Bean (LMP, who knew "
        "where the SCE switch was) flipped it. Telemetry returned within "
        "seconds. Conrad and Gordon then reset the fuel-cell disconnects "
        "from the now-readable panel. The mission continued to the moon."
    ),
    ground_truth_outcome=(
        "Telemetry restored, fuel cells re-connected, vehicle continued the "
        "lunar mission. Apollo 12 landed at the Surveyor 3 site (Ocean of "
        "Storms) with crew + LM intact. The 'SCE to AUX' call became "
        "iconic in NASA training and is taught as the canonical example "
        "of a deep-system-knowledge save under time pressure."
    ),
    citation=(
        "Apollo 12 Mission Report MSC-01855 §5.1; John Aaron NASA JSC oral "
        "history; Conrad / Bean post-mission debrief transcripts; Brian "
        "Brand 2015 'When the Lightning Struck Apollo 12'."
    ),
    rubric=ScoringRubric(criteria=(
        RubricCriterion(
            name="diagnoses_lightning_strike",
            description="Identifies lightning as the cause of the cascading C&W lights",
            keywords=("lightning", "strike", "electrical surge",
                      "atmospheric discharge"),
            weight=1.0,
            must_have=True,
        ),
        RubricCriterion(
            name="recognises_common_mode_signal_conditioning",
            description="Diagnoses signal conditioning / SCE as the failure point (not the systems themselves)",
            keywords=("sce", "signal conditioning", "telemetry corruption",
                      "garbled telemetry", "common mode", "common-mode"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="recommends_sce_to_aux",
            description="Calls 'SCE to AUX' (the specific known-recovery action)",
            keywords=("sce to aux", "sce aux", "auxiliary",
                      "aux backup", "switch to aux"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="recognises_saturn_iu_independent",
            description="Notes Saturn V IU telemetry is independent and still good",
            keywords=("saturn iu", "instrument unit", "iu telemetry",
                      "launch vehicle", "saturn v telemetry",
                      "trajectory nominal"),
            weight=1.0,
        ),
        RubricCriterion(
            name="rejects_abort_with_iu_nominal",
            description="Argues against abort while Saturn IU + trajectory nominal",
            keywords=("not abort", "do not abort", "no abort", "reject abort",
                      "trajectory ok", "trajectory nominal", "abort would"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="recovers_fuel_cells_after_telemetry",
            description="Plans to re-connect fuel cells once telemetry is back",
            keywords=("fuel cell", "fuel-cell reconnect", "main bus",
                      "reset disconnect", "reconnect"),
            weight=0.75,
        ),
        RubricCriterion(
            name="acknowledges_time_pressure",
            description="Acknowledges < 5 min decision window / S-IC cutoff",
            keywords=("5 min", "minutes", "time pressure", "before staging",
                      "before s-ic", "before sic"),
            weight=0.5,
        ),
        RubricCriterion(
            name="prior_simulator_pattern_match",
            description="Notes the all-zero / all-one pattern from training data",
            keywords=("simulator", "training", "saw before", "pattern match",
                      "1968 sim", "prior sim"),
            weight=0.5,
        ),
    )),
)
# ── Mir Spektr depressurization (1997-06-25) ──────────────────────


# Source: NASA Mir 24 Postflight Report; Foale 1999 'Mission Mir' personal
# log; Linenger 2000 'Off the Planet'; NASA-Mir Phase 1 final report;
# IFR Progress M-34 collision investigation (Roscosmos 1997).
MIR_SPEKTR_DEPRESS = EvalScenario(
    id="mir_spektr_depressurization",
    title="Mir Spektr module depressurization after Progress collision",
    date_iso="1997-06-25",
    situation=(
        "It is 09:18 UTC. NASA-4 astronaut Mike Foale is aboard Mir with "
        "Russian commander Vasily Tsibliyev and engineer Sasha Lazutkin. They "
        "have just executed a manual TORU (tele-robotic) docking test of an "
        "uncrewed Progress M-34 freighter — the test was specifically designed "
        "to substitute for a scheduled automatic Kurs docking after Kurs "
        "hardware was returned to Earth.\n\n"
        "The Progress, controlled manually by Tsibliyev via TORU monitor, "
        "approached too fast and at the wrong angle. It struck the Spektr "
        "science module a glancing blow on its solar array, then impacted the "
        "module body itself near a cargo door. Mir's master alarm sounds: "
        "DEPRESSURIZATION. Cabin pressure is dropping at ~0.1 atm/min. The "
        "leak is in Spektr — Foale can hear hissing through the open hatch.\n\n"
        "Spektr contains: Foale's personal effects + sleep station; the NASA-4 "
        "experiment payload; the EVA pressure suits; AND ~50 % of Mir's solar-"
        "panel power generation (4 of 8 panels feed via Spektr cables to the "
        "main bus). If the entire station depressurizes, the crew dies. The "
        "Soyuz TM-25 lifeboat is docked at Kvant — they could evacuate, but "
        "abandoning Mir is irreversible. The hissing is louder near Spektr's "
        "hatch.\n\n"
        "Time to vacuum if leak continues: ~22 minutes."
    ),
    constraints=(
        "Hard constraints:",
        "  - Cabin pressure dropping ~0.1 atm/min; ~22 min to fatal",
        "  - Communication with TsUP (Russian mission control) is intermittent",
        "    — they're below the horizon for the next ~30 min",
        "  - Soyuz TM-25 evacuation is available but irreversible",
        "  - Spektr hatch has ~18 power + data cables passing through it that",
        "    must be cut or disconnected before the hatch can close + seal",
        "  - The cables include the Spektr solar-array feed (~50 % of station",
        "    power generation)",
        "  - The hatch is held open by the cables; closing it requires manual",
        "    cable severing",
        "  - No pre-prepared emergency procedure exists for this exact case",
        "  - Foale's EVA suits are inside Spektr (lost if isolated)",
        "Available items aboard:",
        "  - Wire cutters, snippers, knives in standard tool kit",
        "  - Crew-rated breathing masks (limited duration)",
        "  - Soyuz TM-25 (lifeboat at Kvant)",
        "  - Hatch with rubber gasket; pressure on the high-pressure side ",
        "    helps it seal",
        "Personnel:",
        "  - Tsibliyev (Cmdr), Lazutkin (Eng), Foale (NASA): 3 person crew",
        "  - Tsibliyev shaken; Foale + Lazutkin function-capable",
    ),
    ground_truth_decision=(
        "Lazutkin and Foale severed the ~18 cables passing through the Spektr "
        "hatch using snippers from the tool kit. They closed and dogged the "
        "hatch before cabin pressure crossed the survival threshold. The "
        "station lost 50 % of solar generation but retained survival pressure "
        "in all other modules. Mir was put into a slow-spin, sun-pointing "
        "attitude to maximize remaining-panel output while ground prepared a "
        "recovery plan."
    ),
    ground_truth_outcome=(
        "Crew survived. Mir continued operations on degraded power for the "
        "remaining NASA-Mir program. A subsequent EVA into the depressurized "
        "Spektr (1997-08-22) re-routed power feeds to the main bus and "
        "sealed the suspected leak source. NASA-Mir continued to STS-91 in "
        "1998. The incident drove the requirement that ISS modules be able "
        "to be sealed off without cable-severing — ISS modules use sealable "
        "feedthroughs as standard."
    ),
    citation=(
        "NASA Mir 24 Postflight Report; Foale 1999 'Mission Mir' personal "
        "log; Linenger 2000 'Off the Planet'; NASA-Mir Phase 1 Final Report; "
        "Progress M-34 collision investigation (Roscosmos 1997)."
    ),
    rubric=ScoringRubric(criteria=(
        RubricCriterion(
            name="recognises_isolate_spektr_priority",
            description="Identifies isolating Spektr as the immediate priority",
            keywords=("isolate spektr", "seal spektr", "close hatch",
                      "isolate the leak", "seal off spektr",
                      "close the hatch", "shut hatch"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="recommends_cable_severing",
            description="Plans to sever the cables blocking the hatch",
            keywords=("sever cable", "cut cable", "snip cable",
                      "cut the cable", "severing", "snippers", "cut wires",
                      "wire cutter"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="acknowledges_power_loss_tradeoff",
            description="Recognises the 50 % solar-power loss tradeoff",
            keywords=("50%", "50 percent", "half", "solar array",
                      "power loss", "power generation", "lose power"),
            weight=1.0,
            must_have=True,
        ),
        RubricCriterion(
            name="time_budget_22_min",
            description="Quantifies the ~22 min depressurization window",
            keywords=("22 min", "20 min", "minutes", "depressurization rate",
                      "0.1 atm/min", "before vacuum",
                      "before fatal"),
            weight=0.5,
        ),
        RubricCriterion(
            name="rejects_immediate_evacuation",
            description="Argues against immediate Soyuz evacuation if isolation possible",
            keywords=("not abandon", "not evacuate", "soyuz reserve",
                      "stay aboard", "save the station", "do not abandon"),
            weight=1.0,
        ),
        RubricCriterion(
            name="post_isolation_attitude_recovery",
            description="Plans degraded-power attitude (sun-pointing) after isolation",
            keywords=("sun point", "sun-point", "sun pointing", "spin",
                      "attitude", "maximize panel", "remaining panel",
                      "remaining-panel", "slow spin"),
            weight=1.0,
        ),
        RubricCriterion(
            name="comm_blackout_independence",
            description="Notes the call must be made without TsUP comms",
            keywords=("comms blackout", "no communication", "without ground",
                      "tsup", "below horizon", "loss of signal",
                      "comm gap"),
            weight=0.5,
        ),
        RubricCriterion(
            name="loss_of_eva_suits_acknowledged",
            description="Acknowledges loss of EVA suits inside Spektr",
            keywords=("eva suit", "spacesuit", "lose suit", "no eva",
                      "without eva", "suits inside spektr"),
            weight=0.5,
        ),
        RubricCriterion(
            name="prefers_irreversible_action_only_if_needed",
            description="Treats Soyuz evacuation as last resort, not first",
            keywords=("last resort", "fallback", "if isolation fails",
                      "if hatch fails", "only if", "evacuation is",
                      "soyuz only"),
            weight=0.5,
        ),
    )),
)


# ── STS-114 RTF gap-filler EVA (2005-08-03) ─────────────────────────


# Source: NASA STS-114 Mission Report 2005; CAIB Report Vol 1; Robinson
# EVA debrief; Wayne Hale's blog "Pulling out the gap fillers"; Discovery
# OBSS imagery analysis report.
STS_114_GAP_FILLER = EvalScenario(
    id="sts_114_gap_filler_eva",
    title="STS-114 Discovery — gap-filler protrusion + decision to perform repair EVA",
    date_iso="2005-08-03",
    situation=(
        "STS-114, the first Shuttle Return-to-Flight mission after Columbia. "
        "Discovery is at the ISS during docked operations. The crew has "
        "performed unprecedented imagery surveys of the orbiter underbelly "
        "with the new Orbiter Boom Sensor System (OBSS) plus ISS RPM (Rendezvous "
        "Pitch Manoeuvre) photography from Expedition 11.\n\n"
        "Imagery analysis identifies two ceramic-fabric 'gap fillers' protruding "
        "from between thermal-protection-system tiles on Discovery's belly — "
        "one near the nose-landing-gear door (sticking out ~2.9 cm), one near "
        "the body-flap area (~2.0 cm). Gap fillers are normally flush with "
        "the tile surface; they exist to prevent inter-tile thermal-shock "
        "damage on ascent.\n\n"
        "Aerothermal analysis from JSC indicates that protruding gap fillers "
        "could cause boundary-layer transition from laminar to turbulent flow "
        "earlier than design, raising local heating on the downstream tile "
        "field by 100-300 °C and exceeding the design temperature of nearby "
        "tiles. The exact transition trigger threshold is uncertain — published "
        "wind-tunnel data is sparse for this exact protrusion height + "
        "Reynolds number. There is no in-flight precedent for repairing or "
        "removing protruding gap fillers.\n\n"
        "Options under MOCR consideration: (1) accept-as-is and re-enter; "
        "(2) ad-hoc EVA from the ISS to manually pull / cut the gap fillers; "
        "(3) request Soyuz return for Discovery crew + abandon orbiter (no "
        "supported by sufficient Soyuz seats); (4) launch Atlantis as STS-300 "
        "rescue if needed."
    ),
    constraints=(
        "Hard constraints:",
        "  - First post-Columbia RTF; risk tolerance is asymmetric (one TPS",
        "    failure ends the Shuttle program)",
        "  - Aerothermal model: protruding gap filler raises downstream",
        "    heating by 100-300 °C over design",
        "  - No in-flight precedent for gap-filler removal EVA",
        "  - ISS is docked; EVA from ISS airlock is feasible",
        "  - Discovery's robotic arm + OBSS can position the EVA crew but",
        "    the orbiter belly is not designed for crew access",
        "  - Crew time available for EVA prep + execution: ~24 hours",
        "Available capabilities:",
        "  - Steve Robinson trained for orbital EVA tasks generically",
        "  - Forceps + tweezers + scissors in EVA tool caddy",
        "  - SAFER backpack for emergency self-rescue if untethered",
        "  - OBSS as a manipulator-plus-camera platform",
        "  - Atlantis (STS-300) on standby for crew rescue if Discovery is",
        "    declared unsafe to enter",
        "Risk inputs:",
        "  - EVA risk: damage to TPS during the EVA itself if Robinson",
        "    inadvertently contacts other tiles",
        "  - Re-entry risk if accept-as-is: transition + downstream",
        "    overheating, low-confidence statistical estimate",
    ),
    ground_truth_decision=(
        "MOCR + the NASA Mission Management Team decided to perform an EVA "
        "to remove the protruding gap fillers. EVA-3 (2005-08-03) had "
        "Stephen Robinson positioned by the ISS Canadarm2 + Discovery OBSS "
        "to a station beneath Discovery's belly. He pulled the first gap "
        "filler out by hand (came free easily); the second was trimmed with "
        "EVA forceps. The repair took ~6 minutes. The remainder of EVA-3 "
        "was nominal."
    ),
    ground_truth_outcome=(
        "Discovery returned safely. Post-flight TPS inspection found NO "
        "evidence of unusual heating in the regions where gap fillers had "
        "been removed (consistent with the EVA succeeding). The mission "
        "was declared a successful Return-to-Flight; STS-300 stand-by was "
        "stood down. Future Shuttle missions added the gap-filler-removal "
        "EVA to the standard contingency procedure."
    ),
    citation=(
        "NASA STS-114 Mission Report 2005; CAIB Report Vol 1; "
        "Robinson EVA debrief; Wayne Hale 'Pulling out the gap fillers' "
        "blog post 2010; STS-114 OBSS imagery analysis report."
    ),
    rubric=ScoringRubric(criteria=(
        RubricCriterion(
            name="recognises_aerothermal_concern",
            description="Identifies boundary-layer transition / heating risk from protrusion",
            keywords=("boundary layer", "boundary-layer", "transition",
                      "turbulent", "laminar", "heating", "aerothermal",
                      "heat transfer"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="recommends_eva_removal",
            description="Recommends performing a contingency EVA to remove the gap fillers",
            keywords=("eva removal", "perform eva", "remove gap filler",
                      "remove the gap", "extract", "pull out", "trim",
                      "contingency eva"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="cites_canadarm2_obss_positioning",
            description="Plans to use Canadarm2 / OBSS to position the EVA crew",
            keywords=("canadarm", "robotic arm", "obss", "boom sensor",
                      "positioning", "manipulator", "orbiter boom"),
            weight=1.0,
        ),
        RubricCriterion(
            name="quantifies_protrusion_heights",
            description="References the actual protrusion measurements (2.9 + 2.0 cm)",
            keywords=("2.9 cm", "2.0 cm", "29 mm", "20 mm",
                      "protrusion height", "protrusion of", "sticking out"),
            weight=0.5,
        ),
        RubricCriterion(
            name="rejects_crew_rescue_mode",
            description="Doesn't escalate to STS-300 / abandon-orbiter without trying repair",
            keywords=("not abandon", "before sts-300", "before rescue",
                      "before crew rescue", "less invasive",
                      "try repair first", "before declaring"),
            weight=0.75,
        ),
        RubricCriterion(
            name="acknowledges_eva_risk_to_tps",
            description="Acknowledges the EVA itself could damage adjacent TPS",
            keywords=("eva risk", "damage tps", "damage tiles",
                      "contact other tile", "inadvertent contact",
                      "tile damage"),
            weight=0.75,
        ),
        RubricCriterion(
            name="post_columbia_risk_tolerance",
            description="Frames the decision in post-Columbia risk-tolerance context",
            keywords=("columbia", "rtf", "return to flight",
                      "post-columbia", "first flight after", "asymmetric",
                      "risk tolerance"),
            weight=1.0,
        ),
        RubricCriterion(
            name="prefers_minimum_invasive_repair",
            description="Recommends pulling rather than cutting where possible",
            keywords=("pull by hand", "pull out", "manual extraction",
                      "less invasive", "pull first", "tug",
                      "minimum invasive"),
            weight=0.5,
        ),
    )),
)


# ── SOHO 1998 contact loss + recovery (1998-06-25 to 1998-09-16) ──────


# Source: ESA SOHO Mission Recovery Final Report 1998; NASA SOHO Recovery
# Investigation Board Report 1998-09; ESA SOHO operations log; AAS
# Astronautical Engineering Conference 1999 paper "SOHO: The Recovery".
SOHO_1998_RECOVERY = EvalScenario(
    id="soho_1998_recovery",
    title="SOHO contact loss + spinning-spacecraft recovery (June–September 1998)",
    date_iso="1998-06-25",
    situation=(
        "The Solar and Heliospheric Observatory (SOHO) — a joint ESA/NASA "
        "spacecraft at the Sun-Earth L1 Lagrange point — has lost contact. "
        "The last telemetry was received at 04:43 UTC on 1998-06-25 during "
        "an Engineering Maintenance Operation that involved (a) gyro 'A' "
        "calibration, (b) a brief disabling of fault-protection software so "
        "that the calibration could complete without trip, and (c) a sequence "
        "of attitude-control system commands that *should* have been routine.\n\n"
        "Post-loss reconstruction shows that the calibration sequence inadvertently "
        "swapped the active gyro from gyro 'A' to gyro 'B' to gyro 'A' in rapid "
        "succession; gyro 'B' had a known small bias not accounted for in the "
        "fault-protection software (which was disabled); the spacecraft drifted "
        "off Sun-pointing; the now-unsupervised reaction wheels saturated; "
        "SOHO entered a slow flat-spin around its Z-axis (estimated rate "
        "~1 rpm based on the last attitude derivative).\n\n"
        "The spacecraft has tumbled out of the Earth-side antenna pattern. "
        "ESA + NASA + Goldstone DSN have been searching for SOHO carrier "
        "for ~7 weeks at L1 with no detection. The spacecraft is presumed "
        "to be tumbling, with solar panels intermittently illuminated; "
        "battery is presumed depleted; thermal control has been lost; if "
        "the propulsion-line hydrazine has frozen (~2 °C), the planned "
        "recovery requires actively re-warming it before any attitude "
        "manoeuvre."
    ),
    constraints=(
        "Hard constraints:",
        "  - SOHO at L1, ~1.5 million km from Earth",
        "  - Last contact 1998-06-25; weeks of search by DSN with no detection",
        "  - Spacecraft tumbling; solar panels in/out of illumination",
        "  - Hydrazine propulsion may have frozen (line temp below ~2 °C)",
        "  - Battery presumed depleted; only intermittent solar power available",
        "  - DSN 70 m antenna (Goldstone) is the only practical Earth uplink",
        "  - SOHO antennas designed for sun-pointing; off-axis link budgets",
        "    are tight",
        "  - Replacement is years out (no funded backup); SOHO is the primary",
        "    source of solar wind data for space-weather forecasting",
        "Available capability:",
        "  - Arecibo 305 m radio telescope can radar-ping SOHO and detect",
        "    return; can localise + measure spin",
        "  - DSN 70 m can provide high-power continuous-wave illumination",
        "    even off-pointing if SOHO's receiver is functional",
        "  - SOHO's Sun Acquisition Mode (SAM) firmware should automatically",
        "    capture sun-pointing if the gyros + reaction wheels are alive",
        "Personnel:",
        "  - Joint ESA/NASA recovery team; Bernhard von Weyhe (ESA flight",
        "    director); Carolyn Duncan (Goldstone)",
    ),
    ground_truth_decision=(
        "(1) Use Arecibo 305 m radar to detect SOHO and measure spin axis "
        "+ rate. (2) Use DSN 70 m to send a continuous-wave 'wake-up' "
        "carrier on SOHO's expected receive frequency, betting that the "
        "spacecraft's fault-protection-mode firmware would lock onto a "
        "carrier and re-establish telemetry. (3) Execute a thermal warm-"
        "up sequence for the hydrazine propulsion lines using residual "
        "battery + solar input over weeks before attempting any thruster "
        "firing. (4) Once propulsion was warm, command sun-acquisition "
        "manoeuvres."
    ),
    ground_truth_outcome=(
        "1998-08-03: Arecibo radar detected SOHO at expected L1 location, "
        "spinning at ~1 rpm. 1998-08-08: DSN carrier was detected back. "
        "1998-09-16: SOHO re-acquired sun-pointing after weeks of slow "
        "warm-up + small thruster pulses. 1998-10-22: science operations "
        "resumed. SOHO continued operating into 2026+ — far exceeding its "
        "2-year design life. The recovery is taught as the canonical "
        "deep-space-spacecraft rescue case study."
    ),
    citation=(
        "ESA SOHO Mission Recovery Final Report 1998; NASA SOHO Recovery "
        "Investigation Board Report 1998-09; ESA SOHO operations log; "
        "AAS 1999 paper 'SOHO: The Recovery'."
    ),
    rubric=ScoringRubric(criteria=(
        RubricCriterion(
            name="proposes_arecibo_radar_detection",
            description="Use Arecibo (or equivalent radar telescope) to localise SOHO + measure spin",
            keywords=("arecibo", "radar telescope", "radar ping",
                      "radar detection", "radar return", "spin rate",
                      "spin axis"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="proposes_dsn_carrier_wakeup",
            description="DSN 70m carrier illumination to re-establish telemetry",
            keywords=("dsn carrier", "wake up", "wake-up", "carrier sweep",
                      "uplink carrier", "70m antenna", "continuous wave",
                      "high-power illumination"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="hydrazine_freeze_concern",
            description="Recognises hydrazine line freeze + need for warm-up before manoeuvre",
            keywords=("hydrazine", "frozen", "freeze", "thaw",
                      "warm up", "warm-up", "line temperature",
                      "propellant freeze"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="acknowledges_battery_depleted",
            description="Notes battery state-of-charge is depleted / only solar-intermittent available",
            keywords=("battery depleted", "no battery", "battery dead",
                      "solar only", "intermittent power",
                      "low state of charge", "soc low"),
            weight=0.75,
        ),
        RubricCriterion(
            name="slow_warmup_before_thruster",
            description="Specifies weeks-long slow warm-up + small thruster pulses before full manoeuvre",
            keywords=("slow warm", "weeks", "small thruster",
                      "small pulse", "slow recovery", "incremental",
                      "over weeks"),
            weight=1.0,
        ),
        RubricCriterion(
            name="bet_on_fault_mode_recovery",
            description="Bets on SOHO's fault-protection / sun-acquisition firmware to recover",
            keywords=("fault protection", "fault-protection",
                      "sun acquisition", "sun-acquisition",
                      "safe mode", "automatic recovery"),
            weight=0.75,
        ),
        RubricCriterion(
            name="acknowledges_unique_irreplaceable",
            description="Recognises SOHO is the unique primary source for solar-wind / space-weather data",
            keywords=("irreplaceable", "unique", "primary source",
                      "space weather", "no replacement", "years out",
                      "no backup"),
            weight=0.5,
        ),
        RubricCriterion(
            name="reject_giveup_after_7_weeks",
            description="Argues against declaring SOHO lost despite 7-week silence",
            keywords=("not give up", "do not abandon", "do not give up",
                      "continue search", "keep trying", "not lost",
                      "not declare loss"),
            weight=1.0,
        ),
    )),
)
# ── Galileo HGA antenna failure (1991-04-11 to mission-end) ─────────


# Source: NASA JPL Galileo Mission Final Report 2003; O'Neil 1996
# 'Galileo: The Tour Guide'; JPL Galileo HGA Anomaly Investigation
# Report 1991-1992; Daly 2002 'The Galileo Antenna Project'.
GALILEO_HGA_FAILURE = EvalScenario(
    id="galileo_hga_antenna_failure",
    title="Galileo High-Gain Antenna deployment failure — mission redesign decision",
    date_iso="1991-04-11",
    situation=(
        "Galileo is en route to Jupiter (encounter 1995-12). The spacecraft "
        "carries a 4.8 m diameter High-Gain Antenna (HGA) that has been "
        "stowed since launch (1989-10) for vibrational protection. At "
        "T+533 days post-launch, ground commanded the HGA umbrella deployment "
        "via the dual-redundant DDA actuator motors. Telemetry shows the "
        "rib-actuator motor current ramp anomaly — three of the antenna's "
        "18 ribs (Ribs 1, 5, 11) failed to fully deploy. The umbrella is "
        "stuck partially open, asymmetric, and unable to focus RF.\n\n"
        "Without the HGA, science return drops from a planned ~134 kbps "
        "(via S-band HGA) to ~10 bps via the S-band Low-Gain Antenna (LGA) "
        "alone — a factor of ~13,000 less data. The original mission plan "
        "called for ~50,000 images of Jupiter, Galilean moons, atmospheric "
        "spectroscopy, magnetospheric mapping. With LGA only, the mission "
        "would return roughly the equivalent of 50 single images over the "
        "~2-year orbital tour.\n\n"
        "Likely root cause (post-1991 ground analysis + scale-model tests): "
        "the antenna ribs use lubricated pin joints; cold-soak in cruise "
        "(>3 yr) plus vibration-induced stiction at the launch / Earth-flyby "
        "shaking caused 3 ribs to bind. There is no on-board mechanism to "
        "free a stuck rib from Earth control; lasers, mechanical agitation, "
        "and higher motor torque are not in the tool kit."
    ),
    constraints=(
        "Hard constraints:",
        "  - Galileo at 1.7 AU; light-time ~30 min round-trip",
        "  - HGA stuck partially open; no command can free the 3 ribs",
        "  - LGA bandwidth: ~10 bps (vs HGA's planned ~134 kbps)",
        "  - Cruise to Jupiter: ~5 years remaining at decision time",
        "  - Mission cost-to-date: ~$1.6B; replacement spacecraft impossible",
        "  - DSN budget: 70m antennas can be assigned to Galileo at",
        "    encounters but cost ~$1M/week of dedicated coverage",
        "Available levers:",
        "  - 5 years of cruise time to develop ground-side recovery",
        "  - DSN arraying: combine multiple 70m + 34m dishes for higher",
        "    receive gain (at the cost of other missions)",
        "  - Onboard data compression: image-by-image lossless (factor ~2)",
        "    or lossy (factor ~10-50 depending on content)",
        "  - Onboard data prioritization: tape-recorder-stored images can",
        "    be selectively downlinked at LGA bitrates",
        "  - Tour redesign: trade encounter geometry for science return",
        "  - 'Hammer' approach: command the rib motors at higher torque",
        "    + pulsed thermal cycles in case stiction can be broken",
    ),
    ground_truth_decision=(
        "JPL adopted a 5-prong workaround: (1) DSN arraying — combine "
        "multiple antennas (Goldstone + Madrid + Canberra + Australian "
        "Parkes) to boost effective receive aperture by factor ~2.5; "
        "(2) onboard image-compression upgrades uplinked during cruise "
        "(ICT — Integer Cosine Transform; ratio ~10:1 for gas-giant "
        "atmospherics); (3) selective tape-recorder playback prioritising "
        "the highest-science-value images; (4) redesigned tour focusing "
        "on close moon flybys where less data per encounter still produces "
        "high science; (5) attempted thermal-cycling + motor-pulse "
        "campaigns to free the stuck ribs — these failed but were low-cost. "
        "All without any hardware contact."
    ),
    ground_truth_outcome=(
        "Galileo entered Jupiter orbit 1995-12-07. Despite returning ~70× "
        "less data than original plan, the mission returned ~30 % of the "
        "planned science by volume and arguably MORE by per-bit "
        "information density (the prioritisation forced focus on the "
        "highest-value targets). Galileo discovered the subsurface "
        "Europa ocean evidence, Io volcanism details, the Jovian "
        "magnetosphere structure. Mission was extended through 2003. "
        "The HGA recovery techniques are taught as the canonical "
        "ground-side-only mission-saving case study."
    ),
    citation=(
        "NASA JPL Galileo Mission Final Report 2003; O'Neil 1996 "
        "'Galileo: The Tour Guide'; JPL Galileo HGA Anomaly Investigation "
        "Report 1991-1992; Daly 2002 'The Galileo Antenna Project'."
    ),
    rubric=ScoringRubric(criteria=(
        RubricCriterion(
            name="dsn_arraying_for_aperture",
            description="Combine multiple DSN antennas (arraying) to boost receive gain",
            keywords=("arraying", "array", "multiple antenna",
                      "combine antenna", "combined receive",
                      "additional dish", "parkes", "70m", "70 m"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="onboard_data_compression",
            description="Upload onboard image / data compression algorithms",
            keywords=("compression", "ict", "integer cosine",
                      "lossy compression", "data compression",
                      "compress images", "compression ratio"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="onboard_data_prioritization",
            description="Selective tape-recorder playback / data prioritisation",
            keywords=("prioritization", "prioritisation", "selective",
                      "tape recorder", "playback", "highest value",
                      "highest-value", "downlink priority"),
            weight=1.0,
        ),
        RubricCriterion(
            name="rejects_giving_up_mission",
            description="Argues against abandoning the mission despite massive bandwidth loss",
            keywords=("not give up", "not abandon", "do not abandon",
                      "salvage", "still recover", "still do science",
                      "continue mission"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="tour_redesign_for_close_flybys",
            description="Redesign tour to favour close moon flybys (high info / data point)",
            keywords=("tour redesign", "close flyby", "close moon",
                      "encounter geometry", "moon flybys", "europa",
                      "io flyby"),
            weight=0.75,
        ),
        RubricCriterion(
            name="attempts_to_free_ribs",
            description="Notes low-cost attempts to free the stuck ribs (thermal cycling, motor pulses)",
            keywords=("thermal cycle", "motor pulse", "free the rib",
                      "unjam", "agitation", "warm + cool", "hammer"),
            weight=0.5,
        ),
        RubricCriterion(
            name="bandwidth_quantification",
            description="Quantifies the 10 bps vs 134 kbps gap",
            keywords=("10 bps", "134 kbps", "factor of", "bandwidth",
                      "13000", "1000x", "10000x", "bps", "data rate"),
            weight=0.5,
        ),
        RubricCriterion(
            name="cruise_time_as_resource",
            description="Identifies the 5-year cruise as time to develop the workaround",
            keywords=("cruise time", "5 year", "five year",
                      "development time", "before encounter",
                      "lead time", "remaining cruise"),
            weight=0.75,
        ),
    )),
)


# ── Mars Climate Orbiter unit conversion (1999-09-23) ──────────────


# Source: NASA Mars Climate Orbiter Mishap Investigation Board Phase I
# Report 1999-11-10; JPL Mars Climate Orbiter Project Final Report 1999;
# Pollack et al. 2000 'Lessons from the Loss of MCO'.
MARS_CLIMATE_ORBITER = EvalScenario(
    id="mars_climate_orbiter_unit_conversion",
    title="Mars Climate Orbiter — pre-loss unit-conversion decision opportunity",
    date_iso="1999-09-22",
    situation=(
        "Mars Climate Orbiter (MCO) is on final approach to Mars. The Mars "
        "Orbital Insertion (MOI) burn is scheduled for 1999-09-23 09:01 UTC "
        "— ~12 hours from now. The spacecraft will fire its main engine to "
        "decelerate by ~640 m/s, dropping into a ~150 km × ~21,000 km "
        "elliptical capture orbit, then aerobrake over weeks down to its "
        "operational 421 km × 437 km mapping orbit.\n\n"
        "Trajectory navigation has been showing persistent inconsistencies "
        "for ~6 weeks. Multiple Trajectory Correction Manoeuvres (TCM-3 + "
        "TCM-4 + TCM-5) have produced post-burn residuals 2-3 sigma higher "
        "than expected. The Navigation team reconstructed the accumulated "
        "thrust impulse from 13 small angular-momentum-desaturation (AMD) "
        "burns and found that the as-flown trajectory implies impulses "
        "consistently ~4.45× different from what the AMD model predicts.\n\n"
        "The number 4.45 is suspicious — it is exactly the ratio between "
        "pound-force and Newton (1 lbf = 4.448 N). The AMD burn-impulse data "
        "is generated by Lockheed Martin AOSP (Attitude Operations Software "
        "Program) and consumed by JPL SM_FORCES (Small Forces) navigation. "
        "MIB Phase 1 finds: AOSP outputs in lbf-s; SM_FORCES expects N-s; "
        "no documented unit-conversion at the interface.\n\n"
        "Today's MOI burn parameters are computed assuming SM_FORCES has "
        "been integrating correct units for the last 286 days of cruise. "
        "If the navigation reconstruction is wrong by factor ~4.45 in the "
        "AMD impulse history, the as-flown trajectory differs from the "
        "navigation estimate by an unknown amount."
    ),
    constraints=(
        "Hard constraints:",
        "  - MOI burn ~12 hours away",
        "  - Persistent 2-3 sigma residuals on TCM-3/4/5 over 6 weeks",
        "  - 4.45× ratio between observation and AMD-model prediction",
        "    matches lbf:N exactly",
        "  - No automated unit-conversion at the AOSP → SM_FORCES interface",
        "  - Cruise time remaining: not enough for a full re-derivation",
        "    of the trajectory from raw range-rate data",
        "  - Periapsis target: 150 km altitude, with 25 km tolerance",
        "  - If actual periapsis < ~85 km altitude, atmospheric drag at",
        "    Mars density will destroy the spacecraft",
        "Available actions:",
        "  - DELAY MOI by 24-48 hours; recompute trajectory with",
        "    explicit unit-aware AMD model rebuild",
        "  - DELAY further; recompute from raw radio metric data only",
        "    (independent of AMD model assumptions)",
        "  - PROCEED as planned with current navigation",
        "  - Contingency-burn: a 5 m/s pre-MOI 'safety bias' to raise",
        "    the targeted periapsis by ~30 km if reconstructed trajectory",
        "    is biased low",
    ),
    ground_truth_decision=(
        "[Counterfactual — note this is the decision the LLM is being graded "
        "on, not what NASA actually decided.] The historically-correct "
        "decision would have been to DELAY MOI by 24-48 hours, re-derive "
        "the trajectory from raw radio range-rate data independent of the "
        "AMD impulse model, and verify periapsis altitude with a "
        "non-AMD-derived solution. If the data window were too short, a "
        "5-10 m/s pre-MOI safety burn would raise the targeted periapsis "
        "well above the atmospheric-loss threshold."
    ),
    ground_truth_outcome=(
        "[As actually flown.] MCO proceeded with planned MOI 1999-09-23. "
        "The unit-conversion error meant the actual trajectory put periapsis "
        "at ~57 km altitude — below the atmospheric-loss threshold. MCO was "
        "destroyed by atmospheric drag during MOI. The MIB Phase 1 report "
        "identified the lbf:N units mismatch as the root cause. The lesson "
        "drove industry-wide adoption of mandatory unit annotation in flight "
        "software interfaces and integration testing across vendor boundaries."
    ),
    citation=(
        "NASA Mars Climate Orbiter Mishap Investigation Board Phase I "
        "Report 1999-11-10; JPL MCO Project Final Report 1999; "
        "Pollack et al. 2000 'Lessons from the Loss of MCO'."
    ),
    rubric=ScoringRubric(criteria=(
        RubricCriterion(
            name="recognises_unit_conversion_error",
            description="Diagnoses the lbf-vs-N unit mismatch as the root cause",
            keywords=("lbf", "newton", "unit conversion", "unit mismatch",
                      "pound force", "imperial", "metric",
                      "unit error", "4.45"),
            weight=2.0,
            must_have=True,
        ),
        RubricCriterion(
            name="recommends_delay_moi",
            description="Recommends delaying MOI for re-verification",
            keywords=("delay moi", "postpone moi", "delay the burn",
                      "delay orbit insertion", "reschedule moi",
                      "scrub moi", "delay 24"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="independent_radio_metric_recompute",
            description="Re-derive trajectory from raw radio range-rate data independent of AMD model",
            keywords=("radio metric", "range rate", "range-rate",
                      "raw doppler", "raw tracking", "independent",
                      "from scratch", "unbiased"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="recognises_periapsis_atmospheric_threshold",
            description="Notes the ~85 km atmospheric-loss threshold for Mars periapsis",
            keywords=("periapsis", "85 km", "atmospheric drag",
                      "atmospheric threshold", "loss threshold",
                      "atmospheric capture", "destroy spacecraft",
                      "below the threshold"),
            weight=1.0,
        ),
        RubricCriterion(
            name="proposes_safety_bias_burn",
            description="Optional: a small pre-MOI burn to bias periapsis higher as insurance",
            keywords=("safety bias", "bias burn", "raise periapsis",
                      "raise altitude", "buffer burn", "5 m/s",
                      "pre-moi burn", "insurance"),
            weight=0.75,
        ),
        RubricCriterion(
            name="rejects_proceed_as_planned",
            description="Argues against proceeding with current navigation given suspect residuals",
            keywords=("not proceed", "do not proceed", "do not fire",
                      "do not commit", "should not burn",
                      "halt the burn", "stop the burn"),
            weight=1.5,
        ),
        RubricCriterion(
            name="cross_vendor_interface_audit",
            description="Recognises the AOSP / SM_FORCES vendor-boundary interface as the source",
            keywords=("vendor", "interface", "lockheed", "aosp",
                      "sm_forces", "small forces",
                      "interface contract", "vendor boundary"),
            weight=0.75,
        ),
        RubricCriterion(
            name="2_3_sigma_residual_pattern",
            description="Recognises the 6-week pattern of consistent 2-3 sigma residuals",
            keywords=("2 sigma", "3 sigma", "residual",
                      "consistent residual", "post-burn residual",
                      "tcm residual", "pattern"),
            weight=0.75,
        ),
    )),
)


# ── Cassini Grand Finale planetary protection (2017-09-15) ──────────


# Source: NASA JPL Cassini Grand Finale End-of-Mission Report 2017;
# Spilker et al. 2018 'Cassini's Grand Finale'; COSPAR Planetary
# Protection Categorisation Document 2014; NASA-Goddard Spilker
# 2017 mission close-out brief.
CASSINI_GRAND_FINALE = EvalScenario(
    id="cassini_grand_finale_eom",
    title="Cassini end-of-mission Saturn-atmospheric-entry decision",
    date_iso="2017-04-22",
    situation=(
        "Cassini has been in Saturn orbit since 2004-07. After 13 years of "
        "operations, propellant is approaching the level where reliable "
        "attitude control + science manoeuvres can no longer be guaranteed. "
        "Estimated remaining propellant: ~10 kg of monomethyl hydrazine + "
        "nitrogen tetroxide oxidiser (out of 3,132 kg loaded at launch). The "
        "spacecraft has executed ~360 manoeuvres totalling ~3,200 m/s of Δv.\n\n"
        "Three planetary-protection issues constrain end-of-mission options:\n\n"
        "1. ENCELADUS hosts liquid-water plumes Cassini directly sampled. "
        "The plumes contain organic compounds and salt; the ice shell hides "
        "a global subsurface ocean. COSPAR Category III/IV protections "
        "require any spacecraft entering the Saturnian system not be left "
        "in an orbit that could collide with Enceladus (or Titan, similarly "
        "categorised) at the ~1 % level over 100 years.\n\n"
        "2. TITAN hosts hydrocarbon lakes + a thick atmosphere; potential "
        "abode for prebiotic chemistry. Category III applies.\n\n"
        "3. Cassini was assembled in non-bioburden-controlled conditions "
        "(unlike a Mars lander) — an uncontrolled impact onto Enceladus "
        "or Titan would be a planetary-protection violation.\n\n"
        "Possible end-of-mission options under PSG (Project Science Group) "
        "consideration:\n\n"
        "(a) Park orbit — extend Cassini's orbit to a stable resonance "
        "outside Enceladus / Titan crossing geometry. Stability over 100 yr "
        "uncertain due to perturbations from the Galilean satellites.\n"
        "(b) Saturn-atmosphere entry — direct the spacecraft to plunge into "
        "Saturn's atmosphere on a controlled trajectory; spacecraft burns "
        "up entirely. Eliminates planetary-protection risk completely.\n"
        "(c) Eject from Saturn system — use Titan flyby to send Cassini to "
        "a heliocentric orbit. Propellant marginal; trajectory not yet "
        "validated for the available Δv budget.\n\n"
        "Science return considerations: option (b) allows ~22 'Grand Finale' "
        "orbits passing between Saturn and its rings — a region no spacecraft "
        "has visited; first direct in-situ measurement of Saturn's deep "
        "atmosphere via the entry probe phase."
    ),
    constraints=(
        "Hard constraints:",
        "  - Propellant remaining: ~10 kg (out of 3,132 kg launched)",
        "  - Cassini NOT bioburden-controlled at assembly",
        "  - COSPAR Category III/IV: <1% Enceladus/Titan collision over",
        "    100 yr",
        "  - Limited Δv: ~80 m/s estimated remaining authority",
        "  - 1.5-hour light-time round-trip for commanding",
        "  - End of funded operations: 2017-09-30",
        "  - Cassini's RTG has Pu-238 fuel (radioisotope thermoelectric",
        "    generator) — entering Saturn's atmosphere is acceptable",
        "    (gas giant absorbs); striking icy moons is not",
        "Available science targets accessible via grand-finale path:",
        "  - 22 orbits between Saturn and rings (closest ring approaches)",
        "  - First in-situ Saturn atmosphere measurement during entry",
        "  - First Saturn gravity field measurement at 1-Saturn-radius",
        "    altitude (constrains interior structure)",
        "  - Direct sampling of ring particles at unprecedented closeness",
    ),
    ground_truth_decision=(
        "Cassini end-of-mission was committed to a controlled Saturn-"
        "atmospheric-entry trajectory ('Grand Finale'). The mission spent "
        "April–September 2017 executing 22 orbits passing through the gap "
        "between Saturn and its innermost ring, taking first-ever data of "
        "the planet's deep atmosphere, gravity field, and ring particle "
        "composition. On 2017-09-15 Cassini entered Saturn's atmosphere on "
        "a north-pole approach trajectory; loss-of-signal occurred at "
        "11:55:39 UTC at altitude ~1900 km above the 1-bar level."
    ),
    ground_truth_outcome=(
        "Cassini disintegrated in Saturn's atmosphere, eliminating the "
        "planetary-protection risk. The 22 Grand Finale orbits returned "
        "the highest-priority unique science of the entire 13-year mission "
        "— including direct atmosphere composition (CH₄, NH₃, H₂O, He, H₂), "
        "first interior-structure constraints (J6, J8, J10 zonal moments), "
        "and ring-mass measurement (1.54×10^19 kg, ~½ Mimas; rings are "
        "young, ~10-100 Myr). The Grand Finale is taught as the canonical "
        "end-of-mission planetary-protection-driven plan."
    ),
    citation=(
        "NASA JPL Cassini Grand Finale End-of-Mission Report 2017; "
        "Spilker et al. 2018 'Cassini's Grand Finale'; COSPAR "
        "Planetary Protection Categorisation Document 2014."
    ),
    rubric=ScoringRubric(criteria=(
        RubricCriterion(
            name="recognises_planetary_protection_constraint",
            description="Frames decision around planetary-protection (Enceladus/Titan)",
            keywords=("planetary protection", "cospar", "category iii",
                      "category iv", "enceladus", "ice moon",
                      "no contamination", "bioburden"),
            weight=2.0,
            must_have=True,
        ),
        RubricCriterion(
            name="recommends_saturn_atmospheric_entry",
            description="Recommends Saturn atmospheric entry as end-of-mission",
            keywords=("saturn atmosphere", "atmospheric entry",
                      "burn up", "burn-up", "destroy by entry",
                      "plunge into saturn", "saturn dive",
                      "deorbit into saturn"),
            weight=1.5,
            must_have=True,
        ),
        RubricCriterion(
            name="rejects_park_orbit_due_to_perturbations",
            description="Rejects parking orbit due to long-term perturbation uncertainty",
            keywords=("park orbit", "perturbation", "long term stability",
                      "long-term", "100 year", "satellite perturb",
                      "unstable", "cannot guarantee"),
            weight=0.75,
        ),
        RubricCriterion(
            name="recognises_grand_finale_science_value",
            description="Notes the 22 grand-finale orbits + unique-science value",
            keywords=("22 orbits", "ring gap", "between rings",
                      "ring gap orbit", "in-situ atmosphere",
                      "gravity field", "first measurement",
                      "unprecedented"),
            weight=1.0,
        ),
        RubricCriterion(
            name="rejects_solar_ejection",
            description="Rejects solar-ejection due to insufficient Δv",
            keywords=("solar ejection", "heliocentric", "eject from",
                      "insufficient delta-v", "insufficient propellant",
                      "marginal propellant"),
            weight=0.75,
        ),
        RubricCriterion(
            name="quantifies_propellant_constraint",
            description="Quantifies the ~10 kg remaining propellant / ~80 m/s authority",
            keywords=("10 kg", "remaining propellant", "low propellant",
                      "delta v", "Δv", "80 m/s", "limited",
                      "running out"),
            weight=0.5,
        ),
        RubricCriterion(
            name="rtg_in_saturn_acceptable",
            description="Notes that Saturn (gas giant) absorbing the RTG is acceptable",
            keywords=("rtg", "pu-238", "plutonium", "gas giant",
                      "acceptable", "absorbs", "no radioactive",
                      "no contamination of saturn", "gaseous"),
            weight=0.75,
        ),
        RubricCriterion(
            name="acknowledges_assembly_not_bioburden",
            description="Acknowledges Cassini was not assembled bioburden-controlled",
            keywords=("not bioburden", "not sterilised", "non-sterile",
                      "non-bioburden", "ordinary assembly",
                      "no clean room", "contamination risk"),
            weight=0.5,
        ),
    )),
)
# ── Loader ──────────────────────────────────────────────────────


_DEFAULT_SCENARIOS = (
    APOLLO_13_CO2,
    HUBBLE_SM4,
    ISS_RUSSIAN_LEAK,
    APOLLO_11_PROGRAM_ALARMS,
    APOLLO_12_LIGHTNING,
    MIR_SPEKTR_DEPRESS,
    STS_114_GAP_FILLER,
    SOHO_1998_RECOVERY,
    GALILEO_HGA_FAILURE,
    MARS_CLIMATE_ORBITER,
    CASSINI_GRAND_FINALE,
)


def load_default_scenarios() -> Tuple[EvalScenario, ...]:
    """The default benchmark set."""
    return _DEFAULT_SCENARIOS
