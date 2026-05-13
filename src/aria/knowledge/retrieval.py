from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from aria.knowledge.lessons_learned import LessonRecord


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]+")
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "this", "that", "into", "over",
    "onto", "between", "during", "after", "before", "while", "when", "where",
    "which", "their", "they", "them", "than", "then", "are", "was", "were",
    "been", "have", "has", "had", "but", "not", "any", "all", "may", "must",
    "shall", "should", "could", "will", "would", "can", "via", "per", "off",
    "out", "via", "use", "used", "use", "using",
})


def _tokenise(text: str) -> tuple[str, ...]:
    if not text:
        return ()
    tokens = (token.lower() for token in _TOKEN_RE.findall(text))
    return tuple(token for token in tokens if token not in _STOPWORDS and len(token) >= 3)


@dataclass
class _Document:
    record_id: str
    record: LessonRecord
    term_freq: Counter[str] = field(default_factory=Counter)
    length: int = 0


@dataclass(frozen=True)
class RetrievalHit:
    record: LessonRecord
    score: float
    matched_terms: tuple[str, ...]


class TfIdfIndex:
    def __init__(self) -> None:
        self._docs: list[_Document] = []
        self._doc_freq: Counter[str] = Counter()

    def add(self, record: LessonRecord) -> None:
        text = " ".join(filter(None, (
            record.title, record.summary, " ".join(record.keywords),
            record.citation, " ".join(record.parameters),
        )))
        tokens = _tokenise(text)
        tf: Counter[str] = Counter(tokens)
        for token in tf:
            self._doc_freq[token] += 1
        self._docs.append(_Document(
            record_id=record.record_id, record=record,
            term_freq=tf, length=len(tokens),
        ))

    def add_many(self, records: Iterable[LessonRecord]) -> None:
        for record in records:
            self.add(record)

    @property
    def n_documents(self) -> int:
        return len(self._docs)

    def _idf(self, token: str) -> float:
        if token not in self._doc_freq:
            return 0.0
        n = max(1, len(self._docs))
        return math.log((n + 1) / (self._doc_freq[token] + 0.5)) + 1.0

    def _score_doc(
        self, doc: _Document, query_tokens: Sequence[str],
    ) -> tuple[float, tuple[str, ...]]:
        score = 0.0
        matched: list[str] = []
        for token in query_tokens:
            tf = doc.term_freq.get(token, 0)
            if tf <= 0:
                continue
            idf = self._idf(token)
            sublinear_tf = 1.0 + math.log(tf)
            score += sublinear_tf * idf
            matched.append(token)
        if doc.length > 0:
            score /= math.sqrt(doc.length)
        return score, tuple(matched)

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        keyword_boost: float = 1.5,
    ) -> tuple[RetrievalHit, ...]:
        if not query:
            return ()
        query_tokens = _tokenise(query)
        if not query_tokens:
            return ()
        scored: list[RetrievalHit] = []
        for doc in self._docs:
            base_score, matched = self._score_doc(doc, query_tokens)
            if base_score <= 0:
                continue
            keyword_set = {keyword.lower() for keyword in doc.record.keywords}
            extra = sum(
                keyword_boost for token in query_tokens
                if token in keyword_set
            )
            scored.append(RetrievalHit(
                record=doc.record,
                score=base_score + extra,
                matched_terms=matched,
            ))
        scored.sort(key=lambda hit: -hit.score)
        return tuple(scored[:top_k])


def build_default_lesson_index(
    *,
    include_curated: bool = True,
    include_llis: bool = True,
    llis_path: Optional["Path"] = None,
) -> TfIdfIndex:
    from pathlib import Path
    from aria.knowledge.lessons_learned import load_curated_lessons
    from aria.knowledge.llis_ingest import load_llis_lessons
    index = TfIdfIndex()
    if include_curated:
        index.add_many(load_curated_lessons())
    if include_llis:
        target = llis_path if llis_path is not None else Path("data/lessons_learned/llis_corpus.json")
        for lesson in load_llis_lessons(target):
            index.add(lesson.to_lesson_record())
    return index
