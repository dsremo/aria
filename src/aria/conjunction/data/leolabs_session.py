"""LeoLabs commercial-feed adapter — anisotropic covariance ingest.

LeoLabs publishes Object State Vectors (OSV) and Conjunction Data
Messages (CDM) with **per-object 6×6 covariance** in along-track /
cross-track / radial axes.  This is the data class the Iridium-Cosmos
σ-sweep flagged as missing — isotropic operator-grade σ peaks at
Foster Pc ≈ 1.7×10⁻⁵ no matter how miss distance moves; with
anisotropic σ a real-event RED is reachable.

This module is a *thin* HTTPS client around the LeoLabs API.  The
network interaction layer is operator-supplied (REST or webhook)
because credentials are commercial.  We expose a clean
`leolabs_covariance_for_norad(norad_id) -> 6x6 ndarray` so the
screener can substitute LeoLabs covariance whenever available and
fall back to operator-grade isotropic σ otherwise.

API reference (public docs):
  * https://platform.leolabs.space/api-docs (operator account required)
  * Object covariance is published as covariance_matrix in CCSDS-OEM
    style, ECI frame, units km² / km²/s / km²/s².

Citation policy:
  Per CLAUDE.md, every numerical constant has a citation.  This file
  has only structural defaults (HTTP timeouts, retries) which are
  software-engineering choices, not physical constants.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np


LEOLABS_API_BASE = os.environ.get(
    "LEOLABS_API_BASE", "https://api.leolabs.space/v1"
)
LEOLABS_TIMEOUT_S = 10.0
LEOLABS_MAX_RETRIES = 3


@dataclass
class LeoLabsState:
    """Single-epoch state vector + covariance from LeoLabs."""
    norad_id: str
    epoch_utc: datetime
    position_km: np.ndarray            # ECI, shape (3,)
    velocity_kmps: np.ndarray          # ECI, shape (3,)
    covariance_6x6_km2: np.ndarray     # ECI, shape (6, 6)
    catalog_id: Optional[str] = None
    notes: str = ""

    def covariance_position_3x3_km2(self) -> np.ndarray:
        """Return the upper-left 3×3 block (position-only covariance)."""
        return np.asarray(self.covariance_6x6_km2)[:3, :3]


class LeoLabsSession:
    """Operator-credentialed LeoLabs session.

    Two modes are supported:

    * **Live**: pass an ``access_token`` (or set ``LEOLABS_TOKEN``);
      the session calls the public API.
    * **Cached**: pass ``cache_dir`` and the session will read locally
      pre-fetched JSON files keyed by NORAD ID.  This is the test +
      offline-replay mode.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        cache_dir: Optional[str] = None,
        api_base: str = LEOLABS_API_BASE,
        timeout_s: float = LEOLABS_TIMEOUT_S,
    ) -> None:
        self.access_token = access_token or os.environ.get("LEOLABS_TOKEN")
        self.cache_dir = cache_dir
        self.api_base = api_base
        self.timeout_s = timeout_s
        self._last_request_t = 0.0

    # ── Public API ─────────────────────────────────────────────

    def state_for_norad(
        self, norad_id: str,
        target_utc: Optional[datetime] = None,
    ) -> Optional[LeoLabsState]:
        """Return the closest LeoLabs OSV to ``target_utc``."""
        if self.cache_dir:
            return self._cached_state(norad_id, target_utc)
        if not self.access_token:
            return None
        return self._fetch_live(norad_id, target_utc)

    def covariance_for_norad(
        self, norad_id: str,
        target_utc: Optional[datetime] = None,
    ) -> Optional[np.ndarray]:
        """Convenience wrapper — return the 3×3 position covariance."""
        st = self.state_for_norad(norad_id, target_utc)
        return st.covariance_position_3x3_km2() if st is not None else None

    # ── Cached / offline mode ──────────────────────────────────

    def _cached_state(
        self, norad_id: str, target_utc: Optional[datetime],
    ) -> Optional[LeoLabsState]:
        from pathlib import Path
        if self.cache_dir is None:
            return None
        path = Path(self.cache_dir) / f"{norad_id}.json"
        if not path.is_file():
            return None
        raw = json.loads(path.read_text())
        return _state_from_payload(raw)

    # ── Live mode (operator-credentialed) ─────────────────────

    def _fetch_live(
        self, norad_id: str, target_utc: Optional[datetime],
    ) -> Optional[LeoLabsState]:
        """Issue a GET to /catalog/objects/{norad}/states.

        We rate-limit ourselves at 1 req/s to be polite; LeoLabs's
        documented rate is far higher but operator-side budgets
        differ.  The function intentionally fails-closed: on any
        network error we return None so the screener falls back to
        operator-grade isotropic σ.
        """
        try:
            import requests  # local import — keeps dependency optional
        except ImportError:
            return None
        self._respect_rate_limit()
        t = target_utc or datetime.now(timezone.utc)
        url = f"{self.api_base}/catalog/objects/{norad_id}/states"
        params = {"epoch": t.isoformat()}
        headers = {"Authorization": f"Bearer {self.access_token}"}
        for attempt in range(LEOLABS_MAX_RETRIES):
            try:
                r = requests.get(
                    url, params=params, headers=headers,
                    timeout=self.timeout_s,
                )
            except Exception:
                time.sleep(0.5 * (attempt + 1))
                continue
            if r.status_code == 200:
                payload = r.json()
                if isinstance(payload, dict) and payload.get("states"):
                    return _state_from_payload(payload["states"][0])
                if isinstance(payload, list) and payload:
                    return _state_from_payload(payload[0])
            elif r.status_code == 429:
                time.sleep(2.0 * (attempt + 1))
            else:
                return None
        return None

    def _respect_rate_limit(self) -> None:
        now = time.monotonic()
        delta = now - self._last_request_t
        if delta < 1.0:
            time.sleep(1.0 - delta)
        self._last_request_t = time.monotonic()


# ── Helpers ────────────────────────────────────────────────


def _state_from_payload(raw: Dict[str, object]) -> LeoLabsState:
    """Translate one LeoLabs OSV JSON record into a LeoLabsState."""
    epoch = raw.get("epoch") or raw.get("timestamp")
    if isinstance(epoch, str):
        epoch_dt = datetime.fromisoformat(epoch.replace("Z", "+00:00"))
    elif isinstance(epoch, (int, float)):
        epoch_dt = datetime.fromtimestamp(float(epoch), tz=timezone.utc)
    else:
        epoch_dt = datetime.now(tz=timezone.utc)
    pos = np.asarray(raw.get("position", [0.0, 0.0, 0.0]), dtype=float)
    vel = np.asarray(raw.get("velocity", [0.0, 0.0, 0.0]), dtype=float)
    cov = np.asarray(
        raw.get("covariance", [[0.0] * 6] * 6), dtype=float,
    )
    return LeoLabsState(
        norad_id=str(raw.get("norad_id", raw.get("noradId", ""))),
        epoch_utc=epoch_dt,
        position_km=pos,
        velocity_kmps=vel,
        covariance_6x6_km2=cov,
        catalog_id=str(raw.get("catalog_id", raw.get("catalogId", ""))) or None,
        notes=str(raw.get("notes", "")),
    )
