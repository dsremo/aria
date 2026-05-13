"""V3-V2: masked-residual self-supervised pretraining for the GRU backbone.

The V3 audit (van der Schaar panel §V-2) flags that a new satellite
cold-starts from 100 calibration samples while its neural backbone has
thousands of free parameters — severe overfitting.  The fix is fleet-
level pretraining: train on pooled historical residuals across many
satellites, then warm-start each new satellite's detector from the
pretrained weights.

This module implements a lightweight variant of BERT-style masked
prediction for 1-D time series.  Given a residual corpus:
  1. Slide seq_length windows over each satellite's history
  2. Random-mask `mask_ratio` of positions in each window (set to 0)
  3. Train the standard GRU autoencoder to reconstruct the FULL
     window from the masked version; loss is weighted to the masked
     positions so the model must infer from context
  4. Save (state_dict, train_mean, train_std, config) as a .pt file

Fine-tuning on a new satellite uses `AutoencoderDetector.warmstart_from`
to load the weights before its normal `fit()` refinement.

Contrastive approaches (SimCLR-TS, TF-C) are a later step — they
require augmentation choices that differ per spacecraft class and
benefit from a larger compute budget than CPU-only pretraining can
afford.  Masked prediction is the CPU-tractable minimum viable.

References
  * Devlin et al. 2019 NAACL §3.1 — masked-language-modeling formulation.
  * Zerveas et al. 2021 KDD — "A Transformer-based Framework for
    Multivariate Time Series Representation Learning"; §3.2 applies
    masked-value pretraining to time series, the template this module
    follows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


DEFAULT_MASK_RATIO = 0.15  # Devlin 2019 §3.1 — the canonical BERT mask fraction; works well for TS per Zerveas 2021 §4.1
DEFAULT_SEQ_LENGTH = 30    # Matches AutoencoderDetector default
DEFAULT_HIDDEN     = 32    # Matches AutoencoderDetector default
DEFAULT_BOTTLENECK = 8     # Matches AutoencoderDetector default
DEFAULT_EPOCHS     = 40    # ESTIMATE — matches AutoencoderDetector; pretrain corpus is larger so more epochs not needed
DEFAULT_LR         = 0.005 # ESTIMATE — 2× lower than AutoencoderDetector default (0.01) since pretrain wants smoother weights for fine-tune
DEFAULT_BATCH_SIZE = 64    # ESTIMATE — bounded to fit CPU memory for pooled multi-satellite corpus
MIN_CORPUS_WINDOWS = 200   # ESTIMATE — ≥200 windows for a meaningful fleet-level backbone; below this, backbone doesn't beat per-sat training


@dataclass(frozen=True)
class MaskedPretrainConfig:
    """Architecture-and-training settings baked into the checkpoint."""

    seq_length:  int   = DEFAULT_SEQ_LENGTH
    hidden:      int   = DEFAULT_HIDDEN
    bottleneck:  int   = DEFAULT_BOTTLENECK
    epochs:      int   = DEFAULT_EPOCHS
    lr:          float = DEFAULT_LR
    batch_size:  int   = DEFAULT_BATCH_SIZE
    mask_ratio:  float = DEFAULT_MASK_RATIO

    def to_dict(self) -> dict:
        return {
            "seq_length": self.seq_length,
            "hidden":     self.hidden,
            "bottleneck": self.bottleneck,
            "epochs":     self.epochs,
            "lr":         self.lr,
            "batch_size": self.batch_size,
            "mask_ratio": self.mask_ratio,
        }


@dataclass
class MaskedPretrainResult:
    """Outcome of a pretraining run — weights + normalisation + metadata."""

    state_dict: dict                                    # torch state_dict — keeps dict-of-tensors typing out of this module
    train_mean: float
    train_std:  float
    config:     MaskedPretrainConfig
    n_windows:  int
    n_satellites: int
    final_loss: float
    sat_ids:    list[str] = field(default_factory=list)


# ── Public helpers (pure NumPy) ───────────────────────────────────────────────


def build_masked_windows(
    corpus_by_sat: dict[str, np.ndarray],
    seq_length: int,
    mask_ratio: float = DEFAULT_MASK_RATIO,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
    """Assemble the masked-window training set from a multi-satellite corpus.

    Returns (X_masked, X_target, mask, mean, std) where:
      X_masked  shape (N, seq_length) with masked positions set to 0
      X_target  shape (N, seq_length) — the original unmasked window
      mask      shape (N, seq_length) float {0, 1}; 1 at masked positions
      mean,std  normalisation stats computed on the FULL (unmasked) corpus
                so fine-tuners can re-apply identically.

    Rules
      * Only satellites with ≥ seq_length residuals contribute
      * Each satellite contributes non-overlapping windows (stride=seq_length)
      * mask_ratio ∈ (0, 1) strictly; at least 1 masked position per window
    """
    if not corpus_by_sat:
        raise ValueError("corpus_by_sat is empty")
    if seq_length <= 0:
        raise ValueError(f"seq_length must be positive, got {seq_length!r}")
    if not 0.0 < mask_ratio < 1.0:
        raise ValueError(f"mask_ratio must be in (0, 1), got {mask_ratio!r}")

    if rng is None:
        rng = np.random.default_rng()

    # Normalisation stats across the pooled corpus (pre-masking).
    all_samples: list[float] = []
    for arr in corpus_by_sat.values():
        all_samples.extend(np.asarray(arr, dtype=np.float64).ravel().tolist())
    if not all_samples:
        raise ValueError("corpus_by_sat contains no samples")
    mean = float(np.mean(all_samples))
    std  = max(float(np.std(all_samples)), 1e-6)

    windows: list[np.ndarray] = []
    for arr in corpus_by_sat.values():
        a = np.asarray(arr, dtype=np.float64).ravel()
        if len(a) < seq_length:
            continue
        # Stride = seq_length → disjoint windows → larger effective fleet.
        n_windows = len(a) // seq_length
        for k in range(n_windows):
            w = a[k * seq_length: (k + 1) * seq_length]
            windows.append(w)

    if not windows:
        raise ValueError(
            f"no window fits seq_length={seq_length} in corpus; "
            f"longest satellite has {max((len(np.asarray(a).ravel()) for a in corpus_by_sat.values()), default=0)} samples"
        )

    X_target = np.stack(windows).astype(np.float32)
    X_target_norm = ((X_target - mean) / std).astype(np.float32)

    # Random mask: Bernoulli(mask_ratio), clamped to ≥1 masked position per row.
    mask = (rng.random(size=X_target_norm.shape) < mask_ratio).astype(np.float32)
    # Ensure at least one masked cell per window.
    zero_rows = np.where(mask.sum(axis=1) == 0)[0]
    if len(zero_rows):
        cols = rng.integers(0, seq_length, size=len(zero_rows))
        mask[zero_rows, cols] = 1.0

    X_masked = X_target_norm.copy()
    X_masked[mask.astype(bool)] = 0.0  # zero-mask token

    return X_masked, X_target_norm, mask, mean, std


# ── Training entry-point (lazy torch import) ──────────────────────────────────


def pretrain_gru_on_corpus(
    corpus_by_sat: dict[str, np.ndarray],
    config: MaskedPretrainConfig | None = None,
    *,
    rng_seed: int | None = None,
) -> MaskedPretrainResult:
    """Train the GRU autoencoder on masked-residual prediction.

    The backbone is the same `_build_gru_model(seq_len, hidden,
    bottleneck, input_channels=1)` used by `AutoencoderDetector`, so
    the resulting state_dict is warm-start-compatible with the
    production detector.  Training loss is mean-squared error on
    *masked positions only* — unmasked positions carry no gradient
    (zeroed by the loss mask).

    Raises `RuntimeError` if torch is not installed.  Returns a
    `MaskedPretrainResult` whose `save()` companion is
    `save_pretrain_result(result, path)`.
    """
    try:
        import torch        # noqa: PLC0415
        import torch.nn as nn  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("pretrain_gru_on_corpus requires PyTorch") from exc

    cfg = config or MaskedPretrainConfig()
    rng = np.random.default_rng(rng_seed) if rng_seed is not None else np.random.default_rng()

    X_masked_np, X_target_np, mask_np, mean, std = build_masked_windows(
        corpus_by_sat,
        seq_length=cfg.seq_length,
        mask_ratio=cfg.mask_ratio,
        rng=rng,
    )
    if len(X_masked_np) < MIN_CORPUS_WINDOWS:
        raise ValueError(
            f"corpus too small: got {len(X_masked_np)} windows, "
            f"need ≥{MIN_CORPUS_WINDOWS}. Extend the pretrain corpus or "
            f"accept a smaller backbone via cfg.seq_length."
        )

    # Lazy import to match autoencoder_detector's import lifecycle.
    from aria.dsremo.detection.autoencoder_detector import _build_gru_model  # noqa: PLC0415

    model = _build_gru_model(
        seq_len=cfg.seq_length,
        hidden=cfg.hidden,
        bottleneck=cfg.bottleneck,
        input_channels=1,
    )

    X_masked = torch.from_numpy(X_masked_np).unsqueeze(-1)   # (N, seq, 1)
    X_target = torch.from_numpy(X_target_np).unsqueeze(-1)   # (N, seq, 1)
    mask_t   = torch.from_numpy(mask_np).unsqueeze(-1)       # (N, seq, 1)

    opt = torch.optim.Adam(model.parameters(), lr=cfg.lr)
    model.train()
    final_loss = float("nan")
    GRAD_CLIP_MAX_NORM = 1.0  # Pascanu, Mikolov, Bengio 2013 ICML §4 — canonical RNN grad-norm clip
    for _epoch in range(cfg.epochs):
        # Simple full-batch training — CPU is fine for a few thousand windows.
        opt.zero_grad()
        recon = model(X_masked)
        err = (recon - X_target) ** 2
        loss = (err * mask_t).sum() / mask_t.sum().clamp(min=1.0)
        if torch.isnan(loss) or torch.isinf(loss):
            raise RuntimeError(
                f"pretrain diverged at epoch {_epoch}: loss={float(loss)!r}"
            )
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=GRAD_CLIP_MAX_NORM)
        opt.step()
        final_loss = float(loss.detach())

    state = {k: v.detach().clone().cpu() for k, v in model.state_dict().items()}
    return MaskedPretrainResult(
        state_dict=state,
        train_mean=float(mean),
        train_std=float(std),
        config=cfg,
        n_windows=int(X_masked_np.shape[0]),
        n_satellites=len([a for a in corpus_by_sat.values() if len(np.asarray(a).ravel()) >= cfg.seq_length]),
        final_loss=final_loss,
        sat_ids=list(corpus_by_sat.keys()),
    )


# ── Persistence ───────────────────────────────────────────────────────────────


def save_pretrain_result(result: MaskedPretrainResult, path: Path) -> None:
    """Write a `MaskedPretrainResult` to disk as a torch checkpoint.

    Schema keys (stable):
      state_dict, train_mean, train_std, config (dict),
      n_windows, n_satellites, final_loss, sat_ids, format="v3-v2".
    """
    import torch  # noqa: PLC0415

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "format":       "v3-v2",
            "state_dict":   result.state_dict,
            "train_mean":   result.train_mean,
            "train_std":    result.train_std,
            "config":       result.config.to_dict(),
            "n_windows":    result.n_windows,
            "n_satellites": result.n_satellites,
            "final_loss":   result.final_loss,
            "sat_ids":      list(result.sat_ids),
        },
        path,
    )


def load_pretrain_result(path: Path) -> MaskedPretrainResult:
    """Read a pretrain checkpoint back into a ``MaskedPretrainResult``.

    Uses ``weights_only=True`` so a malicious checkpoint dropped on disk
    cannot smuggle arbitrary Python via pickle (CVE-2024-31580 class).
    The structured fields we serialise (state_dict, config dict, sat_ids
    list) all round-trip through the safe loader.
    """
    import torch  # noqa: PLC0415

    blob = torch.load(path, map_location="cpu", weights_only=True)
    if blob.get("format") != "v3-v2":
        raise ValueError(
            f"unexpected pretrain checkpoint format: {blob.get('format')!r} "
            "(expected 'v3-v2')"
        )
    cfg_dict = blob["config"]
    return MaskedPretrainResult(
        state_dict=blob["state_dict"],
        train_mean=float(blob["train_mean"]),
        train_std=float(blob["train_std"]),
        config=MaskedPretrainConfig(
            seq_length=int(cfg_dict["seq_length"]),
            hidden=int(cfg_dict["hidden"]),
            bottleneck=int(cfg_dict["bottleneck"]),
            epochs=int(cfg_dict["epochs"]),
            lr=float(cfg_dict["lr"]),
            batch_size=int(cfg_dict["batch_size"]),
            mask_ratio=float(cfg_dict["mask_ratio"]),
        ),
        n_windows=int(blob["n_windows"]),
        n_satellites=int(blob["n_satellites"]),
        final_loss=float(blob["final_loss"]),
        sat_ids=list(blob.get("sat_ids", [])),
    )


__all__ = [
    "DEFAULT_MASK_RATIO",
    "MIN_CORPUS_WINDOWS",
    "MaskedPretrainConfig",
    "MaskedPretrainResult",
    "build_masked_windows",
    "load_pretrain_result",
    "pretrain_gru_on_corpus",
    "save_pretrain_result",
]
