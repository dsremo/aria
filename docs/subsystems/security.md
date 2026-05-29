# Security & guard library — layered, fail-closed defence from session auth to adversarial AI

The `aria.security` package is the largest in the codebase: **387 Python files across three directories** — 30 foundation modules in `security/`, 352 adversarial guard plugins in `security/rounds/`, and 5 supply-chain tools in `security/supply_chain/`. Together they implement four layers of protection (human attacker → quantum-class adversary), every failsafe in the `F-4 / F-6 / F-8 / F-19` cluster, and a large body of domain-specific checks that span prompt injection, capability-token forgery, confused-deputy, and influence/psyops detection.

The single public entry point is `from aria.security.guard import …` or `from aria.security import …`.

---

## Where it sits in the architecture

```
                 ┌─────────────────────────────────────────────┐
Operator / UI    │  F-9 console · F-14 two-person rule          │
                 └───────────────────────┬─────────────────────┘
                                         │  session + per-action auth
                 ┌───────────────────────▼─────────────────────┐
Cognitive        │  Constitution · sealed prompt (F-1)          │
engine (LLM)     │  Capability token minting (F-6)              │
                 └───────────────────────┬─────────────────────┘
                                         │  capability token + command
          ┌──────────────────────────────▼──────────────────────────────┐
Security  │  guard library · per-actuator rate limit + circuit breaker  │
package   │  CommandAuthenticator · TOCTOU/nonce/seq (F-19)             │
(this doc)│  execution guard plugins (rounds/)                          │
          └──────────────────────────────┬──────────────────────────────┘
                                         │  audited commands
          ┌──────────────────────────────▼──────────────────────────────┐
Audit     │  hash-chained AuditLog (F-8) · AuditBusMirror               │
chain     │  audit_downlink (hourly Ed25519-signed head-hash anchor)     │
          └─────────────────────────────────────────────────────────────┘
```

The security package wraps the **execute** and **record** stages of the five-stage loop (propose → authorise → execute → observe → record). It sits below the cognitive engine and above raw actuator dispatching. An untrusted payload that clears the constitution still has to pass `CommandAuthenticator`, capability-token verification, the rate-limit/circuit-breaker, nonce deduplication, and the guard plugin chain before any command reaches hardware. Every decision, block, or alert is written to the hash-chained audit log.

The package is deliberately **not** the only layer. The constitution (`src/aria/cognitive/constitution.py`) and the independent monitor (`src/aria/monitor/`) sit outside and above it. Loss of the security package alone does not silence the monitor or break the sealed constitution.

---

## What's in the package

### Foundation modules (30 files)

**Audit chain**
- `audit.py` — `AuditLog`: hash-chained, append-only JSONL store. Every entry commits `sha256(prev_hash ‖ canonical_bytes)`. Thread-safe, genesis-initialised, restores and re-verifies the chain at load; emits `aria.security.audit_chain_break` on tamper.
- `audit_bus_mirror.py` — `AuditBusMirror`: subscribes to the process event bus (`aria.security.*`, `aria.safety.*`, `aria.approval.*`, `aria.kill_switch.*`, etc.) and mirrors every matching event into the chain without polling. Failures surface `aria.security.audit_mirror_failed` so FDIR can react.
- `audit_downlink.py` — hourly Ed25519-signed `aria.security.audit.head_anchor` event; `GroundAttestChecker` flags missing anchors (> 1.5 × interval). Reference: RFC 9162 Certificate Transparency head-hash pattern.
- `audit_trace.py` — trace-context correlation: every log entry auto-fills the active `trace_id` propagated by `trace_context.py`.

