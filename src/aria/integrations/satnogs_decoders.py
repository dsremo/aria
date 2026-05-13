from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any, Optional

from aria.integrations.satnogs_live import SatNOGSDecoder, SatNOGSFrame


def _unhex(frame_hex: str) -> bytes:
    cleaned = "".join(ch for ch in (frame_hex or "") if ch in "0123456789abcdefABCDEF")
    if len(cleaned) % 2:
        cleaned = cleaned[:-1]
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        return b""


@dataclass(frozen=True)
class FrameMetadata:
    norad_cat_id: int
    bytes: bytes
    length: int


def _frame_metadata(frame: SatNOGSFrame) -> FrameMetadata:
    raw = _unhex(frame.frame_hex)
    return FrameMetadata(
        norad_cat_id=frame.norad_cat_id,
        bytes=raw,
        length=len(raw),
    )


class FuncubeOneDecoder(SatNOGSDecoder):
    norad_cat_ids = (39444,)

    def decode(self, frame: SatNOGSFrame) -> dict[str, Any]:
        meta = _frame_metadata(frame)
        if meta.length < 16:
            return {}
        sequence = struct.unpack(">H", meta.bytes[0:2])[0]
        bus_v_raw = meta.bytes[2]
        bus_voltage_v = bus_v_raw * 0.04
        battery_temp_c = (meta.bytes[3] - 128) * 0.5
        rssi_dbm = -120.0 + (meta.bytes[4] * 0.5)
        return {
            "sequence_number": sequence,
            "bus_voltage_v": round(bus_voltage_v, 3),
            "battery_temp_c": round(battery_temp_c, 2),
            "rssi_dbm": round(rssi_dbm, 1),
            "decoder": "funcube_one_v1",
        }


class GenericAx25KissDecoder(SatNOGSDecoder):
    norad_cat_ids: tuple[int, ...] = ()

    def decode(self, frame: SatNOGSFrame) -> dict[str, Any]:
        meta = _frame_metadata(frame)
        if meta.length < 16:
            return {"decoder": "ax25_skip", "reason": "frame too short"}
        if meta.bytes[0] != 0xC0:
            return {"decoder": "ax25_skip", "reason": "no kiss frame-start"}
        end = meta.bytes.rfind(b"\xC0", 1)
        if end < 16:
            return {"decoder": "ax25_skip", "reason": "no kiss frame-end"}
        body = meta.bytes[2:end]
        if len(body) < 14:
            return {"decoder": "ax25_skip", "reason": "ax25 header truncated"}
        dest = "".join(chr(byte >> 1) for byte in body[0:6]).strip()
        src = "".join(chr(byte >> 1) for byte in body[7:13]).strip()
        info = body[16:] if len(body) > 16 else b""
        return {
            "decoder": "ax25_kiss_v1",
            "ax25_dest": dest,
            "ax25_source": src,
            "info_bytes": len(info),
            "info_preview_hex": info[:32].hex() if info else "",
        }


class GenericCwBeaconDecoder(SatNOGSDecoder):
    norad_cat_ids: tuple[int, ...] = ()

    def decode(self, frame: SatNOGSFrame) -> dict[str, Any]:
        raw = _unhex(frame.frame_hex)
        if not raw:
            return {"decoder": "cw_skip", "reason": "non-hex frame"}
        printable = sum(
            1 for byte in raw if 0x20 <= byte <= 0x7E or byte in (0x09, 0x0A, 0x0D)
        )
        if printable / len(raw) < 0.85:
            return {"decoder": "cw_skip", "reason": "non-printable"}
        text = raw.decode("ascii", errors="replace")
        return {
            "decoder": "cw_beacon_v1",
            "ascii_text": text.strip(),
            "ascii_length": len(text.strip()),
        }


class FoxOneDecoder(SatNOGSDecoder):
    norad_cat_ids = (40967, 43137, 43770, 43017)

    def decode(self, frame: SatNOGSFrame) -> dict[str, Any]:
        meta = _frame_metadata(frame)
        if meta.length < 32:
            return {}
        bus_v_raw = struct.unpack("<H", meta.bytes[12:14])[0]
        bus_voltage_v = bus_v_raw * 0.001
        bat_a_temp_raw = struct.unpack("<h", meta.bytes[14:16])[0]
        bat_a_temp_c = bat_a_temp_raw * 0.0625
        rx_count = struct.unpack("<H", meta.bytes[16:18])[0]
        return {
            "decoder": "fox_one_v1",
            "bus_voltage_v": round(bus_voltage_v, 3),
            "battery_a_temp_c": round(bat_a_temp_c, 2),
            "rx_count": rx_count,
        }


class LightsailDecoder(SatNOGSDecoder):
    norad_cat_ids = (44420,)

    def decode(self, frame: SatNOGSFrame) -> dict[str, Any]:
        meta = _frame_metadata(frame)
        if meta.length < 24:
            return {}
        sail_deploy_state = meta.bytes[8]
        bus_voltage_mv = struct.unpack(">H", meta.bytes[10:12])[0]
        return {
            "decoder": "lightsail_v1",
            "sail_deploy_state": sail_deploy_state,
            "bus_voltage_v": round(bus_voltage_mv * 0.001, 3),
        }


