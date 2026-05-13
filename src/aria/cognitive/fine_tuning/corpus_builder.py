"""Training-corpus builder for ARIA mission corpora.

Converts heterogeneous sources into ``(system, user, assistant)`` instruction
triples for supervised fine-tuning.  Sources supported:

* RAG JSON cache (``~/.aria/rag_cache/records.json``) — each record becomes
  Q&A pairs about its abstract / title / year / authors.
* ARIA simulation decision logs — (context_snapshot, decision, rationale) triples.
* Plain-text manuals / procedures — paragraph-level Q&A via extraction heuristics.
* CSV/JSONL datasets — arbitrary JSON lines with ``instruction`` / ``output`` keys.

No ML dependencies required to build the dataset; only standard-library + numpy.
HuggingFace ``datasets`` is used only if installed (upgrades to Arrow format).
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import textwrap
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_SYSTEM_PROMPT = (
    "You are ARIA, the Adaptive Response and Intelligence Architecture for "
    "long-duration space missions. You have deep expertise in spacecraft systems, "
    "crew health, orbital mechanics, radiation physics, and mission operations. "
    "Answer accurately, cite sources when known, and acknowledge uncertainty."
)

_RAG_CACHE_DEFAULT = Path.home() / ".aria" / "rag_cache" / "records.json"


@dataclass
class TrainingExample:
    """One instruction-following training sample."""
    system: str
    user: str
    assistant: str
    source_tag: str = ""
    uid: str = field(default="", init=False)

    def __post_init__(self) -> None:
        raw = f"{self.system}|{self.user}|{self.assistant}"
        self.uid = hashlib.sha256(raw.encode()).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "system": self.system,
            "user": self.user,
            "assistant": self.assistant,
            "source_tag": self.source_tag,
        }

    def to_chatml(self) -> str:
        """Format as ChatML string for tokenizer templates."""
        return (
            f"<|im_start|>system\n{self.system}<|im_end|>\n"
            f"<|im_start|>user\n{self.user}<|im_end|>\n"
            f"<|im_start|>assistant\n{self.assistant}<|im_end|>"
        )


class CorpusBuilder:
    """Aggregate training examples from multiple mission-corpora sources.

    Args:
        system_prompt: Default system prompt for all examples.
                       Override per-source via keyword args.
        dedup: Remove examples with identical (user, assistant) hashes.
    """

    def __init__(
        self,
        system_prompt: str = _SYSTEM_PROMPT,
        dedup: bool = True,
    ) -> None:
        self._system = system_prompt
        self._dedup = dedup
        self._examples: list[TrainingExample] = []
        self._seen_uids: set[str] = set()

    # ── Public add methods ─────────────────────────────────────────────────────

    def add_ntrs_cache(self, cache_path: Optional[Path] = None) -> int:
        """Ingest the RAG JSON cache and generate Q&A training pairs.

        Each NTRS record generates up to 4 pairs:
        - "What does [title] conclude?" → abstract excerpt
        - "Who wrote [title]?" → author list
        - "What year was [title] published?" → year
        - "Summarise [title] for mission planning." → abstract

        Returns number of examples added.
        """
        path = cache_path or _RAG_CACHE_DEFAULT
        if not path.exists():
            warnings.warn(f"RAG cache not found at {path}. Run RagPipeline.save_cache() first.")
            return 0

        payload = json.loads(path.read_text())
        n_added = 0
        for rid, meta in payload.items():
            title = meta.get("title") or rid
            abstract = meta.get("abstract", "").strip()
            authors = meta.get("authors") or []
            year = meta.get("year") or "unknown"
            url = meta.get("document_url", "")

            if abstract:
                # Main Q&A pair
                n_added += self._add(TrainingExample(
                    system=self._system,
                    user=f"What are the key findings of the NTRS paper titled '{title}'?",
                    assistant=abstract[:800] + (
                        f"\n\nSource: {url}" if url else ""
                    ),
                    source_tag="ntrs_cache",
                ))
                # Mission planning summary
                n_added += self._add(TrainingExample(
                    system=self._system,
                    user=(
                        f"Summarise '{title}' for mission planning purposes "
                        f"in 2-3 sentences."
                    ),
                    assistant=self._summarise_abstract(abstract),
                    source_tag="ntrs_cache",
                ))

            if authors:
                n_added += self._add(TrainingExample(
                    system=self._system,
                    user=f"Who authored the paper '{title}'?",
                    assistant=(
                        ", ".join(authors[:5])
                        + (f" et al." if len(authors) > 5 else "")
                        + (f" ({year})" if year else "")
                    ),
                    source_tag="ntrs_cache",
                ))

        return n_added

    def add_simulation_log(self, log_path: Path) -> int:
        """Ingest an ARIA decision-log JSON file.

        Expected format (one JSON object per line)::

            {"timestamp": "...", "context": {...}, "decision": "...", "rationale": "..."}

        Returns number of examples added.
        """
        if not log_path.exists():
            warnings.warn(f"Log not found: {log_path}")
            return 0
        n_added = 0
        with log_path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                context_str = json.dumps(rec.get("context", {}), indent=2)
                decision = str(rec.get("decision", ""))
                rationale = str(rec.get("rationale", ""))
                if not decision:
                    continue
                n_added += self._add(TrainingExample(
                    system=self._system,
                    user=(
                        "Given the following spacecraft state snapshot, what is "
                        "the recommended action and reasoning?\n\n"
                        f"```json\n{context_str[:1000]}\n```"
                    ),
                    assistant=(
                        f"**Recommended action**: {decision}\n\n"
                        f"**Reasoning**: {rationale}"
                    ),
                    source_tag=f"sim_log:{log_path.name}",
                ))
        return n_added

    def add_manual(
        self,
        path: Path,
        source_tag: str = "manual",
        max_chunk_chars: int = 800,
    ) -> int:
        """Ingest a plain-text procedure manual or technical document.

        Splits on double-newlines (paragraphs) and generates:
        - "What does this section describe?" → paragraph text
        - Question extracted from heading lines (e.g. "## 4.2 EVA Pre-Breathe")
          → next paragraph as answer.

        Returns number of examples added.
        """
        p = Path(path)
        if not p.exists():
            warnings.warn(f"Manual not found: {p}")
            return 0
        text = p.read_text(errors="replace")
        paragraphs = [pg.strip() for pg in re.split(r"\n{2,}", text) if pg.strip()]
        n_added = 0

        heading_re = re.compile(r"^#{1,4}\s+(.+)$")
        for i, para in enumerate(paragraphs):
            if len(para) < 30:
                continue
            # Truncate very long paragraphs
            body = para[:max_chunk_chars]
            m = heading_re.match(para)
            if m:
                # This is a heading — pair with next paragraph if available
                heading_text = m.group(1).strip()
                if i + 1 < len(paragraphs):
                    answer = paragraphs[i + 1][:max_chunk_chars]
                    n_added += self._add(TrainingExample(
                        system=self._system,
                        user=f"Explain the '{heading_text}' section from the mission manual.",
                        assistant=answer,
                        source_tag=source_tag,
                    ))
            else:
                n_added += self._add(TrainingExample(
                    system=self._system,
                    user="What is described in the following mission document section?",
                    assistant=body,
                    source_tag=source_tag,
                ))
        return n_added

    def add_jsonl(self, path: Path, source_tag: str = "jsonl") -> int:
        """Ingest a JSONL file with ``instruction`` / ``output`` (or ``input``) keys.

        Compatible with Alpaca-format and ShareGPT-format datasets.
        For ShareGPT (``conversations`` list), extracts human/gpt pairs.

        Returns number of examples added.
        """
        p = Path(path)
        if not p.exists():
            warnings.warn(f"JSONL not found: {p}")
            return 0
        n_added = 0
        with p.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Alpaca format
                if "instruction" in rec and "output" in rec:
                    n_added += self._add(TrainingExample(
                        system=self._system,
                        user=rec["instruction"] + (
                            "\n\n" + rec["input"] if rec.get("input") else ""
                        ),
                        assistant=rec["output"],
                        source_tag=source_tag,
                    ))
                # ShareGPT format
                elif "conversations" in rec:
                    convs = rec["conversations"]
                    for j in range(0, len(convs) - 1, 2):
                        human = convs[j]
                        gpt = convs[j + 1] if j + 1 < len(convs) else None
                        if not gpt:
                            continue
                        user_val = human.get("value", "")
                        asst_val = gpt.get("value", "")
                        if user_val and asst_val:
                            n_added += self._add(TrainingExample(
                                system=self._system,
                                user=user_val,
                                assistant=asst_val,
                                source_tag=source_tag,
                            ))
        return n_added

    # ── Build output ───────────────────────────────────────────────────────────

    def build_dataset(self) -> list[dict[str, Any]]:
        """Return all examples as a list of dicts."""
        return [ex.to_dict() for ex in self._examples]

    def save_jsonl(self, path: Path) -> int:
        """Save examples to a JSONL file, one example per line.

        Returns number of examples written.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as fh:
            for ex in self._examples:
                fh.write(json.dumps(ex.to_dict(), ensure_ascii=False) + "\n")
        return len(self._examples)

    def to_hf_dataset(self):
        """Convert to a HuggingFace ``datasets.Dataset`` (requires ``datasets``)."""
        try:
            from datasets import Dataset  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "HuggingFace `datasets` not installed. pip install datasets"
            ) from exc
        return Dataset.from_list(self.build_dataset())

    def __len__(self) -> int:
        return len(self._examples)

    def stats(self) -> dict[str, Any]:
        """Summary statistics for the corpus."""
        tags: dict[str, int] = {}
        total_chars = 0
        for ex in self._examples:
            tags[ex.source_tag] = tags.get(ex.source_tag, 0) + 1
            total_chars += len(ex.user) + len(ex.assistant)
        return {
            "total_examples": len(self._examples),
            "sources": tags,
            "mean_chars": total_chars / max(len(self._examples), 1),
        }

    # ── Private ────────────────────────────────────────────────────────────────

    def _add(self, ex: TrainingExample) -> int:
        if self._dedup and ex.uid in self._seen_uids:
            return 0
        self._seen_uids.add(ex.uid)
        self._examples.append(ex)
        return 1

    @staticmethod
    def _summarise_abstract(abstract: str, max_sentences: int = 3) -> str:
        """Return first max_sentences of abstract as a mission-planning summary."""
        sentences = re.split(r"(?<=[.!?])\s+", abstract.strip())
        return " ".join(sentences[:max_sentences])
