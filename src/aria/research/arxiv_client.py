"""arXiv API client — cached + rate-limit-aware.

Endpoint: ``http://export.arxiv.org/api/query`` (Atom 1.0 over HTTP).
Rate-limit guidance from arXiv: 3-second delay between calls is
the recommended polite-poll interval. We respect that.

Per arXiv API User Manual:
  * Default sort is RELEVANCE; we use ``submittedDate``.
  * ``max_results`` per call is capped at 2000 by upstream.
  * Atom XML must be parsed; the ``<entry>`` items are papers.
"""

from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence
from urllib import error, parse, request

import structlog

logger = structlog.get_logger()


ARXIV_API_BASE = "http://export.arxiv.org/api/query"
DEFAULT_RATE_LIMIT_DELAY_S = 3.0       # arXiv recommended polite delay
DEFAULT_REQUEST_TIMEOUT_S = 45.0       # arXiv export endpoint can be slow
DEFAULT_CACHE_TTL_S = 21_600.0         # 6 h — papers don't churn faster
DEFAULT_MAX_RESULTS_PER_CALL = 50      # below the 2000 upstream cap
DEFAULT_USER_AGENT = "ARIA-Core/1.0 (research-tracker; contact via repo)"


# Atom-XML namespaces used by arXiv responses.
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}


@dataclass(frozen=True)
class ArxivPaper:
    """Normalised arXiv paper record."""

    arxiv_id: str            # e.g. "2604.17176"
    title: str
    authors: tuple[str, ...]
    summary: str             # abstract (one paragraph)
    primary_category: str    # e.g. "cs.RO"
    categories: tuple[str, ...]
    published_iso: str
    updated_iso: str
    pdf_url: str
    abs_url: str             # https://arxiv.org/abs/<id>


@dataclass
class ArxivClient:
    """Polite, file-cached arXiv API client.

    ``cache_dir`` lives under ``ARIA_RUNTIME_DIR/research/arxiv_cache``
    by default. Each query is keyed by the URL-encoded query string so
    the cache works as a content-addressable store.
    """

    cache_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("ARIA_RUNTIME_DIR", "data/runtime")
    ) / "research" / "arxiv_cache")
    cache_ttl_s: float = DEFAULT_CACHE_TTL_S
    rate_limit_delay_s: float = DEFAULT_RATE_LIMIT_DELAY_S
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S
    user_agent: str = DEFAULT_USER_AGENT
    base_url: str = ARXIV_API_BASE
    _last_call_monotonic: float = 0.0

    def _wait_for_rate_limit(self) -> None:
        delta = time.monotonic() - self._last_call_monotonic
        if delta < self.rate_limit_delay_s:
            time.sleep(self.rate_limit_delay_s - delta)

    def _cache_path(self, query: str) -> Path:
        safe = parse.quote(query, safe="")
        return self.cache_dir / f"{safe}.xml"

    def _read_cache(self, query: str) -> Optional[bytes]:
        path = self._cache_path(query)
        if not path.is_file():
            return None
        if (time.time() - path.stat().st_mtime) > self.cache_ttl_s:
            return None
        try:
            return path.read_bytes()
        except OSError as exc:
            logger.warning("arxiv.cache_read_failed", error=str(exc))
            return None

    def _write_cache(self, query: str, body: bytes) -> None:
        try:
            path = self._cache_path(query)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(body)
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning("arxiv.cache_write_failed", error=str(exc))

    def _fetch_raw(self, query: str) -> bytes:
        """HTTP GET against arXiv. Returns the raw Atom XML body."""
        self._wait_for_rate_limit()
        url = f"{self.base_url}?{query}"
        req = request.Request(
            url, headers={"User-Agent": self.user_agent}, method="GET",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_s) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"arXiv returned HTTP {response.status}"
                    )
                body = response.read()
        except error.HTTPError as exc:
            raise RuntimeError(
                f"arXiv HTTP {exc.code}: {exc.reason}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(
                f"arXiv network error: {exc.reason}"
            ) from exc
        finally:
            object.__setattr__(self, "_last_call_monotonic", time.monotonic())
        return body

    def search(
        self,
        category: str,
        *,
        max_results: int = DEFAULT_MAX_RESULTS_PER_CALL,
        sort_by: str = "submittedDate",
        sort_order: str = "descending",
    ) -> list[ArxivPaper]:
        """Search a single category, sorted newest-first."""
        if not 1 <= max_results <= 2000:
            raise ValueError(
                f"max_results must be 1..2000, got {max_results}"
            )
        query_params = {
            "search_query": f"cat:{category}",
            "sortBy": sort_by,
            "sortOrder": sort_order,
            "max_results": str(max_results),
        }
        query = parse.urlencode(query_params)

        cached = self._read_cache(query)
        body = cached or self._fetch_raw(query)
        if cached is None:
            self._write_cache(query, body)

        return self._parse_atom(body)

    @staticmethod
    def _parse_atom(body: bytes) -> list[ArxivPaper]:
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise RuntimeError(f"arXiv returned non-XML: {exc}") from exc
        out: list[ArxivPaper] = []
        for entry in root.findall("atom:entry", _NS):
            try:
                out.append(_parse_entry(entry))
            except (TypeError, ValueError) as exc:
                logger.warning("arxiv.parse_entry_failed", error=str(exc))
        return out


def _parse_entry(entry: ET.Element) -> ArxivPaper:
    """Parse one ``<entry>`` element into an ArxivPaper."""
    arxiv_id = _id_from_entry_url(_text(entry, "atom:id"))
    title = _text(entry, "atom:title").strip()
    summary = _text(entry, "atom:summary").strip()
    published = _text(entry, "atom:published").strip()
    updated = _text(entry, "atom:updated").strip()

    authors = tuple(
        _text(author, "atom:name").strip()
        for author in entry.findall("atom:author", _NS)
        if _text(author, "atom:name").strip()
    )

    primary_category_el = entry.find("arxiv:primary_category", _NS)
    primary_category = (
        primary_category_el.attrib.get("term", "")
        if primary_category_el is not None else ""
    )
    categories = tuple(
        cat.attrib.get("term", "")
        for cat in entry.findall("atom:category", _NS)
        if cat.attrib.get("term")
    )

    pdf_url = ""
    abs_url = ""
    for link in entry.findall("atom:link", _NS):
        href = link.attrib.get("href", "")
        rel = link.attrib.get("rel", "")
        link_title = link.attrib.get("title", "")
        if link_title == "pdf":
            pdf_url = href
        elif rel == "alternate":
            abs_url = href

    return ArxivPaper(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        summary=summary,
        primary_category=primary_category,
        categories=categories,
        published_iso=published,
        updated_iso=updated,
        pdf_url=pdf_url,
        abs_url=abs_url,
    )


def _id_from_entry_url(url: str) -> str:
    """arXiv IDs come back as e.g. http://arxiv.org/abs/2604.17176v1."""
    if not url:
        return ""
    last = url.rsplit("/", 1)[-1]
    # Drop trailing version suffix vN to match the canonical id.
    if "v" in last:
        prefix, _, _suffix = last.rpartition("v")
        if _suffix.isdigit():
            return prefix
    return last


def _text(element: ET.Element, path: str) -> str:
    found = element.find(path, _NS)
    return found.text or "" if found is not None else ""
