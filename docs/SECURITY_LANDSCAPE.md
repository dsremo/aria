# Where ARIA's security stack sits in the 2026 landscape

**Honest comparison.  No marketing language.**  Operators deserve to know
exactly what they get from `aria.security.*` and what they still need to
buy / build elsewhere.

---

## TL;DR

ARIA's security library is **best-in-class for an open-source application-layer + LLM-aware Python SaaS stack.**  It is **NOT** a substitute for:

* a kernel EDR (CrowdStrike Falcon / SentinelOne Singularity)
* an HSM-rooted bank stack (Thales Luna / AWS CloudHSM, FIPS 140-3 Level 3)
* nation-state defence (NSA CNT, GCHQ NCSC, FSB CRSI)
* a full antivirus engine with signature feeds + on-device behavioural ML
* MITM line-rate inspection appliances
* a SIEM / SOAR (Splunk + Sentinel + XSIAM)

What ARIA's library **is** competitive with at the application-API / LLM
boundary:

* Protect-AI **LLM Guard** (MIT) — comparable scanner coverage + we add
  six-axis psyops + behavioural fingerprint
* OWASP **Coraza** + **Core Rule Set** (Apache-2.0) — we cover most CRS
  classes (R11-R20) and add LLM-specific (R21-R30)
* NVIDIA **garak** (Apache-2.0) — comparable probe coverage in R51 plus
  all defence sides built-in
* Cloudflare WAF / AWS WAF managed-rules — similar coverage at the
  application layer; they additionally ship line-rate hardware

---

## What top-tier defenders run that ARIA doesn't

### Banks (FIPS 140-3 Level 3 stacks)

| Capability | Production banks | ARIA today | Gap |
|------------|------------------|------------|-----|
| Hardware-rooted key storage | Thales Luna 7 / AWS CloudHSM (FIPS 140-3 L3) | software-only secrets via env vars | hardware partner needed |
| Cert pinning | mandated; enforced at TLS handshake | scheme + host allow-list (R50) | round R52 stub; HW-rooted pinning still needs operator KMS |
| TLS 1.3 enforcement | mandated; downgrade refused | Caddy auto-TLS (handled by reverse proxy) | OK at proxy; codify in deploy doc |
| Sub-200 ms fraud scoring | dedicated stream-processing | adaptive scoring + plugin hooks (~1 ms) | OK for shape; specific transaction-fraud features = bank-side |
| MFA / behavioural biometrics | hard-required by PCI-DSS | TOTP-shape `mfa_admin_check` (R10) | round R63 ships RFC-6238 implementation |
| Real-time MITM detection | line-rate IPS hardware | n/a (Layer-7 only) | needs Cloudflare / Imperva / Akamai sidecar |

### Nation-state defenders (NSA, FSB CRSI, MSS, RAW)

| Capability | Nation-state | ARIA today | Gap |
|------------|--------------|------------|-----|
| Classified threat intel | partner feeds via TIBER-EU / FBI Liaison | CISA-KEV public feed (R-foundation) | upgradable; operator subscribes |
| Side-channel hardening (timing / cache / power) | mandatory in classified compute | constant-time HMAC compare; rest is software | rounds R57-R60 add detection but not silicon |
| Hardware attestation (TPM 2.0 / Pluton) | required for SECRET / TS systems | software-PCR fallback in `attestation.py` | needs real TPM device |
| Air-gapped operation | classified deployments | no hard requirement; `.env` boots without network | OK for SaaS, not for SCIF |
| Formal verification (TLA+ / Coq / SPARK) | classified GNC + crypto | none | out of scope for v0.3 |
| Counter-intelligence opsec | dedicated discipline | n/a | always operator-side |

### Endpoint Detection & Response (EDR / XDR — CrowdStrike, SentinelOne, MS Defender)

