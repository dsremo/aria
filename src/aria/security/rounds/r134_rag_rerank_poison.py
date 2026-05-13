"""R134 — RAG re-ranker poisoning.

Threat: the retrieval pipeline pulls k=20 docs, the re-ranker selects
top-3 for the prompt.  A poisoned doc with a high-relevance shape
(verbatim quote of the user query) climbs to top-1 even when its
content is hostile.  Liu et al. 2024 (PoisonedRAG) + the 2025 ICLR
paper "Re-Rank, Then Realign" both demonstrate this at scale.

Defence: `rerank_score_audit(docs)` flags re-ranker outputs that pass
all of: top doc has > 0.95 cosine similarity, top doc length < 256
chars, top doc body classifies as influence/jailbreak.  When all
three hold, `top doc is suspicious` — caller drops it from the
final prompt and falls back to top-2.
"""

from __future__ import annotations

from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


def is_suspicious_top(
    doc_body: str,
    *,
    similarity: float,
) -> Tuple[bool, str]:
    if similarity < 0.95:
        return False, ""
    if len(doc_body) > 512:
        return False, "too_long_to_be_query_echo"
    try:
        from aria.security.psyops import detect_influence
        from aria.security.rounds.r22_dan_jailbreak import detect_dan
        if detect_influence(doc_body).alert:
            return True, "high_sim + influence"
        ds, _ = detect_dan(doc_body)
        if ds >= 0.5:
            return True, f"high_sim + dan {ds:.2f}"
    except Exception:
        pass
    return False, ""


def filter_top(
    docs: List[Tuple[str, float]],
) -> Tuple[List[Tuple[str, float]], List[str]]:
    """Drop suspicious top-k items, return ``(filtered, removed_reasons)``.

    Each input item is ``(body, similarity)`` from the re-ranker."""
    out: List[Tuple[str, float]] = []
    removed: List[str] = []
    for body, sim in docs:
        bad, why = is_suspicious_top(body, similarity=sim)
        if bad:
            removed.append(why)
            continue
        out.append((body, sim))
    return out, removed


register(DefencePlugin(
    round_id="R134",
    name="rag_rerank_poison",
    description="Drop high-similarity short docs whose body looks like influence/DAN.",
))
