# Supporting packages — connective tissue for the headline subsystems

The packages documented here are not in the critical path of any single
mission scenario, but every headline subsystem depends on at least one of
them. They handle the work that would otherwise be duplicated: exchanging
messages, storing state, routing alerts, exporting metrics, checking physics
invariants, and serving the web dashboard. Reading them alongside the
headline docs gives a complete picture of how ARIA holds together.

All packages live under `../../src/aria/` and are importable as
`aria.<package>`. Source-of-truth links in each section point to the
actual files on disk.

---

## Boot & the tool registry

### `boot/` — F-18 sealed-boot manifest verification

**Files:** [`verify.py`](../../src/aria/boot/verify.py),
[`generate_manifest.py`](../../src/aria/boot/generate_manifest.py),
`__init__.py`

`aria.boot.verify_boot_integrity()` is the first call in `__main__`. It
recomputes SHA-256 hashes of every `.py` file under five safety-critical
subtrees (`cognitive`, `safety`, `monitor`, `agents`, `security`) and
compares them against `data/sealed/BOOT_MANIFEST.toml`. A missing or
mismatched file causes `sys.exit(87)` — distinct from a sealed-prompt
failure (exit 86) so operators can tell the failure mode at a glance.

The manifest is generated at release time with
`python -m aria.boot.generate_manifest` and is intended to be Ed25519-signed
before being baked into the boot image. A second, smaller
`RESCUE_MANIFEST.toml` covers the minimal trusted computing base (beacon
path, safe-mode, kill-switch, ground deadman, monitor heartbeat). When the
primary manifest fails but the rescue manifest passes, `verify.py` touches
`data/runtime/boot.rescue` and returns `True`; the application reads that
marker and starts in beacon-only mode (Recovery audit R-19). In development
trees the manifest is typically absent and the check is a logged warning;
production deployments must set `skip_if_missing=False`. The `security/`
subtree was added to `PROTECTED_SUBTREES` under R-38.

### `tools/` — cognitive-engine tool registry

**Files:** [`registry.py`](../../src/aria/tools/registry.py),
[`physics_sandbox.py`](../../src/aria/tools/physics_sandbox.py),
`__init__.py`

`ToolRegistry` is the single dispatch surface the cognitive engine uses to
discover and invoke tools. Tools self-register on startup; the registry
enforces uniqueness, validates that each tool exposes a well-formed JSON
Schema via `input_schema()`, tracks per-tool health (degraded flag, circuit
breaker), and exposes `export_schemas()` for LLM context injection.

There are two invocation paths:

- `invoke(tool_name, params, authority)` — used by agents with their own
  authority level; calls `tool.safe_execute` directly.
- `safe_invoke(tool_name, params, authority)` — used by the cognitive engine
  for LLM-derived calls; refuses any invocation that lacks a valid
  `_capability_token` satisfying the F-6 capability-token protocol (tool
  name bound, arg dict hashed, nonce-unique, unexpired). The token is
  stripped before the downstream tool sees the params.

The concrete tool count verified on disk is **60** — 18 in
`integrations/control_tools.py`, 30 in `integrations/extended_tools.py`,
8 in the dsremo integration, 3 in the conjunction-watch integration, 2 in
the GenAstra integration, and 3 in `tools/physics_sandbox.py`. The README
figure "55-tool registry" is a lower bound; the live count is 60.

`physics_sandbox.py` exposes three read-only tools (`simulate_trajectory`,
`simulate_reentry`, `what_if_analysis`). Their `SafetyLevel.READ_ONLY`
flag means they simulate without executing — the same iterative "what if?"
reasoning human engineers used to discover skip reentry, available to the
cognitive engine without touching any actuator.

---

## The web/API/dashboard surface

### `api/` — REST + WebSocket server

**Files:** [`server.py`](../../src/aria/api/server.py),
[`command_envelope.py`](../../src/aria/api/command_envelope.py),
[`per_ip_rate_limiter.py`](../../src/aria/api/per_ip_rate_limiter.py),
`__init__.py`

`server.py` is a `websockets`-based HTTP + WebSocket server exposing seven
endpoints: five read-only REST routes (system status, agent list, alerts,
telemetry scores, metrics snapshot) plus a command POST and a real-time
event WebSocket. Commands require both a Bearer token (constant-time
comparison) and a signed `CommandEnvelope`.

`command_envelope.py` defines the four-header signing scheme (counter,
nonce, timestamp, HMAC-SHA-256 over `"counter|nonce|timestamp|body"`). Body
binding prevents payload-swap replays; a monotonic counter + nonce guard
tracked in `ReplayGuard` prevents sequence replays; clock skew is bounded
at ±30 s. These hardenings are labelled C-1 through C-4 and H-1/H-2 in the
TT&C audit. `per_ip_rate_limiter.py` enforces 30 commands/minute per source
IP so a single client cannot starve others. Authenticated commands are
published onto the bus with the verified envelope identity attached so
downstream consumers can reject unauthenticated messages.

