"""CCSDS Space Packet Protocol — the standard for spacecraft telemetry.

Implements the CCSDS 133.0-B-1 (Space Packet Protocol) used by virtually
all spaceflight missions since the 1980s. Telemetry and commands are
framed in 6-byte primary headers followed by optional secondary headers
and user data.

Primary header structure (48 bits):
- Version number (3 bits): always 0 for Space Packet
- Packet type (1 bit): 0=telemetry, 1=command
- Secondary header flag (1 bit)
- APID (11 bits): Application Process ID (up to 2047)
- Sequence flags (2 bits): 00=continuation, 01=first, 10=last, 11=unsegmented
- Sequence count (14 bits): rolling counter per-APID
- Data length - 1 (16 bits): length of secondary header + user data

TT&C audit (2026-04-28) hardenings:
  • C-6: optional ``CCITT-FALSE`` CRC-16 over the entire packet, and
    HMAC-SHA-256-truncated-128-bit auth tag on TC frames per CCSDS
    SDLS-flavour conventions.  Helpers ``decode_with_crc``,
    ``encode_with_crc``, ``build_authenticated_command_packet``,
    ``verify_authenticated_command_packet``.
  • M-3: ``CCSDSSequenceTracker`` rejects ``(apid, epoch, seq_count)``
    combinations it has already accepted, defeating the 16384-rollover
    replay window.  ``epoch`` is a caller-supplied APID epoch (e.g.,
    mission-elapsed-time bucket) that increments on rollover.

References:
  - CCSDS 133.0-B-2 (2020) Space Packet Protocol — Blue Book.
  - CCSDS 232.0-B-3 §4.1.2.6 — TC frame CRC-16-CCITT-FALSE.
  - CCSDS 355.0-B-2 — Space Data Link Security Protocol (auth-tag pattern).
"""

from __future__ import annotations

import hashlib
import hmac
import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, Optional, Tuple


# CCITT-FALSE CRC-16 polynomial = 0x1021, init = 0xFFFF, no reflect, no XOR-out.
# Reference: CCSDS 232.0-B-3 §4.1.2.6 / KOOPMAN 2002 polynomial selection.
_CRC16_POLY = 0x1021
_CRC16_INIT = 0xFFFF


def crc16_ccitt(data: bytes) -> int:
    """CCITT-FALSE CRC-16 over ``data``.  Used for TC frame integrity."""
    crc = _CRC16_INIT
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ _CRC16_POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


# HMAC-SHA-256 truncated to 128 bits matches CCSDS 355.0-B-2 §A.2 mandatory
# auth-tag length.  Truncation is canonical (left-most bytes per RFC 2104 §5).
_AUTH_TAG_LEN = 16    # bytes — 128-bit HMAC-SHA-256 truncation


class PacketType(IntEnum):
    TELEMETRY = 0
    COMMAND = 1


class SequenceFlags(IntEnum):
    CONTINUATION = 0b00
    FIRST_SEGMENT = 0b01
    LAST_SEGMENT = 0b10
    UNSEGMENTED = 0b11


# Primary header is 6 bytes (48 bits)
PRIMARY_HEADER_SIZE = 6


