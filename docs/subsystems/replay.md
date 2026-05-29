# Replay & the closed-loop demonstration — the first end-to-end falsifiable result

The replay subsystem is the part of ARIA that does something testable: it takes reconstructed telemetry from a documented historical spacecraft anomaly, runs it through the full anomaly-detector → LLM-advisor → cross-monitor → HAL chain, and records whether each link behaved correctly. The Apollo 13 cryo-stir run is ARIA's headline demonstration — a measurable, reproducible, falsifiable claim on real-anomaly data. Every number in that claim carries a citation or an honest caveat. Read those caveats first.

Package path: [`src/aria/replay/`](../../src/aria/replay/)  
Full Apollo 13 result: [`docs/APOLLO13_REPLAY_REPORT.md`](../APOLLO13_REPLAY_REPORT.md)

---

## Why this subsystem matters

Most AI-for-space research produces either a capability report ("our model scores X on benchmark Y") or a simulation that is not grounded in a real anomaly. The replay subsystem does something different: it connects all four layers of ARIA — detection, reasoning, independent oversight, and actuation — to a reconstructed telemetry stream derived directly from documented mission data, and asks whether the loop closes correctly.

For the Apollo 13 scenario, that means:

- The parameters being watched are the same eight channels that matter during the cryo-stir event (O₂ tank pressures, quantity, temperature, heater current, fuel-cell voltages).
- The numerical constants in the telemetry model are sourced from the Cortright Commission Report (NASA SP-1969, 1970) and the Apollo 13 Mission Report (MSC-02680, Sep 1970, §5).
- The detection threshold, window size, and warmup are declared up front and do not change between the demo run and the integration tests.
- The advisor prompt, the JSON-only response contract, and the cross-monitor decision rule are all in source control.

The result — detector flagged O₂ tank 2 pressure 94 seconds before the historical master alarm; advisor returned six doctrine-matching steps in ~8 s; full loop closed in under 16 s — is the specific, reproducible, falsifiable claim the replay harness exists to produce.

The subsystem also carries 15 additional scenario sketches (Apollo 12 lightning, STS-114 gap-filler, SOHO attitude loss, Mir Spektr, Salyut 7, MAVEN safe mode, Galileo HGA failure, JWST micrometeorite, Voyager 2 plasma fault, Apollo 1 fire, ISS Quest leak, Crew Dragon dock abort, Hayabusa wheel failures, Hubble SM4 stuck bolt) so the same harness can be pointed at other documented incidents as ARIA matures.

---

## The closed loop

The loop has four stages. Each stage is separated by a typed dataclass boundary; no stage reaches into another stage's internals.

```
TelemetrySample
    │
    ▼
WindowedZScoreDetector  ──→  AnomalyEvent
                                    │
                                    ▼
                             LlmAdvisor.advise()  ──→  AdvisorVerdict
                                                              │
                                                              ▼
                                                   CrossMonitor.review()  ──→  MonitorVerdict
                                                                                      │
                                                              ┌───────────────────────┘
                                                              │   APPROVE → ActionRegistry.translate()
                                                              │                    │
                                                              │                    ├── applied → hal_apply_fn()
                                                              │                    └── deferred / refused → residual_log
                                                              └── DEFER / REJECT → residual_log
                                                                        │
                                                                        ▼
                                                                  LoopOutcome  (frozen dataclass)
```

`LoopOutcome` captures every typed field from all four stages: the original `AnomalyEvent`, the `AdvisorVerdict`, the `MonitorVerdict`, the `ActionTranslation`, the name of the HAL primitive that was actually applied (or `None`), both elapsed times, and any residual log entry. Nothing is discarded; `ClosedLoop.outcomes` is a growing `tuple[LoopOutcome, ...]` readable at any time.

### WindowedZScoreDetector

Defined in [`closed_loop.py`](../../src/aria/replay/closed_loop.py). A per-parameter rolling z-score detector over a configurable window.

For each incoming `TelemetrySample`:

