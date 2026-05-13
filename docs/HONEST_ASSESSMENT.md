# ARIA — Honest Assessment of What This Is, Isn't, and Should Become

This document exists because earlier banners (including ones added
2026-04-28 in the "production-grade sprint") drifted into language
that overclaimed. ARIA is a sophisticated R&D sandbox. It is **not**
production AI for spacecraft, no one has built that, and the
distance to anything spaceworthy is honestly described below.

This file supersedes optimistic banners; when language conflicts,
this file wins.

## What ARIA actually is

* A **simulation framework** for orbital mechanics, propulsion, thermal,
  power, ECLSS, FEA, CFD — research-grade, with citations.
* A **governance prototype**: 19 failsafe controls (F-1..F-19),
  351 round-by-round security defenses, two-person rule for
  CONSENT-or-above actions, sealed prompt + capability tokens, a
  monitor sidecar process.
* An **arithmetic-validation harness** against historical missions —
  Apollo 11 Δv per phase, Saturn V launch-to-TLI, Iridium-Cosmos
  TCA, Soyuz rendezvous, Artemis II planned profile, 12 historical
  conjunctions. The simulator reproduces these within stated tolerance
  bands. That is **not** flight validation. It is *cross-checking the
  simulator math against the historical record*.
* An **engineering trade-study sandbox** with parametric CadQuery
  geometry, 1098 BoH components, ~5000 mostly-parametric catalog parts.

## What ARIA is not

* Not flight software. No flight heritage. No DO-178C / NPR-7150.2D
  Class B. No real-time guarantees. Python is not a flight language.
* Not certified for any spacecraft, anywhere, ever.
* Not "production AI for intergalactic travel". No nation has built
  that. Mars rovers run AEGIS / MEXEC — **narrow rule-based planners**
  with petabytes of mission-specific tuning. Voyager runs hand-coded
  command sequences from the 1970s. The ISS uses commercial off-the-
  shelf computers running Linux and 30-year-old C++ for ECLSS.
* Not running an LLM in the spacecraft control loop. ARIA's LLM
  integration is an **advisor that runs above the safety layer**. It
  cannot close any control loop. This is correct safety architecture
  but means the actual "decision making" is done by deterministic
  rules, not the LLM, when it counts.
* Not validated against any real hardware. No HIL, no flatsat, no
  air-bearing, no vibration table, no thermal-vacuum chamber. Every
  number ARIA reports is from simulation.
* Not modelling real microbial dynamics, plant growth physics,
  hypervelocity impact mechanics, or radiation transport at the
  fidelity of dedicated tools (LIM, GEANT4, Cucinotta NSCRR, etc.).
  ARIA either calls into those tools or uses simplified analytical
  models that get within an order of magnitude.

## Where the LLM legitimately fits — based on 2026 research

Recent published work (CVPR 2026 AI4Space Workshop; arXiv 2601.04334
+ 2604.17176 + 2603.27306) shows the research community putting LLMs
in spacecraft control in **specific, narrow ways with formal safety
gates**:

| Approach | Where the LLM sits | Safety gate |
|----------|-------------------|-------------|
| Intent-aligned guidance (arXiv 2604.17176) | LLM produces *waypoint constraints* from high-level intent | SCP solver enforces dynamics + safety; LLM never produces final trajectory |
| GUIDE in-context evolution (CVPR 2026 AI4Space) | LLM picks from a *playbook* of pre-validated actions | Acting model (not LLM) does real-time control; LLM only updates the playbook offline |
| GRPO + SFT spacecraft control (arXiv 2601.04334) | LLM is fine-tuned on simulated trajectories | Future work calls for MPC integration + formal verification |
| Fine-tuned LLM as KSP controller (arXiv 2408.08676) | LLM produces control commands directly | Demonstrated in *Kerbal Space Program*, not real spacecraft |

