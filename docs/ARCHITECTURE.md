# ARIA — Architecture (1-page)

A single-page system-level summary.  Read this first; then dive into
`INDEX.md` for the per-module map and `README.md` for sprint history.

## What ARIA is

A research-grade Python codebase that combines:

* an **orbital-mechanics simulator** (SGP4, Lambert-Izzo, J4, drag,
  TLI, lunar descent / ascent, return);
* a **digital-twin / mission-design layer** (CadQuery → Gmsh → FEA →
  thermal → glTF → optimiser);
* an **LLM-advised cognitive layer** (LLM tool-use loop, sealed
  constitution, two-person approval queue);
* a **failsafe architecture** (19 named controls F-1..F-19: tamper-
  evident audit, cross-vendor monitor, TPM 2.0 + software-PCR
  attestation, FIDO2-per-action, continuous integrity monitoring);
* two **shippable products** (Conjunction Screener-as-a-Service,
  CubeSat End-of-Life Advisor);
* and a **cFS bridge** that compiles + loads under upstream NASA cFS.

## Layered view

```
                ┌──────────────────────────────────────────────┐
                │  Operators / Customers / Reviewers           │
                └────────┬───────────────────────┬─────────────┘
                         │                       │
                  HTTPS  │                       │  CLI
                         │                       │
       ┌─────────────────▼─────────────────┐ ┌───▼──────────────┐
       │ Conjunction Screener (aiohttp)    │ │  CubeSat Advisor │
       │  /v1/screen, /v1/screen_bulk,     │ │  /v1/advise,     │
       │  /v1/usage, /v1/rotate_key,       │ │  /v1/advise/*    │
       │  /v1/admin/*                      │ │                  │
       └─────────────────┬─────────────────┘ └───┬──────────────┘
                         │                       │
                         ▼                       ▼
          ┌──────────────────────────────────────────────┐
          │           aria.products.* (HTTP shells)       │
          └──┬─────────────┬─────────────┬───────────────┘
             │             │             │
             ▼             ▼             ▼
   ┌───────────────┐ ┌────────────┐ ┌──────────────────────┐
   │ Conjunction   │ │ CubeSat    │ │ Validation gates      │
   │ pipeline      │ │ Deorbit    │ │ Apollo / Iridium /    │
   │ TLE→TCA→Pc    │ │ Advisor    │ │ Artemis-2 / Soyuz /   │
   │               │ │            │ │ Historical (12 evt)   │
   └──────┬────────┘ └──────┬─────┘ └──────┬────────────────┘
          │                 │              │
          ▼                 ▼              ▼
       ┌──────────────────────────────────────────────────┐
       │  aria.simulation.* + aria.physics.* + …           │
       │  SGP4 · Lambert · J4 · drag · TLI · lunar         │
       │  descent / ascent · porkchop · porkchop_dsm       │
       │  Apollo / Artemis / Soyuz Δv reference data       │
       └──────────────────────────────────────────────────┘

       ┌──────────────────────────────────────────────────┐
       │  aria.security.* + aria.safety.* + aria.monitor.* │
       │  F-1..F-19 failsafe controls                       │
       │   - sealed constitution + audit chain              │
       │   - cross-vendor LLM monitor                       │
       │   - TPM 2.0 + software-PCR attestation             │
       │   - FIDO2-per-action                               │
       │   - continuous integrity monitoring                │
       └──────────────────────────────────────────────────┘

       ┌──────────────────────────────────────────────────┐
       │  cFS bridge (cfs_bridge/aria_adv/)                 │
       │  C port of constitution + audit + safe-mode;       │
       │  compiles + loads under upstream nasa/cFS;         │
       │  14-scenario equivalence harness vs Python ref.    │
       └──────────────────────────────────────────────────┘
```

## Data flow — example: an operator screens a pair

```
operator's TLE upload
       │
       ▼
[POST /v1/screen, X-ARIA-Token]
       │
       ▼
TenantStore.find_by_key (constant-time, grace-window aware)
       │
       ▼
RateLimiter.check (per-min + per-day windows)
       │
       ▼
ConjunctionScreenerService.screen
       ├── TLEParser.parse_tle      (aria.conjunction.data.tle_parser)
       ├── TCAFinder.find_tca       (aria.conjunction.conjunction.tca_finder)
       ├── SGP4Propagator.propagate (aria.conjunction.propagation.sgp4_propagator)
       ├── encounter-plane covariance  (operator-grade σ
       │                                or LeoLabs / IS4OM if available)
       └── foster_pc                (aria.conjunction.probability.foster)
       │
       ▼
risk classification {RED, YELLOW, GREEN}
       │
       ▼
TenantStore.record_usage (n_pairs + elapsed_ms)
       │
       ▼
JSON response
```

## Key trust boundaries

1. **Operator → service**: HTTPS via Caddy / nginx; per-tenant API key
   in `X-ARIA-Token`; constant-time HMAC compare; rate-limited;
   admin endpoints behind a separate `X-ARIA-Admin-Token`.

2. **Service → ARIA core**: pure-functional; the screener and advisor
   are *thin* HTTP shells around modules that have no global state
   beyond the SQLite tenant store.

3. **ARIA core → cFS bridge**: code crosses language boundary
   (Python → C) via a 14-scenario equivalence harness; the C port is
   never trusted blindly — every scenario must produce the same
   verdict in both implementations.

4. **Constitution**: sealed table at boot; runtime mutation requires
   re-signing.  Python and C ports share the *same* sealed JSON.

5. **Audit**: hash-chained; an hourly Merkle root is downlinked +
   verified by an independent ground-attestation checker.

## What is *not* in scope

* **Flight-software certification** — DO-178C / NPR-7150.2D Class B is
  partner-funded work tracked in `docs/REMAINING_WORK.md` Tier 3 §3.3.
* **Hardware-rooted attestation** — TPM 2.0 + software-PCR fallback
  exists; *real* TPM hardware needs a flight CPU board.
* **Real local LLM** — `aria.monitor.cross_check` ships with a stub
  provider; provisioning Phi-3-mini is Tier 3 §3.1.
* **Stripe billing** — multi-tenant SQLite store exists; payments flow
  is Tier 2 §2.4.

## Sprint cadence (high-level)

* R29 (2026-04-25): threat model + failsafe architecture (38 tests)
* R38–R42: anti-tamper + physics breadth + governance scaffolding
* R43: honest-framing pass; provenance tagging
* R44: Apollo + Iridium-Cosmos replay validators
* R45: first products + cFS bridge skeleton
* R46: SpaceTrack integration + screener service + paper draft
* R47: productionisation + Artemis II replay + cFS clean compile
* R48: panel-prioritised closures (cFS HK telemetry, LeoLabs, IS4OM,
  DSM porkchop, Soyuz replay, CI, CoC, pre-commit)

For the per-file inventory see `INDEX.md`.  For the full remaining
work tracker see `docs/REMAINING_WORK.md`.
