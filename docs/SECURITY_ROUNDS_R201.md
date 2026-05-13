# R152-R201 — fifty more round-by-round defences

**Audited:** 2026-04-26
**Library entry:** `from aria.security.guard import activate_all_rounds, ...`
**Tests (per file):** 66 R152-R201 + 58 R102-R151 + 70 R52-R101 + 112 R1-R51 + 34 guard + 19 foundation = **359 security tests** (plus 143 smoke)
**Composition:** every R152-R201 round registers a `DefencePlugin` exactly like R1-R151.

This document is the **R152-R201 supplement** — the fourth 50 rounds adding zero-trust mesh, GRC/compliance, mobile/IoT, advanced AI alignment, and DFIR/forensics. See [SECURITY_ROUNDS_R51.md](SECURITY_ROUNDS_R51.md) (R1-R51), [SECURITY_ROUNDS_R101.md](SECURITY_ROUNDS_R101.md) (R52-R101), and [SECURITY_ROUNDS_R151.md](SECURITY_ROUNDS_R151.md) (R102-R151) for the prior 150.

---

## Block Q — Zero-trust networking + service mesh (R152–R161)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R152 | Istio AuthorizationPolicy | Default-permissive mesh (Tesla 2018) | deny-all + per-principal ALLOW YAML generator |
| R153 | BeyondCorp posture | Stolen laptop with valid session | DevicePosture → ALLOW / LIMITED / DENY |
| R154 | SPIFFE/SPIRE SVID | IP-based service auth spoof | spiffe:// URI parser + trust-domain verifier |
| R155 | Envoy ext_authz | Misconfigured filter fail-open | ALLOW/DENY decision builder; raises on missing principal |
| R156 | gRPC mTLS | Plaintext gRPC inside mesh | Channel factory; refuses insecure default in prod |
| R157 | Microsegmentation | Flat VPC + lateral movement | Allow-list flow audit; refuses out-of-policy |
| R158 | ECH / Encrypted SNI | SNI-based censorship + DPI | Runtime ECH support detector |
| R159 | WireGuard config | Default-route peer = open VPN | Audit peer list + flag 0.0.0.0/0 |
| R160 | Zero-trust tunnel | Public admin port surface | Refuse public listeners outside allow-list in prod |
| R161 | Per-request authz | Per-conn authz misses revocation | Combine SPIFFE + posture + scope; ledger |

## Block R — Compliance / GRC (R162–R171)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R162 | NIST 800-53 Rev 5 | Controls implemented but unmapped | Static control → ARIA round map for SSP |
| R163 | SOC 2 Type II | Audit-time evidence scramble | TSC → ARIA round evidence collector |
| R164 | ISO/IEC 27001:2022 | Annex A re-write each cycle | 28-control SoA table generator |
| R165 | FedRAMP Moderate | "FedRAMP-ready" without coverage | Family-level gap report against R162 |
| R166 | GDPR DSAR | Ad-hoc PII exports under deadline | Art. 15/17/20 export + erasure dispatcher |
| R167 | HIPAA PHI scrub | Safe-Harbor PHI in logs | Redact 18 identifiers from text |
| R168 | PCI-DSS scope | Unsegmented CDE | Classify CDE/Connected/OutOfScope; refuse unseg-CDE |
| R169 | CIS Linux Level 1 | Baseline drift | Spot-check sshd/cron/passwd/kmods |
| R170 | Log retention | Too-short or too-long retention | Per-class TTL + grace; emit keep/delete |
| R171 | Incident response | No playbook → MTTR doubles | Open + close gate (artefacts required by severity) |

## Block S — Mobile / IoT / embedded (R172–R181)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R172 | Android Network Security Config | Cleartext + user-CA trust on release | Audit XML + emit strict pinned template |
| R173 | iOS App Transport Security | NSAllowsArbitraryLoads exceptions | Plist audit; refuse arbitrary loads on release |
| R174 | MQTT broker auth | Open / default-cred IoT brokers | Refuse anon, cleartext, default creds |
| R175 | CoAP DTLS | Shared fleet PSK | Profile audit + per-device HKDF derivation |
| R176 | Firmware signing | Unsigned LoJax-class firmware | Ed25519 chain verifier across boot stages |
| R177 | CBOR safe types | Tag-bomb / depth DoS on MCU | Strict-types loader, no tags, depth-limited |
| R178 | Bluetooth pairing | Just-Works MITM | Pairing-method audit; refuse Just-Works for sensitive |
| R179 | Zigbee link key | Well-known TC link key | Refuse 5A696742... + rotation policy |
| R180 | OTA update | Rollback / replay | Sig + anti-rollback + fresh-nonce HMAC |
| R181 | JTAG/SWD/UART | Live debug port in production | Manifest validator + kgdb runtime probe |

## Block T — Advanced AI safety / alignment (R182–R191)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R182 | Sandbagging | Capability suppression on evals (Apollo 2024) | Paired-prompt gap detector |
| R183 | Deceptive alignment | Sleeper Agents (Hubinger 2024) | eval-vs-prod refusal-rate gap |
| R184 | Goal misgeneralisation | Sycophancy + intent drift | Intent-conflict probe scorer |
| R185 | Honest reporting | Self-report ≠ verified outcome (METR) | Honesty rate ledger |
| R186 | Capability eval gate | RSP enforcement gap | Per-capability deploy gate + waiver |
| R187 | Refusal consistency | Paraphrase-induced jailbreak | N-paraphrase divergence audit |
| R188 | Power-seeking | Instrumental resource accumulation | Per-session suspicious-action rate |
| R189 | Capability budget | Tool-call flood / hijacked agent | Per-capability token bucket |
| R190 | Constitutional invariant | Multi-turn rationalised harm | Pattern-bank audit per response |
| R191 | Red-team diversity | Inflated coverage from similar prompts | Bigram entropy + length + unique-ratio floor |

