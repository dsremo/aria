from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from aria.integrations.satnogs_live import (
    SatNOGSDecoder,
    SatNOGSFrame,
    SatNOGSLivePump,
)


def _mock_response(payload):
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=None)
    return resp


class TestPumpConstruction:
    def test_requires_token(self):
        with pytest.raises(ValueError, match="api_token"):
            SatNOGSLivePump(norad_cat_ids=[1], api_token="")

    def test_requires_at_least_one_norad(self):
        with pytest.raises(ValueError, match="NORAD"):
            SatNOGSLivePump(norad_cat_ids=[], api_token="x")


class TestPollOnce:
    def test_emits_frames_to_sink(self):
        captured: list[SatNOGSFrame] = []
        opener = MagicMock()
        opener.open.return_value = _mock_response({
            "results": [
                {"timestamp": "2026-04-29T08:00:00Z", "frame": "AAAA",
                 "observer": "obs1", "transmitter": "uuid1"},
                {"timestamp": "2026-04-29T08:01:00Z", "frame": "BBBB",
                 "observer": "obs2", "transmitter": "uuid1"},
            ],
        })
        pump = SatNOGSLivePump(
            norad_cat_ids=[25544], api_token="t", opener=opener,
            sinks=[captured.append],
        )
        emitted = pump.poll_once()
        assert emitted == 2
        assert {frame.frame_hex for frame in captured} == {"AAAA", "BBBB"}

    def test_dedup_skips_seen_frames(self):
        captured: list[SatNOGSFrame] = []
        opener = MagicMock()
        first = _mock_response({"results": [
            {"timestamp": "2026-04-29T08:00:00Z", "frame": "AAAA"},
        ]})
        second = _mock_response({"results": [
            {"timestamp": "2026-04-29T08:00:00Z", "frame": "AAAA"},
            {"timestamp": "2026-04-29T08:01:00Z", "frame": "BBBB"},
        ]})
        opener.open.side_effect = [first, second]
        pump = SatNOGSLivePump(
            norad_cat_ids=[25544], api_token="t", opener=opener,
            sinks=[captured.append],
        )
        pump.poll_once()
        pump.poll_once()
        hexes = [frame.frame_hex for frame in captured]
        assert hexes == ["AAAA", "BBBB"]
        assert pump.stats.duplicate_skipped >= 1

    def test_handles_empty_payload(self):
        opener = MagicMock()
        opener.open.return_value = _mock_response({"results": []})
        pump = SatNOGSLivePump(
            norad_cat_ids=[25544], api_token="t", opener=opener,
        )
        emitted = pump.poll_once()
        assert emitted == 0

    def test_handles_unexpected_top_level_shape(self):
        opener = MagicMock()
        opener.open.return_value = _mock_response("not a list nor dict")
        pump = SatNOGSLivePump(
            norad_cat_ids=[25544], api_token="t", opener=opener,
        )
        emitted = pump.poll_once()
        assert emitted == 0

    def test_http_error_increments_counter(self):
        import urllib.error
        opener = MagicMock()
        opener.open.side_effect = urllib.error.URLError("connection refused")
        pump = SatNOGSLivePump(
            norad_cat_ids=[25544], api_token="t", opener=opener,
        )
        emitted = pump.poll_once()
        assert emitted == 0
        assert pump.stats.http_errors == 1

    def test_authorization_header_present(self):
        opener = MagicMock()
        opener.open.return_value = _mock_response({"results": []})
        pump = SatNOGSLivePump(
            norad_cat_ids=[25544], api_token="abc123", opener=opener,
        )
        pump.poll_once()
        request_arg = opener.open.call_args.args[0]
        assert request_arg.get_header("Authorization") == "Token abc123"


class TestDecoder:
    def test_decoder_invoked_for_matching_norad(self):
        captured: list[SatNOGSFrame] = []

        class _MyDecoder(SatNOGSDecoder):
            norad_cat_ids = (25544,)

            def decode(self, frame):
                return {"voltage_v": 3.7, "rssi_dbm": -95.0}

        opener = MagicMock()
        opener.open.return_value = _mock_response({"results": [
            {"timestamp": "2026-04-29T09:00:00Z", "frame": "AABB"},
        ]})
        pump = SatNOGSLivePump(
            norad_cat_ids=[25544], api_token="t", opener=opener,
            sinks=[captured.append], decoders=[_MyDecoder()],
        )
        pump.poll_once()
        assert captured[0].decoded["voltage_v"] == 3.7

    def test_decoder_skipped_for_other_norad(self):
        captured: list[SatNOGSFrame] = []

        class _OnlyForA(SatNOGSDecoder):
            norad_cat_ids = (12345,)

            def decode(self, frame):
                return {"should": "not-appear"}

        opener = MagicMock()
        opener.open.return_value = _mock_response({"results": [
            {"timestamp": "2026-04-29T09:00:00Z", "frame": "AABB"},
        ]})
        pump = SatNOGSLivePump(
            norad_cat_ids=[25544], api_token="t", opener=opener,
            sinks=[captured.append], decoders=[_OnlyForA()],
        )
        pump.poll_once()
        assert captured[0].decoded == {}

    def test_decoder_exception_counted_not_raised(self):
        captured: list[SatNOGSFrame] = []

        class _Crashy(SatNOGSDecoder):
            norad_cat_ids = (25544,)

            def decode(self, frame):
                raise RuntimeError("boom")

        opener = MagicMock()
        opener.open.return_value = _mock_response({"results": [
            {"timestamp": "2026-04-29T09:00:00Z", "frame": "AABB"},
        ]})
        pump = SatNOGSLivePump(
            norad_cat_ids=[25544], api_token="t", opener=opener,
            sinks=[captured.append], decoders=[_Crashy()],
        )
        pump.poll_once()
        assert pump.stats.decode_errors == 1
        assert len(captured) == 1


class TestStats:
    def test_stats_increment(self):
        opener = MagicMock()
        opener.open.return_value = _mock_response({"results": [
            {"timestamp": "2026-04-29T09:00:00Z", "frame": "AABB"},
        ]})
        pump = SatNOGSLivePump(
            norad_cat_ids=[25544], api_token="t", opener=opener,
        )
        pump.poll_once()
        pump.poll_once()
        assert pump.stats.polls == 2
        assert pump.stats.frames_emitted == 1
        assert pump.stats.duplicate_skipped == 1
