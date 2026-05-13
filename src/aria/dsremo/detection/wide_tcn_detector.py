"""V3-S2: wide-receptive-field TCN for orbital-period patterns.

The existing `TCNDetector` (Sprint 13) has n_blocks=4, kernel_size=3,
and therefore a causal receptive field of

    RF = 1 + 2 · (kernel - 1) · (2^n_blocks - 1) = 1 + 4 · 15 = 61 steps

At 1 Hz that covers ~1 min — useful for spike and short oscillation
patterns, but completely blind to orbital-period phenomena (LEO
~5400 s period).  Singh panel §S-2 in the V3 audit flagged this:

> TCN can only detect patterns within a 24-second window — i.e. spike
> patterns and very fast oscillations only.  This makes the TCN and
> GRU redundant.  For the TCN to add value over simpler detectors,
> receptive field must cover the orbital period.

Rather than reshape the existing `TCNDetector` (which is tuned for
short-range residuals and whose checkpoints are in the field), we add
a *sibling* detector with dilations {1, 2, 4, 8, 16, 32, 64, 128} and
seq_length 256.  Receptive field:

    RF = 1 + 2 · (kernel - 1) · (2^n_blocks - 1)
       = 1 + 2 · 2 · (2^8 - 1)
       = 1 + 4 · 255
       = 1021 steps        ≈ 17 min at 1 Hz

The stack still fits the CPU-only budget (~30 k parameters, < 1 s CPU
inference at seq_length=256).  For an ensemble perspective the two
TCNs are now *complementary*: `TCNDetector` catches 1-minute-scale
anomalies; `WideTCNDetector` catches trend-scale patterns.

References
  * Bai, Kolter, Koltun (2018) arXiv:1803.01271 §3 — dilated-conv RF formula.
  * van den Oord et al. (2016) arXiv:1609.03499 — WaveNet dilation strategy.
"""

from __future__ import annotations

from aria.dsremo.detection.base_ml_detector import AbstractMLDetector
from aria.dsremo.detection.tcn_detector import _build_tcn_model


def causal_tcn_receptive_field(
    n_blocks: int,
    kernel_size: int = 3,
) -> int:
    """Return the causal receptive field of a dilated TCN stack.

    Formula: RF = 1 + 2 · (kernel - 1) · (2^n_blocks - 1) for 2 causal
    conv layers per block with geometric dilation.  Reference: Bai,
    Kolter & Koltun (2018) arXiv:1803.01271 §3.
    """
    if n_blocks <= 0 or kernel_size < 2:
        raise ValueError(
            f"n_blocks must be ≥ 1 and kernel_size ≥ 2, got "
            f"n_blocks={n_blocks!r}, kernel_size={kernel_size!r}"
        )
    return 1 + 2 * (kernel_size - 1) * ((1 << n_blocks) - 1)


class WideTCNDetector(AbstractMLDetector):
    """TCN detector with orbital-period-scale receptive field (V3-S2).

    detector_name = "wide_tcn" — ensemble-distinct from "tcn".

    Default RF ≈ 1021 steps (17 min @ 1 Hz).  The compute budget
    per fit is ≲ 1 s on CPU for 2000 windows × seq_length=256.
    """

    _detector_name = "wide_tcn"
    _log_prefix    = "wide_tcn"

    def __init__(
        self,
        seq_length:        int   = 256,  # Matches the RF so each window carries the full causal dependency chain; Bai 2018 §3 recommends seq_length ≥ RF
        n_channels:        int   = 16,   # Matches short TCN — 16 channels keeps parameter count ~30 k (CPU-only)
        n_blocks:          int   = 8,    # Dilations {1,2,4,8,16,32,64,128} → RF=1021 (Bai 2018 §3 formula)
        kernel_size:       int   = 3,    # Identical to short TCN for comparability
        epochs:            int   = 40,   # ESTIMATE — matches short TCN; convergence on seq_length=256 empirically similar to seq_length=32
        lr:                float = 0.002, # ESTIMATE — Bai 2018 Appendix: 0.002-0.01 for deeper TCN; halved vs short TCN since grad magnitudes grow with depth
        min_train_samples: int   = 512,  # ESTIMATE — 2 × seq_length for ≥ 256 sliding windows; matches short TCN's 2×seq_length heuristic
        retrain_interval:  int   = 1000, # ESTIMATE — longer than short TCN (500): wider RF means more sensitivity to state, refresh more conservatively
        threshold_sigma:   float = 3.0,  # Shewhart 1931: 3σ; see also _pot_threshold EVT fallback
    ) -> None:
        super().__init__(
            seq_length=seq_length,
            epochs=epochs,
            lr=lr,
            min_train_samples=min_train_samples,
            retrain_interval=retrain_interval,
            threshold_sigma=threshold_sigma,
        )
        self.n_channels  = n_channels
        self.n_blocks    = n_blocks
        self.kernel_size = kernel_size

    @property
    def receptive_field(self) -> int:
        return causal_tcn_receptive_field(self.n_blocks, self.kernel_size)

    def _build_model(self, input_channels: int = 1):  # type: ignore[no-untyped-def]
        return _build_tcn_model(
            self.seq_length, self.n_channels, self.n_blocks, self.kernel_size,
            input_channels=input_channels,
        )

    def _model_config(self) -> dict:
        return {
            "seq_length":  self.seq_length,
            "n_channels":  self.n_channels,
            "n_blocks":    self.n_blocks,
            "kernel_size": self.kernel_size,
        }

    def _load_model_from_config(self, cfg: dict):  # type: ignore[no-untyped-def]
        return _build_tcn_model(
            cfg.get("seq_length",  self.seq_length),
            cfg.get("n_channels",  self.n_channels),
            cfg.get("n_blocks",    self.n_blocks),
            cfg.get("kernel_size", self.kernel_size),
        )


__all__ = ["WideTCNDetector", "causal_tcn_receptive_field"]
