from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import structlog

from aria.integrations.hal_sidecar.actuators import ActuatorBank
from aria.integrations.hal_sidecar.protocol import (
    HalReply,
    parse_and_verify_frame,
)

logger = structlog.get_logger()

NONCE_WINDOW = 4096
SOCKET_RECV_BYTES = 8192
SELECT_TIMEOUT_S = 0.25


@dataclass
class _ReplayGuard:
    last_counter_per_issuer: dict[str, int] = field(default_factory=dict)
    seen_nonces: set[str] = field(default_factory=set)
    seen_nonces_order: list[str] = field(default_factory=list)

    def accept(self, *, issuer: str, counter: int, nonce: str) -> tuple[bool, str]:
        if nonce in self.seen_nonces:
            return False, "nonce_replay"
        last = self.last_counter_per_issuer.get(issuer, 0)
        if counter <= last:
            return False, "counter_not_monotonic"
        self.last_counter_per_issuer[issuer] = counter
        self.seen_nonces.add(nonce)
        self.seen_nonces_order.append(nonce)
        if len(self.seen_nonces_order) > NONCE_WINDOW:
            evicted = self.seen_nonces_order.pop(0)
            self.seen_nonces.discard(evicted)
        return True, "ok"


def _reply_bytes(reply: HalReply) -> bytes:
    payload = {
        "v": 1,
        "counter": reply.counter,
        "accepted": reply.accepted,
        "detail": reply.detail,
        "state": reply.state_snapshot,
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


class HalSidecarServer:
    def __init__(
        self,
        *,
        bind_host: str,
        bind_port: int,
        secret: bytes,
        bank: Optional[ActuatorBank] = None,
        max_frame_age_s: float = 60.0,
    ) -> None:
        if not secret or len(secret) < 16:
            raise ValueError("HAL secret must be >= 16 bytes")
        self._bind_host = bind_host
        self._bind_port = bind_port
        self._secret = secret
        self._bank = bank or ActuatorBank()
        self._max_frame_age_s = max_frame_age_s
        self._sock: Optional[socket.socket] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._guard = _ReplayGuard()
        self._frames_accepted = 0
        self._frames_rejected = 0

    @property
    def bank(self) -> ActuatorBank:
        return self._bank

    @property
    def stats(self) -> dict[str, int]:
        return {
            "accepted": self._frames_accepted,
            "rejected": self._frames_rejected,
        }

    @property
    def address(self) -> tuple[str, int]:
        if self._sock is None:
            return (self._bind_host, self._bind_port)
        host, port = self._sock.getsockname()[:2]
        return (host, port)

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("HalSidecarServer already started")
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._bind_host, self._bind_port))
        self._sock.settimeout(SELECT_TIMEOUT_S)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._serve_forever, name="hal-sidecar", daemon=True,
        )
        self._thread.start()
        logger.info(
            "aria.hal_sidecar.started",
            bind=f"{self.address[0]}:{self.address[1]}",
        )

    def stop(self, *, timeout_s: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)
            self._thread = None
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        logger.info("aria.hal_sidecar.stopped", stats=self.stats)

    def _serve_forever(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                data, peer = self._sock.recvfrom(SOCKET_RECV_BYTES)
            except socket.timeout:
                continue
            except OSError:
                break
            self._handle_packet(data, peer)

    def _handle_packet(self, data: bytes, peer: tuple) -> None:
        verdict = parse_and_verify_frame(
            data, self._secret, max_age_s=self._max_frame_age_s,
        )
        if not verdict.accepted or verdict.frame is None:
            self._frames_rejected += 1
            logger.warning(
                "aria.hal_sidecar.frame_rejected",
                peer=f"{peer[0]}:{peer[1]}",
                reason=verdict.reason,
            )
            self._send_nak(peer, counter=0, detail=f"reject:{verdict.reason}")
            return
        frame = verdict.frame
        ok_replay, replay_reason = self._guard.accept(
            issuer=frame.issuer, counter=frame.counter, nonce=frame.nonce,
        )
        if not ok_replay:
            self._frames_rejected += 1
            logger.warning(
                "aria.hal_sidecar.frame_replay",
                peer=f"{peer[0]}:{peer[1]}",
                reason=replay_reason,
                counter=frame.counter,
                issuer=frame.issuer,
            )
            self._send_nak(peer, counter=frame.counter, detail=f"replay:{replay_reason}")
            return
        accepted, detail = self._bank.dispatch(
            command=frame.command, params=frame.params, counter=frame.counter,
        )
        snap = self._bank.snapshot_dict()
        reply = HalReply(
            counter=frame.counter,
            accepted=accepted,
            detail=detail,
            state_snapshot=snap,
        )
        self._send_reply(peer, reply)
        if accepted:
            self._frames_accepted += 1
            logger.info(
                "aria.hal_sidecar.frame_dispatched",
                command=frame.command,
                counter=frame.counter,
                issuer=frame.issuer,
                detail=detail,
            )
        else:
            self._frames_rejected += 1
            logger.warning(
                "aria.hal_sidecar.command_failed",
                command=frame.command,
                counter=frame.counter,
                detail=detail,
            )

    def _send_reply(self, peer: tuple, reply: HalReply) -> None:
        if self._sock is None:
            return
        try:
            self._sock.sendto(_reply_bytes(reply), peer)
        except OSError as exc:
            logger.warning("aria.hal_sidecar.reply_send_failed", error=str(exc))

    def _send_nak(self, peer: tuple, *, counter: int, detail: str) -> None:
        self._send_reply(peer, HalReply(counter=counter, accepted=False, detail=detail))
