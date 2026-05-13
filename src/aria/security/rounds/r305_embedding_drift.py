"""R305 — Embedding-model drift detector.

Threat: a swapped embedding model (silently upgraded, or attacker-
poisoned via supply chain) produces subtly different vectors — RAG
retrieval shifts, vector-DB lookups misroute, downstream models see
distribution drift.  Hard to notice without per-vector baseline.

Defence: maintain a small fingerprint corpus (10-50 sentinel
strings) and their reference vectors.  ``check_drift`` re-embeds the
sentinels with the current model and compares cosine; > 1% drift
triggers alarm.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Baseline:
    sentinels: Dict[str, List[float]] = field(default_factory=dict)


_BASELINE: _Baseline = _Baseline()
_LOCK = threading.Lock()


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-12
    nb = math.sqrt(sum(y * y for y in b)) or 1e-12
    return dot / (na * nb)


def install_baseline(sentinels: Dict[str, List[float]]) -> None:
    with _LOCK:
        _BASELINE.sentinels = {k: list(v) for k, v in sentinels.items()}


def check_drift(
    embed_fn: Callable[[str], List[float]],
    *,
    threshold: float = 0.99,
) -> Tuple[float, List[str]]:
    """Returns (min_cosine, drifted_sentinels).  threshold=0.99 ⇒ 1% drift."""
    with _LOCK:
        baseline = dict(_BASELINE.sentinels)
    if not baseline:
        return 1.0, ["no_baseline"]
    cosines: List[float] = []
    drifted: List[str] = []
    for sentinel, ref in baseline.items():
        try:
            current = embed_fn(sentinel)
        except Exception as exc:
            drifted.append(f"{sentinel[:32]}:embed_error:{exc}")
            continue
        c = cosine(current, ref)
        cosines.append(c)
        if c < threshold:
            drifted.append(f"{sentinel[:32]}:cos={c:.4f}")
    return (min(cosines) if cosines else 0.0), drifted


def reset_for_tests() -> None:
    with _LOCK:
        _BASELINE.sentinels.clear()


register(DefencePlugin(
    round_id="R305",
    name="embedding_drift",
    description="Sentinel-corpus embedding-model drift detector via cosine baseline.",
))
