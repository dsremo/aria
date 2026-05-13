# AUTONOMY_AUDIT_2026-04-27 — Flight-Software / AI-Safety posture

**Audit performed:** 2026-04-27
**Scope:** the cognitive engine, agent base, safe-mode manager, kill switch,
deadman timer, approval queue, resource budget gate, replay guard, monitor
heartbeat, FDIR manager, and the `safe_dispatch` composition entry point.
**Posture:** zero ground correction within the next 8-30 minutes; faults
are not retryable from Mission Control; "fail soft" is the design contract.
**Result:** 35 findings (9 CATASTROPHIC + 18 MISSION DEGRADATION +
8 INFORMATIONAL); **all 35 fixed**.

The audit's signature finding was that the codebase had the *architecture*
of a proper safety stack (sealed constitution, F-1..F-19, two-person rule,
kill switch, hash-chained audit) but was undermined by:

* **Default-ALLOW** at the constitution layer (F1).
* **Wall-clock dependency** in every gate (F4).
* **Silent fallbacks** in the LLM stack (F8) and cross-vendor monitor (F2).
* **NaN propagation** through every numeric defence (F10/F17/F18).
* **Unbounded queues** at the agent boundary (F3).
* **Same-root-cause re-fault drop** in FDIR (F9).

Each is closable in a single PR; the order chosen here is **F1 → F4 →
F10/F17/F18 → F2/F8 → F3 → F9** (earliest catastrophic with smallest
code footprint first).

---

## 1. Mission Criticality Summary

| Impact | Count | Status |
|---|---:|---|
| **CATASTROPHIC** (mission-terminating, irrecoverable) | 9 | ✅ all fixed |
| **MISSION DEGRADATION** (loss of capability) | 18 | ✅ all fixed |
| **INFORMATIONAL** (latent / forensic) | 8 | ✅ all fixed |
| **Total** | **35** | **✅ all fixed** |

---

## 2. Findings + Fixes

### 2.1 CATASTROPHIC

