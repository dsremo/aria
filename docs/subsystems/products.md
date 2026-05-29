# Product-line wrappers — narrowly-scoped application slices built on the ARIA core

ARIA ships two reference products under `src/aria/products/`: the **conjunction screener** and the **CubeSat de-orbit advisor**. Each product is a thin, mission-specific application that composes existing ARIA core subsystems (conjunction analysis, SGP4 propagation, atmospheric-drag simulation, Lambert solvers, uncertainty classification) into a focused operator-facing interface — a REST API or a CLI — without duplicating any physics or safety logic.

Both products are reference/demonstration slices on a research prototype rated TRL 3–5. Neither has flown. Neither is a commercially deployed service. The deployment posture described in this document is a ground-systems R&D staging stack, not a flight-qualified system.

---

## Where they sit in the architecture

```
   Operator (HTTP client / CLI)
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  src/aria/products/                                              │
│                                                                  │
│  conjunction_screener/          cubesat_deorbit/                 │
│  ─────────────────────          ─────────────────                │
│  aiohttp REST API               aiohttp REST API + CLI           │
│  tenant auth + rate-limit       tenant auth + rate-limit         │
│  ConjunctionScreenerService     advise_deorbit()                 │
└──────────┬──────────────────────────────┬───────────────────────┘
           │                              │
           ▼                              ▼
┌──────────────────────┐    ┌─────────────────────────────────────┐
│  aria.conjunction.*  │    │  aria.simulation.atmo_drag           │
│  tca_finder          │    │  aria.simulation.lambert_izzo        │
│  sgp4_propagator     │    │  aria.physics.uncertainty            │
│  probability.foster  │    └─────────────────────────────────────┘
└──────────────────────┘
```

Products sit above the shared ARIA core and below the operator. They own only the API surface, input validation, auth/rate-limit, and output rendering. All physics, conjunction maths, and uncertainty bookkeeping live in the core subsystems documented separately.

---

## The products

### conjunction-screener

**Source:** [`../../src/aria/products/conjunction_screener/`](../../src/aria/products/conjunction_screener/)

The conjunction screener wraps `aria.conjunction.*` behind a JSON HTTPS API that a smallsat operator can call without hosting their own astrodynamics stack. It is stateless with respect to orbital data: operators bring their own TLEs and, optionally, their own SpaceTrack credentials. ARIA never centrally stores 18 SDS catalog data.

