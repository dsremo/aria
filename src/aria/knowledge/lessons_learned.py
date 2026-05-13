from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import structlog

logger = structlog.get_logger()


NTRS_SEARCH_URL = "https://ntrs.nasa.gov/api/citations/search"
NTRS_DEFAULT_TIMEOUT_S = 30.0
NTRS_DEFAULT_PAGE_SIZE = 25
NTRS_USER_AGENT = "aria-knowledge/1.0 (research; contact: ARIA project)"


@dataclass(frozen=True)
class LessonRecord:
    record_id: str
    title: str
    summary: str
    keywords: tuple[str, ...] = ()
    source: str = "curated"
    citation: str = ""
    parameters: tuple[str, ...] = ()
    fetched_at_iso: str = ""

    def as_doctrine_entry(self) -> dict[str, Any]:
        return {
            "rule_id": f"LL-{self.record_id}",
            "kind": "incident_report",
            "title": self.title,
            "body": self.summary,
            "keywords": list(self.keywords),
            "citation": self.citation or self.source,
            "parameters": list(self.parameters),
        }


@dataclass
class LessonsLearnedStore:
    records: list[LessonRecord] = field(default_factory=list)

    def add(self, record: LessonRecord) -> None:
        self.records.append(record)

    def extend(self, records: Iterable[LessonRecord]) -> None:
        self.records.extend(records)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "record_id": record.record_id,
                "title": record.title,
                "summary": record.summary,
                "keywords": list(record.keywords),
                "source": record.source,
                "citation": record.citation,
                "parameters": list(record.parameters),
                "fetched_at": record.fetched_at_iso,
            }
            for record in self.records
        ]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load(self, path: Path) -> int:
        if not path.exists():
            return 0
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0
        if not isinstance(payload, list):
            return 0
        added = 0
        for item in payload:
            if not isinstance(item, dict):
                continue
            self.records.append(LessonRecord(
                record_id=str(item.get("record_id", "")),
                title=str(item.get("title", "")),
                summary=str(item.get("summary", "")),
                keywords=tuple(str(keyword) for keyword in item.get("keywords") or ()),
                source=str(item.get("source", "curated")),
                citation=str(item.get("citation", "")),
                parameters=tuple(str(parameter) for parameter in item.get("parameters") or ()),
                fetched_at_iso=str(item.get("fetched_at", "")),
            ))
            added += 1
        return added


