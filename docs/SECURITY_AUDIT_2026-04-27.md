# SECURITY_AUDIT_2026-04-27 — red-team audit findings + fixes

**Audit performed:** 2026-04-27
**Methodology:** paranoid red-team posture — assume hostile environment, motivated attackers, anonymous → authenticated → insider → supply-chain.  Concrete file:line citations only; no theoretical issues.
**Result:** 41 findings (8 CRIT + 13 HIGH + 14 MED + 6 LOW); **all 41 fixed in commit `4c3a289`**.

The full red-team report (with attacker profiles, trust boundaries, and chained-attack analysis) is preserved verbatim below.

---

## Threat Model

| Attacker profile | Entry points | Trust-boundary they cross |
|---|---|---|
| **Anonymous internet** | `/v1/healthz`, `/v1/version`, the Caddy plain-HTTP block, exposed Docker port 8090 | Public ↔ tenant API |
| **Authenticated tenant** (low-priv) | `X-ARIA-Token` to `/v1/screen`, `/v1/screen_bulk`, `/v1/usage`, `/v1/rotate_key`; cubesat advisor | Tenant ↔ tenant, tenant ↔ admin |
| **API consumer with stolen session** | session token in any worker, browser localStorage, log files | Any client ↔ that user |
| **Insider operator** | Captain console, sealed-roster files, attestation key, ground-uplink SSH | Operator ↔ ground state, operator ↔ flight |
| **Compromised supply chain** | `pip install`, Docker `:latest` pull, KEV feed, downloaded TLE / CDM, ESA pickle, model weights | Build host ↔ runtime, ground ↔ fleet |
| **On-path / MITM** | Caddy frontend, plain-HTTP /healthz, OpenMCT bridge CORS, telemetry server CORS | Network ↔ session |

**Sensitive assets**: tenant API keys, Ed25519 attestation key, `ARIA_MASTER_KEY` (HKDF root), captain shared-secret, sealed roster + manifest, SpaceTrack creds, audit hash chain.

---

## 1. Vulnerability Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 8 | ✅ all fixed |
| HIGH     | 13 | ✅ all fixed |
| MEDIUM   | 14 | ✅ all fixed |
| LOW      | 6 | ✅ all fixed |
| **Total** | **41** | **✅ all fixed** |

---

## 2. Findings + Fixes

### 2.1 CRITICAL

| ID | Title | Affected | Fix |
|----|-------|----------|-----|
| CRIT-1 | Hardcoded `aria-default-secret` for captain console | `src/aria/core/console.py:57` → `src/aria/security/auth.py:54` | `CommandAuthenticator` refuses `None`/short/banned secrets; `ARIA_CONSOLE_SECRET` ≥ 32 bytes required. |
| CRIT-2 | Weak session token: `sha256(issuer:time:id(self))[:32]` | `src/aria/security/auth.py:66` | Replaced with `secrets.token_urlsafe(32)`. |
| CRIT-3 | Single `admin_token_hex` reused across services | `conjunction_screener/service.py:451`, `cubesat_deorbit/service.py:140` | Service-bound: wire token = `HMAC(secret, service_id)`. |
| CRIT-4 | Demo tenant fallback `"d" × 64` | `conjunction_screener/service.py:122` | `_load_tenants` raises in `ARIA_ENV=prod` unless `ARIA_ALLOW_DEMO_TENANT=1`. |
| CRIT-5 | `.env` with live SpaceTrack credential | `./.env` | File scrubbed; placeholder-only; credential noted REVOKED — operator-side rotation required. |
| CRIT-6 | `eval()` in R325 YARA-lite condition | `src/aria/security/rounds/r325_yara_lite.py:76` | AST allow-list: `BoolOp` / `UnaryOp(Not)` / `Name` / `Constant(True\|False)` only. |
| CRIT-7 | `ARIA_MASTER_KEY` accepts weak / well-known patterns | `src/aria/security/rounds/r53_hkdf_per_tenant.py:26` | 64-hex floor in prod, 8+ distinct chars, deny-list (`"0"*64`, `"f"*64`, `deadbeef…`). |
| CRIT-8 | Missing COOP / COEP / strict CSP at proxy + app | `deploy/screener/Caddyfile`, `nginx-aria-screener.conf`, `src/aria/security/guard.py:560` | Both layers emit COOP same-origin, COEP require-corp, strict CSP with `require-trusted-types-for`, Permissions-Policy. |

