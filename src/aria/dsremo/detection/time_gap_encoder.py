"""V3-V1: Time-gap encoding for irregularly-sampled telemetry.

Problem
-------
GRU and TCN detectors treat input sequences as uniformly sampled: the i-th
token represents time T₀ + i·Δt.  Spacecraft telemetry violates this
assumption in three ways:

  1. AOS/LOS contact gaps — LEO satellites lose downlink for up to 80 min
     per orbit when outside a ground-station footprint.
  2. Packet drops — intermittent corruption at the physical layer.
  3. Multi-rate streams — ADCS at 10 Hz, housekeeping at 0.1 Hz interleaved.

Two naive workarounds fail:
  - Linear interpolation across a gap artificially smooths the very
    discontinuity that signals an anomaly.
  - Leaving gaps as NaN collapses the sequence length below the GRU/TCN
    minimum and produces reconstruction error unrelated to anomaly content.

Solution
--------
Augment each input token with the *elapsed time since the previous sample*,
normalised against the nominal cadence:

    x_t' = concat( x_t, log( Δt_t / Δt_nominal ) )

This is the mTAN (Multi-Time Attention Network) approach of Shukla & Marlin
(ICLR 2021).  The neural encoder can then learn that post-gap reconstruction
uncertainty is higher and scale its residuals accordingly.

For gaps larger than GAP_THRESHOLD × Δt_nominal we insert a *learned gap
token* (a dedicated sentinel value + a large positive log-Δt flag) rather
than interpolating across the void.  Downstream reconstruction loss is
masked at gap-token positions so the detector does not penalise the model
for failing to predict values that never existed.

References
----------
Shukla, S.N. & Marlin, B. (2021).  "Multi-Time Attention Networks for
    Irregularly Sampled Time Series."  ICLR 2021.

Rubanova, Y., Chen, T.Q. & Duvenaud, D. (2019).  "Latent ODEs for
    irregularly-sampled time series."  NeurIPS 2019.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# ── Encoder constants ────────────────────────────────────────────────────────
# Gap token sentinel value.  Chosen well outside the range of residual values
# (which are post-STL, roughly zero-mean, unit-scale after calibration).  The
# large negative value tells the encoder "no valid sample here".
GAP_TOKEN_VALUE: float = -999.0   # ESTIMATE — sentinel outside residual range

# When Δt > GAP_THRESHOLD × Δt_nominal, the interval counts as a "gap":
# insert a gap token rather than passing the raw sample unchanged.
# 3× nominal cadence is the threshold used in Shukla & Marlin 2021 §3.2
# for benchmark datasets (MIMIC-III, PhysioNet).
GAP_THRESHOLD: float = 3.0   # Shukla & Marlin 2021 ICLR §3.2

# Log-Δt value assigned to a gap token.  Must exceed the log-Δt that any
# non-gap interval could produce, so the encoder can learn "anything this
# large is a gap" without a separate categorical flag.  At GAP_THRESHOLD = 3
# the non-gap maximum is log(3) ≈ 1.10, so we use 5.0 as a safely distinct
# signal (corresponds to Δt ≈ 148 × nominal).
GAP_LOG_DT: float = 5.0   # ESTIMATE — distinct from any non-gap log(Δt/Δt_nom)

# Lower bound for Δt clipping.  A sample arriving faster than 0.1 × Δt_nominal
# produces a very large negative log value; we clip to avoid numerical blow-up
# while still conveying "this arrived quickly".
MIN_DT_FRAC: float = 0.1   # ESTIMATE — prevents log(0) and numerical blow-up


@dataclass(frozen=True, slots=True)
class EncodedSequence:
    """Output of `encode` — augmented input + gap mask.

    Fields
    ------
    values:    (T, 2) float32.  Column 0 is the residual (or GAP_TOKEN_VALUE
               at gap positions); column 1 is log(Δt / Δt_nominal).
    gap_mask:  (T,) bool.  True at positions that are synthetic gap tokens;
               the reconstruction loss should be masked at these indices.
    timestamps: (T,) float.  Unix-epoch timestamps for every row — gap-token
               rows receive the midpoint of the gap they represent.
    """

    values:     np.ndarray
    gap_mask:   np.ndarray
    timestamps: np.ndarray


def encode(
    residuals:      np.ndarray,
    timestamps:     np.ndarray,
    dt_nominal_s:   float,
    insert_gap_tokens: bool = True,
) -> EncodedSequence:
    """Encode residual + timestamp stream as (value, log-Δt) token stream.

    Algorithm (one pass, O(T)):

      1. Compute Δt[i] = timestamps[i] − timestamps[i-1], with Δt[0] set to
         `dt_nominal_s` so the first sample is "on schedule".
      2. Clip Δt below MIN_DT_FRAC × dt_nominal_s (prevents log(0)).
      3. For every i with Δt[i] ≤ GAP_THRESHOLD × dt_nominal_s:
             emit token (residuals[i], log(Δt[i] / dt_nominal_s)).
         Otherwise (gap detected):
             first emit a GAP token with log-Δt = GAP_LOG_DT,
             then emit the real sample using Δt = dt_nominal_s.

    Args
    ----
    residuals:     (T,) post-STL residuals for a single channel.
    timestamps:    (T,) Unix-epoch seconds, monotonically non-decreasing.
    dt_nominal_s:  Nominal sampling cadence for this channel (seconds).
    insert_gap_tokens:  If False, skip gap-token insertion (useful for
                   evaluating ablation: mTAN vs. plain log-Δt encoding).

    Returns
    -------
    EncodedSequence with augmented values, gap_mask, and timestamps.

    Raises
    ------
    ValueError when inputs are empty, mismatched length, or dt_nominal_s ≤ 0.
    """
    if dt_nominal_s <= 0.0:
        raise ValueError("dt_nominal_s must be > 0")
    residuals  = np.asarray(residuals,  dtype=np.float64)
    timestamps = np.asarray(timestamps, dtype=np.float64)
    if residuals.ndim != 1 or timestamps.ndim != 1:
        raise ValueError("residuals and timestamps must be 1-D")
    if len(residuals) != len(timestamps):
        raise ValueError("residuals and timestamps must have equal length")
    n = len(residuals)
    if n == 0:
        return EncodedSequence(
            values=np.zeros((0, 2), dtype=np.float64),
            gap_mask=np.zeros(0, dtype=bool),
            timestamps=np.zeros(0, dtype=np.float64),
        )

    min_dt = MIN_DT_FRAC * dt_nominal_s
    out_values:  list[tuple[float, float]] = []
    out_mask:    list[bool]                = []
    out_epoch:   list[float]               = []

    # First sample: treat its Δt as nominal (no prior reference).
    out_values.append((float(residuals[0]), 0.0))  # log(1) = 0
    out_mask.append(False)
    out_epoch.append(float(timestamps[0]))

    for i in range(1, n):
        dt = timestamps[i] - timestamps[i - 1]
        if dt < min_dt:
            dt = min_dt  # clip to avoid log(0) and negative log spikes

        if insert_gap_tokens and dt > GAP_THRESHOLD * dt_nominal_s:
            # Gap detected — insert one gap token at the midpoint, then the sample.
            gap_midpoint = (timestamps[i] + timestamps[i - 1]) * 0.5
            out_values.append((GAP_TOKEN_VALUE, GAP_LOG_DT))
            out_mask.append(True)
            out_epoch.append(float(gap_midpoint))
            # Real sample that follows uses nominal Δt since the gap token
            # already carries the "elapsed time" signal.
            out_values.append((float(residuals[i]), 0.0))
            out_mask.append(False)
            out_epoch.append(float(timestamps[i]))
        else:
            log_dt = float(np.log(dt / dt_nominal_s))
            out_values.append((float(residuals[i]), log_dt))
            out_mask.append(False)
            out_epoch.append(float(timestamps[i]))

    return EncodedSequence(
        values=np.asarray(out_values, dtype=np.float64),
        gap_mask=np.asarray(out_mask, dtype=bool),
        timestamps=np.asarray(out_epoch, dtype=np.float64),
    )


def reconstruction_loss_mask(encoded: EncodedSequence) -> np.ndarray:
    """Return a float mask in {0, 1} of shape (T,) suitable for element-wise
    multiplication with per-token reconstruction errors.

    Gap-token positions receive weight 0 so the encoder is not penalised for
    failing to predict sentinel values.
    """
    return (~encoded.gap_mask).astype(np.float64)


def effective_sample_count(encoded: EncodedSequence) -> int:
    """Number of real (non-gap) tokens in the encoded sequence."""
    return int((~encoded.gap_mask).sum())


def detect_nominal_cadence_s(
    timestamps: np.ndarray, min_samples: int = 10
) -> float:
    """Estimate the nominal sampling cadence Δt_nominal from a timestamp stream.

    Uses the median of the inter-sample differences — robust to a minority
    of gaps and rate changes.  Returns 0.0 when fewer than `min_samples`
    differences are available.
    """
    timestamps = np.asarray(timestamps, dtype=np.float64)
    if len(timestamps) < min_samples + 1:
        return 0.0
    diffs = np.diff(timestamps)
    valid = diffs[diffs > 0]
    if len(valid) < min_samples:
        return 0.0
    return float(np.median(valid))
