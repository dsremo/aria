"""Launch Library 2 (TheSpaceDevs) integration — upcoming launches.

Pulls the global rocket-launch schedule from the LL2 public API,
which aggregates announcements from operators worldwide
(SpaceX, ULA, ISRO, JAXA, ESA, Roscosmos, CASC, RocketLab, etc.)

Used by:
  * conjunction screener — pre-compute close-approach windows
    against all upcoming launches' published trajectories
  * mission planner — show operator-relevant upcoming launches
  * captain advisor — flag launch-day windows where the screener
    should run more frequently

Rate limit (per LL2 docs): 15 anonymous API calls / hour / IP.
A documented free API key raises this. ARIA caches responses
locally with a configurable TTL so repeated lookups don't burn
the budget.

API URL: https://ll.thespacedevs.com/2.2.0/launch/upcoming/
Tutorial: https://github.com/TheSpaceDevs/Tutorials
License: API access is free per The Space Devs terms; data is
attributed to the upstream source operators.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error, parse, request

import structlog

logger = structlog.get_logger()


LL2_BASE_URL = "https://ll.thespacedevs.com/2.2.0"
DEFAULT_CACHE_TTL_S = 600.0           # 10 min — balance freshness vs rate limit
DEFAULT_REQUEST_TIMEOUT_S = 8.0       # connect + read timeout for upstream
DEFAULT_LIMIT = 20                    # number of upcoming launches per call
MAX_LIMIT = 100                       # LL2 enforces this cap


@dataclass(frozen=True)
class UpcomingLaunch:
    """A single normalized upcoming-launch record.

    All fields are typed and bounded; the upstream JSON has dozens
    of optional sub-fields we don't need. Adding fields here is a
    breaking change — extend, don't repurpose.
    """

    launch_id: str                         # LL2 UUID
    name: str                              # e.g. "Falcon 9 Block 5 | Starlink Group 7-99"
    net_iso: str                           # NET (No-Earlier-Than) timestamp, ISO-8601
    status: str                            # GO / TBD / TBC / SUCCESS / FAILURE / HOLD
    rocket_name: str                       # e.g. "Falcon 9 Block 5"
    provider: str                          # Launch service provider (e.g. "SpaceX")
    pad_name: Optional[str] = None         # Launch pad
    pad_lat_deg: Optional[float] = None
    pad_lon_deg: Optional[float] = None
    mission_name: Optional[str] = None
    mission_orbit: Optional[str] = None    # LEO / GTO / SSO / GEO / HEO / TLI etc.

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LaunchLibraryClient:
    """Cached client for the Launch Library 2 ``/launch/upcoming/`` endpoint.

    Designed to be process-singleton. Backing cache is a single JSON file
    per query-key on disk (``data/runtime/ll2_cache/<sha>.json``) so
    multiple processes can share without lock contention.
    """

    cache_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("ARIA_RUNTIME_DIR", "data/runtime")
    ) / "ll2_cache")
    cache_ttl_s: float = DEFAULT_CACHE_TTL_S
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S
    api_key: Optional[str] = None
    user_agent: str = "ARIA-Core/1.0 (autonomy@aria-core.dev)"
    base_url: str = LL2_BASE_URL

    def _cache_path(self, query_key: str) -> Path:
        # Filename safe for any URL-encoded query string.
        safe = parse.quote(query_key, safe="")
        return self.cache_dir / f"{safe}.json"

    def _read_cache(self, query_key: str) -> Optional[Dict[str, Any]]:
        path = self._cache_path(query_key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("ll2.cache_read_failed", path=str(path), error=str(exc))
            return None
        cached_at = float(payload.get("_cached_at", 0.0))
        if (time.time() - cached_at) > self.cache_ttl_s:
            return None
        return payload

    def _write_cache(self, query_key: str, payload: Dict[str, Any]) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path = self._cache_path(query_key)
            payload_with_ts = dict(payload)
            payload_with_ts["_cached_at"] = time.time()
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload_with_ts), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning("ll2.cache_write_failed", error=str(exc))

    def _fetch_raw(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Issue a single HTTP GET with rate-limit-aware error handling."""
        query = parse.urlencode(params)
        url = f"{self.base_url}{endpoint}?{query}"
        headers = {"User-Agent": self.user_agent}
        if self.api_key:
            headers["Authorization"] = f"Token {self.api_key}"
        req = request.Request(url, headers=headers, method="GET")
        try:
            with request.urlopen(req, timeout=self.timeout_s) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"LL2 returned HTTP {response.status} for {endpoint}"
                    )
                body = response.read()
        except error.HTTPError as exc:
            if exc.code == 429:
                raise RuntimeError(
                    "LL2 rate-limit exceeded (15/hr anonymous). "
                    "Set ARIA_LL2_API_KEY or wait."
                ) from exc
            raise RuntimeError(f"LL2 HTTP {exc.code}: {exc.reason}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"LL2 network error: {exc.reason}") from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"LL2 returned non-JSON payload: {exc}") from exc

    def upcoming(
        self,
        limit: int = DEFAULT_LIMIT,
        mode: str = "list",
    ) -> List[UpcomingLaunch]:
        """Return the next ``limit`` upcoming launches, normalized.

        ``mode="list"`` is the smaller-payload version of the LL2 endpoint;
        ``mode="normal"`` returns more fields. We default to ``list`` to
        stay under rate-limit pressure.
        """
        if not 1 <= limit <= MAX_LIMIT:
            raise ValueError(f"limit must be 1..{MAX_LIMIT}, got {limit}")

        params = {"limit": limit, "mode": mode, "ordering": "net"}
        endpoint = "/launch/upcoming/"
        query_key = f"{endpoint}?{parse.urlencode(params)}"

        cached = self._read_cache(query_key)
        if cached is not None:
            logger.debug("ll2.cache_hit", query=query_key)
            payload = cached
        else:
            logger.info("ll2.fetching", query=query_key)
            payload = self._fetch_raw(endpoint, params)
            self._write_cache(query_key, payload)

        return self._parse_results(payload.get("results", []))

    def _parse_results(self, raw: List[Dict[str, Any]]) -> List[UpcomingLaunch]:
        out: List[UpcomingLaunch] = []
        for entry in raw:
            try:
                out.append(self._parse_one(entry))
            except (KeyError, TypeError, ValueError) as exc:
                # Upstream payload may have null fields; skip the row
                # rather than break the whole batch.
                logger.warning(
                    "ll2.parse_failed",
                    name=entry.get("name") if isinstance(entry, dict) else None,
                    error=str(exc),
                )
        return out

    @staticmethod
    def _parse_one(entry: Dict[str, Any]) -> UpcomingLaunch:
        rocket = entry.get("rocket") or {}
        rocket_config = rocket.get("configuration") or {}
        provider = entry.get("launch_service_provider") or {}
        pad = entry.get("pad") or {}
        mission = entry.get("mission") or {}
        status = entry.get("status") or {}

        return UpcomingLaunch(
            launch_id=str(entry.get("id", "")),
            name=str(entry.get("name", "")),
            net_iso=str(entry.get("net", "")),
            status=str(status.get("name", "TBD")),
            rocket_name=str(rocket_config.get("name", "")),
            provider=str(provider.get("name", "")),
            pad_name=pad.get("name") if pad else None,
            pad_lat_deg=_safe_float(pad.get("latitude")) if pad else None,
            pad_lon_deg=_safe_float(pad.get("longitude")) if pad else None,
            mission_name=mission.get("name") if mission else None,
            mission_orbit=(mission.get("orbit") or {}).get("name")
                if isinstance(mission.get("orbit"), dict) else None,
        )


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# Module-level singleton ─────────────────────────────────────────


_INSTANCE: Optional[LaunchLibraryClient] = None


def get_launch_library_client() -> LaunchLibraryClient:
    """Process-wide LL2 client. Honours ``ARIA_LL2_API_KEY`` env var."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = LaunchLibraryClient(
            api_key=os.environ.get("ARIA_LL2_API_KEY"),
        )
    return _INSTANCE


def reset_for_test() -> None:
    """Test-only — replace the singleton with a fresh instance."""
    global _INSTANCE
    _INSTANCE = None
