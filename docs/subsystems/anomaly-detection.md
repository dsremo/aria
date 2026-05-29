# Telemetry anomaly detection (Dsremo) — 12-detector ensemble for spacecraft health monitoring

Dsremo is ARIA's onboard telemetry anomaly-detection subsystem. It ingests raw spacecraft
telemetry, decomposes each channel's signal to strip orbital periodicity and long-term trend,
then runs a 12-detector ensemble over the residuals. Detected anomalies are scored, assigned
a severity level, grouped into incidents, broadcast over a WebSocket feed, and made available
to ARIA's cognitive engine as structured tool responses.

The subsystem comprises 127 Python files (~31,000 LOC) under
[`src/aria/dsremo/`](../../src/aria/dsremo/).

---

## Where it sits in the architecture

```
Telemetry sources (SatNOGS · YAMCS · InfluxDB · CSV · XTCE)
      │  POST /telemetry
      ▼
  Ingest adapter  ──────────────────────────────────────────►  DB (TimescaleDB / SQLite)
  (src/aria/dsremo/ingest/)                                         │
      │ triggers run_detection_cycle()                              │ window query (600 pts)
      ▼                                                             │
  DetectionPipeline  ◄─────────────────────────────────────────────┘
  (detection/detector.py)
      │
      ├─ STLDecomposer  →  residuals + trend + seasonal
      │
      ├─ CalibrationManager  →  ref_mean, ref_std, cusum_k/h, ewma_ucl/lcl
      │
      ├─ 12-detector ensemble  (see next section)
      │
      ├─ _ensemble_vote()  →  confidence ∈ [0, 1]  +  Severity
      │
      ├─ IncidentGrouper  →  correlated anomalies → Incident record
      │
      ├─ WebSocket broadcast  (api/websocket.py)
      │
      └─ AlertService.dispatch()  →  webhook / email  (WARNING + CRITICAL only)

Cognitive engine (aria.main / aria.integrations.dsremo.tools)
      │  tool call: DsremoQueryAnomalies / DsremoGetAnomalyScore
      ▼
  LLM advisor  →  proposed action  →  Constitution  →  Execution guard  →  HAL
```

The cognitive engine subscribes to live anomalies via `DsremoWebSocketSubscribe` and also
queries historical anomaly scores through the REST tools. It never drives the detection
pipeline directly; it reads what Dsremo has already scored and reasons about response.

The independent monitor sidecar (F-7) watches the cognitive engine's proposed commands and
can veto them. Dsremo anomaly events are one of its primary evidence sources.

---

## The detector ensemble

All 12 detectors operate on **STL residuals** (raw telemetry minus the seasonal orbital
component), not on raw values. This is architecturally important: eclipse transitions,
battery charge/discharge cycles, and orbital thermal swings live in the seasonal component
and are never passed to any detector. Only genuine deviations from the expected pattern
reach the ensemble.

STL decomposition is performed by
[`detection/stl_decomposer.py`](../../src/aria/dsremo/detection/stl_decomposer.py) with
three modes auto-selected per channel: full statsmodels STL when the orbital period is
detectable, Savitzky-Golay trend-only extraction when the data rate is too coarse for
seasonal decomposition, and global-mean subtraction for cold-start windows.

### 1. CUSUM — Cumulative Sum drift detector

File: [`detection/cusum.py`](../../src/aria/dsremo/detection/cusum.py)

Two-sided CUSUM on AR(1)-whitened STL residuals. Accumulates evidence across samples:
`S_pos[t] = max(0, S_pos[t-1] + (x[t] − k))`, where `k = 0.5 σ_ref` and the alarm
threshold `H = 5 σ_ref` follow the NASA/ESA standard for spacecraft telemetry. Fires when
sustained drift accumulates above `H`; resets accumulators after each alarm so consecutive
events are tracked independently. Default ensemble weight: **0.1261** (highest weighted
benchmarked detector).

### 2. EWMA — Exponentially Weighted Moving Average level-shift detector

