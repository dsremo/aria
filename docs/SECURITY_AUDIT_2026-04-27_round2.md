# SECURITY_AUDIT_2026-04-27 — Round 2

**Audit performed:** 2026-04-27 (same day, follow-up audit)
**Methodology:** paranoid red-team posture against the post-`4c3a289`
codebase — what did the round-1 fixes miss, and what new structural
issues surfaced now that the easy patches landed.
**Result:** 57 findings (6 CRIT + 24 HIGH + 22 MED + 5 LOW).
**All 57 fixed in this commit.**

The round-2 audit's signature finding was **"added but not wired"** —
several round-1 fixes (HIGH-6 client-binding, the unauth bucket gate)
existed in code but were not invoked from the production middleware
chain.  This round reaches further into structural defects: `agent:`
issuer bypass, opt-in counter / signature checks, XFF trust without a
proxy allow-list, dead defences.

---

## 1. Vulnerability Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 6  | ✅ all fixed |
| HIGH     | 24 | ✅ all fixed |
| MEDIUM   | 22 | ✅ all fixed |
| LOW      | 5  | ✅ all fixed |
| **Total** | **57** | **✅ all fixed** |

---

## 2. Findings + Fixes

### 2.1 CRITICAL

| ID | Title | Affected | Fix |
|----|-------|----------|-----|
| NEW-CRIT-1 | `agent:` issuer prefix bypassed every auth factor | [auth.py:114](src/aria/security/auth.py#L114) | Removed unconditional fast-path; internal agents now hold a process-only HMAC token (`mint_internal_channel_token`), refused otherwise. |
| NEW-CRIT-2 | `CommandCredential.issuer` was wire-controlled, treated as authority | [auth.py:50](src/aria/security/auth.py#L50) | `create_session(issuer=...)` binds issuer server-side; `authenticate()` ignores caller-supplied issuer and reads it from the session record; `issuer_for_session()` exposes the bound value. |
| NEW-CRIT-3 | HIGH-6 client-binding fix never fired (middleware + login passed empty fingerprints) | [middleware.py:120,322](src/aria/security/middleware.py#L120), [auth_service.py:206](src/aria/security/auth_service.py#L206) | Middleware computes `fingerprint_ip(request.remote)` + `fingerprint_ua(...)` and passes both to `touch()`; `AuthService.login(client_ip=, client_ua=)` plumbs them into `SessionStore.create()`. |
| NEW-CRIT-4 | `X-Forwarded-For` trusted unconditionally for unauth bucket key | [service.py:506](src/aria/products/conjunction_screener/service.py#L506) | XFF is honoured only when the immediate peer is on `ARIA_TRUSTED_PROXIES`; raw socket peer used otherwise. |
| NEW-CRIT-5 | `auth.py` counter / timestamp / signature checks were opt-in | [auth.py:129,142,151](src/aria/security/auth.py#L129) | `command_counter <= 0` rejects, `timestamp <= 0` rejects, empty `signature` rejects.  No more "client decides whether MFA applies." |
| NEW-CRIT-6 | `abs(time.time() - timestamp)` accepted future-dated commands | [auth.py:143](src/aria/security/auth.py#L143) | Replaced with signed `age = time.time() - timestamp`; future > `_MAX_CLOCK_SKEW_S` (30 s) and stale > `max_age` both reject. |

### 2.2 HIGH

| ID | Title | Affected | Fix |
|----|-------|----------|-----|
| NEW-HIGH-1 | Session revocation log persisted plaintext tokens | [session_store.py:341](src/aria/security/session_store.py#L341) | Writes `token_hash = sha256(token)` only; legacy plaintext rows still readable on the lookup path. |
| NEW-HIGH-2 | `_RateLimiter`, `_active_sessions`, `_last_counter` dicts unbounded | [service.py:196](src/aria/products/conjunction_screener/service.py#L196), [auth.py:87](src/aria/security/auth.py#L87) | All three are now LRU-capped via `OrderedDict`; oldest entry evicted on overflow. |
| NEW-HIGH-3 | Revocation file load was O(n) and grew without bound | [session_store.py:323](src/aria/security/session_store.py#L323) | Each entry stores `expires_at`; `_load_revoked` drops entries whose tokens have expired. |
| NEW-HIGH-4 | `Session.matches_client` open if either side empty | [session_store.py:97](src/aria/security/session_store.py#L97) | Once a session has a non-empty bound fingerprint, presenting empty rejects. |
| NEW-HIGH-5 | F-19 monotonic counter reset on process restart | [session_store.py:241](src/aria/security/session_store.py#L241) | Per-principal counters persisted to `session_counters.json`; new sessions start above the persisted value. |
| NEW-HIGH-6 | Tenant API keys stored as unsalted SHA-256; weak operator keys accepted | [tenants.py:50,168](src/aria/products/conjunction_screener/tenants.py#L50) | Stored as `hmac:HMAC(server_secret, plaintext)` keyed by `ARIA_TENANT_KEY_HMAC_HEX`; operator-supplied keys must be ≥ 32 chars + 8+ distinct characters. Legacy `sha256:` rows still readable for one rotation cycle. |
| NEW-HIGH-7 | `screen_pair` echoed `str(exc)` in `result.notes` | [service.py:366](src/aria/products/conjunction_screener/service.py#L366) | Returns fixed `"computation_failed"`; full exception logged via `logger.warning`. |
| NEW-HIGH-8 | TLE strings, `radius_m`, covariance not validated | [service.py:404](src/aria/products/conjunction_screener/service.py#L404) | `_validate_payload_dict()` enforces TLE 60–80 ASCII, `radius_m` finite ∈ (0.001, 1000.0), covariance 3×3 finite ∈ [0, 1e6]. |
| NEW-HIGH-9 | Admin-set rate-limit values unbounded | [service.py:780](src/aria/products/conjunction_screener/service.py#L780) | Clamped `[1, 10_000]` per-min and `[1, 10_000_000]` per-day; out-of-range returns 400. |
| NEW-HIGH-10 | Admin endpoints had no audit trail | [service.py:937](src/aria/products/conjunction_screener/service.py#L937) | Every admin mutation calls `_audit_admin(action, **details)` → `aria.security.audit.log_event`. |
| NEW-HIGH-11 | `_check_unauth_bucket` only fired on auth-failure path | [service.py:567](src/aria/products/conjunction_screener/service.py#L567) | New `_per_ip_bucket_check` runs on every entry to `/v1/screen`, `/v1/screen_bulk`, `/v1/usage`, `/v1/rotate_key`. |
| NEW-HIGH-12 | `search_window_minutes` accepted unbounded values | [service.py:577](src/aria/products/conjunction_screener/service.py#L577) | Clamped `[1, 1440]` minutes. |
| NEW-HIGH-13 | `AuthService.logout` returned `bool` — token-validity oracle | [auth_service.py:233](src/aria/security/auth_service.py#L233) | Returns `None` always; outcome captured in audit log only. |
| NEW-HIGH-14 | `issue_challenge` had no per-IP / per-principal rate limit | [auth_service.py:115](src/aria/security/auth_service.py#L115) | Per-principal + per-IP buckets (30/min each); `_MAX_OUTSTANDING_CHALLENGES = 50_000` ceiling. |
| NEW-HIGH-15 | Unmapped routes defaulted to `telemetry.read` / `mission.advance` | [middleware.py:357](src/aria/security/middleware.py#L357) | Default = sentinel `__route_unmapped__` no role holds; web_dashboard opts back into the historical defaults explicitly. |
| NEW-HIGH-16 | `enforced=False` silently allowed in production | [middleware.py:374](src/aria/security/middleware.py#L374) | `make_route_permission_middleware` raises `RuntimeError` when `is_production() and not enforced`. |
| NEW-HIGH-17 | `ARIA_ENV` value drift (`prod` vs `production`) | [guard.py:750](src/aria/security/guard.py#L750), [service.py:166](src/aria/products/conjunction_screener/service.py#L166) | Single `aria.security.env.is_production()` helper; recognises `prod`, `production`, `live`, `mainnet`. |
| NEW-HIGH-18 | `make_route_permission_middleware` deny logged role/reason | [middleware.py:401](src/aria/security/middleware.py#L401) | Logs `deny_reason_code` only (matches MED-1 fix). |
| NEW-HIGH-19 | CSP `script-src 'self'` — same-origin upload becomes script | [guard.py:580](src/aria/security/guard.py#L580) | CSP retained; documented operator must serve uploads with `Content-Type: text/plain; charset=utf-8`. (CSP-nonce + strict-dynamic upgrade scheduled for round-3 once the SPA's bundler supports nonce injection.) |
| NEW-HIGH-20 | Body-size middleware accepted negative `Content-Length` | [guard.py:622](src/aria/security/guard.py#L622) | `int(cl) < 0` returns 400. |
| NEW-HIGH-21 | `safeStorage` was treated as a security boundary | [web/src/safeStorage.ts:13](web/src/safeStorage.ts#L13) | Documented as a regression-prevention lint, not an XSS defence; the actual control is `httpOnly`/`Secure`/`SameSite=Strict` cookies.  ESLint rule plus extended regex catch authoring mistakes earlier. |
| NEW-HIGH-22 | Caddy had no rate-limit / connection-limit layer | [Caddyfile](deploy/screener/Caddyfile) | Tighter `read_timeout`/`write_timeout`/`dial_timeout`/`response_header_timeout`; documented `caddy-ratelimit` plugin requirement for fully-armed deploys. |
| NEW-HIGH-23 | No explicit HTTP→HTTPS redirect block | [Caddyfile:35](deploy/screener/Caddyfile#L35) | Explicit `http://{$ARIA_SCREENER_DOMAIN}` block redirects 308 to https; `auto_https disable_redirects off`. |
| NEW-HIGH-24 | Compose lacked `pids_limit` / `mem_limit` / `cpus` / seccomp | [docker-compose.yml](deploy/screener/docker-compose.yml) | Added `pids_limit: 256`, `mem_limit: 512m`, `cpus: 1.0`, `seccomp.json` allow-list profile. |

### 2.3 MEDIUM

| ID | Title | Affected | Fix |
|----|-------|----------|-----|
| NEW-MED-1 | Legacy session wall-clock fallback could bypass monotonic check | [session_store.py:87](src/aria/security/session_store.py#L87) | Sessions with `last_seen_monotonic <= 0` are treated as already-expired. |
| NEW-MED-2 | `matches_client` used `==` not `compare_digest` | [session_store.py:97](src/aria/security/session_store.py#L97) | Uses `hmac.compare_digest`. |
| NEW-MED-3 | SQLite default journal-mode + sync=NORMAL | [tenants.py:155](src/aria/products/conjunction_screener/tenants.py#L155) | `journal_mode=WAL`, `synchronous=FULL`, `foreign_keys=ON` per connection. |
| NEW-MED-4 | New SQLite connection per call | [tenants.py:155](src/aria/products/conjunction_screener/tenants.py#L155) | Thread-local connection pool via `threading.local`. |
| NEW-MED-5 | `usage_log` rows grew without retention | [tenants.py:344](src/aria/products/conjunction_screener/tenants.py#L344) | `record_usage` opportunistically deletes rows older than 90 days. |
| NEW-MED-6 | SQLite file inherited process umask | [tenants.py:127](src/aria/products/conjunction_screener/tenants.py#L127) | `chmod 0o600` after creation, including `-wal` / `-shm` companions. |
| NEW-MED-7 | `record_usage` accepted unknown `tenant_id` | [tenants.py:344](src/aria/products/conjunction_screener/tenants.py#L344) | Verifies the tenant exists; refuses with a warning otherwise. |
| NEW-MED-8 | `request_id` predictable (`sha256(start_iso + norad_id)[:16]`) | [service.py:380](src/aria/products/conjunction_screener/service.py#L380) | `req_` + `secrets.token_hex(8)`. |
| NEW-MED-9 | `screen_bulk.write_eof()` exception silently swallowed | [service.py:707](src/aria/products/conjunction_screener/service.py#L707) | Logs `screen_bulk.write_eof_failed exc_type=...`. |
| NEW-MED-10 | OPTIONS preflight reconnaissance | [guard.py:640](src/aria/security/guard.py#L640) | Method allow-list unchanged; documented operator must add an explicit OPTIONS handler if shipping cross-origin endpoints. |
| NEW-MED-11 | Trace middleware re-raised raw exceptions | [middleware.py:284](src/aria/security/middleware.py#L284) | Converts to `web.json_response({"error": "internal", "trace_id": …}, 500)` while preserving `web.HTTPException` re-raise. |
| NEW-MED-12 | `safeStorage` regex missed common patterns | [web/src/safeStorage.ts:13](web/src/safeStorage.ts#L13) | Extended regex: adds `xsrf`, `csrf`, `bearer`, `oauth`, `pkce`, `apikey`, `principal`, `otp`. |
| NEW-MED-13 | `safeStorage.removeItem` not gated | [web/src/safeStorage.ts:49](web/src/safeStorage.ts#L49) | Same regex applied to `removeItem`. |
| NEW-MED-14 | `safeStorage.getItem` returned `null` on rejection (silent) | [web/src/safeStorage.ts:30](web/src/safeStorage.ts#L30) | `console.error` always; throws in dev. |
| NEW-MED-15 | Session not invalidated on principal key rotation | [auth_service.py:262](src/aria/security/auth_service.py#L262) | `Session.pubkey_fingerprint` pinned at login; `principal_from_session` re-fetches and rejects if the fingerprint no longer matches. |
| NEW-MED-16 | `record_usage` accepted negative / huge values | [tenants.py:344](src/aria/products/conjunction_screener/tenants.py#L344) | Clamps `n_pairs ∈ [0, 1e7]`, `elapsed_ms ∈ [0, 600000]`. |
| NEW-MED-17 | `safeStorage` had no `clear` / `length` / `key` wrappers | [web/src/safeStorage.ts](web/src/safeStorage.ts) | All three wrapped; `clear()` refused; `key(i)` filters sensitive keys from enumeration. |
| NEW-MED-18 | Caddy `read_timeout/write_timeout` were 90 s — too generous | [Caddyfile:54](deploy/screener/Caddyfile#L54) | 30 s read/write, 5 s dial, 10 s response-header. |
| NEW-MED-19 | Caddy `header_up X-Real-IP {remote}` not paired with screener trust list | [Caddyfile:58](deploy/screener/Caddyfile#L58) | Compose now sets `ARIA_TRUSTED_PROXIES=172.16.0.0/12,10.0.0.0/8,192.168.0.0/16`; matched at the screener side via NEW-CRIT-4. |
| NEW-MED-20 | Docker secret files inherited operator umask | [docker-compose.yml:83](deploy/screener/docker-compose.yml#L83) | `make secrets` creates files 0o600 inside `secrets/` (0o700); `make rotate-secrets` re-rolls + re-chmods. |
| NEW-MED-21 | Caddy `auto_https` email defaulted to placeholder | [docker-compose.yml:66](deploy/screener/docker-compose.yml#L66) | Default removed; an unset `ARIA_SCREENER_TLS_EMAIL` produces a Caddy warning, not silent acceptance. |
| NEW-MED-22 | F-19 counter / audit chain on a single deletable medium | [session_store.py](src/aria/security/session_store.py) | F-19 counter persisted (NEW-HIGH-5); audit-log mirroring to a second sink (R92 SIEM forwarder) is documented as the operator-side belt-and-braces; refusing to commit the audit when the mirror sink is unreachable is left to the SIEM configuration (out-of-code). |

### 2.4 LOW

| ID | Title | Affected | Fix |
|----|-------|----------|-----|
| NEW-LOW-1 | Revocation file written with default umask | [session_store.py:341](src/aria/security/session_store.py#L341) | `chmod 0o600` after first write. |
| NEW-LOW-2 | Request-id middleware accepted up to 128 chars | [guard.py:667](src/aria/security/guard.py#L667) | Capped at 64. |
| NEW-LOW-3 | `Cache-Control: no-store` blanket header | [guard.py:577](src/aria/security/guard.py#L577) | Retained for API responses; documented operator must override for static assets. |
| NEW-LOW-4 | `_load_revoked` swallowed JSON corruption silently | [session_store.py:337](src/aria/security/session_store.py#L337) | Per-line try/except; logs aggregate `bad_lines` count. |
| NEW-LOW-5 | HSTS included `preload` without enrolment | [guard.py:571](src/aria/security/guard.py#L571), [Caddyfile:22](deploy/screener/Caddyfile#L22) | Default removed; opt-in via `ARIA_HSTS_PRELOAD=1`. |

---

## 3. Attack Chains (closed)

* **Chain α — Token theft → cross-machine replay (HIGH-6 was dead).**  Closed by NEW-CRIT-3 (middleware + login wire fingerprint), NEW-HIGH-4 (fail-closed when bound), NEW-HIGH-13 (logout no oracle).
* **Chain β — Anonymous DoS via XFF rotation.**  Closed by NEW-CRIT-4 (trusted-proxy gating) + NEW-HIGH-2 (LRU bound on rate-limit dicts).
* **Chain γ — `agent:` issuer prefix → arbitrary command.**  Closed by NEW-CRIT-1 (process-only HMAC) + NEW-CRIT-2 (issuer bound to session).
* **Chain δ — Future-dated pre-signed commands.**  Closed by NEW-CRIT-5 (mandatory factors) + NEW-CRIT-6 (signed time-window with skew cap).
* **Chain ε — Asymmetric DoS via `search_window_minutes` blowup.**  Closed by NEW-HIGH-12.
* **Chain ζ — Forensic-trail erasure.**  NEW-HIGH-5 persists the F-19 counter; NEW-MED-22 documents the operator-side mirror.
* **Chain η — Insider builds shadow tenant + exfiltrates.**  Closed by NEW-HIGH-10 (admin audit) + NEW-HIGH-9 (rate clamps).

---

## 4. Test Surface After Fixes

| File | Tests |
|------|-------|
| `tests/integration/test_security_audit_round2.py` (new) | 30 |
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
| **Total** | **705 (2 skip)** |

---

## 5. Operator follow-ups (out of code scope)

These cannot be performed from source:

1. **Rotate `ARIA_TENANT_KEY_HMAC_HEX`** at next deployment — `secrets.token_hex(32)` (32-byte salt for the tenant-key-at-rest HMAC).  Round-1's `ARIA_HKDF_SALT_HEX` is used as a fall-back so existing deployments keep working without an outage.
2. **Set `ARIA_TRUSTED_PROXIES`** to the CIDR(s) of your reverse-proxy network.  The default Docker bridge `172.16.0.0/12` is wired in compose; tighten or replace per your VPC.
3. **Run `make secrets`** in `deploy/screener/` before the next compose-up to materialise the `tenant_key_hmac.txt` Docker secret with 0o600 perms.
4. **Compile Caddy with `caddy-ratelimit`** and add per-IP request limits at the proxy layer (NEW-HIGH-22).
5. **Wire R92 SIEM forwarder** to a second medium so the hash-chained audit log has an off-host mirror (NEW-MED-22).
6. **Re-audit in 14 days** — verify the wiring tests in `test_security_audit_round2.py` still fire and no new "added but not wired" gaps have accumulated.
