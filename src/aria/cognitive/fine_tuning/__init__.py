"""LoRA fine-tuning scaffold for ARIA's on-ship language model.

OFFLINE / GROUND-STATION USE ONLY (Wiring audit Pass 3 F14.12).
================================================================
This subpackage is NOT loaded at flight runtime. None of its
classes are constructed by the cognitive engine, the coordinator,
or any agent. The only callers are offline ground-station tooling
that prepares a domain-adapted local LLM for deep-space deployment.

Constraints:
  - Do NOT import from this subpackage in any flight code path.
  - Production deploys SHOULD exclude this directory from PCR-8
    package-tree hashing (``attestation._hash_tree(aria_pkg_root)``)
    so changes to fine-tuning code do not trigger CIM-mismatch
    alerts at flight runtime.
  - Future refactor: relocate this entire subpackage to
    ``tools/offline/fine_tuning/`` so the package-tree hash naturally
    excludes it. Tracked in the Sprint Backlog (F14.12 MOVE).

The cognitive engine uses a cloud LLM (the LLM) during development.
For deep-space missions with no internet access, a domain-adapted local model
is required.  This package provides:

1. ``CorpusBuilder``    — collect + format training data from NTRS/RAG/sim logs
2. ``LoRAFineTuner``    — fine-tune any causal LM with LoRA (HuggingFace PEFT)
3. ``LocalModelBackend`` — drop-in LLMBackend that serves the fine-tuned model

Typical offline workflow::

    # 1. Build corpus
    builder = CorpusBuilder()
    builder.add_ntrs_cache()          # RAG JSON cache → instruction pairs
    builder.add_simulation_log()      # sim decision logs → Q&A pairs
    builder.add_manual("ECLSS_BVAD.txt", source_tag="NASA-BVAD")
    dataset = builder.build_dataset()

    # 2. Fine-tune
    ft = LoRAFineTuner("microsoft/phi-3-mini-4k-instruct", output_dir="/data/aria_lm")
    ft.train(dataset)

    # 3. Deploy via cognitive engine
    from aria.cognitive.engine import CognitiveEngine
    backend = LocalModelBackend("/data/aria_lm")
    engine = CognitiveEngine(llm_backend=backend)
"""
from .corpus_builder import CorpusBuilder, TrainingExample
from .lora_scaffold import LoRAFineTuner, LoRAConfig, TrainingConfig
from .local_backend import LocalModelBackend

__all__ = [
    "CorpusBuilder",
    "TrainingExample",
    "LoRAFineTuner",
    "LoRAConfig",
    "TrainingConfig",
    "LocalModelBackend",
]
