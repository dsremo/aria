from __future__ import annotations

import io
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from aria.conjunction.data.celestrak_client import (
    CelestrakClient,
    CelestrakError,
)


SAMPLE_TLE = (
    "ISS (ZARYA)\n"
    "1 25544U 98067A   24001.00000000  .00010000  00000+0  18000-3 0  9999\n"
    "2 25544  51.6400 100.0000 0001000  90.0000 270.0000 15.50000000123454\n"
)


def _mock_resp(body: str):
    resp = MagicMock()
    resp.read.return_value = body.encode("utf-8")
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=None)
    return resp


class TestFetchGroup:
    def test_success(self):
        opener = MagicMock()
        opener.open.return_value = _mock_resp(SAMPLE_TLE)
        client = CelestrakClient(opener=opener)
        response = client.fetch_group("active")
        assert response.group == "active"
        assert "ISS" in response.raw_text
        assert response.n_lines == 3

    def test_empty_response_rejected(self):
        opener = MagicMock()
        opener.open.return_value = _mock_resp("")
        client = CelestrakClient(opener=opener)
        with pytest.raises(CelestrakError, match="empty|fetch"):
            client.fetch_group("active")

    def test_html_response_rejected_as_throttled(self):
        opener = MagicMock()
        opener.open.return_value = _mock_resp(
            "<html><body>Too many requests</body></html>"
        )
        client = CelestrakClient(opener=opener)
        with pytest.raises(CelestrakError, match="HTML|fetch"):
            client.fetch_group("active")

    def test_url_error_retried_then_raises(self):
        opener = MagicMock()
        opener.open.side_effect = urllib.error.URLError("connection refused")
        client = CelestrakClient(opener=opener)
        with patch("aria.conjunction.data.celestrak_client.time.sleep"):
            with pytest.raises(CelestrakError, match="failed after retries"):
                client.fetch_group("active")
        assert opener.open.call_count == 3

    def test_user_agent_header_included(self):
        opener = MagicMock()
        opener.open.return_value = _mock_resp(SAMPLE_TLE)
        client = CelestrakClient(opener=opener, user_agent="custom-test-agent")
        client.fetch_group("active")
        request_arg = opener.open.call_args.args[0]
        assert request_arg.get_header("User-agent") == "custom-test-agent"

    def test_fetch_groups_collects_successes_and_skips_failures(self):
        opener = MagicMock()
        side_effects = [
            _mock_resp(SAMPLE_TLE),
            urllib.error.URLError("boom"),
            urllib.error.URLError("boom"),
            urllib.error.URLError("boom"),
        ]
        opener.open.side_effect = side_effects
        client = CelestrakClient(opener=opener)
        with patch("aria.conjunction.data.celestrak_client.time.sleep"):
            results = client.fetch_groups(["active", "starlink"])
        assert "active" in results
        assert "starlink" not in results
