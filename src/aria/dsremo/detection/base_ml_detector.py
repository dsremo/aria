"""AbstractMLDetector — shared base for GRU and TCN autoencoder detectors.

Both AutoencoderDetector (GRU, Sprint 11) and TCNDetector (Sprint 13) share
~90% identical logic: buffer management, fit/detect/save/load lifecycle, MSE
scoring, and persistence.  This base class extracts that shared logic once.

Subclasses override three small methods:
    _build_model()             → construct and return an nn.Module
    _model_config() -> dict    → architecture params to persist in checkpoint
    _load_model_from_config()  → rebuild model from saved config dict

Public API (identical for both subclasses):
    det.add_sample(residual)
    det.fit([residuals])
    det.detect(residuals) -> DetectorResult
    det.save(path)
    det.load(path) -> bool
    det.sample_count, det.is_fitted, det.needs_refit()

Design constraints:
    - Lazy torch import: module importable without PyTorch installed.
    - Single-threaded asyncio: no locking needed.
    - Buffer cap: training data capped at 2000 samples so per-channel
      retrain cost stays O(1) regardless of how much history accumulates.
      (Fixes ESA channel_15 bottleneck where unbounded history caused 30s retrains.)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import structlog

logger = structlog.get_logger()

# Maximum training samples used per fit().  Caps retrain cost for long-running
# channels.  2000 >> seq_length (30-32) so the sliding-window dataset still
# has ~1970 sequences — plenty for a tiny autoencoder.
_MAX_TRAIN_SAMPLES = 2000  # ESTIMATE — 2000 sample cap; fits in ~1 s CPU inference for 5K-param model; ESA channel_15 bottleneck was >30s with unbounded history


class AbstractMLDetector(ABC):
    """Shared base for ML autoencoder anomaly detectors (GRU, TCN).

    Subclasses declare class variables:
        _detector_name: str   — used as DetectorResult.detector_name
        _log_prefix:    str   — prefix for structlog event names
    """

    _detector_name: str
    _log_prefix: str

    def __init__(
        self,
        seq_length:        int,
        epochs:            int,
        lr:                float,
        min_train_samples: int,
        retrain_interval:  int,
        threshold_sigma:   float,
    ) -> None:
        self.seq_length        = seq_length
        self.epochs            = epochs
        self.lr                = lr
        self.min_train_samples = min_train_samples
        self.retrain_interval  = retrain_interval
        self.threshold_sigma   = threshold_sigma

        # Runtime state
        self._buffer: list[float]    = []
        # V3-V1: parallel timestamp buffer.  Populated only when callers use
        # add_sample_with_time(); empty buffers mean "no time information" and
        # downstream mTAN encoding falls back to nominal cadence.
        self._ts_buffer: list[float] = []
        self._samples_since_fit: int = 0
        self._is_fitted: bool        = False
        self._model                  = None   # nn.Module | None
        # V3-V1: tracks whether the currently-fitted model expects 2-channel
        # (value, log-Δt) input.  Set to 2 when fit() used time-aware encoding;
        # 1 for the plain path.  detect() consults this to shape its input.
        self._input_channels: int    = 1

        # Learned from training data
        self._train_mean:     float = 0.0
        self._train_std:      float = 1.0
        self._train_mse_mean: float = 0.0
        self._train_mse_std:  float = 1.0
        self._threshold:      float = float("inf")

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def sample_count(self) -> int:
        return len(self._buffer)

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def needs_refit(self) -> bool:
        """True when enough new residuals have arrived since last training."""
        return self._is_fitted and self._samples_since_fit >= self.retrain_interval

    # ── Subclass contract ─────────────────────────────────────────────────────

    @abstractmethod
    def _build_model(self):  # type: ignore[no-untyped-def]
        """Construct and return an untrained nn.Module for this detector.

        Called lazily inside fit() — torch is never imported at module load.
        """

    @abstractmethod
    def _model_config(self) -> dict:
        """Return the architecture hyperparameters to persist in checkpoint."""

    @abstractmethod
    def _load_model_from_config(self, cfg: dict):  # type: ignore[no-untyped-def]
        """Rebuild model from a saved config dict (loaded from checkpoint)."""

    # ── Data accumulation ─────────────────────────────────────────────────────

    def add_sample(self, residual: float) -> None:
        """Append one STL residual to the training buffer."""
        self._buffer.append(float(residual))
        if self._is_fitted:
            self._samples_since_fit += 1

    def add_sample_with_time(self, residual: float, timestamp: float) -> None:
        """V3-V1: Append a (residual, Unix epoch timestamp) pair.

        Populates the parallel timestamp buffer so callers can later produce
        an mTAN-encoded sequence via `get_encoded_sequence`.  Keeps the plain
        residual buffer in sync so existing fit()/detect() paths are unaffected.
        """
        self._buffer.append(float(residual))
        self._ts_buffer.append(float(timestamp))
        if self._is_fitted:
            self._samples_since_fit += 1

    def get_encoded_sequence(self, dt_nominal_s: float):
        """V3-V1: Return an mTAN-encoded view of the buffered residuals.

        Only usable when `add_sample_with_time` has been populating timestamps.
        Returns None when no timestamps have been recorded, indicating the
        detector should use the plain `_buffer` for training (fixed Δt assumption).

        The encoded sequence augments each residual with log(Δt / Δt_nominal)
        and inserts gap tokens across large temporal discontinuities, per
        Shukla & Marlin 2021 (ICLR).
        """
        if not self._ts_buffer or len(self._ts_buffer) != len(self._buffer):
            return None
        # Local import: time_gap_encoder depends on numpy; tests for torch-free
        # environments should still be able to import this module.
        import numpy as _np  # noqa: PLC0415
        from aria.dsremo.detection.time_gap_encoder import encode  # noqa: PLC0415
        return encode(
            residuals=_np.asarray(self._buffer, dtype=_np.float64),
            timestamps=_np.asarray(self._ts_buffer, dtype=_np.float64),
            dt_nominal_s=dt_nominal_s,
        )

    # ── Time-aware tensor preparation (V3-V1) ────────────────────────────────

    def _prepare_time_aware_tensor(self, torch, dt_nominal_s: float):  # type: ignore[no-untyped-def]
        """Build (X, loss_mask, input_channels) tensors from the mTAN encoded buffer.

        Sliding windows are drawn over the encoded sequence so gap tokens sit
        inside windows exactly where they occurred temporally.  `loss_mask`
        is shape (N, seq_len) of {0, 1} floats — zero at gap-token positions.
        Falls back to (X_plain, None, 1) if encoding fails.
        """
        enc = self.get_encoded_sequence(dt_nominal_s)
        if enc is None or len(enc.values) < self.seq_length:
            # Fall back to plain path: callers will treat this as 1-channel.
            data = self._buffer[-_MAX_TRAIN_SAMPLES:] if len(self._buffer) > _MAX_TRAIN_SAMPLES else list(self._buffer)
            seqs = [data[i: i + self.seq_length] for i in range(len(data) - self.seq_length + 1)]
            X = torch.tensor(seqs, dtype=torch.float32).unsqueeze(-1)
            return X, None, 1

        # Encoded values have shape (T, 2); cap to _MAX_TRAIN_SAMPLES most recent rows.
        vals = enc.values
        gap  = enc.gap_mask
        if len(vals) > _MAX_TRAIN_SAMPLES:
            vals = vals[-_MAX_TRAIN_SAMPLES:]
            gap  = gap[-_MAX_TRAIN_SAMPLES:]

        # Real samples contribute to reconstruction loss; gap tokens do not.
        real_mask = (~gap).astype("float32")

        import numpy as _np  # noqa: PLC0415
        n_windows = len(vals) - self.seq_length + 1
        if n_windows <= 0:
            return (
                torch.zeros((0, self.seq_length, 2), dtype=torch.float32),
                torch.zeros((0, self.seq_length),    dtype=torch.float32),
                2,
            )
        seqs_arr  = _np.stack([vals[i: i + self.seq_length]      for i in range(n_windows)])
        masks_arr = _np.stack([real_mask[i: i + self.seq_length] for i in range(n_windows)])
        X         = torch.from_numpy(seqs_arr).float()   # (N, seq, 2)
        loss_mask = torch.from_numpy(masks_arr).float()  # (N, seq)
        return X, loss_mask, 2

    # ── V3-S1: labelled val slice for AUROC early-stopping ────────────────────

    def _build_auroc_val_tensor(
        self,
        *,
        torch,                        # type: ignore[no-untyped-def]
        raw_samples: list[float],
        seed: int | None,
    ) -> dict | None:
        """Assemble a (X_val, target_val, window_labels) triple for AUROC.

        Splits off the last `DEFAULT_VAL_FRACTION` of `raw_samples`, injects
        labelled synthetic anomalies (spike / drift / step), builds sliding
        windows, and normalises with the train statistics already computed
        on the training slice.  Returns None if the slice is too small.

        Only called in the 1-channel plain path — time-aware training
        already derives its labels from gap tokens, orthogonal to S-1.
        """
        import numpy as _np  # noqa: PLC0415
        from aria.dsremo.detection.auroc_objective import (  # noqa: PLC0415
            DEFAULT_INJECTION_RATE,
            DEFAULT_VAL_FRACTION,
            inject_labeled_anomalies,
            window_labels,
        )

        clean = _np.asarray(raw_samples, dtype=_np.float32)
        if clean.ndim != 1:
            return None
        min_val = self.seq_length + 10
        val_n = max(min_val, int(round(len(clean) * DEFAULT_VAL_FRACTION)))
        if len(clean) <= val_n or val_n < min_val:
            return None

        val_slice = clean[-val_n:]
        rng = _np.random.default_rng(seed) if seed is not None else _np.random.default_rng()
        try:
            injected = inject_labeled_anomalies(
                val_slice, injection_rate=DEFAULT_INJECTION_RATE, rng=rng,
            )
        except ValueError:
            return None

        # Sliding windows in raw (un-normalised) space.
        vals = injected.residuals
        n_windows = len(vals) - self.seq_length + 1
        if n_windows <= 0:
            return None
        seqs = _np.stack([vals[i: i + self.seq_length] for i in range(n_windows)])
        X_val_raw = torch.tensor(seqs, dtype=torch.float32).unsqueeze(-1)  # (N, seq, 1)
        # Normalise with training statistics already computed above.
        X_val = (X_val_raw - self._train_mean) / self._train_std
        target_val = X_val
        labels = window_labels(injected.sample_labels, seq_length=self.seq_length)
        if labels.sum() == 0:
            # No positive class → AUROC degenerate; skip objective.
            return None
        return {
            "X":      X_val,
            "target": target_val,
            "labels": labels.astype(_np.float32),
        }

    # ── Training ──────────────────────────────────────────────────────────────

    def fit(
        self,
        residuals: list[float] | None = None,
        *,
        dt_nominal_s: float | None = None,
        use_auroc_objective: bool = False,
        auroc_patience: int = 5,
        auroc_seed: int | None = None,
    ) -> None:
        """Train the model on the provided or buffered residuals.

        No-op if data is insufficient or PyTorch is not installed.

        Parameters
        ----------
        residuals:
            Optional external list to train on.  If None, trains on the
            internal buffer accumulated via add_sample().
            In both cases, data is capped at the last _MAX_TRAIN_SAMPLES
            points so that retrain cost stays O(1) for long-running channels.

        dt_nominal_s:
            V3-V1: when provided AND the internal timestamp buffer is
            populated via add_sample_with_time, use mTAN encoding so the
            model sees (residual, log-Δt) pairs with gap tokens inserted
            across large temporal discontinuities.  When None or no
            timestamps are available, the plain 1-channel path is used
            exactly as before.

        use_auroc_objective, auroc_patience, auroc_seed:
            V3-S1 (Singh 2020 §4): when `use_auroc_objective=True`, hold
            out the last `DEFAULT_VAL_FRACTION` of training sequences,
            inject labelled synthetic anomalies into the raw val slice
            (spike / drift / step), and early-stop on *validation AUROC*
            rather than val MSE.  Restores best-AUROC weights.  Backward
            compatible: default False keeps the MSE-only loop unchanged.
            `auroc_patience` is the epochs-without-improvement ceiling
            (default 5).  `auroc_seed` seeds the injection RNG for
            reproducible early-stopping behaviour.
        """
        try:
            import torch                  # noqa: PLC0415
            import torch.nn as nn         # noqa: PLC0415
        except ImportError:
            logger.warning(
                f"{self._log_prefix}_torch_missing",
                reason="torch not installed",
            )
            return

        raw = list(residuals) if residuals is not None else list(self._buffer)
        if len(raw) < self.min_train_samples:
            return

        # ── Prepare training tensor: plain 1-ch or mTAN-encoded 2-ch ────
        use_time = (
            dt_nominal_s is not None
            and residuals is None
            and len(self._ts_buffer) == len(self._buffer)
            and len(self._ts_buffer) >= self.min_train_samples
        )

        if use_time:
            X, mask, input_channels = self._prepare_time_aware_tensor(torch, dt_nominal_s)
        else:
            # Cap at _MAX_TRAIN_SAMPLES to bound retrain cost.
            data = raw[-_MAX_TRAIN_SAMPLES:] if len(raw) > _MAX_TRAIN_SAMPLES else raw
            seqs = [
                data[i: i + self.seq_length]
                for i in range(len(data) - self.seq_length + 1)
            ]
            if not seqs:
                return
            X = torch.tensor(seqs, dtype=torch.float32).unsqueeze(-1)  # (N, seq, 1)
            mask = None
            input_channels = 1

        # Normalise the value channel only (column 0).  Leaving log-Δt in
        # natural units preserves the "3× nominal → gap" interpretation.
        value_slice = X[..., 0:1]
        self._train_mean = float(value_slice.mean())
        self._train_std  = max(float(value_slice.std()), 1e-6)
        X_norm = X.clone()
        X_norm[..., 0:1] = (X[..., 0:1] - self._train_mean) / self._train_std
        X = X_norm

        # Reconstruction target is always the value channel, even when input
        # has 2 channels (the decoder outputs (seq_len, 1)).
        target = X[..., 0:1]

        self._input_channels = input_channels
        model   = self._build_model(input_channels=input_channels)
        opt     = torch.optim.Adam(model.parameters(), lr=self.lr)

        def _masked_mse(recon, tgt):
            # recon, tgt: (N, seq, 1).  mask: (N, seq) of {0,1}
            err = (recon - tgt) ** 2
            if mask is not None:
                err = err * mask.unsqueeze(-1)
                denom = mask.sum().clamp(min=1.0)
                return err.sum() / denom
            return err.mean()

        # V3-S5: clip gradient norm + detect training divergence.  Without
        # clipping, a single outlier window can produce NaN gradients that
        # silently disable the detector (score=0 for everything afterwards).
        # Reference: Pascanu, Mikolov & Bengio 2013, ICML §4 — grad clipping.
        GRAD_CLIP_MAX_NORM = 1.0     # Pascanu et al. 2013 §4: max_norm=1.0 is the canonical grad-clip value for RNN-like architectures

        # V3-S1: optionally build a labelled val slice for AUROC-based
        # early stopping.  Done up-front so the training loop does not
        # keep re-running injection every epoch.
        val_xform = None
        if use_auroc_objective and not use_time and input_channels == 1:
            val_xform = self._build_auroc_val_tensor(
                torch=torch,
                raw_samples=raw,
                seed=auroc_seed,
            )
        diverged = False
        best_state: dict | None = None
        best_auroc: float = -1.0
        patience_left = auroc_patience
        model.train()
        for _epoch in range(self.epochs):
            opt.zero_grad()
            loss = _masked_mse(model(X), target)
            if torch.isnan(loss) or torch.isinf(loss):
                logger.warning(
                    f"{self._log_prefix}_training_divergence",
                    epoch=_epoch,
                    reason="nan_or_inf_loss",
                )
                diverged = True
                break
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=GRAD_CLIP_MAX_NORM)
            opt.step()

            if val_xform is not None:
                model.eval()
                with torch.no_grad():
                    val_recon = model(val_xform["X"])
                    val_per_err = ((val_recon - val_xform["target"]) ** 2).squeeze(-1).mean(dim=1)
                scores_np = val_per_err.detach().cpu().numpy()
                from aria.dsremo.detection.auroc_objective import auroc_from_scores  # noqa: PLC0415
                epoch_auroc = auroc_from_scores(scores_np, val_xform["labels"])
                model.train()
                if epoch_auroc > best_auroc + 1e-6:
                    best_auroc = epoch_auroc
                    best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
                    patience_left = auroc_patience
                else:
                    patience_left -= 1
                    if patience_left <= 0:
                        logger.debug(
                            f"{self._log_prefix}_auroc_early_stop",
                            epoch=_epoch,
                            best_auroc=round(best_auroc, 4),
                        )
                        break

        if diverged:
            # Leave _is_fitted = False so detect() returns NOMINAL with
            # reason="model_not_fitted" — the detector will refit on the next
            # pass once clean samples accumulate.
            return

        # Restore best-AUROC weights if the objective was in use.
        if best_state is not None:
            model.load_state_dict(best_state)
            logger.debug(
                f"{self._log_prefix}_restored_best_auroc",
                best_auroc=round(best_auroc, 4),
            )

        model.eval()
        with torch.no_grad():
            per_err = ((model(X) - target) ** 2).squeeze(-1)  # (N, seq)
            if mask is not None:
                per_err = per_err * mask
                denom = mask.sum(dim=1).clamp(min=1.0)
                errors = (per_err.sum(dim=1) / denom).numpy()
            else:
                errors = per_err.mean(dim=1).numpy()

        self._model          = model
        self._train_mse_mean = float(errors.mean())
        self._train_mse_std  = max(float(errors.std()), 1e-6)

        # ── POT threshold (Peak Over Threshold / Extreme Value Theory) ────────
        # The fixed 3σ threshold assumes Gaussian reconstruction errors, but
        # GRU/TCN errors are right-skewed.  POT fits a Generalized Pareto
        # Distribution (GPD) to the tail of training errors and sets the
        # threshold at the 0.1% false-positive rate.
        # Falls back to 3σ if scipy is unavailable or too few tail samples.
        pot_threshold = self._pot_threshold(errors)
        self._threshold      = (
            pot_threshold if pot_threshold is not None
            else self._train_mse_mean + self.threshold_sigma * self._train_mse_std
        )
        self._is_fitted       = True
        self._samples_since_fit = 0

        logger.debug(
            f"{self._log_prefix}_trained",
            seq_length=self.seq_length,
            n_sequences=int(X.shape[0]),
            input_channels=input_channels,
            threshold=round(self._threshold, 6),
        )

    # ── POT threshold calibration ─────────────────────────────────────────────

    @staticmethod
    def _pot_threshold(
        errors: "np.ndarray",  # type: ignore[name-defined]
        q: float = 0.001,           # Siffer et al. 2017 KDD (SPOT algorithm): q = 10⁻³ FPR target; §3.2
        init_percentile: float = 0.85,  # ESTIMATE — 85th percentile init threshold (Siffer 2017 uses 98th, but 98th requires ≥100 samples; 85th works with 60+)
        min_tail_samples: int = 15,  # ESTIMATE — GPD needs ≥15 tail points for stable fit; Pickands 1975 Ann Stat 3 119: GPD threshold stability
    ) -> float | None:
        """Compute anomaly threshold via Peak Over Threshold (EVT).

        Sets the threshold at risk level q (default 0.1% FPR) using the
        Generalized Pareto Distribution fitted to training error tail exceedances.
        Returns None if scipy is unavailable or there are insufficient tail samples
        (falls back to caller's σ-based threshold in that case).

        Uses 85th percentile as the initial threshold (rather than 98th) to
        ensure enough tail samples even with 60-200 training sequences.

        Reference: Siffer et al., KDD 2017 — SPOT algorithm.
        """
        try:
            from scipy.stats import genpareto  # noqa: PLC0415
            import numpy as _np               # noqa: PLC0415
        except ImportError:
            return None

        init_t = float(_np.quantile(errors, init_percentile))
        exceedances = errors[errors > init_t] - init_t
        if len(exceedances) < min_tail_samples:
            return None  # not enough tail data — fall back to σ threshold

        try:
            shape, _, scale = genpareto.fit(exceedances, floc=0)
        except Exception:
            return None

        n_total  = len(errors)
        n_excess = len(exceedances)
        if shape == 0.0:
            # Exponential tail (shape → 0)
            return float(init_t - scale * _np.log(q * n_total / n_excess))
        return float(init_t + (scale / shape) * (
            (q * n_total / n_excess) ** (-shape) - 1.0
        ))

    # ── Detection ─────────────────────────────────────────────────────────────

    def detect(
        self,
        residuals: list[float],
        *,
        timestamps:   list[float] | None = None,
        dt_nominal_s: float | None       = None,
    ) -> "DetectorResult":  # type: ignore[name-defined]
        """Score the most recent seq_length residuals.

        Returns a DetectorResult with score in [0, 1].
        Falls back to NOMINAL when not fitted, insufficient data, or no torch.

        V3-V1: when `timestamps` and `dt_nominal_s` are provided AND the
        model was trained with 2-channel input, the window is mTAN-encoded
        so inference sees the same representation as training.
        """
        from aria.dsremo.core.models import DetectorResult, Severity  # noqa: PLC0415

        name = self._detector_name

        if not self._is_fitted:
            return DetectorResult(
                detector_name=name, is_anomaly=False, score=0.0,
                severity=Severity.NOMINAL, details={"reason": "model_not_fitted"},
            )

        if len(residuals) < self.seq_length:
            return DetectorResult(
                detector_name=name, is_anomaly=False, score=0.0,
                severity=Severity.NOMINAL, details={"reason": "insufficient_data"},
            )

        try:
            import torch  # noqa: PLC0415
        except ImportError:
            return DetectorResult(
                detector_name=name, is_anomaly=False, score=0.0,
                severity=Severity.NOMINAL, details={"reason": "torch_not_available"},
            )

        want_time = (
            self._input_channels == 2
            and timestamps is not None
            and dt_nominal_s is not None
            and len(timestamps) == len(residuals)
        )

        if want_time:
            from aria.dsremo.detection.time_gap_encoder import encode  # noqa: PLC0415
            import numpy as _np                                        # noqa: PLC0415
            enc = encode(
                residuals=_np.asarray(residuals, dtype=_np.float64),
                timestamps=_np.asarray(timestamps, dtype=_np.float64),
                dt_nominal_s=dt_nominal_s,
            )
            # Take the last seq_length rows of the encoded sequence — these
            # may include gap tokens, which reconstruction loss will mask.
            if len(enc.values) < self.seq_length:
                return DetectorResult(
                    detector_name=name, is_anomaly=False, score=0.0,
                    severity=Severity.NOMINAL, details={"reason": "insufficient_encoded_data"},
                )
            window_vals = enc.values[-self.seq_length:]
            window_mask = (~enc.gap_mask[-self.seq_length:]).astype("float32")
            X = torch.tensor(window_vals, dtype=torch.float32).unsqueeze(0)        # (1, seq, 2)
            X[..., 0:1] = (X[..., 0:1] - self._train_mean) / self._train_std
            target = X[..., 0:1]
            mask_t = torch.tensor(window_mask, dtype=torch.float32).unsqueeze(0)   # (1, seq)
            self._model.eval()
            with torch.no_grad():
                out = self._model(X)
            per_err = ((out - target) ** 2).squeeze(-1) * mask_t
            denom   = mask_t.sum().clamp(min=1.0)
            mse     = float(per_err.sum() / denom)
        else:
            window = residuals[-self.seq_length:]
            X = torch.tensor([[v] for v in window], dtype=torch.float32).unsqueeze(0)
            X = (X - self._train_mean) / self._train_std
            self._model.eval()
            with torch.no_grad():
                out = self._model(X)
            mse = float(((out - X) ** 2).mean())

        z     = (mse - self._train_mse_mean) / (
            self.threshold_sigma * self._train_mse_std
        )
        score      = float(min(max(z, 0.0), 1.0))
        is_anomaly = mse > self._threshold

        severity = Severity.NOMINAL
        if is_anomaly:
            severity = (
                Severity.CRITICAL if z >= 3.0 else  # ECSS-E-ST-70-32C §5.3: CRITICAL at 3σ
                Severity.WARNING  if z >= 2.0 else  # ECSS-E-ST-70-32C §5.3: WARNING at 2σ
                Severity.WATCH
            )

        return DetectorResult(
            detector_name=name,
            is_anomaly=is_anomaly,
            score=score,
            severity=severity,
            details={
                "mse":            mse,
                "threshold":      self._threshold,
                "train_mse_mean": self._train_mse_mean,
                "train_mse_std":  self._train_mse_std,
                "z_score":        z,
            },
        )

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, path: Path) -> None:
        """Persist model weights and MSE statistics to a checkpoint file.

        No-op if not fitted or torch is unavailable.
        """
        if not self._is_fitted or self._model is None:
            return
        try:
            import torch  # noqa: PLC0415
            path.parent.mkdir(parents=True, exist_ok=True)
            config = self._model_config()
            # V3-V1: persist input_channels so load() can rebuild the exact
            # architecture (1-channel plain model vs. 2-channel mTAN model).
            config["input_channels"] = self._input_channels
            torch.save(
                {
                    "state_dict":     self._model.state_dict(),
                    "train_mean":     self._train_mean,
                    "train_std":      self._train_std,
                    "train_mse_mean": self._train_mse_mean,
                    "train_mse_std":  self._train_mse_std,
                    "threshold":      self._threshold,
                    "sample_count":   len(self._buffer),
                    "config":         config,
                },
                path,
            )
            logger.debug(f"{self._log_prefix}_model_saved", path=str(path))
        except Exception as exc:
            logger.warning(
                f"{self._log_prefix}_model_save_failed",
                path=str(path),
                error=str(exc),
            )

    def load(self, path: Path) -> bool:
        """Warm-start from a persisted checkpoint.

        Returns True on success, False on any error (caller continues cold-start).
        """
        try:
            import torch  # noqa: PLC0415
            checkpoint = torch.load(path, map_location="cpu", weights_only=True)
            cfg = checkpoint.get("config", {})
            model = self._load_model_from_config(cfg)
            model.load_state_dict(checkpoint["state_dict"])
            model.eval()
            self._model           = model
            self._train_mean      = float(checkpoint["train_mean"])
            self._train_std       = float(checkpoint["train_std"])
            self._train_mse_mean  = float(checkpoint["train_mse_mean"])
            self._train_mse_std   = float(checkpoint["train_mse_std"])
            self._threshold       = float(checkpoint["threshold"])
            self._input_channels  = int(cfg.get("input_channels", 1))
            self._is_fitted       = True
            self._samples_since_fit = 0
            logger.debug(f"{self._log_prefix}_model_loaded", path=str(path))
            return True
        except Exception as exc:
            logger.warning(
                f"{self._log_prefix}_model_load_failed",
                path=str(path),
                error=str(exc),
            )
            return False
