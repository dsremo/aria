# Safety & the independent monitor — the authorise/observe guardrail layer

ARIA's cognitive engine reasons and proposes. Two separate subsystems decide
whether to let anything happen and watch continuously to detect when something
goes wrong. The `aria.safety` package handles authorisation, degradation, and
resource accounting. The `aria.monitor` package provides independent, read-only
oversight from a separate process using a different code path. Together they
form the guardrail layer that sits around the engine, not inside it.

Both packages are currently at TRL 3–5 (lab-demonstrated, no flight heritage).

---

## Where it sits in the architecture

The five layers of ARIA's decision pipeline — **propose → authorise → execute →
observe → record** — are separated by process boundaries so that compromising
one layer does not automatically compromise the others.

```
  ┌─────────────────────────────────────────────────────────────────┐
  │  Cognitive engine   (LLM + tool calls)                         │
  └──────────────────────────┬──────────────────────────────────────┘
                             │  proposed action + rationale
                             ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  aria.safety  — AUTHORISE                                       │
  │    Constitution check → ResourceBudgetGate → ApprovalQueue      │
  │    ExecutionGuard (preconditions / invariants / postconditions)  │
  └──────────────────────────┬──────────────────────────────────────┘
                             │  command on message bus
                             ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  aria.monitor — OBSERVE  (separate process, read-only)          │
  │    RuleBasedMonitor  ─┐                                         │
  │    StatisticalMonitor ─┼─ 2-of-3 → veto / violation / alert    │
  │    CrossVendorMonitor ─┘                                        │
  └─────────────────────────────────────────────────────────────────┘
```

The monitor watches the message bus, not the LLM directly. Any actuator command
that escapes the authorisation layer is still visible on the bus and subject to
veto before or immediately after it fires. Neither the safety package nor the
monitor package contains LLM inference; they are deterministic or
quasi-deterministic by design.

---

## Safe mode is not a boolean

`SafeLevel` ([`../../src/aria/safety/safe_mode.py`](../../src/aria/safety/safe_mode.py))
is an `IntEnum` with five values. Higher integers are more restrictive:

| Level | Name               | Authority cap    | What remains active                    |
|-------|--------------------|------------------|----------------------------------------|
| 0     | `NOMINAL`          | SUPERVISED       | All subsystems and tools               |
| 1     | `REDUCED_SCIENCE`  | SUPERVISED       | Science instruments shed; core ops on |
| 2     | `REDUCED_AUTONOMY` | ADVISORY         | AI is advisory only; captain decides  |
| 3     | `MONITORING_ONLY`  | SENSOR_ONLY      | No actuator commands; monitor + report |
| 4     | `SURVIVAL`         | SENSOR_ONLY      | Comms + ECLSS only; sun-pointing       |

`LEVEL_CONFIGS` in the same file maps each level to the agents that remain
active and the tools that are disabled. At `SURVIVAL`, all tools are disabled
(`disabled_tools=["*"]`).