File: [`detection/ewma.py`](../../src/aria/dsremo/detection/ewma.py)

EWMA-STR: `Z[t] = λ x[t] + (1 − λ) Z[t−1]`, with upper/lower control limits
`UCL/LCL = ±L σ_ref √(λ/(2−λ))`. Smoothing factor λ = 0.2 (configurable). Where CUSUM
catches gradual drift over many samples, EWMA responds within ~5 samples for λ = 0.2 and
is the primary level-shift detector. Unlike CUSUM, EWMA does not reset after an alarm —
sustained anomalies keep the statistic elevated. Default weight: **0.0887**.

### 3. Statistical (rolling Z-score / spike detector)

File: [`detection/statistical.py`](../../src/aria/dsremo/detection/statistical.py)

MAD-based modified z-score (Median Absolute Deviation) on the current residual window.
Prefers MAD over standard deviation because a single spike cannot inflate the denominator
and blind the detector. Default threshold: 3.5 σ; severe threshold: 5 σ. Also checks
rate-of-change for ramp anomalies. Effective weight in the current default configuration:
**0.0** (the CATS benchmark showed this fires with high FPR on non-stationary channels;
CUSUM and BOCPD carry drift detection; it remains active as a cross-check, just
zero-weighted in the LLR derivation).

### 4. PELT changepoint (structural break detector)

File: [`detection/changepoint.py`](../../src/aria/dsremo/detection/changepoint.py)

Pruned Exact Linear Time (PELT) algorithm via the `ruptures` library. Detects mean and
variance shifts in residual windows. Default weight: **0.0** (same reason as z-score: on
non-stationary telemetry PELT fires nearly every window, so its LLR weight is zero in the
CATS benchmark). Superseded in practice by BOCPD for online changepoint detection;
retained for compatibility and for batch retrospective analysis.

### 5. Isolation Forest — multivariate cross-parameter anomaly detector

File: [`detection/isolation.py`](../../src/aria/dsremo/detection/isolation.py)

scikit-learn Isolation Forest over all simultaneously-monitored parameters. The only
detector that operates across parameters rather than within a single channel. Catches
anomalies that only appear in the relationship between channels — for example, battery
voltage dropping while solar current stays high. Requires ≥ 2 parameters and ≥ 200 training
samples before first scoring. Default weight: **0.0473**.

### 6. Variance spike detector

File: [`detection/variance_detector.py`](../../src/aria/dsremo/detection/variance_detector.py)

Computes the rolling standard deviation of the last `window` (default 30) residuals and
compares it to the calibrated baseline `ref_std`. Fires when the ratio exceeds
`variance_z_threshold` (default 2.5×). Motivated by the CATS dataset (ESA Solenix,
Zenodo 8338435) where variance doubled while the residual mean barely moved — invisible to
z-score, CUSUM, and EWMA. Default weight: **0.2507** (second-highest, jointly with
trend velocity).

### 7. GRU Autoencoder (ML temporal pattern detector)

File: [`detection/autoencoder_detector.py`](../../src/aria/dsremo/detection/autoencoder_detector.py)

Per-channel GRU sequence autoencoder trained on normal residuals. Architecture: GRU
encoder (input=1, hidden=32) → Linear(32→8) bottleneck → Linear(8→32) → Linear(32→seq_len)
decoder. ~5 K parameters; trains in < 1 s per channel on CPU. Anomaly score: MSE of the
reconstructed window versus the mean training MSE. Per-channel model registry with LRU
eviction at 200 models. Lazy-imports PyTorch; returns NOMINAL when PyTorch is unavailable.
Supports optional masked-residual pretraining warm-start (V3-V2). Default weight:
**0.0473**, grouped with TCN under `ml_temporal`.

### 8. TCN — Temporal Convolutional Network

File: [`detection/tcn_detector.py`](../../src/aria/dsremo/detection/tcn_detector.py)

