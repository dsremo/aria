"""
Space-Track.org API client.

Handles authentication, rate limiting, and bulk TLE/CDM fetching.
Rate limits: 30 requests/minute, 300 requests/hour.
"""

from __future__ import annotations

import logging
import time

import httpx

from aria.conjunction.core.types import SpaceObject
from aria.conjunction.data.tle_parser import TLEParser

logger = logging.getLogger(__name__)

BASE_URL = "https://www.space-track.org"
AUTH_URL = f"{BASE_URL}/ajaxauth/login"
TLE_URL = f"{BASE_URL}/basicspacedata/query"


class SpaceTrackError(Exception):
    """Raised on Space-Track API errors."""


class RateLimiter:
    """Simple token-bucket rate limiter for Space-Track compliance."""

    def __init__(self, max_per_minute: int = 30, max_per_hour: int = 300):
        self._max_per_minute = max_per_minute
        self._max_per_hour = max_per_hour
        self._minute_timestamps: list[float] = []
        self._hour_timestamps: list[float] = []

    def wait_if_needed(self) -> None:
        """Block until a request is allowed."""
        now = time.monotonic()

        # Prune old timestamps
        self._minute_timestamps = [t for t in self._minute_timestamps if now - t < 60]
        self._hour_timestamps = [t for t in self._hour_timestamps if now - t < 3600]

        # Check minute limit
        if len(self._minute_timestamps) >= self._max_per_minute:
            sleep_time = 60 - (now - self._minute_timestamps[0])
            if sleep_time > 0:
                logger.info(f"Rate limit: sleeping {sleep_time:.1f}s (minute limit)")
                time.sleep(sleep_time)

        # Check hour limit
        if len(self._hour_timestamps) >= self._max_per_hour:
            sleep_time = 3600 - (now - self._hour_timestamps[0])
            if sleep_time > 0:
                logger.info(f"Rate limit: sleeping {sleep_time:.1f}s (hour limit)")
                time.sleep(sleep_time)

        now = time.monotonic()
        self._minute_timestamps.append(now)
        self._hour_timestamps.append(now)


class SpaceTrackClient:
    """Client for the Space-Track.org REST API.

    Usage:
        client = SpaceTrackClient("user@email.com", "password")
        objects = client.fetch_tle_latest(norad_ids=[25544, 48274])
    """

    def __init__(self, identity: str, password: str, timeout: float = 30.0):
        self._identity = identity
        self._password = password
        self._client = httpx.Client(timeout=timeout, follow_redirects=True)
        self._rate_limiter = RateLimiter()
        self._authenticated = False

    def _authenticate(self) -> None:
        """Authenticate with Space-Track and store session cookie."""
        resp = self._client.post(
            AUTH_URL,
            data={"identity": self._identity, "password": self._password},
        )
        if resp.status_code != 200 or "Login Failed" in resp.text:
            raise SpaceTrackError(f"Authentication failed: {resp.status_code}")
        self._authenticated = True
        logger.info("Authenticated with Space-Track.org")

    def _request(self, url: str) -> str:
        """Make a rate-limited, authenticated request."""
        if not self._authenticated:
            self._authenticate()

        self._rate_limiter.wait_if_needed()
        resp = self._client.get(url)

        if resp.status_code == 401:
            # Session expired — re-authenticate and retry
            self._authenticate()
            self._rate_limiter.wait_if_needed()
            resp = self._client.get(url)

        if resp.status_code != 200:
            raise SpaceTrackError(f"Request failed: {resp.status_code} — {url}")

        return resp.text

    def fetch_tle_latest(
        self,
        norad_ids: list[int] | None = None,
        epoch_days_ago: int = 30,
        limit: int = 1000,
    ) -> list[SpaceObject]:
        """Fetch latest TLEs for specified NORAD IDs or recent objects.

        Args:
            norad_ids: Specific NORAD IDs (comma-delimited in API call for efficiency)
            epoch_days_ago: Only fetch TLEs with epoch within this many days
            limit: Maximum number of results

        Returns:
            List of SpaceObject with parsed TLEs
        """
        if norad_ids:
            # Comma-delimited for single API call (Space-Track best practice)
            id_str = ",".join(str(i) for i in norad_ids)
            url = (
                f"{TLE_URL}/class/tle_latest/NORAD_CAT_ID/{id_str}"
                f"/ORDINAL/1/orderby/NORAD_CAT_ID asc/format/3le"
            )
        else:
            url = (
                f"{TLE_URL}/class/tle_latest"
                f"/EPOCH/>now-{epoch_days_ago}/ORDINAL/1"
                f"/orderby/NORAD_CAT_ID asc/limit/{limit}/format/3le"
            )

        tle_text = self._request(url)
        return TLEParser.parse_multi_tle(tle_text)

    def fetch_catalog_tle(
        self,
        object_type: str = "DEBRIS",
        epoch_days_ago: int = 7,
        limit: int = 5000,
    ) -> list[SpaceObject]:
        """Fetch TLEs for a category of objects (DEBRIS, PAYLOAD, ROCKET BODY).

        Args:
            object_type: "DEBRIS", "PAYLOAD", or "ROCKET BODY"
            epoch_days_ago: TLE freshness filter
            limit: Max results
        """
        url = (
            f"{TLE_URL}/class/tle_latest"
            f"/OBJECT_TYPE/{object_type}"
            f"/EPOCH/>now-{epoch_days_ago}/ORDINAL/1"
            f"/orderby/NORAD_CAT_ID asc/limit/{limit}/format/3le"
        )
        tle_text = self._request(url)
        return TLEParser.parse_multi_tle(tle_text)

    def fetch_gp_data(self, norad_ids: list[int]) -> list[dict]:
        """Fetch General Perturbations data in JSON format (richer than TLE).

        Includes object name, type, RCS size, country, launch date, etc.
        """
        id_str = ",".join(str(i) for i in norad_ids)
        url = (
            f"{TLE_URL}/class/gp/NORAD_CAT_ID/{id_str}"
            f"/orderby/NORAD_CAT_ID asc/format/json"
        )
        import json

        return json.loads(self._request(url))

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