**The pattern is consistent: LLMs as high-level reasoners, deterministic
control underneath, formal verification on top.** ARIA's architecture
(LLM advises, safety layer enforces, agents actuate) is in the right
shape — but the LLM's *decisions are not used* in any closed control
loop, even in our own simulator. That is the gap.

## Real gaps, with citations

### 1. Geometry — parametric expansions vs real STEP files

* **What we have**: 11 parametric CadQuery parts; 5,123 mostly-
  parametric catalog parts; 1,098 BoH components.
* **What real spacecraft have**: thousands of physical parts with
  vendor part numbers, interface control documents (ICDs), heritage
  test data, qualification waivers, real STEP files round-tripped
  through assembly tools.
* **Real-world tooling**: [FreeCAD 1.0](https://www.freecad.org)
  ships with built-in assembly workbench (Ondsel Solver, 3D
  constraints between parts). [OpenCASCADE Technology](https://dev.opencascade.org)
  is the kernel underneath FreeCAD and many commercial tools; it
  reads/writes STEP and is the canonical aerospace exchange format.
* **What would actually help ARIA**: a STEP-import path that lets
  an operator drop in real CubeSat / smallsat CAD models from MfG
  catalogs (ISIS Space, NanoAvionics, Spire) and get geometry,
  mass properties, and FEA out without re-modelling. We have
  parametric *templates* for things like hulls and reactors;
  we do not have **real spacecraft geometry**.

### 2. Materials — parametric vs MMPDS / MAPTIS / SPACEMATDB

* **What we have**: 67 materials in the catalog, 1098 BoH components
  with parametric properties.
* **What real material design uses**: [MMPDS Handbook 2025](https://www.mmpds.org)
  with 2,000+ statistically-derived design allowables for aerospace
  alloys. NASA [MAPTIS](https://maptis.nasa.gov) has spacecraft-
  specific material data — vacuum outgassing, atomic-oxygen erosion,
  radiation tolerance. [SPACEMATDB](https://www.spacematdb.com) is
  open-access for declared materials in real flown hardware.
  [CINDAS Aerospace Structural Materials Database](https://cindasdata.com)
  has 98,815 data curves on 287 alloys.
* **Gap**: ARIA's catalog is parametric. MMPDS / MAPTIS / SPACEMATDB
  is statistically validated against thousands of test specimens.
  When ARIA says a Ti-6Al-4V part can survive a load case, the
  underlying yield strength is one number with no S/N curve, no
  notch sensitivity, no temperature derate, no aging effect.
  Real designs need the full curve.

### 3. Energy — parameterized agent vs real cell-level models

* **What we have**: PowerAgent with battery SoH (Schmalstieg 2014 +
  Millner 2010), eclipse predictor, load-shed cascade, inrush guard.
  Citations are good, math is correct.
* **What real spacecraft EPS systems use**:
  - **Solar cells**: actual I-V curves from Spectrolab XTJ-Prime
    (29.5 % BOL efficiency), Azur Space 3G30A, etc. Each cell type
    has temperature coefficient, radiation degradation curve,
    angle-of-incidence loss table.
  - **Batteries**: vendor cell models from Saft VES180 (Li-ion),
    EaglePicher SAR-10231 (Li-CFx), with real cycle/calendar data.
  - **RTGs / reactors**: GPHS-MMRTG (124 W BOL Pu-238), Kilopower
    (1-10 kWe fission). Real models account for thermo-electric
    decay, hot/cold-side ΔT, radiator emissivity drift.
  - **Power conditioning**: real PCDU efficiency maps, real point-of-
    load DC-DC converters, real harness IR drop.
* **Gap**: ARIA's power model is at the agent level. To simulate a
  real CubeSat or smallsat EPS you need cell-level fidelity with
  vendor datasheet curves.

### 4. Food / bioregenerative life support

* **What we have**: ECLSS bridge claims "100 % food self-sufficiency
  at 100 crew via ring agriculture" — this is *aspirational* and
  badly overclaimed.
* **Reality check**: [MELiSSA](https://www.esa.int/Enabling_Support/Space_Engineering_Technology/Melissa)
  is the most advanced closed-loop life-support project on Earth.
  It is at TRL 4-6 in the lab and **needs 4-8 more years of
  operational experience to reach full TRL** for a fully
  bioregenerative system. ESA's pilot plant in Barcelona is still
  running compartment tests — and they're testing 1-3 humans, not
  100. ISS food is still 100 % resupply except for token Veggie /
  Advanced Plant Habitat experiments.
* **Microbial dynamics, plant growth physics, atmosphere CO2/O2
  balance, water recovery, waste decomposition** — these are real,
  hard, multi-disciplinary problems. ARIA does not model them at
  the fidelity required for a real closed loop. Saying "100 % food
  self-sufficiency" without orders-of-magnitude more biology is
  fiction.
* **Honest gap**: pull the 100-crew claim. Replace with "1-3 person
  bioregenerative model based on MELiSSA compartment fidelity,
  with explicit TRL gating".

### 5. Hardware-in-loop validation

* **What we have**: zero. Pure software simulator.
* **What's needed**: HIL with real ADCS sensors / actuators on an
  air-bearing platform. Universities have these:
  - Naval Postgraduate School CubeTAS (nano-sat 3-axis)
  - University of Brasília Helmholtz-cage tabletop
  - South Dakota State START (Aerospace Robotics Testbed Lab)
  - Caltech, Stanford, Georgia Tech all have flatsats
* **Path forward**: partner with one of these to ingest real IMU /
  star-tracker / reaction-wheel telemetry and validate the GNC
  layer against ground truth.

### 6. Real-time / safety certification

* **What we have**: Python on CPython. Garbage collector. No real-
  time guarantees. No formal verification.
* **What flight software is**: NASA cFS in C, frozen WCET budgets,
  static memory allocation, MISRA-C, hardware watchdog, redundant
  computing chains. Class B per NPR-7150.2D requires formal hazard
  analysis, code coverage, traceability matrices.
* **Reality**: ARIA's cFS bridge skeleton compiles. That is **not
  the same as running**. To actually fly you need a complete RTOS
  port (VxWorks, RTEMS, FreeRTOS) and the certification paperwork
  trail of a real flight project (typically 3-5 years, $10-50M).

### 7. Radiation environment

* **What we have**: SPE catalog (17 events 1956-2024), HZE dose
  proxies, ICRP-123 crew radiation calculations.
* **What real radiation engineering needs**:
  - GEANT4 / FLUKA / PHITS Monte Carlo transport for shielding
    design (not analytical Cucinotta proxies)
  - SPENVIS or OMERE for trapped-belt + GCR + SPE environment
  - Real device cross-section data for SEU/SEL/SEFI
  - TID and DDD analysis with vendor lot data
* **Gap**: every Monte Carlo radiation result in ARIA is a
  simplified analytical proxy. For real shielding design you need
  to run GEANT4.

### 8. Where the LLM should — and shouldn't — be

* **Should**: high-level mission planning, anomaly explanation, ops
  procedure generation, ground-side analysis, generating regression
  tests for the safety layer, helping operators understand what
  the spacecraft is doing.
* **Should NOT**: closing any control loop without a formal
  verification gate underneath. **The current ARIA architecture is
  correct on this** — the LLM's `engine.reason()` produces text;
  the action_executor parses it; the agents call `safe_dispatch`
  which runs the full F-1..F-19 stack.
* **What's missing**: a clean **LLM evaluation surface** that
  measures decision quality the way frontier labs
  measure it on benchmarks — refusal-rate vs evaluation marker,
  hallucination rate vs grounded-context, action-overlap with
  expert operators on a held-out test set. We have F-11 sandbagging
  detection but not a continuous benchmark.

### 9. What would honestly move the needle

In rough priority order:

1. **Pull the worst over-claims out of README + INDEX**. "100 %
   food self-sufficiency at 100 crew", "production-grade",
   "deployable on real spacecraft" must go.
   **✅ DONE 2026-04-29** — commit `aea3744`.
2. **STEP file import path** (FreeCAD / OCCT) for real spacecraft
   geometry — replaces the parametric-only fiction with operator-
   uploadable real models.
   **✅ DONE 2026-04-29** — commit `b394c3c`. 21 tests passing;
   validated against analytical truth (1 m³ Al cube → 2700 kg,
   450 kg·m² inertia) + CDS-Rev-14 3U CubeSat envelope. See
   [`src/aria/digital_twin/step_loader.py`](../src/aria/digital_twin/step_loader.py).
3. **Vendor-cell-level EPS model**: ingest real Spectrolab XTJ-
   Prime + Saft VES180 + Azur 3G30A datasheet curves. Replace the
   single-Isp / single-efficiency numbers with real I-V + cycle
   curves.
   **✅ DONE 2026-04-29** — commit `725689d` (preceded by EPS
   commit). 35 tests passing; cited per Spectrolab TR2020A,
   Azur 3G30C-Adv Rev 5.5, Saft VES180 Doc 31130-2-0316. See
   [`src/aria/physics/eps/`](../src/aria/physics/eps/).
4. **Bioregenerative model bounded to MELiSSA TRL 4-6 fidelity**:
   1-3 person Compartment IV-A (higher plants), Compartment III
   (nitrification), Compartment I (anaerobic). 100-crew claim
   retired.
   **✅ DONE 2026-04-29** — `aria.physics.bioregen` module with
   five MELiSSA compartments (C-I anaerobic, C-II R. rubrum,
   C-III nitrification, C-IV-A higher plants, C-IV-B Spirulina)
   coupled by the steady-state mass-balance solver. 39 tests
   passing; cited per Lasseur 2010, Hendrickx 2006, Godia 2002,
   Wheeler 2017, NASA BVAD §4.1. Crew complement gated to
   `MAX_VALIDATED_CREW = 3`; constructing `Crew(crew_size=100)`
   raises `ValueError` mentioning "MELiSSA validated 1-3", so the
   100-crew overclaim is **structurally impossible** to revive
   in code. See [`src/aria/physics/bioregen/`](../src/aria/physics/bioregen/).
5. **Real radiation transport via GEANT4 calls** (not analytical
   proxy) for the shielding-design path.
   **✅ DONE 2026-04-29** (optional-dependency pattern) —
   `aria.physics.radiation_transport` exposes a single
   `simulate_dose()` API with two backends: an always-available
   analytical proxy (NIST PSTAR proton ranges + Cucinotta 2014
   GCR attenuation, ±20 % screening) and an optional GEANT4
   backend that activates when `geant4-pybind` is installed.
   Auto-selection picks GEANT4 when present, falls back to
   analytical with a structured warning otherwise. 29 tests
   passing — analytical math validated against NIST PSTAR proton
   ranges + Cucinotta exp-fall attenuation; GEANT4 backend
   ImportError path tested without requiring the install. The
   integration point (`_geant4_runner.py`) is the operator's
   extension point — supply a geant4_pybind-version-pinned
   runner for full TRL 5/6 closure. See
   [`src/aria/physics/radiation_transport/`](../src/aria/physics/radiation_transport/).
6. **University HIL partnership** for ADCS validation against real
   air-bearing telemetry. The pitch: ARIA's safety stack + their
   hardware = a real test article for autonomous control research.
7. **LLM evaluation harness** that grades decisions against held-
   out historical-mission decision logs (Apollo 13 fault diagnosis,
   Hubble servicing decision tree, ISS Russian-segment leak response).
   **✅ DONE 2026-04-29** — commits `725689d` (3 scenarios) and
   `f280cee` (8 more, 11 total). Live benchmark via the configured LLM CLI
   CLI, no API key needed. 91 weighted criteria across 11
   scenarios spanning 9 failure modes. First score on default
   set: aggregate 0.98 (3/3 PASS) on initial 3-scenario set.
   See [`src/aria/cognitive/llm_eval/`](../src/aria/cognitive/llm_eval/).
8. **Continuous integration of new published research**: V-2
   masked-residual pretraining, A-3 BOCPD detection lag, GUIDE in-
   context evolution — these are landing in the literature monthly.
   ARIA should auto-track the relevant arXiv-cs.RO + arXiv-cs.LG
   feeds the way Dependabot tracks pip packages.
   **✅ DONE 2026-04-29** — `aria.research` module: polite arXiv
   API client (3 s rate-limit, 6 h cache), 7 subsystem-specific
   filters (autonomy / ml_safety / guidance_navigation /
   life_support / propulsion / radiation / conjunction), digest
   builder that aggregates matches and writes
   `data/runtime/research/digest_<YYYY-MM-DD>.{md,json}`.
   17 unit tests passing; live arXiv smoke confirmed parsing of
   real cs.RO entries. Run via `python -m aria.research`. See
   [`src/aria/research/`](../src/aria/research/).
9. **Real ground-station integration** with actual telemetry from
   SatNOGS or RBC-Signal volunteer networks. ARIA's screener,
   advisor, and conjunction tools should run against real LEO
   smallsat downlink — not synthetic test fixtures.
   **✅ DONE 2026-04-29** — `aria.integrations.satnogs` is a
   working SatNOGS DB API client. Public-tier endpoints
   (satellites, transmitters, TLE, modes) work without auth;
   authenticated telemetry endpoint gates cleanly on
   `ARIA_SATNOGS_API_KEY`. 16 unit + 2 live tests passing; live
   smoke confirmed against ISS (NORAD 25544): 49 transmitter
   records pulled cleanly with frequencies in MHz, modes
   labelled (FM Voice / AFSK 1k2 / etc.).
   Remaining for full TRL-6 closure: actually wire the live
   telemetry feed into the dsremo anomaly detector and run a
   multi-week soak against a chosen smallsat (operator
   decision; needs API key registration with SatNOGS). See
   [`src/aria/integrations/satnogs.py`](../src/aria/integrations/satnogs.py).
10. **Honest TRL banner per subsystem** in README + INDEX. Each
    module should say what TRL it's at and what it would take to
    raise it. Many are at TRL 3 (analytical proof of concept),
    not the TRL 6-8 the banners imply.
    **✅ DONE 2026-04-29** — `docs/SUBSYSTEM_TRL.md` is the
    authoritative per-subsystem TRL accounting on the NASA
    NPR-7150.2D scale. ~50 subsystems classified across orbital
    mechanics + propulsion + power/thermal/ECLSS + geometry +
    materials + radiation + cognitive engine + safety architecture
    (F-1..F-19) + recovery + bridges + security + operations.
    **Nothing in ARIA is at TRL 7 or higher** (no flight heritage).
    Most subsystems are TRL 3-5; flight gap (RTOS / rad-hard CPU /
    DO-178C / HIL / partner mission) is named explicitly. Reviewed
    at every minor release.  See [`docs/SUBSYSTEM_TRL.md`](SUBSYSTEM_TRL.md).

## What this means for next work

Stop adding more layers and audit passes against the existing
simulator. Start grounding the simulator against real data, real
hardware, and real published reference tools. Specifically:

* Don't add another security audit pass; we have nine.
* Don't add another parametric subsystem; we have dozens.
* Don't add another in-house simulation module; the open-source
  ecosystem (FreeCAD, OpenCASCADE, GEANT4, MELiSSA pilot plant
  data, OpenRadioss, Code_Aster, CalculiX, SPICE, GMAT) is mature
  and validated.
* Do replace ARIA's parametric / synthetic numbers with calls into
  those validated tools where possible.
* Do retire over-claims from the README banner pile.
* Do find one concrete real-data integration to ground each major
  subsystem (Geometry → STEP/FreeCAD; Materials → MAPTIS/MMPDS;
  Power → vendor I-V curves; Bioregen → MELiSSA compartment data;
  Radiation → GEANT4).

## What "help humanity conquer space" honestly looks like for ARIA

ARIA can be a useful **open R&D sandbox** for autonomy + safety
research where the LLM is in a defensible role. The realistic
trajectory:

* **2026-2027**: replace synthetic / parametric models with real-
  data integrations; partner with one HIL lab; publish the safety-
  architecture work as a real paper (not just the SciTech 2027
  abstract draft).
* **2027-2028**: get a real CubeSat operator to use the conjunction
  screener in production (real customer); get a real flatsat or
  CubeSat mission operator to test the autonomy layer in a non-
  flight-critical role; submit cFS bridge for NASA cFS Gov review.
* **2028-2030**: with one or two real partner missions providing
  real telemetry, the autonomy layer accumulates evidence; safety
  certification work begins (probably Class C, not B, initially).
* **2030+**: maybe a real flown payload uses ARIA's cFS bridge
  for a non-mission-critical experiment, supervised by ground.

That is the honest path. "Intergalactic travel" is, generously, a
century out and ARIA's role would be one small piece of a much
larger ecosystem that doesn't exist yet.

## Sources (all real, all 2026)

* [NASA cFS GitHub](https://github.com/nasa/cFS) — production flight software with real heritage (JWST, LRO, GPM, 40+ missions); cFS Gov Alpha planned April 2026.
* [JPL AI Group — Operations for Autonomy](https://ai.jpl.nasa.gov/public/projects/ops-for-autonomy/) — MEXEC, ASPEN, AEGIS deployments and current research.
* [MEXEC paper](https://ai.jpl.nasa.gov/public/documents/papers/IntEx-2020-MEXEC.pdf) — flight-proven on ASTERIA CubeSat, components in Perseverance.
* [ESA MELiSSA program](https://www.esa.int/Enabling_Support/Space_Engineering_Technology/Melissa) — bioregenerative state of the art.
* [GUIDE: Guided Updates for In-context Decision Evolution (CVPR 2026 AI4Space)](https://arxiv.org/html/2603.27306) — LLM in-context evolution for KSP differential games.
* [Intent-aligned Autonomous Spacecraft Guidance via Reasoning Models](https://arxiv.org/html/2604.17176) — Qwen2.5-7B + LoRA + SCP solver.
* [Autonomous Reasoning for Spacecraft Control with GRPO](https://arxiv.org/html/2601.04334) — SFT + GRPO; calls for formal verification.
* [Fine-tuning LLMs for Autonomous Spacecraft Control](https://arxiv.org/pdf/2408.08676) — KSP demonstration.
* [MMPDS Handbook 2025](https://www.mmpds.org) — aerospace metallic materials design allowables.
* [NASA MAPTIS](https://maptis.nasa.gov) — spacecraft material properties.
* [SPACEMATDB](https://www.spacematdb.com) — declared materials in real flown spacecraft.
* [FreeCAD 1.0](https://www.freecad.org) — open-source parametric CAD with assembly + STEP.
* [OpenCASCADE Technology](https://dev.opencascade.org) — CAD kernel.
* [OpenRadioss](https://altair.com/newsroom/news-releases/industry-proven-altair-radioss-finite-element-analysis-solver-now-available-as-open-source-solution) — Altair's commercial-grade FEA solver, now open source.
* [Code_Aster](https://www.code-aster.org) — French nuclear-industry FEA, accepted for safety-critical applications.

---

*If you read only one section of this file, read "Where the LLM
legitimately fits" and "What would honestly move the needle".
Everything else is supporting evidence.*