1. If the parameter is not in the declared set, or the value is `NaN`, the sample is ignored.
2. Until `warmup_samples` have accumulated in the ring buffer (minimum 4, maximum `window_size`), the detector is silent.
3. Once warm, it computes the sample mean and unbiased variance of the buffer. If the population standard deviation is below `1e-6`, the sample is added and the detector stays silent (avoids spurious division on perfectly-flat pre-event windows).
4. If `|value - mean| / std >= z_threshold` and no alert was issued for this parameter within `cooldown_s` seconds, it returns an `AnomalyEvent`.
5. The `severity` field is `CRITICAL` when `z > 8.0`, `HIGH` when `z > 5.0`, and `MEDIUM` otherwise. The `score` field is `min(z / 10.0, 1.0)`.

Default parameters used in the Apollo 13 run: `window_size=30`, `warmup_samples=10`, `z_threshold=3.5`, `cooldown_s=5.0`.

### LlmAdvisor Protocol and implementations

The `LlmAdvisor` Protocol (also in `closed_loop.py`) requires two attributes: a `label: str` and an `advise(anomaly, recent_state, doctrine) -> AdvisorVerdict` method.

**`StubAdvisor`** — rule-based fallback. Inspects the parameter name and returns a hard-coded `AdvisorVerdict` with `confidence=0.6`. O₂ tank pressure events produce a four-step LM-lifeboat path; fuel-cell voltage events produce a load-shed path; anything else defers to ground. Used in unit and integration tests, and as the fallback if `LlmCliAdvisor` finds the CLI binary not on PATH.

**`LlmCliAdvisor`** — the real advisor. Dispatches to the Claude CLI via `subprocess.run` (configurable `binary`, `effort`, `timeout_s`). The system prompt instructs the advisor to return exactly one JSON object:

```json
{"proposed_action": "short_snake_case", "rationale": "one sentence",
 "immediate_steps": ["step1", "step2"], "confidence": 0.0}
```

No prose, no markdown fences. The parser (`_parse_advisor_response`) scans for the outermost `{…}` and falls back to `proposed_action="investigate"` with `confidence=0.0` on any parse failure, so a garbled response never crashes the loop. On timeout or non-zero exit, `_stub_fallback` delegates to `StubAdvisor` with the confidence halved and a degradation note in the rationale.

The user-facing prompt includes: GET timestamp, parameter name and value, severity, detector name, z-score reason, a `recent_state` dict of the last seen value for every watched parameter, and any doctrine or lesson text the `ClosedLoop` has assembled for this event.

### CrossMonitor Protocol and StubCrossMonitor

`CrossMonitor` (Protocol in `closed_loop.py`) requires `label: str` and `review(advisor, anomaly) -> MonitorVerdict`. `MonitorVerdict.decision` is one of `"APPROVE"`, `"DEFER"`, or `"REJECT"`.

`StubCrossMonitor` approves any verdict with `confidence >= 0.3` and defers the rest. The Apollo 13 demo run used this stub. The full ARIA monitor subsystem (`aria.monitor.providers`) has Ollama and Claude-CLI auditor backends capable of a real 2-of-3 vote, but they were not wired into that specific run (see the limitations section).

### ClosedLoop orchestrator

`ClosedLoop` (dataclass in `closed_loop.py`) wires the four stages. Its `step(sample)` method does:

1. Updates the rolling `_state` dict with the new sample's value.
2. Calls `detector.step(sample)`. Returns `None` if no anomaly.
3. Calls `_build_doctrine(event)` — either returns `doctrine_text` verbatim, or (when a `DoctrineBundle` is provided) uses `select_relevant_entries` + `format_doctrine_for_prompt` to build a budget-limited excerpt.
4. Calls `_build_lessons(event)` — if a `lesson_index` is wired, runs a TF-IDF query over the lessons corpus and prepends the top-k hits to the doctrine text.
5. Calls `advisor.advise(anomaly, recent_state, doctrine)` and times it.
6. Calls `monitor.review(verdict, event)` and times it.
7. Calls `action_registry.translate(verdict.proposed_action, context)` — see action translation below.
8. If `monitor.decision == "APPROVE"` and the translation is `"applied"`, calls `hal_apply_fn(hal_command.primitive, verdict)`.
9. Records any gap between the monitor decision and an actual HAL application in `residual_log`.
10. Returns a frozen `LoopOutcome`.

---

## What's in the package

The package has 10 files totalling approximately 3,010 lines:

