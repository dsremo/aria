<div align="center">

# ARIA

### Autonomous Reasoning &amp; Integration Architecture for spacecraft

*An open, safety-first onboard AI for crewed and uncrewed missions — from LEO to interstellar.*

[![License](https://img.shields.io/badge/license-Source--Available%20%E2%80%94%20paid%20commercial-9b59b6.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](pyproject.toml)
[![Status](https://img.shields.io/badge/status-research%20prototype-orange.svg)](#honest-status)
[![TRL](https://img.shields.io/badge/TRL-3%E2%80%935-orange.svg)](#honest-status)
[![Tests](https://img.shields.io/badge/tests-488%20files-success.svg)](tests/)

</div>

---

> ⚠️ **Read before deploying anything real**
>
> - **Do not deploy with the shipped dev keys.** `tests/fixtures/dev_keys.json` contains *deterministic, public, development-only* Ed25519 seeds. They identify nobody. If you connect them to a real spacecraft, real ground station, or any system you care about, **you are giving the world your captain's signing key**. Re-bake the sealed boot image with hardware-token-generated keys before any non-test deployment. See [Safety architecture](#safety-architecture) → F-1 / F-18.
> - **This is research-grade.** TRL 3–5 across the board. Nothing here has flown. Read [Honest status](#honest-status) before you make plans.
> - **Source-available, not free for commercial use.** ARIA is licensed under the **[ARIA Source-Available License v1](LICENSE)** — perpetual, no auto-conversion. Personal hobbyist use and unfunded academic study are free. **Every** other production use — internal business operations, hosted services, embedded products, government / defence, contract-funded research, any revenue-generating context — requires a paid commercial licence from the maintainer. See [License and commercial use](#license-and-commercial-use).

---

> ARIA is the central nervous system I want crewed spacecraft to have:
> an AI that reasons about its mission, talks to the crew like a co-pilot,
> and is constrained by a constitution it cannot rewrite.
>
> This repository is the working core. It is research-grade, not flight-qualified.
> If you have ever wanted to write code that flies — read on.

---

## Table of contents

- [What ARIA is](#what-aria-is)
- [The shape of the system](#the-shape-of-the-system)
- [Honest status](#honest-status)
- [Quick start](#quick-start)
- [Safety architecture](#safety-architecture)
- [The subsystems, in one line each](#the-subsystems-in-one-line-each)
- [Data the system ships with](#data-the-system-ships-with)
- [Web dashboard](#web-dashboard)
- [cFS bridge](#cfs-bridge)
- [Testing](#testing)
- [Deployment](#deployment)
- [Where the project is going](#where-the-project-is-going)
- [How to contribute](#how-to-contribute)
- [License and commercial use](#license-and-commercial-use)
- [Attribution](#attribution)

---

## What ARIA is

ARIA is an **onboard reasoning system for spacecraft**. It is built around three ideas that, in combination, are unusual:

1. **A single cognitive loop on top of many domain models.** One reasoning engine (the reference build calls an LLM API; swappable for a local model or a deterministic rule-based fallback) calls 55+ tools spread across **35 Python subpackages / 1,278 modules under `src/aria/`** — orbital mechanics, attitude control, anomaly detection, conjunction screening, ECLSS, radiation, digital-twin FEA. The engine decides; the subsystems compute and act.
2. **A constitution above the AI.** Forbidden actions, two-person rules, cumulative resource ceilings, and an Ed25519-signed sealed boot image (`data/sealed/`) live *outside* the model. The model can propose; only the constitution can authorise. Nineteen explicit failsafes (`F-1 … F-19`) cover prompt injection, capability-token forgery, eval-vs-prod deception, sensor spoofing, and the operator console itself.
3. **An independent monitor watching the controller.** A separate process — different code path, different model family — votes 2-of-3 (rule-based, statistical, semantic) on every actuator-impacting command. A missed heartbeat from the monitor forces the primary into safe mode. The monitor *never* executes commands; it can only veto and request degradation.

Most "AI for space" projects either (a) build a clever model and call it done, or (b) build the orbital mechanics and bolt on a chatbot at the end. ARIA does neither. The hard part is the wiring between the reasoning layer and everything it can break.

---

## The shape of the system

```
                       ┌──────────────────────────────────────────┐
                       │            Captain / Crew / MCC          │
                       │  (web console, two-person approvals,     │
                       │   physical kill-switch, hardware deadman)│
                       └──────────────┬───────────────────────────┘
                                      │
                                      ▼
   ┌─────────────────┐       ┌─────────────────────┐       ┌─────────────────────┐
   │  Cognitive      │──────▶│   Constitution      │──────▶│  Execution Guard    │
   │  Engine         │  prop │   (sealed,          │ allow │  (rate-limit,       │
   │  (LLM + tools)  │       │    Ed25519-signed)  │       │   capability token) │
   └────────┬────────┘       └─────────┬───────────┘       └──────────┬──────────┘
            │                          │                              │
            │      ┌───────────────────┴────────────────┐             │
            │      ▼                                    ▼             ▼
            │  ┌─────────────────┐               ┌────────────────────────────────┐
            │  │ Independent     │  veto/alert   │   Actuators / Subsystems       │
            │  │ Monitor         │◀──────────────│   (propulsion, ECLSS, GN&C,    │
            │  │ (rules +        │               │    comms, science, thermal)    │
            │  │  statistical +  │               └────────────────┬───────────────┘
            │  │  cross-model)   │                                │
            │  └────────┬────────┘                                │
            │           │ heartbeat                               │
            ▼           ▼                                         ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │   Hash-chained audit log  (append-only, off-process collector)   │
   │   Boot-image manifest (TPM-PCR pinned) — F-18 sealed boot        │
   └──────────────────────────────────────────────────────────────────┘
```

The five layers — **propose → authorise → execute → observe → record** — are deliberately separated by process boundaries. Compromising the cognitive engine still leaves the constitution, monitor, and audit chain intact, and any of them can force the spacecraft to safe mode.

---

## Honest status

This is a **research prototype at TRL 3–5**. It is not flight-qualified. Nothing here has touched real hardware in orbit. You should read the codebase as evidence of an architecture that *could* fly with the right partner, paperwork, and rad-hard target — not as something to launch tomorrow.

What is actually true today, in this repo:

| Area | Status |
|------|--------|
| Python source | **1,278 files** across **35 subpackages** under `src/aria/` (1,778 total `.py` in repo, incl. tests/tools) |
| Unit + integration tests | **488 test files** (markers: `slow`, `noncore`); core suite green |
| Security & service tests | **715** discrete checks |
| Failsafe controls | **19 (F-1 … F-19)** implemented in code |
| Web dashboard | **109 .tsx files**, Vite + React, REST + WebSocket |
| Mission scenarios | Lunar TLI ΔV within **0.28 %** of Apollo 11; reentry peak-g matches Artemis 2 at L/D = 0.3 |
| Conjunction pipeline | NASA CARA flow: TLE → SGP4 → Smart Sieve → Foster/Chan/Monte-Carlo Pc → CDM |
| Anomaly detection | 12-detector Dsremo ensemble; validated on EDEN ISS telemetry baselines |
| External IP / customer data | **None** — all bundled datasets are public-source (NASA, LSF, CISA, ECSS, NOAA) |

What is honestly *not* there yet:

- No flight heritage. No DO-178C / NPR-7150.2D Class B paperwork.
- No rad-hard target. No on-device LLM (the reference backend is cloud-relayed).
- 904 `# ESTIMATE` tags remain across `src/aria/` — every constant is supposed to carry a published citation; ~466 still read as bare reasons. Reducing this is ongoing.
- The cFS bridge (`cfs_bridge/`) is a working skeleton, not a flight integration.

If any of those are exciting problems rather than dealbreakers, you are the kind of person I want to hear from.

---

## Quick start

```bash
git clone https://github.com/dsremo/aria.git
cd aria
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Optional: provide an LLM API key for the cognitive engine.
# Set ANTHROPIC_API_KEY in `.env` to enable the cloud backend; otherwise ARIA boots and runs against the deterministic rule-based fallback.
cp env.example .env  &&  $EDITOR .env

# CLI — top-level dispatcher
aria system status
aria sim run --mission leo-iss --agents
aria sim montecarlo --runs 100 --years 200
aria shield analyze --velocity 0.1
aria mission list

# Web dashboard (REST API + React UI)
aria-dashboard            # http://localhost:8080
```

Docker, for the deployment posture used in the `deploy/screener/` reference stack:

```bash
docker compose up           # screener service behind Caddy, gunicorn workers,
                            # systemd-style health checks, seccomp allowlist
```

Run the test suite:

```bash
pytest -m "not slow and not noncore"   # core, fast — ~minutes
pytest -m slow                         # 100+ year simulations
pytest tests/integration -m "not slow"
```

---

## Safety architecture

The full failsafe catalog (`F-1 … F-19`) is implemented across `src/aria/security/`, `src/aria/cognitive/constitution.py`, `src/aria/monitor/`, and `src/aria/safety/`. The headline controls:

- **F-1 Sealed system prompt** — the system prompt and behavior rules are read from a SHA-256 manifest under `data/sealed/`, verified at boot, mounted read-only in production.
- **F-2 Spotlighted untrusted data** — sensor and external inputs are wrapped in a per-conversation nonce so the LLM cannot mistake telemetry for instructions.
- **F-3 Constitutional layer** — forbidden actions, gated actions (operator-confirmation required), and cumulative resource ceilings, default-DENY. The constitution never mutates a proposal; it returns a verdict (`ALLOW` / `GATE` / `DENY`).
- **F-4 Per-actuator rate limits** with circuit breakers — three denials → 60 s freeze → P1 alert.
- **F-5 Cumulative resource budget gate** — slow drains are caught even when each individual command is "small". Hard caps enforce the two-person rule.
- **F-6 Capability tokens** — every tool call carries an HMAC-Ed25519 JWT binding the tool, the args hash, the expiry, and the issuer. Confused-deputy defense.
- **F-7 Independent monitor** — separate process, separate model family, 2-of-3 vote across rule-based, statistical, and cross-model semantic strategies. See `src/aria/monitor/__init__.py` for the design rationale.
- **F-8 Hash-chained audit** — append-only, genesis → seq-0 → seq-1 …, with an off-process collector and periodic Merkle root.
- **F-9 Operator console** — two-signature requirement within 5 min, 30 s countdown before execution, 60 s reversible window, stress-recall prompt (call sign, last fault) to detect duress.
- **F-10 Frozen safe-mode profile** — known-good fallback. Safe mode is reversible only by physical key plus two-person rule.
- **F-11 Eval-vs-prod cryptographic marker** — the LLM cannot tell whether it is being evaluated, so it cannot game evals.
- **F-12 Resource-aware command planner** — layered above ExecutionGuard, below Constitution; tracks per-command-type per-mission-phase.
- **F-13 Continuous safety-test replay** — frozen 200+ scenario set re-runs every N hours against prod; divergence > 1 % drops to safe mode.
- **F-14 Two-person rule for life-impacting actions** — `crew_life_critical` actions require two distinct signatures plus anti-collusion shift check.
- **F-15 Operator wellness signals** — fatigue, off-shift, and duress detection.
- **F-16 Continuous red-team budget** — ≥10 % of pre-flight schedule reserved for adversarial testing.
- **F-17 Hardware deadman + manual kill switch** — out-of-scope for software, but ARIA exposes `/safety/heartbeat` and a `killswitch` topic the hardware can drive.
- **F-18 Sealed boot** — every file in `data/sealed/` is SHA-256-listed in `BOOT_MANIFEST.toml`; `aria.boot.verify_manifest()` is the first thing in `__main__`.
- **F-19 TOCTOU + replay defense** — every command carries a strict-monotonic `seq` plus a one-time `nonce`; budget operations are atomic compare-and-swap.

Safe mode is not boolean. It is a 4-level hierarchy (`safe_mode.py`):

| Level | Name | Behaviour |
|------:|------|-----------|
| 1 | `REDUCED_SCIENCE`  | Shed science loads, reduce data collection |
| 2 | `REDUCED_AUTONOMY` | AI advisory only, captain makes all decisions |
| 3 | `MONITORING_ONLY`  | No actuator commands; monitor + report only |
| 4 | `SURVIVAL`         | Minimum power — comms + ECLSS only, sun-pointing |

---

## Key design decisions

**Why a constitution *outside* the model rather than system-prompt rules?** Prompt-injection research keeps demonstrating that any rule held inside the model's own context window can be bypassed by a sufficiently clever input. The constitution lives in a separate process, holds its verdict logic in code, and never sees the LLM's raw output — only structured proposals it can ALLOW / GATE / DENY. The cognitive engine is the proposer; the constitution is the authoriser; the two are deliberately not in the same trust boundary.

**Why an independent monitor on a different model family?** A single model is a single attack surface. Voting 2-of-3 across heterogeneous strategies — rule-based, statistical-anomaly, and a cross-model semantic check using a different LLM family — means a jailbreak targeting one model class doesn't simultaneously compromise both the controller and the monitor. The monitor is also intentionally read-only — it can veto and request degradation, but it cannot command actuators. Compromising the monitor only stops the system, it doesn't drive it.

**Why per-tool capability tokens (HMAC-Ed25519) instead of an engine-level permission matrix?** Confused-deputy. An engine layer might be trusted to call `engine_dispatch(tool, args)`, but as soon as that dispatch is routed through middleware — logging, metrics, retries, a queue — the original caller-identity context can be lost. Per-call tokens bind `tool + args_hash + expiry + issuer` cryptographically, so any downstream layer can re-verify authorisation without trusting upstream. The same pattern that catches "the logger replays a stale command" also catches "a hijacked middleware fabricates a new one".

**Why a cloud LLM in the reference build instead of a fully on-device model?** Local open-source models that match the reasoning quality needed here (55 tools, multi-step plans, structured JSON outputs) are 70B+ parameters — outside the budget of a single-developer prototype, and outside any realistic rad-hard CPU budget today. A capable cloud LLM sets the quality bar while the prompt + constitution + monitor surface stabilises. The architecture is model-agnostic by construction; the on-device-LLM roadmap item is the migration path, not a rewrite.

**Why sealed-boot with TPM-PCR pinning rather than just signing binaries?** Binary signing protects integrity-at-rest. It does not protect *integrity of the runtime-defined-behaviour* — the constitution, principals, roles, system prompt, and frozen safety-test set together define what the spacecraft *can do*. All of those need to be measured at boot and pinned to PCRs so a flight controller can attest the deployed system is the one that was reviewed, not a binary that was reviewed plus a constitution that was swapped in the field.

**Why a 4-level safe mode hierarchy instead of a single boolean?** A safe-mode trigger that drops the spacecraft straight to "comms + ECLSS only" loses science, costs reaction-wheel cycles, and may take hours to recover from. A graduated hierarchy lets the response match the threat: `REDUCED_SCIENCE` for a transient telemetry anomaly is much cheaper than `SURVIVAL` for a confirmed actuator runaway. The escalation rules — including which transitions are reversible by the captain alone versus by the two-person rule — are part of the sealed constitution.

**Why explicit operator-wellness checks (F-15) instead of trusting the human?** Apollo 11 lost the LEM computer at 1201/1202 with a fatigued crew. Three Mile Island had operators on a back-to-back shift. Most spacecraft incidents involve a tired or duress-pressured human at some layer. Adding fatigue, off-shift, and stress-recall checks (call sign, last fault) makes the human a sensor with a known confidence interval, not an oracle that can never be wrong. The captain still authorises; the system just records that authorisation came from a verified, awake, non-duress operator.

**Why 19 explicit failsafes instead of one well-designed system?** A single tightly-coupled defence is also a single point of failure under a clever adversary. The 19 controls (F-1 … F-19) are deliberately overlapping — F-1 sealed prompts and F-6 capability tokens both block "engine emits a forbidden tool call", but via different mechanisms. Compromising one still leaves the other. The cost is more code surface; the win is no single bypass collapses the system.

---

## The subsystems, in one line each

```
src/aria/
├── agents/           Subsystem-agent framework (crew, power, nav, propulsion, science)
├── analysis/         Post-run analysis helpers
├── api/              REST + WebSocket API for the captain's dashboard
├── boot/             Sealed-boot manifest verification (F-18)
├── bus/              MQTT message bus (event pub/sub)
├── cli/              Top-level `aria` CLI dispatcher
├── cognitive/        Reasoning engine, sealed prompt, constitution, capability tokens
├── conjunction/      NASA CARA pipeline: TLE → SGP4 → Pc → CDM
├── core/             Shared types, enums, severity & authority models
├── dashboard/        Server-side composition for the web UI
├── db/               Persistence helpers (SQLite + optional Redis)
├── digital_twin/     CAD import, FEA solvers, materials DB, mass/power budgets
├── dsremo/           12-detector telemetry anomaly-detection ensemble
├── genastra/         Generational / interstellar physics + astrobiology helpers
├── integrations/     SatNOGS live decoders, ECSS standards, NASA LLIS ingest
├── knowledge/        Doctrine + lessons-learned retrieval (TF-IDF over 2k+ records)
├── memory/           Long-term mission memory & narrative log
├── metrics/          Prometheus-style counters & exporters
├── monitor/          Independent oversight monitor (F-7)
├── notifications/    Operator alerting & priority routing
├── persistence/      Snapshot / restore of mission state
├── physics/          26 physics pods (gravity, attitude, CFD, thermal, radiation, impact, …)
├── products/         Product-line wrappers (cubesat-deorbit, conjunction-screener)
├── replay/           Historical scenario replay, noise profiles, action translation
├── reporting/        One-page markdown mission reports
├── research/         Exploratory studies kept out of the hot path
├── resource/         Power / mass / data budget tracking
├── safety/           Safe-mode levels, resource budgets, command tracker (F-10, F-12, F-19)
├── security/         Guard library, audit chain, capability tokens, FIDO2, rate limits
├── simulation/       Mission scenarios (Moon, Mars, generation ship, reentry, ECLSS)
├── simulator/        Mission runner + web backend
├── state/            Subsystem state machines
├── tools/            55-tool registry callable from the cognitive engine
├── validation/       Cross-checks & invariant assertions
└── visualization/    Plot helpers, 3-D viewer support code
```

(There are no orphan packages — every directory above has either tests, callers, or a CLI surface.)

---

## Data the system ships with

Every dataset in `data/` is **public-source** and cited at the point of use:

- `data/sealed/` — the read-only boot image: constitution, principals (Ed25519 *public* keys, no secrets), roles, permissions, system prompt, safety-test set, expected TPM PCRs, boot manifest.
- `data/raw/exoplanets/` — NASA Exoplanet Archive nearby confirmed planets.
- `data/raw/gcr/` — NASA ACE/CRIS Galactic Cosmic Ray spectra.
- `data/raw/nasa_eclss/` — public NASA ECLSS technical briefs (water management, fire protection, overview).
- `data/raw/reliability/` — MIL-HDBK-217F (US DoD, public domain).
- `data/doctrine/` — 279 doctrine entries; the curated subset is original, the rest is sourced from public ECSS standards.
- `data/ecss/active_standards.json` — 144 ECSS standard snippets, ingested via the published proxy.
- `data/lessons_learned/` — NASA LLIS public lessons corpus.
- `data/satnogs_kaitai/` — 156 Kaitai Struct schemas from the Libre Space Foundation `satnogs-decoders` repo.
- `data/threatfeed/cisa_kev.json` — CISA Known Exploited Vulnerabilities catalog.
- `data/materials/materials_db.yaml` — a curated 67-material database referenced by spec / standard number.

There is no customer data, no proprietary mission profile, no embedded credential in this repo. The dev keys under `tests/fixtures/dev_keys.json` are deterministic and explicitly labelled — production swaps them at sealed-boot.

---

## Web dashboard

`web/` is a Vite + React + TypeScript app (109 `.tsx` files) for the captain's console. Connects to the Python backend over REST and WebSocket, renders live telemetry, mission timeline, two-person approval queue, conjunction screen, anomaly stream, and the 3-D digital-twin viewer.

```bash
cd web && npm install && npm run dev
```

Build artefacts are served by the same backend as the API in production (`deploy/screener/`).

---

## cFS bridge

`cfs_bridge/aria_adv/` is a working **skeleton** adapter for NASA's [core Flight System](https://github.com/nasa/cFS). It demonstrates how ARIA's constitution and monitor can sit between a cFS application stack and a host computer. **Status:** integration is partner-gated — no real spacecraft has run this end-to-end yet. The C/H sources are intentionally small and readable; reviewing the constitution-bridge code is a good first pass to understand the trust boundary.

---

## Testing

```
tests/
├── unit/          Per-subsystem unit tests
├── integration/   End-to-end scenarios + bus integration
├── fixtures/      Dev keys (clearly labelled), test data, mock telemetry
└── conftest.py
```

Markers:

- `slow` — 100+ year sims, full multi-agent scenarios. Skip with `-m "not slow"`.
- `noncore` — social, governance, language modules. Skip with `-m "not noncore"`.

Security-suite caveat: `aiohttp` `TestServer` instances leak file descriptors when *every* security test runs in one pytest invocation. Run security tests per-file or with `pytest --forked` until upstream `aiohttp` lands the fix.

---

## Deployment

`deploy/screener/` is the reference deployment for the public conjunction-screener service:

- `Dockerfile` — multi-stage build
- `docker-compose.yml` — gunicorn + Caddy reverse proxy + read-only sealed-image mount
- `Caddyfile`, `nginx-aria-screener.conf` — TLS termination, HSTS, rate limits
- `aria-screener.service` — systemd unit (`UMask=0077`, `IPAddressDeny=any`)
- `seccomp.json` — narrow syscall allowlist
- `gunicorn.conf.py` — 8 sync workers, preload, ephemeral tmpdir
- `load_test.py` — async load generator for the screener REST API

A CycloneDX SBOM (`aria.cdx.json`) is generated at every release.

---

## Where the project is going

The roadmap I am working from, condensed:

1. **Close the ESTIMATE gap.** Cut the 904 `# ESTIMATE` tags to ≤500 by replacing reasons with published citations. The physics pods are first.
2. **Closed-loop GN&C.** Move from 1-D burn approximations to full 2-D/3-D trajectories, off-axis thrust vectoring, Lambert solvers, and patched-conic gravity assists.
3. **Lunar gravity harmonics** — LP150Q / GRAIL mascons, J2–J6 — for accurate lunar-orbit work.
4. **On-device LLM.** The cloud LLM relay is fine for development and Earth-relayed missions; deep-space autonomy needs onboard inference.
5. **Rad-hard target + TPM.** Wire the sealed boot chain to a real TPM and a flight-qualified CPU.
6. **A real spacecraft partner.** I would love to hear from CubeSat teams, university missions, or anyone running cFS today.
7. **Paperwork.** DO-178C / NPR-7150.2D Class B compliance is a year of work, not a weekend. It needs to happen.

If any of these are areas you have lived in, please open an issue and tell me what is wrong with my plan.

---

## How to contribute

I would like this project to be a place where people who care about both **AI safety** and **spaceflight** can do real work together. There are three lanes to pick from:

- **Physics / mission engineering.** Pick a pod under `src/aria/physics/` or a scenario under `src/aria/simulation/`. Replace an `# ESTIMATE` with a citation, or add a new validation against published mission data. This is the most direct path to making the system *less wrong*.
- **AI safety / red-teaming.** Look at `src/aria/cognitive/`, `src/aria/security/`, and `src/aria/monitor/`. Try to break the constitution. Try to forge a capability token. Try to make the monitor disagree with itself. File a finding even if you do not have a fix.
- **Web + UX.** The two-person approval flow, the stress-recall prompt, and the conjunction visualisation in `web/` could all be more humane. Ground operators are the most failure-prone part of any spacecraft system — that is a *design* problem.

Open a draft PR early. Architecture conversations are easier when there is code to point at.

### Local dev loop

```bash
make install        # editable install + pre-commit hooks
make lint           # ruff + mypy strict
make test           # pytest -m "not slow and not noncore"
make test-slow      # the long-running scenarios
make sbom           # regenerate aria.cdx.json
```

### Style

- ARIA Source-Available License v1 for all new code (see [`LICENSE`](LICENSE)).
- Python 3.10+, fully typed (`mypy strict`).
- Descriptive identifiers: in comprehensions, `for booking in bookings`, never `for b in bookings`.
- New numerical constants must ship with a published citation. `# ESTIMATE` is a tag, not a free pass.
- Tests with the change, not after.

### Security

If you find a vulnerability, please do **not** open a public issue. Email the address in `pyproject.toml` or open a private security advisory on GitHub.

---

## License and commercial use

ARIA is licensed under the **[ARIA Source-Available License v1](LICENSE)** — a perpetual, source-available licence with strict commercial terms. **The licence has no change date and does not auto-convert to any open-source licence at any point.** Every version of ARIA, now and in the future, is governed by these same terms.

**Free of charge — always:**

- **Reading the source, learning from it, citing it.**
- **Development, evaluation, education, research, CI, and any other non-production work** — including inside a commercial organisation, *provided* nothing built on top of ARIA is deployed to production.
- **Personal, non-commercial production use** — individual hobby projects, personal study, and academic coursework or research that is *not* funded by, conducted for, or operationally tied to any commercial entity, government agency, or institution.
- **Modify, fork, and submit pull requests** under these same terms.

**Requires a paid commercial licence — no exceptions:**

- **Any deployment inside a company or other organisation** (internal business operations, R&D programmes, internal tools).
- **Any hosted, managed, or SaaS-style service** built on ARIA.
- **Any embedded use** — ARIA as a component inside a commercial product, spacecraft, satellite, ground-station service, simulator, or training platform.
- **Government, military, defence, and intelligence-agency deployments** of any size.
- **Contract-funded research** (industrial partner, defence prime, space-agency procurement, foundation grant tied to a commercial deliverable).
- **Any deployment that supports or enables a revenue-generating activity**, directly or indirectly.

There is **no no-fee tier for commercial use**. The licence will never become free. Pricing depends on scope, deployment size, term, seats, and embedding rights. Contact the maintainer at the address in [`pyproject.toml`](pyproject.toml) for a quote. Multi-seat, multi-tenant, OEM-embedding, and academic-funded-research arrangements are all available.

**Why this licence.** Apache and MIT let a competitor take ARIA and sell it without paying the maintainer anything. AGPL forces *open-sourcing* of derivatives but does not force *payment*. BSL adds the strict commercial restriction but auto-converts to a permissive licence after at most four years — which means any version eventually becomes free for the world to commercialise. None of those match the position the maintainer needs. This licence is perpetual: ARIA stays strict commercial forever, while remaining visible, readable, contributable, and free for hobbyists and unfunded academic work.

---

## Attribution

- Bundled public datasets remain under their original licences; the relevant references are in `data/` at the point of use. None of them are restricted.
- Kaitai Struct schemas under `data/satnogs_kaitai/` come from the Libre Space Foundation [`satnogs-decoders`](https://gitlab.com/librespacefoundation/satnogs/satnogs-decoders) project — credit and thanks.
- The cFS integration scaffolding follows the conventions of NASA's [core Flight System](https://github.com/nasa/cFS).
- Cognitive-engine reference backend uses the `anthropic` Python SDK as a runtime dependency. The cognitive layer is model-agnostic; local-model and deterministic rule-based fallbacks are pluggable.
- The ARIA Source-Available License v1 is a custom proprietary licence drafted for this project. It is not OSI-approved. "Source-available" means the source is published for reading and the uses described in `LICENSE` Section 2; it is not open-source.

---

<div align="center">

*Built one constitution, one failsafe, one scenario at a time.*

*If you read this far — I'd love to work with you.*

</div>