**Endpoints (v1):**

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/screen` | Screen one primary TLE against up to 1,000 secondaries; returns TCA, miss distance, Foster Pc, and RED/YELLOW/GREEN risk classification per pair. |
| `POST` | `/v1/screen_bulk` | Same as `/v1/screen` but streams results as NDJSON so a large catalog does not block until the last pair is computed. |
| `GET` | `/v1/usage` | Per-tenant usage summary over a configurable lookback window (SQLite-backed store mode only). |
| `POST` | `/v1/rotate_key` | Zero-downtime API-key rotation with a 7-day grace window for the previous key. |
| `GET` | `/v1/healthz` | Liveness probe; returns `{"ok": true}` without version disclosure to unauthenticated callers. |
| `GET` | `/v1/version` | Semver and service identity; admin-token gated. |
| `POST` | `/v1/admin/tenants` | Create a tenant (admin-token gated). |
| `POST` | `/v1/admin/tenants/suspend` | Suspend or reinstate a tenant (admin-token gated). |
| `GET` | `/v1/admin/tenants` | List all tenants (admin-token gated). |

**Core subsystems used:**

- `aria.conjunction.data.tle_parser` — TLE parsing and object construction
- `aria.conjunction.conjunction.tca_finder` — coarse-step + bisection TCA search
- `aria.conjunction.propagation.sgp4_propagator` — SGP4 state propagation
- `aria.conjunction.probability.foster` — Foster Pc with 3×3 per-object covariance or operator-grade isotropic fallback (250 m σ default)

Risk thresholds follow the ARIA CARA-class convention: RED if Pc ≥ 10⁻⁴ or miss < 100 m; YELLOW if Pc ≥ 10⁻⁷ or miss < 1 km; GREEN otherwise.

**Auth and multi-tenancy:**

Tenant API keys are stored as HMAC-SHA-256 digests (keyed by a per-deployment server secret) in a SQLite store with WAL journalling and `synchronous=FULL`. The `TenantStore` class in [`tenants.py`](../../src/aria/products/conjunction_screener/tenants.py) handles key creation, rotation, grace-window expiry, suspension, and usage metering. A simpler JSON-file path is available for development and single-operator use.

The service is also compatible with a shared tenant store when the conjunction screener and the CubeSat advisor run on the same host.

For conjunction analysis concepts and the underlying maths, see [./conjunction.md](./conjunction.md).

---

### cubesat-deorbit

**Source:** [`../../src/aria/products/cubesat_deorbit/`](../../src/aria/products/cubesat_deorbit/)

The CubeSat de-orbit advisor answers the specific question every smallsat operator faces near end-of-life: what must be done, and when, to comply with the FCC 22-271 five-year post-mission disposal rule (effective 2024-09-29) and the NASA-STD-8719.14B 25-year rule. The product targets 6U-class CubeSats in 400–700 km LEO and accepts operator-friendly inputs (altitude, inclination, mass, drag coefficient, cross-section, propellant, Isp) rather than raw TLE bytes.

**Four possible decisions:**

| Decision | Meaning |
|----------|---------|
| `NATURAL_DECAY` | Atmospheric drag will deorbit the spacecraft within the applicable deadline; no propulsive burn needed. |
| `BURN_REQUIRED` | Natural decay exceeds the compliance deadline; a single-impulse retrograde burn is sized and feasible. |
| `BURN_OPTIONAL` | Natural decay covers FCC compliance; a burn would shorten the timeline. |
| `INFEASIBLE` | Natural decay is too slow and the available ΔV / propellant cannot close the gap; shortfalls are enumerated. |

**HTTP endpoints (v1):**

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/advise` | Full de-orbit recommendation as JSON. |
| `POST` | `/v1/advise/report` | Same recommendation rendered as a self-contained HTML page (PDF via `weasyprint` when available). |
| `POST` | `/v1/advise/waiver` | Recommendation plus a 7-section FCC §25.114 waiver-application skeleton (cites FCC 22-271, 47 CFR §1.3, NASA-STD-8719.14B) with operator-supply checklists. |
| `POST` | `/v1/advise/multi` | Multi-impulse burn plan (`two_impulse` Hohmann or `staged` drop for electric-propulsion missions with a per-burn ΔV ceiling). |
| `GET` | `/v1/healthz` | Liveness probe. |
| `GET` | `/v1/version` | Semver; admin-token gated. |

**Core subsystems used:**

- `aria.simulation.atmo_drag.orbit_lifetime` — King-Hele semi-analytic decay integrator against NRLMSISE-00 density (Picone et al. 2002)
- `aria.simulation.atmo_drag.get_density` — NRLMSISE-00 atmospheric density
- `aria.simulation.lambert_izzo` — burn ΔV via Izzo's Lambert solver for multi-impulse legs
- `aria.physics.uncertainty` — confidence-tier tagging (Tier A/B/C per `docs/UNCERTAINTY.md`)

The advisor's decay analysis carries Tier-B confidence (King-Hele introduces a factor-of-two uncertainty in Cd at low solar activity). The reentry-footprint estimate is a first-order Tier-B prediction (200 km × 30 km 3σ) appropriate for compliance planning; high-fidelity footprint predictions require a full break-up model and launch-tracked covariance.

**CLI:**

```
python -m aria.products.cubesat_deorbit \
    --altitude-km 550 --inclination-deg 51.6 --mass-kg 12.0 \
    --propellant-kg 0.5 --isp-s 220 --f107 150
```

The bare command runs the one-shot advisor. The `serve` sub-command starts the HTTP service on port 8444.

