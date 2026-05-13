from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from aria.integrations.hal_sidecar.protocol import (
    HalFrame,
    fresh_nonce,
    sign_frame,
)


CLIENT_DEFAULT_TIMEOUT_S = 2.0


@dataclass
class HalCommandResult:
    accepted: bool
    counter: int
    detail: str
    state: dict[str, Any]


class HalSidecarClient:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        secret: bytes,
        issuer: str = "aria",
        timeout_s: float = CLIENT_DEFAULT_TIMEOUT_S,
    ) -> None:
        if not secret or len(secret) < 16:
            raise ValueError("HAL secret must be >= 16 bytes")
        self._addr = (host, port)
        self._secret = secret
        self._issuer = issuer
        self._timeout_s = timeout_s
        self._counter = 0
        self._lock = threading.Lock()

    def _next_counter(self) -> int:
        with self._lock:
            self._counter += 1
            return self._counter

    def send(
        self, *, command: str, params: Optional[dict[str, Any]] = None,
    ) -> HalCommandResult:
        frame = HalFrame(
            counter=self._next_counter(),
            nonce=fresh_nonce(),
            timestamp_s=time.time(),
            command=command,
            params=dict(params) if params else {},
            issuer=self._issuer,
        )
        raw = sign_frame(self._secret, frame)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self._timeout_s)
        try:
            sock.sendto(raw, self._addr)
            data, _ = sock.recvfrom(8192)
        finally:
            try:
                sock.close()
            except OSError:
                pass
        envelope = json.loads(data.decode("utf-8"))
        return HalCommandResult(
            accepted=bool(envelope.get("accepted")),
            counter=int(envelope.get("counter", 0)),
            detail=str(envelope.get("detail", "")),
            state=dict(envelope.get("state") or {}),
        )

    def ping(self) -> HalCommandResult:
        return self.send(command="ping")

    def fire_thruster(self, *, burn_time_s: float) -> HalCommandResult:
        return self.send(command="thruster.fire", params={"burn_time_s": burn_time_s})

    def apply_wheel_torque(
        self, *, torque_nm: tuple[float, float, float], dt_s: float = 1.0,
    ) -> HalCommandResult:
        return self.send(
            command="wheel.torque",
            params={"torque_nm": list(torque_nm), "dt_s": dt_s},
        )

    def heater_on(self) -> HalCommandResult:
        return self.send(command="heater.on")

    def heater_off(self) -> HalCommandResult:
        return self.send(command="heater.off")

    def heater_step(self, *, dt_s: float) -> HalCommandResult:
        return self.send(command="heater.step", params={"dt_s": dt_s})

    def payload_on(self) -> HalCommandResult:
        return self.send(command="payload.on")

    def payload_off(self) -> HalCommandResult:
        return self.send(command="payload.off")