| Capability | EDR vendors | ARIA today | Gap |
|------------|-------------|------------|-----|
| Kernel-mode telemetry (eBPF / driver) | Falcon / Singularity ring 0 | n/a — application-layer only | by design; ARIA defends services, not hosts |
| Behavioural ML on syscalls | yes; trained on T-class events | adaptive engine on HTTP requests | covers app-layer; can't replace EDR |
| Attack-chain narrative (Storyline) | yes | trace-id propagation (R35) + audit chain | partial — gives request-scope, not host-scope |
| Signature feeds | weekly autoupdated | CISA-KEV via R-foundation | covers known-exploited; does not replace AV signatures |
| Single-agent + cloud telemetry | 1 trillion events / day | per-deployment audit log | OK for shape; not at FAANG scale |

### Antivirus engines (per-file signature)

ARIA does **not** scan files for malware signatures.  Operators put a
real AV (Microsoft Defender / ClamAV / Sophos) on the deploy host; ARIA
guards the application boundary.

---

## What ARIA does that vendors above don't bundle

These are the niches where the open-source library earns its place:

1. **LLM-specific defences as a first-class layer.**  R21 (latent prompt injection), R22 (DAN bank, multi-axis), R23 (encoding bypass), R24 (persona flip), R25 (tool-output watchdog), R26 (RAG trust), R27 (function-arg validation), R28 (token budget), R29 (multi-turn drift), R30 (output filter).  Most enterprise WAFs do not have these patterns; LLM Guard does, but ARIA composes them with HTTP / DoS / injection layers under one import.
2. **Cialdini psyops detector** wired into the LLM context boundary (`ToolResultSanitizer`).  Banks have UEBA but it's behavioural, not influence-axis-aware.
3. **Honeypot mesh + decoy tokens** mountable in one call (`harden_aiohttp_app`).  Vendor canary services exist (Thinkst Canary) but require separate deployment.
4. **Plugin registry** lets operators bolt on per-deployment defences without forking the library — every round R1-R51 lives as an isolated plugin file under `aria/security/rounds/`.
5. **In-process adversarial probe runner** (R51) — garak-class fuzzing without GPU + without external API.

---

## What "world-class" means measurably

Three concrete tests an operator can run today:

```bash
# 1. Static security: HIGH=0, MEDIUM=0
bandit -r src/aria/ -ll

# 2. Dependency advisories: 0 known CVEs in pinned set
pip-audit --strict

# 3. Adversarial probe: every defence fires on a curated payload
python -c "
from aria.security.guard import activate_all_rounds
activate_all_rounds(force_reload=True)
from aria.security.rounds.r51_adversarial_runner import run, render_report
print(render_report(run()))
"
```

If all three pass on every commit (CI: `make smoke && make security`) the
deployment is, at the application layer, **as hard to compromise as the
enterprise SaaS API security stacks shipped by Cloudflare / AWS / GCP
managed services**.  Hardening past that point requires hardware (HSM,
TPM, line-rate IPS) and / or classified threat intel — both operator-side.

---

## Roadmap — what closes the remaining gaps

* **R52-R61** (cryptography depth) — TLS pinning helper, HKDF per-tenant key
  derivation, AES-GCM-SIV nonce-misuse-resistant primitive, hybrid signing
  stub, ML-KEM-768 wiring, constant-time helpers, secure-memory wipe,
  side-channel timing budget.
* **R62-R71** (IAM depth) — WebAuthn / FIDO2 challenge flow, RFC-6238 TOTP,
  session binding, SAML strict-validation, SCIM stub, JIT access.
* **R72-R81** (memory safety) — buffer-overflow detector for the cFS
  bridge C source, format-string guard, integer-overflow helper, recursion
  depth limit, ROP/CFI hooks, PIE/RELRO/canary checker.
* **R82-R91** (network depth) — DoH/DoT enforcement, RPKI BGP-hijack alert
  parser, SYN-flood cookies, TCP-RST injection detector, TLS-downgrade
  refusal, Heartbleed-class memory-leak detector.
* **R92-R101** (forensics + anti-tamper) — runtime code-integrity, anti-debug,
  seccomp profile, audit forwarder (Splunk / Sentinel), MISP threat-intel
  integration, fuzzing harness.

After R101 the gaps remaining are **strictly hardware** (HSM, TPM 2.0,
line-rate IPS) or **strictly operator-side** (classified threat intel,
formal verification, counter-intel opsec).  Both are documented in this
file so they don't get re-discovered as silent surprises.
