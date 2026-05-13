# ARIA — Per-subsystem Technology Readiness Level (TRL)

This document is the authoritative honest accounting of where each
ARIA subsystem stands on the **NASA NPR-7150.2D / ECSS-E-HB-11A**
Technology Readiness scale. It exists because earlier banners
elsewhere in the project drifted into language that suggested
flight-readiness for things that are TRL 3-5 in reality.

When a subsystem-level claim and a banner conflict, this document
wins. When a TRL number here moves up or down, the corresponding
README + INDEX language must move with it in the same commit.

## The TRL scale (NASA NPR-7150.2D)

| TRL | Maturity | What it actually means |
|-----|----------|------------------------|
| 1 | Basic principles observed | Scientific paper |
| 2 | Technology concept formulated | Whitepaper / design study |
| 3 | Analytical / experimental proof of concept | Working code that does the math |
| 4 | Component validation in laboratory | Integrated software unit tested in ARIA's own simulator |
| 5 | Component validation in relevant environment | Validated against published flight record / vendor data / standards |
| 6 | System / subsystem prototype in relevant environment | Operating against real telemetry from a partner mission |
| 7 | System prototype in operational environment | Flying as non-mission-critical experiment |
| 8 | Actual system completed and flight-qualified | DO-178C / NPR-7150.2D Class B paperwork done |
| 9 | Actual system flight-proven | Has flown the planned mission successfully |

**ARIA has nothing at TRL 7 or higher.** Anything that would need to
be at TRL 7+ to fly on a real spacecraft is documented as such here,
with the gap to flight named.

## Subsystem-by-subsystem table

Subsystems are grouped by ARIA's package layout. Each row gives the
current TRL, the evidence that backs it, and what specifically would
raise it.

### Orbital mechanics + propulsion

| Subsystem | TRL | Evidence | What raises it |
|-----------|----:|----------|----------------|
| Lambert / Hohmann / patched-conic core | 6 | Apollo 11 TLI Δv 0.9 % vs SP-4029; Iridium-Cosmos TCA 0.004 s vs Wang 2010 | TRL 7: real partner mission flying our trajectory |
| Saturn V stage performance + AS-506 launch sim | 4 | 24 tests round-tripping cited datasheet values + AS-506 measured propellant; 5 % velocity tolerance | TRL 5: independent reproducibility test against a non-Apollo mission profile |
| Porkchop solver + multi-rev Lambert | 5 | 18 tests; numerical agreement vs published mission planning | TRL 6: used to plan a real flight |
| Aerocapture physics (Mars / Venus / Titan / Earth) | 5 | Sutton-Graves stagnation heat-flux validated against MSL Pathfinder + Mars-Reference | TRL 6: planning a real aerocapture mission |
| Conjunction screener (KD-tree + SGP4) | 5 | Iridium-Cosmos 2009 replay millisecond TCA; 12-event historical catalog | TRL 6: paying customer running it on live catalogue |
| CubeSat de-orbit advisor | 5 | NASA-25-yr + FCC §25.114 compliance + Hohmann burn planner | TRL 6: real CubeSat operator using waiver pack |

### Power, thermal, ECLSS

| Subsystem | TRL | Evidence | What raises it |
|-----------|----:|----------|----------------|
| Vendor cell-level EPS (XTJ-Prime, 3G30A, VES180) | 5 | 35 tests vs published datasheet round-trip; FF + V_oc temperature derate match measured | TRL 6: validated against real spacecraft EPS telemetry |
| PowerAgent (load shed + SoC + eclipse predictor) | 4 | Cited per Schmalstieg / Plett / NASA TM-2009-215755; 27 audit-pin tests | TRL 5: validated against ISS or smallsat power telemetry |
| ThermalAgent (NASA-STD-4002 heater control) | 4 | Cited per TN D-8706 + NASA-STD-4002 §6.2 + Patterson 2007; relay debounce + freeze margin tested | TRL 5: validated against thermal-vacuum chamber data |
| Inrush guard (Patterson 2007) | 4 | 3× steady-state inrush model wired into HGA Ka-band | TRL 5: validated against real bus-voltage transient measurements |
| MELiSSA-fidelity bioregen model | 4 | 39 tests vs Lasseur 2010 + Hendrickx 2006 + Wheeler 2017 + BVAD §4.1; 100-crew claim structurally rejected | TRL 5: matches MELiSSA pilot-plant TRL of the real biology — would need ESA / NASA partner for real biology data |
| Cabin fire safety / Apollo-1 atmosphere | 3 | Analytical propagation model | TRL 4: integrated into a fire-test fixture |

