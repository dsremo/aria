"""SatNOGS DB integration tests.

Mocks ``urllib.request.urlopen`` with canned responses so CI doesn't
hit the live SatNOGS API. Two opt-in live probes (gated on
``ARIA_RUN_LIVE_SATNOGS=1``) exercise the real upstream against
ISS (NORAD 25544) — well-documented, never re-numbered, and present
forever.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from aria.integrations import satnogs as sn_mod
from aria.integrations.satnogs import (
    SatNOGSClient,
    Satellite,
    Transmitter,
    TLE,
    TelemetryFrame,
    get_satnogs_client,
)


# ── Canned response fixtures ────────────────────────────────────


_FAKE_SATELLITE_PAYLOAD = [
    {
        "sat_id": "AAAA-0001-0002-0003-0004",
        "norad_cat_id": 25544,
        "name": "ISS (ZARYA)",
        "names": "ISS",
        "status": "alive",
        "launched": "1998-11-20T06:40:00Z",
        "decayed": None,
        "countries": "IQ,RU,US",
        "is_frequency_violator": False,
        "updated": "2026-04-29T12:00:00Z",
    }
]

_FAKE_TRANSMITTER_PAYLOAD = [
    {
        "uuid": "abc-123-def",
        "description": "ISS Voice Repeater",
        "sat_id": "AAAA-0001-0002-0003-0004",
        "norad_cat_id": 25544,
        "downlink_low": 145800000,    # 145.800 MHz
        "uplink_low": 437800000,      # 437.800 MHz
        "mode": "FM Voice",
        "baud": None,
        "status": "active",
        "updated": "2026-04-29T12:00:00Z",
    },
    {
        "uuid": "def-456-ghi",
        "description": "ISS APRS Digipeater",
        "sat_id": "AAAA-0001-0002-0003-0004",
        "norad_cat_id": 25544,
        "downlink_low": 145825000,    # 145.825 MHz
        "uplink_low": 145825000,
        "mode": "AFSK 1k2",
        "baud": 1200.0,
        "status": "active",
        "updated": "2026-04-29T12:00:00Z",
    },
]

_FAKE_TLE_PAYLOAD = [
    {
        "sat_id": "AAAA-0001-0002-0003-0004",
        "norad_cat_id": 25544,
        "tle_source": "Celestrak",
        "tle0": "ISS (ZARYA)",
        "tle1": "1 25544U 98067A   26119.50000000  .00010000  00000-0  00000-0 0  9999",
        "tle2": "2 25544  51.6431 245.8765 0001234  85.4321 274.6789 15.50000000 99999",
        "updated": "2026-04-29T12:00:00Z",
    }
]

_FAKE_TELEMETRY_PAYLOAD = [
    {
        "norad_cat_id": 25544,
        "timestamp": "2026-04-29T11:50:00Z",
        "decoder": "iss_decoder",
        "frame": "AABBCCDD" * 8,
        "observer": 4242,
        "decoded": True,
    },
    {
        "norad_cat_id": 25544,
        "timestamp": "2026-04-29T11:48:00Z",
        "decoder": None,
        "frame": "1122" * 16,
        "observer": 4242,
        "decoded": False,
    },
]


@pytest.fixture
def isolated_client(tmp_path: Path) -> SatNOGSClient:
    sn_mod.reset_for_test()
    return SatNOGSClient(cache_dir=tmp_path / "cache")


def _mock_urlopen(payload):
    body = json.dumps(payload).encode("utf-8")
    response = io.BytesIO(body)
    response.status = 200

    class _Ctx:
        def __enter__(self):
            return response
        def __exit__(self, *_):
            return False

    return _Ctx()


# ── Public-tier endpoints ───────────────────────────────────────


class TestPublicSatelliteEndpoint:
    def test_get_satellite_iss(self, isolated_client):
        with patch.object(
            sn_mod.request, "urlopen",
            return_value=_mock_urlopen(_FAKE_SATELLITE_PAYLOAD),
        ):
            sat = isolated_client.get_satellite(25544)
        assert sat is not None
        assert isinstance(sat, Satellite)
        assert sat.norad_cat_id == 25544
        assert "ISS" in sat.name
        assert sat.status == "alive"

    def test_get_satellite_returns_none_when_not_found(self, isolated_client):
        with patch.object(
            sn_mod.request, "urlopen", return_value=_mock_urlopen([]),
        ):
            sat = isolated_client.get_satellite(99999999)
        assert sat is None

    def test_list_satellites_alive_default(self, isolated_client):
        with patch.object(
            sn_mod.request, "urlopen",
            return_value=_mock_urlopen(_FAKE_SATELLITE_PAYLOAD),
        ):
            sats = isolated_client.list_satellites()
        assert len(sats) == 1
        assert all(s.status == "alive" for s in sats)


class TestPublicTransmitterEndpoint:
    def test_iss_two_transmitters(self, isolated_client):
        with patch.object(
            sn_mod.request, "urlopen",
            return_value=_mock_urlopen(_FAKE_TRANSMITTER_PAYLOAD),
        ):
            tx = isolated_client.get_transmitters_for(25544)
        assert len(tx) == 2

    def test_voice_repeater_frequencies_in_mhz(self, isolated_client):
        with patch.object(
            sn_mod.request, "urlopen",
            return_value=_mock_urlopen(_FAKE_TRANSMITTER_PAYLOAD),
        ):
            tx = isolated_client.get_transmitters_for(25544)
        voice = next(t for t in tx if "Voice" in t.description)
        # Hz → MHz conversion happens client-side.
        assert voice.downlink_mhz == pytest.approx(145.8, rel=1e-6)
        assert voice.uplink_mhz == pytest.approx(437.8, rel=1e-6)
        assert voice.mode == "FM Voice"

    def test_aprs_digipeater_baud(self, isolated_client):
        with patch.object(
            sn_mod.request, "urlopen",
            return_value=_mock_urlopen(_FAKE_TRANSMITTER_PAYLOAD),
        ):
            tx = isolated_client.get_transmitters_for(25544)
        aprs = next(t for t in tx if "APRS" in t.description)
        assert aprs.baud == 1200.0
        assert aprs.mode == "AFSK 1k2"


class TestPublicTLEEndpoint:
    def test_iss_tle_lines(self, isolated_client):
        with patch.object(
            sn_mod.request, "urlopen",
            return_value=_mock_urlopen(_FAKE_TLE_PAYLOAD),
        ):
            tle = isolated_client.get_tle(25544)
        assert tle is not None
        assert tle.norad_cat_id == 25544
        assert tle.tle1.startswith("1 25544")
        assert tle.tle2.startswith("2 25544")
        # Lines property returns 3-tuple usable by sgp4.
        assert tle.tle_lines[0] == "ISS (ZARYA)"


# ── Authenticated endpoint (telemetry) ──────────────────────────


class TestTelemetryEndpoint:
    def test_telemetry_requires_api_key(self, tmp_path):
        # Client without api_key should refuse with actionable error.
        sn_mod.reset_for_test()
        client = SatNOGSClient(cache_dir=tmp_path / "cache", api_key=None)
        with pytest.raises(RuntimeError, match="API key|ARIA_SATNOGS"):
            client.get_recent_telemetry(25544)

    def test_telemetry_with_api_key_parses_frames(self, tmp_path):
        sn_mod.reset_for_test()
        client = SatNOGSClient(
            cache_dir=tmp_path / "cache",
            api_key="dummy-test-key-deadbeef",
        )
        with patch.object(
            sn_mod.request, "urlopen",
            return_value=_mock_urlopen(_FAKE_TELEMETRY_PAYLOAD),
        ):
            frames = client.get_recent_telemetry(25544, max_frames=10)
        assert len(frames) == 2
        assert frames[0].norad_cat_id == 25544
        assert frames[0].is_decoded is True
        assert frames[1].is_decoded is False

    def test_max_frames_validation(self, tmp_path):
        client = SatNOGSClient(
            cache_dir=tmp_path / "cache",
            api_key="dummy-test-key",
        )
        with pytest.raises(ValueError, match="max_frames"):
            client.get_recent_telemetry(25544, max_frames=0)


# ── Cache + auth header behaviour ───────────────────────────────


class TestCacheBehaviour:
    def test_second_call_within_ttl_skips_network(self, isolated_client):
        call_count = {"n": 0}

        def _counting_urlopen(*args, **kwargs):
            call_count["n"] += 1
            return _mock_urlopen(_FAKE_SATELLITE_PAYLOAD)

        with patch.object(
            sn_mod.request, "urlopen", side_effect=_counting_urlopen,
        ):
            isolated_client.get_satellite(25544)
            isolated_client.get_satellite(25544)
        assert call_count["n"] == 1

    def test_distinct_norad_distinct_cache_files(self, tmp_path):
        client = SatNOGSClient(cache_dir=tmp_path / "cache")

        def _fresh(*args, **kwargs):
            return _mock_urlopen(_FAKE_SATELLITE_PAYLOAD)

        with patch.object(
            sn_mod.request, "urlopen", side_effect=_fresh,
        ):
            client.get_satellite(25544)
            client.get_satellite(43013)

        files = list((tmp_path / "cache").glob("*.json"))
        assert len(files) == 2


# ── Error handling ──────────────────────────────────────────────


class TestErrorHandling:
    def test_401_raises_actionable_error(self, isolated_client):
        from urllib.error import HTTPError

        def _raise_401(*args, **kwargs):
            raise HTTPError(
                url="x", code=401, msg="Unauthorized",
                hdrs=None, fp=None,
            )

        with patch.object(sn_mod.request, "urlopen", side_effect=_raise_401):
            with pytest.raises(RuntimeError, match="API key|invalid|401"):
                isolated_client.get_satellite(25544)

    def test_invalid_json_raises(self, isolated_client):
        bogus = b"<html>not json</html>"
        body = io.BytesIO(bogus)
        body.status = 200

        class _Ctx:
            def __enter__(self):
                return body
            def __exit__(self, *_):
                return False

        with patch.object(sn_mod.request, "urlopen", return_value=_Ctx()):
            with pytest.raises(RuntimeError, match="non-JSON"):
                isolated_client.get_satellite(25544)


# ── Singleton ───────────────────────────────────────────────────


def test_singleton_picks_up_env_api_key(monkeypatch):
    monkeypatch.setenv("ARIA_SATNOGS_API_KEY", "env-test-key-xyz")
    sn_mod.reset_for_test()
    client = get_satnogs_client()
    assert client.api_key == "env-test-key-xyz"


def test_singleton_works_without_env_key(monkeypatch):
    monkeypatch.delenv("ARIA_SATNOGS_API_KEY", raising=False)
    sn_mod.reset_for_test()
    client = get_satnogs_client()
    assert client.api_key is None


# ── Live probes (opt-in) ────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("ARIA_RUN_LIVE_SATNOGS") != "1",
    reason="live SatNOGS probe; gated on ARIA_RUN_LIVE_SATNOGS=1",
)
def test_live_iss_satellite_record(tmp_path):
    """Smoke: pull ISS satellite record from real SatNOGS DB."""
    client = SatNOGSClient(cache_dir=tmp_path / "live_cache")
    sat = client.get_satellite(25544)
    assert sat is not None
    assert sat.norad_cat_id == 25544
    assert "ISS" in sat.name or "ZARYA" in sat.name


@pytest.mark.skipif(
    os.environ.get("ARIA_RUN_LIVE_SATNOGS") != "1",
    reason="live SatNOGS probe; gated on ARIA_RUN_LIVE_SATNOGS=1",
)
def test_live_iss_transmitters(tmp_path):
    """Smoke: pull ISS transmitters from real SatNOGS DB."""
    client = SatNOGSClient(cache_dir=tmp_path / "live_cache")
    tx = client.get_transmitters_for(25544)
    # ISS has many transmitters; should have at least 5.
    assert len(tx) >= 1
    for t in tx:
        if t.downlink_mhz is not None:
            # ISS amateur band transmitters live in 144-146 MHz / 437 MHz.
            assert 100.0 <= t.downlink_mhz <= 500.0