---

## The conjunction-screener reference deployment

**Source:** [`../../deploy/screener/`](../../deploy/screener/)

`deploy/screener/` is the reference stack for running the conjunction screener as a public-facing HTTPS service. It is a ground-systems R&D staging configuration — suitable for research use and operator pilots — not a flight-qualified system.

**Stack overview:**

```
Internet
   │  HTTPS :443
   ▼
Caddy 2 (alpine)
   │  TLS termination, HSTS, security headers, request-body cap (5 MB),
   │  30 s read/write timeout, token-header redaction in access logs,
   │  HTTP→HTTPS 308 redirect
   │  proxy to screener:8443
   ▼
aiohttp app (python:3.11-slim, non-root user aria:1001)
   │  read-only rootfs; writeable paths: /data volume + /tmp tmpfs (64 MB)
   │  seccomp allowlist (seccomp.json — default-deny, explicit syscall set)
   │  cap_drop ALL, no-new-privileges, pids_limit 256, mem_limit 512 MB
   │  SQLite tenant store at /data/screener_tenants.sqlite3
   ▼
screener_data volume (host-mounted, survives image upgrades)
```

**Key files:**

| File | Role |
|------|------|
| `Dockerfile` | Multi-stage build: builder installs `aiohttp`, `numpy`, `sgp4`, `scipy`, `pyerfa`, `astropy`, `tomli`; runtime image is `python:3.11-slim` running as `aria:1001`. |
| `docker-compose.yml` | Defines the `screener` + `caddy` services, five Docker secrets (admin token, master key, OAuth state key, HKDF salt, tenant-key HMAC), resource caps, and `ARIA_TRUSTED_PROXIES` for XFF validation. |
| `Caddyfile` | Auto-HTTPS via Let's Encrypt for `ARIA_SCREENER_DOMAIN`; emits HSTS, `X-Frame-Options: DENY`, `Content-Security-Policy`, `Cross-Origin-*` headers; redacts `X-ARIA-Token` and `X-ARIA-Admin-Token` from access logs. |
| `seccomp.json` | Explicit syscall allowlist (default action `SCMP_ACT_ERRNO`); the running process cannot invoke kernel interfaces outside this set. |
| `aria-screener.service` | Systemd unit for bare-metal deployments (no Docker): `ProtectSystem=strict`, `NoNewPrivileges=true`, `PrivateTmp=true`, `UMask=0077`, `IPAddressDeny=any` with RFC-1918 allow-list, `SystemCallFilter=@system-service`. |
| `Makefile` | `make secrets` — generates the five secret files at `secrets/` with `chmod 0600`; `make rotate-secrets` — rotates all five; `make pin-image` — writes a sha256-digest image pin to `.env.image`. |
| `load_test.py` | Async load generator for the screener REST API with p50/p95/p99 latency reporting and SLO baselines. |

**Secrets and key material:**

Five secrets are mounted as Docker secrets (files at `deploy/screener/secrets/`, all `chmod 0600`):

- `admin_token` — admin-endpoint bearer token (service-bound: HMAC-keyed to `aria-screener:v1`)
- `master_key` — ARIA master symmetric key
- `oauth_state` — OAuth state-signing key
- `hkdf_salt` — HKDF input salt for key derivation
- `tenant_key_hmac` — per-deployment HMAC key for tenant API keys at rest

The `ARIA_TRUSTED_PROXIES` env var controls which source IPs may supply a trusted `X-Forwarded-For` header. It defaults to `172.16.0.0/12,10.0.0.0/8,192.168.0.0/16` to match the Docker bridge range; tighten for a custom subnet.

**Image discipline:**

`docker-compose.yml` pins the screener image via `ARIA_SCREENER_IMAGE` (expected to be a sha256 digest tag, not `:latest`). `make pin-image` writes the digest to `.env.image`.

---

## Current limitations

