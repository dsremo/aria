from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

import structlog

logger = structlog.get_logger()


SATNOGS_DB_BASE = "https://db.satnogs.org/api"
DEFAULT_POLL_INTERVAL_S = 60.0
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_USER_AGENT = "aria-satnogs-live/1.0 (research; ARIA project)"
DEFAULT_PAGE_SIZE = 25
DEFAULT_BACKOFF_S = (1.0, 2.0, 4.0, 8.0)


@dataclass(frozen=True)
class SatNOGSFrame:
    norad_cat_id: int
    timestamp_iso: str
    frame_hex: str
    observer: str = ""
    transmitter_uuid: str = ""
    decoded: dict[str, Any] = field(default_factory=dict)


class SatNOGSDecoder:
    norad_cat_ids: tuple[int, ...] = ()

    def decode(self, frame: SatNOGSFrame) -> dict[str, Any]:
        return {}


class FrameSink:
    def __call__(self, frame: SatNOGSFrame) -> None:
        raise NotImplementedError


@dataclass
class SatNOGSPumpStats:
    polls: int = 0
    frames_emitted: int = 0
    duplicate_skipped: int = 0
    http_errors: int = 0
    decode_errors: int = 0


class SatNOGSLivePump:
    def __init__(
        self,
        *,
        norad_cat_ids: Iterable[int],
        api_token: str,
        sinks: Iterable[Callable[[SatNOGSFrame], None]] = (),
        decoders: Iterable[SatNOGSDecoder] = (),
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        page_size: int = DEFAULT_PAGE_SIZE,
        opener: Optional[urllib.request.OpenerDirector] = None,
    ) -> None:
        if not api_token:
            raise ValueError("api_token required")
        ids = list(norad_cat_ids)
        if not ids:
            raise ValueError("at least one NORAD ID required")
        self._ids = tuple(int(value) for value in ids)
        self._token = api_token
        self._sinks: list[Callable[[SatNOGSFrame], None]] = list(sinks)
        self._decoders: list[SatNOGSDecoder] = list(decoders)
        self._poll_interval_s = poll_interval_s
        self._timeout_s = timeout_s
        self._page_size = max(1, page_size)
        self._opener = opener or urllib.request.build_opener()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_seen: dict[int, str] = {}
        self._stats = SatNOGSPumpStats()

    @property
    def stats(self) -> SatNOGSPumpStats:
        return self._stats

    def add_sink(self, sink: Callable[[SatNOGSFrame], None]) -> None:
        self._sinks.append(sink)

    def add_decoder(self, decoder: SatNOGSDecoder) -> None:
        self._decoders.append(decoder)

    def poll_once(self) -> int:
        emitted = 0
        for norad_id in self._ids:
            emitted += self._poll_one(norad_id)
        self._stats.polls += 1
        return emitted

    def _poll_one(self, norad_id: int) -> int:
        params = {"satellite": str(norad_id), "page_size": str(self._page_size)}
        url = f"{SATNOGS_DB_BASE}/telemetry/?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Token {self._token}",
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with self._opener.open(req, timeout=self._timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            self._stats.http_errors += 1
            logger.warning(
                "satnogs_live.fetch_failed",
                norad=norad_id, error=str(exc),
            )
            return 0
        items = payload.get("results", payload) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            return 0
        emitted = 0
        last_seen_iso = self._last_seen.get(norad_id, "")
        new_last = last_seen_iso
        for item in items:
            if not isinstance(item, dict):
                continue
            ts = str(item.get("timestamp") or "")
            if not ts:
                continue
            if last_seen_iso and ts <= last_seen_iso:
                self._stats.duplicate_skipped += 1
                continue
            frame = self._build_frame(norad_id, item)
            if frame is None:
                continue
            self._dispatch(frame)
            emitted += 1
            if ts > new_last:
                new_last = ts
        if new_last and new_last != last_seen_iso:
            self._last_seen[norad_id] = new_last
        return emitted

    def _build_frame(
        self, norad_id: int, item: dict[str, Any],
    ) -> Optional[SatNOGSFrame]:
        ts = str(item.get("timestamp") or "")
        frame_hex = str(item.get("frame") or "")
        if not ts or not frame_hex:
            return None
        decoded: dict[str, Any] = {}
        for decoder in self._decoders:
            if decoder.norad_cat_ids and norad_id not in decoder.norad_cat_ids:
                continue
            try:
                decoded.update(
                    decoder.decode(SatNOGSFrame(
                        norad_cat_id=norad_id, timestamp_iso=ts,
                        frame_hex=frame_hex,
                    ))
                )
            except Exception as exc:
                self._stats.decode_errors += 1
                logger.warning(
                    "satnogs_live.decode_failed",
                    norad=norad_id, decoder=type(decoder).__name__, error=str(exc),
                )
        return SatNOGSFrame(
            norad_cat_id=norad_id,
            timestamp_iso=ts,
            frame_hex=frame_hex,
            observer=str(item.get("observer") or ""),
            transmitter_uuid=str(item.get("transmitter") or ""),
            decoded=decoded,
        )

    def _dispatch(self, frame: SatNOGSFrame) -> None:
        for sink in self._sinks:
            try:
                sink(frame)
            except Exception as exc:
                logger.warning(
                    "satnogs_live.sink_raised",
                    error=str(exc), sink=getattr(sink, "__name__", type(sink).__name__),
                )
        self._stats.frames_emitted += 1

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("pump already started")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="satnogs-live", daemon=True,
        )
        self._thread.start()
        logger.info(
            "satnogs_live.started", norads=list(self._ids),
            poll_interval_s=self._poll_interval_s,
        )

    def stop(self, *, timeout_s: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)
            self._thread = None
        logger.info("satnogs_live.stopped", stats=vars(self._stats))

    def _run_loop(self) -> None:
        backoff_index = 0
        while not self._stop.is_set():
            try:
                self.poll_once()
                backoff_index = 0
            except Exception as exc:
                logger.warning("satnogs_live.poll_loop_error", error=str(exc))
            wait_s = self._poll_interval_s
            if backoff_index < len(DEFAULT_BACKOFF_S):
                wait_s = max(wait_s, DEFAULT_BACKOFF_S[backoff_index])
                backoff_index += 1
            self._stop.wait(timeout=wait_s)
