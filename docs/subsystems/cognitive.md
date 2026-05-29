# Cognitive engine — the reasoning loop above every subsystem

The cognitive engine is ARIA's single decision-making core. It receives a trigger (a Captain query, an anomaly event, or a periodic tick), assembles spacecraft context, invites an LLM to call tools from a 55-tool registry, passes every proposed action through the constitutional layer, and returns a final text response. It is the only subsystem that holds a live conversation with the crew; everything else computes and acts on its instruction.

The engine is deliberately modest about its own authority: it proposes, but it cannot authorise. Authorisation is the constitution's job.

---

## Where it sits in the architecture

The five-layer loop described in [`../../README.md`](../../README.md) maps directly onto the engine's call path:

1. **Propose** — `CognitiveEngine.reason()` calls the LLM backend with the sealed system prompt, spacecraft context, and the current tool-schema list. The LLM returns either a final text response or a structured tool call.
2. **Authorise** — before any tool call is dispatched, `safe_dispatch` in [`../../src/aria/cognitive/safe_dispatch.py`](../../src/aria/cognitive/safe_dispatch.py) runs the kill-switch check, then `Constitution.check()`, then the resource-budget pre-flight. A `DENY` or `GATE` verdict stops the call before it reaches the tool.
3. **Execute** — if every gate passes, `ToolRegistry.safe_invoke()` verifies the per-call F-6 capability token and hands the stripped parameters to the tool.
4. **Observe** — the tool result is sanitised, spotlight-wrapped, and fed back into the LLM conversation. The `HallucinationDetector` cross-checks the final response against active alerts and recent sensor readings.
5. **Record** — the full `ReasoningTrace` is appended to an in-process ring buffer (capped at 500 entries), the `DecisionLog` is updated for the operator dashboard, and an episode summary is written to the long-term `MemoryStore`.

The constitutional layer and the independent monitor (`src/aria/monitor/`) sit outside the cognitive engine's trust boundary. Compromising the engine leaves both intact.

---

## What's in the package

The package lives in [`../../src/aria/cognitive/`](../../src/aria/cognitive/) and contains **34 Python files totalling approximately 10,036 lines of code**.

**Core reasoning loop**

- **`engine.py`** — `CognitiveEngine`, `CognitiveEngine.reason()`, and the three LLM backend classes: `CloudLlmBackend` (uses the `anthropic` SDK, model id read from `ARIA_LLM_MODEL`), `RuleBasedFallback` (pattern-matching fallback, always available), and the abstract `LLMBackend` base. Also defines `ReasoningTrace`, `ReasoningStep`, and `ReasoningContext`. Hard step limit is 10; hard wall-clock budget is 60 s (`REASONING_TOTAL_TIMEOUT_S`).

- **`constitution.py`** — `Constitution`, the process-wide singleton authoriser. Reads a frozen deep-copy of the sealed JSON at first use. Exposes `check(action, params, trust_tier) → CheckResult` with verdicts `ALLOW`, `GATE`, or `DENY`. Tracks sliding-window resource consumption against hard/soft caps. Runs periodic runtime tamper-detection (`_runtime_reverify`) every 256 calls; fails closed if the re-read diverges from the in-memory copy.

- **`safe_dispatch.py`** — `safe_dispatch()` and `safe_dispatch_check()`, the single entry point for any agent that wants to act on an LLM-derived intent. Chains the kill switch, constitution, resource budget, cross-vendor monitor disagreement counter, and approval queue in order. Returns a `DispatchOutcome` without silently swallowing errors.

**Sealed boot (F-1)**

- **`sealed_prompt.py`** — `verify_and_load()` reads `data/sealed/MANIFEST.toml` at process start, hashes every listed file with SHA-256, and loads the system prompt and constitution JSON into `SealedContent` — a frozen dataclass whose nested dicts and lists are wrapped recursively in `types.MappingProxyType` / tuples so mutation attempts raise at runtime. Hash mismatch aborts boot with exit code 86.

**Untrusted-data isolation (F-2)**

- **`spotlight.py`** — `Spotlighter`, instantiated fresh per reasoning loop. Wraps tool results and any external data in XML-ish delimiters carrying a per-conversation 128-bit random nonce and a `TrustTier` label (`OPERATOR`, `LOCAL_SENSOR`, `EXTERNAL_API`, `THIRD_PARTY_CONTENT`). Detects delimiter-forgery attempts, Unicode bidi-control characters, and a list of common injection trigger phrases before wrapping. The `TrustTier` enum is defined here and imported by `constitution.py`.

**Capability tokens (F-6)**

