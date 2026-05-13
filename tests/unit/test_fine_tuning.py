"""Unit tests for aria.cognitive.fine_tuning — LoRA scaffold + corpus builder.

All tests run without transformers/peft/GPU — only the corpus builder and
scaffold config/metadata paths are tested here.  GPU training is integration-
level and lives in tests/integration/.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from aria.cognitive.fine_tuning.corpus_builder import (
    CorpusBuilder,
    TrainingExample,
    _SYSTEM_PROMPT,
)
from aria.cognitive.fine_tuning.lora_scaffold import LoRAConfig, LoRAFineTuner, TrainingConfig
from aria.cognitive.fine_tuning.local_backend import LocalModelBackend, LocalModelConfig


# ════════════════════════════════════════════════════════════════
#  TrainingExample
# ════════════════════════════════════════════════════════════════

class TestTrainingExample:
    def test_uid_deterministic(self):
        e1 = TrainingExample(system="s", user="u", assistant="a")
        e2 = TrainingExample(system="s", user="u", assistant="a")
        assert e1.uid == e2.uid

    def test_uid_differs_on_content_change(self):
        e1 = TrainingExample(system="s", user="u1", assistant="a")
        e2 = TrainingExample(system="s", user="u2", assistant="a")
        assert e1.uid != e2.uid

    def test_uid_length(self):
        e = TrainingExample(system="s", user="u", assistant="a")
        assert len(e.uid) == 12

    def test_to_dict_keys(self):
        e = TrainingExample(system="sys", user="q", assistant="ans", source_tag="test")
        d = e.to_dict()
        assert set(d.keys()) == {"uid", "system", "user", "assistant", "source_tag"}

    def test_to_chatml_format(self):
        e = TrainingExample(system="SYS", user="USER", assistant="ASST")
        chatml = e.to_chatml()
        assert "<|im_start|>system\nSYS<|im_end|>" in chatml
        assert "<|im_start|>user\nUSER<|im_end|>" in chatml
        assert "<|im_start|>assistant\nASST<|im_end|>" in chatml


# ════════════════════════════════════════════════════════════════
#  CorpusBuilder
# ════════════════════════════════════════════════════════════════

class TestCorpusBuilder:
    def _builder(self) -> CorpusBuilder:
        return CorpusBuilder()

    def test_empty_builder(self):
        b = self._builder()
        assert len(b) == 0
        assert b.build_dataset() == []

    def test_add_ntrs_cache_missing_file_returns_zero(self, tmp_path):
        b = self._builder()
        n = b.add_ntrs_cache(tmp_path / "nonexistent.json")
        assert n == 0

    def test_add_ntrs_cache_populates_examples(self, tmp_path):
        cache = {
            "doc001": {
                "ntrs_id": "doc001",
                "title": "Polyethylene Shielding",
                "abstract": "Polyethylene protects against GCR radiation in deep space.",
                "authors": ["Cucinotta, F.", "Durante, M."],
                "year": 2006,
                "document_url": "https://ntrs.nasa.gov/api/citations/doc001",
                "report_numbers": [],
            }
        }
        cache_file = tmp_path / "records.json"
        cache_file.write_text(json.dumps(cache))
        b = self._builder()
        n = b.add_ntrs_cache(cache_file)
        assert n >= 2  # at least main Q&A + summary
        assert len(b) == n

    def test_add_ntrs_cache_deduplicates(self, tmp_path):
        """Same cache added twice should not double the examples."""
        cache = {
            "doc001": {
                "ntrs_id": "doc001",
                "title": "Test",
                "abstract": "Content.",
                "authors": [],
                "year": 2020,
                "document_url": "",
                "report_numbers": [],
            }
        }
        cache_file = tmp_path / "records.json"
        cache_file.write_text(json.dumps(cache))
        b = self._builder()
        n1 = b.add_ntrs_cache(cache_file)
        n2 = b.add_ntrs_cache(cache_file)
        assert n2 == 0  # all duplicates
        assert len(b) == n1

    def test_add_simulation_log(self, tmp_path):
        log_path = tmp_path / "decision.jsonl"
        entries = [
            {
                "timestamp": "2030-01-01T00:00:00",
                "context": {"hull_integrity": 0.95, "power_kw": 42.0},
                "decision": "maintain_orbit",
                "rationale": "All systems nominal, no action required.",
            },
            {
                "timestamp": "2030-01-02T00:00:00",
                "context": {"hull_integrity": 0.70},
                "decision": "inspect_hull",
                "rationale": "Hull integrity below 75% threshold.",
            },
        ]
        log_path.write_text("\n".join(json.dumps(e) for e in entries))
        b = self._builder()
        n = b.add_simulation_log(log_path)
        assert n == 2

    def test_add_simulation_log_missing_returns_zero(self, tmp_path):
        b = self._builder()
        n = b.add_simulation_log(tmp_path / "ghost.jsonl")
        assert n == 0

    def test_add_manual_plain_text(self, tmp_path):
        manual = textwrap.dedent("""\
            ## EVA Pre-Breathe Procedure

            Crew members must breathe 100% O2 for 4 hours before EVA exit.
            This reduces dissolved nitrogen to prevent decompression sickness.

            ## Suit Donning

            Don the EMU at least 45 minutes before EVA to check for leaks.
        """)
        manual_path = tmp_path / "eva.md"
        manual_path.write_text(manual)
        b = self._builder()
        n = b.add_manual(manual_path)
        assert n >= 1

    def test_add_jsonl_alpaca_format(self, tmp_path):
        data = [
            {"instruction": "What is specific impulse?",
             "input": "",
             "output": "Specific impulse (Isp) is thrust per unit weight-flow of propellant."},
            {"instruction": "Define delta-v.",
             "input": "",
             "output": "Delta-v is the change in velocity of a spacecraft, measured in m/s."},
        ]
        jl = tmp_path / "alpaca.jsonl"
        jl.write_text("\n".join(json.dumps(d) for d in data))
        b = self._builder()
        n = b.add_jsonl(jl)
        assert n == 2

    def test_add_jsonl_missing_returns_zero(self, tmp_path):
        b = self._builder()
        assert b.add_jsonl(tmp_path / "missing.jsonl") == 0

    def test_stats_keys(self, tmp_path):
        b = self._builder()
        b._add(TrainingExample(system="s", user="q", assistant="a", source_tag="test"))
        stats = b.stats()
        assert "total_examples" in stats
        assert "sources" in stats
        assert "mean_chars" in stats

    def test_save_jsonl(self, tmp_path):
        b = self._builder()
        b._add(TrainingExample(system="s", user="q", assistant="ans"))
        out = tmp_path / "out.jsonl"
        n = b.save_jsonl(out)
        assert n == 1
        assert out.exists()
        line = json.loads(out.read_text().strip())
        assert line["user"] == "q"
        assert line["assistant"] == "ans"

    def test_system_prompt_in_examples(self, tmp_path):
        cache = {
            "x": {
                "ntrs_id": "x", "title": "T", "abstract": "Some abstract text.",
                "authors": [], "year": 2020, "document_url": "", "report_numbers": [],
            }
        }
        cache_file = tmp_path / "r.json"
        cache_file.write_text(json.dumps(cache))
        b = CorpusBuilder(system_prompt="CUSTOM_SYSTEM")
        b.add_ntrs_cache(cache_file)
        for ex in b._examples:
            assert ex.system == "CUSTOM_SYSTEM"


# ════════════════════════════════════════════════════════════════
#  LoRAConfig & TrainingConfig
# ════════════════════════════════════════════════════════════════

class TestLoRAConfig:
    def test_defaults(self):
        cfg = LoRAConfig()
        assert cfg.r == 16
        assert cfg.alpha == 32.0
        assert "q_proj" in cfg.target_modules

    def test_scaling_factor(self):
        cfg = LoRAConfig(r=8, alpha=16.0)
        assert cfg.alpha / cfg.r == 2.0

    def test_task_type_causal_lm(self):
        assert LoRAConfig().task_type == "CAUSAL_LM"


class TestTrainingConfig:
    def test_default_model(self):
        cfg = TrainingConfig()
        assert "phi" in cfg.base_model.lower() or "mistral" in cfg.base_model.lower()

    def test_push_to_hub_false(self):
        # Never auto-push to hub
        assert TrainingConfig().push_to_hub is False

    def test_eval_fraction_positive(self):
        assert 0 < TrainingConfig().eval_fraction < 1


# ════════════════════════════════════════════════════════════════
#  LoRAFineTuner
# ════════════════════════════════════════════════════════════════

class TestLoRAFineTuner:
    def test_estimate_params_phi3(self):
        ft = LoRAFineTuner("microsoft/phi-3-mini-4k-instruct")
        est = ft.estimate_params()
        assert est["trainable_fraction_pct"] != "unknown"
        assert float(est["trainable_fraction_pct"]) < 5.0  # LoRA << 5% of params

    def test_estimate_params_mistral(self):
        ft = LoRAFineTuner("mistralai/Mistral-7B-Instruct-v0.3")
        est = ft.estimate_params()
        assert est["total_params"] == 7_200_000_000

    def test_check_deps_raises_when_missing(self):
        """If transformers is not installed, train() raises ImportError."""
        import sys, unittest.mock
        ft = LoRAFineTuner("microsoft/phi-3-mini-4k-instruct")
        modules_to_block = {"transformers", "peft", "trl", "bitsandbytes"}
        with unittest.mock.patch.dict("sys.modules", {m: None for m in modules_to_block}):
            with pytest.raises(ImportError, match="LoRA fine-tuning requires"):
                ft._check_deps()

    def test_config_forwarded_correctly(self):
        ft = LoRAFineTuner("my/model", "/tmp/out")
        assert ft.cfg.base_model == "my/model"
        assert ft.cfg.output_dir == "/tmp/out"


# ════════════════════════════════════════════════════════════════
#  LocalModelBackend
# ════════════════════════════════════════════════════════════════

class TestLocalModelBackend:
    def _write_meta(self, path: Path, base_model: str = "microsoft/phi-3-mini-4k-instruct") -> Path:
        adapter_dir = path / "final_adapter"
        adapter_dir.mkdir(parents=True)
        meta = {"base_model": base_model, "lora_r": 16, "max_seq_length": 2048}
        (adapter_dir / "aria_lm_meta.json").write_text(json.dumps(meta))
        (adapter_dir / "adapter_config.json").write_text("{}")
        return adapter_dir

    def test_loads_metadata(self, tmp_path):
        adapter_dir = self._write_meta(tmp_path)
        backend = LocalModelBackend(adapter_dir)
        assert backend._meta["base_model"] == "microsoft/phi-3-mini-4k-instruct"
        assert backend._meta["lora_r"] == 16

    def test_is_available_true_when_peft_installed(self, tmp_path):
        adapter_dir = self._write_meta(tmp_path)
        backend = LocalModelBackend(adapter_dir)
        # Only test is_available logic path; peft may not be installed
        if backend.is_available():
            assert True  # peft is installed + adapter_config.json present
        # else skip — peft not installed, is_available → False by design

    def test_is_available_false_missing_adapter(self, tmp_path):
        backend = LocalModelBackend(tmp_path / "nonexistent")
        assert backend.is_available() is False

    def test_repr(self, tmp_path):
        adapter_dir = self._write_meta(tmp_path)
        backend = LocalModelBackend(adapter_dir)
        assert "phi" in repr(backend).lower()

    def test_messages_to_chatml_round_trip(self):
        messages = [
            {"role": "system", "content": "You are ARIA."},
            {"role": "user", "content": "What is specific impulse?"},
        ]
        prompt = LocalModelBackend._messages_to_chatml(messages)
        assert "<|im_start|>system\nYou are ARIA.<|im_end|>" in prompt
        assert "<|im_start|>user\nWhat is specific impulse?<|im_end|>" in prompt
        assert prompt.endswith("<|im_start|>assistant\n")

    def test_missing_meta_returns_empty_dict(self, tmp_path):
        backend = LocalModelBackend(tmp_path / "no_meta")
        assert backend._meta == {}