## Block U — DFIR / forensics + capstone (R192–R201)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R192 | Memory forensics | Lost in-RAM artefacts | gcore preferred, /proc/maps fallback |
| R193 | Process tree timeline | Can't reconstruct exec sequence | Walk /proc → sorted timeline |
| R194 | File-integrity monitor | Rootkit / persistence | Tripwire-class SHA-256 baseline + drift |
| R195 | Active deception | No detection between foothold and exfil | Decoy creds + atime watch |
| R196 | Hunt DSL | Ad-hoc grep misses cross-shape events | Tiny `field op value AND/OR` compiler |
| R197 | SOAR playbook | Detection without response | Named-playbook dispatcher → R171 incident |
| R198 | Volatile preservation | Sockets/env/fds/threads vanish on exit | Snapshot + redacted env bundle |
| R199 | Chain of custody | Evidence inadmissible (FRE 901) | Hash-chain ledger; one-pass verify |
| R200 | Continuous control monitoring | Drift between point-in-time audits | Periodic check registry + history |
| R201 | Adversarial runner v4 | Full R152-R200 sweep | In-process probe corpus + Markdown report |

---

## How to run all 201 rounds

```bash
python -c "
from aria.security.guard import activate_all_rounds
loaded = activate_all_rounds(force_reload=True)
print(f'Loaded {len(loaded)} rounds')

# R51 (R1-R51 representative coverage)
from aria.security.rounds.r51_adversarial_runner import run as run_v1, render_report as render_v1
print(render_v1(run_v1()))

# R101 (R52-R101 full-stack v2)
from aria.security.rounds.r101_adversarial_runner_v2 import run_v2, render_v2
print(render_v2(run_v2()))

# R151 (R102-R150 v3)
from aria.security.rounds.r151_adversarial_runner_v3 import run_v3, render_v3
print(render_v3(run_v3()))

# R201 (R152-R200 v4)
from aria.security.rounds.r201_adversarial_runner_v4 import run_v4, render_v4
print(render_v4(run_v4()))

# R100 breach drill
from aria.security.rounds.r100_breach_drill import run_breach_drill, render_drill_md
print(render_drill_md(run_breach_drill()))
"
```

## What R152-R201 closes from SECURITY_LANDSCAPE.md

| Gap row in landscape doc | Round that closes / addresses it |
|--------------------------|----------------------------------|
| Service mesh / east-west authz | R152 + R155 + R161 |
| Workload identity (SPIFFE/SPIRE) | R154 |
| BeyondCorp / device posture | R153 |
| gRPC mTLS in mesh | R156 |
| Microsegmentation enforcement | R157 |
| ECH / SNI privacy | R158 |
| WireGuard / Tailscale-class tunnel | R159 + R160 |
| NIST SP 800-53 Rev 5 mapping | R162 |
| SOC 2 Type II evidence | R163 |
| ISO/IEC 27001:2022 SoA | R164 |
| FedRAMP Moderate baseline | R165 |
| GDPR DSAR (Art. 15/17/20) | R166 |
| HIPAA PHI scrub | R167 |
| PCI-DSS scope segmentation | R168 |
| CIS Linux Benchmark Level 1 | R169 |
| Log retention policy | R170 |
| Incident response runbook gate | R171 |
| Android Network Security Config | R172 |
| iOS App Transport Security | R173 |
| MQTT / CoAP IoT auth | R174 + R175 |
| Firmware signing chain | R176 + R180 |
| Constrained-device CBOR | R177 |
| Bluetooth + Zigbee pairing | R178 + R179 |
| Embedded debug-port disable | R181 |
| Sandbagging / sleeper agents | R182 + R183 |
| Goal-misgeneralisation / sycophancy | R184 |
| Honest reporting (METR) | R185 |
| RSP-style capability gate | R186 |
| Refusal consistency | R187 |
| Power-seeking + resource budget | R188 + R189 |
| Constitutional invariant | R190 |
| Red-team prompt diversity | R191 |
| Memory forensics | R192 |
| Process-tree timeline | R193 |
| Host file-integrity monitor | R194 |
| Active deception (decoys) | R195 |
| Threat-hunt DSL | R196 |
| SOAR playbook automation | R197 |
| Volatile artefact preservation | R198 |
| Chain of custody | R199 |
| Continuous control monitoring | R200 |
| Adversarial regression v4 | R201 |

After R201 the residual rows in SECURITY_LANDSCAPE.md are **strictly hardware** (FIPS 140-3 L3 HSM device, real TPM 2.0 chip, line-rate IPS appliance, hardware-backed FIDO2 fleet) or **strictly operator-side** (classified threat-intel feeds, formal verification of safety-critical kernels, counter-intel opsec, kernel EDR like CrowdStrike Falcon, dedicated SOC 24/7 staffing).
