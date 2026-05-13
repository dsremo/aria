"""SatNOGS DB integration — Libre Space volunteer satellite-tracking network.

SatNOGS (https://satnogs.org) is the largest volunteer-operated
ground-station network on the planet. It tracks the publicly-visible
satellite population — CubeSats, smallsats, weather sats, ham-radio
satellites, university missions — and aggregates their telemetry,
transmitter configurations, and orbital elements into a public CC-BY-SA
database at https://db.satnogs.org.

ARIA uses this integration to:

  * Pull up-to-date TLEs for satellites the conjunction screener
    is asked about (alongside SpaceTrack + Celestrak).
  * Surface known-good transmitter configs for the comms agent's
    link-budget sanity checks.
  * Optionally ingest live telemetry frames for the dsremo anomaly
    detector to score against (requires API key).

Public endpoints (no auth):
  * /api/satellites/        satellite catalogue + status
  * /api/transmitters/      RF mode + frequency catalogue
  * /api/tle/               TLE catalogue
  * /api/modes/             modulation modes
  * /api/artifacts/         observation artifacts

Authenticated endpoints (API key required):
  * /api/telemetry/         per-satellite raw telemetry frames
  * /api/optical-observations/   optical observations

Set ``ARIA_SATNOGS_API_KEY`` to enable telemetry ingest.

Citations:
  * SatNOGS DB API docs: https://docs.satnogs.org/projects/satnogs-db/en/stable/api.html
  * Libre Space Foundation: https://libre.space/
  * Data licence: CC-BY-SA 4.0 — attribute SatNOGS / Libre Space.
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


SATNOGS_DB_BASE = "https://db.satnogs.org/api"
DEFAULT_CACHE_TTL_S = 1800.0       # 30 min — SatNOGS DB updates hourly-ish
DEFAULT_REQUEST_TIMEOUT_S = 30.0
DEFAULT_PER_PAGE = 25
MAX_PAGES = 50                     # bound recursive paging


@dataclass(frozen=True)
class Satellite:
    """One SatNOGS satellite catalogue entry."""

    sat_id: str                    # e.g. "SCHX-0895-2361-9925-0309"
    norad_cat_id: Optional[int]    # e.g. 25544 (ISS)
    name: str
    names: str                     # alternative names, semicolon-separated
    status: str                    # "alive" / "dead" / "re-entered" / "future"
    launched_iso: Optional[str]    # ISO datetime or None
    decayed_iso: Optional[str]
    countries: str                 # comma-separated country codes
    is_frequency_violator: bool
    updated_iso: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Transmitter:
    """One transmitter configuration on a satellite (RF mode + freq)."""

    uuid: str
    description: str
    sat_id: str
    norad_cat_id: Optional[int]
    downlink_mhz: Optional[float]   # MHz (SatNOGS reports Hz; we convert)
    uplink_mhz: Optional[float]
    mode: str                       # e.g. "FSK 9k6", "BPSK 1k2 AX.25"
    baud: Optional[float]
    status: str                     # "active" / "inactive" / "invalid"
    updated_iso: str


@dataclass(frozen=True)
class TLE:
    """A SatNOGS-provided TLE entry."""

    sat_id: str
    norad_cat_id: Optional[int]
    tle_source: str
    tle0: str                       # name line
    tle1: str                       # line 1
    tle2: str                       # line 2
    updated_iso: str

    @property
    def tle_lines(self) -> tuple[str, str, str]:
        return (self.tle0, self.tle1, self.tle2)


@dataclass(frozen=True)
class TelemetryFrame:
    """One raw downlink frame as recorded by a SatNOGS observation."""

    norad_cat_id: int
    timestamp_iso: str
    decoder: Optional[str]          # decoder name if SatNOGS could parse it
    frame_hex: str                  # raw hex frame
    observer_id: Optional[int]      # SatNOGS observer who captured it
    is_decoded: bool


# ── Client ──────────────────────────────────────────────────────


@dataclass
class SatNOGSClient:
    """Cached client for the SatNOGS DB API.

    Public endpoints (satellites / transmitters / TLE / modes) work
    without auth. Telemetry endpoint requires an API key — set
    ``ARIA_SATNOGS_API_KEY`` in env or pass ``api_key=`` here.
    """

    cache_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("ARIA_RUNTIME_DIR", "data/runtime")
    ) / "satnogs_cache")
    cache_ttl_s: float = DEFAULT_CACHE_TTL_S
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S
    api_key: Optional[str] = None
    user_agent: str = "ARIA-Core/1.0 (autonomy@aria-core.dev)"
    base_url: str = SATNOGS_DB_BASE

    # ── Cache ───────────────────────────────────────────────────

    def _cache_path(self, query_key: str) -> Path:
        safe = parse.quote(query_key, safe="")
        return self.cache_dir / f"{safe}.json"

    def _read_cache(self, query_key: str) -> Optional[Any]:
        path = self._cache_path(query_key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("satnogs.cache_read_failed", error=str(exc))
            return None
        cached_at = payload.get("_cached_at", 0.0)
        if (time.time() - cached_at) > self.cache_ttl_s:
            return None
        return payload.get("data")

    def _write_cache(self, query_key: str, data: Any) -> None:
        try:
            path = self._cache_path(query_key)
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"_cached_at": time.time(), "data": data}
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning("satnogs.cache_write_failed", error=str(exc))

    # ── HTTP plumbing ──────────────────────────────────────────

    def _fetch_raw(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None,
        require_auth: bool = False,
    ) -> Any:
        """Issue a GET against the SatNOGS DB API; return decoded JSON."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        if require_auth:
            if not self.api_key:
                raise RuntimeError(
                    f"SatNOGS endpoint {endpoint} requires an API key; "
                    "set ARIA_SATNOGS_API_KEY in env or pass api_key= "
                    "to SatNOGSClient. Public endpoints (satellites, "
                    "transmitters, tle, modes) work without auth."
                )
            headers["Authorization"] = f"Token {self.api_key}"
        elif self.api_key:
            # If we have a key, use it even on public endpoints
            # (gives higher rate limit per SatNOGS docs).
            headers["Authorization"] = f"Token {self.api_key}"

        query = parse.urlencode(params or {})
        url = f"{self.base_url}{endpoint}"
        if query:
            url = f"{url}?{query}"

        req = request.Request(url, headers=headers, method="GET")
        try:
            with request.urlopen(req, timeout=self.timeout_s) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"SatNOGS HTTP {response.status} for {endpoint}"
                    )
                body = response.read()
        except error.HTTPError as exc:
            if exc.code == 401:
                raise RuntimeError(
                    f"SatNOGS returned 401 for {endpoint} — "
                    "endpoint requires API key or your key is invalid."
                ) from exc
            raise RuntimeError(
                f"SatNOGS HTTP {exc.code}: {exc.reason}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(
                f"SatNOGS network error: {exc.reason}"
            ) from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"SatNOGS returned non-JSON: {exc}"
            ) from exc

    # ── Public endpoints ───────────────────────────────────────

    def get_satellite(self, norad_cat_id: int) -> Optional[Satellite]:
        """Fetch a single satellite by NORAD catalogue ID."""
        endpoint = f"/satellites/"
        cache_key = f"{endpoint}?norad_cat_id={norad_cat_id}"
        cached = self._read_cache(cache_key)
        data = cached if cached is not None else self._fetch_raw(
            endpoint, {"norad_cat_id": norad_cat_id},
        )
        if cached is None:
            self._write_cache(cache_key, data)
        if not isinstance(data, list) or not data:
            return None
        return _parse_satellite(data[0])

    def list_satellites(
        self, *, status: str = "alive", per_page: int = DEFAULT_PER_PAGE,
    ) -> List[Satellite]:
        """List satellites with the given status. Default: 'alive' only."""
        endpoint = "/satellites/"
        params = {"status": status, "page_size": per_page}
        cache_key = f"{endpoint}?{parse.urlencode(params)}"
        cached = self._read_cache(cache_key)
        data = cached if cached is not None else self._fetch_raw(
            endpoint, params,
        )
        if cached is None:
            self._write_cache(cache_key, data)
        if not isinstance(data, list):
            return []
        return [_parse_satellite(d) for d in data if isinstance(d, dict)]

    def get_transmitters_for(
        self, norad_cat_id: int,
    ) -> List[Transmitter]:
        endpoint = "/transmitters/"
        params = {"satellite__norad_cat_id": norad_cat_id}
        cache_key = f"{endpoint}?{parse.urlencode(params)}"
        cached = self._read_cache(cache_key)
        data = cached if cached is not None else self._fetch_raw(
            endpoint, params,
        )
        if cached is None:
            self._write_cache(cache_key, data)
        if not isinstance(data, list):
            return []
        return [
            _parse_transmitter(d, norad_cat_id) for d in data
            if isinstance(d, dict)
        ]

    def get_tle(self, norad_cat_id: int) -> Optional[TLE]:
        """Fetch the most recent TLE for a satellite."""
        endpoint = "/tle/"
        params = {"norad_cat_id": norad_cat_id}
        cache_key = f"{endpoint}?{parse.urlencode(params)}"
        cached = self._read_cache(cache_key)
        data = cached if cached is not None else self._fetch_raw(
            endpoint, params,
        )
        if cached is None:
            self._write_cache(cache_key, data)
        if not isinstance(data, list) or not data:
            return None
        return _parse_tle(data[0])

    # ── Authenticated endpoints ────────────────────────────────

    def get_recent_telemetry(
        self,
        norad_cat_id: int,
        *,
        max_frames: int = 100,
    ) -> List[TelemetryFrame]:
        """Pull recent telemetry frames for a satellite.

        Requires an API key. Frames are returned newest-first.
        """
        if max_frames <= 0:
            raise ValueError(f"max_frames must be > 0, got {max_frames}")
        endpoint = "/telemetry/"
        params = {"satellite": norad_cat_id, "page_size": max_frames}
        cache_key = f"{endpoint}?{parse.urlencode(params)}"
        cached = self._read_cache(cache_key)
        data = cached if cached is not None else self._fetch_raw(
            endpoint, params, require_auth=True,
        )
        if cached is None:
            self._write_cache(cache_key, data)
        if not isinstance(data, list):
            return []
        return [
            _parse_telemetry(d) for d in data
            if isinstance(d, dict)
        ]