_CURATED_LESSONS_CORE: tuple[LessonRecord, ...] = (
    LessonRecord(
        record_id="apollo-13-cryo-stir",
        title="Apollo 13 cryo-tank rupture during stir command",
        summary=(
            "Routine cryo-stir command at GET 55:53:18 ignited Teflon "
            "insulation in O2 tank 2 due to prior heater short during "
            "ground processing. Tank pressure ramped 887→1008 psia in "
            "95 s, then ruptured. Tank 1 secondary leak began GET "
            "55:57:00. Crew transferred to LM Aquarius. Lesson: heater "
            "thermostat protection circuit was not redundant; manual "
            "stir during cruise risky if tank state uncertain."
        ),
        keywords=("apollo", "cryo", "tank", "rupture", "stir", "lifeboat"),
        source="cortright_commission",
        citation="Cortright Commission Report NASA SP-1969 (1970); MSC-02680 §5",
        parameters=("O2_TANK_2_PRESSURE", "O2_TANK_2_TEMP", "FUEL_CELL_VOLTAGE"),
    ),
    LessonRecord(
        record_id="apollo-1-fire",
        title="Apollo 1 plugs-out test fire (1967-01-27)",
        summary=(
            "100% O2 cabin atmosphere at 16.7 psia ignited from chafed "
            "wire arc; crew lost in 17 seconds. Lessons: never operate "
            "100% O2 above ambient pressure during ground tests; cabin "
            "outward-opening hatches replaced with quick-egress design; "
            "flammability of cabin materials in pure-O2 retested across "
            "all crew compartments; pad emergency egress drills hardened."
        ),
        keywords=("apollo", "fire", "100% o2", "pure oxygen", "egress"),
        source="thompson_report",
        citation="Apollo 204 Review Board Report (Thompson Report, 1967)",
        parameters=("CABIN_O2_FRACTION", "CABIN_PRESSURE_KPA"),
    ),
    LessonRecord(
        record_id="sts-107-columbia",
        title="STS-107 Columbia foam-strike re-entry breakup (2003-02-01)",
        summary=(
            "External tank foam struck left wing leading edge at L+82 s, "
            "creating breach in RCC panel. On re-entry, hot plasma "
            "entered breach, melted internal structure, vehicle broke up "
            "at Mach 18. Lessons: foam shedding not validated as 'in "
            "family'; on-orbit imagery requests denied during mission; "
            "RCC inspection capability added post-flight; foam loss "
            "treated as immediate flight safety issue thereafter."
        ),
        keywords=("columbia", "foam", "rcc", "re-entry", "thermal protection"),
        source="caib_report",
        citation="Columbia Accident Investigation Board Report Vol I (2003)",
        parameters=("LEADING_EDGE_TEMP_K", "TPS_INTEGRITY"),
    ),
    LessonRecord(
        record_id="mir-spektr-collision",
        title="Mir Progress M-34 collision with Spektr (1997-06-25)",
        summary=(
            "Manual TORU-controlled docking of Progress M-34 cargo vessel "
            "failed; Progress struck Spektr module solar array, "
            "puncturing module. Crew sealed Spektr hatch within 30 min "
            "preventing cabin loss. Lesson: TORU manual docking from Mir "
            "without range-rate ranging is high-risk; subsequent dockings "
            "always used Kurs system with manual TORU as backup only."
        ),
        keywords=("mir", "spektr", "depressurisation", "docking", "toru"),
        source="nasa_mir_lessons",
        citation="NASA-Mir Phase 1 Program Joint Report (1998)",
        parameters=("CABIN_PRESSURE_KPA", "MODULE_HATCH_STATE"),
    ),
    LessonRecord(
        record_id="iss-quest-pca-2018",
        title="ISS Quest airlock leak (2018) — pre-EVA depress",
        summary=(
            "Slow leak in PCA (Pressure Control Assembly) line during "
            "Quest airlock pre-EVA depress detected by trending of "
            "ppN2 vs commanded profile. Crew aborted depress, "
            "isolated line, EVA delayed 24 h. Lesson: small leaks "
            "below master-alarm threshold detectable only by trend "
            "monitoring of multiple correlated parameters; raw-rate "
            "alarms insufficient for slow loss-of-pressure events."
        ),
        keywords=("iss", "quest", "leak", "eva", "depress"),
        source="iss_anomaly_log",
        citation="ISS On-Orbit Anomaly Log JSC-66050 (NASA, 2018)",
        parameters=("CABIN_PRESSURE_KPA", "CABIN_PPN2_KPA", "LEAK_RATE_KPA_PER_MIN"),
    ),
    LessonRecord(
        record_id="cassini-grand-finale-units",
        title="Cassini Grand Finale unit-convention near-miss",
        summary=(
            "During Grand Finale planning, propulsion model used "
            "thrust in pound-force while integrator expected newtons "
            "in one branch; caught by independent dual-team review "
            "before upload. Lesson: unit conventions must be machine-"
            "checked at every interface, not human-eyeballed; Mars "
            "Climate Orbiter (1999) loss had identical root cause."
        ),
        keywords=("cassini", "units", "lbf", "newton", "propulsion"),
        source="jpl_mission_report",
        citation="Cassini Grand Finale End-of-Mission Report (JPL, 2017)",
        parameters=("THRUST_N", "DELTA_V_M_S"),
    ),
    LessonRecord(
        record_id="soho-1998-attitude-loss",
        title="SOHO 1998-06-25 attitude loss + recovery",
        summary=(
            "Spacecraft entered emergency-sun-reacquisition mode after "
            "ground-uplink commanding sequence introduced by post-"
            "anomaly recovery procedure had a swapped-sign in Y-axis "
            "gyro calibration; cascade led to loss of lock on Sun for "
            "4 months. Recovered via Arecibo radar pings and ground "
            "thermal model. Lesson: never push 'recovery' commands "
            "without independent verification of sign / unit / "
            "axis-frame conventions; have a thermal model good enough "
            "to predict recovery from any safe-mode."
        ),
        keywords=("soho", "attitude", "gyro", "safe mode", "recovery"),
        source="esa_soho_report",
        citation="SOHO Mission Interruption Investigation Board (NASA/ESA 1998)",
        parameters=("ATTITUDE_QUATERNION", "GYRO_RATE_BODY"),
    ),
    LessonRecord(
        record_id="mco-1999-units",
        title="Mars Climate Orbiter unit-conversion loss (1999)",
        summary=(
            "Spacecraft entered Mars atmosphere ~57 km lower than "
            "intended due to pound-force-seconds vs newton-seconds "
            "discrepancy between Lockheed Martin (lbf-s) and JPL "
            "navigation (N-s) software. Spacecraft destroyed. Lesson: "
            "ICDs must specify SI units at every interface, machine-"
            "checked; build verification must include cross-team "
            "independent navigation simulation."
        ),
        keywords=("mco", "mars", "units", "lbf", "navigation"),
        source="mco_mishap_report",
        citation="Mars Climate Orbiter Mishap Investigation Board Report (NASA, 1999)",
        parameters=("DELTA_V_M_S", "PERIAPSIS_KM"),
    ),
    LessonRecord(
        record_id="iss-cdra-bed-failures",
        title="ISS CDRA bed switch repeated failures",
        summary=(
            "CDRA (Carbon Dioxide Removal Assembly) zeolite bed failed "
            "to perform automatic switch on multiple occasions due to "
            "valve sticking. Crew or ground rebooted CDRA; backup "
            "Vozdukh activated when both CDRAs unavailable. Lesson: "
            "single-string CRAs are insufficient for long-duration "
            "missions; redundancy must be maintained even if dispatch "
            "rate looks adequate."
        ),
        keywords=("iss", "cdra", "co2", "scrubber", "vozdukh"),
        source="iss_eclss_lessons",
        citation="ISS Air Revitalization Subsystem Lessons Learned (NASA, 2014)",
        parameters=("CABIN_PPCO2_KPA", "CDRA_BED_TEMP_C"),
    ),
    LessonRecord(
        record_id="apollo-12-sce-aux",
        title="Apollo 12 launch lightning strike — 'SCE to AUX'",
        summary=(
            "Saturn V struck by lightning twice during ascent; CSM "
            "fuel cells offline, telemetry garbled. EECOM John Aaron "
            "recognised pattern from 1968 SCE test, called 'SCE to "
            "AUX'. Crew restored telemetry, mission continued. "
            "Lesson: pattern-matching across past anomalies is a "
            "high-leverage controller skill; trained-pattern catalog "
            "must be available to controllers (and AI advisors) in "
            "real-time."
        ),
        keywords=("apollo", "lightning", "sce", "aux", "fuel cell"),
        source="apollo_12_mission_report",
        citation="Apollo 12 Mission Report MSC-01855 (1970)",
        parameters=("FUEL_CELL_VOLTAGE", "TELEMETRY_LOCK_STATE"),
    ),
)


