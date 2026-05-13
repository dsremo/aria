"""Tests for the SatNOGS API fetcher.

Uses mocked HTTP responses — no real API calls needed.

The SatNOGS public REST API returns raw hex frames, NOT decoded telemetry.
We extract signal-level metrics: frame_length, byte_mean, byte_entropy, frame_gap.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from aria.dsremo.ingest.satnogs_fetcher import (
    SatNOGSFetcher,
    _byte_entropy,
    _guess_subsystem,
)


class TestByteEntropy:
    def test_uniform_bytes_have_max_entropy(self):
        # 256 unique byte values → max entropy = 8.0
        data = bytes(range(256))
        result = _byte_entropy(data)
        assert abs(result - 8.0) < 0.01

    def test_single_byte_repeated_has_zero_entropy(self):
        data = bytes([0xAA] * 100)
        result = _byte_entropy(data)
        assert result == 0.0

    def test_two_equal_bytes_entropy(self):
        # p=0.5 each → entropy = 1.0 bit
        data = bytes([0x00, 0xFF] * 50)
        result = _byte_entropy(data)
        assert abs(result - 1.0) < 0.01

    def test_empty_bytes_returns_zero(self):
        assert _byte_entropy(b"") == 0.0

    def test_entropy_range(self):
        data = bytes([0x01, 0x02, 0x03, 0x04] * 10)
        result = _byte_entropy(data)
        assert 0.0 <= result <= 8.0


class TestGuessSubsystem:
    def test_eps_keywords(self):
        assert _guess_subsystem("battery_voltage") == "eps"
        assert _guess_subsystem("solar_array_current") == "eps"
        assert _guess_subsystem("bus_power") == "eps"

    def test_adcs_keywords(self):
        assert _guess_subsystem("gyro_x") == "adcs"
        assert _guess_subsystem("reaction_wheel_speed") == "adcs"
        assert _guess_subsystem("magnetometer_z") == "adcs"
        assert _guess_subsystem("attitude_error") == "adcs"

    def test_thermal_keywords(self):
        assert _guess_subsystem("panel_temperature") == "thermal"
        assert _guess_subsystem("thermal_control") == "thermal"
        assert _guess_subsystem("heater_status") == "thermal"

    def test_comms_keywords(self):
        assert _guess_subsystem("rssi_level") == "comms"
        assert _guess_subsystem("signal_strength") == "comms"
        assert _guess_subsystem("radio_power") == "comms"
        assert _guess_subsystem("beacon_interval") == "comms"

    def test_unknown_fallback(self):
        assert _guess_subsystem("some_random_param") == "unknown"
        assert _guess_subsystem("cpu_load") == "unknown"


class TestSatNOGSFetcher:
    def test_init_with_token(self):
        fetcher = SatNOGSFetcher(api_token="test-token-123")
        assert fetcher.api_token == "test-token-123"

    def test_init_without_token_warns(self, monkeypatch):
        # Should not raise, just warn (clear env so _load_dotenv doesn't find it)
        monkeypatch.delenv("SATNOGS_API_TOKEN", raising=False)
        monkeypatch.setattr("aria.dsremo.core.config._DOTENV_PATH", type("P", (), {"exists": lambda self: False})())
        fetcher = SatNOGSFetcher(api_token="")
        assert fetcher.api_token == ""

    def test_headers_include_token(self):
        fetcher = SatNOGSFetcher(api_token="my-token")
        headers = fetcher._headers
        assert headers["Authorization"] == "Token my-token"

    @pytest.mark.asyncio
    async def test_fetch_without_token_raises(self, monkeypatch):
        monkeypatch.delenv("SATNOGS_API_TOKEN", raising=False)
        monkeypatch.setattr("aria.dsremo.core.config._DOTENV_PATH", type("P", (), {"exists": lambda self: False})())
        fetcher = SatNOGSFetcher(api_token="")
        with pytest.raises(ValueError, match="SATNOGS_API_TOKEN not set"):
            await fetcher.fetch_telemetry("12345")


class TestConvertToPoints:
    """Tests for signal-level metric extraction from raw hex frames."""

    @pytest.fixture
    def fetcher(self) -> SatNOGSFetcher:
        return SatNOGSFetcher(api_token="test")

    def _make_frame(
        self,
        norad: int = 44830,
        timestamp: str = "2024-03-15T10:30:00Z",
        hex_data: str = "deadbeef0102030405",
    ) -> dict:
        return {
            "norad_cat_id": norad,
            "timestamp": timestamp,
            "frame": hex_data,
        }

    def test_single_frame_produces_three_points(self, fetcher: SatNOGSFetcher):
        # One frame → frame_length + byte_mean + byte_entropy (no frame_gap — first frame)
        raw = [self._make_frame()]
        points = fetcher.convert_to_points(raw)
        assert len(points) == 3
        params = {p.parameter for p in points}
        assert params == {"frame_length", "byte_mean", "byte_entropy"}

    def test_two_frames_produces_frame_gap(self, fetcher: SatNOGSFetcher):
        # Second frame adds frame_gap → 3 + 4 = 7 points
        raw = [
            self._make_frame(timestamp="2024-03-15T10:30:00Z"),
            self._make_frame(timestamp="2024-03-15T10:31:00Z"),
        ]
        points = fetcher.convert_to_points(raw)
        assert len(points) == 7
        params = [p.parameter for p in points]
        assert "frame_gap" in params

    def test_frame_length_value_correct(self, fetcher: SatNOGSFetcher):
        # "deadbeef" → 4 bytes
        raw = [self._make_frame(hex_data="deadbeef")]
        points = fetcher.convert_to_points(raw)
        length_pts = [p for p in points if p.parameter == "frame_length"]
        assert len(length_pts) == 1
        assert length_pts[0].value == 4.0

    def test_byte_mean_value_correct(self, fetcher: SatNOGSFetcher):
        # 10 distinct bytes 0x40-0x49 (64-73) → mean = 68.5, entropy ≈ 3.32 (passes filter)
        # All-identical bytes have entropy = 0 and are filtered by the entropy guard.
        hex_data = "40414243444546474849"
        raw = [self._make_frame(hex_data=hex_data)]
        points = fetcher.convert_to_points(raw)
        mean_pts = [p for p in points if p.parameter == "byte_mean"]
        assert len(mean_pts) == 1
        assert mean_pts[0].value == pytest.approx(68.5)

    def test_byte_entropy_value_range(self, fetcher: SatNOGSFetcher):
        raw = [self._make_frame(hex_data="deadbeef0102030405060708")]
        points = fetcher.convert_to_points(raw)
        entropy_pts = [p for p in points if p.parameter == "byte_entropy"]
        assert len(entropy_pts) == 1
        assert 0.0 <= entropy_pts[0].value <= 8.0

    def test_frame_gap_seconds_correct(self, fetcher: SatNOGSFetcher):
        raw = [
            self._make_frame(timestamp="2024-03-15T10:00:00Z"),
            self._make_frame(timestamp="2024-03-15T10:00:30Z"),  # 30s gap
        ]
        points = fetcher.convert_to_points(raw)
        gap_pts = [p for p in points if p.parameter == "frame_gap"]
        assert len(gap_pts) == 1
        assert gap_pts[0].value == 30.0

    def test_all_metrics_go_to_comms_subsystem(self, fetcher: SatNOGSFetcher):
        raw = [self._make_frame()]
        points = fetcher.convert_to_points(raw)
        assert all(p.subsystem == "comms" for p in points)

    def test_satellite_id_from_norad(self, fetcher: SatNOGSFetcher):
        raw = [self._make_frame(norad=35933)]
        points = fetcher.convert_to_points(raw)
        assert all(p.satellite_id == "35933" for p in points)

    def test_custom_satellite_id_overrides_norad(self, fetcher: SatNOGSFetcher):
        raw = [self._make_frame(norad=12345)]
        points = fetcher.convert_to_points(raw, satellite_id="BEESAT")
        assert all(p.satellite_id == "BEESAT" for p in points)

    def test_skips_empty_frame_field(self, fetcher: SatNOGSFetcher):
        raw = [{"norad_cat_id": 44830, "timestamp": "2024-03-15T10:30:00Z", "frame": ""}]
        points = fetcher.convert_to_points(raw)
        assert len(points) == 0

    def test_skips_missing_frame_field(self, fetcher: SatNOGSFetcher):
        raw = [{"norad_cat_id": 44830, "timestamp": "2024-03-15T10:30:00Z"}]
        points = fetcher.convert_to_points(raw)
        assert len(points) == 0

    def test_skips_invalid_hex(self, fetcher: SatNOGSFetcher):
        raw = [{"norad_cat_id": 44830, "timestamp": "2024-03-15T10:30:00Z", "frame": "ZZZZ"}]
        points = fetcher.convert_to_points(raw)
        assert len(points) == 0

    def test_skips_frames_too_short(self, fetcher: SatNOGSFetcher):
        # Single byte — too short (need >= 2 bytes for meaningful metrics)
        raw = [self._make_frame(hex_data="ff")]
        points = fetcher.convert_to_points(raw)
        assert len(points) == 0

    def test_skips_invalid_timestamp(self, fetcher: SatNOGSFetcher):
        raw = [{"norad_cat_id": 44830, "timestamp": "not-a-date", "frame": "deadbeef"}]
        points = fetcher.convert_to_points(raw)
        assert len(points) == 0

    def test_skips_large_frame_gap(self, fetcher: SatNOGSFetcher):
        # Gap > 86400s (different orbital passes) is excluded
        raw = [
            self._make_frame(timestamp="2024-03-10T10:00:00Z"),
            self._make_frame(timestamp="2024-03-15T10:00:00Z"),  # 5 days gap
        ]
        points = fetcher.convert_to_points(raw)
        gap_pts = [p for p in points if p.parameter == "frame_gap"]
        assert len(gap_pts) == 0

    def test_quality_is_correct(self, fetcher: SatNOGSFetcher):
        raw = [self._make_frame()]
        points = fetcher.convert_to_points(raw)
        for p in points:
            assert p.quality in (0.9, 0.85)

    def test_empty_input(self, fetcher: SatNOGSFetcher):
        assert fetcher.convert_to_points([]) == []

    def test_timestamp_parsed_correctly(self, fetcher: SatNOGSFetcher):
        raw = [self._make_frame(timestamp="2024-06-15T14:30:00Z")]
        points = fetcher.convert_to_points(raw)
        ts = points[0].timestamp
        assert ts.year == 2024
        assert ts.month == 6
        assert ts.hour == 14
        assert ts.tzinfo is not None

    def test_skips_non_dict_frames(self, fetcher: SatNOGSFetcher):
        raw = ["not_a_dict", 42, None, self._make_frame()]
        points = fetcher.convert_to_points(raw)  # type: ignore[arg-type]
        # Only the valid dict frame should produce points
        assert len(points) == 3
