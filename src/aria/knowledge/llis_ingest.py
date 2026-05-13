from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import structlog

from aria.knowledge.lessons_learned import LessonRecord

logger = structlog.get_logger()


LLIS_SEARCH_URL = "https://llis.nasa.gov/llis/lesson/_search"
DEFAULT_PAGE_SIZE = 100
DEFAULT_TIMEOUT_S = 30.0
USER_AGENT = "aria-knowledge/1.0 (research; ARIA project)"


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    cleaned = cleaned.replace("&nbsp;", " ").replace("&amp;", "&")
    cleaned = cleaned.replace("&quot;", '"').replace("&#39;", "'")
    cleaned = _WS_RE.sub(" ", cleaned)
    return cleaned.strip()


@dataclass(frozen=True)
class LlisLesson:
    lesson_id: str
    title: str
    abstract: str
    description_event: str
    lesson: str
    recommendation: str
    lesson_date: str
    submitting_organization: str
    topics: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def to_lesson_record(self) -> LessonRecord:
        body_parts = []
        if self.description_event:
            body_parts.append("EVENT: " + self.description_event)
        if self.lesson:
            body_parts.append("LESSON: " + self.lesson)
        if self.recommendation:
            body_parts.append("RECOMMENDATION: " + self.recommendation)
        summary = " | ".join(body_parts)[:1500]
        keywords: list[str] = []
        for topic in self.topics:
            if topic and topic != "None":
                keywords.append(topic.lower())
        for category in self.categories:
            if category and category != "None":
                keywords.append(category.lower())
        return LessonRecord(
            record_id=f"llis-{self.lesson_id}",
            title=self.title or f"NASA LLIS Lesson #{self.lesson_id}",
            summary=summary,
            keywords=tuple(keywords[:8]),
            source="nasa_llis",
            citation=(
                f"NASA Public Lessons Learned System #{self.lesson_id} "
                f"({self.lesson_date or 'undated'}); "
                f"{self.submitting_organization or 'NASA'}"
            ),
            parameters=(),
            fetched_at_iso=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )


def _parse_hit(hit: dict[str, Any]) -> Optional[LlisLesson]:
    source = hit.get("_source")
    if not isinstance(source, dict) or not source:
        return None
    raw_topics = source.get("topics") or []
    topics: list[str] = []
    if isinstance(raw_topics, list):
        for item in raw_topics:
            if isinstance(item, dict):
                topics.append(str(item.get("topic_text") or item.get("name") or "").strip())
            elif isinstance(item, str):
                topics.append(item.strip())
    raw_categories = source.get("categories") or []
    categories: list[str] = []
    if isinstance(raw_categories, list):
        for item in raw_categories:
            if isinstance(item, dict):
                categories.append(str(item.get("category_text") or item.get("name") or "").strip())
            elif isinstance(item, str):
                categories.append(item.strip())
    return LlisLesson(
        lesson_id=str(hit.get("_id") or source.get("public_lesson_number") or ""),
        title=_strip_html(str(source.get("abstract") or source.get("title") or "")),
        abstract=_strip_html(str(source.get("abstract") or "")),
        description_event=_strip_html(str(source.get("description_event") or "")),
        lesson=_strip_html(str(source.get("lesson") or "")),
        recommendation=_strip_html(str(source.get("recommendation") or "")),
        lesson_date=str(source.get("lesson_date") or ""),
        submitting_organization=str(source.get("submitting_organization") or ""),
        topics=tuple(filter(None, topics)),
        categories=tuple(filter(None, categories)),
        raw=source,
    )


class LlisError(RuntimeError):
    pass


@dataclass
class LlisFetcher:
    page_size: int = DEFAULT_PAGE_SIZE
    timeout_s: float = DEFAULT_TIMEOUT_S
    user_agent: str = USER_AGENT
    base_url: str = LLIS_SEARCH_URL
    max_pages: int = 25
    rest_seconds: float = 1.5

    def fetch_page(self, *, from_offset: int) -> tuple[list[LlisLesson], int]:
        params = {
            "size": str(self.page_size),
            "from": str(from_offset),
            "q": "*",
        }
        url = f"{self.base_url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            raise LlisError(f"LLIS fetch failed at offset {from_offset}: {exc}") from exc
        hits = (payload.get("hits") or {}).get("hits") or []
        total = (payload.get("hits") or {}).get("total") or 0
        if isinstance(total, dict):
            total = total.get("value", 0)
        lessons: list[LlisLesson] = []
        for hit in hits:
            parsed = _parse_hit(hit) if isinstance(hit, dict) else None
            if parsed is not None:
                lessons.append(parsed)
        return lessons, int(total)

    def fetch_all(
        self, *, on_progress: Optional[callable] = None,
    ) -> list[LlisLesson]:
        collected: list[LlisLesson] = []
        offset = 0
        total: Optional[int] = None
        for page_index in range(self.max_pages):
            page, total_value = self.fetch_page(from_offset=offset)
            collected.extend(page)
            if total is None:
                total = total_value
            if on_progress is not None:
                on_progress(len(collected), total)
            if not page or len(collected) >= total_value:
                break
            offset += self.page_size
            time.sleep(self.rest_seconds)
        return collected


def write_llis_lessons(
    lessons: Iterable[LlisLesson], out_path: Path,
) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "lesson_id": lesson.lesson_id,
            "title": lesson.title,
            "abstract": lesson.abstract,
            "description_event": lesson.description_event,
            "lesson": lesson.lesson,
            "recommendation": lesson.recommendation,
            "lesson_date": lesson.lesson_date,
            "submitting_organization": lesson.submitting_organization,
            "topics": list(lesson.topics),
            "categories": list(lesson.categories),
        }
        for lesson in lessons
    ]
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return len(payload)


def load_llis_lessons(path: Path) -> list[LlisLesson]:
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[LlisLesson] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append(LlisLesson(
            lesson_id=str(item.get("lesson_id", "")),
            title=str(item.get("title", "")),
            abstract=str(item.get("abstract", "")),
            description_event=str(item.get("description_event", "")),
            lesson=str(item.get("lesson", "")),
            recommendation=str(item.get("recommendation", "")),
            lesson_date=str(item.get("lesson_date", "")),
            submitting_organization=str(item.get("submitting_organization", "")),
            topics=tuple(item.get("topics") or ()),
            categories=tuple(item.get("categories") or ()),
        ))
    return out