### 2.2 HIGH

| ID | Title | Affected | Fix |
|----|-------|----------|-----|
| HIGH-1 | NDJSON streaming has no per-line write timeout | `conjunction_screener/service.py:549` | Each `await resp.write(...)` wrapped in `asyncio.wait_for(2.0)`; loop aborts on slow client. |
| HIGH-2 | No `len(secondaries)` cap before deserialise | `conjunction_screener/service.py:678` | Pre-validates `len(secondaries) ≤ 1000`; refuses non-dict bodies. |
| HIGH-3 | Unauthenticated requests bypass rate limit | `conjunction_screener/service.py:462` | Per-source-IP `_RateLimiter` consumed before the auth check. |
| HIGH-4 | `str(exc)` echoed in 4xx/5xx | `conjunction_screener/service.py:483, 496, 529, 638`; `cubesat_deorbit/service.py:178` | `_safe_error()` returns fixed code; `logger.exception` writes the trace server-side. |
| HIGH-5 | Per-action exception leaks crypto internals | `src/aria/security/per_action_auth.py:217` | Distinct catches for `InvalidSignature` / `ValueError`; fixed `"signature invalid"` returned to wire. |
| HIGH-6 | Session not bound to client | `src/aria/security/session_store.py:58` | `Session` carries `client_ip_hash` + `client_ua_hash`; `touch()` refuses mismatched fingerprints. |
| HIGH-7 | `:latest` Docker tag | `deploy/screener/docker-compose.yml:16` | Pinned via `${ARIA_SCREENER_IMAGE}` (digest expected); non-root user, read-only rootfs, `cap_drop ALL`, `tmpfs /tmp`, secrets. |
| HIGH-8 | `/v1/healthz` and `/v1/version` echo build version | `conjunction_screener/service.py:456, 459` | `healthz` returns `{"ok": true}` only; `version` is admin-only. |
| HIGH-9 | `Access-Control-Allow-Origin: *` on telemetry / OpenMCT | `dashboard/telemetry_server.py:255`, `integrations/openmct_bridge.py:364` | Exact-origin allow-list driven by `ARIA_CORS_ORIGINS`; wildcard never emitted. |
| HIGH-10 | `localStorage` anti-pattern in front-end | `web/src/App.tsx:221, 252` | `web/src/safeStorage.ts` runtime-refuses any key matching `token\|jwt\|session\|auth\|secret\|key\|cred\|password\|nonce`. |
| HIGH-11 | Tenant API keys plaintext at rest | `conjunction_screener/tenants.py:41` | SHA-256 hashed at rest with `sha256:` prefix; plaintext returned only at create/rotate; in-memory hash-index for O(1) lookup. |
| HIGH-12 | OAuth state per-process random fallback in prod | `src/aria/security/rounds/r05_oauth_state_csrf.py:30` | Refuses fallback when `ARIA_ENV=prod`; mandates `ARIA_OAUTH_STATE_KEY`. |
| HIGH-13 | Touch / revoke race | `src/aria/security/session_store.py:172` | Entire critical section under `self._lock`; revoke + touch atomic. |

### 2.3 MEDIUM

