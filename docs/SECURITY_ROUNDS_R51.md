# R51 — 51 round-by-round defences

**Audited:** 2026-04-26
**Library entry point:** `from aria.security.guard import activate_all_rounds, ...`
**Test surface:** 112 per-round regressions in `tests/integration/test_security_rounds.py`
**Combined security tests:** 181 green
**Plugin registry:** every round registers a `DefencePlugin` so the per-request middleware fires its hook automatically.

This document is the operator-readable index of all 51 rounds.  The R50 audit
(see [SECURITY_AUDIT_R50.md](SECURITY_AUDIT_R50.md)) covered the *static-defence*
foundation; this round-by-round walk adds adaptive, attack-class-specific defences
each tied to a real CVE / breach.

| # | Topic | Threat (real-world example) | Defence |
|---|-------|------------------------------|---------|
| R1 | Credential stuffing | Snowflake/UNC5537 (2024) | shape-bucketed velocity score blocks tokens seen across ≥ 4 IPs / 5 min |
| R2 | Token-leak in error responses | Hugging Face token leak (2024) | scrub AWS/GitHub/Slack/JWT/API-key shapes from 4xx/5xx bodies |
| R3 | JWT alg=none / alg-confusion | CVE-2024-53861 PyJWT regression | refuse banned alg before any signature check |
| R4 | IDOR | Dell unauth API leak (2024) | tenant-bound resource lookup helper + audit on cross-tenant attempt |
| R5 | OAuth state-CSRF + redirect_uri | Salesforce CRM connectors (2023) | HMAC-bound state + exact-match URI allow-list |
| R6 | Mass assignment | Rails/Mongoose class | `strict_fields()` + scorer flagging internal field names |
| R7 | HTTP parameter pollution | SonicWall SSL-VPN bypass (2023) | block duplicate query keys with conflicting values |
| R8 | Anti-replay | Plaid/Capital-Group API replay (2023-24) | nonce ledger; 5-min eviction |
| R9 | Geographic / impossible-travel | AT&T / Microsoft Midnight Blizzard (2024) | per-token Haversine speed; opt-in GeoIP |
| R10 | Sealed forward-only audit | Insider-threat hardening | hourly chmod-444 seal of chain head |
| R11 | NoSQL injection | CWE-943 generic | refuse `$where`/`$regex`/`$expr` in JSON bodies |
| R12 | SSTI | Confluence (2022 still scanned 2024) | block Jinja/Mako/JSP markers |
| R13 | OS command injection | CVE-2025-29635 D-Link (CISA KEV) | `safe_shell_arg()` + metachar-density scorer |
| R14 | LDAP injection | Generic CWE-90 | `escape_ldap_filter` + scorer |
| R15 | XPath injection | CWE-643 | `escape_xpath_string` + scorer |
| R16 | CSV / spreadsheet formula | Excel DDE / HYPERLINK class | `escape_csv_field` + safe_writerow |
| R17 | Email header injection | Sendgrid (2024) | refuse CR/LF + `Bcc:`/`Cc:` keywords |
| R18 | HTTP Host-header injection | Cache poisoning class | 421 hosts outside `ARIA_ALLOWED_HOSTS` |
| R19 | TOCTOU | SimpleHelp CVE-2024-57728 | `open_locked_read` with O_NOFOLLOW + post-stat verify |
| R20 | ReDoS | CVE-2024-43374 cpython | `timed_search` watchdog + `is_pattern_safe` |
| R21 | Latent prompt injection | Microsoft Spotlighting (2024) | spotlight-fence external content; flag instruction heads |
| R22 | DAN-class jailbreak | NVIDIA garak corpus | multi-axis (persona/token-economy/alignment) |
| R23 | Encoding-bypass jailbreak | base64/hex/rot13/ZWSP | detect-then-decode-then-rescan |
| R24 | Persona-flip / role-play override | "grandma jailbreak" class | short-form persona-redefine detector |
| R25 | LLM tool-output watchdog | WaspBench / Backbone Jailbreak (2024) | block tool-call loops, exfil patterns, decoy args |
| R26 | RAG / retrieval poisoning | PoisonedRAG (USENIX 2024) | provenance + freshness + DAN trust score |
| R27 | LLM function-arg validation | Schema-shape but hostile values | `validate_args` with hostile-content per-field check |
| R28 | Token-budget exhaustion | Context-window stuffing | per-identity sliding 60-s token budget |
| R29 | Multi-turn jailbreak / drift | Many-Shot Jailbreak (frontier-lab research, 2024) | per-session cumulative influence + persona-flip |
| R30 | LLM output-side filter | Memorisation leak / unsafe CTA | scrub secrets + decoys + call-to-action |
| R31 | Slowloris | Cloudflare 2024 advisory | byte-rate floor middleware (1 KiB/s after 5-s grace) |
| R32 | HTTP/2 RAPID-RESET | CVE-2023-44487 (100 M+ rps) | per-connection RST_STREAM detector + nginx config |
| R33 | WebSocket flood | DoS class | per-connection token bucket (100 burst / 20 sustained) |
| R34 | Gzip / Brotli decompression bomb | CWE-409 | bounded-output decoder; raise on bomb |
| R35 | Hash flooding | CCC 2011 / PEP-456 | refuse JSON > 10 K keys; refuse fixed `PYTHONHASHSEED` |
| R36 | Subprocess fork-bomb | OS process-table exhaustion | semaphore + RLIMIT_NPROC/AS/CPU on child |
| R37 | Per-request memory cap | Handler runaway | `tracemalloc` snapshot diff; raise post-hoc |
| R38 | Per-IP connection cap | TCP exhaustion | counter + nginx `limit_conn` snippet |
| R39 | Per-tenant bandwidth cap | Egress link saturation | rolling-window byte budget (1 GiB/min default) |
| R40 | HTTP keep-alive idle abuse | Socket-hold class | per-connection idle timer; close after 30 s |
| R41 | Wheel hash verification | XZ Utils (2024) | `sha256_of_file` + RECORD verification |
| R42 | Dependency confusion / typosquatting | Birsan disclosure (2021), npm waves | allow-list vs lockfile + known-typosquat shapes |
| R43 | Lockfile-diff CI gate | Silent transitive upgrade | `diff_lockfiles` + PR-comment renderer |
| R44 | GitHub Actions hardening | tj-actions/changed-files (2024) | scan workflows for unpinned actions + script-injection |
| R45 | Read-only rootfs + cap-drop | Container persistence | audit Dockerfile + compose; emit K8s PodSpec |
| R46 | Repo secret-scan | Pre-commit / pre-push | walk paths for secret-shape patterns |
| R47 | Two-person rule | Snowflake / Storm-0558 (2024) | dual-token authoriser distinct-principal check |
| R48 | Production-mode strict boot | Twilio Authy debug-endpoint leak (2024) | refuse to start with default tokens / debug flags |
| R49 | Debug-endpoint refusal | Spring Boot `/actuator/heapdump` (2024) | block `/debug`, `/_internal`, `/actuator` in prod |
| R50 | First-outbound-host audit | Drive-by new dependency | record + log first call to any new host |
| R51 | Adversarial probe runner | Garak-style multi-vector | in-process probe corpus over all rounds |

