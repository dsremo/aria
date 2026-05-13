"""Drop-in LLMBackend that serves a locally fine-tuned LoRA adapter.

Plugs into ``aria.cognitive.engine.CognitiveEngine`` as a drop-in replacement
for ``CloudLlmBackend`` when the spacecraft has no internet access.

Usage::

    from aria.cognitive.engine import CognitiveEngine
    from aria.cognitive.fine_tuning.local_backend import LocalModelBackend

    backend = LocalModelBackend("/data/aria_lm/final_adapter")
    engine = CognitiveEngine(llm_backend=backend)
    result = await engine.process(context, query)

The backend performs greedy decoding (temperature=0, max_new_tokens=512) by
default.  Pass ``generation_kwargs`` to override (e.g. beam search, sampling).

Dependencies: transformers>=4.40, peft>=0.10 (optional: bitsandbytes for 4-bit)
"""
from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class LocalModelConfig:
    """Configuration for the local inference backend."""
    adapter_path: str             # Path to final_adapter/ directory
    load_in_4bit: bool = True     # QLoRA quantisation (halves VRAM requirement)
    device_map: str = "auto"      # "auto" selects GPU if available, else CPU
    max_new_tokens: int = 512
    temperature: float = 0.0      # 0 = greedy decode (deterministic)
    repetition_penalty: float = 1.1
    do_sample: bool = False


class LocalModelBackend:
    """Serves a LoRA fine-tuned causal LM as an LLMBackend for CognitiveEngine.

    The model is loaded lazily on first use to avoid startup cost.  Inference
    is synchronous (wraps in asyncio.to_thread for async callers).

    Args:
        adapter_path: Directory containing the PEFT adapter weights and
                      tokenizer.  Must contain ``adapter_config.json``
                      (written by ``LoRAFineTuner.train()``).
        config:       Optional full LocalModelConfig.
    """

    def __init__(
        self,
        adapter_path: str | Path,
        config: Optional[LocalModelConfig] = None,
    ) -> None:
        self.cfg = config or LocalModelConfig(adapter_path=str(adapter_path))
        self.cfg.adapter_path = str(adapter_path)
        self._model = None
        self._tokenizer = None
        self._meta: dict[str, Any] = self._load_meta()

    # ── LLMBackend protocol ────────────────────────────────────────────────────

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: Optional[list[dict]] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a response for a ChatML message list.

        Args:
            messages: List of dicts with ``role`` and ``content`` keys.
                      Roles: "system", "user", "assistant".
            tools:    Ignored — local model does not support tool-use.
                      A warning is emitted if tools are passed.

        Returns:
            Dict with ``content`` (str) and ``tool_calls`` (empty list).
        """
        if tools:
            warnings.warn(
                "LocalModelBackend: tool_use not supported by local LM. "
                "Falling back to text-only response.",
                RuntimeWarning,
                stacklevel=2,
            )

        prompt = self._messages_to_chatml(messages)
        response_text = await self._async_generate(prompt, **kwargs)
        return {"content": response_text, "tool_calls": []}

    def is_available(self) -> bool:
        """Return True if model weights exist and transformers is installed."""
        try:
            import transformers  # noqa: F401
            import peft  # noqa: F401
        except ImportError:
            return False
        adapter_dir = Path(self.cfg.adapter_path)
        return (adapter_dir / "adapter_config.json").exists()

    # ── Inference ──────────────────────────────────────────────────────────────

    async def _async_generate(self, prompt: str, **kwargs: Any) -> str:
        import asyncio
        return await asyncio.to_thread(self._generate_sync, prompt, **kwargs)

    def _generate_sync(self, prompt: str, **kwargs: Any) -> str:
        import torch
        model, tokenizer = self._load_model()
        inputs = tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=2048,
        ).to(model.device)

        gen_cfg = self.cfg
        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=gen_cfg.max_new_tokens,
                temperature=gen_cfg.temperature if gen_cfg.do_sample else 1.0,
                do_sample=gen_cfg.do_sample,
                repetition_penalty=gen_cfg.repetition_penalty,
                pad_token_id=tokenizer.eos_token_id,
                **kwargs,
            )

        # Decode only the newly generated tokens
        new_tokens = output_ids[0][inputs["input_ids"].shape[1]:]
        return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    def _load_model(self):
        """Lazy load model + tokenizer on first call."""
        if self._model is not None:
            return self._model, self._tokenizer

        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        base_model_id = self._meta.get("base_model")
        if not base_model_id:
            raise ValueError(
                f"aria_lm_meta.json missing 'base_model' key in {self.cfg.adapter_path}"
            )

        bnb_config = None
        if self.cfg.load_in_4bit:
            try:
                import bitsandbytes  # noqa: F401
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=torch.bfloat16,
                )
            except ImportError:
                warnings.warn(
                    "bitsandbytes not installed — loading full-precision model.",
                    RuntimeWarning,
                    stacklevel=3,
                )

        # Pin model revision to a known-good commit when the operator has
        # configured one — defends against XZ/Polyfill-style supply-chain
        # swaps where a maintainer pushes a hostile build to HEAD.
        revision = (
            self._meta.get("base_model_revision")
            or os.environ.get("ARIA_HF_BASE_REVISION")
            or None
        )
        if revision is None:
            warnings.warn(
                f"Loading {base_model_id!r} from HF Hub WITHOUT a pinned "
                "revision. Set 'base_model_revision' in aria_lm_meta.json "
                "or ARIA_HF_BASE_REVISION env var to lock to a commit SHA.",
                RuntimeWarning, stacklevel=3,
            )

        base = AutoModelForCausalLM.from_pretrained(
            base_model_id,
            quantization_config=bnb_config,
            device_map=self.cfg.device_map,
            trust_remote_code=False,           # CVE class — never auto-exec repo code
            revision=revision,
        )
        self._model = PeftModel.from_pretrained(base, self.cfg.adapter_path)
        self._model.eval()

        # nosec B615 (adapter_path is a local filesystem path, not an HF id —
        # revision pinning does not apply; the local artefact's integrity is
        # verified separately via the operator's release-management process).
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.cfg.adapter_path, trust_remote_code=False,  # nosec B615
        )
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        return self._model, self._tokenizer

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _load_meta(self) -> dict[str, Any]:
        meta_path = Path(self.cfg.adapter_path) / "aria_lm_meta.json"
        if meta_path.exists():
            try:
                return json.loads(meta_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    @staticmethod
    def _messages_to_chatml(messages: list[dict[str, str]]) -> str:
        """Convert OpenAI-style messages list to a ChatML-formatted prompt string."""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)

    def __repr__(self) -> str:
        base = self._meta.get("base_model", "unknown")
        return f"LocalModelBackend(base_model={base!r}, path={self.cfg.adapter_path!r})"
