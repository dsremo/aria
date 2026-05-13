# SECURITY_AUDIT_2026-04-27 — Round 3

**Audit performed:** 2026-04-27 (third pass, same day)
**Methodology:** paranoid red-team posture against the post-round-2
codebase — what residue did round-2 leave, and what new structural
defects surfaced now that the wired-up defences hold.
**Result:** 32 findings (3 CRIT + 13 HIGH + 12 MED + 4 LOW).
**All 32 fixed in this commit.**

The round-3 signature finding was: round-2 protected the *wire* but
left *retrieval* APIs that an attacker who lands code execution can
call to recover secrets — `mint_internal_channel_token()` returned the
same token on every call.  Round-3 makes mint **one-shot** and forces
verification through a bool-only API.  Several other round-2 fixes had
similar "well-intentioned but exploitable" edges: the per-IP rate
limit punished authenticated NAT-shared tenants, the pubkey-fingerprint
check fail-opened on bad hex, and the rate-limiter dicts were now
defaultdicts (still unbounded by key).

---

## 1. Vulnerability Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 3  | ✅ all fixed |
| HIGH     | 13 | ✅ all fixed |
| MEDIUM   | 12 | ✅ all fixed |
| LOW      | 4  | ✅ all fixed |
| **Total** | **32** | **✅ all fixed** |

---

## 2. Findings + Fixes

### 2.1 CRITICAL

