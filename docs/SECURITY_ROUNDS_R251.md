# R202-R251 — fifty more round-by-round defences

**Audited:** 2026-04-26
**Library entry:** `from aria.security.guard import activate_all_rounds, ...`
**Tests (per file):** 55 R202-R251 + 66 R152-R201 + 58 R102-R151 + 70 R52-R101 + 112 R1-R51 + 34 guard + 19 foundation = **414 security tests** (plus 143 smoke)
**Composition:** every R202-R251 round registers a `DefencePlugin` exactly like R1-R201.

This document is the **R202-R251 supplement** — the fifth 50 rounds adding quantum-resilient crypto depth, OT/SCADA, Web3/blockchain, privacy/anonymity, and nation-grade ops.  See [SECURITY_ROUNDS_R51.md](SECURITY_ROUNDS_R51.md) (R1-R51), [SECURITY_ROUNDS_R101.md](SECURITY_ROUNDS_R101.md) (R52-R101), [SECURITY_ROUNDS_R151.md](SECURITY_ROUNDS_R151.md) (R102-R151), [SECURITY_ROUNDS_R201.md](SECURITY_ROUNDS_R201.md) (R152-R201) for the prior 200.

---

## Block V — Quantum-resilient crypto depth (R202–R211)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R202 | ML-DSA-87 | NSA CNSA 2.0 Top Secret by 2030 | Level-5 signing wrapper; soft-fallback to ML-DSA-65 |
| R203 | SLH-DSA / SPHINCS+ | Lattice-oracle break would void all lattice schemes | FIPS 205 hash-based sigs for code-signing roots |
| R204 | Crypto agility | Y2Q migration discoverability | Per-role manifest + deprecated/quantum-only audit |
| R205 | PQ hybrid TLS | Harvest-now-decrypt-later TLS | Prefer X25519+ML-KEM-768 group when supported |
| R206 | PQ SSH | Recorded-then-replayed SSH tunnels | OpenSSH KexAlgorithms audit; refuse non-PQ first |
| R207 | Lattice probe | Custom lattice param weakness | Self-probe LLL/BKZ smoke-test |
| R208 | Template attack | Power/EM/cache side-channels | Randomised jitter + decoy work around crypto ops |
| R209 | QRNG interface | Weak seed entropy reconstructible | ARIA_QRNG_DEV with hwrng cascade |
| R210 | Crypto inventory | Long-lived keys without rotation | Per-key install/rotation ledger + overdue audit |
| R211 | Y2Q tracker | Migration progress invisibility | Per-role classical→PQ rollout % tracker |

## Block W — OT/SCADA + industrial protocols (R212–R221)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R212 | Modbus TCP | No-auth + safety register writes (Triton 2017) | Function code/range + safety register audit; refuse cleartext |
| R213 | DNP3 SAv5/v6 | Ukraine grid 2015/2016 | Session params audit; refuse weak HMAC + key sizes |
| R214 | BACnet | HVAC pivot (Target 2013) | Refuse cleartext + life-safety object writes |
| R215 | OPC-UA | SecurityPolicy=None default | Refuse None in prod; flag deprecated Basic128Rsa15 |
| R216 | ICS anomaly | Stuxnet centrifuge drift | Per-tag bound + rate-of-change checker |
| R217 | Purdue model | IT-OT convergence pivot | L4/L5 → L3-L0 flow audit; refuse without DMZ |
| R218 | SIS air-gap | TRITON SIS firmware reflash | Refuse outbound from SIS hosts + 2-person FW gate |
| R219 | Protocol whitelist | Pivot via non-OT protocols | Per-zone L4-port + protocol allow-list |
| R220 | Historian tamper | TRITON evidence destruction | Per-row Merkle hash chain |
| R221 | PLC firmware | BlackEnergy/Industroyer | Sig + 2-person + cooldown gate |

## Block X — Web3 / blockchain (R222–R231)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R222 | Solidity reentrancy | DAO 2016 / Cream 2021 | Lint: external call before state write or no nonReentrant |
| R223 | Proxy upgrade key | Audius 2022 / PolyNetwork 2021 ($600M) | Refuse EOA admin + low-threshold + no-timelock |
| R224 | Bridge replay | Wormhole/Nomad/Ronin 2022 | Per-(chain_pair, msg_hash) ledger + guardian quorum |
| R225 | Wallet phishing | Inferno/Pink/Angel drainers ($295M 2024) | EIP-712 sign-request audit; refuse infinite + drainer addr |
| R226 | Address poisoning | Vanity prefix/suffix collision ($1.6B Q1 2024) | Detect prefix+suffix match with different middle |
| R227 | Oracle manipulation | bZx/Cream/Mango flash-loan ($600M+) | Median-of-N + TWAP + deviation cap |
| R228 | ERC-20 allowance | Sushi 2023 phishing | Refuse infinite + over-soft-cap approve |
| R229 | MEV / front-running | $1B+/yr searcher extraction | Risk score + private-bundle recommender |
| R230 | Cross-chain message | LayerZero v1 / Hop 2024 | Source allow-list + nonce + freshness audit |
| R231 | HW-wallet attestation | Supply-chain tampered Ledger/Trezor | Vendor root + firmware floor + challenge-response |

