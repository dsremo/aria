# Subsystem agents & core types — domain expertise and the shared vocabulary of trust

ARIA's domain knowledge lives in ten subsystem agents that each own one slice of spacecraft operations. Those agents share a common vocabulary — severity levels, authority models, command priorities — defined in a single `core/types.py` module. The shared vocabulary is what lets every safety check, every anomaly event, and every command proposal speak the same language regardless of which agent produced it.

---

## Where they sit in the architecture

The `core/` package is the foundation layer. It exports no business logic; it exports only types, enums, and base classes. Every other package — agents, safety, cognitive engine, constitution, monitors — imports from `core`. Nothing in `core` imports from anywhere else in ARIA. That one-way dependency rule is what makes the type system trustworthy: a `Severity.CRITICAL` produced by `NavigationAgent` and a `Severity.CRITICAL` produced by `EclssAgent` are the same value with the same numeric ordinal, so the coordinator's storm-detection counter, the `DecisionEngine`'s routing table, and the constitution's precondition predicates all reason about the same scale.

The subsystem agents sit one layer above `core`. They form the domain layer between raw telemetry and the cognitive engine. The cognitive engine (`aria.cognitive.engine.CognitiveEngine`) does not have independent situational awareness; it answers questions that agents bring to it. When an agent's deterministic rules are not enough — a low-SoC eclipse with rising battery temperature, a conjunction within 24 hours with minimal delta-V remaining — the agent calls `request_reasoning()`, which publishes `aria.agent.reasoning_request` on the message bus. The coordinator receives that message, calls `engine.reason()` with the agent's question and context, then publishes the final text back on `aria.agent.reasoning_response.{agent_name}`. The agent's `on_reasoning_response()` hook receives the answer and decides whether to act.

The cognitive engine is therefore an on-call advisor, not a continuous controller. Agents run their own deterministic loops; they escalate to the engine when the situation exceeds what threshold rules can handle. Every LLM-originated action still passes through `safe_dispatch_check` (kill switch → constitution → resource budget) before any actuator command is issued.

```
Captain / Crew / MCC
        │
        ▼
Coordinator (AriaCoordinator)
 ├─ CognitiveEngine  ←── answers questions from agents
 ├─ DecisionEngine   ←── routes approvals by AuthorityLevel
 ├─ ExecutionGuard   ←── precondition + resource validation
 ├─ CommandTracker   ←── timeout + sequence number on every command
 └─ [SubsystemAgents]  ←── domain experts, event-driven
       telemetry · power · thermal · eclss · navigation
       propulsion · comms · science · medical
```

---

## The subsystem-agent framework

### Base class

`SubsystemAgent` ([`../../src/aria/agents/base.py`](../../src/aria/agents/base.py)) is the abstract base for every domain agent. It provides:

- **Message bus subscription and bounded queue.** Each agent subscribes to its topic patterns on start. Incoming messages are enqueued in a bounded `asyncio.Queue` (default 1 024 slots). On overflow the oldest message is evicted and a structured overflow counter is incremented — recent telemetry survives a flood, old telemetry is dropped.
- **Two background tasks.** `_process_loop` dequeues messages one at a time, calling `handle_message()` with a per-message timeout (default 30 s). A stuck handler promotes the agent to `AgentStatus.ERROR` rather than blocking the queue. `_heartbeat_loop` publishes `aria.agent.{name}.heartbeat` every `heartbeat_interval_s` seconds.
- **Subclass hooks.** `on_start()` / `on_stop()` for resource management; `periodic_task()` for background work called between messages; `handle_message()` (abstract) for the per-message dispatch; `on_reasoning_response()` as the default LLM-response handler.
- **Safety context injection.** `set_safety_context()` wires in the coordinator-managed safety modules: `FaultManager`, `CommandTracker`, `ExecutionGuard`, and `HealthMonitor`. These are injected after instantiation; agents that lack the method (older or test variants) continue to work without them.
- **`request_reasoning()`** publishes a reasoning request on `aria.agent.reasoning_request`. The coordinator routes this to the cognitive engine and delivers the response back through the same message queue.
- **`dispatch_command()`** wraps every actuator command through `ExecutionGuard` (precondition + resource check) and `CommandTracker` (sequence number + timeout). Falls back to direct publish in test environments where no safety context is wired.
- **`report_fault()`** sends a structured fault to `FaultManager`, which persists it to disk and publishes a bus event so the operator console can open an ack/shelve/resolve workflow.
- **Decision learning.** `log_decision()` and `record_outcome()` track false-alarm and missed-alarm rates. An `alert_threshold_offset` property provides a bounded exponential-moving-average shift (clamped to ±0.05) that agents can apply on top of their base thresholds.
- **Liveness-aware health ping.** `handle_ping()` echoes the ping key if the process loop is making progress, or raises `RuntimeError` (causing `HealthMonitor` to count a missed cycle) if messages are queuing but `messages_processed` is not advancing.