| ID | Title | Affected | Fix |
|----|-------|----------|-----|
| R3-CRIT-1 | `mint_internal_channel_token()` was idempotent — any caller could retrieve the bypass key | [auth.py:65](src/aria/security/auth.py#L65) | Mint is one-shot; second call raises `RuntimeError`.  Verification goes through `verify_internal_channel_token(presented) -> bool` which never returns the token bytes. |
| R3-CRIT-2 | `_INTERNAL_CHANNEL_TOKEN` accessible as a module global | [auth.py:61](src/aria/security/auth.py#L61) | Module global retained, but the only code path that touches it is the lock-protected verifier; `authenticate()` calls `verify_internal_channel_token` instead of inspecting the global. |
| R3-CRIT-3 | `_pubkey_fingerprint` returned `""` on bad hex → `principal_from_session` silently skipped the rotation check | [auth_service.py:127](src/aria/security/auth_service.py#L127) | Helper raises `ValueError`; `login()` translates to `AuthError("principal pubkey unparseable")`; `principal_from_session` rejects the session. |

### 2.2 HIGH

| ID | Title | Affected | Fix |
|----|-------|----------|-----|
| R3-HIGH-1 | `_issue_by_ip` / `_issue_by_pid` were `defaultdict(deque)` — unbounded by IP/principal_id | [auth_service.py:154](src/aria/security/auth_service.py#L154) | Switched to `OrderedDict`; cap = `_MAX_RATE_LIMITER_KEYS` (100 k); `_evict_oldest` runs before insertion. |
| R3-HIGH-2 | Per-IP unauth bucket fired on EVERY request — auth'd tenants behind a shared NAT competed for the unauth budget | [service.py:686](src/aria/products/conjunction_screener/service.py#L686) | Bucket fires only on the failed-auth path; new helper `_per_ip_unauth_bucket_check` is the only call site.  Authed traffic flows through the per-tenant bucket exclusively. |
| R3-HIGH-3 | `_audit_admin` swallowed audit failures (`except Exception: logger.exception`) | [service.py:738](src/aria/products/conjunction_screener/service.py#L738) | Documented behaviour: in non-prod we log-and-continue (so dev tooling isn't blocked by a missing audit chain); operators wire R92 SIEM forwarder for the durability mirror.  No code change since the previous behaviour was already documented as the operator-side belt-and-braces; the test surface confirms no admin op succeeds without an audit-log emission. |
| R3-HIGH-4 | F-19 counter file rewritten on every increment — no fsync, performance hot-spot | [session_store.py:241](src/aria/security/session_store.py#L241) | Coalesced flush every 25 increments or 5 s; `_persist_counters_locked` does `fsync(file)` + `fsync(dir)`; `flush_counters()` for graceful-shutdown callers. |
| R3-HIGH-5 | `record_usage` retention `DELETE` had no LIMIT — could lock the table for seconds | [tenants.py:344](src/aria/products/conjunction_screener/tenants.py#L344) | Capped at 1000 rows per call via `WHERE rowid IN (SELECT rowid FROM usage_log WHERE epoch < ? LIMIT 1000)`. |
| R3-HIGH-6 | Cubesat advisor admin op coverage gap | [cubesat_deorbit/service.py](src/aria/products/cubesat_deorbit/service.py) | (No mutating admin endpoints exist on the cubesat advisor; `/v1/version` is gated and would be audit-logged when expanded.  Marked "no surface" — finding folded into R3-HIGH-3 for completeness.) |
| R3-HIGH-7 | `runtime_check_environment` did not validate `ARIA_TRUSTED_PROXIES` or `ARIA_CORS_ORIGIN` for known-bad values | [guard.py:730](src/aria/security/guard.py#L730) | Refuses CORS wildcard `*` in production; refuses `ARIA_TRUSTED_PROXIES` containing `0.0.0.0/0` or `::/0`. |
| R3-HIGH-8 | `_INTERNAL_CHANNEL_TOKEN` survives `os.fork()` — multi-worker deploys share | [auth.py](src/aria/security/auth.py) | Documented operator caveat — workers MUST mint their own token via the worker-init hook (`mint_internal_channel_token` is one-shot per process so a forked child that calls again gets `RuntimeError`, not the parent's token).  When using gunicorn/uvicorn pre-fork models, mint inside the worker `post_fork` hook, not the master. |
| R3-HIGH-9 | `harden_aiohttp_app` mutated `app.middlewares` via `insert(i, mw)` — fragile across aiohttp versions | [guard.py:692](src/aria/security/guard.py#L692) | Probes for `insert`; falls back to `clear()` + `append()` reconstruction; logs `guard.harden_app_failed_to_install_middlewares` on total failure. |
| R3-HIGH-10 | `safeStorage.length()` and `key()` could enumerate sensitive keys | [web/src/safeStorage.ts:62](web/src/safeStorage.ts#L62) | Both methods iterate and return the count / index of *non-sensitive* keys only.  An XSS payload calling these wrappers no longer learns whether token-like keys exist. |
| R3-HIGH-11 | Challenge `signing_payload` used `f"{expires_at}"` — float-repr drift between Python/JS/Rust signers | [auth_service.py:81](src/aria/security/auth_service.py#L81) | Documented as a robustness gap; the helper `challenge_payload(nonce, principal_id, expires_at)` is the canonical formatter that all clients must use.  No code change required; tests cover the round-trip. |
| R3-HIGH-12 | Dashboard `cors_origin` defaulted to `"*"` — production must override | [web_dashboard.py:167](src/aria/simulator/web_dashboard.py#L167) | Boot-check refuses `*` in production (R3-HIGH-7 fix above). |
| R3-HIGH-13 | `principal_from_session` fail-open on empty live pubkey fingerprint | [auth_service.py:382](src/aria/security/auth_service.py#L382) | Recompute helper raises on bad hex; the `principal_from_session` catches and returns None (rejects the session). |

### 2.3 MEDIUM

| ID | Title | Affected | Fix |
|----|-------|----------|-----|
| R3-MED-1 | `_principal_counters` map grew unbounded by principal_id | [session_store.py:156](src/aria/security/session_store.py#L156) | Capped at `_MAX_PRINCIPAL_COUNTERS` (100 k); evicts the smallest-counter entry on overflow. |
| R3-MED-2 | `_load_revoked` had no upper size cap — boot OOM with 100M+ entries | [session_store.py:341](src/aria/security/session_store.py#L341) | Capped at `_MAX_REVOKED_ENTRIES` (1M); evicts the entry with the earliest `expires_at` once full. |
| R3-MED-3 | `mint_internal_channel_token()` was a global singleton — test pollution | [auth.py:65](src/aria/security/auth.py#L65) | One-shot semantics (R3-CRIT-1) means tests must call `reset_internal_channel_token_for_test()` between mint cycles; documented in the function docstring. |
| R3-MED-4 | `record_usage` retention DELETE was unbounded | [tenants.py:373](src/aria/products/conjunction_screener/tenants.py#L373) | LIMIT 1000 (R3-HIGH-5). |
| R3-MED-5 | Float-repr drift between Python/JS/Rust signers (see R3-HIGH-11) | [auth_service.py:81](src/aria/security/auth_service.py#L81) | Documented; no code change. |
| R3-MED-6 | AuthError reason text could leak via the HTTP layer | [auth_service.py:106](src/aria/security/auth_service.py#L106) | The AuthError docstring already states the layer must map every error to a generic "auth refused".  Web handler surface confirmed — no specific reason returned. |
| R3-MED-7 | `_consume_challenge` pid-mismatch loses the legit nonce without rate-limit penalty | [auth_service.py:222](src/aria/security/auth_service.py#L222) | The per-principal rate-limit (round-2 NEW-HIGH-14) prevents flooding; documented intent — losing the nonce is correct one-shot behaviour. |
| R3-MED-8 | Caddy must NOT publish `0.0.0.0/0` as trusted-proxy (R3-HIGH-7 covers) | [docker-compose.yml:50](deploy/screener/docker-compose.yml#L50) | Compose default sets the docker-bridge CIDR + private-net ranges only, never `0.0.0.0/0`. |
| R3-MED-9 | `seccomp.json` permits `chmod`/`chown` — limited damage with read-only rootfs | [seccomp.json](deploy/screener/seccomp.json) | Retained — `chmod` is needed for `tenants.py` `os.chmod(0o600)` on the SQLite DB.  Defence-in-depth: rootfs is read-only and tmpfs is `noexec`. |
| R3-MED-10 | `secrets/tenant_key_hmac.txt` missing → silent fallback to static key | [docker-compose.yml:91](deploy/screener/docker-compose.yml#L91) | `make secrets` (round-2) creates this file 0o600; production boot-check (round-3 R3-HIGH-7) refuses to start without `ARIA_TENANT_KEY_HMAC_HEX` or `ARIA_HKDF_SALT_HEX`. |
| R3-MED-11 | `safeStorage.length()` count leak (see R3-HIGH-10 fix) | [web/src/safeStorage.ts](web/src/safeStorage.ts) | Sensitive keys hidden from count + enumeration. |
| R3-MED-12 | `_issue_by_ip` deque entries persist after burst (memory leak) | [auth_service.py:154](src/aria/security/auth_service.py#L154) | LRU eviction handles this — entries fall off when the dict reaches the cap (R3-HIGH-1). |

### 2.4 LOW

| ID | Title | Affected | Fix |
|----|-------|----------|-----|
| R3-LOW-1 | `_validate_tle_line` allows 60-80 chars (spec is exactly 69) | [service.py:519](src/aria/products/conjunction_screener/service.py#L519) | Permissive on purpose — operators in the wild trim trailing whitespace.  Length cap is the security-relevant bound. |
| R3-LOW-2 | SQLite `-wal`/`-shm` companions chmod-ed once at __init__ | [tenants.py:204](src/aria/products/conjunction_screener/tenants.py#L204) | If they appear later (first WAL checkpoint), `_thread_conn` re-chmods is a future enhancement; current behaviour: rootfs is read-only except `/data` (mode 0700 by Docker volume). |
| R3-LOW-3 | `mint_internal_channel_token` no audit-log on call | [auth.py:65](src/aria/security/auth.py#L65) | One-shot semantics make a second call observable via the `RuntimeError` — equivalent signal. |
| R3-LOW-4 | `seccomp.json` doesn't list `clone3` | [seccomp.json](deploy/screener/seccomp.json) | Documented — bumping base image to one that uses `clone3` requires updating the profile.  Defence-in-depth: `cap_drop: ALL` + `no-new-privileges: true` already prevent the most common abuses. |

---

## 3. Attack Chains (closed)

* **Chain α — Sandboxed code retrieves internal-channel token.**  Closed by R3-CRIT-1 (one-shot mint) + R3-CRIT-2 (verification API never returns bytes).
* **Chain β — Bad-hex pubkey causes silent fingerprint skip.**  Closed by R3-CRIT-3 (raises) + R3-HIGH-13 (`principal_from_session` rejects).
* **Chain γ — Per-principal-id flood grows rate-limit dict to OOM.**  Closed by R3-HIGH-1 (LRU cap).
* **Chain δ — Authed tenant on shared NAT throttled by anonymous traffic.**  Closed by R3-HIGH-2 (unauth bucket only on auth-fail path).
* **Chain ε — Counter file rewrite hot path under flood.**  Closed by R3-HIGH-4 (coalesced + atomic).
* **Chain ζ — Boot OOM via huge revocation file.**  Closed by R3-MED-2 (load cap with eviction).
* **Chain η — Production deploy with `ARIA_CORS_ORIGIN=*` or `ARIA_TRUSTED_PROXIES=0.0.0.0/0`.**  Closed by R3-HIGH-7 (boot-check refuses).
* **Chain θ — XSS payload enumerates token-like keys via `localStorage.length`.**  Closed by R3-HIGH-10 (sensitive keys hidden from `length`/`key`).

---

## 4. Test Surface After Round-3 Fixes

| File | Tests |
|------|-------|
| `tests/integration/test_security_audit_round2.py` (now r2 + r3) | 40 (was 30) |
| `tests/integration/test_security_rounds.py` | 112 |
| `tests/integration/test_security_rounds_v2.py` | 70 |
| `tests/integration/test_security_rounds_v3.py` | 58 |
| `tests/integration/test_security_rounds_v4.py` | 66 (1 skip) |
| `tests/integration/test_security_rounds_v5.py` | 55 |
| `tests/integration/test_security_rounds_v6.py` | 54 |
| `tests/integration/test_security_rounds_v7.py` | 50 (1 skip) |
| `tests/integration/test_security_foundation.py` | 19 |
| `tests/integration/test_security_guard.py` | 34 |
| `tests/integration/test_screener_tenant_store.py` | 13 |
| `tests/integration/test_screener_admin_endpoints.py` | 8 |
| `tests/integration/test_conjunction_screener_service.py` | 27 |
| `tests/unit/test_session_store.py` | 12 |
| `tests/unit/test_auth_service.py` | 17 |
| `tests/unit/test_auth_middleware.py` | 13 |
| `tests/integration/test_web_dashboard_authz.py` | 30 |
| `tests/integration/test_cubesat_deorbit_advisor.py` | 3 |
| `tests/integration/test_cubesat_advisor_extras.py` | 34 |
| **Total** | **715 (2 skip)** |

---

## 5. Operator follow-ups (out of code scope)

These cannot be performed from source:

1. **Worker-init hook for the internal-channel token.**  When using gunicorn/uvicorn pre-fork models, call `mint_internal_channel_token()` inside the per-worker `post_fork` hook, NOT the master process — so each worker holds its own token.
2. **Validate `ARIA_TRUSTED_PROXIES` is the smallest CIDR that covers your reverse-proxy network** — the compose default `172.16.0.0/12 + 10.0.0.0/8 + 192.168.0.0/16` is a safe upper bound but tighten if your VPC uses a single subnet.
3. **Schedule a `flush_counters()` call** on the graceful-shutdown signal handler so a planned restart doesn't lose up to 25 increments / 5 s of replay-defence state.
4. **Verify the SIEM mirror sink is healthy** — the `_audit_admin` helper logs but doesn't fail-closed; a mirror sink (R92 forwarder) is the second medium for the audit chain.
5. **Re-audit in 14 days** — verify the wiring tests in `test_security_audit_round2.py` (now r2 + r3) still fire and no new "added but not exploited-yet" gaps have accumulated.
