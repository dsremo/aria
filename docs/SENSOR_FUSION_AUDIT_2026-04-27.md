# Sensor-Fusion + Data-Ingestion Audit — 2026-04-27

**Persona:** Senior Space Systems Reliability Engineer + Sensor Fusion Specialist
**Threat Model:** Extreme environmental interference, intermittent sensor degradation, signal-to-noise anomalies, bus-attacker injecting forged telemetry, Kalman-filter divergence over multi-year arcs.
**Outcome:** 24 numbered findings (S-1 .. S-24) + 1 architectural recommendation (A-1).  **All 25 closed.**

---

## Findings ↔ Fixes

| ID    | Severity  | File                                                                  | Title |
|-------|-----------|-----------------------------------------------------------------------|-------|
| S-1   | CRITICAL  | `physics/gravity/orbit_determination.py`                              | No chi-squared Mahalanobis innovation gate |
| S-2   | CRITICAL  | `physics/gravity/orbit_determination.py`                              | Naïve `(I-KH)P` Kalman update (numerical drift) |
| S-3   | CRITICAL  | `physics/gravity/orbit_determination.py`                              | FD-STM with absolute epsilon |
| S-4   | CRITICAL  | `physics/gravity/orbit_determination.py`                              | P symmetrisation missing |
| S-5   | CRITICAL  | `physics/gravity/orbit_determination.py`                              | Unbounded measurement history |
| S-6   | CRITICAL  | `safety/replay_guard.py`                                              | Single-sample wall-clock TOCTOU |
| S-7   | CRITICAL  | `dsremo/ingest/adapter.py`                                            | No bounded-rate ingestion |
| S-8   | HIGH      | `dsremo/ingest/utils.py`                                              | Naïve datetimes silently localised |
| S-9   | HIGH      | `dsremo/ingest/bulk_loader.py`                                        | Race on concurrent batches |
| S-10  | HIGH      | `dsremo/ingest/bulk_loader.py`                                        | No drop-count observability |
| S-11  | HIGH      | `dsremo/detection/physical_constraints.py`                            | `or` truthiness fix |
| S-12  | HIGH      | `dsremo/detection/calibration.py`                                     | Recal factor without sigma cap |
| S-13  | HIGH      | `dsremo/detection/sensor_switchover.py`                               | No statistical fallback |
| S-14  | HIGH      | `monitor/heartbeat.py`                                                | Boot_id rotation rate-limit |
| S-15  | HIGH      | `monitor/cross_check.py`                                              | No majority-vote provider |
| S-16  | MEDIUM    | `state/manager.py`                                                    | Schema validators missing |
| S-17  | MEDIUM    | `state/manager.py`                                                    | Save not atomic |
| S-18  | MEDIUM    | `state/manager.py`                                                    | Returned references not deepcopied |
| S-19  | MEDIUM    | `dsremo/ingest/adapter.py`                                            | No epoch window |
| S-20  | MEDIUM    | `dsremo/ingest/adapter.py`                                            | No `BatchStats` |
| S-21  | MEDIUM    | `dsremo/detection/calibration.py`                                     | Hard limit at 8σ |
| S-22  | LOW       | `physics/gravity/orbit_determination.py`                              | Q-noise citations |
| S-23  | LOW       | `dsremo/detection/physical_constraints.py`                            | Staleness cite |
| S-24  | LOW       | `dsremo/detection/physical_constraints.py`                            | Citations |
| A-1   | RECO      | `safety/sensor_voter.py` (NEW)                                        | TripleSensorVoter |

---

## Verification

```bash
$ python -m pytest tests/integration/test_sensor_fusion_audit_2026_04_27.py
======= 28 passed in ~1.3s =======
```

Pinned by 28 wiring tests; broader regression remained green (1485+ tests).

---

## Wiring lessons reused in later audits

* The Mahalanobis innovation-gate pattern was reused in the orbital-determination layer of the conjunction-watch screener.
* `BatchStats` drop-count observability pattern was extended to the comms / approval-queue / replay-guard surfaces.
* TripleSensorVoter (A-1) became the foundation for the F-7 monitor stack's majority-vote fan-out.
