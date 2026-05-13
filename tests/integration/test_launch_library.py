"""Launch Library 2 integration tests.

The tests do NOT hit the live LL2 endpoint — that would burn the
15/hr anonymous rate limit and make CI flaky. Instead they patch
the underlying ``urllib.request.urlopen`` to return canned JSON
that mirrors the documented LL2 response shape.

A separate, opt-in test (gated on ``ARIA_RUN_LIVE_BACKTESTS=1``)
exercises the real upstream when an operator wants live-mode
verification.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from aria.integrations import launch_library as ll_mod


# ── Fixture: canned LL2 response (docs-shape compatible) ────────


_FAKE_LL2_PAYLOAD = {
    "count": 2,
    "next": None,
    "previous": None,
    "results": [
        {
            "id": "abc-123",
            "name": "Falcon 9 Block 5 | Starlink Group 7-99",
            "net": "2026-05-01T12:34:56Z",
            "status": {"name": "GO", "id": 1},
            "launch_service_provider": {"name": "SpaceX", "id": 121},
            "rocket": {
                "id": 11,
                "configuration": {"name": "Falcon 9 Block 5", "id": 164},
            },
            "mission": {
                "name": "Starlink Group 7-99",
                "orbit": {"name": "LEO", "id": 8},
            },
            "pad": {
                "name": "Space Launch Complex 4E",
                "latitude": "34.6",
                "longitude": "-120.6",
            },
        },
        {
            "id": "def-456",
            "name": "GSLV Mk III | LVM3-M5",
            "net": "2026-05-03T09:00:00Z",
            "status": {"name": "TBC", "id": 8},
            "launch_service_provider": {"name": "ISRO", "id": 31},
            "rocket": {
                "id": 17,
                "configuration": {"name": "GSLV Mk III", "id": 88},
            },
            "mission": {
                "name": "LVM3-M5 mission",
                "orbit": {"name": "GTO", "id": 2},
            },
            "pad": {
                "name": "Satish Dhawan Space Centre Second Launch Pad",
                "latitude": "13.7",
                "longitude": "80.2",
            },
        },
    ],
}


@pytest.fixture
def isolated_client(tmp_path: Path):
    """Return a fresh client with a temp cache dir."""
    ll_mod.reset_for_test()
    return ll_mod.LaunchLibraryClient(cache_dir=tmp_path / "cache")


def _mock_urlopen_response(payload: dict):
    """Build a context-manager mock that returns a canned response."""
    body = json.dumps(payload).encode("utf-8")
    response = io.BytesIO(body)
    response.status = 200

    class _Ctx:
        def __enter__(self):
            return response
        def __exit__(self, *_):
            return False

    return _Ctx()


# ── Parse + normalize the LL2 payload ────────────────────────────


class TestUpcomingLaunchParser:
    def test_parses_two_launches_from_canned_payload(
        self, isolated_client,
    ):
        with patch.object(
            ll_mod.request, "urlopen",
            return_value=_mock_urlopen_response(_FAKE_LL2_PAYLOAD),
        ):
            launches = isolated_client.upcoming(limit=10)
        assert len(launches) == 2

    def test_first_launch_fields_match_canned(self, isolated_client):
        with patch.object(
            ll_mod.request, "urlopen",
            return_value=_mock_urlopen_response(_FAKE_LL2_PAYLOAD),
        ):
            launches = isolated_client.upcoming(limit=10)
        first = launches[0]
        assert first.launch_id == "abc-123"
        assert first.name == "Falcon 9 Block 5 | Starlink Group 7-99"
        assert first.net_iso == "2026-05-01T12:34:56Z"
        assert first.status == "GO"
        assert first.provider == "SpaceX"
        assert first.rocket_name == "Falcon 9 Block 5"
        assert first.mission_name == "Starlink Group 7-99"
        assert first.mission_orbit == "LEO"
        assert first.pad_lat_deg == pytest.approx(34.6)
        assert first.pad_lon_deg == pytest.approx(-120.6)

    def test_second_launch_isro_provider(self, isolated_client):
        with patch.object(
            ll_mod.request, "urlopen",
            return_value=_mock_urlopen_response(_FAKE_LL2_PAYLOAD),
        ):
            launches = isolated_client.upcoming(limit=10)
        assert launches[1].provider == "ISRO"
        assert launches[1].mission_orbit == "GTO"

    def test_partial_payload_does_not_break_batch(
        self, isolated_client,
    ):
        # One row missing nested fields — should be skipped, not crash.
        partial = {
            "count": 2,
            "results": [
                _FAKE_LL2_PAYLOAD["results"][0],
                {"id": "broken-row"},  # no name, no rocket, no provider
            ],
        }
        with patch.object(
            ll_mod.request, "urlopen",
            return_value=_mock_urlopen_response(partial),
        ):
            launches = isolated_client.upcoming(limit=10)
        # Either both parse with empty fields or broken one is skipped — either is fine.
        assert len(launches) >= 1
        assert launches[0].launch_id == "abc-123"


# ── Cache behaviour ──────────────────────────────────────────────


class TestCacheBehaviour:
    def test_second_call_within_ttl_skips_network(self, isolated_client):
        call_count = {"n": 0}
        original_urlopen = ll_mod.request.urlopen

        def _counting_urlopen(*args, **kwargs):
            call_count["n"] += 1
            return _mock_urlopen_response(_FAKE_LL2_PAYLOAD)

        with patch.object(ll_mod.request, "urlopen", side_effect=_counting_urlopen):
            isolated_client.upcoming(limit=10)
            isolated_client.upcoming(limit=10)
        assert call_count["n"] == 1, (
            f"Cache miss: expected 1 network call, got {call_count['n']}"
        )

    def test_cache_expires_after_ttl(self, isolated_client):
        call_count = {"n": 0}

        def _counting_urlopen(*args, **kwargs):
            call_count["n"] += 1
            return _mock_urlopen_response(_FAKE_LL2_PAYLOAD)

        # Force TTL to 0 so the cache is immediately stale.
        isolated_client.cache_ttl_s = 0.0
        with patch.object(ll_mod.request, "urlopen", side_effect=_counting_urlopen):
            isolated_client.upcoming(limit=10)
            isolated_client.upcoming(limit=10)
        assert call_count["n"] == 2

    def test_cache_persists_across_client_instances(self, tmp_path):
        cache_dir = tmp_path / "cache"
        client1 = ll_mod.LaunchLibraryClient(cache_dir=cache_dir)
        with patch.object(
            ll_mod.request, "urlopen",
            return_value=_mock_urlopen_response(_FAKE_LL2_PAYLOAD),
        ):
            client1.upcoming(limit=10)
        # Fresh client, same cache dir.
        client2 = ll_mod.LaunchLibraryClient(cache_dir=cache_dir)
        with patch.object(
            ll_mod.request, "urlopen",
            side_effect=AssertionError("client2 should hit cache, not network"),
        ):
            launches = client2.upcoming(limit=10)
        assert len(launches) == 2


# ── Error handling ───────────────────────────────────────────────


class TestErrorHandling:
    def test_rate_limit_raises_actionable_error(self, isolated_client):
        from urllib.error import HTTPError

        def _raise_429(*args, **kwargs):
            raise HTTPError(
                url="x", code=429, msg="Too Many Requests",
                hdrs=None, fp=None,
            )

        with patch.object(ll_mod.request, "urlopen", side_effect=_raise_429):
            with pytest.raises(RuntimeError, match="rate-limit"):
                isolated_client.upcoming(limit=10)

    def test_invalid_limit_rejected(self, isolated_client):
        with pytest.raises(ValueError, match="limit must be"):
            isolated_client.upcoming(limit=0)
        with pytest.raises(ValueError, match="limit must be"):
            isolated_client.upcoming(limit=999)


# ── Module-level singleton ───────────────────────────────────────


def test_get_launch_library_client_is_singleton(monkeypatch):
    monkeypatch.delenv("ARIA_LL2_API_KEY", raising=False)
    ll_mod.reset_for_test()
    a = ll_mod.get_launch_library_client()
    b = ll_mod.get_launch_library_client()
    assert a is b


def test_api_key_picked_up_from_env(monkeypatch):
    monkeypatch.setenv("ARIA_LL2_API_KEY", "test-key-deadbeef")
    ll_mod.reset_for_test()
    client = ll_mod.get_launch_library_client()
    assert client.api_key == "test-key-deadbeef"


# ── Live-mode probe (opt-in only) ────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("ARIA_RUN_LIVE_BACKTESTS") != "1",
    reason="live LL2 burns rate-limit budget; gated on ARIA_RUN_LIVE_BACKTESTS=1",
)
def test_live_lll2_returns_at_least_one_launch(tmp_path):
    """Opt-in live probe — operator can run with
    ``ARIA_RUN_LIVE_BACKTESTS=1 pytest -k test_live_lll2`` to verify
    the integration against the real upstream."""
    client = ll_mod.LaunchLibraryClient(cache_dir=tmp_path / "live_cache")
    launches = client.upcoming(limit=5)
    assert len(launches) >= 1
    assert all(launch.launch_id for launch in launches)
    assert all(launch.name for launch in launches)
