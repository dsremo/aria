from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger()


CELESTRAK_GP_URL = "https://celestrak.org/NORAD/elements/gp.php"
CELESTRAK_DEFAULT_GROUP = "active"
CELESTRAK_USER_AGENT = "aria-conjunction/1.0 (research; contact: ARIA project)"
CELESTRAK_DEFAULT_TIMEOUT_S = 30.0
CELESTRAK_RETRY_BACKOFF_S = (1.0, 2.0, 4.0)


class CelestrakError(RuntimeError):
    pass


@dataclass(frozen=True)
class CelestrakResponse:
    group: str
    raw_text: str
    fetched_at_s: float
    n_lines: int


class CelestrakClient:
    def __init__(
        self,
        *,
        timeout_s: float = CELESTRAK_DEFAULT_TIMEOUT_S,
        user_agent: str = CELESTRAK_USER_AGENT,
        opener: Optional[urllib.request.OpenerDirector] = None,
    ) -> None:
        self._timeout_s = timeout_s
        self._user_agent = user_agent
        self._opener = opener or urllib.request.build_opener()

    def fetch_group(self, group: str = CELESTRAK_DEFAULT_GROUP) -> CelestrakResponse:
        url = f"{CELESTRAK_GP_URL}?GROUP={group}&FORMAT=TLE"
        last_exc: Optional[Exception] = None
        for attempt_index, backoff_s in enumerate(CELESTRAK_RETRY_BACKOFF_S):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": self._user_agent},
                )
                with self._opener.open(req, timeout=self._timeout_s) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                if not raw.strip():
                    raise CelestrakError(f"empty response for group={group}")
                if "<html" in raw[:512].lower():
                    raise CelestrakError(
                        f"HTML response (likely throttled) for group={group}"
                    )
                lines = raw.strip().splitlines()
                logger.info(
                    "aria.celestrak.fetch_ok",
                    group=group,
                    lines=len(lines),
                    bytes=len(raw),
                )
                return CelestrakResponse(
                    group=group,
                    raw_text=raw,
                    fetched_at_s=time.time(),
                    n_lines=len(lines),
                )
            except (urllib.error.URLError, CelestrakError) as exc:
                last_exc = exc
                logger.warning(
                    "aria.celestrak.fetch_retry",
                    group=group,
                    attempt=attempt_index + 1,
                    error=str(exc),
                )
                if attempt_index < len(CELESTRAK_RETRY_BACKOFF_S) - 1:
                    time.sleep(backoff_s)
        raise CelestrakError(
            f"celestrak fetch for group={group} failed after retries: {last_exc}"
        )

    def fetch_groups(self, groups: list[str]) -> dict[str, CelestrakResponse]:
        results: dict[str, CelestrakResponse] = {}
        for group in groups:
            try:
                results[group] = self.fetch_group(group)
            except CelestrakError as exc:
                logger.warning(
                    "aria.celestrak.group_failed", group=group, error=str(exc),
                )
        return results