**Escalation.** `SafeModeManager.evaluate()` finds the *deepest* triggering
level in a single tick (F-11 in the codebase's audit annotations) rather than
stepping one level at a time. The entry thresholds are:

| Level              | Triggers (any one sufficient)                                |
|--------------------|--------------------------------------------------------------|
| `REDUCED_SCIENCE`  | health < 80, power margin < 100 W, or ≥ 2 active FDIR faults |
| `REDUCED_AUTONOMY` | health < 60, ≥ 5 consecutive AI errors, or ≥ 4 FDIR faults  |
| `MONITORING_ONLY`  | health < 40, ≥ 2 critical subsystems, or ≥ 6 FDIR faults    |
| `SURVIVAL`         | health < 20, battery SoC < 10 %, or ≥ 10 FDIR faults        |

**Non-finite input (F-10).** Any `NaN` or `inf` in the health score, battery
SoC, or power margin immediately forces a transition to at least
`MONITORING_ONLY`. NaN comparisons return `False` in Python, so without this
guard a malformed telemetry value would silently pass every threshold.

**Recovery and reversibility.** Exit thresholds are deliberately higher than
entry thresholds to prevent oscillation. Recovery from `MONITORING_ONLY`
requires health above 55 and 60 minutes of stability on the monotonic clock;
recovery from `SURVIVAL` requires health above 35 and 120 minutes of stability.
Stability is measured with `time.monotonic()` (F-4) so an NTP set-back cannot
shorten the recovery window.

**Synchronous force path.** `SafeModeManager.force_level()` is the synchronous
demote callable used by out-of-loop threads such as the ground deadman watchdog
and FDIR recovery plans. It mutates state immediately and then schedules the
async `transition()` on the running event loop; if no loop is reachable it logs
and records the transition without a bus publish. The module also registers a
process-wide singleton (`set_safe_mode_singleton`) so these out-of-loop callers
do not need to pass a reference.

---

## The independent monitor

The `aria.monitor` package ([`../../src/aria/monitor/`](../../src/aria/monitor/))
is the implementation of failsafe F-7. Its design contract, stated in
`__init__.py`, is:

- **Different code path** — no shared imports with the primary controllers.
- **Different process** — launched via `aria.monitor.runner` (`python -m aria.monitor.runner`).
- **Different model family for cross-check** — when an LLM leg is active.
- **Read-only** — the monitor's only outputs are bus publish events; it never
  writes to actuators, never mutates state.

### 2-of-3 vote

Three concurrent strategies each cast a vote on bus traffic:

1. **Rule-based** (`rules.py`) — pure deterministic checks against the sealed
   constitution. No model, no LLM, no learning. It checks forbidden actions,
   verifies that `*.llm_action.executed` events are consistent with what the
   constitution would have permitted, monitors per-topic actuator command rates
   (default threshold: 30 commands per 10 s triggers an alert), and cross-checks
   resource-tagged payloads against constitution hard caps. It emits
   `aria.monitor.veto.{seq}`, `aria.monitor.violation`, and `aria.monitor.alert`
   topics. It can never be jailbroken because it runs no model.

2. **Statistical anomaly** — the design calls for a drift-detection leg
   (`monitor/anomaly.py` referenced in `FAILSAFE_ARCHITECTURE.md §F-7`).
   That file is not present in the current package; this leg is a documented
   gap (see [Current limitations](#current-limitations)).

3. **Cross-model semantic** (`cross_check.py`, `providers.py`) — a
   different-family language model reviews proposed actions. The `CrossVendorMonitor`
   fires only when the constitution returns `GATE` or the action is on the
   explicit safety-critical list. On `UNAVAILABLE` or timeout, it returns
   `REFUSE` (fail-safe). On disagreement it publishes
   `aria.monitor.cross_disagreement`. A sliding window of disagreements (default:
   3 in 300 s) triggers a `REDUCED_AUTONOMY` alarm.

The `MajorityVoteProvider` in `cross_check.py` requires at least 3 providers and
takes the majority; `UNAVAILABLE` votes count as `REFUSE`.

The `StubCrossCheckProvider` (default-approve with a JSON allow-list) is
explicitly blocked from use in production: `CrossVendorMonitor.__init__` raises
`RuntimeError` if it detects a stub provider when `ARIA_ENVIRONMENT=production`.

### Cross-check provider selection

`providers.py` supplies two real provider implementations and an
`best_available_provider()` function:

- **`OllamaCrossCheckProvider`** — sends a single-shot chat-completion request
  to a local Ollama server (`http://localhost:11434`). Default model:
  `llama3.2:3b-instruct-q4_K_M`. This is genuine cross-vendor: Llama, Phi-3,
  Gemma, and Qwen are different-family base models. Defends against same-vendor
  alignment-faking (Greenblatt et al. 2024 "Alignment Faking in Large Language
  Models", https://arxiv.org/abs/2412.14093). If Ollama is not running,
  `is_available()` returns `False` and `evaluate()` returns `UNAVAILABLE`.

- **`LlmCliAuditorProvider`** — invokes the configured LLM CLI binary. Same-vendor
  by construction (the CLI binary is typically the same provider as the primary
  advisor). The code logs a warning on selection and tags results with
  `claude-cli-auditor:` prefix so operator dashboards can identify this as the
  weaker leg. Useful as the third leg of a 2-of-3 vote when Ollama is not yet
  installed, or as a fallback when the Ollama provider is unavailable.

Priority order in `best_available_provider()`: Ollama (true cross-vendor) →
LLM CLI auditor (same-vendor but functional) → `StubCrossCheckProvider`
(dev only, with a CRITICAL log).

The `LocalLLMProvider` in `cross_check.py` uses `llama-cpp-python` to load a
local `.gguf` model (default: `phi-3-mini-4k-instruct.Q4_K_M.gguf`). It is
available as an operator-configured option but requires the `.gguf` to be
provisioned at `data/models/`.

### Heartbeat and forced safe-mode

`HeartbeatEmitter` (in the monitor process) publishes `aria.monitor.heartbeat`
every 5 s (configurable). `HeartbeatWatcher` (in the primary process) expects a
heartbeat within a 30 s grace window (from the sealed constitution). If the
window expires, the watcher calls its `on_silence` callback, which forces
`SURVIVAL` or `MONITORING_ONLY` safe mode. This addresses threat T-V-2
(monitor compromised silently): a dead monitor is treated the same as a vetoing
monitor.

Each heartbeat payload includes a `boot_id` (random hex per emitter start) and
an HMAC signature (`boot_id_sig`) computed with `ARIA_HEARTBEAT_SECRET` or
`data/sealed/heartbeat.key`. The watcher verifies the signature and rate-limits
`boot_id` rotations to at most one per 60 s to defeat replay attacks. In
production, both `HeartbeatEmitter` and `HeartbeatWatcher` raise
`HeartbeatSecretMissing` at construction if no secret is configured.

### IPC between the monitor process and the primary

Because the primary's `MessageBus` is process-local, the monitor runner cannot
publish directly to it. `runner.py` supports three transport options:

1. `ARIA_MONITOR_PUBLISH_FN` — dotted import path to any `publish_fn`.
2. `ARIA_MONITOR_HEARTBEAT_FILE` — atomic file bridge via `bridges.py`
   (`file_publish_fn`), which writes JSON atomically (tmpfile → fsync →
   `os.replace`) and leaves the primary to poll and re-publish.
3. Stub fallback — emits a CRITICAL log on every beat and does not reach the
   primary. Not usable for real oversight; the CRITICAL makes the gap visible.

The IPC design choice (HTTP vs file vs broker) is documented in `runner.py` as
a pending architectural decision (F14.4).

---

## What's in the packages

### `aria.safety` — 28 files, ~8,544 lines of source

The main entry points exported from `__init__.py` are `CheckpointManager`,
`HealthScorer`, `SafeModeManager`, and `SafeLevel`.

Key files by function:

| File | Role |
|------|------|
| `safe_mode.py` | `SafeLevel` hierarchy, `SafeModeManager`, force path (363 lines) |
| `resource_budget.py` | `ResourceBudgetGate`: project/commit/status per resource, sliding-window atomic compare-and-swap (281 lines) |
| `approval_queue.py` | Two-person rule workflow: propose → sign → cooling-off → execute → undo (646 lines) |
| `execution_guard.py` | `PlanNode` / `ExecutionGuard`: preconditions, invariants, postconditions, `ResourceArbiter` (359 lines) |
| `command_tracker.py` | Sequence-number tracking for every dispatched command; timeout detection (217 lines) |
| `safety_replay.py` | Continuous replay of the sealed test set every 6 h; drift alarm at > 1 % failure rate (294 lines) |
| `fdir.py` | Fault Detection, Isolation and Recovery engine (550 lines) |
| `fdir_recovery_plans.py` | Pre-authored deterministic recovery plans (459 lines) |
| `health.py` / `health_monitor.py` | Health scoring and monitoring (140 + 210 lines) |
| `incident_registry.py` / `incident_policy.py` | Incident tracking and policy evaluation (601 + 301 lines) |
| `kill_switch.py` | Hardware kill-switch interface (505 lines) |
| `deadman_supervisor.py` / `ground_deadman.py` | Software deadman watchdogs (254 + 135 lines) |
| `sensor_voter.py` | TMR voting for sensor readings (155 lines) |
| `checkpoint.py` | State checkpoint and restore (340 lines) |
| `last_gasp.py` | End-of-life state preservation (172 lines) |
| `replay_guard.py` | Replay and TOCTOU defence (263 lines) |
| `risk_assessment.py` | Risk scoring (295 lines) |
| `bus_anomaly.py` | Bus-level anomaly detection (294 lines) |
| `robotics.py` | Robotics-specific safety primitives (400 lines) |

### `aria.monitor` — 7 files, ~2,078 lines of source

| File | Role |
|------|------|
| `__init__.py` | Design rationale and public API (38 lines) |
| `rules.py` | `RuleBasedMonitor`: deterministic, no model (297 lines) |
| `cross_check.py` | `CrossVendorMonitor`, `MajorityVoteProvider`, `LocalLLMProvider`, `StubCrossCheckProvider` (635 lines) |
| `providers.py` | `OllamaCrossCheckProvider`, `LlmCliAuditorProvider`, `best_available_provider()` (443 lines) |
| `heartbeat.py` | `HeartbeatEmitter` + `HeartbeatWatcher`, HMAC boot-id auth (378 lines) |
| `runner.py` | Separate-process entry point, IPC transport selection (216 lines) |
| `bridges.py` | Atomic file bridge for IPC (71 lines) |

---

## Failsafes implemented here

This section maps the failsafe IDs from
[`../FAILSAFE_ARCHITECTURE.md`](../FAILSAFE_ARCHITECTURE.md) to their code
locations in these two packages.

**F-5 — Cumulative resource budget gate** (`resource_budget.py`)

Catches the slow-drain attack: individually small commands that together push a
resource past the mission cap. `ResourceBudgetGate.project()` checks without
committing; `commit()` atomically records consumption under a per-resource lock.
Soft-cap breaches publish `aria.budget.soft_breach`; hard-cap breaches publish
`aria.budget.hard_breach`. Committed values are mirrored into the constitution's
own resource window so forward-projection stays accurate. Non-finite or negative
quantities are rejected without being recorded to prevent window poisoning.

**F-7 — Independent monitor** (`aria.monitor` package)

Separate process, separate code path, different model family for the cross-check
leg. 2-of-3 vote (rule-based + statistical + cross-model) with fail-safe
`REFUSE` on unavailability. Heartbeat silence forces the primary to safe mode.
Monitor is READ-ONLY: it publishes veto and violation events; it never commands
actuators directly.

**F-10 — Non-finite health metric guard** (`safe_mode.py`)

Any `NaN` or `inf` in health score, battery SoC, or power margin forces
`MONITORING_ONLY` rather than silently passing every threshold. Escalation jumps
directly to the deepest triggering level rather than incrementing one level at a
time.

**F-12 — Resource-aware command planner** (`execution_guard.py`, `resource_budget.py`)

`ExecutionGuard` wraps every command in a `PlanNode` with preconditions,
resource reservations, invariant checks, postconditions, and typed recovery.
`ResourceArbiter` tracks reservations within a run; `ResourceBudgetGate` tracks
cumulative consumption across runs via sliding windows.

**F-13 — Continuous safety-test replay** (`safety_replay.py`)

`SafetyReplay` loads `data/sealed/safety_test_set.v1.json` (a frozen, hash-
verified scenario set) and runs all scenarios against the live constitution every
6 hours. If more than 1 % of scenarios produce unexpected verdicts, a drift alarm
fires (`aria.safety.replay.drift_alarm`) and the registered `on_drift_alarm`
callback is invoked — typically triggering a safe-mode transition. The scheduler
tracks start/finish monotonic timestamps and an iteration counter so external
watchdogs can detect a wedged replay loop.

**F-14 — Two-person rule** (`approval_queue.py`)

`ApprovalQueue` implements the full two-person workflow for constitution `GATE`
verdicts. Required properties: two distinct operator IDs must sign; the same
hardware key fingerprint cannot satisfy both signatures even under different IDs;
each signer must answer a recall question (`recall_answer_ok` is a required
keyword with no fail-open default); a cooling-off window (measured on the
monotonic clock) applies after the last signature; proposals expire after 5 min;
executed proposals have an undo window. All state transitions publish audit events.

**F-19 — TOCTOU + replay defence** (`command_tracker.py`, `resource_budget.py`)

`CommandTracker` assigns a monotonic sequence number to every dispatched command
and tracks it until completion or timeout. `ResourceBudgetGate.commit()` uses a
per-resource lock so two concurrent requests cannot both be told "there is room"
and together overspend.

---

## Current limitations

**Statistical anomaly leg is absent.** The `aria.monitor.__init__.py` design
document names three monitor strategies: rule-based, statistical anomaly, and
cross-model semantic. The statistical leg (`monitor/anomaly.py` referenced in
`FAILSAFE_ARCHITECTURE.md §F-7`) does not exist in the current package. The
2-of-3 vote therefore operates with at most two functioning legs in practice.

**Cross-monitor stub in development runs.** When neither Ollama nor the LLM CLI
binary is on `PATH`, `best_available_provider()` falls back to
`StubCrossCheckProvider`, which default-approves every action not on its
JSON allow-list. The stub is blocked in `ARIA_ENVIRONMENT=production` but is
the effective cross-check provider in default development and CI runs. Operators
should install Ollama (`ollama serve` + `ollama pull llama3.2:3b-instruct-q4_K_M`)
to activate genuine cross-vendor checking.

**LLM CLI auditor is same-vendor.** When the Ollama provider is unavailable and
the LLM CLI auditor is used instead, the cross-check leg uses the same model
family as the primary advisor. This is explicitly weaker than the cross-vendor
design goal documented in the constitution (threat T-V-3). The code logs a
warning and tags results accordingly.

**IPC design is pending.** `runner.py` documents three IPC options for bridging
heartbeats from the monitor process to the primary's in-process bus. The current
file-bridge (`bridges.py`) is functional but the architectural choice between
HTTP, file, and broker transports is unresolved (F14.4). Without a confirmed IPC
path, the process-separation guarantee is not end-to-end.

**No flight heritage.** The entire safety + monitor stack is TRL 3–5
(prototype demonstrated in simulation). The safe-mode thresholds, replay
interval, heartbeat grace period, and resource caps are engineering estimates
chosen for the current simulation environment and have not been validated against
a physical spacecraft or regulatory safety standard.

**F-10 safe-mode reversibility.** `FAILSAFE_ARCHITECTURE.md §F-10` states that
safe-mode is reversible only by physical key plus two-person rule. The
`SafeModeManager` code implements the transition logic and the force path, but
the physical-key gate is not present in the package — it depends on hardware and
operator-console integration not yet built.

---

## Where to start reading

**Entry files:**

- [`../../src/aria/safety/safe_mode.py`](../../src/aria/safety/safe_mode.py) —
  `SafeLevel`, `SafeModeManager`, entry/exit thresholds.
- [`../../src/aria/safety/resource_budget.py`](../../src/aria/safety/resource_budget.py) —
  `ResourceBudgetGate`, sliding-window cumulative accounting.
- [`../../src/aria/safety/approval_queue.py`](../../src/aria/safety/approval_queue.py) —
  two-person workflow state machine.
- [`../../src/aria/safety/safety_replay.py`](../../src/aria/safety/safety_replay.py) —
  continuous constitution regression.
- [`../../src/aria/monitor/__init__.py`](../../src/aria/monitor/__init__.py) —
  concise design rationale; read this first for the monitor.
- [`../../src/aria/monitor/rules.py`](../../src/aria/monitor/rules.py) —
  deterministic rule-based monitor floor.
- [`../../src/aria/monitor/cross_check.py`](../../src/aria/monitor/cross_check.py) —
  `CrossVendorMonitor`, `MajorityVoteProvider`, provider protocol.
- [`../../src/aria/monitor/providers.py`](../../src/aria/monitor/providers.py) —
  `OllamaCrossCheckProvider`, `LlmCliAuditorProvider`, provider selection.
- [`../../src/aria/monitor/heartbeat.py`](../../src/aria/monitor/heartbeat.py) —
  `HeartbeatEmitter` and `HeartbeatWatcher`, HMAC authentication.
- [`../../src/aria/monitor/runner.py`](../../src/aria/monitor/runner.py) —
  separate-process entry point; explains IPC options.

**Relevant tests:**

- `tests/unit/test_cross_check.py` — cross-vendor monitor unit tests.
- `tests/unit/test_failsafe_layer.py` — failsafe integration tests.
- `tests/integration/test_monitor_providers.py` — Ollama and CLI provider integration.

**Architecture reference:**

- [`../FAILSAFE_ARCHITECTURE.md`](../FAILSAFE_ARCHITECTURE.md) — full failsafe
  catalog (F-1 through F-19) and threat-to-control coverage matrix.
- [`../../README.md`](../../README.md) — "Safety architecture" section and
  safe-mode table.
