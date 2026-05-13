"""LoRA fine-tuning script for ESM-2 radiation damage prediction.

Panel 11 (AI/ML Engineer) critique:
- Must use LoRA (r=16), not full fine-tuning
- ESM-2 650M has 650M params; GeneLab radiation data is ~10K sequences → catastrophic overfit
- Trainable params: 2 × 33 layers × 2 (Q,V) × 1280 × 16 = 2,703,360 (~0.4%)
- Loss: BCE + λ_cal × ECE (Expected Calibration Error)
- Train/test split: MMseqs2 at 30% identity (no homolog leakage)

This script is run offline, not as part of the API server.
Usage: python -m genastra.radiation.training.lora_finetune --config configs/training.yaml
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger()


@dataclass
class LoRAConfig:
    """LoRA adapter configuration."""

    rank: int = 16
    alpha: float = 32.0  # scaling = alpha / rank
    dropout: float = 0.1
    target_modules: tuple[str, ...] = ("q_proj", "v_proj")
    base_model: str = "esm2_t33_650M_UR50D"  # 650M parameter model
    trainable_params: int = 2_703_360  # ~0.4% of total


@dataclass
class TrainingConfig:
    """Full training configuration for radiation damage LoRA."""

    lora: LoRAConfig = field(default_factory=LoRAConfig)
    batch_size: int = 8
    learning_rate: float = 1e-4
    weight_decay: float = 0.01
    max_epochs: int = 50
    early_stopping_patience: int = 5
    calibration_lambda: float = 0.1  # weight for calibration loss
    calibration_bins: int = 10
    max_sequence_length: int = 1024  # training limit (GPU memory)
    gradient_accumulation_steps: int = 4
    seed: int = 42
    output_dir: str = "models/radiation_lora"
    data_dir: str = "data/radiation"
    mmseqs2_identity_threshold: float = 0.30  # 30% for train/test split


def compute_calibration_loss(
    predictions: list[float],
    labels: list[int],
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error (ECE).

    ECE = Σ_b |accuracy(b) - confidence(b)| × |B_b| / N

    Forces the model's predicted probabilities to be well-calibrated:
    if it says P=0.7, then ~70% of those predictions should be true positives.
    """
    import numpy as np

    preds = np.array(predictions)
    labs = np.array(labels)
    n = len(preds)
    if n == 0:
        return 0.0

    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0

    for i in range(n_bins):
        mask = (preds >= bin_boundaries[i]) & (preds < bin_boundaries[i + 1])
        count = mask.sum()
        if count > 0:
            avg_confidence = preds[mask].mean()
            avg_accuracy = labs[mask].mean()
            ece += abs(avg_accuracy - avg_confidence) * count / n

    return float(ece)


def compute_training_data_hash(data_dir: str) -> str:
    """Compute a deterministic hash of the training data for provenance.

    Every trained model must record this hash so we can verify
    which data was used.
    """
    h = hashlib.sha256()
    data_path = Path(data_dir)

    for f in sorted(data_path.glob("**/*")):
        if f.is_file() and f.suffix in (".csv", ".tsv", ".json", ".fasta"):
            h.update(f.read_bytes())

    return h.hexdigest()


def generate_provenance(config: TrainingConfig, data_hash: str) -> dict:
    """Generate a provenance record for a trained model.

    Panel 10 (ESA Researcher): "Every analysis must store the exact
    software version, input parameters, and random seeds used."
    """
    return {
        "model_type": "esm2_radiation_lora",
        "base_model": config.lora.base_model,
        "lora_rank": config.lora.rank,
        "lora_alpha": config.lora.alpha,
        "target_modules": list(config.lora.target_modules),
        "trainable_params": config.lora.trainable_params,
        "training_data_hash": data_hash,
        "batch_size": config.batch_size,
        "learning_rate": config.learning_rate,
        "max_epochs": config.max_epochs,
        "calibration_lambda": config.calibration_lambda,
        "seed": config.seed,
        "mmseqs2_identity_threshold": config.mmseqs2_identity_threshold,
    }


# ── Main training loop would be here ──────────────────────────────
# Actual training requires:
# 1. GeneLab radiation proteomics data (not yet collected)
# 2. GPU environment with torch + fair-esm
# 3. MMseqs2 for sequence clustering
#
# The training script will be completed when data is available.
# For now, the heuristic predictor in damage_predictor.py serves as fallback.