_CURATED_LESSONS_EXTENDED: tuple[LessonRecord, ...] = (
    LessonRecord(
        record_id="challenger-sts-51l",
        title="Challenger STS-51L SRB O-ring failure (1986-01-28)",
        summary=(
            "Cold-weather launch (-1 °C ambient) hardened SRB field-joint "
            "O-rings. Hot exhaust burned through joint at T+58 s; ET "
            "structural failure at T+73 s; vehicle disintegrated. Lessons: "
            "low-temperature O-ring data was known to engineers but not "
            "communicated to launch decision; risk-acceptance pressure "
            "in 'Go for launch' culture; teleconference dissent "
            "suppressed. Resulted in NASA's 'Flight Readiness Review' "
            "process restructure."
        ),
        keywords=("challenger", "srb", "o-ring", "cold launch", "groupthink"),
        source="rogers_commission",
        citation="Rogers Commission Report on the Challenger Accident (1986)",
        parameters=("SRB_FIELD_JOINT_TEMP_K", "AMBIENT_TEMP_K"),
    ),
    LessonRecord(
        record_id="parmitano-eva-water",
        title="Parmitano EVA-23 helmet water (2013-07-16)",
        summary=(
            "ESA astronaut Luca Parmitano nearly drowned in EMU during "
            "EVA-23. Fan/pump separator backflowed water into helmet via "
            "vent loop. Crew commander aborted EVA. Root cause: blocked "
            "filter in fan-pump separator allowed condensate accumulation; "
            "sub-suspect was water rejection through sublimator. Lessons: "
            "EMU helmet water absorption pads added; pre-EVA loop checks "
            "extended; no-launch criterion if condensate-side pressure "
            "anomaly observed."
        ),
        keywords=("emu", "helmet", "water", "drowning", "parmitano"),
        source="iss_anomaly_log",
        citation="ISS On-Orbit Anomaly Investigation EVA-23 (NASA, 2013)",
        parameters=("EMU_HELMET_HUMIDITY_PCT", "EMU_FAN_PUMP_STATE"),
    ),
    LessonRecord(
        record_id="iss-ammonia-leak-2014",
        title="ISS US-segment ammonia leak (2014-12-10)",
        summary=(
            "Bus voltage on US-segment thermal control loop A dropped; "
            "false alarm of ammonia in cabin pulled crew to Russian "
            "segment. Real cause was a software / sensor anomaly not a "
            "real leak. Crew remained sheltered for several hours until "
            "ground confirmed. Lessons: Russian segment serves as effective "
            "safe haven; cross-segment isolation procedure validated; "
            "improved sensor cross-checking added to FCC."
        ),
        keywords=("ammonia", "leak", "false alarm", "russian segment"),
        source="iss_anomaly_log",
        citation="ISS On-Orbit Anomaly Log JSC-66050-2014-12 (NASA)",
        parameters=("CABIN_NH3_PPM",),
    ),
    LessonRecord(
        record_id="dragon-crs-7-failure",
        title="SpaceX CRS-7 second-stage breakup (2015-06-28)",
        summary=(
            "Strut holding helium COPV inside LOX tank failed at ~T+139 s "
            "due to material defect; helium release over-pressurized LOX "
            "tank; vehicle break-up; Dragon cargo lost. Lessons: COPV "
            "strut sourcing tightened; redundant pressure-relief paths; "
            "manufacturing-batch traceability to component-level."
        ),
        keywords=("falcon 9", "crs-7", "copv", "helium", "strut"),
        source="spacex_root_cause",
        citation="SpaceX CRS-7 root-cause statement (Aug 2015)",
        parameters=("STAGE2_LOX_TANK_PRESSURE_PSIA",),
    ),
    LessonRecord(
        record_id="dragon-amos-6-pad",
        title="SpaceX AMOS-6 pad explosion (2016-09-01)",
        summary=(
            "During pre-flight static-fire propellant loading, helium "
            "COPV inside Falcon 9 second-stage LOX tank failed; LOX-to-"
            "helium failure mode (subcooled-LOX intrusion into COPV "
            "buckled lining). Pad lost; AMOS-6 destroyed pre-launch. "
            "Lessons: subcooled-LOX loading procedure adjusted; COPV "
            "design + manufacturing changed; static-fire risk re-evaluated."
        ),
        keywords=("amos-6", "falcon 9", "copv", "subcooled lox"),
        source="spacex_root_cause",
        citation="SpaceX AMOS-6 statement (Jan 2017)",
        parameters=("COPV_PRESSURE_PSIA", "LOX_TEMP_K"),
    ),
    LessonRecord(
        record_id="ariane-5-501",
        title="Ariane 5 flight 501 inertial reference overflow (1996-06-04)",
        summary=(
            "Inertial reference system reused from Ariane 4 software; "
            "horizontal velocity exceeded representable 16-bit integer "
            "37 s after lift-off; system raised exception interpreted as "
            "flight data; SRBs commanded extreme angle; vehicle self-"
            "destructed. Lessons: never reuse software without re-"
            "envelope analysis; protect every conversion with bounds-"
            "check; coupled-system FMEA must include software-component "
            "data flow."
        ),
        keywords=("ariane 5", "inertial", "overflow", "software"),
        source="esa_flight_501",
        citation="Ariane 5 Flight 501 Inquiry Board Report (ESA, 1996)",
        parameters=("HORIZONTAL_VELOCITY_M_S",),
    ),
    LessonRecord(
        record_id="hayabusa-1-recovery",
        title="Hayabusa 1 multi-anomaly recovery (2010 sample return)",
        summary=(
            "JAXA Hayabusa 1 suffered RCS thruster leaks, ion-engine "
            "failures, attitude loss (3 of 3 reaction wheels failed), "
            "communication blackouts. Recovery via creative engineering: "
            "ion-engine cross-strapping (combining components from two "
            "failed engines), low-thrust trajectory re-targeting, and "
            "spinning-spacecraft recovery. Sample returned 2010. Lessons: "
            "graceful degradation paths matter more than redundancy "
            "depth; on-board reconfigurability earns its weight."
        ),
        keywords=("hayabusa", "ion engine", "graceful degradation", "jaxa"),
        source="jaxa_hayabusa_report",
        citation="Hayabusa Mission Final Report (JAXA, 2011)",
        parameters=("ION_ENGINE_THRUST_MN", "REACTION_WHEEL_HEALTH"),
    ),
    LessonRecord(
        record_id="kepler-mission",
        title="Kepler reaction-wheel failure & K2 recovery (2013)",
        summary=(
            "Two of four reaction wheels failed on Kepler. Original "
            "mission required 3 wheels for fine-pointing of star fields. "
            "K2 mission designed using solar pressure as third axis "
            "stabilization, observing along ecliptic plane. Extended "
            "mission until 2018. Lessons: thrust-from-photons can "
            "replace mechanical wheels for short-axis stabilisation; "
            "graceful-degradation operating modes should be designed in."
        ),
        keywords=("kepler", "reaction wheel", "k2", "solar pressure"),
        source="nasa_kepler_report",
        citation="Kepler & K2 Final Mission Report (NASA Ames, 2018)",
        parameters=("REACTION_WHEEL_HEALTH", "POINTING_ERROR_ARCSEC"),
    ),
    LessonRecord(
        record_id="dscovr-restart",
        title="DSCOVR processor restart (2019)",
        summary=(
            "DSCOVR went into safe-hold for 8 months after a processor "
            "restart triggered by SEU (single event upset). Recovery "
            "required ground-uplink procedure to clear safe-hold. "
            "Lessons: long-duration L1 spacecraft need on-board safe-"
            "hold-self-clear after diagnostic confidence; avoid "
            "ground-only recovery paths for survival modes."
        ),
        keywords=("dscovr", "seu", "safe hold", "l1"),
        source="noaa_dscovr_report",
        citation="DSCOVR On-Orbit Anomaly Report (NOAA, 2020)",
        parameters=("SAFE_HOLD_FLAG", "SEU_COUNT"),
    ),
    LessonRecord(
        record_id="genesis-crash",
        title="Genesis sample-return parachute failure (2004-09-08)",
        summary=(
            "Genesis solar-wind sample-return capsule's drogue and main "
            "parachute pyrotechnic deployment failed; capsule impacted "
            "Utah desert at ~310 km/h. Root cause: G-switch sensors "
            "installed inverted by manufacturer; pre-launch verification "
            "missed because test fixture matched the inverted "
            "installation. Lessons: pre-launch testing must include "
            "right-way-up validation; vendor-installation drawings must "
            "be cross-checked at integration."
        ),
        keywords=("genesis", "parachute", "g-switch", "manufacturing defect"),
        source="genesis_mishap",
        citation="Genesis Mishap Investigation Board Report (NASA, 2006)",
        parameters=("ENTRY_VEHICLE_VELOCITY_M_S", "PARACHUTE_DEPLOY_FLAG"),
    ),
    LessonRecord(
        record_id="solar-orbiter-pre-launch-cooler",
        title="Solar Orbiter HRT instrument pre-launch contamination (2020)",
        summary=(
            "ESA Solar Orbiter High Resolution Telescope developed "
            "post-launch performance issue traced to pre-launch outgassing "
            "and contamination on optical surfaces. Mitigation: "
            "decontamination heater cycles in low-Sun-flux phases. "
            "Lessons: ground-handling cleanliness procedures critical "
            "for optical instruments; bake-out schedules must account "
            "for both pre-launch and on-orbit phases."
        ),
        keywords=("solar orbiter", "outgassing", "optical contamination"),
        source="esa_solo_report",
        citation="Solar Orbiter In-Flight Calibration Report (ESA, 2021)",
        parameters=("INSTRUMENT_TEMP_K", "DECONTAMINATION_CYCLE_FLAG"),
    ),
    LessonRecord(
        record_id="proba-2-emergency-recovery",
        title="ESA PROBA-2 magnetometer-only recovery (2009)",
        summary=(
            "PROBA-2 lost star-tracker lock during early ops; recovered "
            "attitude using magnetometer-only B-dot detumble + "
            "magnetorquer pointing. Lessons: small spacecraft must have "
            "rate-only and magnetometer-only attitude recovery; star-"
            "tracker should not be the only path to attitude knowledge."
        ),
        keywords=("proba-2", "magnetometer", "b-dot", "esa"),
        source="esa_proba_report",
        citation="PROBA-2 Mission Operations Report (ESA, 2010)",
        parameters=("MAGNETOMETER_VECTOR_T", "BODY_RATE_DEG_S"),
    ),
    LessonRecord(
        record_id="iridium-cosmos-2009",
        title="Iridium 33 / Cosmos 2251 collision (2009-02-10)",
        summary=(
            "Active Iridium 33 and inactive Cosmos 2251 collided at "
            "789 km altitude generating ~2,000 trackable debris. First "
            "hypervelocity collision between two intact satellites in "
            "orbit. Lessons: pre-2009 SSN tracking accuracy + dwell "
            "time inadequate for active conjunction screening; led to "
            "expanded SDA capabilities and CARA process."
        ),
        keywords=("iridium", "cosmos", "collision", "debris", "sda"),
        source="cara",
        citation="Iridium-Cosmos Collision Lessons Learned (NASA CARA, 2009)",
        parameters=("MISS_DISTANCE_KM", "PROBABILITY_OF_COLLISION"),
    ),
    LessonRecord(
        record_id="fengyun-1c-asat",
        title="Fengyun-1C ASAT debris event (2007-01-11)",
        summary=(
            "Chinese ASAT test on aging Fengyun-1C satellite produced "
            "~3,500 trackable debris pieces persisting for decades. "
            "Lessons: ASAT debris is a long-tail problem; debris "
            "mitigation guidelines (UN COPUOS) must be enforced; "
            "operators must plan for an increasingly cluttered LEO "
            "environment."
        ),
        keywords=("fengyun", "asat", "debris", "leo"),
        source="us_state_dept",
        citation="US State Dept Fact Sheet on FY-1C (2007)",
        parameters=("DEBRIS_FLUX_PER_M2_DAY",),
    ),
    LessonRecord(
        record_id="iss-water-pump-2024",
        title="ISS WPA water pump failure (2024)",
        summary=(
            "Water Processor Assembly pump degraded due to silica build-up "
            "in process loop. Manual cleaning procedure executed by crew "
            "in-flight; recycle path restored. Lessons: cabin water "
            "chemistry trending must be more frequent; pre-emptive "
            "maintenance schedule should consider silica build-up rate."
        ),
        keywords=("wpa", "water pump", "silica"),
        source="iss_anomaly_log",
        citation="ISS On-Orbit Anomaly Report 2024-WPA (NASA)",
        parameters=("WPA_FLOW_KG_HR", "WPA_INLET_PRESSURE_KPA"),
    ),
    LessonRecord(
        record_id="hubble-pre-cosstar",
        title="Hubble primary-mirror flaw + COSTAR fix (1990-1993)",
        summary=(
            "Hubble launched 1990 with spherical aberration in primary "
            "mirror due to ground-test null-corrector misalignment "
            "during fabrication. SM1 (1993) installed COSTAR optics + "
            "WFPC2 to compensate. Lessons: end-to-end optical "
            "verification before flight; never trust a single null-"
            "corrector test; cosmic verification (star image) trumps "
            "test-stand verification."
        ),
        keywords=("hubble", "mirror", "spherical aberration", "costar"),
        source="hubble_history",
        citation="Hubble Space Telescope Optical Systems Failure Report (NASA, 1990)",
        parameters=("OPTICAL_PSF_FWHM_ARCSEC",),
    ),
    LessonRecord(
        record_id="iss-power-2022-tcs",
        title="ISS TCS pump module failure (2022)",
        summary=(
            "Loop B Pump Module developed leak; isolated, replaced via "
            "robotic-arm operation using spare from ESP. Lessons: "
            "spares-on-station for TCS critical components; robotic "
            "ORU replacement procedure validated; loop crossover "
            "capability proved out."
        ),
        keywords=("tcs", "pump module", "loop b", "oru"),
        source="iss_anomaly_log",
        citation="ISS On-Orbit Anomaly Log 2022-TCS (NASA)",
        parameters=("TCS_LOOP_B_PRESSURE_PSI",),
    ),
)