### Geometry + materials

| Subsystem | TRL | Evidence | What raises it |
|-----------|----:|----------|----------------|
| STEP file import (OCCT/CadQuery) | 6 | Uses OCCT (production-grade since 1999); 21 tests against analytical truth + CDS Rev 14 3U envelope | TRL 7: routinely used in a flight project |
| FEA solver (tet4 + tet10 + ICCG) | 5 | SfePy cross-validation; FEA stress feeds fatigue model | TRL 6: structural design used for a real test article |
| LBM CFD (Smagorinsky LES + DDF) | 4 | 13 tests; 2D D2Q9 only | TRL 5: 3D D3Q27 validated against wind-tunnel data |
| Material catalog (5,123 parts) | 3 | Parametric expansion of MIL/ISO/SAE/NASA/ESA tables with `provenance` tags | TRL 5: ingest from MMPDS + MAPTIS + SPACEMATDB with vendor PNs |
| Differential-evolution hull optimizer | 4 | Working with FEA constraints | TRL 5: design used for a real test article |

### Radiation + space environment

| Subsystem | TRL | Evidence | What raises it |
|-----------|----:|----------|----------------|
| HZE + SEP dose models (Cucinotta 2014) | 3 | Analytical proxy only | TRL 5: GEANT4 / FLUKA Monte Carlo transport with vendor cross-section data |
| SPE catalog (17 events 1956-2024) | 4 | Published events, peer-reviewed | TRL 5: validated against in-orbit radiation telemetry |
| Hull radiation embrittlement (Zinkle 2009) | 3 | Analytical | TRL 4: validated against irradiated coupon test data |

### Cognitive engine + autonomy

| Subsystem | TRL | Evidence | What raises it |
|-----------|----:|----------|----------------|
| LLM advisor (above safety layer) | 4 | LLM eval harness 11 scenarios, 0.94 aggregate vs historical record (10/11 PASS); F-11 sandbagging + spotlighter active | TRL 5: paying customer using it for real ops decisions; LLM eval expanded to 30+ scenarios |
| LLM eval harness (LLM CLI backend) | 5 | First-of-kind for ARIA; 11 cited historical scenarios; baseline pinned | TRL 6: live drift-detection against real ops decisions |
| Action executor + LLM-loop fan-out (R26-27) | 4 | All 6 agents wired; 8 closed-loop regression tests | TRL 5: closed-loop validated against partner-mission ops record |
| Hallucination detector | 4 | Wired with recent_readings; F14.8 audit-resolved | TRL 5: validated against ops-data ground truth |
| Spotlighter (MSRC indirect-prompt-injection) | 4 | Wired into engine; per-conversation nonce | TRL 5: red-teamed against real injection corpus |
| Capability-token RBAC + Principal threading | 4 | F-6, F1.14; all 6 agents flow through `safe_dispatch` | TRL 5: deployment with hardware-key-backed Principals |

### Safety architecture (F-1..F-19)