class PocketqubeBeaconDecoder(SatNOGSDecoder):
    norad_cat_ids = (51439,)

    def decode(self, frame: SatNOGSFrame) -> dict[str, Any]:
        meta = _frame_metadata(frame)
        if meta.length < 8:
            return {}
        battery_voltage_raw = meta.bytes[2]
        battery_voltage_v = 3.0 + (battery_voltage_raw / 255.0) * 1.5
        battery_temp_c = (meta.bytes[3] - 128) * 0.5
        comm_mode = meta.bytes[4]
        return {
            "decoder": "pocketqube_v1",
            "battery_voltage_v": round(battery_voltage_v, 3),
            "battery_temp_c": round(battery_temp_c, 2),
            "comm_mode": comm_mode,
        }


class EseoDecoder(SatNOGSDecoder):
    norad_cat_ids = (43017,)

    def decode(self, frame: SatNOGSFrame) -> dict[str, Any]:
        meta = _frame_metadata(frame)
        if meta.length < 24:
            return {}
        sequence = struct.unpack(">H", meta.bytes[0:2])[0]
        bus_voltage_raw = struct.unpack(">H", meta.bytes[8:10])[0]
        bus_voltage_v = bus_voltage_raw * 0.001
        battery_temp_raw = struct.unpack(">h", meta.bytes[10:12])[0]
        battery_temp_c = battery_temp_raw * 0.0625
        return {
            "decoder": "eseo_v1",
            "sequence_number": sequence,
            "bus_voltage_v": round(bus_voltage_v, 3),
            "battery_temp_c": round(battery_temp_c, 2),
        }


class Aausat4Decoder(SatNOGSDecoder):
    norad_cat_ids = (41460,)

    def decode(self, frame: SatNOGSFrame) -> dict[str, Any]:
        meta = _frame_metadata(frame)
        if meta.length < 32:
            return {}
        bat_voltage_v = meta.bytes[16] * 0.025 + 6.0
        bat_temp_c = (meta.bytes[17] - 128) * 0.5
        sun_sensor_x = struct.unpack(">h", meta.bytes[20:22])[0] * 0.001
        return {
            "decoder": "aausat4_v1",
            "battery_voltage_v": round(bat_voltage_v, 3),
            "battery_temp_c": round(bat_temp_c, 2),
            "sun_sensor_x": round(sun_sensor_x, 4),
        }


class Gomx3Decoder(SatNOGSDecoder):
    norad_cat_ids = (41460, 41459)

    def decode(self, frame: SatNOGSFrame) -> dict[str, Any]:
        meta = _frame_metadata(frame)
        if meta.length < 30:
            return {}
        ax_25_overhead = 16
        if meta.length < ax_25_overhead + 8:
            return {}
        body = meta.bytes[ax_25_overhead:]
        bat_v_raw = struct.unpack(">H", body[0:2])[0]
        bat_voltage_v = bat_v_raw * 0.001
        eps_temp_raw = struct.unpack(">h", body[2:4])[0]
        eps_temp_c = eps_temp_raw * 0.01
        return {
            "decoder": "gomx3_v1",
            "battery_voltage_v": round(bat_voltage_v, 3),
            "eps_temp_c": round(eps_temp_c, 2),
        }


class SwisscubeDecoder(SatNOGSDecoder):
    norad_cat_ids = (35932,)

    def decode(self, frame: SatNOGSFrame) -> dict[str, Any]:
        raw = _unhex(frame.frame_hex)
        if len(raw) < 16:
            return {}
        try:
            text = raw.decode("ascii", errors="replace").strip()
        except UnicodeDecodeError:
            return {}
        if "HB9" not in text and "SwissCube" not in text:
            return {"decoder": "swisscube_skip", "reason": "no callsign"}
        return {
            "decoder": "swisscube_v1",
            "beacon_text": text[:100],
        }


class DelfiPqDecoder(SatNOGSDecoder):
    norad_cat_ids = (51439, 51440)

    def decode(self, frame: SatNOGSFrame) -> dict[str, Any]:
        meta = _frame_metadata(frame)
        if meta.length < 16:
            return {}
        bat_voltage_raw = meta.bytes[4]
        bat_voltage_v = 2.5 + (bat_voltage_raw / 255.0) * 2.5
        bat_temp_c = (meta.bytes[5] - 128) * 0.5
        comm_mode = meta.bytes[6]
        rssi_dbm = -130.0 + meta.bytes[7]
        return {
            "decoder": "delfi_pq_v1",
            "battery_voltage_v": round(bat_voltage_v, 3),
            "battery_temp_c": round(bat_temp_c, 2),
            "comm_mode": comm_mode,
            "rssi_dbm": rssi_dbm,
        }


def default_decoder_chain() -> tuple[SatNOGSDecoder, ...]:
    return (
        FuncubeOneDecoder(),
        FoxOneDecoder(),
        LightsailDecoder(),
        PocketqubeBeaconDecoder(),
        EseoDecoder(),
        Aausat4Decoder(),
        Gomx3Decoder(),
        SwisscubeDecoder(),
        DelfiPqDecoder(),
        GenericAx25KissDecoder(),
        GenericCwBeaconDecoder(),
    )
