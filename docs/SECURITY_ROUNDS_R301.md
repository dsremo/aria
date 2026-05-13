# R252-R301 — fifty more round-by-round defences

**Audited:** 2026-04-26
**Library entry:** `from aria.security.guard import activate_all_rounds, ...`
**Tests (per file):** 54 R252-R301 + 55 R202-R251 + 66 R152-R201 + 58 R102-R151 + 70 R52-R101 + 112 R1-R51 + 34 guard + 19 foundation = **468 security tests** (plus 143 smoke)
**Composition:** every R252-R301 round registers a `DefencePlugin` exactly like R1-R251.

This document is the **R252-R301 supplement** — the sixth 50 rounds adding browser/front-end security, email + DNS depth, storage + database hardening, application-layer threat modeling, and insider-threat depth. See [SECURITY_ROUNDS_R51.md](SECURITY_ROUNDS_R51.md) (R1-R51), [SECURITY_ROUNDS_R101.md](SECURITY_ROUNDS_R101.md) (R52-R101), [SECURITY_ROUNDS_R151.md](SECURITY_ROUNDS_R151.md) (R102-R151), [SECURITY_ROUNDS_R201.md](SECURITY_ROUNDS_R201.md) (R152-R201), [SECURITY_ROUNDS_R251.md](SECURITY_ROUNDS_R251.md) (R202-R251) for the prior 250.

---

## Block AA — Browser / front-end security (R252–R261)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R252 | CSP strict-dynamic | Stored XSS via 'unsafe-inline' | Per-response nonce + audit refusing forbidden tokens |
| R253 | Trusted Types | DOM-XSS sinks (innerHTML, eval) | Require-trusted-types-for 'script' directive emitter |
| R254 | SubResource Integrity | Polyfill.io 2024 / CDN tamper | SHA-384 binding for external scripts; refuse unpinned |
| R255 | Permissions-Policy | Iframe API access (camera, mic, geo) | Strict-deny default + audit wildcard refusal |
| R256 | Clickjacking | Transparent-overlay UI hijack | X-Frame-Options DENY + frame-ancestors 'none' |
| R257 | COOP / COEP | Spectre re-enablement of timers | Cross-origin isolation header pair |
| R258 | Referrer-Policy | Token-in-URL leakage | strict-origin-when-cross-origin enforcement |
| R259 | WebAssembly sandbox | Compromised wasm CDN | Pinned-origin + raw-buffer instantiation refusal |
| R260 | Service Worker | XSS-installed persistent MITM | Same-origin + bounded scope + SHA-256 baseline |
| R261 | postMessage origin | Cross-frame postMessage hijack | Audit handlers without explicit origin allow-list |

## Block BB — Email + DNS depth (R262–R271)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R262 | SPF | Domain spoofing via +all | TXT record audit; RFC 7208 lookup count cap |
| R263 | DKIM | Forged signature / weak algo | Header parser + rsa-sha1 refusal |
| R264 | DMARC | Spoof against p=none domains | p=reject enforcement + rua aggregate report |
| R265 | BIMI / VMC | Forged brand logo in inbox | HTTPS SVG + VMC under strict DMARC |
| R266 | ARC | Forwarded-mail auth break | Chain validator (RFC 8617); refuse cv=fail |
| R267 | MTA-STS | STARTTLS strip (LightBasin 2021) | Policy audit; refuse mode!=enforce in prod |
| R268 | TLS-RPT | No visibility into TLS-downgrade attempts | Refuse missing rua aggregate target |
| R269 | DNSSEC | Cache poisoning + BGP-driven NS hijack | DS + DNSKEY presence audit via dnspython |
| R270 | DNS-over-TLS | Port-53 plaintext leakage | TLS 1.3-pinned DoT client + resolver allow-list |
| R271 | DNS exfil | Tunneling via subdomain entropy | Subdomain entropy + length + TXT + per-zone burst |

## Block CC — Storage + database hardening (R272–R281)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R272 | SQL parameterisation | f-string SQL injection | Source lint + runtime safe_query gate |
| R273 | Row-level security | Cross-tenant data leak via missing WHERE | RLS enabled/forced/USING(true) audit |
| R274 | Stored procedure | DEFINER + dynamic SQL escalation | Refuse SECURITY DEFINER with EXECUTE format() |
| R275 | pg_hba.conf | Postgres world-open with trust | Refuse trust/password/world-open entries |
| R276 | MongoDB auth | Open ES/Mongo / no-auth | World-bind + auth-disabled + weak TLS audit |
| R277 | Redis ACL | protected-mode no + RCE via CONFIG SET | Refuse protected-mode off + world-bind |
| R278 | Elasticsearch | xpack.security.enabled false | Audit anonymous + TLS + xpack.security |
| R279 | Backup encryption | S3 backup leak (Capital One 2019) | Refuse unencrypted + missing KMS + stale verify |
| R280 | Slow-query log | Bulk pull / repetitive expensive queries | Per-principal burn + bulk-rows + repeat-fingerprint |
| R281 | Pool exhaustion | One tenant starves connection pool | Per-principal cap + global ceiling fairness |

