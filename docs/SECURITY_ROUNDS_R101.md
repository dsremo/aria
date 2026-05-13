# R52-R101 — fifty more round-by-round defences

**Audited:** 2026-04-26
**Library entry:** `from aria.security.guard import activate_all_rounds, ...`
**Tests:** 70 R52-R101 regressions + 112 R1-R51 + 34 R50 + 19 foundation + 16 screener = **251 security tests green** (plus 143 smoke)
**Composition:** every R52-R101 round registers a `DefencePlugin` exactly like R1-R51, picked up automatically by `harden_aiohttp_app`.  Full architecture diagram in [SECURITY_ROUNDS_R51.md](SECURITY_ROUNDS_R51.md) §"How rounds compose".

This document is the **R52-R101 supplement** — the second 50 rounds adding cryptography depth, IAM depth, memory-safety / native-code lint, network depth, and forensics + anti-tamper.  The honest comparison to nation-state / banking / EDR stacks lives in [SECURITY_LANDSCAPE.md](SECURITY_LANDSCAPE.md).

---

## Block G — Cryptography depth (R52–R61)

| # | Topic | Threat (real-world) | Defence |
|---|-------|---------------------|---------|
| R52 | TLS certificate pinning + CT-log advisory | Rogue-CA MITM (banking class) | Per-host SPKI-SHA-256 pin list; constant-time compare |
| R53 | HKDF per-tenant key derivation | Single-master compromise blast | RFC-5869 HKDF-SHA-256 keyed on `ARIA_MASTER_KEY` |
| R54 | AES-GCM-SIV (nonce-misuse-resistant) | WhatsApp 2017 nonce-reuse class | RFC-8452 AESGCMSIV; falls back to AES-GCM with unique nonce |
| R55 | Hybrid Ed25519 + ML-DSA-65 signing | Harvest-now-decrypt-later (NSA CNSA 2.0) | JSON frame: classical sig + optional PQ sig; verify both |
| R56 | Secure memory wipe + mlock | Heartbleed CVE-2014-0160 class | `secure_buffer` ctx mgr: mlock + 3-pass wipe |
| R57 | Constant-time helpers + benchmark | Lucky-13 / BEAST timing-side-channel | `constant_time_eq` + variance benchmark for CI |
| R58 | OCSP certificate revocation | Stolen-cert MITM | OCSP query with 1 h cache; UNKNOWN/UNAVAILABLE policy |
| R59 | TLS downgrade refusal | POODLE / BEAST / FREAK / SWEET32 | Banned-version + banned-cipher allow-list; `make_strict_context` |
| R60 | Password KDF | GPU-cracking weak hashes | Argon2id; PBKDF2-SHA512 600 K-iter fallback |
| R61 | ML-KEM-768 (Kyber) wrapper | CRQC harvest-now-decrypt-later | `oqs` wrap; classical-only fallback when oqs unavailable |

## Block H — IAM depth (R62–R71)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R62 | WebAuthn / FIDO2 | Phishable second factor (Snowflake 2024) | Challenge issuer + assertion verifier (origin-pinned) |
| R63 | RFC-6238 TOTP | Weak 2FA | Real RFC-6238 with HMAC-SHA-1/256/512; ±1 step skew |
| R64 | One-time backup codes | MFA lockout panic | Argon2-hashed; single-shot consume; default 8 × 12 chars |
| R65 | Risk-based step-up | Bank standard | `required_factor(action, signals)` returns NONE→DUAL_PERSON |
| R66 | Session binding (cookie+IP+UA+ASN) | Token leak replay | `match_score` returns 0.00–1.00; fold into R65 step-up |
| R67 | Just-in-time elevation | Standing-admin attack surface | `request_elevation` with TTL + justification + audit |
| R68 | Concurrent-session cap | Stolen-cred parallel session | Per-principal counter (3 default); `force=True` evicts oldest |
| R69 | Privileged-session recording | PCI-DSS 10.2 / SOC 2 | Append-only JSONL; chmod-440 on stop |
| R70 | SAML XSW pre-flight | Golden SAML / SolarWinds 2020 | One-assertion + signature-targets-assertion-ID guard |
| R71 | SCIM protected attributes | Okta 2024 SCIM PATCH | Refuse `role`/`permissions`/`isSuperUser` mutations |

## Block I — Memory safety + native code (R72–R81)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R72 | C buffer-overflow lint | strcpy/sprintf/gets in cFS bridge | Walk `.c` for unsafe primitives; require `// allow_unsafe(reason=...)` |
| R73 | Format-string lint | CWE-134 printf-class | Flag printf-family + Python LOG calls with non-literal format |
| R74 | Integer overflow | length × stride wrap (image/video decoders) | `checked_mul` / `checked_add` / `size_for` with bounded max |
| R75 | Recursion depth | Deeply-nested input DoS | `bounded_recursion(max_depth=N)` ctx mgr |
| R76 | Use-after-free hint | aiohttp 2023 streaming UAF class | `track_lifetime` + `mark_freed` + `UseAfterFree` raise |
| R77 | ASLR/PIE/RELRO/canary check | Mitigation regression | Live `/proc/self/maps` + ELF `readelf -d` walker |
| R78 | seccomp-bpf profile | RCE-confined syscall surface | Generator emits Docker / podman JSON profile (default 80 syscalls) |
| R79 | Anti-debugger | gdb attach + memory dump | `prctl(PR_SET_DUMPABLE,0)` + TracerPid poll |
| R80 | Runtime code integrity | Disk-write tamper after boot | Boot baseline + 60 s periodic SHA-256 verify |
| R81 | Pickle-safe alt (msgpack) | RCE via pickle deserialise | `safe_dumps`/`safe_loads` strict-types whitelist |