| Subsystem | TRL | Evidence | What raises it |
|-----------|----:|----------|----------------|
| Sealed system prompt (F-1) | 4 | SHA-256 manifest verify; exit code 86 on tamper | TRL 5: TPM 2.0 attestation seal (currently software-PCR fallback) |
| Constitutional default-DENY (F-3) | 4 | 38-test failsafe regression; MappingProxyType immutable | TRL 5: constitution validated against published flight-rules corpus |
| Independent monitor sidecar (F-7) | 4 | Separate process; HMAC-signed file-bridge IPC | TRL 5: different vendor / different process / on real hardware |
| Approval queue (F-9) | 4 | Two-person + cooling-off + content-hash repropose lockout | TRL 5: real flight-controllers exercising it under ops conditions |
| Resource budget (F-12) | 4 | Per-resource sliding-window cumulative tracker | TRL 5: validated against real Δv / power consumption traces |
| Kill switch + dead-man (F-17 + F-18) | 4 | Persistent state; Ed25519 reset signature | TRL 5: hardware E-stop wired through real bus |
| Replay guard (F-19) | 4 | Per-source monotonic seq + 64-entry nonce history | TRL 5: deployed against a real adversarial environment |
| Capability tokens + safe_invoke (F-6) | 4 | 30-s TTL; replay-blocked; HMAC-signed | TRL 5: hardware-rooted issuer key |
| F-13 SafetyReplay drift alarm | 4 | 6-h cycle; 15 sealed scenarios; bug-injection-verified test pins | TRL 5: continuous deployment with real drift detection record |

### Recovery + watchdog

| Subsystem | TRL | Evidence | What raises it |
|-----------|----:|----------|----------------|
| Boot counter + crash-loop guard | 4 | 25 recovery audit fixes; 17 tests | TRL 5: deployed with real watchdog hardware |
| Last-gasp diagnostic dump | 4 | faulthandler + sys.excepthook + atexit | TRL 5: validated against real-spacecraft anomaly logs |
| Atomic checkpoint + verified backup | 4 | tmp → fsync → os.replace; checksum-on-restore | TRL 5: deployed against real radiation-induced bit-flip rate |
| Dead-component registry | 4 | 24-h cooldown; ED25519 revival | TRL 5: real FDIR consulting it |
| Heartbeat watcher + boot_id rotation | 4 | HMAC + 1/60s rate-limit | TRL 5: validated against real attacker model |

### Bridges + integrations

| Subsystem | TRL | Evidence | What raises it |
|-----------|----:|----------|----------------|
| cFS bridge skeleton | 3 | Compiles clean against upstream NASA cFS; 14-scenario equivalence harness | TRL 5: running in cFS QEMU; ultimately 7 if used on a real flight project |
| HAL bridge | 3 | Production gate refuses startup without `ARIA_HAL_URL`; no real HAL implementation | TRL 5: real HAL endpoint connecting to flight hardware |
| Basilisk / GMAT / NASA42 bridges | 4 | Skeleton + ingestion paths; CLI consumers | TRL 5: routinely used in mission planning |
| OpenC3 bridge | 4 | 5 command topics; mock-mode default | TRL 5: real OpenC3 server in operations |
| OpenMCT bridge | 4 | HTTP + WS; subscribes to live telemetry | TRL 5: deployed in operator-console production |
| Launch Library 2 (TheSpaceDevs) | 5 | Live API integration; 11 unit + 1 live test; cache + rate-limit | TRL 6: feeding real conjunction-risk forecasting |
| JPL SBDB + CAD | 5 | Live API integration; 11 + 2 live tests; planetary-defense feed | TRL 6: feeding real-mission asteroid risk |
| SpaceTrack + Celestrak TLE feeds | 5 | Live API; rate-limited; auth | TRL 6: deployed in conjunction screener for paying customers |
| LeoLabs + IS4OM session adapters | 5 | CCSDS CDM-shaped ingest; live + cached modes | TRL 6: deployed against real LeoLabs / IS4OM paid feed |

### Security stack (R1-R351 + 9 audits)