**Capability tokens and operator auth**
- `per_action_auth.py` — `PerActionChallenge`: issues fresh 32-byte OS-random challenges per action, binds `sha256(challenge_id ‖ action ‖ args_hash ‖ issued_at ‖ principal_id)`, verifies Ed25519 signatures, maintains a TTL-evicted used-nonce set persisted to `data/runtime/per_action_used.json` across restarts. Mission-phase-aware challenge windows (LEO 120 s → outer-planetary 3600 s ceiling, per JPL DSN810-005-200 one-way light times).
- `auth.py` — `CommandAuthenticator`: four-factor session + command auth: (1) session bound to issuer server-side, (2) strict-monotonic counter (counter ≤ last → `REJECTED_REPLAY`), (3) bounded clock-skew timestamp (`[-30 s, +1 h]`; signed window, not `abs()`), (4) HMAC-SHA256 signature over command data. Internal-channel fast-path uses a one-shot process-only 256-bit token via `mint_internal_channel_token()` / `verify_internal_channel_token()` (one-shot: second call to mint raises `RuntimeError`; fork-safe via `os.register_at_fork`).
- `auth_service.py` — login/challenge/logout service layer; rate-limits challenge issuance (30/min) with 50 k-entry LRU cap; `principal_from_session` rejects sessions whose pubkey-fingerprint diverges from the stored principal record.
- `session_store.py` — `SessionStore`: client-binding (IP hash + UA hash, `hmac.compare_digest`); per-principal monotonic counters persisted to `session_counters.json` so F-19 survives restarts; revocation log stores `sha256(token)` only.
- `principals.py`, `secret_roles.py` — RBAC with authority ceilings; HKDF-SHA256 per-role subkey derivation so a leaked role key does not expose sibling roles.

**Input guard library**
- `guard.py` — the unified one-import surface. Provides: `safe_open_url` (SSRF block + DNS-resolution check + host allowlist + streaming size cap); `safe_xml_fromstring` / `safe_xml_parse` (XXE/billion-laughs via defusedxml); `safe_json_loads` (depth + byte cap); `safe_zip_extract` / `safe_zip_open` (zip-slip + decompression bomb); `safe_pickle_block` (always raises); `safe_yaml_load` (safe_load only); `sanitise_for_log` (CRLF + bidi-control strip, CWE-117 / CVE-2021-42574); `mfa_admin_check` (HMAC-based two-factor gate); `harden_aiohttp_app` (request-ID, method allow-list, body-size, security headers, adaptive scorer, honeypot routes — one call wires everything); `runtime_check_environment` (boot-time fail-closed check: refuses `ARIA_AUTH_REQUIRED=0`, wildcard CORS, `0.0.0.0/0` trusted proxy, missing tenant HMAC key in production).
- `sanitizer.py` — `InputSanitizer` (SQL, XSS, path-traversal, SSRF pattern match); `ToolResultSanitizer` (prevents prompt injection via tool telemetry; calls `psyops.detect_influence` internally).
- `hardening.py` — layered OWASP-mapping input validation (`InputValidator`).

**Behavioural and adversarial**
- `adaptive.py` — `BehaviourFingerprinter` + `score_request`: Shannon entropy, Markov chain novelty, CUSUM-style velocity scoring; pluggable via `register_request_scorer`. Returns a `ThreatScore` with block/alert thresholds.
- `psyops.py` — `detect_influence`: per-Cialdini-axis scoring (authority, scarcity, reciprocity, commitment, social proof, liking) across English phishing and LLM jailbreak pattern banks. Used by `ToolResultSanitizer` and `make_adaptive_middleware`.
- `honeypot_llm.py` — `HoneypotRegistry`: mints short-lived decoy tokens; `scan_for_decoys` checks outbound responses for token leakage (exfiltration check in `make_adaptive_middleware`).
- `anomaly.py` — `AnomalyDetector`: CUSUM command-velocity, Shannon entropy, Poisson regularity.
- `canary.py` — `CanaryRegistry` + `HoneypotResponder`: URL honeypots, scanner-signature detection.