| File | Role |
|---|---|
| [`apollo13_cryo_stir.py`](../../src/aria/replay/apollo13_cryo_stir.py) | Reconstructed Apollo 13 telemetry: constants, piecewise time-functions, `generate_apollo13_cryo_stir_telemetry()`, `HISTORICAL_TIMELINE`, `HISTORICAL_GROUND_RESPONSE`, `CITATIONS` |
| [`replayer.py`](../../src/aria/replay/replayer.py) | `TelemetryReplayer`, `ReplayClock` (configurable real-time vs. fast-forward), `ReplayStats`, `TelemetrySink` Protocol |
| [`closed_loop.py`](../../src/aria/replay/closed_loop.py) | `WindowedZScoreDetector`, `LlmAdvisor` Protocol, `StubAdvisor`, `LlmCliAdvisor`, `CrossMonitor` Protocol, `StubCrossMonitor`, `ClosedLoop`, all typed outcome dataclasses (`AnomalyEvent`, `AdvisorVerdict`, `MonitorVerdict`, `LoopOutcome`) |
| [`action_translator.py`](../../src/aria/replay/action_translator.py) | `ActionRegistry`, `ActionTranslation`, `HalCommand`, `ActionMapping`, `DEFAULT_MAPPINGS` (60+ entries across power, thermal, attitude, comms, propulsion, life support, ops), `_SAFETY_BLOCKED_ACTIONS`, precondition helpers |
| [`audit_log.py`](../../src/aria/replay/audit_log.py) | `AuditLogger` (thread-safe, append-only JSON Lines file), `replay_audit_events_from()`, `loop_outcome_to_event()` |
| [`noise.py`](../../src/aria/replay/noise.py) | `SensorNoiseProfile`, `DEFAULT_SENSOR_NOISE_PROFILES` (13 entries with citations), `overlay_noise()` |
| [`report.py`](../../src/aria/replay/report.py) | `ReportInputs`, `render_one_page_markdown()`, `collect_report_inputs_from_audit()` |
| [`scenarios.py`](../../src/aria/replay/scenarios.py) | `ReplayScenario` dataclass, 16 named scenarios in the `SCENARIOS` dict, `get_scenario()`, `list_scenarios()` |
| [`__main__.py`](../../src/aria/replay/__main__.py) | CLI driver: `python -m aria.replay --scenario <id> --advisor stub|claude --noise --with-doctrine --with-lessons --audit-log <path> --json` |
| [`__init__.py`](../../src/aria/replay/__init__.py) | Package re-exports: all public names from the five core modules |

### TelemetryReplayer and ReplayClock

`TelemetryReplayer` takes any `Iterable[TelemetrySample]`, sorts by `get_seconds`, and fans each sample out to a list of `TelemetrySink` callables. Sink exceptions are counted in `ReplayStats.samples_dropped` but do not abort the run.

`ReplayClock` controls pacing. `accel=0.0` means instant (wall time is not throttled — the default when no clock is given). Any positive `accel` value makes the replayer sleep so that `sim_elapsed / accel` wall-clock seconds pass per simulated second. `accel=60.0` (the declared default) means one simulated minute plays in one real second. `ClosedLoop.step` is always called synchronously, so with a real advisor the LLM latency dominates.

### Action translation

`ActionRegistry.translate(proposed_action, context)` maps the advisor's free-text snake-case action to a `HalCommand`. The registry checks three things in order:

1. If the action is in `_SAFETY_BLOCKED_ACTIONS` (14 entries: `vent_to_space`, `deorbit`, `delete_audit_log`, `kill_main_bus`, etc.), it returns `status="refused"` unconditionally.
2. If no `ActionMapping` is registered for the action, it returns `status="deferred"` with either a preset residual reason (from `_RESIDUAL_REASONS` — which explicitly covers `isolate_o2_tank_2`, `isolate_h2_tank`, `shutdown_main_bus`, and six other actions the current HAL sidecar cannot execute) or a generic "no HAL primitive registered" message.
3. If a mapping exists, preconditions are evaluated. On pass, `status="applied"` and a `HalCommand(primitive, params)` is returned.

`DEFAULT_MAPPINGS` covers 60+ actions across six subsystems. Many life-support and cryo-tank actions map to the `"ping"` primitive with a residual note — this is intentional and honest: the current HAL sidecar does not model cryo-valve or hatch hardware.