# ── Parsers ─────────────────────────────────────────────────────


def _parse_satellite(d: Dict[str, Any]) -> Satellite:
    return Satellite(
        sat_id=str(d.get("sat_id", "")),
        norad_cat_id=_safe_int(d.get("norad_cat_id")),
        name=str(d.get("name", "")),
        names=str(d.get("names", "") or ""),
        status=str(d.get("status", "")),
        launched_iso=d.get("launched"),
        decayed_iso=d.get("decayed"),
        countries=str(d.get("countries", "") or ""),
        is_frequency_violator=bool(d.get("is_frequency_violator", False)),
        updated_iso=str(d.get("updated", "")),
    )


def _parse_transmitter(d: Dict[str, Any], fallback_norad: int) -> Transmitter:
    downlink = _safe_float(d.get("downlink_low"))
    uplink = _safe_float(d.get("uplink_low"))
    return Transmitter(
        uuid=str(d.get("uuid", "")),
        description=str(d.get("description", "")),
        sat_id=str(d.get("sat_id", "")),
        norad_cat_id=_safe_int(d.get("norad_cat_id")) or fallback_norad,
        downlink_mhz=(downlink / 1e6) if downlink else None,
        uplink_mhz=(uplink / 1e6) if uplink else None,
        mode=str(d.get("mode", "")),
        baud=_safe_float(d.get("baud")),
        status=str(d.get("status", "")),
        updated_iso=str(d.get("updated", "")),
    )


