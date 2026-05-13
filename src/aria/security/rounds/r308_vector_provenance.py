"""R308 — Vector-store / embeddings provenance ledger.

Threat: a vector store backing a RAG index accumulates documents
from many sources; without per-vector provenance the operator can't
audit which source poisoned a given retrieval.  PoisonedRAG (USENIX
2024) abused this directly.

Defence: ``record_insertion`` stores (vector_id, source_uri,
content_sha256, embedded_at, embedder_model_id, signed_by) tuples in
a tamper-evident chain so the provenance can be replayed at retrieval
time.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _VectorProvenance:
    vector_id: str
    source_uri: str
    content_sha256: str
    embedded_at: float
    embedder_model_id: str
    prev_chain_hash: str
    chain_hash: str = ""


_LEDGER: List[_VectorProvenance] = []
_LOCK = threading.Lock()


def record_insertion(
    *, vector_id: str, source_uri: str, content_blob: bytes,
    embedder_model_id: str,
) -> _VectorProvenance:
    sha = hashlib.sha256(content_blob or b"").hexdigest()
    with _LOCK:
        prev = _LEDGER[-1].chain_hash if _LEDGER else ("0" * 64)
        record = _VectorProvenance(
            vector_id=vector_id, source_uri=source_uri,
            content_sha256=sha, embedded_at=time.time(),
            embedder_model_id=embedder_model_id, prev_chain_hash=prev,
        )
        canonical = f"{vector_id}|{source_uri}|{sha}|{embedder_model_id}|{prev}".encode()
        record.chain_hash = hashlib.sha256(canonical).hexdigest()
        _LEDGER.append(record)
    return record


def lookup(vector_id: str) -> _VectorProvenance:
    with _LOCK:
        for r in reversed(_LEDGER):
            if r.vector_id == vector_id:
                return r
    return None


def verify_chain() -> Tuple[bool, int]:
    with _LOCK:
        ledger = list(_LEDGER)
    prev = "0" * 64
    for i, r in enumerate(ledger):
        canonical = f"{r.vector_id}|{r.source_uri}|{r.content_sha256}|{r.embedder_model_id}|{prev}".encode()
        recomputed = hashlib.sha256(canonical).hexdigest()
        if recomputed != r.chain_hash or r.prev_chain_hash != prev:
            return False, i
        prev = r.chain_hash
    return True, len(ledger)


def quarantine_source(source_uri: str) -> List[str]:
    with _LOCK:
        return [r.vector_id for r in _LEDGER if r.source_uri == source_uri]


def reset_for_tests() -> None:
    with _LOCK:
        _LEDGER.clear()


register(DefencePlugin(
    round_id="R308",
    name="vector_provenance",
    description="Vector-store provenance ledger; per-vector source + hash + chain.",
))