### Audit log

`AuditLogger` opens a file in append mode (creating parent directories if needed) and writes one JSON object per line, flushing after every write. It is thread-safe via `threading.Lock`. `loop_outcome_to_event()` serialises a `LoopOutcome` to the flat dict shape the audit consumer expects. `replay_audit_events_from()` reads the file back for report generation.

### Noise profiles

`overlay_noise()` applies Gaussian noise plus optional quantization to each sample. `DEFAULT_SENSOR_NOISE_PROFILES` has 13 entries for Apollo-era and ISS-era sensors, each with a `one_sigma`, `bias`, `quantization_step`, and `citation`. The Apollo cryo pressure transducer entry cites "Apollo SC09 Operations: cryo pressure transducer ±0.5 % FS, FS=1500 psia", giving `one_sigma=2.0 psia`. Applying noise before running the detector is the honest path toward a publishable z-score distribution.

### Scenario catalog

`scenarios.py` defines 16 `ReplayScenario` entries keyed by string ID. Each carries a title, ISO date, description, parameter tuple, `historical_alarm_get_s`, `historical_response_get_s`, `expected_keywords`, `citations`, a `samples_factory` callable, and a `timeline` tuple of `HistoricalTimeline` events. The full list:

`apollo_13_cryo_stir`, `apollo_12_lightning`, `sts_114_gap_filler`, `soho_1998_attitude_loss`, `mir_spektr_collision`, `salyut7_blackout`, `maven_safe_mode`, `galileo_hga_failure`, `jwst_micrometeorite`, `voyager2_plasma_anomaly`, `apollo_1_fire`, `iss_quest_leak`, `dragon_dock_abort`, `hayabusa_wheel_failures`, `hubble_sm4_stuck_bolt`, and one further entry.

All but `dragon_dock_abort` (explicitly labelled "synthetic") are grounded in documented incidents with citations.

---

## The Apollo 13 cryo-stir result

The full run record is in [`docs/APOLLO13_REPLAY_REPORT.md`](../APOLLO13_REPLAY_REPORT.md). The headline numbers:

| Metric | Value |
|---|---|
| Stir command (GET) | 55:53:18 |
| ARIA first detection (GET) | 55:53:19 |
| Historical master alarm (GET) | 55:54:53 |
| Lead time over historical alarm | 94 seconds |
| Detector | `WindowedZScore(window=30, z=3.5)` |
| Severity at detection | CRITICAL |
| Advisor | `LlmCliAdvisor` (Claude CLI, effort=low) |
| Advisor latency | 7.98 s wall |
| Steps returned | 6 |
| Cross-monitor | `StubCrossMonitor` |
| Monitor decision | APPROVE |
| HAL command shape | `isolate_o2_tank_2` |
| End-to-end wall time | 15.9 s (two outcomes) |

The six advisor steps — notify Flight Director per rule 5-9; close O₂ tank 2 isolation valve; de-energise heaters and fans; monitor fuel cells for degradation; cross-check O₂ tank 1; prepare LM lifeboat checklist as contingency — match the textbook EECOM response documented by Sy Liebergot. The LM-lifeboat contingency step appeared in the advisor output ~13 minutes before Kranz issued the equivalent order historically.

To reproduce:

```sh
python -m aria.replay \
    --scenario apollo_13_cryo_stir \
    --advisor claude \
    --effort low \
    --z 3.5
```

The Claude CLI must be on PATH. No API key is required for the CLI backend. Swap `--advisor stub` for a deterministic, instant run that exercises the same detector and loop plumbing without the LLM call.

---

## What this does NOT demonstrate

These limitations are real and must be understood before interpreting the result.

**1. The telemetry is reconstructed, not raw.**
NASA never released the raw 1 Hz channel logs from Apollo 13. Every constant in `apollo13_cryo_stir.py` — nominal pressure 887 psia, peak 1008 psia, stir-event start GET 55:53:18, master alarm GET 55:54:53 — comes from documented peaks and trajectories in the Cortright Commission Report and the Apollo 13 Mission Report, each cited at the point of use. The shape of the pressure ramp is faithful to those documents; the sub-second noise structure is not.

