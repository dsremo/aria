"""LoRA fine-tuning scaffold for ARIA's on-ship language model.

Wraps HuggingFace PEFT + Transformers to fine-tune any causal LM with LoRA
adapters on the ARIA mission corpus.  Designed for offline execution on a
ground-station workstation; the resulting adapter is shipped with the spacecraft.

Target models (all fit in 16 GB RAM with 4-bit quantisation):
- ``microsoft/phi-3-mini-4k-instruct``  — 3.8 B params, best quality/size
- ``mistralai/Mistral-7B-Instruct-v0.3`` — 7 B params, stronger reasoning
- ``meta-llama/Llama-3.2-1B-Instruct``  — 1 B params, lowest compute

References
----------
Hu et al. (2022) "LoRA: Low-Rank Adaptation of Large Language Models"
    arXiv:2106.09685 — r=16, α=32 for instruction-following fine-tuning
Dettmers et al. (2023) "QLoRA: Efficient Finetuning of Quantized LLMs"
    arXiv:2305.14314 — 4-bit NF4 quantisation for 7B models on 16 GB GPU

Dependencies (optional, only needed for fine-tuning, not inference):
    pip install transformers>=4.40 peft>=0.10 bitsandbytes>=0.43 accelerate trl
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class LoRAConfig:
    """LoRA adapter hyperparameters.

    Defaults follow Hu et al. (2022) Table 2 for instruction-following:
    r=16, alpha=32 (scaling = alpha/r = 2.0), dropout=0.05.
    """
    r: int = 16                    # rank — number of trainable params ∝ r
    alpha: float = 32.0            # scaling: merged weight Δ = (α/r) * BA
    dropout: float = 0.05
    target_modules: tuple[str, ...] = (
        "q_proj", "k_proj", "v_proj", "o_proj",  # attention
        "gate_proj", "up_proj", "down_proj",       # MLP (LLaMA/Mistral/Phi)
    )
    bias: str = "none"             # "none" | "all" | "lora_only"
    task_type: str = "CAUSAL_LM"


@dataclass
class TrainingConfig:
    """Training hyperparameters for the LoRA fine-tune run."""
    base_model: str = "microsoft/phi-3-mini-4k-instruct"
    output_dir: str = str(Path.home() / ".aria" / "lm_adapter")
    lora: LoRAConfig = field(default_factory=LoRAConfig)
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 8
    learning_rate: float = 2e-4   # Hu et al. (2022) recommend 1e-4 – 3e-4
    lr_scheduler_type: str = "cosine"
    warmup_ratio: float = 0.05
    max_seq_length: int = 2048
    load_in_4bit: bool = True      # QLoRA (Dettmers 2023) — saves ~4× VRAM
    fp16: bool = False             # use bf16 on Ampere+, fp16 elsewhere
    bf16: bool = True
    eval_fraction: float = 0.05   # fraction of corpus reserved for eval
    save_steps: int = 200
    logging_steps: int = 20
    seed: int = 42
    push_to_hub: bool = False     # never push to hub without explicit opt-in


class LoRAFineTuner:
    """Fine-tune a causal LM on ARIA mission corpus with LoRA.

    All heavy imports (transformers, peft, trl) are deferred to ``train()``
    so this class can be instantiated and inspected without GPU deps installed.

    Args:
        model_name_or_path: HuggingFace model id or local path.
        output_dir:         Directory to save adapter weights.
        config:             Optional full TrainingConfig (overrides model_name
                            and output_dir if provided).

    Example::

        ft = LoRAFineTuner("microsoft/phi-3-mini-4k-instruct", "/data/aria_lm")
        ft.train(corpus_builder.to_hf_dataset())
        # Saved to /data/aria_lm/final_adapter/
    """

    def __init__(
        self,
        model_name_or_path: Optional[str] = None,
        output_dir: Optional[str] = None,
        config: Optional[TrainingConfig] = None,
    ) -> None:
        self.cfg = config or TrainingConfig()
        if model_name_or_path:
            self.cfg.base_model = model_name_or_path
        if output_dir:
            self.cfg.output_dir = output_dir

    def estimate_params(self) -> dict[str, Any]:
        """Estimate trainable-parameter count without loading the model.

        Uses known architecture sizes for common models.
        """
        known = {
            "phi-3-mini":  (3_800_000_000, 32, 3072),
            "mistral-7b":  (7_200_000_000, 32, 4096),
            "llama-3.2-1b": (1_200_000_000, 16, 2048),
            "llama-3-8b":  (8_000_000_000, 32, 4096),
        }
        n_target = len(self.cfg.lora.target_modules)
        r = self.cfg.lora.r
        name_lower = self.cfg.base_model.lower()

        for key, (total_params, n_layers, hidden) in known.items():
            if key in name_lower:
                # LoRA params: 2 × n_layers × n_modules × hidden × r
                lora_params = 2 * n_layers * n_target * hidden * r
                return {
                    "total_params": total_params,
                    "lora_trainable_params": lora_params,
                    "trainable_fraction_pct": 100 * lora_params / total_params,
                }
        return {
            "total_params": "unknown",
            "lora_trainable_params": "unknown",
            "trainable_fraction_pct": "unknown",
        }

    def train(self, dataset, eval_dataset=None) -> Path:
        """Run the LoRA fine-tune.

        Args:
            dataset:      HuggingFace ``Dataset`` or list of dicts with
                          ``system``, ``user``, ``assistant`` keys.
            eval_dataset: Optional held-out eval set. If None and
                          ``eval_fraction > 0``, a random split is made.

        Returns:
            Path to the saved adapter directory.

        Raises:
            ImportError: If ``transformers``, ``peft``, or ``trl`` are missing.
        """
        self._check_deps()

        import torch
        from datasets import Dataset
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            TrainingArguments,
        )
        from trl import SFTTrainer

        cfg = self.cfg

        # Convert list input to Dataset
        if isinstance(dataset, list):
            dataset = Dataset.from_list(dataset)

        # Train/eval split
        if eval_dataset is None and cfg.eval_fraction > 0:
            splits = dataset.train_test_split(
                test_size=cfg.eval_fraction, seed=cfg.seed
            )
            dataset = splits["train"]
            eval_dataset = splits["test"]

        # Pin the HF revision (XZ-class supply-chain defence). Operators
        # set ``cfg.base_model_revision`` (commit SHA) for production runs.
        revision = getattr(cfg, "base_model_revision", None)
        if revision is None:
            import warnings as _w
            _w.warn(
                f"Training against {cfg.base_model!r} without a pinned "
                "revision — set cfg.base_model_revision to a commit SHA "
                "to defend against upstream maintainer compromise.",
                RuntimeWarning, stacklevel=3,
            )

        # Tokenizer
        tokenizer = AutoTokenizer.from_pretrained(
            cfg.base_model, trust_remote_code=False, revision=revision,
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        # Quantisation config for QLoRA (Dettmers 2023)
        bnb_config = None
        if cfg.load_in_4bit:
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",      # Dettmers 2023 §3.1: NF4 beats FP4
                bnb_4bit_use_double_quant=True,  # nested quantisation saves ~0.4 GB
                bnb_4bit_compute_dtype=torch.bfloat16,
            )

        # Load base model — trust_remote_code=False means HF won't execute
        # arbitrary repo code; revision pins to a known commit SHA.
        model = AutoModelForCausalLM.from_pretrained(
            cfg.base_model,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=False,
            revision=revision,
        )
        if cfg.load_in_4bit:
            model = prepare_model_for_kbit_training(model)

        # Apply LoRA
        lora_cfg = cfg.lora
        peft_cfg = LoraConfig(
            r=lora_cfg.r,
            lora_alpha=lora_cfg.alpha,
            target_modules=list(lora_cfg.target_modules),
            lora_dropout=lora_cfg.dropout,
            bias=lora_cfg.bias,
            task_type=lora_cfg.task_type,
        )
        model = get_peft_model(model, peft_cfg)
        model.print_trainable_parameters()

        # Format function: convert dict records to ChatML strings
        def formatting_func(examples):
            texts = []
            for i in range(len(examples["user"])):
                sys = examples.get("system", [self._system] * len(examples["user"]))[i]
                user = examples["user"][i]
                asst = examples["assistant"][i]
                texts.append(
                    f"<|im_start|>system\n{sys}<|im_end|>\n"
                    f"<|im_start|>user\n{user}<|im_end|>\n"
                    f"<|im_start|>assistant\n{asst}<|im_end|>"
                )
            return texts

        # Training arguments
        out_path = Path(cfg.output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        training_args = TrainingArguments(
            output_dir=str(out_path),
            num_train_epochs=cfg.num_train_epochs,
            per_device_train_batch_size=cfg.per_device_train_batch_size,
            gradient_accumulation_steps=cfg.gradient_accumulation_steps,
            learning_rate=cfg.learning_rate,
            lr_scheduler_type=cfg.lr_scheduler_type,
            warmup_ratio=cfg.warmup_ratio,
            fp16=cfg.fp16,
            bf16=cfg.bf16,
            save_steps=cfg.save_steps,
            logging_steps=cfg.logging_steps,
            seed=cfg.seed,
            report_to="none",
            push_to_hub=False,  # never auto-push
        )

        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=dataset,
            eval_dataset=eval_dataset,
            max_seq_length=cfg.max_seq_length,
            formatting_func=formatting_func,
            args=training_args,
        )

        trainer.train()

        # Save final adapter
        final_dir = out_path / "final_adapter"
        trainer.model.save_pretrained(str(final_dir))
        tokenizer.save_pretrained(str(final_dir))
        self._save_metadata(final_dir)
        return final_dir

    def _save_metadata(self, adapter_dir: Path) -> None:
        """Write training metadata alongside the adapter weights."""
        meta = {
            "base_model": self.cfg.base_model,
            "lora_r": self.cfg.lora.r,
            "lora_alpha": self.cfg.lora.alpha,
            "target_modules": list(self.cfg.lora.target_modules),
            "max_seq_length": self.cfg.max_seq_length,
            "aria_version": "1.0",
        }
        (adapter_dir / "aria_lm_meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False)
        )

    @staticmethod
    def _check_deps() -> None:
        missing = []
        for pkg in ("transformers", "peft", "trl", "bitsandbytes"):
            try:
                __import__(pkg)
            except ImportError:
                missing.append(pkg)
        if missing:
            raise ImportError(
                f"LoRA fine-tuning requires: {', '.join(missing)}.\n"
                f"  pip install transformers>=4.40 peft>=0.10 bitsandbytes>=0.43 trl"
            )

    @property
    def _system(self) -> str:
        from .corpus_builder import _SYSTEM_PROMPT
        return _SYSTEM_PROMPT