Per-channel causal dilated TCN autoencoder: 4 residual blocks with dilations 1, 2, 4, 8
and 16 channels per block. Receptive field: 61 steps at kernel_size=3. ~5.6 K parameters;
fully parallelisable (no RNN state). Complements the GRU autoencoder by covering longer
temporal dependencies without vanishing gradients. Same per-channel model registry, same
LRU eviction policy. Default weight: **0.0473**, same group as GRU.

### 9. Trend Velocity — STL trend acceleration (onset detector)

File: [`detection/trend_velocity_detector.py`](../../src/aria/dsremo/detection/trend_velocity_detector.py)

Differentiates the STL *trend* component (not residuals) to detect acceleration. Computes
`velocity = dTrend/dt` via central-difference approximation over the last `window` (default
20) samples; alarms when the maximum recent velocity exceeds `threshold_sigma × (ref_std /
window)`. Fires at the moment a drift *begins* — often several CUSUM accumulation periods
earlier than CUSUM itself. Also drives the time-to-limit prediction: when hard redline
limits are configured, the pipeline estimates minutes-to-redline from the current trend
velocity and escalates severity if that estimate falls below `ttl_warn_min`. Default weight:
**0.2507** (joint highest).

### 10. Matrix Profile discord (shape anomaly detector)

File: [`detection/discord_detector.py`](../../src/aria/dsremo/detection/discord_detector.py)

FFT-accelerated z-normalized Euclidean distance from the most recent `m`-length (default
20) subsequence to its nearest neighbor in a rolling buffer of `window` (default 300)
residuals. A high discord score means the current shape has never appeared before in recent
history — the detector reports as `matrix_profile` in all outputs. Catches anomalous
oscillations at novel frequencies, unusual recovery trajectories, and flat segments in
normally oscillating channels that statistical detectors miss entirely. Default weight:
**0.0473**.

### 11. Correlation Graph — relationship breakdown detector

File: [`detection/correlation_detector.py`](../../src/aria/dsremo/detection/correlation_detector.py)

Rolling Pearson correlation between every pair of simultaneously-monitored parameters.
Calibrates baseline mean and std for each pair during warmup, then alarms when the current
rolling correlation deviates more than `threshold_sigma` (default 3 σ) from the baseline.
Catches structural decoupling — two normally correlated channels drifting apart — which is
invisible to per-channel detectors. Inspired by STGLR (MDPI Sensors, Jan 2025) but
implemented with numpy-only rolling correlations rather than PyTorch Geometric. Default
weight: **0.0473**.

### 12. BOCPD — Bayesian Online Changepoint Detection

File: [`detection/bocpd_detector.py`](../../src/aria/dsremo/detection/bocpd_detector.py)

Online Bayesian changepoint detector (Adams & MacKay 2007, arXiv:0710.3742) with a
conjugate Normal-Gamma prior. Maintains a probability distribution over run length
(time since the last changepoint) and updates it with one observation per step using
Bayes' theorem. Outputs `P(changepoint NOW)` — a calibrated probability that integrates
cleanly with the score-based ensemble. Replaced PELT (weight=0) as the structural-break
detector: PELT requires a retrospective window and fires nearly continuously on
non-stationary telemetry, while BOCPD is online and produces calibrated per-step
probabilities. O(max_run) per sample at max_run=300. Default weight: **0.0473**.

### Optional extended members (inactive by default)

Three additional detectors exist in the codebase but carry weight = 0 until operators
explicitly activate them:

- **WideTCN** (`detection/wide_tcn_detector.py`) — sibling TCN with dilations up to 128
  and a 1021-step receptive field (~17 min at 1 Hz); activate via `enable_wide_tcn()`.
- **TemporalCrossAttention** (`detection/temporal_cross_attention.py`) — lagged Pearson
  cross-channel attention tensor across subsystems; activate via
  `enable_cross_channel_attn()`.
- **RWBearingProxy** (`detection/rw_bearing_proxy.py`) — ADCS-specific reaction-wheel
  torque-residual proxy using BPFO/BPFI/FTF bearing-frequency formulas; activate via
  `enable_rw_bearing_proxy()`.