**Cryptography and identity**
- `pqc.py` — `HybridKEM` (X25519 + MLKEM-768 when available, SHA3-256 KDF); `SymmetricEncryptor` (AES-256-GCM); `SignatureScheme` (Ed25519 + composite ML-DSA-65 upgrade path); `constant_time_compare`.
- `zero_trust.py` — `ZeroTrustGuard`: every inter-service call carries a signed `ServiceToken`; replay protection via sequence numbers.
- `attestation.py` — software PCR + HMAC-chain-of-trust; on real flight hardware a TPM-bound AK replaces the file-backed key.
- `pqc.py`, `audit_downlink.py` — Ed25519 signer used for both attestation quotes and downlink anchors; single key rotation re-keys both.
- `middleware.py` — aiohttp auth + route-permission middleware; deny-by-default sentinel for unmapped routes; production refuses `enforced=False` at construction.
- `env.py` — `is_production()` single truth-point; `trace_context.py` — `contextvars`-based trace-id propagation.
- `integrity_monitor.py`, `evolve.py` (CISA KEV feed), `admin.py`, `worker_init.py`.

**Supply chain (5 files)**
- `supply_chain/sbom.py`, `creds_scan.py`, `vuln_gate.py` — CycloneDX SBOM generation, credential scanning, CVE gate.

### Guard plugin library (352 files in `security/rounds/`)

`rounds/` contains one module per adversarial scenario, each self-registering a `DefencePlugin` into the in-process `_Registry` via `register(...)`. The registry fires hook points — `on_request`, `on_response`, `on_outbound_url`, `on_audit`, `on_score` — at the right moment in every request cycle. Plugins are loaded by calling `guard.activate_all_rounds()`, which imports each module and triggers its self-registration.

The library covers, among many others: credential stuffing, token-leak detection, JWT `alg=none`, IDOR, OAuth-state CSRF, mass assignment, parameter pollution, anti-replay nonces (`r08`), geo-anomaly, sealed audit, redos limiting, prompt-injection scenarios, capability-token forgery simulation, confused-deputy simulation, spoofing detection, TPM attestation stubs (`r102`), HSM/PKCS11 integration (`r103`), post-quantum KEM (`r61`), WebAuthn/FIDO2 (`r62`), TOTP, step-up auth, session binding, JIT access, buffer overflow hints, seccomp profile, DNS rebinding, HTTP smuggling v2, mTLS, NIST 800-53 mapping (`r162`), immutable-log enforcement (`r98`), kill-switch (`r99`), constitutional red-team (`r190`), memory forensics (`r192`), file-integrity monitoring (`r194`), and more through `r351+`.

---

## Key design decisions

**Why a deep stack of overlapping checks rather than one gate?**

A single tightly-coupled gate is also a single bypass. The README states the rationale directly: F-1 (sealed prompts) and F-6 (capability tokens) both block "engine emits a forbidden tool call", but via different mechanisms. Compromising one still leaves the other. The security package alone has four independent barriers on the command path: session auth, capability-token verification, per-actuator rate limit, and nonce deduplication. A replay of a captured token still fails nonce deduplication even if somehow the HMAC check were bypassed. A confused-deputy substitution still fails because the capability token binds `tool + args_hash + expiry + issuer` in a single HMAC.

The cost is more code surface. The benefit is that no single bypass collapses the system.

**Why per-call capability tokens (HMAC-Ed25519) rather than an engine-level permission matrix?**

Once a command is dispatched through middleware — logging, metrics, retries, queuing — the original caller-identity context can be lost. Per-call tokens bind `tool + args_hash + expiry + issuer + nonce` cryptographically, so any downstream layer can re-verify authorisation without trusting upstream. The token at `src/aria/cognitive/capability_token.py` is minted by the planner for each tool call with a 30 s TTL (configurable up to 600 s). The tool registry verifies it before dispatch. If the token is expired, has an args mismatch, or has already been redeemed, the call is rejected with `ScopeMismatch`.

**Why an off-process audit collector?**

