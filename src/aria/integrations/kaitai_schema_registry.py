from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


DEFAULT_KAITAI_DIR = Path("data/satnogs_kaitai")


@dataclass(frozen=True)
class KaitaiSchemaRecord:
    schema_id: str
    file_path: Path
    title: str
    endian: str
    doc_ref: str
    summary: str
    field_count: int
    raw_text: str

    def schema_excerpt(self, *, max_chars: int = 800) -> str:
        if len(self.raw_text) <= max_chars:
            return self.raw_text
        return self.raw_text[:max_chars] + f"\n... [{len(self.raw_text) - max_chars} chars truncated]"


_META_LINE_RE = re.compile(r"^\s+(\w+):\s*(.+?)\s*$", re.MULTILINE)
_FIELD_LINE_RE = re.compile(r"^\s*:field\s+\w+:", re.MULTILINE)


def _extract_metadata(raw_text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    in_meta = False
    for line in raw_text.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("meta:"):
            in_meta = True
            continue
        if in_meta:
            if not stripped.startswith(" ") and not stripped.startswith("\t"):
                if stripped:
                    in_meta = False
                continue
            match = _META_LINE_RE.match(stripped)
            if match:
                key, value = match.group(1), match.group(2)
                metadata[key] = value.strip().strip("'\"")
    return metadata


def _extract_doc_ref(raw_text: str) -> str:
    match = re.search(r"doc-ref:\s*'?\"?([^'\"\n]+)'?\"?", raw_text)
    if match:
        return match.group(1).strip()
    return ""


def _extract_summary(raw_text: str) -> str:
    match = re.search(r"^doc:\s*(?:\|)?\s*$([^]]*?)(?:^[a-zA-Z]|\Z)", raw_text, re.MULTILINE)
    if match:
        body = match.group(1).strip()
        return body[:500]
    return ""


def parse_kaitai_file(path: Path) -> Optional[KaitaiSchemaRecord]:
    if not path.exists() or path.suffix != ".ksy":
        return None
    raw = path.read_text(encoding="utf-8", errors="replace")
    metadata = _extract_metadata(raw)
    schema_id = metadata.get("id") or path.stem
    title = metadata.get("title") or schema_id
    endian = metadata.get("endian", "be")
    doc_ref = _extract_doc_ref(raw)
    summary = _extract_summary(raw)
    field_count = len(_FIELD_LINE_RE.findall(raw))
    return KaitaiSchemaRecord(
        schema_id=schema_id,
        file_path=path,
        title=title,
        endian=endian,
        doc_ref=doc_ref,
        summary=summary,
        field_count=field_count,
        raw_text=raw,
    )


@dataclass
class KaitaiSchemaRegistry:
    schemas_by_id: dict[str, KaitaiSchemaRecord] = field(default_factory=dict)

    @classmethod
    def from_directory(cls, doctrine_dir: Path = DEFAULT_KAITAI_DIR) -> "KaitaiSchemaRegistry":
        registry = cls()
        if not doctrine_dir.exists():
            return registry
        for path in sorted(doctrine_dir.glob("*.ksy")):
            record = parse_kaitai_file(path)
            if record is not None:
                registry.schemas_by_id[record.schema_id] = record
        return registry

    def lookup(self, schema_id: str) -> Optional[KaitaiSchemaRecord]:
        return self.schemas_by_id.get(schema_id.lower())

    def search_by_keyword(self, keyword: str) -> list[KaitaiSchemaRecord]:
        keyword_lower = keyword.lower()
        return [
            record for record in self.schemas_by_id.values()
            if keyword_lower in record.title.lower() or keyword_lower in record.schema_id
        ]

    @property
    def n_schemas(self) -> int:
        return len(self.schemas_by_id)

    def all_titles(self) -> list[str]:
        return sorted(record.title for record in self.schemas_by_id.values())


def render_schema_for_advisor_prompt(
    record: KaitaiSchemaRecord, *, max_chars: int = 600,
) -> str:
    return (
        f"[KAITAI SCHEMA {record.schema_id}] {record.title}\n"
        f"  endian: {record.endian}; fields: {record.field_count}\n"
        f"  doc-ref: {record.doc_ref}\n"
        f"  schema excerpt:\n{record.schema_excerpt(max_chars=max_chars)}"
    )