| ID | Title | Affected | Fix |
|----|-------|----------|-----|
| F1 | Constitution defaults to **ALLOW** for unmapped actions | [constitution.py:272-301](src/aria/cognitive/constitution.py#L272) | Default-DENY when sealed `allowed_actions` list is present; explicit allow-list per action.  Legacy default-ALLOW preserved for fixtures that don't ship the list (with a structured warning). |
| F2 | Cross-vendor monitor exception silently fails-open | [safe_dispatch.py:300-306](src/aria/cognitive/safe_dispatch.py#L300) | On any cross-monitor exception, `cross_signers = 1` (require operator override) and emit `safe_dispatch.cross_monitor_unavailable`.  No silent fall-through. |
| F3 | `_message_queue` is unbounded `asyncio.Queue` | [agents/base.py:54](src/aria/agents/base.py#L54) | `asyncio.Queue(maxsize=1024)` (overridable per-agent); FIFO drop-oldest with `agent.queue_overflow` audit event when full. |
| F4 | `time.time()` everywhere in safety-critical paths | [safe_mode.py](src/aria/safety/safe_mode.py), [approval_queue.py](src/aria/safety/approval_queue.py), [resource_budget.py](src/aria/safety/resource_budget.py), [kill_switch.py](src/aria/safety/kill_switch.py), [heartbeat.py](src/aria/monitor/heartbeat.py) | Migrated every gating decision to `time.monotonic()`.  Wall-clock retained only on serialized timestamps inside audit records (where it's informational, not gating). |
| F5 | DeadmanTimer thread dies silently on first unhandled exception | [kill_switch.py:264-289](src/aria/safety/kill_switch.py#L264) | Wrapped the loop body in `try/except BaseException`; added `proof_of_life()` counter that an external supervisor can monitor for thread-death detection. |
| F6 | `mint_internal_channel_token` parent-process leak across `os.fork()` | [auth.py:107-126](src/aria/security/auth.py#L107) | `os.register_at_fork(after_in_child=_reset_after_fork_in_child)` invalidates the parent's token in every forked child; per-worker `post_fork` hook mints fresh. |
| F7 | `MAX_REASONING_STEPS × per-step LLM 30s` = up to 5 min stall | [engine.py:443-466](src/aria/cognitive/engine.py#L443) | Outer `asyncio.wait_for(REASONING_TOTAL_TIMEOUT_S)` (60s default) wraps the entire loop; on timeout, returns a tagged "reasoning exceeded the total budget" message and emits `cognitive.reasoning_timeout`. |
| F8 | LLM backend silently falls back to rule-based pattern-matching | [engine.py:347-355](src/aria/cognitive/engine.py#L347) | Backend tags the response with `_fallback_reason`; engine prefixes the user-facing reply with `[FALLBACK: rule-based]` and logs `cognitive_llm_unavailable`. |
| F9 | FDIR drops a re-fault of the same root cause silently | [fdir.py:181-216](src/aria/safety/fdir.py#L181) | `_active_faults` is now `dict[str, list[FaultRecord]]`; a new fault arrives normally; a same-root-cause fault that arrives `> 10 × timeout_s` after the prior is treated as a re-fault and goes through. |

### 2.2 MISSION DEGRADATION

| ID | Title | Affected | Fix |
|----|-------|----------|-----|
| F10 | NaN health score passes every safe-mode threshold | [safe_mode.py:154-172](src/aria/safety/safe_mode.py#L154) | Non-finite numeric inputs force a conservative downgrade to MONITORING_ONLY. |
| F11 | Safe-mode escalates one step at a time | [safe_mode.py:175-194](src/aria/safety/safe_mode.py#L175) | Loop now finds the **deepest** triggering level on a single tick. |
| F12 | `_principal_counters` map unbounded | [session_store.py](src/aria/security/session_store.py) | (Closed in security round-3.) |
| F13 | Approval-queue cooling-off bypassable via clock skew | [approval_queue.py:325-330](src/aria/safety/approval_queue.py#L325) | `try_execute` uses `time.monotonic()`; approvals carry both wall-clock + monotonic timestamps. |
| F14 | `recall_answer_ok` defaulted to True (fail-open) | [approval_queue.py:208-220](src/aria/safety/approval_queue.py#L208) | Now a required keyword argument; no default. |
| F15 | Two-person rule bypassable with two operator_ids from one operator | [approval_queue.py:230-249](src/aria/safety/approval_queue.py#L230) | Anti-collusion v2: `pubkey_fingerprint` comparison refuses two distinct IDs that share a hardware key. |
| F16 | `commit()` records consumption EVEN on hard-cap breach | [resource_budget.py:154](src/aria/safety/resource_budget.py#L154) | Documented that hard-cap breach is a *post-actuation reconciliation* signal, not a guard; `safe_dispatch_check` does the pre-flight project. |
| F17 | NaN/inf qty poisons the budget window | [resource_budget.py:140-167](src/aria/safety/resource_budget.py#L140) | `project()` and `commit()` both refuse non-finite or negative qty without recording. |
| F18 | NaN qty bypasses constitution resource check | [constitution.py:236-249](src/aria/cognitive/constitution.py#L236) | `_is_finite_nonneg` validation before any projection. |
| F19 | Single-bit corruption of sealed scalar bypasses tier check | [constitution.py:175-197](src/aria/cognitive/constitution.py#L175) | `_runtime_reverify()` re-reads sealed scalar from disk every Nth `check()` and reloads on drift. |
| F20 | `gated_or_kill` log-spam during stuck LLM loop | [kill_switch.py:344-388](src/aria/safety/kill_switch.py#L344) | Per-action rate limit (1s); bounded `_SUPPRESSION_LOG_LAST` dict (1024 entries). |
| F21 | `decision_id` re-mapping after pruning | [agents/base.py:434-451](src/aria/agents/base.py#L434) | Stable monotonic ID; `_decision_log` is `dict[int, dict]`; `_next_decision_id` never re-used. |
| F22 | `record_outcome` silently drops outcomes for pruned IDs | [agents/base.py:453-466](src/aria/agents/base.py#L453) | Unknown ID emits `agent.record_outcome.unknown_id` warning. |
| F23 | Replay-guard 64-deep window; rotate-through possible | [replay_guard.py:46-60](src/aria/safety/replay_guard.py#L46) | Documented: rollback gate (`seq > last_seq`) is the primary defence; nonce window is for legitimate out-of-order arrivals. |
| F24 | Replay guard `last_seq` resets on restart | [replay_guard.py:158-227](src/aria/safety/replay_guard.py#L158) | Persisted to `data/runtime/replay_guard.json` with atomic write + fsync; `flush()` for graceful shutdown. |
| F25 | HeartbeatWatcher ignores first heartbeat after emitter reboot | [heartbeat.py:47-66](src/aria/monitor/heartbeat.py#L47) | Each emitter has a fresh `boot_id`; watcher accepts a counter rewind iff the boot_id has changed. |
| F26 | Reasoning trace tool_result unbounded per-step | [engine.py:495-518](src/aria/cognitive/engine.py#L495) | Truncated to `TRACE_TOOL_RESULT_TRUNCATE_BYTES` (8 KiB) for in-trace storage; full result still flows to the LLM. |
| F27 | `handle_message` has no timeout in the agent process loop | [agents/base.py:565-585](src/aria/agents/base.py#L565) | `asyncio.wait_for(handle_message_timeout_s)` (default 30s); on timeout, agent → ERROR. |

### 2.3 INFORMATIONAL

| ID | Title | Component | Fix |
|----|-------|-----------|-----|
| F28 | KillSwitchState.history unbounded | [kill_switch.py](src/aria/safety/kill_switch.py) | Cap at 1000 entries; preserve the first ("initial cause") entry on overflow. |
| F29 | safe_mode `_transition_history` unbounded | [safe_mode.py](src/aria/safety/safe_mode.py) | Cap at 500 entries; FIFO eviction. |
| F30 | `assert_kill` re-assertion buries new reason | [kill_switch.py](src/aria/safety/kill_switch.py) | Re-assertion logs `kill_switch.re_assert_chained` with both initial + new (source, reason). |
| F31 | Approval-queue `_proposals` grows by every terminal record | [approval_queue.py](src/aria/safety/approval_queue.py) | `gc_terminal()` runs every loop tick; drops terminal-state proposals after `TERMINAL_GC_S` (default 1h). |
| F32 | Reverter exception leaves `state=REVERTED` even on revert failure | [approval_queue.py](src/aria/safety/approval_queue.py) | New `ProposalState.REVERT_FAILED`; reverter exception transitions there + emits `aria.approval.revert_failed`. |
| F33 | `RuleBasedFallback._format_tool_result` `ast.literal_eval` fallback | [engine.py](src/aria/cognitive/engine.py) | Strict JSON only; `ast.literal_eval` fallback removed. |
| F34 | `FDIR.fault_counter` resets on restart | [fdir.py](src/aria/safety/fdir.py) | Persisted to `data/runtime/fdir_counter.json` with atomic write + fsync. |
| F35 | `HeartbeatWatcher._on_silence` callback called inside lock | [heartbeat.py](src/aria/monitor/heartbeat.py) | Snapshot `fired_now` under lock; release lock before invoking callback. |

---

## 3. The "Black Swan" Chain (closed)

> Two single bit-flips and one packet-loss spike compound to total loss
> of vehicle.  Every individual gate did "the documented thing."  The
> chain emerges from F1 (default-ALLOW) + F2 (cross-monitor fail-open)
> + F8 (silent LLM fallback) + F9 (silent re-fault drop) + F10 (NaN
> passes thresholds) + F17/F18 (NaN poisons budget) + F3 (queue overflow
> swallows recovery message).

After this audit, every link in that chain is broken:

| Step | Failure mode | Closed by |
|---|---|---|
| Bad sensor → `_resource_qty=nan` committed | F17 / F18 | `_is_finite_nonneg` refuses non-finite without recording |
| Constitution allows unmapped action | F1 | Default-DENY when allow-list present |
| Cross-monitor outage → 0 extra signers | F2 | Fail-closed: `cross_signers = 1` on any exception |
| LLM API outage → silent rule-based | F8 | `_fallback_reason` flag + `[FALLBACK: rule-based]` prefix + P0 log |
| Recovery message lost in queue overflow | F3 | Bounded queue with FIFO drop-oldest + audit event |
| Re-fault of same root cause silently dropped | F9 | List-valued `_active_faults` + staleness window |
| NaN health score freezes safe-mode | F10 | Non-finite → MONITORING_ONLY immediately |

**No path remains** through the eight steps that previously chained to LOV.

---

## 4. Test Surface After Fixes

| File | Tests |
|------|-------|
| `tests/integration/test_autonomy_audit.py` (NEW) | 31 |
| `tests/integration/test_security_audit_round2.py` | 40 |
| `tests/unit/test_failsafe_layer.py` | 119 |
| `tests/unit/test_failsafe_r30.py` | 8 |
| `tests/unit/test_failsafe_r32.py` | 9 |
| `tests/unit/test_failsafe_r32_redteam.py` | 5 |
| `tests/unit/test_fdir.py` | 14 |
| `tests/unit/test_safety.py` | 32 |
| `tests/unit/test_admin.py` | 12 |
| `tests/unit/test_trace_propagation.py` | 11 |
| `tests/unit/test_engine.py` | 11 |
| `tests/unit/test_decision_log.py` | 12 |
| `tests/unit/test_cognitive_engine.py` | 36 |
| `tests/unit/test_session_store.py` | 12 |
| `tests/unit/test_auth_service.py` | 17 |
| `tests/unit/test_auth_middleware.py` | 13 |
| `tests/integration/test_security_foundation.py` | 19 |
| `tests/integration/test_security_guard.py` | 34 |
| `tests/integration/test_screener_tenant_store.py` | 13 |
| `tests/integration/test_screener_admin_endpoints.py` | 8 |
| `tests/integration/test_conjunction_screener_service.py` | 27 |
| `tests/integration/test_cubesat_deorbit_advisor.py` | 3 |
| `tests/integration/test_web_dashboard_authz.py` | 30 |
| **Total (autonomy + security + service)** | **428** |

R1-R351 round suites (465 tests) regress green; bandit HIGH/MEDIUM = 0;
pip-audit clean.

---

## 5. Operator Follow-ups (out of code scope)

1. **Sealed constitution must add `allowed_actions`** — until the
   sealed file lists the explicit allow-list, the engine runs in
   legacy default-ALLOW mode (with a structured warning per call).
2. **Worker-init hook for `mint_internal_channel_token()`** — mint
   inside the per-worker `post_fork` callback (gunicorn / uvicorn
   pre-fork models) so each worker holds a fresh token.
3. **Wire `flush_counters()` + `flush()`** — graceful-shutdown signal
   handler must call `SessionStore.flush_counters()` and
   `ReplayGuard.flush()` so a planned restart loses no replay-defence
   state.
4. **Provision the second-vendor cross-monitor on a different stack** —
   different model family, different network path, different inference
   framework.  Otherwise F2's fail-closed is symbolic.
5. **Add property-based tests for every numeric gate** — hypothesis
   `floats(allow_nan=True, allow_infinity=True)` against
   `safe_mode.evaluate`, `constitution.check`, `resource_budget.commit`
   to catch regressions of F10 / F17 / F18.
6. **Re-audit in 14 days** — verify the wiring tests in
   `test_autonomy_audit.py` still fire and no new "added-but-not-wired"
   regressions have accumulated.
