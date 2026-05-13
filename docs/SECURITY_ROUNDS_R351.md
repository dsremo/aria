# R302-R351 — fifty more round-by-round defences

**Audited:** 2026-04-26
**Library entry:** `from aria.security.guard import activate_all_rounds, ...`
**Tests (per file):** 50 R302-R351 + 54 R252-R301 + 55 R202-R251 + 66 R152-R201 + 58 R102-R151 + 70 R52-R101 + 112 R1-R51 + 34 guard + 19 foundation = **518 security tests** (plus 143 smoke)
**Composition:** every R302-R351 round registers a `DefencePlugin` exactly like R1-R301.

This document is the **R302-R351 supplement** — the seventh 50 rounds adding AI/ML supply-chain depth, resilience/chaos engineering, threat-intel/Sigma/ATT&CK, deepfake/synthetic-media, and final consolidation. See [SECURITY_ROUNDS_R51.md](SECURITY_ROUNDS_R51.md) (R1-R51), [SECURITY_ROUNDS_R101.md](SECURITY_ROUNDS_R101.md) (R52-R101), [SECURITY_ROUNDS_R151.md](SECURITY_ROUNDS_R151.md) (R102-R151), [SECURITY_ROUNDS_R201.md](SECURITY_ROUNDS_R201.md) (R152-R201), [SECURITY_ROUNDS_R251.md](SECURITY_ROUNDS_R251.md) (R202-R251), [SECURITY_ROUNDS_R301.md](SECURITY_ROUNDS_R301.md) (R252-R301) for the prior 300.

---

## Block FF — AI/ML supply chain depth (R302–R311)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R302 | Model lineage | Swapped weights / poisoned base | Manifest with weights SHA + hybrid signing |
| R303 | safetensors | Header / offset abuse | Header validator + dtype allow-list |
| R304 | Tokenizer poisoning | Glitch tokens / ZW vocab | Vocab + BPE-merge audit |
| R305 | Embedding drift | Silent embedder swap / poison | Sentinel-corpus cosine baseline |
| R306 | Prompt template | Tampered system prompt | SHA-256 + hybrid signature on load |
| R307 | Fine-tune canary | Data exfil via fine-tune | Inject + probe synthetic strings |
| R308 | Vector provenance | PoisonedRAG (USENIX 2024) | Per-vector source + hash + chain |
| R309 | ML registry RBAC | Compromised CI publishes models | Per-action gate; production needs 2-person |
| R310 | GPU side-channel | LeftoverLocals (Trail of Bits 2024) | Refuse shared MIG + non-zeroised allocator |
| R311 | Pipeline reproducibility | Audit-impossible training run | Seed + env + inputs manifest audit |

## Block GG — Resilience / chaos engineering (R312–R321)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R312 | Chaos injection | Failure paths only tested in real outage | Probability + per-scope injection harness |
| R313 | Graceful fallback | Hard-fail cascade | Primary + fallback + degraded counter |
| R314 | Circuit breaker | Flaky downstream pins workers | Per-resource breaker + bulkhead |
| R315 | Backpressure | Unbounded queue OOM | Bounded semaphore; producer sheds |
| R316 | Timeout cascade | Tail-latency amplification | Deadline propagation with safety margin |
| R317 | Liveness vs readiness | Single /healthz kills pods on dep outage | Split probes; liveness no externals |
| R318 | Game-day simulator | Untested outage paths | Registered-dep + fail-mode dispatcher |
| R319 | DR audit | Untested RTO/RPO claims | Per-system test-freshness audit |
| R320 | Multi-region failover | Stale passive region | Drill-freshness + RPO-lag check |
| R321 | RED metrics | Silent SLO breach | Rate + error-rate + p99 alert |

## Block HH — Threat intel / Sigma / ATT&CK (R322–R331)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R322 | ATT&CK mapping | Detections unmappable to playbooks | Per-round technique IDs + heatmap |
| R323 | Sigma engine | Cross-SIEM detection not portable | Subset Sigma matcher (selections + AND/OR/NOT) |
| R324 | STIX / TAXII | Missed ISAC / CISA AIS feeds | STIX 2.1 indicator parser + TAXII client |
| R325 | YARA-lite | libyara C dependency in pure Python | Hex / ASCII / regex matcher |
| R326 | Diamond Model | Unstructured incident reports | Four-vertex event encoder |
| R327 | TLP tagging | Over-shared threat intel | Per-item TLP + share-policy gate |
| R328 | APT fingerprint | Unattributed intrusions | Group-profile technique-overlap scorer |
| R329 | TTP clustering | Alert fatigue | Jaccard-clustering by ATT&CK set |
| R330 | Pyramid of Pain | Block hashes only | Per-indicator level + weight |
| R331 | Feed freshness | Stale KEV / AV / YARA feeds | Per-feed last-refresh ledger |