_CURATED_LESSONS_PROBES: tuple[LessonRecord, ...] = (
    LessonRecord(
        record_id="voyager-2-plasma-2007",
        title="Voyager 2 plasma instrument fault recovery (2007)",
        summary=(
            "Voyager 2 PLS instrument tripped due to high-voltage arc; ground "
            "command sequence reset the instrument to safe-mode. Lessons: "
            "high-voltage instruments age unpredictably; design must support "
            "safe-mode entry + ground-clearable; redundant power channels "
            "essential for instruments at edge of qualification life."
        ),
        keywords=("voyager", "plasma", "instrument", "high voltage"),
        source="jpl_voyager",
        citation="JPL Voyager Operations Status (2007)",
        parameters=("INSTRUMENT_HV_V", "INSTRUMENT_SAFE_FLAG"),
    ),
    LessonRecord(
        record_id="galileo-hga-failure",
        title="Galileo High Gain Antenna deployment failure (1991)",
        summary=(
            "Galileo's HGA failed to fully unfurl after 6-year storage in transit; "
            "3 of 18 ribs stuck. Mission rescued by reprogramming on-board "
            "compression + using LGA. Lessons: long-duration mechanism storage "
            "needs lubrication-degradation testing; communication system needs "
            "graceful-degradation modes from design phase."
        ),
        keywords=("galileo", "hga", "antenna", "deployment"),
        source="jpl_galileo",
        citation="Galileo Mission Final Report (JPL, 2003)",
        parameters=("HGA_DEPLOY_RIB_COUNT", "TELEMETRY_RATE_BPS"),
    ),
    LessonRecord(
        record_id="curiosity-wheel-damage-2014",
        title="Curiosity wheel damage discovery (2014)",
        summary=(
            "Curiosity wheels showed unexpected punctures after 1.5 years of "
            "Mars driving. Cause: sharp embedded rocks in fine-grained terrain. "
            "Lessons: wheel-life-prediction model under-estimated wear by 5x; "
            "drive-planning now incorporates wheel imagery monthly; future "
            "rovers (Perseverance) had wheel redesign."
        ),
        keywords=("curiosity", "wheel", "mars", "wear"),
        source="jpl_msl",
        citation="MSL Wheel Wear Investigation (JPL D-100789, 2014)",
        parameters=("WHEEL_PUNCTURE_COUNT", "DISTANCE_DRIVEN_KM"),
    ),
    LessonRecord(
        record_id="lunar-prospector-spin-recovery",
        title="Lunar Prospector spin recovery (1998)",
        summary=(
            "Lunar Prospector entered emergency-sun-acquisition after attitude "
            "control fault. Recovered via on-board sun-spin attitude algorithm. "
            "Lessons: simple sun-spin recovery suffices for first-line attitude "
            "loss; expensive star-tracker recovery only needed for fine pointing."
        ),
        keywords=("lunar prospector", "sun spin", "attitude"),
        source="nasa_ames_lp",
        citation="Lunar Prospector Mission Report (NASA Ames, 1999)",
        parameters=("SUN_LOCK_FLAG", "SPIN_RATE_RPM"),
    ),
    LessonRecord(
        record_id="maven-safe-mode-2018",
        title="MAVEN safe-mode entry during Mars conjunction (2018)",
        summary=(
            "MAVEN entered safe-mode during 2018 solar conjunction; communication "
            "blackout extended recovery by ~3 weeks. Cause: thermal model under-"
            "predicted heater duty during conjunction. Lessons: thermal models "
            "must include conjunction worst-case scenarios; safe-mode recovery "
            "must work autonomously through conjunction blackout."
        ),
        keywords=("maven", "safe mode", "mars", "conjunction"),
        source="nasa_maven",
        citation="MAVEN Anomaly Report 2018-09 (NASA, 2018)",
        parameters=("SAFE_MODE_FLAG", "HEATER_DUTY_PCT"),
    ),
    LessonRecord(
        record_id="soyuz-ms11-pad-abort-2018",
        title="Soyuz MS-11 pad abort (2018)",
        summary=(
            "Soyuz launcher experienced staging anomaly causing crew capsule "
            "abort. Crew survived ballistic descent at 7g. Lessons: launch escape "
            "system worked as designed; subsequent investigation found bent "
            "actuating-pin in stage-2/3 separation; manufacturing QA tightened."
        ),
        keywords=("soyuz", "abort", "ms-11", "staging"),
        source="roscosmos",
        citation="Roscosmos Soyuz MS-11 Inquiry Commission (2019)",
        parameters=("STAGING_ANOMALY_FLAG", "G_LOAD_G"),
    ),
    LessonRecord(
        record_id="terrasar-x-failure-2018",
        title="TerraSAR-X SAR-instrument cooling failure (2018)",
        summary=(
            "TerraSAR-X SAR instrument lost cooling capability; instrument went "
            "offline. Recovery required lower-duty-cycle operation. Lessons: "
            "active cooling for radar instruments is single-point-of-failure; "
            "future SAR satellites have redundant cooling loops."
        ),
        keywords=("terrasar-x", "sar", "cooling"),
        source="dlr_terrasar",
        citation="TerraSAR-X Operations Report (DLR, 2019)",
        parameters=("SAR_COOLER_TEMP_K", "SAR_DUTY_CYCLE_PCT"),
    ),
    LessonRecord(
        record_id="cluster-2-mass-imbalance-2000",
        title="Cluster-2 mass imbalance discovery on orbit",
        summary=(
            "ESA Cluster-2 four-spacecraft formation found unexpected ~2% mass "
            "imbalance between vehicles, complicating formation-flying control. "
            "Lessons: pre-launch mass-property measurements must achieve <0.5%; "
            "balance-mass adjustment kits should be flight-launchable."
        ),
        keywords=("cluster", "formation flying", "mass"),
        source="esa_cluster",
        citation="Cluster-2 Mission Report (ESA, 2003)",
        parameters=("MASS_IMBALANCE_PCT"),
    ),
    LessonRecord(
        record_id="iss-amg-2007-failure",
        title="ISS Service Module computer triple-redundant failure (2007)",
        summary=(
            "All 3 RS Service Module computers failed simultaneously; ISS attitude "
            "lost 4 hours; CMG-only attitude restored. Cause: condensation in "
            "connector pins. Lessons: triple-redundancy can fail to common-cause "
            "(condensation here); environmental qualification must include high-"
            "humidity exposure."
        ),
        keywords=("iss", "service module", "computer", "redundancy"),
        source="iss_anomaly_log",
        citation="ISS On-Orbit Anomaly Log 2007-RS-COMP",
        parameters=("RS_COMPUTER_HEALTH_COUNT"),
    ),
    LessonRecord(
        record_id="mer-airbag-deflation-2004",
        title="MER airbag deflation contingency (Spirit, 2004)",
        summary=(
            "Spirit airbag caught on lander petal during retraction, requiring "
            "rover to drive across lander to deploy. Contingency procedure was "
            "ad-hoc; took 2 sols to develop. Lessons: airbag-and-petal interactions "
            "should be ground-tested in regolith analog with mockup; future "
            "missions plan deployment contingency before launch."
        ),
        keywords=("spirit", "mer", "airbag", "petal"),
        source="jpl_mer",
        citation="MER Spirit Operations Report (JPL, 2004)",
        parameters=("PETAL_DEPLOYED_FLAG", "AIRBAG_RETRACTED_FLAG"),
    ),
    LessonRecord(
        record_id="iss-water-2025-leak",
        title="ISS Russian Segment Zvezda water leak (2025)",
        summary=(
            "Long-running water leak in Zvezda module steadily declining cabin "
            "humidity. Crew applied multiple patches; leak rate reduced not "
            "eliminated. Lessons: legacy hardware reaches end-of-life mid-mission; "
            "fleet planning must include hardware refresh cadence."
        ),
        keywords=("iss", "zvezda", "leak", "water"),
        source="iss_anomaly_log",
        citation="ISS On-Orbit Anomaly Log 2025-ZVEZDA",
        parameters=("CABIN_HUMIDITY_PCT", "LEAK_RATE_KG_DAY"),
    ),
    LessonRecord(
        record_id="bepicolombo-thrust-issue-2024",
        title="BepiColombo SEP thrust degradation (2024)",
        summary=(
            "BepiColombo solar electric propulsion system experienced thrust "
            "degradation requiring trajectory replan. Mission delayed Mercury "
            "arrival from 2025 to 2026. Lessons: SEP cumulative-burn lifetime is "
            "uncertain; mission timelines need budget for mid-mission contingency."
        ),
        keywords=("bepicolombo", "sep", "thrust"),
        source="esa_jaxa_bepicolombo",
        citation="BepiColombo Operations Report (ESA/JAXA, 2024)",
        parameters=("SEP_THRUST_MN", "SEP_CUMULATIVE_HOURS"),
    ),
    LessonRecord(
        record_id="iss-leak-russia-2020",
        title="ISS Russian Segment leak detection (2020)",
        summary=(
            "Slow leak in Zvezda detected via cabin pressure trending. Crew used "
            "tea-bag particle method to locate leak (visual airflow). Patch "
            "applied; pressure stable. Lessons: low-tech leak-locator tools "
            "(particle tracking) work effectively where electronic detectors fail."
        ),
        keywords=("iss", "leak", "zvezda", "particle"),
        source="iss_anomaly_log",
        citation="ISS Anomaly Report 2020-ZVEZDA",
        parameters=("CABIN_PRESSURE_RATE_KPA_HR"),
    ),
    LessonRecord(
        record_id="boeing-cft-thruster-2024",
        title="Boeing Starliner CFT thruster failures (2024)",
        summary=(
            "During Crewed Flight Test, multiple RCS thrusters degraded due to "
            "Teflon seal heating during fire-cycles. Crew docked successfully but "
            "return delayed pending analysis. Lessons: thermal-cycle test envelope "
            "must include in-flight worst case; spare thruster strings critical."
        ),
        keywords=("starliner", "cft", "thruster", "rcs"),
        source="boeing_cft",
        citation="Starliner CFT Anomaly Report (Boeing/NASA, 2024)",
        parameters=("RCS_THRUSTER_HEALTH_COUNT"),
    ),
    LessonRecord(
        record_id="jwst-micrometeorite-2022",
        title="JWST primary mirror micrometeorite hit (2022)",
        summary=(
            "JWST primary segment C3 hit by larger-than-expected micrometeorite "
            "shortly after commissioning. Permanent ~deg-arc surface damage; image "
            "quality degraded slightly. Lessons: L2 environment more debris-rich "
            "than predicted; future telescopes must design micrometeorite resistance "
            "to higher specs."
        ),
        keywords=("jwst", "micrometeorite", "mirror", "l2"),
        source="nasa_jwst",
        citation="JWST Commissioning Report (NASA/STScI, 2022)",
        parameters=("MIRROR_SEGMENT_DAMAGE_FLAG"),
    ),
    LessonRecord(
        record_id="hayabusa2-touchdown-anomaly",
        title="Hayabusa2 first touchdown delay (2018)",
        summary=(
            "Hayabusa2 first sample-collection touchdown delayed when LIDAR found "
            "unexpectedly rough Ryugu surface. Multi-month replan to find safe site. "
            "Lessons: pre-arrival imaging insufficient for asteroids; on-site LIDAR "
            "essential and replan capability critical."
        ),
        keywords=("hayabusa2", "ryugu", "touchdown", "lidar"),
        source="jaxa_hayabusa2",
        citation="Hayabusa2 Mission Report (JAXA, 2020)",
        parameters=("LIDAR_RANGE_M", "TARGET_SURFACE_ROUGHNESS"),
    ),
    LessonRecord(
        record_id="aeolus-end-of-life",
        title="ESA Aeolus controlled deorbit (2023)",
        summary=(
            "First operational satellite to perform fully ground-controlled "
            "targeted deorbit (assisted re-entry over uninhabited ocean). "
            "Lessons: space-debris-mitigation can be done; future missions should "
            "design for controlled deorbit even if not initially required."
        ),
        keywords=("aeolus", "deorbit", "esa", "debris"),
        source="esa_aeolus",
        citation="Aeolus End-of-Life Report (ESA, 2023)",
        parameters=("DEORBIT_PHASE", "RE_ENTRY_LAT_DEG"),
    ),
    LessonRecord(
        record_id="kepler-spacecraft-emergency-2016",
        title="Kepler spacecraft emergency mode (2016)",
        summary=(
            "Kepler entered emergency mode during K2 campaign; recovery took 14 "
            "hours by ground team. Cause: faulty orbital propagation in onboard "
            "model. Lessons: critical fault paths must self-recover or have very "
            "rapid ground response capability."
        ),
        keywords=("kepler", "emergency mode", "k2"),
        source="nasa_kepler",
        citation="Kepler Operations Report (NASA Ames, 2017)",
        parameters=("EMERGENCY_MODE_DURATION_HR"),
    ),
    LessonRecord(
        record_id="nimbus-7-spinrate-2007",
        title="NOAA Nimbus-7 spin-rate anomaly (2007)",
        summary=(
            "Aging Nimbus-7 satellite suddenly increased spin rate after 26 years. "
            "Cause: bearing degradation in momentum wheel. Lessons: spacecraft "
            "well past design life can experience sudden mechanical degradation; "
            "consistent monitoring is mission-extension prerequisite."
        ),
        keywords=("nimbus", "spin", "bearing", "wheel"),
        source="noaa",
        citation="NOAA Nimbus-7 End of Life Report (2007)",
        parameters=("SPIN_RATE_RPM"),
    ),
    LessonRecord(
        record_id="aqua-aura-thruster-degradation",
        title="Aqua/Aura thruster degradation (mid-mission)",
        summary=(
            "Aqua and Aura Earth-observation satellites experienced gradual "
            "thruster performance degradation, requiring more propellant for "
            "station-keeping. Lessons: cumulative thrust-on-time has higher "
            "performance impact than expected; propellant budget must include "
            "degradation factor."
        ),
        keywords=("aqua", "aura", "thruster", "degradation"),
        source="nasa_eos",
        citation="EOS Aqua/Aura Operations Status (NASA Goddard, 2017)",
        parameters=("THRUSTER_PERFORMANCE_PCT"),
    ),
    LessonRecord(
        record_id="stardust-1999-cruise-saa",
        title="Stardust SAA-induced reset (1999)",
        summary=(
            "Stardust experienced multiple South Atlantic Anomaly induced computer "
            "resets during cruise phase. Lessons: shielding inadequate for SAA "
            "transit; future missions to deep space had EDAC strengthened; SAA "
            "transit avoidance during critical operations adopted."
        ),
        keywords=("stardust", "saa", "reset", "edac"),
        source="jpl_stardust",
        citation="Stardust Mission Operations Report (JPL, 2006)",
        parameters=("SAA_RESET_COUNT"),
    ),
    LessonRecord(
        record_id="fermi-gamma-ray-pointing-2018",
        title="Fermi Gamma-Ray pointing anomaly (2018)",
        summary=(
            "Fermi pointing accuracy degraded due to reaction wheel friction "
            "increase. Mission shifted to lower-precision survey mode. Lessons: "
            "instrument-driven pointing requirements must allow degraded modes; "
            "engineering reserves for wheel torque are critical."
        ),
        keywords=("fermi", "gamma ray", "pointing", "wheel"),
        source="nasa_fermi",
        citation="Fermi Operations Report (NASA Goddard, 2018)",
        parameters=("POINTING_ERROR_ARCMIN", "WHEEL_FRICTION_NM"),
    ),
    LessonRecord(
        record_id="dawn-end-of-mission-2018",
        title="Dawn fuel depletion + mission end (2018)",
        summary=(
            "Dawn ion-engine spacecraft ran out of hydrazine for attitude control "
            "after 11 years; left in stable orbit around Ceres. Lessons: hydrazine "
            "for attitude control is mission-life-limiting; mission planning must "
            "balance ion-engine ΔV with attitude budget."
        ),
        keywords=("dawn", "ion engine", "hydrazine", "ceres"),
        source="nasa_dawn",
        citation="Dawn Mission Final Report (JPL, 2019)",
        parameters=("HYDRAZINE_REMAINING_KG"),
    ),
    LessonRecord(
        record_id="ladee-2014-end-mission",
        title="LADEE atmospheric impact (2014)",
        summary=(
            "LADEE deliberately impacted Lunar surface at end-of-mission to "
            "characterise crashes. Spacecraft survived longer than predicted in "
            "low-altitude orbit. Lessons: atmospheric drag at lunar altitude is "
            "predictable but lower than CSM expectations; controlled-impact end-"
            "of-mission generates valuable science."
        ),
        keywords=("ladee", "lunar", "impact", "drag"),
        source="nasa_ladee",
        citation="LADEE Mission Final Report (NASA Ames, 2014)",
        parameters=("ALTITUDE_KM"),
    ),
    LessonRecord(
        record_id="iss-sarj-degradation-2007",
        title="ISS Solar Alpha Rotary Joint contamination (2007)",
        summary=(
            "Right-hand SARJ developed unexpected metal-shavings contamination "
            "in trundle bearings. Mission switched to backup string; multiple EVAs "
            "required for cleanup. Lessons: rotary joints in continuous service "
            "need monitoring of bearing health; debris-tolerant design essential."
        ),
        keywords=("iss", "sarj", "rotary joint", "bearing"),
        source="iss_anomaly_log",
        citation="ISS SARJ Anomaly Investigation (NASA, 2008)",
        parameters=("SARJ_BEARING_VIBRATION_G"),
    ),
)