### Anomaly-detection mixin

`DsremoAnomalyMixin` ([`../../src/aria/agents/dsremo_mixin.py`](../../src/aria/agents/dsremo_mixin.py)) adds `dsremo_score()` and `dsremo_score_batch()` to any agent that inherits it. These methods call the `dsremo_ingest_telemetry` / `dsremo_ingest_batch` tools and return a float anomaly score in [0, 1]. The mixin also provides `dsremo_classify()` which maps scores to severity strings (`WATCH` ≥ 0.50, `WARNING` ≥ 0.65, `CRITICAL` ≥ 0.85). This is the "Layer 2" statistical detection that runs on top of each agent's own deterministic threshold rules.

Nine of the ten subsystem agents mix in `DsremoAnomalyMixin`. `TelemetryAgent` handles Dsremo ingestion differently — it is the universal bus bridge for the full ML ensemble and does not use the per-reading mixin path.

### Inrush guard

`inrush_guard.check_burst_allowed()` ([`../../src/aria/agents/inrush_guard.py`](../../src/aria/agents/inrush_guard.py)) is a standalone pure function called by `PropulsionAgent` and `CommsAgent` before commanding any pulsed load (thruster fire, HGA switch). It estimates the instantaneous bus voltage dip from inrush current (default: 3× steady-state, per Patterson 2007 §3) and refuses the burst if the post-dip voltage would fall within 1 V of the undervoltage cutoff, or if battery SoC is below 30 %.

### The ten subsystem agents on disk

| Agent | File | Domain |
|-------|------|--------|
| `TelemetryAgent` | [`telemetry.py`](../../src/aria/agents/telemetry.py) | Universal Dsremo bridge — subscribes to all `aria.sensor.*` topics, batches readings to the 12-detector ML ensemble, publishes `aria.anomaly.detected` and `aria.telemetry.scored`. Does not use the per-reading mixin; runs its own 500 ms flush loop. CRITICAL_CHANNELS (CO₂, O₂, pressure, SoC, angular rates) have a lower threshold for severity promotion. |
| `PowerAgent` | [`power.py`](../../src/aria/agents/power.py) | Battery SoC/SoH, solar array, bus voltage, load shedding. Physics-based SoH (Schmalstieg/Millner models via `aria.physics.electrical.battery`). Minimum-subset load shedding ordered by priority table (ECLSS and `aria_core` are not sheddable). Load-shed state, charge cycles, and SoH alert band persisted across restarts. |
| `ThermalAgent` | [`thermal.py`](../../src/aria/agents/thermal.py) | Eight thermal zones (battery pack, electronics bay, propulsion, solar array, crew cabin, science instruments, radiator panel, antenna assembly). Bang-bang thermostat with per-zone deadband, relay-debounce (60 s min on/off, 200-cycle/day budget), thermistor sanity checks, and eclipse pre-heat logic gated on battery budget. Gradient monitoring between adjacent zones. |
| `EclssAgent` | [`eclss.py`](../../src/aria/agents/eclss.py) | Life support: O₂ (target 20.9 %), CO₂ (emergency at ≥ 15 mmHg), cabin pressure (emergency below 13.5 psi), humidity, temperature, fire detection, water quality. Most safety-critical agent — heartbeat every 5 s. Staged CO₂ response; pressure-leak rate estimation over rolling history; automatic backup-scrubber activation. |
| `NavigationAgent` | [`navigation.py`](../../src/aria/agents/navigation.py) | GPS, IMU, star-tracker fusion; orbital state estimation; conjunction monitoring via `ConjunctionWatch`; TLE staleness alerts (72 h max). Tumble detection above 5 deg/s triggers ADCS desaturation and emergency safe-mode. Conjunction data written to scratchpad for `PropulsionAgent`. |
| `PropulsionAgent` | [`propulsion.py`](../../src/aria/agents/propulsion.py) | Four thrusters, hydrazine-class (MR-107T, 22 N, 220 s Isp). Thrust-scaled rocket-equation fuel accounting; delta-V budget gate (resource committed at actual burn, not at plan time); stuck-valve detection; inrush guard check before each fire; fuel state and maneuver history persisted across restarts. |
| `CommsAgent` | [`comms.py`](../../src/aria/agents/comms.py) | RF link (signal strength, SNR, BER, data rate); antenna state; outbound message queue with priority ordering; contact window tracking. Auto-beacon after 30 min of signal loss. Inrush guard check before HGA switch (80 kW TX peak). |
| `ScienceAgent` | [`science.py`](../../src/aria/agents/science.py) | Spectrometer, radiation monitor, microscope. Crew radiation dose monitoring (ICRP limits); solar particle event detection and shelter protocol. GenAstra biosignature analysis with a formal escalation protocol before candidate announcements. Power-aware observation scheduling via scratchpad. |
| `MedicalAgent` | [`medical.py`](../../src/aria/agents/medical.py) | Per-crew vital signs (NASA-STD-3001 thresholds: HR, SpO₂, BP, temperature, respiratory rate); fatigue/sleep tracking; radiation dose per crew member; bone density (microgravity deconditioning); SANS vision monitoring; psychological stress indicators. Reads ECLSS atmosphere and fire state from scratchpad for cross-system health assessment. |
| `(inrush_guard)` | [`inrush_guard.py`](../../src/aria/agents/inrush_guard.py) | Not an agent — a module-level pure function called by PropulsionAgent and CommsAgent. Listed here because it lives in `agents/` and guards two agents' pulsed-load paths. |