The hash chain alone proves tampering after the fact, but only if the chain itself survives. A process that holds both the log and the write key could in principle re-sign a rewritten chain from a compromised position. The architectural intent (FAILSAFE_ARCHITECTURE.md §F-8) is an off-process collector that receives audit events via write-only UDP, writes to a separate noexec filesystem, and produces periodic Merkle roots for the operator console. The current implementation provides the in-process hash chain, the `AuditBusMirror` subscriber, and the `audit_downlink` anchor publisher (hourly Ed25519-signed head hash visible to ground). The full off-process collector is identified as a gap in FAILSAFE_ARCHITECTURE.md §F-8.

**Why one-shot internal channel tokens?**

`mint_internal_channel_token()` in `auth.py` can be called exactly once per process — a second call raises `RuntimeError`. Verification returns a `bool` only, never the bytes. This closes the class of attack where a debug endpoint, sandboxed Python environment, or deserialiser round-tripping through the auth module could retrieve the bypass key. The fork-safe hook (`os.register_at_fork`) invalidates the parent's token in the child so pre-fork worker models do not share bypass authority across worker boundaries.

---

## Failsafes implemented here

**F-4 — Per-actuator rate limit + circuit breaker**
Implemented in `src/aria/api/per_ip_rate_limiter.py` (sliding-window, per-source-IP, exponential backoff, persisted violation counters) and `src/aria/core/tool.py` (`ToolHealth`: 5 consecutive failures → `circuit_breaker_open = True` → 403 on dispatch; half-open recovery probe). The original monolithic `security/rate_limiter.py` was retired and consolidated there. Three successive denials trigger a P1_CRITICAL operator alert.

**F-6 — Capability tokens**
`src/aria/cognitive/capability_token.py`. `TokenMinter.mint(tool, args, ttl_s=30)` produces an HMAC-signed `CapabilityToken`; `verify_token(token, expected_tool, args)` checks expiry, args-hash, and signature. Agent role cannot mint `CONSENT`-or-higher authority tokens (hard cap in `_enforce_mint_rbac`). The issuer field binds to the principal, not a caller-supplied string.

**F-8 — Hash-chained audit log**
`src/aria/security/audit.py` (`AuditLog`): SHA-256 hash chain, `data/runtime/audit.jsonl`, append-only, verified at boot. `src/aria/security/audit_bus_mirror.py`: in-process subscriber feeds every safety/security/approval/emergency bus event into the chain. `src/aria/security/audit_downlink.py`: hourly Ed25519-signed anchor downlink; `GroundAttestChecker.is_overdue()` fires at 1.5 × interval. Gap: the full off-process UDP collector with separate filesystem is design-described in FAILSAFE_ARCHITECTURE.md §F-8 but not yet implemented as a separate process.

**F-19 — TOCTOU + replay defence**
Three interlocking mechanisms: (1) `CommandAuthenticator` enforces strict-monotonic counter (counter ≤ last ⟹ `REJECTED_REPLAY`); (2) `rounds/r08_replay_nonce.py` provides `check_and_consume(nonce)` — an atomic in-memory nonce ledger with TTL eviction; (3) `PerActionChallenge` in `per_action_auth.py` uses a `_used` dict that survives restarts via `data/runtime/per_action_used.json`, closes the window atomically (check-then-set under lock), and covers the race case explicitly (`VerifyResult(False, "race: already redeemed")`). Resource budget gates are intended to use atomic compare-and-swap (FAILSAFE_ARCHITECTURE.md §F-19); the per-session monotonic counters in `session_store.py` are also persisted for F-19 continuity across restarts.

**Other failsafes with roots here**
- `per_action_auth.py` contributes to the NIST SP 800-63B AAL3 operator-auth path that backs F-9 (two-person rule) and F-14 (life-critical two-person rule).
- `pqc.py` hybrid KEM + Ed25519 signature scheme underpins F-17 / F-18 (sealed boot, hardware deadman).
- `guard.runtime_check_environment` is part of the F-1 / F-18 boot-time integrity pass.

---

## Current limitations

