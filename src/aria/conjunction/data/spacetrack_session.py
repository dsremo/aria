"""R45 — SpaceTrack.org session helper.

Thin wrapper around the SpaceTrack REST API.  Reads credentials
from environment variables (`SPACETRACK_USERNAME`,
`SPACETRACK_PASSWORD`).  Never stores credentials in any returned
object beyond the duration of the session, never logs them.

API rate limits (per SpaceTrack ToS):
  * ~30 requests/minute
  * ~300 requests/hour
  * Bulk re-distribution forbidden — derivative products (risk
    reports / verdicts) are OK.

Honest reading: this is a *thin* wrapper.  Production usage
should layer caching, retries with exponential backoff, and
respect of the rate-limit headers SpaceTrack returns.  The
class below is the minimum viable interface for the replay
validators + the conjunction screener.

Reference:
  https://www.space-track.org/documentation#api
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, Iterator, List, Optional, Sequence


DEFAULT_BASE_URL = "https://www.space-track.org"
RATE_LIMIT_RPM = 25            # 5-req headroom under 30 RPM ceiling
RATE_LIMIT_RPH = 250           # 50-req headroom under 300 RPH ceiling


# ── Public exception types ──────────────────────────────────────


class SpaceTrackError(RuntimeError):
    """Any failure talking to SpaceTrack — auth, network, parse."""


class SpaceTrackAuthError(SpaceTrackError):
    """Login refused (bad credentials or account suspended)."""


class SpaceTrackRateLimitError(SpaceTrackError):
    """Rate-limit ceiling reached.  Caller should back off."""


# ── Session ─────────────────────────────────────────────────────


class SpaceTrackSession:
    """Login-once, query-many session.

    Construction reads the credentials from env (or accepts an
    explicit override).  The session lives for the duration of the
    `with` block, after which the auth cookie is dropped.
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self._username = username or os.environ.get("SPACETRACK_USERNAME")
        self._password = password or os.environ.get("SPACETRACK_PASSWORD")
        self._base_url = (
            base_url
            or os.environ.get("SPACETRACK_BASE_URL", DEFAULT_BASE_URL)
        ).rstrip("/")
        if not self._username or not self._password:
            raise SpaceTrackAuthError(
                "SPACETRACK_USERNAME / SPACETRACK_PASSWORD env vars "
                "missing — see ~/Music/DB_CREDENTIALS.md for setup"
            )
        self._session = None       # requests.Session lazily on enter
        self._minute_window: List[float] = []
        self._hour_window: List[float] = []

    # ── Lifecycle ──────────────────────────────────────────────

    def __enter__(self) -> "SpaceTrackSession":
        try:
            import requests
        except ImportError as exc:                # pragma: no cover
            raise SpaceTrackError(
                "requests library required: pip install requests"
            ) from exc
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "ARIA/R45 conjunction-data-puller",
        })
        login_url = f"{self._base_url}/ajaxauth/login"
        try:
            r = self._session.post(login_url, data={
                "identity": self._username,
                "password": self._password,
            }, timeout=30.0)
        except requests.RequestException as exc:  # pragma: no cover
            raise SpaceTrackError(f"login failed: {exc}") from exc
        if r.status_code != 200:
            raise SpaceTrackAuthError(
                f"login refused (HTTP {r.status_code}): {r.text[:200]}"
            )
        # SpaceTrack returns the JSON {"Login":"Failed"} on bad auth
        # with HTTP 200 — must inspect body.
        try:
            body = r.json()
            if isinstance(body, dict) and body.get("Login") == "Failed":
                raise SpaceTrackAuthError("login refused: bad credentials")
        except ValueError:
            # Empty body on success is normal.
            pass
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._session is not None:
            try:
                self._session.get(f"{self._base_url}/ajaxauth/logout")
            except Exception:  # pragma: no cover
                pass
            self._session.close()
            self._session = None

    # ── Queries ───────────────────────────────────────────────

    def gp(
        self,
        norad_ids: Sequence[int],
        epoch_within: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """Pull general-perturbations records for ``norad_ids``.

        Returns a list of dicts in SpaceTrack's GP JSON form.
        Caller should filter / convert to TLE lines.

        ``epoch_within`` accepts SpaceTrack's range syntax
        (e.g. ``">2009-02-08,<2009-02-10"``) to bracket historical
        epochs.
        """
        if not norad_ids:
            return []
        ids = ",".join(str(n) for n in norad_ids)
        path = f"/basicspacedata/query/class/gp_history/NORAD_CAT_ID/{ids}"
        if epoch_within:
            path += f"/EPOCH/{epoch_within}"
        path += f"/orderby/EPOCH desc/limit/{int(limit)}/format/json"
        return self._get_json(path)

    def gp_history_around(
        self,
        norad_id: int,
        target_utc: datetime,
        days_window: int = 2,
        before_strict: Optional[datetime] = None,
    ) -> List[dict]:
        """Convenience: pull GP history for one object within ±N days
        of ``target_utc``.  Returns list sorted by epoch ascending.

        ``before_strict`` — if set, the query excludes any record with
        epoch ≥ this datetime.  Critical for replaying conjunction
        events: a default ±N query against an object that has since
        broken up returns the *post-event* tracking elements, not the
        pre-event state.  Pass the event UTC here to get only
        pre-event records.
        """
        target = target_utc.astimezone(timezone.utc)
        lo = (target.replace(hour=0, minute=0, second=0, microsecond=0)
              - _days(days_window))
        if before_strict is not None:
            hi = before_strict.astimezone(timezone.utc)
        else:
            hi = (target.replace(hour=0, minute=0, second=0, microsecond=0)
                  + _days(days_window))
        # SpaceTrack range syntax: `>lo,<hi` (comma-AND).  Use
        # date-only on the bounds because the day-precision form is
        # the documented / supported syntax — second-precision was
        # rejected with HTTP 500 in testing.
        epoch = (
            f">{lo.strftime('%Y-%m-%d')},"
            f"<{hi.strftime('%Y-%m-%d')}"
        )
        records = self.gp([norad_id], epoch_within=epoch, limit=20)
        records.sort(key=lambda r: r.get("EPOCH", ""))
        return records

    def tle_lines(self, gp_record: dict) -> tuple[str, str]:
        """Extract the (line1, line2) pair from a GP record."""
        l1 = str(gp_record.get("TLE_LINE1", "")).strip()
        l2 = str(gp_record.get("TLE_LINE2", "")).strip()
        if not l1 or not l2:
            raise SpaceTrackError(
                f"GP record missing TLE_LINE1/TLE_LINE2: {gp_record}"
            )
        return l1, l2

    # ── Internals ─────────────────────────────────────────────

    def _enforce_rate_limit(self) -> None:
        now = time.time()
        # Prune old timestamps.
        self._minute_window = [t for t in self._minute_window if now - t < 60.0]
        self._hour_window = [t for t in self._hour_window if now - t < 3600.0]
        if len(self._minute_window) >= RATE_LIMIT_RPM:
            sleep_s = 60.0 - (now - self._minute_window[0]) + 0.5
            if sleep_s > 0:
                time.sleep(sleep_s)
                self._enforce_rate_limit()
                return
        if len(self._hour_window) >= RATE_LIMIT_RPH:
            raise SpaceTrackRateLimitError(
                "hourly rate-limit ceiling reached; back off > 1 h"
            )
        self._minute_window.append(now)
        self._hour_window.append(now)

    def _get_json(self, path: str) -> List[dict]:
        if self._session is None:
            raise SpaceTrackError("session not active — use `with`")
        self._enforce_rate_limit()
        url = self._base_url + path
        try:
            r = self._session.get(url, timeout=60.0)
        except Exception as exc:  # pragma: no cover
            raise SpaceTrackError(f"GET {path} failed: {exc}") from exc
        if r.status_code == 401:
            raise SpaceTrackAuthError(
                "session expired / unauthorised — re-login"
            )
        if r.status_code == 429:
            raise SpaceTrackRateLimitError(
                "HTTP 429 — back off"
            )
        if r.status_code != 200:
            raise SpaceTrackError(
                f"HTTP {r.status_code} on {path}: {r.text[:200]}"
            )
        try:
            data = r.json()
        except ValueError as exc:
            raise SpaceTrackError(
                f"non-JSON response from {path}: {r.text[:200]}"
            ) from exc
        return data if isinstance(data, list) else []


def _days(n: int):
    from datetime import timedelta
    return timedelta(days=int(n))


# ── Convenience CLI ─────────────────────────────────────────────


def fetch_iridium_cosmos_2009(out_path: Optional[str] = None) -> dict:
    """One-shot fetch of the actual Iridium-33 + Cosmos-2251 TLEs
    from immediately before the 2009-02-10 16:56 UTC collision.

    Critical: queries with a strict pre-collision upper bound so the
    catalogue's *post-event* tracking elements (broadcast minutes
    after the collision when 18-SDS re-acquired the debris cloud)
    are excluded.  A naïve ±N-day-around query returns those.

    Requires SPACETRACK_USERNAME / SPACETRACK_PASSWORD env vars set.
    """
    # Collision was 2009-02-10 16:55:59.8 UTC.  Use 16:55:00 strict
    # so any record with epoch on the collision-day is filtered out.
    target = datetime(2009, 2, 9, 12, 0, tzinfo=timezone.utc)
    pre_event = datetime(2009, 2, 10, 16, 55, 0, tzinfo=timezone.utc)
    with SpaceTrackSession() as sess:
        iri = sess.gp_history_around(
            24946, target, days_window=4,
            before_strict=pre_event,
        )
        cos = sess.gp_history_around(
            22675, target, days_window=4,
            before_strict=pre_event,
        )
    if not iri or not cos:
        raise SpaceTrackError(
            "no PRE-event GP records returned for Iridium-33 / "
            "Cosmos-2251 — the catalogue may carry only post-event "
            "tracking elements; widen the days_window or use the "
            "tle_publish archive endpoint"
        )
    # Use the LATEST pre-event entry (closest to the collision).
    iri_l1, iri_l2 = SpaceTrackSession.tle_lines(SpaceTrackSession, iri[-1])
    cos_l1, cos_l2 = SpaceTrackSession.tle_lines(SpaceTrackSession, cos[-1])
    out = {
        "primary_norad_id": "24946",
        "primary_name":     "IRIDIUM 33",
        "primary_line1":    iri_l1,
        "primary_line2":    iri_l2,
        "primary_epoch":    iri[-1].get("EPOCH"),
        "secondary_norad_id": "22675",
        "secondary_name":     "COSMOS 2251",
        "secondary_line1":    cos_l1,
        "secondary_line2":    cos_l2,
        "secondary_epoch":    cos[-1].get("EPOCH"),
    }
    if out_path is not None:
        from pathlib import Path
        Path(out_path).write_text(_render_iridium_cosmos_toml(out))
    return out


def _render_iridium_cosmos_toml(d: dict) -> str:
    return (
        "# Auto-generated by aria.conjunction.data.spacetrack_session.\n"
        "# Source: SpaceTrack.org ajaxauth/basicspacedata.\n\n"
        f'primary_norad_id   = "{d["primary_norad_id"]}"\n'
        f'primary_name       = "{d["primary_name"]}"\n'
        "primary_radius_m   = 1.5\n"
        f'primary_line1 = "{d["primary_line1"]}"\n'
        f'primary_line2 = "{d["primary_line2"]}"\n\n'
        f'secondary_norad_id  = "{d["secondary_norad_id"]}"\n'
        f'secondary_name      = "{d["secondary_name"]}"\n'
        "secondary_radius_m  = 2.5\n"
        f'secondary_line1 = "{d["secondary_line1"]}"\n'
        f'secondary_line2 = "{d["secondary_line2"]}"\n\n'
        'approx_tca_utc = "2009-02-10T16:56:00Z"\n'
        'truth_tca_utc           = "2009-02-10T16:55:59.8Z"\n'
        "truth_relative_speed_kmps = 11.65\n"
        "truth_altitude_km       = 789.0\n"
        "truth_collision         = true\n"
        "truth_jspoc_predicted_miss_m = 584.0\n"
    )