---

## The core type system

All types are defined in one file: [`../../src/aria/core/types.py`](../../src/aria/core/types.py). There are no circular imports; every other package imports from here.

### Severity

```python
class Severity(Enum):
    NOMINAL   = 0
    WATCH     = 1  # score >= 0.50
    WARNING   = 2  # score >= 0.65
    CRITICAL  = 3  # score >= 0.85
    EMERGENCY = 4  # imminent danger
```

`Severity` is the common scale for anomaly events, fault reports, `_raise_alert()` calls, decision routing, and the storm-detection counter in the coordinator. The numeric values are load-bearing: `severity.value >= Severity.CRITICAL.value` is used as an inequality predicate throughout. The thresholds at 0.50 / 0.65 / 0.85 are calibrated against the Dsremo precision-recall evaluation set (`dsremo/eval/auto_scorer.py`).

### AuthorityLevel

```python
class AuthorityLevel(Enum):
    SENSOR_ONLY  = 0  # read-only queries
    ROUTINE      = 1  # automated ops, logged
    SUPERVISED   = 2  # AI acts, captain notified after
    CONSENT      = 3  # AI proposes, captain may veto within timeout
    ADVISORY     = 4  # captain decides, AI recommends
    CAPTAIN_ONLY = 5  # only captain may initiate
```

`AuthorityLevel` drives the `DecisionEngine`: `WATCH` decisions use `SUPERVISED`, `WARNING` uses `CONSENT` (30 s veto window), `CRITICAL` uses `ADVISORY` (60 s, AI acts on timeout), `EMERGENCY` overrides to immediate AI action with post-hoc notification. The coordinator constructs `ReasoningContext` with `AuthorityLevel.ADVISORY` for all agent reasoning requests so LLM-originated tool calls pass through `ExecutionGuard` rather than executing autonomously.

### SafetyLevel

```python
class SafetyLevel(Enum):
    READ_ONLY    = "read_only"
    REVERSIBLE   = "reversible"
    IRREVERSIBLE = "irreversible"
    EMERGENCY    = "emergency"
```

`SafetyLevel` annotates individual tools in `ToolRegistry`. It is separate from `Severity` — a tool's safety level is a static property of what it does; a fault's severity is a runtime judgment about how bad the current reading is.

### InterruptBehavior

```python
class InterruptBehavior(Enum):
    CANCEL     = "cancel"      # stop and discard
    BLOCK      = "block"       # keep running, queue the interrupt
    CHECKPOINT = "checkpoint"  # save state then yield
```

`InterruptBehavior` is a per-tool lifecycle annotation. The `CHECKPOINT` variant is an ARIA extension for long-running science or planning tasks.

### EventPriority