These are inert unless enabled, so existing ensemble behaviour and benchmark results are
unchanged in a default deployment.

---

## How votes combine

### Preprocessing

Before the ensemble, each detector score is **calibrated** to `[0, 1]` via a
distribution-appropriate CDF mapping
(`_calibrate_score()` in `detection/detector.py`):

- z-like scores (CUSUM, EWMA, statistical, trend_velocity): normal CDF approximation
- BOCPD: already `[0, 1]`, passed through
- variance: exponential CDF
- matrix profile, PELT: sigmoid
- isolation forest, correlation graph: sigmoid centred at 0.5
- GRU, TCN: normal CDF

### Correlation-aware grouping

Detectors sharing the same residual input are grouped to prevent redundant accumulation of
the same underlying signal:

| Group | Members |
|-------|---------|
| `residual_stateful` | CUSUM, EWMA, statistical, BOCPD |
| `residual_window` | variance, matrix_profile, changepoint |
| `trend` | trend_velocity |
| `multivariate` | isolation_forest, correlation_graph |
| `ml_temporal` | GRU autoencoder, TCN (+ WideTCN if active) |

Within each group, only the strongest calibrated signal is used (the detectors within a
group share the same input and do not provide independent evidence). Across groups, signals
add because they originate from genuinely different evidence sources.

### Ensemble vote algorithm

```
for each triggered detector:
    calibrated_score = _calibrate_score(detector_result)
    group_best_score[group] = max(group_best_score[group],
                                  calibrated_score * detector_weight)

for each triggered group:
    pure_score = group_best_score / detector_weight   # recover [0,1]
    total_signal += pure_score * group_weight
    total_group_weight += group_weight

base_confidence = total_signal / total_group_weight

agreement_factor = 0.70 if 1 group triggered
                   0.85 if 2 groups triggered
                   1.00 if ≥3 groups triggered

confidence = min(1.0, base_confidence * agreement_factor)
```

Group weights (sum to 1.0): `residual_stateful` = 0.30, `residual_window` = 0.25,
`trend` = 0.20, `ml_temporal` = 0.15, `multivariate` = 0.10.

The agreement multiplier means a single CUSUM spike (one group) produces at most 0.70
confidence regardless of its score; CUSUM + BOCPD + GRU autoencoder triggering together
(three independent groups) can reach full confidence.

### Severity thresholds

Severity is derived entirely from ensemble confidence:

| Level | Confidence threshold | Meaning |
|-------|---------------------|---------|
| CAUTION | ≥ 0.35 | Informational; no pager alert |
| WATCH | ≥ 0.50 | Notable; logged; no pager alert |
| WARNING | ≥ 0.65 | Alert dispatched (webhook/email) |
| CRITICAL | ≥ 0.85 | Alert dispatched; fastest cooldown |

All four thresholds are configurable via `dsremo.yaml`; the defaults above match the ISRO
FOLIO four-level standard. Hard redline limits (absolute value gates configured per channel)
bypass the ensemble and force CRITICAL at confidence 1.0.

### Weight learning from operator feedback

When an operator marks a detection as a false positive, `record_false_positive()` multiplies
each triggering detector's per-channel weight by 0.95 and renormalises. Per-channel weights
shadow the global defaults; channels that have never received feedback use global weights.
This is an additive mechanism — after enough false-positive feedback on a given detector for
a given channel, that detector's contribution to that channel's score approaches zero without
affecting any other channel.

---

## Validation

### CATS benchmark (LLR weight derivation)

The default ensemble weights (0.1261 for CUSUM, 0.0887 for EWMA, 0.2507 for variance and
trend_velocity, etc.) are derived from log-likelihood ratios computed on the CATS benchmark
dataset (`scripts/benchmark_llr_weights.py`). The CATS evaluation is what drove the
`changepoint` and `statistical` weights to 0: on the CATS non-stationary telemetry corpus,
PELT fires on nearly every window (TPR ≈ FPR ≈ 0.98) and the z-score detector produces
high false-positive rates. These results are incorporated into the defaults but the
benchmark script is the authoritative derivation.