**Development key fixtures are public.** `tests/fixtures/dev_keys.json` ships Ed25519 seeds that are deterministic and therefore public. The README calls this out explicitly: any deployment connecting these to real hardware gives the world its signing key. Regenerate all key material from hardware sources before any non-test deployment.

**Internal channel token is in-memory only.** `mint_internal_channel_token()` generates a fresh 32-byte secret per process start. A process that restarts mid-mission loses the token and any in-flight commands signed with it will fail. This is intentional (no disk serialisation = no disk-based extraction) but requires a clean restart protocol.

**Off-process audit collector is not yet built.** The hash chain and the anchor downlink are implemented. The separate-process UDP receiver that writes to a noexec filesystem and produces Merkle roots — described in FAILSAFE_ARCHITECTURE.md §F-8 — is a documented gap.

**Several tunable constants are marked ESTIMATE.** `DEFAULT_ANCHOR_EVERY_N = 100` in `audit.py`, session idle/absolute lifetimes in `session_store.py`, and challenge nonce TTL in `auth_service.py` are marked `ESTIMATE` with no published source. Mission-specific tuning is expected before any operational use.

**Attestation key is file-backed by default.** `attestation.py` generates an Ed25519 key at `data/runtime/attestation_key.pem` on first boot. The module docstring explicitly notes: "a real flight build would replace this with a TPM-bound AK." The file-backed key provides software attestation only; hardware-rooted attestation requires integration with a physical TPM.

**Round modules in `rounds/` are in-process and in-memory.** Guard plugins do not persist across restarts. `activate_all_rounds()` must be called at startup. There is no dynamic reload path in production.

**TRL 3–5. Nothing has flown.** This is a research prototype. No claim of flight heritage, spaceflight qualification, or production-grade certification is made. All timing parameters, thresholds, and window sizes should be validated against real mission profiles.

---

## Where to start reading

**Entry files**
- `../../src/aria/security/__init__.py` — layered public API with the four-layer description.
- `../../src/aria/security/guard.py` — one-stop import surface; read `harden_aiohttp_app_v2` for the middleware wiring order.
- `../../src/aria/security/audit.py` — `AuditLog`, hash-chain design, `verify_at_boot`.
- `../../src/aria/security/auth.py` — `CommandAuthenticator`, `mint_internal_channel_token`.
- `../../src/aria/cognitive/capability_token.py` — F-6 token minting and verification.
- `../../src/aria/security/per_action_auth.py` — F-19 / FIDO2 per-action challenge.
- `../../src/aria/security/audit_downlink.py` — Ed25519-signed ground anchor downlink.
- `../../src/aria/security/plugins.py` — `DefencePlugin` registry; hook points.
- `../../src/aria/security/rounds/__init__.py` — `activate_all()` loader.

**Relevant tests**
- `../../tests/integration/test_security_foundation.py` — behavioural tests for the adaptive engine, honeypots, psyops detector.
- `../../tests/integration/test_security_guard.py` — SSRF, XML, JSON, ZIP, pickle, log-sanitiser, MFA, runtime-check.
- `../../tests/integration/test_security_audit_round2.py` — wiring tests for round-2 and round-3 hardening (one-shot mint, verifier-only retrieval, LRU caps, NAT-shared per-IP isolation, CORS/trusted-proxy boot checks).
- `../../tests/integration/test_security_rounds.py` through `test_security_rounds_v7.py` — round-by-round plugin coverage.
- `../../tests/unit/test_security.py` — unit tests for core primitives.

**Linked documents**
- `../THREAT_MODEL.md` — threat taxonomy (T-I-* through T-VII-*) this package addresses.
- `../FAILSAFE_ARCHITECTURE.md` — full F-1 … F-19 specification with gap analysis.
- `../SECURITY_ROUNDS_R51.md`, `../SECURITY_ROUNDS_R101.md`, etc. — per-batch guard library coverage summaries.
- `../../README.md` — "Safety architecture" section for the five-layer picture.