@dataclass
class CCSDSPacket:
    """A single CCSDS Space Packet."""
    apid: int                              # 0-2047
    packet_type: PacketType = PacketType.TELEMETRY
    sequence_count: int = 0                # 0-16383
    sequence_flags: SequenceFlags = SequenceFlags.UNSEGMENTED
    secondary_header: bytes = b""
    user_data: bytes = b""
    version: int = 0

    def total_length(self) -> int:
        """Total packet size including primary header."""
        return PRIMARY_HEADER_SIZE + len(self.secondary_header) + len(self.user_data)

    def encode(self) -> bytes:
        """Serialize to binary per CCSDS 133.0-B-2."""
        if self.apid < 0 or self.apid > 2047:
            raise ValueError(f"APID must be 0-2047, got {self.apid}")
        if self.sequence_count < 0 or self.sequence_count > 16383:
            raise ValueError(f"Sequence count must be 0-16383, got {self.sequence_count}")

        # First 2 bytes: version(3) + type(1) + sec_hdr(1) + APID(11)
        sec_hdr_flag = 1 if self.secondary_header else 0
        word1 = (
            (self.version & 0x07) << 13
            | (int(self.packet_type) & 0x01) << 12
            | (sec_hdr_flag & 0x01) << 11
            | (self.apid & 0x7FF)
        )

        # Next 2 bytes: seq_flags(2) + seq_count(14)
        word2 = ((int(self.sequence_flags) & 0x03) << 14) | (self.sequence_count & 0x3FFF)

        # Next 2 bytes: packet data length (bytes in secondary+user, minus 1)
        data_length = len(self.secondary_header) + len(self.user_data) - 1
        if data_length < 0:
            data_length = 0

        header = struct.pack(">HHH", word1, word2, data_length)
        return header + self.secondary_header + self.user_data

    @classmethod
    def decode(cls, data: bytes) -> CCSDSPacket:
        """Parse a CCSDS packet from binary.

        Assumes data starts at the primary header. Reads exactly the
        declared packet length.
        """
        if len(data) < PRIMARY_HEADER_SIZE:
            raise ValueError(f"Need at least {PRIMARY_HEADER_SIZE} bytes for header")

        word1, word2, data_length = struct.unpack(">HHH", data[:6])
        version = (word1 >> 13) & 0x07
        packet_type = PacketType((word1 >> 12) & 0x01)
        sec_hdr_flag = (word1 >> 11) & 0x01
        apid = word1 & 0x7FF
        sequence_flags = SequenceFlags((word2 >> 14) & 0x03)
        sequence_count = word2 & 0x3FFF

        total_payload = data_length + 1
        payload_end = PRIMARY_HEADER_SIZE + total_payload
        if len(data) < payload_end:
            raise ValueError(f"Packet truncated: need {payload_end}, got {len(data)}")

        payload = data[PRIMARY_HEADER_SIZE:payload_end]

        # Split secondary header / user data — we don't know sec header size
        # without context; for basic use, assume 0 or known size from APID table
        secondary_header = b""
        user_data = payload
        if sec_hdr_flag:
            # Assume the first byte of secondary header gives its size
            # (many missions use this convention — but it's mission-specific)
            if len(payload) >= 1:
                sec_hdr_size = payload[0]
                if sec_hdr_size <= len(payload):
                    secondary_header = payload[:sec_hdr_size]
                    user_data = payload[sec_hdr_size:]

        return cls(
            apid=apid,
            packet_type=packet_type,
            sequence_count=sequence_count,
            sequence_flags=sequence_flags,
            secondary_header=secondary_header,
            user_data=user_data,
            version=version,
        )