### `dashboard/` — server-side health aggregation and OpenMCT bridge

**Files:** [`health_dashboard.py`](../../src/aria/dashboard/health_dashboard.py),
[`telemetry_server.py`](../../src/aria/dashboard/telemetry_server.py),
[`run_demo.py`](../../src/aria/dashboard/run_demo.py),
`__init__.py`

`health_dashboard.py` defines `HealthDashboard` and `DashboardSnapshot`.
A snapshot aggregates all nine agent statuses, subsystem telemetry (power,
thermal, ECLSS, navigation), the Dsremo anomaly scores, challenge states
(interstellar missions only), bus queue depth, and system uptime into a
single dataclass consumed by the API's status endpoint and by
`MissionReportGenerator`.

`telemetry_server.py` is a separate lightweight server for
[OpenMCT](https://github.com/nasa/openmct). It speaks the OpenMCT
real-time protocol: clients subscribe to dot-notation telemetry keys
(`aria.power.battery_soc`, etc.) over `/realtime` WebSocket; the server
also serves `/dictionary` (telemetry point metadata for auto-discovery),
`/history/<key>` (time-range query), and `/latest/<key>`.

`run_demo.py` wires these two servers together for local demo runs without
needing the full mission simulator.

### `visualization/` — terminal-safe plot helpers

**Files:** [`text_charts.py`](../../src/aria/visualization/text_charts.py),
`__init__.py`

`text_charts.py` provides `bar_chart`, `timeline_chart`, and related
helpers that render in plain ASCII/Unicode block characters. They work over
SSH, in CI log output, and piped to files with no GUI dependencies. The CLI
reporting commands use these when producing human-readable summaries without
a browser. A 3-D viewer integration hook is reserved in `__init__.py` for
future Three.js / Babylon.js bindings but is not yet populated.

---

## State, persistence & memory

### `state/` — agent state machines and shared scratchpad

**Files:** [`manager.py`](../../src/aria/state/manager.py),
[`scratchpad.py`](../../src/aria/state/scratchpad.py),
`__init__.py`

`StateManager` is a versioned key-value store that agents use as their
primary shared state surface. Each entry carries a version counter and a
`updated_by` tag; subscribers register `StateObserver` callbacks that fire
on every write. Three sensor-fusion audit hardenings apply: S-13 (per-namespace schema validators reject malformed values at write time), S-22
(writes go through `tmp + os.fsync + os.replace` so a power-loss mid-write
cannot corrupt the file), and S-23 (snapshots return deep-copied values so
callers cannot mutate the live store).

`Scratchpad` is a separate TTL-aware store for inter-agent observations that
outlive a single message but should not be persisted forever. A typical
pattern: `PowerAgent` posts `power.eclipse_state`; `ThermalAgent` reads it
to pre-heat before the eclipse. Entries expire after their `ttl_s` unless
overwritten.

### `persistence/` — completed-mission snapshot store

**Files:** [`mission_store.py`](../../src/aria/persistence/mission_store.py),
`__init__.py`

`MissionStore` wraps a SQLite database (`~/.aria/missions.db`,
auto-created) and provides save/load/list/query operations on
`MissionRecord` objects. A record captures the full numerical summary of a
completed run: orbit range, velocity range, eclipse count, anomaly count,
agent messages processed, and the outcomes of any interstellar challenges.
The store supports querying by ID, mission type, date range, and recency so
the CLI and analysis tools can retrieve prior runs for comparison.

### `db/` — core SQLite persistence with async wrappers

**Files:** [`persistence.py`](../../src/aria/db/persistence.py),
`__init__.py`

`PersistenceManager` opens SQLite in WAL journal mode with foreign keys on
and wraps the synchronous sqlite3 API in `asyncio.run_in_executor` calls.
Its schema holds `events`, `decisions`, `alerts`, and `state_snapshots`.
Unlike `persistence/mission_store.py` (completed mission summaries),
`db/persistence.py` stores live in-flight records — the detailed audit trail
of AI decisions, tool calls, and anomalies during a running mission.

### `memory/` — multi-tier long-term memory

**Files:** [`store.py`](../../src/aria/memory/store.py),
[`temporal_graph.py`](../../src/aria/memory/temporal_graph.py),
`__init__.py`

`MemoryStore` in `store.py` implements four tiers: working memory (recent
events ring buffer), episodic memory (past incidents by type/severity),
semantic memory (domain knowledge and procedures), and procedural memory
(calibration data and operator preferences). Relevance scoring is currently
keyword-based; the code notes this as a stub for embedding-based retrieval.

`TemporalGraph` in `temporal_graph.py` is a SQLite-backed directed knowledge
graph. Nodes are entities (subsystems, sensors, episodes, decisions, crew
actions); edges carry typed, time-stamped relationships (`CAUSED_BY`,
`RESOLVED_BY`, `CORRELATES_WITH`, `PRECEDES`, `SIMILAR_TO`, and others).
`valid_from`/`valid_to` columns capture relationships that changed during a
multi-year cruise, answering causal-chain queries a flat episode list cannot.

---

## Observability

### `metrics/` — Prometheus-style counters and audit trail

**Files:** [`collector.py`](../../src/aria/metrics/collector.py),
[`event_log.py`](../../src/aria/metrics/event_log.py),
`__init__.py`

`MetricsCollector` in `collector.py` tracks latency histograms (P50, P95,
P99), throughput counters, and resource gauges for tool calls, bus messages,
agent processing, and cognitive-engine reasoning turns. The registry injects
the shared `MetricsCollector` into each tool at registration time so
per-tool latency is tracked automatically. The `/api/v1/metrics` endpoint
serialises the collector's snapshot.

`EventLogger` in `event_log.py` is an in-memory ring buffer that also
publishes to the message bus. It covers nine structured event categories:
`ANOMALY`, `DECISION`, `FDIR`, `ALERT`, `STATE`, `AGENT`, `TOOL`,
`SECURITY`, and `REASONING`. Every event carries a `trace_id` for
cross-cutting correlation; the `SECURITY` category captures authentication
events and injection attempts specifically.

### `notifications/` — operator alerting

**Files:** [`alerter.py`](../../src/aria/notifications/alerter.py),
`__init__.py`

`AlertNotifier` dispatches `Alert` objects across a pluggable list of
channels: `ConsoleChannel` (stdout with severity colouring), `FileChannel`
(append-mode log), `WebhookChannel` (POST JSON to any URL — Slack, Discord,
custom), and `CallbackChannel` (in-process function, used in tests). Alerts
carry a four-level severity: `WATCH`, `WARNING`, `CRITICAL`, `EMERGENCY`.
The notifier is called directly by agents (not via the bus) so that a bus
failure does not silence a `CRITICAL` or `EMERGENCY` alert.

### `reporting/` — post-mission reports

**Files:** [`mission_report.py`](../../src/aria/reporting/mission_report.py),
`__init__.py`

`MissionReportGenerator` accepts a `MissionResults` object plus optional
`DashboardSnapshot` and interstellar challenge summaries and produces three
output formats: structured text (for the CLI), JSON (for machine
consumption), and HTML (for archival). It also computes a composite
`MissionScore` (0–100) broken into weighted sub-scores: mission completion,
alert health, system health, and anomaly-detection effectiveness. The score
is used in the parameter-sweep analysis and by the test suite as a
quantitative pass/fail signal.

### `analysis/` — post-run analysis helpers

**Files:** [`parameter_sweep.py`](../../src/aria/analysis/parameter_sweep.py),
`__init__.py`

`ParameterSweep` provides helpers that systematically vary one configuration
parameter while holding others constant and collect `SweepResult` objects
across runs. The current implementation focuses on the generation-ship
scenario (crew size, mission duration, breakthrough-config variants) and
calls `GenerationShipSimulation` directly. The results are formatted as a
table for visual comparison. This package is intentionally outside the hot
path; it is invoked from the CLI's `aria analyze` subcommand and by
exploratory notebooks.

---

## Validation, resource budgets & research

### `validation/` — cross-checks and invariant assertions

**Files (7):**
[`physics_validator.py`](../../src/aria/validation/physics_validator.py),
[`apollo_replay.py`](../../src/aria/validation/apollo_replay.py),
[`artemis2_replay.py`](../../src/aria/validation/artemis2_replay.py),
[`iridium_cosmos_replay.py`](../../src/aria/validation/iridium_cosmos_replay.py),
[`soyuz_rendezvous_replay.py`](../../src/aria/validation/soyuz_rendezvous_replay.py),
[`historical_conjunctions.py`](../../src/aria/validation/historical_conjunctions.py),
`__init__.py`

`physics_validator.py` checks a simulation timeline against physical laws
and engineering constraints across seven categories: energy conservation
(RTG Pu-238 decay curve, fuel energy density), mass conservation (no
creation in void), velocity constraints (0.1 c ceiling, magsail-only
deceleration), population feasibility, resource non-negativity, thermal
balance (radiator capacity vs waste heat), and shield-erosion monotonicity
(Hoang et al. model). Each check returns typed `Violation` objects with a
`ViolationSeverity` (`INFO`/`WARNING`/`ERROR`/`CRITICAL`) and the mission
year.

The four replay modules (`apollo_replay.py`, `artemis2_replay.py`,
`iridium_cosmos_replay.py`, `soyuz_rendezvous_replay.py`) each take a
known historical mission, run it through the relevant ARIA simulator, and
produce a divergence report comparing ARIA's numerical outputs against the
published reference values. These are honest cross-checks — agreement does
not claim ARIA would have flown those missions; it bounds the numerical
layer's accuracy. `historical_conjunctions.py` applies the same pattern to
catalogued close-approach events to exercise the conjunction pipeline.

### `resource/` — power, mass, and data budget tracking

**Files:** [`manager.py`](../../src/aria/resource/manager.py),
`__init__.py`

`ResourceInventory` tracks named material resources (propellant, water,
food, spares) as `Resource` objects carrying quantity in kg, daily
consumption rate, a critical-threshold alarm value, and an optional
recycling-efficiency factor. The `consume` / `produce` / `recycle` /
`days_remaining` API is called by the generation-ship and long-duration
mission simulators. The `safety` package's `ResourceBudget` (F-19) uses the
same schema; `resource/` supplies runtime tracking while `safety/` enforces
the hard budget limits.

### `research/` — arXiv digest and exploratory studies

**Files (5):** [`arxiv_client.py`](../../src/aria/research/arxiv_client.py),
[`digest.py`](../../src/aria/research/digest.py),
[`filters.py`](../../src/aria/research/filters.py),
`__init__.py`, `__main__.py`

`ArxivClient` in `arxiv_client.py` queries the arXiv Atom API with a
polite 3-second inter-call delay (per arXiv's User Manual), on-disk
caching (6-hour TTL), and configurable timeouts. `ResearchFilter` objects
in `filters.py` define per-subsystem query terms and relevance predicates.
`DigestBuilder` in `digest.py` polls each filter, applies it, and writes a
dated markdown digest to `data/runtime/research/digest_<YYYY-MM-DD>.md` for
walkable history. The `__main__` module makes the whole pipeline runnable
as `python -m aria.research` for a daily cron. The package is deliberately
isolated from the hot path; it does not affect mission-critical logic.

### `bus/` — priority-queued pub/sub message bus

**Files:** [`message_bus.py`](../../src/aria/bus/message_bus.py),
`__init__.py`

`MessageBus` is the single inter-agent communication fabric. All agents
communicate exclusively through the bus — no direct agent-to-agent calls.
Messages are immutable frozen dataclasses carrying a topic string
(`aria.telemetry.anomaly.detected`, etc.), a payload dict, a priority
(`P0_EMERGENCY` through `P3_ROUTINE`), source/target agent, a UUID message
ID, an ISO-8601 timestamp, and an optional `correlation_id` for linking
request/response pairs. The bus maintains per-priority `asyncio.PriorityQueue`
instances with delivery-latency targets: P0 < 50 µs, P1 < 1 ms, P2 < 5 ms,
P3 < 50 ms. Subscribers register async callbacks per topic (exact match or
prefix wildcard). `EventLogger` (`metrics/event_log.py`) subscribes to the
bus to populate the audit trail.

---

## Where to start reading

Suggested order to minimise backtracking:

1. **`bus/message_bus.py`** — every cross-package interaction flows through
   `Message` and `MessageBus`; understanding this first unlocks everything
   else.
2. **`boot/verify.py`** — the startup contract; `verify_boot_integrity` and
   `PROTECTED_SUBTREES` explain which subtrees are hash-checked and what the
   three exit-code failure modes look like.
3. **`tools/registry.py`** — `ToolRegistry.safe_invoke` is the F-6
   capability-token gate between the LLM and every actuator.
4. **`state/manager.py`** — the shared state surface agents read and write;
   observer callbacks and the S-22 atomic-write pattern are the main things
   to understand.
5. **`metrics/event_log.py`** — scan the nine `EventCategory` values for a
   quick map of what ARIA logs permanently.
6. **`validation/physics_validator.py`** — the seven invariant categories
   summarise the physical constraints the simulation layer must honour.

Headline subsystem docs in this directory: [`cognitive.md`](./cognitive.md),
[`safety-and-monitor.md`](./safety-and-monitor.md),
[`anomaly-detection.md`](./anomaly-detection.md),
[`digital-twin.md`](./digital-twin.md), [`physics.md`](./physics.md),
[`security.md`](./security.md). Top-level overview: [`../../README.md`](../../README.md).
