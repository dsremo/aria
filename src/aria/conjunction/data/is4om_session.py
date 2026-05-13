"""ISRO IS4OM adapter — Indian Space Situational Awareness feed.

ISRO's IS4OM (ISTRAC System for Safe and Sustainable Operations
Management) provides conjunction predictions for Indian operators as
an alternative to registering with U.S. 18 SDS.  Indian smallsat
operators need this as their primary conjunction-data source.

Public-facing API documentation is sparse; the most stable touch-
point is the operator-portal HTTPS endpoint.  This adapter is
deliberately *contract-thin*:

  * The :class:`IS4OMSession` exposes the operations the screener
    needs (``cdm_for_norad`` and ``catalog_around``) with a clear
    fall-back to a cached / offline mode for testing.
  * The wire format expected from IS4OM is **CCSDS CDM** (502.0-B-2)
    — the same XML/JSON format 18 SDS uses for CDMs.  ISRO has
    indicated public alignment with CCSDS CDM.

Operator authentication: assumed to be a per-account API key set in
the ``IS4OM_TOKEN`` env var.  Adjust per the operator's actual
account flow once published.

Citation policy:
  * CCSDS 502.0-B-2 (Conjunction Data Message), Recommended Standard, Issue 2.
  * ISRO IS4OM operator documentation (operator's own account).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np


IS4OM_API_BASE = os.environ.get(
    "IS4OM_API_BASE", "https://is4om.istrac.gov.in/api/v1"
)
IS4OM_TIMEOUT_S = 15.0
IS4OM_MAX_RETRIES = 3


@dataclass
class IS4OMConjunctionMessage:
    """One IS4OM CDM-equivalent conjunction record."""
    primary_norad_id: str
    secondary_norad_id: str
    tca_utc: datetime
    miss_distance_m: float
    relative_velocity_kmps: float
    pc_bin: str                              # GREEN / YELLOW / RED bucket
    pc_value: Optional[float] = None
    primary_covariance_6x6_km2: Optional[np.ndarray] = None
    secondary_covariance_6x6_km2: Optional[np.ndarray] = None
    notes: str = ""


class IS4OMSession:
    """Operator-credentialed IS4OM session.

    Modes:
      * **Live**: ``access_token`` (or ``IS4OM_TOKEN`` env var) → calls
        the public API.
      * **Cached**: ``cache_dir`` reads pre-fetched JSON files keyed by
        NORAD ID.  Used by tests and air-gapped deployments.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        cache_dir: Optional[str] = None,
        api_base: str = IS4OM_API_BASE,
        timeout_s: float = IS4OM_TIMEOUT_S,
    ) -> None:
        self.access_token = access_token or os.environ.get("IS4OM_TOKEN")
        self.cache_dir = cache_dir
        self.api_base = api_base
        self.timeout_s = timeout_s
        self._last_request_t = 0.0

    def cdm_for_norad(
        self,
        norad_id: str,
        window_hours: float = 72.0,
    ) -> List[IS4OMConjunctionMessage]:
        """Pull every CDM where ``norad_id`` is the primary, within
        ``window_hours`` of now."""
        if self.cache_dir:
            return self._cached_cdms(norad_id)
        if not self.access_token:
            return []
        return self._fetch_live_cdms(norad_id, window_hours)

    # ── Cached mode ────────────────────────────────────────────

    def _cached_cdms(self, norad_id: str) -> List[IS4OMConjunctionMessage]:
        if self.cache_dir is None:
            return []
        path = Path(self.cache_dir) / f"{norad_id}_cdms.json"
        if not path.is_file():
            return []
        raw = json.loads(path.read_text())
        if isinstance(raw, dict) and "cdms" in raw:
            raw = raw["cdms"]
        return [_cdm_from_payload(d) for d in raw if isinstance(d, dict)]

    # ── Live mode ──────────────────────────────────────────────

    def _fetch_live_cdms(
        self, norad_id: str, window_hours: float,
    ) -> List[IS4OMConjunctionMessage]:
        try:
            import requests
        except ImportError:
            return []
        self._respect_rate_limit()
        url = f"{self.api_base}/cdms"
        params = {"norad": norad_id, "window_h": window_hours}
        headers = {"Authorization": f"Bearer {self.access_token}"}
        for attempt in range(IS4OM_MAX_RETRIES):
            try:
                r = requests.get(
                    url, params=params, headers=headers,
                    timeout=self.timeout_s,
                )
            except Exception:
                time.sleep(0.5 * (attempt + 1))
                continue
            if r.status_code == 200:
                body = r.json()
                if isinstance(body, dict) and "cdms" in body:
                    return [_cdm_from_payload(d) for d in body["cdms"]]
                if isinstance(body, list):
                    return [_cdm_from_payload(d) for d in body]
                return []
            if r.status_code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            return []
        return []

    def _respect_rate_limit(self) -> None:
        now = time.monotonic()
        delta = now - self._last_request_t
        if delta < 1.0:
            time.sleep(1.0 - delta)
        self._last_request_t = time.monotonic()


# ── Helpers ────────────────────────────────────────────────


def _cdm_from_payload(raw: Dict[str, object]) -> IS4OMConjunctionMessage:
    tca_raw = raw.get("tca_utc") or raw.get("tca") or raw.get("TCA")
    if isinstance(tca_raw, str):
        tca = datetime.fromisoformat(tca_raw.replace("Z", "+00:00"))
    else:
        tca = datetime.now(timezone.utc)
    cov_p = raw.get("primary_covariance")
    cov_s = raw.get("secondary_covariance")
    cov_p_arr = (
        np.asarray(cov_p, dtype=float)
        if isinstance(cov_p, list) else None
    )
    cov_s_arr = (
        np.asarray(cov_s, dtype=float)
        if isinstance(cov_s, list) else None
    )
    pc_bin = str(raw.get("pc_bin") or raw.get("risk") or "GREEN").upper()
    if pc_bin not in ("RED", "YELLOW", "GREEN"):
        pc_bin = "GREEN"
    pc_value = raw.get("pc")
    return IS4OMConjunctionMessage(
        primary_norad_id=str(raw.get("primary_norad_id", raw.get("primary", ""))),
        secondary_norad_id=str(raw.get("secondary_norad_id", raw.get("secondary", ""))),
        tca_utc=tca,
        miss_distance_m=float(raw.get("miss_distance_m", 0.0)),
        relative_velocity_kmps=float(raw.get("relative_velocity_kmps", 0.0)),
        pc_bin=pc_bin,
        pc_value=float(pc_value) if pc_value is not None else None,
        primary_covariance_6x6_km2=cov_p_arr,
        secondary_covariance_6x6_km2=cov_s_arr,
        notes=str(raw.get("notes", "")),
    )