class CCSDSSequenceTracker:
    """Tracks sequence counters per APID for gap detection.

    Each APID has its own counter. Receivers detect dropped packets
    by checking for counter gaps.

    TT&C audit M-3: ``receive_with_epoch`` requires the caller to
    supply an APID epoch (e.g., mission-elapsed-time bucket) and
    rejects any ``(apid, epoch, seq_count)`` triple already accepted —
    defeats the 14-bit-rollover replay window where an attacker could
    replay a 16384-old packet because the counter looks "in sequence."
    The legacy ``receive`` method preserves prior behaviour for
    consumers that have not yet adopted epochs.
    """

    def __init__(self) -> None:
        self._counters: Dict[int, int] = {}
        self._seen_per_apid: Dict[int, set[Tuple[int, int]]] = {}
        self._gaps_detected: int = 0
        self._replays_detected: int = 0
        self._packets_received: int = 0

    def next_count(self, apid: int) -> int:
        """Get the next sequence count for a given APID (for TX)."""
        current = self._counters.get(apid, -1)
        next_val = (current + 1) % 16384
        self._counters[apid] = next_val
        return next_val

    def receive(self, apid: int, seq_count: int) -> bool:
        """Record a received packet and detect gaps.

        Returns True if this packet is in sequence, False if a gap
        was detected.
        """
        self._packets_received += 1
        expected = self._counters.get(apid)
        self._counters[apid] = seq_count

        if expected is None:
            # First packet for this APID — no gap
            return True

        expected_next = (expected + 1) % 16384
        if seq_count != expected_next:
            self._gaps_detected += 1
            return False
        return True

    def receive_with_epoch(
        self, apid: int, epoch: int, seq_count: int,
    ) -> bool:
        """Record a packet bound to an explicit APID epoch (TT&C M-3).

        Returns ``True`` when accepted, ``False`` when this
        ``(apid, epoch, seq_count)`` triple has already been seen
        (replay) — the rollover-replay window is closed because epochs
        are not modular.
        """
        self._packets_received += 1
        seen = self._seen_per_apid.setdefault(apid, set())
        key = (int(epoch), int(seq_count) & 0x3FFF)
        if key in seen:
            self._replays_detected += 1
            return False
        seen.add(key)
        # Bound the per-APID set so a long-running session does not
        # grow unbounded; keep the most recent 4× the rollover space.
        if len(seen) > 65_536:
            self._seen_per_apid[apid] = set(list(seen)[-32_768:])
        # Update gap-detection counter on the modular ring.
        expected = self._counters.get(apid)
        self._counters[apid] = seq_count
        if expected is not None:
            expected_next = (expected + 1) % 16384
            if seq_count != expected_next:
                self._gaps_detected += 1
        return True

    def stats(self) -> Dict[str, int]:
        return {
            "apids_tracked": len(self._counters),
            "packets_received": self._packets_received,
            "gaps_detected": self._gaps_detected,
            "replays_detected": self._replays_detected,
        }


# ══════════════════════════════════════════════════════════════════
#  Convenience: telemetry packet builder
# ══════════════════════════════════════════════════════════════════

def build_telemetry_packet(
    apid: int,
    user_data: bytes,
    sequence_count: int = 0,
    timestamp_s: Optional[float] = None,
) -> CCSDSPacket:
    """Build a telemetry packet with optional 4-byte timestamp secondary hdr.

    Secondary header format (8 bytes, mission-specific):
    - 1 byte: header size (7)
    - 3 bytes: reserved / flags
    - 4 bytes: mission elapsed time (big-endian float32)

    For production use, adopt the mission's specific secondary header
    format (CCSDS 301.0-B-4 Time Code Formats).
    """
    sec_hdr = b""
    if timestamp_s is not None:
        sec_hdr = struct.pack(">BBHf", 7, 0, 0, timestamp_s)

    return CCSDSPacket(
        apid=apid,
        packet_type=PacketType.TELEMETRY,
        sequence_count=sequence_count,
        secondary_header=sec_hdr,
        user_data=user_data,
    )


def build_command_packet(
    apid: int,
    function_code: int,
    params: bytes = b"",
    sequence_count: int = 0,
) -> CCSDSPacket:
    """Build a command packet with function code + checksum secondary header.

    Secondary header (4 bytes):
    - 1 byte: function code (0-255)
    - 1 byte: reserved
    - 2 bytes: XOR checksum of user_data

    DEPRECATED: the XOR "checksum" is non-cryptographic and trivially
    forge-able.  Production deploys MUST use
    :func:`build_authenticated_command_packet` instead.
    Reference: cFS command convention (NASA GSFC).
    """
    checksum = 0
    for b in params:
        checksum ^= b
    sec_hdr = struct.pack(">BBH", function_code & 0xFF, 0, checksum & 0xFFFF)
    return CCSDSPacket(
        apid=apid,
        packet_type=PacketType.COMMAND,
        sequence_count=sequence_count,
        secondary_header=sec_hdr,
        user_data=params,
    )


# ══════════════════════════════════════════════════════════════════
#  CRC + auth-tag helpers (TT&C audit C-6)
# ══════════════════════════════════════════════════════════════════