- **No flight heritage.** Neither product has been used in a mission operations context. The conjunction screener and de-orbit advisor are reference slices on a TRL 3–5 research prototype.
- **No commercial deployment.** `deploy/screener/` is a staging reference, not a certified SaaS offering. Rate limits, SLOs, and tenant quotas are tunable defaults, not contracted service levels.
- **Physics confidence.** Decay lifetime uses the King-Hele semi-analytic integrator with NRLMSISE-00 density; this is Tier-B confidence. Conjunction probability uses the Foster Pc method; accuracy depends on the quality of the operator-supplied covariance. Neither substitutes for a qualified mission-operations astrodynamics tool.
- **Footprint stub.** The reentry-footprint estimate in the de-orbit advisor uses pessimistic fixed 3σ bounds (200 km × 30 km). A high-fidelity prediction requires a break-up model and launch-tracked position covariance — outside ARIA's current scope.
- **FCC waiver skeleton.** The `fcc_waiver.py` output is a technical starting point for FCC Form 312/442 narrative; it is not legal advice, and the operator (or their counsel) must supply mission-impact narrative, comparable precedents, and coordinate filings with 18 SDS, FAA/AST, and ITU.
- **Multi-tenant DB is v1.** The SQLite tenant store is adequate for low-traffic research pilots. A high-volume deployment would want a proper relational backend and an external secrets manager.
- **cFS bridge is a skeleton.** `cfs_bridge/aria_adv/` demonstrates the trust boundary but no end-to-end flight integration exists. See `../../README.md` → [cFS bridge](../../README.md#cfs-bridge).

---

## Where to start reading

**Conjunction screener:**

- [`../../src/aria/products/conjunction_screener/service.py`](../../src/aria/products/conjunction_screener/service.py) — `ConjunctionScreenerService`, `create_app`, rate-limiter, all HTTP handlers
- [`../../src/aria/products/conjunction_screener/tenants.py`](../../src/aria/products/conjunction_screener/tenants.py) — `TenantStore` (SQLite, HMAC-at-rest keys, usage metering)
- [`../../src/aria/products/conjunction_screener/__main__.py`](../../src/aria/products/conjunction_screener/__main__.py) — CLI entry (`python -m aria.products.conjunction_screener serve`)

**CubeSat de-orbit advisor:**

- [`../../src/aria/products/cubesat_deorbit/advisor.py`](../../src/aria/products/cubesat_deorbit/advisor.py) — `advise_deorbit`, `natural_decay_lifetime`, `plan_propulsive_deorbit`, `estimate_reentry_footprint`; all three decision regimes
- [`../../src/aria/products/cubesat_deorbit/burn_planner.py`](../../src/aria/products/cubesat_deorbit/burn_planner.py) — `plan_two_impulse_hohmann`, `plan_staged_drop`
- [`../../src/aria/products/cubesat_deorbit/fcc_waiver.py`](../../src/aria/products/cubesat_deorbit/fcc_waiver.py) — `build_waiver_application`, `FCCWaiverApplication`
- [`../../src/aria/products/cubesat_deorbit/report.py`](../../src/aria/products/cubesat_deorbit/report.py) — `render_html`, `render_report` (HTML + optional PDF)
- [`../../src/aria/products/cubesat_deorbit/service.py`](../../src/aria/products/cubesat_deorbit/service.py) — `create_app`, all HTTP handlers
- [`../../src/aria/products/cubesat_deorbit/__main__.py`](../../src/aria/products/cubesat_deorbit/__main__.py) — CLI entry (one-shot advisor or `serve`)

**Reference deployment:**

- [`../../deploy/screener/`](../../deploy/screener/) — Dockerfile, docker-compose.yml, Caddyfile, seccomp.json, aria-screener.service, Makefile, load_test.py

**Related subsystem docs:**

- [./conjunction.md](./conjunction.md) — TCA finder, SGP4 propagator, Foster Pc, TLE parser
- [./physics.md](./physics.md) — atmospheric drag, NRLMSISE-00, Lambert solvers
- [./security.md](./security.md) — guard library, `harden_aiohttp_app`, audit chain