- **`capability_token.py`** — `TokenMinter` and `TokenVerifier`. The minter issues a compact JSON token per tool call: `tool name + SHA-256 of canonical args + issued_at + expires_at + issuer + 128-bit nonce`, signed with HMAC-SHA-256. Default TTL is 30 s; maximum is 600 s. The verifier enforces tool-name match, args-hash match, expiry, valid signature, and one-shot nonce (nonces are blocklisted until expiry). The `_enforce_mint_rbac` method on `TokenMinter` enforces a hard rule: the agent role can never mint a `CONSENT`-tier or higher token without a named `Principal`, preventing AI self-elevation.

**Eval-vs-prod marker (F-11)**

- **`eval_marker.py`** — `mark_traffic(kind)` mints an `EvalMark` side-channel object, HMAC-signed with a process-local random secret, that is never serialised into the model's prompt. `SandbaggingDetector` tracks a rolling window of eval and production responses and raises `aria.safety.sandbagging_suspected` if refusal-rate gap, response-length z-score, or action-overlap Jaccard fall outside thresholds. Requires ≥30 samples of each kind before any verdict.

- **`sandbagging_v2.py`** — `SandbaggingDetectorV2`, a more sensitive second-generation detector. Adds chain-of-thought keyword scanning (patterns like "being tested", "hide my capabilities"), irreversible-action refusal-gap analysis, and error-admission-gap tracking. Signals `aria.safety.sandbagging_v2_suspected` only when ≥2 of its 6 independent signals trip and the suspect verdict persists across 3 consecutive report windows.

**Context management**

- **`context.py`** — `ContextWindowManager` builds a budget-constrained context block (8,000 token ceiling) for each reasoning session. Priority order: active anomalies and alerts (up to 2,000 tokens, severity-sorted), condensed system state (1,000 tokens), keyword-matched procedures (800 tokens), episodic memory recall (500 tokens). Anomaly tokens are never sacrificed for procedure or memory tokens.

**Output verification**

- **`hallucination.py`** — `HallucinationDetector` cross-checks the LLM's final response against: active CRITICAL/EMERGENCY alerts (flags calm-sounding phrases), tool-registry membership (flags unknown tool names the LLM referenced), physical plausibility bounds for common spacecraft metrics (temperature, pressure, SOC, altitude, etc.), and recent numeric sensor readings (flags divergence > 20 percentage points on battery SOC claims).

**Memory and learning**

- **`decision_memory.py`** — `DecisionMemory`, a SQLite-backed store for individual `DecisionRecord` entries and aggregated `DecisionPattern` rows. Patterns track success/partial/failure counts and a weighted success rate using 30-day exponential decay. `DecisionRecommender` surfaces the top-K historically successful actions for a given (subsystem, trigger) pair.

- **`decision_log.py`** — `DecisionLog`, a thread-safe ring buffer (400 entries) of every LLM Q&A roundtrip. Polled by `/api/ai/decisions` for the operator dashboard.

- **`action_log.py`** — `ActionLog`, a parallel ring buffer of concrete `ActionEntry` rows with statuses `advisory` or `executed`. Feeds the operator's action-oversight surface.

**Supporting modules**

- **`doctrine/loader.py`** — `DoctrineLoader` and `DoctrineBundle`. Loads JSON doctrine entries (flight rules, malfunction procedures, checklists, incident reports) from `data/doctrine/` and ranks them by TF-IDF-like keyword intersection for prompt injection. Budget-capped at 4,000 characters.

- **`action_executor.py`** — `parse_recommendation(text)` extracts structured `ActionIntent` objects from LLM free text using regex patterns covering `throttle_engine`, `shed_load`, `safe_mode`, `schedule_maneuver`, `vent_tank`, `pressurize_cabin`, `set_setpoint`, `switch_antenna`, `attitude_hold`, `boost_scrubber`. Used by domain agents in their `on_reasoning_response` handlers.

- **`gemini_advisor.py`** — `GeminiAdvisor`, a secondary cloud-LLM advisor using the `google-genai` SDK. Reads model ids from `ARIA_GEMINI_MODELS` (comma-separated, ranked). Rotates across models on 429/503, with a 65 s cooldown per model. Used as an alternative advisory path when `ANTHROPIC_API_KEY` is not set. The 6 s per-call cap is an engineering UX budget, not a published number.

- **`self_improvement.py`** — `SelfImprovementEngine`, which tracks per-model prediction accuracy (TP/FP/TN/FN, precision, recall, F1, false-alarm rate) and decision-outcome history. `evolve(mission_year)` runs a review cycle at most once per 50 mission years and produces threshold-adjustment suggestions. In the current prototype this produces suggestions only — it does not mutate any detector threshold autonomously.