CURATED_LESSONS: tuple[LessonRecord, ...] = (
    _CURATED_LESSONS_CORE + _CURATED_LESSONS_EXTENDED + _CURATED_LESSONS_PROBES
)


def load_curated_lessons() -> tuple[LessonRecord, ...]:
    return CURATED_LESSONS


class NtrsSearchClient:
    def __init__(
        self,
        *,
        timeout_s: float = NTRS_DEFAULT_TIMEOUT_S,
        user_agent: str = NTRS_USER_AGENT,
        opener: Optional[urllib.request.OpenerDirector] = None,
    ) -> None:
        self._timeout_s = timeout_s
        self._user_agent = user_agent
        self._opener = opener or urllib.request.build_opener()

    def search(
        self,
        query: str,
        *,
        page_size: int = NTRS_DEFAULT_PAGE_SIZE,
    ) -> list[dict]:
        params = {"q": query, "page.size": str(page_size)}
        url = f"{NTRS_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url, headers={"User-Agent": self._user_agent, "Accept": "application/json"},
        )
        try:
            with self._opener.open(req, timeout=self._timeout_s) as resp:
                raw = resp.read()
        except urllib.error.URLError as exc:
            logger.warning("ntrs.fetch_failed", error=str(exc), query=query)
            return []
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            logger.warning("ntrs.json_decode_error", query=query)
            return []
        results = payload.get("results") or []
        if not isinstance(results, list):
            return []
        return [item for item in results if isinstance(item, dict)]


def write_lessons_to_doctrine(
    records: Iterable[LessonRecord],
    *,
    doctrine_path: Path,
) -> int:
    doctrine_path.parent.mkdir(parents=True, exist_ok=True)
    entries = [record.as_doctrine_entry() for record in records]
    doctrine_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return len(entries)
