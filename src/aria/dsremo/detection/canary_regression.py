"""V3-Be3: Canary regression test for recalibration validation.

When calibration produces updated thresholds, a genuine long-duration
anomaly may have been absorbed as "nominal" (the "boiling frog" failure).
This module validates that post-recalibration CUSUM sensitivity is preserved
by injecting synthetic anomalies.

If the canary test fails, recalibration is rejected and operators are alerted.

Reference: Klinkenberg, R. (2004). "Learning drifting concepts: Example
           selection vs. example weighting." IDA 8(3):281–300.
"""

from __future__ import annotations

import numpy as np
import structlog

logger = structlog.get_logger()


def canary_test(
    ref_mean: float,
    ref_std: float,
    cusum_k: float,
    cusum_h: float,
    n_simulations: int = 100,             # ESTIMATE — 100 MC runs for ±10% detection rate accuracy
    shift_magnitude_sigma: float = 3.0,   # ESTIMATE — 3σ shift: target detection in practice (Lucas 1982)
    max_arl1_samples: int = 50,           # ESTIMATE — ARL₁ ≤ 50 for 3σ shift (Lucas 1982 Technometrics 24 199)
) -> dict:
    """Run synthetic anomaly injection to validate CUSUM sensitivity.

    Injects a step change of `shift_magnitude_sigma × ref_std` into
    simulated N(ref_mean, ref_std) data and verifies that CUSUM detects
    it within `max_arl1_samples` samples in at least 90% of simulations.

    Args:
        ref_mean: Post-recalibration reference mean.
        ref_std:  Post-recalibration reference std.
        cusum_k:  CUSUM allowance parameter.
        cusum_h:  CUSUM alarm threshold.
        n_simulations: Number of Monte Carlo runs.
        shift_magnitude_sigma: Size of injected step change (in σ units).
        max_arl1_samples: Maximum detection delay considered acceptable.

    Returns:
        {"passed": bool, "detection_rate": float, "mean_arl1": float,
         "recommendation": str}
    """
    if ref_std < 1e-12:
        return {
            "passed": False,
            "detection_rate": 0.0,
            "mean_arl1": float("inf"),
            "recommendation": "ref_std is near zero — recalibration invalid",
        }

    rng = np.random.default_rng(42)
    shift = shift_magnitude_sigma * ref_std

    detections = 0
    arl1_sum = 0.0

    for _ in range(n_simulations):
        # Generate nominal data, then inject step change.
        nominal = rng.normal(ref_mean, ref_std, 50)  # ESTIMATE — 50-sample nominal warmup; Lucas 1982 Technometrics 24 199: CUSUM needs ~50 in-control samples before meaningful ARL
        shifted = rng.normal(ref_mean + shift, ref_std, max_arl1_samples)
        data = np.concatenate([nominal, shifted])

        # Run CUSUM on the shifted portion.
        s_pos = 0.0
        detected = False
        detection_delay = max_arl1_samples

        for i, x in enumerate(shifted):
            s_pos = max(0.0, s_pos + (x - ref_mean) - cusum_k)
            if s_pos > cusum_h:
                detected = True
                detection_delay = i + 1
                break

        if detected:
            detections += 1
            arl1_sum += detection_delay

    detection_rate = detections / n_simulations
    mean_arl1 = arl1_sum / max(detections, 1)

    passed = detection_rate >= 0.90  # ESTIMATE — 90% detection rate minimum; Lucas 1982 Technometrics 24 199: ARL₁ target implies ≥90% detection in practice

    recommendation = ""
    if not passed:
        recommendation = (
            f"RECALIBRATION REJECTED: post-recalibration CUSUM detects "
            f"{shift_magnitude_sigma}σ shift in only {detection_rate*100:.0f}% "
            f"of simulations (need ≥90%). System sensitivity degraded — "
            f"revert to previous calibration."
        )
        logger.warning(
            "canary_test_failed",
            detection_rate=round(detection_rate, 3),
            mean_arl1=round(mean_arl1, 1),
            ref_std=ref_std,
        )

    return {
        "passed": passed,
        "detection_rate": round(detection_rate, 3),
        "mean_arl1": round(mean_arl1, 1),
        "shift_sigma": shift_magnitude_sigma,
        "recommendation": recommendation,
    }