| ID | Title | Affected | Fix |
|----|-------|----------|-----|
| MED-1 | Authz audit logs role + reason | `src/aria/security/middleware.py:199` | Logs `deny_reason_code` only (`PERMISSION_MISSING`, `PRINCIPAL_EXPIRED`, …). |
| MED-2 | Idle timeout uses `time.time()` | `src/aria/security/session_store.py:74` | `last_seen_monotonic` field; idle check uses `time.monotonic()`. |
| MED-3 | HMAC truncated to 128-bit | `src/aria/security/auth.py:127` | Full 256-bit hexdigest. |
| MED-4 | Duress session has no explicit revoke | `src/aria/security/session_store.py:212` | `revoke_duress_for_principal()` revokes only duress sessions per principal. |
| MED-5 | `find_by_key` is O(n) timing-leak | `conjunction_screener/tenants.py:158` | In-memory hash → tenant_id index for O(1) lookup. |
| MED-6 | Previous API key never garbage-collected | `conjunction_screener/tenants.py:80` | `_purge_previous_key()` invoked the first time `find_by_key()` observes the grace window has elapsed. |
| MED-7 | Main `docker-compose.yml` binds `0.0.0.0:8090` | `docker-compose.yml:8` | Binds `127.0.0.1`; `ARIA_HOST=127.0.0.1`; `ARIA_CORS_ORIGINS` empty default. |
| MED-8 | Caddy / nginx logs full request headers | `deploy/screener/Caddyfile:54`, `nginx-aria-screener.conf:33` | `Authorization`, `X-ARIA-Token`, `X-ARIA-Admin-Token`, `Cookie` redacted in both. |
| MED-9 | systemd unit lacks tight perms | `deploy/screener/aria-screener.service:53` | `UMask=0077`, `StateDirectoryMode=0700`, `IPAddressDeny=any` + private-range allow-list. |
| MED-10 | `ast.literal_eval` on tool-result string | `src/aria/cognitive/engine.py:220` | `json.loads()` first; `ast.literal_eval` typed fallback. |
| MED-11 | Negative `window_seconds` in `/v1/usage` | `conjunction_screener/service.py:592` | Clamped `[60s, 90 d]`; non-numeric → 400. |
| MED-12 | MD5 truncated to 32-bit | `src/aria/security/anomaly.py:111` | SHA-256 truncated to 64-bit. |
| MED-13 | HKDF default salt fixed string | `src/aria/security/rounds/r53_hkdf_per_tenant.py:66` | `ARIA_HKDF_SALT_HEX` per-deployment salt env var. |
| MED-14 | SSH KEX audit (R206) detector-only | `src/aria/security/rounds/r206_pq_ssh.py` | `boot_check_local_sshd()` reads `/etc/ssh/sshd_config` and gates the `KexAlgorithms` line. |

### 2.4 LOW

| ID | Title | Affected | Fix |
|----|-------|----------|-----|
| LOW-1 | `/healthz` reachable on plain HTTP | `deploy/screener/Caddyfile:27` | Moved into HTTPS-only block. |
| LOW-2 | Admin endpoints leak existence pre-body-parse | `conjunction_screener/service.py:619` | Body parsed first, then auth-check. |
| LOW-3 | `created_at` / `last_rotated_at` in default admin listing | `conjunction_screener/service.py:668` | Gated behind `?include_audit=1`. |
| LOW-4 | Per-action GC stalls past 2× TTL | `src/aria/security/per_action_auth.py:54` | GC runs on every `issue()` and `verify()`. |
| LOW-5 | `X-Trace-Id` parser order accepts mis-classed input | `src/aria/security/middleware.py:248` | Strict explicit branching (`startswith("trc_")` → 16-hex; `len == 32` → OTel; else reject). |
| LOW-6 | `aria-default-secret` accepted from env-only too | `src/aria/security/auth.py:54` | Deny-list applies to the env-derived secret as well. |

---

## 3. Attack Chains (closed)

* **Chain A** — Anonymous → admin via demo-tenant fallback + cross-product admin token. Closed by CRIT-3 (service-bound admin) + CRIT-4 (demo refusal in prod).
* **Chain B** — Browser XSS → backend → audit forge via missing isolation + localStorage + console-secret. Closed by CRIT-1 + CRIT-8 + HIGH-10.
* **Chain C** — Supply-chain (`:latest`) → master-key → fleet. Closed by HIGH-7 (image pin) + CRIT-7 (master-key entropy floor) + HIGH-11 (keys hashed at rest).
* **Chain D** — Slowloris on bulk + no body cap + no unauth limit → cluster DoS. Closed by HIGH-1 + HIGH-2 + HIGH-3.
* **Chain E** — Concurrent revoke/touch un-revokes session. Closed by HIGH-13.
* **Chain F** — Forensic-trail subversion via header-rich Caddy logs. Closed by MED-8.