## Block II — Deepfake / synthetic media (R332–R341)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R332 | Deepfake video | Face-swap CEO fraud | Per-frame metadata heuristic scorer |
| R333 | AI-generated text | Bulk LLM-generated content | Stylometric scorer (sent-var + TTR + em-dash) |
| R334 | Voice deepfake | Voice-clone fraud ($25M HK CFO 2024) | Pause + bandwidth + background heuristic |
| R335 | C2PA / Content Credentials | Unsigned synthetic media | Manifest verifier (ingredients + signature) |
| R336 | Liveness | Photo / video / mask spoof | ISO 30107-3 PAD-level + score gate |
| R337 | Synthetic identity | $20B+/yr Federal Reserve estimate | Bureau + device + SSN-geo scorer |
| R338 | PDF forgery | Doctored contracts / IDs | Incremental updates + producer + sig audit |
| R339 | Image watermark | AI-generated content blending in | IPTC digitalSourceType + C2PA + EXIF detect |
| R340 | AI-generated code | Hallucinated imports / typo-squat | Heuristic source-file scorer |
| R341 | Reverse image | Catfish / fake-recruiter photos | Hash + Hamming-distance lookup |

## Block JJ — Final consolidation + capstone v7 (R342–R351)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R342 | Runner orchestrator | Forgotten runner = blind spot | Single entry-point invokes v1-v7 |
| R343 | Coverage map | Unknown SPoF in defence portfolio | Threat-class → round mapping |
| R344 | Defence in depth | Single-defender threat classes | Audit < min_layers defenders |
| R345 | Policy bundle | Drift across teams | Single signed JSON of CSP+sshd+Istio+... |
| R346 | Threat-model refresh | Stale threat assumptions | Per-domain refresh ledger + overdue audit |
| R347 | Bug bounty intake | Slow triage of researcher reports | Structured submission + reject malformed |
| R348 | Coordinated disclosure | No SLA = full-disclosure default | State machine + 90-day clock |
| R349 | CVSS v3.1 | Vulnerability triage drift | Base-score calculator + canonical vector |
| R350 | API stability | Renamed/removed defence functions | Per-round signature contract audit |
| R351 | Adversarial runner v7 | Full R302-R350 sweep | In-process probe corpus + Markdown report |

---

## How to run all 351 rounds

```bash
python -c "
from aria.security.guard import activate_all_rounds
loaded = activate_all_rounds(force_reload=True)
print(f'Loaded {len(loaded)} rounds')

# Single orchestrator (recommended)
from aria.security.rounds.r342_runner_orchestrator import run_all, render_consolidated
print(render_consolidated(run_all()))

# Individual runners (for forensic detail)
from aria.security.rounds.r51_adversarial_runner import run as run_v1, render_report as render_v1
print(render_v1(run_v1()))

from aria.security.rounds.r101_adversarial_runner_v2 import run_v2, render_v2
print(render_v2(run_v2()))

from aria.security.rounds.r151_adversarial_runner_v3 import run_v3, render_v3
print(render_v3(run_v3()))

from aria.security.rounds.r201_adversarial_runner_v4 import run_v4, render_v4
print(render_v4(run_v4()))

from aria.security.rounds.r251_adversarial_runner_v5 import run_v5, render_v5
print(render_v5(run_v5()))

from aria.security.rounds.r301_adversarial_runner_v6 import run_v6, render_v6
print(render_v6(run_v6()))

from aria.security.rounds.r351_adversarial_runner_v7 import run_v7, render_v7
print(render_v7(run_v7()))

# R100 breach drill
from aria.security.rounds.r100_breach_drill import run_breach_drill, render_drill_md
print(render_drill_md(run_breach_drill()))
"
```

## What R302-R351 closes from SECURITY_LANDSCAPE.md

| Gap row in landscape doc | Round that closes / addresses it |
|--------------------------|----------------------------------|
| Model lineage / safetensors / tokenizer | R302 + R303 + R304 |
| Embedding drift + prompt-template signing | R305 + R306 |
| Fine-tune canary + vector provenance | R307 + R308 |
| ML registry RBAC + GPU side-channel | R309 + R310 |
| Pipeline reproducibility | R311 |
| Chaos / fallback / breaker / backpressure | R312 + R313 + R314 + R315 |
| Timeout cascade + health split + game day | R316 + R317 + R318 |
| DR + multi-region + RED metrics | R319 + R320 + R321 |
| ATT&CK mapping + Sigma engine + STIX/TAXII | R322 + R323 + R324 |
| YARA-lite + Diamond + TLP | R325 + R326 + R327 |
| APT fingerprint + clustering + Pyramid | R328 + R329 + R330 |
| Feed freshness | R331 |
| Deepfake video + AI text + voice | R332 + R333 + R334 |
| C2PA + liveness + synthetic ID | R335 + R336 + R337 |
| PDF forgery + watermark + AI code | R338 + R339 + R340 |
| Reverse image | R341 |
| Runner orchestrator + coverage + DiD | R342 + R343 + R344 |
| Policy bundle + threat-model refresh | R345 + R346 |
| Bug bounty + CVD + CVSS | R347 + R348 + R349 |
| API stability | R350 |
| Adversarial regression v7 | R351 |

After R351 the residual rows in SECURITY_LANDSCAPE.md are **strictly hardware** (FIPS 140-3 L3 HSM device, real TPM 2.0 chip, line-rate IPS appliance, hardware-backed FIDO2 fleet, physical fibre data diode, real QKD appliance, RF-shielded enclosure, biometric continuous-authentication hardware, dedicated GPU partitions with hardware MIG isolation) or **strictly operator-side** (classified threat-intel feeds, formal verification of safety-critical kernels, counter-intel opsec, kernel EDR like CrowdStrike Falcon, dedicated 24/7 SOC, NSA-cleared SCIF infrastructure, signed deepfake-detector ML model contracts with vendors).