**2. The pre-event window has artificially clean variance.**
The synthetic pre-stir window is a flat constant (887 psia). With zero variance in the baseline, the z-score on the first divergent sample is extreme — on the order of tens of thousands. On real mission telemetry with sensor noise, the same detector would see z values in the 5–20 range against the 3.5 threshold. The 94-second lead time is directionally correct but the z-score magnitude in this run is not a publishable number. Running with `--noise` and the documented `SensorNoiseProfile` for the cryo pressure transducer (`one_sigma=2.0 psia`, `quantization_step=0.5 psia`) is the path toward a realistic distribution.

**3. The cross-monitor is a stub in this run.**
`StubCrossMonitor` approves any verdict with confidence ≥ 0.3. The full `aria.monitor.providers` subsystem has Ollama and Claude-CLI auditor backends supporting a real 2-of-3 vote. A production-grade run of this scenario should replace the stub with an `OllamaCrossCheckProvider` (Llama 3.2 on the second leg) and require agreement from both legs before HAL fires.

**4. The HAL sidecar has no cryo-valve driver.**
`isolate_o2_tank_2` is in `_RESIDUAL_REASONS`, not in `DEFAULT_MAPPINGS`, because the current HAL sidecar actuator bank does not model cryo-tank isolation valves, SM reactant control valves, or fuel-cell shutoffs. The sidecar accepted the command shape and logged it, but no physical model was actuated. The `ActionTranslation` for that action returns `status="deferred"` with an explicit note: "no cryo-tank-isolation valve driver in HAL sidecar; advisor's intent logged for ground console + crew ack." The residual log captures this honestly.

**5. The result is not a claim of mission-saving superiority.**
The historical Apollo 13 EECOMs and Flight Director worked on the same telemetry stream, constrained by 1970 telemetry rates, voice-loop comms, and the cognitive load of managing an entire vehicle. A 94-second detection lead in ARIA's loop — with no comms latency, a single anomaly in focus, and a reconstructed clean signal — is the floor ARIA has to clear to be interesting, not a flag of superiority over the real team.

---

## Where to start reading

For the detector and loop logic: [`closed_loop.py`](../../src/aria/replay/closed_loop.py) — `WindowedZScoreDetector`, `LlmCliAdvisor`, `ClosedLoop`.

For the telemetry model: [`apollo13_cryo_stir.py`](../../src/aria/replay/apollo13_cryo_stir.py) — the piecewise functions and `HISTORICAL_TIMELINE` constants, each with its citation.

For the action-translation layer: [`action_translator.py`](../../src/aria/replay/action_translator.py) — `ActionRegistry`, `DEFAULT_MAPPINGS`, `_SAFETY_BLOCKED_ACTIONS`.

For the CLI driver: [`__main__.py`](../../src/aria/replay/__main__.py) — run `python -m aria.replay --list` to see all 16 scenarios.

For end-to-end falsifiability: [`tests/integration/test_apollo13_replay.py`](../../tests/integration/test_apollo13_replay.py) — four test classes covering telemetry shape, replayer ordering, detector lead time, and closed-loop doctrine adherence. The `test_detector_flags_o2_tank2_pressure_before_master_alarm` and `test_detector_lead_time_reasonable` tests assert the 94-second claim structurally without hard-coding a single GET timestamp.

For the full run record and "what this does and does not demonstrate" in its original form: [`docs/APOLLO13_REPLAY_REPORT.md`](../APOLLO13_REPLAY_REPORT.md).

For the anomaly-detection ensemble that the replay detector is extracted from: [`./anomaly-detection.md`](./anomaly-detection.md).

For the independent monitor the cross-monitor stub approximates: [`./safety-and-monitor.md`](./safety-and-monitor.md).

For HAL sidecar integrations: [`./integrations.md`](./integrations.md).

---

### Citations (telemetry constants in apollo13_cryo_stir.py)

- Cortright Commission Report on the Apollo 13 Accident, NASA SP-1969 (1970)
- Apollo 13 Mission Report, MSC-02680, NASA Manned Spacecraft Center (Sep 1970), §5
- Apollo Spacecraft Flight History, NASA TM-X-65495
- Liebergot, S. *EECOM: Last Man Through the Door* (oral-history compilation)
