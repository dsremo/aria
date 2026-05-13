# R102-R151 — fifty more round-by-round defences

**Audited:** 2026-04-26
**Library entry:** `from aria.security.guard import activate_all_rounds, ...`
**Tests (per file):** 58 R102-R151 + 70 R52-R101 + 112 R1-R51 + 34 R50 + 19 foundation + 16 screener = **309 security tests** (plus 143 smoke)
**Composition:** every R102-R151 round registers a `DefencePlugin` exactly like R1-R101.

This document is the **R102-R151 supplement** — the third 50 rounds adding hardware-rooted trust, container/K8s, cloud-native, advanced-LLM, and specialised attacks.  See [SECURITY_ROUNDS_R51.md](SECURITY_ROUNDS_R51.md) (R1-R51) and [SECURITY_ROUNDS_R101.md](SECURITY_ROUNDS_R101.md) (R52-R101) for the prior 100.

---

## Block L — Hardware-rooted trust (R102–R111)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R102 | TPM 2.0 quote/verify | Compromised host runs tampered binary (LoJax / BlackLotus) | `request_quote` + `verify_quote`; software-PCR fallback |
| R103 | HSM PKCS#11 | FIPS 140-3 L3 path required by banks | sign/verify wrapper; HSM never releases key |
| R104 | Secure-boot chain | UEFI Secure Boot bypass | EFI-var read + kernel/initrd hash baseline |
| R105 | Hardware RNG | Entropy starvation in cloud VMs | hwrng > GRND_RANDOM > urandom cascade |
| R106 | Sealed storage | Disk-clone attack | TPM seal + AES-GCM-SIV soft fallback |
| R107 | Remote attestation | Fleet-join spoofing | challenge/response wired to R102 + R8 |
| R108 | AES key-wrap (RFC 5649) | Plaintext-key in transit | KWP wrap; HSM PKCS#11 path |
| R109 | Cache-timing safe | Bernstein 2005 / Flush+Reload | oblivious_lookup XOR-mask shape |
| R110 | RowHammer / cosmic-ray | DRAM bit-flip | CRC32 + SHA-256 ECC wrapper |
| R111 | Spectre/Meltdown | Speculative-exec leaks | Parse `/sys/.../vulnerabilities/*`; refuse "Vulnerable" in prod |

## Block M — Container / Kubernetes (R112–R121)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R112 | K8s admission | hostNetwork / privileged / hostPath=/ pods | Pod-spec validator for OPA / Kyverno |
| R113 | NetworkPolicy | Default-permissive cluster (Tesla 2018) | Deny-by-default + per-component YAML generator |
| R114 | Cosign image signing | Polyfill-class registry tamper | `cosign verify` wrapper |
| R115 | Runtime drift | In-container binary swap | Boot snapshot + on-demand SHA-256 verify of critical paths |
| R116 | mTLS | Service-to-service plaintext | Strict context factory + SAN verifier |
| R117 | Namespace isolation | Shared host PID/net/IPC | Refuse production start without isolation |
| R118 | Resource quota | Memory / fork bomb | setrlimit caps; refuse infinite rlimits in prod |
| R119 | Secret-volume | Env-var secret in `/proc/<pid>/environ` | Refuse env secrets in prod; projected-volume YAML |
| R120 | Pod Security Standards | PSS Restricted compliance | `check_pss` for Baseline + Restricted profile |
| R121 | SLSA in-toto provenance | Tampered toolchain (XZ-class) | `cosign verify-attestation` SLSA wrapper |

## Block N — Cloud-specific (R122–R131)

| # | Topic | Threat (real) | Defence |
|---|-------|---------------|---------|
| R122 | AWS IMDSv2 enforcement | Capital One 2019 | Refuse production with IMDSv1 still answering |
| R123 | S3 bucket policy | Public-bucket leaks | Lint Principal=* + missing SecureTransport |
| R124 | IAM least-privilege | Action=*+Resource=* | Refuse wildcards on dangerous action set |
| R125 | KMS rotation (PCI-DSS 3.6.4) | Stale master key | Audit key rotation status |
| R126 | CloudTrail integrity | Log-tamper to hide footprint | `aws cloudtrail validate-logs` wrapper |
| R127 | sts:AssumeRole ExternalId | Confused-deputy class | Refuse cross-account trust without ExternalId |
| R128 | STS session duration | 12-h stolen-token window | Audit `MaxSessionDuration` ≤ 1 h |
| R129 | Cloud secret manager | Env-var secret exposure | Pluggable AWS Secrets Manager / Vault fetch |
| R130 | Lambda sandbox | EOL runtime / no DLQ / huge timeout | Audit function config |
| R131 | VPC flow log | Exfil hidden in normal traffic | Parse v2 logs; merge with R90 IP reputation |