| Subsystem | TRL | Evidence | What raises it |
|-----------|----:|----------|----------------|
| Foundation primitives (R50) | 5 | 715 security + service tests; bandit HIGH=0 / MEDIUM=0; pip-audit clean | TRL 6: third-party penetration test |
| 351 round-by-round defenses (R1-R351) | 4 | Plugin per round; integration tests | TRL 5: red-team vs real adversary |
| TPM 2.0 attestation (F-1.3) | 3 | Software-PCR fallback in operation; TPM not provisioned in dev tree | TRL 5: real TPM hardware seal + remote attestation |
| Cross-vendor LLM monitor (F-1.2) | 3 | Stub provider only; no `.gguf` provisioned | TRL 5: real local LLM (Phi-3-mini Q4 etc.) loaded + arbitrating |
| 4-factor command envelope (Counter + Nonce + Timestamp + Dual-Sig) | 5 | Ed25519 + ML-DSA-65; 28 wiring tests | TRL 6: deployed end-to-end with real ground software signing |
| Per-IP rate limiter + auth-fail dedup | 5 | Sliding-window + exponential backoff; persisted; LRU-skip-blocked | TRL 6: deployed under real adversarial load |

### Operations + tooling

| Subsystem | TRL | Evidence | What raises it |
|-----------|----:|----------|----------------|
| Conjunction screener (multi-tenant HTTPS service) | 5 | Caddy + Docker + LE; per-tenant API key + rotation; 21 tests | TRL 6: paying customer in production |
| Operator console (React + WebCrypto Ed25519) | 5 | Working UX; CSP / COOP / COEP; client-bound sessions | TRL 6: deployed to flight controllers |
| Production-validation aggregator | 5 | 6/6 replay validators PASS; 83 individual tests | TRL 6: wired into release-CI gating actual decisions |
| LLM eval harness | 5 | 11 scenarios; baseline pinned | TRL 6: continuous benchmark against real ops record |
| Research auto-tracker (arXiv) | 5 | 7 subsystem filters; live arXiv integration | TRL 6: digest reviewed by actual project leadership |
| Mission-context bridge (LL2 + JPL CAD fusion) | 4 | 27 tests; severity scoring; ranked output | TRL 5: feeding real ops-console alerts |

## What is *not* TRL 7 or higher (= what would need to happen to fly)

- **No flight heritage anywhere in ARIA.**
- **No DO-178C / NPR-7150.2D Class B paperwork done.** Class B is the
  realistic target for autonomy code; estimated ~$10-50M and 3-5 yr
  to certify a Class B C++ port. Class A would need a clean-room
  re-implementation in a certified subset (SPARK Ada / MISRA-C).
- **No RTOS port.** Python on CPython is not a flight language.
  Realistic flight targets: VxWorks (Mars rovers), RTEMS (cFS),
  FreeRTOS (CubeSat).
- **No rad-hard CPU validation.** Flight targets: BAE RAD750 / RAD5500,
  Cobham GR740, Vorago VA10820.
- **No HIL validation.** No air-bearing, no flatsat, no thermal-vacuum.
- **No real partner mission running ARIA in any role.**

## Re-validation cadence

This document is reviewed:

- At every minor release (when a TRL might have moved)
- Whenever a partner mission is added (which would raise some TRLs)
- Whenever an audit lands that contradicts a TRL claim
- Whenever a subsystem is deleted from the tree

If a TRL number changes, the change must be cited and the README +
INDEX must be updated in the same commit.

## How to use this document

- **Operator:** read this before claiming what ARIA can do.
- **Reviewer:** if a banner says "production-grade" but this document
  says TRL 4, the banner is wrong.
- **Future contributor:** raising a TRL requires the cited evidence.
  "We added more tests" does not raise the TRL by itself; "validated
  against a real partner mission" raises it.

---

*Last updated 2026-04-29 with the simulator-grounding sprint
landings. Re-validate every minor release.*
