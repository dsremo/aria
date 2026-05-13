from __future__ import annotations

import enum
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional


DEFAULT_DOCTRINE_DIR = Path("data/doctrine")
DEFAULT_PROMPT_BUDGET_CHARS = 4000
RELEVANCE_TOPK = 8


class DoctrineKind(str, enum.Enum):
    FLIGHT_RULE = "flight_rule"
    MALFUNCTION_PROCEDURE = "malfunction_procedure"
    INCIDENT_REPORT = "incident_report"
    CHECKLIST = "checklist"
    REFERENCE = "reference"


@dataclass(frozen=True)
class DoctrineEntry:
    rule_id: str
    kind: DoctrineKind
    title: str
    body: str
    keywords: tuple[str, ...] = ()
    citation: str = ""
    parameters: tuple[str, ...] = ()

    def render(self) -> str:
        head = f"[{self.kind.value.upper()} {self.rule_id}] {self.title}"
        if self.citation:
            head += f"  ({self.citation})"
        return f"{head}\n{self.body.strip()}"

    def char_count(self) -> int:
        return len(self.render())


@dataclass(frozen=True)
class DoctrineBundle:
    entries: tuple[DoctrineEntry, ...] = ()

    def by_kind(self, kind: DoctrineKind) -> tuple[DoctrineEntry, ...]:
        return tuple(entry for entry in self.entries if entry.kind == kind)

    def by_id(self, rule_id: str) -> Optional[DoctrineEntry]:
        for entry in self.entries:
            if entry.rule_id == rule_id:
                return entry
        return None


class DoctrineLoader:
    def __init__(self, doctrine_dir: Optional[Path] = None) -> None:
        self._doctrine_dir = doctrine_dir or DEFAULT_DOCTRINE_DIR

    def load(self) -> DoctrineBundle:
        if not self._doctrine_dir.exists():
            return DoctrineBundle()
        entries: list[DoctrineEntry] = []
        for path in sorted(self._doctrine_dir.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                entry = _parse_entry(payload)
                if entry is not None:
                    entries.append(entry)
            elif isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict):
                        entry = _parse_entry(item)
                        if entry is not None:
                            entries.append(entry)
        return DoctrineBundle(entries=tuple(entries))


def _parse_entry(payload: dict) -> Optional[DoctrineEntry]:
    rule_id = str(payload.get("rule_id") or payload.get("id") or "").strip()
    if not rule_id:
        return None
    kind_raw = str(payload.get("kind") or "reference").lower()
    try:
        kind = DoctrineKind(kind_raw)
    except ValueError:
        kind = DoctrineKind.REFERENCE
    title = str(payload.get("title") or rule_id)
    body = str(payload.get("body") or "")
    keywords = tuple(
        str(keyword).lower().strip()
        for keyword in (payload.get("keywords") or ())
        if str(keyword).strip()
    )
    citation = str(payload.get("citation") or "")
    parameters = tuple(
        str(parameter).strip()
        for parameter in (payload.get("parameters") or ())
        if str(parameter).strip()
    )
    return DoctrineEntry(
        rule_id=rule_id, kind=kind, title=title, body=body,
        keywords=keywords, citation=citation, parameters=parameters,
    )


def _tokenise(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9_]*", text or "") if len(token) >= 3}


def _score_entry(
    entry: DoctrineEntry,
    *,
    parameter: str,
    severity: str,
    state_tokens: set[str],
    free_text: str,
) -> float:
    parameter_lower = parameter.lower()
    if parameter and parameter_lower in (param.lower() for param in entry.parameters):
        return 100.0
    score = 0.0
    text = (entry.title + " " + entry.body + " " + " ".join(entry.keywords)).lower()
    if parameter and parameter_lower in text:
        score += 25.0
    if severity and severity.lower() in text:
        score += 5.0
    intersect = state_tokens & _tokenise(entry.body)
    score += len(intersect) * 0.5
    free_tokens = _tokenise(free_text)
    score += 1.5 * len(free_tokens & _tokenise(entry.body))
    score += 1.0 * len(free_tokens & set(entry.keywords))
    return score


def select_relevant_entries(
    bundle: DoctrineBundle,
    *,
    parameter: str = "",
    severity: str = "",
    recent_state: Optional[dict[str, float]] = None,
    free_text: str = "",
    top_k: int = RELEVANCE_TOPK,
) -> tuple[DoctrineEntry, ...]:
    state_tokens: set[str] = set()
    if recent_state:
        for key in recent_state:
            state_tokens.update(_tokenise(key))
    scored: list[tuple[float, DoctrineEntry]] = []
    for entry in bundle.entries:
        score = _score_entry(
            entry,
            parameter=parameter, severity=severity,
            state_tokens=state_tokens, free_text=free_text,
        )
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda pair: -pair[0])
    return tuple(entry for _score, entry in scored[:top_k])


def format_doctrine_for_prompt(
    entries: Iterable[DoctrineEntry],
    *,
    budget_chars: int = DEFAULT_PROMPT_BUDGET_CHARS,
) -> str:
    rendered: list[str] = []
    used = 0
    for entry in entries:
        block = entry.render()
        if used + len(block) + 2 > budget_chars and rendered:
            break
        rendered.append(block)
        used += len(block) + 2
    return "\n\n".join(rendered)