```python
class EventPriority(Enum):
    P0_EMERGENCY = 0  # fire, depress, collision
    P1_CRITICAL  = 1  # attitude loss, power failure
    P2_WARNING   = 2  # anomaly escalation, conjunction alert
    P3_ROUTINE   = 3  # telemetry summary, schedule update
    P4_BULK      = 4  # science data, logs
    P5_BACKGROUND = 5 # model updates, calibration
```

`EventPriority` annotates every `Message` on the bus. It is what every call to `publish()` and `_raise_alert()` sets; the coordinator uses it to route to captain alerts. The mapping from `Severity` to `EventPriority` is repeated (identically) in each agent's `_raise_alert()` helper: `EMERGENCY → P0`, `CRITICAL → P1`, `WARNING → P2`, `WATCH → P3`.

### AgentStatus

```python
class AgentStatus(Enum):
    INITIALIZING | READY | BUSY | DEGRADED | ERROR | SHUTTING_DOWN | STOPPED
```

`AgentStatus` is the lifecycle state tracked in `SubsystemAgent._status`. The coordinator's health monitor checks for `ERROR` or `STOPPED` to trigger restart. `HealthScorer` aggregates statuses into a system health score.

### MissionPhase and PHASE_CONFIG

```python
class MissionPhase(Enum):
    PRE_LAUNCH | LAUNCH_ASCENT | EARLY_ORBIT | NOMINAL_LEO | ORBIT_TRANSFER
    PROXIMITY_OPS | PLANETARY_APPROACH | ENTRY_DESCENT_LANDING | SURFACE_OPS
    DEEP_SPACE_CRUISE | EMERGENCY
```

`PHASE_CONFIG` (a plain dict in `types.py`) maps each phase string to a default `AuthorityLevel`, an autonomy level integer (0–4), and a list of which agents are active. `NOMINAL_LEO` and `DEEP_SPACE_CRUISE` are the only phases that include all nine agents; `PRE_LAUNCH` activates five; `PROXIMITY_OPS` drops back to `CAPTAIN_ONLY` authority. The coordinator's `transition_phase()` method reads this table.

### ToolCategory

An `auto()`-valued enum covering: `TELEMETRY`, `NAVIGATION`, `PROPULSION`, `LIFE_SUPPORT`, `COMMUNICATION`, `POWER`, `SCIENCE`, `STRUCTURAL`, `EMERGENCY`, `DIAGNOSTIC`, `PLANNING`, `FLEET`. Used by `ToolRegistry` for domain-filtered tool lookup.

---

## Key design decisions

**One vocabulary for all trust boundaries.** The constitution, the monitors, the execution guard, and the agent loop all reason in terms of the same `Severity`, `AuthorityLevel`, and `EventPriority` values defined in `core/types.py`. There is no translation layer. A `Severity.CRITICAL` produced by an `EclssAgent` threshold check and a `Severity.CRITICAL` produced by the Dsremo ML ensemble are the same value. The coordinator's storm counter, the `DecisionEngine`'s routing, and the constitution's predicate checks all operate on the same ordinal scale.

**Per-subsystem agents, not one monolithic monitor.** Splitting domain knowledge across ten agents keeps each unit testable against its own physics and thresholds. `EclssAgent` embeds CO₂ toxicology and pressure-leak modelling without requiring the power subsystem to know about them. `PowerAgent` embeds battery physics (NMC floor, Arrhenius degradation) without requiring ECLSS to know about them. Cross-cutting dependencies — eclipse state, conjunction proximity, fuel budget — flow through a typed scratchpad rather than direct agent-to-agent coupling.

**Two-layer anomaly detection per agent.** Each agent applies deterministic threshold rules (Layer 1) before invoking the Dsremo ML ensemble (Layer 2). Layer 1 fires first and is fast. Layer 2 runs on the same telemetry sample and catches subtle drift, cross-channel correlation, and pre-failure signatures that threshold rules miss until a value crosses a hard limit. The two layers use the same `Severity` enum, so anomalies from either path are indistinguishable to the coordinator.

**LLM as on-call advisor, not loop controller.** The cognitive engine answers questions; agents act. Agents expose `request_reasoning()` for situations that exceed deterministic reasoning (e.g. a complex power budget decision during eclipse). Every LLM-originated action still passes `safe_dispatch_check` before touching an actuator. This keeps the deterministic safety envelope intact regardless of the LLM's output.

