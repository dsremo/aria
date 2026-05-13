"""V3-S3: Out-of-distribution detector via Mahalanobis distance on latent features.

Problem
-------
When a GRU or TCN model trained on Satellite A is applied to Satellite B
(same constellation, different bus revision) the reconstruction errors are
systematically elevated due to *domain shift*, not genuine anomalies.
The pipeline cannot currently distinguish "Satellite B is OOD for this
model" from "Satellite B has a fault."  In multi-tenant fleet deployments
this produces false-positive storms at onboarding.

Solution
--------
Fit a Mahalanobis distribution to the bottleneck (latent) representations
of training sequences:

    μ_train, Σ_train = sample mean and covariance of z_i = encoder(x_i)

At inference, compute:

    d_M(z) = sqrt( (z − μ_train)ᵀ Σ_train⁻¹ (z − μ_train) )

When `d_M` exceeds a threshold (set at the 99.9th percentile of training-set
Mahalanobis distances), the sample is flagged as OOD and its ML-detector
score is suppressed until fine-tuning has converged.

This module is architecture-agnostic — any latent-feature extractor that
returns a fixed-length vector per window can be paired with the Mahalanobis
distribution here.  Integration with `AbstractMLDetector` is the next step.

Reference
---------
Lee, K. et al. (2018).  "A simple unified framework for detecting
    out-of-distribution samples and adversarial attacks."  NeurIPS 2018.
    §3.2 — Mahalanobis distance OOD detection.

Ruff, L. et al. (2021).  "A unifying review of deep and shallow anomaly
    detection."  Proceedings of the IEEE 109(5).  §5 — representation-space
    anomaly detection.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# ── Defaults ───────────────────────────────────────────────────────────────
# Numerical floor added to the covariance diagonal before inversion.  A
# small isotropic jitter (λI) is the standard trick (Lee 2018 §3.2) to
# guarantee invertibility when the training-set covariance is rank-deficient
# (e.g. when latent dims exceed the number of training windows).
COV_JITTER: float = 1e-6   # Lee 2018 §3.2 — Tikhonov jitter for numerical stability

# OOD threshold percentile of the training-set Mahalanobis distances.  The
# 99.9-th percentile yields a theoretical 0.1 % false-positive rate under
# a well-fit Gaussian — the canonical choice in Lee 2018 §4.
DEFAULT_OOD_PERCENTILE: float = 99.9   # Lee 2018 §4


@dataclass(frozen=True, slots=True)
class MahalanobisOOD:
    """Fitted OOD detector.

    Fields
    ------
    mean:      (d,) sample mean of training latents.
    inv_cov:   (d, d) inverse covariance (Tikhonov-regularised).
    threshold: Mahalanobis distance above which a sample is flagged OOD.
    """

    mean:      np.ndarray
    inv_cov:   np.ndarray
    threshold: float

    def score(self, latents: np.ndarray) -> np.ndarray:
        """Mahalanobis distance for each row of `latents` (shape (n, d))."""
        z = np.atleast_2d(np.asarray(latents, dtype=np.float64))
        diff = z - self.mean[None, :]
        # (n, d) @ (d, d) @ (d, n) → diagonal = per-row quadratic form.
        quad = np.einsum("nd,de,ne->n", diff, self.inv_cov, diff)
        return np.sqrt(np.maximum(quad, 0.0))

    def is_ood(self, latents: np.ndarray) -> np.ndarray:
        """Boolean mask — True for rows whose distance exceeds the threshold."""
        return self.score(latents) > self.threshold


def fit_mahalanobis_ood(
    latents: np.ndarray,
    percentile: float = DEFAULT_OOD_PERCENTILE,
    jitter:     float = COV_JITTER,
) -> MahalanobisOOD:
    """Fit Mahalanobis parameters from a matrix of training latents.

    Args
    ----
    latents:    (n, d) float matrix.  n = number of training windows,
                d = latent dimension (e.g. GRU bottleneck size = 8).
    percentile: Training-set distance percentile used as the OOD threshold.
                Default 99.9 → approximately 0.1 % false-positive rate.
    jitter:     Tikhonov regulariser added to the covariance diagonal to
                guarantee invertibility.

    Returns
    -------
    MahalanobisOOD with mean, inv_cov, and threshold populated.

    Raises
    ------
    ValueError when `latents` has fewer than `d + 1` rows or d == 0.
    """
    Z = np.atleast_2d(np.asarray(latents, dtype=np.float64))
    if Z.size == 0 or Z.ndim != 2:
        raise ValueError("latents must be a non-empty 2-D array")
    n, d = Z.shape
    if d == 0:
        raise ValueError("latent dimension must be ≥ 1")
    if n < d + 1:
        raise ValueError(
            f"need at least d+1={d + 1} samples to fit covariance; got {n}"
        )

    mean  = Z.mean(axis=0)
    diff  = Z - mean[None, :]
    cov   = (diff.T @ diff) / max(n - 1, 1)
    # Tikhonov jitter ensures positive-definiteness under rank deficiency.
    cov_reg = cov + jitter * np.eye(d)
    inv_cov = np.linalg.inv(cov_reg)

    train_dists = np.sqrt(np.maximum(
        np.einsum("nd,de,ne->n", diff, inv_cov, diff), 0.0,
    ))
    threshold = float(np.percentile(train_dists, percentile))

    return MahalanobisOOD(mean=mean, inv_cov=inv_cov, threshold=threshold)