---

## Architecture

```
┌──────────────────────────── HTTP request ────────────────────────────┐
│                                                                       │
│  R32 RAPID-RESET ◄──┐                                                 │
│  R31 Slowloris      │   reverse proxy / aiohttp guard middleware     │
│  R38 Conn cap       ├──► R7 param pollution                          │
│  R40 keep-alive     │   ► R18 host header                             │
│  ...                │   ► R31 slow-body                               │
│                     │                                                 │
│            ▼ harden_aiohttp_app  (security headers, request-id, ...)  │
│                                                                       │
│            ▼ adaptive middleware (entropy / novelty / Markov / behav) │
│                                                                       │
│            ▼ plugin.fire_request(...)                                 │
│                  ├── R1 credential velocity                           │
│                  ├── R3 JWT alg                                       │
│                  ├── R7 param pollution                               │
│                  ├── R9 impossible travel                             │
│                  ├── R18 host header                                  │
│                  ├── R49 debug path block                             │
│                  └── …                                                │
│                                                                       │
│            ▼ score_request (composes plugin on_score hooks)           │
│                  ├── R6  mass assignment                              │
│                  ├── R11 NoSQL                                        │
│                  ├── R12 SSTI                                         │
│                  ├── R13 cmd-inj                                      │
│                  ├── R14 LDAP                                         │
│                  ├── R15 XPath                                        │
│                  ├── R21 latent prompt-injection                      │
│                  ├── R22 DAN                                          │
│                  ├── R23 encoded jailbreak                            │
│                  ├── R24 persona flip                                 │
│                  ├── R35 hash flood                                   │
│                  └── …                                                │
│                                                                       │
│            ▼ handler (screener / advisor / dashboard)                 │
│                                                                       │
│            ▼ plugin.fire_response(...)                                │
│                  ├── R2  token-leak scrub                             │
│                  ├── R30 output filter                                │
│                  └── …                                                │
└───────────────────────────────────────────────────────────────────────┘
```