## Block Y — Privacy / anonymity / data minimisation (R232–R241)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R232 | DP Laplace clamp | Re-identification via repeat queries (Netflix 2007) | Per-subject epsilon budget + Laplace noise |
| R233 | k-anonymity / l-diversity | Quasi-identifier re-id (Sweeney 2002) | Min equivalence-class + sensitive-value diversity |
| R234 | Tor/VPN egress | Anonymising hop on sensitive flow | Exit/VPN list + risk bump on sensitive action |
| R235 | PII tokenisation | PII in logs/dashboards | Format-preserving deterministic FPE keyed on HKDF |
| R236 | Model inversion | Repeated extraction (Fredrikson 2015) | Per-caller query-rate limiter |
| R237 | Membership inference | Training set leak (Shokri 2017) | Confidence clip + temperature softmax |
| R238 | FL gradient privacy | Deep Leakage from Gradients (Zhu 2019) | L2-clip + Gaussian noise |
| R239 | Data residency | GDPR / DPDP / PIPL / 242-FZ violation | Per-tenant region allow-list |
| R240 | RTBF propagation | Incomplete erasure across sinks | Per-sink completion ledger + 30d deadline |
| R241 | Privacy budget | Cumulative epsilon drift | Cross-query subject-level annual ceiling |

## Block Z — Nation-grade ops + capstone v5 (R242–R251)

| # | Topic | Threat | Defence |
|---|-------|--------|---------|
| R242 | Air-gap diode | Covert-channel IT/OT bridge | Direction enforcement; refuse violating flow |
| R243 | Two-person crypto | Single-rogue-admin compromise | Quorum ceremony for sensitive crypto ops |
| R244 | Token enrollment | Network-only FIDO2 enrollment hijack | Physical-presence + attestation + 2-person for privileged |
| R245 | QKD interface | 50-year-secret confidentiality | ETSI GS QKD 014 client stub; soft-fail when no appliance |
| R246 | Insider UBA | Snowden/Manning slow exfil | Per-user behavioural baseline scorer |
| R247 | Espionage indicator | APT 24-day median dwell (CrowdStrike 2024) | Pattern-bank + per-host cumulative score |
| R248 | Counter-intel decoy | Static decoy recognition | Rotating realistic decoys with embedded canaries |
| R249 | FISMA-High audit | NSS audit-trail completeness | Refuse incomplete records; tamper-evident chain |
| R250 | Crypto destruction | NIST 800-88 crypto-erase | Secure-erase buffer/file + signed destruction cert |
| R251 | Adversarial runner v5 | Full R202-R250 sweep | In-process probe corpus + Markdown report |

---

## How to run all 251 rounds

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

# R100 breach drill
from aria.security.rounds.r100_breach_drill import run_breach_drill, render_drill_md
print(render_drill_md(run_breach_drill()))
"
```

## What R202-R251 closes from SECURITY_LANDSCAPE.md

| Gap row in landscape doc | Round that closes / addresses it |
|--------------------------|----------------------------------|
| CNSA 2.0 Level-5 (Top Secret) | R202 |
| Hash-based signatures (FIPS 205) | R203 |
| Crypto agility / migration tracking | R204 + R211 |
| Hybrid TLS / SSH (PQ KEX) | R205 + R206 |
| Lattice parameter audit | R207 |
| Side-channel hardening (template) | R208 |
| Quantum RNG | R209 |
| Crypto-key inventory + rotation | R210 |
| Modbus / DNP3 / BACnet / OPC-UA | R212 + R213 + R214 + R215 |
| ICS process anomaly | R216 |
| Purdue / SIS / protocol whitelist | R217 + R218 + R219 |
| Historian + PLC firmware | R220 + R221 |
| Smart-contract reentrancy + upgrade-key | R222 + R223 |
| Bridge replay + cross-chain | R224 + R230 |
| Wallet drainer / address poisoning | R225 + R226 |
| DeFi oracle / allowance / MEV | R227 + R228 + R229 |
| Hardware-wallet attestation | R231 |
| Differential privacy + k-anon | R232 + R233 |
| Tor/VPN egress on sensitive flow | R234 |
| PII tokenisation (FPE) | R235 |
| ML inversion / membership inference / FL DP | R236 + R237 + R238 |
| Data residency + RTBF + privacy budget | R239 + R240 + R241 |
| Air-gap diode | R242 |
| Two-person rule for crypto | R243 |
| Hardware-token enrollment ceremony | R244 |
| QKD interface | R245 |
| Insider threat UEBA | R246 |
| APT espionage indicator | R247 |
| Counter-intel decoy refresh | R248 |
| FISMA-High / NSS audit | R249 |
| Crypto-erase NIST 800-88 | R250 |
| Adversarial regression v5 | R251 |

After R251 the residual rows in SECURITY_LANDSCAPE.md are **strictly hardware** (FIPS 140-3 L3 HSM device, real TPM 2.0 chip, line-rate IPS appliance, hardware-backed FIDO2 fleet, physical fibre data diode, real QKD appliance) or **strictly operator-side** (classified threat-intel feeds, formal verification of safety-critical kernels, counter-intel opsec, kernel EDR like CrowdStrike Falcon, dedicated SOC 24/7 staffing, NSA-cleared SCIF infrastructure).