## Block O — Advanced LLM (R132–R141)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R132 | GCG / AutoDAN suffix | Gradient-optimised adversarial suffix | Char-class + natural-ratio + punct-burst scorer |
| R133 | Multi-modal injection | Image / OCR caption carrying instructions | Score caption text for instruction shapes |
| R134 | RAG re-ranker poisoning | PoisonedRAG (USENIX 2024) | Drop high-similarity short docs that look like influence/DAN |
| R135 | Memory injection | Persistent malicious memory entry | Filter every write through R26 trust scoring |
| R136 | Self-reflection bypass | "Imagine you're reviewing your own response" | Pattern bank + R24 compose |
| R137 | Multi-agent coordinated attack | X-Teaming 2025 | Cross-agent verb+object detector |
| R138 | Output watermarking | Attacker republishes ARIA output | HMAC-SHA-256 sidecar |
| R139 | Prompt provenance | Mid-flight prompt edit | Hop-by-hop hash chain + verify |
| R140 | Indirect tool-loop | Oracle-style multi-hop exfil | Repeated tool with shifting args ⇒ block |
| R141 | JBB-Behaviors taxonomy | 100 forbidden-content classes | `classify_behavior` to 10-category mapping |

## Block P — Specialised + capstone (R142–R151)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R142 | Padding oracle (Lucky-13 / Bleichenbacher) | Differential decrypt errors | Unified error response + constant-time pad check |
| R143 | XSSI | Cross-origin JSON read via `<script>` | `)]}'` prefix + refuse raw-array roots |
| R144 | Subdomain takeover | Dangling CNAME to S3/Heroku/etc | Resolve + check provider-family + dangling check |
| R145 | DNS CAA + DMARC + SPF | Rogue-CA mis-issuance + email forge | Audit DNS records present + DMARC policy ≠ none |
| R146 | Polyglot file | ZIP+PDF+HTML hybrid bypass | Detect > 1 magic-byte format |
| R147 | Zero-width Unicode steganography | Covert payload via ZWSP | Count + score zero-width / bidi chars |
| R148 | NFKC + confusable | Cyrillic-Latin homograph (apple → аpple) | Canonicalize + detect-confusable script mix |
| R149 | Cookie security flags | Missing Secure/HttpOnly/SameSite | Audit + safe Set-Cookie minter |
| R150 | Request-ID uniqueness | Audit-log correlation collision | 24 h horizon + collision detect |
| R151 | Adversarial runner v3 | Full R102-R150 sweep | In-process probe corpus + Markdown report |

---

## How to run all 151 rounds

```bash
python -c "
from aria.security.guard import activate_all_rounds
loaded = activate_all_rounds(force_reload=True)
print(f'Loaded {len(loaded)} rounds')

# R51 (R1-R51 representative coverage)
from aria.security.rounds.r51_adversarial_runner import run as run_v1, render_report as render_v1
print(render_v1(run_v1()))

# R101 (R1-R101 full-stack v2)
from aria.security.rounds.r101_adversarial_runner_v2 import run_v2, render_v2
print(render_v2(run_v2()))

# R151 (R102-R150 capstone v3)
from aria.security.rounds.r151_adversarial_runner_v3 import run_v3, render_v3
print(render_v3(run_v3()))

# R100 breach drill
from aria.security.rounds.r100_breach_drill import run_breach_drill, render_drill_md
print(render_drill_md(run_breach_drill()))
"
```

## What R102-R151 closes from SECURITY_LANDSCAPE.md

| Gap row in landscape doc | Round that closes / addresses it |
|--------------------------|----------------------------------|
| Hardware-rooted key storage (HSM) | R103 + R108 |
| TPM 2.0 attestation | R102 + R104 + R107 |
| Sealed storage | R106 |
| Side-channel hardening | R109 + R111 |
| RowHammer / DRAM defence | R110 |
| K8s posture management | R112 + R113 + R115 + R117 + R119 + R120 |
| Image signing + provenance | R114 + R121 |
| Mutual TLS | R116 |
| Resource quotas | R118 |
| AWS IMDSv2 / S3 / IAM / KMS / CloudTrail | R122 + R123 + R124 + R125 + R126 + R127 + R128 |
| Cloud secret manager | R129 |
| Lambda + VPC posture | R130 + R131 |
| GCG / AutoDAN class | R132 |
| Multi-modal LLM attacks | R133 |
| RAG poisoning | R134 |
| Conversation memory injection | R135 |
| Self-reflection / multi-agent jailbreaks | R136 + R137 |
| Output watermarking | R138 |
| Prompt provenance | R139 |
| Tool-use loop attacks | R140 |
| Forbidden-content classification | R141 |
| Padding oracle / XSSI / subdomain takeover | R142 + R143 + R144 |
| DNS CAA / DMARC | R145 |
| Polyglot files | R146 |
| Unicode steganography + homograph | R147 + R148 |
| Cookie hardening | R149 |
| Request-ID uniqueness | R150 |
| Adversarial regression suite | R51 + R101 + R151 |

After R151 the residual rows in SECURITY_LANDSCAPE.md are **strictly hardware** (FIPS 140-3 L3 HSM device, real TPM 2.0 chip, line-rate IPS appliance) or **strictly operator-side** (classified threat-intel feeds, formal verification, counter-intel opsec, kernel EDR like CrowdStrike).