### EDEN ISS integration tests

The claim in [`README.md`](../../README.md) — "validated on EDEN ISS telemetry baselines"
— is backed by the integration test file
[`tests/integration/test_eden_iss_dsremo.py`](../../tests/integration/test_eden_iss_dsremo.py).
The test suite covers:

- `ams-feg:co2-1`: CO₂ channel spiking above 2000 ppm in early 2020 (plant respiration /
  sensor recalibration events from the EDEN ISS 2020 dataset, Romberg et al. 2024,
  Zenodo 11485183); the StatisticalDetector must flag at least one event with value > 1500 ppm.
- `ams-feg:temp-gl`: Grow-light gallery temperature anomaly on 2020-02-05; at least 3 of the
  4 basic detectors (EWMA, CUSUM, statistical, variance) must concur.
- Global: at least 50 anomaly events detected across 10 channels with 500 rows per channel.

**Honest caveats.** All EDEN ISS tests are marked `@skip_no_eden` and `@skip_no_dsremo`;
they run only when the raw EDEN ISS CSV files are present under
`data/raw/eden_iss/edeniss2020/`. That data is not shipped in the repository. The
integration tests confirm that the pipeline's basic detectors (EWMA, CUSUM, z-score,
variance) fire on known anomalous segments of the EDEN ISS record; they do not provide
precision/recall curves, do not cover all 12 ensemble detectors, and do not constitute
a formal benchmark against a held-out labeled test set. The EDEN ISS dataset is from a
controlled greenhouse environment (ISS FEG section), not from a spacecraft in orbit; the
validation confirms the pipeline's detection mechanics work on real scientific sensor data,
not that it generalises to arbitrary spacecraft telemetry.

### Apollo 13 replay demo

[`docs/APOLLO13_REPLAY_REPORT.md`](../APOLLO13_REPLAY_REPORT.md) documents a closed-loop
replay of the Apollo 13 O₂ tank 2 pressure anomaly. The detector used is
`WindowedZScore(window=30, z=3.5)` from `aria.replay`, which is the same rolling z-score
family as Dsremo's `StatisticalDetector`. The replay report is explicit about what this
demonstrates and does not demonstrate: the telemetry is reconstructed from the Cortright
Commission Report, not raw mission data; the pre-event window is synthetic and has near-zero
noise, giving an unrealistically large z-score; and the cross-monitor was a stub in that
run. The demo confirms the end-to-end loop (detection → LLM advisor → command) closes, not
that the ensemble is calibrated for Apollo-era sensor noise.

For a full discussion of the replay subsystem, see [./replay.md](./replay.md).

---

## Current limitations

**No flight heritage.** Nothing in Dsremo has been validated on actual spacecraft in
operation. All evaluation is on ground datasets (CATS, EDEN ISS) or reconstructed mission
data (Apollo 13 replay). The system is TRL 3–5.

**Clean-data assumptions.** STL decomposition requires the orbital period to be detectable
via FFT; at low data rates (below ~4 samples per orbit) the decomposer falls back to
Savitzky-Golay trend extraction or cold-start mean subtraction. Sensors with highly
irregular sampling, large data gaps, or multi-frequency seasonality are not fully handled.

**ML detectors require warm-up.** The GRU autoencoder requires ≥ 60 samples and the TCN
requires ≥ 64 samples before first scoring. In streaming mode this means several minutes
to tens of minutes of observation at 1 Hz before ML-layer scores appear in the ensemble.
During warm-up those two detectors return NOMINAL, reducing the ensemble to 10 active
members.

**Isolation Forest requires ≥ 2 simultaneous parameters.** When Dsremo is monitoring a
single telemetry channel the multivariate detector is disabled. Per the code, a minimum of
200 training samples is also required before the first fit.