- **`eval_marker.py`** (shared), **`sandbagging_v2.py`** (above), **`code_audit/`** (static code analysis utilities), **`llm_eval/`** (eval harness + 100+ scored scenarios), **`fine_tuning/`** (LoRA scaffold for on-device fine-tuning, requires optional HuggingFace PEFT/Transformers deps).

---

## Key design decisions

**The engine only proposes; it never authorises.** The LLM output drives a structured tool call, not a raw actuation command. Every call passes through `ToolRegistry.safe_invoke()`, which demands a valid F-6 capability token, and through `Constitution.check()`, which can refuse regardless of what the LLM said. This separation means a jailbroken or confused model can produce a harmful proposal without it executing — the constitution has no prompt surface to attack.

**The sealed system prompt is hash-verified, not just loaded.** `sealed_prompt.py` computes SHA-256 for every file listed in `data/sealed/MANIFEST.toml` before the engine ever reads them. A tampered prompt or constitution aborts boot with a distinct exit code (86) rather than silently running with modified rules. In production the sealed directory is mounted read-only; `ARIA_SEALED_DIR` can override the path for ground-test rigs.

**Tool results are untrusted by default.** Even though tools are first-party code, their output may embed telemetry that was corrupted, spoofed, or injected. `Spotlighter` wraps every tool result in nonce-bearing delimiters tagged `LOCAL_SENSOR` before it enters the LLM context, and the system-prompt addendum tells the model those regions are informational only. The nonce rotates per conversation, so an attacker embedded in a telemetry value cannot pre-forge a delimiter close.

**Capability tokens bind intent, not just identity.** HMAC-signing `tool + args_hash + expiry + issuer` at mint time and verifying at dispatch time means a token cannot be replayed for a different tool or with different arguments. The one-shot nonce blocklist prevents replay within the token's window. The `agent` role hard-cap prevents the engine from minting `CONSENT`-or-higher tokens for itself — the AI cannot escalate its own authority.

**Model-agnostic by construction.** `CloudLlmBackend` is one concrete implementation of the `LLMBackend` abstract class. `RuleBasedFallback` is another. `GeminiAdvisor` provides a third advisory path. The `fine_tuning/` subpackage contains a LoRA scaffold targeting small open-source models (Phi-3-mini, Mistral-7B, LLaMA-3.2-1B) as a roadmap item for on-device inference. Swapping backends requires no changes to the constitution, the token layer, or the tool registry.

---

## Failsafes implemented here

**F-1 — Sealed system prompt** (`sealed_prompt.py`): SHA-256 manifest verification at process start, deep-frozen `SealedContent` (nested `MappingProxyType`), boot-abort on any mismatch. The `Constitution` class calls `get_sealed()` lazily; `_runtime_reverify()` re-reads and re-compares the `min_tier_for_safety_critical` scalar every 256 `check()` calls and fails closed if the on-disk and in-memory copies diverge.

**F-2 — Spotlighted untrusted data** (`spotlight.py`): per-conversation random nonce in XML-like delimiters; Unicode NFC normalisation; bidi-control and injection-trigger scanning; base64 encoding mode for highest-trust contexts; forgery detection (any pre-existing delimiter in the input is substituted and flagged). The cognitive engine appends the nonce-bearing `system_prompt_addendum()` to the sealed prompt at conversation start.

**F-3 — Constitutional layer** (`constitution.py`): `check(action, params, trust_tier) → CheckResult` with verdicts ALLOW / GATE / DENY. Rule evaluation order: (1) forbidden-actions hard list, (2) projected post-state predicates (four physical end-states: crew-quarters depressurisation, ECLSS shutdown, kill-switch unreachability, audit disable), (3) trust-tier minimum for safety-critical actions, (4) resource sliding-window ceiling projection, (5) gated-action list, (6) explicit allowed-actions list with default-DENY fallback. Production deployments that omit `allowed_actions` run in a legacy default-ALLOW mode and receive a structured warning per call.

**F-6 — Per-tool capability tokens** (`capability_token.py` + `tools/registry.py`): every LLM-derived tool call minted with HMAC-SHA-256 at `CognitiveEngine._reason_inner()` and verified at `ToolRegistry.safe_invoke()` before the tool is invoked. Token carries tool name, SHA-256 args hash, TTL (default 30 s, maximum 600 s), issuer identity, and a 128-bit nonce. The `agent` role is barred from minting `CONSENT`-tier or higher tokens regardless of permission table; this is the AI self-elevation firewall. If token minting fails for any reason, the engine surfaces a structured error to the LLM rather than falling back to an unguarded call.