## How rounds compose

Each round registers a `DefencePlugin`.  Most plugins implement one or two
of the five hook points:

  * **`on_request(request, body)`** — may raise to abort the request (the
    adaptive middleware turns `RuntimeError("R<n>....")` into HTTP 403).
  * **`on_response(request, body)`** — last-mile mutation of outbound bytes.
  * **`on_score(endpoint, payload, identity)`** — feeds `score_request`;
    composes via max with the entropy / novelty / Markov axes.
  * **`on_outbound_url(url)`** — every `safe_open_url` call.
  * **`on_audit(event)`** — every `log_event` call.

Every round whose tests pass is wired into `harden_aiohttp_app` automatically
by virtue of registering through the plugin bus.  No code in the screener,
advisor, or dashboard changes when a new round lands — only the round file.

## Reproducible run

```bash
# Foundation + every round
pytest tests/integration/test_security_guard.py
pytest tests/integration/test_security_foundation.py
pytest tests/integration/test_security_rounds.py

# Adversarial probe runner (R51) — in-process garak-class
python -c "
from aria.security.guard import activate_all_rounds
activate_all_rounds(force_reload=True)
from aria.security.rounds.r51_adversarial_runner import run, render_report
print(render_report(run()))
"

# Smoke + screener
make smoke
```

## Open-source attribution

Patterns + concepts studied (clean-room implementation, license-compatible):

* **NVIDIA garak** (Apache-2.0) — DAN/encoding/latent-injection probe taxonomy
* **protectai/llm-guard** (MIT) — input-scanner architecture
* **OWASP Coraza + CRS** (Apache-2.0) — WAF rule organisation
* **CISA KEV** (public-domain) — known-exploited-vulnerability catalogue
* **Cialdini** (academic public domain) — six-axis persuasion taxonomy

## Residual risk

Items deferred or operator-action-only after R51:

* **Hardware TPM attestation** — code path stubbed; needs real TPM device.
* **WebAuthn / FIDO2 admin** — protocol stubs; awaits operator deployment.
* **Geo-IP database** — opt-in via `configure_geoip_lookup()`; we ship no DB.
* **Real-time MITM detector** — requires line-rate inspection; out of process scope.
* **Hardware-rooted secret store** — handled by Caddy / nginx + KMS.

These are documented (each round's docstring states what's not in scope) so a
future R75 audit re-discovers them as deliberate gaps, not unknown holes.