## Block DD — Application-layer threat modeling (R282–R291)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R282 | Business-logic race | Concurrent transfer (Starbucks 2014) | Per-key idempotency + in-flight lock |
| R283 | Workflow bypass | Skip KYC step (fintech bug bounties) | State-machine refusing out-of-order advance |
| R284 | API versioning | Downgrade to vulnerable v1 | Version state machine; retired returns 410 |
| R285 | GraphQL complexity | Deep-nest + alias DoS | Pre-execution depth + field-count + alias limit |
| R286 | WebSocket subprotocol | Confused-client attack | Server allow-list + audit unknown offers |
| R287 | SSE | Long-lived stream + CORS wildcard | Per-event size + per-stream rate + CORS audit |
| R288 | Webhook signature | Forged Stripe/GitHub events | HMAC-SHA-256 + skew + replay window |
| R289 | API auth boundary | Mixed key + OAuth grants | Per-route auth-class enforcement |
| R290 | Per-tenant fairness | Noisy tenant exhausts global quota | Per-tenant token bucket + global ceiling |
| R291 | gRPC reflection | API surface leak in prod | Refuse reflection registration in production |

## Block EE — Insider depth + capstone v6 (R292–R301)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R292 | USB block | Stuxnet / BadUSB on classified | Sysfs USB mass-storage device audit |
| R293 | Print egress | Snowden/Manning paper exfil | Per-user 24h pages + bytes + classification burst |
| R294 | Clipboard governor | Cmd+C exfil bypassing server caps | Per-event size + hourly + classified-doc cap |
| R295 | Endpoint telemetry | Keylogger without consent (ECPA / GDPR) | Consent record + event-class disclosure gate |
| R296 | Travel mode | Border search + theft risk | Refuse high-classification while travelling |
| R297 | Foreign influence | CFIUS-class beneficial-owner risk | Sanctioned-ISO + entity-hash counterparty score |
| R298 | Image steganography | LSB exfil in chat / marketing images | Chi-squared + pair-of-values LSB analyzer |
| R299 | Covert timing | Inter-packet-delay tunnel | Histogram-based timing-channel detector |
| R300 | Air-gap radio disable | Cellular/Wi-Fi/BT/NFC leak from classified | Refuse start unless every radio hardware-killed |
| R301 | Adversarial runner v6 | Full R252-R300 sweep | In-process probe corpus + Markdown report |

---

## How to run all 301 rounds

```bash
python -c "
from aria.security.guard import activate_all_rounds
loaded = activate_all_rounds(force_reload=True)
print(f'Loaded {len(loaded)} rounds')

# R51 (R1-R51 representative coverage)
from aria.security.rounds.r51_adversarial_runner import run as run_v1, render_report as render_v1
print(render_v1(run_v1()))

# R101 (R52-R101 v2)
from aria.security.rounds.r101_adversarial_runner_v2 import run_v2, render_v2
print(render_v2(run_v2()))

# R151 (R102-R150 v3)
from aria.security.rounds.r151_adversarial_runner_v3 import run_v3, render_v3
print(render_v3(run_v3()))

# R201 (R152-R200 v4)
from aria.security.rounds.r201_adversarial_runner_v4 import run_v4, render_v4
print(render_v4(run_v4()))

# R251 (R202-R250 v5)
from aria.security.rounds.r251_adversarial_runner_v5 import run_v5, render_v5
print(render_v5(run_v5()))

# R301 (R252-R300 v6)
from aria.security.rounds.r301_adversarial_runner_v6 import run_v6, render_v6
print(render_v6(run_v6()))

# R100 breach drill
from aria.security.rounds.r100_breach_drill import run_breach_drill, render_drill_md
print(render_drill_md(run_breach_drill()))
"
```

## What R252-R301 closes from SECURITY_LANDSCAPE.md

| Gap row in landscape doc | Round that closes / addresses it |
|--------------------------|----------------------------------|
| Browser CSP / Trusted Types / SRI | R252 + R253 + R254 |
| Permissions / clickjacking / isolation | R255 + R256 + R257 |
| Referrer-Policy / WASM / SW / postMessage | R258 + R259 + R260 + R261 |
| SPF / DKIM / DMARC / BIMI / ARC | R262 + R263 + R264 + R265 + R266 |
| MTA-STS / TLS-RPT / DNSSEC | R267 + R268 + R269 |
| DNS-over-TLS / DNS exfil | R270 + R271 |
| SQL parameterisation / RLS / stored proc | R272 + R273 + R274 |
| pg_hba / Mongo / Redis / Elasticsearch | R275 + R276 + R277 + R278 |
| Backup encryption + integrity | R279 |
| Slow-query forensics + pool fairness | R280 + R281 |
| Business-logic race / workflow bypass | R282 + R283 |
| API versioning / GraphQL / WS / SSE | R284 + R285 + R286 + R287 |
| Webhook sig + auth-class boundary | R288 + R289 |
| Per-tenant fairness + gRPC reflection | R290 + R291 |
| USB block / print / clipboard | R292 + R293 + R294 |
| Endpoint-telemetry consent | R295 |
| Travel mode / foreign influence | R296 + R297 |
| Image steg / covert timing / radio kill | R298 + R299 + R300 |
| Adversarial regression v6 | R301 |

After R301 the residual rows in SECURITY_LANDSCAPE.md are **strictly hardware** (FIPS 140-3 L3 HSM device, real TPM 2.0 chip, line-rate IPS appliance, hardware-backed FIDO2 fleet, physical fibre data diode, real QKD appliance, RF-shielded enclosure) or **strictly operator-side** (classified threat-intel feeds, formal verification of safety-critical kernels, counter-intel opsec, kernel EDR like CrowdStrike Falcon, dedicated 24/7 SOC, NSA-cleared SCIF infrastructure, biometric continuous-authentication hardware).