**No flight-language port.** The implementation is Python on CPython. There is no RTOS
port, no DO-178C / NPR-7150.2D Class B certification, and no rad-hard CPU validation. A
realistic flight target would require a certified C++ or SPARK Ada re-implementation.

**Weight estimates, not measurements.** The `ESTIMATE —` annotations throughout the detector
source files (threshold values, window sizes, training sample counts) are reasonable
engineering choices supported by cited literature, but most have not been empirically
optimised against a labeled spacecraft anomaly corpus. The CATS-derived LLR weights are the
closest thing to a calibrated measurement; everything else is a prior.

---

## Where to start reading

| File | What it is |
|------|------------|
| [`detection/detector.py`](../../src/aria/dsremo/detection/detector.py) | Orchestrator. `run_detection_cycle()` is the main async entry point. `_ensemble_vote()` is the fusion logic. ~2,870 LOC. |
| [`detection/pipeline_config.py`](../../src/aria/dsremo/detection/pipeline_config.py) | Typed dataclass for all detection configuration. Start here when configuring thresholds. |
| [`detection/cusum.py`](../../src/aria/dsremo/detection/cusum.py) | CUSUM two-sided implementation with state persistence. |
| [`detection/ewma.py`](../../src/aria/dsremo/detection/ewma.py) | EWMA-STR level-shift detector. |
| [`detection/statistical.py`](../../src/aria/dsremo/detection/statistical.py) | MAD-based rolling z-score spike detector. |
| [`detection/bocpd_detector.py`](../../src/aria/dsremo/detection/bocpd_detector.py) | Bayesian online changepoint, Adams & MacKay 2007. |
| [`detection/variance_detector.py`](../../src/aria/dsremo/detection/variance_detector.py) | Variance-ratio spike detector. |
| [`detection/trend_velocity_detector.py`](../../src/aria/dsremo/detection/trend_velocity_detector.py) | STL trend acceleration onset detector. |
| [`detection/discord_detector.py`](../../src/aria/dsremo/detection/discord_detector.py) | Matrix Profile shape discord (numpy FFT-based). |
| [`detection/correlation_detector.py`](../../src/aria/dsremo/detection/correlation_detector.py) | Rolling Pearson correlation breakdown. |
| [`detection/isolation.py`](../../src/aria/dsremo/detection/isolation.py) | scikit-learn Isolation Forest, multivariate. |
| [`detection/autoencoder_detector.py`](../../src/aria/dsremo/detection/autoencoder_detector.py) | GRU sequence autoencoder (lazy PyTorch import). |
| [`detection/tcn_detector.py`](../../src/aria/dsremo/detection/tcn_detector.py) | Dilated causal TCN autoencoder (lazy PyTorch import). |
| [`detection/stl_decomposer.py`](../../src/aria/dsremo/detection/stl_decomposer.py) | STL + Savitzky-Golay + Box-Cox preprocessing. |
| [`detection/calibration.py`](../../src/aria/dsremo/detection/calibration.py) | Per-channel CalibrationState (ref_mean, ref_std, CUSUM/EWMA limits, GMM). |
| [`detection/decision.py`](../../src/aria/dsremo/detection/decision.py) | Decision-theoretic cost framework and Platt scaling. |

**Unit tests:**

All unit tests for Dsremo live under
[`tests/unit/test_dsremo/`](../../tests/unit/test_dsremo/). Key starting points:

- `test_bocpd.py`, `test_a1_bocpd_heavy_tailed.py` — BOCPD edge cases
- `test_changepoint.py` — PELT detector
- `test_isolation.py` — Isolation Forest
- `test_statistical.py` — z-score spike detector
- `test_gmm_autoz.py` — GMM-based auto z-threshold
- `test_s2_wide_tcn.py` — WideTCN optional member
- `test_s3_ood_mahalanobis.py` — OOD Mahalanobis detector (standalone)
- `tests/integration/test_eden_iss_dsremo.py` — full-pipeline integration on EDEN ISS data
  (requires dataset present locally; skipped otherwise)