**Cognitive engine relationship to agents.** The cognitive engine is consulted by agents, not the reverse. Agents are domain experts that call the engine when they need higher-level reasoning. The engine does not poll agents; it reads scratchpad state and invokes registered tools when called. The coordinator mediates the request/response cycle and maintains a 200-entry AI decision log for the operator dashboard.

---

## Current limitations

The following are honest status notes, not aspirational claims. TRL 3–5 across this subsystem.

- **Simulation-only.** No agent has been tested against real spacecraft hardware. All threshold calibrations (load priorities, SoC limits, thermistor rate-of-change limits, radiation dose ceilings) are derived from published references (NASA STD-3001, Gilmore 2002, Plett 2015, Patterson 2007) but are not validated against real telemetry streams.
- **`TelemetryAgent` Dsremo connectivity is tested against a stub.** The 12-detector ensemble (`CUSUM`, `EWMA`, `Z-score`, `GMM-2`, `BOCPD`, `AR(1)`, `IQR`, `LLR`, `IsolationForest`, `DBSCAN`, `Prophet`, `LSTM`) is described in the module header and called via tool invocations. Whether the `dsremo_ingest_batch` tool actually reaches a running Dsremo deployment depends on deployment configuration.
- **`MedicalAgent` and `ScienceAgent` have no `on_reasoning_response()` overrides.** Both agents inherit the base class advisory-publish path. LLM-originated actions for medical and science domains surface as `aria.{name}.llm_action.advisory` events visible in the operator console, but are not autonomously acted upon by the agents themselves. This is a deliberate conservative stance for crew health decisions, but it means the cognitive-loop-to-actuation path is incomplete for these two agents.
- **`DsremoAnomalyMixin` returns `None` on circuit-breaker open.** When the Dsremo integration is unreachable (timeout, circuit breaker tripped), `dsremo_score()` returns `None` and the agent falls back to Layer 1 rules only. There is no alerting on prolonged Dsremo unavailability beyond the tool health report.
- **`PHASE_CONFIG` autonomy level integers (0–4) are not yet enforced.** The table is consulted for the default `AuthorityLevel` string and the active-agent list. The integer `autonomy_level` field is logged on phase transition but does not yet gate agent actions differently by phase.
- **Decision learning thresholds are clamped to ±0.05.** The adaptive alert threshold offset is deliberately conservative to prevent oscillation on sparse early-mission data. Agents with fewer than five historical decisions do not adjust at all.

---

## Where to start reading

| What you want to understand | Start here |
|-----------------------------|------------|
| How any agent processes a message | [`../../src/aria/agents/base.py`](../../src/aria/agents/base.py) — `_process_loop`, `handle_message`, `on_reasoning_response` |
| The shared type vocabulary | [`../../src/aria/core/types.py`](../../src/aria/core/types.py) — all enums in one file |
| How the LLM connects to agents | [`../../src/aria/core/coordinator.py`](../../src/aria/core/coordinator.py) — `_on_reasoning_request`, `_get_cognitive_engine` |
| How decisions reach the captain | [`../../src/aria/core/decision_engine.py`](../../src/aria/core/decision_engine.py) — `submit_decision`, timeout logic |
| The most safety-critical agent | [`../../src/aria/agents/eclss.py`](../../src/aria/agents/eclss.py) — CO₂ staged response, pressure-leak detection, fire protocol |
| Battery physics and load shedding | [`../../src/aria/agents/power.py`](../../src/aria/agents/power.py) — `_update_battery`, `LOAD_PRIORITY`, `_execute_load_shed` |
| How ML anomaly detection layers in | [`../../src/aria/agents/telemetry.py`](../../src/aria/agents/telemetry.py) — `_batch_flush_loop`, `_evaluate_channel` |
| Cross-agent context sharing | [`../../src/aria/state/scratchpad.py`](../../src/aria/state/scratchpad.py) — the shared scratchpad that power, nav, propulsion, thermal, and medical read from each other |
| How agents relate to the cognitive layer | [`./cognitive.md`](./cognitive.md) |
| Safety checks on LLM-originated actions | [`./safety-and-monitor.md`](./safety-and-monitor.md) |

### Key test entry points

Tests live under `tests/agents/` and `tests/core/`. Each agent has a dedicated test module. The coordinator integration tests are under `tests/integration/`. Running `pytest tests/agents/test_power_agent.py -v` is a fast sanity check that covers both the threshold-rule path and the simulated Dsremo-mixin path.