---

## 4. Test Surface After Fixes

| File | Tests | Status |
|------|-------|--------|
| `tests/integration/test_security_rounds.py` | 112 | ✅ |
| `tests/integration/test_security_rounds_v2.py` | 70 | ✅ |
| `tests/integration/test_security_rounds_v3.py` | 58 | ✅ (1 skip = cbor2 missing) |
| `tests/integration/test_security_rounds_v4.py` | 66 | ✅ (1 skip = cbor2 missing) |
| `tests/integration/test_security_rounds_v5.py` | 55 | ✅ |
| `tests/integration/test_security_rounds_v6.py` | 54 | ✅ |
| `tests/integration/test_security_rounds_v7.py` | 50 | ✅ (1 skip = cbor2 missing) |
| `tests/integration/test_security_foundation.py` | 19 | ✅ |
| `tests/integration/test_security_guard.py` | 34 | ✅ |
| `tests/integration/test_screener_tenant_store.py` | 14 | ✅ |
| `tests/integration/test_screener_admin_endpoints.py` | 8 | ✅ |
| `tests/integration/test_conjunction_screener_service.py` | 25 | ✅ |
| `tests/unit/test_session_store.py` | 21 | ✅ |
| `tests/unit/test_auth_service.py` | 17 | ✅ |
| `tests/unit/test_auth_middleware.py` | 13 | ✅ |
| `tests/integration/test_web_dashboard_authz.py` | 7 | ✅ |
| `tests/integration/test_cubesat_deorbit_advisor.py` | 3 | ✅ |
| **Total** | **626** | **all green** |

Plus bandit `HIGH=0 / MEDIUM=0`, pip-audit clean.

---

## 5. Operator follow-ups (out of code scope)

These cannot be done from source; the operator must execute them out-of-band:

1. **Rotate the SpaceTrack credential** at https://www.space-track.org/ — the previously-stored SpaceTrack credential (account email and password redacted from this public copy) is treated as compromised.
2. **Generate fresh production crypto material**:
   - `ARIA_MASTER_KEY = secrets.token_hex(32)` (256 bit, must satisfy 8+ distinct chars + not on R53 deny-list)
   - `ARIA_CONSOLE_SECRET = secrets.token_urlsafe(32)`
   - `ARIA_OAUTH_STATE_KEY = secrets.token_hex(32)` (shared across all workers)
   - `ARIA_ADMIN_TOKEN = secrets.token_hex(32)` (the wire token derived per-service is `HMAC(token, b"aria-screener:v1")` etc.)
   - `ARIA_HKDF_SALT_HEX = secrets.token_hex(32)` (per-deployment salt)
3. **Pin the deployable image** — build, record the resulting digest, and set `ARIA_SCREENER_IMAGE=aria-screener@sha256:<digest>`.
4. **Populate Docker secrets** — `deploy/screener/secrets/{admin_token,master_key,oauth_state,hkdf_salt}.txt` with one value per file before the next `docker compose up`.
5. **Rotate any tenant API key that lived through the migration** so every key is now stored as a fresh SHA-256 hash with no plaintext history.
6. **Configure `ARIA_CORS_ORIGINS`** explicitly per deployment (no wildcard accepted).

After these six steps the residual gaps in [SECURITY_LANDSCAPE.md](SECURITY_LANDSCAPE.md) remain strictly hardware (HSM / TPM / IPS / FIDO2 fleet / fibre data diode / QKD / RF-shielded enclosure) or operator-side (classified threat-intel, kernel EDR, 24/7 SOC, NSA-cleared SCIF, formal verification).