def _parse_tle(d: Dict[str, Any]) -> TLE:
    return TLE(
        sat_id=str(d.get("sat_id", "")),
        norad_cat_id=_safe_int(d.get("norad_cat_id")),
        tle_source=str(d.get("tle_source", "")),
        tle0=str(d.get("tle0", "")),
        tle1=str(d.get("tle1", "")),
        tle2=str(d.get("tle2", "")),
        updated_iso=str(d.get("updated", "")),
    )


def _parse_telemetry(d: Dict[str, Any]) -> TelemetryFrame:
    return TelemetryFrame(
        norad_cat_id=_safe_int(d.get("norad_cat_id")) or 0,
        timestamp_iso=str(d.get("timestamp", "")),
        decoder=d.get("decoder"),
        frame_hex=str(d.get("frame", "")),
        observer_id=_safe_int(d.get("observer")),
        is_decoded=bool(d.get("decoded", d.get("is_decoded", False))),
    )


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ── Module singleton ────────────────────────────────────────────


_INSTANCE: Optional[SatNOGSClient] = None


def get_satnogs_client() -> SatNOGSClient:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = SatNOGSClient(
            api_key=os.environ.get("ARIA_SATNOGS_API_KEY"),
        )
    return _INSTANCE


def reset_for_test() -> None:
    global _INSTANCE
    _INSTANCE = None