## Block J — Network depth (R82–R91)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R82 | DNS-over-HTTPS | DNS poisoning (Kaminsky still relevant) | RFC-8484 wire-format client via `safe_open_url` |
| R83 | DNS-rebinding pin (advanced) | Beyond R15 — connect-time IP swap | `resolve_and_pin` 5 s cache + `RebindDetector` |
| R84 | SYN-flood mitigation | Backlog exhaustion | Boot check `tcp_syncookies=1`; recommended sysctl block |
| R85 | Reflection / amplification | NTP/DNS/memcached/CLDAP DDoS | Boot check we hold no UDP listeners on amp ports |
| R86 | Smuggling v2 | CL.TE / TE.CL / multi-CL | Refuse CL+TE combo + non-`chunked` TE values |
| R87 | CORS strict | Wildcard ACAO + creds | Refuse Origin outside `ARIA_CORS_ORIGINS` allow-list |
| R88 | Open-redirect | Phishing via own domain | Refuse `//evil.com`, JS/data URIs; origin allow-list |
| R89 | WebSocket auth on upgrade | R50 residual gap | `require_token_on_upgrade(request)` |
| R90 | IP reputation hook | Tor exit / AbuseIPDB | Pluggable score 0..1 + known-bad set |
| R91 | Egress block | Post-RCE call-home | Production-mode deny-by-default; flag metadata.* |

## Block K — Forensics + anti-tamper (R92–R101)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R92 | SIEM forwarder | Local-host log-tamper | Async forward (Splunk HEC / Sentinel / Loki); fallback JSONL |
| R93 | MISP intel | Stale defenders / fast campaigns | Pull MISP event JSON; normalise IOCs into R90 + lookups |
| R94 | Fuzz harness | Untested edge inputs | Bounded mutation fuzzer; reproducible by seed; capped 60 s |
| R95 | Clock-skew check | TTL-bypass via wall-clock shift | HEAD-and-Date against public reference; ±5 s tolerance |
| R96 | Browser SRI + COOP/COEP | Polyfill 2024 CDN compromise | `compute_sri` + browser-isolation header pack |
| R97 | Data classification + redact | GDPR / CCPA / HIPAA fines | Tag `{public/pii/secret}`; threshold redact for audit |
| R98 | Immutable hash-chained logs | Tamper-resistant audit | `ImmutableSink` + `verify_chain` walker |
| R99 | Kill-switch (3 states) | Active-compromise freeze | ACTIVE / READONLY / LOCKED; healthz always passes |
| R100 | Breach simulation | Defences rot when untested | `run_breach_drill` orchestrated red-team; Markdown report |
| R101 | Adversarial runner v2 | Full-stack regression | Probe corpus across all R1–R100 defences |

---

## How to run all 101 rounds against ARIA

```bash
python -c "
from aria.security.guard import activate_all_rounds
loaded = activate_all_rounds(force_reload=True)
print(f'Loaded {len(loaded)} rounds: {sorted(loaded)}')

# R51 (R1-R51 coverage)
from aria.security.rounds.r51_adversarial_runner import run, render_report
print(render_report(run()))

# R101 (full-stack v2)
from aria.security.rounds.r101_adversarial_runner_v2 import run_v2, render_v2
print(render_v2(run_v2()))

# R100 (breach drill)
from aria.security.rounds.r100_breach_drill import run_breach_drill, render_drill_md
print(render_drill_md(run_breach_drill()))
"
```

## What R52-R101 closes from SECURITY_LANDSCAPE.md

| Gap row in landscape doc | Round that closes it |
|--------------------------|----------------------|
| Cert pinning (banks) | R52 (software pinning); HW pinning still operator KMS |
| FIPS 140-3 hybrid keys | R55 (Ed25519+ML-DSA frame), R61 (ML-KEM wrapper) |
| Real-time MITM detection | R52 + R58 + R59 + R83 |
| MFA enforcement (Snowflake class) | R62 + R63 + R64 + R65 + R67 |
| Behavioural session security | R66 + R68 + R69 + R65 |
| Side-channel timing | R57 + R56 |
| Algorithmic complexity DoS | R75 + R94 |
| EDR-class kernel telemetry | R77 + R78 + R79 + R80 (process boundary, not kernel) |
| SIEM integration | R92 + R98 + R99 + R100 |
| Threat-intel feeds | R93 (MISP) + R-foundation evolve (CISA KEV) |
| Browser-side hardening | R96 |
| Privileged-session forensics | R69 + R98 + R97 |

After R101, the residual rows in the landscape doc are **strictly hardware** (HSM / TPM 2.0 / line-rate IPS) or **strictly operator-side** (classified threat intel feeds, formal verification, counter-intel opsec).
