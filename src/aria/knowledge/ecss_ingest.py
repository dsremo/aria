from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import structlog

logger = structlog.get_logger()


ECSS_ROOT = "https://ecss.nl"
ECSS_ACTIVE_STANDARDS_URL = f"{ECSS_ROOT}/standard/active-standards/"
ECSS_ACTIVE_HANDBOOKS_URL = f"{ECSS_ROOT}/hbs/active-handbooks/"
ECSS_TMS_URL = f"{ECSS_ROOT}/hbs/tms/"
DEFAULT_TIMEOUT_S = 30.0
USER_AGENT = "Mozilla/5.0 aria-knowledge/1.0 (research; ARIA project)"
DEFAULT_REST_S = 1.5


_TITLE_RE = re.compile(r"<title>\s*([^<|]+?)\s*\|\s*European", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_STANDARD_HREF_RE = re.compile(r'href="(https://ecss\.nl/standard/[^"]+)"')
_PDF_HREF_RE = re.compile(r'href="(https://ecss\.nl/wp-content/uploads/[^"]+\.pdf)"', re.IGNORECASE)
_TYPE_FROM_SLUG_RE = re.compile(r"ecss-([a-z]+)-(?:as|st|hb|tm)-([0-9-]+)c?", re.IGNORECASE)


def _strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    cleaned = cleaned.replace("&nbsp;", " ").replace("&amp;", "&")
    cleaned = cleaned.replace("&quot;", '"').replace("&#39;", "'")
    cleaned = _WS_RE.sub(" ", cleaned)
    return cleaned.strip()


@dataclass(frozen=True)
class EcssStandardRecord:
    standard_id: str
    title: str
    url: str
    issue_date: str = ""
    standard_type: str = ""
    pdf_urls: tuple[str, ...] = ()
    abstract: str = ""

    def to_doctrine_entry(self) -> dict:
        kind = "flight_rule"
        if "training" in self.title.lower() or "handbook" in self.title.lower():
            kind = "reference"
        return {
            "rule_id": self.standard_id,
            "kind": kind,
            "title": self.title,
            "body": self.abstract or self.title,
            "keywords": list(_extract_keywords(self.title)),
            "citation": f"ECSS {self.standard_id} ({self.issue_date or 'undated'}); {self.url}",
            "parameters": [],
        }


def _extract_keywords(title: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9]{3,}", title.lower())
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out[:10]


def _build_cookie_header() -> str:
    parts: list[str] = []
    phpsessid = os.environ.get("ARIA_ECSS_COOKIE_PHPSESSID")
    if phpsessid:
        parts.append(f"PHPSESSID={phpsessid}")
    for key in ("ARIA_ECSS_COOKIE_WFWAF", "ARIA_ECSS_COOKIE_LOGGED_IN", "ARIA_ECSS_COOKIE_SEC"):
        cookie = os.environ.get(key)
        if cookie:
            parts.append(cookie.strip())
    return "; ".join(parts)


class EcssAuthError(RuntimeError):
    pass


@dataclass
class EcssFetcher:
    timeout_s: float = DEFAULT_TIMEOUT_S
    user_agent: str = USER_AGENT
    rest_seconds: float = DEFAULT_REST_S

    def _open(self, url: str) -> str:
        cookie_header = _build_cookie_header()
        if not cookie_header:
            raise EcssAuthError(
                "ARIA_ECSS_COOKIE_* env vars not set. "
                "Manual login + browser cookie export required (reCAPTCHA-gated)."
            )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html",
                "Cookie": cookie_header,
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def fetch_active_standards_index(self) -> list[str]:
        body = self._open(ECSS_ACTIVE_STANDARDS_URL)
        urls = sorted(set(_STANDARD_HREF_RE.findall(body)))
        return urls

    def fetch_standard_record(self, url: str) -> Optional[EcssStandardRecord]:
        try:
            body = self._open(url)
        except urllib.error.URLError as exc:
            logger.warning("ecss.fetch_failed", url=url, error=str(exc))
            return None
        title = ""
        title_match = _TITLE_RE.search(body)
        if title_match:
            title = title_match.group(1).strip()
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        standard_id = _slug_to_standard_id(slug, title)
        date_match = re.search(
            r"(\d{1,2}\s+(?:january|february|march|april|may|june|july|august|"
            r"september|october|november|december)\s+\d{4})",
            title.lower(),
        )
        issue_date = date_match.group(1) if date_match else ""
        pdf_urls = tuple(sorted(set(_PDF_HREF_RE.findall(body))))
        abstract = _extract_abstract(body)
        return EcssStandardRecord(
            standard_id=standard_id,
            title=title,
            url=url,
            issue_date=issue_date,
            standard_type=_classify_type(standard_id),
            pdf_urls=pdf_urls,
            abstract=abstract,
        )

    def fetch_all_active_standards(
        self, *,
        max_records: Optional[int] = None,
        on_progress: Optional[callable] = None,
    ) -> list[EcssStandardRecord]:
        urls = self.fetch_active_standards_index()
        if max_records is not None:
            urls = urls[:max_records]
        records: list[EcssStandardRecord] = []
        for index, url in enumerate(urls):
            record = self.fetch_standard_record(url)
            if record is not None:
                records.append(record)
            if on_progress is not None:
                on_progress(len(records), len(urls))
            time.sleep(self.rest_seconds)
        return records


def _slug_to_standard_id(slug: str, title: str) -> str:
    if slug.isdigit():
        match = re.search(
            r"(ECSS-[A-Z](?:-(?:AS|ST|HB|TM))?-[0-9][0-9-]*[A-Z]?(?:\s+Rev[\.\s]*\d+)?)",
            title, re.IGNORECASE,
        )
        if match:
            return match.group(1).upper().replace("  ", " ")
        return f"ECSS-#{slug}"
    match = re.match(r"(ecss-[a-z0-9-]+?)-(?:adoption|space|structural|simulation|test|reliability|cleanliness|design|qualification|electrical|telecommand|telemetry|extending|space|software|product)", slug.lower())
    if match:
        return match.group(1).upper()
    cleaned = slug.upper().split("-")[0:7]
    return "-".join(cleaned)


def _classify_type(standard_id: str) -> str:
    sid = standard_id.upper()
    if "ECSS-E-" in sid:
        return "engineering"
    if "ECSS-Q-" in sid:
        return "product_assurance"
    if "ECSS-M-" in sid:
        return "management"
    if "ECSS-S-" in sid:
        return "system"
    return "other"


def _extract_abstract(html: str) -> str:
    match = re.search(
        r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</div>',
        html, re.DOTALL,
    )
    if not match:
        return ""
    return _strip_html(match.group(1))[:600]


def write_ecss_records(
    records: Iterable[EcssStandardRecord], out_path: Path,
) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "standard_id": record.standard_id,
            "title": record.title,
            "url": record.url,
            "issue_date": record.issue_date,
            "standard_type": record.standard_type,
            "pdf_urls": list(record.pdf_urls),
            "abstract": record.abstract,
        }
        for record in records
    ]
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return len(payload)


def load_ecss_records(path: Path) -> list[EcssStandardRecord]:
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[EcssStandardRecord] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append(EcssStandardRecord(
            standard_id=str(item.get("standard_id", "")),
            title=str(item.get("title", "")),
            url=str(item.get("url", "")),
            issue_date=str(item.get("issue_date", "")),
            standard_type=str(item.get("standard_type", "")),
            pdf_urls=tuple(item.get("pdf_urls") or ()),
            abstract=str(item.get("abstract", "")),
        ))
    return out