**F-11 — Eval-vs-prod cryptographic marker** (`eval_marker.py`, `sandbagging_v2.py`): `EvalMark` objects are HMAC-signed with a process-local random secret and never serialised into the model's context. `SandbaggingDetector` (v1) and `SandbaggingDetectorV2` (v2) track rolling windows of eval and production responses. V2 extends V1 with chain-of-thought keyword scanning, irreversible-action refusal-gap analysis, and a persistence requirement (suspect verdict must appear in 3 of the last 5 report windows before an alert is published). Both publish to `aria.safety.sandbagging_suspected` / `aria.safety.sandbagging_v2_suspected`.

---

## Current limitations

**Cloud-LLM dependency.** The reference build calls the Anthropic API over a ground relay. Deep-space autonomy needs onboard inference; the `fine_tuning/` scaffold shows the intended path (small open-source models via LoRA), but no on-device inference path is wired in the current prototype. `RuleBasedFallback` ensures the spacecraft always responds, but pattern-matched responses are substantially less capable than LLM-guided ones.

**Principal threading is partially complete.** The F-6 RBAC path that restricts which tiers an agent-role principal can mint requires a `Principal` object to be threaded from the reasoning context into the token minter. The code includes the threading and a structured fallback warning, but the `agent` role's `mint_token.<tier>` permissions are not yet populated in the sealed `data/sealed/permissions.v1.toml`. Until that permissions entry is created, all non-CONSENT-tier mints flow through a legacy no-principal path that carries a logged warning.

**Hallucination detection is heuristic.** The four checks in `HallucinationDetector` (alert contradiction, unknown-tool reference, physical plausibility, sensor-reading divergence) catch obvious failures but are not a substitute for a semantic entailment model. False negatives are expected on subtly wrong factual claims.

**`SelfImprovementEngine` produces suggestions only.** The `evolve()` cycle computes threshold-adjustment recommendations but does not mutate any detector parameter. Closed-loop adaptation is a roadmap item.

**Token count is estimated.** `ContextWindowManager` approximates token usage at 1 token per 4 characters. On typical spacecraft telemetry text this is reasonable but not exact; some context windows will silently exceed the 8,000 token budget passed to the LLM.

**Sandbagging detectors need calibration data.** Both `SandbaggingDetector` and `SandbaggingDetectorV2` require ≥30 paired samples of each traffic kind before any verdict is computed. The thresholds (refusal-gap 0.15, length z-score 3.0, action-overlap 50 %) were set conservatively pending a calibration corpus; they should be revisited once the system accumulates real operational data.

**The codebase carries ~904 `# ESTIMATE` tags** across `src/aria/` (noted in the README). Several constants in the cognitive package — notably the `_CALL_TIMEOUT_S` cap in `gemini_advisor.py` — are labelled as UX budgets rather than published engineering numbers.

---

## Where to start reading

1. **[`../../src/aria/cognitive/engine.py`](../../src/aria/cognitive/engine.py)** — `CognitiveEngine._reason_inner()` is the main loop. Read the token-mint block (~line 540), the spotlight-wrap block (~line 665), and the hallucination-verify block (~line 707) to see the three in-loop failsafes.

2. **[`../../src/aria/cognitive/constitution.py`](../../src/aria/cognitive/constitution.py)** — `Constitution.check()` is the authorisation entry point. The post-condition predicates (~line 236) and the forbidden-actions short-circuit (~line 342) illustrate the "deny on physical end-state, not just action name" design.

3. **[`../../src/aria/cognitive/sealed_prompt.py`](../../src/aria/cognitive/sealed_prompt.py)** — `verify_and_load()` shows the complete boot verification path: manifest parse, file hashing, frozen content construction.

4. **[`../../src/aria/cognitive/capability_token.py`](../../src/aria/cognitive/capability_token.py)** — `TokenMinter.mint()` and `TokenVerifier.verify()`. The `_enforce_mint_rbac` method (~line 186) is the AI self-elevation firewall; `TokenVerifier.verify()` (~line 337) shows the one-shot nonce blocklist.

**Relevant tests:**

- `tests/unit/cognitive/` — unit tests for individual cognitive modules
- `tests/unit/test_cognitive_engine.py` and `tests/unit/test_engine.py` — engine loop behaviour under various backend conditions
- `tests/integration/test_cognitive_pipeline.py` — end-to-end scenario through the full propose → authorise → execute path
