from __future__ import annotations

import pytest

from aria.integrations.satnogs_decoders import (
    FoxOneDecoder,
    FuncubeOneDecoder,
    GenericAx25KissDecoder,
    GenericCwBeaconDecoder,
    LightsailDecoder,
    PocketqubeBeaconDecoder,
    default_decoder_chain,
)
from aria.integrations.satnogs_live import SatNOGSFrame


def _frame(norad: int, hex_payload: str) -> SatNOGSFrame:
    return SatNOGSFrame(
        norad_cat_id=norad,
        timestamp_iso="2026-04-29T08:00:00Z",
        frame_hex=hex_payload,
    )


class TestFuncubeOne:
    def test_decodes_minimum_frame(self):
        decoder = FuncubeOneDecoder()
        frame_hex = "00010180a0" + "00" * 12
        decoded = decoder.decode(_frame(39444, frame_hex))
        assert decoded["decoder"] == "funcube_one_v1"
        assert decoded["sequence_number"] == 1
        assert isinstance(decoded["bus_voltage_v"], float)

    def test_skips_short_frame(self):
        decoder = FuncubeOneDecoder()
        decoded = decoder.decode(_frame(39444, "0001"))
        assert decoded == {}


class TestFoxOne:
    def test_decodes_battery_voltage(self):
        decoder = FoxOneDecoder()
        frame_hex = "00" * 12 + "1027" + "0040" + "0500" + "00" * 14
        decoded = decoder.decode(_frame(40967, frame_hex))
        assert decoded["decoder"] == "fox_one_v1"
        assert "bus_voltage_v" in decoded
        assert "battery_a_temp_c" in decoded


class TestLightsail:
    def test_decodes_sail_state(self):
        decoder = LightsailDecoder()
        frame_hex = "00" * 8 + "01" + "00" + "0BA8" + "00" * 12
        decoded = decoder.decode(_frame(44420, frame_hex))
        assert decoded["decoder"] == "lightsail_v1"
        assert decoded["sail_deploy_state"] == 1


class TestPocketqube:
    def test_decodes_battery(self):
        decoder = PocketqubeBeaconDecoder()
        frame_hex = "0000" + "80" + "82" + "01" + "00" * 4
        decoded = decoder.decode(_frame(51439, frame_hex))
        assert decoded["decoder"] == "pocketqube_v1"
        assert 3.0 <= decoded["battery_voltage_v"] <= 4.5


class TestGenericCw:
    def test_decodes_ascii_text(self):
        text = "HI DE TEST CALLSIGN/N FOX-1A   "
        hex_payload = text.encode("ascii").hex()
        decoder = GenericCwBeaconDecoder()
        decoded = decoder.decode(_frame(0, hex_payload))
        assert decoded["decoder"] == "cw_beacon_v1"
        assert "TEST CALLSIGN" in decoded["ascii_text"]

    def test_skips_non_ascii(self):
        decoder = GenericCwBeaconDecoder()
        decoded = decoder.decode(_frame(0, "ff" * 20))
        assert decoded.get("decoder") == "cw_skip"


class TestGenericAx25:
    def test_skips_non_kiss(self):
        decoder = GenericAx25KissDecoder()
        decoded = decoder.decode(_frame(0, "00" * 32))
        assert decoded.get("decoder") == "ax25_skip"

    def test_decodes_minimal_kiss(self):
        dest = "ARISS "
        src = "ON0AB "
        encoded_addresses = bytes((ord(ch) << 1) for ch in (dest + " " + src))
        body = b"\xc0\x00" + encoded_addresses[:14] + b"\x03\xf0HELLO" + b"\xc0"
        decoder = GenericAx25KissDecoder()
        decoded = decoder.decode(_frame(0, body.hex()))
        assert decoded["decoder"] == "ax25_kiss_v1"
        assert decoded["ax25_dest"] == "ARISS"


class TestDefaultChain:
    def test_chain_has_all_eleven(self):
        chain = default_decoder_chain()
        assert len(chain) == 11
        names = {type(decoder).__name__ for decoder in chain}
        for required in (
            "FuncubeOneDecoder", "FoxOneDecoder", "LightsailDecoder",
            "PocketqubeBeaconDecoder", "EseoDecoder", "Aausat4Decoder",
            "Gomx3Decoder", "SwisscubeDecoder", "DelfiPqDecoder",
            "GenericAx25KissDecoder", "GenericCwBeaconDecoder",
        ):
            assert required in names, f"missing {required}"

    def test_funcube_decoder_skipped_for_other_norad(self):
        decoder = FuncubeOneDecoder()
        decoded = decoder.decode(_frame(99999, "00" * 32))
        assert isinstance(decoded, dict)


class TestNewDecoders:
    def test_eseo_decodes_minimum_frame(self):
        from aria.integrations.satnogs_decoders import EseoDecoder
        frame_hex = "0001" + "00" * 6 + "0BB8" + "0040" + "00" * 12
        decoded = EseoDecoder().decode(_frame(43017, frame_hex))
        assert decoded["decoder"] == "eseo_v1"
        assert decoded["sequence_number"] == 1

    def test_aausat4_decodes(self):
        from aria.integrations.satnogs_decoders import Aausat4Decoder
        frame_hex = "00" * 16 + "C8" + "82" + "00" * 2 + "0064" + "00" * 10
        decoded = Aausat4Decoder().decode(_frame(41460, frame_hex))
        assert decoded["decoder"] == "aausat4_v1"
        assert "battery_voltage_v" in decoded

    def test_gomx3_decodes(self):
        from aria.integrations.satnogs_decoders import Gomx3Decoder
        frame_hex = "00" * 16 + "0DAC" + "0064" + "00" * 16
        decoded = Gomx3Decoder().decode(_frame(41460, frame_hex))
        assert decoded["decoder"] == "gomx3_v1"
        assert decoded["battery_voltage_v"] > 0

    def test_swisscube_decodes_callsign(self):
        from aria.integrations.satnogs_decoders import SwisscubeDecoder
        text = "HB9EG SwissCube de orbit         "
        frame_hex = text.encode("ascii").hex()
        decoded = SwisscubeDecoder().decode(_frame(35932, frame_hex))
        assert decoded["decoder"] == "swisscube_v1"
        assert "HB9" in decoded["beacon_text"]

    def test_delfi_pq_decodes(self):
        from aria.integrations.satnogs_decoders import DelfiPqDecoder
        frame_hex = "00" * 4 + "80" + "82" + "01" + "10" + "00" * 12
        decoded = DelfiPqDecoder().decode(_frame(51439, frame_hex))
        assert decoded["decoder"] == "delfi_pq_v1"
        assert 2.5 <= decoded["battery_voltage_v"] <= 5.0