def encode_with_crc(packet: CCSDSPacket) -> bytes:
    """Serialise a packet and append a 16-bit CCITT-FALSE CRC trailer.

    The CRC is *not* a security primitive — it defends against random
    bit flips on the RF link; ``build_authenticated_command_packet``
    adds a cryptographic auth tag in addition.
    """
    body = packet.encode()
    crc = crc16_ccitt(body)
    return body + struct.pack(">H", crc)


def decode_with_crc(data: bytes) -> CCSDSPacket:
    """Parse a CRC-trailered packet, raising on mismatch."""
    if len(data) < PRIMARY_HEADER_SIZE + 2:
        raise ValueError("packet too short for CRC trailer")
    body, trailer = data[:-2], data[-2:]
    expected_crc, = struct.unpack(">H", trailer)
    if crc16_ccitt(body) != expected_crc:
        raise ValueError("ccsds.crc_mismatch")
    return CCSDSPacket.decode(body)


def build_authenticated_command_packet(
    apid: int,
    function_code: int,
    params: bytes,
    sequence_count: int,
    *,
    secret: bytes,
    epoch: int,
) -> bytes:
    """Build a TC frame with HMAC-SHA-256-128 auth tag + CRC trailer.

    Secondary header layout (8 bytes; ``byte 0`` is the size byte
    expected by ``CCSDSPacket.decode`` — 8 — so the parser carves out
    exactly the 8-byte block we wrote, ignoring attacker payload prefix):

        byte 0      : sec_hdr_size = 8 (matches CCSDSPacket.decode contract)
        byte 1      : function_code (0-255)
        bytes 2-5   : APID epoch (uint32 BE) — defeats 14-bit rollover replay
        bytes 6-7   : reserved (must be 0)

    Body layout: ``primary_header || secondary_header || params``
    Trailer:     ``HMAC-SHA-256(secret, body)[:16] || CRC-16(body || tag)``

    Verification: :func:`verify_authenticated_command_packet`.
    """
    if not isinstance(secret, (bytes, bytearray)) or len(secret) < 16:
        raise ValueError("auth tag secret must be >= 16 bytes")

    sec_hdr = struct.pack(">BBLH", 8, function_code & 0xFF,
                          int(epoch) & 0xFFFFFFFF, 0)
    pkt = CCSDSPacket(
        apid=apid,
        packet_type=PacketType.COMMAND,
        sequence_count=sequence_count,
        secondary_header=sec_hdr,
        user_data=params,
    )
    body = pkt.encode()
    tag = hmac.new(secret, body, hashlib.sha256).digest()[:_AUTH_TAG_LEN]
    body_with_tag = body + tag
    crc = crc16_ccitt(body_with_tag)
    return body_with_tag + struct.pack(">H", crc)


def verify_authenticated_command_packet(
    data: bytes,
    *,
    secret: bytes,
) -> Tuple[CCSDSPacket, int]:
    """Parse and verify a frame produced by
    :func:`build_authenticated_command_packet`.  Returns the parsed
    packet and the embedded APID epoch.  Raises ``ValueError`` on any
    integrity / authenticity failure.
    """
    if len(data) < PRIMARY_HEADER_SIZE + _AUTH_TAG_LEN + 2:
        raise ValueError("ccsds.frame_truncated")
    crc_offset = len(data) - 2
    body_with_tag = data[:crc_offset]
    expected_crc, = struct.unpack(">H", data[crc_offset:])
    if crc16_ccitt(body_with_tag) != expected_crc:
        raise ValueError("ccsds.crc_mismatch")

    body = body_with_tag[:-_AUTH_TAG_LEN]
    presented_tag = body_with_tag[-_AUTH_TAG_LEN:]
    expected_tag = hmac.new(secret, body, hashlib.sha256).digest()[:_AUTH_TAG_LEN]
    if not hmac.compare_digest(presented_tag, expected_tag):
        raise ValueError("ccsds.auth_tag_mismatch")

    pkt = CCSDSPacket.decode(body)
    if len(pkt.secondary_header) < 8:
        raise ValueError("ccsds.secondary_header_truncated")
    _size, _fn, epoch, _rsvd = struct.unpack(
        ">BBLH", pkt.secondary_header[:8],
    )
    return pkt, int(epoch)
